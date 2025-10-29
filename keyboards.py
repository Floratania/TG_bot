# keyboards.py

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from storage import get_user_role
from config import SUPER_ADMIN_ID, FACEBOOK_LINK, INSTAGRAM_LINK, TIKTOK_LINK
from db import SessionLocal

def main_menu(telegram_id):
    db = SessionLocal()
    try:
        role = get_user_role(db, telegram_id)
        # attached = is_attached_to_site(db, telegram_id) - вилучено
    finally:
        db.close()

    # Спрощене меню: містить лише необхідні кнопки та адмін-функції
    keyboard = [
        ["🌐 Наші соцмережі"],
        ["💬 Підтримка", "❓ Часті питання"]
    ]

    if role in ("адмін", "старший адмін") or telegram_id == SUPER_ADMIN_ID:
        keyboard.append(["📢 Розсилка", "📥 Завантажити користувачів"])
    if role == "старший адмін" or telegram_id == SUPER_ADMIN_ID:
        keyboard.append(["➕ Додати адміна", "❌ Видалити адміна"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def social_media_menu():
    buttons = [
        [InlineKeyboardButton("📘 Facebook", url=FACEBOOK_LINK)],
        [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_LINK)],
        [InlineKeyboardButton("📱 TikTok", url=TIKTOK_LINK)]
    ]
    return InlineKeyboardMarkup(buttons)