# -*- coding: utf-8 -*-
"""
VK-бот 4.2 — модерация + Мафия + тикеты + ивенты + статистика + подсказки команд
Адаптирован для деплоя на Bothost (переменные окружения)
"""

import os, re, sys, json, time, random, threading, difflib
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.exceptions import VkApiError

# ================================================================
# НАСТРОЙКИ (читаются из переменных окружения Bothost)
# ================================================================
TOKEN = os.getenv("VK_TOKEN", "").strip()
GROUP_ID = int(os.getenv("VK_GROUP_ID", "241512398"))
GLOBAL_OWNER_ID = int(os.getenv("GLOBAL_OWNER_ID", "1054352381"))

if not TOKEN:
    print("❌ Не задан VK_TOKEN в переменных окружения Bothost!")
    print("   Добавь переменную VK_TOKEN = ваш_токен_группы")
    sys.exit(1)

WELCOME_TEXT = """👋 Добро пожаловать, {user}!

📋 Команды:
/help /staff /role /стата
/offer /report — идея / жалоба
/claim — стать владельцем беседы
/ивент — список ивентов"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PID_FILE = "/tmp/.bot.pid"
CFG_VERSION = 4
MUTE_DM_INTERVAL = 300

# ================================================================
# ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА
# ================================================================
def check_single_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            if os.name != "nt":
                try:
                    os.kill(old_pid, 0)
                    print(f"❌ Уже запущен бот с PID={old_pid}!")
                    sys.exit(1)
                except OSError:
                    pass
        except (ValueError, FileNotFoundError):
            pass
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

check_single_instance()

# ================================================================
# НАБОРЫ КОМАНД
# ================================================================
BASIC_CMDS     = ["help", "info", "staff", "claim", "role", "стата", "stat", "offer", "report"]
MODERATOR_CMDS = BASIC_CMDS + ["nick", "rnick", "warn", "unwarn",
                                "mute", "unmute", "clear", "banlist",
                                "tickets", "adt"]
ADMIN_CMDS     = MODERATOR_CMDS + ["kick", "ban", "unban", "gban", "ungban"]
STAFF_CMDS     = ADMIN_CMDS + ["loginfo", "ивент", "event"]
OWNER_CMDS     = STAFF_CMDS + ["addstaff", "removestaff", "setrole", "setowner",
                                "setlog", "unsetlog", "setwarns", "setmutetime",
                                "createivent"]

DEFAULT_ROLES = {
    "head": {"name": "Руководитель", "priority": 95, "commands": STAFF_CMDS},
    "deputy_head": {"name": "Заместитель Руководителя", "priority": 90, "commands": STAFF_CMDS},
    "special_admin": {"name": "Специальный Администратор", "priority": 85, "commands": STAFF_CMDS},
    "chief_admin": {"name": "Главный Администратор", "priority": 80, "commands": ADMIN_CMDS},
    "deputy_chief_admin": {"name": "Заместитель Главного Администратора", "priority": 75, "commands": ADMIN_CMDS},
    "chief_watcher": {"name": "Главный Следящий", "priority": 70, "commands": MODERATOR_CMDS},
    "deputy_chief_watcher": {"name": "Заместитель Главного Следящего", "priority": 65, "commands": MODERATOR_CMDS},
    "admin": {"name": "Администратор", "priority": 60, "commands": ADMIN_CMDS},
    "moderator": {"name": "Модератор", "priority": 50, "commands": MODERATOR_CMDS},
    "helper": {"name": "Хелпер", "priority": 20, "commands": BASIC_CMDS},
}

def commands_for_priority(p):
    if p >= 70: return list(STAFF_CMDS)
    if p >= 60: return list(ADMIN_CMDS)
    if p >= 40: return list(MODERATOR_CMDS)
    return list(BASIC_CMDS)

# ================================================================
# СПИСОК ВСЕХ КОМАНД (для подсказок)
# ================================================================
ALL_COMMANDS = set()
for _r in DEFAULT_ROLES.values():
    ALL_COMMANDS.update(_r.get("commands", []))
ALL_COMMANDS.update([
    "offer", "report", "tickets", "adt", "role",
    "createivent", "newrole", "delrole",
    "объявление", "announce", "рассылка",
    "ивент", "event", "стата", "stat", "help",
])

def suggest_command(cmd):
    matches = difflib.get_close_matches(cmd, list(ALL_COMMANDS), n=1, cutoff=0.55)
    return matches[0] if matches else None

# ================================================================
# КОНФИГ
# ================================================================
DEFAULT_CHAT = {"owner": None, "staff": {}, "banned": {}, "muted": {},
                "warns": {}, "nicknames": {}, "welcome": True}
DEFAULT_CFG = {
    "version": CFG_VERSION, "global_owner": GLOBAL_OWNER_ID,
    "default_mute_minutes": 30, "max_warns": 3, "log_peer_id": 0,
    "roles": DEFAULT_ROLES, "chats": {}, "known_peers": [],
    "tickets": {}, "next_ticket_id": 1,
    "user_stats": {}, "custom_events": {},
}
_cfg_lock = threading.Lock()

def migrate(d):
    d.setdefault("version", 1)
    for k, v in DEFAULT_CFG.items():
        if k not in d: d[k] = v
    roles = d.get("roles") or {}
    if not all(isinstance(v, dict) and "priority" in v for v in roles.values()):
        d["roles"] = json.loads(json.dumps(DEFAULT_ROLES))
    else:
        for k, v in DEFAULT_ROLES.items():
            if k not in d["roles"]: d["roles"][k] = v
    d["version"] = CFG_VERSION
    d.setdefault("global_owner", GLOBAL_OWNER_ID)
    d.setdefault("chats", {}); d.setdefault("known_peers", []); d.setdefault("log_peer_id", 0)
    d.setdefault("tickets", {}); d.setdefault("next_ticket_id", 1)
    d.setdefault("user_stats", {}); d.setdefault("custom_events", {})
    for ch in d.get("chats", {}).values():
        muted = ch.get("muted", {})
        for uid, val in list(muted.items()):
            if isinstance(val, (int, float)):
                muted[uid] = {"until": val, "last_dm": 0}
    return d

def load_cfg():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CFG, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[cfg create] {e}")
        return json.loads(json.dumps(DEFAULT_CFG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return migrate(json.load(f))
    except Exception as e:
        print(f"[cfg load] {e}")
        return json.loads(json.dumps(DEFAULT_CFG))

def save_cfg(d):
    with _cfg_lock:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[cfg save] {e}")

cfg = load_cfg()
save_cfg(cfg)

# ================================================================
# VK
# ================================================================
print("🔌 Подключаюсь к VK...")
vk = vk_api.VkApi(token=TOKEN)
api = vk.get_api()
try:
    gi = api.groups.getById(group_id=GROUP_ID)
    print(f"   ✅ Группа: {gi[0]['name']} (id={GROUP_ID})")
except VkApiError as e:
    print(f"   ❌ {e}"); sys.exit(1)
try:
    longpoll = VkBotLongPoll(vk, group_id=GROUP_ID)
    print("   ✅ Long Poll готов")
except VkApiError as e:
    print(f"   ❌ Long Poll: {e}"); sys.exit(1)
BOT_ID = -GROUP_ID

# ================================================================
# ИМЕНА
# ================================================================
_name_cache = {}
_name_lock = threading.Lock()

def prefetch_names(uids):
    uids = [int(u) for u in uids if u and int(u) > 0]
    to = []
    with _name_lock:
        for u in uids:
            if u not in _name_cache: to.append(u)
    if not to: return
    try:
        for i in range(0, len(to), 500):
            res = api.users.get(user_ids=",".join(map(str, to[i:i+500])),
                                fields="first_name,last_name")
            with _name_lock:
                for u in res:
                    n = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
                    _name_cache[u["id"]] = n or f"id{u['id']}"
    except Exception as e:
        print(f"[prefetch] {e}")

def get_vk_name(uid):
    uid = int(uid)
    with _name_lock:
        if uid in _name_cache: return _name_cache[uid]
    try:
        r = api.users.get(user_ids=uid, fields="first_name,last_name")
        n = f"{r[0].get('first_name','')} {r[0].get('last_name','')}".strip() if r else f"id{uid}"
        n = n or f"id{uid}"
    except Exception:
        n = f"id{uid}"
    with _name_lock:
        _name_cache[uid] = n
    return n

def mention(uid, peer_id=None):
    uid = int(uid)
    if peer_id and is_chat(peer_id):
        c = get_chat(peer_id)
        nick = c.get("nicknames", {}).get(str(uid))
        if nick: return f"[id{uid}|{nick}]"
    return f"[id{uid}|{get_vk_name(uid)}]"

# ================================================================
# ДЕДУПЛИКАЦИЯ
# ================================================================
_processed = set()
_processed_lock = threading.Lock()

def is_duplicate(peer_id, msg):
    cmid = msg.get("conversation_message_id") or msg.get("id") or 0
    text = (msg.get("text") or "")[:40]
    key = (peer_id, cmid, msg.get("from_id"), text)
    with _processed_lock:
        if key in _processed: return True
        _processed.add(key)
        if len(_processed) > 5000:
            for x in list(_processed)[:2500]: _processed.discard(x)
        return False

# ================================================================
# ХЕЛПЕРЫ
# ================================================================
def send(peer_id, text, reply_to=None):
    kw = {"peer_id": peer_id, "message": text,
          "random_id": int(time.time() * 1000) + random.randint(0, 999),
          "disable_mentions": 0}
    if reply_to:
        try:
            r = int(reply_to)
            if r > 0: kw["reply_to"] = r
        except Exception: pass
    try:
        api.messages.send(**kw)
    except Exception as e:
        print(f"[send error] {e}")
        if "reply_to" in kw:
            del kw["reply_to"]
            try: api.messages.send(**kw)
            except Exception as e2: print(f"[send2] {e2}")

def send_dm(uid, text):
    try:
        api.messages.send(peer_id=uid, message=text,
                          random_id=int(time.time() * 1000) + random.randint(0, 999),
                          disable_mentions=1)
        return True
    except Exception as e:
        print(f"[dm {uid}] {e}")
        return False

def log_action(actor_id, text):
    peer = cfg.get("log_peer_id")
    if not peer: return
    try:
        who = "🤖 бот" if actor_id == BOT_ID else f"[id{actor_id}|модератор]"
        api.messages.send(peer_id=peer, message=f"📝 {who}: {text}",
                          random_id=int(time.time() * 1000) + random.randint(0, 999))
    except Exception as e:
        print(f"[log] {e}")

def is_chat(peer_id): return peer_id > 2000000000
def chat_id_from_peer(peer_id): return peer_id - 2000000000 if peer_id > 2000000000 else None

def get_chat(peer_id):
    if not is_chat(peer_id): return None
    chats = cfg.setdefault("chats", {}); key = str(peer_id)
    if key not in chats:
        chats[key] = json.loads(json.dumps(DEFAULT_CHAT)); save_cfg(cfg)
    for k, v in DEFAULT_CHAT.items():
        chats[key].setdefault(k, json.loads(json.dumps(v)))
    return chats[key]

def track_peer(peer_id):
    if not is_chat(peer_id): return
    kp = cfg.setdefault("known_peers", [])
    if peer_id not in kp:
        kp.append(peer_id); save_cfg(cfg)

def track_message(from_id, peer_id, text):
    stats = cfg.setdefault("user_stats", {})
    key = str(from_id)
    s = stats.get(key) or {"msg_count": 0, "last_text": "", "last_peer": 0, "last_at": 0}
    s["msg_count"] += 1
    if text:
        s["last_text"] = text[:120]
    s["last_peer"] = peer_id
    s["last_at"] = int(time.time())
    stats[key] = s
    if s["msg_count"] % 20 == 0:
        save_cfg(cfg)

def get_role_key(uid, peer_id):
    if int(uid) == int(cfg["global_owner"]): return "global"
    if not is_chat(peer_id): return None
    c = get_chat(peer_id)
    if c.get("owner") == uid: return "owner"
    return c.get("staff", {}).get(str(uid))

def role_display(uid, peer_id):
    k = get_role_key(uid, peer_id)
    if k == "global": return "🌐 Главный владелец"
    if k == "owner": return "👑 Владелец беседы"
    if k and k in cfg["roles"]: return cfg["roles"][k]["name"]
    return "нет"

def can(uid, cmd, peer_id):
    if int(uid) == int(cfg["global_owner"]): return True
    if not is_chat(peer_id): return False
    c = get_chat(peer_id)
    if c.get("owner") == uid:
        return cmd not in ("newrole", "delrole", "объявление", "announce", "рассылка", "createivent")
    rk = c.get("staff", {}).get(str(uid))
    if not rk: return False
    return cmd in cfg["roles"].get(rk, {}).get("commands", [])

def extract_user(text, reply_msg=None):
    m = re.search(r"\[id(\d+)\|", text)
    if m: return int(m.group(1))
    m = re.search(r"@id(\d+)", text)
    if m: return int(m.group(1))
    if reply_msg: return reply_msg.get("from_id")
    return None

def kick_user(cid, uid):
    try:
        api.messages.removeChatUser(chat_id=cid, user_id=uid); return True, None
    except Exception as e:
        return False, str(e)

def delete_msg(mid, cmid=None, peer_id=None):
    if cmid and peer_id:
        try:
            api.messages.delete(conversation_message_ids=cmid, peer_id=peer_id, delete_for_all=1)
            return True
        except Exception as e:
            print(f"[del cmid] {e}")
    if mid and mid > 0:
        try:
            api.messages.delete(message_ids=mid, delete_for_all=1); return True
        except Exception as e:
            print(f"[del id] {e}")
    if cmid and peer_id:
        time.sleep(0.3)
        try:
            api.messages.delete(conversation_message_ids=cmid, peer_id=peer_id, delete_for_all=1)
            return True
        except Exception as e:
            print(f"[del retry] {e}")
    return False

def fmt_time(s):
    s = int(s)
    if s < 60: return f"{s} сек"
    if s < 3600:
        m = s // 60; sec = s % 60
        return f"{m} мин {sec} сек" if sec else f"{m} мин"
    if s < 86400:
        h = s // 3600; m = s % 3600 // 60
        return f"{h} ч {m} мин" if m else f"{h} ч"
    d = s // 86400; h = s % 86400 // 3600
    return f"{d} д {h} ч" if h else f"{d} д"

def fmt_dt(ts):
    if not ts: return "—"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))

def mute_notify_dm(uid, minutes):
    send_dm(uid, f"🔇 Вы получили мут на {minutes} мин.\n\n"
                 f"Ваши сообщения будут удаляться.\n"
                 f"Размут: через {minutes} мин.")

def mute_warn_dm(uid, remaining_seconds):
    send_dm(uid, f"🔇 Вы всё ещё в муте.\n"
                 f"⏳ Осталось: {fmt_time(remaining_seconds)}")

def mute_expired_dm(uid):
    send_dm(uid, "🔊 Ваш мут снят. Можете снова писать.")

def get_mute_until(info):
    if isinstance(info, dict): return info.get("until", 0)
    return info or 0

def find_role_by_input(s):
    sl = (s or "").lower().strip()
    if not sl: return None
    for k in cfg["roles"]:
        if k.lower() == sl: return k
    for k, v in cfg["roles"].items():
        if v.get("name", "").lower() == sl: return k
    if sl.isdigit():
        p = int(sl)
        for k, v in cfg["roles"].items():
            if v.get("priority") == p: return k
    return None

# ================================================================
# СТАТИСТИКА
# ================================================================
def user_stats_text(uid, peer_id):
    uid = int(uid)
    role = role_display(uid, peer_id)
    c = get_chat(peer_id) if is_chat(peer_id) else None
    bans_local = 0
    bans_global = False
    for ch in cfg.get("chats", {}).values():
        info = ch.get("banned", {}).get(str(uid))
        if info:
            bans_local += 1
            if info.get("global"): bans_global = True
    warns = 0
    chat_mute = False
    nick = None
    if c:
        warns = c.get("warns", {}).get(str(uid), 0)
        mu_until = get_mute_until(c.get("muted", {}).get(str(uid)))
        chat_mute = bool(mu_until and mu_until > time.time())
        nick = c.get("nicknames", {}).get(str(uid))
    s = cfg.get("user_stats", {}).get(str(uid), {})
    msg_count = s.get("msg_count", 0)
    last_text = s.get("last_text") or "—"
    last_at = s.get("last_at", 0)
    lines = [
        "📊 Информация о пользователе:",
        f"• Пользователь: {mention(uid, peer_id)}",
        f"• Роль: {role}",
        f"• Блокировок: {bans_local}",
        f"• Общая блокировка в чатах: {'Да' if bans_global else 'Нет'}",
        f"• Общая блокировка в беседах игроков: {'Да' if bans_global else 'Нет'}",
        f"• Активные предупреждения: {warns}",
        f"• Блокировка чата: {'Да' if chat_mute else 'Нет'}",
        f"• Ник: {nick if nick else 'Нет'}",
        f"• Всего сообщений: {msg_count}",
        f"• Последнее сообщение: {last_text}",
        f"• Когда: {fmt_dt(last_at)}",
    ]
    return "\n".join(lines)

# ================================================================
# ТИКЕТЫ
# ================================================================
def create_ticket(ttype, uid, peer_id, text):
    tid = cfg.get("next_ticket_id", 1)
    cfg["tickets"][str(tid)] = {
        "type": ttype, "from": uid, "peer_id": peer_id,
        "text": text, "status": "open",
        "answer": "", "answered_by": 0, "answered_at": 0,
        "created_at": int(time.time()),
    }
    cfg["next_ticket_id"] = tid + 1
    save_cfg(cfg)
    return tid

def tickets_list_text(only_open=True):
    t = cfg.get("tickets", {})
    if not t:
        return "📭 Тикетов нет."
    lines = ["🎫 Список тикетов:", ""]
    n = 0
    for tid, info in sorted(t.items(), key=lambda x: int(x[0])):
        if only_open and info.get("status") != "open": continue
        emoji = "💡" if info.get("type") == "offer" else "❓"
        status = "🟢 открыт" if info.get("status") == "open" else "✅ отвечен"
        lines.append(
            f"#{tid} {emoji} [{status}] от {mention(info['from'])} "
            f"— {fmt_dt(info.get('created_at', 0))}\n   {info['text'][:120]}"
        )
        n += 1
    if n == 0:
        return "📭 Открытых тикетов нет."
    return "\n".join(lines)

def answer_ticket(tid, admin_id, answer_text):
    tickets = cfg.get("tickets", {})
    info = tickets.get(str(tid))
    if not info:
        return False, "Тикет не найден."
    if info.get("status") == "answered":
        return False, "На этот тикет уже отвечено."
    info["status"] = "answered"
    info["answer"] = answer_text
    info["answered_by"] = admin_id
    info["answered_at"] = int(time.time())
    save_cfg(cfg)
    who = "жалобу/вопрос" if info["type"] == "report" else "предложение идеи"
    send_dm(info["from"],
        f"✅ Ответ на ваш тикет #{tid} ({who}):\n\n"
        f"Ваше сообщение: {info['text'][:200]}\n\n"
        f"Ответ: {answer_text}\n\n— Администрация")
    try:
        send(info["peer_id"],
             f"🎫 Ответ на тикет #{tid} от {mention(info['from'])}:\n\n"
             f"❓ {info['text'][:200]}\n\n✅ {answer_text}")
    except Exception:
        pass
    return True, "OK"

# ================================================================
# ИНФО ПОЛЬЗОВАТЕЛЯ И СОСТАВ АДМИНИСТРАЦИИ
# ================================================================
def user_info_text(uid, peer_id):
    role = role_display(uid, peer_id)
    lines = [f"ℹ️ {mention(uid, peer_id)}:", f"• Роль: {role}"]
    c = get_chat(peer_id) if is_chat(peer_id) else None
    if c:
        lines.append(f"• Ник: {c.get('nicknames',{}).get(str(uid), '—')}")
        mu_info = c.get("muted", {}).get(str(uid))
        mu_until = get_mute_until(mu_info)
        if mu_until and mu_until > time.time():
            lines.append(f"• 🔇 Мут ещё: {fmt_time(mu_until - time.time())}")
        else:
            lines.append("• 🔇 Мут: нет")
        w = c.get("warns", {}).get(str(uid), 0)
        lines.append(f"• ⚠️ Предупреждения: {w}/{cfg['max_warns']}")
        b = c.get("banned", {}).get(str(uid))
        if b: lines.append(f"• 🚫 Бан: {'🌐' if b.get('global') else '🏠'} ({b.get('reason','—')})")
        else: lines.append("• 🚫 Бан: нет")
    return "\n".join(lines)

def build_staff_text(peer_id):
    c = get_chat(peer_id) if is_chat(peer_id) else None
    by_role = {}
    if c:
        for uid, rk in c.get("staff", {}).items():
            by_role.setdefault(rk, []).append(uid)
    uids_fetch = [cfg["global_owner"]]
    if c:
        if c.get("owner"): uids_fetch.append(c["owner"])
        uids_fetch += [int(u) for u in c.get("staff", {}).keys()]
    prefetch_names(uids_fetch)
    lines = ["👮 Состав администрации:", "",
             "🌐 Главный владелец:", f"— {mention(cfg['global_owner'], peer_id)}", "",
             "👑 Владелец беседы:"]
    lines.append(f"— {mention(c['owner'], peer_id)}" if c and c.get("owner") else "— (не назначен, /claim)")
    lines.append("")
    for key, role in sorted(cfg["roles"].items(), key=lambda x: -x[1].get("priority", 0)):
        lines.append(f"{role['name']}:")
        us = by_role.get(key, [])
        if us:
            for u in us: lines.append(f"— {mention(u, peer_id)}")
        else:
            lines.append("— ")
        lines.append("")
    return "\n".join(lines).rstrip()

# ================================================================
# МАФИЯ
# ================================================================
MAFIA_MIN_PLAYERS = 4
MAFIA_LOBBY_SECONDS = 60
MAFIA_DAY_DISCUSSION = 120
MAFIA_VOTE_SECONDS = 60
MAFIA_JOIN_WORDS = {"вступить", "я", "+", "играю", "в игре", "мафия", "го", "за"}

ROLE_MAFIA = "🔫 Мафия"
ROLE_DOCTOR = "💉 Доктор"
ROLE_POLICE = "👮 Полицейский"
ROLE_WAITER = "🍽️ Официант"
ROLE_CIVILIAN = "👤 Мирный житель"
NIGHT_STEPS = ["mafia", "doctor", "police", "waiter"]

GAMES = {}
GAMES_LOCK = threading.Lock()

def mafia_start(peer_id, host_id):
    with GAMES_LOCK:
        if peer_id in GAMES:
            send(peer_id, "⚠️ Игра уже идёт."); return
        GAMES[peer_id] = {
            "phase": "lobby", "lobby_players": [host_id], "players": {},
            "alive": set(), "host": host_id,
            "lobby_deadline": time.time() + MAFIA_LOBBY_SECONDS,
            "night_step_idx": 0, "night_step": None, "night_actions": {},
            "day_deadline": 0, "vote_deadline": 0, "votes": {},
            "waiter_block": None, "round": 0, "_alive_order": [],
        }
    send(peer_id, f"""🎭 МАФИЯ 🎭
