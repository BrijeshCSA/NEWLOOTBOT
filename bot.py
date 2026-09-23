import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import sqlite3
import time
import datetime
import random
import logging
import sys
import os
import re

TOKEN = 'vk1.a.hczRCAHcJ503htmFIydw0l5Vu32Zcgsca5MvCAg03PU5qWteDUi-jO3a_NWYnGrRk0gKmOji3-bEK5qfp_dlnOTvuErLO2h9ImG8MgxfH84Msr_ZQFfOv8_M9jijfCG8mUUz9dgqLmKiCHEtnPX2Slsf6zHqEoyphYeqaiV0ddaUZ7A4lIl9YfsFmVadZY645o7mk_aUvK_dYFihF3PVTQ'
CREATOR_ID = 1085788257
BOT_GROUP_ID = 241262855

MAT_WORDS = ['блять', 'сука', 'хуй', 'пизда', 'ебать', 'еблан', 'мудак', 'говно', 'залупа', 'член', 'шлюха', 'блядь', 'пидор', 'гандон', 'мразь']

MODER_ROLES = ['agent', 'moder', 'senior_moder', 'zgm', 'head_moder', 'manager', 'zrm', 'head_of_moderation', 'head_admin', 'helper', 'head_watcher', 'watcher', 'junior_watcher']
ROLE_NAMES = {
    'user': 'Участник', 'agent': 'Агент поддержки', 'moder': 'Модератор',
    'senior_moder': 'Старший модератор', 'zgm': 'ЗГМ', 'head_moder': 'Главный модератор',
    'manager': 'Менеджер', 'zrm': 'ЗРМ', 'head_of_moderation': 'Руководитель модерации',
    'admin': 'Администратор', 'tech': 'Тех. специалист', 'dev': 'Разработчик',
    'youtuber': 'Ютубер', 'owner': 'Владелец', 'deputy': 'Зам.владельца',
    'head_admin': 'Главный Админ', 'helper': 'Хелпер', 'head_watcher': 'Гл.Смотрящий',
    'watcher': 'Смотрящий', 'junior_watcher': 'Мл.Смотрящий', 'sponsor': 'Спонсор',
    'premium': 'Премиум пользователь'
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler('bot.log', encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

conn = sqlite3.connect('lutbot.db', check_same_thread=False)
cursor = conn.cursor()

def ensure_column(table, column, col_type):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    if column not in cols:
        if 'CURRENT_TIMESTAMP' in col_type:
            col_type = col_type.replace('DEFAULT CURRENT_TIMESTAMP', "DEFAULT ''")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()

def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 500, passport INTEGER DEFAULT 0,
        card INTEGER DEFAULT 0, bank_worker INTEGER DEFAULT 0, rank INTEGER DEFAULT 0,
        bank_level INTEGER DEFAULT 0, experience INTEGER DEFAULT 0, house TEXT DEFAULT NULL,
        car TEXT DEFAULT NULL, company TEXT DEFAULT NULL, family INTEGER DEFAULT 0,
        last_daily TEXT, last_work TEXT, spam_balance REAL DEFAULT 0, mute_until TEXT,
        role TEXT DEFAULT 'user', credit_amount REAL DEFAULT 0, credit_due TEXT,
        vip INTEGER DEFAULT 0, promocodes_used TEXT DEFAULT '',
        tt_channel TEXT DEFAULT NULL, tt_subscribers INTEGER DEFAULT 0, tt_verified INTEGER DEFAULT 0,
        tt_videos INTEGER DEFAULT 0, tt_likes INTEGER DEFAULT 0, last_tt_film TEXT,
        level INTEGER DEFAULT 1, reputation INTEGER DEFAULT 0, clan TEXT DEFAULT NULL,
        registration_date TEXT DEFAULT '', hidden_from_top INTEGER DEFAULT 0,
        limited_items TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS bans (user_id INTEGER PRIMARY KEY, reason TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS mutes (user_id INTEGER PRIMARY KEY, until TEXT, reason TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_stats (user_id INTEGER PRIMARY KEY, messages_count INTEGER DEFAULT 0, mat_count INTEGER DEFAULT 0, photo_count INTEGER DEFAULT 0, voice_count INTEGER DEFAULT 0, video_count INTEGER DEFAULT 0, last_message_time TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward REAL, vip INTEGER DEFAULT 0, created_by INTEGER, used_by TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS offers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_quests (user_id INTEGER, quest_id INTEGER, progress INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0, PRIMARY KEY (user_id, quest_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS wipe_info (id INTEGER PRIMARY KEY, last_wipe TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS limited_items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_by INTEGER, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_roles (
        role_key TEXT PRIMARY KEY, role_name TEXT, priority INTEGER DEFAULT 0,
        created_by INTEGER, timestamp TEXT)''')
    conn.commit()
    for col, col_type in [
        ('credit_amount','REAL DEFAULT 0'), ('credit_due','TEXT'), ('last_work','TEXT'),
        ('vip','INTEGER DEFAULT 0'), ('promocodes_used',"TEXT DEFAULT ''"),
        ('tt_channel','TEXT'), ('tt_subscribers','INTEGER DEFAULT 0'), ('tt_verified','INTEGER DEFAULT 0'),
        ('tt_videos','INTEGER DEFAULT 0'), ('tt_likes','INTEGER DEFAULT 0'), ('last_tt_film','TEXT'),
        ('level','INTEGER DEFAULT 1'), ('reputation','INTEGER DEFAULT 0'), ('clan','TEXT'),
        ('registration_date',"TEXT DEFAULT ''"), ('hidden_from_top','INTEGER DEFAULT 0'),
        ('limited_items',"TEXT DEFAULT ''")]:
        ensure_column('users', col, col_type)
    conn.commit()

init_db()

def load_custom_roles():
    cursor.execute('SELECT role_key, role_name FROM custom_roles')
    for role_key, role_name in cursor.fetchall():
        ROLE_NAMES[role_key] = role_name

load_custom_roles()

def get_all_roles():
    builtin = {
        'user': ('Участник', 0),
        'premium': ('Премиум пользователь', 5),
        'sponsor': ('Спонсор', 10),
        'youtuber': ('Ютубер', 15),
        'junior_watcher': ('Мл.Смотрящий', 20),
        'watcher': ('Смотрящий', 25),
        'head_watcher': ('Гл.Смотрящий', 30),
        'helper': ('Хелпер', 35),
        'agent': ('Агент поддержки', 40),
        'moder': ('Модератор', 45),
        'senior_moder': ('Старший модератор', 50),
        'zgm': ('ЗГМ', 55),
        'head_moder': ('Главный модератор', 60),
        'manager': ('Менеджер', 65),
        'zrm': ('ЗРМ', 70),
        'head_of_moderation': ('Руководитель модерации', 75),
        'head_admin': ('Главный Админ', 80),
        'admin': ('Администратор', 85),
        'tech': ('Тех. специалист', 88),
        'dev': ('Разработчик', 90),
        'deputy': ('Зам.владельца', 95),
        'owner': ('Владелец', 100),
    }
    cursor.execute('SELECT role_key, role_name, priority FROM custom_roles')
    for role_key, role_name, priority in cursor.fetchall():
        builtin[role_key] = (role_name, priority)
    return builtindef generate_houses():
    types = ["Квартира", "Дом", "Вилла", "Пентхаус", "Таунхаус", "Коттедж", "Особняк", "Усадьба", "Апартаменты", "Шале"]
    levels = ["Эконом", "Стандарт", "Комфорт", "Бизнес", "Премиум", "Люкс", "Элит", "Делюкс", "Эксклюзив", "Королевский"]
    extras = ["Остров", "Планета", "Вселенная", "Галактика", "Мультивселенная"]
    houses = {}
    house_id = 1
    for e in extras:
        for l in levels[:5]:
            houses[f"{e} {l} [ID: {house_id}]"] = 50000 + house_id * 5000
            house_id += 1
    for t in types:
        for l in levels:
            houses[f"{t} {l} [ID: {house_id}]"] = 1000 + house_id * 500
            house_id += 1
    return houses

def generate_cars():
    brands = ["Lada", "Kia", "Toyota", "BMW", "Mercedes", "Audi", "Ford", "Hyundai", "Volkswagen", "Porsche"]
    models = ["Базовая", "Комфорт", "Бизнес", "Премиум", "Люкс", "Спорт", "Эксклюзив", "Лимед", "Гранд", "Королевская"]
    extras = ["Космолёт", "Звездолёт", "Телепорт", "Киберкар", "Флаер"]
    cars = {}
    car_id = 1
    for e in extras:
        for m in models[:5]:
            cars[f"{e} {m} [ID: {car_id}]"] = 20000 + car_id * 2000
            car_id += 1
    for b in brands:
        for m in models:
            cars[f"{b} {m} [ID: {car_id}]"] = 500 + car_id * 100
            car_id += 1
    return cars

def generate_companies():
    sectors = ["Ларёк", "Магазин", "Кафе", "Автосервис", "Салон красоты", "Фитнес-клуб", "Ресторан", "Отель", "Завод", "Корпорация"]
    scales = ["Малый", "Средний", "Крупный", "Сетевой", "Региональный", "Федеральный", "Международный", "Глобальный", "Транснациональный", "Мега"]
    extras = ["Банк", "Космопорт", "Звездная империя", "Галактический холдинг", "Мультивселенная корпорация"]
    companies = {}
    comp_id = 1
    for e in extras:
        for s in scales[:5]:
            companies[f"{e} {s} [ID: {comp_id}]"] = 50000 + comp_id * 5000
            comp_id += 1
    for s in sectors:
        for sc in scales:
            companies[f"{s} {sc} [ID: {comp_id}]"] = 2000 + comp_id * 200
            comp_id += 1
    return companies

HOUSES = generate_houses()
CARS = generate_cars()
COMPANIES = generate_companies()

QUESTS = [
    {'id': 1, 'desc': 'Выполните работу 3 раза', 'type': 'work', 'target': 3, 'reward_money': 100, 'reward_exp': 50},
    {'id': 2, 'desc': 'Выполните фриланс 5 раз', 'type': 'freelance', 'target': 5, 'reward_money': 150, 'reward_exp': 70},
    {'id': 3, 'desc': 'Сыграйте в казино 3 раза', 'type': 'casino', 'target': 3, 'reward_money': 200, 'reward_exp': 80},
    {'id': 4, 'desc': 'Откройте 2 контейнера', 'type': 'container', 'target': 2, 'reward_money': 300, 'reward_exp': 100},
    {'id': 5, 'desc': 'Получите ежедневный бонус 2 раза', 'type': 'daily', 'target': 2, 'reward_money': 250, 'reward_exp': 90},
    {'id': 6, 'desc': 'Напишите 20 сообщений', 'type': 'message', 'target': 20, 'reward_money': 100, 'reward_exp': 50},
]

def find_item_by_id(items_dict, item_id):
    for name, price in items_dict.items():
        if f"[ID: {item_id}]" in name:
            return name, price
    return None, None

def get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        cursor.execute('UPDATE users SET registration_date = ? WHERE user_id = ?', (datetime.datetime.now().isoformat(), user_id))
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
    columns = [desc[0] for desc in cursor.description]
    user_dict = dict(zip(columns, row))
    if not user_dict.get('registration_date'):
        cursor.execute('UPDATE users SET registration_date = ? WHERE user_id = ?', (datetime.datetime.now().isoformat(), user_id))
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        user_dict = dict(zip(columns, row))
    return user_dict

def update_user(user_id, **kwargs):
    fields = ', '.join([f'{key} = ?' for key in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    cursor.execute(f'UPDATE users SET {fields} WHERE user_id = ?', values)
    conn.commit()

def get_stats(user_id):
    cursor.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO user_stats (user_id) VALUES (?)', (user_id,))
        conn.commit()
        cursor.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))

def update_stats(user_id, text='', attachments=None):
    stats = get_stats(user_id)
    messages_count = stats['messages_count'] + 1
    mat_count = stats['mat_count']
    photo_count = stats['photo_count']
    voice_count = stats['voice_count']
    video_count = stats['video_count']
    lower_text = text.lower() if text else ''
    for word in MAT_WORDS:
        if word in lower_text:
            mat_count += 1
            break
    if attachments and isinstance(attachments, list):
        for att in attachments:
            if isinstance(att, dict):
                att_type = att.get('type', '')
                if att_type == 'photo': photo_count += 1
                elif att_type == 'voice': voice_count += 1
                elif att_type == 'video': video_count += 1
    cursor.execute('''UPDATE user_stats SET messages_count = ?, mat_count = ?, photo_count = ?, voice_count = ?, video_count = ?, last_message_time = ? WHERE user_id = ?''',
                   (messages_count, mat_count, photo_count, voice_count, video_count, datetime.datetime.now().isoformat(), user_id))
    conn.commit()
    update_quest_progress(user_id, 'message')

def update_quest_progress(user_id, quest_type, amount=1):
    for quest in QUESTS:
        if quest['type'] == quest_type:
            cursor.execute('SELECT progress, claimed FROM user_quests WHERE user_id = ? AND quest_id = ?', (user_id, quest['id']))
            row = cursor.fetchone()
            if row is None:
                cursor.execute('INSERT INTO user_quests (user_id, quest_id, progress, claimed) VALUES (?, ?, ?, 0)', (user_id, quest['id'], amount))
            else:
                if row[1] == 0:
                    cursor.execute('UPDATE user_quests SET progress = progress + ? WHERE user_id = ? AND quest_id = ?', (amount, user_id, quest['id']))
    conn.commit()

def is_muted(user_id):
    user = get_user(user_id)
    if user.get('mute_until'):
        mute_until = datetime.datetime.fromisoformat(user['mute_until'])
        if datetime.datetime.now() < mute_until: return True
    return False

def check_ban(user_id):
    cursor.execute('SELECT * FROM bans WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def get_user_name(user_id):
    try:
        info = vk.users.get(user_ids=user_id)
        if info: return f"{info[0].get('first_name','')} {info[0].get('last_name','')}".strip()
    except: pass
    return f"id{user_id}"

def send_message(peer_id, text):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=get_random_id())
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

def parse_amount(text):
    try: return float(text.strip())
    except: return None

def extract_id_from_mention(text):
    if not text: return None
    match = re.search(r'\[id(\d+)\|', text)
    if match: return int(match.group(1))
    match = re.search(r'@id(\d+)', text)
    if match: return int(match.group(1))
    if text.isdigit(): return int(text)
    return None

def get_last_seen(user_id):
    try:
        info = vk.users.get(user_ids=user_id, fields='last_seen')
        if info and info[0].get('last_seen'):
            return datetime.datetime.fromtimestamp(info[0]['last_seen']['time']).strftime('%d.%m.%Y %H:%M:%S')
        return 'скрыт'
    except: return 'ошибка'

def is_admin(user_id):
    user = get_user(user_id)
    return user_id == CREATOR_ID or user.get('role') in ['admin', 'owner', 'deputy']

def is_owner(user_id):
    return user_id == CREATOR_ID or get_user(user_id).get('role') in ['owner', 'deputy']

def is_moder(user_id):
    role = get_user(user_id).get('role')
    if is_admin(user_id):
        return True
    if role in MODER_ROLES:
        return True
    all_roles = get_all_roles()
    if role in all_roles and all_roles[role][1] >= 40:
        return True
    return False

def is_youtuber(user_id):
    user = get_user(user_id)
    return user.get('role') in ['youtuber', 'owner', 'deputy', 'admin', 'dev']

def check_credit(user_id):
    user = get_user(user_id)
    if user.get('credit_amount', 0) > 0 and user.get('credit_due'):
        due = datetime.datetime.fromisoformat(user['credit_due'])
        if datetime.datetime.now() > due:
            cursor.execute('INSERT OR REPLACE INTO bans (user_id, reason, timestamp) VALUES (?, ?, ?)', (user_id, 'Долг!', datetime.datetime.now().isoformat()))
            conn.commit()
            update_user(user_id, credit_amount=0, credit_due=None)
            return False
    return Truedef cmd_help(user_id, peer_id):
    text = (
        "📋 КОМАНДЫ УЧАСТНИКОВ:\n"
        "/профиль — профиль\n/паспорт — паспорт\n/карта — карта\n"
        "/работа_да — устроиться в банк\n/работа_нет — отказаться\n/работа — работать (24ч)\n"
        "/ранг — ранг\n/улучшить_банк — улучшить банк\n/кредит [сумма] [дней] — кредит\n/погасить_кредит — погасить\n"
        "/фриланс — фриланс\n/казино [ставка] — казино\n/бонус — бонус\n"
        "/купить_дом — дома\n/купить_машину — машины\n/купить_бизнес — бизнесы\n"
        "/кейс — кейс (100₽)\n/обмен — обмен\n/топ — топ\n"
        "/подписка — подписка\n/купить_вип — купить VIP (1000₽)\n"
        "/промокод [код] — промокод\n/промолист — список промокодов\n/идея [текст] — идея\n"
        "/жалоба [текст] — жалоба/вопрос\n"
        "/ид — ID\n/стата — статистика\n/зов — @all\n/онлайн — кто в сети\n/состав — персонал\n"
        "/задания — список заданий\n/получить [id] — забрать награду задания\n"
        "/вайп — информация о вайпе"
    )
    send_message(peer_id, text)

def cmd_mhelp(user_id, peer_id):
    text = "🛡 КОМАНДЫ МОДЕРАЦИИ:\n/мут [id] [минуты]\n/размут [id]\n/пред [id] [причина]\n/бан [id] [причина]\n/разбан [id]\n/жалобы — список жалоб\n/ответ [номер] — ответить на жалобу (агент)"
    send_message(peer_id, text)

def cmd_thelp(user_id, peer_id):
    text = (
        "📺 КОМАНДЫ ЮТУБЕРОВ:\n"
        "/тт_статистика — статистика канала\n"
        "/тт_снять — снять видео (30 мин)\n"
        "/тт_название [название] — создать канал\n"
        "/тт_подписка [название канала] — подписаться на канал\n"
        "/тт_verify — верификация (1000 подписчиков)\n"
        "/тт_выдать_подписчиков [id] [кол-во] — владелец\n"
        "/тт_установить_лайки [id] [номер] [кол-во] — владелец\n"
        "/создать_промокод [код] [награда] — создать промокод"
    )
    send_message(peer_id, text)

def cmd_ahelp(user_id, peer_id):
    text = (
        "👑 КОМАНДЫ АДМИНОВ:\n"
        "/выдать [id] [сумма] — выдать деньги\n"
        "/выдать_спасибо [id] [сумма] — выдать ЛутКоины\n"
        "/снять [id] [сумма]\n"
        "/выдать_роль [id] [роль]\n"
        "/выдать_ранг [id] [ранг]\n"
        "/рассылка [текст]\n"
        "/скрыть_из_топа [id]\n"
        "/newrole [ключ] [название] [приоритет 0-100] — создать кастомную роль"
    )
    send_message(peer_id, text)

def cmd_dhelp(user_id, peer_id):
    text = (
        "💻 КОМАНДЫ РАЗРАБОТЧИКОВ И ВЛАДЕЛЬЦА:\n"
        "/eval [код] — Python код\n/sql [запрос] — SQL\n/логи — логи\n"
        "/tell [текст] — рассылка подписчикам\n/тех [текст] — тех. работы\n"
        "/идеи — идеи\n/создать_промокод [код] [награда] — создать промокод\n"
        "/тт_выдать_подписчиков [id] [кол-во] — владелец\n/тт_установить_лайки [id] [номер] [кол-во]\n"
        "/тт_статистика — статистика\n/тт_снять — снять видео (30 мин)\n/тт_название [название]\n/тт_подписка [название канала]\n/тт_verify — верификация\n"
        "/вайпс — ручной вайп (создатель)\n/лимитка [название] — создать лимитированный предмет\n/выдать_лимитку [id] [название] — выдать лимитку\n/инвентарь — список лимиток"
    )
    send_message(peer_id, text)

def cmd_ghelp(user_id, peer_id):
    text = (
        "📚 ВСЕ КОМАНДЫ ЛутБот:\n\n"
        "👤 Участники:\n"
        "/профиль — профиль\n/паспорт — паспорт\n/карта — карта\n"
        "/работа_да — работа\n/работа_нет — отказ\n/работа — работать\n"
        "/ранг — ранг\n/улучшить_банк — улучшить банк\n"
        "/кредит — кредит\n/погасить_кредит — погасить\n"
        "/фриланс — фриланс\n/казино — казино\n/бонус — бонус\n"
        "/купить_дом — дома\n/купить_машину — машины\n/купить_бизнес — бизнесы\n"
        "/кейс — кейс\n/обмен — обмен\n/топ — топ\n"
        "/подписка — подписка\n/купить_вип — VIP\n/промокод — промокод\n/промолист — список промокодов\n"
        "/идея — идея\n/жалоба — жалоба\n/ид — ID\n/стата — статистика\n"
        "/зов — @all\n/онлайн — онлайн\n/состав — персонал\n"
        "/задания — задания\n/получить — забрать награду\n/вайп — инфо о вайпе\n\n"
        "🛡 Модерация:\n/мут\n/размут\n/пред\n/бан\n/разбан\n/жалобы\n/ответ\n\n"
        "🔧 Тех. специалисты:\n/рестарт\n/статус\n/бэкап\n/тех\n\n"
        "👑 Админы:\n/выдать\n/выдать_спасибо\n/снять\n/выдать_роль\n/выдать_ранг\n/рассылка\n/скрыть_из_топа\n/newrole\n\n"
        "💻 Разработчики:\n/eval\n/sql\n/логи\n/tell\n/идеи\n/создать_промокод\n/вайпс\n/лимитка\n/выдать_лимитку\n/инвентарь\n\n"
        "📺 Ютуберы:\n/тт_статистика\n/тт_снять\n/тт_название\n/тт_подписка\n/тт_verify\n"
        "/тт_выдать_подписчиков (владелец)\n/тт_установить_лайки (владелец)\n/тт_топ — топ ютуберов"
    )
    send_message(peer_id, text)

def cmd_newrole(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 3:
        send_message(peer_id, "Использование: /newrole [ключ] [название] [приоритет 0-100]\n"
                               "Пример: /newrole vip2 VIP-Клиент 50")
        return
    role_key = args[0].lower().strip()
    try:
        priority = int(args[-1])
    except ValueError:
        send_message(peer_id, "Приоритет должен быть числом от 0 до 100.")
        return
    if priority < 0 or priority > 100:
        send_message(peer_id, "Приоритет должен быть от 0 до 100.")
        return
    role_name = ' '.join(args[1:-1]).strip()
    if not role_name:
        send_message(peer_id, "Укажите название роли.")
        return
    if not re.match(r'^[a-z0-9_]+$', role_key):
        send_message(peer_id, "Ключ роли может содержать только латиницу, цифры и _.")
        return
    if role_key in ['user', 'owner', 'deputy', 'admin', 'dev', 'tech']:
        send_message(peer_id, "Этот ключ зарезервирован.")
        return
    cursor.execute('INSERT OR REPLACE INTO custom_roles (role_key, role_name, priority, created_by, timestamp) VALUES (?, ?, ?, ?, ?)',
                   (role_key, role_name, priority, user_id, datetime.datetime.now().isoformat()))
    conn.commit()
    ROLE_NAMES[role_key] = role_name
    send_message(peer_id, f"✅ Роль «{role_name}» создана.\nКлюч: {role_key}\nПриоритет: {priority}")

def get_rank_name(rank):
    ranks = ["Стажёр", "Специалист", "Менеджер", "Зам. директора", "Директор"]
    return ranks[rank] if 0 <= rank < len(ranks) else "Неизвестно"def cmd_profil(user_id, peer_id):
    user = get_user(user_id)
    credit_info = f"{user.get('credit_amount',0):.2f}₽" if user.get('credit_amount',0) > 0 else "нет"
    tt_verified = "✅" if user.get('tt_verified', 0) else "❌"
    level = user.get('level', 1)
    exp = user.get('experience', 0)
    clan = user.get('clan') or "нет"
    reg_date = user.get('registration_date', '')[:19]

    text = (
        f"[Фото]\nhttps://vk.ru/photo-221392393_458134449\n"
        f"🏠Профиль: {get_user_name(user_id)} (ID: {user_id})\n"
        f"🪪Паспорт: {'✅' if user['passport'] else '❌'}\n"
        f"💰Баланс: {user['balance']:.2f}₽\n"
        f"💳Карта: {'✅' if user['card'] else '❌'}\n"
        f"🪙ЛутКоины: {user['spam_balance']:.2f}\n"
        f"💪Уровень: {level} ({exp}/100)\n"
        f"😘Репутация: {user.get('reputation', 0)}\n"
        f"🏦Должность в Банке: {get_rank_name(user['rank']) if user['bank_worker'] else 'Нет'}\n\n"
        f"СЕМЬИ\n"
        f"🍜Клан: {clan}\n\n"
        f"МАШИНА/ДОМ\n"
        f"🚗Машина: {user['car'] or 'нет'}\n"
        f"🏡Дом: {user['house'] or 'нет'}\n\n"
        f"БИЗНЕС\n"
        f"🏆Доход с бизнесов: {COMPANIES.get(user['company'], 0)//100 if user['company'] else 0}₽/день\n"
        f"6️⃣7️⃣Бизнес: {user['company'] or 'нет'}\n\n"
        f"ТИКТОК\n"
        f"📱TikTok: {user.get('tt_channel') or 'нет'}\n"
        f"🎙️подписчиков: {user.get('tt_subscribers', 0)}\n"
        f"📺видео: {user.get('tt_videos', 0)}\n"
        f"👍лайки: {user.get('tt_likes', 0)}\n"
        f"🆚Verify: {tt_verified}\n\n"
        f"👀Дата регистрации: {reg_date}"
    )
    send_message(peer_id, text)

def cmd_passport(user_id, peer_id):
    user = get_user(user_id)
    if user.get('passport'):
        send_message(peer_id, "У вас уже есть паспорт!")
        return
    update_user(user_id, passport=1)
    send_message(peer_id, "📕 Вы получили паспорт!")

def cmd_register_card(user_id, peer_id):
    user = get_user(user_id)
    if not user.get('passport'):
        send_message(peer_id, "Сначала паспорт: /паспорт")
        return
    if user.get('card'):
        send_message(peer_id, "Карта уже есть!")
        return
    update_user(user_id, card=1)
    send_message(peer_id, "💳 Карта зарегистрирована!")

def cmd_work_yes(user_id, peer_id):
    user = get_user(user_id)
    if not user.get('card'):
        send_message(peer_id, "Сначала карта: /карта")
        return
    if user.get('bank_worker'):
        send_message(peer_id, "Вы уже работаете!")
        return
    update_user(user_id, bank_worker=1, rank=0)
    send_message(peer_id, "🏦 Вы устроились в банк!")

def cmd_work_no(user_id, peer_id):
    user = get_user(user_id)
    if user.get('bank_worker'):
        send_message(peer_id, "Вы уже работаете!")
        return
    send_message(peer_id, "Вы отказались.")

def cmd_work(user_id, peer_id):
    user = get_user(user_id)
    if not user.get('bank_worker'):
        send_message(peer_id, "Вы не работаете. /работа_да")
        return
    last_work = user.get('last_work')
    if last_work:
        last_dt = datetime.datetime.fromisoformat(last_work)
        if (datetime.datetime.now() - last_dt).total_seconds() < 86400:
            remaining = 86400 - (datetime.datetime.now() - last_dt).total_seconds()
            send_message(peer_id, f"Следующая смена через {int(remaining//3600)}ч {int((remaining%3600)//60)}мин.")
            return
    salary = 100 + user['rank'] * 50 + user['bank_level'] * 20
    if user.get('vip', 0): salary *= 2
    new_exp = user.get('experience', 0) + 10
    new_level = user.get('level', 1)
    if new_exp >= 100:
        new_level += 1
        new_exp = 0
        update_user(user_id, level=new_level, experience=new_exp)
    else:
        update_user(user_id, experience=new_exp)
    update_user(user_id, balance=user['balance'] + salary, last_work=datetime.datetime.now().isoformat())
    update_quest_progress(user_id, 'work')
    send_message(peer_id, f"💼 Вы заработали {salary}₽!")

def cmd_rank(user_id, peer_id):
    user = get_user(user_id)
    if not user.get('bank_worker'):
        send_message(peer_id, "Вы не работаете.")
        return
    send_message(peer_id, f"Ранг: {get_rank_name(user['rank'])}")

def cmd_upgrade_bank(user_id, peer_id):
    user = get_user(user_id)
    if not user.get('bank_worker'):
        send_message(peer_id, "Вы не работаете.")
        return
    cost = (user['bank_level'] + 1) * 1000
    if user['balance'] < cost:
        send_message(peer_id, f"Нужно {cost}₽")
        return
    update_user(user_id, bank_level=user['bank_level']+1, balance=user['balance']-cost)
    send_message(peer_id, f"🏦 Банк улучшен!")

def cmd_credit(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('credit_amount', 0) > 0:
        send_message(peer_id, "Уже есть кредит!")
        return
    if len(args) < 2:
        send_message(peer_id, "/кредит [сумма] [дней]")
        return
    amount = parse_amount(args[0])
    days = int(args[1]) if args[1].isdigit() else 0
    if not amount or days <= 0 or amount > 100000:
        send_message(peer_id, "Неверные параметры. Макс 100000₽")
        return
    due = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    update_user(user_id, balance=user['balance']+amount, credit_amount=amount, credit_due=due)
    send_message(peer_id, f"🏦 Кредит {amount}₽ на {days} дней.")

def cmd_pay_credit(user_id, peer_id):
    user = get_user(user_id)
    if user.get('credit_amount', 0) <= 0:
        send_message(peer_id, "Нет кредита.")
        return
    if user['balance'] < user['credit_amount']:
        send_message(peer_id, f"Нужно {user['credit_amount']:.2f}₽")
        return
    update_user(user_id, balance=user['balance']-user['credit_amount'], credit_amount=0, credit_due=None)
    send_message(peer_id, "✅ Кредит погашен!")

def cmd_freelance(user_id, peer_id):
    if is_muted(user_id):
        send_message(peer_id, "Вы в муте!")
        return
    user = get_user(user_id)
    earnings = random.randint(50, 200)
    if user.get('vip', 0): earnings *= 2
    update_user(user_id, balance=user['balance']+earnings)
    update_quest_progress(user_id, 'freelance')
    send_message(peer_id, f"💻 Фриланс: +{earnings}₽")

def cmd_casino(user_id, peer_id, args):
    if is_muted(user_id):
        send_message(peer_id, "Вы в муте!")
        return
    user = get_user(user_id)
    if len(args) < 1:
        send_message(peer_id, "/казино [ставка]")
        return
    bet = parse_amount(args[0])
    if not bet or bet < 50:
        send_message(peer_id, "Мин. 50₽")
        return
    if user['balance'] < bet:
        send_message(peer_id, "Недостаточно денег.")
        return
    if random.random() < 0.45:
        base_win = bet * 2
        bonus = base_win * 0.20 if user.get('vip', 0) else 0
        total_win = base_win + bonus
        net_profit = total_win - bet
        update_user(user_id, balance=user['balance'] + net_profit)
        text = (
            f"🎰 Вы сыграли на ставку «{bet:.0f}₽»\n"
            f"Результат: 🎉\n"
            f"Статус: ✅ ВЫИГРЫШ\n\n"
            f"💵 Базовый выигрыш: {base_win:.0f}₽\n"
            f"📈 Бонус к выигрышу: {bonus:.0f}₽\n"
            f"💰 Итого выигрыш: {total_win:.0f}₽ (чистая прибыль: {net_profit:.0f}₽)"
        )
    else:
        update_user(user_id, balance=user['balance'] - bet)
        text = (
            f"🎰 Вы сыграли на ставку «{bet:.0f}₽»\n"
            f"Результат: 😞\n"
            f"Статус: ❌ Проигрыш\n\n"
            f"💵 Базовый выигрыш: 0₽\n"
            f"📈 Бонус к выигрышу: 0₽\n"
            f"💰 Итого выигрыш: 0₽ (чистая прибыль: -{bet:.0f}₽)"
        )
    update_quest_progress(user_id, 'casino')
    send_message(peer_id, text)def cmd_buy_house(user_id, peer_id):
    user = get_user(user_id)
    if user.get('house'):
        send_message(peer_id, "Уже есть дом!")
        return
    text = "🏠 Дома (ID для покупки):\n"
    for i, (name, price) in enumerate(list(HOUSES.items())[:30], 1):
        text += f"{name} — {price}₽\n"
    text += "...\n/купить_дом [ID]"
    send_message(peer_id, text)

def cmd_buy_house_name(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('house'):
        send_message(peer_id, "Уже есть дом!")
        return
    try:
        item_id = int(args[0])
        name, price = find_item_by_id(HOUSES, item_id)
        if not name:
            send_message(peer_id, "Нет такого ID.")
            return
        if user['balance'] < price:
            send_message(peer_id, f"Нужно {price}₽")
            return
        update_user(user_id, house=name, balance=user['balance']-price)
        send_message(peer_id, f"🏠 Куплен дом: {name} за {price}₽")
    except:
        send_message(peer_id, "Используйте ID: /купить_дом [ID]")

def cmd_buy_car(user_id, peer_id):
    user = get_user(user_id)
    if user.get('car'):
        send_message(peer_id, "Уже есть машина!")
        return
    text = "🚗 Машины (ID для покупки):\n"
    for i, (name, price) in enumerate(list(CARS.items())[:30], 1):
        text += f"{name} — {price}₽\n"
    text += "...\n/купить_машину [ID]"
    send_message(peer_id, text)

def cmd_buy_car_name(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('car'):
        send_message(peer_id, "Уже есть машина!")
        return
    try:
        item_id = int(args[0])
        name, price = find_item_by_id(CARS, item_id)
        if not name:
            send_message(peer_id, "Нет такого ID.")
            return
        if user['balance'] < price:
            send_message(peer_id, f"Нужно {price}₽")
            return
        update_user(user_id, car=name, balance=user['balance']-price)
        send_message(peer_id, f"🚗 Куплена машина: {name} за {price}₽")
    except:
        send_message(peer_id, "Используйте ID: /купить_машину [ID]")

def cmd_buy_company(user_id, peer_id):
    user = get_user(user_id)
    if user.get('company'):
        send_message(peer_id, "Уже есть бизнес!")
        return
    text = "🏢 Бизнесы (ID для покупки):\n"
    for i, (name, price) in enumerate(list(COMPANIES.items())[:30], 1):
        text += f"{name} — {price}₽\n"
    text += "...\n/купить_бизнес [ID]"
    send_message(peer_id, text)

def cmd_buy_company_name(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('company'):
        send_message(peer_id, "Уже есть бизнес!")
        return
    try:
        item_id = int(args[0])
        name, price = find_item_by_id(COMPANIES, item_id)
        if not name:
            send_message(peer_id, "Нет такого ID.")
            return
        if user['balance'] < price:
            send_message(peer_id, f"Нужно {price}₽")
            return
        update_user(user_id, company=name, balance=user['balance']-price)
        send_message(peer_id, f"🏢 Куплен бизнес: {name} за {price}₽")
    except:
        send_message(peer_id, "Используйте ID: /купить_бизнес [ID]")

def cmd_daily(user_id, peer_id):
    user = get_user(user_id)
    now = datetime.datetime.now()
    last = user.get('last_daily')
    if last:
        last_dt = datetime.datetime.fromisoformat(last)
        if (now - last_dt).total_seconds() < 86400:
            remaining = 86400 - (now - last_dt).total_seconds()
            send_message(peer_id, f"Бонус через {int(remaining//3600)}ч {int((remaining%3600)//60)}мин.")
            return
    base = 100
    if user.get('house'): base += 50
    if user.get('car'): base += 30
    if user.get('company'): base += 100
    if user.get('vip', 0): base *= 2
    update_user(user_id, balance=user['balance']+base, last_daily=now.isoformat())
    update_quest_progress(user_id, 'daily')
    send_message(peer_id, f"🎁 Бонус: {base}₽")

def cmd_top(user_id, peer_id):
    cursor.execute('SELECT user_id, balance FROM users WHERE hidden_from_top = 0 ORDER BY balance DESC LIMIT 10')
    rows = cursor.fetchall()
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text = "🏆 ТОП-10:\n"
    for i, (uid, bal) in enumerate(rows, 1):
        text += f"{medals[i-1]} {get_user_name(uid)} — {bal:.2f}₽\n"
    send_message(peer_id, text)

def cmd_container(user_id, peer_id):
    user = get_user(user_id)
    if user['balance'] < 100:
        send_message(peer_id, "Нужно 100₽")
        return
    update_user(user_id, balance=user['balance']-100)
    prizes = [("money", random.randint(50,1000)), ("spasibo", random.randint(10,200)),
              ("house", random.choice(list(HOUSES.keys()))), ("car", random.choice(list(CARS.keys()))),
              ("company", random.choice(list(COMPANIES.keys()))), ("nothing", 0)]
    prize_type, value = random.choice(prizes)
    if prize_type == "money":
        update_user(user_id, balance=get_user(user_id)['balance']+value)
        text = f"🎁 +{value}₽!"
    elif prize_type == "spasibo":
        update_user(user_id, spam_balance=get_user(user_id)['spam_balance']+value)
        text = f"🎁 +{value} ЛутКоинов!"
    elif prize_type == "house":
        if not get_user(user_id).get('house'):
            update_user(user_id, house=value)
            text = f"🎁 Дом: {value}!"
        else:
            update_user(user_id, balance=get_user(user_id)['balance']+500)
            text = "🎁 +500₽"
    elif prize_type == "car":
        if not get_user(user_id).get('car'):
            update_user(user_id, car=value)
            text = f"🎁 Машина: {value}!"
        else:
            update_user(user_id, balance=get_user(user_id)['balance']+300)
            text = "🎁 +300₽"
    elif prize_type == "company":
        if not get_user(user_id).get('company'):
            update_user(user_id, company=value)
            text = f"🎁 Бизнес: {value}!"
        else:
            update_user(user_id, balance=get_user(user_id)['balance']+1000)
            text = "🎁 +1000₽"
    else:
        text = "🎁 Ничего."
    update_quest_progress(user_id, 'container')
    send_message(peer_id, text)

def cmd_convert_spasibo(user_id, peer_id):
    user = get_user(user_id)
    if user['spam_balance'] <= 0:
        send_message(peer_id, "Нет ЛутКоинов.")
        return
    rub = user['spam_balance'] * 0.5
    update_user(user_id, balance=user['balance']+rub, spam_balance=0)
    send_message(peer_id, f"💱 Обмен: {rub:.2f}₽")

def cmd_setpromo(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') not in ['youtuber', 'admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав. Только для ютуберов!")
        return
    if len(args) < 2:
        send_message(peer_id, "/создать_промокод [код] [награда]")
        return
    code = args[0].upper()
    reward = parse_amount(args[1])
    if not reward or reward <= 0:
        send_message(peer_id, "Неверная награда.")
        return
    if user['balance'] < reward:
        send_message(peer_id, "❌ Недостаточно денег на вашем балансе для создания промокода.")
        return
    update_user(user_id, balance=user['balance'] - reward)
    cursor.execute('INSERT OR REPLACE INTO promocodes (code, reward, vip, created_by, used_by) VALUES (?, ?, 0, ?, "")', (code, reward, user_id))
    conn.commit()
    send_message(peer_id, f"✅ Промокод {code} создан с наградой {reward}₽.")

def cmd_promo(user_id, peer_id, args):
    if len(args) < 1:
        send_message(peer_id, "/промокод [код]")
        return
    code = args[0].upper()
    cursor.execute('SELECT * FROM promocodes WHERE code = ?', (code,))
    promo = cursor.fetchone()
    if not promo:
        send_message(peer_id, "❌ Промокод не найден.")
        return
    if promo[4] != '':
        send_message(peer_id, "❌ Промокод уже использован.")
        return
    user = get_user(user_id)
    used_codes = user.get('promocodes_used', '')
    if code in used_codes:
        send_message(peer_id, "Вы уже использовали этот промокод!")
        return
    reward = promo[1]
    update_user(user_id, balance=user['balance']+reward, promocodes_used=used_codes + ',' + code)
    cursor.execute('UPDATE promocodes SET used_by = ? WHERE code = ?', (str(user_id), code))
    conn.commit()
    send_message(peer_id, f"🎉 Промокод активирован! +{reward}₽")

def cmd_promolist(user_id, peer_id):
    cursor.execute('SELECT code, reward FROM promocodes WHERE used_by = ""')
    rows = cursor.fetchall()
    if not rows:
        send_message(peer_id, "Нет активных промокодов.")
        return
    text = "🎟 Активные промокоды:\n"
    for code, reward in rows:
        text += f"• {code} — {reward}₽\n"
    send_message(peer_id, text)

def cmd_subscribe(user_id, peer_id):
    user = get_user(user_id)
    if user.get('vip', 0):
        send_message(peer_id, "У вас уже есть VIP!")
        return
    try:
        member = vk.groups.isMember(group_id=BOT_GROUP_ID, user_id=user_id)
        if member:
            update_user(user_id, vip=1, balance=user['balance']+500)
            send_message(peer_id, "✅ Спасибо за подписку! Вы получили VIP и 500₽!")
        else:
            send_message(peer_id, "❌ Вы не подписаны на сообщество.")
    except:
        send_message(peer_id, "Ошибка проверки подписки.")

def cmd_buy_vip(user_id, peer_id):
    user = get_user(user_id)
    if user.get('vip', 0):
        send_message(peer_id, "У вас уже есть VIP!")
        return
    cost = 1000
    if user['balance'] < cost:
        send_message(peer_id, f"Нужно {cost}₽")
        return
    update_user(user_id, balance=user['balance']-cost, vip=1)
    send_message(peer_id, "✅ VIP куплен!")

def cmd_offer(user_id, peer_id, args):
    if len(args) < 1:
        send_message(peer_id, "/идея [текст идеи]")
        return
    text = ' '.join(args)
    cursor.execute('INSERT INTO offers (user_id, text, timestamp) VALUES (?, ?, ?)', (user_id, text, datetime.datetime.now().isoformat()))
    conn.commit()
    send_message(peer_id, "✅ Идея отправлена разработчикам!")

def cmd_offers(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    cursor.execute('SELECT * FROM offers ORDER BY id DESC LIMIT 10')
    rows = cursor.fetchall()
    if not rows:
        send_message(peer_id, "Нет идей.")
        return
    text = "💡 Идеи:\n"
    for row in rows:
        text += f"{row[0]}. {get_user_name(row[1])}: {row[2]}\n"
    send_message(peer_id, text)

def cmd_report(user_id, peer_id, args):
    if len(args) < 1:
        send_message(peer_id, "/жалоба [текст жалобы/вопроса]")
        return
    text = ' '.join(args)
    cursor.execute('INSERT INTO reports (user_id, text, timestamp) VALUES (?, ?, ?)', (user_id, text, datetime.datetime.now().isoformat()))
    conn.commit()
    send_message(peer_id, "✅ Жалоба/вопрос отправлены!")

def cmd_reports(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') != 'agent' and not is_admin(user_id):
        send_message(peer_id, "Нет прав. Только для агентов поддержки!")
        return
    cursor.execute('SELECT * FROM reports ORDER BY id DESC LIMIT 20')
    rows = cursor.fetchall()
    if not rows:
        send_message(peer_id, "Нет жалоб/вопросов.")
        return
    text = "📋 Жалобы/Вопросы:\n"
    for row in rows:
        text += f"#{row[0]} {get_user_name(row[1])}: {row[2]}\n"
    send_message(peer_id, text)

def cmd_and(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') != 'agent' and not is_admin(user_id):
        send_message(peer_id, "Нет прав. Только для агентов поддержки!")
        return
    if len(args) < 1:
        send_message(peer_id, "/ответ [номер жалобы]")
        return
    report_id = int(args[0]) if args[0].isdigit() else 0
    if not report_id:
        send_message(peer_id, "Неверный номер.")
        return
    cursor.execute('SELECT * FROM reports WHERE id = ?', (report_id,))
    report = cursor.fetchone()
    if not report:
        send_message(peer_id, "Жалоба не найдена.")
        return
    send_message(peer_id, f"✅ Жалоба #{report_id} обработана.")
    cursor.execute('DELETE FROM reports WHERE id = ?', (report_id,))
    conn.commit()def cmd_mute(user_id, peer_id, args):
    if not is_moder(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 2:
        send_message(peer_id, "/мут [id] [минуты]")
        return
    target_id = extract_id_from_mention(args[0])
    minutes = int(args[1]) if args[1].isdigit() else 0
    if not target_id or minutes <= 0:
        send_message(peer_id, "Неверные параметры.")
        return
    until = (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).isoformat()
    cursor.execute('INSERT OR REPLACE INTO mutes (user_id, until, reason) VALUES (?, ?, ?)', (target_id, until, 'Мут'))
    conn.commit()
    update_user(target_id, mute_until=until)
    send_message(peer_id, f"🔇 {get_user_name(target_id)} заглушен на {minutes} мин.")

def cmd_unmute(user_id, peer_id, args):
    if not is_moder(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/размут [id]")
        return
    target_id = extract_id_from_mention(args[0])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    cursor.execute('DELETE FROM mutes WHERE user_id = ?', (target_id,))
    conn.commit()
    update_user(target_id, mute_until=None)
    send_message(peer_id, f"🔊 {get_user_name(target_id)} размучен")

def cmd_warn(user_id, peer_id, args):
    if not is_moder(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 2:
        send_message(peer_id, "/пред [id] [причина]")
        return
    target_id = extract_id_from_mention(args[0])
    reason = ' '.join(args[1:])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    send_message(peer_id, f"⚠️ {get_user_name(target_id)}: {reason}")

def cmd_give(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 2:
        send_message(peer_id, "/выдать [id] [сумма]")
        return
    target_id = extract_id_from_mention(args[0])
    amount = parse_amount(args[1])
    if not target_id or not amount:
        send_message(peer_id, "Неверные параметры.")
        return
    target_user = get_user(target_id)
    update_user(target_id, balance=target_user['balance']+amount)
    send_message(peer_id, f"✅ Выдано {amount}₽ пользователю {get_user_name(target_id)}")

def cmd_givespasibo(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 2:
        send_message(peer_id, "/выдать_спасибо [id] [сумма]")
        return
    target_id = extract_id_from_mention(args[0])
    amount = parse_amount(args[1])
    if not target_id or not amount:
        send_message(peer_id, "Неверные параметры.")
        return
    target_user = get_user(target_id)
    update_user(target_id, spam_balance=target_user['spam_balance']+amount)
    send_message(peer_id, f"✅ Выдано {amount} ЛутКоинов пользователю {get_user_name(target_id)}")

def cmd_take(user_id, peer_id, args):
    if not is_admin(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 2:
        send_message(peer_id, "/снять [id] [сумма]")
        return
    target_id = extract_id_from_mention(args[0])
    amount = parse_amount(args[1])
    if not target_id or not amount:
        send_message(peer_id, "Неверные параметры.")
        return
    target_user = get_user(target_id)
    if target_user['balance'] < amount:
        send_message(peer_id, "Недостаточно денег.")
        return
    update_user(target_id, balance=target_user['balance']-amount)
    send_message(peer_id, f"✅ Снято {amount}₽ у {get_user_name(target_id)}")

def cmd_setrole(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 2:
        all_roles = get_all_roles()
        sorted_roles = sorted(all_roles.items(), key=lambda x: x[1][1], reverse=True)
        roles_list = "\n".join([f"{k} — {v[0]} (приоритет {v[1]})" for k, v in sorted_roles])
        send_message(peer_id, f"Роли:\n{roles_list}\n\n/выдать_роль [id] [роль]")
        return
    target_id = extract_id_from_mention(args[0])
    role = args[1].lower()
    all_roles = get_all_roles()
    if not target_id or role not in all_roles:
        send_message(peer_id, "Неверные параметры.")
        return
    update_user(target_id, role=role)
    send_message(peer_id, f"✅ Роль {all_roles[role][0]} установлена для {get_user_name(target_id)}")

def cmd_setrank(user_id, peer_id, args):
    if not is_admin(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 2:
        send_message(peer_id, "/выдать_ранг [id] [0-4]")
        return
    target_id = extract_id_from_mention(args[0])
    try: rank = int(args[1])
    except: rank = -1
    if not target_id or rank < 0 or rank > 4:
        send_message(peer_id, "Неверные параметры.")
        return
    update_user(target_id, rank=rank)
    send_message(peer_id, f"✅ Ранг {get_rank_name(rank)} установлен для {get_user_name(target_id)}")

def cmd_ban(user_id, peer_id, args):
    if not is_moder(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/бан [id] [причина]")
        return
    target_id = extract_id_from_mention(args[0])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    reason = ' '.join(args[1:]) if len(args) > 1 else 'Не указана'
    cursor.execute('INSERT OR REPLACE INTO bans (user_id, reason, timestamp) VALUES (?, ?, ?)', (target_id, reason, datetime.datetime.now().isoformat()))
    conn.commit()
    send_message(peer_id, f"⛔ {get_user_name(target_id)} забанен: {reason}")

def cmd_unban(user_id, peer_id, args):
    if not is_moder(user_id):
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/разбан [id]")
        return
    target_id = extract_id_from_mention(args[0])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    cursor.execute('DELETE FROM bans WHERE user_id = ?', (target_id,))
    conn.commit()
    send_message(peer_id, f"✅ {get_user_name(target_id)} разбанен")

def cmd_broadcast(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 1:
        send_message(peer_id, "/рассылка [текст]")
        return
    text = ' '.join(args)
    send_message(peer_id, f"📢 {text}")

def cmd_tell(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/tell [текст]")
        return
    text = ' '.join(args)
    try:
        subscribers = vk.groups.getMembers(group_id=BOT_GROUP_ID)['items']
        count = 0
        for sub_id in subscribers:
            try:
                vk.messages.send(user_id=sub_id, message=f"📣 {text}", random_id=get_random_id())
                count += 1
                time.sleep(0.1)
            except: continue
        send_message(peer_id, f"✅ Отправлено {count} подписчикам")
    except Exception as e:
        send_message(peer_id, f"❌ Ошибка: {e}")

def cmd_tex(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'tech', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    text = ' '.join(args) if args else "Технические работы 💻"
    try:
        subscribers = vk.groups.getMembers(group_id=BOT_GROUP_ID)['items']
        count = 0
        for sub_id in subscribers:
            try:
                vk.messages.send(user_id=sub_id, message=f"🔧 {text}", random_id=get_random_id())
                count += 1
                time.sleep(0.1)
            except: continue
        send_message(peer_id, f"✅ Отправлено {count} подписчикам")
    except Exception as e:
        send_message(peer_id, f"❌ Ошибка: {e}")

def cmd_tt_stats(user_id, peer_id):
    if not is_youtuber(user_id):
        send_message(peer_id, "Нет прав. Только для ютуберов!")
        return
    user = get_user(user_id)
    verified = " ✅" if user.get('tt_verified', 0) else ""
    text = (
        f"📺 Канал: {user.get('tt_channel') or 'Нет'}{verified}\n"
        f"Подписчики: {user.get('tt_subscribers', 0)}\n"
        f"Видео: {user.get('tt_videos', 0)}\n"
        f"Лайки: {user.get('tt_likes', 0)}"
    )
    send_message(peer_id, text)

def cmd_tt_film(user_id, peer_id):
    if not is_youtuber(user_id):
        send_message(peer_id, "Нет прав. Только для ютуберов!")
        return
    user = get_user(user_id)
    if not user.get('tt_channel'):
        send_message(peer_id, "Сначала создайте канал: /тт_название [название]")
        return
    last_film = user.get('last_tt_film')
    if last_film:
        last_dt = datetime.datetime.fromisoformat(last_film)
        if (datetime.datetime.now() - last_dt).total_seconds() < 1800:
            remaining = 1800 - (datetime.datetime.now() - last_dt).total_seconds()
            send_message(peer_id, f"Следующее видео можно снять через {int(remaining//60)} мин.")
            return
    earnings = 1000
    update_user(user_id, spam_balance=user['spam_balance']+earnings, tt_videos=user.get('tt_videos',0)+1, last_tt_film=datetime.datetime.now().isoformat())
    send_message(peer_id, f"🎬 Видео снято! +{earnings} ЛутКоинов!")

def cmd_tt_name(user_id, peer_id, args):
    if not is_youtuber(user_id):
        send_message(peer_id, "Нет прав. Только для ютуберов!")
        return
    if len(args) < 1:
        send_message(peer_id, "/тт_название [название]")
        return
    name = ' '.join(args)
    cursor.execute('SELECT user_id FROM users WHERE lower(tt_channel) = lower(?)', (name,))
    exists = cursor.fetchone()
    if exists and exists[0] != user_id:
        send_message(peer_id, "Это название уже занято!")
        return
    update_user(user_id, tt_channel=name)
    send_message(peer_id, f"📺 Канал создан: {name}")

def cmd_tt_subscribe(user_id, peer_id, args):
    if len(args) < 1:
        send_message(peer_id, "/тт_подписка [название канала]")
        return
    channel_name = ' '.join(args)
    cursor.execute('SELECT user_id FROM users WHERE lower(tt_channel) = lower(?)', (channel_name,))
    target = cursor.fetchone()
    if not target:
        send_message(peer_id, "Канал не найден!")
        return
    target_id = target[0]
    if target_id == user_id:
        send_message(peer_id, "Нельзя подписываться на самого себя!")
        return
    target_user = get_user(target_id)
    update_user(target_id, tt_subscribers=target_user.get('tt_subscribers',0)+1)
    send_message(peer_id, f"📈 Вы подписались на канал {channel_name}! +1 подписчик!")

def cmd_tt_verify(user_id, peer_id):
    if not is_youtuber(user_id):
        send_message(peer_id, "Нет прав. Только для ютуберов!")
        return
    user = get_user(user_id)
    if user.get('tt_verified', 0):
        send_message(peer_id, "У вас уже есть галочка!")
        return
    if user.get('tt_subscribers', 0) < 1000:
        send_message(peer_id, "Нужно 1000 подписчиков для верификации!")
        return
    update_user(user_id, tt_verified=1)
    send_message(peer_id, "✅ Вы верифицированы! Галочка получена!")

def cmd_tt_give_subscribers(user_id, peer_id, args):
    user = get_user(user_id)
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 2:
        send_message(peer_id, "/тт_выдать_подписчиков [id] [кол-во]")
        return
    target_id = extract_id_from_mention(args[0])
    count = int(args[1]) if args[1].isdigit() else 0
    if not target_id or count <= 0:
        send_message(peer_id, "Неверные параметры.")
        return
    target_user = get_user(target_id)
    update_user(target_id, tt_subscribers=target_user.get('tt_subscribers',0)+count)
    send_message(peer_id, f"✅ Выдано {count} подписчиков пользователю {get_user_name(target_id)}")

def cmd_tt_set_likes(user_id, peer_id, args):
    user = get_user(user_id)
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 3:
        send_message(peer_id, "/тт_установить_лайки [id] [номер видео] [кол-во]")
        return
    target_id = extract_id_from_mention(args[0])
    video_num = int(args[1]) if args[1].isdigit() else 0
    likes = int(args[2]) if args[2].isdigit() else 0
    if not target_id or video_num <= 0 or likes < 0:
        send_message(peer_id, "Неверные параметры.")
        return
    target_user = get_user(target_id)
    update_user(target_id, tt_likes=target_user.get('tt_likes',0)+likes)
    send_message(peer_id, f"✅ Установлено {likes} лайков для видео {video_num}")

def cmd_tt_top(user_id, peer_id):
    cursor.execute('SELECT user_id, tt_subscribers, tt_videos, tt_likes FROM users WHERE tt_channel IS NOT NULL ORDER BY tt_subscribers DESC LIMIT 10')
    rows = cursor.fetchall()
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text = "📺 ТОП-10 ЮТУБЕРОВ:\n"
    for i, (uid, subs, videos, likes) in enumerate(rows, 1):
        name = get_user_name(uid)
        text += f"{medals[i-1]} {name} — {subs} подписчиков, {videos} видео, {likes} лайков\n"
    send_message(peer_id, text)def cmd_restart(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'tech', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    send_message(peer_id, "Перезапуск...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

def cmd_status(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'tech', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    send_message(peer_id, f"📊 Пользователей: {count}")

def cmd_db_backup(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'tech', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    import shutil
    shutil.copy('lutbot.db', f'lutbot_backup_{int(time.time())}.db')
    send_message(peer_id, "✅ Бэкап создан")

def cmd_eval(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/eval [код]")
        return
    code = ' '.join(args)
    try:
        result = eval(code)
        send_message(peer_id, f"✅ {result}")
    except Exception as e:
        send_message(peer_id, f"❌ {e}")

def cmd_sql(user_id, peer_id, args):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    if len(args) < 1:
        send_message(peer_id, "/sql [запрос]")
        return
    query = ' '.join(args)
    try:
        cursor.execute(query)
        conn.commit()
        rows = cursor.fetchall()
        send_message(peer_id, f"✅ {rows[:10] if rows else 'Выполнено'}")
    except Exception as e:
        send_message(peer_id, f"❌ {e}")

def cmd_logs(user_id, peer_id):
    user = get_user(user_id)
    if user.get('role') not in ['admin', 'dev', 'owner', 'deputy']:
        send_message(peer_id, "Нет прав.")
        return
    cursor.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 10')
    rows = cursor.fetchall()
    text = "Логи:\n"
    for row in rows:
        text += f"{row[1]}: {row[2]}\n"
    send_message(peer_id, text)

def cmd_zov(user_id, peer_id):
    try:
        members = vk.messages.getConversationMembers(peer_id=peer_id)['items']
        user_ids = [m['member_id'] for m in members if m['member_id'] > 0]
        mentions = []
        for uid in user_ids:
            user = get_user(uid)
            if user.get('role') == 'user':
                mentions.append(f"[id{uid}|{get_user_name(uid)}]")
        if mentions:
            send_message(peer_id, "📣 " + " ".join(mentions[:50]))
        else:
            send_message(peer_id, "📣 Нет участников без роли.")
    except Exception as e:
        send_message(peer_id, f"Ошибка: {e}")

def cmd_online(user_id, peer_id):
    try:
        members = vk.messages.getConversationMembers(peer_id=peer_id)['items']
        user_ids = [m['member_id'] for m in members if m['member_id'] > 0]
        if not user_ids:
            send_message(peer_id, "Не удалось получить список.")
            return
        users_info = vk.users.get(user_ids=user_ids, fields='online')
        online_users = [u for u in users_info if u.get('online', 0) == 1]
        text = f"🔵 В сети: {len(online_users)} из {len(user_ids)}\n"
        for u in online_users[:20]:
            name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
            text += f"• {name}\n"
        send_message(peer_id, text)
    except Exception as e:
        send_message(peer_id, f"Ошибка: {e}")

def cmd_staff(user_id, peer_id):
    cursor.execute("SELECT user_id, role FROM users WHERE role != 'user'")
    rows = cursor.fetchall()
    all_roles = get_all_roles()
    staff_by_role = {}
    for uid, role in rows:
        if role not in staff_by_role:
            staff_by_role[role] = []
        staff_by_role[role].append(get_user_name(uid))
    sorted_roles = sorted(staff_by_role.keys(), key=lambda r: all_roles.get(r, ('', 0))[1], reverse=True)
    text = "👮 Состав команды:\n\n"
    for role in sorted_roles:
        role_display = all_roles.get(role, (role, 0))[0]
        text += f"{role_display}:\n" + "\n".join([f"— {name}" for name in staff_by_role[role]]) + "\n\n"
    if not text.strip():
        send_message(peer_id, "Нет персонала.")
        return
    send_message(peer_id, text)

def cmd_id(user_id, peer_id, args):
    if args:
        target_id = extract_id_from_mention(args[0])
        if target_id is None:
            send_message(peer_id, "Не удалось распознать ID.")
            return
    else:
        target_id = user_id
    send_message(peer_id, f"🆔 {get_user_name(target_id)}: {target_id}")

def cmd_stats(user_id, peer_id, args):
    if args:
        target_id = extract_id_from_mention(args[0])
        if target_id is None and args[0].isdigit():
            target_id = int(args[0])
        if target_id is None:
            send_message(peer_id, "Неверный ID.")
            return
    else:
        target_id = user_id
    stats = get_stats(target_id)
    target_user = get_user(target_id)
    last_seen = get_last_seen(target_id)
    role = ROLE_NAMES.get(target_user.get('role'), target_user.get('role'))
    text = (
        f"📊 {get_user_name(target_id)}:\n"
        f"Сообщений: {stats['messages_count']}\nМатов: {stats['mat_count']}\n"
        f"Фото: {stats['photo_count']}\nГолосовых: {stats['voice_count']}\n"
        f"Видео: {stats['video_count']}\nВ сети: {last_seen}\n"
        f"Роль: {role}"
    )
    send_message(peer_id, text)

def cmd_quests(user_id, peer_id):
    text = "📋 ЗАДАНИЯ:\n\n"
    for quest in QUESTS:
        cursor.execute('SELECT progress, claimed FROM user_quests WHERE user_id = ? AND quest_id = ?', (user_id, quest['id']))
        row = cursor.fetchone()
        progress = row[0] if row else 0
        claimed = row[1] if row else 0
        status = "✅ Выполнено" if progress >= quest['target'] else f"🔲 {progress}/{quest['target']}"
        if claimed:
            status = "🎁 Получено"
        text += f"{quest['id']}. {quest['desc']} — {status}\n"
        if progress >= quest['target'] and not claimed:
            text += f"   Награда: {quest['reward_money']}₽, {quest['reward_exp']} опыта. Забрать: /получить {quest['id']}\n"
    send_message(peer_id, text)

def cmd_claim(user_id, peer_id, args):
    if len(args) < 1:
        send_message(peer_id, "Использование: /получить [id задания]")
        return
    quest_id = int(args[0]) if args[0].isdigit() else 0
    quest = next((q for q in QUESTS if q['id'] == quest_id), None)
    if not quest:
        send_message(peer_id, "Задание не найдено.")
        return
    cursor.execute('SELECT progress, claimed FROM user_quests WHERE user_id = ? AND quest_id = ?', (user_id, quest_id))
    row = cursor.fetchone()
    if not row or row[1] == 1:
        send_message(peer_id, "Задание уже получено или не выполнено.")
        return
    if row[0] < quest['target']:
        send_message(peer_id, f"Задание ещё не выполнено: {row[0]}/{quest['target']}")
        return
    update_user(user_id, balance=get_user(user_id)['balance'] + quest['reward_money'])
    user = get_user(user_id)
    new_exp = user.get('experience', 0) + quest['reward_exp']
    new_level = user.get('level', 1)
    while new_exp >= 100:
        new_exp -= 100
        new_level += 1
    update_user(user_id, experience=new_exp, level=new_level)
    cursor.execute('UPDATE user_quests SET claimed = 1 WHERE user_id = ? AND quest_id = ?', (user_id, quest_id))
    conn.commit()
    send_message(peer_id, f"🎉 Награда получена: {quest['reward_money']}₽ и {quest['reward_exp']} опыта!")

def cmd_wipe_info(user_id, peer_id):
    cursor.execute('SELECT last_wipe FROM wipe_info WHERE id = 1')
    row = cursor.fetchone()
    last_wipe = row[0] if row else 'не было'
    text = (
        "🧹 Система вайпов экономики\n\n"
        "🌐 Ближайший глобальный вайп: 00:00 МСК\n"
        "Глобальный вайп проходит 1 раз в 1 месяц и обнуляет экономику.\n"
        "Сохраняются: лимитированные предметы.\n"
        "🏆 Награды топа перед вайпом: 1 место — 100 ЛутКоинов, 2 место — 50, 3 место — 25, остальные топ-10 — по 10.\n\n"
        f"📊 Последний вайп: {last_wipe}\n"
        "• Топ экономики: доступен по /топ"
    )
    send_message(peer_id, text)

def cmd_wipe(user_id, peer_id):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    cursor.execute('SELECT last_wipe FROM wipe_info WHERE id = 1')
    row = cursor.fetchone()
    now = datetime.datetime.now()
    if row:
        last_wipe = datetime.datetime.fromisoformat(row[0])
        if (now - last_wipe).days < 30:
            remaining = 30 - (now - last_wipe).days
            send_message(peer_id, f"Вайп уже был. Следующий через {remaining} дней.")
            return
    cursor.execute('SELECT user_id FROM users WHERE hidden_from_top = 0 ORDER BY balance DESC LIMIT 10')
    top_users = cursor.fetchall()
    rewards = {1: 100, 2: 50, 3: 25}
    for i, (uid,) in enumerate(top_users, 1):
        reward = rewards.get(i, 10)
        user = get_user(uid)
        update_user(uid, spam_balance=user['spam_balance']+reward)
    cursor.execute('UPDATE users SET balance = 500, credit_amount = 0, credit_due = NULL')
    conn.commit()
    cursor.execute('INSERT OR REPLACE INTO wipe_info (id, last_wipe) VALUES (1, ?)', (now.isoformat(),))
    conn.commit()
    send_message(peer_id, "🧹 Вайп выполнен! Экономика обнулена, награды топам выданы. Лимитированные предметы сохранены.")

def cmd_red(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 1:
        send_message(peer_id, "/скрыть_из_топа [id]")
        return
    target_id = extract_id_from_mention(args[0])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    update_user(target_id, hidden_from_top=1)
    send_message(peer_id, f"✅ Игрок {get_user_name(target_id)} скрыт из топа.")

def cmd_limited(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 1:
        send_message(peer_id, "/лимитка [название]")
        return
    name = ' '.join(args)
    cursor.execute('INSERT OR IGNORE INTO limited_items (name, created_by, timestamp) VALUES (?, ?, ?)', (name, user_id, datetime.datetime.now().isoformat()))
    conn.commit()
    send_message(peer_id, f"✅ Лимитированный предмет \"{name}\" создан!")

def cmd_givelimited(user_id, peer_id, args):
    if not is_owner(user_id):
        send_message(peer_id, "Нет прав. Только для владельца/заместителя!")
        return
    if len(args) < 2:
        send_message(peer_id, "/выдать_лимитку [id] [название]")
        return
    target_id = extract_id_from_mention(args[0])
    name = ' '.join(args[1:])
    if not target_id:
        send_message(peer_id, "Неверный ID.")
        return
    cursor.execute('SELECT * FROM limited_items WHERE name = ?', (name,))
    item = cursor.fetchone()
    if not item:
        send_message(peer_id, "Лимитированный предмет не найден.")
        return
    target_user = get_user(target_id)
    items = target_user.get('limited_items', '')
    if items:
        items += ',' + name
    else:
        items = name
    update_user(target_id, limited_items=items)
    send_message(peer_id, f"✅ Лимитированный предмет \"{name}\" выдан пользователю {get_user_name(target_id)}")

def cmd_inventory(user_id, peer_id):
    user = get_user(user_id)
    items = user.get('limited_items', '')
    if not items:
        send_message(peer_id, "У вас нет лимитированных предметов.")
        return
    item_list = items.split(',')
    text = "🎒 Ваши лимитированные предметы:\n"
    for item in item_list:
        text += f"• {item}\n"
    send_message(peer_id, text)

def handle_command(user_id, peer_id, cmd, args):
    if cmd in ['/start', '/help', '/хелп']: cmd_help(user_id, peer_id)
    elif cmd == '/ghelp': cmd_ghelp(user_id, peer_id)
    elif cmd == '/mhelp': cmd_mhelp(user_id, peer_id)
    elif cmd == '/thelp': cmd_thelp(user_id, peer_id)
    elif cmd == '/ahelp': cmd_ahelp(user_id, peer_id)
    elif cmd == '/dhelp': cmd_dhelp(user_id, peer_id)
    elif cmd in ['/профиль', '/profile']: cmd_profil(user_id, peer_id)
    elif cmd in ['/ид', '/id']: cmd_id(user_id, peer_id, args)
    elif cmd in ['/стата', '/stats']: cmd_stats(user_id, peer_id, args)
    elif cmd in ['/паспорт', '/passport']: cmd_passport(user_id, peer_id)
    elif cmd in ['/карта', '/register_card']: cmd_register_card(user_id, peer_id)
    elif cmd in ['/работа_да', '/work_yes']: cmd_work_yes(user_id, peer_id)
    elif cmd in ['/работа_нет', '/work_no']: cmd_work_no(user_id, peer_id)
    elif cmd in ['/работа', '/work']: cmd_work(user_id, peer_id)
    elif cmd in ['/ранг', '/rank']: cmd_rank(user_id, peer_id)
    elif cmd in ['/улучшить_банк', '/upgrade_bank']: cmd_upgrade_bank(user_id, peer_id)
    elif cmd in ['/кредит', '/credit']: cmd_credit(user_id, peer_id, args)
    elif cmd in ['/погасить_кредит', '/pay_credit']: cmd_pay_credit(user_id, peer_id)
    elif cmd in ['/фриланс', '/freelance']: cmd_freelance(user_id, peer_id)
    elif cmd in ['/казино', '/casino']: cmd_casino(user_id, peer_id, args)
    elif cmd in ['/купить_дом', '/buy_house']:
        if args: cmd_buy_house_name(user_id, peer_id, args)
        else: cmd_buy_house(user_id, peer_id)
    elif cmd in ['/купить_машину', '/buy_car']:
        if args: cmd_buy_car_name(user_id, peer_id, args)
        else: cmd_buy_car(user_id, peer_id)
    elif cmd in ['/купить_бизнес', '/buy_company']:
        if args: cmd_buy_company_name(user_id, peer_id, args)
        else: cmd_buy_company(user_id, peer_id)
    elif cmd in ['/бонус', '/daily']: cmd_daily(user_id, peer_id)
    elif cmd in ['/топ', '/top']: cmd_top(user_id, peer_id)
    elif cmd in ['/кейс', '/container', '/case']: cmd_container(user_id, peer_id)
    elif cmd in ['/обмен', '/convert_spasibo']: cmd_convert_spasibo(user_id, peer_id)
    elif cmd in ['/подписка', '/subscribe']: cmd_subscribe(user_id, peer_id)
    elif cmd in ['/купить_вип', '/buy_vip']: cmd_buy_vip(user_id, peer_id)
    elif cmd in ['/промокод', '/promo']: cmd_promo(user_id, peer_id, args)
    elif cmd in ['/промолист', '/promolist']: cmd_promolist(user_id, peer_id)
    elif cmd in ['/создать_промокод', '/setpromo']: cmd_setpromo(user_id, peer_id, args)
    elif cmd in ['/идея', '/offer']: cmd_offer(user_id, peer_id, args)
    elif cmd in ['/идеи', '/offers']: cmd_offers(user_id, peer_id)
    elif cmd in ['/жалоба', '/report']: cmd_report(user_id, peer_id, args)
    elif cmd in ['/жалобы', '/reports']: cmd_reports(user_id, peer_id)
    elif cmd in ['/ответ', '/and']: cmd_and(user_id, peer_id, args)
    elif cmd in ['/тех', '/tex']: cmd_tex(user_id, peer_id, args)
    elif cmd == '/tell': cmd_tell(user_id, peer_id, args)
    elif cmd in ['/тт', '/тт_статистика']: cmd_tt_stats(user_id, peer_id)
    elif cmd == '/тт_снять': cmd_tt_film(user_id, peer_id)
    elif cmd == '/тт_название': cmd_tt_name(user_id, peer_id, args)
    elif cmd == '/тт_подписка': cmd_tt_subscribe(user_id, peer_id, args)
    elif cmd == '/тт_verify': cmd_tt_verify(user_id, peer_id)
    elif cmd == '/тт_выдать_подписчиков': cmd_tt_give_subscribers(user_id, peer_id, args)
    elif cmd == '/тт_установить_лайки': cmd_tt_set_likes(user_id, peer_id, args)
    elif cmd == '/тт_топ': cmd_tt_top(user_id, peer_id)
    elif cmd in ['/зов', '/zov']: cmd_zov(user_id, peer_id)
    elif cmd in ['/онлайн', '/online']: cmd_online(user_id, peer_id)
    elif cmd in ['/состав', '/staff']: cmd_staff(user_id, peer_id)
    elif cmd in ['/выдать', '/give']: cmd_give(user_id, peer_id, args)
    elif cmd in ['/выдать_спасибо', '/givespasibo']: cmd_givespasibo(user_id, peer_id, args)
    elif cmd in ['/снять', '/take']: cmd_take(user_id, peer_id, args)
    elif cmd in ['/выдать_роль', '/setrole']: cmd_setrole(user_id, peer_id, args)
    elif cmd in ['/выдать_ранг', '/setrank']: cmd_setrank(user_id, peer_id, args)
    elif cmd in ['/бан', '/ban']: cmd_ban(user_id, peer_id, args)
    elif cmd in ['/разбан', '/unban']: cmd_unban(user_id, peer_id, args)
    elif cmd in ['/рассылка', '/broadcast']: cmd_broadcast(user_id, peer_id, args)
    elif cmd in ['/мут', '/mute']: cmd_mute(user_id, peer_id, args)
    elif cmd in ['/размут', '/unmute']: cmd_unmute(user_id, peer_id, args)
    elif cmd in ['/пред', '/warn']: cmd_warn(user_id, peer_id, args)
    elif cmd in ['/рестарт', '/restart']: cmd_restart(user_id, peer_id)
    elif cmd in ['/статус', '/status']: cmd_status(user_id, peer_id)
    elif cmd in ['/бэкап', '/db_backup']: cmd_db_backup(user_id, peer_id)
    elif cmd == '/eval': cmd_eval(user_id, peer_id, args)
    elif cmd == '/sql': cmd_sql(user_id, peer_id, args)
    elif cmd in ['/логи', '/logs']: cmd_logs(user_id, peer_id)
    elif cmd in ['/задания', '/quests']: cmd_quests(user_id, peer_id)
    elif cmd in ['/получить', '/claim']: cmd_claim(user_id, peer_id, args)
    elif cmd in ['/вайп', '/wipe']: cmd_wipe_info(user_id, peer_id)
    elif cmd in ['/вайпс', '/wipe_now']: cmd_wipe(user_id, peer_id)
    elif cmd in ['/скрыть_из_топа', '/red']: cmd_red(user_id, peer_id, args)
    elif cmd in ['/лимитка', '/limited']: cmd_limited(user_id, peer_id, args)
    elif cmd in ['/выдать_лимитку', '/givelimited']: cmd_givelimited(user_id, peer_id, args)
    elif cmd in ['/инвентарь', '/inventory']: cmd_inventory(user_id, peer_id)
    elif cmd in ['/newrole', '/новаяроль']: cmd_newrole(user_id, peer_id, args)

def process_command(user_id, peer_id, text):
    if is_muted(user_id):
        send_message(peer_id, "🔇 Вы в муте!")
        return
    if check_ban(user_id):
        send_message(peer_id, "⛔ Вы забанены!")
        return
    if not check_credit(user_id):
        send_message(peer_id, "⛔ Бан: Долг!")
        return

    text = re.sub(r'\[club\d+\|@?\w+\]\s*', '', text, flags=re.IGNORECASE).strip()
    if not text:
        return

    if text.startswith('/'):
        parts = text[1:].strip().lower().split()
        if not parts:
            return
        cmd = '/' + parts[0]
        args = parts[1:]
        handle_command(user_id, peer_id, cmd, args)
        return

    lower_text = text.lower()
    keyword_map = {
        'профиль': '/профиль',
        'инвентарь': '/инвентарь',
        'казино': '/казино',
        'дом': '/купить_дом',
        'машина': '/купить_машину',
        'бизнес': '/купить_бизнес',
        'донат': '/купить_вип',
        'vip': '/купить_вип',
        'помощь': '/help',
        'меню': '/help',
        'хелп': '/help',
    }
    cmd = None
    args = []
    for keyword, mapped_cmd in keyword_map.items():
        if keyword in lower_text:
            cmd = mapped_cmd
            break
    if not cmd:
        parts = lower_text.split()
        if parts:
            possible_cmd = '/' + parts[0]
            if possible_cmd in ['/профиль', '/паспорт', '/карта', '/работа_да', '/работа_нет', '/работа',
                                '/ранг', '/улучшить_банк', '/кредит', '/погасить_кредит', '/фриланс',
                                '/казино', '/купить_дом', '/купить_машину', '/купить_бизнес', '/бонус',
                                '/топ', '/кейс', '/обмен', '/подписка', '/купить_вип', '/промокод',
                                '/промолист', '/идея', '/жалоба', '/ид', '/стата', '/зов', '/онлайн',
                                '/состав', '/задания', '/получить', '/вайп', '/вайпс', '/скрыть_из_топа',
                                '/лимитка', '/выдать_лимитку', '/инвентарь', '/выдать', '/выдать_спасибо',
                                '/снять', '/выдать_роль', '/выдать_ранг', '/бан', '/разбан', '/рассылка',
                                '/мут', '/размут', '/пред', '/рестарт', '/статус', '/бэкап', '/логи',
                                '/тт', '/тт_статистика', '/тт_снять', '/тт_название', '/тт_подписка',
                                '/тт_verify', '/тт_выдать_подписчиков', '/тт_установить_лайки', '/тт_топ',
                                '/newrole']:
                cmd = possible_cmd
                args = parts[1:]
    if cmd:
        handle_command(user_id, peer_id, cmd, args)

def main():
    logger.info("ЛутБот запущен")
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW:
            peer_id = event.peer_id
            user_id = event.user_id if hasattr(event, 'user_id') else None
            text = event.text
            attachments = getattr(event, 'attachments', None)
            if user_id and user_id > 0:
                try:
                    update_stats(user_id, text, attachments)
                    logger.info(f"Сообщение от {user_id} в {peer_id}: {text}")
                    process_command(user_id, peer_id, text)
                except Exception as e:
                    logger.error(f"Ошибка обработки: {e}")

if __name__ == '__main__':
    main()
