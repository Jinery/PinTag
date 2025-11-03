import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

from Handler.handlers import start_command, help_command, create_new_board_command, boards_command, cancel_add_item, \
    add_item_conservation, GET_TITLE, get_title, SELECT_BOARD, inline_board_selection, show_command, view_command, \
    remove_command

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def main():
    application = Application.builder().token(TOKEN).build()

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

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createboard", create_new_board_command))
    application.add_handler(CommandHandler("boards", boards_command))
    application.add_handler(CommandHandler("show", show_command))
    application.add_handler(CommandHandler("view", view_command))
    application.add_handler(CommandHandler("remove", remove_command))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()