import time
import re
import json
import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

# ================= НАСТРОЙКИ =================
TELEGRAM_BOT_TOKEN = "8994730100:AAE6P65OqjVOTAftOIPZuBF70WAwzxz116A"
YOUTUBE_API_KEY = "AIzaSyAbAkrORDfJRoTfGn7nn0TSuP8tz_hFEb0"

# ================= ПАРАМЕТРЫ ФИЛЬТРАЦИИ =================
MIN_ENGAGEMENT_RATE = 3.0
MIN_GROWTH_RATE = 5.0
MAX_DAYS_INACTIVE = 30
MIN_SCORE_FOR_TOP = 65

# ================= НАСТРОЙКИ GOOGLE =================
GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
SPREADSHEET_NAME = "YouTube Каналы RP (из видео)"
MAIN_SHEET_NAME = "База данных"

# ================= ФАЙЛЫ ДЛЯ ХРАНЕНИЯ =================
SETTINGS_FILE = "bot_settings.json"
CHANNELS_DB_FILE = "data/channels_db.json"

# ================= ИНИЦИАЛИЗАЦИЯ =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS, scope)
client = gspread.authorize(creds)

user_states = {}

# ================= ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ =================
def ensure_data_dir():
    os.makedirs("data", exist_ok=True)

def load_settings():
    default = {
        "allowed_users": [1138809734],
        "search_topics": ["Arizona RP", "Amazing RP", "Rodina RP"],
        "max_subscribers": 50000,
        "min_subscribers": 100,
        "min_engagement_rate": 3.0,
        "min_growth_rate": 5.0,
        "max_days_inactive": 30,
        "min_score_for_top": 65
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    else:
        save_settings(default)
        return default

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def load_channels_db():
    ensure_data_dir()
    if os.path.exists(CHANNELS_DB_FILE):
        try:
            with open(CHANNELS_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_channels_db(db):
    ensure_data_dir()
    with open(CHANNELS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

settings = load_settings()
ALLOWED_USER_IDS = settings.get("allowed_users", [1138809734])
SEARCH_TOPICS = settings.get("search_topics", ["Arizona RP", "Amazing RP", "Rodina RP"])
MAX_SUBSCRIBERS = settings.get("max_subscribers", 50000)
MIN_SUBSCRIBERS = settings.get("min_subscribers", 100)

def update_global_settings():
    global ALLOWED_USER_IDS, SEARCH_TOPICS, MAX_SUBSCRIBERS, MIN_SUBSCRIBERS
    s = load_settings()
    ALLOWED_USER_IDS = s.get("allowed_users", [1138809734])
    SEARCH_TOPICS = s.get("search_topics", ["Arizona RP", "Amazing RP", "Rodina RP"])
    MAX_SUBSCRIBERS = s.get("max_subscribers", 50000)
    MIN_SUBSCRIBERS = s.get("min_subscribers", 100)

# ================= РАБОТА С YOUTUBE API =================
def get_channel_statistics(channel_id):
    try:
        request = youtube.channels().list(part="statistics,snippet", id=channel_id)
        response = request.execute()
        if response.get("items"):
            item = response["items"][0]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            return {
                "subscribers": int(stats.get("subscriberCount", 0)),
                "views": int(stats.get("viewCount", 0)),
                "videos": int(stats.get("videoCount", 0)),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnails": snippet.get("thumbnails", {})
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return None

def get_video_statistics(video_id):
    try:
        request = youtube.videos().list(part="statistics", id=video_id)
        response = request.execute()
        if response.get("items"):
            stats = response["items"][0]["statistics"]
            return {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0))
            }
        return None
    except:
        return None

def get_recent_videos(channel_id, limit=10):
    try:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            maxResults=limit,
            order="date"
        )
        response = request.execute()
        videos = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            stats = get_video_statistics(video_id)
            if stats:
                videos.append({
                    "id": video_id,
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "views": stats["views"],
                    "likes": stats["likes"],
                    "comments": stats["comments"]
                })
            time.sleep(0.1)
        return videos
    except Exception as e:
        logger.error(f"Ошибка получения видео: {e}")
        return []

def search_channels_by_topic(topic, max_results=20):
    found_channels = {}
    next_page_token = None
    attempts = 0
    
    while len(found_channels) < max_results and attempts < 3:
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
                video_id = item["id"]["videoId"]
                
                if channel_id in found_channels:
                    continue
                
                stats = get_channel_statistics(channel_id)
                if not stats:
                    continue
                
                subs = stats["subscribers"]
                if MIN_SUBSCRIBERS <= subs <= MAX_SUBSCRIBERS:
                    found_channels[channel_id] = {
                        "channel_id": channel_id,
                        "name": channel_name,
                        "url": channel_url,
                        "subscribers": subs,
                        "topic": topic,
                        "video_title": video_title,
                        "video_id": video_id,
                        "description": stats["description"],
                        "videos_count": stats["videos"]
                    }
                
                time.sleep(0.15)
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
            attempts += 1
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            break
    
    return list(found_channels.values())

# ================= АНАЛИЗ И СКОРИНГ =================
def extract_links(text):
    links = {
        "vk": "",
        "telegram": "",
        "instagram": "",
        "twitter": "",
        "youtube": "",
        "tiktok": "",
        "email": "",
        "site": ""
    }
    
    if not text:
        return links
    
    patterns = {
        "vk": r'(?:https?://)?(?:www\.)?(?:vk\.com|vk\.ru)/[^\s]+',
        "telegram": r'(?:https?://)?(?:www\.)?t\.me/[^\s]+',
        "instagram": r'(?:https?://)?(?:www\.)?instagram\.com/[^\s]+',
        "twitter": r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[^\s]+',
        "youtube": r'(?:https?://)?(?:www\.)?youtube\.com/(?:c|channel|user)/[^\s]+',
        "tiktok": r'(?:https?://)?(?:www\.)?tiktok\.com/@[^\s]+',
        "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "site": r'(?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
    }
    
    for key, pattern in patterns.items():
        if key == "site":
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                if not any(social in m.lower() for social in ['vk', 't.me', 'instagram', 'twitter', 'youtube', 'tiktok']):
                    links[key] = m
                    break
        else:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                links[key] = matches[0]
    
    return links

def calculate_engagement_rate(videos):
    if not videos or len(videos) < 3:
        return 0.0
    
    total_views = 0
    total_likes = 0
    total_comments = 0
    count = 0
    
    for video in videos[:10]:
        total_views += video["views"]
        total_likes += video["likes"]
        total_comments += video["comments"]
        count += 1
    
    if count == 0 or total_views == 0:
        return 0.0
    
    total_engagement = total_likes + total_comments
    er = (total_engagement / total_views) * 100
    return round(er, 2)

def calculate_days_inactive(videos):
    if not videos:
        return 999
    try:
        last_date = datetime.fromisoformat(videos[0]["published_at"].replace('Z', '+00:00'))
        days = (datetime.now() - last_date).days
        return days
    except:
        return 999

def calculate_channel_score(channel_data, videos):
    score = 0
    
    subs = channel_data.get("subscribers", 0)
    if subs >= 100000:
        score += 25
    elif subs >= 50000:
        score += 22
    elif subs >= 10000:
        score += 18
    elif subs >= 5000:
        score += 14
    elif subs >= 1000:
        score += 10
    elif subs >= 500:
        score += 5
    else:
        score += 2
    
    er = calculate_engagement_rate(videos)
    if er >= 10:
        score += 25
    elif er >= 7:
        score += 20
    elif er >= 5:
        score += 15
    elif er >= 3:
        score += 10
    elif er >= 1:
        score += 5
    else:
        score += 0
    
    days = calculate_days_inactive(videos)
    if days <= 3:
        score += 20
    elif days <= 7:
        score += 15
    elif days <= 14:
        score += 10
    elif days <= 30:
        score += 5
    else:
        score += 0
    
    contacts = channel_data.get("contacts", {})
    if contacts.get("email"):
        score += 10
    if contacts.get("telegram"):
        score += 5
    if contacts.get("vk"):
        score += 3
    if contacts.get("instagram"):
        score += 2
    
    desc = channel_data.get("description", "")
    if len(desc) > 200:
        score += 5
    if "партнер" in desc.lower() or "сотрудничество" in desc.lower():
        score += 5
    
    return min(score, 100)

def analyze_channel_deep(channel_data):
    channel_id = channel_data.get("channel_id")
    videos = get_recent_videos(channel_id, 10)
    er = calculate_engagement_rate(videos)
    days_inactive = calculate_days_inactive(videos)
    contacts = extract_links(channel_data.get("description", ""))
    
    channel_data["videos"] = videos
    channel_data["engagement_rate"] = er
    channel_data["days_inactive"] = days_inactive
    channel_data["contacts"] = contacts
    channel_data["score"] = calculate_channel_score(channel_data, videos)
    channel_data["analyzed"] = True
    channel_data["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return channel_data

# ================= КЛАВИАТУРЫ =================
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🚀 Запустить парсер", callback_data="start_parser"),
        InlineKeyboardButton("📊 Статистика", callback_data="show_status")
    )
    keyboard.add(
        InlineKeyboardButton("🔍 Глубокий анализ", callback_data="deep_analysis"),
        InlineKeyboardButton("🏆 ТОП кандидатов", callback_data="show_top")
    )
    keyboard.add(
        InlineKeyboardButton("🔄 Проверить VK/TG", callback_data="check_vk_tg"),
        InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")
    )
    keyboard.add(
        InlineKeyboardButton("💾 Сохранить настройки", callback_data="save_settings"),
        InlineKeyboardButton("❓ Помощь", callback_data="show_help")
    )
    return keyboard

def admin_menu():
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
        InlineKeyboardButton("📈 Параметры анализа", callback_data="analysis_settings"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_main")
    )
    return keyboard

def users_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user"),
        InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")
    )
    keyboard.add(
        InlineKeyboardButton("📋 Список пользователей", callback_data="list_users"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def topics_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить тему", callback_data="add_topic"),
        InlineKeyboardButton("➖ Удалить тему", callback_data="remove_topic")
    )
    keyboard.add(
        InlineKeyboardButton("📋 Список тем", callback_data="list_topics"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def subs_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📈 Макс. подписчиков", callback_data="set_max_subs"),
        InlineKeyboardButton("📉 Мин. подписчиков", callback_data="set_min_subs")
    )
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

def analysis_settings_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"📈 Мин. ER: {MIN_ENGAGEMENT_RATE}%", callback_data="set_min_er"),
        InlineKeyboardButton(f"📊 Мин. рост: {MIN_GROWTH_RATE}%", callback_data="set_min_growth"),
        InlineKeyboardButton(f"⏰ Макс. дней неактивности: {MAX_DAYS_INACTIVE}", callback_data="set_max_inactive"),
        InlineKeyboardButton(f"⭐ Мин. скор для ТОПа: {MIN_SCORE_FOR_TOP}", callback_data="set_min_score")
    )
    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data="back_admin")
    )
    return keyboard

