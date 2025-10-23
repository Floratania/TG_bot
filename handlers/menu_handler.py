from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from keyboards import social_media_menu
from handlers.support_handler import start_support  # <- додай цей рядок


async def show_social_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує меню соцмереж при натисканні кнопки."""
    if update.message:  # натискання кнопки ReplyKeyboardMarkup
        await update.message.reply_text(
            "📱 Наші соцмережі:",
            reply_markup=social_media_menu()
        )
    elif update.callback_query:  # натискання Inline кнопки (якщо треба)
        await update.callback_query.message.edit_text(
            "📱 Наші соцмережі:",
            reply_markup=social_media_menu()
        )
        await update.callback_query.answer()



from telegram import Update
from telegram.ext import ContextTypes
from handlers.support_handler import start_support  # запускаємо support через /support
# from handlers.start_handler import show_social_media

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🌐 Наші соцмережі":
        await show_social_media(update, context)
    elif text == "💬 Підтримка":
        # Імітуємо команду /support для запуску ConversationHandler
        await context.bot.send_message(chat_id=update.effective_chat.id, text="/support")
    elif text == "❓ Часті питання":
        await update.message.reply_text("❓ Тут будуть часті питання...")
