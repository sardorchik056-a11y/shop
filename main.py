import telebot
from telebot import types
import sqlite3
import requests
from datetime import date, datetime

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────

BOT_TOKEN      = "8607716276:AAH-zY7Zk0hrDLFRdWSqp9IiXxiaBbWJbfM"
CRYPTO_TOKEN   = "582363:AALEf7JOugnrQyrkMHzH5UrO7pdOjjYnTQy"
CRYPTO_API_URL = "https://pay.crypt.bot/api"

ADMIN_IDS    = {8118184388}
SUPPORT_URL  = "https://t.me/Xeltryx"   # ← ссылка на поддержку

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
            stock   INTEGER,
            min_qty INTEGER DEFAULT 10
        )
    """)
    # миграция для существующей БД
    try:
        c.execute("ALTER TABLE products ADD COLUMN min_qty INTEGER DEFAULT 10")
    except:
        pass
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
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO products (id, name, price, stock) VALUES (?,?,?,?)", [
            (1, "Авторег", 5.0, 100),
            (2, "Токен",   5.0, 100),
            (3, "Json",    5.0, 100),
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
    c.execute("SELECT id,name,price,stock,min_qty FROM products")
    rows = c.fetchall()
    conn.close()
    return rows

def get_product(pid):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id,name,price,stock,min_qty FROM products WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    return row

def update_product(pid, price=None, stock=None, min_qty=None):
    conn = db()
    c = conn.cursor()
    if price is not None:
        c.execute("UPDATE products SET price=? WHERE id=?", (price, pid))
    if stock is not None:
        c.execute("UPDATE products SET stock=? WHERE id=?", (stock, pid))
    if min_qty is not None:
        c.execute("UPDATE products SET min_qty=? WHERE id=?", (min_qty, pid))
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

def create_invoice(amount: float, user_id: int):
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
#  UI HELPERS
# ─────────────────────────────────────────

LINE  = "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰"
LINE2 = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─"

# Эмодзи для каждого товара по названию
PRODUCT_EMOJI = {
    "Авторег": "🤖",
    "Токен":   "🔑",
    "Json":    "🗂",
}

def product_emoji(name: str) -> str:
    return PRODUCT_EMOJI.get(name, "📦")

def text_main(u):
    days  = days_in_project(u["joined"])
    uname = f"@{u['username']}" if u["username"] != "—" else "не указан"
    return (
        f"┌─────────────────────┐\n"
        f"│     💼  <b>ПРОФИЛЬ</b>     │\n"
        f"├─────────────────────┤\n"
        f"│ 👤 <b>Имя:</b>  {u['full_name']}\n"
        f"│ 🆔 <b>ID:</b>  <code>{u['user_id']}</code>\n"
        f"│ 📎 <b>Ник:</b>  {uname}\n"
        f"├─────────────────────┤\n"
        f"│ 💎 <b>Баланс:</b>  <b>{u['balance']:.2f} $</b>\n"
        f"│ 🗓 <b>В проекте:</b>  <b>{days} дн.</b>\n"
        f"└─────────────────────┘\n\n"
    )

def kb_main():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("📄  Купить",     callback_data="menu_buy"),
        types.InlineKeyboardButton("💎  Баланс",     callback_data="menu_balance"),
    )
    kb.row(
        types.InlineKeyboardButton("📊  Статистика", callback_data="menu_stats"),
        types.InlineKeyboardButton("📋  История",    callback_data="menu_history"),
    )
    kb.row(
        types.InlineKeyboardButton("❗️  Поддержка",  url=SUPPORT_URL),
    )
    return kb

def kb_back():
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("🔙 Главное меню", callback_data="back_main"))
    return kb


# ─────────────────────────────────────────
#  /start
# ─────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg: types.Message):
    u = get_or_create_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    bot.send_message(msg.chat.id, text_main(u), parse_mode="HTML", reply_markup=kb_main())


# ─────────────────────────────────────────
#  BACK
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
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("➕ 5$",  callback_data="topup_5"),
        types.InlineKeyboardButton("➕ 10$", callback_data="topup_10"),
    )
    kb.row(
        types.InlineKeyboardButton("➕ 20$", callback_data="topup_20"),
        types.InlineKeyboardButton("➕ 50$", callback_data="topup_50"),
    )
    kb.row(types.InlineKeyboardButton("🔙 Главное меню", callback_data="back_main"))
    text = (
        f"┌─────────────────────┐\n"
        f"│     💰  <b>БАЛАНС</b>          │\n"
        f"├─────────────────────┤\n"
        f"│ 💎 <b>Текущий баланс:</b>\n"
        f"│     <b>{u['balance']:.2f} $</b>\n"
        f"├─────────────────────┤\n"
        f"│ Выберите сумму 👇\n"
        f"└─────────────────────┘"
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
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("💳 Оплатить", url=inv["bot_invoice_url"]))
    kb.row(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv['invoice_id']}"))
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_balance"))
    text = (
        f"┌─────────────────────┐\n"
        f"│    💳  <b>ПОПОЛНЕНИЕ</b>        │\n"
        f"├─────────────────────┤\n"
        f"│ 💵 <b>Сумма:</b>  <b>{amount} $</b>\n"
        f"│ 🪙 <b>Валюта:</b>  <b>USDT</b>\n"
        f"│ ⏱ <b>Срок:</b>  <b>1 час</b>\n"
        f"├─────────────────────┤\n"
        f"│ 1️⃣ Нажмите <b>«Оплатить»</b>\n"
        f"│ 2️⃣ Нажмите <b>«Проверить»</b>\n"
        f"└─────────────────────┘"
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
                f"┌─────────────────────┐\n"
                f"│   ✅  <b>ОПЛАТА ПРИНЯТА</b>    │\n"
                f"├─────────────────────┤\n"
                f"│ 💰 <b>Зачислено:</b>  <b>{row[1]} $</b>\n"
                f"│ 💎 <b>Баланс:</b>  <b>{u['balance']:.2f} $</b>\n"
                f"└─────────────────────┘",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=kb_back()
            )
            # уведомление всем админам
            uname = f"@{u['username']}" if u['username'] != "—" else "без ника"
            admin_text = (
                f"┌─────────────────────┐\n"
                f"│   💸  <b>ПОПОЛНЕНИЕ</b>         │\n"
                f"├─────────────────────┤\n"
                f"│ 👤 <b>Юзер:</b>  {u['full_name']}\n"
                f"│ 📎 <b>Ник:</b>  {uname}\n"
                f"│ 🆔 <b>ID:</b>  <code>{u['user_id']}</code>\n"
                f"├─────────────────────┤\n"
                f"│ 💰 <b>Сумма:</b>  <b>{row[1]} $</b>\n"
                f"│ 💎 <b>Баланс:</b>  <b>{u['balance']:.2f} $</b>\n"
                f"└─────────────────────┘"
            )
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except:
                    pass
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
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)

    lines = ""
    for pid, name, price, stock, min_qty in products:
        ico = product_emoji(name)
        status = "✅ В наличии" if stock > 0 else "❌ Нет"
        lines += f"│ {ico} <b>{name}</b>\n│    💵 <b>{price}$</b>  •  📦 <b>{stock} шт.</b>  •  {status}\n"

    kb = types.InlineKeyboardMarkup()
    for pid, name, price, stock, min_qty in products:
        ico = product_emoji(name)
        if stock > 0:
            kb.row(types.InlineKeyboardButton(
                f"{ico} {name}  —  {price}$",
                callback_data=f"product_{pid}"
            ))
        else:
            kb.row(types.InlineKeyboardButton(
                f"🚫 {name}  —  нет в наличии",
                callback_data=f"product_{pid}"
            ))
    kb.row(types.InlineKeyboardButton("🔙 Главное меню", callback_data="back_main"))

    text = (
        f"┌─────────────────────┐\n"
        f"│     🛒  <b>МАГАЗИН</b>          │\n"
        f"├─────────────────────┤\n"
        f"│ 💎 <b>Ваш баланс:</b>  <b>{u['balance']:.2f}$</b>\n"
        f"├─────────────────────┤\n"
        f"{lines}"
        f"└─────────────────────┘\n\n"
        f"<b>Выберите товар 👇</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("product_") and len(c.data.split("_")) == 2)
def cb_product(call: types.CallbackQuery):
    pid = int(call.data.split("_")[1])
    p = get_product(pid)
    if not p:
        bot.answer_callback_query(call.id, "Товар не найден", show_alert=True)
        return
    _, name, price, stock, min_qty = p
    ico = product_emoji(name)
    avail = "✅ В наличии" if stock > 0 else "❌ Нет в наличии"
    total = round(price * min_qty, 2)

    kb = types.InlineKeyboardMarkup()
    if stock > 0:
        kb.row(
            types.InlineKeyboardButton("➖", callback_data=f"qty_{pid}_{max(min_qty, min_qty)}"),
            types.InlineKeyboardButton(f"  {min_qty} шт.  ", callback_data="noop"),
            types.InlineKeyboardButton("➕", callback_data=f"qty_{pid}_{min_qty + min_qty}"),
        )
        kb.row(types.InlineKeyboardButton(
            f"✅ Купить {min_qty} шт. за {total}$",
            callback_data=f"confirm_{pid}_{min_qty}"
        ))
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_buy"))

    text = (
        f"┌─────────────────────┐\n"
        f"│  {ico}  <b>{name}</b>\n"
        f"├─────────────────────┤\n"
        f"│ 💵 <b>Цена за 1 шт.:</b>  <b>{price}$</b>\n"
        f"│ 📦 <b>Остаток:</b>  <b>{stock} шт.</b>\n"
        f"│ 🔢 <b>Мин. покупка:</b>  <b>{min_qty} шт.</b>\n"
        f"│ 🔖 <b>Статус:</b>  {avail}\n"
        f"└─────────────────────┘\n\n"
        f"{'<b>Выберите количество 👇</b>' if stock > 0 else '<b>Товар временно недоступен</b>'}"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("qty_"))
def cb_qty(call: types.CallbackQuery):
    parts = call.data.split("_")
    pid, qty = int(parts[1]), int(parts[2])
    p = get_product(pid)
    if not p:
        return
    _, name, price, stock, min_qty = p
    ico = product_emoji(name)
    # ограничения: не ниже min_qty, не выше stock
    qty = max(min_qty, min(qty, stock))
    total = round(price * qty, 2)

    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("➖", callback_data=f"qty_{pid}_{max(min_qty, qty - min_qty)}"),
        types.InlineKeyboardButton(f"  {qty} шт.  ", callback_data="noop"),
        types.InlineKeyboardButton("➕", callback_data=f"qty_{pid}_{min(stock, qty + min_qty)}"),
    )
    kb.row(types.InlineKeyboardButton(
        f"✅ Купить {qty} шт. за {total}$",
        callback_data=f"confirm_{pid}_{qty}"
    ))
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="menu_buy"))

    avail = "✅ В наличии" if stock > 0 else "❌ Нет в наличии"
    text = (
        f"┌─────────────────────┐\n"
        f"│  {ico}  <b>{name}</b>\n"
        f"├─────────────────────┤\n"
        f"│ 💵 <b>Цена за 1 шт.:</b>  <b>{price}$</b>\n"
        f"│ 📦 <b>Остаток:</b>  <b>{stock} шт.</b>\n"
        f"│ 🔢 <b>Мин. покупка:</b>  <b>{min_qty} шт.</b>\n"
        f"│ 🔖 <b>Статус:</b>  {avail}\n"
        f"└─────────────────────┘\n\n"
        f"<b>Выбрано:</b>  <b>{qty} шт.</b>  →  <b>{total}$</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_"))
def cb_confirm(call: types.CallbackQuery):
    parts = call.data.split("_")
    pid, qty = int(parts[1]), int(parts[2])
    p = get_product(pid)
    u = get_or_create_user(call.from_user.id, call.from_user.username, call.from_user.full_name)
    if not p or p[3] < qty:
        bot.answer_callback_query(call.id, "❌ Недостаточно товара на складе", show_alert=True)
        return
    _, name, price, stock, min_qty = p
    ico = product_emoji(name)
    total = round(price * qty, 2)
    if u["balance"] < total:
        bot.answer_callback_query(
            call.id,
            f"❌ Недостаточно средств!\nНужно: {total}$  |  Баланс: {u['balance']:.2f}$",
            show_alert=True
        )
        return
    conn = db()
    c_db = conn.cursor()
    c_db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (total, u["user_id"]))
    c_db.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, pid))
    c_db.execute("INSERT INTO purchases (user_id,product_id,amount) VALUES (?,?,?)",
                 (u["user_id"], pid, total))
    conn.commit()
    conn.close()
    new_balance = u["balance"] - total
    bot.edit_message_text(
        f"┌─────────────────────┐\n"
        f"│   ✅  <b>ПОКУПКА УСПЕШНА</b>   │\n"
        f"├─────────────────────┤\n"
        f"│ {ico} <b>Товар:</b>  <b>{name}</b>\n"
        f"│ 🔢 <b>Количество:</b>  <b>{qty} шт.</b>\n"
        f"│ 💸 <b>Списано:</b>  <b>{total}$</b>\n"
        f"│ 💎 <b>Баланс:</b>  <b>{new_balance:.2f}$</b>\n"
        f"└─────────────────────┘",
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
        f"┌─────────────────────┐\n"
        f"│    📊  <b>СТАТИСТИКА</b>        │\n"
        f"├─────────────────────┤\n"
        f"│ 🛒 <b>Покупок:</b>  <b>{orders}</b>\n"
        f"│ 💸 <b>Потрачено:</b>  <b>{spent:.2f}$</b>\n"
        f"│ 💎 <b>Баланс:</b>  <b>{u['balance']:.2f}$</b>\n"
        f"│ 🗓 <b>В проекте:</b>  <b>{days} дн.</b>\n"
        f"├─────────────────────┤\n"
        f"│ 👥 <b>Всего юзеров:</b>  <b>{total_users}</b>\n"
        f"└─────────────────────┘"
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
            f"┌─────────────────────┐\n"
            f"│  📋  <b>ИСТОРИЯ ПОКУПОК</b>   │\n"
            f"├─────────────────────┤\n"
            f"│  😔 Покупок пока нет\n"
            f"└─────────────────────┘"
        )
    else:
        lines = ""
        for i, (name, amount, dt) in enumerate(rows, 1):
            lines += f"│ <b>{i}.</b> <b>{name}</b>  —  <b>{amount:.2f}$</b>\n│     🗓 {dt[:10]}\n"
        text = (
            f"┌─────────────────────┐\n"
            f"│  📋  <b>ИСТОРИЯ ПОКУПОК</b>   │\n"
            f"├─────────────────────┤\n"
            f"{lines}"
            f"├─────────────────────┤\n"
            f"│ Последние <b>{len(rows)}</b> операций\n"
            f"└─────────────────────┘"
        )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb_back())


# ─────────────────────────────────────────
#  SUPPORT
# ─────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "menu_support")
def cb_support(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("✉️ Написать оператору", url="https://t.me/username"))
    kb.row(types.InlineKeyboardButton("🔙 Главное меню", callback_data="back_main"))
    text = (
        f"┌─────────────────────┐\n"
        f"│     🎧  <b>ПОДДЕРЖКА</b>        │\n"
        f"├─────────────────────┤\n"
        f"│ Мы рады помочь!\n"
        f"├─────────────────────┤\n"
        f"│ ⏱ <b>Ответ:</b>  до <b>15 минут</b>\n"
        f"│ 🕐 <b>Работаем:</b>  <b>10:00–22:00</b>\n"
        f"└─────────────────────┘"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          parse_mode="HTML", reply_markup=kb)


# ─────────────────────────────────────────
#  ADMIN PANEL
# ─────────────────────────────────────────

def is_admin(user_id):
    return user_id in ADMIN_IDS

admin_states = {}

@bot.message_handler(commands=["admin"])
def cmd_admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📦 Управление товарами", callback_data="adm_products"))
    kb.row(types.InlineKeyboardButton("💰 Начислить баланс",    callback_data="adm_topup_form"))
    kb.row(types.InlineKeyboardButton("📊 Общая статистика",    callback_data="adm_stats"))
    bot.send_message(
        msg.chat.id,
        f"┌─────────────────────┐\n"
        f"│    🔧  <b>АДМИН-ПАНЕЛЬ</b>      │\n"
        f"└─────────────────────┘\n\n"
        f"<b>Выберите действие 👇</b>",
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_products")
def cb_adm_products(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    products = get_products()
    kb = types.InlineKeyboardMarkup()
    for p in products:
        pid, name, price, stock, min_qty = p
        kb.row(types.InlineKeyboardButton(
            f"✏️ {name}  |  {price}$  |  {stock} шт.",
            callback_data=f"adm_edit_{pid}"
        ))
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text(
        f"┌─────────────────────┐\n"
        f"│   📦  <b>ТОВАРЫ</b>             │\n"
        f"├─────────────────────┤\n"
        f"│ Выберите для редакт. 👇\n"
        f"└─────────────────────┘",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_edit_"))
def cb_adm_edit(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    p = get_product(pid)
    if not p: return
    _, name, price, stock, min_qty = p
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("💵 Цена",    callback_data=f"adm_price_{pid}"),
        types.InlineKeyboardButton("📦 Остаток", callback_data=f"adm_stock_{pid}"),
    )
    kb.row(
        types.InlineKeyboardButton("🔢 Мин. кол-во", callback_data=f"adm_minqty_{pid}"),
    )
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_products"))
    bot.edit_message_text(
        f"┌─────────────────────┐\n"
        f"│  ✏️  <b>РЕДАКТИРОВАНИЕ</b>      │\n"
        f"├─────────────────────┤\n"
        f"│ 📦 <b>Товар:</b>  <b>{name}</b>\n"
        f"│ 💵 <b>Цена:</b>  <b>{price}$</b>\n"
        f"│ 📦 <b>Остаток:</b>  <b>{stock} шт.</b>\n"
        f"│ 🔢 <b>Мин. покупка:</b>  <b>{min_qty} шт.</b>\n"
        f"└─────────────────────┘",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_price_"))
def cb_adm_set_price(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    admin_states[call.from_user.id] = {"action": "set_price", "pid": pid}
    bot.edit_message_text(
        f"💵 <b>Введите новую цену в $:</b>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_stock_"))
def cb_adm_set_stock(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    admin_states[call.from_user.id] = {"action": "set_stock", "pid": pid}
    bot.edit_message_text(
        f"📦 <b>Введите новый остаток (шт.):</b>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_minqty_"))
def cb_adm_set_minqty(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    pid = int(call.data.split("_")[2])
    admin_states[call.from_user.id] = {"action": "set_minqty", "pid": pid}
    bot.edit_message_text(
        f"🔢 <b>Введите минимальное количество для покупки (шт.):</b>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_topup_form")
def cb_adm_topup_form(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    admin_states[call.from_user.id] = {"action": "topup"}
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
    kb.row(types.InlineKeyboardButton("🔙 Назад", callback_data="adm_back"))
    bot.edit_message_text(
        f"┌─────────────────────┐\n"
        f"│   📊  <b>СТАТИСТИКА</b>         │\n"
        f"├─────────────────────┤\n"
        f"│ 👥 <b>Пользователей:</b>  <b>{total_users}</b>\n"
        f"│ 🛒 <b>Покупок:</b>  <b>{total_orders}</b>\n"
        f"│ 💸 <b>Выручка:</b>  <b>{total_revenue:.2f}$</b>\n"
        f"└─────────────────────┘",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "adm_back")
def cb_adm_back(call: types.CallbackQuery):
    if not is_admin(call.from_user.id): return
    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("📦 Управление товарами", callback_data="adm_products"))
    kb.row(types.InlineKeyboardButton("💰 Начислить баланс",    callback_data="adm_topup_form"))
    kb.row(types.InlineKeyboardButton("📊 Общая статистика",    callback_data="adm_stats"))
    bot.edit_message_text(
        f"┌─────────────────────┐\n"
        f"│    🔧  <b>АДМИН-ПАНЕЛЬ</b>      │\n"
        f"└─────────────────────┘\n\n"
        f"<b>Выберите действие 👇</b>",
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
                f"✅ <b>Цена обновлена!</b>\n<b>{p[1]}</b>  →  <b>{p[2]}$</b>",
                parse_mode="HTML")
        except:
            bot.send_message(msg.chat.id, "❌ <b>Неверный формат. Введите число.</b>", parse_mode="HTML")

    elif action == "set_stock":
        try:
            stock = int(msg.text.strip())
            update_product(state["pid"], stock=stock)
            p = get_product(state["pid"])
            bot.send_message(msg.chat.id,
                f"✅ <b>Остаток обновлён!</b>\n<b>{p[1]}</b>  →  <b>{p[3]} шт.</b>",
                parse_mode="HTML")
        except:
            bot.send_message(msg.chat.id, "❌ <b>Неверный формат. Введите целое число.</b>", parse_mode="HTML")

    elif action == "set_minqty":
        try:
            min_qty = int(msg.text.strip())
            if min_qty < 1:
                raise ValueError
            update_product(state["pid"], min_qty=min_qty)
            p = get_product(state["pid"])
            bot.send_message(msg.chat.id,
                f"✅ <b>Мин. кол-во обновлено!</b>\n<b>{p[1]}</b>  →  <b>{p[4]} шт.</b>",
                parse_mode="HTML")
        except:
            bot.send_message(msg.chat.id, "❌ <b>Неверный формат. Введите целое число ≥ 1.</b>", parse_mode="HTML")

    elif action == "topup":
        try:
            parts = msg.text.strip().split()
            uid, amount = int(parts[0]), float(parts[1])
            conn = db()
            conn.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
            conn.commit()
            conn.close()
            bot.send_message(msg.chat.id,
                f"✅ <b>Начислено {amount}$ → пользователю {uid}</b>", parse_mode="HTML")
            try:
                bot.send_message(uid,
                    f"┌─────────────────────┐\n"
                    f"│   💰  <b>ПОПОЛНЕНИЕ</b>        │\n"
                    f"├─────────────────────┤\n"
                    f"│ Администратор зачислил\n"
                    f"│ <b>{amount}$</b> на ваш баланс\n"
                    f"└─────────────────────┘",
                    parse_mode="HTML")
            except:
                pass
        except:
            bot.send_message(msg.chat.id, "❌ <b>Формат: user_id сумма</b>", parse_mode="HTML")


# ─────────────────────────────────────────
#  WEBHOOK  (Render)
# ─────────────────────────────────────────

import os
from flask import Flask, request, abort

app = Flask(__name__)

# инициализируем БД при старте
with app.app_context():
    init_db()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")   # опционально
RENDER_URL      = os.environ.get("RENDER_URL", "")       # https://your-app.onrender.com

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            abort(403)
    json_data = request.get_data(as_text=True)
    update   = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running", 200

def set_webhook():
    url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=url)
    print(f"✅ Webhook установлен: {url}")

if __name__ == "__main__":
    init_db()
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    print(f"🤖 Бот запущен на порту {port}...")
    app.run(host="0.0.0.0", port=port)