def cancel_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard

# ================= РАБОТА С GOOGLE SHEETS =================
def get_workbook():
    try:
        return client.open(SPREADSHEET_NAME)
    except:
        return None

def save_to_sheets(workbook, channels):
    try:
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
    except:
        main_sheet = workbook.add_worksheet(title=MAIN_SHEET_NAME, rows=1, cols=9)
        main_sheet.append_row([
            "Название канала", "Ссылка", "Подписчики", "Тема",
            "ER (%)", "Дней неактивности", "Email", "Telegram", "VK"
        ])
    
    existing_urls = set()
    all_data = main_sheet.get_all_values()
    for row in all_data[1:]:
        if len(row) > 1 and row[1]:
            existing_urls.add(row[1].strip())
    
    new_rows = []
    for ch in channels:
        if ch["url"] not in existing_urls:
            contacts = ch.get("contacts", {})
            new_rows.append([
                ch["name"],
                ch["url"],
                ch["subscribers"],
                ch["topic"],
                ch.get("engagement_rate", 0),
                ch.get("days_inactive", 999),
                contacts.get("email", ""),
                contacts.get("telegram", ""),
                contacts.get("vk", "")
            ])
    
    if new_rows:
        for row in new_rows:
            try:
                main_sheet.append_row(row)
            except:
                pass
    
    return new_rows

