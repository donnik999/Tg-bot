import asyncio
import re
import sqlite3
import json
import logging
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
MAIN_ADMIN_ID = 6712617550
DEPUTY_ROLE = "deputy"
ADMIN_ROLE = "admin"
MAIN_ADMIN_ROLE = "main_admin"

bot = Bot(API_TOKEN)
dp = Dispatcher()

# FSM состояния
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    waiting_for_announce = State()
    selecting_announce = State()
    admin_set_user = State()
    admin_set_permissions = State()
    admin_remove_user = State()

# --- Работа с БД ---
def db_connect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # USERS
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            username TEXT
        )
    ''')
    # RESPONSES
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
    # ANNOUNCEMENTS
    c.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')
    # ADMINS (user_id, role, permissions (json))
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

# --- Админка ---
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
        [KeyboardButton(text="🚀 Начать")],
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Редактировать никнейм")]
    ]
    if is_admin:
        if perms.get("can_create_announce"): kb.append([KeyboardButton(text="📢 Сделать объявление")])
        kb.append([KeyboardButton(text="📥 Активные объявления")])
        kb.append([KeyboardButton(text="📄 Список зарегистрированных пользователей")])
        if perms.get("can_manage_admins"): kb.append([KeyboardButton(text="⚙️ Управление администраторами")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Хендлеры ---
@dp.message(Command("start"))
@dp.message(F.text == "🚀 Начать")
async def send_welcome(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет!\n\n"
        "Ты попал в бота для выбора участников БизВара ⚔️🏆\n"
        "Используй кнопки ниже ⬇️",
        reply_markup=main_menu(message.from_user.id),
        parse_mode="HTML"
    )

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
    await message.answer(f"✅ Никнейм <b>{nickname}</b> успешно зарегистрирован!", parse_mode="HTML", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "✏️ Редактировать никнейм")
async def edit_nick_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_edit_nick") and message.from_user.id != MAIN_ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
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
    await message.answer(f"✅ Никнейм изменён на <b>{nickname}</b>!", parse_mode="HTML", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "📢 Сделать объявление")
async def announce_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_create_announce") and message.from_user.id != MAIN_ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    await message.answer("📝 Введите текст объявления для всех участников:")
    await state.set_state(RegStates.waiting_for_announce)

@dp.message(RegStates.waiting_for_announce)
async def announce_send(message: Message, state: FSMContext):
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
            print(f"Ошибка отправки объявы юзеру {uid}: {e}")
            failed += 1
            continue
    await message.answer(
        f"✅ Объявление отправлено всем зарегистрированным!{' (Некоторым не удалось доставить)' if failed else ''}",
        reply_markup=main_menu(message.from_user.id)
    )
    await state.clear()

@dp.message(F.text == "📥 Активные объявления")
async def show_active_announcements(message: Message, state: FSMContext):
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
    kb = InlineKeyboardBuilder()
    for ann_id, text in announces:
        kb.button(text=f"Объявление #{ann_id}", callback_data=f"show_announce_{ann_id}")
    await message.answer("Выберите объявление:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.regexp(r'show_announce_(\d+)'))
async def show_announce_users(call: types.CallbackQuery, state: FSMContext):
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
    msg = f"📢 <b>Объявление:</b> {text}\nСтатус: <b>{status}</b>\n\n"
    msg += "🟢 <b>Готовы:</b>\n" + "\n".join(f"• {x}" for x in ready) if ready else "🟢 Готовых нет.\n"
    msg += "\n\n🔴 <b>Не готовы:</b>\n" + "\n".join(f"• {x}" for x in not_ready) if not_ready else "\n\n🔴 Нет откликов 'не готов'."
    kb = InlineKeyboardBuilder()
    if has_permission(call.from_user.id, "can_close_announce") and status == "active":
        kb.button(text="❌ Закрыть объявление", callback_data=f"close_announce_{ann_id}")
    if has_permission(call.from_user.id, "can_open_announce") and status == "closed":
        kb.button(text="🔓 Открыть объявление", callback_data=f"open_announce_{ann_id}")
    if has_permission(call.from_user.id, "can_delete_announce"):
        kb.button(text="🗑 Удалить объявление", callback_data=f"delete_announce_{ann_id}")
    await call.message.answer(msg, parse_mode="HTML", reply_markup=kb.as_markup() if kb.buttons else None)
    await call.answer()

@dp.callback_query(F.data.regexp(r'(close|open|delete)_announce_(\d+)'))
async def manage_announce_status(call: types.CallbackQuery, state: FSMContext):
    action, ann_id = call.data.split("_")[0], int(call.data.split("_")[-1])
    if action == "close" and not has_permission(call.from_user.id, "can_close_announce"):
        await call.answer("Нет права закрывать", show_alert=True)
        return
    if action == "open" and not has_permission(call.from_user.id, "can_open_announce"):
        await call.answer("Нет права открывать", show_alert=True)
        return
    if action == "delete" and not has_permission(call.from_user.id, "can_delete_announce"):
        await call.answer("Нет права удалять", show_alert=True)
        return
    conn, c = db_connect()
    if action in ["close", "open"]:
        new_status = "closed" if action == "close" else "active"
        c.execute('UPDATE announcements SET status = ? WHERE id = ?', (new_status, ann_id))
    elif action == "delete":
        c.execute('DELETE FROM announcements WHERE id = ?', (ann_id,))
        c.execute('DELETE FROM responses WHERE announcement_id = ?', (ann_id,))
    conn.commit()
    conn.close()
    await call.answer("Готово!", show_alert=True)
    await call.message.delete()

@dp.callback_query(F.data.regexp(r'(ready|notready)_(\d+)'))
async def handle_announce_response(callback_query: types.CallbackQuery, state: FSMContext):
    response_type, announcement_id = callback_query.data.split("_")
    conn, c = db_connect()
    c.execute('SELECT status FROM announcements WHERE id=?', (announcement_id,))
    ann = c.fetchone()
    if not ann or ann[0] != "active":
        await callback_query.answer("Объявление не активно", show_alert=True)
        return
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

@dp.message(F.text == "📄 Список зарегистрированных пользователей")
async def show_registered_users(message: Message, state: FSMContext):
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
    text = "<b>Список зарегистрированных пользователей:</b>\n\n"
    for nick, username, uid in users:
        user_info = f"{nick} | @{username if username else uid}"
        text += f"• {user_info}\n"
    await message.reply(text, parse_mode="HTML")

# --- Запуск бота ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn, c = db_connect()
    c.execute('SELECT * FROM admins WHERE user_id=?', (MAIN_ADMIN_ID,))
    if not c.fetchone():
        set_admin(MAIN_ADMIN_ID, MAIN_ADMIN_ROLE, DEFAULT_PERMISSIONS[MAIN_ADMIN_ROLE])
    conn.close()
    asyncio.run(dp.start_polling(bot)) 2
