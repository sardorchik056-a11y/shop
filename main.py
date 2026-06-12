import telebot
from telebot import types
from datetime import datetime, date
import sqlite3
import os

BOT_TOKEN = "8610804137:AAFkdrZIDRAsdhn4fZP51-rcnrI5C8d4xpg"

bot = telebot.TeleBot(BOT_TOKEN)

# ─────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────

def init_db():
    conn = sqlite3.connect("users.db")
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
        CREATE TABLE IF NOT EXISTS purchases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            item        TEXT,
            amount      REAL,
            date        TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def get_or_create_user(user_id: int, username: str, full_name: str) -> dict:
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute(
            "INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    conn.close()
    return {
        "user_id":   row[0],
        "username":  row[1] or "—",
        "full_name": row[2] or "—",
        "balance":   row[3],
        "joined":    row[4],
    }

def days_in_project(joined_date_str: str) -> int:
    try:
        joined = date.fromisoformat(joined_date_str)
        return (date.today() - joined).days
    except Exception:
        return 0

def get_history(user_id: int) -> list:
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        "SELECT item, amount, date FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────

def main_menu() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🛒 Купить"),
        types.KeyboardButton("💰 Баланс"),
        types.KeyboardButton("🎧 Поддержка"),
        types.KeyboardButton("📊 Статистика"),
        types.KeyboardButton("📋 История покупок"),
    )
    return kb


# ─────────────────────────────────────────
#  PROFILE CARD  (shared header)
# ─────────────────────────────────────────

def profile_card(u: dict) -> str:
    days = days_in_project(u["joined"])
    name_display = u["full_name"] if u["full_name"] != "—" else "Без имени"
    uname = f"@{u['username']}" if u["username"] != "—" else "не указан"
    return (
        "╔══════════════════════╗\n"
        f"║  👤  {name_display[:18]:<18}  ║\n"
        "╠══════════════════════╣\n"
        f"║  🆔  {u['user_id']:<20}  ║\n"
        f"║  📎  {uname:<20}  ║\n"
        f"║  💎  {u['balance']:.2f} ₽{'':<13}  ║\n"
        f"║  🗓  {days} дн. в проекте{'':<7}  ║\n"
        "╚══════════════════════╝"
    )


def clean_profile_card(u: dict) -> str:
    """Красивая версия без псевдографики — для разных экранов."""
    days = days_in_project(u["joined"])
    uname = f"@{u['username']}" if u["username"] != "—" else "не указан"
    return (
        f"👤 <b>{u['full_name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
        f"📎 <b>Username:</b> {uname}\n"
        f"💎 <b>Баланс:</b> {u['balance']:.2f} ₽\n"
        f"🗓 <b>В проекте:</b> {days} дн."
    )


# ─────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg: types.Message):
    u = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )
    days = days_in_project(u["joined"])
    uname = f"@{u['username']}" if u['username'] != '—' else "не указан"

    text = (
        f"✨ <b>Добро пожаловать!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Имя:</b> {u['full_name']}\n"
        f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
        f"📎 <b>Username:</b> {uname}\n"
        f"💎 <b>Баланс:</b> <b>{u['balance']:.2f} ₽</b>\n"
        f"🗓 <b>В проекте:</b> {days} дн.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Выберите раздел в меню 👇"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def btn_balance(msg: types.Message):
    u = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )
    text = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{clean_profile_card(u)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Для пополнения обратитесь в <b>поддержку</b>."
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
def btn_buy(msg: types.Message):
    u = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )
    # Пример товаров — замените на свои
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📦 Товар «Старт» — 99 ₽",    callback_data="buy_99"),
        types.InlineKeyboardButton("🚀 Товар «Про» — 299 ₽",     callback_data="buy_299"),
        types.InlineKeyboardButton("💎 Товар «Премиум» — 799 ₽", callback_data="buy_799"),
    )
    text = (
        f"🛒 <b>Магазин</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 Ваш баланс: <b>{u['balance']:.2f} ₽</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Выберите товар 👇"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML",
                     reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def cb_buy(call: types.CallbackQuery):
    prices = {"buy_99": (99, "Товар «Старт»"),
              "buy_299": (299, "Товар «Про»"),
              "buy_799": (799, "Товар «Премиум»")}
    amount, item = prices.get(call.data, (0, "Неизвестно"))
    u = get_or_create_user(call.from_user.id, call.from_user.username or "", call.from_user.full_name or "")

    if u["balance"] < amount:
        bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
        return

    # Списываем баланс
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, u["user_id"]))
    c.execute("INSERT INTO purchases (user_id, item, amount) VALUES (?, ?, ?)",
              (u["user_id"], item, amount))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, f"✅ Покупка оформлена!", show_alert=True)
    bot.edit_message_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"📦 Товар: <b>{item}</b>\n"
        f"💸 Списано: <b>{amount:.2f} ₽</b>",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML"
    )


@bot.message_handler(func=lambda m: m.text == "🎧 Поддержка")
def btn_support(msg: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✉️ Написать оператору", url="https://t.me/username"))
    text = (
        f"🎧 <b>Поддержка</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Мы рады помочь! Нажмите кнопку ниже,\n"
        f"чтобы связаться с оператором.\n\n"
        f"⏱ Время ответа: до <b>15 минут</b>\n"
        f"🕐 Режим работы: <b>10:00 – 22:00</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def btn_stats(msg: types.Message):
    u = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM purchases WHERE user_id = ?", (u["user_id"],))
    total_orders, total_spent = c.fetchone()
    c.execute("SELECT COUNT(*) FROM users")
    all_users = c.fetchone()[0]
    conn.close()

    days = days_in_project(u["joined"])
    text = (
        f"📊 <b>Ваша статистика</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Имя:</b> {u['full_name']}\n"
        f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Покупок:</b> {total_orders}\n"
        f"💸 <b>Потрачено:</b> {total_spent:.2f} ₽\n"
        f"💎 <b>Баланс:</b> {u['balance']:.2f} ₽\n"
        f"🗓 <b>В проекте:</b> {days} дн.\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Всего пользователей:</b> {all_users}"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "📋 История покупок")
def btn_history(msg: types.Message):
    u = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )
    rows = get_history(u["user_id"])

    if not rows:
        text = (
            f"📋 <b>История покупок</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"😔 У вас пока нет покупок.\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        lines = ""
        for i, (item, amount, dt) in enumerate(rows, 1):
            short_dt = dt[:10]  # только дата
            lines += f"  {i}. {item} — <b>{amount:.2f} ₽</b> · {short_dt}\n"
        text = (
            f"📋 <b>История покупок</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{lines}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👆 Последние {len(rows)} операций"
        )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_menu())


# ─────────────────────────────────────────
#  ADMIN: начислить баланс
#  /add_balance <user_id> <amount>
# ─────────────────────────────────────────

ADMIN_IDS = {123456789}  # ← укажите свой Telegram ID

@bot.message_handler(commands=["add_balance"])
def cmd_add_balance(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        _, uid, amount = msg.text.split()
        uid, amount = int(uid), float(amount)
    except ValueError:
        bot.reply_to(msg, "Формат: /add_balance <user_id> <сумма>")
        return
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
    conn.commit()
    conn.close()
    bot.reply_to(msg, f"✅ Начислено {amount:.2f} ₽ пользователю {uid}")


# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("🤖 Бот запущен...")
    bot.infinity_polling()
