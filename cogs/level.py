"""
⚡ نظام المستويات والتفاعل (النسخة الاحترافية v3)

ملاحظات مهمة:
- لكل عضو 3 مستويات منفصلة: نصي / صوتي / رياكشن. والأقسام المتوقفة بتختفي تماماً من رسائل الأعضاء.
- منحنى الـ XP الجديد تصاعدي (كل ليفل أصعب من اللي قبله). والبيانات القديمة بتتحول أوتوماتيك مع الحفاظ على ليفل كل عضو.
- رسائل الترقية والمكافآت بالأقواس المربعة [user] [level] [type] [xp] [server] [role] (والقديمة {user} بتتحول لوحدها).
- كل الـ XP بيتجمع في الذاكرة ويتحفظ دفعات كل 5 ثواني (أسرع بكتير على السيرفرات الكبيرة).
- التصفير اليومي/الأسبوعي/الشهري الساعة 12 ظهراً بتوقيت LEVELS_TZ (الافتراضي Africa/Cairo) في ملف .env.
- محتاج Intents: members + message_content + voice_states.
"""
import asyncio
import calendar
import datetime
import json
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
COLOR_ORANGE = 0xFFA500

TYPES = ("text", "voice", "reaction")
PERIODS = ("day", "week", "month")
TYPE_LABEL = {"text": "النصي 💬", "voice": "الصوتي 🎙️", "reaction": "الرياكشن ⭐"}
TYPE_EMOJI = {"text": "💬", "voice": "🎙️", "reaction": "⭐"}
SHORT_LABEL = {"text": "نصي 💬", "voice": "صوتي 🎙️", "reaction": "ريأكشن 😄"}
PERIOD_LABEL = {"all": "العام", "day": "اليومي", "week": "الأسبوعي", "month": "الشهري"}
NOTIFY_MODES = {"mention": "منشن في الإعلان", "silent": "إعلان من غير منشن", "dm": "إشعار في الخاص بس", "off": "بدون أي إشعار"}
PLACEHOLDERS = ("user", "level", "type", "xp", "server", "role")

MAX_LEVEL = 1000
SETTINGS_TTL = 120          # ثواني: مدة كاش الإعدادات
SHORTCUT_COOLDOWN = 5       # ثواني بين استخدام الاختصارات
TOP_CACHE_TTL = 15          # ثواني: كاش صفحات التوب (يخفف الضغط على السيرفرات الكبيرة)
XP_FLUSH_SECONDS = 5        # كل كام ثانية بنحفظ دفعة الـ XP
INACTIVITY_DAYS = 5
RESET_HOUR = 12
PER_PAGE = 5

# إعدادات خوارزمية توزيع الـ XP
DUPLICATE_WINDOW = 300      # نفس الرسالة بالظبط خلال المدة دي = 0 XP
VOICE_ALONE_FACTOR = 0.5    # لو العضو لوحده في الروم الصوتي
VOICE_VIDEO_FACTOR = 1.25   # كاميرا أو بث
FATIGUE_FLOOR = 0.35        # أقل نسبة بيوصلها الـ XP بعد الإفراط
FATIGUE_WINDOW = 3600

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
    "level_message_enabled": 1,
    "level_message": "يا هلا يا [user]! لقد صعدت إلى المستوى [level] بنجاح، استمر في تفاعلك الجامد!",
    "level_embed_title": "♦ ترقية إلى المستوى [level]",
    "level_image": None,
    "reward_message_enabled": 1,
    "reward_message": "🎁 **مبروك يا فنان:** تم منحك رتبة المكافأة [role]",
    "dm_notifications": 0,
    "anti_grind_enabled": 1,
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
BOOL_SETTINGS = ("status", "dm_notifications", "text_xp_enabled", "voice_xp_enabled", "reaction_xp_enabled",
                 "inactivity_decay_enabled", "level_message_enabled", "reward_message_enabled", "anti_grind_enabled")


def _new_user_defaults() -> dict:
    d: dict[str, Any] = {"messages": 0, "voice_minutes": 0, "last_active_timestamp": 0, "curve_v": 2}
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
# 🧮 منحنى المستويات (تصاعدي الصعوبة) والوقت
# ==============================================================================
def cumulative_xp(level: int) -> int:
    """إجمالي الـ XP المطلوب للوصول لمستوى معين. الانتقال من ليفل n للي بعده بيكلف 5n² + 50n + 100،
    يعني كل ليفل أصعب من اللي قبله بشكل تدريجي (ليفل 10 ≈ 4.7 ألف، ليفل 50 ≈ 107 ألف، ليفل 100 ≈ 1.9 مليون)."""
    L = max(0, min(int(level), MAX_LEVEL))
    return 5 * (L - 1) * L * (2 * L - 1) // 6 + 25 * L * (L - 1) + 100 * L


MAX_XP = cumulative_xp(MAX_LEVEL)


def xp_for_next(level: int) -> int:
    return cumulative_xp(level + 1)


def level_from_xp(xp: int) -> int:
    if xp <= 0:
        return 0
    lo, hi = 0, MAX_LEVEL
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if cumulative_xp(mid) <= xp:
            lo = mid
        else:
            hi = mid - 1
    return lo


def level_bounds(level: int) -> tuple[int, int]:
    return cumulative_xp(level), cumulative_xp(level + 1)


# ----- المنحنى القديم (للترحيب بالبيانات القديمة بس) -----
def _legacy_cumulative(level: int) -> int:
    return 0 if level <= 0 else int(level * 300 + ((level - 1) ** 1.2) * 120)


def _legacy_level_from_xp(xp: int) -> int:
    lvl = 0
    while lvl < 1000 and xp >= _legacy_cumulative(lvl + 1):
        lvl += 1
    return lvl


def convert_legacy_xp(old_xp: int) -> int:
    """بيحوّل XP قديم لمنحنى جديد مع الحفاظ على الليفل ونسبة التقدم جواه."""
    lvl = _legacy_level_from_xp(old_xp)
    lo, hi = _legacy_cumulative(lvl), _legacy_cumulative(lvl + 1)
    frac = (old_xp - lo) / (hi - lo) if hi > lo else 0.0
    new_lo, new_hi = cumulative_xp(lvl), cumulative_xp(lvl + 1)
    return int(new_lo + max(0.0, min(0.999, frac)) * (new_hi - new_lo))


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


def convert_legacy_braces(text: str) -> str:
    """الرسائل القديمة بالأقواس {user} بتتحول للأقواس المربعة [user]."""
    for name in PLACEHOLDERS:
        text = text.replace("{" + name + "}", "[" + name + "]")
    return text


def parse_type(text: str) -> str:
    """نوع واحد (للأحداث): text / voice / reaction / all."""
    t = normalize_ar(text)
    if "نص" in t or "text" in t:
        return "text"
    if "صوت" in t or "voice" in t:
        return "voice"
    if "ريا" in t or "react" in t:
        return "reaction"
    return "all"


def parse_req_type(text: str) -> Optional[str]:
    """شرط رتبة المكافأة: نوع واحد، أو أنواع مجمّعة بـ + (لازم الليفل في كلهم)، أو all (كل الأنواع المفعلة)، أو any (أي نوع)."""
    t = normalize_ar(text)
    types = []
    if "نص" in t or "text" in t:
        types.append("text")
    if "صوت" in t or "voice" in t:
        types.append("voice")
    if "ريا" in t or "react" in t:
        types.append("reaction")
    tokens = {x for x in re.split(r"[^\w]+", t) if x}
    if len(types) >= 2 and tokens & {"او", "or"}:
        return None  # "نصي أو صوتي" غير واضحة: لازم يستخدم + أو أي
    if types:
        return "+".join(types)
    if tokens & {"اي", "any", "ايا", "ايهم"}:
        return "any"
    return "all"


