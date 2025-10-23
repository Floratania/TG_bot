from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters
from storage import save_message, get_user_role, SessionLocal

ASK_QUESTION = 1  # стан діалогу

# --- старт підтримки ---
async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    role = get_user_role(SessionLocal(), telegram_id)
    if role != "користувач":
        await update.message.reply_text("❌ Ця функція лише для клієнтів.")
        return ConversationHandler.END

    await update.message.reply_text(
        "💬 Напишіть своє питання, і наш менеджер незабаром з вами зв'яжеться."
    )
    return ASK_QUESTION

# --- отримання питання від користувача ---
async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    text = update.message.text

    # зберігаємо в базу
    save_message(client_id=telegram_id, sender="client", manager_id=None, type_="text", text=text)

    # відповідаємо користувачу
    await update.message.reply_text("✅ Дякуємо, наш менеджер невдовзі зв'яжеться з вами!")

    return ConversationHandler.END

# --- ConversationHandler ---
def get_support_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("support", start_support)],
        states={
            ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)]
        },
        fallbacks=[],
        name="support_conversation",
        persistent=True
    )
