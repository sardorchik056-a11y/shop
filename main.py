import telebot
from telebot import types
import sqlite3
import requests
from datetime import date, datetime

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────

BOT_TOKEN      = "8610804137:AAFkdrZIDRAsdhn4fZP51-rcnrI5C8d4xpg"
CRYPTO_TOKEN   = "582363:AALEf7JOugnrQyrkMHzH5UrO7pdOjjYnTQy"   # токен от @CryptoBot → @send
CRYPTO_API_URL = "https://pay.crypt.bot/api"  # mainnet
# Для теста: "https://testnet-pay.crypt.bot/api"

ADMIN_IDS = {8118184388}  # ← ваш Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)

# ─────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────

def init_db():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            balance     REAL    DEFAULT 0.0,
            joined_date TEXT    DEFAULT (date('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id      INTEGER PRIMARY KEY,
            name    TEXT,
            price   REAL,
            stock   INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            product_id  INTEGER,
            amount      REAL,
            date        TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id  TEXT PRIMARY KEY,
            user_id     INTEGER,
            amount      REAL,
            status      TEXT DEFAULT 'pending'
        )
    """)
    # дефолтные товары
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO products (id, name, price, stock) VALUES (?,?,?,?)", [
            (1, "Авторег",  5.0, 100),
            (2, "Токен",    5.0, 100),
            (3, "QR-код",   5.0, 100),
        ])
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("shop.db")

def get_or_create_user(user_id, username, full_name):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id,username,full_name) VALUES (?,?,?)",
                  (user_id, username or "", full_name or ""))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    conn.close()
    return {"user_id": row[0], "username": row[1] or "—",
            "full_name": row[2] or "—", "balance": row[3], "joined": row[4]}

def get_products():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id,name,price,stock FROM products")
    rows = c.fetchall()
    conn.close()
    return rows

def get_product(pid):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id,name,price,stock FROM products WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    return row

def update_product(pid, price=None, stock=None):
    conn = db()
    c = conn.cursor()
    if price is not None:
        c.execute("UPDATE products SET price=? WHERE id=?", (price, pid))
    if stock is not None:
        c.execute("UPDATE products SET stock=? WHERE id=?", (stock, pid))
    conn.commit()
    conn.close()

def days_in_project(joined):
    try:
        return (date.today() - date.fromisoformat(joined)).days
    except:
        return 0

def get_stats(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM purchases WHERE user_id=?", (user_id,))
    orders, spent = c.fetchone()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    conn.close()
    return orders, spent, total_users

def get_history(user_id):
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT p.name, pu.amount, pu.date
        FROM purchases pu JOIN products p ON pu.product_id=p.id
        WHERE pu.user_id=? ORDER BY pu.id DESC LIMIT 10
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────
#  CRYPTOBOT API
# ─────────────────────────────────────────

def create_invoice(amount: float, user_id: int) -> dict | None:
    try:
        r = requests.post(
            f"{CRYPTO_API_URL}/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
            json={
                "asset": "USDT",
                "amount": str(amount),
                "description": f"Пополнение баланса — {amount}$",
                "payload": str(user_id),
                "allow_comments": False,
                "allow_anonymous": False,
                "expires_in": 3600,
            },
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            inv = data["result"]
            conn = db()
            conn.execute("INSERT INTO invoices (invoice_id,user_id,amount) VALUES (?,?,?)",
                         (str(inv["invoice_id"]), user_id, amount))
            conn.commit()
            conn.close()
            return inv
    except Exception as e:
        print("CryptoBot error:", e)
    return None

def check_invoice(invoice_id: str) -> str:
    try:
        r = requests.get(
            f"{CRYPTO_API_URL}/getInvoices",
            headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
            params={"invoice_ids": invoice_id},
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            items = data["result"].get("items", [])
            if items:
                return items[0]["status"]
    except Exception as e:
        print("CryptoBot check error:", e)
    return "unknown"


# ─────────────────────────────────────────
#  TEXT BUILDERS
# ─────────────────────────────────────────

def text_main(u):
    days = days_in_project(u["joined"])
    uname = f"@{u['username']}" if u["username"] != "—" else "не указан"
    return (
        f"👤 <b>Имя:</b> {u['full_name']}\n"
        f"🆔 <b>ID:</b> <b>{u['user_id']}</b>\n"
        f"📎 <b>Username:</b> <b>{uname}</b>\n"
        f"💎 <b>Баланс:</b> <b>{u['balance']:.2f}$</b>\n"
        f"🗓 <b>В проекте:</b> <b>{days} дн.</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Выберите раздел:</b>"
    )

def kb_main():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛒 Купить",           callback_data="menu_buy"),
        types.InlineKeyboardButton("💰 Баланс",           callback_data="menu_balance"),
        types.InlineKeyboardButton("📊 Статистика",       callback_data="menu_stats"),
        types.InlineKeyboardButton("📋 История покупок",  callback_data="menu_history"),
        types.InlineKeyboardButton("🎧 Поддержка",        callback_data="menu_support"),
    )
    return kb

def kb_back():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    return kb


# ─────────────────────────────────────────
#  /start
# ─────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg: types.Message):
    u = get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    bot.send_message(msg.chat.id, text_main(u), parse_mode="HTML", reply_markup=kb_main())


# ─────────────────────────────────────────
#  BACK TO MAIN
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def cb_back(call: types.CallbackQuery):
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    bot.edit_message_text(text_main(u), call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb_main())


# ─────────────────────────────────────────
#  BALANCE
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_balance")
def cb_balance(call: types.CallbackQuery):
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ 5$",   callback_data="topup_5"),
        types.InlineKeyboardButton("➕ 10$",  callback_data="topup_10"),
        types.InlineKeyboardButton("➕ 20$",  callback_data="topup_20"),
        types.InlineKeyboardButton("➕ 50$",  callback_data="topup_50"),
    )
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    text = (
        f"💰 <b>Баланс</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>Текущий баланс:</b> <b>{u['balance']:.2f}$</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Выберите сумму пополнения (USDT):</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_"))
def cb_topup(call: types.CallbackQuery):
    amount = float(call.data.split("_")[1])
    inv = create_invoice(amount, call.from_user.id)
    if not inv:
        bot.answer_callback_query(call.id, "❌ Ошибка создания счёта, попробуйте позже", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("💳 Оплатить", url=inv["bot_invoice_url"]),
        types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv['invoice_id']}"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="menu_balance"),
    )
    text = (
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Сумма:</b> <b>{amount}$</b>\n"
        f"🪙 <b>Валюта:</b> <b>USDT</b>\n"
        f"⏱ <b>Действует:</b> <b>1 час</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Нажмите «Оплатить», затем «Проверить оплату»</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def cb_check(call: types.CallbackQuery):
    invoice_id = call.data.split("_", 1)[1]
    status = check_invoice(invoice_id)

    if status == "paid":
        conn = db()
        c_db = conn.cursor()
        c_db.execute("SELECT user_id, amount, status FROM invoices WHERE invoice_id=?", (invoice_id,))
        row = c_db.fetchone()
        if row and row[2] == "pending":
            c_db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (row[1], row[0]))
            c_db.execute("UPDATE invoices SET status='paid' WHERE invoice_id=?", (invoice_id,))
            conn.commit()
            conn.close()
            u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
            bot.edit_message_text(
                f"✅ <b>Баланс пополнен!</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 <b>Новый баланс:</b> <b>{u['balance']:.2f}$</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=kb_back()
            )
        else:
            conn.close()
            bot.answer_callback_query(call.id, "✅ Уже зачислено ранее", show_alert=True)
    elif status == "active":
        bot.answer_callback_query(call.id, "⏳ Оплата ещё не поступила", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ Счёт истёк или ошибка", show_alert=True)


# ─────────────────────────────────────────
#  BUY
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_buy")
def cb_buy_menu(call: types.CallbackQuery):
    products = get_products()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in products:
        pid, name, price, stock = p
        stock_txt = f"{stock} шт." if stock > 0 else "❌ нет"
        kb.add(types.InlineKeyboardButton(
            f"{'🛒' if stock>0 else '🚫'} {name} — {price}$ | {stock_txt}",
            callback_data=f"product_{pid}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"))
    bot.edit_message_text(
        f"🛒 <b>Магазин</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Выберите товар:</b>",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("product_"))
def cb_product(call: types.CallbackQuery):
    pid = int(call.data.split("_")[1])
    p = get_product(pid)
    if not p:
        bot.answer_callback_query(call.id, "Товар не найден", show_alert=True)
        return
    _, name, price, stock = p
    kb = types.InlineKeyboardMarkup(row_width=1)
    if stock > 0:
        kb.add(types.InlineKeyboardButton(f"✅ Купить за {price}$", callback_data=f"confirm_{pid}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_buy"))
    text = (
        f"📦 <b>{name}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Цена:</b> <b>{price}$</b>\n"
        f"📦 <b>Остаток:</b> <b>{stock} шт.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{'<b>Нажмите «Купить» для оформления</b>' if stock > 0 else '<b>❌ Товар закончился</b>'}"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_"))
def cb_confirm(call: types.CallbackQuery):
    pid = int(call.data.split("_")[1])
    p = get_product(pid)
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    if not p or p[3] <= 0:
        bot.answer_callback_query(call.id, "❌ Товар закончился", show_alert=True)
        return
    _, name, price, stock = p
    if u["balance"] < price:
        bot.answer_callback_query(call.id,
            f"❌ Недостаточно средств!\nНужно: {price}$\nВаш баланс: {u['balance']:.2f}$",
            show_alert=True)
        return
    # Списываем
    conn = db()
    c_db = conn.cursor()
    c_db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (price, u["user_id"]))
    c_db.execute("UPDATE products SET stock=stock-1 WHERE id=?", (pid,))
    c_db.execute("INSERT INTO purchases (user_id,product_id,amount) VALUES (?,?,?)",
                 (u["user_id"], pid, price))
    conn.commit()
    conn.close()
    new_balance = u["balance"] - price
    bot.edit_message_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Товар:</b> <b>{name}</b>\n"
        f"💸 <b>Списано:</b> <b>{price}$</b>\n"
        f"💎 <b>Остаток:</b> <b>{new_balance:.2f}$</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb_back()
    )


# ─────────────────────────────────────────
#  STATS
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_stats")
def cb_stats(call: types.CallbackQuery):
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    orders, spent, total_users = get_stats(u["user_id"])
    days = days_in_project(u["joined"])
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Покупок:</b> <b>{orders}</b>\n"
        f"💸 <b>Потрачено:</b> <b>{spent:.2f}$</b>\n"
        f"💎 <b>Баланс:</b> <b>{u['balance']:.2f}$</b>\n"
        f"🗓 <b>В проекте:</b> <b>{days} дн.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Пользователей в боте:</b> <b>{total_users}</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb_back())


# ─────────────────────────────────────────
#  HISTORY
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_history")
def cb_history(call: types.CallbackQuery):
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    rows = get_history(u["user_id"])
    if not rows:
        text = (
            f"📋 <b>История покупок</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>😔 Покупок пока нет</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        lines = ""
        for i, (name, amount, dt) in enumerate(rows, 1):
            lines += f"<b>{i}.</b> <b>{name}</b> — <b>{amount:.2f}$</b> · <b>{dt[:10]}</b>\n"
        text = (
            f"📋 <b>История покупок</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{lines}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Последние {len(rows)} операций</b>"
        )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb_back())


# ─────────────────────────────────────────
#  SUPPORT
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_support")
def cb_support(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✉️ Написать оператору", url="https://t.me/username"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"),
    )
    text = (
        f"🎧 <b>Поддержка</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Мы рады помочь!</b>\n\n"
        f"⏱ <b>Время ответа:</b> <b>до 15 минут</b>\n"
        f"🕐 <b>Режим работы:</b> <b>10:00 – 22:00</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)


# ─────────────────────────────────────────
#  ADMIN PANEL
# ─────────────────────────────────────────

def is_admin(user_id):
    return user_id in ADMIN_IDS

@bot.message_handler(commands=["admin"])
def cmd_admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📦 Управление товарами", callback_data="adm_products"),
        types.InlineKeyboardButton("💰 Начислить баланс",    callback_data="adm_topup_form"),
        types.InlineKeyboardButton("📊 Общая статистика",    callback_data="adm_stats"),
    )
    bot.send_message(msg.chat.id,
        f"🔧 <b>Админ-панель</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Выберите действие:</b>",
        parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "adm_products")
def cb_adm_products(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    products = get_products()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in products:
        pid, name, price, stock = p
        kb.add(types.InlineKeyboardButton(
            f"✏️ {name} | {price}$ | {stock} шт.",
            callback_data=f"adm_edit_{pid}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text(
        f"📦 <b>Товары</b>\n\n<b>Выберите товар для редактирования:</b>",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_edit_"))
def cb_adm_edit(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    p = get_product(pid)
    if not p: return
    _, name, price, stock = p
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💵 Изменить цену",    callback_data=f"adm_price_{pid}"),
        types.InlineKeyboardButton("📦 Изменить остаток", callback_data=f"adm_stock_{pid}"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="adm_products"),
    )
    bot.edit_message_text(
        f"✏️ <b>Редактирование: {name}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Цена:</b> <b>{price}$</b>\n"
        f"📦 <b>Остаток:</b> <b>{stock} шт.</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

# Хранилище состояний
admin_states = {}

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_price_"))
def cb_adm_set_price(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    admin_states[call.from_user.id] = {"action": "set_price", "pid": pid, "msg_id": call.message.message_id}
    bot.edit_message_text(
        f"💵 <b>Введите новую цену (в $):</b>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_stock_"))
def cb_adm_set_stock(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    admin_states[call.from_user.id] = {"action": "set_stock", "pid": pid, "msg_id": call.message.message_id}
    bot.edit_message_text(
        f"📦 <b>Введите новый остаток (шт.):</b>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_topup_form")
def cb_adm_topup_form(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    admin_states[call.from_user.id] = {"action": "topup", "msg_id": call.message.message_id}
    bot.edit_message_text(
        f"💰 <b>Введите: user_id сумма</b>\n<b>Пример:</b> <code>123456789 10</code>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_stats")
def cb_adm_stats(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    conn = db()
    c_db = conn.cursor()
    c_db.execute("SELECT COUNT(*) FROM users")
    total_users = c_db.fetchone()[0]
    c_db.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM purchases")
    total_orders, total_revenue = c_db.fetchone()
    conn.close()
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text(
        f"📊 <b>Общая статистика</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Пользователей:</b> <b>{total_users}</b>\n"
        f"🛒 <b>Покупок:</b> <b>{total_orders}</b>\n"
        f"💸 <b>Выручка:</b> <b>{total_revenue:.2f}$</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_back")
def cb_adm_back(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📦 Управление товарами", callback_data="adm_products"),
        types.InlineKeyboardButton("💰 Начислить баланс",    callback_data="adm_topup_form"),
        types.InlineKeyboardButton("📊 Общая статистика",    callback_data="adm_stats"),
    )
    bot.edit_message_text(
        f"🔧 <b>Админ-панель</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Выберите действие:</b>",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.message_handler(func=lambda m: m.from_user.id in admin_states and is_admin(m.from_user.id))
def handle_admin_input(msg: types.Message):
    state = admin_states.pop(msg.from_user.id)
    action = state["action"]

    if action == "set_price":
        try:
            price = float(msg.text.strip())
            update_product(state["pid"], price=price)
            p = get_product(state["pid"])
            bot.send_message(msg.chat.id,
                f"✅ <b>Цена обновлена!</b>\n<b>{p[1]}</b> → <b>{p[2]}$</b>",
                parse_mode="HTML")
        except:
            bot.send_message(msg.chat.id, "❌ <b>Неверный формат. Введите число.</b>", parse_mode="HTML")

    elif action == "set_stock":
        try:
            stock = int(msg.text.strip())
            update_product(state["pid"], stock=stock)
            p = get_product(state["pid"])
            bot.send_message(msg.chat.id,
                f"✅ <b>Остаток обновлён!</b>\n<b>{p[1]}</b> → <b>{p[3]} шт.</b>",
                parse_mode="HTML")
        except:
            bot.send_message(msg.chat.id, "❌ <b>Неверный формат. Введите целое число.</b>", parse_mode="HTML")

    elif action == "topup":
        try:
            parts = msg.text.strip().split()
            uid, amount = int(parts[0]), float(parts[1])
            conn = db()
            conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
            conn.commit()
            conn.close()
            bot.send_message(msg.chat.id,
                f"✅ <b>Начислено {amount}$ пользователю {uid}</b>", parse_mode="HTML")
            try:
                bot.send_message(uid,
                    f"💰 <b>Вам начислено {amount}$</b>\n<b>Пополнение от администратора</b>",
                    parse_mode="HTML")
            except:
                pass
        except:
            bot.send_message(msg.chat.id, "❌ <b>Формат: user_id сумма</b>", parse_mode="HTML")


# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("🤖 Бот запущен...")
    bot.infinity_polling()
