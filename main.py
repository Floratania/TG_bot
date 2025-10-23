from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, PicklePersistence, CallbackQueryHandler
)
from config import TOKEN, SUPER_ADMIN_ID
from handlers.start_handler import start, save_user_contact, ASK_PHONE, MAIN_MENU
from handlers.menu_handler import show_social_media
from handlers.menu_handler import menu_handler
from telegram.ext import MessageHandler, filters
from db import Base, engine

from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from handlers.support_handler import get_support_handler

# --- Створюємо таблиці при першому запуску ---
# Base.metadata.create_all(bind=engine)

def main():
    # PicklePersistence для збереження станів і даних користувачів
    persistence = PicklePersistence(filepath="bot_data.pkl")

    # Створюємо Application з персистенцією
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # --- ConversationHandler для старту та головного меню клієнта ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PHONE: [MessageHandler(filters.CONTACT, save_user_contact)],
            MAIN_MENU: [
                MessageHandler(filters.Regex("🌐 Наші соцмережі"), show_social_media),
            ],
        },
        fallbacks=[],
        name="my_conversation",  # обов'язково задаємо ім'я для збереження
        persistent=True
    )

    application.add_handler(conv_handler)

    # --- Меню підтримки для менеджера ---
    # application.add_handler(CommandHandler("support", open_support))
    # application.add_handler(CommandHandler("support", open_support))
    # application.add_handler(CallbackQueryHandler(support_callback))
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_client))  # для менеджера
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, client_message)) 
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    application.add_handler(get_support_handler())

    print("Бот запущено ✅")
    application.run_polling()  # синхронний виклик

if __name__ == "__main__":
    main()