def req_label(req: str) -> str:
    if req == "any":
        return "أي نوع 🔀"
    if req == "all":
        return "كل الأنواع معاً 🌐"
    return " + ".join(SHORT_LABEL[t] for t in req.split("+") if t in SHORT_LABEL) or req


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
    for k in BOOL_SETTINGS:
        cfg[k] = bool(raw[k])
    for k in ("level_message", "reward_message", "level_embed_title"):
        cfg[k] = convert_legacy_braces(str(raw.get(k) or DEFAULT_SETTINGS[k]))
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
        try:
            cfg = await run_db(load_settings_sync, gid)
        except Exception:
            if gid in self._data:  # الداتابيز واقعة: نكمل بآخر إعدادات معروفة
                self._ts[gid] = now - SETTINGS_TTL + 30
                return self._data[gid]
            raise
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


def enabled_types(cfg: dict) -> list[str]:
    """الأقسام المفعّلة فقط (لو النظام كله متوقف → مفيش أقسام)."""
    if not cfg["status"]:
        return []
    return [t for t in TYPES if cfg[f"{t}_xp_enabled"]]


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
    """ترحيل لمرة واحدة: (1) فصل الـ xp القديم لنصي/صوتي/رياكشن (2) تحويل XP للمنحنى الجديد مع الحفاظ على الليفل.
    كل مستند بيتعلّم curve_v=2 بعد ما يتحول، فلو الترحيل وقف في النص بيكمل من غير ما يحوّل نفس المستند مرتين."""
    ops, count = [], 0
    for doc in user_stats_col.find({"curve_v": {"$exists": False}}):
        voice_xp = int(doc.get("voice_xp", 0) or 0)
        reaction_xp = int(doc.get("reaction_xp", 0) or 0)
        if "text_xp" in doc:
            text_xp = int(doc.get("text_xp", 0) or 0)
        else:
            text_xp = max(0, int(doc.get("xp", 0) or 0) - voice_xp - reaction_xp)
        new_vals = {t: convert_legacy_xp(v) for t, v in (("text", text_xp), ("voice", voice_xp), ("reaction", reaction_xp))}
        set_: dict[str, Any] = {"curve_v": 2}
        for t, xp in new_vals.items():
            set_[f"{t}_xp"] = xp
            set_[f"{t}_level"] = level_from_xp(xp)
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


def apply_batch_sync(gid: int, items: list, ts: int) -> dict:
    """بيطبّق دفعة XP لكذا عضو مرة واحدة (bulk) وبيرجّع بياناتهم الجديدة في استعلام واحد."""
    ops = []
    for uid, inc in items:
        defaults = {k: v for k, v in NEW_USER_DEFAULTS.items() if k not in inc and k != "last_active_timestamp"}
        ops.append(UpdateOne(
            {"guild_id": gid, "user_id": uid},
            {"$inc": inc, "$set": {"last_active_timestamp": ts, "left": False}, "$setOnInsert": defaults},
            upsert=True,
        ))
    user_stats_col.bulk_write(ops, ordered=False)
    uids = [u for u, _ in items]
    return {d["user_id"]: d for d in user_stats_col.find({"guild_id": gid, "user_id": {"$in": uids}})}


def claim_level_sync(gid: int, uid: int, field: str, old: int, new: int) -> bool:
    """تحديث ذري للمستوى: بيرجع True مرة واحدة بس (يمنع الإعلان المكرر)."""
    cond: dict[str, Any] = {field: old}
    if old == 0:
        cond = {"$or": [{field: 0}, {field: {"$exists": False}}]}
    res = user_stats_col.update_one({"guild_id": gid, "user_id": uid, **cond}, {"$set": {field: new}})
    return res.modified_count == 1


def get_user_sync(gid: int, uid: int) -> Optional[dict]:
    return user_stats_col.find_one({"guild_id": gid, "user_id": uid})


def set_user_fields_sync(gid: int, uid: int, sets: dict) -> dict:
    defaults = {k: v for k, v in NEW_USER_DEFAULTS.items() if k not in sets}
    return user_stats_col.find_one_and_update(
        {"guild_id": gid, "user_id": uid}, {"$set": sets, "$setOnInsert": defaults},
        upsert=True, return_document=ReturnDocument.AFTER)


def reset_all_sync(gid: int, types: list) -> int:
    sets: dict[str, Any] = {}
    for t in types:
        sets[f"{t}_xp"] = 0
        sets[f"{t}_level"] = 0
        for p in PERIODS:
            sets[f"{p}_{t}_xp"] = 0
    return user_stats_col.update_many({"guild_id": gid}, {"$set": sets}).modified_count


def mark_left_sync(gid: int, uid: int, left: bool):
    user_stats_col.update_one({"guild_id": gid, "user_id": uid}, {"$set": {"left": left}})


def rank_sync(gid: int, field: str, value: int, extra: dict) -> int:
    q = {"guild_id": gid, field: {"$gt": value}, **extra}
    return user_stats_col.count_documents(q) + 1


def top_page_sync(gid: int, field: str, extra: dict, skip: int, limit: int) -> tuple[int, list]:
    q = {"guild_id": gid, field: {"$gt": 0}, **extra}
    total = user_stats_col.count_documents(q)
    rows = list(user_stats_col.find(q).sort([(field, -1), ("user_id", 1)]).skip(skip).limit(limit))
    return total, rows


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
        {"$match": {"guild_id": gid, "left": {"$ne": True}}},
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


# ----- كاش صفحات التوب (للسيرفرات الكبيرة) -----
_TOP_CACHE: dict[tuple, tuple[float, int, list]] = {}


async def get_top_page(gid: int, field: str, extra: dict, skip: int, limit: int) -> tuple[int, list]:
    key = (gid, field, json.dumps(extra, sort_keys=True), skip, limit)
    hit = _TOP_CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < TOP_CACHE_TTL:
        return hit[1], hit[2]
    total, rows = await run_db(top_page_sync, gid, field, extra, skip, limit)
    if len(_TOP_CACHE) > 500:
        _TOP_CACHE.clear()
    _TOP_CACHE[key] = (now, total, rows)
    return total, rows


