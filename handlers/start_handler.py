from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from db import SessionLocal
from storage import save_user, get_user_by_telegram_id # ВИКОРИСТОВУЄМО get_user_by_telegram_id замість is_attached_to_site
from utils import normalize_phone
from keyboards import main_menu
from telegram.error import TelegramError

ASK_PHONE = 0
MAIN_MENU = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Додаємо перевірку, щоб обробляти лише повідомлення, а не інші оновлення, 
    # які можуть бути перехоплені MessageHandler(filters.ALL)
    if not update.message:
        return MAIN_MENU

    try:
        telegram_id = update.message.from_user.id
        print(f"DEBUG: START викликано для ID: {telegram_id}")

        db = SessionLocal()
        user = None
        try:
            # Перевіряємо, чи існує користувач у БД
            user = get_user_by_telegram_id(db, telegram_id)
        except Exception as e:
            print(f"ERROR: Не вдалося перевірити існування користувача в БД: {e}")
        finally:
            db.close()
        
        if user:
            # Користувач вже зареєстрований, одразу показуємо меню
            await update.message.reply_text(
                "👋 Ласкаво просимо!",
                reply_markup=main_menu(telegram_id)
            )
            return MAIN_MENU

        # Якщо не зареєстрований — просимо надіслати номер
        await update.message.reply_text(
            "👋 Привіт!\n📲 Будь ласка, надішліть свій номер телефону:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📞 Поділитися номером", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return ASK_PHONE
    
    except Exception as e:
        print(f"FATAL ERROR in start handler (runtime): {e}")
        # Якщо сталася помилка, намагаємося повідомити користувача
        if update.message:
            await update.message.reply_text("❌ Виникла критична помилка. Спробуйте пізніше.")
        return MAIN_MENU


async def save_user_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        # Обробник для текстових повідомлень, які приходять, коли очікується контакт
        await update.message.reply_text("❗ Надішліть номер кнопкою нижче.")
        return ASK_PHONE

    telegram_id = update.message.from_user.id
    phone = normalize_phone(contact.phone_number)

    db = SessionLocal()
    try:
        # Зберігаємо користувача в БД
        save_user(db, telegram_id, phone, role="користувач") 
        print(f"DEBUG: Користувач {telegram_id} успішно збережений.")
    except Exception as e:
        print(f"FATAL ERROR while saving user {telegram_id}: {e}")
        db.rollback()
        await update.message.reply_text("❌ Помилка збереження даних. Спробуйте пізніше.")
        return MAIN_MENU # Виходимо, якщо не вдалося зберегти
    finally:
        db.close()

    # Відповідь користувачеві
    try:
        await update.message.reply_text(
            "✅ Ви зареєстровані та можете користуватися ботом!",
            reply_markup=main_menu(telegram_id) 
        )
    except Exception as e:
        print(f"FATAL ERROR while generating main_menu/reply: {e}")
        await update.message.reply_text(
            "✅ Ви зареєстровані, але виникла помилка завантаження меню. Спробуйте /start."
        )

    return MAIN_MENU
