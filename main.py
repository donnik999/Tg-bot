import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

API_TOKEN = '8099941356:AAFyHCfCt4jVkmXQqdIC3kufKj5f0Wg969o'
ADMIN_ID = 6712617550  # твой Telegram ID

bot = Bot(API_TOKEN)
dp = Dispatcher()

# FSM состояния
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    waiting_for_announce = State()

# --- Работа с БД ---
def db_connect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            username TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            user_id INTEGER,
            nickname TEXT,
            username TEXT,
            response TEXT,
            announcement_id INTEGER,
            PRIMARY KEY (user_id, announcement_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT
        )
    ''')
    conn.commit()
    return conn, c

# --- Проверка никнейма ---
def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

# --- Главное меню ---
def main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="🚀 Начать")],
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Редактировать никнейм")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="📢 Сделать объявление")])
        kb.append([KeyboardButton(text="👥 Список участников")])
        kb.append([KeyboardButton(text="📄 Список зарегистрированных пользователей")])  # Новая кнопка
    kb.append([KeyboardButton(text="🏠 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Команда /start, кнопка "Начать", "Главное меню" ---
@dp.message(Command("start"))
@dp.message(F.text == "🏠 Главное меню")
@dp.message(F.text == "🚀 Начать")
async def send_welcome(message: Message):
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(
        "👋 Привет!\n\n"
        "Ты попал в бота для выбора участников БизВара ⚔️🏆\n"
        "Используй кнопки ниже ⬇️",
        reply_markup=main_menu(is_admin),
        parse_mode="HTML"
    )

# --- Регистрация ---
@dp.message(F.text == "📝 Регистрация")
async def registration_start(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Придумай себе никнейм в формате <b>Имя_Фамилия</b> (только латиница, знак подчеркивания _ обязательно).\n\nВведи свой никнейм сообщением:",
        parse_mode="HTML"
    )
    await state.set_state(RegStates.waiting_for_nick)

@dp.message(RegStates.waiting_for_nick)
async def registration_finish(message: Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз:")
        return
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO users (user_id, nickname, username) VALUES (?, ?, ?)',
              (message.from_user.id, nickname, message.from_user.username or ""))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Никнейм <b>{nickname}</b> успешно зарегистрирован!", parse_mode="HTML", reply_markup=main_menu(message.from_user.id == ADMIN_ID))
    await state.clear()

# --- Редактировать никнейм ---
@dp.message(F.text == "✏️ Редактировать никнейм")
async def edit_nick_start(message: Message, state: FSMContext):
    await message.answer(
        "🔄 Введи новый никнейм в формате <b>Имя_Фамилия</b> (только латиница, знак _ обязательно):",
        parse_mode="HTML"
    )
    await state.set_state(RegStates.editing_nick)

@dp.message(RegStates.editing_nick)
async def edit_nick_finish(message: Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз:")
        return
    conn, c = db_connect()
    c.execute('UPDATE users SET nickname = ?, username = ? WHERE user_id = ?', (nickname, message.from_user.username or "", message.from_user.id))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Никнейм изменён на <b>{nickname}</b>!", parse_mode="HTML", reply_markup=main_menu(message.from_user.id == ADMIN_ID))
    await state.clear()

# --- Сделать объявление (только для админа) ---
@dp.message(F.text == "📢 Сделать объявление")
async def announce_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    await message.answer("📝 Введите текст объявления для всех участников:")
    await state.set_state(RegStates.waiting_for_announce)

@dp.message(RegStates.waiting_for_announce)
async def announce_send(message: Message, state: FSMContext):
    text = message.text
    conn, c = db_connect()
    # записываем объявление
    c.execute('INSERT INTO announcements (text) VALUES (?)', (text,))
    announcement_id = c.lastrowid
    # список пользователей
    c.execute('SELECT user_id, nickname, username FROM users')
    users = c.fetchall()
    conn.commit()
    conn.close()
    # Клавиатура для ответа
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Готов", callback_data=f"ready_{announcement_id}"),
            InlineKeyboardButton(text="🔴 Не готов", callback_data=f"notready_{announcement_id}")
        ]
    ])
    for uid, nick, username in users:
        await bot.send_message(uid,
            f"📢 <b>Объявление:</b>\n{text}\n\n"
            "Ответьте на приглашение кнопкой ниже 👇",
            parse_mode="HTML",
            reply_markup=kb
        )
    await message.answer("✅ Объявление отправлено всем!", reply_markup=main_menu(True))
    await state.clear()

# --- Обработка ответов на объявление ---
@dp.callback_query(F.data.regexp(r'(ready|notready)_(\d+)'))
async def handle_announce_response(callback_query: types.CallbackQuery):
    response_type, announcement_id = callback_query.data.split("_")
    conn, c = db_connect()
    # Получаем ник и username пользователя
    c.execute('SELECT nickname, username FROM users WHERE user_id = ?', (callback_query.from_user.id,))
    user = c.fetchone()
    nickname = user[0] if user else ""
    username = user[1] if user else callback_query.from_user.username or ""
    c.execute(
        'INSERT OR REPLACE INTO responses (user_id, nickname, username, response, announcement_id) VALUES (?, ?, ?, ?, ?)',
        (callback_query.from_user.id, nickname, username, response_type, int(announcement_id))
    )
    conn.commit()
    conn.close()
    await callback_query.answer("Спасибо, ответ принят!")

# --- Список участников (только для админа) ---
@dp.message(F.text == "👥 Список участников")
async def show_ready_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    # Получаем id последнего объявления
    c.execute('SELECT id FROM announcements ORDER BY id DESC LIMIT 1')
    last = c.fetchone()
    if not last:
        await message.reply("❗ Пока не было объявлений.")
        conn.close()
        return
    announcement_id = last[0]
    # Получаем участников, кто нажал "Готов"
    c.execute('''
        SELECT nickname, username, user_id
        FROM responses
        WHERE response = "ready" AND announcement_id = ?
    ''', (announcement_id,))
    users = c.fetchall()
    conn.close()
    if not users:
        await message.reply("❗ Пока никто не откликнулся.")
        return
    text = "🟢 <b>Готовы к событию:</b>\n\n"
    for nick, username, uid in users:
        user_info = f"{nick} | @{username if username else uid}"
        text += f"• {user_info}\n"
    await message.reply(text, parse_mode="HTML")

# --- Список всех зарегистрированных пользователей (только для админа) ---
@dp.message(F.text == "📄 Список зарегистрированных пользователей")
async def show_registered_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    c.execute('SELECT nickname, username, user_id FROM users')
    users = c.fetchall()
    conn.close()
    if not users:
        await message.reply("❗ Нет зарегистрированных пользователей.")
        return
    text = "<b>Список зарегистрированных пользователей:</b>\n\n"
    for nick, username, uid in users:
        user_info = f"{nick} | @{username if username else uid}"
        text += f"• {user_info}\n"
    await message.reply(text, parse_mode="HTML")

# --- Запуск бота ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
