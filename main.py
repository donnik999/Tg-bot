import asyncio
import re
import sqlite3
import json
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
ADMIN_ID = 6712617550  # Главный админ

bot = Bot(API_TOKEN)
dp = Dispatcher()

# FSM состояния
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    waiting_for_announce = State()
    admin_set_user = State()
    admin_remove_user = State()
    admin_set_permissions = State()

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            permissions TEXT  -- json
        )
    ''')
    conn.commit()
    return conn, c

def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

# --- Система админов ---
DEFAULT_PERMISSIONS = {
    "can_create_announce": True,
    "can_close_announce": True,
    "can_edit_nick": True,
    "can_delete_nick": True
}

def get_permissions(user_id):
    if user_id == ADMIN_ID:
        return {k: True for k in DEFAULT_PERMISSIONS}
    conn, c = db_connect()
    c.execute('SELECT permissions FROM admins WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {}
    return json.loads(row[0])

def has_permission(user_id, permission):
    perms = get_permissions(user_id)
    return perms.get(permission, False)

def set_admin(user_id, permissions=None):
    if permissions is None:
        permissions = DEFAULT_PERMISSIONS
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO admins (user_id, permissions) VALUES (?, ?)', (user_id, json.dumps(permissions)))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn, c = db_connect()
    c.execute('DELETE FROM admins WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def admin_menu():
    kb = [
        [KeyboardButton("➕ Добавить админа")],
        [KeyboardButton("➖ Снять админа")],
        [KeyboardButton("⚙️ Изменить права")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="🚀 Начать")],
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Редактировать никнейм")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="📢 Сделать объявление")])
        kb.append([KeyboardButton(text="👥 Список участников")])
        kb.append([KeyboardButton(text="📄 Список зарегистрированных пользователей")])
        kb.append([KeyboardButton(text="🛠 Админ-панель")])
    kb.append([KeyboardButton(text="🏠 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton("❌ Отмена")]], resize_keyboard=True)

# --- Команда /start, главное меню ---
@dp.message(Command("start"))
@dp.message(F.text == "🏠 Главное меню")
@dp.message(F.text == "🚀 Начать")
async def send_welcome(message: Message, state: FSMContext):
    await state.clear()
    is_admin = (message.from_user.id == ADMIN_ID) or (get_permissions(message.from_user.id) != {})
    await message.answer(
        "👋 Привет!\n\n"
        "Ты попал в бота для выбора участников БизВара ⚔️🏆\n"
        "Используй кнопки ниже ⬇️",
        reply_markup=main_menu(is_admin),
        parse_mode="HTML"
    )

# --- Регистрация пользователя ---
@dp.message(F.text == "📝 Регистрация")
async def registration_start(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Придумай себе никнейм в формате <b>Имя_Фамилия</b> (только латиница, знак подчеркивания _ обязательно).\n\nВведи свой никнейм сообщением или нажми 'Отмена':",
        parse_mode="HTML",
        reply_markup=cancel_menu()
    )
    await state.set_state(RegStates.waiting_for_nick)

@dp.message(RegStates.waiting_for_nick)
async def registration_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await send_welcome(message, state)
        return
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз или нажми 'Отмена':", reply_markup=cancel_menu())
        return
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO users (user_id, nickname, username) VALUES (?, ?, ?)',
              (message.from_user.id, nickname, message.from_user.username or ""))
    conn.commit()
    conn.close()
    is_admin = (message.from_user.id == ADMIN_ID) or (get_permissions(message.from_user.id) != {})
    await message.answer(f"✅ Никнейм <b>{nickname}</b> успешно зарегистрирован!", parse_mode="HTML", reply_markup=main_menu(is_admin))
    await state.clear()

# --- Редактировать никнейм ---
@dp.message(F.text == "✏️ Редактировать никнейм")
async def edit_nick_start(message: Message, state: FSMContext):
    await message.answer(
        "🔄 Введи новый никнейм в формате <b>Имя_Фамилия</b> (только латиница, знак _ обязательно) или нажми 'Отмена':",
        parse_mode="HTML",
        reply_markup=cancel_menu()
    )
    await state.set_state(RegStates.editing_nick)

@dp.message(RegStates.editing_nick)
async def edit_nick_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await send_welcome(message, state)
        return
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз или нажми 'Отмена':", reply_markup=cancel_menu())
        return
    conn, c = db_connect()
    c.execute('UPDATE users SET nickname = ?, username = ? WHERE user_id = ?', (nickname, message.from_user.username or "", message.from_user.id))
    conn.commit()
    conn.close()
    is_admin = (message.from_user.id == ADMIN_ID) or (get_permissions(message.from_user.id) != {})
    await message.answer(f"✅ Никнейм изменён на <b>{nickname}</b>!", parse_mode="HTML", reply_markup=main_menu(is_admin))
    await state.clear()

# --- Сделать объявление (по правам) ---
@dp.message(F.text == "📢 Сделать объявление")
async def announce_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_create_announce"):
        await message.reply("⛔ Нет доступа.")
        return
    await message.answer("📝 Введите текст объявления для всех участников:")
    await state.set_state(RegStates.waiting_for_announce)

@dp.message(RegStates.waiting_for_announce)
async def announce_send(message: Message, state: FSMContext):
    text = message.text
    conn, c = db_connect()
    c.execute('INSERT INTO announcements (text) VALUES (?)', (text,))
    announcement_id = c.lastrowid
    c.execute('SELECT user_id, nickname, username FROM users WHERE nickname IS NOT NULL AND nickname != ""')
    users = c.fetchall()
    conn.commit()
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Готов", callback_data=f"ready_{announcement_id}"),
            InlineKeyboardButton(text="🔴 Не готов", callback_data=f"notready_{announcement_id}")
        ]
    ])
    failed = 0
    for uid, nick, username in users:
        try:
            await bot.send_message(
                uid,
                f"📢 <b>Объявление:</b>\n{text}\n\n"
                "Ответьте на приглашение кнопкой ниже 👇",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            failed += 1
            continue
    await message.answer(
        f"✅ Объявление отправлено всем зарегистрированным!{' (Некоторым не удалось доставить)' if failed else ''}",
        reply_markup=main_menu(True)
    )
    await state.clear()

# --- Админ-панель (только для главного админа) ---
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("Меню управления администраторами:", reply_markup=admin_menu())
    await state.clear()

# --- Добавить админа ---
@dp.message(F.text == "➕ Добавить админа")
async def admin_add_start(message: Message, state: FSMContext):
    await message.answer("Введи user_id нового админа:")
    await state.set_state(RegStates.admin_set_user)

@dp.message(RegStates.admin_set_user)
async def admin_add_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        set_admin(user_id)
        await message.answer("✅ Админ добавлен с дефолтными правами.", reply_markup=admin_menu())
    except:
        await message.answer("Ошибка! Введи числовой user_id.")
    await state.clear()

# --- Снять админа ---
@dp.message(F.text == "➖ Снять админа")
async def admin_remove_start(message: Message, state: FSMContext):
    await message.answer("Введи user_id админа для снятия:")
    await state.set_state(RegStates.admin_remove_user)

@dp.message(RegStates.admin_remove_user)
async def admin_remove_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        if user_id == ADMIN_ID:
            await message.answer("Нельзя снять главного админа.")
        else:
            remove_admin(user_id)
            await message.answer("✅ Админ снят.", reply_markup=admin_menu())
    except:
        await message.answer("Ошибка! Введи числовой user_id.")
    await state.clear()

# --- Изменить права админа ---
@dp.message(F.text == "⚙️ Изменить права")
async def admin_setperm_start(message: Message, state: FSMContext):
    await message.answer(
        "Введи user_id и права через пробел (например: 123456789 can_create_announce can_close_announce ...):\n"
        "Доступные права: can_create_announce, can_close_announce, can_edit_nick, can_delete_nick"
    )
    await state.set_state(RegStates.admin_set_permissions)

@dp.message(RegStates.admin_set_permissions)
async def admin_setperm_process(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        user_id = int(parts[0])
        rights = set(parts[1:])
        allowed = set(DEFAULT_PERMISSIONS.keys())
        perms = {k: (k in rights) for k in allowed}
        set_admin(user_id, perms)
        await message.answer("✅ Права обновлены.", reply_markup=admin_menu())
    except:
        await message.answer("Ошибка! Проверь ввод.")
    await state.clear()

# --- Назад из админ-панели ---
@dp.message(F.text == "🔙 Назад")
async def back_from_admin(message: Message, state: FSMContext):
    await send_welcome(message, state)

# --- Обработка ответов на объявление ---
@dp.callback_query(F.data.regexp(r'(ready|notready)_(\d+)'))
async def handle_announce_response(callback_query: types.CallbackQuery):
    response_type, announcement_id = callback_query.data.split("_")
    conn, c = db_connect()
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
    if not has_permission(message.from_user.id, "can_create_announce"):
        await message.reply("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    c.execute('SELECT id FROM announcements ORDER BY id DESC LIMIT 1')
    last = c.fetchone()
    if not last:
        await message.reply("❗ Пока не было объявлений.")
        conn.close()
        return
    announcement_id = last[0]
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
    is_admin = (message.from_user.id == ADMIN_ID) or (get_permissions(message.from_user.id) != {})
    if not is_admin:
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
    # Гарантировать, что главный админ есть в базе с полными правами
    set_admin(ADMIN_ID, {k: True for k in DEFAULT_PERMISSIONS})
    asyncio.run(dp.start_polling(bot))
