import time
import re
import json
import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import logging

# ================= НАСТРОЙКИ =================
TELEGRAM_BOT_TOKEN = "8994730100:AAE6P65OqjVOTAftOIPZuBF70WAwzxz116A"
YOUTUBE_API_KEY = "AIzaSyAbAkrORDfJRoTfGn7nn0TSuP8tz_hFEb0"

MIN_ENGAGEMENT_RATE = 3.0
MIN_GROWTH_RATE = 5.0
MAX_DAYS_INACTIVE = 30
MIN_SCORE_FOR_TOP = 65

GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
SPREADSHEET_NAME = "YouTube Каналы RP (из видео)"

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

# ================= КЛАВИАТУРЫ (ТОЛЬКО REPLY) =================
def main_menu():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(
        KeyboardButton("🚀 Запустить парсер"),
        KeyboardButton("📊 Статистика")
    )
    keyboard.add(
        KeyboardButton("🔍 Глубокий анализ"),
        KeyboardButton("🏆 ТОП кандидатов")
    )
    keyboard.add(
        KeyboardButton("🔄 Проверить VK/TG"),
        KeyboardButton("👑 Админ-панель")
    )
    keyboard.add(
        KeyboardButton("💾 Сохранить настройки"),
        KeyboardButton("❓ Помощь")
    )
    return keyboard

def admin_menu():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(
        KeyboardButton("📋 Настройки"),
        KeyboardButton("👥 Пользователи")
    )
    keyboard.add(
        KeyboardButton("📌 Темы поиска"),
        KeyboardButton("👤 Лимит подписчиков")
    )
    keyboard.add(
        KeyboardButton("📈 Параметры анализа"),
        KeyboardButton("🔙 Главное меню")
    )
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

# ================= РАБОТА С GOOGLE SHEETS =================
def get_or_create_workbook():
    """Получает существующую таблицу или создаёт новую"""
    try:
        workbook = client.open(SPREADSHEET_NAME)
        return workbook
    except SpreadsheetNotFound:
        workbook = client.create(SPREADSHEET_NAME)
        workbook.insert_permission(
            value='',
            perm_type='anyone',
            role='reader'
        )
        return workbook

