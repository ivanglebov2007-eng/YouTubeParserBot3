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

# Параметры фильтрации
MIN_ENGAGEMENT_RATE = 3.0
MIN_GROWTH_RATE = 5.0
MAX_DAYS_INACTIVE = 30
MIN_SCORE_FOR_TOP = 65

GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
MAIN_SHEET_NAME = "База данных"

SETTINGS_FILE = "bot_settings.json"
CHANNELS_DB_FILE = "data/channels_db.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS, scope)
client = gspread.authorize(creds)

user_states = {}

# ================= ЗАГРУЗКА/СОХРАНЕНИЕ =================
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

# ================= РАБОТА С YOUTUBE =================
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

def search_channels_by_topic(topic, max_results=15):
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
    links = {"vk": "", "telegram": "", "instagram": "", "twitter": "", "youtube": "", "tiktok": "", "email": "", "site": ""}
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
    if subs >= 100000: score += 25
    elif subs >= 50000: score += 22
    elif subs >= 10000: score += 18
    elif subs >= 5000: score += 14
    elif subs >= 1000: score += 10
    elif subs >= 500: score += 5
    else: score += 2
    
    er = calculate_engagement_rate(videos)
    if er >= 10: score += 25
    elif er >= 7: score += 20
    elif er >= 5: score += 15
    elif er >= 3: score += 10
    elif er >= 1: score += 5
    else: score += 0
    
    days = calculate_days_inactive(videos)
    if days <= 3: score += 20
    elif days <= 7: score += 15
    elif days <= 14: score += 10
    elif days <= 30: score += 5
    else: score += 0
    
    contacts = channel_data.get("contacts", {})
    if contacts.get("email"): score += 10
    if contacts.get("telegram"): score += 5
    if contacts.get("vk"): score += 3
    if contacts.get("instagram"): score += 2
    
    desc = channel_data.get("description", "")
    if len(desc) > 200: score += 5
    if "партнер" in desc.lower() or "сотрудничество" in desc.lower(): score += 5
    
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

