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
MAIN_ADMIN_ID = 6712617550  # Главный админ
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

# Права по-умолчанию для ролей
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

# --- Главное меню ---
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
    kb.append([KeyboardButton(text="🏠 Главное меню")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- Команда /start, кнопка "Начать", "Главное меню" ---
@dp.message(Command("start"))
@dp.message(F.text == "🏠 Главное меню")
@dp.message(F.text == "🚀 Начать")
async def send_welcome(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Ты попал в бота для выбора участников БизВара ⚔️🏆\n"
        "Используй кнопки ниже ⬇️",
        reply_markup=main_menu(message.from_user.id),
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
    await message.answer(f"✅ Никнейм <b>{nickname}</b> успешно зарегистрирован!", parse_mode="HTML", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- Редактировать никнейм ---
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

# --- Сделать объявление (несколько объявлений) ---
@dp.message(F.text == "📢 Сделать объявление")
async def announce_start(message: Message, state: FSMContext):
    if not has_permission(message.from_user.id, "can_create_announce") and message.from_user.id != MAIN_ADMIN_ID:
        await message.reply("⛔ Нет доступа.")
        return
    await message.answer("📝 Введите текст объявления для всех участников:")
    await state.set_state(RegStates.waiting_for_announce)

@dp.message(RegStates.waiting_for_announce)
async def announce_send(message: Message, state: FSMContext):
    text = message.text
    conn, c = db_connect()
    # Записываем объявление. Статус активный.
    c.execute('INSERT INTO announcements (text, status) VALUES (?, "active")', (text,))
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
        try:
            await bot.send_message(uid,
                f"📢 <b>Объявление:</b>\n{text}\n\n"
                "Ответьте на приглашение кнопкой ниже 👇",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            continue
    await message.answer("✅ Объявление отправлено всем!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- Список активных объявлений и ответы участников ---
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
        await message.answer("❗ Активных объявлений нет.")
        return
    kb = InlineKeyboardBuilder()
    for ann_id, text in announces:
        kb.button(text=f"Объявление #{ann_id}", callback_data=f"show_announce_{ann_id}")
    await message.answer("Выберите объявление:", reply_markup=kb.as_markup())

# --- Просмотр откликов на объявление (админ) ---
@dp.callback_query(F.data.regexp(r'show_announce_(\d+)'))
async def show_announce_users(call: types.CallbackQuery):
    ann_id = int(call.data.split("_")[-1])
    conn, c = db_connect()
    # Получить текст объявления
    c.execute('SELECT text, status FROM announcements WHERE id=?', (ann_id,))
    ann = c.fetchone()
    if not ann:
        await call.answer("Объявление не найдено", show_alert=True)
        return
    text, status = ann
    # Получить ответы
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
    # Кнопки управления
    kb = InlineKeyboardBuilder()
    if has_permission(call.from_user.id, "can_close_announce") and status == "active":
        kb.button(text="❌ Закрыть объявление", callback_data=f"close_announce_{ann_id}")
    if has_permission(call.from_user.id, "can_open_announce") and status == "closed":
        kb.button(text="🔓 Открыть объявление", callback_data=f"open_announce_{ann_id}")
    if has_permission(call.from_user.id, "can_delete_announce"):
        kb.button(text="🗑 Удалить объявление", callback_data=f"delete_announce_{ann_id}")
    await call.message.answer(msg, parse_mode="HTML", reply_markup=kb.as_markup() if kb.buttons else None)
    await call.answer()

# --- Закрытие/открытие/удаление объявления ---
@dp.callback_query(F.data.regexp(r'(close|open|delete)_announce_(\d+)'))
async def manage_announce_status(call: types.CallbackQuery):
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

# --- Обработка ответов на объявление ---
@dp.callback_query(F.data.regexp(r'(ready|notready)_(\d+)'))
async def handle_announce_response(callback_query: types.CallbackQuery):
    response_type, announcement_id = callback_query.data.split("_")
    conn, c = db_connect()
    # Проверка что объявление активно
    c.execute('SELECT status FROM announcements WHERE id=?', (announcement_id,))
    ann = c.fetchone()
    if not ann or ann[0] != "active":
        await callback_query.answer("Объявление не активно", show_alert=True)
        return
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

# --- Список всех зарегистрированных пользователей (только для админа) ---
@dp.message(F.text == "📄 Список зарегистрированных пользователей")
async def show_registered_users(message: Message):
    role = get_admin_role(message.from_user.id)
    if role is None and message.from_user.id != MAIN_ADMIN_ID:
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

# --- Управление администраторами (главный и зам) ---
@dp.message(F.text == "⚙️ Управление администраторами")
async def admin_management(message: Message, state: FSMContext):
    role = get_admin_role(message.from_user.id)
    if not has_permission(message.from_user.id, "can_manage_admins"):
        await message.answer("⛔ Нет доступа.")
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить админа", callback_data="admin_add")
    kb.button(text="Удалить админа", callback_data="admin_remove")
    kb.button(text="Изменить права", callback_data="admin_setperm")
    await message.answer("Управление администраторами:", reply_markup=kb.as_markup())

# --- Обработка кнопок админки ---
@dp.callback_query(F.data == "admin_add")
async def admin_add_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введи user_id или @username пользователя, которого хочешь сделать админом, и его роль (admin/deputy):\nПример: 123456789 admin")
    await state.set_state(RegStates.admin_set_user)
    await call.answer()

@dp.message(RegStates.admin_set_user)
async def admin_add_process(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        user = parts[0]
        role = parts[1].lower()
        user_id = int(user) if user.isdigit() else None
        if not user_id and user.startswith("@"):
            conn, c = db_connect()
            c.execute('SELECT user_id FROM users WHERE username=?', (user[1:],))
            row = c.fetchone()
            conn.close()
            if not row:
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            user_id = row[0]
        if role not in [ADMIN_ROLE, DEPUTY_ROLE]:
            await message.answer("Роль должна быть admin или deputy.")
            await state.clear()
            return
        set_admin(user_id, role)
        await message.answer("✅ Админ назначен.")
    except Exception as e:
        await message.answer("Ошибка! Проверь ввод.")
    await state.clear()

@dp.callback_query(F.data == "admin_remove")
async def admin_remove_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введи user_id или @username пользователя, у которого забрать права администратора:")
    await state.set_state(RegStates.admin_remove_user)
    await call.answer()

@dp.message(RegStates.admin_remove_user)
async def admin_remove_process(message: Message, state: FSMContext):
    try:
        user = message.text.strip()
        user_id = int(user) if user.isdigit() else None
        if not user_id and user.startswith("@"):
            conn, c = db_connect()
            c.execute('SELECT user_id FROM users WHERE username=?', (user[1:],))
            row = c.fetchone()
            conn.close()
            if not row:
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            user_id = row[0]
        remove_admin(user_id)
        await message.answer("✅ Права администратора сняты.")
    except Exception as e:
        await message.answer("Ошибка! Проверь ввод.")
    await state.clear()

@dp.callback_query(F.data == "admin_setperm")
async def admin_setperm_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "Введи user_id или @username и список прав через пробел (например: can_create_announce can_kick ...):\n"
        "Пример: 123456789 can_create_announce can_kick"
    )
    await state.set_state(RegStates.admin_set_permissions)
    await call.answer()

@dp.message(RegStates.admin_set_permissions)
async def admin_setperm_process(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        user = parts[0]
        user_id = int(user) if user.isdigit() else None
        if not user_id and user.startswith("@"):
            conn, c = db_connect()
            c.execute('SELECT user_id FROM users WHERE username=?', (user[1:],))
            row = c.fetchone()
            conn.close()
            if not row:
                await message.answer("Пользователь не найден.")
                await state.clear()
                return
            user_id = row[0]
        # Разрешения
        allowed_perms = [
            "can_create_announce", "can_delete_announce", "can_close_announce", "can_open_announce",
            "can_kick", "can_edit_nick", "can_delete_nick", "can_manage_admins"
        ]
        perms = {k: False for k in allowed_perms}
        for perm in parts[1:]:
            if perm in allowed_perms:
                perms[perm] = True
        role = get_admin_role(user_id) or ADMIN_ROLE
        set_admin(user_id, role, permissions=perms)
        await message.answer("✅ Права обновлены.")
    except Exception as e:
        await message.answer("Ошибка! Проверь ввод.")
    await state.clear()

# --- Кик и удаление/редактирование ника (по правам) ---
@dp.message(Command("kick"))
async def kick_user(message: Message):
    if not has_permission(message.from_user.id, "can_kick"):
        await message.reply("⛔ Нет права кикать.")
        return
    args = message.get_args()
    user_id = int(args) if args.isdigit() else None
    if not user_id:
        await message.reply("Укажи user_id.")
        return
    conn, c = db_connect()
    c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    await message.reply(f"Пользователь {user_id} удалён.")

@dp.message(Command("delnick"))
async def delnick_user(message: Message):
    if not has_permission(message.from_user.id, "can_delete_nick"):
        await message.reply("⛔ Нет права удалять ник.")
        return
    args = message.get_args()
    user_id = int(args) if args.isdigit() else None
    if not user_id:
        await message.reply("Укажи user_id.")
        return
    conn, c = db_connect()
    c.execute('UPDATE users SET nickname=NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    await message.reply(f"Ник пользователя {user_id} удалён.")

@dp.message(Command("editnick"))
async def editnick_user(message: Message):
    if not has_permission(message.from_user.id, "can_edit_nick"):
        await message.reply("⛔ Нет права менять ник.")
        return
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("Используй: /editnick user_id Новый_Ник")
        return
    user_id = int(args[0])
    new_nick = args[1]
    if not is_valid_nick(new_nick):
        await message.reply("Никнейм должен быть в формате Имя_Фамилия (латиница, _).")
        return
    conn, c = db_connect()
    c.execute('UPDATE users SET nickname=? WHERE user_id=?', (new_nick, user_id))
    conn.commit()
    conn.close()
    await message.reply(f"Ник пользователя {user_id} изменён на {new_nick}.")

# --- Запуск бота ---
if __name__ == "__main__":
    # При первом запуске добавить себя как главного админа, если не существует
    conn, c = db_connect()
    c.execute('SELECT * FROM admins WHERE user_id=?', (MAIN_ADMIN_ID,))
    if not c.fetchone():
        set_admin(MAIN_ADMIN_ID, MAIN_ADMIN_ROLE, DEFAULT_PERMISSIONS[MAIN_ADMIN_ROLE])
    conn.close()
    asyncio.run(dp.start_polling(bot))
