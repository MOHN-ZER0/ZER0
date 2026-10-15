"""
🎉 نظام الجيف أواي الإمبراطوري (النسخة الاحترافية الكاملة)

أهم المميزات:
- بيانات في MongoDB (بدل ملف JSON): كل مشاركة document لوحدها فمفيش حد أقصى للمشاركين، والانضمام ذري وسريع.
- لوحة إنشاء (Builder) فيها معاينة حية: جائزة نصية أو رتبة (البوت يديها للفايزين وممكن تنتهي بعد أيام)،
  شروط (عمر الحساب، مدة العضوية، رتب مطلوبة أي/كل، رتب ممنوعة)، مدخلات إضافية بالرتب، مظهر مخصص، قوالب.
- إدارة كاملة لأي سحب شغال: إيقاف/استئناف، تعديل الوقت والجائزة والشروط، المشاركين، تصدير، إنهاء، إلغاء، Reroll.
- قائمة سوداء (أعضاء ورتب)، رتب مديرين، روم سجلات، وإعدادات افتراضية قابلة للتعديل.
- بيانات الجيف أواي القديمة (ملف JSON) بتتنقل أوتوماتيك أول تشغيل، وزرار الانضمام القديم بيفضل شغال (نفس الـ custom_id).
- محتاج Intents: guilds + members. وصلاحيات البوت: Send Messages + Embed Links (+ Manage Roles لو جوائز الرتب).
"""
import asyncio
import calendar
import copy
import datetime
import io
import json
import logging
import os
import random
import re
import time
from typing import Any, Awaitable, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

load_dotenv()
log = logging.getLogger("giveaway")

# ==============================================================================
# ⚙️ الثوابت
# ==============================================================================
COG_NAME = "ZiuoGiveawayDashboardCog"
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Giveaway_DB"
LEGACY_JSON = "ziuo_giveaway_enterprise_database.json"

COLOR_DARK = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_ORANGE = 0xFFA500
COLOR_BLUE = 0x3498DB

STATUS_ACTIVE, STATUS_PAUSED, STATUS_ENDED, STATUS_CANCELLED = "active", "paused", "ended", "cancelled"
LIVE = (STATUS_ACTIVE, STATUS_PAUSED)
STATUS_ICON = {STATUS_ACTIVE: "🟢", STATUS_PAUSED: "🟠", STATUS_ENDED: "🔴", STATUS_CANCELLED: "⚫", "ending": "🟡"}
STATUS_NAME = {STATUS_ACTIVE: "شغال", STATUS_PAUSED: "متوقف مؤقتاً", STATUS_ENDED: "منتهي", STATUS_CANCELLED: "ملغي", "ending": "بينتهي"}

JOIN_CUSTOM_ID = "enterprise_gw_join_btn"   # نفس الـ id القديم عشان السحوبات القديمة تفضل شغالة
INFO_CUSTOM_ID = "gw:info"
MAX_WINNERS = 50
MIN_DURATION, MAX_DURATION = 30, 90 * 86400
MAX_BONUS_ROLES = 10
MAX_TEMPLATES = 25

DEFAULT_SETTINGS: dict[str, Any] = {
    "log_channel_id": None,
    "manager_role_ids": [],
    "blacklist_users": [],
    "blacklist_roles": [],
    "default_min_account_days": 0,
    "default_min_member_days": 0,
    "default_color": "2B2D31",
    "default_title": "🎉 مسـابـقـة جـيـف أواي",
    "default_button_label": "انضمام للسحب",
    "default_button_emoji": "🎉",
    "footer_text": "",
    "dm_winners": True,
    "show_count": True,
    "allow_leave": True,
    "ping_role_id": None,
    "end_style": "embed",
}

# ==============================================================================
# 💾 قاعدة البيانات
# ==============================================================================
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None


def _col(name: str):
    return _db[name] if _db is not None else None


gw_col = _col("giveaways")
entries_col = _col("giveaway_entries")
settings_col = _col("giveaway_settings")
grants_col = _col("giveaway_role_grants")
templates_col = _col("giveaway_templates")
meta_col = _col("giveaway_meta")


async def run_db(fn, *args, **kwargs):
    """عمليات pymongo (المتزامنة) في thread عشان ما تعطلش البوت."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def now() -> int:
    return int(time.time())


def ensure_indexes_sync():
    specs = [
        (gw_col, [("status", 1), ("ends_at", 1)], {}),
        (gw_col, [("guild_id", 1), ("created_at", -1)], {}),
        (gw_col, [("message_id", 1)], {}),
        (entries_col, [("gw_id", 1), ("user_id", 1)], {"unique": True}),
        (entries_col, [("gw_id", 1), ("joined_at", 1)], {}),
        (settings_col, [("guild_id", 1)], {"unique": True}),
        (grants_col, [("expires_at", 1)], {}),
        (templates_col, [("guild_id", 1), ("name", 1)], {"unique": True}),
    ]
    for col, keys, opts in specs:
        try:
            col.create_index(keys, **opts)
        except Exception:
            log.warning("تعذر إنشاء index %s", keys, exc_info=True)


def settings_get_sync(gid: int) -> dict:
    doc = settings_col.find_one({"guild_id": gid}) or {}
    cfg = copy.deepcopy(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if k in doc:
            cfg[k] = doc[k]
    return cfg


def settings_set_sync(gid: int, fields: dict):
    settings_col.update_one({"guild_id": gid}, {"$set": fields}, upsert=True)


def gw_insert_sync(doc: dict):
    gw_col.insert_one(doc)


def gw_get_sync(gw_id: str) -> Optional[dict]:
    return gw_col.find_one({"_id": gw_id})


def gw_by_message_sync(mid: int) -> Optional[dict]:
    return gw_col.find_one({"message_id": mid})


def gw_update_sync(gw_id: str, sets: dict, unsets: Optional[list] = None, expect: Optional[list] = None) -> Optional[dict]:
    q: dict[str, Any] = {"_id": gw_id}
    if expect:
        q["status"] = {"$in": expect}
    upd: dict[str, Any] = {"$set": sets}
    if unsets:
        upd["$unset"] = {k: "" for k in unsets}
    return gw_col.find_one_and_update(q, upd, return_document=ReturnDocument.AFTER)


def gw_claim_end_sync(gw_id: str) -> Optional[dict]:
    """بيحجز عملية الإنهاء (مرة واحدة بس) ويرجّع الحالة القديمة."""
    return gw_col.find_one_and_update(
        {"_id": gw_id, "status": {"$in": list(LIVE)}}, {"$set": {"status": "ending", "ending_at": now()}},
        return_document=ReturnDocument.BEFORE)


def gw_due_sync(ts: int) -> list:
    return [d["_id"] for d in gw_col.find({"status": STATUS_ACTIVE, "ends_at": {"$lte": ts}}, projection={"_id": 1})]


def gw_recover_sync():
    gw_col.update_many({"status": "ending"}, {"$set": {"status": STATUS_ACTIVE}})


def gw_live_messages_sync() -> list:
    return [d["message_id"] for d in gw_col.find({"status": {"$in": list(LIVE)}, "message_id": {"$ne": None}}, projection={"message_id": 1})]


def gw_delete_sync(gw_id: str):
    gw_col.delete_one({"_id": gw_id})
    entries_col.delete_many({"gw_id": gw_id})


def gw_list_sync(gid: int, statuses: Optional[list], limit: int = 25) -> list:
    q: dict[str, Any] = {"guild_id": gid}
    if statuses:
        q["status"] = {"$in": statuses}
    return list(gw_col.find(q).sort("created_at", -1).limit(limit))


def gw_search_sync(gid: int, text: str, limit: int = 25) -> list:
    q: dict[str, Any] = {"guild_id": gid}
    if text:
        q["$or"] = [{"_id": {"$regex": "^" + re.escape(text)}}, {"prize": {"$regex": re.escape(text), "$options": "i"}}]
    return list(gw_col.find(q, projection={"prize": 1, "status": 1}).sort("created_at", -1).limit(limit))


def entry_add_sync(gw_id: str, gid: int, uid: int, weight: int) -> tuple[bool, int]:
    try:
        entries_col.insert_one({"gw_id": gw_id, "guild_id": gid, "user_id": uid, "weight": weight, "joined_at": now()})
    except DuplicateKeyError:
        doc = gw_col.find_one({"_id": gw_id}, projection={"entries_count": 1}) or {}
        return False, int(doc.get("entries_count", 0))
    doc = gw_col.find_one_and_update({"_id": gw_id}, {"$inc": {"entries_count": 1}}, return_document=ReturnDocument.AFTER)
    return True, int((doc or {}).get("entries_count", 0))


def entry_remove_sync(gw_id: str, uid: int) -> tuple[bool, int]:
    res = entries_col.delete_one({"gw_id": gw_id, "user_id": uid})
    if res.deleted_count != 1:
        return False, 0
    doc = gw_col.find_one_and_update({"_id": gw_id}, {"$inc": {"entries_count": -1}}, return_document=ReturnDocument.AFTER)
    return True, int((doc or {}).get("entries_count", 0))


def entries_all_sync(gw_id: str) -> list:
    return [(d["user_id"], int(d.get("weight", 1))) for d in entries_col.find({"gw_id": gw_id}, projection={"user_id": 1, "weight": 1, "_id": 0})]


def entries_page_sync(gw_id: str, skip: int, limit: int) -> list:
    return list(entries_col.find({"gw_id": gw_id}).sort("joined_at", 1).skip(skip).limit(limit))


def stats_sync(gid: int) -> dict:
    out: dict[str, Any] = {"total": 0, "entries": 0, "by_status": {}}
    for row in gw_col.aggregate([{"$match": {"guild_id": gid}}, {"$group": {"_id": "$status", "n": {"$sum": 1}, "e": {"$sum": "$entries_count"}}}]):
        out["by_status"][row["_id"]] = row["n"]
        out["total"] += row["n"]
        out["entries"] += row["e"]
    return out


def grant_add_sync(gid: int, uid: int, role_id: int, expires: int, gw_id: str):
    grants_col.insert_one({"guild_id": gid, "user_id": uid, "role_id": role_id, "expires_at": expires, "gw_id": gw_id})


def grants_due_sync(ts: int) -> list:
    return list(grants_col.find({"expires_at": {"$lte": ts}}).limit(200))


def grant_delete_sync(_id):
    grants_col.delete_one({"_id": _id})


def template_save_sync(gid: int, name: str, data: dict) -> bool:
    if templates_col.count_documents({"guild_id": gid}) >= MAX_TEMPLATES and not templates_col.find_one({"guild_id": gid, "name": name}):
        return False
    templates_col.update_one({"guild_id": gid, "name": name}, {"$set": {"data": data}}, upsert=True)
    return True


def templates_list_sync(gid: int) -> list:
    return list(templates_col.find({"guild_id": gid}).sort("name", 1).limit(MAX_TEMPLATES))


def template_delete_sync(gid: int, name: str):
    templates_col.delete_one({"guild_id": gid, "name": name})


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


_URL_RE = re.compile(r"^https?://\S{3,2000}$")
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_DUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z\u0600-\u06FF]*)")


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def parse_color(value: Any, default: int = COLOR_DARK) -> int:
    m = _HEX_RE.match(str(value or "").strip())
    return int(m.group(1), 16) if m else default


def normalize_ar(text: str) -> str:
    t = (text or "").strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        t = t.replace(a, b)
    return t


def parse_duration(text: str) -> Optional[int]:
    """مدة بالثواني: 90 (دقائق) / 30m / 2h / 1d12h / ساعتين / 3 ايام. بترجع None لو غير صالحة."""
    total, found = 0.0, False
    for num, unit in _DUR_RE.findall(normalize_ar(text)):
        n = float(num.replace(",", "."))
        u = unit[:1]
        if u in ("s", "ث"):
            mult = 1
        elif u in ("m", "د", ""):
            mult = 60
        elif u in ("h", "س"):
            mult = 3600
        elif u in ("d", "ي"):
            mult = 86400
        elif u in ("w", "ا"):
            mult = 604800
        else:
            return None
        total += n * mult
        found = True
    return int(total) if found and total > 0 else None


def fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d} يوم")
    if h:
        parts.append(f"{h} ساعة")
    if m or not parts:
        parts.append(f"{m} دقيقة")
    return " و ".join(parts)


def fmt_short(seconds: int) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return (f"{d}d" if d else "") + (f"{h}h" if h else "") + (f"{m}m" if m or not (d or h) else "")


def ts_tag(t: int, style: str = "R") -> str:
    return f"<t:{int(t)}:{style}>"


def roles_text(ids: list) -> str:
    return " ".join(f"<@&{r}>" for r in ids) or "—"


def is_manager(member: discord.Member, st: dict) -> bool:
    p = member.guild_permissions
    return p.administrator or p.manage_guild or any(r.id in st.get("manager_role_ids", []) for r in member.roles)


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def edit_ui(interaction: discord.Interaction, **kwargs):
    """يعدّل رسالة الواجهة سواء اتعمل defer قبل كده ولا لأ."""
    if interaction.response.is_done():
        return await interaction.edit_original_response(**kwargs)
    return await interaction.response.edit_message(**kwargs)


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


class ManagerView(SafeView):
    """أي واجهة إدارة: للمشرفين فقط (أدمن / Manage Server / رتبة مدير الجيف أواي)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cog = interaction.client.get_cog(COG_NAME)
        st = await cog.get_settings(interaction.guild.id) if cog else DEFAULT_SETTINGS
        if is_manager(interaction.user, st):
            return True
        await respond(interaction, embed=err_embed("الواجهة دي للمشرفين فقط."), ephemeral=True)
        return False


