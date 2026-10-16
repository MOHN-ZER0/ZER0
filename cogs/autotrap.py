"""
⚡ نظام الرد التلقائي الاحترافي (/autoreply)

- أمر واحد /autoreply بيفتح قائمة: ➕ إضافة | ✏️ تعديل | 🗑️ حذف | 📋 القواعد (بنفس نظام الإيمبد).
- كل قاعدة = شرط + رومات + رد + إجراءات، وبتتحفظ في MongoDB (MONGODB_URI) وبتشتغل من الكاش (من غير ضغط على الداتابيز).
- الشرط: أي رسالة في الروم / كلمات مفتاحية (تحتوي، مطابقة تامة، تبدأ، تنتهي، كلمة كاملة) / روابط / دعوات / أي مرفق.
- الرد: نص أو إيمبد أو بدون رسالة، وتقدر تسيب كله فاضي وتحط الصورة بس. العنوان اختياري.
- التسليم: رد على رسالة العضو / رسالة جديدة / خاص، وحذف رسالة العضو (فوراً أو بعد تأخير)، وحذف رد البوت بعد ثواني.
- إجراءات إضافية: إيموجيات، ثريد تلقائي، منشن رتبة. وفلاتر: استثناء رتب، تفاعل مع البوتات، كولداون.
- التعديل على قاعدة محفوظة بيتطبق فوراً (من غير زرار تطبيق). وقواعد الملف القديم (JSON) بتتنقل أوتوماتيك.
- محتاج Intents: message_content (للكلمات المفتاحية). وصلاحيات البوت حسب القاعدة: Send Messages, Embed Links,
  Add Reactions, Manage Messages (للحذف), Create Public Threads, Read Message History.
"""
import asyncio
import copy
import json
import logging
import math
import os
import random
import re
import time
from typing import Any, Awaitable, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()
log = logging.getLogger("autoreply")

# ==============================================================================
# ⚙️ الثوابت
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_AutoReply_DB"
LEGACY_JSON = "ziuo_mega_autotrap_database.json"
DEBUG = os.getenv("AUTOREPLY_DEBUG", "1") == "1"

DEFAULT_COLOR = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_BLUE = 0x3498DB

MAX_RULES_PER_GUILD = 100
MAX_KEYWORDS = 50
MAX_REACTIONS = 20
MAX_CHANNELS = 25
MAX_DELETE_DELAY = 3600
PER_PAGE = 6
DB_TIMEOUT = 15.0

MODE_LABEL = {"every": "كل رسالة في الروم", "keywords": "كلمات مفتاحية", "links": "أي رابط", "invites": "دعوات ديسكورد فقط", "attachments": "أي مرفق / صورة"}
MODE_DESC = {"every": "أي رسالة تتبعت في الرومات المحددة", "keywords": "لو الرسالة فيها كلمة من كلماتك", "links": "أي رسالة فيها رابط", "invites": "رسائل فيها دعوة سيرفر ديسكورد", "attachments": "أي رسالة فيها صورة أو ملف"}
MATCH_LABEL = {"contains": "تحتوي على الكلمة", "exact": "مطابقة تامة", "starts": "تبدأ بالكلمة", "ends": "تنتهي بالكلمة", "word": "الكلمة كاملة"}
MATCH_DESC = {"contains": "الكلمة موجودة في أي مكان في الرسالة (الأنسب غالباً)", "exact": "الرسالة كلها = الكلمة بالظبط", "starts": "الرسالة بتبدأ بالكلمة", "ends": "الرسالة بتنتهي بالكلمة", "word": "الكلمة لوحدها مش جزء من كلمة تانية"}
TYPE_LABEL = {"text": "نص عادي", "embed": "إيمبد", "none": "بدون رسالة"}
DELIVERY_LABEL = {"reply": "رد على رسالة العضو", "send": "رسالة جديدة في الروم", "dm": "رسالة خاصة للعضو"}
PLACEHOLDERS = ("user", "userName", "displayName", "userId", "server", "channel", "keyword", "memberCount")

# ==============================================================================
# 💾 قاعدة البيانات
# ==============================================================================
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None
rules_col = _db["rules"] if _db is not None else None


async def run_db(fn, *args, **kwargs):
    return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), DB_TIMEOUT)


def ensure_indexes_sync():
    for keys, opts in (([("guild_id", 1), ("name_key", 1)], {"unique": True}), ([("guild_id", 1), ("created_at", 1)], {})):
        try:
            rules_col.create_index(keys, **opts)
        except Exception:
            log.warning("تعذر إنشاء index %s", keys, exc_info=True)


def load_all_sync() -> list:
    return list(rules_col.find({}))


def list_rules_sync(gid: int) -> list:
    return list(rules_col.find({"guild_id": gid}).sort("created_at", 1))


def get_rule_sync(rid: str) -> Optional[dict]:
    return rules_col.find_one({"_id": rid})


def insert_rule_sync(doc: dict):
    rules_col.insert_one(doc)


def update_rule_sync(rid: str, sets: dict):
    rules_col.update_one({"_id": rid}, {"$set": sets})


def delete_rule_sync(rid: str):
    rules_col.delete_one({"_id": rid})


def count_rules_sync(gid: int) -> int:
    return rules_col.count_documents({"guild_id": gid})


def search_rules_sync(gid: int, text: str, limit: int = 25) -> list:
    q: dict[str, Any] = {"guild_id": gid}
    if text:
        rx = {"$regex": re.escape(text), "$options": "i"}
        q["$or"] = [{"_id": {"$regex": "^" + re.escape(text)}}, {"data.name": rx}]
    return list(rules_col.find(q).sort("created_at", 1).limit(limit))


def flush_hits_sync(hits: dict, ts: int):
    for rid, n in hits.items():
        rules_col.update_one({"_id": rid}, {"$inc": {"hits": n}, "$set": {"last_hit": ts}})


# ==============================================================================
# 🧬 بنية القاعدة
# ==============================================================================
def new_rule() -> dict:
    return {
        "name": "", "enabled": True, "channels": [],
        "trigger": {"mode": "every", "keywords": [], "match": "contains", "collapse": True},
        "reply": {"type": "text", "text": "", "title": None, "color": DEFAULT_COLOR, "image_url": None, "thumbnail_url": None,
                  "footer_text": None, "footer_icon_url": None, "author_name": None, "author_icon_url": None,
                  "outside_text": None, "timestamp": False},
        "delivery": {"mode": "reply", "mention_author": False, "delete_trigger": False, "delete_trigger_after": 0, "delete_reply_after": 0},
        "actions": {"reactions": [], "thread": False, "thread_name": "نقاش: [userName]", "ping_role_id": None},
        "filters": {"allow_bots": False, "exempt_roles": [], "exempt_staff": False, "cooldown": 0},
    }


def sanitize(data: Optional[dict]) -> dict:
    base = new_rule()
    for key, value in (data or {}).items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key].update(copy.deepcopy(value))
        else:
            base[key] = copy.deepcopy(value)
    return base


def get_path(d: dict, path: tuple):
    for p in path:
        d = d[p]
    return d


def set_path(d: dict, path: tuple, value):
    for p in path[:-1]:
        d = d[p]
    d[path[-1]] = value


PRESETS = {
    "reply_all": ("رد على كل رسالة في روم", "كل رسالة في الروم بيرد عليها البوت (نص أو صورة)", "💬"),
    "keywords": ("رد على كلمات معينة", "لو الرسالة فيها كلمة من كلماتك بيرد", "🔑"),
    "reactions": ("إيموجيات تلقائية", "البوت يحط إيموجيات على كل رسالة", "😀"),
    "thread": ("ثريد تلقائي", "يفتح ثريد نقاش لكل رسالة", "🧵"),
    "antilink": ("حماية الروابط", "يحذف الروابط ويحذّر العضو", "🛡️"),
    "polls": ("تصويت اقتراحات", "يحط ⬆️ ⬇️ على كل اقتراح", "🗳️"),
    "role_ping": ("منشن رتبة عند كلمة", "لما حد يكتب كلمة معينة يتنشن رتبة", "🔔"),
    "blank": ("قاعدة فاضية", "ابدأ من الصفر وظبط كل حاجة بنفسك", "✨"),
}


def preset_data(key: str, channel_id: Optional[int]) -> dict:
    d = new_rule()
    d["channels"] = [channel_id] if channel_id else []
    d["name"] = PRESETS[key][0]
    if key == "reply_all":
        d["reply"]["text"] = "أهلاً بيك يا [user] في [server] 👋"
    elif key == "keywords":
        d["trigger"]["mode"] = "keywords"
        d["reply"]["text"] = "أهلاً [user]!"
    elif key == "reactions":
        d["reply"]["type"] = "none"
        d["actions"]["reactions"] = ["👍", "❤️"]
    elif key == "thread":
        d["reply"]["type"] = "none"
        d["actions"]["thread"] = True
    elif key == "antilink":
        d["trigger"]["mode"] = "links"
        d["reply"]["text"] = "⚠️ [user]، ممنوع إرسال الروابط هنا!"
        d["delivery"].update(mode="send", delete_trigger=True, delete_reply_after=5)
        d["filters"]["exempt_staff"] = True
    elif key == "polls":
        d["reply"]["type"] = "none"
        d["actions"]["reactions"] = ["⬆️", "⬇️"]
    elif key == "role_ping":
        d["trigger"]["mode"] = "keywords"
        d["reply"]["text"] = "🔔 تم طلب الدعم بواسطة [user]"
        d["delivery"]["mode"] = "send"
    return d


