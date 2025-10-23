from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters, CallbackQueryHandler
from storage import (
    save_message, get_user_role, is_manager, get_active_support_chats,
    get_support_chat_by_client_id, get_chat_history, assign_manager_to_chat,
    get_manager_roles, close_support_chat
)
from models import SupportChat, ChatMessage, TelegramUser
from typing import List
from db import SessionLocal
from config import SUPER_ADMIN_ID
from telegram.error import TelegramError

# --- СТАНИ ДІАЛОГУ ---
ASK_QUESTION = 1
IN_CHAT = 2

MANAGER_STATE_SELECTING_CLIENT = 10
MANAGER_STATE_IN_CHAT = 11


# --- УТИЛІТИ ---

async def notify_managers(context: ContextTypes.DEFAULT_TYPE, client_id: int, is_new_chat: bool = False):
    """Сповіщає всіх менеджерів про нове повідомлення або новий чат."""
    
    db = SessionLocal()
    try:
        chat = get_support_chat_by_client_id(db, client_id)
        if not chat:
            return

        client_user = db.query(TelegramUser).filter(TelegramUser.telegram_id == client_id).first()
        client_info = client_user.phone if client_user and client_user.phone else f"ID: {client_id}"

        # Визначаємо кому надсилати
        targets = []
        
        if chat.status == "awaiting_manager":
            # Новий чат - повідомляємо всіх менеджерів + супер адміна
            managers = db.query(TelegramUser).filter(
                TelegramUser.role.in_(get_manager_roles())
            ).all()
            targets = [m.telegram_id for m in managers]
            if SUPER_ADMIN_ID not in targets:
                targets.append(SUPER_ADMIN_ID)
            
            message_text = f"🆕 *НОВИЙ ЗАПИТ ПІДТРИМКИ*\n\nКлієнт: {client_info}\nID: `{client_id}`\n\nОберіть чат, щоб прийняти його."
        
        elif chat.status == "open" and chat.manager_id:
            # Чат вже призначений - повідомляємо тільки відповідального менеджера
            targets = [chat.manager_id]
            message_text = f"💬 *Нове повідомлення від клієнта*\n\nКлієнт: {client_info}\nID: `{client_id}`"
        
        else:
            return

        # Надсилаємо сповіщення
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Відкрити чат", callback_data=f"support_select:{client_id}")],
            [InlineKeyboardButton("🧑‍💻 Панель чатів", callback_data="support_refresh_list")]
        ])

        for target_id in targets:
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Помилка при відправці сповіщення менеджеру {target_id}: {e}")

    finally:
        db.close()


