import logging

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ConversationHandler

from Database.database import get_db, Board, Item
from utils.item_searcher import find_item_by_title, find_items_by_keyword, find_item_by_id

logger = logging.getLogger(__name__)
GET_TITLE, SELECT_BOARD = range(2)

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
        await update.message.reply_text("Укажи название элемента для просмотра, например /view Моя первая запись")
        return

    item_title = " ".join(context.args)
    db = next(get_db())

    try:
        items = find_items_by_keyword(db, user_id, item_title)

        if not items:
            await update.message.reply_text(f"Элемент, содержащий *{item_title}* не найден.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        if len(items) > 1:
            item_list = "\n".join(
                [f"• {item.title} (в доске {item.board.emoji} {item.board.name})" for item in items]
            )
            message = (
                f"Найдено *{len(items)}* совпадений для *'{item_title}'*:\n\n"
                f"{item_list}\n\n"
                f"Уточни название для команды /view, чтобы получить нужный элемент."
            )
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            return

        item = items[0]

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🗑 Удалить", callback_data=f"remove_item:{item.id}")],
        ])

        if item.content_type == 'link':
            await update.message.reply_text(f"*{item.title}* (из доски *{item.board.name}*):\n" + item.content_data,
                                            parse_mode=ParseMode.MARKDOWN,
                                            reply_markup=reply_markup)
        elif item.content_type in ('photo', 'document', 'video'):
            if item.content_type == 'photo':
                await update.message.reply_photo(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                 parse_mode=ParseMode.MARKDOWN,
                                                 reply_markup=reply_markup)
            elif item.content_type == 'document':
                await update.message.reply_document(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                    parse_mode=ParseMode.MARKDOWN,
                                                    reply_markup=reply_markup)
            elif item.content_type == 'video':
                await update.message.reply_video(item.content_data, caption=f"*{item.title}* (из доски *{item.board.name}*):",
                                                 parse_mode=ParseMode.MARKDOWN,
                                                 reply_markup=reply_markup)
        else:
            await update.message.reply_text(f"*{item.title}* (из доски *{item.board.name}*):" + item.content_data,
                                            parse_mode=ParseMode.MARKDOWN,
                                            reply_markup=reply_markup)

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



async def move_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text("Укажи название элемента и доски, например: move Первая запись Первая доска")
        return

    target_board_name = context.args[-1]
    item_title = " ".join(context.args[:-1])

    db = next(get_db())
    try:
        item = find_item_by_title(db, user_id, item_title)

        if not item:
            await update.message.reply_text(f"Элемент с названием *{item_title}* не найден.",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        old_board_name = item.board.name

        target_board = db.query(Board).filter(
            Board.user_id == user_id,
            func.lower(Board.name) == func.lower(target_board_name)
        ).first()

        if not target_board:
            await update.message.reply_text(f"Доска с названием: *{target_board_name} не найдена.*",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        if item.board_id == target_board.id:
            await update.message.reply_text(f"Элемент *{item_title}* уже находит в доске *{target_board_name}*",
                                            parse_mode=ParseMode.MARKDOWN)
            return

        item.board_id = target_board.id
        db.commit()

        await update.message.reply_text(f"✅ Элемент *{item_title}* успешно перемещён из *{old_board_name}* в *{target_board_name}*",
                                        parse_mode=ParseMode.MARKDOWN)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /move command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при перемещении элемента.")
    finally:
        db.close()


async def stats_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    db = next(get_db())

    try:
        board_count = db.query(Board).filter(Board.user_id == user_id).count()
        total_items = db.query(Item).filter(Item.user_id == user_id).count()

        item_stats = db.query(
            Item.content_type,
            func.count(Item.id),
        ).filter(
            Item.user_id == user_id,
        ).group_by(Item.content_type).all()

        if total_items == 0:
            message = "📊 *Твоя Статистика PinTag:*\n\n" \
                      "У тебя пока нет сохраненных элементов."
        else:
            type_mapping = {
                'link': '🔗 Ссылки',
                'photo': '🖼️ Фото',
                'document': '📄 Документы',
                'video': '📹 Видео',
                'text': '📝 Текст',
                'audio': '🔊 Аудио',
            }

            stats_list = []
            for item_type, count in item_stats:
                display_name = type_mapping.get(item_type, item_type.capitalize())
                stats_list.append(f"    • {count}: {display_name}")

            stats_text = "\n".join(stats_list)

            message = (
                f"📊 *Твоя Статистика PinTag:*\n\n"
                f"🔸 *Доски:* {board_count}\n"
                f"🔸 *Всего элементов:* {total_items}\n\n"
                f"*Разбивка по типу контента:*\n"
                f"{stats_text}"
            )

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /stats command: {sqlex}")
        await update.message.reply_text("Ошибка базы данных при обработке статистики")
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


async def inline_board_item(update: Update, context: CallbackContext) -> None:
    try:
        query = update.callback_query
        await query.answer()

        action = query.data
        user_id = query.from_user.id

        if action.startswith("remove_item:"):
            item_id = int(action.split(":")[1])

            db = next(get_db())
            item = find_item_by_id(db, user_id, item_id)

            if not item:
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text=f"Элемент с id *{item_id}* не был найден.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            item_name = item.title
            db.delete(item)
            db.commit()
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=query.message.message_id,
                text=f"✅ Элемент *{item_name}({item_id})* успешно удалён.",
                parse_mode=ParseMode.MARKDOWN
            )
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on delete element in database: {sqlex}")
        await context.bot.sendMessage(
            chat_id=update.effective_user.id,
            text="Ошибка базы данных при удалении элемента."
        )


async def cancel_add_item(update: Update, context: CallbackContext) -> int:
    if "temp_item" not in context.user_data:
        await update.message.reply_text("❌ Нет активного процесса добавления для отмены.")
        return ConversationHandler.END

    context.user_data.pop("temp_item", None)
    await update.message.reply_text("❌ Добавление элемента отменено.")
    return ConversationHandler.END