# ==============================================================================
# 🧬 بنية السحب والشروط والاختيار العشوائي
# ==============================================================================
def default_req(st: dict) -> dict:
    return {"min_account_days": int(st.get("default_min_account_days", 0)), "min_member_days": int(st.get("default_min_member_days", 0)),
            "roles_mode": "any", "required_roles": [], "forbidden_roles": []}


def default_draft(st: dict, channel_id: int) -> dict:
    return {
        "prize": "", "description": "", "winners_count": 1, "duration": 3600, "image_url": None,
        "prize_type": "custom", "prize_role_id": None, "prize_role_days": 0,
        "req": default_req(st), "bonus": {},
        "style": {"title": None, "color": None, "button_label": None, "button_emoji": None, "footer": None},
        "opts": {"dm_winners": bool(st["dm_winners"]), "show_count": bool(st["show_count"]), "allow_leave": bool(st["allow_leave"])},
        "ping_role_id": st.get("ping_role_id"), "ping_everyone": False, "channel_id": channel_id,
    }


def draft_to_gw(draft: dict, host_id: int, guild_id: int, gw_id: str = "PREVIEW") -> dict:
    gw = copy.deepcopy(draft)
    t = now()
    gw.update({"_id": gw_id, "guild_id": guild_id, "host_id": host_id, "status": STATUS_ACTIVE, "created_at": t,
               "ends_at": t + int(gw.pop("duration", 3600)), "entries_count": 0, "winners": [], "message_id": None,
               "winners_count": int(gw["winners_count"])})
    return gw


def compute_weight(member: Optional[discord.Member], gw: dict) -> int:
    if member is None:
        return 1
    role_ids = {r.id for r in member.roles}
    extra = sum(int(v) for rid, v in (gw.get("bonus") or {}).items() if int(rid) in role_ids)
    return max(1, min(1 + extra, 500))


def check_member(member: discord.Member, gw: dict, st: dict) -> list[str]:
    """بيرجّع قايمة أسباب عدم الأهلية (فاضية = مؤهل)."""
    role_ids = {r.id for r in member.roles}
    if member.id in st.get("blacklist_users", []) or role_ids & set(st.get("blacklist_roles", [])):
        return ["🚫 أنت ممنوع من المشاركة في الجيف أواي (القائمة السوداء)."]
    req = gw.get("req") or {}
    fails = []
    tnow = discord.utils.utcnow()
    need = int(req.get("min_account_days") or 0)
    if need and (tnow - member.created_at).days < need:
        fails.append(f"🔞 عمر حسابك لازم يكون **{need}** يوم على الأقل.")
    need = int(req.get("min_member_days") or 0)
    if need and member.joined_at and (tnow - member.joined_at).days < need:
        fails.append(f"📅 لازم تكون في السيرفر من **{need}** يوم على الأقل.")
    rr = [int(x) for x in req.get("required_roles") or []]
    if rr:
        ok = (all if req.get("roles_mode") == "all" else any)(r in role_ids for r in rr)
        if not ok:
            fails.append(f"🎭 لازم تكون معاك {'كل' if req.get('roles_mode') == 'all' else 'أي واحدة من'} الرتب: {roles_text(rr)}")
    bad = [int(x) for x in req.get("forbidden_roles") or [] if int(x) in role_ids]
    if bad:
        fails.append(f"⛔ رتبك دي ممنوعة من المشاركة: {roles_text(bad)}")
    return fails


def weighted_order(entries: list, exclude: set, rng=random) -> list[int]:
    """ترتيب عشوائي موزون بدون تكرار (Efraimidis–Spirakis): الأعلى وزناً فرصته أكبر."""
    keyed = [(rng.random() ** (1.0 / w), uid) for uid, w in entries if uid not in exclude and w > 0]
    keyed.sort(reverse=True)
    return [uid for _, uid in keyed]


def role_problem(guild: discord.Guild, role: Optional[discord.Role]) -> Optional[str]:
    if role is None:
        return "الرتبة مش موجودة"
    if role.is_default():
        return "مينفعش @everyone"
    if role.managed:
        return "رتبة خاصة بتكامل/بوت"
    if role >= guild.me.top_role:
        return "الرتبة أعلى من رتبة البوت أو مساوية لها"
    return None


# ==============================================================================
# 🖼️ الإيمبدات
# ==============================================================================
def requirement_lines(req: dict) -> list[str]:
    lines = []
    if req.get("min_account_days"):
        lines.append(f"🔞 عمر الحساب: **{req['min_account_days']}** يوم على الأقل")
    if req.get("min_member_days"):
        lines.append(f"📅 مدة العضوية في السيرفر: **{req['min_member_days']}** يوم على الأقل")
    if req.get("required_roles"):
        lines.append(f"🎭 رتب مطلوبة ({'كلها' if req.get('roles_mode') == 'all' else 'أي واحدة'}): {roles_text(req['required_roles'])}")
    if req.get("forbidden_roles"):
        lines.append(f"⛔ ممنوع على: {roles_text(req['forbidden_roles'])}")
    return lines


def bonus_lines(bonus: dict) -> list[str]:
    return [f"<@&{rid}> ⟵ **+{v}** مدخلات" for rid, v in (bonus or {}).items()]


def build_giveaway_embed(gw: dict, guild: discord.Guild, st: dict) -> discord.Embed:
    status = gw.get("status", STATUS_ACTIVE)
    style = gw.get("style") or {}
    title = style.get("title") or st["default_title"]
    color = parse_color(style.get("color") or st["default_color"])
    if status == STATUS_PAUSED:
        title, color = f"⏸️ {title}", COLOR_ORANGE
    elif status == STATUS_ENDED:
        title, color = "🔒 **انـتـهـى الـجـيـف أواي (مغلق)** 🔒", COLOR_DARK
    elif status == STATUS_CANCELLED:
        title, color = "🚫 **تـم إلـغـاء الـجـيـف أواي** 🚫", COLOR_RED
    embed = discord.Embed(title=clip(title, 256), description=(f"💬 **{clip(gw.get('description'), 1500)}**" if gw.get("description") else None),
                          color=color, timestamp=discord.utils.utcnow())
    prize = f"**{clip(gw['prize'], 200) or '—'}**"
    if gw.get("prize_type") == "role" and gw.get("prize_role_id"):
        days = gw.get("prize_role_days") or 0
        prize += f"\n🎭 رتبة: <@&{gw['prize_role_id']}>" + (f" (لمدة {days} يوم)" if days else " (دايمة)")
    embed.add_field(name="🎁 الجائزة", value=prize, inline=True)
    embed.add_field(name="🏆 عدد الفائزين", value=f"`{gw.get('winners_count', 1)}`", inline=True)
    if status == STATUS_PAUSED:
        embed.add_field(name="⏳ الوقت", value=f"⏸️ متوقف (المتبقي {fmt_duration(gw.get('paused_remaining') or 0)})", inline=True)
    elif status in (STATUS_ENDED, STATUS_CANCELLED):
        embed.add_field(name="⏳ الوقت", value=f"انتهى {ts_tag(gw.get('ended_at') or gw.get('ends_at') or now())}", inline=True)
    else:
        embed.add_field(name="⏳ ينتهي", value=f"{ts_tag(gw['ends_at'])}\n{ts_tag(gw['ends_at'], 'f')}", inline=True)
    embed.add_field(name="👤 المُنشئ", value=f"<@{gw['host_id']}>", inline=True)
    if (gw.get("opts") or {}).get("show_count", True):
        embed.add_field(name="👥 المشاركين", value=f"`{gw.get('entries_count', 0)}`", inline=True)
    embed.add_field(name="🛡️ الشروط", value=clip("\n".join(requirement_lines(gw.get("req") or {})) or "✅ مفيش شروط، الكل يقدر يشارك", 1024), inline=False)
    if gw.get("bonus"):
        embed.add_field(name="⭐ مدخلات إضافية", value=clip("\n".join(bonus_lines(gw["bonus"])), 1024), inline=False)
    if status == STATUS_ENDED:
        winners = gw.get("winners") or []
        embed.add_field(name="👑 الفائزون", value=clip("\n".join(f"**{i}.** <@{u}>" for i, u in enumerate(winners, 1)) or "❌ مفيش فايزين (مفيش مشاركين مؤهلين)", 1024), inline=False)
    if gw.get("image_url"):
        embed.set_image(url=gw["image_url"])
    foot = style.get("footer") or st.get("footer_text") or "النظام الاحترافي"
    embed.set_footer(text=clip(f"Giveaway ID: {gw['_id']} • {foot}", 2048), icon_url=guild.icon.url if guild.icon else None)
    return embed


def build_result_embed(gw: dict, winners: list[int], reroll: bool, gw_url: Optional[str], granted: Optional[tuple[int, int]] = None) -> discord.Embed:
    if not winners:
        e = discord.Embed(title="❌ انتهى السحب بدون فايزين", description=f"انتهى السحب على **{gw['prize']}** ومحدش مؤهل شارك للأسف!", color=COLOR_RED)
    else:
        lines = "\n".join(f"**{i}.** <@{u}>" for i, u in enumerate(winners, 1))
        e = discord.Embed(title="🔄 إعادة سحب — فايزين جدد!" if reroll else "🎊 إنـتـهـى الـسـحـب بـنـجـاح 🎊",
                          description=f"🎁 **الجائزة:** {gw['prize']}\n\n👑 **{'الفايزون الجدد' if reroll else 'الفايزون بالترتيب'}:**\n{lines}", color=COLOR_GREEN)
        if gw.get("prize_type") == "role" and granted:
            e.add_field(name="🎭 توزيع الرتبة", value=f"اتمنحت لـ `{granted[0]}` فايز" + (f" (وفشل `{granted[1]}`)" if granted[1] else ""), inline=False)
    if gw_url:
        e.add_field(name="🔗 رسالة السحب", value=f"[اضغط هنا]({gw_url})", inline=False)
    e.set_footer(text=f"Giveaway ID: {gw['_id']}")
    return e


def settings_summary_embed(guild: discord.Guild, st: dict) -> discord.Embed:
    def onoff(v):
        return "مفعل ✅" if v else "معطل ❌"

    desc = (
        "> **لوحة الإعدادات العامة للجيف أواي.** ⚙️\n\n"
        f"📊 **روم السجلات:** {f'<#{st['log_channel_id']}>' if st['log_channel_id'] else '`غير محدد`'}\n"
        f"👮 **رتب المديرين:** {roles_text(st['manager_role_ids'])}\n"
        f"📣 **رتبة التنبيه الافتراضية:** {f'<@&{st['ping_role_id']}>' if st['ping_role_id'] else '`بدون`'}\n\n"
        f"✉️ **إرسال خاص للفايزين:** {onoff(st['dm_winners'])}\n"
        f"👥 **إظهار عدد المشاركين:** {onoff(st['show_count'])}\n"
        f"🚪 **السماح بالانسحاب:** {onoff(st['allow_leave'])}\n\n"
        f"🎨 **العنوان:** {st['default_title']} ┊ **اللون:** `#{st['default_color']}`\n"
        f"🔘 **الزرار:** {st['default_button_emoji']} {st['default_button_label']}\n"
        f"🛡️ **شروط افتراضية:** عمر حساب `{st['default_min_account_days']}` يوم ┊ عضوية `{st['default_min_member_days']}` يوم\n"
        f"📢 **شكل رسالة النتيجة:** `{'إيمبد' if st['end_style'] == 'embed' else 'نص'}`\n\n"
        "_الإعدادات دي هي القيم الافتراضية لأي سحب جديد، وتقدر تعدلها لكل سحب لوحده من لوحة الإنشاء._"
    )
    e = discord.Embed(title=f"⚙️ ‹ إعدادات الجيف أواي — {guild.name} ›", description=desc, color=COLOR_DARK)
    return e


