import logging

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes, ConversationHandler

from Database.database import get_db, User, create_default_board, Board, Item

logger = logging.getLogger(__name__)

GET_TITLE, SELECT_BOARD = range(2)

async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user

    db = next(get_db())
    greeting = ""

    try:
        user_db = db.query(User).filter(User.id == user.id).first()

        if not user_db:
            user_db = User(
                id = user.id,
                username = user.username,
                first_name = user.first_name,
            )
            db.add(user_db)

            board = create_default_board(user.id, db)
            db.commit()

            logger.info(f"Created new user in database {user_db.username}")
            greeting = (
                f"Привет, {user.mention_markdown()}! 👋 Я **PinTag**, и я готов помочь тебе победить хаос!\n\n"
                f"Я создал для тебя первую доску: **{board.emoji}{board.name}**.\n"
                f"Отправь мне ссылку или файл, чтобы начать!"
            )
        else:
            greeting = f"С возвращением, {user.mention_markdown()}! Рад снова видеть тебя☺️"

        await update.message.reply_text(greeting, parse_mode=ParseMode.MARKDOWN)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error: {sqlex}")
        await update.message.reply_html("Ошибка в базе данных, попробуйте позже.")
    finally:
        db.close()


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


def extract_content_info(message):
    content_type = 'text'
    data = None
    title = "Неизвестный контент"

    if message.text and ('http' in message.text or 'https' in message.text):
        content_type = "link"
        data = message.text
        title = data.split('//')[-1].split('/')[0]
    elif message.photo:
        content_type = "photo"
        data = message.photo[-1].file_id
        title = "Фотография"
    elif message.document:
        content_type = "document"
        data = message.document.file_id
        title = message.document.file_name or "Документ"
    elif message.video:
        content_type = "video"
        data = message.video.file_id
        title = "Видеозапись"

    return content_type, data, title


def find_item_by_title(db, user_id: int, title: str) -> Item:
    return db.query(Item).filter(
        Item.user_id == user_id,
        Item.title == title
    ).first()


