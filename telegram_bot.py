import time
import re
import json
import os
from datetime import datetime
from googleapiclient.discovery import build
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ TELEGRAM БОТА =================
TELEGRAM_BOT_TOKEN = "8994730100:AAE6P65OqjVOTAftOIPZuBF70WAwzxz116A"

# ================= ФАЙЛ ДЛЯ ХРАНЕНИЯ НАСТРОЕК =================
SETTINGS_FILE = "bot_settings.json"

# ================= ЗАГРУЗКА/СОХРАНЕНИЕ НАСТРОЕК =================
def load_settings():
    """Загружает настройки из файла, если файла нет - создаёт со значениями по умолчанию"""
    default_settings = {
        "allowed_users": [1138809734],
        "search_topics": ["Arizona RP", "Amazing RP", "Rodina RP"],
        "max_subscribers": 50000,
        "max_channels_per_topic": 20,
        "max_videos_per_topic": 50
    }
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_settings
    else:
        save_settings(default_settings)
        return default_settings

def save_settings(settings):
    """Сохраняет настройки в файл"""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# Загружаем настройки
settings = load_settings()

# ================= ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =================
ALLOWED_USER_IDS = settings.get("allowed_users", [1138809734])
SEARCH_TOPICS = settings.get("search_topics", ["Arizona RP", "Amazing RP", "Rodina RP"])
MAX_SUBSCRIBERS = settings.get("max_subscribers", 50000)
MAX_CHANNELS_PER_TOPIC = settings.get("max_channels_per_topic", 20)
MAX_VIDEOS_PER_TOPIC = settings.get("max_videos_per_topic", 50)

# Состояния для диалогов
user_states = {}

# ================= ОСТАЛЬНЫЕ НАСТРОЙКИ =================
YOUTUBE_API_KEY = "AIzaSyAbAkrORDfJRoTfGn7nn0TSuP8tz_hFEb0"
GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
SPREADSHEET_NAME = "YouTube Каналы RP (из видео)"
MAIN_SHEET_NAME = "База данных"

# ================= ИНИЦИАЛИЗАЦИЯ =================
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# YouTube API
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS, scope)
client = gspread.authorize(creds)

