import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ConversationHandler

from database.database import Item
from database.database_worker import get_all_user_boards, get_board_by_name, update_board_name, create_new_board, \
    get_all_items_by_board_id, get_item_by_title, get_all_items_by_keyword, remove_item_by_id, move_item, \
    get_all_user_board_count, get_all_user_item_count, get_item_stats, create_new_item, get_board_by_id, get_item_by_id, \
    get_board_item_count

from database.database_worker import remove_board_by_id
from files.encryption_manager import encryption_manager
from files.file_manager import file_manager

logger = logging.getLogger(__name__)
GET_TITLE, SELECT_BOARD = range(2)

ALL_FILE_TYPES = ['photo', 'document', 'video']

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


async def send_board_selection(update: Update, context: CallbackContext) -> int | None:
    try:
        user_id = update.effective_user.id

        boards = await get_all_user_boards(user_id)

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
    except SQLAlchemyError as sqlex:
        logger.error(sqlex)


async def boards_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    message = ""

    try:
        boards = await get_all_user_boards(user_id)
        if not boards:
            message = "У тебя пока нет доски. Создай первую."
        else:
            board_list = "\n".join(
                [f"{b.emoji} <b>{b.name}</b> ({await get_board_item_count(user_id, b.id)} элементов)" for b in boards]
            )
            message = (
                f"📚 <b>Твои Доски:</b>\n\n"
                f"{board_list}\n\n"
                f"Чтобы создать новую доску, используй команду /createboard название эмодзи"
                f"Чтобы создать новую доску, используй команду /createboard название эмодзи"
            )

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQL Error on /boards command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных, попробуй позже.")


async def rename_board_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используй: /renameboard старое_название новое_название [эмодзи]\n"
            "Пример: /renameboard Стараядоска Новаядоска 🎯"
        )
        return

    user_id = update.effective_user.id
    old_name = context.args[0]
    new_name = context.args[1]
    new_emoji = context.args[2] if len(context.args) > 2 else None

    try:
        board = await get_board_by_name(user_id, old_name)

        if not board:
            await update.message.reply_text(f"❌ Доска с названием '{old_name}' не найдена.")
            return

        existing_board = await get_board_by_name(user_id, new_name)

        if existing_board and existing_board.id != board.id:
            await update.message.reply_text(f"❌ Доска с названием '{new_name}' уже существует.")
            return

        old_name, old_emoji, new_name, final_emoji = await update_board_name(user_id, board.id, new_name, new_emoji)

        await update.message.reply_text(
            f"✅ Доска '{old_emoji} {old_name}' переименована в '{final_emoji} {new_name}'!"
        )
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /renameboard command: {sqlex}")
        await update.message.reply_text("❌ Ошибка базы данных при переименовании доски.")


async def create_new_board_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Укажи название доски. Например: /createboard Python 🐍")
        return

    user_id = update.effective_user.id
    board_name = " ".join(context.args[:-1]) if len(context.args) > 0 else context.args[0]
    board_emoji = context.args[-1] if len(context.args) > 1 and len(context.args[-1]) <= 2 else "📁"

    if board_name == board_emoji:
        board_name = context.args[0]
        board_emoji = "📁"

    try:
        existing_board = await get_board_by_name(user_id, board_name)

        if existing_board:
            await update.message.reply_text(f"Доска с названием <b>{board_name}</b> уже существует. Попробуй другое название.",
                                            parse_mode=ParseMode.HTML)
            return

        await create_new_board(user_id, board_name, board_emoji)
        await update.message.reply_text(f"✅ Новая доска <b>{board_emoji} {board_name}</b> успешно создана!",
                                        parse_mode=ParseMode.HTML)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /createboard command: {sqlex}")
        await update.message.reply_text("Ошибка базы данных при создании доски")