def update_sheet_with_analysis(workbook, channels_db):
    try:
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        
        headers = main_sheet.row_values(1)
        new_headers = ["Название канала", "Ссылка", "Подписчики", "Тема", "ER (%)", "Дней неактивности", "Email", "Telegram", "VK", "Скор"]
        
        if len(headers) < len(new_headers):
            main_sheet.append_row(new_headers)
            main_sheet.delete_row(1)
            main_sheet.append_row(new_headers)
        
        all_data = main_sheet.get_all_values()
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) < 2:
                continue
            
            channel_url = row[1]
            channel_id = channel_url.split("/")[-1]
            
            if channel_id in channels_db:
                data = channels_db[channel_id]
                contacts = data.get("contacts", {})
                
                try:
                    main_sheet.update_cell(i, 5, data.get("engagement_rate", 0))
                    main_sheet.update_cell(i, 6, data.get("days_inactive", 999))
                    main_sheet.update_cell(i, 7, contacts.get("email", ""))
                    main_sheet.update_cell(i, 8, contacts.get("telegram", ""))
                    main_sheet.update_cell(i, 9, contacts.get("vk", ""))
                    main_sheet.update_cell(i, 10, data.get("score", 0))
                except:
                    pass
                
                time.sleep(0.1)
                
    except Exception as e:
        logger.error(f"Ошибка обновления таблицы: {e}")

# ================= ПРОВЕРКА ДОСТУПА =================
def is_admin(user_id):
    return user_id == ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else False

def is_user_allowed(user_id):
    return user_id in ALLOWED_USER_IDS