# ================= КНОПКИ =================
def main_menu():
    """Главное меню с кнопками"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🚀 Запустить парсер", callback_data="start_parser"),
        InlineKeyboardButton("📊 Статистика", callback_data="show_status")
    )
    keyboard.add(
        InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel"),
        InlineKeyboardButton("❓ Помощь", callback_data="show_help")
    )
    return keyboard

def admin_menu():
    """Админ-панель с кнопками"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Настройки", callback_data="show_settings"),
        InlineKeyboardButton("👥 Пользователи", callback_data="users_menu")
    )
    keyboard.add(
        InlineKeyboardButton("📌 Темы поиска", callback_data="topics_menu"),
        InlineKeyboardButton("👤 Лимит подписчиков", callback_data="subs_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data="back_main")
    )
    return keyboard

def users_menu():
    """Меню управления пользователями"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user"),
        InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")
    )
    keyboard.add(
        InlineKeyboardButton("📋 Список пользователей", callback_data="list_users")
    )
    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def topics_menu():
    """Меню управления темами"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить тему", callback_data="add_topic"),
        InlineKeyboardButton("➖ Удалить тему", callback_data="remove_topic")
    )
    keyboard.add(
        InlineKeyboardButton("📋 Список тем", callback_data="list_topics")
    )
    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def subs_menu():
    """Меню управления лимитом подписчиков"""
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton("10 000", callback_data="set_subs_10000"),
        InlineKeyboardButton("50 000", callback_data="set_subs_50000"),
        InlineKeyboardButton("100 000", callback_data="set_subs_100000")
    )
    keyboard.add(
        InlineKeyboardButton("200 000", callback_data="set_subs_200000"),
        InlineKeyboardButton("500 000", callback_data="set_subs_500000"),
        InlineKeyboardButton("1 000 000", callback_data="set_subs_1000000")
    )
    keyboard.add(
        InlineKeyboardButton("✏️ Своё значение", callback_data="set_subs_custom"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def cancel_button():
    """Кнопка отмены"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard

# ================= ПРОВЕРКА ПРАВ ДОСТУПА =================
def is_admin(user_id):
    """Проверяет, является ли пользователь админом (первый в списке)"""
    return user_id == ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else False

def is_user_allowed(user_id):
    """Проверяет, есть ли пользователь в списке разрешённых"""
    return user_id in ALLOWED_USER_IDS

def check_access(message):
    """Проверяет доступ и отправляет сообщение об ошибке, если доступа нет"""
    user_id = message.from_user.id
    if not is_user_allowed(user_id):
        bot.send_message(
            message.chat.id, 
            "❌ У вас нет доступа к этому боту.\n"
            "Обратитесь к создателю для добавления в список разрешённых."
        )
        return False
    return True

# ================= ФУНКЦИИ ПАРСЕРА =================
def get_subscriber_count(channel_id):
    try:
        request = youtube.channels().list(part="statistics", id=channel_id)
        response = request.execute()
        if response.get("items"):
            stats = response["items"][0]["statistics"]
            return int(stats.get("subscriberCount", 0))
        return 0
    except:
        return 0

def get_channel_description_and_links(channel_id):
    try:
        request = youtube.channels().list(part="snippet", id=channel_id)
        response = request.execute()
        if not response.get("items"):
            return "", "", ""
        
        description = response["items"][0]["snippet"].get("description", "")
        
        vk_link = ""
        tg_link = ""
        
        vk_pattern = r'(?:https?://)?(?:www\.)?(?:vk\.com|vk\.ru)/[^\s]+'
        vk_matches = re.findall(vk_pattern, description, re.IGNORECASE)
        if vk_matches:
            vk_link = vk_matches[0]
        
        tg_pattern = r'(?:https?://)?(?:www\.)?t\.me/[^\s]+'
        tg_matches = re.findall(tg_pattern, description, re.IGNORECASE)
        if tg_matches:
            tg_link = tg_matches[0]
        
        return description[:200], vk_link, tg_link
    except:
        return "", "", ""

def search_channels(topic, max_results):
    found_channels = {}
    next_page_token = None
    attempts = 0
    
    while len(found_channels) < max_results and attempts < 5:
        try:
            request = youtube.search().list(
                part="snippet",
                q=topic,
                type="video",
                maxResults=min(50, max_results - len(found_channels)),
                pageToken=next_page_token,
                order="relevance"
            )
            response = request.execute()
            
            for item in response.get("items", []):
                if len(found_channels) >= max_results:
                    break
                
                channel_id = item["snippet"]["channelId"]
                channel_name = item["snippet"]["channelTitle"]
                channel_url = f"https://www.youtube.com/channel/{channel_id}"
                video_title = item["snippet"]["title"]
                
                if channel_id in found_channels:
                    continue
                
                subs = get_subscriber_count(channel_id)
                if 0 < subs <= MAX_SUBSCRIBERS:
                    _, vk_link, tg_link = get_channel_description_and_links(channel_id)
                    
                    found_channels[channel_id] = {
                        "name": channel_name,
                        "url": channel_url,
                        "subscribers": subs,
                        "topic": topic,
                        "video_title": video_title,
                        "vk": vk_link,
                        "telegram": tg_link
                    }
                
                time.sleep(0.15)
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
            attempts += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"Ошибка: {e}")
            break
    
    return list(found_channels.values())

def get_workbook():
    try:
        return client.open(SPREADSHEET_NAME)
    except:
        return None

def save_to_sheets(workbook, channels):
    try:
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
    except:
        main_sheet = workbook.add_worksheet(title=MAIN_SHEET_NAME, rows=1, cols=7)
        main_sheet.append_row(["Название канала", "Ссылка на канал", "Подписчики", "Тема", "Найдено в видео", "VK", "Telegram"])
    
    existing_urls = set()
    all_data = main_sheet.get_all_values()
    for row in all_data[1:]:
        if len(row) > 1 and row[1]:
            existing_urls.add(row[1].strip())
    
    new_channels = []
    for ch in channels:
        if ch["url"] not in existing_urls:
            new_channels.append(ch)
    
    if not new_channels:
        return [], main_sheet, None
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_name = f"Отчет {timestamp}"
    try:
        report_sheet = workbook.worksheet(report_name)
    except:
        report_sheet = workbook.add_worksheet(title=report_name, rows=1, cols=7)
        report_sheet.append_row(["Название канала", "Ссылка на канал", "Подписчики", "Тема", "Найдено в видео", "VK", "Telegram"])
    
    for ch in new_channels:
        row = [ch["name"], ch["url"], ch["subscribers"], ch["topic"], ch["video_title"][:50], ch["vk"], ch["telegram"]]
        main_sheet.append_row(row)
        report_sheet.append_row(row)
    
    return new_channels, main_sheet, report_name

# ================= ОБРАБОТКА ТЕКСТОВЫХ КОМАНД =================
@bot.message_handler(commands=['start'])
def handle_start_command(message):
    if not check_access(message):
        return
    
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для поиска YouTube каналов по темам RP.\n"
        "Выберите действие в меню ниже:",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['help'])
def handle_help_command(message):
    if not check_access(message):
        return
    
    chat_id = message.chat.id
    bot.send_message(
        chat_id,
        "🤖 **Помощь**\n\n"
        "Используйте кнопки меню для управления ботом.\n\n"
        "**Основные функции:**\n"
        "• Поиск каналов по темам RP\n"
        "• Сохранение в Google Таблицу\n"
        "• Автоматическое создание отчётов\n\n"
        "**Админ-панель:**\n"
        "• Управление пользователями\n"
        "• Управление темами поиска\n"
        "• Настройка лимита подписчиков",
        parse_mode='Markdown',
        reply_markup=main_menu()
    )

# ================= ОБРАБОТКА CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    # Проверка доступа
    if not is_user_allowed(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет доступа!", show_alert=True)
        return
    
    # Главное меню
    if call.data == "back_main":
        bot.edit_message_text(
            "👋 Главное меню:\n\nВыберите действие:",
            chat_id,
            call.message.message_id,
            reply_markup=main_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    # Запуск парсера
    if call.data == "start_parser":
        bot.answer_callback_query(call.id, "🚀 Запускаю парсер...")
        bot.edit_message_text(
            "🚀 Запускаю парсер YouTube каналов...\n\nПодождите, это может занять несколько минут.",
            chat_id,
            call.message.message_id,
            reply_markup=None
        )
        run_parser(chat_id, call.message.message_id)
        return
    
    # Статистика
    if call.data == "show_status":
        bot.answer_callback_query(call.id)
        show_status(chat_id, call.message.message_id)
        return
    
    # Помощь
    if call.data == "show_help":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🤖 **Помощь**\n\n"
            "Используйте кнопки меню для управления ботом.\n\n"
            "**Основные функции:**\n"
            "• Поиск каналов по темам RP\n"
            "• Сохранение в Google Таблицу\n"
            "• Автоматическое создание отчётов\n\n"
            "**Админ-панель:**\n"
            "• Управление пользователями\n"
            "• Управление темами поиска\n"
            "• Настройка лимита подписчиков",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
        return
    
    # Админ-панель
    if call.data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "👑 **АДМИН-ПАНЕЛЬ**\n\n"
            f"📊 Текущие настройки:\n"
            f"• Макс. подписчиков: `{MAX_SUBSCRIBERS}`\n"
            f"• Тем: `{len(SEARCH_TOPICS)}`\n"
            f"• Пользователей: `{len(ALLOWED_USER_IDS)}`\n\n"
            "Выберите раздел:",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
        return
    
    # Назад в админку
    if call.data == "back_admin":
        bot.edit_message_text(
            "👑 **АДМИН-ПАНЕЛЬ**\n\n"
            f"📊 Текущие настройки:\n"
            f"• Макс. подписчиков: `{MAX_SUBSCRIBERS}`\n"
            f"• Тем: `{len(SEARCH_TOPICS)}`\n"
            f"• Пользователей: `{len(ALLOWED_USER_IDS)}`\n\n"
            "Выберите раздел:",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
        bot.answer_callback_query(call.id)
        return
    
    # Настройки
    if call.data == "show_settings":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        settings_text = (
            "📊 **ТЕКУЩИЕ НАСТРОЙКИ**\n\n"
            f"👥 **Пользователей:** {len(ALLOWED_USER_IDS)}\n"
            f"📌 **Тем:** {len(SEARCH_TOPICS)}\n"
            f"👤 **Макс. подписчиков:** {MAX_SUBSCRIBERS}\n"
            f"📺 **Макс. каналов на тему:** {MAX_CHANNELS_PER_TOPIC}\n\n"
            f"**Список тем:**\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]) + "\n\n"
            f"**Список пользователей:**\n" + "\n".join([f"• `{uid}`" for uid in ALLOWED_USER_IDS])
        )
        bot.edit_message_text(
            settings_text,
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=admin_menu()
        )
        return
    
    # Меню пользователей
    if call.data == "users_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "👥 **Управление пользователями**\n\n"
            f"Всего: {len(ALLOWED_USER_IDS)} пользователей\n\n"
            "Выберите действие:",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=users_menu()
        )
        return
    
    # Меню тем
    if call.data == "topics_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📌 **Управление темами**\n\n"
            f"Всего: {len(SEARCH_TOPICS)} тем\n\n"
            "Текущие темы:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]) + "\n\n"
            "Выберите действие:",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=topics_menu()
        )
        return
    
    # Меню подписчиков
    if call.data == "subs_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"👤 **Лимит подписчиков**\n\n"
            f"Текущий лимит: `{MAX_SUBSCRIBERS}`\n\n"
            "Выберите новый лимит:",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=subs_menu()
        )
        return
    
    # Установка лимита подписчиков
    if call.data.startswith("set_subs_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        value_str = call.data.replace("set_subs_", "")
        
        if value_str == "custom":
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "✏️ Введите новое значение в сообщении.\n\n"
                "Пример: `100000`",
                chat_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=cancel_button()
            )
            user_states[user_id] = "waiting_subs"
            return
        
        try:
            new_value = int(value_str)
            
            # Обновляем глобальную переменную
            global MAX_SUBSCRIBERS
            MAX_SUBSCRIBERS = new_value
            settings["max_subscribers"] = new_value
            save_settings(settings)
            
            bot.answer_callback_query(call.id, f"✅ Установлено: {new_value}")
            bot.edit_message_text(
                f"✅ Лимит подписчиков изменён на: `{new_value}`\n\n"
                f"🔙 Возврат в админ-панель...",
                chat_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка!", show_alert=True)
        return
    
    # Список пользователей
    if call.data == "list_users":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        text = "📋 **Список пользователей**\n\n"
        for i, uid in enumerate(ALLOWED_USER_IDS, 1):
            is_creator = "👑 " if i == 1 else ""
            text += f"{i}. {is_creator}`{uid}`\n"
        
        bot.edit_message_text(
            text,
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=users_menu()
        )
        return
    
    # Список тем
    if call.data == "list_topics":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        text = "📌 **Список тем**\n\n" + "\n".join([f"{i}. {t}" for i, t in enumerate(SEARCH_TOPICS, 1)])
        
        bot.edit_message_text(
            text,
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=topics_menu()
        )
        return
    
    # Добавить пользователя
    if call.data == "add_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите ID пользователя в сообщении.\n\n"
            "Пример: `123456789`",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_add_user"
        return
    
    # Удалить пользователя
    if call.data == "remove_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите ID пользователя для удаления.\n\n"
            "Пример: `123456789`\n"
            f"⚠️ Нельзя удалить создателя: `{ALLOWED_USER_IDS[0]}`",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_remove_user"
        return
    
    # Добавить тему
    if call.data == "add_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите новую тему в сообщении.\n\n"
            "Пример: `GTA 5 RP`",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_add_topic"
        return
    
    # Удалить тему
    if call.data == "remove_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите название темы для удаления.\n\n"
            "Текущие темы:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]) + "\n\n"
            "Пример: `Amazing RP`",
            chat_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_remove_topic"
        return
    
    # Отмена
    if call.data == "cancel":
        if user_id in user_states:
            del user_states[user_id]
        
        bot.answer_callback_query(call.id, "❌ Отменено")
        bot.edit_message_text(
            "✅ Действие отменено.\n\n"
            "Вернулись в админ-панель:",
            chat_id,
            call.message.message_id,
            reply_markup=admin_menu()
        )
        return

# ================= ФУНКЦИЯ ЗАПУСКА ПАРСЕРА =================
def run_parser(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text(
                "❌ Ошибка: Таблица не найдена!\n"
                "Создайте таблицу в Google Sheets и дайте доступ сервисному аккаунту.",
                chat_id,
                message_id
            )
            return
        
        all_channels = []
        
        for topic in SEARCH_TOPICS:
            bot.edit_message_text(
                f"🔍 Ищу каналы по теме: {topic}...",
                chat_id,
                message_id
            )
            channels = search_channels(topic, MAX_CHANNELS_PER_TOPIC)
            all_channels.extend(channels)
            time.sleep(1)
        
        if all_channels:
            all_channels.sort(key=lambda x: x["subscribers"], reverse=True)
            new_channels, main_sheet, report_name = save_to_sheets(workbook, all_channels)
            
            if new_channels:
                channel_list = ""
                for i, ch in enumerate(new_channels[:10], 1):
                    channel_list += f"{i}. {ch['name']} — {ch['subscribers']} подписчиков\n"
                    if ch['vk']:
                        channel_list += f"   VK: {ch['vk']}\n"
                    if ch['telegram']:
                        channel_list += f"   TG: {ch['telegram']}\n"
                
                if len(new_channels) > 10:
                    channel_list += f"\n... и ещё {len(new_channels) - 10} каналов"
                
                sheet_url = f"https://docs.google.com/spreadsheets/d/{workbook.id}"
                
                message = f"✅ **Парсинг завершён!**\n\n"
                message += f"📊 Найдено новых каналов: **{len(new_channels)}**\n"
                message += f"📋 Всего каналов в базе: **{len(main_sheet.get_all_values()) - 1}**\n\n"
                message += f"📌 Найденные каналы:\n{channel_list}\n\n"
                message += f"🔗 **Ссылка на таблицу:**\n{sheet_url}\n\n"
                message += f"📄 Отчёт сохранён в листе: **{report_name}**"
                
                bot.edit_message_text(
                    message,
                    chat_id,
                    message_id,
                    parse_mode='Markdown',
                    reply_markup=main_menu()
                )
            else:
                bot.edit_message_text(
                    f"⚠️ Новых каналов не найдено.\n"
                    f"Все каналы уже есть в базе данных.\n\n"
                    f"🔙 Возврат в главное меню:",
                    chat_id,
                    message_id,
                    reply_markup=main_menu()
                )
        else:
            bot.edit_message_text(
                "❌ Каналы не найдены.\n"
                "Попробуйте изменить тему поиска.\n\n"
                "🔙 Возврат в главное меню:",
                chat_id,
                message_id,
                reply_markup=main_menu()
            )
    
    except Exception as e:
        bot.edit_message_text(
            f"❌ Произошла ошибка:\n`{str(e)}`",
            chat_id,
            message_id,
            parse_mode='Markdown',
            reply_markup=main_menu()
        )

# ================= ФУНКЦИЯ СТАТИСТИКИ =================
def show_status(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text(
                "❌ Таблица не найдена!",
                chat_id,
                message_id,
                reply_markup=main_menu()
            )
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        total = len(main_sheet.get_all_values()) - 1
        
        bot.edit_message_text(
            f"📊 **СТАТИСТИКА**\n\n"
            f"📋 Всего каналов в базе: **{total}**\n"
            f"📌 Активные темы: **{len(SEARCH_TOPICS)}**\n"
            f"👥 Макс. подписчиков: **{MAX_SUBSCRIBERS}**\n"
            f"👤 Разрешённых пользователей: **{len(ALLOWED_USER_IDS)}**\n\n"
            f"📝 Темы поиска:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]) + "\n\n"
            f"🔗 **Ссылка на таблицу:**\nhttps://docs.google.com/spreadsheets/d/{workbook.id}",
            chat_id,
            message_id,
            parse_mode='Markdown',
            reply_markup=main_menu()
        )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка: {str(e)}",
            chat_id,
            message_id,
            reply_markup=main_menu()
        )

# ================= ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ =================
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "❌ У вас нет доступа к этому боту.")
        return
    
    # Обработка ожидающих состояний
    if user_id in user_states:
        state = user_states[user_id]
        text = message.text.strip()
        
        # Добавить пользователя
        if state == "waiting_add_user":
            try:
                new_id = int(text)
                if new_id in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ Пользователь с ID `{new_id}` уже в списке.", parse_mode='Markdown')
                    return
                
                ALLOWED_USER_IDS.append(new_id)
                settings["allowed_users"] = ALLOWED_USER_IDS
                save_settings(settings)
                
                del user_states[user_id]
                bot.send_message(
                    chat_id,
                    f"✅ Пользователь с ID `{new_id}` добавлен!",
                    parse_mode='Markdown',
                    reply_markup=admin_menu()
                )
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID (только цифры).")
            return
        
        # Удалить пользователя
        if state == "waiting_remove_user":
            try:
                remove_id = int(text)
                
                if remove_id == ALLOWED_USER_IDS[0]:
                    bot.send_message(chat_id, "❌ Нельзя удалить создателя бота.")
                    return
                
                if remove_id not in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ Пользователь с ID `{remove_id}` не найден.", parse_mode='Markdown')
                    return
                
                ALLOWED_USER_IDS.remove(remove_id)
                settings["allowed_users"] = ALLOWED_USER_IDS
                save_settings(settings)
                
                del user_states[user_id]
                bot.send_message(
                    chat_id,
                    f"✅ Пользователь с ID `{remove_id}` удалён!",
                    parse_mode='Markdown',
                    reply_markup=admin_menu()
                )
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID (только цифры).")
            return
        
        # Добавить тему
        if state == "waiting_add_topic":
            if text in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема `{text}` уже существует.", parse_mode='Markdown')
                return
            
            SEARCH_TOPICS.append(text)
            settings["search_topics"] = SEARCH_TOPICS
            save_settings(settings)
            
            del user_states[user_id]
            bot.send_message(
                chat_id,
                f"✅ Тема `{text}` добавлена!",
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
            return
        
        # Удалить тему
        if state == "waiting_remove_topic":
            if text not in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема `{text}` не найдена.", parse_mode='Markdown')
                return
            
            SEARCH_TOPICS.remove(text)
            settings["search_topics"] = SEARCH_TOPICS
            save_settings(settings)
            
            del user_states[user_id]
            bot.send_message(
                chat_id,
                f"✅ Тема `{text}` удалена!",
                parse_mode='Markdown',
                reply_markup=admin_menu()
            )
            return
        
        # Своё значение подписчиков
        if state == "waiting_subs":
            try:
                new_value = int(text)
                if new_value <= 0:
                    bot.send_message(chat_id, "❌ Число должно быть больше 0.")
                    return
                
                global MAX_SUBSCRIBERS
                MAX_SUBSCRIBERS = new_value
                settings["max_subscribers"] = new_value
                save_settings(settings)
                
                del user_states[user_id]
                bot.send_message(
                    chat_id,
                    f"✅ Лимит подписчиков изменён на: `{new_value}`",
                    parse_mode='Markdown',
                    reply_markup=admin_menu()
                )
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.")
            return
    
    # Если не в состоянии - показываем главное меню
    bot.send_message(
        chat_id,
        "Используйте кнопки меню:",
        reply_markup=main_menu()
    )

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 TELEGRAM БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👤 ID создателя: {ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 'Не задан'}")
    print(f"👥 Разрешённых пользователей: {len(ALLOWED_USER_IDS)}")
    print(f"📌 Активные темы: {', '.join(SEARCH_TOPICS)}")
    print(f"👥 Макс. подписчиков: {MAX_SUBSCRIBERS}")
    print("=" * 50)
    print("📌 Бот работает с кнопками!")
    print("=" * 50)
    print("⏳ Ожидание команд...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 10 секунд...")
            time.sleep(10)