def create_new_sheet(workbook):
    """Создаёт новый лист с датой и временем"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H-%M")
    sheet_name = f"Отчёт {timestamp}"
    
    try:
        # Проверяем, есть ли уже такой лист
        sheet = workbook.worksheet(sheet_name)
        return sheet, sheet_name
    except WorksheetNotFound:
        # Создаём новый лист
        sheet = workbook.add_worksheet(title=sheet_name, rows=1, cols=10)
        headers = ["Название канала", "Ссылка", "Подписчики", "Тема", 
                   "ER (%)", "Дней неактивности", "Email", "Telegram", "VK", "Скор"]
        sheet.append_row(headers)
        return sheet, sheet_name

def format_sheet(sheet):
    """Форматирует лист"""
    try:
        sheet.format('A1:J1', {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.8},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
        })
        
        # Устанавливаем ширину колонок
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

def save_channels_to_sheet(sheet, channels):
    """Сохраняет каналы в лист"""
    for ch in channels:
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
            sheet.append_row(row)
        except Exception as e:
            logger.error(f"Ошибка добавления строки: {e}")

# ================= ОСНОВНЫЕ ФУНКЦИИ БОТА =================
def run_parser(chat_id):
    """Запускает поиск каналов и создаёт новый лист"""
    try:
        bot.send_message(chat_id, "📊 Создаю новый лист в таблице...")
        
        # Получаем таблицу
        workbook = get_or_create_workbook()
        
        # Создаём новый лист
        sheet, sheet_name = create_new_sheet(workbook)
        
        bot.send_message(chat_id, f"📝 Создан новый лист: {sheet_name}\n\n🔍 Ищу каналы...")
        
        all_channels = []
        
        for topic in SEARCH_TOPICS:
            bot.send_message(chat_id, f"🔍 Ищу: {topic}...")
            channels = search_channels_by_topic(topic, 15)
            
            if channels:
                # Анализируем каждый канал
                analyzed = []
                for ch in channels:
                    analyzed.append(analyze_channel_deep(ch))
                all_channels.extend(analyzed)
            
            time.sleep(1)
        
        if all_channels:
            # Сортируем по подписчикам
            all_channels.sort(key=lambda x: x.get("subscribers", 0), reverse=True)
            
            # Сохраняем в локальную БД
            db = load_channels_db()
            new_count = 0
            for ch in all_channels:
                ch_id = ch.get("channel_id")
                if ch_id and ch_id not in db:
                    db[ch_id] = ch
                    new_count += 1
            save_channels_db(db)
            
            # Сохраняем в Google Sheets
            save_channels_to_sheet(sheet, all_channels)
            
            # Форматируем
            format_sheet(sheet)
            
            # Ссылка на таблицу
            sheet_url = f"https://docs.google.com/spreadsheets/d/{workbook.id}"
            
            msg = f"✅ **Парсинг завершён!**\n\n"
            msg += f"📊 Найдено каналов: **{len(all_channels)}**\n"
            msg += f"🆕 Новых в БД: **{new_count}**\n"
            msg += f"📄 Лист: **{sheet_name}**\n\n"
            msg += f"🔗 {sheet_url}"
            
            bot.send_message(chat_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(
                chat_id,
                "❌ Каналы не найдены.\n\n"
                "Проверьте:\n"
                "• Настройки подписчиков\n"
                "• Темы поиска\n"
                "• Квоту YouTube API"
            )
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")

def run_deep_analysis(chat_id):
    """Глубокий анализ всех каналов в базе"""
    try:
        bot.send_message(chat_id, "🔍 Запускаю глубокий анализ...\n\nЭто может занять несколько минут.")
        
        db = load_channels_db()
        if not db:
            bot.send_message(chat_id, "⚠️ Нет каналов в базе. Сначала запустите парсер.")
            return
        
        total = len(db)
        analyzed = 0
        found_contacts = 0
        
        for ch_id, ch_data in db.items():
            if ch_data.get("analyzed"):
                continue
            
            analyzed_data = analyze_channel_deep(ch_data)
            db[ch_id] = analyzed_data
            analyzed += 1
            
            if analyzed_data.get("contacts", {}).get("email") or analyzed_data.get("contacts", {}).get("telegram"):
                found_contacts += 1
            
            if analyzed % 3 == 0:
                bot.send_message(chat_id, f"🔍 Проанализировано {analyzed} из {total} каналов...")
            
            save_channels_db(db)
            time.sleep(0.5)
        
        save_channels_db(db)
        
        msg = f"✅ **Глубокий анализ завершён!**\n\n"
        msg += f"📊 Проанализировано: **{analyzed}** каналов\n"
        msg += f"📧 Найдено контактов: **{found_contacts}**\n\n"
        msg += f"🏆 Нажмите **ТОП кандидатов** для просмотра лучших вариантов."
        
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")

def show_top_candidates(chat_id):
    """Показывает ТОП кандидатов"""
    try:
        db = load_channels_db()
        if not db:
            bot.send_message(chat_id, "⚠️ Нет данных. Сначала запустите парсер.")
            return
        
        candidates = []
        for ch_id, data in db.items():
            score = data.get("score", 0)
            er = data.get("engagement_rate", 0)
            days = data.get("days_inactive", 999)
            if score >= MIN_SCORE_FOR_TOP and er >= MIN_ENGAGEMENT_RATE and days <= MAX_DAYS_INACTIVE:
                candidates.append(data)
        
        if not candidates:
            bot.send_message(
                chat_id,
                f"❌ Кандидатов не найдено.\n\n"
                f"Попробуйте снизить порог:\n"
                f"• Мин. скор: {MIN_SCORE_FOR_TOP}\n"
                f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
                f"• Макс. неактивность: {MAX_DAYS_INACTIVE} дн"
            )
            return
        
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        msg = "🏆 **ТОП КАНДИДАТЫ**\n\n"
        
        for i, c in enumerate(candidates[:10], 1):
            contacts = c.get("contacts", {})
            msg += f"**{i}. {c.get('name', 'N/A')}**\n"
            msg += f"   📊 Скор: {c.get('score', 0)}/100\n"
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
            msg += f"\n... и ещё {len(candidates) - 10} кандидатов."
        msg += f"\n📋 Всего: **{len(candidates)}** каналов"
        
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")

def check_vk_tg(chat_id):
    """Перепроверяет ссылки VK и Telegram"""
    try:
        bot.send_message(chat_id, "🔄 Проверяю ссылки VK и Telegram...")
        
        db = load_channels_db()
        if not db:
            bot.send_message(chat_id, "⚠️ Нет каналов в базе.")
            return
        
        updated = 0
        for ch_id, data in db.items():
            description = data.get("description", "")
            contacts = extract_links(description)
            
            old_contacts = data.get("contacts", {})
            if contacts.get("vk") != old_contacts.get("vk") or contacts.get("telegram") != old_contacts.get("telegram"):
                data["contacts"] = contacts
                db[ch_id] = data
                updated += 1
        
        save_channels_db(db)
        bot.send_message(chat_id, f"✅ Проверка завершена!\n\n📊 Обновлено: **{updated}** каналов")
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")

def show_status(chat_id):
    """Показывает статистику"""
    try:
        db = load_channels_db()
        total = len(db)
        analyzed = len([c for c in db.values() if c.get("analyzed")])
        with_contacts = len([c for c in db.values() if c.get("contacts", {}).get("email") or c.get("contacts", {}).get("telegram")])
        
        msg = f"📊 **СТАТИСТИКА**\n\n"
        msg += f"📋 Всего каналов: **{total}**\n"
        msg += f"🔍 Проанализировано: **{analyzed}**\n"
        msg += f"📧 Найдено контактов: **{with_contacts}**\n\n"
        msg += f"📌 Активных тем: {len(SEARCH_TOPICS)}\n"
        msg += f"👤 Пользователей: {len(ALLOWED_USER_IDS)}\n\n"
        msg += f"⚙️ Параметры:\n"
        msg += f"• Мин. подписчиков: {MIN_SUBSCRIBERS}\n"
        msg += f"• Макс. подписчиков: {MAX_SUBSCRIBERS}\n"
        msg += f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
        msg += f"• Мин. скор: {MIN_SCORE_FOR_TOP}"
        
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")

# ================= АДМИН-ФУНКЦИИ =================
def show_settings(chat_id):
    s = load_settings()
    text = (
        "📊 **НАСТРОЙКИ**\n\n"
        f"👥 Пользователей: {len(s.get('allowed_users', []))}\n"
        f"📌 Темы: {', '.join(s.get('search_topics', []))}\n"
        f"👤 Мин. подписчиков: {s.get('min_subscribers', 100)}\n"
        f"👤 Макс. подписчиков: {s.get('max_subscribers', 50000)}\n"
        f"📈 Мин. ER: {s.get('min_engagement_rate', 3.0)}%\n"
        f"📊 Мин. рост: {s.get('min_growth_rate', 5.0)}%\n"
        f"⏰ Макс. неактивность: {s.get('max_days_inactive', 30)} дн\n"
        f"⭐ Мин. скор для ТОПа: {s.get('min_score_for_top', 65)}"
    )
    bot.send_message(chat_id, text, parse_mode='Markdown')

def list_users(chat_id):
    text = "👥 **Список пользователей**\n\n"
    for i, uid in enumerate(ALLOWED_USER_IDS, 1):
        is_creator = "👑 " if i == 1 else ""
        text += f"{i}. {is_creator}`{uid}`\n"
    bot.send_message(chat_id, text, parse_mode='Markdown')

def list_topics(chat_id):
    text = "📌 **Список тем**\n\n" + "\n".join([f"{i}. {t}" for i, t in enumerate(SEARCH_TOPICS, 1)])
    bot.send_message(chat_id, text)

# ================= ОБРАБОТЧИКИ КОМАНД =================
@bot.message_handler(commands=['start'])
def handle_start(message):
    if not check_access(message):
        return
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 **Партнёрский ассистент для YouTube**\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text
    
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "❌ У вас нет доступа.")
        return
    
    # ========== ГЛАВНОЕ МЕНЮ ==========
    if text == "🚀 Запустить парсер":
        run_parser(chat_id)
        return
    
    if text == "📊 Статистика":
        show_status(chat_id)
        return
    
    if text == "🔍 Глубокий анализ":
        run_deep_analysis(chat_id)
        return
    
    if text == "🏆 ТОП кандидатов":
        show_top_candidates(chat_id)
        return
    
    if text == "🔄 Проверить VK/TG":
        check_vk_tg(chat_id)
        return
    
    if text == "👑 Админ-панель":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        bot.send_message(chat_id, "👑 **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:", reply_markup=admin_menu())
        return
    
    if text == "💾 Сохранить настройки":
        update_global_settings()
        bot.send_message(chat_id, "✅ Настройки сохранены!", reply_markup=main_menu())
        return
    
    if text == "❓ Помощь":
        help_text = """