def migrate_old_rule(name: str, old: dict) -> dict:
    """تحويل قاعدة من الملف القديم (6 أنواع أنظمة) للشكل الجديد."""
    d = new_rule()
    d["name"] = name
    d["channels"] = [int(old["channel_id"])] if old.get("channel_id") else []
    d["filters"]["allow_bots"] = bool(old.get("allow_bots", False))
    kw = (old.get("custom_keyword") or "").strip()
    sys_type = old.get("system_type")
    d["reply"]["type"] = "none"
    if sys_type == "keyword_emoji":
        if kw:
            d["trigger"].update(mode="keywords", keywords=[kw])
        d["actions"]["reactions"] = [r for r in old.get("reactions", []) if r]
    elif sys_type == "auto_thread":
        d["actions"]["thread"] = True
    elif sys_type == "media_trap":
        rtype = old.get("reply_type", "text")
        d["reply"].update(type=rtype if rtype in TYPE_LABEL else "text", text=old.get("message_content", ""), image_url=old.get("image_url") or None)
        d["delivery"]["mode"] = "send"
    elif sys_type == "anti_spam":
        d["trigger"]["mode"] = "links"
        d["reply"].update(type="text", text="⚠️ [user]، ممنوع إرسال الروابط هنا!")
        d["delivery"].update(mode="send", delete_trigger=True, delete_reply_after=5)
    elif sys_type == "role_mention":
        if kw:
            d["trigger"].update(mode="keywords", keywords=[kw])
        d["reply"].update(type="text", text="🔔 تم طلب الدعم بواسطة [user]")
        d["delivery"]["mode"] = "send"
        d["actions"]["ping_role_id"] = old.get("target_role_id")
    elif sys_type == "voting_polls":
        d["actions"]["reactions"] = ["⬆️", "⬇️"]
    return d


def migrate_legacy_sync() -> int:
    if not os.path.exists(LEGACY_JSON):
        return 0
    try:
        with open(LEGACY_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        log.warning("تعذر قراءة ملف الرد التلقائي القديم", exc_info=True)
        return 0
    count, now = 0, int(time.time())
    for guild_id, rules in data.items():
        try:
            gid = int(guild_id)
        except ValueError:
            continue
        for name, old in (rules or {}).items():
            try:
                rule = migrate_old_rule(str(name), old)
                doc = {"_id": str(random.randint(100000, 999999)), "guild_id": gid, "name_key": str(name).strip().lower(), "created_by": 0,
                       "created_at": now + count, "updated_at": now, "hits": 0, "last_hit": None, "data": rule}
                rules_col.insert_one(doc)
                count += 1
            except (DuplicateKeyError, KeyError, ValueError, TypeError):
                continue
    try:
        os.replace(LEGACY_JSON, LEGACY_JSON + ".migrated")
    except OSError:
        pass
    return count


# ==============================================================================
# 🧰 دوال مساعدة
# ==============================================================================
def clip(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def ok_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_GREEN)


def err_embed(description: str, title: str = "❌ خطأ") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_RED)


def error_text(exc: BaseException) -> str:
    text = "❌ حصل خطأ أثناء تنفيذ الأمر، حاول تاني."
    if DEBUG:
        text += f"\n```{type(exc).__name__}: {clip(exc, 300)}```"
    return text


_URL_RE = re.compile(r"^https?://\S{3,2000}$")
_LINK_RE = re.compile(r"(https?://|www\.)\S+|discord(?:app)?\.com/invite/\S+|discord\.gg/\S+", re.I)
_INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.I)
_CUSTOM_EMOJI_RE = re.compile(r"^<a?:\w{2,32}:\d{15,25}>$")
_TASHKEEL_RE = re.compile("[\u064B-\u0652\u0640\u0670]")
_PLACEHOLDER_RE = re.compile(r"\[(" + "|".join(PLACEHOLDERS) + r")\]")


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def parse_color(text: Optional[str]) -> Optional[int]:
    names = {"red": 0xE74C3C, "احمر": 0xE74C3C, "green": 0x2ECC71, "اخضر": 0x2ECC71, "blue": 0x3498DB, "ازرق": 0x3498DB, "yellow": 0xF1C40F,
             "اصفر": 0xF1C40F, "orange": 0xE67E22, "برتقالي": 0xE67E22, "purple": 0x9B59B6, "بنفسجي": 0x9B59B6, "pink": 0xFF69B4, "وردي": 0xFF69B4,
             "white": 0xFFFFFF, "ابيض": 0xFFFFFF, "gold": 0xFFD700, "ذهبي": 0xFFD700, "gray": 0x95A5A6, "رمادي": 0x95A5A6, "dark": DEFAULT_COLOR, "داكن": DEFAULT_COLOR}
    t = normalize_ar(text or "")
    if not t:
        return DEFAULT_COLOR
    if t in names:
        return names[t]
    t = t.lstrip("#")
    if t.startswith("0x"):
        t = t[2:]
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6:
        return None
    try:
        return int(t, 16)
    except ValueError:
        return None


def normalize_ar(text: str) -> str:
    t = (text or "").strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        t = t.replace(a, b)
    return t


def normalize_msg(text: str, collapse: bool) -> str:
    """تطبيع للمقارنة: حروف صغيرة، من غير تشكيل، همزات موحدة، ومسافات مرتبة، (وتجاهل الحروف المكررة لو collapse)."""
    t = normalize_ar(_TASHKEEL_RE.sub("", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"(.)\1+", r"\1", t) if collapse else t


def match_keyword(text: str, kw: str, mode: str) -> bool:
    """text و kw متطبّعين بنفس الطريقة."""
    if not kw:
        return False
    if mode == "exact":
        return text == kw
    if mode == "starts":
        return text.startswith(kw)
    if mode == "ends":
        return text.endswith(kw)
    if mode == "word":
        return re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text) is not None
    return kw in text


def parse_keywords(text: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[\n,،|؛;]+", text or ""):
        part = part.strip()[:100]
        if part and part.lower() not in (o.lower() for o in out):
            out.append(part)
    return out[:MAX_KEYWORDS]


def parse_emojis(text: str) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for token in re.split(r"[\s,،]+", (text or "").strip()):
        if not token:
            continue
        if _CUSTOM_EMOJI_RE.match(token) or (not token.isascii() and len(token) <= 12):
            if token not in valid:
                valid.append(token)
        else:
            invalid.append(token)
    return valid[:MAX_REACTIONS], invalid


def fill(text: Optional[str], ctx: dict) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: str(ctx.get(m.group(1), "")), text or "")


def make_ctx(user: discord.abc.User, guild: discord.Guild, channel, keyword: str = "") -> dict:
    return {"user": user.mention, "userName": user.name, "displayName": getattr(user, "display_name", user.name), "userId": str(user.id),
            "server": guild.name, "channel": getattr(channel, "mention", "#روم"), "keyword": keyword, "memberCount": str(guild.member_count or 0)}


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def edit_ui(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.edit_original_response(**kwargs)
    return await interaction.response.edit_message(**kwargs)


async def report_error(interaction: discord.Interaction, exc: Optional[BaseException] = None):
    try:
        await respond(interaction, content=error_text(exc) if exc else "❌ حصل خطأ غير متوقع، حاول تاني.", ephemeral=True)
    except discord.HTTPException:
        pass


class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction, error)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction, error)


