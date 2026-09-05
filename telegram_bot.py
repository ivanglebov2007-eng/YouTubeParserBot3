import time
import re
import json
import os
from datetime import datetime
from googleapiclient.discovery import build
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
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
CONTACTS_SHEET_NAME = "Контакты"

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

# ================= КЛАВИАТУРА =================
def main_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)
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
        KeyboardButton("🔄 Обновить таблицу")
    )
    keyboard.add(
        KeyboardButton("👑 Админ-панель"),
        KeyboardButton("❓ Помощь")
    )
    keyboard.add(
        KeyboardButton("💾 Сохранить настройки")
    )
    return keyboard

def admin_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)
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
        KeyboardButton("🔙 Назад")
    )
    return keyboard

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

# ================= ФОРМАТИРОВАНИЕ ТАБЛИЦ =================
def format_sheet(sheet):
    """Форматирует основную таблицу"""
    try:
        # Устанавливаем ширину колонок
        sheet.set_column_widths([
            ("A", "A", 300),
            ("B", "B", 350),
            ("C", "C", 120),
            ("D", "D", 150),
            ("E", "E", 350),
            ("F", "F", 120),
            ("G", "G", 120),
            ("H", "H", 150),
            ("I", "I", 150),
            ("J", "J", 100)
        ])
        
        # Форматируем заголовки
        sheet.format('A1:J1', {
            "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.6},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"
        })
        
        # Автоматическая подгонка высоты строк
        sheet.format('A1:J', {
            "wrapStrategy": "WRAP"
        })
        
    except Exception as e:
        logger.error(f"Ошибка форматирования основной таблицы: {e}")

def format_contacts_sheet(sheet):
    """Форматирует лист с контактами"""
    try:
        # Устанавливаем ширину колонок
        sheet.set_column_widths([
            ("A", "A", 300),
            ("B", "B", 350),
            ("C", "C", 250),
            ("D", "D", 200),
            ("E", "E", 200),
            ("F", "F", 100)
        ])
        
        # Форматируем заголовки
        sheet.format('A1:F1', {
            "backgroundColor": {"red": 0.1, "green": 0.6, "blue": 0.1},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"
        })
        
        # Автоматическая подгонка высоты строк
        sheet.format('A1:F', {
            "wrapStrategy": "WRAP"
        })
        
        # Подсвечиваем строки с email (зелёным фоном)
        all_data = sheet.get_all_values()
        for i in range(2, len(all_data) + 1):
            try:
                email = sheet.cell(i, 3).value
                if email:
                    sheet.format(f'A{i}:F{i}', {
                        "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.75}
                    })
            except:
                pass
        
    except Exception as e:
        logger.error(f"Ошибка форматирования листа контактов: {e}")

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
        main_sheet = workbook.add_worksheet(title=MAIN_SHEET_NAME, rows=1, cols=10)
        main_sheet.append_row([
            "Название канала", "Ссылка", "Подписчики", "Тема",
            "Найдено в видео", "ER (%)", "Дней неактивности",
            "Telegram", "VK", "Скор"
        ])
        format_sheet(main_sheet)
    
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
                ch.get("video_title", "")[:50],
                ch.get("engagement_rate", 0),
                ch.get("days_inactive", 999),
                contacts.get("telegram", ""),
                contacts.get("vk", ""),
                ch.get("score", 0)
            ])
    
    if new_rows:
        for row in new_rows:
            try:
                main_sheet.append_row(row)
            except:
                pass
        format_sheet(main_sheet)
    
    return new_rows