def check_access(message):
    user_id = message.from_user.id
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этому боту.")
        return False
    return True

# ================= ОБРАБОТЧИКИ КОМАНД =================
@bot.message_handler(commands=['start'])
def handle_start_command(message):
    if not check_access(message):
        return
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Партнёрский ассистент для YouTube**\n\n"
        "Что я умею:\n"
        "• 🔍 Искать каналы по темам RP\n"
        "• 📊 Анализировать вовлеченность (ER)\n"
        "• 🏆 Отбирать лучшие каналы по рейтингу\n"
        "• 📧 Находить контакты для связи\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['help'])
def handle_help_command(message):
    if not check_access(message):
        return
    help_text = """
🤖 **Помощь**

**Основные функции:**

🔍 **Запустить парсер** — поиск новых каналов по темам

📊 **Глубокий анализ** — анализ ER, активности, поиск контактов

🏆 **ТОП кандидатов** — список лучших каналов для сотрудничества

🔄 **Проверить VK/TG** — обновление ссылок в таблице

👑 **Админ-панель** — управление настройками

**Как это работает:**
1. Запускаете парсер → бот ищет каналы
2. Делаете глубокий анализ → бот считает ER, находит контакты
3. Смотрите ТОП кандидатов → выбираете лучших
4. Пишете им вручную → сотрудничество!

**Критерии оценки:**
• Подписчики (0-25 баллов)
• Вовлеченность ER (0-25 баллов)
• Активность (0-20 баллов)
• Наличие контактов (0-20 баллов)
• Качество описания (0-10 баллов)
    """
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown', reply_markup=main_menu())