class OwnedView(SafeView):
    def __init__(self, owner_id: int, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await respond(interaction, content="🔒 اللوحة دي مش بتاعتك، اكتب `/autoreply` وافتح لوحتك.", ephemeral=True)
        return False


# ==============================================================================
# 💬 بناء الرد (نص / إيمبد) والمعاينة
# ==============================================================================
def reply_has_body(r: dict) -> bool:
    if r["type"] == "embed":
        return bool(r.get("title") or (r.get("text") or "").strip() or r.get("image_url") or r.get("thumbnail_url") or r.get("author_name") or r.get("footer_text"))
    if r["type"] == "text":
        return bool((r.get("text") or "").strip() or r.get("image_url"))
    return False


def build_embed(r: dict, ctx: dict) -> Optional[discord.Embed]:
    if r["type"] != "embed" or not reply_has_body(r):
        return None
    desc = fill(r.get("text"), ctx).replace("\\n", "\n").strip()
    embed = discord.Embed(description=desc or None, color=int(r.get("color") or DEFAULT_COLOR))
    if r.get("title"):
        embed.title = clip(fill(r["title"], ctx), 256)
    if r.get("timestamp"):
        embed.timestamp = discord.utils.utcnow()
    if r.get("author_name"):
        embed.set_author(name=clip(fill(r["author_name"], ctx), 256), icon_url=r.get("author_icon_url") or None)
    if r.get("image_url"):
        embed.set_image(url=r["image_url"])
    if r.get("thumbnail_url"):
        embed.set_thumbnail(url=r["thumbnail_url"])
    if r.get("footer_text"):
        embed.set_footer(text=clip(fill(r["footer_text"], ctx), 2048), icon_url=r.get("footer_icon_url") or None)
    return embed


def build_reply(d: dict, ctx: dict) -> tuple[Optional[str], Optional[discord.Embed]]:
    """بيرجّع (النص, الإيمبد) اللي البوت هيبعتهم. (None, None) = مفيش رسالة."""
    r, role_id = d["reply"], d["actions"].get("ping_role_id")
    ping = f"<@&{role_id}>" if role_id else ""
    embed = None
    if r["type"] == "text":
        body = fill(r.get("text"), ctx).replace("\\n", "\n").strip()
        if r.get("image_url"):
            body = f"{body}\n{r['image_url']}".strip()
        content = f"{ping} {body}".strip()
    elif r["type"] == "embed":
        embed = build_embed(r, ctx)
        content = f"{ping} {fill(r.get('outside_text'), ctx)}".strip()
    else:
        content = ping
    return (clip(content, 2000) or None), embed


def rule_problems(d: dict) -> list[str]:
    t, r, a, dl = d["trigger"], d["reply"], d["actions"], d["delivery"]
    problems = []
    if t["mode"] == "keywords" and not t["keywords"]:
        problems.append("حدد كلمة مفتاحية واحدة على الأقل (⚡ الشرط ← الكلمات المفتاحية).")
    if t["mode"] == "every" and not d["channels"]:
        problems.append("قاعدة «كل رسالة» لازم تتحدد لها روم (📢 الرومات) عشان ما تشتغلش في السيرفر كله.")
    if r["type"] != "none" and not reply_has_body(r):
        problems.append("الرد فاضي — اكتب نص أو حط صورة (💬 الرد ← المحتوى)، أو غيّر النوع لـ «بدون رسالة».")
    if not (r["type"] != "none" or a["reactions"] or a["thread"] or dl["delete_trigger"] or a["ping_role_id"]):
        problems.append("القاعدة ملهاش أي إجراء (رد / إيموجي / ثريد / حذف / منشن).")
    return problems


# ==============================================================================
# 🏗️ جلسة التحرير (مسودة أو قاعدة محفوظة بتعديل مباشر)
# ==============================================================================
class Session:
    def __init__(self, cog: "AutoReplyCog", guild: discord.Guild, user: discord.Member, data: dict, record: Optional[dict] = None):
        self.cog, self.guild, self.user, self.data, self.record = cog, guild, user, data, record

    @property
    def live(self) -> bool:
        return self.record is not None

    def summary(self, d: dict) -> list[str]:
        t, r, dl, a, f = d["trigger"], d["reply"], d["delivery"], d["actions"], d["filters"]
        channels = " ".join(f"<#{c}>" for c in d["channels"][:8]) + (" …" if len(d["channels"]) > 8 else "") or "🌐 كل رومات السيرفر"
        trig = MODE_LABEL[t["mode"]]
        if t["mode"] == "keywords":
            kws = "، ".join(f"`{clip(k, 20)}`" for k in t["keywords"][:6]) + (" …" if len(t["keywords"]) > 6 else "") or "_(لسه ما اتحددتش)_"
            trig += f" ({MATCH_LABEL[t['match']]}): {kws}"
        lines = [f"⚡ **الشرط:** {trig}", f"📢 **الرومات:** {channels}"]
        lines.append(f"💬 **الرد:** {TYPE_LABEL[r['type']]} ┊ 🚚 {DELIVERY_LABEL[dl['mode']]}" if r["type"] != "none" else "💬 **الرد:** بدون رسالة")
        clean = []
        if dl["delete_trigger"]:
            clean.append("حذف رسالة العضو " + ("فوراً" if dl["delete_trigger_after"] <= 0 else f"بعد {dl['delete_trigger_after']}ث"))
        if dl["delete_reply_after"] > 0 and r["type"] != "none":
            clean.append(f"حذف الرد بعد {dl['delete_reply_after']}ث")
        if clean:
            lines.append("🗑️ **الحذف:** " + " • ".join(clean))
        extras = []
        if a["reactions"]:
            extras.append("إيموجي " + " ".join(a["reactions"][:8]))
        if a["thread"]:
            extras.append("ثريد تلقائي")
        if a["ping_role_id"]:
            extras.append(f"منشن <@&{a['ping_role_id']}>")
        if extras:
            lines.append("🎭 **إجراءات:** " + " • ".join(extras))
        flt = []
        if f["allow_bots"]:
            flt.append("بيتفاعل مع البوتات")
        if f["exempt_staff"]:
            flt.append("استثناء المشرفين")
        if f["exempt_roles"]:
            flt.append(f"{len(f['exempt_roles'])} رتب مستثناة")
        if f["cooldown"]:
            flt.append(f"كولداون {f['cooldown']}ث")
        if flt:
            lines.append("🛡️ **فلاتر:** " + " • ".join(flt))
        return lines

    def embeds(self, note: Optional[str] = None, page_title: str = "") -> list[discord.Embed]:
        d = self.data
        name = d.get("name") or "_(بدون اسم)_"
        if self.live:
            state = "🟢 شغالة" if d["enabled"] else "🔴 متوقفة"
            head = f"📍 **قاعدة محفوظة** `#{self.record['_id']}` — **{name}** ({state})\n⚡ **أي تعديل بيتطبق فوراً** — مفيش زرار تطبيق."
            err = self.cog.errors.get(self.record["_id"])
            if err:
                head += f"\n⚠️ آخر خطأ في التنفيذ: `{clip(err, 150)}`"
        else:
            head = f"🆕 **مسودة جديدة** — **{name}**\nجهّز القاعدة واضغط 💾 حفظ عشان تشتغل."
        if page_title:
            head = f"### {page_title}\n" + head
        lines = [head, ""] + self.summary(d)
        for p in rule_problems(d):
            lines.append(f"⚠️ _{p}_")
        if note:
            lines += ["", note]
        banner = discord.Embed(description=clip("\n".join(lines), 4000), color=COLOR_BLUE)
        result = [banner]
        ctx = make_ctx(self.user, self.guild, self.guild.get_channel(d["channels"][0]) if d["channels"] else None, "كلمة")
        content, embed = build_reply(d, ctx)
        if embed is not None:
            result.append(embed)
        elif content:
            result.append(discord.Embed(title="👁️ معاينة الرد (رسالة نصية)", description=content, color=DEFAULT_COLOR))
        return result

    def check(self, data: dict) -> Optional[str]:
        if data["trigger"]["mode"] == "every" and not data["channels"]:
            return "قاعدة «كل رسالة» لازم تتحدد لها روم. غيّر الشرط الأول أو حدد روم."
        embed = build_embed(data["reply"], make_ctx(self.user, self.guild, None, "كلمة"))
        if embed is not None and len(embed) > 6000:
            return "الإيمبد عدّى الحد الأقصى (6000 حرف). قلّل النص."
        return None

    async def show(self, interaction: discord.Interaction, note: Optional[str] = None, page: str = "main"):
        view, title = make_view(self, page)
        await edit_ui(interaction, content=None, embeds=self.embeds(note, title), view=view)

    async def apply(self, interaction: discord.Interaction, mutate: Callable[[dict], None], page: str = "main"):
        """بيطبق التعديل: لو القاعدة محفوظة بيتحفظ ويتطبق فوراً، ولو مسودة بيحدّث المعاينة بس."""
        new = copy.deepcopy(self.data)
        mutate(new)
        problem = self.check(new)
        if problem:
            await respond(interaction, embed=err_embed(problem), ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        note = None
        if self.live:
            ok, note = await self.cog.persist_live(self, new, interaction.user)
            if not ok:
                await interaction.followup.send(embed=err_embed(note), ephemeral=True)
                await self.show(interaction, page=page)
                return
        self.data = new
        await self.show(interaction, note, page)


# ==============================================================================
# ✏️ المودالات
# ==============================================================================
class TextFieldModal(SafeModal):
    """مودال عام لحقل نصي واحد."""

    def __init__(self, s: Session, page: str, title: str, label: str, path: tuple, max_length: int = 100, required: bool = True, paragraph: bool = False):
        super().__init__(title=title)
        self.s, self.page, self.path, self.required = s, page, path, required
        cur = get_path(s.data, path)
        self.box = discord.ui.TextInput(label=label[:45], default=clip(cur, max_length) if cur else None, required=required, max_length=max_length,
                                        style=discord.TextStyle.paragraph if paragraph else discord.TextStyle.short)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.box.value.strip()
        await self.s.apply(interaction, lambda d: set_path(d, self.path, value or None), self.page)


class NumberModal(SafeModal):
    def __init__(self, s: Session, page: str, title: str, label: str, path: tuple, lo: int, hi: int):
        super().__init__(title=title)
        self.s, self.page, self.path, self.lo, self.hi = s, page, path, lo, hi
        self.box = discord.ui.TextInput(label=label[:45], default=str(get_path(s.data, path)), required=True, max_length=6, placeholder=f"من {lo} لـ {hi}")
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.box.value.strip())
            if not self.lo <= value <= self.hi:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed(f"اكتب رقم صحيح من {self.lo} لـ {self.hi}."), ephemeral=True)
            return
        await self.s.apply(interaction, lambda d: set_path(d, self.path, value), self.page)


class KeywordsModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="🔑 الكلمات المفتاحية")
        self.s = s
        cur = "\n".join(s.data["trigger"]["keywords"])
        self.box = discord.ui.TextInput(label="كلمة في كل سطر (أو افصل بفاصلة)", style=discord.TextStyle.paragraph, default=clip(cur, 4000) or None,
                                        required=True, max_length=4000, placeholder="مرحبا\nاهلا\nسلام عليكم")
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        words = parse_keywords(self.box.value)
        if not words:
            await respond(interaction, embed=err_embed("اكتب كلمة واحدة على الأقل."), ephemeral=True)
            return
        await self.s.apply(interaction, lambda d: d["trigger"].update(keywords=words), "trigger")


class TextReplyModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="📝 محتوى الرد (نص)")
        self.s, r = s, s.data["reply"]
        self.text_in = discord.ui.TextInput(label="نص الرسالة (اتركه فاضي لو هتحط صورة بس)", style=discord.TextStyle.paragraph, default=clip(r.get("text"), 2000) or None, required=False, max_length=2000,
                                            placeholder="المتغيرات: [user] [userName] [server] [channel] [keyword]")
        self.img_in = discord.ui.TextInput(label="رابط صورة (اختياري)", default=r.get("image_url") or None, required=False, max_length=500)
        self.add_item(self.text_in)
        self.add_item(self.img_in)

    async def on_submit(self, interaction: discord.Interaction):
        img = self.img_in.value.strip()
        if img and not clean_url(img):
            await respond(interaction, embed=err_embed("رابط الصورة لازم يبدأ بـ http أو https."), ephemeral=True)
            return
        text = self.text_in.value.strip()
        await self.s.apply(interaction, lambda d: d["reply"].update(text=text, image_url=img or None), "reply")


class EmbedReplyModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="📝 محتوى الرد (إيمبد)")
        self.s, r = s, s.data["reply"]
        self.title_in = discord.ui.TextInput(label="العنوان (اختياري — سيبه فاضي)", default=clip(r.get("title"), 256) if r.get("title") else None, required=False, max_length=256)
        self.text_in = discord.ui.TextInput(label="الوصف / النص", style=discord.TextStyle.paragraph, default=clip(r.get("text"), 4000) or None, required=False, max_length=4000,
                                            placeholder="المتغيرات: [user] [userName] [server] [channel] [keyword]")
        self.footer_in = discord.ui.TextInput(label="نص الفوتر (اختياري)", default=clip(r.get("footer_text"), 2048) if r.get("footer_text") else None, required=False, max_length=2048)
        self.author_in = discord.ui.TextInput(label="اسم الأوثر (اختياري)", default=clip(r.get("author_name"), 256) if r.get("author_name") else None, required=False, max_length=256)
        self.outside_in = discord.ui.TextInput(label="نص خارج الإيمبد (اختياري)", default=clip(r.get("outside_text"), 1000) if r.get("outside_text") else None, required=False, max_length=1000)
        for box in (self.title_in, self.text_in, self.footer_in, self.author_in, self.outside_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        vals = {"title": self.title_in.value.strip() or None, "text": self.text_in.value.strip(), "footer_text": self.footer_in.value.strip() or None,
                "author_name": self.author_in.value.strip() or None, "outside_text": self.outside_in.value.strip() or None}
        await self.s.apply(interaction, lambda d: d["reply"].update(vals), "reply")


class StyleModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="🎨 الألوان والصور")
        self.s, r = s, s.data["reply"]
        self.color_in = discord.ui.TextInput(label="اللون (Hex أو اسم: #2b2d31 / red / أحمر)", default=f"#{int(r.get('color') or DEFAULT_COLOR):06x}", required=False, max_length=20)
        self.image_in = discord.ui.TextInput(label="رابط الصورة الكبيرة (اختياري)", default=r.get("image_url") or None, required=False, max_length=500)
        self.thumb_in = discord.ui.TextInput(label="رابط الصورة المصغرة (اختياري)", default=r.get("thumbnail_url") or None, required=False, max_length=500)
        self.aicon_in = discord.ui.TextInput(label="صورة الأوثر (محتاج اسم أوثر)", default=r.get("author_icon_url") or None, required=False, max_length=500)
        self.ficon_in = discord.ui.TextInput(label="صورة الفوتر (محتاج نص فوتر)", default=r.get("footer_icon_url") or None, required=False, max_length=500)
        for box in (self.color_in, self.image_in, self.thumb_in, self.aicon_in, self.ficon_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        color = parse_color(self.color_in.value)
        if color is None:
            await respond(interaction, embed=err_embed("اللون غير صالح. اكتب Hex مثل `#2b2d31` أو اسم مثل `red` / `أحمر`."), ephemeral=True)
            return
        urls = {}
        for key, box, label in (("image_url", self.image_in, "الصورة الكبيرة"), ("thumbnail_url", self.thumb_in, "الصورة المصغرة"),
                                ("author_icon_url", self.aicon_in, "صورة الأوثر"), ("footer_icon_url", self.ficon_in, "صورة الفوتر")):
            raw = box.value.strip()
            if raw and not clean_url(raw):
                await respond(interaction, embed=err_embed(f"رابط {label} لازم يبدأ بـ http أو https."), ephemeral=True)
                return
            urls[key] = raw or None
        await self.s.apply(interaction, lambda d: d["reply"].update(color=color, **urls), "reply")


class ReactionsModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="😀 الإيموجيات التلقائية")
        self.s = s
        self.box = discord.ui.TextInput(label="الإيموجيات مفصولة بمسافة (فاضي = بدون)", default=" ".join(s.data["actions"]["reactions"]) or None,
                                        required=False, max_length=400, placeholder="👍 ❤️ ⬆️ ⬇️ أو إيموجي سيرفر <:name:id>")
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        valid, invalid = parse_emojis(self.box.value)
        if invalid:
            await respond(interaction, embed=err_embed("إيموجيات غير صالحة: " + " ".join(f"`{clip(i, 20)}`" for i in invalid[:5]) + "\nافصل بينهم بمسافة، واستخدم إيموجي عادي أو إيموجي سيرفر بصيغة `<:name:id>`."), ephemeral=True)
            return
        await self.s.apply(interaction, lambda d: d["actions"].update(reactions=valid), "actions")


# ==============================================================================
# 🧭 الواجهات الفرعية
# ==============================================================================
class PickView(OwnedView):
    def __init__(self, owner_id: int, options: list[discord.SelectOption], on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
                 back: Callable[[discord.Interaction], Awaitable[None]], placeholder: str):
        super().__init__(owner_id, 300)
        select = discord.ui.Select(placeholder=placeholder, options=options[:25], row=0)

        async def pick_cb(i: discord.Interaction):
            await on_pick(i, select.values[0])

        async def back_cb(i: discord.Interaction):
            await back(i)

        select.callback = pick_cb
        self.add_item(select)
        btn = discord.ui.Button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        btn.callback = back_cb
        self.add_item(btn)


class BackMixin:
    """زرار رجوع للصفحة الرئيسية مشترك."""
    s: Session

    async def _back(self, interaction: discord.Interaction):
        await self.s.show(interaction)