def update_contacts_sheet(workbook, channels_db):
    """Обновляет лист с контактами (без дубликатов)"""
    try:
        # Собираем все контакты из базы
        contacts_dict = {}
        for ch_id, data in channels_db.items():
            url = data.get("url", "")
            if not url:
                continue
            contacts = data.get("contacts", {})
            if url not in contacts_dict:
                contacts_dict[url] = {
                    "name": data.get("name", ""),
                    "url": url,
                    "email": contacts.get("email", ""),
                    "telegram": contacts.get("telegram", ""),
                    "vk": contacts.get("vk", ""),
                    "score": data.get("score", 0)
                }
            else:
                existing = contacts_dict[url]
                if contacts.get("email") and not existing["email"]:
                    existing["email"] = contacts["email"]
                if contacts.get("telegram") and not existing["telegram"]:
                    existing["telegram"] = contacts["telegram"]
                if contacts.get("vk") and not existing["vk"]:
                    existing["vk"] = contacts["vk"]
                if data.get("score", 0) > existing["score"]:
                    existing["score"] = data["score"]
        
        # Фильтруем каналы с контактами
        contacts_list = []
        for url, data in contacts_dict.items():
            has_contact = data["email"] or data["telegram"] or data["vk"]
            if has_contact and data["score"] >= MIN_SCORE_FOR_TOP:
                contacts_list.append(data)
        
        contacts_list.sort(key=lambda x: x["score"], reverse=True)
        
        # Создаём или очищаем лист
        try:
            contacts_sheet = workbook.worksheet(CONTACTS_SHEET_NAME)
            all_data = contacts_sheet.get_all_values()
            if len(all_data) > 1:
                contacts_sheet.delete_rows(2, len(all_data) - 1)
        except:
            contacts_sheet = workbook.add_worksheet(title=CONTACTS_SHEET_NAME, rows=1, cols=6)
            contacts_sheet.append_row([
                "Название канала", "Ссылка", "Email", "Telegram", "VK", "Скор"
            ])
        
        # Заполняем
        for ch in contacts_list:
            try:
                contacts_sheet.append_row([
                    ch["name"],
                    ch["url"],
                    ch["email"],
                    ch["telegram"],
                    ch["vk"],
                    ch["score"]
                ])
            except:
                pass
        
        # Форматируем
        format_contacts_sheet(contacts_sheet)
        
        return len(contacts_list)
        
    except Exception as e:
        logger.error(f"Ошибка обновления листа контактов: {e}")
        return 0

def update_sheet_with_analysis(workbook, channels_db):
    try:
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        
        headers = main_sheet.row_values(1)
        new_headers = [
            "Название канала", "Ссылка", "Подписчики", "Тема",
            "Найдено в видео", "ER (%)", "Дней неактивности",
            "Telegram", "VK", "Скор"
        ]
        
        if len(headers) < len(new_headers):
            main_sheet.append_row(new_headers)
            main_sheet.delete_row(1)
            main_sheet.append_row(new_headers)
            format_sheet(main_sheet)
        
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
                    main_sheet.update_cell(i, 5, data.get("video_title", "")[:50])
                    main_sheet.update_cell(i, 6, data.get("engagement_rate", 0))
                    main_sheet.update_cell(i, 7, data.get("days_inactive", 999))
                    main_sheet.update_cell(i, 8, contacts.get("telegram", ""))
                    main_sheet.update_cell(i, 9, contacts.get("vk", ""))
                    main_sheet.update_cell(i, 10, data.get("score", 0))
                except:
                    pass
                
                time.sleep(0.1)
        
        update_contacts_sheet(workbook, channels_db)
        format_sheet(main_sheet)
                
    except Exception as e:
        logger.error(f"Ошибка обновления таблицы: {e}")

