import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

API_TOKEN = 'YOUR_TOKEN_HERE'
ADMIN_ID = 6712617550

bot = Bot(API_TOKEN)
dp = Dispatcher()

# Состояния FSM
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    admin_add_id = State()
    admin_remove_id = State()

# --- Работа с БД ---
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

def remove_admin(user_id):
    if user_id == ADMIN_ID:
        return
    conn, c = db_connect()
    c.execute('DELETE FROM admins WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Изменить никнейм")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Добавить админа")],
        [KeyboardButton(text="➖ Снять админа")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_menu():
    kb = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

@dp.message(Command("start"))
async def on_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Добро пожаловать!\n\nДля регистрации или смены ника используйте кнопки ниже.",
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )

@dp.message(F.text == "📝 Регистрация")
async def registration_start(message: Message, state: FSMContext):
    await state.set_state(RegStates.waiting_for_nick)
    await message.answer(
        "Введи никнейм в формате Имя_Фамилия (латиница, _ обязателен):",
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
            "❌ Никнейм должен быть на английском и содержать '_' (пример: Ivan_Ivanov). Попробуй ещё раз или нажми 'Отмена':"
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
        f"✅ Никнейм {nickname} зарегистрирован!",
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )
    await state.clear()

@dp.message(F.text == "✏️ Изменить никнейм")
async def edit_nick_start(message: Message, state: FSMContext):
    await state.set_state(RegStates.editing_nick)
    await message.answer(
        "Введи новый никнейм в формате Имя_Фамилия (латиница, _ обязателен):",
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
            "❌ Никнейм должен быть на английском и содержать '_' (пример: Ivan_Ivanov). Попробуй ещё раз или нажми 'Отмена':"
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
        f"✅ Никнейм изменён на {nickname}!",
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id))
    )
    await state.clear()

@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer("Меню управления администраторами:", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.set_state(RegStates.admin_add_id)
    await message.answer("Введи user_id для добавления в админы:", reply_markup=cancel_menu())

@dp.message(RegStates.admin_add_id)
async def add_admin_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await admin_panel(message, state)
        return
    try:
        user_id = int(message.text.strip())
        add_admin(user_id)
        await message.answer(f"✅ Админ {user_id} добавлен.", reply_markup=admin_menu())
        await state.clear()
    except Exception:
        await message.answer("Ошибка! Введи числовой user_id или 'Отмена'.", reply_markup=cancel_menu())

@dp.message(F.text == "➖ Снять админа")
async def remove_admin_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.set_state(RegStates.admin_remove_id)
    await message.answer("Введи user_id для снятия из админов:", reply_markup=cancel_menu())

@dp.message(RegStates.admin_remove_id)
async def remove_admin_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await admin_panel(message, state)
        return
    try:
        user_id = int(message.text.strip())
        remove_admin(user_id)
        await message.answer(f"✅ Админ {user_id} снят.", reply_markup=admin_menu())
        await state.clear()
    except Exception:
        await message.answer("Ошибка! Введи числовой user_id или 'Отмена'.", reply_markup=cancel_menu())

@dp.message(F.text == "🔙 Назад")
async def back_from_admin(message: Message, state: FSMContext):
    await on_start(message, state)

if __name__ == "__main__":
    add_admin(ADMIN_ID)
    asyncio.run(dp.start_polling(bot))