class TriggerView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        t = s.data["trigger"]
        mode = discord.ui.Select(placeholder="⚡ الشرط: امتى القاعدة تشتغل؟", row=0, options=[
            discord.SelectOption(label=MODE_LABEL[k], description=MODE_DESC[k], value=k, default=(t["mode"] == k)) for k in MODE_LABEL])
        match = discord.ui.Select(placeholder="🔤 طريقة مطابقة الكلمات (للكلمات المفتاحية)", row=1, options=[
            discord.SelectOption(label=MATCH_LABEL[k], description=MATCH_DESC[k], value=k, default=(t["match"] == k)) for k in MATCH_LABEL])

        async def mode_cb(i: discord.Interaction):
            await s.apply(i, lambda d: d["trigger"].update(mode=mode.values[0]), "trigger")

        async def match_cb(i: discord.Interaction):
            await s.apply(i, lambda d: d["trigger"].update(match=match.values[0]), "trigger")

        mode.callback, match.callback = mode_cb, match_cb
        self.add_item(mode)
        self.add_item(match)
        self.collapse_btn.style = discord.ButtonStyle.success if t["collapse"] else discord.ButtonStyle.secondary
        self.collapse_btn.label = "تجاهل الحروف المكررة: شغال" if t["collapse"] else "تجاهل الحروف المكررة: متوقف"

    @discord.ui.button(label="الكلمات المفتاحية", emoji="🔑", style=discord.ButtonStyle.primary, row=2)
    async def keywords_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(KeywordsModal(self.s))

    @discord.ui.button(label="تجاهل الحروف المكررة", emoji="🔠", style=discord.ButtonStyle.secondary, row=2)
    async def collapse_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["trigger"].update(collapse=not d["trigger"]["collapse"]), "trigger")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class ChannelPickView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📢 اختر الرومات (ممكن أكتر من روم)", channel_types=[discord.ChannelType.text, discord.ChannelType.news],
                       min_values=1, max_values=MAX_CHANNELS, row=0)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        ids = [c.id for c in select.values]
        await self.s.apply(interaction, lambda d: d.update(channels=ids), "main")

    @discord.ui.button(label="كل رومات السيرفر", emoji="🌐", style=discord.ButtonStyle.secondary, row=1)
    async def all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d.update(channels=[]), "main")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class ReplyView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        r = s.data["reply"]
        self.type_btn.label = f"النوع: {TYPE_LABEL[r['type']]}"
        self.content_btn.disabled = r["type"] == "none"
        self.style_btn.disabled = r["type"] != "embed"

    @discord.ui.button(label="النوع", emoji="🔄", style=discord.ButtonStyle.primary, row=0)
    async def type_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = ["text", "embed", "none"]
        await self.s.apply(interaction, lambda d: d["reply"].update(type=order[(order.index(d["reply"]["type"]) + 1) % 3]), "reply")

    @discord.ui.button(label="المحتوى", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def content_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedReplyModal(self.s) if self.s.data["reply"]["type"] == "embed" else TextReplyModal(self.s))

    @discord.ui.button(label="الألوان والصور", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def style_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StyleModal(self.s))

    @discord.ui.button(label="التوقيت", emoji="🕒", style=discord.ButtonStyle.secondary, row=1)
    async def ts_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["reply"].update(timestamp=not d["reply"]["timestamp"]), "reply")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class DeliveryView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        dl = s.data["delivery"]
        mode = discord.ui.Select(placeholder="🚚 الرد هيتبعت إزاي؟", row=0, options=[
            discord.SelectOption(label=DELIVERY_LABEL[k], value=k, default=(dl["mode"] == k)) for k in DELIVERY_LABEL])

        async def mode_cb(i: discord.Interaction):
            await s.apply(i, lambda d: d["delivery"].update(mode=mode.values[0]), "delivery")

        mode.callback = mode_cb
        self.add_item(mode)
        self.del_btn.style = discord.ButtonStyle.success if dl["delete_trigger"] else discord.ButtonStyle.secondary
        self.del_btn.label = "حذف رسالة العضو: شغال" if dl["delete_trigger"] else "حذف رسالة العضو: متوقف"
        self.mention_btn.style = discord.ButtonStyle.success if dl["mention_author"] else discord.ButtonStyle.secondary
        self.mention_btn.disabled = dl["mode"] != "reply"
        self.del_after_btn.label = f"تأخير حذف رسالة العضو: {dl['delete_trigger_after']}ث"
        self.reply_after_btn.label = f"حذف الرد بعد: {dl['delete_reply_after']}ث"

    @discord.ui.button(label="حذف رسالة العضو", emoji="🗑️", style=discord.ButtonStyle.secondary, row=1)
    async def del_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["delivery"].update(delete_trigger=not d["delivery"]["delete_trigger"]), "delivery")

    @discord.ui.button(label="تأخير الحذف", emoji="⏱️", style=discord.ButtonStyle.secondary, row=1)
    async def del_after_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NumberModal(self.s, "delivery", "⏱️ تأخير حذف رسالة العضو", "بعد كام ثانية؟ (0 = فوراً)", ("delivery", "delete_trigger_after"), 0, MAX_DELETE_DELAY))

    @discord.ui.button(label="حذف الرد بعد", emoji="⏳", style=discord.ButtonStyle.secondary, row=1)
    async def reply_after_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NumberModal(self.s, "delivery", "⏳ حذف رد البوت تلقائياً", "بعد كام ثانية؟ (0 = مايتحذفش)", ("delivery", "delete_reply_after"), 0, MAX_DELETE_DELAY))

    @discord.ui.button(label="منشن صاحب الرسالة", emoji="🔔", style=discord.ButtonStyle.secondary, row=2)
    async def mention_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["delivery"].update(mention_author=not d["delivery"]["mention_author"]), "delivery")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class ActionsView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        self.thread_btn.style = discord.ButtonStyle.success if s.data["actions"]["thread"] else discord.ButtonStyle.secondary
        self.thread_btn.label = "ثريد تلقائي: شغال" if s.data["actions"]["thread"] else "ثريد تلقائي: متوقف"

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🔔 منشن رتبة مع الرد (امسح الاختيار للإلغاء)", min_values=0, max_values=1, row=0)
    async def ping_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0] if select.values else None
        if role is not None and role.is_default():
            await respond(interaction, embed=err_embed("مينفعش @everyone هنا. اختار رتبة عادية."), ephemeral=True)
            return
        await self.s.apply(interaction, lambda d: d["actions"].update(ping_role_id=role.id if role else None), "actions")

    @discord.ui.button(label="الإيموجيات", emoji="😀", style=discord.ButtonStyle.primary, row=1)
    async def reactions_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReactionsModal(self.s))

    @discord.ui.button(label="ثريد تلقائي", emoji="🧵", style=discord.ButtonStyle.secondary, row=1)
    async def thread_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["actions"].update(thread=not d["actions"]["thread"]), "actions")

    @discord.ui.button(label="اسم الثريد", emoji="✏️", style=discord.ButtonStyle.secondary, row=1)
    async def thread_name_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextFieldModal(self.s, "actions", "✏️ اسم الثريد", "اسم الثريد ([userName] [displayName])", ("actions", "thread_name"), 100, required=True))

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class FiltersView(OwnedView, BackMixin):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        f = s.data["filters"]
        self.bots_btn.style = discord.ButtonStyle.success if f["allow_bots"] else discord.ButtonStyle.secondary
        self.staff_btn.style = discord.ButtonStyle.success if f["exempt_staff"] else discord.ButtonStyle.secondary
        self.cool_btn.label = f"كولداون لكل عضو: {f['cooldown']}ث"

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🛡️ رتب مستثناة من القاعدة (امسح الاختيار للإزالة)", min_values=0, max_values=10, row=0)
    async def exempt_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        ids = [r.id for r in select.values if not r.is_default()]
        await self.s.apply(interaction, lambda d: d["filters"].update(exempt_roles=ids), "filters")

    @discord.ui.button(label="التفاعل مع البوتات", emoji="🤖", style=discord.ButtonStyle.secondary, row=1)
    async def bots_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["filters"].update(allow_bots=not d["filters"]["allow_bots"]), "filters")

    @discord.ui.button(label="استثناء المشرفين", emoji="👮", style=discord.ButtonStyle.secondary, row=1)
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d["filters"].update(exempt_staff=not d["filters"]["exempt_staff"]), "filters")

    @discord.ui.button(label="كولداون", emoji="⏱️", style=discord.ButtonStyle.secondary, row=1)
    async def cool_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NumberModal(self.s, "filters", "⏱️ كولداون لكل عضو", "كام ثانية بين كل تفعيل؟ (0 = بدون)", ("filters", "cooldown"), 0, 86400))

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._back(interaction)