def get_chat_list_keyboard(chats: List[SupportChat], manager_id: int, db: SessionLocal) -> InlineKeyboardMarkup:
    """Створює клавіатуру зі списком активних чатів для менеджера."""
    buttons = []
    
    for chat in chats:
        client_user = db.query(TelegramUser).filter(TelegramUser.telegram_id == chat.client_id).first()
        client_info = client_user.phone if client_user and client_user.phone else str(chat.client_id)
        
        # Визначаємо статус чату
        if chat.status == "awaiting_manager":
            text = f"🔴 НОВИЙ: {client_info}"
            callback_data = f"support_select:{chat.client_id}"
        elif chat.manager_id == manager_id:
            text = f"🟢 ВИ: {client_info}"
            callback_data = f"support_view:{chat.client_id}"
        else:
            manager = db.query(TelegramUser).filter(TelegramUser.telegram_id == chat.manager_id).first()
            manager_name = manager.phone if manager and manager.phone else "інший"
            text = f"🟡 {manager_name}: {client_info}"
            callback_data = f"support_view:{chat.client_id}"
        
        buttons.append([InlineKeyboardButton(text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton("🔄 Оновити список", callback_data="support_refresh_list")])
    
    return InlineKeyboardMarkup(buttons)


def format_chat_history(messages: List[ChatMessage]) -> str:
    """Форматує історію повідомлень для відображення."""
    if not messages:
        return "_Історія порожня_\n"
    
    history = []
    for msg in messages:
        sender_label = "🧑‍💻 Менеджер" if msg.sender == "manager" else "👤 Клієнт"
        text = msg.text if msg.text else f"[{msg.type}]"
        
        # Виправлено: перевірка на існування created_at
        if hasattr(msg, 'created_at') and msg.created_at:
            try:
                time_str = msg.created_at.strftime('%d.%m %H:%M')
            except:
                time_str = 'Щойно'
        else:
            time_str = 'Щойно'
        
        history.append(f"`{time_str}` *{sender_label}:*\n{text}\n")
    
    return "\n".join(history)


# --- ОБРОБНИКИ ДЛЯ КЛІЄНТА ---

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок діалогу підтримки для клієнта."""
    telegram_id = update.message.from_user.id
    
    db = SessionLocal()
    try:
        role = get_user_role(db, telegram_id)
        
        # Менеджери не можуть використовувати клієнтський чат
        if role in get_manager_roles() or telegram_id == SUPER_ADMIN_ID:
            # === ЗМІНА: Перенаправляємо менеджера на Панель підтримки ===
            print(f"🔄 Менеджер {telegram_id} спробував /support, перенаправляємо на панель.")
            return await open_support_manager(update, context) 
            # =========================================================

        # Перевіряємо чи є активний чат
        chat = get_support_chat_by_client_id(db, telegram_id)
        
        if chat and chat.status != "closed":
            await update.message.reply_text(
                "💬 Ви вже в чаті підтримки. Надішліть своє повідомлення, і менеджер відповість.\n\n"
                "Щоб завершити чат, використовуйте /end_chat"
            )
            return IN_CHAT
        
        # Новий чат
        await update.message.reply_text(
            "💬 Вітаємо в чаті підтримки!\n\n"
            "Напишіть своє питання, і наш менеджер зв'яжеться з вами найближчим часом.\n\n"
            "Ви можете надсилати текст, фото, відео та документи.\n\n"
            "Щоб завершити чат, використовуйте /end_chat"
        )
        
    finally:
        db.close()
    
    return ASK_QUESTION


async def client_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє повідомлення від клієнта."""
    telegram_id = update.message.from_user.id
    message = update.message

    # if message.text == "💬 Підтримка":
    #     # Якщо це текст кнопки, ми просто виходимо зі стану, 
    #     # дозволяючи наступному повідомленню бути першим питанням.
    #     return IN_CHAT
    
    # Перевірка чи користувач є менеджером
    db_check = SessionLocal()
    try:
        if is_manager(db_check, telegram_id):
            return ConversationHandler.END
    finally:
        db_check.close()
    
    # Обробка команди завершення чату
    if message.text == "/end_chat":
        db = SessionLocal()
        try:
            close_support_chat(db, telegram_id)
            await update.message.reply_text(
                "👋 Чат підтримки завершено.\n\n"
                "Дякуємо, що звернулися до нас! Ви можете почати новий чат у будь-який час."
            )
        finally:
            db.close()
        return ConversationHandler.END
    
    # Визначаємо тип повідомлення
    message_type = "text"
    text = None
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
        text = "Голосове повідомлення"
    elif message.text:
        message_type = "text"
        text = message.text
    else:
        await update.message.reply_text(
            "❗ На жаль, цей тип повідомлення не підтримується."
        )
        return IN_CHAT
    
    # Зберігаємо повідомлення
    db = SessionLocal()
    try:
        # Перевіряємо статус чату
        chat = get_support_chat_by_client_id(db, telegram_id)
        is_new_chat = not chat or chat.status == "closed"
        
        # Зберігаємо повідомлення (функція save_message створює чат якщо потрібно)
        save_message(
            client_id=telegram_id,
            sender="client",
            type_=message_type,
            text=text,
            file_id=file_id
        )
        
        # Підтверджуємо отримання
        await update.message.reply_text(
            "✅ Повідомлення отримано. Менеджер незабаром з вами зв'яжеться."
        )
        
    finally:
        db.close()
    
    # Сповіщаємо менеджерів
    await notify_managers(context, telegram_id, is_new_chat)
    
    return IN_CHAT


async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник першого повідомлення клієнта."""
    return await client_message(update, context)


# --- ОБРОБНИКИ ДЛЯ МЕНЕДЖЕРА ---

async def open_support_manager(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """Відкриває панель чатів для менеджера."""
    
    if is_callback:
        query = update.callback_query
        telegram_id = query.from_user.id
    else:
        telegram_id = update.message.from_user.id
    
    db = SessionLocal()
    try:
        # Перевірка доступу
        if not is_manager(db, telegram_id):
            text = "❌ Вам не дозволено використовувати цю функцію."
            if is_callback:
                await query.answer(text, show_alert=True)
            else:
                await update.message.reply_text(text)
            return ConversationHandler.END
        
        # Отримуємо активні чати
        chats = get_active_support_chats(db)
        
        # Формуємо повідомлення
        if not chats:
            text = "🧑‍💻 *ПАНЕЛЬ ПІДТРИМКИ*\n\n📭 Немає активних чатів."
        else:
            text = f"🧑‍💻 *ПАНЕЛЬ ПІДТРИМКИ*\n\n📊 Активних чатів: {len(chats)}\n\nОберіть чат:"
        
        keyboard = get_chat_list_keyboard(chats, telegram_id, db)
        
        if is_callback:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        
    finally:
        db.close()
    
    return MANAGER_STATE_SELECTING_CLIENT


async def support_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE, is_global_entry=False):
    """Обробляє натискання кнопок у панелі менеджера."""
    query = update.callback_query
    
    if not is_global_entry:
        await query.answer()
    
    data = query.data
    manager_id = query.from_user.id
    
    db = SessionLocal()
    try:
        # Оновлення списку чатів
        if data == "support_refresh_list":
            return await open_support_manager(update, context, is_callback=True)
        
        # Вибір або перегляд чату
        elif data.startswith("support_select:") or data.startswith("support_view:"):
            client_id = int(data.split(":")[1])
            
            # Отримуємо чат
            chat = get_support_chat_by_client_id(db, client_id)
            if not chat:
                await query.answer("❌ Чат не знайдено", show_alert=True)
                return MANAGER_STATE_SELECTING_CLIENT
            
            # Якщо чат новий або призначений цьому менеджеру - призначаємо/відкриваємо
            if chat.status == "awaiting_manager" or chat.manager_id == manager_id:
                assign_manager_to_chat(db, client_id, manager_id)
                context.user_data['current_client_chat_id'] = client_id
            elif chat.manager_id and chat.manager_id != manager_id:
                # Чат призначений іншому менеджеру
                other_manager = db.query(TelegramUser).filter(
                    TelegramUser.telegram_id == chat.manager_id
                ).first()
                other_name = other_manager.phone if other_manager and other_manager.phone else "іншому менеджеру"
                await query.answer(
                    f"⚠️ Цей чат веде {other_name}",
                    show_alert=True
                )
                return MANAGER_STATE_SELECTING_CLIENT
            
            # Завантажуємо історію
            history = get_chat_history(db, client_id, limit=20)
            client_user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == client_id
            ).first()
            
            client_display = client_user.phone if client_user and client_user.phone else f'ID: {client_id}'
            
            # Клавіатура чату
            chat_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Закрити чат", callback_data=f"support_close:{client_id}")],
                [InlineKeyboardButton("⬅️ Назад до списку", callback_data="support_refresh_list")]
            ])
            
            # Показуємо чат
            history_text = format_chat_history(history)
            
            await query.edit_message_text(
                f"💬 *ЧАТ З КЛІЄНТОМ*\n\n"
                f"👤 Клієнт: {client_display}\n"
                f"🆔 ID: `{client_id}`\n\n"
                f"{'─' * 30}\n\n"
                f"{history_text}\n"
                f"{'─' * 30}\n\n"
                f"_Ви можете відповідати прямо в цей чат_",
                reply_markup=chat_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            return MANAGER_STATE_IN_CHAT
        
        # Закриття чату
        elif data.startswith("support_close:"):
            client_id = int(data.split(":")[1])
            
            # Очищаємо поточний чат
            if context.user_data.get('current_client_chat_id') == client_id:
                context.user_data['current_client_chat_id'] = None
            
            # Закриваємо чат
            close_support_chat(db, client_id)
            
            # Сповіщаємо клієнта
            try:
                await context.bot.send_message(
                    chat_id=client_id,
                    text="✅ Ваш чат підтримки завершено менеджером.\n\n"
                         "Дякуємо за звернення! Ви можете почати новий чат у будь-який час."
                )
            except:
                pass
            
            await query.edit_message_text(
                f"✅ Чат з клієнтом `{client_id}` закрито.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад до списку", callback_data="support_refresh_list")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return MANAGER_STATE_SELECTING_CLIENT
    
    finally:
        db.close()
    
    return ConversationHandler.END


async def manager_reply_to_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє відповідь менеджера клієнту."""
    manager_id = update.message.from_user.id
    client_id = context.user_data.get('current_client_chat_id')
    message = update.message
    
    if not client_id:
        await update.message.reply_text(
            "❌ Немає активного чату. Оберіть чат у панелі /support_manager"
        )
        return MANAGER_STATE_IN_CHAT
    
    # Визначаємо тип повідомлення
    message_type = "text"
    text = None
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
        text = "Голосове повідомлення"
    elif message.text:
        message_type = "text"
        text = message.text
    else:
        await update.message.reply_text(
            "❗ Цей тип повідомлення не підтримується."
        )
        return MANAGER_STATE_IN_CHAT
    
    try:
        # Зберігаємо повідомлення
        save_message(
            client_id=client_id,
            sender="manager",
            manager_id=manager_id,
            type_=message_type,
            text=text,
            file_id=file_id
        )
        
        # Пересилаємо клієнту
        await context.bot.copy_message(
            chat_id=client_id,
            from_chat_id=manager_id,
            message_id=message.message_id
        )
        
        await update.message.reply_text(
            f"✅ Повідомлення доставлено клієнту `{client_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except TelegramError as e:
        error_msg = f"❌ Не вдалося доставити повідомлення клієнту `{client_id}`\n\nМожлива причина: клієнт заблокував бота"
        await update.message.reply_text(error_msg, parse_mode=ParseMode.MARKDOWN)
        print(f"Telegram error: {e}")
        
    except Exception as e:
        error_msg = f"❌ Помилка при відправці: {e}"
        await update.message.reply_text(error_msg)
        print(f"Error: {e}")
    
    return MANAGER_STATE_IN_CHAT


async def handle_notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальний обробник для кнопок зі сповіщень."""
    query = update.callback_query
    await query.answer()
    
    return await support_callback_query(update, context, is_global_entry=True)


# --- ConversationHandler ---
def get_support_handler():
    """Повертає всі необхідні обробники для системи підтримки."""
    
    # Обробник для клієнтів
    client_handler = ConversationHandler(
        entry_points=[CommandHandler("support", start_support)],
        states={
            ASK_QUESTION: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_question)
            ],
            IN_CHAT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, client_message)
            ]
        },
        fallbacks=[CommandHandler("end_chat", client_message)],
        name="client_support_conversation",
        persistent=True
    )
    
    # Обробник для менеджерів
    manager_handler = ConversationHandler(
        entry_points=[CommandHandler("support_manager", open_support_manager)],
        states={
            MANAGER_STATE_SELECTING_CLIENT: [
                CallbackQueryHandler(
                    support_callback_query,
                    pattern="^support_select:|^support_refresh_list|^support_view:"
                )
            ],
            MANAGER_STATE_IN_CHAT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, manager_reply_to_client),
                CallbackQueryHandler(
                    support_callback_query,
                    pattern="^support_close:|^support_refresh_list|^support_view:"
                )
            ]
        },
        fallbacks=[],
        name="manager_support_conversation",
        persistent=True
    )
    
    # Глобальний обробник для кнопок зі сповіщень
    notification_callback_handler = CallbackQueryHandler(
        handle_notification_callback,
        pattern="^support_select:|^support_refresh_list"
    )
    
    return client_handler, manager_handler, notification_callback_handler