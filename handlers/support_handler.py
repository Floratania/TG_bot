from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode # Виправлений імпорт ParseMode
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters, CallbackQueryHandler
from storage import save_message, get_user_role, SessionLocal, is_manager, get_active_support_chats, get_support_chat_by_client_id, get_chat_history, assign_manager_to_chat, get_manager_roles, close_support_chat
from models import SupportChat, ChatMessage, TelegramUser # Додано TelegramUser
from typing import List
from db import SessionLocal 
from config import SUPER_ADMIN_ID 
from telegram.error import TelegramError

# --- СТАН ДІАЛОГУ ---
ASK_QUESTION = 1  
IN_CHAT = 2       

MANAGER_STATE_SELECTING_CLIENT = 10 
MANAGER_STATE_IN_CHAT = 11


# --- УТИЛІТИ ---

def get_update_info(update: Update, is_callback: bool):
    """Повертає об'єкт та ID чату в залежності від типу Update (команда чи кнопка)."""
    if is_callback:
        # Для кнопки використовуємо chat_id повідомлення, яке містить кнопку
        return update.callback_query, update.callback_query.message.chat_id
    # Для команди/повідомлення
    return update.message, update.message.from_user.id 


async def notify_manager_or_admin(context: ContextTypes.DEFAULT_TYPE, client_id: int):
    """Сповіщує призначеного менеджера або головного адміна про нове повідомлення/запит."""
    
    db = SessionLocal() # ВІДКРИВАЄМО НОВУ СЕСІЮ
    try:
        chat = get_support_chat_by_client_id(db, client_id)
        if not chat:
            return

        target_id = chat.manager_id
        
        if not target_id and chat.status == "awaiting_manager":
            target_id = SUPER_ADMIN_ID 
            
        if target_id:
            try:
                client_user = db.query(TelegramUser).filter(TelegramUser.telegram_id == client_id).first()
                
                # FIX: Використовуємо phone або ID, оскільки username може бути відсутній
                if client_user:
                    client_info = client_user.phone if client_user.phone else f"ID: {client_id}"
                else:
                    client_info = f"ID: {client_id} (Користувач не знайдений)"

                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"📨 *НОВИЙ ЗАПИТ* або повідомлення від клієнта `{client_id}`. \nСтатус: *{chat.status}*\nКористувач: {client_info}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Перейти до чату", callback_data=f"support_select:{client_id}")] +
                                                       [InlineKeyboardButton("🧑‍💻 Панель чатів", callback_data="support_refresh_list")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                # Помилка при відправці, відкатуємо (хоча тут немає commit, краще бути впевненим)
                print(f"Помилка при відправці сповіщення менеджеру/адміну {target_id}: {e}")
                
    finally:
        db.close() # ЗАКРИВАЄМО СЕСІЮ


def get_chat_list_keyboard(chats: List[SupportChat], manager_id: int, db: SessionLocal) -> InlineKeyboardMarkup:
    """Створює клавіатуру зі списком активних чатів для менеджера."""
    buttons = []
    
    for chat in chats:
        client_user = db.query(TelegramUser).filter(TelegramUser.telegram_id == chat.client_id).first()
        # FIX: Прибрали username
        client_info = client_user.phone if client_user and client_user.phone else str(chat.client_id)
        
        status_icon = "🔴" if chat.status == "awaiting_manager" else "🟢"
        
        is_assigned_to_current_manager = chat.manager_id == manager_id
        
        if is_assigned_to_current_manager and chat.status == "open":
            text = f"✅ ВИ (ведете): {client_info}"
            callback_data = f"support_view:{chat.client_id}"
        elif chat.status == "awaiting_manager":
            text = f"🚨 НОВИЙ ({client_info})"
            callback_data = f"support_select:{chat.client_id}"
        else:
            text = f"{status_icon} {client_info}"
            callback_data = f"support_select:{chat.client_id}"
        
        buttons.append([InlineKeyboardButton(text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton("🔄 Оновити список", callback_data="support_refresh_list")])
    
    return InlineKeyboardMarkup(buttons)

def format_chat_history(messages: List[ChatMessage]) -> str:
    """Форматує історію повідомлень для відображення менеджеру."""
    history = []
    for msg in messages:
        sender_label = "🧑‍💻 Менеджер:" if msg.sender == "manager" else "👤 Клієнт:"
        text = msg.text if msg.text else f"[{msg.type.capitalize()}]"
        
        # FIX: Перевіряємо, чи існує created_at перед викликом strftime
        if msg.created_at:
            time_str = msg.created_at.strftime('%H:%M')
        else:
            time_str = '??:??' # Використовуємо заглушку, якщо час відсутній
            
        # Використовуємо Markdown
        history.append(f"_{time_str}_ *{sender_label}* {text}")
    
    return "\n".join(history)


# --- ОБРОБНИКИ ДЛЯ КЛІЄНТА ---

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    db = SessionLocal()
    try:
        role = get_user_role(db, telegram_id)
        chat = get_support_chat_by_client_id(db, telegram_id)
    finally:
        db.close()
        
    if role not in get_manager_roles():
        if chat and chat.status != "closed":
            await update.message.reply_text("💬 Продовжуйте спілкування. Менеджер скоро відповість. Або відправте /end_chat для завершення розмови.")
            return IN_CHAT
        
        await update.message.reply_text(
            "💬 Напишіть своє питання, і наш менеджер незабаром з вами зв'яжеться. Або відправте /end_chat для завершення розмови."
        )
        return ASK_QUESTION
    else:
        await update.message.reply_text("❌ Ця функція лише для клієнтів. Ви можете використовувати /support_manager.")
        return ConversationHandler.END


# client_message - обробляє всі повідомлення клієнта
# client_message - обробляє всі повідомлення клієнта
async def client_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    
    db_check = SessionLocal()
    try:
        # 1. Перевіряємо, чи є користувач менеджером (ця перевірка тепер включає SUPER_ADMIN_ID)
        is_user_manager = is_manager(db_check, telegram_id)
    finally:
        db_check.close()
        
    # --- КРИТИЧНА ПЕРЕВІРКА ---
    # Якщо користувач є менеджером, ми ігноруємо повідомлення в цьому клієнтському обробнику.
    # Воно має бути оброблено ConversationHandler менеджера, або проігнороване.
    if is_user_manager:
        # Додаткове нагадування: якщо менеджер пише, коли не в режимі відповіді.
        if not context.user_data.get('current_client_chat_id'):
            await update.message.reply_text("❌ Ваше повідомлення ігнорується, оскільки ви є менеджером. Використовуйте /support_manager для роботи з чатами.")
        return ConversationHandler.END # Ігноруємо повідомлення менеджера
        
    # --- КЛІЄНТСЬКА ЛОГІКА ---

    message = update.message
    
    if message.text == "/end_chat":
        db_close = SessionLocal()
        try:
            close_support_chat(db_close, telegram_id)
        finally:
            db_close.close()
        
        await update.message.reply_text("👋 Чат підтримки завершено. Ви завжди можете почати новий, відправивши повідомлення або натиснувши 'Підтримка'.")
        return ConversationHandler.END 
    
    # Визначаємо тип повідомлення
    message_type = "text"
    text = message.text
    file_id = None
    
    if message.photo:
        message_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.caption
    elif message.video:
        message_type = "video"
        file_id = message.video.file_id
        text = message.caption
    elif message.document:
        message_type = "document"
        file_id = message.document.file_id
        text = message.caption
    elif message.voice:
        message_type = "voice"
        file_id = message.voice.file_id
    elif message.text:
        message_type = "text"
        text = message.text
    else:
        await update.message.reply_text("❗ На жаль, цей тип повідомлення поки не підтримується підтримкою.")
        return IN_CHAT 
        
    # save_message керує своєю сесією, тому не потрібно try/finally тут
    save_message(client_id=telegram_id, sender="client", type_=message_type, text=text, file_id=file_id, manager_id=None)
    
    # Викликаємо нову функцію, яка відкриє свій власний DB-з'єднання
    await notify_manager_or_admin(context, telegram_id)

    return IN_CHAT

# Обробник першого повідомлення 
async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await client_message(update, context)


# --- ОБРОБНИКИ ДЛЯ МЕНЕДЖЕРА ---

# Функція, яка може бути викликана як командою, так і callback
async def open_support_manager(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """Обробник команди /support_manager або натискання кнопки 'Назад до списку'. Показує список активних чатів."""
    
    handler_obj, telegram_id = get_update_info(update, is_callback)
    
    db = SessionLocal()
    try:
        if not is_manager(db, telegram_id):
            if not is_callback:
                await update.message.reply_text("❌ Вам не дозволено використовувати цю функцію.")
            return ConversationHandler.END
        
        chats = get_active_support_chats(db)
    finally:
        db.close()

    text = "🧑‍💻 *ПАНЕЛЬ ПІДТРИМКИ*\n\nОберіть чат для відповіді:"
    keyboard = get_chat_list_keyboard(chats, telegram_id, db)
    
    if is_callback:
        await handler_obj.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await handler_obj.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    return MANAGER_STATE_SELECTING_CLIENT


async def handle_notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник кнопок зі сповіщень менеджера, що ініціює ConversationHandler."""
    query = update.callback_query
    await query.answer()
    
    # Викликаємо support_callback_query. 
    # Вона виконує логіку (вибирає чат або оновлює список) і ПОВЕРТАЄ НОВИЙ СТАН CH.
    # Ми просто повертаємо цей стан як результат роботи цього глобального обробника.
    return await support_callback_query(update, context, is_global_entry=True)



async def support_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE, is_global_entry=False):
    """Обробник натискань кнопок у панелі менеджера."""
    query = update.callback_query
    
    # Якщо це не викликано з глобального обробника, відповідаємо на запит
    if not is_global_entry:
        await query.answer()
        
    data = query.data
    manager_id = query.from_user.id
    
    db = SessionLocal()
    try:
        if data == "support_refresh_list":
            # Якщо це кнопка "Назад до списку" або "Оновити список"
            return await open_support_manager(update, context, is_callback=True)

        elif data.startswith("support_select:") or data.startswith("support_view:"):
            # Менеджер обрав клієнта або переглядає поточний чат
            client_id = int(data.split(":")[1])
            
            chat = get_support_chat_by_client_id(db, client_id)
            if chat and (chat.status == "awaiting_manager" or chat.manager_id == manager_id):
                 assign_manager_to_chat(db, client_id, manager_id)
            
            context.user_data['current_client_chat_id'] = client_id
            
            history = get_chat_history(db, client_id)
            client_user_info = db.query(TelegramUser).filter(TelegramUser.telegram_id == client_id).first()
            
            # FIX: Видаляємо username і @
            client_display = client_user_info.phone if client_user_info and client_user_info.phone else 'ID: ' + str(client_id)
            
            chat_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Закрити чат", callback_data=f"support_close:{client_id}")],
                [InlineKeyboardButton("⬅️ Назад до списку", callback_data="support_refresh_list")]
            ])
            
            await query.edit_message_text(
                f"📝 *ЧАТ З КЛІЄНТОМ* `{client_id}` ({client_display}) \n\n_Ви можете відповідати на повідомлення в цьому чаті._\n\n---\n{format_chat_history(history)}---\n",
                reply_markup=chat_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            return MANAGER_STATE_IN_CHAT

        elif data.startswith("support_close:"):
            client_id = int(data.split(":")[1])
            
            if context.user_data.get('current_client_chat_id') == client_id:
                context.user_data['current_client_chat_id'] = None
            
            close_support_chat(db, client_id)
            
            await query.edit_message_text(
                f"✅ Чат з клієнтом `{client_id}` закрито.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад до списку", callback_data="support_refresh_list")]])
            )
            return MANAGER_STATE_SELECTING_CLIENT

    finally:
        db.close()
    
    return ConversationHandler.END


async def manager_reply_to_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник повідомлення менеджера у відкритому чаті."""
    manager_id = update.message.from_user.id
    client_id = context.user_data.get('current_client_chat_id')
    
    if not client_id:
        await update.message.reply_text("❌ Немає обраного активного чату для відповіді. Оберіть його в панелі /support_manager.")
        return MANAGER_STATE_IN_CHAT
        
    message = update.message
    
    message_type = "text"
    text = message.text
    file_id = None
    media_group_id = None
    
    # Логіка визначення типу повідомлення (залишається як є)
    if message.photo:
        message_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.caption
    elif message.video:
        message_type = "video"
        file_id = message.video.file_id
        text = message.caption
    elif message.document:
        message_type = "document"
        file_id = message.document.file_id
        text = message.caption
    elif message.voice:
        message_type = "voice"
        file_id = message.voice.file_id
    elif message.text:
        message_type = "text"
        text = message.text
    else:
        await update.message.reply_text("❗ На жаль, цей тип повідомлення поки не підтримується для відповіді.")
        return MANAGER_STATE_IN_CHAT
        
    # --- БЛОК ВИКОНАННЯ З ОБРОБКОЮ ПОМИЛОК ---
    
    try:
        # 1. Зберігаємо повідомлення в базу
        # save_message керує своєю сесією
        save_message(client_id=client_id, sender="manager", manager_id=manager_id, type_=message_type, text=text, file_id=file_id, media_group_id=media_group_id)
        
        # 2. Пересилаємо повідомлення клієнту
        await context.bot.copy_message(
            chat_id=client_id,
            from_chat_id=manager_id,
            message_id=message.message_id
        )
        
        # 3. Надсилаємо підтвердження менеджеру
        await update.message.reply_text(f"✅ Повідомлення надіслано клієнту `{client_id}`.")
        
    except TelegramError as e:
        # Ця помилка виникає, якщо клієнт заблокував бота або ID чату неправильний
        error_msg = f"❌ ПОМИЛКА: Не вдалося доставити клієнту `{client_id}`. Можлива причина: клієнт заблокував бота. Деталі: {e}"
        await update.message.reply_text(error_msg)
        print(error_msg) # Виводимо в лог
        
    except Exception as e:
        # Загальна помилка виконання (наприклад, DB error)
        error_msg = f"❌ ПОМИЛКА: Невідома помилка під час обробки повідомлення: {e}"
        await update.message.reply_text(error_msg)
        print(error_msg) # Виводимо в лог
        
    return MANAGER_STATE_IN_CHAT

# --- ConversationHandler ---
def get_support_handler():
    
    client_handler = ConversationHandler(
        entry_points=[CommandHandler("support", start_support)],
        states={
            ASK_QUESTION: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_question)],
            IN_CHAT: [MessageHandler(filters.ALL & ~filters.COMMAND, client_message)]
        },
        fallbacks=[CommandHandler("end_chat", client_message)],
        name="client_support_conversation",
        persistent=True
    )
    
    manager_handler = ConversationHandler(
        entry_points=[CommandHandler("support_manager", open_support_manager)],
        states={
            MANAGER_STATE_SELECTING_CLIENT: [
                # Обробітники всередині CH
                CallbackQueryHandler(support_callback_query, pattern="^support_select:|^support_refresh_list|^support_view:")
            ],
            MANAGER_STATE_IN_CHAT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, manager_reply_to_client),
                CallbackQueryHandler(support_callback_query, pattern="^support_close:|^support_refresh_list|^support_view:")
            ]
        },
        fallbacks=[],
        name="manager_support_conversation",
        persistent=True
    )

    # Глобальний обробник для кнопок зі сповіщень
    notification_callback_handler = CallbackQueryHandler(
        handle_notification_callback, 
        pattern="^support_select:|^support_refresh_list" # Обробляє кнопки, які можуть бути натиснуті поза CH
    )
    
    # ПОВЕРТАЄМО ТРИ ОБРОБНИКИ
    return client_handler, manager_handler, notification_callback_handler