import logging
import asyncio
import re
import sqlite3
import json

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text, Command

API_TOKEN = '8099941356:AAFyHCfCt4jVkmXQqdIC3kufKj5f0Wg969o'
MAIN_ADMIN_ID = 6712617550
DEPUTY_ROLE = "deputy"
ADMIN_ROLE = "admin"
MAIN_ADMIN_ROLE = "main_admin"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    waiting_for_announce = State()
    admin_set_user = State()
    admin_set_permissions = State()
    admin_remove_user = State()

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
            text TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT,
            permissions TEXT
        )
    ''')
    conn.commit()
    return conn, c

def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

DEFAULT_PERMISSIONS = {
    MAIN_ADMIN_ROLE: {
        "can_create_announce": True,
        "can_delete_announce": True,
        "can_close_announce": True,
        "can_open_announce": True,
        "can_kick": True,
        "can_edit_nick": True,
        "can_delete_nick": True,
        "can_manage_admins": True
    },
    DEPUTY_ROLE: {
        "can_create_announce": True,
        "can_delete_announce": True,
        "can_close_announce": True,
        "can_open_announce": True,
        "can_kick": True,
        "can_edit_nick": True,
        "can_delete_nick": True,
        "can_manage_admins": True
    },
    ADMIN_ROLE: {
        "can_create_announce": True,
        "can_delete_announce": False,
        "can_close_announce": True,
        "can_open_announce": False,
        "can_kick": False,
        "can_edit_nick": True,
        "can_delete_nick": False,
        "can_manage_admins": False
    }
}

def get_admin_permissions(user_id):
    if user_id == MAIN_ADMIN_ID:
        return DEFAULT_PERMISSIONS[MAIN_ADMIN_ROLE]
    conn, c = db_connect()
    c.execute('SELECT role, permissions FROM admins WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row is None:
        return {}
    role, perm_json = row
    if perm_json:
        perms = json.loads(perm_json)
    else:
        perms = DEFAULT_PERMISSIONS.get(role, {})
    return perms

def has_permission(user_id, perm):
    perms = get_admin_permissions(user_id)
    return perms.get(perm, False)

def get_admin_role(user_id):
    if user_id == MAIN_ADMIN_ID:
        return MAIN_ADMIN_ROLE
    conn, c = db_connect()
    c.execute('SELECT role FROM admins WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def set_admin(user_id, role, permissions=None):
    conn, c = db_connect()
    perms = permissions if permissions is not None else DEFAULT_PERMISSIONS.get(role, {})
    perms_json = json.dumps(perms)
    c.execute('INSERT OR REPLACE INTO admins (user_id, role, permissions) VALUES (?, ?, ?)', (user_id, role, perms_json))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn, c = db_connect()
    c.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def main_menu(user_id):
    role = get_admin_role(user_id)
    perms = get_admin_permissions(user_id)
    is_admin = role is not None or user_id == MAIN_ADMIN_ID

    kb = [
        [KeyboardButton("🚀 Начать")],
        [KeyboardButton("📝 Регистрация")],
        [KeyboardButton("✏️ Редактировать никнейм")]
    ]
    if is_admin:
        if perms.get("can_create_announce"): kb.append([KeyboardButton("📢 Сделать объявление")])
        kb.append([KeyboardButton("📥 Активные объявления")])
        kb.append([KeyboardButton("📄 Список зарегистрированных пользователей")])
        if perms.get("can_manage_admins"): kb.append([KeyboardButton("⚙️ Управление администраторами")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

@dp.message_handler(commands=["start"])
@dp.message_handler(lambda m: m.text == "🚀 Начать")
async def send_welcome(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "👋 Привет!\n\n"
        "Ты попал в бота для выбора участников БизВара ⚔️🏆\n"
        "Используй кнопки ниже ⬇️",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.message_handler(lambda m: m.text == "📝 Регистрация")
async def registration_start(message: types.Message, state: FSMContext):
    await message.answer(
        "✍️ Придумай себе никнейм в формате Имя_Фамилия (только латиница, знак подчеркивания _ обязательно).\n\nВведи свой никнейм сообщением:"
    )
    await RegStates.waiting_for_nick.set()

@dp.message_handler(state=RegStates.waiting_for_nick)
async def registration_finish(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз:")
        return
    conn, c = db_connect()
    c.execute('INSERT OR REPLACE INTO users (user_id, nickname, username) VALUES (?, ?, ?)',
              (message.from_user.id, nickname, message.from_user.username or ""))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Никнейм {nickname} успешно зарегистрирован!", reply_markup=main_menu(message.from_user.id))
    await state.finish()

@dp.message_handler(lambda m: m.text == "✏️ Редактировать никнейм")
async def edit_nick_start(message: types.Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_edit_nick") and message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer(
        "🔄 Введи новый никнейм в формате Имя_Фамилия (только латиница, знак _ обязательно):"
    )
    await RegStates.editing_nick.set()

@dp.message_handler(state=RegStates.editing_nick)
async def edit_nick_finish(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    if not is_valid_nick(nickname):
        await message.answer("❌ Никнейм должен быть на английском и содержать '_' (например: Sander_Kligan). Попробуй ещё раз:")
        return
    conn, c = db_connect()
    c.execute('UPDATE users SET nickname = ?, username = ? WHERE user_id = ?', (nickname, message.from_user.username or "", message.from_user.id))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Никнейм изменён на {nickname}!", reply_markup=main_menu(message.from_user.id))
    await state.finish()

@dp.message_handler(lambda m: m.text == "📢 Сделать объявление")
async def announce_start(message: types.Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_create_announce") and message.from_user.id != MAIN_ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    await message.answer("📝 Введите текст объявления для всех участников:")
    await RegStates.waiting_for_announce.set()

@dp.message_handler(state=RegStates.waiting_for_announce)
async def announce_send(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❗ Введите текст объявления.")
        return

    conn, c = db_connect()
    c.execute('INSERT INTO announcements (text, status) VALUES (?, "active")', (text,))
    announcement_id = c.lastrowid
    c.execute('SELECT user_id, nickname, username FROM users WHERE nickname IS NOT NULL AND nickname != ""')
    users = c.fetchall()
    conn.commit()
    conn.close()
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🟢 Готов", callback_data=f"ready_{announcement_id}"),
        InlineKeyboardButton("🔴 Не готов", callback_data=f"notready_{announcement_id}")
    )
    failed = 0
    for uid, nick, username in users:
        try:
            await bot.send_message(
                uid,
                f"📢 Объявление:\n{text}\n\nОтветьте на приглашение кнопкой ниже 👇",
                reply_markup=kb
            )
        except Exception as e:
            print(f"Ошибка отправки объявы юзеру {uid}: {e}")
            failed += 1
            continue
    await message.answer(
        f"✅ Объявление отправлено всем зарегистрированным!{' (Некоторым не удалось доставить)' if failed else ''}",
        reply_markup=main_menu(message.from_user.id)
    )
    await state.finish()

@dp.message_handler(lambda m: m.text == "📥 Активные объявления")
async def show_active_announcements(message: types.Message):
    role = get_admin_role(message.from_user.id)
    if role is None and message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    c.execute('SELECT id, text FROM announcements WHERE status="active" ORDER BY id DESC')
    announces = c.fetchall()
    conn.close()
    if not announces:
        await message.answer("❗ Сейчас нет активных объявлений.")
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for ann_id, text in announces:
        kb.add(InlineKeyboardButton(f"Объявление #{ann_id}", callback_data=f"show_announce_{ann_id}"))
    await message.answer("Выберите объявление:", reply_markup=kb)

@dp.callback_query_handler(lambda call: call.data.startswith("show_announce_"))
async def show_announce_users(call: types.CallbackQuery):
    ann_id = int(call.data.split("_")[-1])
    conn, c = db_connect()
    c.execute('SELECT text, status FROM announcements WHERE id=?', (ann_id,))
    ann = c.fetchone()
    if not ann:
        await call.answer("Объявление не найдено", show_alert=True)
        return
    text, status = ann
    c.execute('''
        SELECT nickname, username, user_id, response
        FROM responses
        WHERE announcement_id = ?
    ''', (ann_id,))
    users = c.fetchall()
    conn.close()
    ready = [f"{n}|@{u if u else uid}" for n,u,uid,r in users if r=="ready"]
    not_ready = [f"{n}|@{u if u else uid}" for n,u,uid,r in users if r=="notready"]
    msg = f"📢 Объявление: {text}\nСтатус: {status}\n\n"
    msg += "🟢 Готовы:\n" + "\n".join(f"• {x}" for x in ready) if ready else "🟢 Готовых нет.\n"
    msg += "\n\n🔴 Не готовы:\n" + "\n".join(f"• {x}" for x in not_ready) if not_ready else "\n\n🔴 Нет откликов 'не готов'."
    kb = InlineKeyboardMarkup(row_width=1)
    await call.message.answer(msg, reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda call: call.data.startswith("ready_") or call.data.startswith("notready_"))
async def handle_announce_response(call: types.CallbackQuery):
    response_type, announcement_id = call.data.split("_")
    conn, c = db_connect()
    c.execute('SELECT status FROM announcements WHERE id=?', (announcement_id,))
    ann = c.fetchone()
    if not ann or ann[0] != "active":
        await call.answer("Объявление не активно", show_alert=True)
        return
    c.execute('SELECT nickname, username FROM users WHERE user_id = ?', (call.from_user.id,))
    user = c.fetchone()
    nickname = user[0] if user else ""
    username = user[1] if user else call.from_user.username or ""
    c.execute(
        'INSERT OR REPLACE INTO responses (user_id, nickname, username, response, announcement_id) VALUES (?, ?, ?, ?, ?)',
        (call.from_user.id, nickname, username, response_type, int(announcement_id))
    )
    conn.commit()
    conn.close()
    await call.answer("Спасибо, ответ принят!")

@dp.message_handler(lambda m: m.text == "📄 Список зарегистрированных пользователей")
async def show_registered_users(message: types.Message):
    role = get_admin_role(message.from_user.id)
    if role is None and message.from_user.id != MAIN_ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    c.execute('SELECT nickname, username, user_id FROM users WHERE nickname IS NOT NULL AND nickname != ""')
    users = c.fetchall()
    conn.close()
    if not users:
        await message.reply("❗ Нет зарегистрированных пользователей.")
        return
    text = "Список зарегистрированных пользователей:\n\n"
    for nick, username, uid in users:
        user_info = f"{nick} | @{username if username else uid}"
        text += f"• {user_info}\n"
    await message.reply(text)

if __name__ == "__main__":
    conn, c = db_connect()
    c.execute('SELECT * FROM admins WHERE user_id=?', (MAIN_ADMIN_ID,))
    if not c.fetchone():
        set_admin(MAIN_ADMIN_ID, MAIN_ADMIN_ROLE, DEFAULT_PERMISSIONS[MAIN_ADMIN_ROLE])
    conn.close()
    executor.start_polling(dp, skip_updates=True)