# ==============================================================================
# 🧠 منطق الـ XP والمضاعفات والمكافآت
# ==============================================================================
def visible_filter(cfg: dict) -> dict:
    """فلتر التوب والترتيب: بيخفي اللي غادروا السيرفر، وغير النشطين لو خيار طرد المتخاذلين شغال."""
    f: dict[str, Any] = {"left": {"$ne": True}}
    if cfg["inactivity_decay_enabled"]:
        cutoff = (int(time.time()) // 60) * 60 - INACTIVITY_DAYS * 86400  # مقرّب للدقيقة عشان الكاش يشتغل
        f["last_active_timestamp"] = {"$gte": cutoff}
    return f


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


# ----- شروط رتب المكافآت (نوع واحد / مجمّع / كل الأنواع / أي نوع) -----
def reward_possible(req: str, enabled: list[str]) -> bool:
    """هل الرتبة دي ممكن تتاخد أصلاً؟ (لو شرطها بيتطلب قسم متوقف بتتخفي)."""
    if not enabled:
        return False
    if req in ("any", "all"):
        return True
    return set(req.split("+")) <= set(enabled)


def reward_satisfied(req: str, need: int, levels: dict, enabled: list[str]) -> bool:
    if not reward_possible(req, enabled):
        return False
    if req == "any":
        return any(levels.get(t, 0) >= need for t in enabled)
    types = set(enabled) if req == "all" else set(req.split("+"))
    return all(levels.get(t, 0) >= need for t in types)


def reward_involves(req: str, type_: str) -> bool:
    return req in ("any", "all") or type_ in req.split("+")


def last_reward_role(guild: discord.Guild, cfg: dict, levels: dict, enabled: list[str], involving: Optional[str] = None) -> Optional[discord.Role]:
    """آخر رتبة مكافأة وصلها العضو (الأعلى ليفل، ولو متساويين الأعلى ترتيباً)."""
    best = None
    for rw in cfg["rewards"]:
        if not reward_satisfied(rw["req_type"], rw["level"], levels, enabled):
            continue
        if involving and not reward_involves(rw["req_type"], involving):
            continue
        role = guild.get_role(rw["role_id"])
        if role is None:
            continue
        key = (rw["level"], role.position)
        if best is None or key > best[0]:
            best = (key, role)
    return best[1] if best else None


def doc_levels(doc: Optional[dict]) -> dict:
    doc = doc or {}
    return {t: int(doc.get(f"{t}_level", 0) or 0) for t in TYPES}


BAR_PATTERNS = [
    (5.0, ["⬜"]), (4.5, ["⬜", "🟨"]), (4.0, ["🟨"]), (3.5, ["🟨", "🟧"]), (3.0, ["🟧"]),
    (2.5, ["🟧", "🟥"]), (2.0, ["🟥"]), (1.5, ["🟥", "🟩"]), (0.0, ["🟩"]),
]


def progress_bar(pct: float, mult: float, width: int = 12) -> str:
    filled = int(max(0.0, min(1.0, pct)) * width)
    pattern = next(p for m, p in BAR_PATTERNS if mult >= m)
    return "".join(pattern[i % len(pattern)] for i in range(filled)) + "⬛" * (width - filled)


# ----- جودة الرسالة (جزء من خوارزمية توزيع الـ XP) -----
_STRIP_RE = re.compile(r"<[^>]+>|https?://\S+")


def message_quality(content: str, attachments: int) -> tuple[float, str]:
    """بيرجّع (معامل الجودة, نص مطبّع). الرسائل القصيرة جداً بتاخد أقل، والرسائل الكاملة أكتر."""
    text = re.sub(r"\s+", " ", _STRIP_RE.sub("", content or "")).strip().lower()
    n = len(text)
    if n == 0:
        return (0.8 if attachments else 0.5), text
    if n < 4:
        return 0.3, text
    if n < 15:
        return 0.7, text
    if n < 100:
        return 1.0, text
    return 1.25, text


# ----- رسائل الترقية والمكافآت (بالأقواس المربعة) -----
def fill_template(text: str, **vars_: str) -> str:
    out = convert_legacy_braces(text)
    for name, value in vars_.items():
        out = out.replace("[" + name + "]", value)
    return out


def build_announcement(cfg: dict, member: discord.Member, type_: str, level: int, xp: int, role_mentions: list[str],
                       silent: bool = False) -> tuple[Optional[str], Optional[discord.Embed], list[str]]:
    """بيبني رسالة الإعلان. بيرجّع (النص, الإيمبد, الأجزاء). لو الرسالتين متوقفين مفيش إعلان."""
    guild = member.guild
    label = TYPE_LABEL[type_]
    who = member.display_name if silent else member.mention

    def fill(text: str, plain: bool = False, **extra: str) -> str:
        return fill_template(text, user=who, level=str(level) if plain else f"`{level}`", type=label,
                             xp=str(xp), server=guild.name, **extra)

    parts: list[str] = []
    if cfg["level_message_enabled"]:
        parts.append(fill(cfg["level_message"]))
    if cfg["reward_message_enabled"]:
        for rm in role_mentions:
            parts.append(fill(cfg["reward_message"], role=rm))
    if not parts:
        return None, None, []
    body = "\n".join(parts)
    img = cfg.get("level_image")
    if cfg["msg_type"] == "embed":
        embed = discord.Embed(
            title=clip(fill(cfg["level_embed_title"], plain=True), 256),
            description=clip(f"{body}\n\n• **المستوى الحالي ({label}):** `{level}` 🏆", 4000),
            color=COLOR_GREEN, timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if img:
            embed.set_image(url=img)
        return f"🌟 عاش يا {who}!", embed, parts
    return clip(f"🌟 {body}" + (f"\n{img}" if img else ""), 2000), None, parts


# ==============================================================================
# 🖼️ لوحة التحكم
# ==============================================================================
def generate_levels_panel_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    status_str = "شغال `🟢`" if cfg["status"] else "متوقف `🔴`"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg["announcement_channel"] else "`غير محددة (مفيش إعلانات)` 📌"
    logs_disp = f"<#{cfg['logs_channel']}>" if cfg["logs_channel"] else "`غير محددة (مفيش سجلات)` 📌"
    decay_str = "مفعل `✅`" if cfg["inactivity_decay_enabled"] else "مقفول `❌`"
    dm_str = "مفعل `✅`" if cfg["dm_notifications"] else "مقفول `❌`"
    on, off = "شغال `✅`", "مقفول `❌`"

    ev = cfg["event"]
    if ev["mult"] > 1.0 and ev["end"] > time.time():
        target_str = "السيرفر بالكامل" if ev["roles"] is None else "رتب محددة 🎯"
        event_str = f"`x{ev['mult']:g}` | {SHORT_LABEL.get(ev['type'], 'كل الأنواع 🌐')} | المدى: {target_str} | ينتهي <t:{ev['end']}:R>"
    else:
        event_str = "`لا يوجد حدث نشط` ⚪"

    periodic_disp = (
        f"<@&{cfg['periodic_reward_role']}> ({PERIOD_LABEL[cfg['periodic_type']]})" if cfg["periodic_reward_role"] else "`غير مفعلة` ⚪"
    )
    shortcuts_str = f"الليفل: `{cfg['shortcut_level']}` | التوب: `{cfg['shortcut_top']}` | المكافآت: `{cfg['shortcut_rewards']}`"

    desc = (
        "> **أهلاً بك يا فنان في لوحة التحكم المركزية لنظام التفاعل بالسيرفر.** 📊\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "### 🌐 ┃ الحالة العامة للنظام\n"
        f"> * **حالة النظام:** {status_str}\n"
        f"> * **قناة الإعلانات:** {chan_disp}\n"
        f"> * **قناة السجلات (Log):** {logs_disp}\n"
        f"> * **رسالة الترقية:** {on if cfg['level_message_enabled'] else off} ┊ **رسالة المكافأة:** {on if cfg['reward_message_enabled'] else off}\n"
        f"> * **إشعارات الخاص:** {dm_str} ┊ **حماية الإفراط:** {on if cfg['anti_grind_enabled'] else off}\n"
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
        super().__init__(title="💬 رسائل الترقية والمكافآت")
        self.msg_box = discord.ui.TextInput(
            label="رسالة الترقية ([user] [level] [type])", style=discord.TextStyle.paragraph,
            default=clip(cfg["level_message"], 1000), max_length=1000, required=True,
            placeholder="المتغيرات: [user] [level] [type] [xp] [server]")
        self.reward_box = discord.ui.TextInput(
            label="رسالة المكافأة ([role] [level] [user])", style=discord.TextStyle.paragraph,
            default=clip(cfg["reward_message"], 500), max_length=500, required=True,
            placeholder="بتتبعت لكل رتبة مكافأة بتتمنح. المتغير: [role]")
        self.type_box = discord.ui.TextInput(label="نوع الإعلان (embed أو text)", default=cfg["msg_type"], max_length=10)
        self.title_box = discord.ui.TextInput(label="عنوان الإيمبد ([level] [type])", default=clip(cfg["level_embed_title"], 100), max_length=100, required=False)
        self.image_box = discord.ui.TextInput(label="رابط صورة الترقية (اختياري)", default=cfg["level_image"] or "", placeholder="https://example.com/image.png", max_length=300, required=False)
        for box in (self.msg_box, self.reward_box, self.type_box, self.title_box, self.image_box):
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
            interaction.guild.id, level_message=self.msg_box.value, reward_message=self.reward_box.value, msg_type=m_type,
            level_embed_title=self.title_box.value.strip() or DEFAULT_SETTINGS["level_embed_title"], level_image=image,
        )
        await panel_modal_done(interaction, "✅ تسلم إيدك", "تم حفظ رسائل الترقية والمكافآت. جرّب زر 👁️ معاينة الرسائل.")


class LevelsRewardModal(SafeModal, title="🎁 إضافة رول مكافأة"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", placeholder="1234567890", max_length=30, required=True)
    lvl_box = discord.ui.TextInput(label="المستوى المطلوب للحصول عليها", placeholder="5", max_length=5, required=True)
    type_box = discord.ui.TextInput(
        label="الشرط (نصي / نصي+صوتي / الكل / أي)", default="الكل",
        placeholder="نصي أو صوتي أو رياكشن | اجمعهم بـ + (يلزم الليفل في الكل) | الكل = كل الأنواع المفعلة | أي = أي نوع",
        max_length=40, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ids = parse_ids(self.role_box.value)
        role = interaction.guild.get_role(ids[0]) if ids else None
        try:
            lvl = int(self.lvl_box.value.strip())
            if not 1 <= lvl <= MAX_LEVEL:
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
        req_type = parse_req_type(self.type_box.value)
        if req_type is None:
            await respond(interaction, embed=err_embed("الشرط مش واضح. استخدم **+** لو عاوز الليفل في أكتر من نوع (مثال: `نصي+صوتي`)، أو اكتب **أي** لو أي نوع كفاية."), ephemeral=True)
            return
        await interaction.response.defer()
        await run_db(add_reward_sync, interaction.guild.id, lvl, role.id, req_type)
        SETTINGS.invalidate(interaction.guild.id)
        await panel_modal_done(interaction, "✅ يا سلام يا فنان", f"تم ربط المستوى `{lvl}` بالرتبة {role.mention}\n• **الشرط:** {req_label(req_type)}")


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
        await panel_modal_done(interaction, "🎉 بدأ الحدث", f"المضاعف `x{mult:g}` على **{SHORT_LABEL.get(etype, 'كل الأنواع 🌐')}** وينتهي <t:{end}:R>.")


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


# ----- أزرار التشغيل والإيقاف (بتتعدل في نفس رسالة اللوحة) -----
TOGGLES = [
    ("status", "النظام العام", "🌐", "تشغيل/إيقاف نظام المستويات بالكامل."),
    ("text_xp_enabled", "القسم النصي", "💬", "XP الرسائل. لو اتقفل بيختفي من البطاقة والتوب."),
    ("voice_xp_enabled", "القسم الصوتي", "🎙️", "XP الفويس. لو اتقفل بيختفي من البطاقة والتوب."),
    ("reaction_xp_enabled", "قسم الرياكشن", "⭐", "XP الرياكشنات. لو اتقفل بيختفي من البطاقة والتوب."),
    ("level_message_enabled", "رسالة الترقية", "📢", "رسالة إعلان الترقية (محتاج قناة إعلانات)."),
    ("reward_message_enabled", "رسالة المكافأة", "🎁", "رسالة منح رتبة المكافأة."),
    ("dm_notifications", "إشعار الخاص", "✉️", "إرسال إشعار الترقية في خاص العضو."),
    ("anti_grind_enabled", "حماية الإفراط", "📉", "بيقلل الـ XP تدريجياً بعد ساعة تفاعل مكثف جداً."),
    ("inactivity_decay_enabled", "طرد المتخاذلين", "🧹", "بيخفي غير النشطين (5 أيام) من التوب والترتيب."),
]


def build_toggles_embed(cfg: dict) -> discord.Embed:
    lines = [f"{emoji} **{label}:** {'🟩 مفعل' if cfg[key] else '⬜ متوقف'} — {desc}" for key, label, emoji, desc in TOGGLES]
    return discord.Embed(
        title="🔄 تشغيل وإيقاف الأنظمة",
        description="اضغط على أي زر لتغيير حالته فوراً:\n\n" + "\n".join(lines),
        color=COLOR_DARK,
    )


class TogglesView(SafeView):
    def __init__(self, cfg: dict, panel_inter: Optional[discord.Interaction]):
        super().__init__(timeout=300)
        self.panel_inter = panel_inter
        for key, label, emoji, _ in TOGGLES:
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.success if cfg[key] else discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(key)
            self.add_item(btn)
        back = discord.ui.Button(label="رجوع للوحة", emoji="↩️", style=discord.ButtonStyle.primary)
        back.callback = self._back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await respond(interaction, embed=err_embed("اللوحة دي للإدارة فقط."), ephemeral=True)
        return False

    def _make_cb(self, key: str):
        async def cb(interaction: discord.Interaction):
            cfg = await SETTINGS.get(interaction.guild.id)
            await update_settings(interaction.guild.id, **{key: int(not cfg[key])})
            _TOP_CACHE.clear()
            new_cfg = await SETTINGS.get(interaction.guild.id)
            await interaction.response.edit_message(embed=build_toggles_embed(new_cfg), view=TogglesView(new_cfg, self.panel_inter))
        return cb

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=await panel_embed(interaction.guild), view=LevelsAdminPanelView(self.panel_inter))


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

    @discord.ui.button(label="تشغيل / إيقاف الأنظمة", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_v11")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await SETTINGS.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_toggles_embed(cfg), view=TogglesView(cfg, self.panel_inter))

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

    @discord.ui.button(label="رسائل الترقية والمكافآت", style=discord.ButtonStyle.secondary, emoji="💬", row=1, custom_id="p_msg_v11")
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
        _TOP_CACHE.clear()
        await interaction.edit_original_response(embed=await panel_embed(interaction.guild))

    @discord.ui.button(label="معاينة الرسائل", style=discord.ButtonStyle.green, emoji="👁️", row=3, custom_id="p_preview_v13")
    async def preview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cfg = await SETTINGS.get(interaction.guild.id)
        me = interaction.user
        sample_type = (enabled_types(cfg) or ["text"])[0]
        sample_level = 7
        content, embed, parts = build_announcement(cfg, me, sample_type, sample_level, cumulative_xp(sample_level) + 120, ["**@اسم-الرتبة**"])
        if not parts:
            await interaction.followup.send(embed=err_embed("رسالة الترقية ورسالة المكافأة الاتنين متوقفين، فمفيش إعلان بيتبعت.", "⚠️ مفيش معاينة"), ephemeral=True)
            return
        note = "👁️ **معاينة إعلان الترقية** (بياناتك كمثال):"
        if not cfg["announcement_channel"]:
            note += "\n⚠️ _لسه ما حددتش قناة إعلانات، فالإعلان مش هيتبعت فعلياً._"
        try:
            await interaction.followup.send(content=f"{note}\n{content or ''}", embed=embed, ephemeral=True) if embed else \
                await interaction.followup.send(content=f"{note}\n{content}", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send(content=f"{note}\n⚠️ رابط الصورة غير صالح.", ephemeral=True)


# ==============================================================================
# 📋 قائمة المتصدرين (لكل نوع مستواه الخاص، والمفعّل فقط)
# ==============================================================================
class TopTypeSelect(discord.ui.Select):
    def __init__(self, current: str, enabled: list[str]):
        options = [
            discord.SelectOption(label={"text": "النصي / Text XP", "voice": "الصوتي / Voice XP", "reaction": "الرياكشن / Reactions"}[t],
                                 value=t, emoji=TYPE_EMOJI[t], default=(current == t))
            for t in enabled
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
    def __init__(self, guild: discord.Guild, owner_id: int, enabled: list[str], top_type: Optional[str] = None, timeframe: str = "all"):
        super().__init__(timeout=180)
        self.guild, self.owner_id = guild, owner_id
        self.enabled = enabled
        self.top_type = top_type if top_type in enabled else (enabled[0] if enabled else "text")
        self.timeframe, self.page = timeframe, 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        if self.enabled:
            self.add_item(TopTypeSelect(self.top_type, self.enabled))
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
        self.enabled = enabled_types(cfg)
        if not self.enabled:
            return discord.Embed(title="📋 قائمة المتصدرين", description="⏸️ كل أقسام التفاعل متوقفة حالياً.", color=COLOR_DARK)
        if self.top_type not in self.enabled:  # الأدمن قفل القسم ده وإحنا شغالين
            self.top_type, self.page = self.enabled[0], 0
        field = xp_field(self.top_type, self.timeframe)
        extra = visible_filter(cfg)
        total, rows = await get_top_page(self.guild.id, field, extra, self.page * PER_PAGE, PER_PAGE)
        self.total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        if self.page >= self.total_pages:  # الصفحة بقت أكبر من المتاح (بيانات اتغيرت)
            self.page = self.total_pages - 1
            total, rows = await get_top_page(self.guild.id, field, extra, self.page * PER_PAGE, PER_PAGE)

        lines = []
        for i, doc in enumerate(rows, self.page * PER_PAGE + 1):
            levels = doc_levels(doc)
            level = levels[self.top_type]  # ليفل نفس النوع المعروض
            role = last_reward_role(self.guild, cfg, levels, self.enabled, involving=self.top_type)
            lines.append(f"#{i}• <@{doc['user_id']}>: `{doc.get(field, 0)}` XP (ليفل {level})" + (f" ⟵ {role.mention}" if role else ""))

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
        if self.top_type not in enabled_types(cfg):
            await respond(interaction, content="⏸️ القسم ده اتوقف حالياً.", ephemeral=True)
            return
        field = xp_field(self.top_type, self.timeframe)
        doc = await run_db(get_user_sync, self.guild.id, interaction.user.id)
        value = int(doc.get(field, 0)) if doc else 0
        if value <= 0:
            desc = "مش ظاهر في قائمة التوب حالياً."
        else:
            rank = await run_db(rank_sync, self.guild.id, field, value, visible_filter(cfg))
            level = doc.get(f"{self.top_type}_level", 0)
            desc = f"يا فنان، ترتيبك هو: `#{rank}`\n• **XP:** `{value}`\n• **الليفل ({TYPE_LABEL[self.top_type]}):** `{level}`"
        await respond(interaction, embed=discord.Embed(title="📍 ترتيبك", description=desc, color=COLOR_GREEN), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="▶", row=2)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.refresh(interaction)


class ConfirmView(SafeView):
    def __init__(self, owner_id: int, on_confirm, label: str = "تأكيد"):
        super().__init__(timeout=30)
        self.owner_id, self.on_confirm = owner_id, on_confirm
        self.confirm_btn.label = label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="تأكيد", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="تم الإلغاء.", embed=None, view=None)
        self.stop()


# ==============================================================================
# 🚀 تجميع الـ XP (Batching) — الأساس لدعم السيرفرات الكبيرة
# ==============================================================================
class XpBatcher:
    """بيجمّع كل الـ XP في الذاكرة ويتحفظ دفعات، بدل ما كل رسالة تعمل عملية داتابيز لوحدها."""

    def __init__(self):
        self.entries: dict[tuple[int, int], dict] = {}

    def add(self, member: discord.Member, type_: Optional[str], amount: int, extra_inc: Optional[dict] = None):
        key = (member.guild.id, member.id)
        e = self.entries.get(key)
        if e is None:
            e = self.entries[key] = {"member": member, "inc": {}, "types": set()}
        e["member"] = member
        inc = e["inc"]
        if type_ and amount > 0:
            for field in (f"{type_}_xp", *[f"{p}_{type_}_xp" for p in PERIODS]):
                inc[field] = inc.get(field, 0) + amount
            e["types"].add(type_)
        for k, v in (extra_inc or {}).items():
            inc[k] = inc.get(k, 0) + v

    def take(self) -> dict:
        taken, self.entries = self.entries, {}
        return taken

    def requeue(self, gid: int, items: list):
        for uid, e in items:
            cur = self.entries.get((gid, uid))
            if cur is None:
                self.entries[(gid, uid)] = e
                continue
            for k, v in e["inc"].items():
                cur["inc"][k] = cur["inc"].get(k, 0) + v
            cur["types"] |= e["types"]


# ==============================================================================
# 🧩 الـ Cog الرئيسي
# ==============================================================================
TYPE_CHOICES = [
    app_commands.Choice(name="النصي 💬", value="text"),
    app_commands.Choice(name="الصوتي 🎙️", value="voice"),
    app_commands.Choice(name="الرياكشن ⭐", value="reaction"),
]


class UltimateLevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.batcher = XpBatcher()
        self.flush_lock = asyncio.Lock()
        self.text_cd: dict[tuple[int, int], float] = {}
        self.reaction_cd: dict[tuple[int, int], float] = {}
        self.shortcut_cd: dict[int, float] = {}
        self.last_text: dict[tuple[int, int], tuple[int, float]] = {}
        self.fatigue: dict[tuple[int, int, str], tuple[float, float]] = {}

    async def cog_load(self):
        await run_db(ensure_indexes_sync)
        migrated = await run_db(migrate_user_stats_sync)
        if migrated:
            log.info("تم ترحيل بيانات %d عضو للمنحنى الجديد (مع الحفاظ على الليفل)", migrated)
        self.bot.add_view(LevelsAdminPanelView())
        self.xp_flush_loop.start()
        self.voice_tracker.start()
        self.periodic_loop.start()

    async def cog_unload(self):
        self.xp_flush_loop.cancel()
        self.voice_tracker.cancel()
        self.periodic_loop.cancel()
        await self.flush_xp()

    # ---------- خوارزمية توزيع الـ XP ----------
    def fatigue_factor(self, key: tuple, soft_cap: float) -> float:
        """حماية الإفراط: بعد ما العضو يجمع XP كتير في ساعة واحدة الـ XP بيقل تدريجياً (حتى 35%)."""
        now = time.monotonic()
        start, acc = self.fatigue.get(key, (now, 0.0))
        if now - start > FATIGUE_WINDOW:
            start, acc = now, 0.0
        self.fatigue[key] = (start, acc)
        if soft_cap <= 0 or acc <= soft_cap:
            return 1.0
        return max(FATIGUE_FLOOR, soft_cap / acc)

    def fatigue_add(self, key: tuple, amount: float):
        start, acc = self.fatigue.get(key, (time.monotonic(), 0.0))
        self.fatigue[key] = (start, acc + amount)

    def roll_xp(self, cfg: dict, member: discord.Member, type_: str, quality: float, channel_id: Optional[int], category_id: Optional[int]) -> int:
        lo, hi = sorted((cfg[f"min_{type_}_xp"], cfg[f"max_{type_}_xp"]))
        base = random.randint(lo, hi)
        if base <= 0 or quality <= 0:
            return 0
        factor = quality * compute_multiplier(cfg, member, type_, channel_id, category_id)
        if cfg["anti_grind_enabled"] and type_ in ("text", "reaction"):
            key = (member.guild.id, member.id, type_)
            soft_cap = cfg[f"max_{type_}_xp"] * (30 if type_ == "text" else 20)
            factor *= self.fatigue_factor(key, soft_cap)
        return max(1, round(base * factor))

    def grant(self, member: discord.Member, type_: str, amount: int, cfg: dict, extra_inc: Optional[dict] = None):
        if amount <= 0:
            return
        if cfg["anti_grind_enabled"] and type_ in ("text", "reaction"):
            self.fatigue_add((member.guild.id, member.id, type_), amount)
        self.batcher.add(member, type_, amount, extra_inc)

    # ---------- حفظ الدفعات وفحص الترقيات ----------
    @tasks.loop(seconds=XP_FLUSH_SECONDS)
    async def xp_flush_loop(self):
        try:
            await self.flush_xp()
        except Exception:
            log.exception("خطأ في حفظ دفعة الـ XP")

    @xp_flush_loop.before_loop
    async def before_xp_flush(self):
        await self.bot.wait_until_ready()

    async def flush_xp(self):
        async with self.flush_lock:
            entries = self.batcher.take()
            if not entries:
                return
            by_guild: dict[int, list] = {}
            for (gid, uid), e in entries.items():
                by_guild.setdefault(gid, []).append((uid, e))
            for gid, items in by_guild.items():
                try:
                    docs = await run_db(apply_batch_sync, gid, [(uid, e["inc"]) for uid, e in items], int(time.time()))
                except Exception:
                    log.exception("فشل حفظ دفعة XP للسيرفر %s (هتتعاد المحاولة)", gid)
                    self.batcher.requeue(gid, items)
                    continue
                try:
                    cfg = await SETTINGS.get(gid)
                except Exception:
                    log.exception("تعذر قراءة إعدادات السيرفر %s لفحص الترقيات", gid)
                    continue
                for uid, e in items:
                    doc = docs.get(uid)
                    if doc and e["types"] and e["member"] is not None:
                        try:
                            await self._check_levels(e["member"], doc, e["types"], cfg)
                        except Exception:
                            log.exception("فشل فحص ترقية العضو %s", uid)

    async def _check_levels(self, member: discord.Member, doc: dict, types: set, cfg: dict):
        levels = doc_levels(doc)
        gid = member.guild.id
        for t in TYPES:
            if t not in types:
                continue
            xp_total = int(doc.get(f"{t}_xp", 0))
            new_level = level_from_xp(xp_total)
            if new_level > levels[t] and await run_db(claim_level_sync, gid, member.id, f"{t}_level", levels[t], new_level):
                levels[t] = new_level
                await self.on_level_up(member, t, new_level, xp_total, cfg, dict(levels), doc.get("notify_mode", "mention"))

    # ---------- الرتب والترقية ----------
    async def sync_rewards(self, member: discord.Member, cfg: dict, levels: dict, remove: bool = False) -> tuple[list[discord.Role], list[discord.Role]]:
        """بيمنح رتب المكافآت اللي العضو حقق شرطها (وبيسحب اللي مش مستحقها لو remove=True)."""
        enabled = enabled_types(cfg)
        me = member.guild.me
        should: dict[int, bool] = {}
        for rw in cfg["rewards"]:
            ok = reward_satisfied(rw["req_type"], rw["level"], levels, enabled)
            should[rw["role_id"]] = should.get(rw["role_id"], False) or ok
        given, removed = [], []
        for role_id, ok in should.items():
            role = member.guild.get_role(role_id)
            if role is None or role.managed or role >= me.top_role:
                continue
            try:
                if ok and role not in member.roles:
                    await member.add_roles(role, reason="Level System: reward")
                    given.append(role)
                elif not ok and remove and role in member.roles:
                    await member.remove_roles(role, reason="Level System: reward no longer earned")
                    removed.append(role)
            except discord.HTTPException:
                log.warning("فشل تعديل الرتبة %s للعضو %s", role_id, member.id, exc_info=True)
        return given, removed

    async def on_level_up(self, member: discord.Member, type_: str, new_level: int, xp_total: int, cfg: dict, levels: dict, notify_mode: str = "mention"):
        guild = member.guild
        given, _ = await self.sync_rewards(member, cfg, levels)
        role_mentions = [r.mention for r in given]
        silent = notify_mode == "silent"
        content, embed, parts = build_announcement(cfg, member, type_, new_level, xp_total, role_mentions, silent=silent)
        no_ping = discord.AllowedMentions(users=[member] if not silent else [], roles=False, everyone=False)

        # إعلان الترقية: بيتبعت بس لو القناة اتحددت من اللوحة وعضو مش مختار (خاص/بدون)
        chan = guild.get_channel(cfg["announcement_channel"]) if cfg["announcement_channel"] else None
        if parts and notify_mode in ("mention", "silent") and isinstance(chan, discord.abc.Messageable) \
                and chan.permissions_for(guild.me).send_messages:
            try:
                await chan.send(content=content, embed=embed, allowed_mentions=no_ping)
            except discord.HTTPException:
                log.warning("فشل إرسال إعلان الترقية", exc_info=True)

        # السجل: بيتبعت بس لو قناة السجلات اتحددت
        logs = guild.get_channel(cfg["logs_channel"]) if cfg["logs_channel"] else None
        if isinstance(logs, discord.abc.Messageable) and logs.permissions_for(guild.me).send_messages:
            try:
                extra = "".join(f"\n🎁 تم منحه: {m}" for m in role_mentions)
                log_embed = discord.Embed(
                    title="📋 سجل الترقية والنشاط",
                    description=clip(f"• **العضو:** {member.mention}\n• **وصل إلى المستوى:** `{new_level}` 🏆\n• **نوع التفاعل:** {TYPE_LABEL[type_]}{extra}", 4000),
                    color=COLOR_BLUE, timestamp=discord.utils.utcnow(),
                )
                log_embed.set_thumbnail(url=member.display_avatar.url)
                await logs.send(embed=log_embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.warning("فشل إرسال سجل الترقية", exc_info=True)

        if parts and (notify_mode == "dm" or (cfg["dm_notifications"] and notify_mode != "off")):
            try:
                await member.send(embed=discord.Embed(title=f"🏆 ترقية في {guild.name}", description=clip("\n".join(parts), 4000), color=COLOR_GREEN))
            except discord.HTTPException:
                pass

    # ---------- الرسائل ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return
        try:
            cfg = await SETTINGS.get(message.guild.id)
        except Exception:
            log.exception("تعذر قراءة الإعدادات")
            return
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
        self.batcher.add(member, None, 0, {"messages": 1})  # عدّاد الرسائل بيتحفظ مع الدفعة

        now = time.monotonic()
        if now - self.text_cd.get(key, 0) < cfg["text_cooldown"]:
            return
        self.text_cd[key] = now

        quality, normalized = message_quality(message.content, len(message.attachments))
        h = hash(normalized) if normalized else 0
        last = self.last_text.get(key)
        self.last_text[key] = (h, now)
        if normalized and last and last[0] == h and now - last[1] < DUPLICATE_WINDOW:
            return  # نفس الرسالة بالظبط: مفيش XP (ضد السبام)

        amount = self.roll_xp(cfg, member, "text", quality, message.channel.id, getattr(message.channel, "category_id", None))
        self.grant(member, "text", amount, cfg)

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
                view = TopLeaderboardView(message.guild, message.author.id, enabled_types(cfg))
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
        try:
            cfg = await SETTINGS.get(guild.id)
        except Exception:
            return
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
        amount = self.roll_xp(cfg, member, "reaction", 1.0, payload.channel_id, getattr(channel, "category_id", None))
        self.grant(member, "reaction", amount, cfg)

    # ---------- خروج/دخول الأعضاء (عشان التوب يفضل نضيف) ----------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.bot:
            try:
                await run_db(mark_left_sync, member.guild.id, member.id, True)
                _TOP_CACHE.clear()
            except Exception:
                log.warning("تعذر تعليم العضو كمغادر", exc_info=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            try:
                await run_db(mark_left_sync, member.guild.id, member.id, False)
            except Exception:
                log.warning("تعذر إرجاع العضو للترتيب", exc_info=True)

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
        for vc in guild.voice_channels:
            if vc.id == afk_id or is_channel_ignored(cfg, vc):
                continue
            humans = [m for m in vc.members if not m.bot]
            alone = len(humans) <= 1
            for m in humans:
                vs = m.voice
                if vs is None or vs.self_mute or vs.self_deaf or vs.mute or vs.deaf:
                    continue
                if has_ignored_role(cfg, m):
                    continue
                quality = VOICE_ALONE_FACTOR if alone else 1.0
                if vs.self_video or vs.self_stream:
                    quality *= VOICE_VIDEO_FACTOR
                amount = self.roll_xp(cfg, m, "voice", quality, vc.id, vc.category_id)
                self.grant(m, "voice", amount, cfg, extra_inc={"voice_minutes": 1})

    @voice_tracker.before_loop
    async def before_voice_tracker(self):
        await self.bot.wait_until_ready()

    # ---------- التصفير الدوري والتنظيف ----------
    @tasks.loop(minutes=1)
    async def periodic_loop(self):
        try:
            await self._check_resets()
            now = time.monotonic()
            for d, ttl in ((self.text_cd, 3600), (self.reaction_cd, 3600), (self.shortcut_cd, 3600)):
                for k in [k for k, v in d.items() if now - v > ttl]:
                    d.pop(k, None)
            for k in [k for k, v in self.last_text.items() if now - v[1] > DUPLICATE_WINDOW]:
                self.last_text.pop(k, None)
            for k in [k for k, v in self.fatigue.items() if now - v[0] > FATIGUE_WINDOW]:
                self.fatigue.pop(k, None)
        except Exception:
            log.exception("خطأ في المهمة الدورية")

    @periodic_loop.before_loop
    async def before_periodic_loop(self):
        await self.bot.wait_until_ready()

    async def _check_resets(self):
        keys = {p: period_key(p) for p in PERIODS}
        meta = await run_db(meta_get_sync)
        if not meta:  # أول تشغيل: نسجل الفترة الحالية من غير تصفير
            await run_db(meta_set_sync, keys)
            return
        changed = [p for p in PERIODS if meta.get(p) != keys[p]]
        for p in changed:
            await self.flush_xp()  # نحفظ اللي في الذاكرة قبل التصفير
            await self._award_periodic(p)
            await run_db(reset_period_sync, p)
            _TOP_CACHE.clear()
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
        enabled = enabled_types(cfg)
        if not enabled:
            return discord.Embed(title="⏸️ النظام متوقف", description="كل أقسام التفاعل متوقفة حالياً.", color=COLOR_DARK)
        await self.flush_xp()  # عشان البطاقة تعرض آخر XP (حتى اللي لسه في الذاكرة)
        doc = await run_db(get_user_sync, guild.id, target.id) or {}
        extra = visible_filter(cfg)

        data = {}
        for t in enabled:
            xp = int(doc.get(f"{t}_xp", 0))
            lvl = int(doc.get(f"{t}_level", 0))
            rank = await run_db(rank_sync, guild.id, f"{t}_xp", xp, extra) if xp > 0 else None
            data[t] = {"xp": xp, "lvl": lvl, "rank": rank}

        personal = personal_multiplier(cfg, target)
        ev = cfg["event"]
        has_event = ev["mult"] > 1.0 and ev["end"] > time.time() and (ev["type"] == "all" or ev["type"] in enabled)
        server_mult = f"موجود 🟡 (`x{ev['mult']:g}` — {SHORT_LABEL.get(ev['type'], 'كل الأنواع 🌐')})" if has_event else "مافيش ⚪"
        last_role = last_reward_role(guild, cfg, doc_levels(doc), enabled)

        embed = discord.Embed(color=COLOR_DARK)
        embed.set_author(name=f"📊 ‹ بطاقة إحصائيات ✦ {target.display_name} ›")
        embed.set_thumbnail(url=target.display_avatar.url)

        bars = []
        for t in enabled:
            d = data[t]
            prev, nxt = level_bounds(d["lvl"])
            pct = (d["xp"] - prev) / (nxt - prev) if nxt > prev else 1.0
            rank_str = f"#{d['rank']}" if d["rank"] else "—"
            embed.add_field(
                name=f"🏆 ‹ المستوى {TYPE_LABEL[t]} ›",
                value=f"```\nالمستوى: {d['lvl']} ┃ الترتيب: {rank_str}\nXP: {d['xp']} / {nxt}\n```",
                inline=False,
            )
            bars.append(f"{TYPE_EMOJI[t]} {progress_bar(pct, personal)} `{int(max(0, min(1, pct)) * 100)}%`")

        embed.add_field(name="⚡ ‹ مضاعف السيرفر ›", value=server_mult, inline=False)
        embed.add_field(name="🛡️ ‹ مضاعفك الشخصي / رتبتك ›", value=f"```\nx{personal:g}\n```", inline=False)
        if "text" in enabled:
            embed.add_field(name="📝 ‹ إجمالي رسائلك ›", value=f"```\n{int(doc.get('messages', 0))}\n```", inline=False)
        if "voice" in enabled:
            embed.add_field(name="🎙️ ‹ دقائقك الصوتية ›", value=f"```\n{int(doc.get('voice_minutes', 0))} دقيقة\n```", inline=False)
        embed.add_field(name="🎁 ‹ آخر رتبة مكافأة وصلت لها ›", value=last_role.mention if last_role else "لسه ما أخذتش رتب", inline=False)
        embed.add_field(name="📈 ‹ شريط التقدم ›", value="\n".join(bars), inline=False)
        embed.set_footer(text=f"{guild.name} ✦ Level System | {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M')}")
        return embed

    async def build_rewards_embed(self, guild: discord.Guild) -> discord.Embed:
        cfg = await SETTINGS.get(guild.id)
        enabled = enabled_types(cfg)
        visible = [rw for rw in cfg["rewards"] if reward_possible(rw["req_type"], enabled)]
        if not enabled:
            return discord.Embed(title="⏸️ النظام متوقف", description="كل أقسام التفاعل متوقفة حالياً.", color=COLOR_DARK)
        if not visible:
            return discord.Embed(title="🎁 لوحة المكافآت", description="لم يتم تعديل أو إضافة أي رتب مكافآت في النظام حتى الآن.", color=COLOR_RED)
        lines = [f"• **المستوى {rw['level']}** ⟵ <@&{rw['role_id']}> (الشرط: {req_label(rw['req_type'])})" for rw in visible]
        embed = discord.Embed(
            title="🎁 ‹ جدول رتب المكافآت المتاحة بالسيرفر ›",
            description=clip("\n".join(lines), 4000), color=COLOR_DARK, timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{guild.name} ✦ Rewards System")
        return embed

    async def _ensure_active(self, interaction: discord.Interaction) -> Optional[dict]:
        cfg = await SETTINGS.get(interaction.guild.id)
        if not enabled_types(cfg):
            await respond(interaction, embed=discord.Embed(title="⏸️ النظام متوقف", description="كل أقسام التفاعل متوقفة حالياً.", color=COLOR_DARK), ephemeral=True)
            return None
        return cfg

    # ---------- أوامر الأعضاء ----------
    @app_commands.command(name="top", description="عرض المتصدرين في السيرفر")
    @app_commands.guild_only()
    async def top(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cfg = await SETTINGS.get(interaction.guild.id)
        view = TopLeaderboardView(interaction.guild, interaction.user.id, enabled_types(cfg))
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

    @app_commands.command(name="level_notify", description="اختار طريقة إشعارك لما تترقى (منشن / من غير منشن / خاص / بدون)")
    @app_commands.guild_only()
    @app_commands.describe(mode="طريقة الإشعار")
    @app_commands.choices(mode=[app_commands.Choice(name=v, value=k) for k, v in NOTIFY_MODES.items()])
    async def level_notify(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        await run_db(set_user_fields_sync, interaction.guild.id, interaction.user.id, {"notify_mode": mode.value})
        await interaction.followup.send(embed=ok_embed("✅ تم", f"إشعارات الترقية بتاعتك دلوقتي: **{NOTIFY_MODES[mode.value]}**"), ephemeral=True)

    # ---------- أوامر الإدارة (تعديل يدوي) ----------
    async def _manual_apply(self, interaction: discord.Interaction, member: discord.Member, sets_by_type: dict[str, int],
                            remove_roles: bool, action: str):
        """sets_by_type = {نوع: XP جديد}. بيعدّل النقاط والليفل بالظبط ويزامن الرتب ويسجل في اللوج."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        await self.flush_xp()  # نحفظ اللي في الذاكرة الأول عشان ما يتخبطش مع التعديل
        old = await run_db(get_user_sync, gid, member.id) or {}
        sets: dict[str, Any] = {}
        for t, xp in sets_by_type.items():
            xp = max(0, min(int(xp), MAX_XP))
            sets[f"{t}_xp"] = xp
            sets[f"{t}_level"] = level_from_xp(xp)
        doc = await run_db(set_user_fields_sync, gid, member.id, sets)
        _TOP_CACHE.clear()
        cfg = await SETTINGS.get(gid)
        given, removed = await self.sync_rewards(member, cfg, doc_levels(doc), remove=remove_roles)

        lines = []
        for t in sets_by_type:
            lines.append(f"• **{TYPE_LABEL[t]}:** XP `{int(old.get(f'{t}_xp', 0))}` ⟵ `{int(doc[f'{t}_xp'])}` ┃ ليفل `{int(old.get(f'{t}_level', 0))}` ⟵ `{int(doc[f'{t}_level'])}`")
            if not cfg[f"{t}_xp_enabled"]:
                lines.append(f"  ⚠️ _قسم {TYPE_LABEL[t]} متوقف حالياً (التعديل اتحفظ بس مش ظاهر للأعضاء)_")
        if given:
            lines.append("🎁 **رتب اتمنحت:** " + " ".join(r.mention for r in given))
        if removed:
            lines.append("➖ **رتب اتسحبت:** " + " ".join(r.mention for r in removed))
        embed = ok_embed(f"✅ {action}", f"العضو: {member.mention}\n" + "\n".join(lines))
        await interaction.followup.send(embed=embed, ephemeral=True)

        logs = interaction.guild.get_channel(cfg["logs_channel"]) if cfg["logs_channel"] else None
        if isinstance(logs, discord.abc.Messageable) and logs.permissions_for(interaction.guild.me).send_messages:
            try:
                log_embed = discord.Embed(title="🛠️ تعديل يدوي في المستويات", color=COLOR_ORANGE, timestamp=discord.utils.utcnow(),
                                          description=f"• **الإجراء:** {action}\n• **بواسطة:** {interaction.user.mention}\n• **العضو:** {member.mention}\n" + "\n".join(lines[:6]))
                await logs.send(embed=log_embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    @app_commands.command(name="set_xp", description="[الإدارة] ضبط نقاط الـ XP لعضو في قسم معين")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="العضو", section="القسم", value="قيمة الـ XP الجديدة", remove_roles="سحب رتب المكافآت اللي مبقاش يستحقها؟")
    @app_commands.choices(section=TYPE_CHOICES)
    async def set_xp(self, interaction: discord.Interaction, member: discord.Member, section: app_commands.Choice[str],
                     value: app_commands.Range[int, 0, MAX_XP], remove_roles: bool = False):
        if member.bot:
            await respond(interaction, embed=err_embed("البوتات معندهاش مستويات."), ephemeral=True)
            return
        await self._manual_apply(interaction, member, {section.value: value}, remove_roles, "ضبط XP")

    @app_commands.command(name="set_level", description="[الإدارة] ضبط ليفل عضو في قسم معين")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="العضو", section="القسم", level="الليفل الجديد", remove_roles="سحب رتب المكافآت اللي مبقاش يستحقها؟")
    @app_commands.choices(section=TYPE_CHOICES)
    async def set_level(self, interaction: discord.Interaction, member: discord.Member, section: app_commands.Choice[str],
                        level: app_commands.Range[int, 0, MAX_LEVEL], remove_roles: bool = False):
        if member.bot:
            await respond(interaction, embed=err_embed("البوتات معندهاش مستويات."), ephemeral=True)
            return
        await self._manual_apply(interaction, member, {section.value: cumulative_xp(level)}, remove_roles, "ضبط ليفل")

    @app_commands.command(name="add_xp", description="[الإدارة] إضافة أو خصم نقاط XP من عضو (اكتب رقم سالب للخصم)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="العضو", section="القسم", amount="عدد النقاط (سالب للخصم)", remove_roles="سحب رتب المكافآت اللي مبقاش يستحقها؟")
    @app_commands.choices(section=TYPE_CHOICES)
    async def add_xp(self, interaction: discord.Interaction, member: discord.Member, section: app_commands.Choice[str],
                     amount: app_commands.Range[int, -MAX_XP, MAX_XP], remove_roles: bool = False):
        if member.bot:
            await respond(interaction, embed=err_embed("البوتات معندهاش مستويات."), ephemeral=True)
            return
        await self.flush_xp()
        doc = await run_db(get_user_sync, interaction.guild.id, member.id) or {}
        current = int(doc.get(f"{section.value}_xp", 0))
        await self._manual_apply(interaction, member, {section.value: current + amount}, remove_roles, "إضافة/خصم XP")

    @app_commands.command(name="reset_xp", description="[الإدارة] تصفير مستويات عضو (قسم معين أو كل الأقسام)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="العضو", section="القسم (فاضي = كل الأقسام)", remove_roles="سحب رتب المكافآت اللي مبقاش يستحقها؟")
    @app_commands.choices(section=TYPE_CHOICES)
    async def reset_xp(self, interaction: discord.Interaction, member: discord.Member,
                       section: Optional[app_commands.Choice[str]] = None, remove_roles: bool = True):
        types = [section.value] if section else list(TYPES)
        await self._manual_apply(interaction, member, {t: 0 for t in types}, remove_roles, "تصفير")

    @app_commands.command(name="reset_all_xp", description="[الإدارة] تصفير مستويات كل أعضاء السيرفر (خطير! بيطلب تأكيد)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(section="القسم (فاضي = كل الأقسام)")
    @app_commands.choices(section=TYPE_CHOICES)
    async def reset_all_xp(self, interaction: discord.Interaction, section: Optional[app_commands.Choice[str]] = None):
        types = [section.value for _ in [0]] if section else list(TYPES)
        label = TYPE_LABEL[types[0]] if section else "كل الأقسام"

        async def do_reset(i: discord.Interaction):
            await self.flush_xp()
            count = await run_db(reset_all_sync, i.guild.id, types)
            _TOP_CACHE.clear()
            await i.followup.send(embed=ok_embed("🧹 تم التصفير", f"اتصفّر **{label}** لـ `{count}` عضو.\n_رتب المكافآت مش بتتسحب أوتوماتيك._"), ephemeral=True)

        embed = discord.Embed(title="⚠️ تأكيد التصفير الشامل",
                              description=f"هتصفّر **{label}** لكل أعضاء السيرفر وده **مش ممكن يترجع**. متأكد؟ (30 ثانية)", color=COLOR_RED)
        await interaction.response.send_message(embed=embed, view=ConfirmView(interaction.user.id, do_reset, "أيوه، صفّر الكل"), ephemeral=True)

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
