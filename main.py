import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime

API_TOKEN = '8099941356:AAFyHCfCt4jVkmXQqdIC3kufKj5f0Wg969o'  # <-- ВСТАВЬ СЮДА СВОЙ ТОКЕН!
ADMIN_ID = 6712617550  # <-- ВСТАВЬ СЮДА СВОЙ user_id!

bot = Bot(API_TOKEN)
dp = Dispatcher()

# --- FSM ---
class RegStates(StatesGroup):
    waiting_for_nick = State()
    editing_nick = State()
    creating_announcement_title = State()
    creating_announcement_text = State()
    adding_admin = State()
    removing_admin = State()

# --- DB ---
def db_connect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # Users
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, nickname TEXT, username TEXT)')
    # Admins
    c.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)')
    # Announcements
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        text TEXT,
        creator_id INTEGER,
        created_at TEXT
    )''')
    # User responses to announcements
    c.execute('''CREATE TABLE IF NOT EXISTS announcement_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        announcement_id INTEGER,
        user_id INTEGER,
        status TEXT CHECK(status IN ('ready','not_ready')),
        UNIQUE(announcement_id, user_id)
    )''')
    conn.commit()
    return conn, c

def is_admin(user_id):
    if int(user_id) == int(ADMIN_ID):
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
    if int(user_id) == int(ADMIN_ID):
        return
    conn, c = db_connect()
    c.execute('DELETE FROM admins WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def is_valid_nick(nick):
    return bool(re.fullmatch(r'[A-Za-z0-9]+_[A-Za-z0-9]+', nick))

# --- Keyboards ---
def main_menu(is_admin=False):
    kb = [
        [KeyboardButton(text="📝 Регистрация")],
        [KeyboardButton(text="✏️ Изменить никнейм")],
        [KeyboardButton(text="👥 Список игроков с никнеймом")]
    ]
    if is_admin:
        kb.append([KeyboardButton(text="📢 Объявление")])
        kb.append([KeyboardButton(text="📄 Список участников")])
        kb.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_menu():
    kb = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Добавить админа")],
        [KeyboardButton(text="➖ Снять админа")],
        [KeyboardButton(text="📋 Список администраторов")],  # <-- Новая кнопка
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def announcement_response_kb(announcement_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готов", callback_data=f"ready_{announcement_id}"),
                InlineKeyboardButton(text="❌ Не готов", callback_data=f"notready_{announcement_id}")
            ]
        ]
    )

def announcements_pagination_kb(page, total, ann_id, is_admin=False):
    btns = []
    if page > 1:
        btns.append(InlineKeyboardButton(text="⬅️", callback_data=f"ann_page_{page-1}"))
    if page < total:
        btns.append(InlineKeyboardButton(text="➡️", callback_data=f"ann_page_{page+1}"))
    rows = []
    if btns:
        rows.append(btns)
    if is_admin:
        rows.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"ann_del_{ann_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# --- Handlers ---

@dp.message(Command("start"))
async def on_start(message: Message, state: FSMContext):
    await state.clear()
    photo = FSInputFile("welcome.jpg")
    await message.answer_photo(
        photo,
        caption=(
            "👋 <b>Добро пожаловать в BIZWAR BOT!</b>\n\n"
            "📝 Зарегистрируйся, чтобы участвовать в играх!\n\n"
            "<i>Воспользуйся меню ниже. Если возникнут вопросы — пиши администратору.</i>"
        ),
        parse_mode='HTML'
    )
    await message.answer(
        "📋 <b>Главное меню:</b>",
        reply_markup=main_menu(is_admin=is_admin(message.from_user.id)),
        parse_mode="HTML"
    )

# --- Регистрация ---
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

# --- Изменить никнейм ---
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

# --- Список игроков с никнеймом ---
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

# --- Админ-панель ---
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer("🛠 <b>Меню администратора:</b>", reply_markup=admin_menu(), parse_mode="HTML")

@dp.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("Введи user_id для добавления в админы:", reply_markup=cancel_menu())
    await state.set_state(RegStates.adding_admin)

@dp.message(F.text == "➖ Снять админа")
async def remove_admin_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("Введи user_id для снятия из админов:", reply_markup=cancel_menu())
    await state.set_state(RegStates.removing_admin)

@dp.message(F.text == "🔙 Назад")
async def back_from_admin(message: Message, state: FSMContext):
    await on_start(message, state)

# --- Новый функционал: список админов ---
@dp.message(F.text == "📋 Список администраторов")
async def list_admins(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    # Получаем все айдишники из таблицы admins И обязательно добавляем ADMIN_ID
    c.execute("SELECT user_id FROM admins")
    admin_ids = set(int(row[0]) for row in c.fetchall())
    admin_ids.add(int(ADMIN_ID))
    admin_list = []
    for admin_id in admin_ids:
        c.execute("SELECT nickname, username FROM users WHERE user_id = ?", (admin_id,))
        row = c.fetchone()
        nickname = row[0] if row and row[0] else "—"
        username = ("@" + row[1]) if row and row[1] else "—"
        admin_list.append(f"<b>{nickname}</b> | {username} | <code>{admin_id}</code>")
    conn.close()
    msg = "👮 <b>Список администраторов:</b>\n" + "\n".join(admin_list)
    await message.answer(msg, parse_mode="HTML")

@dp.message(RegStates.adding_admin)
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

@dp.message(RegStates.removing_admin)
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

# --- Объявления ---
@dp.message(F.text == "📢 Объявление")
async def ann_create_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.set_state(RegStates.creating_announcement_title)
    await message.answer("📝 <b>Введи название объявления:</b>", parse_mode="HTML", reply_markup=cancel_menu())

@dp.message(RegStates.creating_announcement_title)
async def ann_create_text(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await on_start(message, state)
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(RegStates.creating_announcement_text)
    await message.answer("📝 <b>Введи текст объявления:</b>", parse_mode="HTML", reply_markup=cancel_menu())

@dp.message(RegStates.creating_announcement_text)
async def ann_create_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await on_start(message, state)
        return
    data = await state.get_data()
    title = data.get("title")
    text = message.text.strip()
    conn, c = db_connect()
    c.execute(
        "INSERT INTO announcements (title, text, creator_id, created_at) VALUES (?, ?, ?, ?)",
        (title, text, message.from_user.id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    ann_id = c.lastrowid
    conn.commit()
    c.execute("SELECT user_id, nickname, username FROM users WHERE nickname IS NOT NULL AND nickname != ''")
    user_rows = c.fetchall()
    user_ids = set()
    user_info = []
    for user_id, nickname, username in user_rows:
        user_ids.add(user_id)
        user_info.append((user_id, nickname, username))
    user_ids.add(message.from_user.id)
    sent = []
    failed = []
    for user_id in user_ids:
        try:
            await bot.send_message(
                user_id,
                f"📢 <b>{title}</b>\n\n{text}\n\n"
                "<i>Отметь свой статус для участия:</i>",
                parse_mode="HTML",
                reply_markup=announcement_response_kb(ann_id)
            )
            sent.append(user_id)
        except Exception:
            failed.append(user_id)
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM users WHERE nickname IS NOT NULL AND nickname != ''")
    users_with_nick = c.fetchone()[0] or 0
    stats = (f"📊 <b>Статистика рассылки:</b>\n"
             f"Всего пользователей: <b>{total_users}</b>\n"
             f"Зарегистрированы с ником: <b>{users_with_nick}</b>\n"
             f"Всего отправлено: <b>{len(sent)}</b>\n"
             f"Получили объявление:\n" +
             "\n".join([f"<code>{uid}</code>" + 
                        (f" ({nick} @{uname})" if (uid, nick, uname) in user_info else (" (вы)" if uid == message.from_user.id else ""))
                        for uid in sent]))
    if failed:
        stats += "\n\n🚫 Не доставлено:\n" + "\n".join([f"<code>{uid}</code>" for uid in failed])
    await message.answer(
        f"✅ Объявление создано и разослано!\n\n{stats}",
        parse_mode="HTML",
        reply_markup=main_menu(is_admin=True)
    )
    conn.close()
    await state.clear()

# --- Ответ на объявление ---
@dp.callback_query(F.data.regexp(r"^(ready|notready)_(\d+)$"))
async def announcement_response(call: types.CallbackQuery):
    match = re.match(r"^(ready|notready)_(\d+)$", call.data)
    status, ann_id = match.group(1), int(match.group(2))
    user_id = call.from_user.id
    conn, c = db_connect()
    c.execute("SELECT id FROM announcements WHERE id=?", (ann_id,))
    ann_exist = c.fetchone()
    if not ann_exist:
        await call.answer("Объявление не найдено.", show_alert=True)
        conn.close()
        return
    c.execute(
        "INSERT OR REPLACE INTO announcement_responses (announcement_id, user_id, status) VALUES (?, ?, ?)",
        (ann_id, user_id, "ready" if status == "ready" else "not_ready")
    )
    conn.commit()
    await call.answer("Ответ учтён!", show_alert=True)
    conn.close()

# --- Список участников (по объявлениям) ---
@dp.message(F.text == "📄 Список участников")
async def list_participants(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    conn, c = db_connect()
    c.execute("SELECT COUNT(*) FROM announcements")
    total = c.fetchone()[0]
    conn.close()
    if total == 0:
        await message.answer("Нет объявлений.")
        return
    await show_announcement_participants(message, 1, total)

async def show_announcement_participants(message, page, total):
    conn, c = db_connect()
    c.execute("SELECT id, title, text FROM announcements ORDER BY id DESC LIMIT 1 OFFSET ?", (page-1,))
    row = c.fetchone()
    if not row:
        await message.answer("Не найдено объявление на этой странице.")
        conn.close()
        return
    ann_id, title, text = row
    msg = f"📢 <b>{title}</b>\n{text}\n\n"
    msg += f"Страница: <b>{page}</b> из <b>{total}</b>\n"
    msg += "———\n"
    c.execute(
        "SELECT u.nickname, u.username, u.user_id, r.status "
        "FROM users u "
        "LEFT JOIN announcement_responses r "
        "ON u.user_id = r.user_id AND r.announcement_id=? "
        "WHERE u.nickname IS NOT NULL AND u.nickname != '' "
        "ORDER BY u.nickname", (ann_id,)
    )
    players = c.fetchall()
    if not players:
        msg += "Нет зарегистрированных игроков."
    else:
        for nickname, username, user_id, status in players:
            status_text = "✅ Готов" if status == "ready" else ("❌ Не готов" if status == "not_ready" else "—")
            msg += f"<b>{nickname}</b> | @{username or 'нет'} | <code>{user_id}</code> — {status_text}\n"
    is_admin_flag = is_admin(message.from_user.id)
    kb = announcements_pagination_kb(page, total, ann_id, is_admin=is_admin_flag)
    await message.answer(msg, parse_mode="HTML", reply_markup=kb)
    conn.close()

@dp.callback_query(F.data.regexp(r"^ann_page_(\d+)$"))
async def ann_page_callback(call: types.CallbackQuery):
    page = int(call.data.split("_")[-1])
    conn, c = db_connect()
    c.execute("SELECT COUNT(*) FROM announcements")
    total = c.fetchone()[0]
    conn.close()
    await show_announcement_participants(call.message, page, total)
    await call.answer()

# --- Удаление объявления (только для админа) ---
@dp.callback_query(F.data.regexp(r"^ann_del_(\d+)$"))
async def ann_delete_callback(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Нет доступа.", show_alert=True)
        return
    ann_id = int(call.data.split("_")[-1])
    conn, c = db_connect()
    c.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    c.execute("DELETE FROM announcement_responses WHERE announcement_id=?", (ann_id,))
    conn.commit()
    c.execute("SELECT COUNT(*) FROM announcements")
    total = c.fetchone()[0]
    conn.close()
    if total == 0:
        await call.message.edit_text("Нет объявлений.", parse_mode="HTML")
    else:
        page = 1
        await show_announcement_participants(call.message, page, total)
    await call.answer("Объявление удалено!", show_alert=True)

# --- Отмена везде ---
@dp.message(F.text == "❌ Отмена")
async def cancel_any(message: Message, state: FSMContext):
    await on_start(message, state)

# --- Стартовая инициализация ---
if __name__ == "__main__":
    add_admin(ADMIN_ID)
    asyncio.run(dp.start_polling(bot))
