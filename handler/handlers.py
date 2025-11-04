import logging

from sqlalchemy.exc import SQLAlchemyError
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from database.database import get_db, User, create_default_board, Board

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    greeting = ""

    try:
        async for db in get_db():
            user_db = await db.get(User, user.id)

            if not user_db:
                user_db = User(
                    id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
                db.add(user_db)

                default_board = Board(
                    user_id=user.id,
                    name="Неотсортированное",
                    emoji="📥"
                )
                db.add(default_board)

                await db.commit()
                await db.refresh(default_board)

                logger.info(f"Created new user in database {user_db.username}")
                greeting = (
                    f"Привет, {user.mention_markdown()}! 👋 Я **PinTag**, и я готов помочь тебе победить хаос!\n\n"
                    f"Я создал для тебя первую доску: **{default_board.emoji} {default_board.name}**.\n"
                    f"Отправь мне ссылку или файл, чтобы начать!"
                )
            else:
                greeting = f"С возвращением, {user.mention_markdown()}! Рад снова видеть тебя☺️"

            await update.message.reply_text(greeting, parse_mode=ParseMode.MARKDOWN)
            break

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error: {sqlex}")
        await update.message.reply_text("Ошибка в базе данных, попробуйте позже.")


async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "**Добавление:** Просто отправь мне ссылку, картинку, PDF или видео!\n\n"
        "**Команды:**\n"
        "🔸 /start — Приветствие и регистрация.\n"
        "🔸 /boards — Показать список твоих досок.\n"
        "🔸 /createboard <название> <эмодзи> — Создать новую доску. *Пример: /createboard Python 🐍*\n"
        "🔸 /show <доска> — Показать элементы в доске.\n"
        "🔸 /view <название> — Получить сохраненный элемент.\n"
        "🔸 /move <название> <доска> — Переместить элемент.\n"
        "🔸 /remove <название> — Удалить элемент.\n"
        "🔸 /stats — Твоя статистика (пока не работает)."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)