# ================= ОСНОВНЫЕ ФУНКЦИИ БОТА =================
def run_parser(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text("❌ Таблица не найдена!", chat_id, message_id, reply_markup=main_menu())
            return
        
        all_channels = []
        for topic in SEARCH_TOPICS:
            bot.edit_message_text(f"🔍 Ищу: {topic}...", chat_id, message_id)
            channels = search_channels_by_topic(topic, 20)
            all_channels.extend(channels)
            time.sleep(1)
        
        if all_channels:
            all_channels.sort(key=lambda x: x["subscribers"], reverse=True)
            new_channels = save_to_sheets(workbook, all_channels)
            
            if new_channels:
                sheet_url = f"https://docs.google.com/spreadsheets/d/{workbook.id}"
                msg = f"✅ **Найдено {len(new_channels)} новых каналов!**\n\n"
                msg += f"📊 Теперь запустите **Глубокий анализ** для оценки качества.\n\n"
                msg += f"🔗 {sheet_url}"
                bot.edit_message_text(msg, chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu())
            else:
                bot.edit_message_text("⚠️ Новых каналов не найдено.", chat_id, message_id, reply_markup=main_menu())
        else:
            bot.edit_message_text("❌ Каналы не найдены.", chat_id, message_id, reply_markup=main_menu())
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def run_deep_analysis(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text("❌ Таблица не найдена!", chat_id, message_id, reply_markup=main_menu())
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        all_data = main_sheet.get_all_values()
        
        if len(all_data) <= 1:
            bot.edit_message_text("⚠️ Нет каналов для анализа. Сначала запустите парсер.", chat_id, message_id, reply_markup=main_menu())
            return
        
        bot.edit_message_text("🔍 Запускаю глубокий анализ...\n\nЭто может занять несколько минут.", chat_id, message_id)
        
        channels_db = load_channels_db()
        analyzed = 0
        found_contacts = 0
        
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) < 2:
                continue
            
            channel_url = row[1]
            channel_id = channel_url.split("/")[-1]
            
            if channel_id in channels_db and channels_db[channel_id].get("analyzed"):
                continue
            
            channel_data = {
                "channel_id": channel_id,
                "name": row[0] if len(row) > 0 else "",
                "url": row[1] if len(row) > 1 else "",
                "subscribers": int(row[2]) if len(row) > 2 and row[2] else 0,
                "topic": row[3] if len(row) > 3 else "",
                "description": ""
            }
            
            stats = get_channel_statistics(channel_id)
            if stats:
                channel_data["description"] = stats.get("description", "")
            
            analyzed_data = analyze_channel_deep(channel_data)
            contacts = analyzed_data.get("contacts", {})
            
            if contacts.get("email") or contacts.get("telegram"):
                found_contacts += 1
            
            channels_db[channel_id] = analyzed_data
            analyzed += 1
            
            if analyzed % 3 == 0:
                bot.edit_message_text(f"🔍 Проанализировано {analyzed} каналов...", chat_id, message_id)
            
            save_channels_db(channels_db)
            time.sleep(0.5)
        
        save_channels_db(channels_db)
        update_sheet_with_analysis(workbook, channels_db)
        
        msg = f"✅ **Глубокий анализ завершён!**\n\n"
        msg += f"📊 Проанализировано: **{analyzed}** каналов\n"
        msg += f"📧 Найдено контактов: **{found_contacts}**\n\n"
        msg += f"🏆 Нажмите **ТОП кандидатов** для просмотра лучших вариантов."
        
        bot.edit_message_text(msg, chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu())
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def show_top_candidates(chat_id, message_id):
    try:
        channels_db = load_channels_db()
        
        if not channels_db:
            bot.edit_message_text(
                "⚠️ Нет данных для анализа.\n\n"
                "Сначала запустите:\n"
                "1. 🚀 Парсер\n"
                "2. 🔍 Глубокий анализ",
                chat_id, message_id, reply_markup=main_menu()
            )
            return
        
        candidates = []
        for ch_id, data in channels_db.items():
            score = data.get("score", 0)
            er = data.get("engagement_rate", 0)
            days = data.get("days_inactive", 999)
            
            if (score >= MIN_SCORE_FOR_TOP and 
                er >= MIN_ENGAGEMENT_RATE and 
                days <= MAX_DAYS_INACTIVE):
                candidates.append(data)
        
        if not candidates:
            bot.edit_message_text(
                "❌ Кандидатов не найдено.\n\n"
                f"Попробуйте снизить порог:\n"
                f"• Мин. скор: {MIN_SCORE_FOR_TOP}\n"
                f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
                f"• Макс. неактивность: {MAX_DAYS_INACTIVE} дн\n\n"
                "Или измените настройки в админ-панели.",
                chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu()
            )
            return
        
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        msg = "🏆 **ТОП КАНДИДАТЫ ДЛЯ СОТРУДНИЧЕСТВА**\n\n"
        
        for i, c in enumerate(candidates[:10], 1):
            contacts = c.get("contacts", {})
            msg += f"**{i}. {c.get('name', 'N/A')}**\n"
            msg += f"   📊 Скор: **{c.get('score', 0)}/100**\n"
            msg += f"   👥 Подписчиков: {c.get('subscribers', 0):,}\n"
            msg += f"   📈 ER: {c.get('engagement_rate', 0)}%\n"
            msg += f"   ⏰ Дней без видео: {c.get('days_inactive', 999)}\n"
            
            if contacts.get("email"):
                msg += f"   📧 Email: `{contacts['email']}`\n"
            if contacts.get("telegram"):
                msg += f"   💬 Telegram: {contacts['telegram']}\n"
            if contacts.get("vk"):
                msg += f"   🎯 VK: {contacts['vk']}\n"
            
            msg += f"   🔗 {c.get('url', '')}\n\n"
        
        if len(candidates) > 10:
            msg += f"\n... и ещё {len(candidates) - 10} кандидатов.\n"
            msg += f"📋 Всего найдено: **{len(candidates)}** каналов"
        
        bot.edit_message_text(msg, chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu())
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def check_vk_tg(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text("❌ Таблица не найдена!", chat_id, message_id, reply_markup=main_menu())
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        all_data = main_sheet.get_all_values()
        
        if len(all_data) <= 1:
            bot.edit_message_text("⚠️ В таблице нет каналов.", chat_id, message_id, reply_markup=main_menu())
            return
        
        bot.edit_message_text("🔄 Проверяю ссылки VK и Telegram...", chat_id, message_id)
        
        updated = 0
        channels_db = load_channels_db()
        
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) < 2:
                continue
            
            channel_url = row[1]
            channel_id = channel_url.split("/")[-1]
            
            if channel_id in channels_db:
                contacts = channels_db[channel_id].get("contacts", {})
                vk = contacts.get("vk", "")
                tg = contacts.get("telegram", "")
                
                if vk:
                    try:
                        main_sheet.update_cell(i, 9, vk)
                        updated += 1
                    except:
                        pass
                if tg:
                    try:
                        main_sheet.update_cell(i, 8, tg)
                        updated += 1
                    except:
                        pass
                
                time.sleep(0.1)
        
        bot.edit_message_text(
            f"✅ Проверка завершена!\n\n"
            f"📊 Обновлено ссылок: **{updated}**",
            chat_id, message_id, reply_markup=main_menu()
        )
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def show_status(chat_id, message_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.edit_message_text("❌ Таблица не найдена!", chat_id, message_id, reply_markup=main_menu())
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        total = len(main_sheet.get_all_values()) - 1
        
        channels_db = load_channels_db()
        analyzed = len([c for c in channels_db.values() if c.get("analyzed")])
        with_contacts = len([c for c in channels_db.values() if c.get("contacts", {}).get("email") or c.get("contacts", {}).get("telegram")])
        
        msg = f"📊 **СТАТИСТИКА**\n\n"
        msg += f"📋 Всего каналов: **{total}**\n"
        msg += f"🔍 Проанализировано: **{analyzed}**\n"
        msg += f"📧 Найдено контактов: **{with_contacts}**\n\n"
        msg += f"📌 Активных тем: **{len(SEARCH_TOPICS)}**\n"
        msg += f"👤 Пользователей: **{len(ALLOWED_USER_IDS)}**\n\n"
        msg += f"⚙️ Параметры отбора:\n"
        msg += f"• Мин. подписчиков: {MIN_SUBSCRIBERS}\n"
        msg += f"• Макс. подписчиков: {MAX_SUBSCRIBERS}\n"
        msg += f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
        msg += f"• Мин. скор для ТОПа: {MIN_SCORE_FOR_TOP}\n\n"
        msg += f"🔗 {workbook.url}"
        
        bot.edit_message_text(msg, chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu())
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

# ================= ОБРАБОТЧИКИ CALLBACK =================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if not is_user_allowed(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет доступа!", show_alert=True)
        return
    
    # Главное меню
    if call.data == "back_main":
        bot.edit_message_text("👋 Главное меню:", chat_id, call.message.message_id, reply_markup=main_menu())
        bot.answer_callback_query(call.id)
        return
    
    if call.data == "back_admin":
        bot.edit_message_text("👑 **АДМИН-ПАНЕЛЬ**", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu())
        bot.answer_callback_query(call.id)
        return
    
    # Запуск парсера
    if call.data == "start_parser":
        bot.answer_callback_query(call.id, "🚀 Запускаю...")
        run_parser(chat_id, call.message.message_id)
        return
    
    # Статистика
    if call.data == "show_status":
        bot.answer_callback_query(call.id)
        show_status(chat_id, call.message.message_id)
        return
    
    # Глубокий анализ
    if call.data == "deep_analysis":
        bot.answer_callback_query(call.id, "🔍 Запускаю глубокий анализ...")
        run_deep_analysis(chat_id, call.message.message_id)
        return
    
    # ТОП кандидатов
    if call.data == "show_top":
        bot.answer_callback_query(call.id)
        show_top_candidates(chat_id, call.message.message_id)
        return
    
    # Проверка VK/TG
    if call.data == "check_vk_tg":
        bot.answer_callback_query(call.id, "🔄 Проверяю...")
        check_vk_tg(chat_id, call.message.message_id)
        return
    
    # Админ-панель
    if call.data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"👑 **АДМИН-ПАНЕЛЬ**\n\n"
            f"📊 Настройки:\n"
            f"• Мин. подписчиков: `{MIN_SUBSCRIBERS}`\n"
            f"• Макс. подписчиков: `{MAX_SUBSCRIBERS}`\n"
            f"• Мин. ER: `{MIN_ENGAGEMENT_RATE}%`\n"
            f"• Мин. скор для ТОПа: `{MIN_SCORE_FOR_TOP}`\n\n"
            "Выберите раздел:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu()
        )
        return
    
    # Настройки
    if call.data == "show_settings":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        s = load_settings()
        text = (
            "📊 **НАСТРОЙКИ**\n\n"
            f"👥 Пользователей: {len(s.get('allowed_users', []))}\n"
            f"📌 Тем: {', '.join(s.get('search_topics', []))}\n"
            f"👤 Мин. подписчиков: {s.get('min_subscribers', 100)}\n"
            f"👤 Макс. подписчиков: {s.get('max_subscribers', 50000)}\n"
            f"📈 Мин. ER: {s.get('min_engagement_rate', 3.0)}%\n"
            f"📊 Мин. рост: {s.get('min_growth_rate', 5.0)}%\n"
            f"⏰ Макс. неактивность: {s.get('max_days_inactive', 30)} дн\n"
            f"⭐ Мин. скор для ТОПа: {s.get('min_score_for_top', 65)}"
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=admin_menu())
        return
    
    # Анализ настройки
    if call.data == "analysis_settings":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📈 **НАСТРОЙКИ АНАЛИЗА**\n\n"
            "Здесь можно настроить критерии отбора:\n"
            "• ER — вовлеченность аудитории\n"
            "• Рост — рост подписчиков в месяц\n"
            "• Неактивность — дней без видео\n"
            "• Мин. скор — порог для ТОП-списка\n\n"
            "Выберите параметр для изменения:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=analysis_settings_menu()
        )
        return
    
    # Установка параметров анализа
    if call.data == "set_min_er":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите минимальный ER (вовлеченность) в %.\n\n"
            "Пример: `5` (означает 5%)\n"
            f"Текущее значение: {MIN_ENGAGEMENT_RATE}%",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_min_er"
        return
    
    if call.data == "set_min_growth":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите минимальный рост подписчиков в месяц (%)\n\n"
            "Пример: `10` (означает 10% роста)\n"
            f"Текущее значение: {MIN_GROWTH_RATE}%",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_min_growth"
        return
    
    if call.data == "set_max_inactive":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите максимальное количество дней без видео.\n\n"
            "Пример: `14`\n"
            f"Текущее значение: {MAX_DAYS_INACTIVE} дн",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_max_inactive"
        return
    
    if call.data == "set_min_score":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите минимальный скор для попадания в ТОП.\n\n"
            "Пример: `70`\n"
            f"Текущее значение: {MIN_SCORE_FOR_TOP}",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_min_score"
        return
    
    # Меню пользователей
    if call.data == "users_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"👥 **Управление пользователями**\n\n"
            f"Всего: {len(ALLOWED_USER_IDS)}\n\n"
            "Выберите действие:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=users_menu()
        )
        return
    
    if call.data == "add_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите ID пользователя.\n\n"
            "Пример: `123456789`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_add_user"
        return
    
    if call.data == "remove_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите ID пользователя для удаления.\n\n"
            f"⚠️ Нельзя удалить создателя: `{ALLOWED_USER_IDS[0]}`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_remove_user"
        return
    
    if call.data == "list_users":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        text = "📋 **Список пользователей**\n\n"
        for i, uid in enumerate(ALLOWED_USER_IDS, 1):
            is_creator = "👑 " if i == 1 else ""
            text += f"{i}. {is_creator}`{uid}`\n"
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=users_menu())
        return
    
    # Меню тем
    if call.data == "topics_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"📌 **Управление темами**\n\n"
            f"Темы: {', '.join(SEARCH_TOPICS)}\n\n"
            "Выберите действие:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=topics_menu()
        )
        return
    
    if call.data == "add_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите новую тему.\n\n"
            "Пример: `GTA 5 RP`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_add_topic"
        return
    
    if call.data == "remove_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите тему для удаления.\n\n"
            f"Текущие темы:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]),
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_remove_topic"
        return
    
    if call.data == "list_topics":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        text = "📌 **Список тем**\n\n" + "\n".join([f"{i}. {t}" for i, t in enumerate(SEARCH_TOPICS, 1)])
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=topics_menu())
        return
    
    # Меню подписчиков
    if call.data == "subs_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"👤 **Лимит подписчиков**\n\n"
            f"Текущий мин: `{MIN_SUBSCRIBERS}`\n"
            f"Текущий макс: `{MAX_SUBSCRIBERS}`\n\n"
            "Выберите новый макс. лимит:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=subs_menu()
        )
        return
    
    if call.data == "set_max_subs":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите новое значение МАКС. подписчиков.\n\n"
            "Пример: `100000`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_max_subs"
        return
    
    if call.data == "set_min_subs":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Введите новое значение МИН. подписчиков.\n\n"
            "Пример: `1000`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_min_subs"
        return
    
    if call.data.startswith("set_subs_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        value_str = call.data.replace("set_subs_", "")
        if value_str == "custom":
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "✏️ Введите новое значение МАКС. подписчиков.\n\n"
                "Пример: `100000`",
                chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
            )
            user_states[user_id] = "waiting_max_subs"
            return
        try:
            new_value = int(value_str)
            s = load_settings()
            s["max_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            bot.answer_callback_query(call.id, f"✅ Установлено: {new_value}")
            bot.edit_message_text(
                f"✅ Макс. подписчиков изменён на: `{new_value}`",
                chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu()
            )
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка!", show_alert=True)
        return
    
    # Сохранение настроек
    if call.data == "save_settings":
        update_global_settings()
        bot.answer_callback_query(call.id, "✅ Настройки сохранены!")
        bot.edit_message_text("✅ Настройки синхронизированы и сохранены!", chat_id, call.message.message_id, reply_markup=main_menu())
        return
    
    # Отмена
    if call.data == "cancel":
        if user_id in user_states:
            del user_states[user_id]
        bot.answer_callback_query(call.id, "❌ Отменено")
        bot.edit_message_text("✅ Действие отменено.", chat_id, call.message.message_id, reply_markup=admin_menu())
        return
    
    # Помощь
    if call.data == "show_help":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🤖 **Помощь**\n\n"
            "Используйте кнопки меню.\n"
            "Подробнее в /help",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=main_menu()
        )
        return

