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

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import social_media_menu
from db import SessionLocal 
from storage import is_manager 
# Нам не потрібен явний імпорт start_support, якщо ми покладаємося на ConversationHandler
from handlers.support_handler import open_support_manager # Залишаємо для менеджера
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє натискання кнопок головного меню."""
    text = update.message.text
    telegram_id = update.message.from_user.id 
    
    is_mgr = False
    db = SessionLocal()
    try:
        is_mgr = is_manager(db, telegram_id)
    finally:
        db.close()

    if text == "🌐 Наші соцмережі":
        await show_social_media(update, context)
        
    elif text == "💬 Підтримка":
        if is_mgr:
            # Для менеджера: відкриваємо панель чатів
            await open_support_manager(update, context)
        else:
            # Для клієнта: відправляємо команду /support. ConversationHandler підхопить її.
            await update.message.reply_text("/support") 
        
    elif text == "❓ Часті питання":
        await update.message.reply_text("❓ Тут будуть часті питання...")
        
    # Додайте інші кнопки меню тут
    elif text == "🛒 Мої замовлення":
        await update.message.reply_text("🛒 Функція в розробці...")
        
    elif text == "➕ Зробити замовлення":
        await update.message.reply_text("➕ Функція в розробці...")