async def send_board_selection(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id

    db = next(get_db())
    boards = db.query(Board).filter(Board.user_id == user_id).order_by(Board.name).all()
    db.close()

    keyboard = []

    for board in boards:
        callback_data = f"board:{board.id}"
        button_text = f"{board.emoji} {board.name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("➕ Создать новую доску", callback_data="create_new_board")])
    keyboard.append([InlineKeyboardButton("❌ Отмена добавления", callback_data="cancel_add_item")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id = user_id,
        text="Куда ты хочешь сохранить этот элемент? Выбери доску или создай новую:",
        reply_markup=reply_markup,
    )
    return SELECT_BOARD


async def boards_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    db = next(get_db())
    message = ""

    try:
        boards = db.query(Board).filter(Board.user_id == user_id).all()
        if not boards:
            message = "У тебя пока нет доски. Создай первую."
        else:
            board_list = "\n".join(
                [f"{b.emoji} **{b.name}** ({len(b.items)} элементов)" for b in boards]
            )
            message = (
                f"📚 **Твои Доски:**\n\n"
                f"{board_list}\n\n"
                f"Чтобы создать новую доску, используй команду /createboard <название> <эмодзи>"
            )

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /boards command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных, попробуй позже.")
    finally:
        db.close()


async def create_new_board_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Еблан? Укажи название доски. Ну хотя-бы: /createboard Python 🐍")
        return

    user_id = update.effective_user.id
    board_name = " ".join(context.args[:-1]) if len(context.args) > 0 else context.args[0]
    board_emoji = context.args[-1] if len(context.args) > 1 and len(context.args[-1]) <= 2 else "📁"

    if board_name == board_emoji:
        board_name = context.args[0]
        board_emoji = "📁"

    db = next(get_db())

    try:
        existing_board = db.query(Board).filter(
            Board.user_id == user_id,
            Board.name.ilike(board_name),
        ).first()

        if existing_board:
            await update.message.reply_text(f"Доска с названием **{board_name}** уже существует. Попробуй другое название.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        new_board = Board(
            name=board_name,
            emoji=board_emoji,
            user_id=user_id,
        )
        db.add(new_board)
        db.commit()
        await update.message.reply_text(f"✅ Новая доска **{board_emoji} {board_name}** успешно создана!",
                                        parse_mode=ParseMode.MARKDOWN)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /createboard command: {sqlex}")
        await update.message.reply_text("Ошибка базы данных при создании доски")
    finally:
        db.close()


async def show_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи название доски, например /show Неотсортированное")
        return

    board_name = " ".join(context.args)
    db = next(get_db())

    try:
        board = db.query(Board).filter(
            Board.user_id == user_id,
            func.lower(Board.name) == func.lower(board_name),
        ).first()

        if not board:
            await update.message.reply_text(f"Доска с названием *{board_name}* не найдена.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        items = db.query(Item).filter(Item.board_id == board.id).order_by(Item.title).all()

        if not items:
            await update.message.reply_text(f"Доска **{board.emoji} {board.name}** пуста.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        item_list = "\n".join(
            [f"• {item.title}" for item in items]
        )

        message = (
            f"📦 **Элементы в доске {board.emoji} {board.name}**:\n\n"
            f"{item_list}\n\n"
            f"Чтобы получить элемент, используй: /view <название>"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /show command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при просмотре доски.")
    finally:
        db.close()


async def view_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи название элемента для просмотра, например /show Моя первая запись")
        return

    item_title = " ".join(context.args)
    db = next(get_db())

    try:
        item = find_item_by_title(db, user_id, item_title)

        if not item:
            await update.message.reply_text(f"Элемент с названием **{item_title}** не найден.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        if item.content_type == 'link':
            await update.message.reply_text(f"*{item.title}* (из доски *{item.board.name}*):\n" + item.content_data,
                                            parse_mode=ParseMode.MARKDOWN)
        elif item.content_type in ('photo', 'document', 'video'):
            if item.content_type == 'photo':
                await update.message.reply_photo(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                 parse_mode=ParseMode.MARKDOWN)
            elif item.content_type == 'document':
                await update.message.reply_document(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                    parse_mode=ParseMode.MARKDOWN)
            elif item.content_type == 'video':
                await update.message.reply_video(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                 parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"*{item.title}* (из доски *{item.board.name}*):" + item.content_data,
                                            parse_mode=ParseMode.MARKDOWN)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /view command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при получении элемента.")
    except Exception as e:
        logger.error(f"Exception on sending content: {e}")
        await update.message.reply_text("Ошибка при отправке контента (возможно, file_id устарел или неверен).")
    finally:
        db.close()


async def remove_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи полное название элемента, который нужно удалить. Пример: /remove статья")
        return

    item_title = " ".join(context.args)
    db = next(get_db())

    try:
        item = find_item_by_title(db, user_id, item_title)

        if not item:
            await update.message.reply_text(f"Элемент с названием **'{item_title}'** не найден.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        board_name = item.board.name
        db.delete(item)
        db.commit()

        await update.message.reply_text(f"🗑️ Элемент **'{item_title}'** (из доски **{board_name}**) был успешно удален.",
                                        parse_mode=ParseMode.MARKDOWN)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /remove command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при удалении элемента.")
    finally:
        db.close()


async def add_item_conservation(update: Update, context: CallbackContext) -> int:
    message = update.message

    content_type, data, suggested_title = extract_content_info(message)

    if not data:
        await update.message.reply_text("Отправь мне ссылку, файл или медиа-контент для сохранения.")
        return ConversationHandler.END

    context.user_data["temp_item"] = {
        "content_type": content_type,
        "content_data": data,
        "telegram_message_id": message.message_id,
    }

    await message.reply_text(
        f"✅ Отлично, я получил твой контент.\n\n"
        f"**Шаг 1 из 2:** Придумай название для этого элемента. \n"
        f"*(Можешь просто ответить на это сообщение, чтобы использовать название по умолчанию:)*\n"
        f"*{suggested_title}*",
        parse_mode=ParseMode.MARKDOWN,
    )
    context.user_data["suggested_item"] = suggested_title

    return GET_TITLE


async def get_title(update: Update, context: CallbackContext) -> int:
    user_response = update.message.text

    if user_response.startswith("/"):
        await update.message.reply_text("Название не может быть командой. Попробуй еще раз или используй /cancel.")
        return GET_TITLE

    final_title = user_response

    if not final_title or len(final_title.strip()) == 0:
        final_title = context.user_data.get('suggested_item', "Элемент без названия")

    context.user_data["temp_item"]["title"] = final_title
    await update.message.reply_text(f"🔥 Отлично! Название: **{final_title}**.", parse_mode=ParseMode.MARKDOWN)
    return await send_board_selection(update, context)


async def inline_board_selection(update: Update, context: CallbackContext) -> int:
    try:
        query = update.callback_query
        await query.answer()

        action = query.data
        user_id = query.from_user.id

        if action == "cancel_add_item":
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=query.message.message_id,
                text="❌ Добавление элемента отменено."
            )
            context.user_data.pop("temp_item", None)
            return ConversationHandler.END

        elif action == "create_new_board":
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=query.message.message_id,
                text="Для создания новой доски используй команду /createboard <название> <эмодзи>"
            )
            context.user_data.pop("temp_item", None)
            return ConversationHandler.END

        elif action.startswith("board:"):
            board_id = int(action.split(":")[1])

            if "temp_item" not in context.user_data:
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="❌ Ошибка: данные устарели. Начни заново."
                )
                return ConversationHandler.END

            item_data = context.user_data["temp_item"]
            db = next(get_db())

            try:
                new_item = Item(
                    user_id=user_id,
                    board_id=board_id,
                    title=item_data["title"],
                    content_type=item_data["content_type"],
                    content_data=item_data["content_data"],
                )

                db.add(new_item)
                db.commit()

                board = db.query(Board).filter(Board.id == board_id).first()
                board_name = board.name if board else "Неизвестная доска"

                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text=f"✅ Элемент **'{item_data['title']}'** успешно сохранен в доску **{board_name}**!",
                    parse_mode=ParseMode.MARKDOWN
                )

            except SQLAlchemyError as sqlex:
                logger.error(f"SQLAlchemy Error on save element in database: {sqlex}")
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="Ошибка при сохранении в базу данных. Попробуй еще раз."
                )
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="Произошла непредвиденная ошибка. Попробуй еще раз."
                )
            finally:
                db.close()
                context.user_data.pop("temp_item", None)
                return ConversationHandler.END

        else:
            return SELECT_BOARD

    except Exception as e:
        await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="❌ Произошла критическая ошибка. Попробуй еще раз."
            )
        return ConversationHandler.END


async def cancel_add_item(update: Update, context: CallbackContext) -> int:
    if "temp_item" not in context.user_data:
        await update.message.reply_text("❌ Нет активного процесса добавления для отмены.")
        return ConversationHandler.END

    context.user_data.pop("temp_item", None)
    await update.message.reply_text("❌ Добавление элемента отменено.")
    return ConversationHandler.END