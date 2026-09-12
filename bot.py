import os
import asyncio
import logging
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")

if not BOT_TOKEN or not ADMIN_ID_RAW:
    exit("❌ Ошибка: В файле .env не заданы BOT_TOKEN или ADMIN_ID!")

ADMIN_ID = int(ADMIN_ID_RAW)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# ПУТЬ К БАЗЕ ДАННЫХ ДЛЯ BOTHOST
DB_PATH = "/app/data/support.db"

# Автоматическое переключение на локальный путь, если запускаете тест на своем ПК
if not os.path.exists("/app/data"):
    DB_PATH = "support.db"


# --- База данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            category TEXT,
            data_text TEXT,
            status TEXT DEFAULT 'open'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_chats (
            admin_id INTEGER,
            user_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()


def start_chat(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO active_chats (admin_id, user_id) VALUES (?, ?)", (ADMIN_ID, user_id))
    conn.commit()
    conn.close()


def close_chat(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_chats WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_active_user_by_admin():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM active_chats WHERE admin_id = ?", (ADMIN_ID,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def is_user_in_chat(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM active_chats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return True if row else False


# --- Состояния FSM ---
class Form(StatesGroup):
    waiting_for_category = State()
    idea_1 = State()
    idea_2 = State()
    idea_3 = State()
    media_1 = State()
    media_2 = State()
    media_3 = State()
    bug_1 = State()
    bug_2 = State()


class AdminReply(StatesGroup):
    waiting_for_first_answer = State()


def get_categories_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Предложение / Идея", callback_data="cat_idea")],
        [InlineKeyboardButton(text="🎥 Заявка на Медиа", callback_data="cat_media")],
        [InlineKeyboardButton(text="🐛 Сообщить о Баге", callback_data="cat_bug")]
    ])


# --- Логика Пользователя ---
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if is_user_in_chat(message.from_user.id):
        await message.answer("💬 У вас уже есть активный чат с поддержкой. Просто пишите сообщения сюда.")
        return
    await state.clear()
    await message.answer("👋 Здравствуйте! Выберите категорию вашего обращения:", reply_markup=get_categories_keyboard())
    await state.set_state(Form.waiting_for_category)


@router.callback_query(Form.waiting_for_category, F.data.startswith("cat_"))
async def process_category_choice(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)

    if category == "idea":
        await callback.message.edit_text("1️⃣ **Ваша идея:**\nНапишите краткую суть в одном предложении.")
        await state.set_state(Form.idea_1)
    elif category == "media":
        await callback.message.edit_text("1️⃣ **Ссылка на ваш ТТ/ЮТ канал:**")
        await state.set_state(Form.media_1)
    elif category == "bug":
        await callback.message.edit_text("1️⃣ **Что за баг вы обнаружили?** Назовите его коротко.")
        await state.set_state(Form.bug_1)
    await callback.answer()


# ВЕТКА: ИДЕИ
@router.message(Form.idea_1)
async def process_idea_1(message: Message, state: FSMContext):
    await state.update_data(q1=message.text)
    await message.answer("2️⃣ **В чем заключается смысл идеи?** Опишите подробнее:")
    await state.set_state(Form.idea_2)


@router.message(Form.idea_2)
async def process_idea_2(message: Message, state: FSMContext):
    await state.update_data(q2=message.text)
    await message.answer("3️⃣ **Польза вашей идеи:** Чем она поможет проекту?")
    await state.set_state(Form.idea_3)


@router.message(Form.idea_3)
async def process_idea_3(message: Message, state: FSMContext):
    data = await state.get_data()
    text_report = (
        f"💡 **Категория:** Предложение / Идея\n\n"
        f"1. **Ваша идея:** {data['q1']}\n"
        f"2. **Смысл идеи:** {data['q2']}\n"
        f"3. **Польза идеи:** {message.text}"
    )
    await send_ticket_to_admin(message, state, "Идея", text_report)


# ВЕТКА: МЕДИА
@router.message(Form.media_1)
async def process_media_1(message: Message, state: FSMContext):
    await state.update_data(q1=message.text)
    await message.answer("2️⃣ **Ваши средние просмотры:**")
    await state.set_state(Form.media_2)


@router.message(Form.media_2)
async def process_media_2(message: Message, state: FSMContext):
    await state.update_data(q2=message.text)
    await message.answer("3️⃣ **Ваш контакт для связи (ТГ/ДС):**")
    await state.set_state(Form.media_3)


@router.message(Form.media_3)
async def process_media_3(message: Message, state: FSMContext):
    data = await state.get_data()
    text_report = (
        f"🎥 **Категория:** Заявка на Медиа\n\n"
        f"1. **Ссылка на ТТ/ЮТ:** {data['q1']}\n"
        f"2. **Средние просмотры:** {data['q2']}\n"
        f"3. **Контакт связи:** {message.text}"
    )
    await send_ticket_to_admin(message, state, "Медиа", text_report)


# ВЕТКА: БАГИ
@router.message(Form.bug_1)
async def process_bug_1(message: Message, state: FSMContext):
    await state.update_data(q1=message.text)
    await message.answer("2️⃣ **В чем суть бага?** Как его воспроизвести?")
    await state.set_state(Form.bug_2)


@router.message(Form.bug_2)
async def process_bug_2(message: Message, state: FSMContext):
    data = await state.get_data()
    text_report = (
        f"🐛 **Категория:** Сообщение о Баге\n\n"
        f"1. **Баг:** {data['q1']}\n"
        f"2. **В чем суть бага:** {message.text}"
    )
    await send_ticket_to_admin(message, state, "Баг", text_report)


async def send_ticket_to_admin(message: Message, state: FSMContext, category_name: str, text_report: str):
    await state.clear()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tickets (user_id, username, category, data_text) VALUES (?, ?, ?, ?)",
        (user_id, username, category_name, text_report)
    )
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await message.answer("✅ Ваша заявка успешно отправлена! Ожидайте ответа оператора.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить и открыть чат", callback_data=f"reply_{ticket_id}")]
    ])

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📬 **Новая заявка #{ticket_id}**\n"
             f"👤 От: {username} (ID: {user_id})\n"
             f"----------------------------------\n\n"
             f"{text_report}",
        reply_markup=kb
    )