def refresh_sheet(chat_id):
    """Полностью пересоздаёт таблицу из данных channels_db.json"""
    try:
        bot.send_message(chat_id, "🔄 Обновляю таблицу...", reply_markup=main_keyboard())
        
        workbook = get_workbook()
        if not workbook:
            bot.send_message(chat_id, "❌ Таблица не найдена!", reply_markup=main_keyboard())
            return
        
        channels_db = load_channels_db()
        
        if not channels_db:
            bot.send_message(chat_id, "⚠️ Нет данных для обновления. Сначала запустите парсер.", reply_markup=main_keyboard())
            return
        
        # ========== 1. ОБНОВЛЯЕМ ЛИСТ "БАЗА ДАННЫХ" ==========
        try:
            main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
            all_data = main_sheet.get_all_values()
            if len(all_data) > 1:
                main_sheet.delete_rows(2, len(all_data) - 1)
        except:
            main_sheet = workbook.add_worksheet(title=MAIN_SHEET_NAME, rows=1, cols=10)
            main_sheet.append_row([
                "Название канала", "Ссылка", "Подписчики", "Тема",
                "Найдено в видео", "ER (%)", "Дней неактивности",
                "Telegram", "VK", "Скор"
            ])
        
        # Собираем все уникальные каналы из базы
        all_channels = []
        seen_urls = set()
        for ch_id, data in channels_db.items():
            url = data.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                contacts = data.get("contacts", {})
                all_channels.append({
                    "name": data.get("name", ""),
                    "url": url,
                    "subscribers": data.get("subscribers", 0),
                    "topic": data.get("topic", ""),
                    "video_title": data.get("video_title", "")[:50],
                    "engagement_rate": data.get("engagement_rate", 0),
                    "days_inactive": data.get("days_inactive", 999),
                    "telegram": contacts.get("telegram", ""),
                    "vk": contacts.get("vk", ""),
                    "email": contacts.get("email", ""),
                    "score": data.get("score", 0)
                })
        
        # Сортируем по скору (по убыванию)
        all_channels.sort(key=lambda x: x["score"], reverse=True)
        
        # Заполняем таблицу
        for ch in all_channels:
            try:
                main_sheet.append_row([
                    ch["name"],
                    ch["url"],
                    ch["subscribers"],
                    ch["topic"],
                    ch["video_title"],
                    ch["engagement_rate"],
                    ch["days_inactive"],
                    ch["telegram"],
                    ch["vk"],
                    ch["score"]
                ])
            except Exception as e:
                logger.error(f"Ошибка добавления строки: {e}")
        
        # Применяем форматирование
        format_sheet(main_sheet)
        
        # ========== 2. ОБНОВЛЯЕМ ЛИСТ "КОНТАКТЫ" ==========
        # Собираем все контакты из всех каналов (без дубликатов по URL)
        contacts_dict = {}
        for ch in all_channels:
            url = ch["url"]
            if url not in contacts_dict:
                contacts_dict[url] = {
                    "name": ch["name"],
                    "url": url,
                    "email": ch.get("email", ""),
                    "telegram": ch.get("telegram", ""),
                    "vk": ch.get("vk", ""),
                    "score": ch.get("score", 0)
                }
            else:
                existing = contacts_dict[url]
                if ch.get("email") and not existing["email"]:
                    existing["email"] = ch["email"]
                if ch.get("telegram") and not existing["telegram"]:
                    existing["telegram"] = ch["telegram"]
                if ch.get("vk") and not existing["vk"]:
                    existing["vk"] = ch["vk"]
                if ch.get("score", 0) > existing["score"]:
                    existing["score"] = ch["score"]
        
        # Фильтруем только те, у которых есть хоть один контакт
        contacts_list = []
        for url, data in contacts_dict.items():
            has_contact = data["email"] or data["telegram"] or data["vk"]
            if has_contact and data["score"] >= MIN_SCORE_FOR_TOP:
                contacts_list.append(data)
        
        # Сортируем по скору
        contacts_list.sort(key=lambda x: x["score"], reverse=True)
        
        # Создаём или очищаем лист контактов
        try:
            contacts_sheet = workbook.worksheet(CONTACTS_SHEET_NAME)
            all_data = contacts_sheet.get_all_values()
            if len(all_data) > 1:
                contacts_sheet.delete_rows(2, len(all_data) - 1)
        except:
            contacts_sheet = workbook.add_worksheet(title=CONTACTS_SHEET_NAME, rows=1, cols=6)
            contacts_sheet.append_row([
                "Название канала", "Ссылка", "Email", "Telegram", "VK", "Скор"
            ])
        
        # Заполняем лист контактов
        for ch in contacts_list:
            try:
                contacts_sheet.append_row([
                    ch["name"],
                    ch["url"],
                    ch["email"],
                    ch["telegram"],
                    ch["vk"],
                    ch["score"]
                ])
            except Exception as e:
                logger.error(f"Ошибка добавления контакта: {e}")
        
        # Форматируем лист контактов
        format_contacts_sheet(contacts_sheet)
        
        msg = f"✅ **Таблица обновлена!**\n\n"
        msg += f"📊 Всего каналов: **{len(all_channels)}**\n"
        msg += f"📧 Каналов с контактами: **{len(contacts_list)}**\n\n"
        msg += f"📋 Лист «{MAIN_SHEET_NAME}» обновлён\n"
        msg += f"📋 Лист «{CONTACTS_SHEET_NAME}» обновлён\n\n"
        msg += f"🔗 {workbook.url}"
        
        bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=main_keyboard())
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка обновления: {str(e)}", reply_markup=main_keyboard())

# ================= ПРОВЕРКА ДОСТУПА =================
def is_admin(user_id):
    return user_id == ALLOWED_USER_IDS[0] if ALLOWED_USER_IDS else False

