import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, Application
from telegram.constants import ParseMode

from database.database_worker import (
    create_user_connection, get_user_connections, update_connection_status
)

logger = logging.getLogger(__name__)


async def generate_connect_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    client_name = " ".join(context.args) if context.args else "Неизвестное устройство"

    try:
        connect_id = await create_user_connection(user_id, client_name)

        message = (
            f"🔐 <b>Подключение нового устройства</b>\n\n"
            f"Устройство: <b>{client_name}</b>\n"
            f"Код подключения: <code>{connect_id}</code>\n\n"
            f"Используй этот код в приложении для подключения.\n"
            f"Затем подтверди подключение здесь."
        )

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error generating connect ID: {e}")
        await update.message.reply_text("❌ Ошибка при генерации кода подключения.")


async def send_connection_request(user_id: int, connect_id: str, client_name: str, bot_app: Application):
    try:
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"auth_accept:{connect_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"auth_reject:{connect_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            f"📱 <b>Запрос на подключение</b>\n\n"
            f"Устройство: <b>{client_name}</b>\n"
            f"Хочет получить доступ к твоему аккаунту.\n\n"
            f"Подтвердить подключение?"
        )

        await bot_app.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error sending connection request: {e}")


async def handle_connection_approval(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    try:
        action, connect_id = query.data.split(":")

        if action == "auth_accept":
            success = await update_connection_status(connect_id, 'accepted')

            if success:
                await query.edit_message_text(
                    f"✅ <b>Подключение подтверждено!</b>\n\n"
                    f"Устройство теперь имеет доступ к твоему аккаунту.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.edit_message_text("❌ Подключение не найдено.")

        elif action == "auth_reject":
            success = await update_connection_status(connect_id, 'rejected')

            if success:
                await query.edit_message_text(
                    f"❌ <b>Подключение отклонено</b>\n\n"
                    f"Устройство не получило доступ к твоему аккаунту.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.edit_message_text("❌ Подключение не найдено.")

    except Exception as e:
        logger.error(f"Error handling connection approval: {e}")
        await query.edit_message_text("❌ Ошибка при обработке запроса.")


async def list_connections_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    try:
        connections = await get_user_connections(user_id)

        if not connections:
            await update.message.reply_text("📱 У вас нет подключенных устройств.")
            return

        message = "📱 <b>Подключенные устройства:</b>\n\n"

        for conn in connections:
            status_emoji = "✅" if conn.status == 'accepted' else "⏳" if conn.status == 'pending' else "❌"
            confirmed_time = f"\nПодтверждено: {conn.confirmed_at.strftime('%d.%m.%Y %H:%M')}" if conn.confirmed_at else ""

            message += (
                f"{status_emoji} <b>{conn.client_name}</b>\n"
                f"Статус: {conn.status}{confirmed_time}\n"
                f"Создано: {conn.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error listing connections: {e}")
        await update.message.reply_text("❌ Ошибка при получении списка подключений.")