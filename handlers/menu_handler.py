# handlers/menu_handler.py
from telegram import Update
from telegram.ext import ContextTypes
# Змінено: Додано main_menu та client_support_menu
from keyboards import social_media_menu, main_menu, client_support_menu 
from db import SessionLocal 
from storage import is_manager 
from config import SUPER_ADMIN_ID
from handlers.support_handler import open_support_manager, start_support 
from handlers.support_handler import client_message


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
    except Exception as e:
        print(f"ERROR in menu_handler check is_manager: {e}")
        is_mgr = False 
    finally:
        db.close()

    action_performed = False 
    
    if text == "🌐 Наші соцмережі":
        await show_social_media(update, context)
        action_performed = True
        
    elif text == "💬 Підтримка":
        if is_mgr:
            # Для менеджера: відкриваємо панель чатів
            return await open_support_manager(update, context)
        else:
            # === ДІЯ: Викликаємо start_support та повертаємо його стан ===
            # Зміна клавіатури має відбутися всередині start_support
            return await start_support(update, context)
            # action_performed = True; -- недосяжно і видалено
            
    elif text == "❓ Часті питання":
        await update.message.reply_text("❓ Тут будуть часті питання...")
        action_performed = True
        
    # --- ЛОГІКА ПОВЕРНЕННЯ КЛАВІАТУРИ ---
    if action_performed and update.message:
        # Надсилаємо клавіатуру, щоб вона "залишилася" внизу екрана
        await update.message.reply_text(
            "Головне меню:", 
            reply_markup=main_menu(telegram_id)
        )
    
    return