# ================= ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ =================
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "❌ У вас нет доступа.")
        return
    
    if user_id not in user_states:
        bot.send_message(chat_id, "Используйте кнопки меню:", reply_markup=main_menu())
        return
    
    state = user_states[user_id]
    text = message.text.strip()
    
    # Добавление пользователя
    if state == "waiting_add_user":
        try:
            new_id = int(text)
            if new_id in ALLOWED_USER_IDS:
                bot.send_message(chat_id, f"⚠️ ID {new_id} уже есть.")
                return
            ALLOWED_USER_IDS.append(new_id)
            s = load_settings()
            s["allowed_users"] = ALLOWED_USER_IDS
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Пользователь {new_id} добавлен!", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректный ID.")
        return
    
    # Удаление пользователя
    if state == "waiting_remove_user":
        try:
            remove_id = int(text)
            if remove_id == ALLOWED_USER_IDS[0]:
                bot.send_message(chat_id, "❌ Нельзя удалить создателя.")
                return
            if remove_id not in ALLOWED_USER_IDS:
                bot.send_message(chat_id, f"⚠️ ID {remove_id} не найден.")
                return
            ALLOWED_USER_IDS.remove(remove_id)
            s = load_settings()
            s["allowed_users"] = ALLOWED_USER_IDS
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Пользователь {remove_id} удалён!", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректный ID.")
        return
    
    # Добавление темы
    if state == "waiting_add_topic":
        if text in SEARCH_TOPICS:
            bot.send_message(chat_id, f"⚠️ Тема '{text}' уже есть.")
            return
        SEARCH_TOPICS.append(text)
        s = load_settings()
        s["search_topics"] = SEARCH_TOPICS
        save_settings(s)
        update_global_settings()
        del user_states[user_id]
        bot.send_message(chat_id, f"✅ Тема '{text}' добавлена!", reply_markup=admin_menu())
        return
    
    # Удаление темы
    if state == "waiting_remove_topic":
        if text not in SEARCH_TOPICS:
            bot.send_message(chat_id, f"⚠️ Тема '{text}' не найдена.")
            return
        SEARCH_TOPICS.remove(text)
        s = load_settings()
        s["search_topics"] = SEARCH_TOPICS
        save_settings(s)
        update_global_settings()
        del user_states[user_id]
        bot.send_message(chat_id, f"✅ Тема '{text}' удалена!", reply_markup=admin_menu())
        return
    
    # Макс. подписчики
    if state == "waiting_max_subs":
        try:
            new_value = int(text)
            if new_value <= 0:
                bot.send_message(chat_id, "❌ Число должно быть > 0.")
                return
            s = load_settings()
            s["max_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Макс. подписчиков: {new_value}", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Мин. подписчики
    if state == "waiting_min_subs":
        try:
            new_value = int(text)
            if new_value < 0:
                bot.send_message(chat_id, "❌ Число должно быть >= 0.")
                return
            s = load_settings()
            s["min_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Мин. подписчиков: {new_value}", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Мин. ER
    if state == "waiting_min_er":
        try:
            new_value = float(text)
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
                return
            s = load_settings()
            s["min_engagement_rate"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Мин. ER: {new_value}%", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Мин. рост
    if state == "waiting_min_growth":
        try:
            new_value = float(text)
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
                return
            s = load_settings()
            s["min_growth_rate"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Мин. рост: {new_value}%", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Макс. неактивность
    if state == "waiting_max_inactive":
        try:
            new_value = int(text)
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
                return
            s = load_settings()
            s["max_days_inactive"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Макс. неактивность: {new_value} дн", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Мин. скор для ТОПа
    if state == "waiting_min_score":
        try:
            new_value = int(text)
            if new_value < 0 or new_value > 100:
                bot.send_message(chat_id, "❌ Значение должно быть от 0 до 100.")
                return
            s = load_settings()
            s["min_score_for_top"] = new_value
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Мин. скор для ТОПа: {new_value}", reply_markup=admin_menu())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.")
        return
    
    # Если ничего не подошло
    bot.send_message(chat_id, "Используйте кнопки меню:", reply_markup=main_menu())

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 TELEGRAM БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👤 ID создателя: {ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 'Не задан'}")
    print(f"👥 Пользователей: {len(ALLOWED_USER_IDS)}")
    print(f"📌 Активные темы: {', '.join(SEARCH_TOPICS)}")
    print(f"👥 Мин. подписчиков: {MIN_SUBSCRIBERS}")
    print(f"👥 Макс. подписчиков: {MAX_SUBSCRIBERS}")
    print(f"📈 Мин. ER: {MIN_ENGAGEMENT_RATE}%")
    print("=" * 50)
    print("⏳ Ожидание команд...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(10)
