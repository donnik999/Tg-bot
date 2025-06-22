import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

API_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
ADMIN_ID = 123456789  # твой Telegram ID

bot = Bot(API_TOKEN)
dp = Dispatcher()

# --- Работа с БД ---
def db_connect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            user_id INTEGER,
            response TEXT,
            event_time TEXT,
            PRIMARY KEY (user_id, event_time)
        )
    ''')
    conn.commit()
    return conn, c

# --- Проверка никнейма ---
def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

# --- Команда регистрации ---
@dp.message(Command("register"))
async def register(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Пожалуйста, укажи никнейм после команды. Пример: /register Sander_Kligan")
        return
    nickname = args[1]
    if not is_valid_nick(nickname):
        await message.reply("Никнейм должен быть на английском и содержать '_' (пример: Sander_Kligan)")
        return
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO users (user_id, nickname) VALUES (?, ?)', (message.from_user.id, nickname))
    conn.commit()
    conn.close()
    await message.reply(f"Никнейм {nickname} успешно зарегистрирован!")

# --- Команда для админа: список пользователей ---
@dp.message(Command("list"))
async def list_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа.")
        return
    conn, c = db_connect()
    c.execute('SELECT user_id, nickname FROM users')
    users = c.fetchall()
    conn.close()
    text = "\n".join([f"{uid}: {nick}" for uid, nick in users])
    await message.reply(f"Список пользователей:\n{text}")

# --- Команда оповещения ---
@dp.message(Command("notify"))
async def notify(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Укажи время. Пример: /notify 20:00")
        return
    event_time = args[1]
    conn, c = db_connect()
    c.execute('SELECT user_id, nickname FROM users')
    users = c.fetchall()
    conn.close()
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Да", callback_data=f"yes_{event_time}"))
    kb.add(InlineKeyboardButton(text="Нет", callback_data=f"no_{event_time}"))
    for uid, nick in users:
        await bot.send_message(
            uid, 
            f"Готовы к Бизвару на {event_time}?",
            reply_markup=kb.as_markup()
        )
    await message.reply("Оповещение отправлено.")

# --- Обработка ответов пользователей ---
@dp.callback_query(F.data.regexp(r'(yes|no)_\d{2}:\d{2}'))
async def handle_response(callback_query: types.CallbackQuery):
    response, event_time = callback_query.data.split('_')
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO responses (user_id, response, event_time) VALUES (?, ?, ?)',
              (callback_query.from_user.id, response, event_time))
    conn.commit()
    conn.close()
    await callback_query.answer(f"Ответ '{response}' записан.")

# --- Команда для админа: посмотреть ответы ---
@dp.message(Command("results"))
async def results(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Нет доступа.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Укажи время. Пример: /results 20:00")
        return
    event_time = args[1]
    conn, c = db_connect()
    c.execute('''
        SELECT users.nickname, responses.response
        FROM responses
        JOIN users ON responses.user_id = users.user_id
        WHERE responses.event_time = ?
    ''', (event_time,))
    results = c.fetchall()
    conn.close()
    text = "\n".join([f"{nick}: {resp}" for nick, resp in results])
    await message.reply(f"Результаты на {event_time}:\n{text if text else 'Нет ответов.'}")

# --- Запуск бота ---
if __name__ == "__main__":
    import asyncio
    from aiogram import executor
    asyncio.run(dp.start_polling(bot))
