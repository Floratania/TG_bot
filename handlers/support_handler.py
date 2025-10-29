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


# --- НОВА ФУНКЦІЯ: Хелпер для відправки контенту ---
async def send_message_content(context: ContextTypes.DEFAULT_TYPE, chat_id: int, msg: ChatMessage, reply_markup: InlineKeyboardMarkup = None, parse_mode=None):
    """Надсилає фактичний контент повідомлення (текст, фото, відео, документ, голос)"""
    if not msg or not chat_id:
        return

    # message_text is used for caption/text
    message_text = msg.text or ""
    
    try:
        if msg.type == "text":
            await context.bot.send_message(
                chat_id=chat_id,
                # Telegram не надсилає порожнє повідомлення, тому додаємо мінімальний текст
                text=message_text if message_text else "_Пусте текстове повідомлення_", 
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif msg.type == "photo" and msg.file_id:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=msg.file_id,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif msg.type == "video" and msg.file_id:
            await context.bot.send_video(
                chat_id=chat_id,
                video=msg.file_id,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif msg.type == "document" and msg.file_id:
            await context.bot.send_document(
                chat_id=chat_id,
                document=msg.file_id,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif msg.type == "voice" and msg.file_id:
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=msg.file_id,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            # Fallback for unsupported media types or messages without file_id
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Непідтримуваний тип: [{msg.type.upper()}] {message_text}",
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except TelegramError as e:
        print(f"Помилка при відправці контенту повідомлення {msg.id} менеджеру {chat_id}: {e}")
# -------------------------------------------------------------------

# --- УТИЛІТИ ---

# Функція для отримання всіх медіафайлів
def get_all_media_messages(db, client_id: int) -> List[ChatMessage]:
    media_types = ["photo", "video", "document", "voice"]
    return db.query(ChatMessage).filter(
        ChatMessage.client_id == client_id,
        ChatMessage.type.in_(media_types),
        ChatMessage.file_id != None
    ).order_by(ChatMessage.created_at.asc()).all()

# НОВИЙ ОБРОБНИК МЕДІА
async def send_chat_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Завантажуємо медіа...", show_alert=False)
    
    manager_id = query.from_user.id
    data = query.data
    client_id = int(data.split(":")[1])
    
    db = SessionLocal()
    try:
        media_messages = get_all_media_messages(db, client_id)
        
        if not media_messages:
            await context.bot.send_message(
                chat_id=manager_id,
                text=f"📭 У чаті з клієнтом `{client_id}` не знайдено медіафайлів.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        await context.bot.send_message(
            chat_id=manager_id,
            text=f"⬇️ *Починаємо завантаження {len(media_messages)} медіафайлів* з чату `{client_id}`...",
            parse_mode=ParseMode.MARKDOWN
        )

        for msg in media_messages:
            # Додаємо інформацію про відправника та час до підпису
            original_text = msg.text
            sender_label = "👤 Клієнт" if msg.sender == "client" else "🧑‍💻 Менеджер"
            
            try:
                time_str = msg.created_at.strftime('%d.%m %H:%M')
            except:
                time_str = 'Щойно'
                
            # Форматуємо новий підпис
            msg.text = f"*{sender_label}* ({time_str}):\n{original_text or ''}"
            
            try:
                # Надсилаємо контент, parse_mode встановлюємо MARKDOWN для підпису
                await send_message_content(
                    context, 
                    manager_id, 
                    msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Помилка при відправці медіафайлу {msg.file_id} з чату {client_id}: {e}")
                
            # Відновлюємо оригінальний текст (хоча це не впливає на DB)
            msg.text = original_text
                
        await context.bot.send_message(
            chat_id=manager_id,
            text=f"✅ *Завантаження медіафайлів завершено* для чату `{client_id}`.",
            parse_mode=ParseMode.MARKDOWN
        )
            
    finally:
        db.close()
        
# Змінено сигнатуру: додано new_msg
async def notify_managers(context: ContextTypes.DEFAULT_TYPE, client_id: int, is_new_chat: bool = False, new_msg: ChatMessage = None):
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
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Відкрити чат", callback_data=f"support_select:{client_id}")],
            [InlineKeyboardButton("🧑‍💻 Панель чатів", callback_data="support_refresh_list")]
        ])

        if chat.status == "awaiting_manager":
            # Новий чат - повідомляємо всіх менеджерів + супер адміна
            managers = db.query(TelegramUser).filter(
                TelegramUser.role.in_(get_manager_roles())
            ).all()
            targets = [m.telegram_id for m in managers]
            if SUPER_ADMIN_ID not in targets:
                targets.append(SUPER_ADMIN_ID)
            
            message_text = f"🆕 *НОВИЙ ЗАПИТ ПІДТРИМКИ*\n\nКлієнт: {client_info}\nID: `{client_id}`\n\nОберіть чат, щоб прийняти його."

            # Надсилаємо сповіщення (заголовок + контент)
            for target_id in targets:
                try:
                    # 1. Надсилаємо заголовок (сповіщення)
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=message_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # 2. Надсилаємо контент (з кнопками)
                    await send_message_content(
                        context, 
                        target_id, 
                        new_msg, # Передаємо об'єкт повідомлення
                        reply_markup=keyboard, 
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    print(f"Помилка при відправці сповіщення менеджеру {target_id}: {e}")

        elif chat.status == "open" and chat.manager_id:
            # Чат вже призначений - повідомляємо тільки відповідального менеджера
            targets = [chat.manager_id]
            
            # Надсилаємо сповіщення (заголовок + контент)
            for target_id in targets:
                try:
                    # 1. Надсилаємо заголовок (сповіщення)
                    header_text = f"💬 *Нове повідомлення від клієнта*\n\nКлієнт: {client_info}\nID: `{client_id}`"
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=header_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # 2. Надсилаємо контент (з кнопками)
                    await send_message_content(
                        context, 
                        target_id, 
                        new_msg, # Передаємо об'єкт повідомлення
                        reply_markup=keyboard, 
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    print(f"Помилка при відправці повідомлення/сповіщення менеджеру {target_id}: {e}")
        
        else:
            return

    finally:
        db.close()

# --- НОВА ФУНКЦІЯ: Примусове оновлення панелей всіх менеджерів ---
async def refresh_manager_panels(context: ContextTypes.DEFAULT_TYPE):
    """Надсилає оновлення всім менеджерам, щоб оновити їхні панелі чатів."""
    db = SessionLocal() #
    try:
        # Отримуємо всіх менеджерів (логіка з notify_managers)
        managers = db.query(TelegramUser).filter(
            TelegramUser.role.in_(get_manager_roles()) #
        ).all()
        targets = [m.telegram_id for m in managers]
        if SUPER_ADMIN_ID not in targets:
            targets.append(SUPER_ADMIN_ID) #
            
        # Формуємо клавіатуру для переходу до панелі
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧑‍💻 Панель чатів", callback_data="support_refresh_list")] #
        ])
        
        message_text = "🔄 *Панель підтримки оновлено*.\n"
        
        for target_id in targets:
            try:
                # Надсилаємо сповіщення
                await context.bot.send_message(
                    chat_id=target_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Помилка при відправці оновлення панелі менеджеру {target_id}: {e}")

    finally:
        db.close()
# ---------------------------------------------------------------------------------


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
    """
    Форматує історію повідомлень для відображення. 
    УВАГА: Оскільки Telegram не підтримує вбудовування медіа у форматований текст, 
    фото та інші файли відображаються як текстові маркери.
    """
    if not messages:
        return "_Історія порожня_\n"
    
    history = []
    for msg in messages:
        sender_label = "🧑‍💻 Менеджер" if msg.sender == "manager" else "👤 Клієнт"
        
        # --- МОДИФІКОВАНА ЛОГІКА ДЛЯ МЕДІА ---
        if msg.type == "text":
            text = msg.text
        elif msg.type in ["photo", "video", "document", "voice"]:
            # Додаємо підпис до позначки типу медіа
            caption_text = f" ({msg.text})" if msg.text else ""
            text = f"[{msg.type.upper()}]" + caption_text
        else:
            text = f"[{msg.type.upper()}] (Невідомий тип)"
            
        if not text:
            text = "_(порожнє повідомлення)_"
        # -----------------------------------
        
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


# --- НОВА УТИЛІТА: Закриття чату клієнтом ---
async def close_chat_by_client(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    """Закриває чат і надсилає сповіщення клієнту та менеджеру."""
    manager_to_notify = None
    
    db = SessionLocal()
    try:
        # 1. Знаходимо чат і менеджера, якого треба повідомити
        chat = get_support_chat_by_client_id(db, telegram_id)
        if chat and chat.status == "open" and chat.manager_id:
            manager_to_notify = chat.manager_id
            
        # 2. Закриваємо чат у БД
        close_support_chat(db, telegram_id)

        # 3. Надсилаємо підтвердження клієнту
        await update.message.reply_text(
            "👋 Чат підтримки завершено.\n\n"
            "Дякуємо, що звернулися до нас! Ви можете почати новий чат у будь-який час."
        )
    finally:
        db.close()
    
    # 4. Надсилаємо сповіщення відповідальному менеджеру (поза транзакцією)
    if manager_to_notify:
        user = update.message.from_user
        # Використовуємо більш повну інформацію про клієнта
        client_info = user.full_name if user.full_name else f"ID: {telegram_id}"
        if user.username:
            client_info += f" (@{user.username})"

        try:
            await context.bot.send_message(
                chat_id=manager_to_notify,
                text=f"🚪 *Чат закрито клієнтом*.\n\n"
                     f"Клієнт: {client_info}\nID: `{telegram_id}`\n\n"
                     f"Чат був закритий користувачем за допомогою команди /end_chat.\n"
                     f"🔄 _Вашу панель підтримки було оновлено автоматично._", # <-- Змінено
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Помилка при відправці сповіщення про закриття чату менеджеру {manager_to_notify}: {e}")
            
    # 5. Оновлюємо панелі ВСІХ менеджерів (виконання вимоги користувача)
    await refresh_manager_panels(context) # <-- Додано
            
    return ConversationHandler.END


# --- ОБРОБНИКИ ДЛЯ КЛІЄНТА ---

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок діалогу підтримки для клієнта."""
    if update.message:
        telegram_id = update.message.from_user.id
    elif update.callback_query:
        telegram_id = update.callback_query.from_user.id
    else:
        return ConversationHandler.END # Невідомий вхід

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
            # Якщо чат АКТИВНИЙ, повертаємо стан IN_CHAT та повідомлення
            await update.message.reply_text(
                "💬 Ви вже в чаті підтримки. Надішліть своє повідомлення, і менеджер відповість.\n\n"
                "Щоб завершити чат, використовуйте /end_chat"
            )
            return IN_CHAT
        
        # Новий чат (або попередній був закритий)
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
    
    # === ВИПРАВЛЕННЯ: Ігноруємо текст кнопки "Підтримка" після запуску розмови ===
    # Тепер ця кнопка - entry_point, але якщо вона потрапляє сюди, ми її ігноруємо
    if message.text == "💬 Підтримка":
        if update.message:
            telegram_id = update.message.from_user.id
        elif update.callback_query:
            telegram_id = update.callback_query.from_user.id
        else:
            return ConversationHandler.END # Невідомий вхід

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
                # Якщо чат АКТИВНИЙ, повертаємо стан IN_CHAT та повідомлення
                await update.message.reply_text(
                    "💬 Ви вже в чаті підтримки. Надішліть своє повідомлення, і менеджер відповість.\n\n"
                    "Щоб завершити чат, використовуйте /end_chat"
                )
                return IN_CHAT
            
            # Новий чат (або попередній був закритий)
            await update.message.reply_text(
                "💬 Вітаємо в чаті підтримки!\n\n"
                "Напишіть своє питання, і наш менеджер зв'яжеться з вами найближчим часом.\n\n"
                "Ви можете надсилати текст, фото, відео та документи.\n\n"
                "Щоб завершити чат, використовуйте /end_chat"
            )
        finally:
            db.close()
    # =========================================================================
    
    # Перевірка чи користувач є менеджером
    db_check = SessionLocal()
    try:
        if is_manager(db_check, telegram_id):
            return ConversationHandler.END
    finally:
        db_check.close()
    
    # Обробка команди завершення чату
    if message.text == "/end_chat":
        # === ВИПРАВЛЕНО: Використовуємо нову функцію, яка сповіщує менеджера ===
        return await close_chat_by_client(update, context, telegram_id)
        # =======================================================================
    
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
        new_msg = save_message( # <--- Змінено: Зберігаємо об'єкт нового повідомлення
            client_id=telegram_id,
            sender="client",
            type_=message_type,
            text=text,
            file_id=file_id
        )
        
        # Підтверджуємо отримання
        if not (message.photo or message.video or message.document or message.voice): # Не дублюємо відповідь під медіа
             await update.message.reply_text(
                "✅ Повідомлення отримано. Менеджер незабаром з вами зв'яжеться.\n"
                "Щоб завершити чат, використовуйте /end_chat"
             )
        
    finally:
        db.close()
    
    # Сповіщаємо менеджерів
    # Змінено: Передаємо new_msg
    await notify_managers(context, telegram_id, is_new_chat, new_msg) 
    
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
            # === ВИПРАВЛЕННЯ: Додаємо перевірку перед edit_message_text ===
            can_edit = query.message.text is not None or query.message.caption is not None
            
            if can_edit:
                try: # <--- ВИПРАВЛЕННЯ: Додано обробку помилки "Message is not modified"
                    await query.edit_message_text(
                        text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except TelegramError as e:
                    if "Message is not modified" in str(e):
                        pass # Ігноруємо помилку, оскільки це просто оновлення без змін
                    else:
                        raise # Перенаправляємо інші помилки Telegram
                
            else:
                # Fallback: Send a new message if the original message was media without caption
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception as e:
                    print(f"Error removing keyboard from message in open_support_manager: {e}")
            # =============================================================
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
            
        # Отримання медіафайлів
        elif data.startswith("support_get_media:"):
            return await send_chat_media(update, context)
        
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
            history = get_chat_history(db, client_id, limit=100)
            
            # Отримуємо дані клієнта (ПЕРЕНЕСЕНО ВГОРУ)
            client_user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == client_id
            ).first()
            
            client_display = client_user.phone if client_user and client_user.phone else f'ID: {client_id}'

            # === ВИПРАВЛЕННЯ: Реверсуємо історію, щоб старіші повідомлення були зверху ===
            history.reverse()
            # ===========================================================================
            
            # Клавіатура чату (ДОДАНО КНОПКУ МЕДІА)
            chat_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Закрити чат", callback_data=f"support_close:{client_id}")],
                [InlineKeyboardButton("⬅️ Назад до списку", callback_data="support_refresh_list")],
                [InlineKeyboardButton("🖼️ Отримати медіа", callback_data=f"support_get_media:{client_id}")]
            ])
            
            # Показуємо чат
            history_text = format_chat_history(history)

            # 1. Determine the message text content for the new state
            new_message_text = (
                f"💬 *ЧАТ З КЛІЄНТОМ*\n\n"
                f"👤 Клієнт: {client_display}\n"
                f"🆔 ID: `{client_id}`\n\n"
                f"{'─' * 30}\n\n"
                f"{history_text}\n"
                f"{'─' * 30}\n\n"
                f"_Ви можете відповідати прямо в цей чат_"
            )
            
            # 2. === ВИПРАВЛЕННЯ: Додаємо перевірку перед edit_message_text ===
            can_edit = query.message.text is not None or query.message.caption is not None

            if can_edit:
                # Показуємо чат шляхом редагування (якщо це можливо)
                await query.edit_message_text(
                    new_message_text,
                    reply_markup=chat_keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Це було чисте медіа без підпису. Надсилаємо нове повідомлення
                await context.bot.send_message(
                    chat_id=manager_id,
                    text=new_message_text,
                    reply_markup=chat_keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                # Опціонально, видаляємо кнопки з оригінального повідомлення
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception as e:
                    print(f"Помилка при видаленні клавіатури з медіа-повідомлення: {e}")
            # =================================================================
            
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
            
            # Додано: Оновлюємо панелі ВСІХ менеджерів
            await refresh_manager_panels(context) # <-- Додано
            
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
    
    # === НОВА ПЕРЕВІРКА: Чи активний чат? (Виконує вимогу "не дозволяй відпрвляти повідомлення") ===
    db_check = SessionLocal()
    try:
        chat = get_support_chat_by_client_id(db_check, client_id)
        if chat and chat.status == "closed":
            await update.message.reply_text(
                "❌ **Відправка неможлива**. Цей чат був закритий клієнтом або менеджером. "
                "Будь ласка, оберіть інший чат у панелі /support_manager.",
                parse_mode=ParseMode.MARKDOWN
            )
            # Якщо чат закритий, не дозволяємо подальші дії та залишаємось у стані
            return MANAGER_STATE_IN_CHAT
    finally:
        db_check.close()
    # ========================================

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
        entry_points=[
            CommandHandler("support", start_support),
            MessageHandler(filters.Regex("^💬 Підтримка$"), start_support) 
        ],
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
                    pattern="^support_close:|^support_refresh_list|^support_view:|^support_get_media:"
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