# ================= СОЗДАНИЕ ПУБЛИЧНОЙ ТАБЛИЦЫ =================
def create_public_workbook(topic):
    """Создаёт новую публичную таблицу с отчётом"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M")
    sheet_name = f"YouTube Отчёт {topic} {timestamp}"
    
    try:
        workbook = client.create(sheet_name)
        
        # Делаем публичной (доступ по ссылке)
        workbook.insert_permission(
            value='',
            perm_type='anyone',
            role='reader'
        )
        
        # Создаём лист с данными
        main_sheet = workbook.add_worksheet(title="Каналы", rows=1, cols=10)
        headers = ["Название канала", "Ссылка", "Подписчики", "Тема", 
                   "ER (%)", "Дней неактивности", "Email", "Telegram", "VK", "Скор"]
        main_sheet.append_row(headers)
        
        return workbook, main_sheet
    except Exception as e:
        logger.error(f"Ошибка создания таблицы: {e}")
        return None, None

def format_public_sheet(sheet):
    """Форматирует публичную таблицу"""
    try:
        sheet.format('A1:J1', {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.8},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
        })
        
        sheet_id = sheet.id
        requests = []
        col_widths = [300, 350, 120, 150, 100, 120, 200, 150, 150, 80]
        for i, width in enumerate(col_widths, start=1):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": i - 1,
                        "endIndex": i
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize"
                }
            })
        
        if requests:
            sheet.spreadsheet.batch_update({"requests": requests})
            
    except Exception as e:
        logger.error(f"Ошибка форматирования: {e}")

# ================= РАБОТА С БАЗОЙ ДАННЫХ =================
def save_to_database(channels):
    """Сохраняет каналы в локальную базу данных"""
    db = load_channels_db()
    for ch in channels:
        channel_id = ch.get("channel_id")
        if channel_id:
            db[channel_id] = ch
    save_channels_db(db)
    return len(channels)

def get_all_channels_from_db():
    return load_channels_db()

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

# ================= ОСНОВНЫЕ ФУНКЦИИ БОТА =================
def run_parser(chat_id, message_id):
    """Запускает поиск каналов и создаёт публичные таблицы"""
    try:
        bot.edit_message_text("📊 Создаю новые публичные таблицы...", chat_id, message_id)
        
        all_channels = []
        table_links = []
        
        for topic in SEARCH_TOPICS:
            bot.edit_message_text(f"🔍 Ищу: {topic}...", chat_id, message_id)
            channels = search_channels_by_topic(topic, 15)
            
            if channels:
                # Анализируем каждый канал
                analyzed_channels = []
                for ch in channels:
                    analyzed = analyze_channel_deep(ch)
                    analyzed_channels.append(analyzed)
                
                all_channels.extend(analyzed_channels)
                
                # Создаём новую публичную таблицу
                workbook, main_sheet = create_public_workbook(topic)
                if workbook and main_sheet:
                    for ch in analyzed_channels:
                        try:
                            contacts = ch.get("contacts", {})
                            row = [
                                ch["name"],
                                ch["url"],
                                ch["subscribers"],
                                ch["topic"],
                                ch.get("engagement_rate", 0),
                                ch.get("days_inactive", 999),
                                contacts.get("email", ""),
                                contacts.get("telegram", ""),
                                contacts.get("vk", ""),
                                ch.get("score", 0)
                            ]
                            main_sheet.append_row(row)
                        except Exception as e:
                            logger.error(f"Ошибка добавления строки: {e}")
                    
                    # Форматируем
                    format_public_sheet(main_sheet)
                    
                    # Сохраняем ссылку
                    sheet_url = f"https://docs.google.com/spreadsheets/d/{workbook.id}"
                    table_links.append(f"📌 **{topic}**: {sheet_url}")
                    
                    # Отправляем ссылку сразу
                    bot.send_message(
                        chat_id,
                        f"📊 **Отчёт по теме: {topic}**\n\n"
                        f"📌 Найдено каналов: {len(analyzed_channels)}\n"
                        f"🔗 Ссылка для всех: {sheet_url}\n\n"
                        f"✅ Таблица публичная — доступна по ссылке!"
                    )
            
            time.sleep(1)
        
        # Сохраняем в локальную базу
        if all_channels:
            saved = save_to_database(all_channels)
            all_channels.sort(key=lambda x: x.get("subscribers", 0), reverse=True)
            
            bot.edit_message_text(
                f"✅ **Парсинг завершён!**\n\n"
                f"📊 Всего найдено: **{len(all_channels)}** каналов\n"
                f"📌 Создано таблиц: **{len(table_links)}**\n"
                f"💾 Сохранено в базу: **{saved}**\n\n"
                f"📋 Все таблицы публичные — доступны по ссылкам выше.",
                chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu()
            )
        else:
            bot.edit_message_text(
                "❌ Каналы не найдены.\n\n"
                "Проверьте:\n"
                "• Настройки подписчиков\n"
                "• Темы поиска\n"
                "• Квоту YouTube API",
                chat_id, message_id, reply_markup=main_menu()
            )
            
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def run_deep_analysis(chat_id, message_id):
    """Глубокий анализ всех каналов в базе"""
    try:
        bot.edit_message_text("🔍 Запускаю глубокий анализ...\n\nЭто может занять несколько минут.", chat_id, message_id)
        
        channels_db = load_channels_db()
        if not channels_db:
            bot.edit_message_text("⚠️ Нет каналов в базе. Сначала запустите парсер.", chat_id, message_id, reply_markup=main_menu())
            return
        
        analyzed = 0
        found_contacts = 0
        total = len(channels_db)
        
        for ch_id, ch_data in channels_db.items():
            if ch_data.get("analyzed"):
                continue
            
            analyzed_data = analyze_channel_deep(ch_data)
            channels_db[ch_id] = analyzed_data
            analyzed += 1
            
            if analyzed_data.get("contacts", {}).get("email") or analyzed_data.get("contacts", {}).get("telegram"):
                found_contacts += 1
            
            if analyzed % 3 == 0:
                bot.edit_message_text(f"🔍 Проанализировано {analyzed} из {total} каналов...", chat_id, message_id)
            
            save_channels_db(channels_db)
            time.sleep(0.5)
        
        save_channels_db(channels_db)
        
        msg = f"✅ **Глубокий анализ завершён!**\n\n"
        msg += f"📊 Проанализировано: **{analyzed}** каналов\n"
        msg += f"📧 Найдено контактов: **{found_contacts}**\n\n"
        msg += f"🏆 Нажмите **ТОП кандидатов** для просмотра лучших вариантов."
        
        bot.edit_message_text(msg, chat_id, message_id, parse_mode='Markdown', reply_markup=main_menu())
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def show_top_candidates(chat_id, message_id):
    """Показывает ТОП кандидатов для сотрудничества"""
    try:
        channels_db = load_channels_db()
        if not channels_db:
            bot.edit_message_text("⚠️ Нет данных для анализа. Сначала запустите парсер и глубокий анализ.", chat_id, message_id, reply_markup=main_menu())
            return
        
        candidates = []
        for ch_id, data in channels_db.items():
            score = data.get("score", 0)
            er = data.get("engagement_rate", 0)
            days = data.get("days_inactive", 999)
            if score >= MIN_SCORE_FOR_TOP and er >= MIN_ENGAGEMENT_RATE and days <= MAX_DAYS_INACTIVE:
                candidates.append(data)
        
        if not candidates:
            bot.edit_message_text(
                f"❌ Кандидатов не найдено.\n\n"
                f"Попробуйте снизить порог:\n"
                f"• Мин. скор: {MIN_SCORE_FOR_TOP}\n"
                f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
                f"• Макс. неактивность: {MAX_DAYS_INACTIVE} дн",
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
    """Перепроверяет ссылки VK и Telegram в базе"""
    try:
        bot.edit_message_text("🔄 Проверяю ссылки VK и Telegram...", chat_id, message_id)
        
        channels_db = load_channels_db()
        if not channels_db:
            bot.edit_message_text("⚠️ Нет каналов в базе.", chat_id, message_id, reply_markup=main_menu())
            return
        
        updated = 0
        for ch_id, data in channels_db.items():
            description = data.get("description", "")
            contacts = extract_links(description)
            
            old_contacts = data.get("contacts", {})
            if contacts.get("vk") != old_contacts.get("vk") or contacts.get("telegram") != old_contacts.get("telegram"):
                data["contacts"] = contacts
                channels_db[ch_id] = data
                updated += 1
        
        save_channels_db(channels_db)
        bot.edit_message_text(
            f"✅ Проверка завершена!\n\n"
            f"📊 Обновлено каналов: **{updated}**",
            chat_id, message_id, reply_markup=main_menu()
        )
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, message_id, reply_markup=main_menu())

def show_status(chat_id, message_id):
    """Показывает статистику"""
    try:
        channels_db = load_channels_db()
        total = len(channels_db)
        analyzed = len([c for c in channels_db.values() if c.get("analyzed")])
        with_contacts = len([c for c in channels_db.values() if c.get("contacts", {}).get("email") or c.get("contacts", {}).get("telegram")])
        
        msg = f"📊 **СТАТИСТИКА**\n\n"
        msg += f"📋 Всего каналов в базе: **{total}**\n"
        msg += f"🔍 Проанализировано: **{analyzed}**\n"
        msg += f"📧 Найдено контактов: **{with_contacts}**\n\n"
        msg += f"📌 Активных тем: **{len(SEARCH_TOPICS)}**\n"
        msg += f"👤 Пользователей: **{len(ALLOWED_USER_IDS)}**\n\n"
        msg += f"⚙️ Параметры отбора:\n"
        msg += f"• Мин. подписчиков: {MIN_SUBSCRIBERS}\n"
        msg += f"• Макс. подписчиков: {MAX_SUBSCRIBERS}\n"
        msg += f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
        msg += f"• Мин. скор для ТОПа: {MIN_SCORE_FOR_TOP}"
        
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
    
    if call.data == "back_main":
        bot.edit_message_text("👋 Главное меню:", chat_id, call.message.message_id, reply_markup=main_menu())
        bot.answer_callback_query(call.id)
        return
    
    if call.data == "back_admin":
        bot.edit_message_text("👑 **АДМИН-ПАНЕЛЬ**", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu())
        bot.answer_callback_query(call.id)
        return
    
    if call.data == "start_parser":
        bot.answer_callback_query(call.id, "🚀 Запускаю парсер...")
        run_parser(chat_id, call.message.message_id)
        return
    
    if call.data == "show_status":
        bot.answer_callback_query(call.id)
        show_status(chat_id, call.message.message_id)
        return
    
    if call.data == "deep_analysis":
        bot.answer_callback_query(call.id, "🔍 Запускаю глубокий анализ...")
        run_deep_analysis(chat_id, call.message.message_id)
        return
    
    if call.data == "show_top":
        bot.answer_callback_query(call.id)
        show_top_candidates(chat_id, call.message.message_id)
        return
    
    if call.data == "check_vk_tg":
        bot.answer_callback_query(call.id, "🔄 Проверяю...")
        check_vk_tg(chat_id, call.message.message_id)
        return
    
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
    
    if call.data == "save_settings":
        update_global_settings()
        bot.answer_callback_query(call.id, "✅ Настройки сохранены!")
        bot.edit_message_text("✅ Настройки синхронизированы и сохранены!", chat_id, call.message.message_id, reply_markup=main_menu())
        return
    
    if call.data == "show_help":
        bot.answer_callback_query(call.id)
        help_text = """
