import logging

from sqlalchemy.exc import SQLAlchemyError
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from database.database import get_db, User, Board

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user

    try:
        async for db in get_db():
            user_db = await db.get(User, user.id)

            if not user_db:
                user_id = user.id
                username = user.username
                first_name = user.first_name
                board_emoji = "📥"
                board_name = "Неотсортированное"

                user_db = User(
                    id=user_id,
                    username=username,
                    first_name=first_name,
                )
                db.add(user_db)

                default_board = Board(
                    user_id=user_id,
                    name=board_name,
                    emoji=board_emoji
                )
                db.add(default_board)
                await db.commit()
                await db.refresh(default_board)

                logger.info(f"Created new user: {user_id}")
                greeting = (
                    f"Привет, <b>{user.first_name}</b>! 👋 Я <b>PinTag</b>, и я готов помочь тебе победить хаос!\n\n"
                    f"Я создал для тебя первую доску: <b>{default_board.emoji} {default_board.name}</b>.\n"
                    f"Отправь мне ссылку или файл, чтобы начать!"
                )
            else:
                greeting = f"С возвращением, <b>{user.first_name}</b>! Рад снова видеть тебя☺️"

            keyboard = [
                [KeyboardButton("📋 Мои доски"), KeyboardButton("❓ Помощь")],
                [KeyboardButton("📊 Статистика"), KeyboardButton("🚀 Начать")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            await update.message.reply_text(greeting, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error: {sqlex}")
        await update.message.reply_text("Ошибка в базе данных, попробуй позже.")


async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "**Добавление:** Просто отправь мне ссылку, картинку, PDF или видео!\n\n"
        "**Команды:**\n"
        "🔸 /start — Приветствие и регистрация.\n"
        "🔸 /boards — Показать список твоих досок.\n"
        "🔸 /getmyid — Получить свой user id(нужен для подключения через локальный клиент либо-же API).\n"
        "🔸 /connections — Узнать все подключённые клиенты.\n"
        "🔸 /createboard <название> <эмодзи> — Создать новую доску. *Пример: /createboard Python 🐍*\n"
        "🔸 /show <доска> — Показать элементы в доске.\n"
        "🔸 /view <название> — Получить сохраненный элемент.\n"
        "🔸 /move <название> <доска> — Переместить элемент.\n"
        "🔸 /remove <название> — Удалить элемент.\n"
        "🔸 /stats — Твоя статистика.\n"
        "🔸 /renameboard <старое название> <новое название> [стикер] — Переименовать доску.\n"
        "🔸 /removeboard <название доски> — Удалить доску со всем её содержимым.\n"
    )

    keyboard = [
        [KeyboardButton("📋 Мои доски"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🚀 Начать"), KeyboardButton("➕ Добавить элемент")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def get_my_id_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    await update.message.reply_text(f"Вот твой ID: {user_id}.\nМожешь использовать его для подключения в клиенте.")