async def show_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи название доски, например /show Неотсортированное")
        return

    board_name = " ".join(context.args)
    try:
        board = await get_board_by_name(user_id, board_name)

        if not board:
            await update.message.reply_text(f"Доска с названием <b>{board_name}</b> не найдена.",
                                            parse_mode=ParseMode.HTML)
            return

        items = await get_all_items_by_board_id(user_id, board.id)

        if not items:
            await update.message.reply_text(f"Доска <b>{board.emoji} {board.name}</b> пуста.",
                                            parse_mode=ParseMode.HTML)
            return

        item_list = "\n".join(
            [f"• {item.title}" for item in items]
        )

        message = (
            f"📦 <b>Элементы в доске {board.emoji} {board.name}</b>:\n\n"
            f"{item_list}\n\n"
            f"Чтобы получить элемент, используй: /view название"
            f"Чтобы получить элемент, используй: /view название"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /show command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при просмотре доски.")


async def view_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи название элемента для просмотра, например /view Моя первая запись")
        return

    item_title = " ".join(context.args)

    try:
        items = await get_all_items_by_keyword(user_id, item_title)

        if not items:
            await update.message.reply_text(f"Элемент, содержащий <b>{item_title}</b> не найден.",
                                            parse_mode=ParseMode.HTML)
            return

        if len(items) > 1:
            item_list = "\n".join([f"• {item.title} (в доске {item.board.emoji} {item.board.name})" for item in items])
            keyboard = [[InlineKeyboardButton(item.title, callback_data=f"select_item:{item.id}")] for item in items[:5]]
            message = (f"Найдено <b>{len(items)}</b> совпадений для <b>'{item_title}'</b>:\n\n"
                       f"{item_list}\n\nУточни название или выбери элемент:")

            await update.message.reply_text(message, parse_mode=ParseMode.HTML,
                                            reply_markup=InlineKeyboardMarkup(keyboard))
            return

        item = items[0]
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Удалить", callback_data=f"remove_item:{item.id}")],
        ])

        await send_item_content(update, context, item, reply_markup)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /view command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при получении элемента.")


async def remove_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи полное название элемента, который нужно удалить. Пример: /remove статья")
        return

    item_title = " ".join(context.args)

    try:
        item = await get_item_by_title(user_id, item_title)

        board = await get_board_by_id(user_id, item.board_id)
        board_name = board.name if board else "Неизвестная доска"

        if item.content_type in ALL_FILE_TYPES and item.file_path:
            try:
                file_manager.delete_file(item.file_path)
                print(f"Removed file: {item.file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {item.file_path}: {e}")

        await remove_item_by_id(user_id, item.id)
        await update.message.reply_text(f"🗑️ Элемент <b>'{item_title}'</b> (из доски <b>{board_name}</b>) был успешно удален.",
                                        parse_mode=ParseMode.HTML)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /remove command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при удалении элемента.")
    except ValueError as vex:
        logger.error(f"ValueError on /remove command: {vex}")
        await update.message.reply_text(f"Элемент с названием <b>'{item_title}'</b> не найден.",
                                        parse_mode=ParseMode.HTML)


async def remove_board_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Укажи название доски для удаления, например: /removeboard Неотсортированное")
        return

    board_name = " ".join(context.args)

    try:
        board = await get_board_by_name(user_id, board_name)
        if not board:
            await update.message.reply_text(f"Доска с названием <b>'{board_name}'</b> не найдена.",
                                            parse_mode=ParseMode.HTML)
            return
        if not board:
            await update.message.reply_text(f"Доска с названием <b>'{board_name}'</b> не найдена.",
                                            parse_mode=ParseMode.HTML)
            return

        items = await get_all_items_by_board_id(user_id, board.id)
        for item in items:
            if item.content_type in ALL_FILE_TYPES and item.file_path:
                try:
                    file_manager.delete_file(item.file_path)
                except FileNotFoundError:
                    logger.warning(f"File not found: {item.file_path}")
                except Exception as e:
                    logger.error(f"Error on deleting file: {e}")
            await remove_item_by_id(user_id, item.id)
        await remove_board_by_id(user_id, board.id)
        await update.message.reply_text(f"🗑️ Доска <b>'{board_name}'</b> и все её элементы были успешно удалены.",
                                        parse_mode=ParseMode.HTML)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /removeboard command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при удалении доски.")
    except ValueError as vex:
        logger.error(f"ValueError on /remove command: {vex}")
        await update.message.reply_text(f"Доска с названием <b>'{board_name}'</b> не найдена.",
                                        parse_mode=ParseMode.HTML)


