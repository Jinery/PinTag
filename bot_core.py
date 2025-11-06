import asyncio

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from database.database import init_db
from handler.auth_handler import handle_connection_approval, list_connections_command
from handler.handlers import start_command, help_command

from handler.database_handler import (
    create_new_board_command, boards_command, cancel_add_item,
    add_item_conservation, GET_TITLE, get_title, SELECT_BOARD, inline_board_selection,
    show_command, view_command, remove_command, move_command, stats_command,
    inline_board_item, rename_board_command, inline_item_selection, remove_board_command
)


def build_bot_application(token: str) -> Application:

    application = Application.builder().token(token).build()

    # --- Conversation handler ---
    application.add_handler(ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_item_conservation),
            MessageHandler(filters.PHOTO | filters.ATTACHMENT | filters.VIDEO, add_item_conservation)
        ],
        states={
            GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            SELECT_BOARD: [CallbackQueryHandler(inline_board_selection)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_item)],
        per_message=False,
        per_chat=False,
    ))

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createboard", create_new_board_command))
    application.add_handler(CommandHandler("boards", boards_command))
    application.add_handler(CommandHandler("show", show_command))
    application.add_handler(CommandHandler("view", view_command))
    application.add_handler(CommandHandler("remove", remove_command))
    application.add_handler(CommandHandler("move", move_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("renameboard", rename_board_command))
    application.add_handler(CommandHandler("removeboard", remove_board_command))
    application.add_handler(CommandHandler("connections", list_connections_command))

    # --- Callback Query Handlers ---
    application.add_handler(CallbackQueryHandler(
        inline_item_selection,
        pattern="^select_item:"
    ))
    application.add_handler(CallbackQueryHandler(
        inline_board_item,
        pattern="^remove_item:"
    ))
    application.add_handler(CallbackQueryHandler(handle_connection_approval, pattern="^auth_"))

    return application


async def start_polling_bot(application):
    try:
        await init_db()
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        print("Bot polling cancelled")
    except Exception as e:
        print(f"Bot error: {e}")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()