def is_user_allowed(user_id):
    return user_id in ALLOWED_USER_IDS

def check_access(message):
    user_id = message.from_user.id
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этому боту.", reply_markup=main_keyboard())
        return False
    return True

# ================= ОСНОВНЫЕ ФУНКЦИИ =================
def run_parser(chat_id):
    try:
        bot.send_message(chat_id, "🔍 Ищу каналы...", reply_markup=main_keyboard())
        
        workbook = get_workbook()
        if not workbook:
            bot.send_message(chat_id, "❌ Таблица не найдена!", reply_markup=main_keyboard())
            return
        
        all_channels = []
        for topic in SEARCH_TOPICS:
            bot.send_message(chat_id, f"🔍 Ищу: {topic}...", reply_markup=main_keyboard())
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
                bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=main_keyboard())
            else:
                bot.send_message(chat_id, "⚠️ Новых каналов не найдено.", reply_markup=main_keyboard())
        else:
            bot.send_message(chat_id, "❌ Каналы не найдены.", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())

def run_deep_analysis(chat_id):
    try:
        bot.send_message(chat_id, "🔍 Запускаю глубокий анализ...\n\nЭто может занять несколько минут.", reply_markup=main_keyboard())
        
        workbook = get_workbook()
        if not workbook:
            bot.send_message(chat_id, "❌ Таблица не найдена!", reply_markup=main_keyboard())
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        all_data = main_sheet.get_all_values()
        
        if len(all_data) <= 1:
            bot.send_message(chat_id, "⚠️ Нет каналов для анализа. Сначала запустите парсер.", reply_markup=main_keyboard())
            return
        
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
                "video_title": row[4] if len(row) > 4 else "",
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
                bot.send_message(chat_id, f"🔍 Проанализировано {analyzed} каналов...", reply_markup=main_keyboard())
            
            save_channels_db(channels_db)
            time.sleep(0.5)
        
        save_channels_db(channels_db)
        update_sheet_with_analysis(workbook, channels_db)
        
        msg = f"✅ **Глубокий анализ завершён!**\n\n"
        msg += f"📊 Проанализировано: **{analyzed}** каналов\n"
        msg += f"📧 Найдено контактов: **{found_contacts}**\n\n"
        msg += f"📋 В таблице создан отдельный лист **«Контакты»** с каналами, у которых есть контакты.\n\n"
        msg += f"🏆 Нажмите **ТОП кандидатов** для просмотра лучших вариантов."
        
        bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=main_keyboard())
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())

def show_top_candidates(chat_id):
    try:
        channels_db = load_channels_db()
        
        if not channels_db:
            bot.send_message(
                chat_id,
                "⚠️ Нет данных для анализа.\n\n"
                "Сначала запустите:\n"
                "1. 🚀 Парсер\n"
                "2. 🔍 Глубокий анализ",
                reply_markup=main_keyboard()
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
            bot.send_message(
                chat_id,
                "❌ Кандидатов не найдено.\n\n"
                f"Попробуйте снизить порог в настройках:\n"
                f"• Мин. скор: {MIN_SCORE_FOR_TOP}\n"
                f"• Мин. ER: {MIN_ENGAGEMENT_RATE}%\n"
                f"• Макс. неактивность: {MAX_DAYS_INACTIVE} дн",
                parse_mode='Markdown',
                reply_markup=main_keyboard()
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
        
        bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=main_keyboard())
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())

def check_vk_tg(chat_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.send_message(chat_id, "❌ Таблица не найдена!", reply_markup=main_keyboard())
            return
        
        main_sheet = workbook.worksheet(MAIN_SHEET_NAME)
        all_data = main_sheet.get_all_values()
        
        if len(all_data) <= 1:
            bot.send_message(chat_id, "⚠️ В таблице нет каналов.", reply_markup=main_keyboard())
            return
        
        bot.send_message(chat_id, "🔄 Проверяю ссылки VK и Telegram...", reply_markup=main_keyboard())
        
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
        
        update_contacts_sheet(workbook, channels_db)
        
        bot.send_message(
            chat_id,
            f"✅ Проверка завершена!\n\n📊 Обновлено ссылок: **{updated}**\n📋 Лист «Контакты» обновлён.",
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())

def show_status(chat_id):
    try:
        workbook = get_workbook()
        if not workbook:
            bot.send_message(chat_id, "❌ Таблица не найдена!", reply_markup=main_keyboard())
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
        
        bot.send_message(chat_id, msg, parse_mode='Markdown', reply_markup=main_keyboard())
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}", reply_markup=main_keyboard())