Вступить — напишите «вступить» (или «я», «+»).
Минимум: {MAFIA_MIN_PLAYERS}. Сбор: {MAFIA_LOBBY_SECONDS} сек.

Участники:
1. {get_vk_name(host_id)}""")

def mafia_join(peer_id, uid):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "lobby": return
    if uid in g["lobby_players"]: return
    g["lobby_players"].append(uid)
    lines = [f"✅ {get_vk_name(uid)} вступил. Участники ({len(g['lobby_players'])}):"]
    for i, u in enumerate(g["lobby_players"], 1):
        lines.append(f"{i}. {get_vk_name(u)}")
    send(peer_id, "\n".join(lines))

def mafia_start_game(peer_id):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "lobby": return
    players = list(g["lobby_players"])
    if len(players) < MAFIA_MIN_PLAYERS:
        send(peer_id, f"❌ Мало игроков ({len(players)}/{MAFIA_MIN_PLAYERS}).")
        GAMES.pop(peer_id, None); return
    n = len(players)
    mafia_count = 2 if n >= 7 else 1
    pool = [ROLE_MAFIA] * mafia_count + [ROLE_DOCTOR, ROLE_POLICE]
    if n >= 5: pool.append(ROLE_WAITER)
    while len(pool) < n: pool.append(ROLE_CIVILIAN)
    random.shuffle(pool)
    roles = dict(zip(players, pool))
    g["players"] = roles; g["alive"] = set(players); g["round"] = 0; g["phase"] = "night"
    names_all = "\n".join(f"— {get_vk_name(u)}" for u in players)
    for uid, role in roles.items():
        send_dm(uid, f"🎭 Ваша роль: {role}\n\nИграют:\n{names_all}")
    send(peer_id, f"🎭 Игра началась! Игроков: {n}.")
    mafia_start_night(peer_id)

def mafia_start_night(peer_id):
    g = GAMES.get(peer_id)
    if not g: return
    if not g["alive"]: GAMES.pop(peer_id, None); return
    g["phase"] = "night"; g["round"] += 1
    g["night_step_idx"] = 0; g["night_step"] = None
    g["night_actions"] = {}; g["waiter_block"] = None; g["votes"] = {}
    send(peer_id, f"🌃 Раунд {g['round']}. Город засыпает...")
    mafia_next_step(peer_id)

def _alive_list_str(g):
    alive = sorted(g["alive"]); g["_alive_order"] = alive
    return "\n".join(f"{i+1}. {get_vk_name(u)}" for i, u in enumerate(alive))

def mafia_next_step(peer_id):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "night": return
    roles_present = set(g["players"][u] for u in g["alive"])
    while g["night_step_idx"] < len(NIGHT_STEPS):
        step = NIGHT_STEPS[g["night_step_idx"]]; g["night_step_idx"] += 1
        rn = {"mafia": ROLE_MAFIA, "doctor": ROLE_DOCTOR,
              "police": ROLE_POLICE, "waiter": ROLE_WAITER}[step]
        if rn in roles_present:
            g["night_step"] = step
            mafia_announce_step(peer_id, step); return
    mafia_resolve_night(peer_id)

def mafia_announce_step(peer_id, step):
    g = GAMES.get(peer_id)
    if not g: return
    lst = _alive_list_str(g)
    if step == "mafia":
        send(peer_id, "🌃 Город засыпает, просыпается 🔫 Мафия...")
        for u, r in g["players"].items():
            if r == ROLE_MAFIA and u in g["alive"]:
                send_dm(u, f"🔫 Вы — Мафия. Кого убить:\n\n{lst}\n\nНомер.")
    elif step == "doctor":
        send(peer_id, "💉 Просыпается Доктор...")
        for u, r in g["players"].items():
            if r == ROLE_DOCTOR and u in g["alive"]:
                send_dm(u, f"💉 Кого спасти?\n\n{lst}\n\nНомер.")
    elif step == "police":
        send(peer_id, "👮 Просыпается Полицейский...")
        for u, r in g["players"].items():
            if r == ROLE_POLICE and u in g["alive"]:
                send_dm(u, f"👮 Кого проверить?\n\n{lst}\n\nНомер.")
    elif step == "waiter":
        send(peer_id, "🍽️ Просыпается Официант...")
        for u, r in g["players"].items():
            if r == ROLE_WAITER and u in g["alive"]:
                send_dm(u, f"🍽️ Кого лишить голоса?\n\n{lst}\n\nНомер.")

def mafia_parse_target(text, g):
    t = text.strip()
    m = re.search(r"\[id(\d+)\|", t)
    if m:
        uid = int(m.group(1))
        if uid in g["alive"]: return uid
    m = re.search(r"@id(\d+)", t)
    if m:
        uid = int(m.group(1))
        if uid in g["alive"]: return uid
    m = re.match(r"^(\d+)$", t)
    if m:
        n = int(m.group(1))
        order = g.get("_alive_order") or sorted(g["alive"])
        if 1 <= n <= len(order): return order[n-1]
    return None

def mafia_handle_night_dm(uid, text, peer_id):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "night": return False
    step = g["night_step"]
    if not step: return False
    need = {"mafia": ROLE_MAFIA, "doctor": ROLE_DOCTOR,
            "police": ROLE_POLICE, "waiter": ROLE_WAITER}[step]
    if g["players"].get(uid) != need or uid not in g["alive"]: return False
    if step in g["night_actions"]:
        send_dm(uid, "Вы уже сделали выбор."); return True
    target = mafia_parse_target(text, g)
    if not target:
        send_dm(uid, "⚠️ Напишите номер игрока."); return True
    g["night_actions"][step] = target
    send_dm(uid, f"✅ Выбрано: {get_vk_name(target)}")
    if step == "police":
        if g["players"].get(target) == ROLE_MAFIA:
            send_dm(uid, f"✅ Угадали! {get_vk_name(target)} — мафия.")
        else:
            send_dm(uid, f"❌ {get_vk_name(target)} не мафия.")
    ann = {"mafia": "🔫 Мафия сделала выбор.",
           "doctor": "💉 Доктор сделал выбор.",
           "police": "👮 Полицейский сделал выбор.",
           "waiter": "🍽️ Официант сделал выбор."}
    send(peer_id, ann.get(step, ""))
    g["night_step"] = None
    mafia_next_step(peer_id)
    return True

def mafia_resolve_night(peer_id):
    g = GAMES.get(peer_id)
    if not g: return
    send(peer_id, "🌅 Город просыпается...")
    mt = g["night_actions"].get("mafia"); dt = g["night_actions"].get("doctor")
    if mt:
        if dt == mt:
            send(peer_id, "☀️ Никого не убили — Доктор спас жертву!")
        else:
            g["alive"].discard(mt)
            role = g["players"][mt]
            send(peer_id, f"💀 Убит {get_vk_name(mt)}. Роль: {role}")
    else:
        send(peer_id, "☀️ Никто не погиб.")
    g["waiter_block"] = g["night_actions"].get("waiter")
    if mafia_check_win(peer_id): return
    g["phase"] = "day"; g["day_deadline"] = time.time() + MAFIA_DAY_DISCUSSION
    send(peer_id, f"🌞 День! {MAFIA_DAY_DISCUSSION} сек на обсуждение.")

def mafia_check_win(peer_id):
    g = GAMES.get(peer_id)
    if not g: return True
    if not g["alive"]:
        mafia_end_game(peer_id, "🎭 Ничья."); return True
    am = sum(1 for u in g["alive"] if g["players"][u] == ROLE_MAFIA)
    ac = len(g["alive"]) - am
    if am == 0:
        mafia_end_game(peer_id, "🎉 Город победил!"); return True
    if am >= ac:
        mafia_end_game(peer_id, "🔫 Мафия победила!"); return True
    return False

def mafia_start_voting(peer_id):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "day": return
    g["phase"] = "voting"; g["votes"] = {}; g["vote_deadline"] = time.time() + MAFIA_VOTE_SECONDS
    send(peer_id, "🗳️ Голосование! Списки в ЛС.")
    alive = sorted(g["alive"]); g["_alive_order"] = alive
    names = "\n".join(f"{i+1}. {get_vk_name(u)}" for i, u in enumerate(alive))
    for u in alive:
        note = "\n⚠️ Вы лишены голоса." if g.get("waiter_block") == u else ""
        send_dm(u, f"🗳️ Голосуйте:\n\n{names}\n\nНомер или 'пропуск'.{note}")

def mafia_handle_vote_dm(uid, text, peer_id):
    g = GAMES.get(peer_id)
    if not g or g["phase"] != "voting": return False
    if uid not in g["alive"]: return False
    if uid in g["votes"]:
        send_dm(uid, "Уже голосовали."); return True
    t = text.strip().lower()
    if t in ("пропуск", "skip", "пас", "0"):
        g["votes"][uid] = "skip"; send_dm(uid, "✅ Пропуск."); return True
    target = mafia_parse_target(text, g)
    if not target:
        send_dm(uid, "⚠️ Номер или 'пропуск'."); return True
    if target == uid:
        send_dm(uid, "⚠️ Не за себя."); return True
    g["votes"][uid] = target
    send_dm(uid, f"✅ Голос за {get_vk_name(target)}."); return True

def mafia_tally_votes(peer_id):
    g = GAMES.get(peer_id)
    if not g: return
    g["phase"] = "ended"
    counts = {}; skip = 0
    for voter, tgt in g["votes"].items():
        if voter == g.get("waiter_block"): continue
        if tgt == "skip": skip += 1
        else: counts[tgt] = counts.get(tgt, 0) + 1
    if not counts:
        send(peer_id, f"🗳️ Все воздержались. Никто не исключён.")
        mafia_start_night(peer_id); return
    mx = max(counts.values())
    top = [u for u, c in counts.items() if c == mx]
    if len(top) > 1:
        names = ", ".join(get_vk_name(u) for u in top)
        send(peer_id, f"🗳️ Ничья ({mx}): {names}.")
        mafia_start_night(peer_id); return
    victim = top[0]; role = g["players"][victim]
    g["alive"].discard(victim)
    if role == ROLE_MAFIA:
        send(peer_id, f"🎉 Угадали! {get_vk_name(victim)} был мафией!")
        mafia_end_game(peer_id, None)
    else:
        send(peer_id, f"❌ Не угадали. {get_vk_name(victim)} — {role}.")
        if mafia_check_win(peer_id): return
        mafia_start_night(peer_id)

def mafia_end_game(peer_id, msg):
    g = GAMES.pop(peer_id, None)
    if msg: send(peer_id, msg)
    if g:
        lines = ["🎭 Все роли:"]
        for u, r in g["players"].items():
            st = "жив" if u in g["alive"] else "мёртв"
            lines.append(f"— {get_vk_name(u)}: {r} ({st})")
        send(peer_id, "\n".join(lines))

def mafia_handle_any_dm(uid, text):
    with GAMES_LOCK: games = list(GAMES.items())
    for peer_id, g in games:
        if uid not in g.get("players", {}): continue
        if g["phase"] == "night" and mafia_handle_night_dm(uid, text, peer_id): return True
        elif g["phase"] == "voting" and mafia_handle_vote_dm(uid, text, peer_id): return True
    return False

def mafia_ticker():
    while True:
        time.sleep(1)
        try:
            now = time.time()
            for peer_id in list(GAMES.keys()):
                g = GAMES.get(peer_id)
                if not g: continue
                if g["phase"] == "lobby" and now >= g["lobby_deadline"]:
                    mafia_start_game(peer_id)
                elif g["phase"] == "day" and now >= g["day_deadline"]:
                    mafia_start_voting(peer_id)
                elif g["phase"] == "voting" and now >= g["vote_deadline"]:
                    mafia_tally_votes(peer_id)
        except Exception as e:
            print(f"[ticker] {e}")

threading.Thread(target=mafia_ticker, daemon=True).start()

# ================================================================
# СПРАВКА
# ================================================================
HELP_TEXT = """📋 Команды бота:

— Для всех —
/help /info @user /стата /staff /role /claim
/offer <текст> — предложить идею
/report <текст> — вопрос или жалоба

— Персонал беседы —
/warn /unwarn /mute /unmute /nick /rnick /clear /banlist
/tickets — открытые тикеты
/adt <номер> <ответ> — ответить на тикет

— Администрация —
/kick /ban /unban /gban /ungban

— Владелец беседы —
/addstaff /removestaff /setrole /setowner
/setwarns N / /setmutetime N / /setlog / /unsetlog / /loginfo

— Ивенты —
/ивент — список / /ивент <название> / /ивент мафия / /ивент рандом

— Только для Главного владельца —
/объявление / /newrole / /delrole
/createivent <название> | <награда> | <требование>

🕐 Мут: {default} мин | ⚠️ Лимит: {max}
"""

EVENTS_LIST = {
    "рулетка": "🎰 Рулетка",
    "дуэль": "⚔️ Дуэль",
    "лотерея": "🎟️ Лотерея",
    "хэллоуин": "🎃 Хэллоуин",
    "новыйгод": "🎄 Новый год",
    "мафия": "🎭 Мафия (мин. 4)",
}
EVENT_TITLES = ["🏆 Победитель", "⚔️ Воин", "🎟️ Счастливчик", "🎄 Снегурочка",
                "🌟 Звезда", "👑 Король", "🎩 Магистр", "🍀 Удачливый",
                "🔥 Горячая штучка", "🐉 Дракон", "🦊 Хитрец", "🌸 Красотка"]

# ================================================================
# ИВЕНТЫ
# ================================================================
def get_chat_members(peer_id):
    try:
        return [m["member_id"] for m in api.messages.getConversationMembers(peer_id=peer_id)["items"]
                if m["member_id"] > 0 and m["member_id"] != BOT_ID]
    except Exception:
        return []

def event_roulette(peer_id):
    c = get_chat(peer_id); users = get_chat_members(peer_id)
    if not users: send(peer_id, "❌ Нет участников."); return
    w = random.choice(users); eff = random.choice(["title", "mute", "warn", "nothing"])
    if eff == "title":
        t = random.choice(EVENT_TITLES); c["nicknames"][str(w)] = t; save_cfg(cfg)
        send(peer_id, f"🎰 Рулетка!\n{mention(w, peer_id)} → {t}")
    elif eff == "mute":
        c["muted"][str(w)] = {"until": time.time() + 300, "last_dm": 0}; save_cfg(cfg)
        send(peer_id, f"🎰 Рулетка!\n{mention(w, peer_id)} — 🔇 5 мин.")
        mute_notify_dm(w, 5)
    elif eff == "warn":
        wr = c["warns"]; wr[str(w)] = wr.get(str(w), 0) + 1; save_cfg(cfg)
        send(peer_id, f"🎰 Рулетка!\n{mention(w, peer_id)} — ⚠️ ({wr[str(w)]}/{cfg['max_warns']}).")
    else:
        send(peer_id, f"🎰 Рулетка!\n{mention(w, peer_id)} — ничего 😅")

def event_duel(peer_id):
    c = get_chat(peer_id); users = get_chat_members(peer_id)
    if len(users) < 2: send(peer_id, "❌ Нужно ≥ 2."); return
    a, b = random.sample(users, 2); w = random.choice([a, b]); t = random.choice(EVENT_TITLES)
    c["nicknames"][str(w)] = t; save_cfg(cfg)
    send(peer_id, f"⚔️ Дуэль!\n{mention(a, peer_id)} vs {mention(b, peer_id)}\n🏆 {mention(w, peer_id)} → {t}")

def event_lottery(peer_id):
    c = get_chat(peer_id); users = get_chat_members(peer_id)
    if len(users) < 3: send(peer_id, "❌ Нужно ≥ 3."); return
    lines = ["🎟️ Лотерея! Победители:"]
    for w in random.sample(users, 3):
        t = random.choice(EVENT_TITLES); c["nicknames"][str(w)] = t
        lines.append(f"— {mention(w, peer_id)} → {t}")
    save_cfg(cfg); send(peer_id, "\n".join(lines))

def event_halloween(peer_id):
    c = get_chat(peer_id); users = get_chat_members(peer_id)
    if not users: send(peer_id, "❌ Нет участников."); return
    v = random.choice(users)
    c["muted"][str(v)] = {"until": time.time() + 300, "last_dm": 0}; save_cfg(cfg)
    send(peer_id, f"🎃 Хэллоуин!\n{mention(v, peer_id)} → 🔇 5 мин.")
    mute_notify_dm(v, 5)

def event_newyear(peer_id):
    c = get_chat(peer_id); un = 0
    for k in list(c["muted"].keys()): del c["muted"][k]; un += 1
    users = get_chat_members(peer_id)
    if users:
        w = random.choice(users); c["nicknames"][str(w)] = "🎄 Снегурочка"; save_cfg(cfg)
        send(peer_id, f"🎄 Снято мьютов: {un}\n{mention(w, peer_id)} → 🎄 Снегурочка")
    else:
        save_cfg(cfg); send(peer_id, f"🎄 Снято мьютов: {un}")

def event_mafia(peer_id, from_id):
    if not is_chat(peer_id):
        send(peer_id, "❌ Только для беседы."); return
    mafia_start(peer_id, from_id)

def event_custom(peer_id, name):
    ev = cfg.get("custom_events", {}).get(name.lower())
    if not ev: return False
    send(peer_id,
         f"🎉 ИВЕНТ: {ev['name']}\n\n"
         f"🏆 Награда: {ev['reward']}\n"
         f"📋 Требуется: {ev['requirement']}\n\n"
         f"Организатор: [id{ev['created_by']}|...]")
    return True

EVENT_HANDLERS = {
    "рулетка": event_roulette, "дуэль": event_duel, "лотерея": event_lottery,
    "хэллоуин": event_halloween, "новыйгод": event_newyear,
}

def run_random_event(peer_id):
    ev = random.choice(list(EVENT_HANDLERS.keys()))
    send(peer_id, f"🎲 Выпал ивент: {EVENTS_LIST[ev]}")
    try: EVENT_HANDLERS[ev](peer_id)
    except Exception as e: send(peer_id, f"❌ {e}")
    return ev

# ================================================================
# ПРИВЕТСТВИЕ
# ================================================================
def handle_welcome(peer_id, action):
    if not is_chat(peer_id): return
    invited = action.get("member_id")
    if not invited or invited <= 0: return
    c = get_chat(peer_id)
    if c.get("welcome") is False: return
    if invited == BOT_ID: return
    if str(invited) in c.get("banned", {}): return
    prefetch_names([invited])
    nick = c.get("nicknames", {}).get(str(invited))
    u = f"[id{invited}|{nick}]" if nick else f"[id{invited}|{get_vk_name(invited)}]"
    send(peer_id, WELCOME_TEXT.format(user=u))

# ================================================================
# ОСНОВНОЙ ЦИКЛ
# ================================================================
def main():
    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW: continue
        msg = event.object.message
        peer_id = msg["peer_id"]; from_id = msg["from_id"]
        text = (msg.get("text") or "").strip()
        real_id = msg.get("id") or 0
        cmid = msg.get("conversation_message_id") or 0
        reply_ref = real_id if real_id > 0 else None

        if peer_id == from_id:
            mafia_handle_any_dm(from_id, text)
            continue

        preview = text[:60].replace("\n", " ")
        print(f"📨 peer={peer_id} from={from_id} id={real_id} cmid={cmid} text={preview!r}")

        if is_duplicate(peer_id, msg): continue

        action = msg.get("action")
        if action:
            atype = action.get("type")
            if atype == "chat_invite_user":
                invited = action.get("member_id")
                if invited and is_chat(peer_id):
                    c = get_chat(peer_id)
                    if str(invited) in c.get("banned", {}):
                        cid = chat_id_from_peer(peer_id)
                        if cid:
                            kick_user(cid, invited)
                            send(peer_id, f"🚫 {mention(invited, peer_id)} в бане — исключён.")
                    else:
                        handle_welcome(peer_id, action)
                continue
            if atype == "chat_kick_user":
                continue

        track_peer(peer_id)
        if from_id > 0:
            track_message(from_id, peer_id, text)

        g = GAMES.get(peer_id) if is_chat(peer_id) else None
        if g:
            if g["phase"] == "night" and from_id in g["players"] and from_id in g["alive"]:
                delete_msg(real_id, cmid, peer_id); continue
            if g["phase"] == "lobby" and text.lower().strip() in MAFIA_JOIN_WORDS:
                mafia_join(peer_id, from_id); continue

        if is_chat(peer_id):
            c = get_chat(peer_id)
            if str(from_id) in c.get("banned", {}):
                delete_msg(real_id, cmid, peer_id)
                kick_user(chat_id_from_peer(peer_id), from_id)
                continue
            muted = c.get("muted", {})
            if str(from_id) in muted:
                info = muted[str(from_id)]
                if isinstance(info, (int, float)):
                    info = {"until": info, "last_dm": 0}
                    muted[str(from_id)] = info; save_cfg(cfg)
                now = time.time()
                if info["until"] > now:
                    delete_msg(real_id, cmid, peer_id)
                    if now - info.get("last_dm", 0) > MUTE_DM_INTERVAL:
                        mute_warn_dm(from_id, info["until"] - now)
                        info["last_dm"] = now; save_cfg(cfg)
                    continue
                else:
                    mute_expired_dm(from_id)
                    del muted[str(from_id)]; save_cfg(cfg)

        if not text.startswith("/"): continue
        parts = text.split()
        cmd = parts[0][1:].lower()
        args = parts[1:]
        reply_msg = msg.get("reply_message")

        # ============ ПРОВЕРКА: СУЩЕСТВУЕТ ЛИ КОМАНДА ============
        if cmd not in ALL_COMMANDS:
            sug = suggest_command(cmd)
            if sug:
                send(peer_id,
                     f"❓ Вы наверное имели в виду /{sug}\n\n"
                     f"📋 Все команды: /help",
                     reply_to=reply_ref)
            else:
                send(peer_id,
                     f"❌ Команды «/{cmd}» не существует.\n\n"
                     f"💡 Вы можете предложить её разработчикам:\n"
                     f"/offer <описание вашей идеи>",
                     reply_to=reply_ref)
            continue

        # ============ ПУБЛИЧНЫЕ ============
        if cmd == "help":
            send(peer_id, HELP_TEXT.format(
                default=cfg["default_mute_minutes"], max=cfg["max_warns"]
            ), reply_to=reply_ref)
            continue

        if cmd == "staff":
            if not is_chat(peer_id): send(peer_id, "❌ Только для беседы.", reply_to=reply_ref); continue
            send(peer_id, build_staff_text(peer_id), reply_to=reply_ref); continue

        if cmd == "role":
            if not is_chat(peer_id): send(peer_id, "❌ Только для беседы.", reply_to=reply_ref); continue
            lines = ["🎭 Доступные роли:"]
            for k, r in sorted(cfg["roles"].items(), key=lambda x: -x[1]["priority"]):
                lines.append(f"• {r['name']} (приоритет {r['priority']})")
            lines.append("")
            lines.append("👑 Владелец беседы — через /claim")
            lines.append("🌐 Главный владелец — фиксированный")
            send(peer_id, "\n".join(lines), reply_to=reply_ref); continue

        if cmd == "info":
            t = extract_user(text, reply_msg)
            if not t: send(peer_id, "⚠ Укажи пользователя.", reply_to=reply_ref); continue
            send(peer_id, user_info_text(t, peer_id), reply_to=reply_ref); continue

        if cmd in ("стата", "stat"):
            t = extract_user(text, reply_msg) or from_id
            prefetch_names([t])
            send(peer_id, user_stats_text(t, peer_id), reply_to=reply_ref); continue

        if cmd == "offer":
            if not args:
                send(peer_id, "⚠ /offer <текст идеи>", reply_to=reply_ref); continue
            tid = create_ticket("offer", from_id, peer_id, " ".join(args))
            send(peer_id, f"💡 Идея принята! Тикет #{tid}.", reply_to=reply_ref)
            log_action(from_id, f"тикет #{tid} (offer)"); continue

        if cmd == "report":
            if not args:
                send(peer_id, "⚠ /report <текст>", reply_to=reply_ref); continue
            tid = create_ticket("report", from_id, peer_id, " ".join(args))
            send(peer_id, f"❓ Принято! Тикет #{tid}.", reply_to=reply_ref)
            log_action(from_id, f"тикет #{tid} (report)"); continue

        if cmd == "claim":
            if not is_chat(peer_id): send(peer_id, "❌ Только для беседы.", reply_to=reply_ref); continue
            c = get_chat(peer_id)
            if c.get("owner"):
                if c["owner"] == from_id: send(peer_id, "👑 Ты уже владелец.", reply_to=reply_ref)
                else: send(peer_id, f"⚠ Владелец — {mention(c['owner'], peer_id)}.", reply_to=reply_ref)
                continue
            c["owner"] = from_id; save_cfg(cfg)
            send(peer_id, f"👑 {mention(from_id, peer_id)} — Владелец беседы!"); continue

        if not can(from_id, cmd, peer_id):
            send(peer_id, "⛔ Нет прав на эту команду.", reply_to=reply_ref); continue

        # ============ ГЛОБАЛЬНЫЕ ============
        if cmd in ("объявление", "announce", "рассылка"):
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            if not args: send(peer_id, "⚠ /объявление <текст>", reply_to=reply_ref); continue
            ann = " ".join(args); ok = 0; fail = 0
            for pid in cfg.get("known_peers", []):
                try:
                    api.messages.send(peer_id=pid,
                        message=f"📢 ОБЪЯВЛЕНИЕ\n\n{ann}",
                        random_id=int(time.time() * 1000) + ok)
                    ok += 1
                except Exception: fail += 1
            send(peer_id, f"✅ Рассылка: {ok} / ошибок: {fail}", reply_to=reply_ref); continue

        if cmd == "newrole":
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            if len(args) < 2 or not args[-1].isdigit():
                send(peer_id, "⚠ /newrole <название> <0-100>", reply_to=reply_ref); continue
            pr = int(args[-1])
            if not (0 <= pr <= 100):
                send(peer_id, "⚠ 0-100", reply_to=reply_ref); continue
            name = " ".join(args[:-1]).strip(); key = name.lower()
            if key in cfg["roles"]:
                send(peer_id, f"⚠ Роль «{name}» уже есть.", reply_to=reply_ref); continue
            cfg["roles"][key] = {"name": name, "priority": pr, "commands": commands_for_priority(pr)}
            save_cfg(cfg); send(peer_id, f"✅ Роль «{name}» создана.", reply_to=reply_ref); continue

        if cmd == "delrole":
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            if not args: send(peer_id, "⚠ /delrole <название>", reply_to=reply_ref); continue
            name = " ".join(args); key = find_role_by_input(name)
            if not key:
                send(peer_id, f"⚠ Роль «{name}» не найдена.", reply_to=reply_ref); continue
            rem = 0
            for ch in cfg.get("chats", {}).values():
                for u in [x for x, r in ch.get("staff", {}).items() if r == key]:
                    del ch["staff"][u]; rem += 1
            del cfg["roles"][key]; save_cfg(cfg)
            send(peer_id, f"🗑 Роль «{name}» удалена. Снято: {rem}.", reply_to=reply_ref); continue

        if cmd == "createivent":
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            if not args:
                send(peer_id,
                     "⚠ /createivent <название> | <награда> | <требование>",
                     reply_to=reply_ref); continue
            raw = " ".join(args)
            parts_ev = [p.strip() for p in raw.split("|")]
            if len(parts_ev) < 3:
                send(peer_id, "⚠ Нужно 3 части через |", reply_to=reply_ref); continue
            name, reward, req = parts_ev[0], parts_ev[1], parts_ev[2]
            key = name.lower()
            if key in cfg.get("custom_events", {}):
                send(peer_id, f"⚠ Ивент «{name}» уже есть.", reply_to=reply_ref); continue
            cfg["custom_events"][key] = {
                "name": name, "reward": reward, "requirement": req,
                "created_by": from_id, "created_at": int(time.time()),
            }
            save_cfg(cfg)
            send(peer_id, f"✅ Ивент «{name}» создан.\n🏆 {reward}\n📋 {req}\n\nЗапуск: /ивент {name}",
                 reply_to=reply_ref); continue

        # ============ ТИКЕТЫ ============
        if cmd == "tickets":
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            send(peer_id, tickets_list_text(only_open=True), reply_to=reply_ref); continue

        if cmd == "adt":
            if len(args) < 2:
                send(peer_id, "⚠ /adt <номер> <ответ>", reply_to=reply_ref); continue
            if not args[0].isdigit():
                send(peer_id, "⚠ Номер числом.", reply_to=reply_ref); continue
            tid = args[0]; answer = " ".join(args[1:])
            ok, msg_ans = answer_ticket(tid, from_id, answer)
            send(peer_id, f"✅ Ответ на #{tid} отправлен." if ok else f"❌ {msg_ans}",
                 reply_to=reply_ref); continue

        # ============ ИВЕНТЫ ============
        if cmd in ("ивент", "event"):
            if not is_chat(peer_id):
                send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            if not args:
                lines = ["🎉 Ивенты:", ""]
                for k, v in EVENTS_LIST.items():
                    lines.append(f"• /ивент {k} — {v}")
                custom = cfg.get("custom_events", {})
                if custom:
                    lines.append("")
                    lines.append("🎨 Кастомные:")
                    for k, v in custom.items():
                        lines.append(f"• /ивент {v['name']} — 🏆 {v['reward']}")
                lines.append(""); lines.append("🎲 /ивент рандом")
                send(peer_id, "\n".join(lines), reply_to=reply_ref); continue
            ev = args[0].lower()
            if ev in ("рандом", "random", "ранд"):
                run_random_event(peer_id); continue
            if ev == "мафия":
                event_mafia(peer_id, from_id); continue
            if ev in EVENT_HANDLERS:
                send(peer_id, f"🎉 {EVENTS_LIST[ev]}")
                try: EVENT_HANDLERS[ev](peer_id)
                except Exception as e: send(peer_id, f"❌ {e}", reply_to=reply_ref)
                continue
            if event_custom(peer_id, ev): continue
            send(peer_id, f"⚠ Ивент «{ev}» не найден.", reply_to=reply_ref); continue

        # ============ УТИЛИТЫ ============
        if cmd == "loginfo":
            send(peer_id, f"📝 Лог: {cfg.get('log_peer_id') or 'не задана'}", reply_to=reply_ref); continue
        if cmd == "setlog":
            if from_id != int(cfg["global_owner"]) and not (is_chat(peer_id) and get_chat(peer_id).get("owner") == from_id):
                send(peer_id, "⛔ Нет прав.", reply_to=reply_ref); continue
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            cfg["log_peer_id"] = peer_id; save_cfg(cfg)
            send(peer_id, f"✅ Лог: {peer_id}", reply_to=reply_ref); continue
        if cmd == "unsetlog":
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            cfg["log_peer_id"] = 0; save_cfg(cfg)
            send(peer_id, "✅ Лог отключён.", reply_to=reply_ref); continue
        if cmd == "setwarns":
            if from_id != int(cfg["global_owner"]) and not (is_chat(peer_id) and get_chat(peer_id).get("owner") == from_id):
                send(peer_id, "⛔ Нет прав.", reply_to=reply_ref); continue
            if not args or not args[0].isdigit(): send(peer_id, "⚠ /setwarns 3", reply_to=reply_ref); continue
            cfg["max_warns"] = int(args[0]); save_cfg(cfg)
            send(peer_id, f"✅ Лимит: {cfg['max_warns']}", reply_to=reply_ref); continue
        if cmd == "setmutetime":
            if from_id != int(cfg["global_owner"]) and not (is_chat(peer_id) and get_chat(peer_id).get("owner") == from_id):
                send(peer_id, "⛔ Нет прав.", reply_to=reply_ref); continue
            if not args or not args[0].isdigit(): send(peer_id, "⚠ /setmutetime 30", reply_to=reply_ref); continue
            cfg["default_mute_minutes"] = int(args[0]); save_cfg(cfg)
            send(peer_id, f"✅ Мут: {cfg['default_mute_minutes']} мин", reply_to=reply_ref); continue
        if cmd == "banlist":
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            b = get_chat(peer_id).get("banned", {})
            if not b: send(peer_id, "📭 Пусто.", reply_to=reply_ref); continue
            lines = ["🚫 Забаненные:"]
            for u, info in b.items(): lines.append(f"• {mention(u, peer_id)} — {info.get('reason','—')}")
            send(peer_id, "\n".join(lines), reply_to=reply_ref); continue
        if cmd == "clear":
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            if not args or not args[0].isdigit(): send(peer_id, "⚠ /clear 10", reply_to=reply_ref); continue
            n = min(int(args[0]), 100)
            if n <= 0: send(peer_id, "⚠ N > 0", reply_to=reply_ref); continue
            try:
                hist = api.messages.getHistory(peer_id=peer_id, count=n, rev=1)["items"]
                ids = [str(m["id"]) for m in hist if m["from_id"] != BOT_ID and m.get("id")]
                if not ids: send(peer_id, "ℹ Нечего.", reply_to=reply_ref); continue
                api.messages.delete(message_ids=",".join(ids), delete_for_all=1)
                send(peer_id, f"🧹 Удалено: {len(ids)}", reply_to=reply_ref)
            except Exception as e: send(peer_id, f"❌ {e}", reply_to=reply_ref)
            continue

        # nick
        if cmd == "nick":
            m = re.search(r"\[id(\d+)\|", text)
            tid = int(m.group(1)) if m else (reply_msg.get("from_id") if reply_msg else None)
            if tid is None:
                tid = from_id; nn = " ".join(args).strip()
            else:
                parts_n = [a for a in args if not re.match(r"\[id\d+\|", a) and not re.match(r"@id\d+", a)]
                nn = " ".join(parts_n).strip()
            if not nn: send(peer_id, "⚠ /nick <ник>", reply_to=reply_ref); continue
            if len(nn) > 32: send(peer_id, "⚠ Ник ≤ 32.", reply_to=reply_ref); continue
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            get_chat(peer_id)["nicknames"][str(tid)] = nn; save_cfg(cfg)
            send(peer_id, f"✅ Ник: {nn}", reply_to=reply_ref); continue
        if cmd == "rnick":
            m = re.search(r"\[id(\d+)\|", text)
            tid = int(m.group(1)) if m else (reply_msg.get("from_id") if reply_msg else None)
            if tid is None: tid = from_id
            if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue
            c = get_chat(peer_id); rem = c["nicknames"].pop(str(tid), None); save_cfg(cfg)
            send(peer_id, "✅ Ник снят." if rem else "ℹ Ника нет.", reply_to=reply_ref); continue

        # ============ С TARGET ============
        target = extract_user(text, reply_msg)
        if not target: send(peer_id, "⚠ Укажи пользователя.", reply_to=reply_ref); continue
        if target == from_id: send(peer_id, "🤔 Нельзя к себе.", reply_to=reply_ref); continue
        if int(target) == int(cfg["global_owner"]) and from_id != int(cfg["global_owner"]):
            send(peer_id, "🌐 Нельзя трогать Главного владельца.", reply_to=reply_ref); continue
        if not is_chat(peer_id): send(peer_id, "❌ Только в беседе.", reply_to=reply_ref); continue

        c = get_chat(peer_id); cid = chat_id_from_peer(peer_id)

        if cmd == "setowner":
            if from_id != int(cfg["global_owner"]):
                send(peer_id, "⛔ Только Главный владелец.", reply_to=reply_ref); continue
            c["owner"] = target; save_cfg(cfg)
            send(peer_id, f"👑 {mention(target, peer_id)} — Владелец беседы.", reply_to=reply_ref); continue
        if cmd == "ban":
            reason = " ".join(args) if args else "без причины"
            ok, err = kick_user(cid, target)
            if not ok: send(peer_id, f"❌ {err}", reply_to=reply_ref); continue
            c["banned"][str(target)] = {"reason": reason, "by": from_id,
                                         "at": int(time.time()), "global": False}
            save_cfg(cfg)
            send(peer_id, f"🔨 {mention(target, peer_id)} забанен. {reason}", reply_to=reply_ref)
        elif cmd == "unban":
            rem = c["banned"].pop(str(target), None); save_cfg(cfg)
            send(peer_id, "✅ Разбанен." if rem else "ℹ Не в бане.", reply_to=reply_ref)
        elif cmd == "gban":
            reason = " ".join(args) if args else "без причины"; kicked = 0
            for pid in cfg.get("known_peers", []):
                c2 = chat_id_from_peer(pid)
                if not c2: continue
                ok, _ = kick_user(c2, target)
                if ok: kicked += 1
            for ch in cfg.get("chats", {}).values():
                ch["banned"][str(target)] = {"reason": reason, "by": from_id,
                                              "at": int(time.time()), "global": True}
            save_cfg(cfg)
            send(peer_id, f"🌐 Глобан {mention(target, peer_id)}. Кикнут в {kicked}.", reply_to=reply_ref)
        elif cmd == "ungban":
            rem = 0
            for ch in cfg.get("chats", {}).values():
                i = ch["banned"].get(str(target))
                if i and i.get("global"):
                    del ch["banned"][str(target)]; rem += 1
            save_cfg(cfg)
            send(peer_id, f"✅ Снят глобан ({rem})." if rem else "ℹ Не в глобане.", reply_to=reply_ref)
        elif cmd == "kick":
            ok, err = kick_user(cid, target)
            send(peer_id, "👢 Исключён." if ok else f"❌ {err}", reply_to=reply_ref)
        elif cmd == "mute":
            minutes = cfg["default_mute_minutes"]
            if args and args[0].isdigit():
                minutes = int(args[0])
                if minutes <= 0: minutes = cfg["default_mute_minutes"]
            until = time.time() + minutes * 60
            c["muted"][str(target)] = {"until": until, "last_dm": time.time()}
            save_cfg(cfg)
            send(peer_id, f"🔇 {mention(target, peer_id)} в муте {minutes} мин.", reply_to=reply_ref)
            mute_notify_dm(target, minutes)
        elif cmd == "unmute":
            rem = c["muted"].pop(str(target), None); save_cfg(cfg)
            if rem:
                send(peer_id, f"🔊 {mention(target, peer_id)} размьючен.", reply_to=reply_ref)
                send_dm(target, "🔊 Ваш мут снят.")
            else:
                send(peer_id, "ℹ Не в муте.", reply_to=reply_ref)
        elif cmd == "warn":
            reason = " ".join(args) if args else "без причины"
            wr = c["warns"]; wr[str(target)] = wr.get(str(target), 0) + 1; cnt = wr[str(target)]
            save_cfg(cfg)
            send(peer_id, f"⚠ {mention(target, peer_id)} — ({cnt}/{cfg['max_warns']}). {reason}",
                 reply_to=reply_ref)
            if cnt >= cfg["max_warns"]:
                until = time.time() + 3600
                c["muted"][str(target)] = {"until": until, "last_dm": time.time()}
                save_cfg(cfg)
                send(peer_id, f"🔇 Лимит — {mention(target, peer_id)} в муте 60 мин.", reply_to=reply_ref)
                mute_notify_dm(target, 60)
        elif cmd == "unwarn":
            c["warns"].pop(str(target), None); save_cfg(cfg)
            send(peer_id, "✅ Снято.", reply_to=reply_ref)
        elif cmd in ("addstaff", "setrole"):
            if from_id != int(cfg["global_owner"]) and c.get("owner") != from_id:
                send(peer_id, "⛔ Нет прав.", reply_to=reply_ref); continue
            ri = " ".join(args).strip(); rk = find_role_by_input(ri)
            if not rk:
                avail = ", ".join(v["name"] for v in cfg["roles"].values())
                send(peer_id, f"⚠ Роль «{ri}» не найдена.\nЕсть: {avail}", reply_to=reply_ref); continue
            c["staff"][str(target)] = rk; save_cfg(cfg)
            send(peer_id, f"✅ {mention(target, peer_id)} → {cfg['roles'][rk]['name']}.", reply_to=reply_ref)
        elif cmd == "removestaff":
            if from_id != int(cfg["global_owner"]) and c.get("owner") != from_id:
                send(peer_id, "⛔ Нет прав.", reply_to=reply_ref); continue
            if str(target) == str(cfg["global_owner"]):
                send(peer_id, "🌐 Нельзя.", reply_to=reply_ref); continue
            rem = c["staff"].pop(str(target), None); save_cfg(cfg)
            if rem:
                rname = cfg["roles"].get(rem, {}).get("name", rem)
                send(peer_id, f"❌ Снят с «{rname}».", reply_to=reply_ref)
            else:
                send(peer_id, "ℹ Без роли.", reply_to=reply_ref)

# ================================================================
if __name__ == "__main__":
    print(f"✅ VK Бот 4.2 запущен (PID={os.getpid()})")
    print(f"   Токен: {'*' * 20}{TOKEN[-8:] if len(TOKEN) > 8 else ''}")
    print(f"   Группа: {GROUP_ID}")
    print(f"   Владелец: {GLOBAL_OWNER_ID}")
    print("   Жду сообщений...\n")
    try:
        while True:
            try: main()
            except KeyboardInterrupt: print("\n⏹ Остановлено."); break
            except Exception as e:
                print(f"⚠ Ошибка: {e}. Рестарт через 5 сек..."); time.sleep(5)
    finally:
        try: os.remove(PID_FILE)
        except Exception: pass