# ==============================================================================
# 🔘 أزرار السحب (دايمة بعد الريستارت)
# ==============================================================================
class GiveawayEntryView(discord.ui.View):
    def __init__(self, label: str = "انضمام للسحب", emoji: Optional[str] = "🎉", count: Optional[int] = None, disabled: bool = False):
        super().__init__(timeout=None)
        self.join_button.label = f"{label} ({count})" if count is not None else label
        self.join_button.emoji = emoji or None
        self.join_button.disabled = disabled
        self.info_button.disabled = False

    @discord.ui.button(label="انضمام للسحب", emoji="🎉", style=discord.ButtonStyle.success, custom_id=JOIN_CUSTOM_ID)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog(COG_NAME)
        if cog is None:
            await respond(interaction, content="❌ النظام مش شغال حالياً.", ephemeral=True)
            return
        await cog.handle_join(interaction)

    @discord.ui.button(label="الشروط", emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id=INFO_CUSTOM_ID)
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog(COG_NAME)
        if cog is None:
            await respond(interaction, content="❌ النظام مش شغال حالياً.", ephemeral=True)
            return
        await cog.handle_info(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في زرار الجيف أواي", exc_info=error)
        await report_error(interaction)


class LeaveView(SafeView):
    def __init__(self, cog, gw_id: str):
        super().__init__(timeout=60)
        self.cog, self.gw_id = cog, gw_id

    @discord.ui.button(label="انسحب من السحب", emoji="🚪", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        removed, count = await run_db(entry_remove_sync, self.gw_id, interaction.user.id)
        if removed:
            self.cog.dirty.add(self.gw_id)
        await interaction.edit_original_response(embed=ok_embed("📤 تم الانسحاب", "اتشلت مشاركتك من السحب.") if removed else err_embed("مشاركتك مش موجودة أصلاً."), view=None)


class ConfirmView(SafeView):
    def __init__(self, owner_id: int, on_confirm: Callable[[discord.Interaction], Awaitable[None]], label: str = "تأكيد"):
        super().__init__(timeout=45)
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
# 🧩 محررات الإعدادات المشتركة (بتشتغل على المسودة وعلى السحب الشغال)
# ==============================================================================
class ConfigTarget:
    """cfg = قاموس قابل للتعديل (مسودة أو سحب شغال). persist = حفظ التعديل (لو السحب شغال)."""

    def __init__(self, cfg: dict, persist: Optional[Callable[[], Awaitable[None]]] = None):
        self.cfg, self.persist = cfg, persist

    async def save(self):
        if self.persist:
            await self.persist()


class AgeModal(SafeModal):
    def __init__(self, view: "RequirementsView"):
        super().__init__(title="🔞 شروط العمر والعضوية")
        self.view = view
        req = view.target.cfg["req"]
        self.acc = discord.ui.TextInput(label="أدنى عمر للحساب بالأيام (0 = بدون)", default=str(req.get("min_account_days", 0)), max_length=4)
        self.mem = discord.ui.TextInput(label="أدنى مدة عضوية في السيرفر بالأيام (0 = بدون)", default=str(req.get("min_member_days", 0)), max_length=4)
        self.add_item(self.acc)
        self.add_item(self.mem)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            a, m = int(self.acc.value.strip()), int(self.mem.value.strip())
            if not (0 <= a <= 5000 and 0 <= m <= 5000):
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("اكتب أرقام صحيحة من 0 لـ 5000."), ephemeral=True)
            return
        self.view.target.cfg["req"].update(min_account_days=a, min_member_days=m)
        await self.view.target.save()
        await self.view.render(interaction)


class RequirementsView(ManagerView):
    def __init__(self, target: ConfigTarget, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(timeout=600)
        self.target, self.back = target, back
        self._sync_labels()

    def _sync_labels(self):
        self.mode_btn.label = "الرتب المطلوبة: كلها" if self.target.cfg["req"].get("roles_mode") == "all" else "الرتب المطلوبة: أي واحدة"

    def embed(self) -> discord.Embed:
        lines = requirement_lines(self.target.cfg["req"]) or ["✅ مفيش شروط حالياً — الكل يقدر يشارك"]
        return discord.Embed(
            title="🛡️ شروط المشاركة",
            description=("اللي بيحقق **كل** الشروط تحت بس يقدر يشارك:\n\n" + "\n".join(lines) +
                         "\n\n🎭 **الرتب المطلوبة:** اختار الرتب من القائمة الأولى (امسح الاختيار لإزالتها).\n"
                         "⛔ **الرتب الممنوعة:** أصحاب الرتب دي مش هيقدروا يشاركوا.\n"
                         "🔀 **وضع الرتب:** هل لازم **أي** واحدة من الرتب المطلوبة ولا **كلها** معاً؟\n"
                         "🔞 **العمر والعضوية:** أدنى عمر للحساب وأدنى مدة في السيرفر."),
            color=COLOR_DARK)

    async def render(self, interaction: discord.Interaction):
        self._sync_labels()
        await edit_ui(interaction, embed=self.embed(), embeds=[self.embed()], view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🎭 الرتب المطلوبة للمشاركة (امسح الاختيار للإزالة)", min_values=0, max_values=10, row=0)
    async def pick_required(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.target.cfg["req"]["required_roles"] = [r.id for r in select.values if not r.is_default()]
        await self.target.save()
        await self.render(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="⛔ الرتب الممنوعة من المشاركة (امسح الاختيار للإزالة)", min_values=0, max_values=10, row=1)
    async def pick_forbidden(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.target.cfg["req"]["forbidden_roles"] = [r.id for r in select.values if not r.is_default()]
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="العمر والعضوية", emoji="🔞", style=discord.ButtonStyle.primary, row=2)
    async def age_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AgeModal(self))

    @discord.ui.button(label="الرتب المطلوبة: أي واحدة", emoji="🔀", style=discord.ButtonStyle.secondary, row=2)
    async def mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        req = self.target.cfg["req"]
        req["roles_mode"] = "any" if req.get("roles_mode") == "all" else "all"
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="مسح كل الشروط", emoji="🧹", style=discord.ButtonStyle.danger, row=2)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.target.cfg["req"].update(min_account_days=0, min_member_days=0, roles_mode="any", required_roles=[], forbidden_roles=[])
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back(interaction)


class BonusAmountModal(SafeModal):
    def __init__(self, view: "BonusView", role_ids: list[int]):
        super().__init__(title="⭐ عدد المدخلات الإضافية")
        self.view, self.role_ids = view, role_ids
        self.box = discord.ui.TextInput(label="كام مدخل إضافي لكل رتبة؟ (1-50)", default="1", max_length=2)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            n = int(self.box.value.strip())
            if not 1 <= n <= 50:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("اكتب رقم من 1 لـ 50."), ephemeral=True)
            return
        bonus = self.view.target.cfg["bonus"]
        for rid in self.role_ids:
            if len(bonus) >= MAX_BONUS_ROLES and str(rid) not in bonus:
                break
            bonus[str(rid)] = n
        await self.view.target.save()
        await self.view.render(interaction)


class BonusView(ManagerView):
    def __init__(self, target: ConfigTarget, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(timeout=600)
        self.target, self.back = target, back

    def embed(self) -> discord.Embed:
        lines = bonus_lines(self.target.cfg["bonus"]) or ["`مفيش مدخلات إضافية حالياً`"]
        return discord.Embed(
            title="⭐ المدخلات الإضافية بالرتب",
            description=("أصحاب الرتب دي فرصتهم في الفوز أعلى (كل مدخل إضافي = فرصة زيادة):\n\n" + "\n".join(lines) +
                         "\n\n➕ **إضافة/تعديل:** اختار رتب وبعدها اكتب عدد المدخلات الإضافية.\n"
                         "➖ **إزالة:** اختار رتب عشان تشيلها.\n"
                         f"_(حد أقصى {MAX_BONUS_ROLES} رتب. المدخلات بتتجمع لو العضو معاه أكتر من رتبة.)_"),
            color=COLOR_DARK)

    async def render(self, interaction: discord.Interaction):
        await edit_ui(interaction, embed=self.embed(), embeds=[self.embed()], view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="➕ اختر رتب لإضافة/تعديل مدخلاتها", min_values=1, max_values=5, row=0)
    async def add_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        ids = [r.id for r in select.values if not r.is_default()]
        if not ids:
            await respond(interaction, embed=err_embed("اختار رتبة حقيقية (مش @everyone)."), ephemeral=True)
            return
        await interaction.response.send_modal(BonusAmountModal(self, ids))

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="➖ اختر رتب لإزالتها", min_values=1, max_values=5, row=1)
    async def remove_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        for r in select.values:
            self.target.cfg["bonus"].pop(str(r.id), None)
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="مسح الكل", emoji="🧹", style=discord.ButtonStyle.danger, row=2)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.target.cfg["bonus"].clear()
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back(interaction)


class RoleDaysModal(SafeModal):
    def __init__(self, view: "PrizeView"):
        super().__init__(title="⏳ مدة رتبة الجائزة")
        self.view = view
        self.box = discord.ui.TextInput(label="كام يوم تفضل الرتبة؟ (0 = دايمة)", default=str(view.target.cfg.get("prize_role_days", 0)), max_length=4)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = int(self.box.value.strip())
            if not 0 <= d <= 3650:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("اكتب عدد أيام من 0 لـ 3650."), ephemeral=True)
            return
        self.view.target.cfg["prize_role_days"] = d
        await self.view.target.save()
        await self.view.render(interaction)


class PrizeView(ManagerView):
    def __init__(self, target: ConfigTarget, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(timeout=600)
        self.target, self.back = target, back

    def embed(self) -> discord.Embed:
        c = self.target.cfg
        if c.get("prize_type") == "role" and c.get("prize_role_id"):
            days = c.get("prize_role_days") or 0
            cur = f"🎭 **جائزة رتبة:** <@&{c['prize_role_id']}> " + (f"(لمدة {days} يوم)" if days else "(دايمة)")
        else:
            cur = "📝 **جائزة نصية:** " + (clip(c.get("prize"), 100) or "`لسه ما اتكتبتش`")
        return discord.Embed(
            title="🎁 نوع الجائزة",
            description=(f"{cur}\n\n📝 **جائزة نصية:** أي حاجة تكتبها (نيترو، رصيد، ...) والتسليم يدوي.\n"
                         "🎭 **جائزة رتبة:** اختار رتبة والبوت **هيديها للفايزين أوتوماتيك** لما السحب ينتهي (محتاج صلاحية Manage Roles ورتبة البوت فوقها).\n"
                         "⏳ **مدة الرتبة:** تقدر تخليها تتشال تلقائياً بعد عدد أيام."),
            color=COLOR_DARK)

    async def render(self, interaction: discord.Interaction):
        await edit_ui(interaction, embed=self.embed(), embeds=[self.embed()], view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🎭 اختر رتبة الجائزة (البوت هيديها للفايزين)", min_values=1, max_values=1, row=0)
    async def pick_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = interaction.guild.get_role(select.values[0].id)
        problem = role_problem(interaction.guild, role)
        if problem:
            await respond(interaction, embed=err_embed(f"{problem}. اختار رتبة تانية أو حرّك رتبة البوت فوقها."), ephemeral=True)
            return
        c = self.target.cfg
        c["prize_type"], c["prize_role_id"] = "role", role.id
        if not c.get("prize"):
            c["prize"] = f"رتبة {role.name}"
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="جائزة نصية", emoji="📝", style=discord.ButtonStyle.primary, row=1)
    async def text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        c = self.target.cfg
        c["prize_type"], c["prize_role_id"], c["prize_role_days"] = "custom", None, 0
        await self.target.save()
        await self.render(interaction)

    @discord.ui.button(label="مدة الرتبة", emoji="⏳", style=discord.ButtonStyle.secondary, row=1)
    async def days_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target.cfg.get("prize_type") != "role":
            await respond(interaction, embed=err_embed("اختار رتبة جائزة الأول."), ephemeral=True)
            return
        await interaction.response.send_modal(RoleDaysModal(self))

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back(interaction)


class AppearanceModal(SafeModal):
    def __init__(self, target: ConfigTarget, after: Callable[[discord.Interaction], Awaitable[None]], st: dict):
        super().__init__(title="🎨 مظهر السحب")
        self.target, self.after = target, after
        s = target.cfg["style"]
        self.t = discord.ui.TextInput(label="عنوان الإيمبد (فاضي = الافتراضي)", default=s.get("title") or "", required=False, max_length=100, placeholder=st["default_title"])
        self.c = discord.ui.TextInput(label="اللون Hex (فاضي = الافتراضي)", default=s.get("color") or "", required=False, max_length=7, placeholder=st["default_color"])
        self.bl = discord.ui.TextInput(label="نص زرار الانضمام", default=s.get("button_label") or "", required=False, max_length=40, placeholder=st["default_button_label"])
        self.be = discord.ui.TextInput(label="إيموجي الزرار", default=s.get("button_emoji") or "", required=False, max_length=60, placeholder=st["default_button_emoji"])
        self.f = discord.ui.TextInput(label="نص التذييل (فاضي = الافتراضي)", default=s.get("footer") or "", required=False, max_length=80)
        for b in (self.t, self.c, self.bl, self.be, self.f):
            self.add_item(b)

    async def on_submit(self, interaction: discord.Interaction):
        color = self.c.value.strip()
        if color and not _HEX_RE.match(color):
            await respond(interaction, embed=err_embed("اللون لازم Hex من 6 خانات، مثال: `2B2D31`."), ephemeral=True)
            return
        emoji = self.be.value.strip()
        if emoji and discord.PartialEmoji.from_str(emoji).name is None:
            emoji = ""
        self.target.cfg["style"] = {"title": self.t.value.strip() or None, "color": (color.lstrip("#").upper() if color else None),
                                    "button_label": self.bl.value.strip() or None, "button_emoji": emoji or None, "footer": self.f.value.strip() or None}
        await self.target.save()
        await self.after(interaction)


class InfoModal(SafeModal):
    """معلومات السحب الأساسية (للمسودة أو لسحب شغال)."""

    def __init__(self, target: ConfigTarget, after: Callable[[discord.Interaction], Awaitable[None]], with_duration: bool):
        super().__init__(title="📝 معلومات السحب")
        self.target, self.after, self.with_duration = target, after, with_duration
        c = target.cfg
        self.prize = discord.ui.TextInput(label="اسم الجائزة", default=c.get("prize", ""), max_length=100, required=True, placeholder="مثال: نيترو / VIP / 100$")
        self.winners = discord.ui.TextInput(label=f"عدد الفائزين (1-{MAX_WINNERS})", default=str(c.get("winners_count", 1)), max_length=2, required=True)
        self.desc = discord.ui.TextInput(label="وصف/شروط إضافية (اختياري)", default=c.get("description", ""), style=discord.TextStyle.paragraph, max_length=1000, required=False)
        self.image = discord.ui.TextInput(label="رابط صورة (اختياري)", default=c.get("image_url") or "", max_length=400, required=False)
        for b in (self.prize, self.winners, self.desc, self.image):
            self.add_item(b)
        if with_duration:
            self.dur = discord.ui.TextInput(label="المدة (60 / 30m / 2h / 1d12h)", default=fmt_short(c.get("duration", 3600)), max_length=20, required=True)
            self.add_item(self.dur)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            w = int(self.winners.value.strip())
            if not 1 <= w <= MAX_WINNERS:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed(f"عدد الفائزين لازم رقم من 1 لـ {MAX_WINNERS}."), ephemeral=True)
            return
        raw_img = self.image.value.strip()
        if raw_img and not clean_url(raw_img):
            await respond(interaction, embed=err_embed("رابط الصورة لازم يبدأ بـ http أو https."), ephemeral=True)
            return
        duration = None
        if self.with_duration:
            duration = parse_duration(self.dur.value)
            if duration is None or not MIN_DURATION <= duration <= MAX_DURATION:
                await respond(interaction, embed=err_embed("المدة غير صالحة (من 30 ثانية لـ 90 يوم). أمثلة: `90` دقيقة، `2h`، `1d12h`."), ephemeral=True)
                return
        c = self.target.cfg
        c.update(prize=self.prize.value.strip(), winners_count=w, description=self.desc.value.strip(), image_url=raw_img or None)
        if duration:
            c["duration"] = duration
        await self.target.save()
        await self.after(interaction)