class DeleteConfirmView(OwnedView):
    def __init__(self, cog: "AutoReplyCog", rec: dict, owner_id: int, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(owner_id, 60)
        self.cog, self.rec, self.back = cog, rec, back

    @discord.ui.button(label="أيوه، احذف القاعدة", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.delete_rule(self.rec)
        await self.back(interaction)
        await interaction.followup.send(embed=ok_embed("🗑️ تم الحذف", f"اتحذفت القاعدة **{self.rec['data'].get('name', '')}**."), ephemeral=True)

    @discord.ui.button(label="إلغاء", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.back(interaction)


# ==============================================================================
# 🏗️ اللوحة الرئيسية للبناء
# ==============================================================================
class BuilderView(OwnedView):
    def __init__(self, s: Session):
        super().__init__(s.user.id)
        self.s = s
        d = s.data
        self.toggle_btn.style = discord.ButtonStyle.success if d["enabled"] else discord.ButtonStyle.danger
        self.toggle_btn.label = "شغالة" if d["enabled"] else "متوقفة"
        if s.live:
            self.remove_item(self.save_btn)
        else:
            self.remove_item(self.copy_btn)
            self.remove_item(self.delete_btn)

    async def _go(self, interaction: discord.Interaction, page: str):
        await self.s.show(interaction, page=page)

    @discord.ui.button(label="الشرط", emoji="⚡", style=discord.ButtonStyle.primary, row=0)
    async def trigger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "trigger")

    @discord.ui.button(label="الرومات", emoji="📢", style=discord.ButtonStyle.primary, row=0)
    async def channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "channels")

    @discord.ui.button(label="الرد", emoji="💬", style=discord.ButtonStyle.primary, row=0)
    async def reply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "reply")

    @discord.ui.button(label="التسليم والحذف", emoji="🚚", style=discord.ButtonStyle.primary, row=0)
    async def delivery_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "delivery")

    @discord.ui.button(label="إجراءات إضافية", emoji="🎭", style=discord.ButtonStyle.primary, row=0)
    async def actions_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "actions")

    @discord.ui.button(label="الاستثناءات", emoji="🛡️", style=discord.ButtonStyle.secondary, row=1)
    async def filters_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "filters")

    @discord.ui.button(label="الاسم", emoji="🏷️", style=discord.ButtonStyle.secondary, row=1)
    async def name_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextFieldModal(self.s, "main", "🏷️ اسم القاعدة", "اسم القاعدة (فريد في السيرفر)", ("name",), 60, required=True))

    @discord.ui.button(label="تجربة الرد", emoji="🧪", style=discord.ButtonStyle.secondary, row=1)
    async def test_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ctx = make_ctx(interaction.user, interaction.guild, interaction.channel, "كلمة")
        content, embed = build_reply(self.s.data, ctx)
        if not content and not embed:
            await interaction.followup.send(embed=err_embed("القاعدة دي مش هتبعت أي رسالة (الرد فاضي أو «بدون رسالة»)."), ephemeral=True)
            return
        info = f"🧪 **دي الرسالة اللي هيبعتها البوت** ({DELIVERY_LABEL[self.s.data['delivery']['mode']]}):"
        try:
            await interaction.followup.send(content=clip(f"{info}\n{content or ''}", 2000), embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            await interaction.followup.send(embed=err_embed(f"ديسكورد رفض الرسالة (غالباً رابط صورة غير صالح):\n`{clip(e, 200)}`"), ephemeral=True)

    @discord.ui.button(label="شغالة", emoji="⏯️", style=discord.ButtonStyle.success, row=1)
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d.update(enabled=not d["enabled"]))

    @discord.ui.button(label="حفظ وتفعيل", emoji="💾", style=discord.ButtonStyle.success, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.cog.save_draft(interaction, self.s)

    @discord.ui.button(label="نسخ كقاعدة جديدة", emoji="📄", style=discord.ButtonStyle.primary, row=2)
    async def copy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = copy.deepcopy(self.s.data)
        data["name"] = clip(f"{data.get('name') or 'قاعدة'} (نسخة)", 60)
        await Session(self.s.cog, self.s.guild, interaction.user, data).show(interaction, "📄 دي نسخة (مسودة) — غيّر اسمها واضغط 💾 حفظ.")

    @discord.ui.button(label="حذف", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rec = self.s.record
        embed = discord.Embed(title="⚠️ تأكيد الحذف", description=f"هتحذف القاعدة **{self.s.data.get('name')}** `#{rec['_id']}` نهائياً. متأكد؟", color=COLOR_RED)
        await interaction.response.edit_message(embeds=[embed], view=DeleteConfirmView(self.s.cog, rec, self.s.user.id, lambda i: go_dashboard(i, self.s.cog)))

    @discord.ui.button(label="القائمة", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await go_dashboard(interaction, self.s.cog)


def make_view(s: Session, page: str) -> tuple[discord.ui.View, str]:
    return {
        "trigger": (lambda: TriggerView(s), "⚡ الشرط"),
        "channels": (lambda: ChannelPickView(s), "📢 الرومات"),
        "reply": (lambda: ReplyView(s), "💬 الرد"),
        "delivery": (lambda: DeliveryView(s), "🚚 التسليم والحذف"),
        "actions": (lambda: ActionsView(s), "🎭 إجراءات إضافية"),
        "filters": (lambda: FiltersView(s), "🛡️ الاستثناءات والفلاتر"),
    }.get(page, (lambda: BuilderView(s), ""))[0](), {
        "trigger": "⚡ الشرط", "channels": "📢 الرومات", "reply": "💬 الرد", "delivery": "🚚 التسليم والحذف",
        "actions": "🎭 إجراءات إضافية", "filters": "🛡️ الاستثناءات والفلاتر"}.get(page, "")


# ==============================================================================
# 🏠 القائمة الرئيسية والقوائم
# ==============================================================================
def dashboard_embed(user: discord.Member, total: Optional[int]) -> discord.Embed:
    count = f"`{total}`" if total is not None else "`؟` _(الداتابيز مش متاحة دلوقتي)_"
    desc = (
        f"أهلاً بيك يا {user.mention} في **مركز الرد التلقائي** ⚡\n\n"
        "➕ **إضافة قاعدة** — ابدأ من قالب جاهز (رد، إيموجي، ثريد، حماية روابط...) أو من الصفر.\n"
        "✏️ **تعديل قاعدة** — التعديلات بتتطبق **فوراً** من غير زرار تطبيق.\n"
        "🗑️ **حذف قاعدة** — بيحذف القاعدة نهائياً.\n"
        "📋 **القواعد** — كل قواعد السيرفر وحالتها وعدد مرات تشغيلها.\n\n"
        f"📦 قواعد السيرفر: {count}"
    )
    return discord.Embed(title="⚡ مركز الرد التلقائي", description=desc, color=DEFAULT_COLOR)


async def go_dashboard(interaction: discord.Interaction, cog: "AutoReplyCog"):
    if not interaction.response.is_done():
        await interaction.response.defer()
    try:
        total = await run_db(count_rules_sync, interaction.guild.id)
    except Exception:
        log.warning("تعذر عدّ القواعد", exc_info=True)
        total = None
    await interaction.edit_original_response(content=None, embeds=[dashboard_embed(interaction.user, total)], view=DashboardView(cog, interaction.user))


class DashboardView(OwnedView):
    def __init__(self, cog: "AutoReplyCog", user: discord.Member):
        super().__init__(user.id, 600)
        select = discord.ui.Select(placeholder="اختر ما تريد من القائمة...", options=[
            discord.SelectOption(label="إضافة قاعدة جديدة", description="من قالب جاهز أو من الصفر", emoji="➕", value="add"),
            discord.SelectOption(label="تعديل قاعدة", description="تعديل مباشر بتطبيق فوري", emoji="✏️", value="edit"),
            discord.SelectOption(label="حذف قاعدة", description="حذف قاعدة نهائياً", emoji="🗑️", value="delete"),
            discord.SelectOption(label="القواعد", description="عرض كل القواعد وحالتها", emoji="📋", value="list"),
        ])

        async def cb(i: discord.Interaction):
            await cog.handle_dashboard(i, select.values[0])

        select.callback = cb
        self.add_item(select)


class ListView(OwnedView):
    def __init__(self, cog: "AutoReplyCog", user: discord.Member, page: int, pages: int):
        super().__init__(user.id, 300)

        async def prev_cb(i): await cog.render_list(i, page - 1)
        async def next_cb(i): await cog.render_list(i, page + 1)
        async def back_cb(i): await go_dashboard(i, cog)

        for label, emoji, cb, disabled in (("", "⬅️", prev_cb, page <= 0), ("", "➡️", next_cb, page + 1 >= pages), ("القائمة", "↩️", back_cb, False)):
            btn = discord.ui.Button(label=label or None, emoji=emoji, style=discord.ButtonStyle.primary if not label else discord.ButtonStyle.secondary, disabled=disabled)
            btn.callback = cb
            self.add_item(btn)


# ==============================================================================
# 🧠 القاعدة المترجمة (للتشغيل السريع من الكاش)
# ==============================================================================
class Compiled:
    __slots__ = ("id", "name", "data", "channels", "mode", "match", "collapse", "keywords", "enabled", "exempt_roles")

    def __init__(self, rec: dict):
        d = sanitize(rec.get("data"))
        self.id, self.name, self.data = rec["_id"], d.get("name") or rec["_id"], d
        self.channels = set(int(c) for c in d["channels"])
        t = d["trigger"]
        self.mode, self.match, self.collapse = t["mode"], t["match"], bool(t["collapse"])
        self.keywords = [k for k in (normalize_msg(k, self.collapse) for k in t["keywords"]) if k]
        self.enabled = bool(d["enabled"])
        self.exempt_roles = set(int(r) for r in d["filters"]["exempt_roles"])


# ==============================================================================
# 🌟 الـ Cog الرئيسي
# ==============================================================================
class AutoReplyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: dict[int, dict] = {}
        self.loaded = False
        self.cooldowns: dict[tuple[str, int], float] = {}
        self.hit_buffer: dict[str, int] = {}
        self.errors: dict[str, str] = {}

    async def cog_load(self):
        try:
            await run_db(ensure_indexes_sync)
            migrated = await asyncio.wait_for(asyncio.to_thread(migrate_legacy_sync), 120)
            if migrated:
                log.info("تم ترحيل %d قاعدة رد تلقائي من الملف القديم", migrated)
        except Exception:
            log.warning("فشل التهيئة الأولية (الـ indexes/الترحيل)", exc_info=True)
        self.maintenance.start()

    async def cog_unload(self):
        self.maintenance.cancel()
        await self.flush_hits()

    # ---------- الكاش ----------
    @staticmethod
    def _build_entry(records: list) -> dict:
        entry: dict[str, Any] = {"by_channel": {}, "global": []}
        for rec in records:
            try:
                rule = Compiled(rec)
            except Exception:
                log.warning("قاعدة تالفة %s اتجاهلت", rec.get("_id"), exc_info=True)
                continue
            if rule.channels:
                for cid in rule.channels:
                    entry["by_channel"].setdefault(cid, []).append(rule)
            else:
                entry["global"].append(rule)
        return entry

    async def load_all(self):
        grouped: dict[int, list] = {}
        for rec in await run_db(load_all_sync):
            grouped.setdefault(rec["guild_id"], []).append(rec)
        for recs in grouped.values():
            recs.sort(key=lambda r: r.get("created_at", 0))
        self.cache = {gid: self._build_entry(recs) for gid, recs in grouped.items()}
        self.loaded = True

    async def reload_guild(self, gid: int):
        recs = await run_db(list_rules_sync, gid)
        if recs:
            self.cache[gid] = self._build_entry(recs)
        else:
            self.cache.pop(gid, None)

    @tasks.loop(seconds=30)
    async def maintenance(self):
        try:
            if not self.loaded:
                await self.load_all()
            await self.flush_hits()
            cutoff = time.monotonic() - 3600
            for key in [k for k, v in self.cooldowns.items() if v < cutoff]:
                self.cooldowns.pop(key, None)
        except Exception:
            log.exception("خطأ في المهمة الدورية للرد التلقائي")

    @maintenance.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()
        if not self.bot.intents.message_content:
            log.warning("Intent الـ message_content مقفول: الكلمات المفتاحية والروابط مش هتشتغل.")

    async def flush_hits(self):
        if not self.hit_buffer:
            return
        hits, self.hit_buffer = self.hit_buffer, {}
        try:
            await run_db(flush_hits_sync, hits, int(time.time()))
        except Exception:
            for rid, n in hits.items():
                self.hit_buffer[rid] = self.hit_buffer.get(rid, 0) + n

    # ---------- حفظ القواعد ----------
    @staticmethod
    def name_key(name: str) -> str:
        return (name or "").strip().lower()

    async def save_draft(self, interaction: discord.Interaction, s: Session):
        problems = rule_problems(s.data)
        try:
            if await run_db(count_rules_sync, s.guild.id) >= MAX_RULES_PER_GUILD:
                problems.append(f"وصلت للحد الأقصى ({MAX_RULES_PER_GUILD} قاعدة). احذف قواعد قديمة.")
        except Exception:
            log.warning("تعذر فحص عدد القواعد", exc_info=True)
        if problems:
            await respond(interaction, embed=err_embed("\n".join(f"• {p}" for p in problems), "⚠️ كمّل الإعداد الأول"), ephemeral=True)
            return
        await interaction.response.defer()
        now = int(time.time())
        rec = None
        for _ in range(6):
            rid = str(random.randint(100000, 999999))
            data = copy.deepcopy(s.data)
            if not data.get("name"):
                data["name"] = f"قاعدة-{rid}"
            doc = {"_id": rid, "guild_id": s.guild.id, "name_key": self.name_key(data["name"]), "created_by": interaction.user.id,
                   "created_at": now, "updated_at": now, "hits": 0, "last_hit": None, "data": data}
            try:
                await run_db(insert_rule_sync, doc)
                rec = doc
                break
            except DuplicateKeyError as e:
                if "name_key" in str(e):
                    await interaction.followup.send(embed=err_embed(f"الاسم **{data['name']}** مستخدم في قاعدة تانية. غيّره من زرار 🏷️ الاسم."), ephemeral=True)
                    return
                continue
            except Exception as e:
                log.exception("فشل حفظ القاعدة")
                await interaction.followup.send(content=error_text(e), ephemeral=True)
                return
        if rec is None:
            await interaction.followup.send(embed=err_embed("معرفتش أنشئ رقم للقاعدة، حاول تاني."), ephemeral=True)
            return
        s.record, s.data = rec, rec["data"]
        await self.reload_guild(s.guild.id)
        await s.show(interaction, f"✅ اتحفظت القاعدة `#{rec['_id']}` وبقت شغالة. من دلوقتي **أي تعديل بيتطبق فوراً**.")

    async def persist_live(self, s: Session, new_data: dict, editor: discord.Member) -> tuple[bool, str]:
        rec = s.record
        if not new_data.get("name"):
            return False, "اسم القاعدة مينفعش يكون فاضي."
        sets = {"data": new_data, "name_key": self.name_key(new_data["name"]), "updated_at": int(time.time()), "updated_by": editor.id}
        try:
            await run_db(update_rule_sync, rec["_id"], sets)
        except DuplicateKeyError:
            return False, f"الاسم **{new_data['name']}** مستخدم في قاعدة تانية."
        except Exception as e:
            log.exception("فشل حفظ تعديل القاعدة")
            return False, f"الداتابيز مردتش: {clip(e, 150)}"
        rec["data"] = new_data
        try:
            await self.reload_guild(s.guild.id)
        except Exception:
            log.warning("تعذر تحديث الكاش", exc_info=True)
        self.errors.pop(rec["_id"], None)
        return True, "✅ اتطبق التعديل فوراً."

    async def delete_rule(self, rec: dict):
        await run_db(delete_rule_sync, rec["_id"])
        self.errors.pop(rec["_id"], None)
        await self.reload_guild(rec["guild_id"])

    # ---------- التشغيل ----------
    def _trigger_match(self, rule: Compiled, message: discord.Message, norms: dict) -> Optional[str]:
        """بيرجّع الكلمة اللي طابقت ("" لو الشرط مش كلمات) أو None لو القاعدة ما تنطبقش."""
        mode = rule.mode
        if mode == "every":
            return ""
        if mode == "attachments":
            return "" if message.attachments else None
        content = message.content or ""
        if mode == "links":
            return "" if _LINK_RE.search(content) else None
        if mode == "invites":
            return "" if _INVITE_RE.search(content) else None
        if mode == "keywords":
            if rule.collapse not in norms:
                norms[rule.collapse] = normalize_msg(content, rule.collapse)
            text = norms[rule.collapse]
            for kw in rule.keywords:
                if match_keyword(text, kw, rule.match):
                    return kw
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or not self.loaded or message.author.id == self.bot.user.id:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        entry = self.cache.get(message.guild.id)
        if not entry:
            return
        rules = entry["by_channel"].get(message.channel.id, []) + entry["global"]
        if not rules:
            return
        norms: dict = {}
        for rule in rules:
            try:
                if await self._process(rule, message, norms):
                    break  # الرسالة اتحذفت: مفيش قواعد تانية تشتغل عليها
            except Exception as e:
                self.errors[rule.id] = f"{type(e).__name__}: {e}"
                log.exception("خطأ في تنفيذ قاعدة الرد التلقائي %s", rule.name)

    async def _process(self, rule: Compiled, message: discord.Message, norms: dict) -> bool:
        if not rule.enabled:
            return False
        flt = rule.data["filters"]
        author = message.author
        if (author.bot or message.webhook_id) and not flt["allow_bots"]:
            return False
        if isinstance(author, discord.Member):
            if rule.exempt_roles and any(r.id in rule.exempt_roles for r in author.roles):
                return False
            if flt["exempt_staff"] and author.guild_permissions.manage_messages:
                return False
        matched = self._trigger_match(rule, message, norms)
        if matched is None:
            return False
        if flt["cooldown"] > 0:
            key, now = (rule.id, author.id), time.monotonic()
            if now - self.cooldowns.get(key, 0) < flt["cooldown"]:
                return False
            self.cooldowns[key] = now
        self.hit_buffer[rule.id] = self.hit_buffer.get(rule.id, 0) + 1
        return await self._execute(rule, message, matched)

    async def _execute(self, rule: Compiled, message: discord.Message, matched: str) -> bool:
        d, guild, channel = rule.data, message.guild, message.channel
        perms = channel.permissions_for(guild.me)
        dl, acts = d["delivery"], d["actions"]
        ctx = make_ctx(message.author, guild, channel, matched)
        delete_now = bool(dl["delete_trigger"] and dl["delete_trigger_after"] <= 0 and perms.manage_messages)
        problems = []

        if not delete_now:
            if acts["reactions"]:
                if perms.add_reactions:
                    for emoji in acts["reactions"]:
                        try:
                            await message.add_reaction(emoji)
                        except discord.HTTPException:
                            pass  # إيموجي غير موجود أو اتحذف: نكمل الباقي
                else:
                    problems.append("add_reactions")
            if acts["thread"]:
                if perms.create_public_threads:
                    try:
                        name = clip(fill(acts["thread_name"], ctx).strip() or "نقاش", 100)
                        await message.create_thread(name=name, auto_archive_duration=1440)
                    except discord.HTTPException as e:
                        self.errors[rule.id] = f"تعذر إنشاء الثريد: {clip(e, 100)}"
                else:
                    problems.append("create_public_threads")

        content, embed = build_reply(d, ctx)
        sent = None
        if content or embed:
            mode = dl["mode"]
            mentions = discord.AllowedMentions(everyone=False, users=True, roles=[discord.Object(id=acts["ping_role_id"])] if acts["ping_role_id"] else False,
                                               replied_user=bool(dl["mention_author"]))
            try:
                if mode == "dm":
                    sent = await message.author.send(content=content, embed=embed)
                else:
                    if not perms.send_messages or (embed is not None and not perms.embed_links):
                        problems.append("send_messages/embed_links")
                    elif mode == "reply" and not delete_now:
                        try:
                            sent = await message.reply(content=content, embed=embed, allowed_mentions=mentions)
                        except discord.HTTPException:  # رسالة العضو اتمسحت أو مفيش Read History: نبعت عادي
                            sent = await channel.send(content=content, embed=embed, allowed_mentions=mentions)
                    else:
                        sent = await channel.send(content=content, embed=embed, allowed_mentions=mentions)
            except discord.Forbidden:
                self.errors[rule.id] = "مقدرتش أبعت الرد (الخاص مقفول أو صلاحيات ناقصة)."
            except discord.HTTPException as e:
                self.errors[rule.id] = f"ديسكورد رفض الرد: {clip(e, 120)}"

        deleted = False
        if dl["delete_trigger"]:
            if perms.manage_messages:
                try:
                    await message.delete(delay=dl["delete_trigger_after"] if dl["delete_trigger_after"] > 0 else None)
                    deleted = delete_now
                except discord.HTTPException:
                    pass
            else:
                problems.append("manage_messages")
        if sent is not None and dl["delete_reply_after"] > 0 and dl["mode"] != "dm":
            try:
                await sent.delete(delay=dl["delete_reply_after"])
            except discord.HTTPException:
                pass
        if problems:
            self.errors[rule.id] = "صلاحيات ناقصة للبوت في " + channel.mention + ": " + ", ".join(problems)
        return deleted

    # ---------- القائمة الرئيسية ----------
    async def open_live(self, interaction: discord.Interaction, rec: dict):
        s = Session(self, interaction.guild, interaction.user, sanitize(rec.get("data")), rec)
        await s.show(interaction)

    async def handle_dashboard(self, interaction: discord.Interaction, choice: str):
        guild, user = interaction.guild, interaction.user
        if choice == "add":
            options = [discord.SelectOption(label=v[0], description=v[1], emoji=v[2], value=k) for k, v in PRESETS.items()]

            async def on_pick(i: discord.Interaction, key: str):
                channel = i.channel if hasattr(i.channel, "send") else None
                await Session(self, guild, i.user, preset_data(key, channel.id if channel else None)).show(i)

            embed = discord.Embed(title="➕ إضافة قاعدة", description="اختار قالب تبدأ منه (هتقدر تعدّل كل حاجة بعد كده).\n📢 القاعدة هتبدأ على **الروم الحالية** وتقدر تغيّرها.", color=COLOR_BLUE)
            await interaction.response.edit_message(embeds=[embed], view=PickView(user.id, options, on_pick, lambda x: go_dashboard(x, self), "اختر القالب"))
            return
        await interaction.response.defer()
        if choice == "list":
            await self.render_list(interaction, 0)
            return
        try:
            rows = (await run_db(list_rules_sync, guild.id))[:25]
        except Exception as e:
            log.exception("فشل جلب القواعد")
            await interaction.followup.send(content=error_text(e), ephemeral=True)
            return
        if not rows:
            await interaction.followup.send(embed=err_embed("مفيش قواعد لسه. ابدأ بـ ➕ إضافة قاعدة جديدة."), ephemeral=True)
            return
        options = [discord.SelectOption(label=clip(r["data"].get("name") or r["_id"], 100), description=f"#{r['_id']} • {'شغالة' if r['data'].get('enabled', True) else 'متوقفة'} • {MODE_LABEL.get(r['data'].get('trigger', {}).get('mode', 'every'), '')}",
                                        emoji="🟢" if r["data"].get("enabled", True) else "🔴", value=r["_id"]) for r in rows]

        async def on_pick(i: discord.Interaction, rid: str):
            await i.response.defer()
            rec = await run_db(get_rule_sync, rid)
            if rec is None or rec["guild_id"] != guild.id:
                await i.followup.send(embed=err_embed("القاعدة دي مش موجودة."), ephemeral=True)
            elif choice == "edit":
                await self.open_live(i, rec)
            else:
                embed = discord.Embed(title="⚠️ تأكيد الحذف", description=f"هتحذف القاعدة **{rec['data'].get('name')}** `#{rec['_id']}` نهائياً. متأكد؟", color=COLOR_RED)
                await i.edit_original_response(embeds=[embed], view=DeleteConfirmView(self, rec, i.user.id, lambda x: go_dashboard(x, self)))

        title, note = ("✏️ تعديل قاعدة", "اختار القاعدة — هتتفتح للتعديل **المباشر**:") if choice == "edit" else ("🗑️ حذف قاعدة", "اختار القاعدة اللي عاوز تحذفها:")
        if len(rows) == 25:
            note += "\n_(معروض أول 25 قاعدة. لو عاوز غيرهم استخدم `/autoreply_edit`.)_"
        await interaction.edit_original_response(embeds=[discord.Embed(title=title, description=note, color=COLOR_BLUE)],
                                                 view=PickView(user.id, options, on_pick, lambda x: go_dashboard(x, self), "اختر القاعدة"))

    async def render_list(self, interaction: discord.Interaction, page: int):
        if not interaction.response.is_done():
            await interaction.response.defer()
        try:
            rows = await run_db(list_rules_sync, interaction.guild.id)
        except Exception as e:
            log.exception("فشل عرض القواعد")
            await interaction.followup.send(content=error_text(e), ephemeral=True)
            return
        pages = max(1, math.ceil(len(rows) / PER_PAGE))
        page = min(max(0, page), pages - 1)
        lines = []
        for n, r in enumerate(rows[page * PER_PAGE:(page + 1) * PER_PAGE], page * PER_PAGE + 1):
            d = sanitize(r.get("data"))
            icon = "🟢" if d["enabled"] else "🔴"
            chans = " ".join(f"<#{c}>" for c in d["channels"][:3]) + (" …" if len(d["channels"]) > 3 else "") or "🌐 كل الرومات"
            last = f" • آخر مرة <t:{int(r['last_hit'])}:R>" if r.get("last_hit") else ""
            lines.append(f"**{n}.** {icon} **{clip(d.get('name'), 40)}** `#{r['_id']}`\n└ ⚡ {MODE_LABEL[d['trigger']['mode']]} • 📢 {chans}\n└ 💬 {TYPE_LABEL[d['reply']['type']]} • 🔥 `{r.get('hits', 0)}` تشغيل{last}")
        embed = discord.Embed(title="📋 قواعد الرد التلقائي", description="\n\n".join(lines) or "مفيش قواعد لسه. ابدأ بـ ➕ إضافة قاعدة جديدة.", color=DEFAULT_COLOR)
        embed.set_footer(text=f"صفحة {page + 1} من {pages} • الإجمالي {len(rows)}")
        await interaction.edit_original_response(content=None, embeds=[embed], view=ListView(self, interaction.user, page, pages))

    # ---------- الأوامر ----------
    @app_commands.command(name="autoreply", description="[نظام إمبراطوري] مركز الرد التلقائي: إضافة، تعديل مباشر، حذف، وعرض القواعد")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autoreply_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await go_dashboard(interaction, self)

    @app_commands.command(name="autoreply_edit", description="[نظام إمبراطوري] فتح قاعدة رد تلقائي للتعديل المباشر بالاسم أو الرقم")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(rule="اسم القاعدة أو رقمها (هيظهر لك اقتراحات وانت بتكتب)")
    async def autoreply_edit(self, interaction: discord.Interaction, rule: str):
        await interaction.response.defer(ephemeral=True)
        rec = await run_db(get_rule_sync, rule.strip().lstrip("#"))
        if rec is None:
            rows = await run_db(search_rules_sync, interaction.guild.id, rule.strip(), 1)
            rec = rows[0] if rows else None
        if rec is None or rec["guild_id"] != interaction.guild.id:
            await interaction.followup.send(embed=err_embed("القاعدة دي مش موجودة."), ephemeral=True)
            return
        await self.open_live(interaction, rec)

    @autoreply_edit.autocomplete("rule")
    async def autoreply_edit_ac(self, interaction: discord.Interaction, current: str):
        try:
            rows = await run_db(search_rules_sync, interaction.guild.id, current.strip().lstrip("#"), 25)
            return [app_commands.Choice(name=clip(f"#{r['_id']} • {r['data'].get('name')}", 100), value=r["_id"]) for r in rows]
        except Exception:
            return []

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ محتاج صلاحية **Manage Server** لاستخدام الأمر ده.", ephemeral=True)
            return
        log.exception("خطأ في أمر الرد التلقائي", exc_info=error)
        await report_error(interaction, getattr(error, "original", error))


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير موجود في ملف .env، نظام الرد التلقائي محتاج قاعدة بيانات.")
    await bot.add_cog(AutoReplyCog(bot))