async def move_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text("Укажи название элемента и доски, например: move Первая запись Первая доска")
        return

    target_board_name = context.args[-1]
    item_title = " ".join(context.args[:-1])

    try:
        item = await get_item_by_title(user_id, item_title)

        if not item:
            await update.message.reply_text(f"Элемент с названием <b>{item_title}</b> не найден.",
                                            parse_mode=ParseMode.HTML)
            return

        old_board_name = item.board.name
        target_board = await get_board_by_name(user_id, target_board_name)

        if not target_board:
            await update.message.reply_text(f"Доска с названием: <b>{target_board_name}</b> не найдена.",
                                            parse_mode=ParseMode.HTML)
            return

        if item.board_id == target_board.id:
            await update.message.reply_text(f"Элемент <b>{item_title}</b> уже находит в доске <b>{target_board_name}</b>",
                                            parse_mode=ParseMode.HTML)
            return

        await move_item(user_id, item.id, target_board.id)
        await update.message.reply_text(f"✅ Элемент <b>{item_title}</b> успешно перемещён из <b>{old_board_name}</b> в <b>{target_board_name}</b>",
                                        parse_mode=ParseMode.HTML)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /move command: {sqlex}")
        await update.message.reply_text("Произошла ошибка базы данных при перемещении элемента.")


async def stats_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    try:
        board_count = await get_all_user_board_count(user_id)
        total_items = await get_all_user_item_count(user_id)

        item_stats = await get_item_stats(user_id)

        if total_items == 0:
            message = "📊 <b>Твоя Статистика PinTag:</b>\n\n" \
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
                f"📊 <b>Твоя Статистика PinTag:</b>\n\n"
                f"🔸 <b>Доски:</b> {board_count}\n"
                f"🔸 <b>Всего элементов:</b> {total_items}\n\n"
                f"<b>Разбивка по типу контента:</b>\n"
                f"{stats_text}"
            )

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on /stats command: {sqlex}")
        await update.message.reply_text("Ошибка базы данных при обработке статистики")


