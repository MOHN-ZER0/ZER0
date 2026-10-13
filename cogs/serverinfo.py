"""
📇 نظام معلومات السيرفر (نسخة مصلّحة، مؤمنة، ومحسّنة بالكامل)
"""
import asyncio
import copy
import datetime
import logging
import os
import re
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
log = logging.getLogger("serverinfo")

# تعيين التوقيت بأمان تام لتفادي أي انهيار على ويندوز أو لينكس
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(os.getenv("SERVERINFO_TZ", "Africa/Cairo"))
except Exception:
    LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=2))

# ==============================================================================
# ⚙️ الثوابت والإعدادات الافتراضية
# ==============================================================================
COLOR_DARK = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_ORANGE = 0xFFA500

PAGE_ORDER = ["overview", "members", "channels", "roles", "emojis", "boost", "features"]
PAGE_META = {
    "overview": ("نظرة عامة", "📇"),
    "members": ("الأعضاء والنمو", "👥"),
    "channels": ("الرومات والقنوات", "💬"),
    "roles": ("الرتب", "🎭"),
    "emojis": ("الإيموجي والملصقات", "😀"),
    "boost": ("البوست والحماية", "🚀"),
    "features": ("ميزات السيرفر", "✨"),
}
OPTIONAL_PAGES = PAGE_ORDER[1:]
BOOST_GOALS = {0: 2, 1: 7, 2: 14}
COMMAND_COOLDOWN = 5

DEFAULTS: dict[str, Any] = {
    "pages": list(OPTIONAL_PAGES),
    "color": "2B2D31",
    "title": "📇 ╎ مـعـلـومـات سـيـرفـر {server} 〣 ｢🛡️｣",
    "footer": "{server} ✦ Enhanced Server Dashboard",
    "banner_url": None,
    "ephemeral": False,
    "track_growth": True,
    "show_presence": True,
    "shortcuts_enabled": True,
    "shortcuts": ["serverinfo"],
    "peak_members": 0,
    "peak_at": 0,
}

VERIFICATION_AR = {
    "none": "ضعيفة (بدون قيود)",
    "low": "منخفضة (تحتاج بريد إلكتروني)",
    "medium": "متوسطة (مسجل لأكثر من 5 دقائق)",
    "high": "عالية (عضو بالسيرفر لأكثر من 10 دقائق)",
    "highest": "عالية جداً (تحتاج هاتف موثق)",
}
FILTER_AR = {"disabled": "معطل", "no_role": "للأعضاء بدون رتب", "all_members": "لكل الأعضاء"}
NOTIF_AR = {"all_messages": "كل الرسائل", "only_mentions": "المنشنات فقط"}
MFA_AR = {"disabled": "غير مطلوب", "require_2fa": "مطلوب للإدارة"}
NSFW_AR = {"default": "افتراضي", "explicit": "صريح", "safe": "آمن", "age_restricted": "محدد بالعمر"}
FEATURES_AR = {
    "COMMUNITY": "مجتمع", "PARTNERED": "شريك", "VERIFIED": "موثّق", "DISCOVERABLE": "قابل للاكتشاف",
    "VANITY_URL": "رابط مخصص", "ANIMATED_ICON": "أيقونة متحركة", "BANNER": "بنر", "ANIMATED_BANNER": "بنر متحرك",
    "INVITE_SPLASH": "خلفية الدعوة", "NEWS": "قنوات إعلانات", "WELCOME_SCREEN_ENABLED": "شاشة الترحيب",
    "MEMBER_VERIFICATION_GATE_ENABLED": "فحص الانضمام", "PREVIEW_ENABLED": "معاينة السيرفر",
    "ROLE_ICONS": "أيقونات الرتب", "PRIVATE_THREADS": "ثريدات خاصة", "THREADS_ENABLED": "ثريدات",
    "MORE_STICKERS": "ملصقات إضافية", "AUTO_MODERATION": "الإشراف التلقائي", "SOUNDBOARD": "لوحة الأصوات",
    "TICKETED_EVENTS_ENABLED": "فعاليات بتذاكر", "MONETIZATION_ENABLED": "التحقيق من الدخل",
}


# ==============================================================================
# 🧰 دوال مساعدة آمنة
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


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def parse_color(value: Any, default: int = COLOR_DARK) -> int:
    m = _HEX_RE.match(str(value or "").strip())
    return int(m.group(1), 16) if m else default


def local_now() -> datetime.datetime:
    return datetime.datetime.now(LOCAL_TZ)


def kv(label: str, value: Any) -> str:
    return f"> **{label}:** ｢ {value} ｣"


def ts(dt: Optional[datetime.datetime], style: str = "R") -> str:
    if not dt:
        return "غير معروف"
    return f"<t:{int(dt.timestamp())}:{style}>"


def format_age(delta: datetime.timedelta) -> str:
    days = max(0, delta.days)
    years, rem = divmod(days, 365)
    months, d = divmod(rem, 30)
    parts = []
    if years:
        parts.append(f"{years} سنة")
    if months:
        parts.append(f"{months} شهر")
    if d or not parts:
        parts.append(f"{d} يوم")
    return "، ".join(parts)