🤖 **Помощь**

🚀 **Запустить парсер** — поиск каналов + новый лист
📊 **Статистика** — текущие данные
🔍 **Глубокий анализ** — ER, контакты, скор
🏆 **ТОП кандидатов** — лучшие для сотрудничества
🔄 **Проверить VK/TG** — обновление ссылок
👑 **Админ-панель** — управление настройками

📌 Все данные сохраняются в локальную БД
📄 Каждый запуск создаёт новый лист в таблице
"""
        bot.send_message(chat_id, help_text, parse_mode='Markdown', reply_markup=main_menu())
        return
    
    if text == "🔙 Главное меню":
        bot.send_message(chat_id, "👋 Главное меню:", reply_markup=main_menu())
        return
    
    # ========== АДМИН-МЕНЮ ==========
    if text == "📋 Настройки":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        show_settings(chat_id)
        return
    
    if text == "👥 Пользователи":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        list_users(chat_id)
        bot.send_message(chat_id, "Используйте команды:\n/add_user [ID]\n/remove_user [ID]")
        return
    
    if text == "📌 Темы поиска":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        list_topics(chat_id)
        bot.send_message(chat_id, "Используйте команды:\n/add_topic [тема]\n/remove_topic [тема]")
        return    
    if text == "👤 Лимит подписчиков":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        bot.send_message(
            chat_id,
            f"Текущий мин: {MIN_SUBSCRIBERS}\n"
            f"Текущий макс: {MAX_SUBSCRIBERS}\n\n"
            "Используйте команды:\n/set_min_subs [число]\n/set_max_subs [число]"
        )
        return
    
    if text == "📈 Параметры анализа":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!")
            return
        bot.send_message(
            chat_id,
            f"📈 Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
            f"📊 Мин. рост: {MIN_GROWTH_RATE}%\n"
            f"⏰ Макс. неактивность: {MAX_DAYS_INACTIVE} дн\n"
            f"⭐ Мин. скор для ТОПа: {MIN_SCORE_FOR_TOP}\n\n"
            "Используйте команды:\n/set_min_er [число]\n/set_min_growth [число]\n/set_max_inactive [число]\n/set_min_score [число]"
        )
        return

# ================= ТЕКСТОВЫЕ КОМАНДЫ (АДМИНКА) =================
@bot.message_handler(commands=['add_user'])
def cmd_add_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /add_user [ID]")
            return
        
        new_id = int(parts[1])
        if new_id in ALLOWED_USER_IDS:
            bot.send_message(chat_id, f"⚠️ ID {new_id} уже есть.")
            return
        
        ALLOWED_USER_IDS.append(new_id)
        s = load_settings()
        s["allowed_users"] = ALLOWED_USER_IDS
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Пользователь {new_id} добавлен!")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректный ID.")

@bot.message_handler(commands=['remove_user'])
def cmd_remove_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /remove_user [ID]")
            return
        
        remove_id = int(parts[1])
        if remove_id == ALLOWED_USER_IDS[0]:
            bot.send_message(chat_id, "❌ Нельзя удалить создателя!")
            return
        if remove_id not in ALLOWED_USER_IDS:
            bot.send_message(chat_id, f"⚠️ ID {remove_id} не найден.")
            return
        
        ALLOWED_USER_IDS.remove(remove_id)
        s = load_settings()
        s["allowed_users"] = ALLOWED_USER_IDS
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Пользователь {remove_id} удалён!")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректный ID.")

@bot.message_handler(commands=['add_topic'])
def cmd_add_topic(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    topic = message.text.replace("/add_topic", "").strip()
    if not topic:
        bot.send_message(chat_id, "❌ Использование: /add_topic [тема]")
        return
    
    if topic in SEARCH_TOPICS:
        bot.send_message(chat_id, f"⚠️ Тема '{topic}' уже есть.")
        return
    
    SEARCH_TOPICS.append(topic)
    s = load_settings()
    s["search_topics"] = SEARCH_TOPICS
    save_settings(s)
    update_global_settings()
    bot.send_message(chat_id, f"✅ Тема '{topic}' добавлена!")

@bot.message_handler(commands=['remove_topic'])
def cmd_remove_topic(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    topic = message.text.replace("/remove_topic", "").strip()
    if not topic:
        bot.send_message(chat_id, "❌ Использование: /remove_topic [тема]")
        return
    
    if topic not in SEARCH_TOPICS:
        bot.send_message(chat_id, f"⚠️ Тема '{topic}' не найдена.")
        return
    
    SEARCH_TOPICS.remove(topic)
    s = load_settings()
    s["search_topics"] = SEARCH_TOPICS
    save_settings(s)
    update_global_settings()
    bot.send_message(chat_id, f"✅ Тема '{topic}' удалена!")

@bot.message_handler(commands=['set_max_subs'])
def cmd_set_max_subs(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_max_subs [число]")
            return
        
        new_value = int(parts[1])
        if new_value <= 0:
            bot.send_message(chat_id, "❌ Число должно быть > 0.")
            return
        
        s = load_settings()
        s["max_subscribers"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Макс. подписчиков: {new_value}")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

@bot.message_handler(commands=['set_min_subs'])
def cmd_set_min_subs(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_min_subs [число]")
            return
        
        new_value = int(parts[1])
        if new_value < 0:
            bot.send_message(chat_id, "❌ Число должно быть >= 0.")
            return
        
        s = load_settings()
        s["min_subscribers"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Мин. подписчиков: {new_value}")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

@bot.message_handler(commands=['set_min_er'])
def cmd_set_min_er(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_min_er [число]")
            return
        
        new_value = float(parts[1])
        if new_value < 0:
            bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
            return
        
        s = load_settings()
        s["min_engagement_rate"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Мин. ER: {new_value}%")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

@bot.message_handler(commands=['set_min_growth'])
def cmd_set_min_growth(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_min_growth [число]")
            return
        
        new_value = float(parts[1])
        if new_value < 0:
            bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
            return
        
        s = load_settings()
        s["min_growth_rate"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Мин. рост: {new_value}%")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

@bot.message_handler(commands=['set_max_inactive'])
def cmd_set_max_inactive(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_max_inactive [число]")
            return
        
        new_value = int(parts[1])
        if new_value < 0:
            bot.send_message(chat_id, "❌ Значение должно быть >= 0.")
            return
        
        s = load_settings()
        s["max_days_inactive"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Макс. неактивность: {new_value} дн")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

@bot.message_handler(commands=['set_min_score'])
def cmd_set_min_score(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        bot.send_message(chat_id, "❌ Только для создателя!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌ Использование: /set_min_score [число]")
            return
        
        new_value = int(parts[1])
        if new_value < 0 or new_value > 100:
            bot.send_message(chat_id, "❌ Значение должно быть от 0 до 100.")
            return
        
        s = load_settings()
        s["min_score_for_top"] = new_value
        save_settings(s)
        update_global_settings()
        bot.send_message(chat_id, f"✅ Мин. скор для ТОПа: {new_value}")
    except ValueError:
        bot.send_message(chat_id, "❌ Введите корректное число.")

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 TELEGRAM БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"👤 ID создателя: {ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else 'Не задан'}")
    print(f"👥 Пользователей: {len(ALLOWED_USER_IDS)}")
    print(f"📌 Темы: {', '.join(SEARCH_TOPICS)}")
    print(f"👥 Мин. подписчиков: {MIN_SUBSCRIBERS}")
    print(f"👥 Макс. подписчиков: {MAX_SUBSCRIBERS}")
    print("=" * 50)
    print("⏳ Ожидание команд...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(10)