@router.message(F.chat.id != ADMIN_ID)
async def user_chat_router(message: Message):
    if is_user_in_chat(message.from_user.id):
        username = f"@{message.from_user.username}" if message.from_user.username else "Пользователь"
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💬 **Сообщение от {username}:**\n\n{message.text}"
        )
    else:
        await message.answer("❌ Нажмите /start, чтобы открыть меню выбора категорий.")


# --- Логика Администратора ---
@router.callback_query(F.data.startswith("reply_"))
async def admin_reply_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Вы не админ!", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await callback.message.answer("❌ Заявка не найдена.")
        await callback.answer()
        return

    user_id = row[0]
    await state.update_data(
        reply_ticket_id=ticket_id,
        target_user_id=user_id,
        admin_msg_id=callback.message.message_id
    )
    await callback.message.answer(f"✍️ Введите первый ответ на заявку #{ticket_id}. Это откроет прямой диалог:")
    await state.set_state(AdminReply.waiting_for_first_answer)
    await callback.answer()


@router.message(AdminReply.waiting_for_first_answer)
async def process_admin_first_answer(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    admin_data = await state.get_data()
    await state.clear()

    ticket_id = admin_data['reply_ticket_id']
    user_id = admin_data['target_user_id']
    answer_text = message.text

    try:
        start_chat(user_id)
        await bot.send_message(
            chat_id=user_id,
            text=f"✉️ Ответ техподдержки по заявке #{ticket_id}:\n\n{answer_text}\n\n"
                 f"ℹ️ Диалог открыт. Все последующие сообщения будут сразу отправлены оператору."
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE tickets SET status = 'in_progress' WHERE id = ?", (ticket_id,))
        conn.commit()
        conn.close()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Закрыть диалог", callback_data=f"close_{user_id}")]
        ])

        await message.answer(
            f"✅ Чат открыт. Ваши сообщения пересылаются пользователю.",
            reply_markup=kb
        )

        await bot.edit_message_text(
            chat_id=ADMIN_ID,
            message_id=admin_data['admin_msg_id'],
            text=f"✅ Заявка #{ticket_id} переведена в режим диалога.\nОтвет: {answer_text}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")


@router.message(F.chat.id == ADMIN_ID)
async def admin_chat_router(message: Message):
    active_user_id = get_active_user_by_admin()
    if active_user_id:
        try:
            await bot.send_message(
                chat_id=active_user_id,
                text=f"💬 Ответ поддержки:\n\n{message.text}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔒 Закрыть диалог", callback_data=f"close_{active_user_id}")]
            ])
            await message.answer("▲ Отправлено.", reply_markup=kb)
        except Exception as e:
            await message.answer(f"❌ Доставка сорвалась: {e}")
    else:
        await message.answer("ℹ️ Сейчас нет активных чатов. Используйте кнопку «Ответить» под входящими заявками.")


@router.callback_query(F.data.startswith("close_"))
async def admin_close_chat(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    user_id = int(callback.data.split("_")[1])
    close_chat(user_id)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tickets SET status = 'closed' WHERE user_id = ? AND status = 'in_progress'",
        (user_id,)
    )
    conn.commit()
    conn.close()

    try:
        await bot.send_message(
            chat_id=user_id,
            text="🔒 Диалог с техподдержкой завершен.\nЕсли появятся новые вопросы, нажмите /start."
        )
    except Exception:
        pass

    await callback.message.answer("🔒 Диалог закрыт.")
    await callback.answer()


async def main():
    init_db()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
