from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, PicklePersistence, CallbackQueryHandler
)
from config import TOKEN, SUPER_ADMIN_ID
from handlers.start_handler import start, save_user_contact, ASK_PHONE, MAIN_MENU
from handlers.menu_handler import show_social_media
from handlers.menu_handler import menu_handler
from telegram.ext import MessageHandler, filters
from handlers.support_handler import get_support_handler
from db import Base, engine

from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from handlers.support_handler import get_support_handler
from handlers.support_handler import client_message # ДОДАНО

# --- Створюємо таблиці при першому запуску ---
# Base.metadata.create_all(bind=engine) # ВАЖЛИВО: залиште ЗАКОМЕНТОВАНИМ, оскільки ви використовуєте Laravel для міграцій!

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
                # ... (інші обробники головного меню)
            ],
        },
        fallbacks=[],
        name="my_conversation",
        persistent=True
    )

    application.add_handler(conv_handler)

    # --- Меню підтримки ---
    # client_support_handler, manager_support_handler = get_support_handler()
    
    # application.add_handler(client_support_handler)
    # application.add_handler(manager_support_handler) # Обробник для менеджера
    client_support_handler, manager_support_handler, notification_callback_handler = get_support_handler()
    
    application.add_handler(client_support_handler)
    application.add_handler(manager_support_handler) 
    application.add_handler(notification_callback_handler)
    # Обробник для кнопок головного меню
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE, menu_handler))
    
    # Глобальний обробник для клієнтських повідомлень (автоматично створює/продовжує чат)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, client_message))
    
    
    print("Бот запущено ✅")
    application.run_polling()

if __name__ == "__main__":
    main()