def progress(current: int, total: int, width: int = 10) -> str:
    ratio = 1.0 if total <= 0 else max(0.0, min(1.0, current / total))
    filled = int(ratio * width)
    return "▰" * filled + "▱" * (width - filled)


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[int]) -> str:
    if not values:
        return SPARK[0] * 7
    top = max(values) if values else 0
    if top <= 0:
        return SPARK[0] * len(values)
    return "".join(SPARK[round(v / top * 7)] for v in values)


def fmt_template(text: str, guild: discord.Guild) -> str:
    return (text.replace("{server}", guild.name)
            .replace("{members}", str(guild.member_count or len(guild.members)))
            .replace("{id}", str(guild.id)))


def enum_name(value: Any) -> str:
    return getattr(value, "name", str(value))


async def respond(interaction: discord.Interaction, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        return await interaction.response.send_message(**kwargs)
    except Exception:
        pass


# ==============================================================================
# 💾 نظام التخزين السحابي الآمن (MongoDB)
# ==============================================================================
class ServerInfoStore:
    def __init__(self):
        self.cache: dict[int, dict] = {}
        self.mem_growth: dict[tuple[int, str], dict] = {}
        self.failed_until: dict[int, float] = {}
        self.col = None
        self.growth_col = None
        uri = os.getenv("MONGODB_URI", "").strip()
        if uri:
            try:
                db = MongoClient(uri, serverSelectionTimeoutMS=5000)["Global_Bot_DB"]
                self.col = db["serverinfo_settings"]
                self.growth_col = db["serverinfo_growth"]
            except Exception:
                log.exception("فشل الاتصال بـ MongoDB")
        else:
            log.warning("MONGODB_URI غير موجود! إعدادات معلومات السيرفر وإحصائيات النمو ستعتمد على الذاكرة المؤقتة.")

    async def init(self):
        if self.col is None:
            return
        for col, keys in ((self.col, [("guild_id", 1)]), (self.growth_col, [("guild_id", 1), ("date", 1)])):
            try:
                await asyncio.to_thread(col.create_index, keys, unique=True)
            except Exception:
                pass

    async def get(self, gid: int) -> dict:
        cfg = self.cache.get(gid)
        if cfg is not None:
            return cfg
        if time.monotonic() < self.failed_until.get(gid, 0):
            return copy.deepcopy(DEFAULTS)
        doc = None
        if self.col is not None:
            try:
                doc = await asyncio.to_thread(self.col.find_one, {"guild_id": gid})
            except Exception:
                self.failed_until[gid] = time.monotonic() + 60
                return copy.deepcopy(DEFAULTS)
        cfg = copy.deepcopy(DEFAULTS)
        if doc:
            for k in DEFAULTS:
                if k in doc:
                    cfg[k] = doc[k]
        self.cache[gid] = cfg
        return cfg

    async def update(self, gid: int, **fields):
        cfg = await self.get(gid)
        cfg.update(fields)
        self.cache[gid] = cfg
        if self.col is not None:
            try:
                await asyncio.to_thread(self.col.update_one, {"guild_id": gid}, {"$set": fields}, True)
            except Exception:
                pass

    async def reset(self, gid: int):
        old = self.cache.get(gid) or {}
        self.cache[gid] = copy.deepcopy(DEFAULTS)
        self.cache[gid]["peak_members"] = old.get("peak_members", 0)
        self.cache[gid]["peak_at"] = old.get("peak_at", 0)
        if self.col is not None:
            try:
                await asyncio.to_thread(self.col.delete_one, {"guild_id": gid})
                await asyncio.to_thread(self.col.update_one, {"guild_id": gid},
                                        {"$set": {"peak_members": self.cache[gid]["peak_members"], "peak_at": self.cache[gid]["peak_at"]}}, True)
            except Exception:
                pass

    async def record_growth(self, gid: int, joins: int, leaves: int, members: int):
        date = local_now().date().isoformat()
        if self.growth_col is None:
            row = self.mem_growth.setdefault((gid, date), {"joins": 0, "leaves": 0})
            row["joins"] += joins
            row["leaves"] += leaves
            return
        try:
            await asyncio.to_thread(
                self.growth_col.update_one, {"guild_id": gid, "date": date},
                {"$inc": {"joins": joins, "leaves": leaves}, "$set": {"members": members}}, True)
        except Exception:
            pass

    async def growth(self, gid: int, days: int = 7) -> list[tuple[str, int, int]]:
        today = local_now().date()
        dates = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        rows: dict[str, tuple[int, int]] = {}
        if self.growth_col is not None:
            try:
                docs = await asyncio.to_thread(lambda: list(self.growth_col.find({"guild_id": gid, "date": {"$gte": dates[0]}})))
                for d in docs:
                    rows[d["date"]] = (int(d.get("joins", 0)), int(d.get("leaves", 0)))
            except Exception:
                pass
        else:
            for d in dates:
                r = self.mem_growth.get((gid, d))
                if r:
                    rows[d] = (r["joins"], r["leaves"])
        return [(d, *rows.get(d, (0, 0))) for d in dates]


STORE = ServerInfoStore()


async def update_peak(guild: discord.Guild, cfg: dict, total: int):
    if total > cfg.get("peak_members", 0):
        await STORE.update(guild.id, peak_members=total, peak_at=int(time.time()))


# ==============================================================================
# 📄 بناء صفحات المعلومات بأمان تام
# ==============================================================================
def member_counts(guild: discord.Guild) -> tuple[int, int, int, bool]:
    total = guild.member_count or len(guild.members)
    bots = sum(1 for m in guild.members if m.bot)
    complete = len(guild.members) >= total * 0.95 if total > 0 else True
    return total, max(0, total - bots), bots, complete


def base_embed(guild: discord.Guild, cfg: dict, page: str) -> discord.Embed:
    if page == "overview":
        title = fmt_template(cfg["title"], guild)
    else:
        name, emoji = PAGE_META.get(page, ("معلومات", "📇"))
        title = f"{emoji} ╎ {name} — {guild.name}"
    embed = discord.Embed(title=clip(title, 256), color=parse_color(cfg["color"]), timestamp=discord.utils.utcnow())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=clip(fmt_template(cfg["footer"], guild), 2048), icon_url=guild.icon.url if guild.icon else None)
    return embed


