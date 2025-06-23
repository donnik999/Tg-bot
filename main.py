import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

API_TOKEN = '8099941356:AAFyHCfCt4jVkmXQqdIC3kufKj5f0Wg969o'  # <-- ВСТАВЬ СВОЙ ТОКЕН!
ADMIN_ID = 6712617550  # <-- ВСТАВЬ СВОЙ user_id

bot = Bot(API_TOKEN)
dp = Dispatcher()

# --- FSM States ---
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()

# --- DB ---
def db_connect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, username TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    return conn, c

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    conn, c = db_connect()
    c.execute('SELECT user_id FROM admins WHERE user_id=?', (user_id,))
    result = c.fetchone()
    conn.close()
    return bool(result)

def add_admin(user_id):
    conn, c = db_connect()
    c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Изменить никнейм")],
        [KeyboardButton(text="👥 Список игроков с никнеймом")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="📢 Объявление")])
        kb.append([KeyboardButton(text="📄 Список участников")])
        kb.append([KeyboardButton(text="🛠 Админ-панель")])  # Всегда последней!
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_menu():
    kb = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

# --- Handlers ---

@dp.message(Command("start"))
async def on_start(message: Message, state: FSMContext):
    await state.clear()
    # Отправляем картинку
    photo = FSInputFile("welcome.jpg")
    await message.answer_photo(
        photo,
        caption="👋 <b>Добро пожаловать в BIZWAR BOT!</b>\n\n"
                "Здесь ты можешь зарегистрироваться, сменить никнейм и участвовать в играх.\n"
                "Пользуйся меню ниже — оно зависит от твоих прав.\n\n"
                "<i>Если возникнут вопросы, пиши администратору.</i>",
        parse_mode='HTML'
    )
    # Отправляем меню
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )

@dp.message(F.text == "📝 Регистрация")
async def registration_start(message: Message, state: FSMContext):
    await state.set_state(RegStates.waiting_for_nick)
    await message.answer(
        "✍️ <b>Введи никнейм</b> в формате <code>Имя_Фамилия</code> (латиница, обязательно _):",
        parse_mode='HTML',
        reply_markup=cancel_menu()
    )

@dp.message(RegStates.waiting_for_nick)
async def registration_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await on_start(message, state)
        return
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer(
            "❌ <b>Ошибка!</b> Никнейм должен быть в формате <code>Имя_Фамилия</code> латиницей. Попробуй ещё раз или нажми 'Отмена'.",
            parse_mode='HTML'
        )
        return
    conn, c = db_connect()
    c.execute(
        'INSERT OR REPLACE INTO users (user_id, nickname, username) VALUES (?, ?, ?)',
        (message.from_user.id, nickname, message.from_user.username or "")
    )
    conn.commit()
    conn.close()
    await message.answer(
        f"✅ <b>Никнейм {nickname} зарегистрирован!</b>",
        parse_mode='HTML',
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )
    await state.clear()

@dp.message(F.text == "✏️ Изменить никнейм")
async def edit_nick_start(message: Message, state: FSMContext):
    await state.set_state(RegStates.editing_nick)
    await message.answer(
        "✍️ <b>Введи новый никнейм</b> в формате <code>Имя_Фамилия</code> (латиница, обязательно _):",
        parse_mode='HTML',
        reply_markup=cancel_menu()
    )

@dp.message(RegStates.editing_nick)
async def edit_nick_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await on_start(message, state)
        return
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer(
            "❌ <b>Ошибка!</b> Никнейм должен быть в формате <code>Имя_Фамилия</code> латиницей. Попробуй ещё раз или нажми 'Отмена'.",
            parse_mode='HTML'
        )
        return
    conn, c = db_connect()
    c.execute(
        'UPDATE users SET nickname=?, username=? WHERE user_id=?',
        (nickname, message.from_user.username or "", message.from_user.id)
    )
    conn.commit()
    conn.close()
    await message.answer(
        f"✅ <b>Никнейм изменён на {nickname}!</b>",
        parse_mode='HTML',
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )
    await state.clear()

@dp.message(F.text == "👥 Список игроков с никнеймом")
async def list_players(message: Message, state: FSMContext):
    conn, c = db_connect()
    c.execute("SELECT nickname, username, user_id FROM users WHERE nickname IS NOT NULL AND nickname != ''")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer("Пока никто не зарегистрирован.")
        return
    msg = "👥 <b>Список игроков:</b>\n"
    msg += "\n".join(
        [f"<b>{row[0]}</b> | @{row[1] or 'нет'} | <code>{row[2]}</code>" for row in rows]
    )
    await message.answer(msg, parse_mode='HTML')

# --- Стартовая инициализация ---
if __name__ == "__main__":
    add_admin(ADMIN_ID)
    asyncio.run(dp.start_polling(bot))