🤖 **Помощь**

🚀 **Запустить парсер** — поиск каналов + создание публичных таблиц
📊 **Статистика** — текущие данные
🔍 **Глубокий анализ** — ER, контакты, скор
🏆 **ТОП кандидатов** — лучшие для сотрудничества
🔄 **Проверить VK/TG** — обновление ссылок
👑 **Админ-панель** — управление настройками

📌 Все таблицы создаются с публичным доступом!
"""
        bot.edit_message_text(help_text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=main_menu())
        return
    
    # ========== АДМИН-КОМАНДЫ ==========
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
    
    if call.data == "users_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"👥 **Управление пользователями**\n\nВсего: {len(ALLOWED_USER_IDS)}", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=users_menu())
        return
    
    if call.data == "add_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text("✏️ Введите ID пользователя:\n\nПример: `123456789`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_add_user"
        return
    
    if call.data == "remove_user":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"✏️ Введите ID пользователя для удаления\n\n⚠️ Нельзя удалить создателя: `{ALLOWED_USER_IDS[0]}`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button()
        )
        user_states[user_id] = "waiting_remove_user"
        return
    
    if call.data == "list_users":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        text = "📋 **Список пользователей**\n\n" + "\n".join([f"{i}. {'👑 ' if i == 1 else ''}`{uid}`" for i, uid in enumerate(ALLOWED_USER_IDS, 1)])
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=users_menu())
        return
    
    if call.data == "topics_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"📌 **Управление темами**\n\nТемы: {', '.join(SEARCH_TOPICS)}", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=topics_menu())
        return
    
    if call.data == "add_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text("✏️ Введите новую тему:\n\nПример: `GTA 5 RP`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_add_topic"
        return
    
    if call.data == "remove_topic":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"✏️ Введите тему для удаления\n\nТекущие темы:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS]),
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
    
    if call.data == "subs_menu":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"👤 **Лимит подписчиков**\n\n"
            f"Текущий мин: `{MIN_SUBSCRIBERS}`\n"
            f"Текущий макс: `{MAX_SUBSCRIBERS}`",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=subs_menu()
        )
        return
    
    if call.data == "set_max_subs":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text("✏️ Введите новое значение МАКС. подписчиков:\n\nПример: `100000`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_max_subs"
        return
    
    if call.data == "set_min_subs":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text("✏️ Введите новое значение МИН. подписчиков:\n\nПример: `1000`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_min_subs"
        return
    
    if call.data.startswith("set_subs_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        value_str = call.data.replace("set_subs_", "")
        if value_str == "custom":
            bot.answer_callback_query(call.id)
            bot.edit_message_text("✏️ Введите новое значение МАКС. подписчиков:\n\nПример: `100000`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
            user_states[user_id] = "waiting_max_subs"
            return
        try:
            new_value = int(value_str)
            s = load_settings()
            s["max_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            bot.answer_callback_query(call.id, f"✅ Установлено: {new_value}")
            bot.edit_message_text(f"✅ Макс. подписчиков: `{new_value}`", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_menu())
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка!", show_alert=True)
        return
    
    if call.data == "analysis_settings":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📈 **НАСТРОЙКИ АНАЛИЗА**\n\n"
            "Выберите параметр для изменения:",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=analysis_settings_menu()
        )
        return
    
    if call.data == "set_min_er":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"✏️ Введите минимальный ER (%)\n\nТекущее: {MIN_ENGAGEMENT_RATE}%", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_min_er"
        return
    
    if call.data == "set_min_growth":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"✏️ Введите минимальный рост (%)\n\nТекущее: {MIN_GROWTH_RATE}%", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_min_growth"
        return
    
    if call.data == "set_max_inactive":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"✏️ Введите макс. дней без видео\n\nТекущее: {MAX_DAYS_INACTIVE} дн", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_max_inactive"
        return
    
    if call.data == "set_min_score":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Только для создателя!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(f"✏️ Введите мин. скор для ТОПа\n\nТекущее: {MIN_SCORE_FOR_TOP}", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=cancel_button())
        user_states[user_id] = "waiting_min_score"
        return
    
    if call.data == "cancel":
        if user_id in user_states:
            del user_states[user_id]
        bot.answer_callback_query(call.id, "❌ Отменено")
        bot.edit_message_text("✅ Действие отменено.", chat_id, call.message.message_id, reply_markup=admin_menu())
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
    
    bot.send_message(chat_id, "Используйте кнопки меню:", reply_markup=main_menu())

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 TELEGRAM БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👤 ID создателя: {ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 'Не задан'}")
    print(f"👥 Пользователей: {len(ALLOWED_USER_IDS)}")
    print(f"📌 Активные темы: {', '.join(SEARCH_TOPICS)}")
    print(f"📊 Создаёт публичные таблицы с отчётами!")
    print("=" * 50)
    print("⏳ Ожидание команд...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(10)
