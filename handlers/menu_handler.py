from telegram import Update
from telegram.ext import ContextTypes
from keyboards import social_media_menu


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


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє натискання кнопок головного меню."""
    text = update.message.text

    if text == "🌐 Наші соцмережі":
        await show_social_media(update, context)
        
    elif text == "💬 Підтримка":
        # Викликаємо команду /support через бота
        await update.message.reply_text("/support")
        # Або краще - явно викликаємо обробник
        from handlers.support_handler import start_support
        await start_support(update, context)
        
    elif text == "❓ Часті питання":
        await update.message.reply_text("❓ Тут будуть часті питання...")
        
    # Додайте інші кнопки меню тут
    elif text == "🛒 Мої замовлення":
        await update.message.reply_text("🛒 Функція в розробці...")
        
    elif text == "➕ Зробити замовлення":
        await update.message.reply_text("➕ Функція в розробці...")