async def add_item_conservation(update: Update, context: CallbackContext) -> int:
    message = update.message
    user_id = update.effective_user.id

    content_type, data, suggested_title = extract_content_info(message)

    if not data:
        await update.message.reply_text("Отправь мне ссылку, файл или медиа-контент для сохранения.")
        return ConversationHandler.END

    file_path = None
    if content_type in ALL_FILE_TYPES:
        try:
            file = await context.bot.get_file(data)
            file_data = await file.download_as_bytearray()

            if content_type == 'document':
                original_filename = message.document.file_name
            else:
                file_extension = '.jpg' if content_type == 'photo' else '.mp4'
                original_filename = f"{content_type}_{int(datetime.now().timestamp())}{file_extension}"

            encrypted_data = encryption_manager.encrypt_file(bytes(file_data))
            file_path = file_manager.save_file(
                encrypted_data,
                user_id,
                content_type + 's',
                original_filename,
            )

        except Exception as e:
            logger.error(f"Error saving file: {e}")
            await update.message.reply_text("❌ Ошибка при сохранении файла")
            return ConversationHandler.END

    is_file = content_type in ALL_FILE_TYPES
    context.user_data["temp_item"] = {
        "content_type": content_type,
        "content_data": data,
        "file_path": file_path,
        "file_size": file_manager.get_file_size(file_path) if file_path else 0,
        "encrypted": True if is_file and file_path else False,
        "telegram_message_id": message.message_id,
    }

    await message.reply_text(
        f"✅ Отлично, я получил твой контент.\n\n"
        f"<b>Шаг 1 из 2:</b> Придумай название для этого элемента.",
        parse_mode=ParseMode.HTML,
    )
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
    await update.message.reply_text(f"🔥 Отлично! Название: <b>{final_title}</b>.", parse_mode=ParseMode.HTML)
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
            current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            board_name = f"{current_time}-Новая-доска"
            board_emoji = "📁"

            try:
                existing_board = await get_board_by_name(user_id, board_name)

                if existing_board:
                    import random
                    board_name = f"{current_time}-Новая-доска-{random.randint(1000, 9999)}"

                new_board = await create_new_board(user_id, board_name, board_emoji)

                board_id = new_board.id
                item_data = context.user_data["temp_item"]

                await create_new_item(
                    user_id=user_id,
                    board_id=board_id,
                    title=item_data["title"],
                    content_type=item_data["content_type"],
                    content_data=item_data["content_data"],
                    file_path=item_data["file_path"],
                    file_size=item_data["file_size"],
                    encrypted=item_data["encrypted"],
                )

                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text=f"✅ Создана новая доска <b>{board_emoji} {board_name}</b> и элемент <b>'{item_data['title']}'</b> сохранен в неё!",
                    parse_mode=ParseMode.HTML
                )
            except SQLAlchemyError as sqlex:
                logger.error(f"SQLAlchemy Error creating board: {sqlex}")
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="Ошибка при создании доски и сохранении элемента."
                )
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="Произошла ошибка."
                )
            finally:
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

            try:
                new_item = await create_new_item(user_id=user_id,
                    board_id=board_id,
                    title=item_data["title"],
                    content_type=item_data["content_type"],
                    content_data=item_data["content_data"],
                    file_path=item_data["file_path"],
                    file_size=item_data["file_size"],
                    encrypted=item_data["encrypted"],
                )

                board = await get_board_by_id(user_id, board_id)
                board_name = board.name if board else "Неизвестная доска"

                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text=f"✅ Элемент <b>'{item_data['title']}'</b> успешно сохранен в доску <b>{board_name}</b>!",
                    parse_mode=ParseMode.HTML
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
                context.user_data.pop("temp_item", None)
                return ConversationHandler.END

        else:
            return SELECT_BOARD

    except Exception:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="❌ Произошла критическая ошибка. Попробуй еще раз."
        )
        return ConversationHandler.END