# ==============================================================================
# 🏗️ لوحة إنشاء الجيف أواي (Builder) مع معاينة حية
# ==============================================================================
class BuilderState:
    def __init__(self, cog, guild: discord.Guild, user_id: int, st: dict, channel_id: int):
        self.cog, self.guild, self.user_id, self.st = cog, guild, user_id, st
        self.draft = default_draft(st, channel_id)

    def validate(self) -> list[str]:
        d, errors = self.draft, []
        if not d["prize"].strip():
            errors.append("📝 اكتب اسم الجائزة (زرار المعلومات الأساسية).")
        if d["prize_type"] == "role":
            problem = role_problem(self.guild, self.guild.get_role(d["prize_role_id"] or 0))
            if problem:
                errors.append(f"🎭 رتبة الجائزة: {problem}")
        chan = self.guild.get_channel_or_thread(d["channel_id"])
        if chan is None:
            errors.append("📢 الروم مش موجود، اختار روم تاني.")
        else:
            p = chan.permissions_for(self.guild.me)
            if not (p.view_channel and p.send_messages and p.embed_links):
                errors.append(f"📢 البوت محتاج Send Messages + Embed Links في {chan.mention}.")
            if d["ping_everyone"] and not p.mention_everyone:
                errors.append("📣 البوت معندوش صلاحية Mention Everyone في الروم ده.")
        return errors

    def embeds(self) -> list[discord.Embed]:
        d = self.draft
        chan = self.guild.get_channel_or_thread(d["channel_id"])
        ping = "@everyone" if d["ping_everyone"] else (f"<@&{d['ping_role_id']}>" if d["ping_role_id"] else "بدون")
        checklist = (
            "**🏗️ لوحة إنشاء الجيف أواي** — جهّز كل حاجة وبعدها اضغط 🚀 إطلاق.\n\n"
            f"📝 **الجائزة:** {'✅ ' + clip(d['prize'], 40) if d['prize'] else '❌ لسه'}\n"
            f"⏱️ **المدة:** `{fmt_duration(d['duration'])}` ┊ 🏆 **الفائزين:** `{d['winners_count']}`\n"
            f"📢 **الروم:** {chan.mention if chan else '❌'} ┊ 📣 **التنبيه:** {ping}\n"
            f"🛡️ **شروط:** `{len(requirement_lines(d['req']))}` ┊ ⭐ **رتب بمدخلات إضافية:** `{len(d['bonus'])}`\n\n"
            "👇 تحت معاينة لشكل السحب بالظبط:")
        preview = build_giveaway_embed(draft_to_gw(d, self.user_id, self.guild.id), self.guild, self.st)
        return [discord.Embed(description=checklist, color=COLOR_BLUE), preview]

    async def show(self, interaction: discord.Interaction):
        await edit_ui(interaction, embeds=self.embeds(), content=None, view=BuilderView(self))

    def target(self) -> ConfigTarget:
        return ConfigTarget(self.draft)


class ChannelPickView(ManagerView):
    def __init__(self, state: BuilderState):
        super().__init__(timeout=600)
        self.state = state

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📢 اختر الروم اللي هيتنشر فيه السحب",
                       channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=1, max_values=1)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.state.draft["channel_id"] = select.values[0].id
        await self.state.show(interaction)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.state.show(interaction)


class OptionsView(ManagerView):
    def __init__(self, state: BuilderState):
        super().__init__(timeout=600)
        self.state = state
        self._sync()

    def _sync(self):
        d = self.state.draft
        for btn, on in ((self.dm_btn, d["opts"]["dm_winners"]), (self.count_btn, d["opts"]["show_count"]),
                        (self.leave_btn, d["opts"]["allow_leave"]), (self.everyone_btn, d["ping_everyone"])):
            btn.style = discord.ButtonStyle.success if on else discord.ButtonStyle.secondary

    def embed(self) -> discord.Embed:
        return discord.Embed(
            title="⚙️ خيارات السحب",
            description=("اضغط أي زرار لتبديله (🟩 مفعل / ⬜ متوقف):\n\n"
                         "✉️ **خاص للفايزين:** البوت يبعت للفايز رسالة خاصة.\n"
                         "👥 **إظهار عدد المشاركين:** العدد بيظهر في الرسالة وعلى الزرار.\n"
                         "🚪 **السماح بالانسحاب:** العضو يقدر يشيل مشاركته.\n"
                         "📣 **@everyone:** تنبيه الكل لما السحب يتنشر.\n"
                         "👇 أو اختار **رتبة تنبيه** من القائمة (امسح الاختيار لإلغائها)."),
            color=COLOR_DARK)

    async def render(self, interaction: discord.Interaction):
        self._sync()
        await edit_ui(interaction, embeds=[self.embed()], view=self)

    def _toggle(self, interaction, key_path):
        d = self.state.draft
        if key_path == "ping_everyone":
            d["ping_everyone"] = not d["ping_everyone"]
        else:
            d["opts"][key_path] = not d["opts"][key_path]

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="📣 رتبة التنبيه (اختياري)", min_values=0, max_values=1, row=0)
    async def ping_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.state.draft["ping_role_id"] = select.values[0].id if select.values else None
        await self.render(interaction)

    @discord.ui.button(label="خاص للفايزين", emoji="✉️", row=1)
    async def dm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._toggle(interaction, "dm_winners")
        await self.render(interaction)

    @discord.ui.button(label="عدد المشاركين", emoji="👥", row=1)
    async def count_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._toggle(interaction, "show_count")
        await self.render(interaction)

    @discord.ui.button(label="السماح بالانسحاب", emoji="🚪", row=1)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._toggle(interaction, "allow_leave")
        await self.render(interaction)

    @discord.ui.button(label="@everyone", emoji="📣", row=1)
    async def everyone_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._toggle(interaction, "ping_everyone")
        await self.render(interaction)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.primary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.state.show(interaction)


class TemplateSaveModal(SafeModal):
    def __init__(self, state: BuilderState):
        super().__init__(title="💾 حفظ كقالب")
        self.state = state
        self.name = discord.ui.TextInput(label="اسم القالب", max_length=40, required=True, placeholder="مثال: سحب نيترو أسبوعي")
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        data = copy.deepcopy(self.state.draft)
        data.pop("channel_id", None)
        ok = await run_db(template_save_sync, interaction.guild.id, self.name.value.strip(), data)
        if not ok:
            await respond(interaction, embed=err_embed(f"وصلت للحد الأقصى ({MAX_TEMPLATES} قالب). احذف قالب الأول."), ephemeral=True)
            return
        await self.state.show(interaction)
        await interaction.followup.send(embed=ok_embed("💾 تم الحفظ", f"اتحفظ القالب **{self.name.value.strip()}**. تقدر تحمّله من زرار 📂 قالب."), ephemeral=True)