# ================= ОБРАБОТЧИКИ =================
@bot.message_handler(commands=['start'])
def handle_start(message):
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
        "📋 В таблице создаётся отдельный лист **«Контакты»** с каналами, у которых есть контакты.\n\n"
        "Выберите действие с помощью кнопок ниже:",
        parse_mode='Markdown',
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "❌ У вас нет доступа к этому боту.", reply_markup=main_keyboard())
        return
    
    # Состояния
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == "waiting_max_subs":
            try:
                new_value = int(text)
                if new_value <= 0:
                    bot.send_message(chat_id, "❌ Число должно быть > 0.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["max_subscribers"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Макс. подписчиков: {new_value}", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_min_subs":
            try:
                new_value = int(text)
                if new_value < 0:
                    bot.send_message(chat_id, "❌ Число должно быть >= 0.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["min_subscribers"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Мин. подписчиков: {new_value}", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_add_user":
            try:
                new_id = int(text)
                if new_id in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ ID {new_id} уже есть.", reply_markup=admin_keyboard())
                    return
                ALLOWED_USER_IDS.append(new_id)
                s = load_settings()
                s["allowed_users"] = ALLOWED_USER_IDS
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Пользователь {new_id} добавлен!", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_remove_user":
            try:
                remove_id = int(text)
                if remove_id == ALLOWED_USER_IDS[0]:
                    bot.send_message(chat_id, "❌ Нельзя удалить создателя.", reply_markup=admin_keyboard())
                    return
                if remove_id not in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ ID {remove_id} не найден.", reply_markup=admin_keyboard())
                    return
                ALLOWED_USER_IDS.remove(remove_id)
                s = load_settings()
                s["allowed_users"] = ALLOWED_USER_IDS
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Пользователь {remove_id} удалён!", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_add_topic":
            if text in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема '{text}' уже есть.", reply_markup=admin_keyboard())
                return
            SEARCH_TOPICS.append(text)
            s = load_settings()
            s["search_topics"] = SEARCH_TOPICS
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Тема '{text}' добавлена!", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_remove_topic":
            if text not in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема '{text}' не найдена.", reply_markup=admin_keyboard())
                return
            SEARCH_TOPICS.remove(text)
            s = load_settings()
            s["search_topics"] = SEARCH_TOPICS
            save_settings(s)
            update_global_settings()
            del user_states[user_id]
            bot.send_message(chat_id, f"✅ Тема '{text}' удалена!", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_min_er":
            try:
                new_value = float(text)
                if new_value < 0:
                    bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["min_engagement_rate"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Мин. ER: {new_value}%", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_min_growth":
            try:
                new_value = float(text)
                if new_value < 0:
                    bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["min_growth_rate"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Мин. рост: {new_value}%", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_max_inactive":
            try:
                new_value = int(text)
                if new_value < 0:
                    bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["max_days_inactive"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Макс. неактивность: {new_value} дн", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        if state == "waiting_min_score":
            try:
                new_value = int(text)
                if new_value < 0 or new_value > 100:
                    bot.send_message(chat_id, "❌ Значение должно быть от 0 до 100.", reply_markup=admin_keyboard())
                    return
                s = load_settings()
                s["min_score_for_top"] = new_value
                save_settings(s)
                update_global_settings()
                del user_states[user_id]
                bot.send_message(chat_id, f"✅ Мин. скор для ТОПа: {new_value}", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
            return
        
        del user_states[user_id]
        bot.send_message(chat_id, "⏳ Время ожидания истекло. Используйте кнопки.", reply_markup=main_keyboard())
        return
    
    # --- ОБРАБОТКА КНОПОК ---
    
    if text == "🔙 Назад":
        bot.send_message(chat_id, "👋 Главное меню:", reply_markup=main_keyboard())
        return
    
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
    
    if text == "🔄 Обновить таблицу":
        refresh_sheet(chat_id)
        return
    
    if text == "💾 Сохранить настройки":
        update_global_settings()
        bot.send_message(chat_id, "✅ Настройки синхронизированы и сохранены!", reply_markup=main_keyboard())
        return
    
    if text == "❓ Помощь":
        help_text = """
🤖 **Помощь**

**Основные функции:**

🚀 **Запустить парсер** — поиск новых каналов по темам

📊 **Глубокий анализ** — анализ ER, активности, поиск контактов

🏆 **ТОП кандидатов** — список лучших каналов для сотрудничества

🔄 **Проверить VK/TG** — обновление ссылок в таблице

🔄 **Обновить таблицу** — пересоздать таблицу из базы данных

👑 **Админ-панель** — управление настройками

📋 **В таблице Google Sheets**:
• Основной лист: все каналы с рейтингом
• Лист «Контакты»: только каналы с найденными контактами

**Как это работает:**
1. Запускаете парсер → бот ищет каналы
2. Делаете глубокий анализ → бот считает ER, находит контакты
3. Смотрите ТОП кандидатов → выбираете лучших
4. Пишете им вручную → сотрудничество!
        """
        bot.send_message(chat_id, help_text, parse_mode='Markdown', reply_markup=main_keyboard())
        return
    
    # --- АДМИН-ПАНЕЛЬ ---
    if text == "👑 Админ-панель":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        bot.send_message(
            chat_id,
            f"👑 **АДМИН-ПАНЕЛЬ**\n\n"
            f"📊 Настройки:\n"
            f"• Мин. подписчиков: `{MIN_SUBSCRIBERS}`\n"
            f"• Макс. подписчиков: `{MAX_SUBSCRIBERS}`\n"
            f"• Мин. ER: `{MIN_ENGAGEMENT_RATE}%`\n"
            f"• Мин. скор для ТОПа: `{MIN_SCORE_FOR_TOP}`\n\n"
            "Выберите раздел:",
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        return
    
    # --- НАСТРОЙКИ ---
    if text == "📋 Настройки":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        s = load_settings()
        text_msg = (
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
        bot.send_message(chat_id, text_msg, parse_mode='Markdown', reply_markup=admin_keyboard())
        return
    
    # --- ПОЛЬЗОВАТЕЛИ ---
    if text == "👥 Пользователи":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        text_msg = "👥 **Управление пользователями**\n\n"
        for i, uid in enumerate(ALLOWED_USER_IDS, 1):
            is_creator = "👑 " if i == 1 else ""
            text_msg += f"{i}. {is_creator}`{uid}`\n"
        text_msg += "\nВведите:\n• `add ID` — добавить пользователя\n• `remove ID` — удалить пользователя"
        bot.send_message(chat_id, text_msg, parse_mode='Markdown', reply_markup=admin_keyboard())
        return
    
    # --- ТЕМЫ ---
    if text == "📌 Темы поиска":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        text_msg = "📌 **Управление темами**\n\n"
        text_msg += f"Текущие темы:\n" + "\n".join([f"• {t}" for t in SEARCH_TOPICS])
        text_msg += "\n\nВведите:\n• `add тема` — добавить тему\n• `remove тема` — удалить тему"
        bot.send_message(chat_id, text_msg, parse_mode='Markdown', reply_markup=admin_keyboard())
        return
    
    # --- ЛИМИТ ПОДПИСЧИКОВ ---
    if text == "👤 Лимит подписчиков":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        bot.send_message(
            chat_id,
            f"👤 **Лимит подписчиков**\n\n"
            f"Текущий мин: `{MIN_SUBSCRIBERS}`\n"
            f"Текущий макс: `{MAX_SUBSCRIBERS}`\n\n"
            "Введите:\n• `max 100000` — установить максимум\n• `min 1000` — установить минимум",
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        return
    
    # --- ПАРАМЕТРЫ АНАЛИЗА ---
    if text == "📈 Параметры анализа":
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=main_keyboard())
            return
        bot.send_message(
            chat_id,
            f"📈 **Параметры анализа**\n\n"
            f"• Мин. ER: `{MIN_ENGAGEMENT_RATE}%`\n"
            f"• Мин. рост: `{MIN_GROWTH_RATE}%`\n"
            f"• Макс. неактивность: `{MAX_DAYS_INACTIVE}` дн\n"
            f"• Мин. скор для ТОПа: `{MIN_SCORE_FOR_TOP}`\n\n"
            "Введите:\n"
            "• `er 5` — мин. ER\n"
            "• `growth 10` — мин. рост\n"
            "• `inactive 14` — макс. неактивность\n"
            "• `score 70` — мин. скор для ТОПа",
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        return
    
    # --- КОМАНДЫ ЧЕРЕЗ ТЕКСТ ---
    if text.startswith("add "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        potential_topic = text.replace("add ", "").strip()
        if potential_topic.isdigit():
            try:
                new_id = int(potential_topic)
                if new_id in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ ID {new_id} уже есть.", reply_markup=admin_keyboard())
                    return
                ALLOWED_USER_IDS.append(new_id)
                s = load_settings()
                s["allowed_users"] = ALLOWED_USER_IDS
                save_settings(s)
                update_global_settings()
                bot.send_message(chat_id, f"✅ Пользователь {new_id} добавлен!", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID.", reply_markup=admin_keyboard())
        else:
            if potential_topic in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема '{potential_topic}' уже есть.", reply_markup=admin_keyboard())
                return
            SEARCH_TOPICS.append(potential_topic)
            s = load_settings()
            s["search_topics"] = SEARCH_TOPICS
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Тема '{potential_topic}' добавлена!", reply_markup=admin_keyboard())
        return
    
    if text.startswith("remove "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        potential = text.replace("remove ", "").strip()
        if potential.isdigit():
            try:
                remove_id = int(potential)
                if remove_id == ALLOWED_USER_IDS[0]:
                    bot.send_message(chat_id, "❌ Нельзя удалить создателя.", reply_markup=admin_keyboard())
                    return
                if remove_id not in ALLOWED_USER_IDS:
                    bot.send_message(chat_id, f"⚠️ ID {remove_id} не найден.", reply_markup=admin_keyboard())
                    return
                ALLOWED_USER_IDS.remove(remove_id)
                s = load_settings()
                s["allowed_users"] = ALLOWED_USER_IDS
                save_settings(s)
                update_global_settings()
                bot.send_message(chat_id, f"✅ Пользователь {remove_id} удалён!", reply_markup=admin_keyboard())
            except ValueError:
                bot.send_message(chat_id, "❌ Введите корректный ID.", reply_markup=admin_keyboard())
        else:
            if potential not in SEARCH_TOPICS:
                bot.send_message(chat_id, f"⚠️ Тема '{potential}' не найдена.", reply_markup=admin_keyboard())
                return
            SEARCH_TOPICS.remove(potential)
            s = load_settings()
            s["search_topics"] = SEARCH_TOPICS
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Тема '{potential}' удалена!", reply_markup=admin_keyboard())
        return
    
    if text.startswith("max "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = int(text.replace("max ", "").strip())
            if new_value <= 0:
                bot.send_message(chat_id, "❌ Число должно быть > 0.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["max_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Макс. подписчиков: {new_value}", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    if text.startswith("min "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = int(text.replace("min ", "").strip())
            if new_value < 0:
                bot.send_message(chat_id, "❌ Число должно быть >= 0.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["min_subscribers"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Мин. подписчиков: {new_value}", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    if text.startswith("er "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = float(text.replace("er ", "").strip())
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["min_engagement_rate"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Мин. ER: {new_value}%", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    if text.startswith("growth "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = float(text.replace("growth ", "").strip())
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["min_growth_rate"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Мин. рост: {new_value}%", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    if text.startswith("inactive "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = int(text.replace("inactive ", "").strip())
            if new_value < 0:
                bot.send_message(chat_id, "❌ Значение должно быть >= 0.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["max_days_inactive"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Макс. неактивность: {new_value} дн", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    if text.startswith("score "):
        if not is_admin(user_id):
            bot.send_message(chat_id, "❌ Только для создателя!", reply_markup=admin_keyboard())
            return
        try:
            new_value = int(text.replace("score ", "").strip())
            if new_value < 0 or new_value > 100:
                bot.send_message(chat_id, "❌ Значение должно быть от 0 до 100.", reply_markup=admin_keyboard())
                return
            s = load_settings()
            s["min_score_for_top"] = new_value
            save_settings(s)
            update_global_settings()
            bot.send_message(chat_id, f"✅ Мин. скор для ТОПа: {new_value}", reply_markup=admin_keyboard())
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректное число.", reply_markup=admin_keyboard())
        return
    
    # Если ничего не подошло
    bot.send_message(chat_id, "Используйте кнопки меню:", reply_markup=main_keyboard())

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
