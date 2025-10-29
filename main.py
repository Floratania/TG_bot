from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, PicklePersistence
)
from telegram.ext import filters
from config import TOKEN
from handlers.start_handler import start, save_user_contact, ASK_PHONE, MAIN_MENU
from handlers.menu_handler import show_social_media, menu_handler
from handlers.support_handler import get_support_handler


# --- Кастомний фільтр: користувач не в підтримці ---
class NotInSupportFilter(filters.BaseFilter):
    def filter(self, message):
        """Повертає True, якщо користувач НЕ у підтримці (клієнт або менеджер)."""
        application = message.get_bot().application
        user_data = application.chat_data.get(message.chat_id, {})
        support_state = user_data.get("support_state")
        # Якщо support_state будь-який, крім "closed", то користувач у підтримці
        return support_state is None or support_state == "closed"


def main():
    # --- Збереження станів (PicklePersistence) ---
    persistence = PicklePersistence(filepath="bot_data.pkl")

    # --- Створення Application ---
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # --- Основна розмова (авторизація + меню) ---
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.COMMAND, start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, start)
        ],
        states={
            ASK_PHONE: [
                MessageHandler(filters.CONTACT, save_user_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_contact)
            ],
            MAIN_MENU: [
                MessageHandler(filters.Regex("🌐 Наші соцмережі"), show_social_media),
                MessageHandler(filters.Regex("💬 Підтримка"), menu_handler),
                MessageHandler(filters.Regex("❓ Часті питання"), menu_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        name="my_conversation",
        persistent=True
    )

    application.add_handler(conv_handler)

    # --- Обробники підтримки ---
    client_support_handler, manager_support_handler, notification_callback_handler = get_support_handler()
    application.add_handler(client_support_handler)
    application.add_handler(manager_support_handler)
    application.add_handler(notification_callback_handler)

    # --- Фільтр "не в підтримці" ---
    not_in_support = NotInSupportFilter(application)

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & not_in_support,
            menu_handler
        )
    )


    print("✅ Бот запущено")
    application.run_polling()


if __name__ == "__main__":
    main()