class TemplatePickView(ManagerView):
    def __init__(self, state: BuilderState, templates: list):
        super().__init__(timeout=300)
        self.state, self.by_name = state, {t["name"]: t for t in templates}
        select = discord.ui.Select(placeholder="📂 اختر القالب", options=[discord.SelectOption(label=clip(n, 100), value=n, emoji="📄") for n in list(self.by_name)[:25]])

        async def cb(i: discord.Interaction):
            data = copy.deepcopy(self.by_name[select.values[0]]["data"])
            merged = default_draft(self.state.st, self.state.draft["channel_id"])
            for k, v in data.items():
                if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                    merged[k].update(v)
                elif k in merged:
                    merged[k] = v
            self.state.draft = merged
            await self.state.show(i)

        select.callback = cb
        self.add_item(select)

    @discord.ui.button(label="حذف القالب المختار", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        sel = next((c for c in self.children if isinstance(c, discord.ui.Select)), None)
        if not sel or not sel.values:
            await respond(interaction, content="اختار قالب من القائمة الأول.", ephemeral=True)
            return
        await run_db(template_delete_sync, interaction.guild.id, sel.values[0])
        await respond(interaction, content="🗑️ اتحذف القالب. افتح 📂 قالب تاني لتحديث القايمة.", ephemeral=True)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.state.show(interaction)


class BuilderView(ManagerView):
    def __init__(self, state: BuilderState):
        super().__init__(timeout=900)
        self.state = state

    @discord.ui.button(label="المعلومات الأساسية", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def basic(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InfoModal(self.state.target(), self.state.show, with_duration=True))

    @discord.ui.button(label="نوع الجائزة", emoji="🎁", style=discord.ButtonStyle.primary, row=0)
    async def prize(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = PrizeView(self.state.target(), self.state.show)
        await edit_ui(interaction, embeds=[v.embed()], view=v)

    @discord.ui.button(label="الشروط", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def reqs(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = RequirementsView(self.state.target(), self.state.show)
        await edit_ui(interaction, embeds=[v.embed()], view=v)

    @discord.ui.button(label="مدخلات إضافية", emoji="⭐", style=discord.ButtonStyle.primary, row=0)
    async def bonus(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = BonusView(self.state.target(), self.state.show)
        await edit_ui(interaction, embeds=[v.embed()], view=v)

    @discord.ui.button(label="المظهر", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def look(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppearanceModal(self.state.target(), self.state.show, self.state.st))

    @discord.ui.button(label="الروم", emoji="📢", style=discord.ButtonStyle.secondary, row=1)
    async def channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_ui(interaction, embeds=[discord.Embed(title="📢 روم النشر", description="اختار الروم اللي هتنشر فيه السحب:", color=COLOR_DARK)], view=ChannelPickView(self.state))

    @discord.ui.button(label="خيارات", emoji="⚙️", style=discord.ButtonStyle.secondary, row=1)
    async def options(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = OptionsView(self.state)
        await edit_ui(interaction, embeds=[v.embed()], view=v)

    @discord.ui.button(label="حفظ كقالب", emoji="💾", style=discord.ButtonStyle.secondary, row=1)
    async def save_tpl(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TemplateSaveModal(self.state))

    @discord.ui.button(label="قالب", emoji="📂", style=discord.ButtonStyle.secondary, row=1)
    async def load_tpl(self, interaction: discord.Interaction, button: discord.ui.Button):
        templates = await run_db(templates_list_sync, interaction.guild.id)
        if not templates:
            await respond(interaction, embed=err_embed("مفيش قوالب محفوظة لسه. جهّز سحب واضغط 💾 حفظ كقالب."), ephemeral=True)
            return
        await edit_ui(interaction, embeds=[discord.Embed(title="📂 القوالب", description="اختار قالب عشان يتحمّل في المسودة:", color=COLOR_DARK)], view=TemplatePickView(self.state, templates))

    @discord.ui.button(label="إطلاق السحب", emoji="🚀", style=discord.ButtonStyle.success, row=2)
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.state.cog.launch_giveaway(interaction, self.state)

    @discord.ui.button(label="إلغاء", emoji="❌", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_ui(interaction, content="❌ اتلغى إنشاء السحب.", embeds=[], view=None)


# ==============================================================================
# 🛠️ إدارة السحوبات (قائمة، لوحة إدارة، مشاركين)
# ==============================================================================
class TimeModal(SafeModal):
    def __init__(self, cog, gw_id: str, after: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(title="⏱️ تعديل وقت السحب")
        self.cog, self.gw_id, self.after = cog, gw_id, after
        self.box = discord.ui.TextInput(label="المدة", placeholder="+30m تمديد | -10m تقليل | 2h = من دلوقتي", max_length=20, required=True)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        ok, msg = await self.cog.adjust_time(self.gw_id, self.box.value)
        if not ok:
            await respond(interaction, embed=err_embed(msg), ephemeral=True)
            return
        await self.after(interaction)


class RerollModal(SafeModal, title="🔄 إعادة سحب (Reroll)"):
    def __init__(self, cog, gw_id: Optional[str] = None):
        super().__init__()
        self.cog, self.gw_id = cog, gw_id
        if gw_id is None:
            self.id_box = discord.ui.TextInput(label="رقم السحب (ID)", placeholder="الرقم اللي في تذييل رسالة السحب", max_length=12)
            self.add_item(self.id_box)
        self.count = discord.ui.TextInput(label="عدد الفايزين الجدد", default="1", max_length=2)
        self.add_item(self.count)

    async def on_submit(self, interaction: discord.Interaction):
        gw_id = self.gw_id or self.id_box.value.strip()
        try:
            n = int(self.count.value.strip())
            if not 1 <= n <= MAX_WINNERS:
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed(f"العدد لازم من 1 لـ {MAX_WINNERS}."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.cog.reroll_giveaway(gw_id, n, interaction.user, interaction.guild.id)
        await interaction.followup.send(embed=ok_embed("🔄 تم", msg) if ok else err_embed(msg), ephemeral=True)


class ParticipantsView(ManagerView):
    PER = 10

    def __init__(self, cog, gw_id: str, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(timeout=300)
        self.cog, self.gw_id, self.back_cb, self.page = cog, gw_id, back, 0
        self.total = 0

    async def build(self, guild: discord.Guild) -> discord.Embed:
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        self.total = int((gw or {}).get("entries_count", 0))
        rows = await run_db(entries_page_sync, self.gw_id, self.page * self.PER, self.PER)
        lines = [f"`{self.page * self.PER + i}.` <@{r['user_id']}>" + (f" ⟵ **x{r.get('weight', 1)}**" if r.get("weight", 1) > 1 else "") for i, r in enumerate(rows, 1)]
        pages = max(1, (self.total + self.PER - 1) // self.PER)
        self.prev_btn.disabled, self.next_btn.disabled = self.page <= 0, self.page + 1 >= pages
        return discord.Embed(title=f"👥 المشاركين — السحب #{self.gw_id}", description="\n".join(lines) or "مفيش مشاركين لسه.", color=COLOR_DARK).set_footer(text=f"صفحة {self.page + 1}/{pages} • الإجمالي {self.total}")

    async def render(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=await self.build(interaction.guild), view=self)

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.primary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self.render(interaction)

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.primary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.render(interaction)

    @discord.ui.button(label="تصدير", emoji="📥", style=discord.ButtonStyle.success, row=0)
    async def export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        entries = await run_db(entries_all_sync, self.gw_id)
        lines = []
        for uid, w in entries:
            m = interaction.guild.get_member(uid)
            lines.append(f"{uid} | {m.name if m else '(غير موجود)'} | x{w}")
        file = discord.File(io.BytesIO("\n".join(lines).encode("utf-8")), filename=f"participants-{self.gw_id}.txt")
        await interaction.followup.send(content=f"📥 المشاركين ({len(entries)})", file=file, ephemeral=True)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_cb(interaction)


class ManageView(ManagerView):
    def __init__(self, cog, gw: dict):
        super().__init__(timeout=600)
        self.cog, self.gw_id, self.status = cog, gw["_id"], gw["status"]
        live = gw["status"] in LIVE
        self.pause_btn.label = "استئناف" if gw["status"] == STATUS_PAUSED else "إيقاف مؤقت"
        self.pause_btn.emoji = "▶️" if gw["status"] == STATUS_PAUSED else "⏸️"
        for b in (self.pause_btn, self.time_btn, self.info_btn, self.prize_btn, self.req_btn, self.bonus_btn, self.end_btn):
            b.disabled = not live
        self.reroll_btn.disabled = gw["status"] != STATUS_ENDED
        self.cancel_btn.label = "إلغاء السحب" if live else "حذف السجل"

    async def render(self, interaction: discord.Interaction):
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        if gw is None:
            await edit_ui(interaction, content="السحب ده اتحذف.", embeds=[], view=None)
            return
        st = await self.cog.get_settings(gw["guild_id"])
        head = discord.Embed(description=f"{STATUS_ICON.get(gw['status'], '⚪')} **الحالة:** {STATUS_NAME.get(gw['status'], gw['status'])} ┊ 🔗 [رسالة السحب]({self.cog.jump_url(gw)})", color=COLOR_BLUE)
        await edit_ui(interaction, content=None, embeds=[head, build_giveaway_embed(gw, interaction.guild, st)], view=ManageView(self.cog, gw))

    def _target(self, gw: dict) -> ConfigTarget:
        async def persist():
            await self.cog.save_gw_cfg(self.gw_id, gw)
        return ConfigTarget(gw, persist)

    @discord.ui.button(label="إيقاف مؤقت", emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.toggle_pause(self.gw_id)
        await self.render(interaction)

    @discord.ui.button(label="تعديل الوقت", emoji="⏱️", style=discord.ButtonStyle.primary, row=0)
    async def time_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeModal(self.cog, self.gw_id, self._after))

    async def _after(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.render(interaction)

    @discord.ui.button(label="تعديل المعلومات", emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        await interaction.response.send_modal(InfoModal(self._target(gw), self._after, with_duration=False))

    @discord.ui.button(label="الجائزة", emoji="🎁", style=discord.ButtonStyle.primary, row=0)
    async def prize_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        v = PrizeView(self._target(gw), self.render)
        await edit_ui(interaction, content=None, embeds=[v.embed()], view=v)

    @discord.ui.button(label="الشروط", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def req_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        v = RequirementsView(self._target(gw), self.render)
        await edit_ui(interaction, content=None, embeds=[v.embed()], view=v)

    @discord.ui.button(label="مدخلات إضافية", emoji="⭐", style=discord.ButtonStyle.primary, row=1)
    async def bonus_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        v = BonusView(self._target(gw), self.render)
        await edit_ui(interaction, content=None, embeds=[v.embed()], view=v)

    @discord.ui.button(label="المشاركين", emoji="👥", style=discord.ButtonStyle.secondary, row=1)
    async def people_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = ParticipantsView(self.cog, self.gw_id, self.render)
        await interaction.response.defer()
        await interaction.edit_original_response(content=None, embeds=[await v.build(interaction.guild)], view=v)

    @discord.ui.button(label="إعادة سحب", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def reroll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RerollModal(self.cog, self.gw_id))

    @discord.ui.button(label="إنهاء الآن", emoji="🔚", style=discord.ButtonStyle.success, row=1)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.end_giveaway(self.gw_id, interaction.user)
        await self.render(interaction)

    @discord.ui.button(label="تحديث الرسالة", emoji="🔃", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        gw = await self.cog.get_gw(self.gw_id, fresh=True)
        if gw:
            await self.cog.refresh_message(gw)
        await self.render(interaction)

    @discord.ui.button(label="إلغاء السحب", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        live = self.status in LIVE

        async def do(i: discord.Interaction):
            if live:
                await self.cog.cancel_giveaway(self.gw_id, i.user)
            else:
                await self.cog.delete_record(self.gw_id, i.user)
            await i.followup.send(embed=ok_embed("✅ تم", "اتنفذ الإجراء."), ephemeral=True)

        text = "هتلغي السحب ومش هيتسحب فايزين." if live else "هتحذف سجل السحب والمشاركات نهائياً."
        await respond(interaction, embed=err_embed(f"{text} متأكد؟", "⚠️ تأكيد"), view=ConfirmView(interaction.user.id, do, "أيوه، نفّذ"), ephemeral=True)

    @discord.ui.button(label="للقائمة", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await GiveawayListView.show(self.cog, interaction, "live")


class GiveawayListView(ManagerView):
    FILTERS = {"live": ("النشطة والمتوقفة", [STATUS_ACTIVE, STATUS_PAUSED]), "ended": ("المنتهية", [STATUS_ENDED]),
               "cancelled": ("الملغية", [STATUS_CANCELLED]), "all": ("الكل", None)}

    def __init__(self, cog, gws: list, current: str):
        super().__init__(timeout=300)
        self.cog = cog
        f = discord.ui.Select(placeholder="🔎 فلتر الحالة", row=0, options=[discord.SelectOption(label=v[0], value=k, default=(k == current)) for k, v in self.FILTERS.items()])

        async def fcb(i: discord.Interaction):
            await i.response.defer()
            await GiveawayListView.show(cog, i, f.values[0])

        f.callback = fcb
        self.add_item(f)
        if gws:
            s = discord.ui.Select(placeholder="📋 اختر سحب لإدارته", row=1, options=[
                discord.SelectOption(label=clip(g["prize"], 90) or "—", description=f"#{g['_id']} • {STATUS_NAME.get(g['status'], g['status'])} • {g.get('entries_count', 0)} مشارك",
                                     value=g["_id"], emoji=STATUS_ICON.get(g["status"], "⚪")) for g in gws[:25]])

            async def scb(i: discord.Interaction):
                await i.response.defer()
                gw = await cog.get_gw(s.values[0], fresh=True)
                if gw:
                    await ManageView(cog, gw).render(i)

            s.callback = scb
            self.add_item(s)

    @classmethod
    async def show(cls, cog, interaction: discord.Interaction, key: str):
        gws = await run_db(gw_list_sync, interaction.guild.id, cls.FILTERS[key][1], 25)
        desc = (f"📋 **{cls.FILTERS[key][0]}** — آخر `{len(gws)}` سحب. اختار واحد لإدارته." if gws else f"مفيش سحوبات في فلتر **{cls.FILTERS[key][0]}**.")
        await edit_ui(interaction, content=None, embeds=[discord.Embed(title="📋 إدارة السحوبات", description=desc, color=COLOR_DARK)], view=cls(cog, gws, key))


# ==============================================================================
# ⚙️ الإعدادات والقائمة السوداء والقوالب والإحصائيات
# ==============================================================================
class DefaultsModal(SafeModal):
    def __init__(self, view: "SettingsView", kind: str):
        super().__init__(title="🎨 المظهر الافتراضي" if kind == "look" else "🛡️ الافتراضيات")
        self.view, self.kind, st = view, kind, view.st
        if kind == "look":
            self.a = discord.ui.TextInput(label="العنوان الافتراضي", default=st["default_title"], max_length=100)
            self.b = discord.ui.TextInput(label="اللون Hex", default=st["default_color"], max_length=7)
            self.c = discord.ui.TextInput(label="نص زرار الانضمام", default=st["default_button_label"], max_length=40)
            self.d = discord.ui.TextInput(label="إيموجي الزرار", default=st["default_button_emoji"], max_length=60, required=False)
            self.e = discord.ui.TextInput(label="نص التذييل", default=st["footer_text"], max_length=80, required=False)
            items = (self.a, self.b, self.c, self.d, self.e)
        else:
            self.a = discord.ui.TextInput(label="أدنى عمر حساب افتراضي (أيام)", default=str(st["default_min_account_days"]), max_length=4)
            self.b = discord.ui.TextInput(label="أدنى مدة عضوية افتراضية (أيام)", default=str(st["default_min_member_days"]), max_length=4)
            self.c = discord.ui.TextInput(label="شكل رسالة النتيجة (embed / text)", default=st["end_style"], max_length=10)
            items = (self.a, self.b, self.c)
        for i in items:
            self.add_item(i)

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        if self.kind == "look":
            if not _HEX_RE.match(self.b.value.strip()):
                await respond(interaction, embed=err_embed("اللون لازم Hex من 6 خانات."), ephemeral=True)
                return
            fields = {"default_title": self.a.value.strip() or DEFAULT_SETTINGS["default_title"], "default_color": self.b.value.strip().lstrip("#").upper(),
                      "default_button_label": self.c.value.strip() or DEFAULT_SETTINGS["default_button_label"],
                      "default_button_emoji": self.d.value.strip() or "", "footer_text": self.e.value.strip()}
        else:
            try:
                a, b = int(self.a.value.strip()), int(self.b.value.strip())
                if not (0 <= a <= 5000 and 0 <= b <= 5000):
                    raise ValueError
            except ValueError:
                await respond(interaction, embed=err_embed("اكتب أرقام صحيحة من 0 لـ 5000."), ephemeral=True)
                return
            fields = {"default_min_account_days": a, "default_min_member_days": b, "end_style": "text" if "text" in self.c.value.lower() or "نص" in self.c.value else "embed"}
        await self.view.cog.update_settings(gid, **fields)
        await self.view.render(interaction)


class SettingsView(ManagerView):
    def __init__(self, cog, st: dict):
        super().__init__(timeout=600)
        self.cog, self.st = cog, st
        for btn, key in ((self.dm_btn, "dm_winners"), (self.count_btn, "show_count"), (self.leave_btn, "allow_leave")):
            btn.style = discord.ButtonStyle.success if st[key] else discord.ButtonStyle.secondary

    async def render(self, interaction: discord.Interaction):
        st = await self.cog.get_settings(interaction.guild.id, force=True)
        await edit_ui(interaction, content=None, embeds=[settings_summary_embed(interaction.guild, st)], view=SettingsView(self.cog, st))

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📊 روم السجلات (امسح الاختيار للإيقاف)", channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=0, max_values=1, row=0)
    async def log_chan(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await self.cog.update_settings(interaction.guild.id, log_channel_id=select.values[0].id if select.values else None)
        await self.render(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="👮 رتب مديري الجيف أواي (امسح الاختيار للإزالة)", min_values=0, max_values=5, row=1)
    async def managers(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await self.cog.update_settings(interaction.guild.id, manager_role_ids=[r.id for r in select.values if not r.is_default()])
        await self.render(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="📣 رتبة التنبيه الافتراضية (اختياري)", min_values=0, max_values=1, row=2)
    async def ping(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await self.cog.update_settings(interaction.guild.id, ping_role_id=select.values[0].id if select.values else None)
        await self.render(interaction)

    async def _toggle(self, interaction: discord.Interaction, key: str):
        await self.cog.update_settings(interaction.guild.id, **{key: not self.st[key]})
        await self.render(interaction)

    @discord.ui.button(label="خاص للفايزين", emoji="✉️", row=3)
    async def dm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, "dm_winners")

    @discord.ui.button(label="عدد المشاركين", emoji="👥", row=3)
    async def count_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, "show_count")

    @discord.ui.button(label="الانسحاب", emoji="🚪", row=3)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, "allow_leave")

    @discord.ui.button(label="المظهر", emoji="🎨", style=discord.ButtonStyle.primary, row=3)
    async def look_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DefaultsModal(self, "look"))

    @discord.ui.button(label="الافتراضيات", emoji="🛡️", style=discord.ButtonStyle.primary, row=3)
    async def defaults_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DefaultsModal(self, "defaults"))


def blacklist_embed(st: dict) -> discord.Embed:
    users = " ".join(f"<@{u}>" for u in st["blacklist_users"][:30]) or "—"
    roles = roles_text(st["blacklist_roles"])
    return discord.Embed(
        title="🚫 القائمة السوداء",
        description=(f"👤 **الأعضاء المحظورين ({len(st['blacklist_users'])}):** {users}\n🎭 **الرتب المحظورة ({len(st['blacklist_roles'])}):** {roles}\n\n"
                     "اختار أعضاء أو رتب من القوائم تحت: **اللي مش محظور بيتحظر، واللي محظور بيتشال حظره** (Toggle)."),
        color=COLOR_RED)


class BlacklistView(ManagerView):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def _toggle(self, interaction: discord.Interaction, key: str, ids: list[int]):
        st = await self.cog.get_settings(interaction.guild.id, force=True)
        cur = list(st[key])
        for i in ids:
            cur.remove(i) if i in cur else cur.append(i)
        await self.cog.update_settings(interaction.guild.id, **{key: cur})
        st = await self.cog.get_settings(interaction.guild.id, force=True)
        await interaction.response.edit_message(embed=blacklist_embed(st), view=BlacklistView(self.cog))
        await self.cog.log_event(interaction.guild, "🚫 تعديل القائمة السوداء", f"بواسطة {interaction.user.mention}", COLOR_RED)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="👤 تبديل حظر أعضاء", min_values=1, max_values=10, row=0)
    async def users(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await self._toggle(interaction, "blacklist_users", [u.id for u in select.values if not u.bot])

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🎭 تبديل حظر رتب", min_values=1, max_values=10, row=1)
    async def roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await self._toggle(interaction, "blacklist_roles", [r.id for r in select.values if not r.is_default()])

    @discord.ui.button(label="مسح الأعضاء", emoji="🧹", style=discord.ButtonStyle.danger, row=2)
    async def clear_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_settings(interaction.guild.id, blacklist_users=[])
        await interaction.response.edit_message(embed=blacklist_embed(await self.cog.get_settings(interaction.guild.id, force=True)), view=BlacklistView(self.cog))

    @discord.ui.button(label="مسح الرتب", emoji="🧹", style=discord.ButtonStyle.danger, row=2)
    async def clear_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_settings(interaction.guild.id, blacklist_roles=[])
        await interaction.response.edit_message(embed=blacklist_embed(await self.cog.get_settings(interaction.guild.id, force=True)), view=BlacklistView(self.cog))


class TemplatesAdminView(ManagerView):
    def __init__(self, templates: list):
        super().__init__(timeout=300)
        select = discord.ui.Select(placeholder="🗑️ اختر قالب لحذفه", options=[discord.SelectOption(label=clip(t["name"], 100), value=t["name"], emoji="📄") for t in templates[:25]])

        async def cb(i: discord.Interaction):
            await run_db(template_delete_sync, i.guild.id, select.values[0])
            await i.response.edit_message(embed=ok_embed("🗑️ تم الحذف", f"اتحذف القالب **{select.values[0]}**."), view=None)

        select.callback = cb
        self.add_item(select)


class DashboardSelect(discord.ui.Select):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(placeholder="اختر الإجراء المطلوب إدارته من القائمة...", min_values=1, max_values=1, options=[
            discord.SelectOption(label="إطلاق جيف أواي جديد", description="لوحة إنشاء كاملة بمعاينة حية", emoji="🎉", value="start"),
            discord.SelectOption(label="إدارة السحوبات", description="تعديل/إيقاف/إنهاء/مشاركين أي سحب", emoji="📋", value="manage"),
            discord.SelectOption(label="إعادة سحب (Reroll)", description="اختيار فايزين جدد لسحب منتهي", emoji="🔄", value="reroll"),
            discord.SelectOption(label="إدارة القائمة السوداء", description="حظر أو إزالة أعضاء ورتب", emoji="🚫", value="blacklist"),
            discord.SelectOption(label="الإعدادات العامة", description="السجلات، المديرين، المظهر والافتراضيات", emoji="⚙️", value="settings"),
            discord.SelectOption(label="القوالب", description="عرض وحذف القوالب المحفوظة", emoji="📂", value="templates"),
            discord.SelectOption(label="الإحصائيات", description="أرقام وإحصائيات الجيف أواي", emoji="📊", value="stats"),
        ])

    async def callback(self, interaction: discord.Interaction):
        val, cog, guild = self.values[0], self.cog, interaction.guild
        if val == "reroll":
            await interaction.response.send_modal(RerollModal(cog))
            return
        await interaction.response.defer(ephemeral=True)
        st = await cog.get_settings(guild.id)
        if val == "start":
            state = BuilderState(cog, guild, interaction.user.id, st, interaction.channel_id)
            await interaction.followup.send(embeds=state.embeds(), view=BuilderView(state), ephemeral=True)
        elif val == "manage":
            gws = await run_db(gw_list_sync, guild.id, [STATUS_ACTIVE, STATUS_PAUSED], 25)
            desc = f"📋 **النشطة والمتوقفة** — آخر `{len(gws)}` سحب. اختار واحد لإدارته." if gws else "مفيش سحوبات شغالة حالياً."
            await interaction.followup.send(embed=discord.Embed(title="📋 إدارة السحوبات", description=desc, color=COLOR_DARK), view=GiveawayListView(cog, gws, "live"), ephemeral=True)
        elif val == "blacklist":
            await interaction.followup.send(embed=blacklist_embed(st), view=BlacklistView(cog), ephemeral=True)
        elif val == "settings":
            await interaction.followup.send(embed=settings_summary_embed(guild, st), view=SettingsView(cog, st), ephemeral=True)
        elif val == "templates":
            templates = await run_db(templates_list_sync, guild.id)
            if not templates:
                await interaction.followup.send(embed=err_embed("مفيش قوالب محفوظة. تقدر تحفظ قالب من لوحة الإنشاء."), ephemeral=True)
            else:
                await interaction.followup.send(embed=discord.Embed(title="📂 القوالب المحفوظة", description="\n".join(f"• **{t['name']}** — {clip(t['data'].get('prize'), 40)}" for t in templates), color=COLOR_DARK), view=TemplatesAdminView(templates), ephemeral=True)
        elif val == "stats":
            s = await run_db(stats_sync, guild.id)
            bs = s["by_status"]
            e = discord.Embed(title="📊 إحصائيات الجيف أواي", color=COLOR_BLUE, description=(
                f"🎉 **إجمالي السحوبات:** `{s['total']}`\n🟢 شغالة: `{bs.get(STATUS_ACTIVE, 0)}` ┊ 🟠 متوقفة: `{bs.get(STATUS_PAUSED, 0)}`\n"
                f"🔴 منتهية: `{bs.get(STATUS_ENDED, 0)}` ┊ ⚫ ملغية: `{bs.get(STATUS_CANCELLED, 0)}`\n👥 **إجمالي المشاركات:** `{s['entries']}`"))
            await interaction.followup.send(embed=e, ephemeral=True)


class GiveawayDashboardView(ManagerView):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.add_item(DashboardSelect(cog))


# ==============================================================================
# 🌟 الـ Cog الرئيسي
# ==============================================================================
class ZiuoGiveawayDashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings_cache: dict[int, tuple[float, dict]] = {}
        self.gw_cache: dict[str, tuple[float, dict]] = {}
        self.msg_map: dict[int, str] = {}
        self.active_msgs: set[int] = set()
        self.dirty: set[str] = set()
        self.end_failures: dict[str, int] = {}

    async def cog_load(self):
        await run_db(ensure_indexes_sync)
        migrated = await run_db(migrate_legacy_json_sync)
        if migrated:
            log.info("تم ترحيل %d سحب من الملف القديم", migrated)
        await run_db(gw_recover_sync)
        self.active_msgs = set(await run_db(gw_live_messages_sync))
        self.bot.add_view(GiveawayEntryView())
        self.end_loop.start()
        self.counts_loop.start()
        self.grants_loop.start()

    async def cog_unload(self):
        self.end_loop.cancel()
        self.counts_loop.cancel()
        self.grants_loop.cancel()

    # ---------- كاش ----------
    async def get_settings(self, gid: int, force: bool = False) -> dict:
        hit = self.settings_cache.get(gid)
        if hit and not force and time.monotonic() - hit[0] < 60:
            return hit[1]
        st = await run_db(settings_get_sync, gid)
        self.settings_cache[gid] = (time.monotonic(), st)
        return st

    async def update_settings(self, gid: int, **fields):
        await run_db(settings_set_sync, gid, fields)
        self.settings_cache.pop(gid, None)

    async def get_gw(self, gw_id: str, fresh: bool = False) -> Optional[dict]:
        hit = self.gw_cache.get(gw_id)
        if hit and not fresh and time.monotonic() - hit[0] < 10:
            return hit[1]
        gw = await run_db(gw_get_sync, gw_id)
        if gw:
            self.gw_cache[gw_id] = (time.monotonic(), gw)
            if gw.get("message_id"):
                self.msg_map[gw["message_id"]] = gw_id
        return gw

    async def get_gw_by_message(self, mid: int) -> Optional[dict]:
        gw_id = self.msg_map.get(mid)
        if gw_id:
            return await self.get_gw(gw_id)
        gw = await run_db(gw_by_message_sync, mid)
        if gw:
            self.msg_map[mid] = gw["_id"]
            self.gw_cache[gw["_id"]] = (time.monotonic(), gw)
        return gw

    def invalidate(self, gw_id: str):
        self.gw_cache.pop(gw_id, None)

    def jump_url(self, gw: dict) -> str:
        return f"https://discord.com/channels/{gw['guild_id']}/{gw['channel_id']}/{gw.get('message_id') or 0}"

    async def log_event(self, guild: discord.Guild, title: str, desc: str, color: int = COLOR_BLUE):
        st = await self.get_settings(guild.id)
        chan = guild.get_channel(st["log_channel_id"]) if st["log_channel_id"] else None
        if isinstance(chan, discord.abc.Messageable) and chan.permissions_for(guild.me).send_messages:
            try:
                await chan.send(embed=discord.Embed(title=title, description=clip(desc, 4000), color=color, timestamp=discord.utils.utcnow()),
                                allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.warning("فشل إرسال سجل الجيف أواي", exc_info=True)

    # ---------- تحديث رسالة السحب ----------
    def entry_view_for(self, gw: dict, st: dict) -> Optional[discord.ui.View]:
        if gw["status"] not in LIVE:
            return None
        style = gw.get("style") or {}
        count = gw.get("entries_count", 0) if (gw.get("opts") or {}).get("show_count", True) else None
        return GiveawayEntryView(style.get("button_label") or st["default_button_label"], style.get("button_emoji") or st["default_button_emoji"],
                                 count, disabled=gw["status"] == STATUS_PAUSED)

    async def refresh_message(self, gw: dict):
        guild = self.bot.get_guild(gw["guild_id"])
        chan = guild.get_channel_or_thread(gw["channel_id"]) if guild else None
        if chan is None or not gw.get("message_id"):
            return
        st = await self.get_settings(gw["guild_id"])
        try:
            await chan.get_partial_message(gw["message_id"]).edit(embed=build_giveaway_embed(gw, guild, st), view=self.entry_view_for(gw, st))
        except discord.NotFound:
            pass
        except discord.HTTPException:
            log.warning("فشل تحديث رسالة السحب %s", gw["_id"], exc_info=True)

    async def save_gw_cfg(self, gw_id: str, cfg: dict) -> Optional[dict]:
        keys = ("prize", "description", "winners_count", "image_url", "prize_type", "prize_role_id", "prize_role_days", "req", "bonus", "style", "opts")
        gw = await run_db(gw_update_sync, gw_id, {k: cfg[k] for k in keys if k in cfg}, None, list(LIVE))
        self.invalidate(gw_id)
        if gw:
            await self.refresh_message(gw)
        return gw

    # ---------- الانضمام ----------
    async def handle_join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gw = await self.get_gw_by_message(interaction.message.id)
        if gw is None or gw["status"] != STATUS_ACTIVE:
            await interaction.followup.send(embed=err_embed("السحب ده انتهى أو متوقف حالياً."), ephemeral=True)
            return
        st = await self.get_settings(gw["guild_id"])
        member = interaction.user
        fails = check_member(member, gw, st)
        if fails:
            await interaction.followup.send(embed=err_embed("\n".join(fails), "⛔ مش مؤهل للمشاركة"), ephemeral=True)
            return
        weight = compute_weight(member, gw)
        added, count = await run_db(entry_add_sync, gw["_id"], gw["guild_id"], member.id, weight)
        if not added:
            if (gw.get("opts") or {}).get("allow_leave", True):
                await interaction.followup.send(embed=discord.Embed(title="✅ أنت مشارك بالفعل", description="عايز تنسحب من السحب؟", color=COLOR_BLUE), view=LeaveView(self, gw["_id"]), ephemeral=True)
            else:
                await interaction.followup.send(embed=ok_embed("✅ أنت مشارك بالفعل", "بالتوفيق 🍀"), ephemeral=True)
            return
        self.dirty.add(gw["_id"])
        extra = f"\n⭐ عندك **{weight}** مدخل (فرصة أعلى)!" if weight > 1 else ""
        await interaction.followup.send(embed=ok_embed("📥 تم تسجيل مشاركتك", f"بالتوفيق في **{clip(gw['prize'], 80)}** 🎉{extra}"), ephemeral=True)

    async def handle_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gw = await self.get_gw_by_message(interaction.message.id)
        if gw is None:
            await interaction.followup.send(embed=err_embed("السحب ده مش مسجل."), ephemeral=True)
            return
        st = await self.get_settings(gw["guild_id"])
        fails = check_member(interaction.user, gw, st)
        lines = requirement_lines(gw.get("req") or {}) or ["✅ مفيش شروط، الكل يقدر يشارك"]
        e = discord.Embed(title="ℹ️ شروط السحب", description="\n".join(lines), color=COLOR_BLUE)
        w = compute_weight(interaction.user, gw)
        e.add_field(name="حالتك", value=("✅ مؤهل للمشاركة" + (f" (x{w} مدخل)" if w > 1 else "")) if not fails else "\n".join(fails), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- الإطلاق ----------
    async def launch_giveaway(self, interaction: discord.Interaction, state: BuilderState):
        errors = state.validate()
        if errors:
            await respond(interaction, embed=err_embed("\n".join(errors), "⚠️ كمّل الإعداد الأول"), ephemeral=True)
            return
        await interaction.response.defer()
        guild, d = interaction.guild, state.draft
        chan = guild.get_channel_or_thread(d["channel_id"])
        gw = None
        for _ in range(6):
            gw = draft_to_gw(d, interaction.user.id, guild.id, str(random.randint(100000, 999999)))
            try:
                await run_db(gw_insert_sync, gw)
                break
            except DuplicateKeyError:
                gw = None
        if gw is None:
            await interaction.followup.send(embed=err_embed("معرفتش أنشئ رقم سحب، حاول تاني."), ephemeral=True)
            return
        st = state.st
        ping, mentions = None, discord.AllowedMentions.none()
        if d["ping_everyone"]:
            ping, mentions = "@everyone", discord.AllowedMentions(everyone=True)
        elif d["ping_role_id"]:
            role = guild.get_role(d["ping_role_id"])
            if role:
                ping, mentions = role.mention, discord.AllowedMentions(roles=[role])
        try:
            msg = await chan.send(content=ping, embed=build_giveaway_embed(gw, guild, st), view=self.entry_view_for(gw, st), allowed_mentions=mentions)
        except discord.HTTPException as e:
            await run_db(gw_delete_sync, gw["_id"])
            await interaction.followup.send(embed=err_embed(f"فشل نشر السحب: {e}"), ephemeral=True)
            return
        gw = await run_db(gw_update_sync, gw["_id"], {"message_id": msg.id}) or gw
        self.active_msgs.add(msg.id)
        self.msg_map[msg.id] = gw["_id"]
        self.gw_cache[gw["_id"]] = (time.monotonic(), gw)
        await interaction.edit_original_response(content=None, embeds=[ok_embed("✅ تم إطلاق الجيف أواي", f"السحب نزل في {chan.mention} برقم مرجعي `{gw['_id']}`\n🔗 [رسالة السحب]({msg.jump_url})\nتقدر تديره من `/giveaway` ← إدارة السحوبات.")], view=None)
        await self.log_event(guild, "🎉 سحب جديد", f"**{gw['prize']}** — `{gw['_id']}`\nبواسطة {interaction.user.mention} في {chan.mention}", COLOR_GREEN)

    # ---------- الإنهاء والـ Reroll ----------
    async def draw_winners(self, guild: discord.Guild, gw: dict, count: int, exclude: set) -> list[int]:
        st = await self.get_settings(guild.id)
        entries = await run_db(entries_all_sync, gw["_id"])
        weighted = [(uid, compute_weight(m, gw) if (m := guild.get_member(uid)) else w) for uid, w in entries]
        winners, budget = [], 150
        for uid in weighted_order(weighted, exclude):
            if len(winners) >= count:
                break
            m = guild.get_member(uid)
            if m is None:
                if budget <= 0:
                    continue
                budget -= 1
                try:
                    m = await guild.fetch_member(uid)
                except discord.HTTPException:
                    continue
            if m.bot or check_member(m, gw, st):
                continue
            winners.append(uid)
        return winners

    async def grant_roles(self, guild: discord.Guild, gw: dict, winners: list[int]) -> tuple[int, int]:
        role = guild.get_role(gw.get("prize_role_id") or 0)
        ok = fail = 0
        if role is None or role_problem(guild, role):
            return 0, len(winners)
        days = int(gw.get("prize_role_days") or 0)
        for uid in winners:
            m = guild.get_member(uid)
            if m is None:
                try:
                    m = await guild.fetch_member(uid)
                except discord.HTTPException:
                    fail += 1
                    continue
            try:
                if role not in m.roles:
                    await m.add_roles(role, reason=f"Giveaway {gw['_id']} prize")
                if days:
                    await run_db(grant_add_sync, guild.id, uid, role.id, now() + days * 86400, gw["_id"])
                ok += 1
            except discord.HTTPException:
                fail += 1
        return ok, fail

    async def announce_result(self, guild: discord.Guild, gw: dict, winners: list[int], reroll: bool):
        st = await self.get_settings(guild.id)
        granted = await self.grant_roles(guild, gw, winners) if (gw.get("prize_type") == "role" and winners) else None
        chan = guild.get_channel_or_thread(gw["channel_id"])
        url = self.jump_url(gw) if gw.get("message_id") else None
        if chan is not None and chan.permissions_for(guild.me).send_messages:
            ref = discord.MessageReference(message_id=gw["message_id"], channel_id=gw["channel_id"], fail_if_not_exists=False) if gw.get("message_id") else None
            mentions = " ".join(f"<@{u}>" for u in winners)
            try:
                if st["end_style"] == "text":
                    head = "🔄 **إعادة سحب**" if reroll else "🎊 **انتهى السحب**"
                    text = f"{head} — 🎁 **{gw['prize']}**\n👑 " + (mentions or "مفيش فايزين")
                    await chan.send(content=text, reference=ref, allowed_mentions=discord.AllowedMentions(users=True))
                else:
                    await chan.send(content=mentions or None, embed=build_result_embed(gw, winners, reroll, url, granted), reference=ref, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                log.warning("فشل إعلان نتيجة السحب", exc_info=True)
        if winners and (gw.get("opts") or {}).get("dm_winners", True):
            for uid in winners:
                m = guild.get_member(uid)
                if m:
                    try:
                        await m.send(embed=discord.Embed(title="🎉 مبروك! فزت!", color=COLOR_GREEN, description=f"فزت بـ **{gw['prize']}** في سيرفر **{guild.name}**" + (f"\n🔗 [رسالة السحب]({url})" if url else "") +
                                                             ("\n🎭 الرتبة اتمنحت ليك أوتوماتيك." if gw.get("prize_type") == "role" else "\nكلم الإدارة لاستلام جائزتك.")))
                    except discord.HTTPException:
                        pass
        await self.log_event(guild, "🔄 إعادة سحب" if reroll else "🏁 انتهى سحب", f"**{gw['prize']}** — `{gw['_id']}`\n👑 " + (" ".join(f"<@{u}>" for u in winners) or "مفيش فايزين"), COLOR_ORANGE)

    async def end_giveaway(self, gw_id: str, by: Optional[discord.abc.User] = None) -> Optional[dict]:
        old = await run_db(gw_claim_end_sync, gw_id)
        if old is None:
            return None
        try:
            guild = self.bot.get_guild(old["guild_id"])
            winners = await self.draw_winners(guild, old, int(old["winners_count"]), set(old.get("winners", []))) if guild else []
            gw = await run_db(gw_update_sync, gw_id, {"status": STATUS_ENDED, "winners": winners, "ended_at": now()}) or old
            self.invalidate(gw_id)
            self.end_failures.pop(gw_id, None)
            if gw.get("message_id"):
                self.active_msgs.discard(gw["message_id"])
            if guild:
                await self.refresh_message(gw)
                await self.announce_result(guild, gw, winners, reroll=False)
            return gw
        except Exception:
            log.exception("فشل إنهاء السحب %s", gw_id)
            n = self.end_failures[gw_id] = self.end_failures.get(gw_id, 0) + 1
            await run_db(gw_update_sync, gw_id, {"status": STATUS_ACTIVE} if n < 3 else {"status": STATUS_ENDED, "winners": [], "ended_at": now()})
            self.invalidate(gw_id)
            return None

    async def reroll_giveaway(self, gw_id: str, count: int, by: discord.abc.User, guild_id: int) -> tuple[bool, str]:
        gw = await self.get_gw(gw_id, fresh=True)
        if gw is None or gw["guild_id"] != guild_id:
            return False, "رقم السحب غير صحيح."
        if gw["status"] != STATUS_ENDED:
            return False, "الـ Reroll بيشتغل على السحوبات المنتهية بس."
        guild = self.bot.get_guild(guild_id)
        winners = await self.draw_winners(guild, gw, count, set(gw.get("winners", [])))
        if not winners:
            return False, "مفيش مشاركين مؤهلين تانيين لإعادة السحب."
        gw = await run_db(gw_update_sync, gw_id, {"winners": list(gw.get("winners", [])) + winners}) or gw
        self.invalidate(gw_id)
        await self.refresh_message(gw)
        await self.announce_result(guild, gw, winners, reroll=True)
        return True, f"اتسحب `{len(winners)}` فايز جديد: " + " ".join(f"<@{u}>" for u in winners)

    async def cancel_giveaway(self, gw_id: str, by: discord.abc.User):
        gw = await run_db(gw_update_sync, gw_id, {"status": STATUS_CANCELLED, "ended_at": now()}, None, list(LIVE))
        self.invalidate(gw_id)
        if gw:
            self.active_msgs.discard(gw.get("message_id"))
            await self.refresh_message(gw)
            guild = self.bot.get_guild(gw["guild_id"])
            if guild:
                await self.log_event(guild, "🚫 إلغاء سحب", f"**{gw['prize']}** — `{gw_id}`\nبواسطة {by.mention}", COLOR_RED)

    async def delete_record(self, gw_id: str, by: discord.abc.User):
        gw = await self.get_gw(gw_id, fresh=True)
        await run_db(gw_delete_sync, gw_id)
        self.invalidate(gw_id)
        if gw and gw.get("message_id"):
            self.active_msgs.discard(gw["message_id"])
            guild = self.bot.get_guild(gw["guild_id"])
            chan = guild.get_channel_or_thread(gw["channel_id"]) if guild else None
            if chan:
                try:
                    await chan.get_partial_message(gw["message_id"]).delete()
                except discord.HTTPException:
                    pass

    async def toggle_pause(self, gw_id: str):
        gw = await self.get_gw(gw_id, fresh=True)
        if gw is None:
            return
        if gw["status"] == STATUS_ACTIVE:
            new = await run_db(gw_update_sync, gw_id, {"status": STATUS_PAUSED, "paused_remaining": max(0, gw["ends_at"] - now())}, None, [STATUS_ACTIVE])
        elif gw["status"] == STATUS_PAUSED:
            new = await run_db(gw_update_sync, gw_id, {"status": STATUS_ACTIVE, "ends_at": now() + int(gw.get("paused_remaining") or 60)}, ["paused_remaining"], [STATUS_PAUSED])
        else:
            return
        self.invalidate(gw_id)
        if new:
            await self.refresh_message(new)

    async def adjust_time(self, gw_id: str, text: str) -> tuple[bool, str]:
        gw = await self.get_gw(gw_id, fresh=True)
        if gw is None or gw["status"] not in LIVE:
            return False, "السحب مش شغال."
        text = text.strip()
        sign = text[:1] if text[:1] in "+-" else ""
        secs = parse_duration(text.lstrip("+-"))
        if secs is None:
            return False, "صيغة غير صالحة. أمثلة: `+30m` تمديد، `-10m` تقليل، `2h` من دلوقتي."
        paused = gw["status"] == STATUS_PAUSED
        base = int(gw.get("paused_remaining") or 0) if paused else gw["ends_at"] - now()
        new_remaining = base + secs if sign == "+" else base - secs if sign == "-" else secs
        if new_remaining < MIN_DURATION or new_remaining > MAX_DURATION:
            return False, "الوقت الجديد لازم يكون بين 30 ثانية و 90 يوم من دلوقتي."
        fields = {"paused_remaining": new_remaining} if paused else {"ends_at": now() + new_remaining}
        new = await run_db(gw_update_sync, gw_id, fields, None, list(LIVE))
        self.invalidate(gw_id)
        if new:
            await self.refresh_message(new)
        return True, "تم."

    # ---------- مهام دورية ----------
    @tasks.loop(seconds=15)
    async def end_loop(self):
        try:
            for gw_id in await run_db(gw_due_sync, now()):
                await self.end_giveaway(gw_id)
        except Exception:
            log.exception("خطأ في مهمة إنهاء السحوبات")

    @tasks.loop(seconds=10)
    async def counts_loop(self):
        ids, self.dirty = list(self.dirty), set()
        for gw_id in ids:
            try:
                gw = await self.get_gw(gw_id, fresh=True)
                if gw and gw["status"] in LIVE:
                    await self.refresh_message(gw)
                    await asyncio.sleep(0.5)
            except Exception:
                log.exception("خطأ في تحديث عدّاد السحب %s", gw_id)

    @tasks.loop(minutes=1)
    async def grants_loop(self):
        try:
            for g in await run_db(grants_due_sync, now()):
                guild = self.bot.get_guild(g["guild_id"])
                role = guild.get_role(g["role_id"]) if guild else None
                member = guild.get_member(g["user_id"]) if guild else None
                if role and member and role in member.roles:
                    try:
                        await member.remove_roles(role, reason=f"Giveaway {g.get('gw_id')} prize expired")
                    except discord.HTTPException:
                        log.warning("تعذر سحب الرتبة المنتهية", exc_info=True)
                await run_db(grant_delete_sync, g["_id"])
        except Exception:
            log.exception("خطأ في مهمة سحب الرتب المنتهية")

    @end_loop.before_loop
    @counts_loop.before_loop
    @grants_loop.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id in self.active_msgs:  # حد مسح رسالة سحب شغال: نلغيه أوتوماتيك
            self.active_msgs.discard(payload.message_id)
            gw = await run_db(gw_by_message_sync, payload.message_id)
            if gw and gw["status"] in LIVE:
                await run_db(gw_update_sync, gw["_id"], {"status": STATUS_CANCELLED, "ended_at": now()})
                self.invalidate(gw["_id"])
                guild = self.bot.get_guild(gw["guild_id"])
                if guild:
                    await self.log_event(guild, "🚫 سحب اتلغى", f"رسالة السحب **{gw['prize']}** (`{gw['_id']}`) اتمسحت فاتلغى السحب أوتوماتيك.", COLOR_RED)

    # ---------- الأوامر ----------
    async def _manager_check(self, interaction: discord.Interaction) -> bool:
        st = await self.get_settings(interaction.guild.id)
        if is_manager(interaction.user, st):
            return True
        await respond(interaction, embed=err_embed("الأمر ده للمشرفين فقط."), ephemeral=True)
        return False

    @app_commands.command(name="giveaway", description="[لوحة التحكم الشاملة] إدارة جميع سحوبات السيرفر من قائمة واحدة تفاعلية")
    @app_commands.guild_only()
    async def giveaway_dashboard(self, interaction: discord.Interaction):
        if not await self._manager_check(interaction):
            return
        embed = discord.Embed(
            title="⚙️ **لـوحـة تـحـكـم الـجـيـف أواي الإمـبـراطـوريـة**",
            description=(f"مرحباً بك يا {interaction.user.mention} في لوحة التحكم المركزية للسحوبات والجوائز.\n\n"
                         "🎉 جوائز نصية أو **رتب بتتوزع أوتوماتيك**، وشروط، ومدخلات إضافية، وإدارة كاملة.\n\n"
                         "👇 **اختر الإجراء المناسب من القائمة المنسدلة بالأسفل للتحكم الفوري:**"),
            color=COLOR_DARK, timestamp=discord.utils.utcnow())
        embed.set_footer(text=f"Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.send_message(embed=embed, view=GiveawayDashboardView(self), ephemeral=True)

    async def _gw_choices(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        rows = await run_db(gw_search_sync, interaction.guild.id, current.strip(), 25)
        return [app_commands.Choice(name=clip(f"#{r['_id']} • {r['prize']} ({STATUS_NAME.get(r['status'], r['status'])})", 100), value=r["_id"]) for r in rows]

    @app_commands.command(name="gend", description="[الإدارة] إنهاء سحب شغال الآن واختيار الفايزين")
    @app_commands.guild_only()
    @app_commands.describe(giveaway_id="رقم السحب")
    async def gend(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self._manager_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gw = await self.get_gw(giveaway_id, fresh=True)
        if gw is None or gw["guild_id"] != interaction.guild.id:
            await interaction.followup.send(embed=err_embed("رقم السحب غير صحيح."), ephemeral=True)
            return
        res = await self.end_giveaway(giveaway_id, interaction.user)
        await interaction.followup.send(embed=ok_embed("🔚 تم", "السحب انتهى واتعلنت النتيجة.") if res else err_embed("السحب مش شغال أو بيتنهي حالياً."), ephemeral=True)

    @gend.autocomplete("giveaway_id")
    async def gend_ac(self, interaction: discord.Interaction, current: str):
        return await self._gw_choices(interaction, current)

    @app_commands.command(name="greroll", description="[الإدارة] إعادة سحب فايزين جدد لسحب منتهي")
    @app_commands.guild_only()
    @app_commands.describe(giveaway_id="رقم السحب", count="عدد الفايزين الجدد")
    async def greroll(self, interaction: discord.Interaction, giveaway_id: str, count: app_commands.Range[int, 1, MAX_WINNERS] = 1):
        if not await self._manager_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.reroll_giveaway(giveaway_id, count, interaction.user, interaction.guild.id)
        await interaction.followup.send(embed=ok_embed("🔄 تم", msg) if ok else err_embed(msg), ephemeral=True)

    @greroll.autocomplete("giveaway_id")
    async def greroll_ac(self, interaction: discord.Interaction, current: str):
        return await self._gw_choices(interaction, current)

    @app_commands.command(name="gcancel", description="[الإدارة] إلغاء سحب شغال (من غير فايزين)")
    @app_commands.guild_only()
    @app_commands.describe(giveaway_id="رقم السحب")
    async def gcancel(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self._manager_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gw = await self.get_gw(giveaway_id, fresh=True)
        if gw is None or gw["guild_id"] != interaction.guild.id or gw["status"] not in LIVE:
            await interaction.followup.send(embed=err_embed("السحب مش موجود أو مش شغال."), ephemeral=True)
            return
        await self.cancel_giveaway(giveaway_id, interaction.user)
        await interaction.followup.send(embed=ok_embed("🚫 تم الإلغاء", f"اتلغى السحب `{giveaway_id}`."), ephemeral=True)

    @gcancel.autocomplete("giveaway_id")
    async def gcancel_ac(self, interaction: discord.Interaction, current: str):
        return await self._gw_choices(interaction, current)

    @app_commands.command(name="glist", description="[الإدارة] عرض وإدارة سحوبات السيرفر")
    @app_commands.guild_only()
    async def glist(self, interaction: discord.Interaction):
        if not await self._manager_check(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gws = await run_db(gw_list_sync, interaction.guild.id, [STATUS_ACTIVE, STATUS_PAUSED], 25)
        desc = f"📋 **النشطة والمتوقفة** — آخر `{len(gws)}` سحب. اختار واحد لإدارته." if gws else "مفيش سحوبات شغالة حالياً."
        await interaction.followup.send(embed=discord.Embed(title="📋 إدارة السحوبات", description=desc, color=COLOR_DARK), view=GiveawayListView(self, gws, "live"), ephemeral=True)

    @app_commands.command(name="gblacklist", description="[الإدارة] حظر/إزالة حظر عضو من الجيف أواي أو عرض القائمة")
    @app_commands.guild_only()
    @app_commands.describe(action="الإجراء", member="العضو (مطلوب للحظر والإزالة)")
    @app_commands.choices(action=[app_commands.Choice(name="حظر", value="add"), app_commands.Choice(name="إزالة الحظر", value="remove"), app_commands.Choice(name="عرض القائمة", value="list")])
    async def gblacklist(self, interaction: discord.Interaction, action: app_commands.Choice[str], member: Optional[discord.Member] = None):
        if not await self._manager_check(interaction):
            return
        st = await self.get_settings(interaction.guild.id, force=True)
        if action.value == "list":
            await respond(interaction, embed=blacklist_embed(st), ephemeral=True)
            return
        if member is None:
            await respond(interaction, embed=err_embed("اختار العضو."), ephemeral=True)
            return
        users = list(st["blacklist_users"])
        if action.value == "add" and member.id not in users:
            users.append(member.id)
        elif action.value == "remove" and member.id in users:
            users.remove(member.id)
        await self.update_settings(interaction.guild.id, blacklist_users=users)
        await respond(interaction, embed=ok_embed("✅ تم", f"{'اتحظر' if action.value == 'add' else 'اتشال حظر'} {member.mention}."), ephemeral=True)
        await self.log_event(interaction.guild, "🚫 تعديل القائمة السوداء", f"{interaction.user.mention} {'حظر' if action.value == 'add' else 'أزال حظر'} {member.mention}", COLOR_RED)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        log.exception("خطأ في أمر سلاش", exc_info=error)
        await report_error(interaction)


# ==============================================================================
# 📦 ترحيل بيانات الملف القديم (JSON)
# ==============================================================================
def migrate_legacy_json_sync() -> int:
    if not os.path.exists(LEGACY_JSON) or meta_col.find_one({"_id": "json_migrated"}):
        return 0
    try:
        with open(LEGACY_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        log.warning("تعذر قراءة ملف الجيف أواي القديم", exc_info=True)
        return 0
    count = 0
    for guild_id, g in data.items():
        try:
            gid = int(guild_id)
        except ValueError:
            continue
        st: dict[str, Any] = {}
        users = [int(x) for x in g.get("blacklist", []) if str(x).isdigit()]
        if users:
            st["blacklist_users"] = users
        log_ch = (g.get("logs") or {}).get("channel_id")
        if log_ch:
            st["log_channel_id"] = int(log_ch)
        days = (g.get("settings") or {}).get("min_account_days")
        if days:
            st["default_min_account_days"] = int(days)
        if st:
            settings_col.update_one({"guild_id": gid}, {"$set": st}, upsert=True)
        for gw_id, gw in (g.get("giveaways") or {}).items():
            try:
                ends = calendar.timegm(datetime.datetime.strptime(gw["ends_at"], "%Y-%m-%d %H:%M:%S").timetuple())
                parts = [int(p) for p in gw.get("participants", []) if str(p).isdigit()]
                st_default = copy.deepcopy(DEFAULT_SETTINGS)
                doc = {"_id": str(gw_id), "guild_id": gid, "channel_id": int(gw["channel_id"]), "message_id": int(gw["message_id"]), "host_id": 0,
                       "prize": str(gw["prize"]), "description": "", "winners_count": int(gw.get("winners_count", 1)), "image_url": None,
                       "prize_type": "custom", "prize_role_id": None, "prize_role_days": 0,
                       "req": {**default_req(st_default), "min_account_days": int(gw.get("min_account_days", 0))}, "bonus": {},
                       "style": {"title": None, "color": None, "button_label": None, "button_emoji": None, "footer": None},
                       "opts": {"dm_winners": True, "show_count": True, "allow_leave": True},
                       "status": STATUS_ACTIVE if gw.get("active") else STATUS_ENDED, "created_at": ends - 3600, "ends_at": ends,
                       "ended_at": None if gw.get("active") else ends, "winners": [], "entries_count": len(set(parts)), "ping_role_id": None}
                gw_col.insert_one(doc)
                for uid in set(parts):
                    try:
                        entries_col.insert_one({"gw_id": str(gw_id), "guild_id": gid, "user_id": uid, "weight": 1, "joined_at": now()})
                    except DuplicateKeyError:
                        pass
                count += 1
            except (DuplicateKeyError, KeyError, ValueError):
                continue
    meta_col.insert_one({"_id": "json_migrated", "at": now()})
    try:
        os.replace(LEGACY_JSON, LEGACY_JSON + ".migrated")
    except OSError:
        pass
    return count


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير موجود في ملف .env، نظام الجيف أواي محتاج قاعدة بيانات.")
    await bot.add_cog(ZiuoGiveawayDashboardCog(bot))