async def page_overview(bot, guild, cfg, embed):
    total, humans, bots, complete = member_counts(guild)
    await update_peak(guild, cfg, total)
    approx = "" if complete else " (تقريبي)"
    embed.description = (
        "> لوحة القيادة المركزية وإحصائيات السيرفر الرسمية والمحدثة بكافة التفاصيل والخصائص العميقـة ⚡.\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )
    banner = cfg["banner_url"] or (guild.banner.url if guild.banner else None)
    if banner:
        try:
            embed.set_image(url=banner)
        except Exception:
            pass

    age = discord.utils.utcnow() - guild.created_at if guild.created_at else datetime.timedelta(0)
    embed.add_field(
        name="📋 ╎ الـمـعـلـومـات الـأسـاسـيـة",
        value="\n".join([
            kv("الـمـالـك", f"<@{guild.owner_id}>"),
            kv("أيدي الـسـيـرفـر", f"`{guild.id}`"),
            kv("تـاريـخ الـتـأسـيـس", f"{ts(guild.created_at, 'D')}"),
            kv("عـمـر السيرفر", format_age(age)),
        ]),
        inline=False,
    )
    embed.add_field(
        name="👥 ╎ إحـصـائـيـات الـأعـضـاء",
        value="\n".join([
            kv("إجمالي الأعضاء", f"{total:,} 👤"),
            kv("البشر", f"{humans:,}{approx}") + " ✦ " + kv("البوتات", f"{bots:,}"),
        ]),
        inline=False,
    )
    channels_total = len(guild.channels) - len(guild.categories)
    embed.add_field(
        name="💬 ╎ تـفـاصـيـل الـرومـات والـقـنـوات",
        value=(
            f"> **الإجمالي:** ｢ {channels_total} ｣ ✦ **الفئات:** ｢ {len(guild.categories)} ｣\n"
            f"> **الكتابية:** ｢ {len(guild.text_channels)} 📝 ｣ ✦ **الصوتية:** ｢ {len(guild.voice_channels)} 🔊 ｣ "
            f"✦ **المنتدى:** ｢ {len(guild.forum_channels)} 📂 ｣"
        ),
        inline=False,
    )
    emojis = guild.emojis
    animated = sum(1 for e in emojis if e.animated)
    highest = next((r for r in reversed(guild.roles) if not r.managed and not r.is_default()), None)
    embed.add_field(
        name="🎭 ╎ الـرتـب والـإيـمـوجـيـات والـمـلـصـقـات",
        value=(
            f"> **عدد الرتب:** ｢ {max(0, len(guild.roles) - 1)} ｣ ✦ **أعلى رتبة:** {highest.mention if highest else 'لا يوجد'}\n"
            f"> **الإيموجيات:** ｢ {len(emojis)} ｣ (عادي: ｢ {len(emojis) - animated} ｣ ✦ متحرك: ｢ {animated} ｣)\n"
            f"> **الملصقات (Stickers):** ｢ {len(guild.stickers)} ｣"
        ),
        inline=False,
    )
    tier, boosts = guild.premium_tier, guild.premium_subscription_count or 0
    verification = VERIFICATION_AR.get(enum_name(guild.verification_level), "عادية")
    embed.add_field(
        name="🚀 ╎ الـبـوسـت والـحـمـايـة والـأمـان",
        value=(
            f"> **مستوى البوست (Tier):** ｢ المستوى {tier} ｣ ✦ **عدد البوستات:** ｢ {boosts} 💎 ｣\n"
            f"> **مستوى الحماية:** ｢ {verification} ｣\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        ),
        inline=False,
    )


async def page_members(bot, guild, cfg, embed):
    total, humans, bots, complete = member_counts(guild)
    await update_peak(guild, cfg, total)
    approx = "" if complete else " (تقريبي)"
    lines = [
        kv("الإجمالي", f"{total:,}"),
        kv("البشر", f"{humans:,}{approx}"),
        kv("البوتات", f"{bots:,}"),
    ]
    peak = cfg.get("peak_members", 0)
    if peak:
        when = f" ({ts(datetime.datetime.fromtimestamp(cfg['peak_at'], datetime.timezone.utc), 'D')})" if cfg.get("peak_at") else ""
        lines.append(kv("أعلى عدد أعضاء", f"{max(peak, total):,}{when}"))
    embed.add_field(name="👥 ╎ الـأعـضـاء", value="\n".join(lines), inline=False)

    if bot.intents.presences and cfg["show_presence"]:
        online = idle = dnd = 0
        for m in guild.members:
            if m.bot:
                continue
            s = enum_name(m.status)
            online += s == "online"
            idle += s == "idle"
            dnd += s == "dnd"
        offline = max(0, humans - online - idle - dnd)
        embed.add_field(
            name="🟢 ╎ الـحـالـات (بشر فقط)",
            value=f"> 🟢 **أونلاين:** ｢ {online:,} ｣ ✦ 🌙 **خامل:** ｢ {idle:,} ｣\n> ⛔ **مشغول:** ｢ {dnd:,} ｣ ✦ ⚫ **أوفلاين:** ｢ {offline:,} ｣",
            inline=False,
        )

    dated = [m for m in guild.members if m.joined_at and not m.bot]
    if dated:
        newest = max(dated, key=lambda m: m.joined_at)
        embed.add_field(name="🆕 ╎ أحـدث عـضـو", value=f"> {newest.mention} ✦ {ts(newest.joined_at)}", inline=False)

    if cfg["track_growth"]:
        rows = await STORE.growth(guild.id, 7)
        joins, leaves = sum(r[1] for r in rows), sum(r[2] for r in rows)
        net = joins - leaves
        embed.add_field(
            name="📈 ╎ نـمـو الـسـيـرفـر (آخر 7 أيام)",
            value=(
                f"> 📥 **دخول:** ｢ {joins} ｣ ✦ 📤 **خروج:** ｢ {leaves} ｣ ✦ **الصافي:** ｢ {net:+d} ｣\n"
                f"> `{sparkline([r[1] for r in rows])}` ⟵ الدخول يومياً\n"
                f"> `{sparkline([r[2] for r in rows])}` ⟵ الخروج يومياً\n"
                "> _الإحصائية بتبدأ من وقت تفعيل التتبع، وبتحسب الأعضاء البشر فقط._"
            ),
            inline=False,
        )


async def page_channels(bot, guild, cfg, embed):
    news = sum(1 for c in guild.text_channels if c.is_news())
    embed.add_field(
        name="💬 ╎ الـقـنـوات",
        value="\n".join([
            kv("كتابية", f"{len(guild.text_channels) - news} 📝") + " ✦ " + kv("إعلانات", f"{news} 📢"),
            kv("صوتية", f"{len(guild.voice_channels)} 🔊") + " ✦ " + kv("مسرح", f"{len(guild.stage_channels)} 🎤"),
            kv("منتدى", f"{len(guild.forum_channels)} 📂") + " ✦ " + kv("الفئات", f"{len(guild.categories)} 📁"),
            kv("ثريدات نشطة", f"{len(guild.threads)} 🧵"),
        ]),
        inline=False,
    )
    special = []
    for label, ch in (("روم النظام", guild.system_channel), ("روم القواعد", guild.rules_channel), ("روم تحديثات ديسكورد", guild.public_updates_channel)):
        if ch:
            special.append(kv(label, ch.mention))
    if guild.afk_channel:
        special.append(kv("روم الـ AFK", f"{guild.afk_channel.mention} (بعد {guild.afk_timeout // 60} دقيقة)"))
    embed.add_field(name="📌 ╎ رومـات خـاصـة", value="\n".join(special) or "> لا يوجد", inline=False)
    largest = sorted(guild.categories, key=lambda c: len(c.channels), reverse=True)[:5]
    if largest:
        embed.add_field(name="📁 ╎ أكـبـر الـفـئـات", value="\n".join(f"> **{clip(c.name, 40)}** ｢ {len(c.channels)} ｣" for c in largest), inline=False)


async def page_roles(bot, guild, cfg, embed):
    roles = [r for r in guild.roles if not r.is_default()]
    admin_roles = sum(1 for r in roles if r.permissions.administrator and not r.managed)
    embed.add_field(
        name="🎭 ╎ الـرتـب",
        value="\n".join([
            kv("الإجمالي", len(roles)) + " ✦ " + kv("رتب البوتات/التكاملات", sum(1 for r in roles if r.managed)),
            kv("رتب بصلاحية Administrator", admin_roles) + " ✦ " + kv("قابلة للمنشن", sum(1 for r in roles if r.mentionable)),
        ]),
        inline=False,
    )
    top = [r for r in reversed(roles) if not r.managed][:10]
    if top:
        embed.add_field(
            name="🏆 ╎ أعـلـى الـرتـب",
            value=clip("\n".join(f"> {r.mention} ｢ {len(r.members)} عضو ｣" for r in top), 1024),
            inline=False,
        )


async def page_emojis(bot, guild, cfg, embed):
    emojis = guild.emojis
    animated = sum(1 for e in emojis if e.animated)
    static = len(emojis) - animated
    embed.add_field(
        name="😀 ╎ الإيـمـوجـيـات",
        value="\n".join([
            kv("العادي", f"{static} / {guild.emoji_limit}") + " ✦ " + kv("المتحرك", f"{animated} / {guild.emoji_limit}"),
            kv("الملصقات", f"{len(guild.stickers)} / {guild.sticker_limit}"),
        ]),
        inline=False,
    )
    if emojis:
        preview = " ".join(str(e) for e in emojis[:25])
        embed.add_field(name="🖼️ ╎ مـعـاينـة", value=clip(preview, 1024), inline=False)


async def page_boost(bot, guild, cfg, embed):
    tier, boosts = guild.premium_tier, guild.premium_subscription_count or 0
    goal = BOOST_GOALS.get(tier)
    if goal:
        goal_text = f"{progress(boosts, goal)} ｢ {boosts}/{goal} ｣ ⟵ متبقي {max(0, goal - boosts)} بوست للمستوى {tier + 1}"
    else:
        goal_text = "الحد الأقصى متاح 🚀"
    embed.add_field(
        name="🚀 ╎ الـبـوسـت",
        value="\n".join([
            kv("المستوى", tier) + " ✦ " + kv("البوستات", f"{boosts} 💎"),
            kv("عدد الداعمين", len(guild.premium_subscribers)),
            f"> {goal_text}",
        ]),
        inline=False,
    )
    embed.add_field(
        name="🎁 ╎ مـزايـا الـمـسـتـوى",
        value="\n".join([
            kv("حجم الرفع", f"{guild.filesize_limit / (1024 * 1024):.0f} MB"),
            kv("جودة الصوت", f"{guild.bitrate_limit / 1000:.0f} kbps"),
            kv("حد الإيموجي", guild.emoji_limit),
        ]),
        inline=False,
    )
    embed.add_field(
        name="🛡️ ╎ الـحـمـايـة والـأمـان",
        value="\n".join([
            kv("مستوى الحماية", VERIFICATION_AR.get(enum_name(guild.verification_level), "عادية")),
            kv("فلتر المحتوى", FILTER_AR.get(enum_name(guild.explicit_content_filter), "—")),
            kv("المصادقة الثنائية للإدارة", MFA_AR.get(enum_name(guild.mfa_level), "—")),
            kv("إشعارات افتراضية", NOTIF_AR.get(enum_name(guild.default_notifications), "—")),
            kv("تصنيف المحتوى", NSFW_AR.get(enum_name(guild.nsfw_level), "—")),
        ]),
        inline=False,
    )


async def page_features(bot, guild, cfg, embed):
    feats = sorted(guild.features)
    vanity = getattr(guild, "vanity_url_code", None)
    lines = []
    if vanity:
        lines.append(kv("الرابط المخصص", f"discord.gg/{vanity}"))
    lines.append(kv("اللغة المفضلة", enum_name(guild.preferred_locale)))
    if guild.description:
        lines.append(kv("الوصف", clip(guild.description, 200)))
    lines.append(kv("أقصى عدد أعضاء", f"{guild.max_members:,}" if guild.max_members else "—"))
    embed.add_field(name="🌐 ╎ مـعـلـومـات إضـافـيـة", value=clip("\n".join(lines), 1024), inline=False)
    if feats:
        shown = [f"`{FEATURES_AR.get(f, f.replace('_', ' ').title())}`" for f in feats[:30]]
        embed.add_field(name=f"✨ ╎ الـمـيـزات ({len(feats)})", value=clip(" ".join(shown), 1024), inline=False)
    else:
        embed.add_field(name="✨ ╎ الـمـيـزات", value="> سيرفر عادي بدون ميزات خاصة.", inline=False)


PAGE_BUILDERS = {
    "overview": page_overview, "members": page_members, "channels": page_channels,
    "roles": page_roles, "emojis": page_emojis, "boost": page_boost, "features": page_features,
}


async def build_page(bot: commands.Bot, guild: discord.Guild, cfg: dict, page: str) -> discord.Embed:
    if page not in PAGE_BUILDERS or (page != "overview" and page not in cfg["pages"]):
        page = "overview"
    embed = base_embed(guild, cfg, page)
    await PAGE_BUILDERS[page](bot, guild, cfg, embed)
    return embed


# ==============================================================================
# 🛡️ الأزرار والـ Views الآمنة
# ==============================================================================
class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في الواجهة", exc_info=error)
        await respond(interaction, content="❌ حدث خطأ أثناء تنفيذ هذا الزر.", ephemeral=True)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في النافذة", exc_info=error)
        await respond(interaction, content="❌ حدث خطأ أثناء حفظ النموذج.", ephemeral=True)


class AdminView(SafeView):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await respond(interaction, embed=err_embed("للمدراء فقط!"), ephemeral=True)
        return False


class PageSelect(discord.ui.Select):
    def __init__(self, cfg: dict, current: str):
        options = []
        for key in PAGE_ORDER:
            if key == "overview" or key in cfg["pages"]:
                name, emoji = PAGE_META[key]
                options.append(discord.SelectOption(label=name, value=key, emoji=emoji, default=(key == current)))
        super().__init__(placeholder="📂 اختر القسم اللي عاوز تشوفه", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "ServerInfoView" = self.view
        view.page = self.values[0]
        await view.refresh(interaction)


class ServerInfoView(SafeView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, cfg: dict, owner_id: int, page: str = "overview"):
        super().__init__(timeout=180)
        self.bot, self.guild, self.owner_id, self.page = bot, guild, owner_id, page
        self.message: Optional[discord.Message] = None
        self.rebuild(cfg)

    def rebuild(self, cfg: dict):
        self.clear_items()
        self.add_item(PageSelect(cfg, self.page))
        self.add_item(self.icon_btn)
        self.add_item(self.banner_btn)
        self.add_item(self.refresh_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await respond(interaction, content="🔒 اللوحة دي بتاعة اللي طلبها، اكتب `/serverinfo` وافتح لوحتك بنفسك.", ephemeral=True)
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
        cfg = await STORE.get(self.guild.id)
        return await build_page(self.bot, self.guild, cfg, self.page)

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cfg = await STORE.get(self.guild.id)
        embed = await build_page(self.bot, self.guild, cfg, self.page)
        self.rebuild(cfg)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="الأيقونة", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def icon_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        icon = self.guild.icon
        if icon is None:
            await respond(interaction, embed=err_embed("السيرفر ده معندوش أيقونة."), ephemeral=True)
            return
        embed = discord.Embed(title=f"🖼️ أيقونة {self.guild.name}", color=COLOR_DARK)
        embed.set_image(url=icon.with_size(1024).url)
        link = discord.ui.View()
        link.add_item(discord.ui.Button(label="فتح بالحجم الكامل", url=icon.url, emoji="🔗"))
        await respond(interaction, embed=embed, view=link, ephemeral=True)

    @discord.ui.button(label="البنر والخلفية", emoji="🏞️", style=discord.ButtonStyle.secondary, row=1)
    async def banner_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embeds, link = [], discord.ui.View()
        for label, asset in (("البنر", self.guild.banner), ("خلفية الدعوة", self.guild.splash)):
            if asset:
                e = discord.Embed(title=f"🏞️ {label} — {self.guild.name}", color=COLOR_DARK)
                e.set_image(url=asset.with_size(1024).url)
                embeds.append(e)
                link.add_item(discord.ui.Button(label=f"{label} بالحجم الكامل", url=asset.url, emoji="🔗"))
        if not embeds:
            await respond(interaction, embed=err_embed("السيرفر ده معندوش بنر أو خلفية دعوة."), ephemeral=True)
            return
        await respond(interaction, embeds=embeds, view=link, ephemeral=True)

    @discord.ui.button(label="تحديث", emoji="🔄", style=discord.ButtonStyle.primary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.refresh(interaction)


# ==============================================================================
# ⚙️ لوحة الإعدادات
# ==============================================================================
def build_settings_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    def on_off(v: bool) -> str:
        return "مفعل ✅" if v else "معطل ❌"

    pages = " ".join(f"{PAGE_META[p][1]}" for p in OPTIONAL_PAGES if p in cfg["pages"]) or "`الصفحة الأساسية فقط`"
    desc = (
        "> **لوحة التحكم في أمر `/serverinfo` وإعداداته.** ⚙️\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "### 📄 ┃ الأقسام الظاهرة\n"
        f"> {pages}\n\n"
        "### 🌐 ┃ الإعدادات\n"
        f"> * 🔒 **الرد خاص (يظهر لصاحب الأمر بس):** {on_off(cfg['ephemeral'])}\n"
        f"> * 📈 **تتبع نمو الأعضاء:** {on_off(cfg['track_growth'])}\n"
        f"> * 🟢 **حالات الأعضاء (أونلاين/خامل):** {on_off(cfg['show_presence'])}\n"
        f"> * ⌨️ **الاختصارات النصية:** {on_off(cfg['shortcuts_enabled'])} ┊ الكلمات: {' '.join(f'`{w}`' for w in cfg['shortcuts']) or '`لا يوجد`'}\n\n"
        "### 🎨 ┃ المظهر\n"
        f"> * **اللون:** `#{cfg['color']}`\n"
        f"> * **العنوان:** {clip(cfg['title'], 100)}\n"
        f"> * **التذييل:** {clip(cfg['footer'], 100)}\n"
        f"> * **صورة البنر:** {'مخصصة ✅' if cfg['banner_url'] else '`بنر السيرفر الأصلي`'}\n\n"
        "💡 تقدر تستخدم `{server}` و`{members}` و`{id}` في العنوان والتذييل.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
    embed = discord.Embed(title=f"⚙️ ‹ إعدادات معلومات السيرفر — {guild.name} ›", description=clip(desc, 4096), color=COLOR_DARK, timestamp=discord.utils.utcnow())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"{guild.name} ✦ ServerInfo Settings")
    return embed


async def show_settings(interaction: discord.Interaction, notice: Optional[str] = None):
    cfg = await STORE.get(interaction.guild.id)
    await interaction.response.edit_message(embed=build_settings_embed(interaction.guild, cfg), view=SettingsView(cfg))
    if notice:
        await interaction.followup.send(embed=ok_embed("✅ تم", notice), ephemeral=True)


class PagesSelect(discord.ui.Select):
    def __init__(self, cfg: dict):
        options = [
            discord.SelectOption(label=PAGE_META[p][0], value=p, emoji=PAGE_META[p][1], default=(p in cfg["pages"]))
            for p in OPTIONAL_PAGES
        ]
        super().__init__(placeholder="📄 اختر الأقسام اللي تظهر في القائمة", options=options, min_values=0, max_values=len(options), row=0)

    async def callback(self, interaction: discord.Interaction):
        await STORE.update(interaction.guild.id, pages=[p for p in OPTIONAL_PAGES if p in self.values])
        await show_settings(interaction)


class AppearanceModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🎨 مظهر لوحة المعلومات")
        self.color = discord.ui.TextInput(label="اللون (Hex مثل 2B2D31)", default=cfg["color"], max_length=7)
        self.title_box = discord.ui.TextInput(label="العنوان ({server} مدعوم)", default=clip(cfg["title"], 200), max_length=200)
        self.footer = discord.ui.TextInput(label="التذييل ({server} {members} مدعومين)", default=clip(cfg["footer"], 150), max_length=150)
        self.banner = discord.ui.TextInput(label="رابط صورة البنر (فاضي = بنر السيرفر)", default=cfg["banner_url"] or "", required=False, max_length=400)
        for box in (self.color, self.title_box, self.footer, self.banner):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        m = _HEX_RE.match(self.color.value.strip())
        if not m:
            await respond(interaction, embed=err_embed("اللون لازم يكون Hex من 6 أرقام/حروف، مثال: `2B2D31`."), ephemeral=True)
            return
        raw = self.banner.value.strip()
        if raw and not clean_url(raw):
            await respond(interaction, embed=err_embed("رابط الصورة لازم يبدأ بـ http أو https."), ephemeral=True)
            return
        await STORE.update(
            interaction.guild.id, color=m.group(1).upper(),
            title=self.title_box.value.strip() or DEFAULTS["title"],
            footer=self.footer.value.strip() or DEFAULTS["footer"],
            banner_url=raw or None,
        )
        await show_settings(interaction, "تم حفظ المظهر. جرّب 👁️ معاينة.")


class ShortcutsModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="⌨️ كلمات الاختصار")
        self.words = discord.ui.TextInput(
            label="الكلمات (كل كلمة في سطر أو بفاصلة)", style=discord.TextStyle.paragraph,
            default="\n".join(cfg["shortcuts"]), required=False, max_length=300)
        self.add_item(self.words)

    async def on_submit(self, interaction: discord.Interaction):
        words = []
        for w in re.split(r"[,\n،]", self.words.value):
            w = w.strip().lower()
            if w and len(w) <= 30 and w not in words:
                words.append(w)
        await STORE.update(interaction.guild.id, shortcuts=words[:5])
        await show_settings(interaction, "تم حفظ كلمات الاختصار (بحد أقصى 5).")


class ResetConfirmView(AdminView):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="تأكيد إعادة الضبط", style=discord.ButtonStyle.danger, emoji="♻️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await STORE.reset(interaction.guild.id)
        await show_settings(interaction, "تم إرجاع الإعدادات للوضع الافتراضي.")

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_settings(interaction)


class SettingsView(AdminView):
    TOGGLES = [
        ("ephemeral", "الرد خاص", "🔒"),
        ("track_growth", "تتبع النمو", "📈"),
        ("show_presence", "حالات الأعضاء", "🟢"),
        ("shortcuts_enabled", "الاختصارات", "⌨️"),
    ]

    def __init__(self, cfg: dict):
        super().__init__(timeout=600)
        self.add_item(PagesSelect(cfg))
        for key, label, emoji in self.TOGGLES:
            btn = discord.ui.Button(label=label, emoji=emoji, row=1,
                                    style=discord.ButtonStyle.success if cfg[key] else discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    @staticmethod
    def _make_cb(key: str):
        async def cb(interaction: discord.Interaction):
            cfg = await STORE.get(interaction.guild.id)
            await STORE.update(interaction.guild.id, **{key: not cfg[key]})
            await show_settings(interaction)
        return cb

    @discord.ui.button(label="المظهر", emoji="🎨", style=discord.ButtonStyle.blurple, row=2)
    async def btn_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppearanceModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="كلمات الاختصار", emoji="⌨️", style=discord.ButtonStyle.blurple, row=2)
    async def btn_shortcuts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ShortcutsModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="معاينة", emoji="👁️", style=discord.ButtonStyle.green, row=2)
    async def btn_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cfg = await STORE.get(interaction.guild.id)
        embed = await build_page(interaction.client, interaction.guild, cfg, "overview")
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            embed.set_image(url=None)
            await interaction.followup.send(content="⚠️ رابط البنر غير صالح، المعاينة من غير صورة.", embed=embed, ephemeral=True)

    @discord.ui.button(label="إعادة الضبط", emoji="♻️", style=discord.ButtonStyle.danger, row=2)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="♻️ إعادة ضبط الإعدادات", description="⚠️ هل أنت متأكد من إعادة الإعدادات للوضع الافتراضي؟", color=COLOR_ORANGE)
        await interaction.response.edit_message(embed=embed, view=ResetConfirmView())


# ==============================================================================
# 🌟 الـ Cog الرئيسي
# ==============================================================================
class ServerInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.shortcut_cd: dict[tuple[int, int], float] = {}

    async def cog_load(self):
        await STORE.init()

    async def open_panel(self, send, guild: discord.Guild, user_id: int, ephemeral: bool = False) -> None:
        try:
            cfg = await STORE.get(guild.id)
            view = ServerInfoView(self.bot, guild, cfg, user_id)
            embed = await view.build_embed()
            try:
                view.message = await send(embed=embed, view=view)
            except discord.HTTPException:
                embed.set_image(url=None)
                view.message = await send(embed=embed, view=view)
        except Exception as e:
            log.exception("خطأ أثناء فتح لوحة المعلومات", exc_info=e)

    @app_commands.command(name="serverinfo", description="[معلومات] لوحة معلومات وإحصائيات السيرفر الشاملة")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, COMMAND_COOLDOWN, key=lambda i: (i.guild_id, i.user.id))
    async def serverinfo(self, interaction: discord.Interaction):
        try:
            cfg = await STORE.get(interaction.guild.id)
            await interaction.response.defer(ephemeral=cfg["ephemeral"])

            async def send(**kwargs):
                return await interaction.followup.send(wait=True, **kwargs)

            await self.open_panel(send, interaction.guild, interaction.user.id)
        except Exception as e:
            log.exception("خطأ في أمر serverinfo", exc_info=e)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ حدث خطأ أثناء جلب معلومات السيرفر.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ حدث خطأ أثناء جلب معلومات السيرفر.", ephemeral=True)
            except Exception:
                pass

    @app_commands.command(name="serverinfo_settings", description="[الإدارة] التحكم في إعدادات ومظهر لوحة معلومات السيرفر")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def serverinfo_settings(self, interaction: discord.Interaction):
        try:
            cfg = await STORE.get(interaction.guild.id)
            await interaction.response.send_message(embed=build_settings_embed(interaction.guild, cfg), view=SettingsView(cfg), ephemeral=True)
        except Exception as e:
            log.exception("خطأ في أمر serverinfo_settings", exc_info=e)
            await respond(interaction, content="❌ حدث خطأ أثناء فتح لوحة الإعدادات.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        content = message.content.strip().lower()
        if not content or len(content) > 40:
            return
        cfg = await STORE.get(message.guild.id)
        if not cfg["shortcuts_enabled"] or content not in cfg["shortcuts"]:
            return
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if now - self.shortcut_cd.get(key, 0) < COMMAND_COOLDOWN:
            return
        self.shortcut_cd[key] = now
        if len(self.shortcut_cd) > 2000:
            cutoff = now - 3600
            self.shortcut_cd = {k: v for k, v in self.shortcut_cd.items() if v > cutoff}
        try:
            async def send(**kwargs):
                return await message.channel.send(**kwargs)

            await self.open_panel(send, message.guild, message.author.id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not member.guild:
            return
        try:
            cfg = await STORE.get(member.guild.id)
            if cfg["track_growth"]:
                await STORE.record_growth(member.guild.id, 1, 0, member.guild.member_count or 0)
            await update_peak(member.guild, cfg, member.guild.member_count or 0)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot or not member.guild:
            return
        try:
            cfg = await STORE.get(member.guild.id)
            if cfg["track_growth"]:
                await STORE.record_growth(member.guild.id, 0, 1, member.guild.member_count or 0)
        except Exception:
            pass

    @commands.command(name="sync_slash")
    @commands.is_owner()
    async def sync_slash(self, ctx: commands.Context):
        try:
            synced = await ctx.bot.tree.sync()
            await ctx.send(f"✅ تمت مزامنة **{len(synced)}** أمر سلاش بنجاح.")
        except Exception as e:
            await ctx.send(f"❌ فشلت المزامنة: `{e}`")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await respond(interaction, content=f"⏳ اللوحة في حالة تهدئة، استنى `{error.retry_after:.0f}` ثواني.", ephemeral=True)
            return
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ الأمر مخصص للإدارة فقط.", ephemeral=True)
            return
        log.exception("خطأ في أمر سلاش", exc_info=error)
        await respond(interaction, content="❌ حدث خطأ غير متوقع أثناء معالجة الأمر.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerInfoCog(bot))
