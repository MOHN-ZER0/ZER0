"""
⚡ نظام المستويات والتفاعل (نسخة مصلّحة ومحسّنة)

ملاحظات مهمة:
- لكل عضو دلوقتي 3 مستويات منفصلة تماماً: نصي / صوتي / رياكشن (كل واحد له XP وليفل لوحده).
- البيانات القديمة بتتحول أوتوماتيك أول تشغيل (النصي = الـ xp القديم - الصوتي - الرياكشن).
- مفيش أي رسالة ترقية أو لوج بتتبعت إلا لو حددت القنوات من لوحة التحكم.
- التصفير اليومي/الأسبوعي/الشهري الساعة 12 ظهراً بتوقيت LEVELS_TZ (الافتراضي Africa/Cairo) في ملف .env.
- محتاج Intents: members + message_content + voice_states.
"""
import asyncio
import calendar
import datetime
import logging
import os
import random
import re
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError

load_dotenv()
log = logging.getLogger("levels")

try:
    from zoneinfo import ZoneInfo
    LEVELS_TZ = ZoneInfo(os.getenv("LEVELS_TZ", "Africa/Cairo"))
except Exception:  # لو مكتبة tzdata مش موجودة على ويندوز
    LEVELS_TZ = datetime.timezone(datetime.timedelta(hours=2))

# ==============================================================================
# ⚙️ الثوابت
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Levels_DB"

COLOR_DARK = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_BLUE = 0x3498DB

TYPES = ("text", "voice", "reaction")
PERIODS = ("day", "week", "month")
TYPE_LABEL = {"text": "النصي 💬", "voice": "الصوتي 🎙️", "reaction": "الرياكشن ⭐"}
REQ_LABEL = {"text": "نصي 💬", "voice": "صوتي 🎙️", "reaction": "ريأكشن 😄", "all": "جميع التفاعلات 🌐"}
PERIOD_LABEL = {"all": "العام", "day": "اليومي", "week": "الأسبوعي", "month": "الشهري"}

SETTINGS_TTL = 120          # ثواني: مدة كاش الإعدادات
SHORTCUT_COOLDOWN = 5       # ثواني بين استخدام الاختصارات
INACTIVITY_DAYS = 5
RESET_HOUR = 12
PER_PAGE = 5

# ==============================================================================
# 💾 قاعدة البيانات
# ==============================================================================
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None


def _col(name: str):
    return _db[name] if _db is not None else None


settings_col = _col("server_settings")
user_stats_col = _col("user_stats")
role_rewards_col = _col("role_rewards")
ignored_roles_col = _col("ignored_roles")
ignored_channels_col = _col("ignored_channels")
ignored_voice_col = _col("ignored_voice")
role_multipliers_col = _col("role_multipliers")
user_multipliers_col = _col("user_multipliers")
channel_multipliers_col = _col("channel_multipliers")
meta_col = _col("levels_meta")

DEFAULT_SETTINGS = {
    "status": 1,
    "announcement_channel": None,
    "logs_channel": None,
    "msg_type": "text",
    "level_message": "يا هلا يا {user}! لقد صعدت إلى المستوى {level} بنجاح، استمر في تفاعلك الجامد!",
    "level_embed_title": "♦ ترقية إلى المستوى [{level}]",
    "level_image": None,
    "dm_notifications": 0,
    "text_xp_enabled": 1,
    "min_text_xp": 5,
    "max_text_xp": 45,
    "text_cooldown": 60,
    "voice_xp_enabled": 1,
    "min_voice_xp": 2,
    "max_voice_xp": 5,
    "reaction_xp_enabled": 0,
    "min_reaction_xp": 2,
    "max_reaction_xp": 5,
    "reaction_cooldown": 30,
    "event_multiplier": 1.0,
    "event_type": "all",
    "event_end_timestamp": 0,
    "event_target_roles": "all",
    "periodic_reward_role": None,
    "periodic_type": "week",
    "inactivity_decay_enabled": 0,
    "shortcut_level": "l",
    "shortcut_top": "t",
    "shortcut_rewards": "r",
}


def _new_user_defaults() -> dict:
    d: dict[str, Any] = {"messages": 0, "voice_minutes": 0, "last_active_timestamp": 0}
    for t in TYPES:
        d[f"{t}_xp"] = 0
        d[f"{t}_level"] = 0
        for p in PERIODS:
            d[f"{p}_{t}_xp"] = 0
    return d


NEW_USER_DEFAULTS = _new_user_defaults()