async def send_item_content(update: Update, context: CallbackContext, item: Item,
                            reply_markup: InlineKeyboardMarkup = None,
                            delete_previous_message_id: int = None):
    caption = f"<b>{item.title}</b> (из доски <b>{item.board.name}</b>):"

    try:
        if update.callback_query:
            chat_id = update.callback_query.message.chat.id
            message_for_reply = None
        else:
            chat_id = update.effective_chat.id
            message_for_reply = update.message

        if delete_previous_message_id:
            try:
                await context.bot.delete_message(chat_id, delete_previous_message_id)
            except Exception as e:
                logger.warning(f"Could not delete message {delete_previous_message_id}: {e}")

        async def send_message():
            if item.content_type in ('photo', 'document', 'video'):
                if item.content_data:
                    try:
                        if item.content_type == 'photo':
                            if message_for_reply:
                                await message_for_reply.reply_photo(item.content_data, caption=caption,
                                                                   parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                            else:
                                await context.bot.send_photo(chat_id, item.content_data, caption=caption,
                                                           parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                        elif item.content_type == 'document':
                            if message_for_reply:
                                await message_for_reply.reply_document(item.content_data, caption=caption,
                                                                      parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                            else:
                                await context.bot.send_document(chat_id, item.content_data, caption=caption,
                                                              parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                        elif item.content_type == 'video':
                            if message_for_reply:
                                await message_for_reply.reply_video(item.content_data, caption=caption,
                                                                   parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                            else:
                                await context.bot.send_video(chat_id, item.content_data, caption=caption,
                                                           parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                        return
                    except Exception as e:
                        logger.warning(f"File_id failed, trying local file: {e}")

                if item.file_path and os.path.exists(item.file_path):
                    file_data = file_manager.get_file(item.file_path)

                    if getattr(item, 'encrypted', False):
                        file_data = encryption_manager.decrypt_file(file_data)

                    filename = Path(item.file_path).name

                    if item.content_type == 'photo':
                        await context.bot.send_photo(chat_id, file_data, caption=caption,
                                                   parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                    elif item.content_type == 'document':
                        await context.bot.send_document(chat_id, file_data, caption=caption, filename=filename,
                                                      parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                    elif item.content_type == 'video':
                        await context.bot.send_video(chat_id, file_data, caption=caption,
                                                   parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                else:
                    await context.bot.send_message(chat_id, "❌ Файл не найден на сервере")
            else:
                full_text = caption + ("\n" + item.content_data if item.content_data else "")
                if message_for_reply:
                    await message_for_reply.reply_text(full_text, parse_mode=ParseMode.HTML,
                                                     reply_markup=reply_markup)
                else:
                    await context.bot.send_message(chat_id, full_text, parse_mode=ParseMode.HTML,
                                                 reply_markup=reply_markup)
        await send_message()
    except Exception as e:
        logger.error(f"Error sending {item.content_type}: {e}")
        error_chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat.id
        await context.bot.send_message(error_chat_id, f"❌ Ошибка при отправке {item.content_type}")


async def inline_item_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        await query.answer()

        action = query.data
        user_id = query.from_user.id

        if action.startswith("select_item:"):
            item_id = int(action.split(":")[1])
            item = await get_item_by_id(user_id, item_id)

            if not item:
                await query.edit_message_text("❌ Элемент не найден")
                return

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Удалить", callback_data=f"remove_item:{item.id}")],
            ])
            await send_item_content(update, context, item, reply_markup, query.message.message_id)
    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error in inline button selection: {sqlex}")
        await query.edit_message_text("Ошибка базы данных")


async def inline_board_item(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    try:
        await query.answer()

        action = query.data
        user_id = query.from_user.id

        if action.startswith("remove_item:"):
            item_id = int(action.split(":")[1])
            item = await get_item_by_id(user_id, item_id)

            if not item:
                await query.delete_message()
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Элемент с id <b>{item_id}</b> не был найден.",
                    parse_mode='HTML'
                )
                return

            item_name = item.title
            if item.content_type in ALL_FILE_TYPES and item.file_path:
                try:
                    file_manager.delete_file(item.file_path)
                    print(f"Removed file: {item.file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {item.file_path}: {e}")

            await remove_item_by_id(user_id, item.id)

            try:
                await query.delete_message()
            except Exception as e:
                logger.warning(f"Could not delete original message: {e}")

            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Элемент <b>{item_name}</b> успешно удалён.",
                parse_mode='HTML'
            )

    except SQLAlchemyError as sqlex:
        logger.error(f"SQLAlchemy Error on delete element in database: {sqlex}")
        try:
            await query.delete_message()
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="❌ Ошибка базы данных при удалении элемента."
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Unexpected error in inline_board_item: {e}")
        try:
            await query.delete_message()
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="❌ Произошла непредвиденная ошибка при удалении."
            )
        except:
            pass

async def cancel_add_item(update: Update, context: CallbackContext) -> int:
    if "temp_item" not in context.user_data:
        await update.message.reply_text("❌ Нет активного процесса добавления для отмены.")
        return ConversationHandler.END

    context.user_data.pop("temp_item", None)
    await update.message.reply_text("❌ Добавление элемента отменено.")
    return ConversationHandler.END