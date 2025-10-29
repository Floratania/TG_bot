# handlers/menu_handler.py

from telegram import Update
from telegram.ext import ContextTypes
# Змінено: Додано main_menu для повернення головної клавіатури
from keyboards import social_media_menu, main_menu
from db import SessionLocal 
from storage import is_manager 
from handlers.support_handler import open_support_manager 

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
    telegram_id = update.message.from_user.id 
    
    is_mgr = False
    db = SessionLocal()
    try:
        is_mgr = is_manager(db, telegram_id)
    finally:
        db.close()

    # Прапорець, що повідомляє, чи було виконано дію, яка не вимагає повернення меню
    action_performed = False 
    
    if text == "🌐 Наші соцмережі":
        await show_social_media(update, context)
        action_performed = True
        
    elif text == "💬 Підтримка":
        if is_mgr:
            # Для менеджера: відкриваємо панель чатів
            await open_support_manager(update, context)
        else:
            # Для клієнта: відправляємо команду /support. ConversationHandler підхопить її.
            await update.message.reply_text("/support") 
            # Після цієї команди клієнт увійде в інший ConversationHandler
            return # ВИХОДИМО, щоб не відправляти меню двічі
        action_performed = True
        
    elif text == "❓ Часті питання":
        await update.message.reply_text("❓ Тут будуть часті питання...")
        action_performed = True
        
    # Кнопки "🛒 Мої замовлення" та "➕ Зробити замовлення" ВИЛУЧЕНІ.
    
    # --- ВИРІШЕННЯ ПРОБЛЕМИ: ПОВЕРНЕННЯ КЛАВІАТУРИ ---
    # Якщо було виконано дію, ми повторно надсилаємо клавіатуру.
    if action_performed:
        # Надсилаємо клавіатуру, щоб вона "залишилася" внизу екрана
        await update.message.reply_text(
            "Головне меню:", # Можна додати будь-який короткий текст
            reply_markup=main_menu(telegram_id)
        )
    
    # Якщо текст не відповідає жодній кнопці, нічого не робимо, це ігнорується.
    return