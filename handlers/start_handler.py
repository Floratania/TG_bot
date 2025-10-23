from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from db import SessionLocal
from storage import save_user, is_attached_to_site
from utils import normalize_phone
from keyboards import main_menu  # твоя функція для головного меню

ASK_PHONE = 0
MAIN_MENU = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    if is_attached_to_site(telegram_id):
        # Користувач вже прив'язаний, одразу показуємо меню
        await update.message.reply_text(
            "👋 Ласкаво просимо!",
            reply_markup=main_menu(telegram_id)
        )
        return MAIN_MENU

    # Якщо не прив'язаний — просимо надіслати номер
    await update.message.reply_text(
        "👋 Привіт!\n📲 Будь ласка, надішліть свій номер телефону:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📞 Поділитися номером", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return ASK_PHONE

async def save_user_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("❗ Надішліть номер кнопкою нижче.")
        return ASK_PHONE

    telegram_id = update.message.from_user.id
    phone = normalize_phone(contact.phone_number)

    db = SessionLocal()
    try:
        save_user(db, telegram_id, phone, role="користувач")
    finally:
        db.close()

    # Перевіряємо чи прив'язаний user_id
    attached = is_attached_to_site(telegram_id)
    if attached:
        await update.message.reply_text(
            "✅ Ви зареєстровані!",
            reply_markup=main_menu(telegram_id)  # повне меню для прив'язаних
        )
    else:
        await update.message.reply_text(
            "✅ Ви тимчасово зареєстровані. Для доступу до замовлень потрібно прив'язати акаунт на сайті.",
            reply_markup=main_menu(telegram_id)
        )


    return MAIN_MENU
