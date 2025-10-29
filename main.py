from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, PicklePersistence
)
from config import TOKEN
from handlers.start_handler import start, save_user_contact, ASK_PHONE, MAIN_MENU
from handlers.menu_handler import show_social_media, menu_handler
from handlers.support_handler import get_support_handler

def main():
    # PicklePersistence для збереження станів
    persistence = PicklePersistence(filepath="bot_data.pkl")

    # Створюємо Application
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # --- ConversationHandler для старту ---
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # ДОДАНО: Якщо бот не знає, що робити, він повертає користувача на старт.
            # Це допомагає, коли стан втрачено, але /start не було надіслано.
            MessageHandler(filters.ALL & ~filters.COMMAND, start)
        ],
        states={
            ASK_PHONE: [
                MessageHandler(filters.CONTACT, save_user_contact),
                # Обробляє текстове повідомлення (якщо користувач вводить номер вручну)
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_contact) 
            ],
            MAIN_MENU: [
                # Додаємо всі основні кнопки меню до стану MAIN_MENU 
                # для коректного виходу з ConversationHandler, якщо вони були натиснуті.
                MessageHandler(filters.Regex("🌐 Наші соцмережі"), show_social_media),
                MessageHandler(filters.Regex("💬 Підтримка"), menu_handler),
                MessageHandler(filters.Regex("❓ Часті питання"), menu_handler),
                # Обробка будь-якого іншого тексту в MAIN_MENU
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
            ],
        },
        fallbacks=[],
        name="my_conversation",
        persistent=True
    )

    application.add_handler(conv_handler)

    # --- Система підтримки ---
    client_support_handler, manager_support_handler, notification_callback_handler = get_support_handler()
    
    application.add_handler(client_support_handler)
    application.add_handler(manager_support_handler)
    application.add_handler(notification_callback_handler)

    # --- Обробник головного меню (повинен бути ПІСЛЯ support handlers) ---
    # Цей обробник буде ловити повідомлення, які не були перехоплені ConversationHandler.
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE,
            menu_handler
        )
    )

    print("✅ Бот запущено")
    application.run_polling()

if __name__ == "__main__":
    main()