async def run_db(fn, *args, **kwargs):
    """بيشغل عمليات pymongo (المتزامنة) في thread عشان ما تعطلش البوت."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ==============================================================================
# 🧮 حسابات المستويات والوقت
# ==============================================================================
def xp_field(type_: str, period: str = "all") -> str:
    return f"{type_}_xp" if period in ("all", None) else f"{period}_{type_}_xp"


def xp_for_next(level: int) -> int:
    """الـ XP التراكمي المطلوب للوصول من المستوى الحالي للي بعده (نفس المعادلة القديمة)."""
    return int((level + 1) * 300 + (level ** 1.2 * 120))


def level_from_xp(xp: int) -> int:
    lvl = 0
    while lvl < 1000 and xp >= xp_for_next(lvl):
        lvl += 1
    return lvl


def level_bounds(level: int) -> tuple[int, int]:
    prev = xp_for_next(level - 1) if level > 0 else 0
    return prev, xp_for_next(level)


def local_now() -> datetime.datetime:
    return datetime.datetime.now(LEVELS_TZ)


def period_key(period: str, now: Optional[datetime.datetime] = None) -> str:
    """مفتاح الفترة الحالية: بيتغير لحظة التصفير (12 ظهراً)."""
    now = now or local_now()
    if period == "day":
        return (now - datetime.timedelta(hours=RESET_HOUR)).date().isoformat()
    if period == "week":  # الأسبوع بيبدأ الجمعة 12 ظهراً
        shifted = (now - datetime.timedelta(hours=RESET_HOUR)).date()
        return str((shifted - datetime.date(2000, 1, 7)).days // 7)
    shifted = now + datetime.timedelta(hours=RESET_HOUR)  # الشهر بيتصفر آخر يوم 12 ظهراً
    return f"{shifted.year}-{shifted.month:02d}"


def next_reset(period: str, now: Optional[datetime.datetime] = None) -> datetime.datetime:
    now = now or local_now()
    noon = now.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    if period == "day":
        return noon if now < noon else noon + datetime.timedelta(days=1)
    if period == "week":
        target = noon + datetime.timedelta(days=(4 - now.weekday()) % 7)
        return target if now < target else target + datetime.timedelta(days=7)

    def last_day_noon(y: int, m: int) -> datetime.datetime:
        return datetime.datetime(y, m, calendar.monthrange(y, m)[1], RESET_HOUR, tzinfo=now.tzinfo)

    target = last_day_noon(now.year, now.month)
    if now >= target:
        y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        target = last_day_noon(y, m)
    return target


def format_remaining(seconds: int) -> str:
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} يوم")
    parts.append(f"{hours} ساعة")
    parts.append(f"{minutes} دقيقة")
    return " و ".join(parts)


# ==============================================================================
# 🧰 دوال مساعدة عامة
# ==============================================================================
def clip(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def ok_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_GREEN)


def err_embed(description: str, title: str = "❌ خطأ") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_RED)


_ID_RE = re.compile(r"\d{15,20}")
_URL_RE = re.compile(r"^https?://\S{3,2000}$")
_TASHKEEL_RE = re.compile("[\u064B-\u0652\u0640]")


def parse_ids(text: str) -> list[int]:
    return [int(x) for x in _ID_RE.findall(text or "")]


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def normalize_ar(text: str) -> str:
    t = _TASHKEEL_RE.sub("", (text or "").strip().lower())
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        t = t.replace(a, b)
    return t


_TRUE_TOKENS = {"مفعل", "تشغيل", "شغال", "نعم", "ايوه", "اه", "on", "yes", "y", "true", "1", "enable", "enabled"}
_FALSE_TOKENS = {"غير", "مش", "مقفول", "ايقاف", "متوقف", "لا", "off", "no", "n", "false", "0", "disable", "disabled"}


def parse_bool(text: str, default: bool = False) -> bool:
    tokens = normalize_ar(text).split()
    if not tokens:
        return default
    if any(t in _FALSE_TOKENS for t in tokens):
        return False
    if any(t in _TRUE_TOKENS for t in tokens):
        return True
    return default


def parse_type(text: str) -> str:
    t = normalize_ar(text)
    if "نص" in t or "text" in t:
        return "text"
    if "صوت" in t or "voice" in t:
        return "voice"
    if "ريا" in t or "react" in t:
        return "reaction"
    return "all"


def parse_range(text: str, maximum: int = 100000) -> tuple[int, int]:
    nums = [int(x) for x in re.findall(r"\d+", text or "")]
    if not nums:
        raise ValueError("no numbers")
    lo, hi = (nums[0], nums[1]) if len(nums) > 1 else (nums[0], nums[0])
    if lo > hi:
        lo, hi = hi, lo
    if hi > maximum:
        raise ValueError("too big")
    return lo, hi


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def report_error(interaction: discord.Interaction):
    try:
        await respond(interaction, content="❌ حصل خطأ غير متوقع، حاول تاني.", ephemeral=True)
    except discord.HTTPException:
        pass


class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


# ==============================================================================
# ⚙️ الإعدادات (مع كاش عشان ما نضربش الداتابيز مع كل رسالة)
# ==============================================================================
def load_settings_sync(gid: int) -> dict:
    try:
        doc = settings_col.find_one_and_update(
            {"guild_id": gid}, {"$setOnInsert": DEFAULT_SETTINGS}, upsert=True, return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        doc = settings_col.find_one({"guild_id": gid})
    raw = {**DEFAULT_SETTINGS, **{k: v for k, v in (doc or {}).items() if k not in ("_id", "guild_id")}}
    cfg = dict(raw)
    for k in ("status", "dm_notifications", "text_xp_enabled", "voice_xp_enabled", "reaction_xp_enabled", "inactivity_decay_enabled"):
        cfg[k] = bool(raw[k])
    cfg["shortcut_level"] = str(raw["shortcut_level"]).lower()
    cfg["shortcut_top"] = str(raw["shortcut_top"]).lower()
    cfg["shortcut_rewards"] = str(raw["shortcut_rewards"]).lower()

    cfg["rewards"] = sorted(
        (
            {"level": int(r["level"]), "role_id": int(r["role_id"]), "req_type": r.get("req_type", "all")}
            for r in role_rewards_col.find({"guild_id": gid})
        ),
        key=lambda r: (r["level"], r["role_id"]),
    )
    cfg["ignored_roles"] = {r["role_id"] for r in ignored_roles_col.find({"guild_id": gid})}
    cfg["ignored_text"] = {c["channel_id"] for c in ignored_channels_col.find({"guild_id": gid})}
    cfg["ignored_voice"] = {v["channel_id"] for v in ignored_voice_col.find({"guild_id": gid})}
    cfg["ignored_any"] = cfg["ignored_text"] | cfg["ignored_voice"]
    cfg["role_multipliers"] = {i["role_id"]: float(i["multiplier"]) for i in role_multipliers_col.find({"guild_id": gid})}
    cfg["user_multipliers"] = {i["user_id"]: float(i["multiplier"]) for i in user_multipliers_col.find({"guild_id": gid})}
    cfg["channel_multipliers"] = {i["channel_id"]: float(i["multiplier"]) for i in channel_multipliers_col.find({"guild_id": gid})}

    roles_raw = raw.get("event_target_roles", "all")
    if isinstance(roles_raw, (list, tuple, set)):
        role_ids = {int(x) for x in roles_raw if str(x).isdigit()}
    elif isinstance(roles_raw, str) and roles_raw.strip().lower() != "all":
        role_ids = set(parse_ids(roles_raw))
    else:
        role_ids = set()
    event_type = "all" if raw["event_type"] in ("both", "all") else raw["event_type"]
    cfg["event"] = {
        "mult": float(raw["event_multiplier"] or 1.0),
        "type": event_type if event_type in TYPES else "all",
        "end": int(raw["event_end_timestamp"] or 0),
        "roles": role_ids or None,
    }
    return cfg


class SettingsCache:
    def __init__(self):
        self._data: dict[int, dict] = {}
        self._ts: dict[int, float] = {}

    async def get(self, gid: int, force: bool = False) -> dict:
        now = time.monotonic()
        if not force and gid in self._data and now - self._ts.get(gid, 0) < SETTINGS_TTL:
            return self._data[gid]
        cfg = await run_db(load_settings_sync, gid)
        self._data[gid] = cfg
        self._ts[gid] = now
        return cfg

    def invalidate(self, gid: int):
        self._data.pop(gid, None)
        self._ts.pop(gid, None)


SETTINGS = SettingsCache()


async def update_settings(gid: int, **fields):
    await run_db(lambda: settings_col.update_one({"guild_id": gid}, {"$set": fields}, upsert=True))
    SETTINGS.invalidate(gid)


# ==============================================================================
# 🗄️ عمليات قاعدة البيانات (كلها متزامنة وبتتشغل في thread)
# ==============================================================================
def ensure_indexes_sync():
    specs = [
        (user_stats_col, [("guild_id", 1), ("user_id", 1)], {"unique": True}),
        (user_stats_col, [("guild_id", 1), ("text_xp", -1)], {}),
        (user_stats_col, [("guild_id", 1), ("voice_xp", -1)], {}),
        (user_stats_col, [("guild_id", 1), ("reaction_xp", -1)], {}),
        (settings_col, [("guild_id", 1)], {"unique": True}),
        (role_rewards_col, [("guild_id", 1), ("level", 1), ("role_id", 1)], {"unique": True}),
        (ignored_roles_col, [("guild_id", 1), ("role_id", 1)], {}),
        (ignored_channels_col, [("guild_id", 1), ("channel_id", 1)], {}),
        (ignored_voice_col, [("guild_id", 1), ("channel_id", 1)], {}),
        (role_multipliers_col, [("guild_id", 1), ("role_id", 1)], {}),
        (user_multipliers_col, [("guild_id", 1), ("user_id", 1)], {}),
        (channel_multipliers_col, [("guild_id", 1), ("channel_id", 1)], {}),
    ]
    for col, keys, opts in specs:
        try:
            col.create_index(keys, **opts)
        except Exception:
            log.warning("تعذر إنشاء index %s (غالباً فيه بيانات مكررة قديمة)", keys, exc_info=True)


def migrate_user_stats_sync() -> int:
    """ترحيل البيانات القديمة: xp القديم كان نصي+صوتي مع بعض، فبنفصلهم."""
    ops, count = [], 0
    for doc in user_stats_col.find({"text_xp": {"$exists": False}}):
        voice_xp = int(doc.get("voice_xp", 0) or 0)
        reaction_xp = int(doc.get("reaction_xp", 0) or 0)
        text_xp = max(0, int(doc.get("xp", 0) or 0) - voice_xp - reaction_xp)
        set_ = {
            "text_xp": text_xp, "text_level": level_from_xp(text_xp),
            "voice_xp": voice_xp, "voice_level": level_from_xp(voice_xp),
            "reaction_xp": reaction_xp, "reaction_level": level_from_xp(reaction_xp),
        }
        for p in PERIODS:
            for t in ("voice", "reaction"):
                if f"{p}_{t}_xp" not in doc:
                    set_[f"{p}_{t}_xp"] = 0
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": set_}))
        if len(ops) >= 500:
            user_stats_col.bulk_write(ops, ordered=False)
            count += len(ops)
            ops = []
    if ops:
        user_stats_col.bulk_write(ops, ordered=False)
        count += len(ops)
    return count


def apply_user_update_sync(gid: int, uid: int, inc: dict, set_: dict) -> dict:
    defaults = {k: v for k, v in NEW_USER_DEFAULTS.items() if k not in inc and k not in set_}
    update: dict[str, Any] = {"$setOnInsert": defaults}
    if inc:
        update["$inc"] = inc
    if set_:
        update["$set"] = set_
    for _ in range(3):
        try:
            return user_stats_col.find_one_and_update(
                {"guild_id": gid, "user_id": uid}, update, upsert=True, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            continue
    raise RuntimeError("تعذر تحديث بيانات العضو")


def claim_level_sync(gid: int, uid: int, field: str, old: int, new: int) -> bool:
    """تحديث ذري للمستوى: بيرجع True مرة واحدة بس (يمنع الإعلان المكرر)."""
    res = user_stats_col.update_one({"guild_id": gid, "user_id": uid, field: old}, {"$set": {field: new}})
    return res.modified_count == 1


def get_user_sync(gid: int, uid: int) -> Optional[dict]:
    return user_stats_col.find_one({"guild_id": gid, "user_id": uid})


def rank_sync(gid: int, field: str, value: int, extra: dict) -> int:
    q = {"guild_id": gid, field: {"$gt": value}, **extra}
    return user_stats_col.count_documents(q) + 1


def top_page_sync(gid: int, field: str, extra: dict, skip: int, limit: int) -> tuple[int, list]:
    q = {"guild_id": gid, field: {"$gt": 0}, **extra}
    total = user_stats_col.count_documents(q)
    rows = list(user_stats_col.find(q).sort([(field, -1), ("user_id", 1)]).skip(skip).limit(limit))
    return total, rows


def flush_messages_sync(items: list):
    defaults = {k: v for k, v in NEW_USER_DEFAULTS.items() if k != "messages"}
    ops = [
        UpdateOne({"guild_id": gid, "user_id": uid}, {"$inc": {"messages": n}, "$setOnInsert": defaults}, upsert=True)
        for (gid, uid), n in items
    ]
    if ops:
        user_stats_col.bulk_write(ops, ordered=False)


def meta_get_sync() -> dict:
    return meta_col.find_one({"_id": "resets"}) or {}


def meta_set_sync(keys: dict):
    meta_col.update_one({"_id": "resets"}, {"$set": keys}, upsert=True)


def reset_period_sync(period: str):
    fields = {f"{period}_{t}_xp": 0 for t in TYPES}
    user_stats_col.update_many({"$or": [{k: {"$gt": 0}} for k in fields]}, {"$set": fields})


def period_winners_sync(gid: int, period: str, limit: int = 10) -> list:
    fields = [f"{period}_{t}_xp" for t in TYPES]
    pipeline = [
        {"$match": {"guild_id": gid}},
        {"$addFields": {"_total": {"$add": [{"$ifNull": [f"${f}", 0]} for f in fields]}}},
        {"$match": {"_total": {"$gt": 0}}},
        {"$sort": {"_total": -1}},
        {"$limit": limit},
        {"$project": {"user_id": 1, "_total": 1}},
    ]
    return list(user_stats_col.aggregate(pipeline))


def add_reward_sync(gid: int, level: int, role_id: int, req_type: str):
    role_rewards_col.update_one({"guild_id": gid, "level": level, "role_id": role_id}, {"$set": {"req_type": req_type}}, upsert=True)


def remove_rewards_sync(gid: int, role_ids: list) -> int:
    return role_rewards_col.delete_many({"guild_id": gid, "role_id": {"$in": role_ids}}).deleted_count


def toggle_ignored_sync(col, key: str, gid: int, ids: list) -> tuple[list, list]:
    """لو العنصر مستبعد بالفعل بيشيله، ولو لأ بيضيفه."""
    existing = {d[key] for d in col.find({"guild_id": gid, key: {"$in": ids}})}
    added, removed = [], []
    for i in ids:
        if i in existing:
            col.delete_many({"guild_id": gid, key: i})
            removed.append(i)
        else:
            col.update_one({"guild_id": gid, key: i}, {"$set": {key: i}}, upsert=True)
            added.append(i)
    return added, removed


def set_multipliers_sync(kind: str, gid: int, ids: list, value: float):
    col, key = {
        "user": (user_multipliers_col, "user_id"),
        "role": (role_multipliers_col, "role_id"),
        "channel": (channel_multipliers_col, "channel_id"),
    }[kind]
    for i in ids:
        if value <= 1.0:
            col.delete_many({"guild_id": gid, key: i})
        else:
            col.update_one({"guild_id": gid, key: i}, {"$set": {"multiplier": value}}, upsert=True)


# ==============================================================================
# 🧠 منطق الـ XP والمضاعفات والمكافآت
# ==============================================================================
def activity_filter(cfg: dict) -> dict:
    if cfg["inactivity_decay_enabled"]:
        return {"last_active_timestamp": {"$gte": int(time.time()) - INACTIVITY_DAYS * 86400}}
    return {}


def is_channel_ignored(cfg: dict, channel) -> bool:
    ids = {channel.id, getattr(channel, "category_id", None), getattr(channel, "parent_id", None)}
    ids.discard(None)
    return bool(ids & cfg["ignored_any"])


def has_ignored_role(cfg: dict, member: discord.Member) -> bool:
    return any(r.id in cfg["ignored_roles"] for r in member.roles)


def personal_multiplier(cfg: dict, member: discord.Member) -> float:
    mult = max(1.0, cfg["user_multipliers"].get(member.id, 1.0))
    for r in member.roles:
        mult = max(mult, cfg["role_multipliers"].get(r.id, 1.0))
    return mult


def compute_multiplier(cfg: dict, member: discord.Member, type_: str, channel_id: Optional[int] = None, category_id: Optional[int] = None) -> float:
    mult = personal_multiplier(cfg, member)
    ev = cfg["event"]
    if ev["mult"] > 1.0 and ev["end"] > time.time() and ev["type"] in ("all", type_):
        if ev["roles"] is None or any(r.id in ev["roles"] for r in member.roles):
            mult = max(mult, ev["mult"])
    for cid in (channel_id, category_id):
        if cid:
            mult = max(mult, cfg["channel_multipliers"].get(cid, 1.0))
    return mult


def reward_matches(req_type: str, trigger_type: str) -> bool:
    return req_type == "all" or req_type == trigger_type


def reward_earned(req_type: str, levels: dict, level_needed: int) -> bool:
    if req_type == "all":
        return max(levels.values()) >= level_needed
    return levels.get(req_type, 0) >= level_needed


def earned_reward_roles(guild: discord.Guild, cfg: dict, type_: str, level: int) -> list[str]:
    out = []
    for rw in cfg["rewards"]:
        if rw["level"] <= level and reward_matches(rw["req_type"], type_):
            role = guild.get_role(rw["role_id"])
            if role:
                out.append(role.mention)
    return out


BAR_PATTERNS = [
    (5.0, ["⬜"]), (4.5, ["⬜", "🟨"]), (4.0, ["🟨"]), (3.5, ["🟨", "🟧"]), (3.0, ["🟧"]),
    (2.5, ["🟧", "🟥"]), (2.0, ["🟥"]), (1.5, ["🟥", "🟩"]), (0.0, ["🟩"]),
]


def progress_bar(pct: float, mult: float, width: int = 12) -> str:
    filled = int(max(0.0, min(1.0, pct)) * width)
    pattern = next(p for m, p in BAR_PATTERNS if mult >= m)
    return "".join(pattern[i % len(pattern)] for i in range(filled)) + "⬛" * (width - filled)


# ==============================================================================
# 🖼️ لوحة التحكم
# ==============================================================================
def generate_levels_panel_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    status_str = "شغال `🟢`" if cfg["status"] else "متوقف `🔴`"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg["announcement_channel"] else "`غير محددة (مفيش إعلانات)` 📌"
    logs_disp = f"<#{cfg['logs_channel']}>" if cfg["logs_channel"] else "`غير محددة (مفيش سجلات)` 📌"
    decay_str = "مفعل `✅`" if cfg["inactivity_decay_enabled"] else "مقفول `❌`"
    dm_str = "مفعل `✅`" if cfg["dm_notifications"] else "مقفول `❌`"

    ev = cfg["event"]
    if ev["mult"] > 1.0 and ev["end"] > time.time():
        target_str = "السيرفر بالكامل" if ev["roles"] is None else "رتب محددة 🎯"
        event_str = f"`x{ev['mult']:g}` | {REQ_LABEL[ev['type']]} | المدى: {target_str} | ينتهي <t:{ev['end']}:R>"
    else:
        event_str = "`لا يوجد حدث نشط` ⚪"

    periodic_disp = (
        f"<@&{cfg['periodic_reward_role']}> ({PERIOD_LABEL[cfg['periodic_type']]})" if cfg["periodic_reward_role"] else "`غير مفعلة` ⚪"
    )
    on, off = "شغال `✅`", "مقفول `❌`"
    shortcuts_str = f"الليفل: `{cfg['shortcut_level']}` | التوب: `{cfg['shortcut_top']}` | المكافآت: `{cfg['shortcut_rewards']}`"

    desc = (
        "> **أهلاً بك يا فنان في لوحة التحكم المركزية لنظام التفاعل بالسيرفر.** 📊\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "### 🌐 ┃ الحالة العامة للنظام\n"
        f"> * **حالة النظام:** {status_str}\n"
        f"> * **قناة الإعلانات:** {chan_disp}\n"
        f"> * **قناة السجلات (Log):** {logs_disp}\n"
        f"> * **إشعارات الخاص:** {dm_str}\n"
        f"> * **طرد المتخاذلين (5 أيام):** {decay_str}\n"
        f"> * **المضاعف العام:** {event_str}\n"
        f"> * **مكافأة التفاعل الدوري:** {periodic_disp}\n"
        f"> * **الاختصارات الحالية:** {shortcuts_str}\n\n"
        "### ⚙️ ┃ أنظمة الـ XP الفعالة\n"
        f"> * 💬 **الرسائل النصية:** {on if cfg['text_xp_enabled'] else off} ┊ النطاق: [ `{cfg['min_text_xp']} - {cfg['max_text_xp']} XP` ] ┊ كولداون `{cfg['text_cooldown']}ث`\n"
        f"> * 🔊 **الرومات الصوتية:** {on if cfg['voice_xp_enabled'] else off} ┊ النطاق: [ `{cfg['min_voice_xp']} - {cfg['max_voice_xp']} XP` ] ┊ كل دقيقة\n"
        f"> * ⭐ **الرياكشنات:** {on if cfg['reaction_xp_enabled'] else off} ┊ النطاق: [ `{cfg['min_reaction_xp']} - {cfg['max_reaction_xp']} XP` ] ┊ كولداون `{cfg['reaction_cooldown']}ث`\n\n"
        "### 🚫 ┃ الاستثناءات والمكافآت\n"
        f"> * 👥 **الرتب المستبعدة:** [ `{len(cfg['ignored_roles'])}` ] رتبة\n"
        f"> * 📁 **الرومات المستبعدة:** [ `{len(cfg['ignored_any'])}` ] روم\n"
        f"> * 🎁 **رتب المكافآت الثابتة:** [ `{len(cfg['rewards'])}` ] رتبة\n"
        f"> * ⚡ **المضاعفات المخصصة:** أعضاء `{len(cfg['user_multipliers'])}` ┊ رتب `{len(cfg['role_multipliers'])}` ┊ رومات `{len(cfg['channel_multipliers'])}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
    embed = discord.Embed(title="⚡ ‹ لوحة التفاعل والمستويات › ⚡", description=desc, color=COLOR_DARK, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"{guild.name} ✦ Voice & Level System")
    return embed


async def panel_embed(guild: discord.Guild) -> discord.Embed:
    return generate_levels_panel_embed(guild, await SETTINGS.get(guild.id))


async def refresh_panel(panel_inter: Optional[discord.Interaction], guild: discord.Guild):
    """تحديث رسالة اللوحة الأصلية (لو لسه صالحة)."""
    if panel_inter is None:
        return
    try:
        await panel_inter.edit_original_response(embed=await panel_embed(guild))
    except discord.HTTPException:
        pass


async def panel_modal_done(interaction: discord.Interaction, title: str, desc: str):
    """بعد مودال اتفتح من اللوحة: يحدّث اللوحة ويبعت تأكيد للأدمن."""
    await interaction.edit_original_response(embed=await panel_embed(interaction.guild))
    await interaction.followup.send(embed=ok_embed(title, desc), ephemeral=True)


# ----- المودالات (بتتفتح من اللوحة مباشرة) -----
class SystemShortcutsModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="⚡ تحديد اختصارات الأوامر")
        self.level_sc = discord.ui.TextInput(label="اختصار أمر الليفل (مثال: l)", default=cfg["shortcut_level"], max_length=15, required=True)
        self.top_sc = discord.ui.TextInput(label="اختصار أمر التوب (مثال: t)", default=cfg["shortcut_top"], max_length=15, required=True)
        self.rewards_sc = discord.ui.TextInput(label="اختصار أمر المكافآت (مثال: r)", default=cfg["shortcut_rewards"], max_length=15, required=True)
        for box in (self.level_sc, self.top_sc, self.rewards_sc):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        vals = [b.value.strip().lower() for b in (self.level_sc, self.top_sc, self.rewards_sc)]
        if any((not v) or re.search(r"\s", v) for v in vals) or len(set(vals)) != 3:
            await respond(interaction, embed=err_embed("الاختصارات لازم تكون كلمة واحدة من غير مسافات، ومختلفة عن بعض."), ephemeral=True)
            return
        await interaction.response.defer()
        await update_settings(interaction.guild.id, shortcut_level=vals[0], shortcut_top=vals[1], shortcut_rewards=vals[2])
        await panel_modal_done(interaction, "✅ تم تظبيط الاختصارات",
                               f"تم حفظ الاختصارات بنجاح:\n• **بطاقة الليفل:** `{vals[0]}`\n• **قائمة التوب:** `{vals[1]}`\n• **جدول المكافآت:** `{vals[2]}`")


class SystemStateModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🔄 تفعيل/إيقاف أنظمة المستويات")

        def yn(v: bool) -> str:
            return "مفعل" if v else "غير مفعل"

        self.sys_status = discord.ui.TextInput(label="حالة النظام العامة (مفعل / غير مفعل)", default=yn(cfg["status"]), max_length=10)
        self.text_status = discord.ui.TextInput(label="الترقيات النصية (مفعل / غير مفعل)", default=yn(cfg["text_xp_enabled"]), max_length=10)
        self.voice_status = discord.ui.TextInput(label="الترقيات الصوتية (مفعل / غير مفعل)", default=yn(cfg["voice_xp_enabled"]), max_length=10)
        self.react_status = discord.ui.TextInput(label="ترقيات الريأكشن (مفعل / غير مفعل)", default=yn(cfg["reaction_xp_enabled"]), max_length=10)
        self.dm_status = discord.ui.TextInput(label="إشعار الترقية في الخاص (مفعل / غير مفعل)", default=yn(cfg["dm_notifications"]), max_length=10)
        for box in (self.sys_status, self.text_status, self.voice_status, self.react_status, self.dm_status):
            self.add_item(box)
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        c = self.cfg
        await interaction.response.defer()
        await update_settings(
            interaction.guild.id,
            status=int(parse_bool(self.sys_status.value, c["status"])),
            text_xp_enabled=int(parse_bool(self.text_status.value, c["text_xp_enabled"])),
            voice_xp_enabled=int(parse_bool(self.voice_status.value, c["voice_xp_enabled"])),
            reaction_xp_enabled=int(parse_bool(self.react_status.value, c["reaction_xp_enabled"])),
            dm_notifications=int(parse_bool(self.dm_status.value, c["dm_notifications"])),
        )
        await panel_modal_done(interaction, "✅ تم التعديل بنجاح", "تم تحديث حالات تفعيل وتشغيل الأقسام بالكامل.")


class XpSettingsModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="⚙️ ضبط نقاط الـ XP")
        self.text_range = discord.ui.TextInput(label="نطاق XP النصي (أدنى-أقصى)", default=f"{cfg['min_text_xp']}-{cfg['max_text_xp']}", max_length=12)
        self.voice_range = discord.ui.TextInput(label="نطاق XP الصوتي (أدنى-أقصى)", default=f"{cfg['min_voice_xp']}-{cfg['max_voice_xp']}", max_length=12)
        self.react_range = discord.ui.TextInput(label="نطاق XP الرياكشن (أدنى-أقصى)", default=f"{cfg['min_reaction_xp']}-{cfg['max_reaction_xp']}", max_length=12)
        self.text_cd = discord.ui.TextInput(label="كولداون الرسائل (بالثواني)", default=str(cfg["text_cooldown"]), max_length=5)
        self.react_cd = discord.ui.TextInput(label="كولداون الرياكشن (بالثواني)", default=str(cfg["reaction_cooldown"]), max_length=5)
        for box in (self.text_range, self.voice_range, self.react_range, self.text_cd, self.react_cd):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            t_lo, t_hi = parse_range(self.text_range.value)
            v_lo, v_hi = parse_range(self.voice_range.value)
            r_lo, r_hi = parse_range(self.react_range.value)
            t_cd, r_cd = int(self.text_cd.value.strip()), int(self.react_cd.value.strip())
            if not (0 <= t_cd <= 3600 and 0 <= r_cd <= 3600):
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("حط أرقام صحيحة، مثال للنطاق: `5-45` والكولداون من 0 لـ 3600 ثانية.", "❌ يا أسطى ركز"), ephemeral=True)
            return
        await interaction.response.defer()
        await update_settings(
            interaction.guild.id, min_text_xp=t_lo, max_text_xp=t_hi, min_voice_xp=v_lo, max_voice_xp=v_hi,
            min_reaction_xp=r_lo, max_reaction_xp=r_hi, text_cooldown=t_cd, reaction_cooldown=r_cd,
        )
        await panel_modal_done(interaction, "✅ زي الفل", "تم تحديث نطاق نقاط الـ XP والكولداون بنجاح.")


class LevelMessageModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="💬 رسالة وصورة الترقية")
        self.msg_box = discord.ui.TextInput(
            label="رسالة الترقية ({user} {level} {type})", style=discord.TextStyle.paragraph,
            default=clip(cfg["level_message"], 1000), max_length=1000, required=True,
        )
        self.type_box = discord.ui.TextInput(label="نوع الرسالة (embed أو text)", default=cfg["msg_type"], max_length=10)
        self.title_box = discord.ui.TextInput(label="عنوان الإيمبد ({level} {type})", default=clip(cfg["level_embed_title"], 100), max_length=100, required=False)
        self.image_box = discord.ui.TextInput(label="رابط صورة الترقية (اختياري)", default=cfg["level_image"] or "", placeholder="https://example.com/image.png", max_length=300, required=False)
        for box in (self.msg_box, self.type_box, self.title_box, self.image_box):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        raw_img = self.image_box.value.strip()
        image = clean_url(raw_img)
        if raw_img and not image:
            await respond(interaction, embed=err_embed("رابط الصورة لازم يبدأ بـ http أو https."), ephemeral=True)
            return
        m_type = "embed" if any(w in normalize_ar(self.type_box.value) for w in ("embed", "ايمبد")) else "text"
        await interaction.response.defer()
        await update_settings(
            interaction.guild.id, level_message=self.msg_box.value, msg_type=m_type,
            level_embed_title=self.title_box.value.strip() or DEFAULT_SETTINGS["level_embed_title"], level_image=image,
        )
        await panel_modal_done(interaction, "✅ تسلم إيدك", "تم حفظ رسالة وصورة الترقية بنجاح.")


class LevelsRewardModal(SafeModal, title="🎁 إضافة رول مكافأة"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", placeholder="1234567890", max_length=30, required=True)
    lvl_box = discord.ui.TextInput(label="المستوى المطلوب للحصول عليها", placeholder="5", max_length=5, required=True)
    type_box = discord.ui.TextInput(
        label="نوع التفاعل (نصي / صوتي / رياكشن / الكل)", default="الكل",
        placeholder="أكتب: نصي أو صوتي أو رياكشن أو الكل", max_length=15, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ids = parse_ids(self.role_box.value)
        role = interaction.guild.get_role(ids[0]) if ids else None
        try:
            lvl = int(self.lvl_box.value.strip())
            if not 1 <= lvl <= 1000:
                raise ValueError
        except ValueError:
            lvl = 0
        if role is None or lvl == 0:
            await respond(interaction, embed=err_embed("تأكد من صحة أيدي الرتبة أو المستوى يا غالي.", "❌ خطأ يا فنان"), ephemeral=True)
            return
        me = interaction.guild.me
        if role.managed or role.is_default() or role >= me.top_role:
            await respond(interaction, embed=err_embed("الرتبة دي أعلى من رتبة البوت أو رتبة خاصة، البوت مش هيعرف يديها. حرّك رتبة البوت فوقها الأول."), ephemeral=True)
            return
        req_type = parse_type(self.type_box.value)
        await interaction.response.defer()
        await run_db(add_reward_sync, interaction.guild.id, lvl, role.id, req_type)
        SETTINGS.invalidate(interaction.guild.id)
        await panel_modal_done(interaction, "✅ يا سلام يا فنان", f"تم ربط المستوى `{lvl}` بالرتبة {role.mention}\n• **نوع التفاعل المطلوب:** {REQ_LABEL[req_type]}")


class PeriodicRewardModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🏅 مكافأة التفاعل الدوري")
        self.role_box = discord.ui.TextInput(label="أيدي رتبة المكافأة (فاضي = إيقاف)", default=str(cfg["periodic_reward_role"] or ""), max_length=30, required=False)
        self.type_box = discord.ui.TextInput(label="الفترة (يومي / أسبوعي / شهري)", default={"day": "يومي", "week": "أسبوعي", "month": "شهري"}[cfg["periodic_type"]], max_length=10)
        self.add_item(self.role_box)
        self.add_item(self.type_box)

    async def on_submit(self, interaction: discord.Interaction):
        t = normalize_ar(self.type_box.value)
        period = "day" if ("يوم" in t or "day" in t) else "month" if ("شهر" in t or "month" in t) else "week"
        ids = parse_ids(self.role_box.value)
        role_id = None
        if ids:
            role = interaction.guild.get_role(ids[0])
            if role is None or role.managed or role.is_default() or role >= interaction.guild.me.top_role:
                await respond(interaction, embed=err_embed("الرتبة مش موجودة أو أعلى من رتبة البوت."), ephemeral=True)
                return
            role_id = role.id
        await interaction.response.defer()
        await update_settings(interaction.guild.id, periodic_reward_role=role_id, periodic_type=period)
        desc = f"هتتمنح الرتبة <@&{role_id}> لأكتر عضو تفاعلاً كل فترة ({PERIOD_LABEL[period]})." if role_id else "تم إيقاف مكافأة التفاعل الدوري."
        await panel_modal_done(interaction, "✅ تم الحفظ", desc)


class EventModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🎉 حدث XP مضاعف")
        ev = cfg["event"]
        active = ev["mult"] > 1.0 and ev["end"] > time.time()
        self.mult_box = discord.ui.TextInput(label="المضاعف (1 = إيقاف الحدث، حتى 10)", default=f"{ev['mult']:g}" if active else "2", max_length=5)
        self.hours_box = discord.ui.TextInput(label="المدة بالساعات (مثال: 2 أو 0.5)", default="2", max_length=6)
        self.type_box = discord.ui.TextInput(label="النوع (نصي / صوتي / رياكشن / الكل)", default={"text": "نصي", "voice": "صوتي", "reaction": "رياكشن", "all": "الكل"}[ev["type"]], max_length=15)
        self.roles_box = discord.ui.TextInput(label="أيديهات الرتب المستهدفة (فاضي = الكل)", style=discord.TextStyle.paragraph, required=False, max_length=300)
        for box in (self.mult_box, self.hours_box, self.type_box, self.roles_box):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mult = float(self.mult_box.value.strip().replace(",", "."))
            hours = float(self.hours_box.value.strip().replace(",", "."))
            if not 1.0 <= mult <= 10.0 or not 0.01 <= hours <= 720:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("المضاعف من 1 لـ 10 والمدة من 0.01 لـ 720 ساعة."), ephemeral=True)
            return
        await interaction.response.defer()
        gid = interaction.guild.id
        if mult <= 1.0:
            await update_settings(gid, event_multiplier=1.0, event_end_timestamp=0)
            await panel_modal_done(interaction, "🛑 تم إيقاف الحدث", "اتوقف الحدث المضاعف.")
            return
        role_ids = [i for i in parse_ids(self.roles_box.value) if interaction.guild.get_role(i)]
        end = int(time.time() + hours * 3600)
        etype = parse_type(self.type_box.value)
        await update_settings(gid, event_multiplier=mult, event_type=etype, event_end_timestamp=end, event_target_roles=role_ids or "all")
        await panel_modal_done(interaction, "🎉 بدأ الحدث", f"المضاعف `x{mult:g}` على **{REQ_LABEL[etype]}** وينتهي <t:{end}:R>.")


# ----- Pickers (رسائل مؤقتة فيها قوائم اختيار) -----
class ChannelPickerView(SafeView):
    def __init__(self, setting_key: str, label: str, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=120)
        self.setting_key, self.label, self.panel_inter = setting_key, label, panel_inter

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="اختر القناة",
                       channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=1, max_values=1)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        chan = interaction.guild.get_channel(select.values[0].id)
        if chan is None:
            await respond(interaction, content="❌ مقدرتش أوصل للقناة دي.", ephemeral=True)
            return
        await update_settings(interaction.guild.id, **{self.setting_key: chan.id})
        perms = chan.permissions_for(interaction.guild.me)
        warn = "" if (perms.send_messages and perms.embed_links) else "\n\n⚠️ **تنبيه:** البوت معندوش صلاحية الإرسال أو Embed Links في القناة دي."
        await interaction.response.edit_message(embed=ok_embed("✅ تمام التمام", f"تم تعيين {self.label} لـ {chan.mention} بنجاح.{warn}"), view=None)
        await refresh_panel(self.panel_inter, interaction.guild)

    @discord.ui.button(label="مسح التحديد (إيقاف الإرسال)", style=discord.ButtonStyle.danger, emoji="🚫")
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await update_settings(interaction.guild.id, **{self.setting_key: None})
        await interaction.response.edit_message(embed=ok_embed("🚫 تم الإيقاف", f"تم مسح {self.label}، مش هيتبعت أي حاجة تاني."), view=None)
        await refresh_panel(self.panel_inter, interaction.guild)


class MultiplierValueModal(SafeModal):
    def __init__(self, kind: str, ids: list, panel_inter: Optional[discord.Interaction]):
        super().__init__(title="⚡ تعيين قيمة المضاعف")
        self.kind, self.ids, self.panel_inter = kind, ids, panel_inter
        self.mult_box = discord.ui.TextInput(label="المضاعف (1.5 / 2 / 3.5 ... واكتب 1 للإزالة)", default="2.0", max_length=5)
        self.add_item(self.mult_box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.mult_box.value.strip().replace(",", "."))
            if not 1.0 <= val <= 5.0:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("يا غالي دخل قيمة صحيحة بين 1.0 و 5.0"), ephemeral=True)
            return
        await interaction.response.defer()
        await run_db(set_multipliers_sync, self.kind, interaction.guild.id, self.ids, val)
        SETTINGS.invalidate(interaction.guild.id)
        desc = f"خلاص، تم تظبيط المضاعف على `x{val:g}` بنجاح!" if val > 1.0 else "تم إزالة المضاعف من العناصر المحددة."
        await interaction.edit_original_response(embed=ok_embed("✅ تم يا باشا", desc), view=None)
        await refresh_panel(self.panel_inter, interaction.guild)


class MultiplierPickerView(SafeView):
    def __init__(self, kind: str, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=120)
        cls, ph = {
            "user": (discord.ui.UserSelect, "اختر الأعضاء لتطبيق المضاعف عليهم"),
            "role": (discord.ui.RoleSelect, "اختر الرتب لتطبيق المضاعف عليها"),
            "channel": (discord.ui.ChannelSelect, "اختر الرومات لتطبيق المضاعف عليها"),
        }[kind]
        select = cls(placeholder=ph, min_values=1, max_values=10)

        async def cb(interaction: discord.Interaction):
            await interaction.response.send_modal(MultiplierValueModal(kind, [v.id for v in select.values], panel_inter))

        select.callback = cb
        self.add_item(select)


class MultiplierTypeSelectView(SafeView):
    def __init__(self, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=120)
        self.panel_inter = panel_inter

    async def _open(self, interaction: discord.Interaction, kind: str, title: str, desc: str):
        await interaction.response.edit_message(embed=discord.Embed(title=title, description=desc, color=COLOR_DARK), view=MultiplierPickerView(kind, self.panel_inter))

    @discord.ui.button(label="مضاعف لأعضاء 👤", style=discord.ButtonStyle.primary)
    async def mult_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "user", "👤 اختر الأعضاء", "حدد الشخص من القائمة يا فنان:")

    @discord.ui.button(label="مضاعف لرتب 🛡️", style=discord.ButtonStyle.secondary)
    async def mult_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "role", "🛡️ اختر الرتب", "حدد الرتبة من القائمة يا غالي:")

    @discord.ui.button(label="مضاعف لرومات 💬/🎙️", style=discord.ButtonStyle.success)
    async def mult_chan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open(interaction, "channel", "💬 اختر الرومات", "حدد الروم من القائمة يا معلم:")


class IgnoreSelectView(SafeView):
    """اختيار عنصر مستبعد بالفعل بيشيله من الاستثناءات (Toggle)."""

    def __init__(self, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=120)
        self.panel_inter = panel_inter

    async def _finish(self, interaction: discord.Interaction, added: list, removed: list, fmt: str):
        SETTINGS.invalidate(interaction.guild.id)
        lines = []
        if added:
            lines.append("🚫 **تم الاستبعاد:** " + " ".join(fmt.format(i) for i in added))
        if removed:
            lines.append("✅ **تم رجوعهم للنظام:** " + " ".join(fmt.format(i) for i in removed))
        await interaction.response.edit_message(embed=ok_embed("✅ تم", "\n".join(lines) or "مفيش تغيير."), view=None)
        await refresh_panel(self.panel_inter, interaction.guild)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="اختر الرتب المراد استبعادها من الـ XP", min_values=1, max_values=10)
    async def pick_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        added, removed = await run_db(toggle_ignored_sync, ignored_roles_col, "role_id", interaction.guild.id, [r.id for r in select.values])
        await self._finish(interaction, added, removed, "<@&{}>")

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="اختر الرومات المراد استبعادها من الـ XP", min_values=1, max_values=10)
    async def pick_channels(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        voice_ids = [c.id for c in select.values if c.type in (discord.ChannelType.voice, discord.ChannelType.stage_voice)]
        other_ids = [c.id for c in select.values if c.id not in voice_ids]
        gid = interaction.guild.id
        added, removed = [], []
        if other_ids:
            a, r = await run_db(toggle_ignored_sync, ignored_channels_col, "channel_id", gid, other_ids)
            added += a
            removed += r
        if voice_ids:
            a, r = await run_db(toggle_ignored_sync, ignored_voice_col, "channel_id", gid, voice_ids)
            added += a
            removed += r
        await self._finish(interaction, added, removed, "<#{}>")


class RewardRemoveView(SafeView):
    def __init__(self, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=120)
        self.panel_inter = panel_inter

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="اختر الرتب المراد حذفها من المكافآت", min_values=1, max_values=10)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        deleted = await run_db(remove_rewards_sync, interaction.guild.id, [r.id for r in select.values])
        SETTINGS.invalidate(interaction.guild.id)
        await interaction.response.edit_message(embed=ok_embed("🗑️ تم الحذف", f"تم حذف `{deleted}` مكافأة مرتبطة بالرتب المحددة."), view=None)
        await refresh_panel(self.panel_inter, interaction.guild)


# ----- اللوحة الرئيسية -----
class LevelsAdminPanelView(SafeView):
    def __init__(self, panel_inter: Optional[discord.Interaction] = None):
        super().__init__(timeout=None)
        self.panel_inter = panel_inter

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await respond(interaction, embed=err_embed("اللوحة دي للإدارة فقط."), ephemeral=True)
        return False

    @discord.ui.button(label="تشغيل / إيقاف النظام", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_v11")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SystemStateModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="تحديد الاختصارات ⚡", style=discord.ButtonStyle.primary, emoji="⌨️", row=0, custom_id="p_shortcuts_v11")
    async def set_shortcuts_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SystemShortcutsModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="قناة إعلانات الترقية", style=discord.ButtonStyle.secondary, emoji="📢", row=0, custom_id="p_ann_chan_v11")
    async def set_announce_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📢 قناة الإعلانات", description="اختر قناة إعلانات الترقية من القائمة أدناه.\nلو مفيش قناة محددة، مفيش إعلانات بتتبعت.", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=ChannelPickerView("announcement_channel", "قناة الإعلانات", self.panel_inter), ephemeral=True)

    @discord.ui.button(label="قناة السجلات (Logs)", style=discord.ButtonStyle.secondary, emoji="📋", row=0, custom_id="p_logs_chan_v11")
    async def set_logs_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📋 قناة السجلات", description="اختر قناة السجلات الإدارية من القائمة أدناه.\nلو مفيش قناة محددة، مفيش سجلات بتتبعت.", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=ChannelPickerView("logs_channel", "قناة السجلات", self.panel_inter), ephemeral=True)

    @discord.ui.button(label="إعدادات الـ XP", style=discord.ButtonStyle.primary, emoji="⚙️", row=1, custom_id="p_xp_unified_v11")
    async def xp_unified_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(XpSettingsModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="مضاعفات الـ XP", style=discord.ButtonStyle.success, emoji="⚡", row=1, custom_id="p_mult_custom_v11")
    async def custom_mult_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="⚡ إدارة مضاعفات الـ XP", description="اختر الفئة المراد تطبيق المضاعف عليها:", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=MultiplierTypeSelectView(self.panel_inter), ephemeral=True)

    @discord.ui.button(label="حدث مضاعف", style=discord.ButtonStyle.success, emoji="🎉", row=1, custom_id="p_event_v12")
    async def event_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EventModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="رسالة الترقية", style=discord.ButtonStyle.secondary, emoji="💬", row=1, custom_id="p_msg_v11")
    async def msg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelMessageModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="إضافة رول مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=2, custom_id="p_reward_v11")
    async def reward_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelsRewardModal())

    @discord.ui.button(label="حذف رول مكافأة", style=discord.ButtonStyle.danger, emoji="🗑️", row=2, custom_id="p_reward_del_v12")
    async def reward_del_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🗑️ حذف رول مكافأة", description="اختر الرتب اللي عاوز تشيلها من المكافآت:", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=RewardRemoveView(self.panel_inter), ephemeral=True)

    @discord.ui.button(label="مكافأة التفاعل الدوري", style=discord.ButtonStyle.primary, emoji="🏅", row=2, custom_id="p_periodic_v12")
    async def periodic_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PeriodicRewardModal(await SETTINGS.get(interaction.guild.id)))

    @discord.ui.button(label="استبعاد روم أو رول", style=discord.ButtonStyle.danger, emoji="🚫", row=2, custom_id="p_ignore_combined_v11")
    async def ignore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await SETTINGS.get(interaction.guild.id)
        roles = " ".join(f"<@&{r}>" for r in list(cfg["ignored_roles"])[:15]) or "—"
        chans = " ".join(f"<#{c}>" for c in list(cfg["ignored_any"])[:15]) or "—"
        desc = f"اختر من القوائم أدناه. **اختيار عنصر مستبعد بالفعل بيرجّعه للنظام.**\n\n👥 **الرتب المستبعدة:** {roles}\n📁 **الرومات المستبعدة:** {chans}"
        await respond(interaction, embed=discord.Embed(title="🚫 استبعاد رومات أو رتب", description=clip(desc, 4000), color=COLOR_DARK), view=IgnoreSelectView(self.panel_inter), ephemeral=True)

    @discord.ui.button(label="نظام طرد المتخاذلين (5 أيام)", style=discord.ButtonStyle.blurple, emoji="🧹", row=3, custom_id="p_decay_v11")
    async def decay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        cfg = await SETTINGS.get(interaction.guild.id)
        await update_settings(interaction.guild.id, inactivity_decay_enabled=0 if cfg["inactivity_decay_enabled"] else 1)
        await interaction.edit_original_response(embed=await panel_embed(interaction.guild))


# ==============================================================================
# 📋 قائمة المتصدرين (لكل نوع مستواه الخاص)
# ==============================================================================
class TopTypeSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(label="النصي / Text XP", value="text", emoji="💬", default=(current == "text")),
            discord.SelectOption(label="الصوتي / Voice XP", value="voice", emoji="🎙️", default=(current == "voice")),
            discord.SelectOption(label="الرياكشن / Reactions", value="reaction", emoji="⭐", default=(current == "reaction")),
        ]
        super().__init__(placeholder="اختر قسم الترتيب يا فنان", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "TopLeaderboardView" = self.view
        view.top_type = self.values[0]
        view.page = 0
        await view.refresh(interaction)


class TopTimeframeSelect(discord.ui.Select):
    def __init__(self, current: str):
        options = [
            discord.SelectOption(label="الترتيب العام / All Time", value="all", emoji="🌐", default=(current == "all")),
            discord.SelectOption(label="اليومي / Daily", value="day", emoji="📅", default=(current == "day")),
            discord.SelectOption(label="الأسبوعي / Weekly", value="week", emoji="🗓️", default=(current == "week")),
            discord.SelectOption(label="الشهري / Monthly", value="month", emoji="📆", default=(current == "month")),
        ]
        super().__init__(placeholder="اختر الفترة الزمنية للترتيب", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: "TopLeaderboardView" = self.view
        view.timeframe = self.values[0]
        view.page = 0
        await view.refresh(interaction)


class TopLeaderboardView(SafeView):
    def __init__(self, guild: discord.Guild, owner_id: int, top_type: str = "text", timeframe: str = "all"):
        super().__init__(timeout=180)
        self.guild, self.owner_id = guild, owner_id
        self.top_type, self.timeframe, self.page = top_type, timeframe, 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        self.add_item(TopTypeSelect(self.top_type))
        self.add_item(TopTimeframeSelect(self.timeframe))
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page + 1 >= self.total_pages
        self.add_item(self.prev_btn)
        self.add_item(self.my_rank_btn)
        self.add_item(self.next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await respond(interaction, content="🔒 القائمة دي بتاعة اللي طلبها، اكتب `/top` وافتح قائمتك بنفسك.", ephemeral=True)
        return False

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def build_embed(self) -> discord.Embed:
        cfg = await SETTINGS.get(self.guild.id)
        field = xp_field(self.top_type, self.timeframe)
        lvl_field = f"{self.top_type}_level"
        extra = activity_filter(cfg)
        total, rows = await run_db(top_page_sync, self.guild.id, field, extra, self.page * PER_PAGE, PER_PAGE)
        self.total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        if self.page >= self.total_pages:  # الصفحة بقت أكبر من المتاح (بيانات اتغيرت)
            self.page = self.total_pages - 1
            total, rows = await run_db(top_page_sync, self.guild.id, field, extra, self.page * PER_PAGE, PER_PAGE)

        lines = []
        for i, doc in enumerate(rows, self.page * PER_PAGE + 1):
            level = doc.get(lvl_field, 0)  # ليفل نفس النوع المعروض (مش الليفل العام)
            roles = earned_reward_roles(self.guild, cfg, self.top_type, level)
            roles_str = f" ⟵ {' ، '.join(roles[:3])}{' …' if len(roles) > 3 else ''}" if roles else ""
            lines.append(f"#{i}• <@{doc['user_id']}>: `{doc.get(field, 0)}` XP (ليفل {level}){roles_str}")

        tf_part = "" if self.timeframe == "all" else f" — {PERIOD_LABEL[self.timeframe]}"
        reset_str = ""
        if self.timeframe != "all":
            remaining = int((next_reset(self.timeframe) - local_now()).total_seconds())
            reset_str = f" ⏱️ (متبقي على التصفير: {format_remaining(remaining)})"
        embed = discord.Embed(
            title=f"📋 قائمة المتصدرين ({TYPE_LABEL[self.top_type]}){tf_part}{reset_str}",
            description="\n".join(lines) if lines else "لا توجد بيانات تفاعل في هذه الصفحة.",
            color=COLOR_DARK,
        )
        embed.set_footer(text=f"الصفحة {self.page + 1} من {self.total_pages} | {self.guild.name}")
        return embed

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await self.build_embed()
        self._rebuild()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="◀", row=2)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="ترتيبي", style=discord.ButtonStyle.secondary, row=2)
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await SETTINGS.get(self.guild.id)
        field = xp_field(self.top_type, self.timeframe)
        doc = await run_db(get_user_sync, self.guild.id, interaction.user.id)
        value = int(doc.get(field, 0)) if doc else 0
        if value <= 0:
            desc = "مش ظاهر في قائمة التوب حالياً."
        else:
            rank = await run_db(rank_sync, self.guild.id, field, value, activity_filter(cfg))
            level = doc.get(f"{self.top_type}_level", 0)
            desc = f"يا فنان، ترتيبك هو: `#{rank}`\n• **XP:** `{value}`\n• **الليفل ({TYPE_LABEL[self.top_type]}):** `{level}`"
        await respond(interaction, embed=discord.Embed(title="📍 ترتيبك", description=desc, color=COLOR_GREEN), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="▶", row=2)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.refresh(interaction)


# ==============================================================================
# 🧩 الـ Cog الرئيسي
# ==============================================================================
class UltimateLevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.msg_pending: dict[tuple[int, int], int] = {}
        self.text_cd: dict[tuple[int, int], float] = {}
        self.reaction_cd: dict[tuple[int, int], float] = {}
        self.shortcut_cd: dict[int, float] = {}

    async def cog_load(self):
        await run_db(ensure_indexes_sync)
        migrated = await run_db(migrate_user_stats_sync)
        if migrated:
            log.info("تم ترحيل بيانات %d عضو للنظام الجديد (مستويات منفصلة)", migrated)
        self.bot.add_view(LevelsAdminPanelView())
        self.voice_tracker.start()
        self.periodic_loop.start()

    async def cog_unload(self):
        self.voice_tracker.cancel()
        self.periodic_loop.cancel()
        await self._flush_messages()

    # ---------- منح الـ XP والترقية ----------
    async def award_xp(self, member: discord.Member, type_: str, amount: int, cfg: dict, extra_inc: Optional[dict] = None):
        try:
            inc = {f"{type_}_xp": amount}
            for p in PERIODS:
                inc[f"{p}_{type_}_xp"] = amount
            if extra_inc:
                inc.update(extra_inc)
            doc = await run_db(apply_user_update_sync, member.guild.id, member.id, inc, {"last_active_timestamp": int(time.time())})
            xp_total = int(doc.get(f"{type_}_xp", 0))
            cur_level = int(doc.get(f"{type_}_level", 0))
            new_level = level_from_xp(xp_total)
            if new_level > cur_level:
                claimed = await run_db(claim_level_sync, member.guild.id, member.id, f"{type_}_level", cur_level, new_level)
                if claimed:
                    await self.on_level_up(member, type_, new_level, xp_total, cfg)
        except Exception:
            log.exception("فشل منح الـ XP لـ %s", member.id)

    async def grant_rewards(self, member: discord.Member, type_: str, new_level: int, cfg: dict) -> list[discord.Role]:
        given = []
        me = member.guild.me
        for rw in cfg["rewards"]:
            if rw["level"] > new_level or not reward_matches(rw["req_type"], type_):
                continue
            role = member.guild.get_role(rw["role_id"])
            if role is None or role in member.roles:
                continue
            if role.managed or role >= me.top_role:
                log.warning("مش قادر أدي الرتبة %s (أعلى من رتبة البوت أو رتبة خاصة)", role.id)
                continue
            try:
                await member.add_roles(role, reason=f"Level System: {type_} level {new_level}")
                given.append(role)
            except discord.HTTPException:
                log.warning("فشل منح الرتبة %s للعضو %s", role.id, member.id, exc_info=True)
        return given

    async def on_level_up(self, member: discord.Member, type_: str, new_level: int, xp_total: int, cfg: dict):
        guild = member.guild
        roles = await self.grant_rewards(member, type_, new_level, cfg)
        role_str = "".join(f"\n🎁 **مبروك يا فنان:** تم منحك رتبة المكافأة {r.mention}" for r in roles)
        label = TYPE_LABEL[type_]

        def fill(text: str, level_fmt: str) -> str:
            return (text.replace("{user}", member.mention).replace("{level}", level_fmt)
                    .replace("{type}", label).replace("{xp}", str(xp_total)).replace("{server}", guild.name))

        final_text = fill(cfg["level_message"] or DEFAULT_SETTINGS["level_message"], f"`{new_level}`")
        no_ping = discord.AllowedMentions(users=[member], roles=False, everyone=False)

        # إعلان الترقية: بيتبعت بس لو القناة اتحددت من اللوحة
        chan = guild.get_channel(cfg["announcement_channel"]) if cfg["announcement_channel"] else None
        if isinstance(chan, discord.abc.Messageable) and chan.permissions_for(guild.me).send_messages:
            try:
                img_url = cfg.get("level_image")
                if cfg["msg_type"] == "embed":
                    title = fill(cfg["level_embed_title"] or DEFAULT_SETTINGS["level_embed_title"], str(new_level))
                    embed = discord.Embed(
                        title=clip(title, 256),
                        description=clip(f"{final_text}{role_str}\n\n• **المستوى الحالي ({label}):** `{new_level}` 🏆", 4000),
                        color=COLOR_GREEN, timestamp=discord.utils.utcnow(),
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    if img_url:
                        embed.set_image(url=img_url)
                    await chan.send(content=f"🌟 عاش يا {member.mention}!", embed=embed, allowed_mentions=no_ping)
                else:
                    await chan.send(content=clip(f"🌟 {final_text}{role_str}\n{img_url or ''}", 2000), allowed_mentions=no_ping)
            except discord.HTTPException:
                log.warning("فشل إرسال إعلان الترقية", exc_info=True)

        # السجل: بيتبعت بس لو قناة السجلات اتحددت
        logs = guild.get_channel(cfg["logs_channel"]) if cfg["logs_channel"] else None
        if isinstance(logs, discord.abc.Messageable) and logs.permissions_for(guild.me).send_messages:
            try:
                log_embed = discord.Embed(
                    title="📋 سجل الترقية والنشاط",
                    description=clip(f"• **العضو:** {member.mention}\n• **وصل إلى المستوى:** `{new_level}` 🏆\n• **نوع التفاعل:** {label}{role_str}", 4000),
                    color=COLOR_BLUE, timestamp=discord.utils.utcnow(),
                )
                log_embed.set_thumbnail(url=member.display_avatar.url)
                await logs.send(embed=log_embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.warning("فشل إرسال سجل الترقية", exc_info=True)

        if cfg["dm_notifications"]:
            try:
                await member.send(embed=discord.Embed(
                    title=f"🏆 ترقية في {guild.name}",
                    description=clip(f"{fill(cfg['level_message'], f'`{new_level}`')}{role_str}", 4000), color=COLOR_GREEN))
            except discord.HTTPException:
                pass

    # ---------- الرسائل ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        cfg = await SETTINGS.get(message.guild.id)
        if not cfg["status"]:
            return
        if await self.handle_shortcuts(message, cfg):
            return
        if not cfg["text_xp_enabled"]:
            return
        member = message.author
        if is_channel_ignored(cfg, message.channel) or has_ignored_role(cfg, member):
            return

        key = (message.guild.id, member.id)
        self.msg_pending[key] = self.msg_pending.get(key, 0) + 1

        now = time.monotonic()
        if now - self.text_cd.get(key, 0) < cfg["text_cooldown"]:
            return
        self.text_cd[key] = now

        lo, hi = sorted((cfg["min_text_xp"], cfg["max_text_xp"]))
        mult = compute_multiplier(cfg, member, "text", message.channel.id, getattr(message.channel, "category_id", None))
        amount = int(random.randint(lo, hi) * mult)
        if amount <= 0:
            return
        pending = self.msg_pending.pop(key, 0)
        await self.award_xp(member, "text", amount, cfg, extra_inc={"messages": pending} if pending else None)

    async def handle_shortcuts(self, message: discord.Message, cfg: dict) -> bool:
        content = message.content.strip().lower()
        if not content:
            return False
        parts = content.split(maxsplit=1)
        first = parts[0]
        if first not in (cfg["shortcut_level"], cfg["shortcut_top"], cfg["shortcut_rewards"]):
            return False

        is_level = first == cfg["shortcut_level"]
        if is_level:
            mention_only = len(parts) == 2 and message.mentions and re.fullmatch(r"<@!?\d+>", parts[1].strip())
            if len(parts) > 1 and not mention_only:
                return False
        elif len(parts) > 1:
            return False

        now = time.monotonic()
        if now - self.shortcut_cd.get(message.author.id, 0) < SHORTCUT_COOLDOWN:
            return True
        self.shortcut_cd[message.author.id] = now

        try:
            if is_level:
                target = message.mentions[0] if message.mentions and isinstance(message.mentions[0], discord.Member) else message.author
                if target.bot:
                    return True
                await message.channel.send(embed=await self.build_level_embed(message.guild, target), allowed_mentions=discord.AllowedMentions.none())
            elif first == cfg["shortcut_top"]:
                view = TopLeaderboardView(message.guild, message.author.id)
                embed = await view.build_embed()
                view._rebuild()
                view.message = await message.channel.send(embed=embed, view=view)
            else:
                await message.channel.send(embed=await self.build_rewards_embed(message.guild))
        except discord.HTTPException:
            log.warning("فشل الرد على اختصار", exc_info=True)
        return True

    # ---------- الرياكشن ----------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        member = payload.member
        if not payload.guild_id or member is None or member.bot:
            return
        if getattr(payload, "message_author_id", None) == payload.user_id:
            return  # ممنوع تاخد XP من الرياكشن على رسالتك
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        cfg = await SETTINGS.get(guild.id)
        if not cfg["status"] or not cfg["reaction_xp_enabled"] or has_ignored_role(cfg, member):
            return
        channel = guild.get_channel_or_thread(payload.channel_id)
        if channel is not None and is_channel_ignored(cfg, channel):
            return

        key = (guild.id, member.id)
        now = time.monotonic()
        if now - self.reaction_cd.get(key, 0) < cfg["reaction_cooldown"]:
            return
        self.reaction_cd[key] = now

        lo, hi = sorted((cfg["min_reaction_xp"], cfg["max_reaction_xp"]))
        mult = compute_multiplier(cfg, member, "reaction", payload.channel_id, getattr(channel, "category_id", None))
        amount = int(random.randint(lo, hi) * mult)
        if amount > 0:
            await self.award_xp(member, "reaction", amount, cfg)

    # ---------- الفويس ----------
    @tasks.loop(minutes=1)
    async def voice_tracker(self):
        for guild in list(self.bot.guilds):
            try:
                await self._voice_guild(guild)
            except Exception:
                log.exception("خطأ في تتبع الفويس للسيرفر %s", guild.id)

    async def _voice_guild(self, guild: discord.Guild):
        cfg = await SETTINGS.get(guild.id)
        if not cfg["status"] or not cfg["voice_xp_enabled"]:
            return
        afk_id = guild.afk_channel.id if guild.afk_channel else None
        lo, hi = sorted((cfg["min_voice_xp"], cfg["max_voice_xp"]))
        for vc in guild.voice_channels:
            if vc.id == afk_id or is_channel_ignored(cfg, vc):
                continue
            for m in vc.members:
                vs = m.voice
                if m.bot or vs is None or vs.self_mute or vs.self_deaf or vs.mute or vs.deaf:
                    continue
                if has_ignored_role(cfg, m):
                    continue
                mult = compute_multiplier(cfg, m, "voice", vc.id, vc.category_id)
                amount = int(random.randint(lo, hi) * mult)
                if amount > 0:
                    await self.award_xp(m, "voice", amount, cfg, extra_inc={"voice_minutes": 1})

    @voice_tracker.before_loop
    async def before_voice_tracker(self):
        await self.bot.wait_until_ready()

    # ---------- التصفير الدوري ----------
    @tasks.loop(minutes=1)
    async def periodic_loop(self):
        try:
            await self._check_resets()
            await self._flush_messages()
            cutoff = time.monotonic() - 3600
            for d in (self.text_cd, self.reaction_cd):
                for k in [k for k, v in d.items() if v < cutoff]:
                    d.pop(k, None)
            for k in [k for k, v in self.shortcut_cd.items() if v < cutoff]:
                self.shortcut_cd.pop(k, None)
        except Exception:
            log.exception("خطأ في المهمة الدورية")

    @periodic_loop.before_loop
    async def before_periodic_loop(self):
        await self.bot.wait_until_ready()

    async def _flush_messages(self):
        if not self.msg_pending:
            return
        items = list(self.msg_pending.items())
        self.msg_pending.clear()
        try:
            await run_db(flush_messages_sync, items)
        except Exception:
            log.exception("فشل حفظ عدّاد الرسائل")

    async def _check_resets(self):
        keys = {p: period_key(p) for p in PERIODS}
        meta = await run_db(meta_get_sync)
        if not meta:  # أول تشغيل: نسجل الفترة الحالية من غير تصفير
            await run_db(meta_set_sync, keys)
            return
        changed = [p for p in PERIODS if meta.get(p) != keys[p]]
        for p in changed:
            await self._award_periodic(p)
            await run_db(reset_period_sync, p)
        if changed:
            await run_db(meta_set_sync, {p: keys[p] for p in changed})

    async def _award_periodic(self, period: str):
        for guild in list(self.bot.guilds):
            try:
                cfg = await SETTINGS.get(guild.id)
                if not cfg["status"] or not cfg["periodic_reward_role"] or cfg["periodic_type"] != period:
                    continue
                role = guild.get_role(cfg["periodic_reward_role"])
                if role is None or role.managed or role >= guild.me.top_role:
                    continue
                rows = await run_db(period_winners_sync, guild.id, period)
                winner, total = None, 0
                for row in rows:
                    m = guild.get_member(row["user_id"])
                    if m and not m.bot and not has_ignored_role(cfg, m):
                        winner, total = m, int(row["_total"])
                        break
                for m in list(role.members):
                    if winner is None or m.id != winner.id:
                        await m.remove_roles(role, reason="Level System: periodic reward ended")
                if winner and role not in winner.roles:
                    await winner.add_roles(role, reason="Level System: periodic reward winner")
                logs = guild.get_channel(cfg["logs_channel"]) if cfg["logs_channel"] else None
                if winner and isinstance(logs, discord.abc.Messageable) and logs.permissions_for(guild.me).send_messages:
                    await logs.send(
                        embed=discord.Embed(
                            title="🏅 صاحب مكافأة التفاعل",
                            description=f"• **الفائز ({PERIOD_LABEL[period]}):** {winner.mention}\n• **مجموع XP:** `{total}`\n• **الرتبة:** {role.mention}",
                            color=COLOR_GREEN, timestamp=discord.utils.utcnow()),
                        allowed_mentions=discord.AllowedMentions.none())
            except Exception:
                log.exception("فشل منح مكافأة التفاعل الدوري في %s", guild.id)

    # ---------- البطاقات ----------
    async def build_level_embed(self, guild: discord.Guild, target: discord.Member) -> discord.Embed:
        cfg = await SETTINGS.get(guild.id)
        doc = await run_db(get_user_sync, guild.id, target.id) or {}
        extra = activity_filter(cfg)

        data = {}
        for t in TYPES:
            xp = int(doc.get(f"{t}_xp", 0))
            lvl = int(doc.get(f"{t}_level", 0))
            rank = await run_db(rank_sync, guild.id, f"{t}_xp", xp, extra) if xp > 0 else None
            data[t] = {"xp": xp, "lvl": lvl, "rank": rank}

        personal = personal_multiplier(cfg, target)
        ev = cfg["event"]
        has_event = ev["mult"] > 1.0 and ev["end"] > time.time()
        server_mult = f"موجود 🟡 (`x{ev['mult']:g}` — {REQ_LABEL[ev['type']]})" if has_event else "مافيش ⚪"

        levels = {t: data[t]["lvl"] for t in TYPES}
        earned = []
        for rw in cfg["rewards"]:
            role = guild.get_role(rw["role_id"])
            if role and reward_earned(rw["req_type"], levels, rw["level"]):
                earned.append(role.mention)
        earned_str = clip(" ، ".join(earned), 1000) if earned else "لسه ما أخذتش رتب"

        embed = discord.Embed(color=COLOR_DARK)
        embed.set_author(name=f"📊 ‹ بطاقة إحصائيات ✦ {target.display_name} ›")
        embed.set_thumbnail(url=target.display_avatar.url)

        bars = []
        for t in TYPES:
            d = data[t]
            prev, nxt = level_bounds(d["lvl"])
            pct = (d["xp"] - prev) / (nxt - prev) if nxt > prev else 0
            rank_str = f"#{d['rank']}" if d["rank"] else "—"
            embed.add_field(
                name=f"🏆 ‹ المستوى {TYPE_LABEL[t]} ›",
                value=f"```\nالمستوى: {d['lvl']} ┃ الترتيب: {rank_str}\nXP: {d['xp']} / {nxt}\n```",
                inline=False,
            )
            bars.append(f"{TYPE_LABEL[t].split()[1]} {progress_bar(pct, personal)} `{int(max(0, min(1, pct)) * 100)}%`")

        embed.add_field(name="⚡ ‹ مضاعف السيرفر ›", value=server_mult, inline=False)
        embed.add_field(name="🛡️ ‹ مضاعفك الشخصي / رتبتك ›", value=f"```\nx{personal:g}\n```", inline=False)
        embed.add_field(name="📝 ‹ إجمالي رسائلك ›", value=f"```\n{int(doc.get('messages', 0))}\n```", inline=False)
        embed.add_field(name="🎙️ ‹ دقائقك الصوتية ›", value=f"```\n{int(doc.get('voice_minutes', 0))} دقيقة\n```", inline=False)
        embed.add_field(name="🎁 ‹ رتب المكافآت المكتسبة ›", value=earned_str, inline=False)
        embed.add_field(name="📈 ‹ شريط التقدم ›", value="\n".join(bars), inline=False)
        embed.set_footer(text=f"{guild.name} ✦ Level System | {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M')}")
        return embed

    async def build_rewards_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = await SETTINGS.get(guild.id)
        if not cfg["rewards"]:
            return discord.Embed(title="🎁 لوحة المكافآت", description="لم يتم تعديل أو إضافة أي رتب مكافآت في النظام حتى الآن.", color=COLOR_RED)
        lines = [f"• **المستوى {rw['level']}** ⟵ <@&{rw['role_id']}> (النوع: {REQ_LABEL.get(rw['req_type'], rw['req_type'])})" for rw in cfg["rewards"]]
        embed = discord.Embed(
            title="🎁 ‹ جدول رتب المكافآت المتاحة بالسيرفر ›",
            description=clip("\n".join(lines), 4000), color=COLOR_DARK, timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{guild.name} ✦ Rewards System")
        return embed

    # ---------- الأوامر ----------
    @app_commands.command(name="top", description="عرض المتصدرين في السيرفر")
    @app_commands.guild_only()
    async def top(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = TopLeaderboardView(interaction.guild, interaction.user.id)
        embed = await view.build_embed()
        view._rebuild()
        view.message = await interaction.followup.send(embed=embed, view=view, wait=True)

    @app_commands.command(name="rewards", description="عرض جدول رتب والمستويات المتاحة في السيرفر")
    @app_commands.guild_only()
    async def rewards(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(embed=await self.build_rewards_embed(interaction.guild), ephemeral=True)

    @app_commands.command(name="level", description="استعراض مستواك ورانكك الحالي")
    @app_commands.guild_only()
    async def level(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        if target.bot:
            await interaction.response.send_message(embed=err_embed("البوتات معندهاش مستويات 😄"), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(embed=await self.build_level_embed(interaction.guild, target))

    @app_commands.command(name="setup_levels", description="[الإدارة] لوحة تحكم المستويات والشات")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_levels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = LevelsAdminPanelView(panel_inter=interaction)
        await interaction.followup.send(embed=await panel_embed(interaction.guild), view=view, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ الأمر ده للإدارة فقط.", ephemeral=True)
            return
        log.exception("خطأ في أمر سلاش", exc_info=error)
        await report_error(interaction)


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير موجود في ملف .env، نظام المستويات محتاج قاعدة بيانات.")
    await bot.add_cog(UltimateLevelsCog(bot))
