"""
⚡ نظام الترحيب والمغادرة والرتب التلقائية (نسخة احترافية)

ملاحظات مهمة:
- الإعدادات بقت لكل سيرفر لوحده وبتتحفظ في MongoDB (collection: welcome_settings) وما بتضيعش بعد الريستارت.
  لو MONGODB_URI مش موجود البوت بيشتغل بالذاكرة بس وبيحذّرك.
- اسم السيرفر بقى بيتجاب أوتوماتيك من السيرفر نفسه عن طريق [server] (مفيش اسم مكتوب ثابت).
- محتاج Intents: guilds + members + invites (وللتتبع: صلاحية Manage Server للبوت، ولرتب أوتوماتيك: Manage Roles).
"""
import asyncio
import collections
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
log = logging.getLogger("welcome")

# ==============================================================================
# ⚙️ الثوابت والإعدادات الافتراضية
# ==============================================================================
COLOR_DARK = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_ORANGE = 0xFFA500
COLOR_BLUE = 0x3498DB

RAID_JOINS = 10        # لو دخل أكتر من العدد ده في RAID_WINDOW ثانية، الترحيب بيتوقف مؤقتاً
RAID_WINDOW = 10
NEW_ACCOUNT_DAYS = 7   # الحسابات الأحدث من كده بتتعلّم في السجل

DEFAULTS: dict[str, Any] = {
    # حالات التشغيل
    "welcome_enabled": True,
    "leave_enabled": True,
    "dm_welcome_enabled": False,
    "card_enabled": True,
    "bot_messages": False,
    "ping_member": True,
    "log_enabled": False,
    # الرتب التلقائية
    "autorole_members_enabled": False,
    "autorole_bots_enabled": False,
    "autorole_wait_screening": True,
    "autorole_member_ids": [],
    "autorole_bot_ids": [],
    "autorole_min_account_age": 0,
    "autorole_delay": 0,
    # الرومات
    "welcome_channel_id": None,
    "leave_channel_id": None,
    "log_channel_id": None,
    # الصور والمظهر
    "card_image_url": "https://probot.media/Bwt5SOHnkM.png",
    "leave_image_url": None,
    "dm_image_url": None,
    "thumbnail_mode": "avatar",
    "welcome_color": "2B2D31",
    "leave_color": "E74C3C",
    "welcome_title": "",
    "leave_title": "",
    "footer_text": "[server] ✦ Welcome System",
    # الرسائل
    "welcome_message": (
        "## ⚡ ╎ WELCOME TO [server] ⚡\n\n"
        "أهلاً بك يا [user]! ✨\n"
        "نورتنا وشرفتنا بانضمامك لعائلة **[server]** الكبيرة، ونتمنى لك أوقاتاً ممتعة معنا.\n\n"
        "> 👥 **أنت العضو رقم** `[memberCount]`\n"
        "> 📨 **تمت دعوتك بواسطة:** [inviter] (`[invites]` دعوة)\n"
        "> 📅 **تاريخ إنشاء حسابك:** [accountCreated] ([accountAge])"
    ),
    "leave_message": (
        "👋 ╎ غادرنا العضو **[userName]**...\n"
        "نتمنى له التوفيق، وأصبح عدد الأعضاء الحالي **[memberCount]**.\n"
        "> ⏱️ كان معنا منذ [joinedAt]"
    ),
    "dm_message": (
        "مرحباً بك يا **[displayName]** في سيرفر **[server]**! 🎉\n"
        "نأمل أن تستمتع بوقتك معنا وتلتزم بالقوانين."
    ),
    "bot_message": (
        "## 🤖 ╎ انضم بوت جديد!\n\n"
        "تمت إضافة البوت [user] إلى **[server]** بواسطة [inviter]."
    ),
}

TOGGLES = [
    ("welcome_enabled", "الترحيب", "📥"),
    ("leave_enabled", "المغادرة", "📤"),
    ("card_enabled", "صورة الترحيب", "🖼️"),
    ("dm_welcome_enabled", "الخاص DM", "✉️"),
    ("bot_messages", "رسائل البوتات", "🤖"),
    ("ping_member", "منشن العضو", "🔔"),
    ("autorole_members_enabled", "رتب الأعضاء", "🏷️"),
    ("autorole_bots_enabled", "رتب البوتات", "🛠️"),
    ("autorole_wait_screening", "انتظار فحص الانضمام", "🛡️"),
    ("log_enabled", "سجل الدخول/الخروج", "📋"),
]

PLACEHOLDERS = [
    ("[user]", "منشن العضو"),
    ("[userName]", "اسم الحساب"),
    ("[displayName]", "الاسم المعروض"),
    ("[userId]", "أيدي العضو"),
    ("[server]", "اسم السيرفر"),
    ("[memberCount]", "عدد الأعضاء الحالي"),
    ("[inviter]", "منشن الداعي"),
    ("[inviterName]", "اسم الداعي"),
    ("[invites]", "عدد دعوات الداعي"),
    ("[accountCreated]", "تاريخ إنشاء الحساب"),
    ("[accountAge]", "عمر الحساب (منذ كذا)"),
    ("[joinedAt]", "مدة وجود العضو (للمغادرة)"),
]


# ==============================================================================
# 💾 التخزين (لكل سيرفر على حدة)
# ==============================================================================
class WelcomeStore:
    def __init__(self):
        self.cache: dict[int, dict] = {}
        self.col = None
        uri = os.getenv("MONGODB_URI", "").strip()
        if uri:
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=5000)
                self.col = client["ZeroPro_Welcome_DB"]["welcome_settings"]
            except Exception:
                log.exception("فشل الاتصال بـ MongoDB")
        else:
            log.warning("MONGODB_URI غير موجود! إعدادات الترحيب هتضيع بعد أي ريستارت.")

    async def init(self):
        if self.col is not None:
            try:
                await asyncio.to_thread(self.col.create_index, "guild_id", unique=True)
            except Exception:
                log.warning("تعذر إنشاء index", exc_info=True)

    async def get(self, gid: int) -> dict:
        cfg = self.cache.get(gid)
        if cfg is not None:
            return cfg
        doc = None
        if self.col is not None:
            try:
                doc = await asyncio.to_thread(self.col.find_one, {"guild_id": gid})
            except Exception:
                log.exception("فشل قراءة إعدادات السيرفر %s (هستخدم الافتراضي مؤقتاً)", gid)
                return copy.deepcopy(DEFAULTS)  # من غير كاش، عشان نعيد المحاولة المرة الجاية
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
                log.exception("فشل حفظ إعدادات السيرفر %s", gid)

    async def reset(self, gid: int):
        self.cache[gid] = copy.deepcopy(DEFAULTS)
        if self.col is not None:
            try:
                await asyncio.to_thread(self.col.delete_one, {"guild_id": gid})
            except Exception:
                log.exception("فشل مسح إعدادات السيرفر %s", gid)


STORE = WelcomeStore()


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


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def parse_color(value: Any, default: int = COLOR_DARK) -> int:
    m = _HEX_RE.match(str(value or "").strip())
    return int(m.group(1), 16) if m else default


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def report_error(interaction: discord.Interaction):
    try:
        await respond(interaction, content="❌ حصل خطأ غير متوقع، حاول تاني.", ephemeral=True)
    except discord.HTTPException:
        pass


def role_problem(guild: discord.Guild, role: Optional[discord.Role]) -> Optional[str]:
    if role is None:
        return "الرتبة اتحذفت"
    if role.is_default():
        return "رتبة @everyone"
    if role.managed:
        return "رتبة خاصة بتكامل/بوت"
    if role >= guild.me.top_role:
        return "أعلى من رتبة البوت أو مساوية لها"
    return None


def format_text(text: str, member: discord.Member, ctx: Optional[dict] = None) -> str:
    ctx = ctx or {}
    guild = member.guild
    created = int(member.created_at.timestamp())
    joined = int(member.joined_at.timestamp()) if member.joined_at else None
    repl = {
        "[user]": member.mention,
        "[userName]": member.name,
        "[displayName]": member.display_name,
        "[userId]": str(member.id),
        "[server]": guild.name,
        "[memberCount]": str(guild.member_count or len(guild.members)),
        "[inviter]": ctx.get("inviter", "—"),
        "[inviterName]": ctx.get("inviter_name", "—"),
        "[invites]": str(ctx.get("invites", 0)),
        "[accountCreated]": f"<t:{created}:D>",
        "[accountAge]": f"<t:{created}:R>",
        "[joinedAt]": f"<t:{joined}:R>" if joined else "—",
    }
    for key, value in repl.items():
        text = text.replace(key, value)
    return text


def apply_thumbnail(embed: discord.Embed, member: discord.Member, mode: str):
    if mode == "server" and member.guild.icon:
        embed.set_thumbnail(url=member.guild.icon.url)
    elif mode == "avatar":
        embed.set_thumbnail(url=member.display_avatar.url)


def base_embed(member: discord.Member, cfg: dict, description: str, title: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=clip(title, 256) or None, description=clip(description, 4096), color=color, timestamp=discord.utils.utcnow())
    embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
    footer = format_text(cfg["footer_text"], member)
    embed.set_footer(text=clip(f"{footer} ┃ ID: {member.id}", 2048))
    return embed


def build_welcome_embed(member: discord.Member, cfg: dict, ctx: dict, as_bot: Optional[bool] = None) -> discord.Embed:
    is_bot = member.bot if as_bot is None else as_bot
    text = cfg["bot_message"] if is_bot else cfg["welcome_message"]
    embed = base_embed(member, cfg, format_text(text, member, ctx), format_text(cfg["welcome_title"], member, ctx), parse_color(cfg["welcome_color"]))
    apply_thumbnail(embed, member, cfg["thumbnail_mode"])
    if cfg["card_enabled"] and cfg["card_image_url"]:
        embed.set_image(url=cfg["card_image_url"])
    return embed


def build_leave_embed(member: discord.Member, cfg: dict) -> discord.Embed:
    embed = base_embed(member, cfg, format_text(cfg["leave_message"], member), format_text(cfg["leave_title"], member), parse_color(cfg["leave_color"], 0xE74C3C))
    apply_thumbnail(embed, member, cfg["thumbnail_mode"])
    if cfg["card_enabled"] and cfg["leave_image_url"]:
        embed.set_image(url=cfg["leave_image_url"])
    return embed


def build_dm_embed(member: discord.Member, cfg: dict, ctx: dict) -> discord.Embed:
    embed = discord.Embed(description=clip(format_text(cfg["dm_message"], member, ctx), 4096), color=parse_color(cfg["welcome_color"]), timestamp=discord.utils.utcnow())
    embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
    embed.set_footer(text=clip(format_text(cfg["footer_text"], member), 2048))
    if cfg["dm_image_url"]:
        embed.set_image(url=cfg["dm_image_url"])
    return embed


def strip_media(embed: discord.Embed) -> discord.Embed:
    fb = embed.copy()
    fb.set_image(url=None)
    return fb


async def deliver(guild: discord.Guild, channel, embed: discord.Embed, content: Optional[str] = None,
                  mention: Optional[discord.Member] = None) -> tuple[bool, str]:
    """إرسال آمن: بيفحص الصلاحيات، وبيعيد المحاولة من غير صور لو الرابط بايظ."""
    if not isinstance(channel, discord.abc.Messageable):
        return False, "الروم غير صالح."
    perms = channel.permissions_for(guild.me)
    if not perms.send_messages:
        return False, "البوت معندوش صلاحية الإرسال في الروم."
    if not perms.embed_links:
        return False, "البوت معندوش صلاحية Embed Links في الروم."
    allowed = discord.AllowedMentions(users=[mention]) if mention else discord.AllowedMentions.none()
    try:
        await channel.send(content=content, embed=embed, allowed_mentions=allowed)
        return True, ""
    except discord.HTTPException:
        try:
            await channel.send(content=content, embed=strip_media(embed), allowed_mentions=allowed)
            return True, "الصورة اتشالت لأن الرابط غير صالح."
        except discord.HTTPException as e:
            return False, f"فشل الإرسال: {e}"


def on_off(value: bool) -> str:
    return "مفعل ✅" if value else "معطل ❌"


# ==============================================================================
# 🖼️ بناء إيمبدات اللوحة
# ==============================================================================
def build_panel_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    def chan(cid):
        return f"<#{cid}>" if cid and guild.get_channel(cid) else "`غير محدد ❌`"

    def roles_line(ids):
        if not ids:
            return "`غير محددة`"
        parts = []
        for rid in ids:
            role = guild.get_role(rid)
            parts.append(role.mention if role and not role_problem(guild, role) else f"`{rid}` ⚠️")
        return " ".join(parts)

    p = guild.me.guild_permissions
    perms = (f"{'✅' if p.manage_guild else '⚠️'} تتبع الدعوات ┊ {'✅' if p.manage_roles else '⚠️'} إعطاء الرتب ┊ "
             f"{'✅' if p.view_audit_log else '➖'} سجل التدقيق (اختياري)")
    age = cfg["autorole_min_account_age"]
    delay = cfg["autorole_delay"]
    rules = f"أقل عمر حساب: `{age} يوم`" if age else "أقل عمر حساب: `بدون شرط`"
    rules += f" ┊ تأخير: `{delay}ث`" if delay else " ┊ تأخير: `فوراً`"

    desc = (
        "> **أهلاً بك في لوحة الإدارة المركزية لنظام الترحيب والمغادرة.** ✨\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "### 🌐 ┃ الحالة العامة\n"
        f"> * 📥 **الترحيب:** {on_off(cfg['welcome_enabled'])}\n"
        f"> * 📤 **المغادرة:** {on_off(cfg['leave_enabled'])}\n"
        f"> * 🖼️ **صورة الترحيب:** {on_off(cfg['card_enabled'])}\n"
        f"> * ✉️ **الترحيب الخاص (DM):** {on_off(cfg['dm_welcome_enabled'])}\n"
        f"> * 🤖 **رسائل البوتات:** {on_off(cfg['bot_messages'])}\n"
        f"> * 🔔 **منشن العضو:** {on_off(cfg['ping_member'])}\n\n"
        "### 📌 ┃ الرومات\n"
        f"> * 📥 **روم الترحيب:** {chan(cfg['welcome_channel_id'])}\n"
        f"> * 📤 **روم المغادرة:** {chan(cfg['leave_channel_id'])}\n"
        f"> * 📋 **روم السجل:** {chan(cfg['log_channel_id'])} ({on_off(cfg['log_enabled'])})\n\n"
        "### 🏷️ ┃ الرتب التلقائية\n"
        f"> * 👤 **رتب الأعضاء** ({on_off(cfg['autorole_members_enabled'])}): {roles_line(cfg['autorole_member_ids'])}\n"
        f"> * 🤖 **رتب البوتات** ({on_off(cfg['autorole_bots_enabled'])}): {roles_line(cfg['autorole_bot_ids'])}\n"
        f"> * 🛡️ **انتظار فحص الانضمام:** {on_off(cfg['autorole_wait_screening'])}\n"
        f"> * ⚙️ **الشروط:** {rules}\n\n"
        "### 🔐 ┃ صلاحيات البوت\n"
        f"> {perms}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
    embed = discord.Embed(title=f"⚡ ‹ لوحة تحكم الترحيب — {guild.name} › ⚡", description=clip(desc, 4096), color=COLOR_DARK, timestamp=discord.utils.utcnow())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"{guild.name} ✦ Welcome Management Panel")
    return embed


def build_toggles_embed() -> discord.Embed:
    return discord.Embed(
        title="⚙️ تشغيل وإيقاف الأنظمة",
        description="اضغط على أي زر لتغيير حالته فوراً:\n🟩 **أخضر** = مفعل ┊ ⬜ **رمادي** = معطل",
        color=COLOR_DARK,
    )


def build_channels_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    lines = []
    for key, label in (("welcome_channel_id", "📥 روم الترحيب"), ("leave_channel_id", "📤 روم المغادرة"), ("log_channel_id", "📋 روم السجل")):
        cid = cfg[key]
        ch = guild.get_channel(cid) if cid else None
        if ch is None:
            lines.append(f"> * {label}: `غير محدد ❌`")
            continue
        perms = ch.permissions_for(guild.me)
        warn = "" if (perms.send_messages and perms.embed_links) else " ⚠️ _البوت معندوش صلاحية الإرسال/Embed هنا_"
        lines.append(f"> * {label}: {ch.mention}{warn}")
    return discord.Embed(
        title="📌 تحديد الرومات",
        description="اختر الروم من القوائم أدناه (وامسح الاختيار لإلغاء الروم):\n\n" + "\n".join(lines),
        color=COLOR_DARK,
    )


def build_roles_embed(guild: discord.Guild, cfg: dict, kind: str, notice: str = "") -> discord.Embed:
    ids = cfg["autorole_bot_ids" if kind == "bot" else "autorole_member_ids"]
    enabled = cfg["autorole_bots_enabled" if kind == "bot" else "autorole_members_enabled"]
    title = "🤖 رتب البوتات التلقائية" if kind == "bot" else "🏷️ رتب الأعضاء التلقائية"
    current = " ".join(f"<@&{r}>" for r in ids) if ids else "`غير محددة`"
    desc = (
        f"اختر الرتب اللي هتتدّي أوتوماتيك لكل {'بوت' if kind == 'bot' else 'عضو'} جديد.\n"
        "**امسح الاختيار لإزالة كل الرتب.**\n\n"
        f"> * **الحالة:** {on_off(enabled)}\n> * **الرتب الحالية:** {current}"
    )
    if notice:
        desc += f"\n\n{notice}"
    return discord.Embed(title=title, description=clip(desc, 4096), color=COLOR_DARK)


def build_guide_embed() -> discord.Embed:
    lines = "\n".join(f"• `{k}` ⟵ {v}" for k, v in PLACEHOLDERS)
    return discord.Embed(
        title="📖 دليل الاختصارات",
        description=f"تقدر تستخدم الاختصارات دي في الرسائل والعناوين والتذييل:\n\n{lines}\n\n💡 اسم السيرفر بيتجاب أوتوماتيك من السيرفر نفسه عن طريق `[server]`.",
        color=COLOR_BLUE,
    )


# ==============================================================================
# 🛡️ Views/Modals آمنة
# ==============================================================================
class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


class AdminView(SafeView):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await respond(interaction, embed=err_embed("للمدراء فقط!"), ephemeral=True)
        return False


async def show_panel(interaction: discord.Interaction, notice: Optional[str] = None):
    """يرجّع اللوحة الرئيسية (بيعدّل نفس الرسالة)."""
    cfg = await STORE.get(interaction.guild.id)
    await interaction.response.edit_message(embed=build_panel_embed(interaction.guild, cfg), view=WelcomePanelView())
    if notice:
        await interaction.followup.send(embed=ok_embed("✅ تم", notice), ephemeral=True)


class BackButton(discord.ui.Button):
    def __init__(self, row: Optional[int] = None):
        super().__init__(label="رجوع للوحة", emoji="↩️", style=discord.ButtonStyle.secondary, row=row)

    async def callback(self, interaction: discord.Interaction):
        await show_panel(interaction)


# ----- القوائم الفرعية -----
class TogglesView(AdminView):
    def __init__(self, cfg: dict):
        super().__init__(timeout=600)
        for key, label, emoji in TOGGLES:
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.success if cfg[key] else discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(key)
            self.add_item(btn)
        self.add_item(BackButton())

    @staticmethod
    def _make_cb(key: str):
        async def cb(interaction: discord.Interaction):
            cfg = await STORE.get(interaction.guild.id)
            await STORE.update(interaction.guild.id, **{key: not cfg[key]})
            await interaction.response.edit_message(embed=build_toggles_embed(), view=TogglesView(cfg))
        return cb


class ChannelsView(AdminView):
    def __init__(self):
        super().__init__(timeout=600)
        self.add_item(BackButton(row=3))

    async def _save(self, interaction: discord.Interaction, key: str, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel(select.values[0].id) if select.values else None
        await STORE.update(interaction.guild.id, **{key: channel.id if channel else None})
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_channels_embed(interaction.guild, cfg), view=ChannelsView())

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news],
                       placeholder="📥 اختر روم الترحيب", min_values=0, max_values=1, row=0)
    async def pick_welcome(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await self._save(interaction, "welcome_channel_id", select)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news],
                       placeholder="📤 اختر روم المغادرة", min_values=0, max_values=1, row=1)
    async def pick_leave(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await self._save(interaction, "leave_channel_id", select)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news],
                       placeholder="📋 اختر روم السجل (اختياري)", min_values=0, max_values=1, row=2)
    async def pick_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await self._save(interaction, "log_channel_id", select)


class RolesView(AdminView):
    def __init__(self, kind: str):
        super().__init__(timeout=600)
        self.kind = kind
        select = discord.ui.RoleSelect(placeholder="اختر الرتب (امسح الاختيار لإزالة الكل)", min_values=0, max_values=10, row=0)

        async def cb(interaction: discord.Interaction):
            await self.save(interaction, list(select.values))

        select.callback = cb
        self.add_item(select)
        self.add_item(BackButton(row=1))

    async def save(self, interaction: discord.Interaction, roles: list):
        guild = interaction.guild
        valid, notes = [], []
        for r in roles:
            problem = role_problem(guild, guild.get_role(r.id))
            if problem:
                notes.append(f"• {r.mention}: {problem}")
            else:
                valid.append(r.id)
        ids_key, flag_key = ("autorole_bot_ids", "autorole_bots_enabled") if self.kind == "bot" else ("autorole_member_ids", "autorole_members_enabled")
        await STORE.update(guild.id, **{ids_key: valid, flag_key: bool(valid)})
        cfg = await STORE.get(guild.id)
        notice = ""
        if notes:
            notice = "⚠️ **تم تجاهل الرتب دي (البوت مش هيعرف يديها):**\n" + "\n".join(notes) + "\n_حرّك رتبة البوت فوقها من إعدادات السيرفر._"
        elif valid:
            notice = "✅ تم الحفظ وتفعيل النظام."
        await interaction.response.edit_message(embed=build_roles_embed(guild, cfg, self.kind, notice), view=RolesView(self.kind))


class ResetConfirmView(AdminView):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="تأكيد إعادة الضبط", style=discord.ButtonStyle.danger, emoji="♻️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await STORE.reset(interaction.guild.id)
        await show_panel(interaction, "تم إرجاع كل الإعدادات للوضع الافتراضي.")

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_panel(interaction)


# ----- المودالات -----
class MessagesModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="💬 تعديل الرسائل")
        self.w_msg = discord.ui.TextInput(label="رسالة الترحيب (للأعضاء)", style=discord.TextStyle.paragraph, default=clip(cfg["welcome_message"], 1500), max_length=1500)
        self.l_msg = discord.ui.TextInput(label="رسالة المغادرة", style=discord.TextStyle.paragraph, default=clip(cfg["leave_message"], 1500), max_length=1500)
        self.dm_msg = discord.ui.TextInput(label="رسالة الخاص (DM)", style=discord.TextStyle.paragraph, default=clip(cfg["dm_message"], 1500), max_length=1500)
        self.bot_msg = discord.ui.TextInput(label="رسالة ترحيب البوتات", style=discord.TextStyle.paragraph, default=clip(cfg["bot_message"], 1500), max_length=1500)
        for box in (self.w_msg, self.l_msg, self.dm_msg, self.bot_msg):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        await STORE.update(interaction.guild.id, welcome_message=self.w_msg.value, leave_message=self.l_msg.value,
                           dm_message=self.dm_msg.value, bot_message=self.bot_msg.value)
        await show_panel(interaction, "تم حفظ الرسائل بنجاح. استخدم زر 👁️ معاينة تشوف الشكل.")


class ImagesModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🖼️ الصور والصورة المصغرة")
        self.card = discord.ui.TextInput(label="رابط صورة الترحيب (فاضي = بدون)", default=cfg["card_image_url"] or "", required=False, max_length=400)
        self.leave = discord.ui.TextInput(label="رابط صورة المغادرة (فاضي = بدون)", default=cfg["leave_image_url"] or "", required=False, max_length=400)
        self.dm = discord.ui.TextInput(label="رابط صورة رسالة الخاص (فاضي = بدون)", default=cfg["dm_image_url"] or "", required=False, max_length=400)
        self.thumb = discord.ui.TextInput(label="الصورة المصغرة (avatar / server / none)", default=cfg["thumbnail_mode"], max_length=10)
        for box in (self.card, self.leave, self.dm, self.thumb):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        urls = {}
        for key, box in (("card_image_url", self.card), ("leave_image_url", self.leave), ("dm_image_url", self.dm)):
            raw = box.value.strip()
            if raw and not clean_url(raw):
                await respond(interaction, embed=err_embed("كل رابط صورة لازم يبدأ بـ http أو https."), ephemeral=True)
                return
            urls[key] = raw or None
        t = self.thumb.value.strip().lower()
        mode = "server" if ("server" in t or "سيرفر" in t) else "none" if ("none" in t or "بدون" in t) else "avatar"
        await STORE.update(interaction.guild.id, thumbnail_mode=mode, **urls)
        await show_panel(interaction, "تم حفظ الصور بنجاح.")


class AppearanceModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🎨 المظهر والألوان")
        self.w_color = discord.ui.TextInput(label="لون إيمبد الترحيب (Hex مثل 2B2D31)", default=cfg["welcome_color"], max_length=7)
        self.l_color = discord.ui.TextInput(label="لون إيمبد المغادرة (Hex مثل E74C3C)", default=cfg["leave_color"], max_length=7)
        self.footer = discord.ui.TextInput(label="نص التذييل ([server] مدعوم)", default=clip(cfg["footer_text"], 100), max_length=100)
        self.w_title = discord.ui.TextInput(label="عنوان إيمبد الترحيب (اختياري)", default=cfg["welcome_title"], required=False, max_length=100)
        self.l_title = discord.ui.TextInput(label="عنوان إيمبد المغادرة (اختياري)", default=cfg["leave_title"], required=False, max_length=100)
        for box in (self.w_color, self.l_color, self.footer, self.w_title, self.l_title):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        for box in (self.w_color, self.l_color):
            if not _HEX_RE.match(box.value.strip()):
                await respond(interaction, embed=err_embed("اللون لازم يكون Hex من 6 أرقام/حروف، مثال: `2B2D31`."), ephemeral=True)
                return
        await STORE.update(
            interaction.guild.id,
            welcome_color=_HEX_RE.match(self.w_color.value.strip()).group(1).upper(),
            leave_color=_HEX_RE.match(self.l_color.value.strip()).group(1).upper(),
            footer_text=self.footer.value.strip() or DEFAULTS["footer_text"],
            welcome_title=self.w_title.value.strip(),
            leave_title=self.l_title.value.strip(),
        )
        await show_panel(interaction, "تم حفظ المظهر بنجاح.")


class AccountRulesModal(SafeModal):
    def __init__(self, cfg: dict):
        super().__init__(title="🛡️ شروط الرتب التلقائية")
        self.age = discord.ui.TextInput(label="أقل عمر للحساب بالأيام (0 = بدون شرط)", default=str(cfg["autorole_min_account_age"]), max_length=4)
        self.delay = discord.ui.TextInput(label="تأخير إعطاء الرتب بالثواني (0 = فوراً)", default=str(cfg["autorole_delay"]), max_length=4)
        self.add_item(self.age)
        self.add_item(self.delay)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            age, delay = int(self.age.value.strip()), int(self.delay.value.strip())
            if not (0 <= age <= 365 and 0 <= delay <= 3600):
                raise ValueError
        except ValueError:
            await respond(interaction, embed=err_embed("العمر من 0 لـ 365 يوم، والتأخير من 0 لـ 3600 ثانية."), ephemeral=True)
            return
        await STORE.update(interaction.guild.id, autorole_min_account_age=age, autorole_delay=delay)
        await show_panel(interaction, "تم حفظ الشروط بنجاح.")


# ----- اللوحة الرئيسية -----
class WelcomePanelView(AdminView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف الأنظمة", emoji="⚙️", style=discord.ButtonStyle.blurple, row=0, custom_id="wl_toggles_v2")
    async def btn_toggles(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_toggles_embed(), view=TogglesView(cfg))

    @discord.ui.button(label="تحديد الرومات", emoji="📌", style=discord.ButtonStyle.green, row=0, custom_id="wl_channels_v2")
    async def btn_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_channels_embed(interaction.guild, cfg), view=ChannelsView())

    @discord.ui.button(label="تعديل الرسائل", emoji="💬", style=discord.ButtonStyle.blurple, row=0, custom_id="wl_messages_v2")
    async def btn_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MessagesModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="الصور", emoji="🖼️", style=discord.ButtonStyle.grey, row=0, custom_id="wl_images_v2")
    async def btn_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagesModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="المظهر والألوان", emoji="🎨", style=discord.ButtonStyle.grey, row=1, custom_id="wl_appearance_v2")
    async def btn_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppearanceModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="رتب الأعضاء", emoji="🏷️", style=discord.ButtonStyle.green, row=1, custom_id="wl_roles_members_v2")
    async def btn_roles_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_roles_embed(interaction.guild, cfg, "member"), view=RolesView("member"))

    @discord.ui.button(label="رتب البوتات", emoji="🤖", style=discord.ButtonStyle.green, row=1, custom_id="wl_roles_bots_v2")
    async def btn_roles_bots(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.edit_message(embed=build_roles_embed(interaction.guild, cfg, "bot"), view=RolesView("bot"))

    @discord.ui.button(label="شروط الرتب", emoji="🛡️", style=discord.ButtonStyle.grey, row=1, custom_id="wl_rules_v2")
    async def btn_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AccountRulesModal(await STORE.get(interaction.guild.id)))

    @discord.ui.button(label="معاينة", emoji="👁️", style=discord.ButtonStyle.blurple, row=2, custom_id="wl_preview_v2")
    async def btn_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cfg = await STORE.get(interaction.guild.id)
        me = interaction.user
        ctx = {"inviter": me.mention, "inviter_name": me.name, "invites": 5}
        embeds = [build_welcome_embed(me, cfg, ctx, as_bot=False), build_welcome_embed(me, cfg, ctx, as_bot=True),
                  build_leave_embed(me, cfg), build_dm_embed(me, cfg, ctx)]
        content = "👁️ **معاينة:** (1) ترحيب الأعضاء ┊ (2) ترحيب البوتات ┊ (3) المغادرة ┊ (4) رسالة الخاص — بياناتك كمثال."
        try:
            await interaction.followup.send(content=content, embeds=embeds, ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send(content=content + "\n⚠️ رابط صورة غير صالح، المعاينة من غير صور.", embeds=[strip_media(e) for e in embeds], ephemeral=True)

    @discord.ui.button(label="إرسال تجريبي", emoji="🧪", style=discord.ButtonStyle.green, row=2, custom_id="wl_test_v2")
    async def btn_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        cfg = await STORE.get(guild.id)
        me = interaction.user
        ctx = {"inviter": me.mention, "inviter_name": me.name, "invites": 5}
        results = []
        for label, key, embed in (("الترحيب", "welcome_channel_id", build_welcome_embed(me, cfg, ctx, as_bot=False)),
                                  ("المغادرة", "leave_channel_id", build_leave_embed(me, cfg))):
            cid = cfg[key]
            chan = guild.get_channel(cid) if cid else None
            if chan is None:
                results.append(f"• **{label}:** ❌ الروم غير محدد")
                continue
            ok, note = await deliver(guild, chan, embed, content=f"🧪 **رسالة تجريبية** بواسطة {me.mention}")
            results.append(f"• **{label}:** {'✅ اتبعتت في ' + chan.mention if ok else '❌ ' + note}" + (f" ({note})" if ok and note else ""))
        await interaction.followup.send(embed=discord.Embed(title="🧪 نتيجة الإرسال التجريبي", description="\n".join(results), color=COLOR_DARK), ephemeral=True)

    @discord.ui.button(label="دليل الاختصارات", emoji="📖", style=discord.ButtonStyle.grey, row=2, custom_id="wl_guide_v2")
    async def btn_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_guide_embed(), ephemeral=True)

    @discord.ui.button(label="إعادة الضبط", emoji="♻️", style=discord.ButtonStyle.danger, row=2, custom_id="wl_reset_v2")
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="♻️ إعادة ضبط الإعدادات", description="⚠️ هترجع **كل** إعدادات الترحيب والرتب التلقائية للوضع الافتراضي. متأكد؟", color=COLOR_ORANGE)
        await interaction.response.edit_message(embed=embed, view=ResetConfirmView())


# ==============================================================================
# 🌟 Cog النظام الرئيسي
# ==============================================================================
class MegaWelcomeSystemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # كاش الدعوات: {guild_id: {code: (uses, inviter_id, inviter_name)}}
        self.invite_cache: dict[int, dict[str, tuple]] = {}
        self.invite_locks: dict[int, asyncio.Lock] = {}
        self.join_times: dict[int, collections.deque] = {}
        self._prime_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        await STORE.init()
        self.bot.add_view(WelcomePanelView())
        self._prime_task = asyncio.create_task(self._prime_invites())

    async def cog_unload(self):
        if self._prime_task:
            self._prime_task.cancel()

    # ---------- تتبع الدعوات ----------
    async def _snapshot_invites(self, guild: discord.Guild) -> Optional[dict]:
        if not guild.me.guild_permissions.manage_guild:
            return None
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return None
        return {i.code: (i.uses or 0, i.inviter.id if i.inviter else None, i.inviter.name if i.inviter else None) for i in invites}

    async def _prime_invites(self):
        await self.bot.wait_until_ready()
        for guild in list(self.bot.guilds):
            snap = await self._snapshot_invites(guild)
            if snap is not None:
                self.invite_cache[guild.id] = snap

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        snap = await self._snapshot_invites(guild)
        if snap is not None:
            self.invite_cache[guild.id] = snap

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild and invite.guild.id in self.invite_cache:
            self.invite_cache[invite.guild.id][invite.code] = (
                invite.uses or 0, invite.inviter.id if invite.inviter else None, invite.inviter.name if invite.inviter else None)

    async def find_bot_adder(self, member: discord.Member) -> Optional[discord.abc.User]:
        if not member.guild.me.guild_permissions.view_audit_log:
            return None
        await asyncio.sleep(1)
        try:
            async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    return entry.user
        except discord.HTTPException:
            pass
        return None

    async def detect_inviter(self, member: discord.Member) -> dict:
        ctx = {"inviter": "رابط عام", "inviter_name": "رابط عام", "invites": 0}
        guild = member.guild
        try:
            if member.bot:
                adder = await self.find_bot_adder(member)
                if adder:
                    ctx.update(inviter=adder.mention, inviter_name=adder.name)
                else:
                    ctx.update(inviter="غير معروف", inviter_name="غير معروف")
                return ctx

            lock = self.invite_locks.setdefault(guild.id, asyncio.Lock())
            async with lock:
                new_map = await self._snapshot_invites(guild)
                if new_map is None:
                    return ctx
                old_map = self.invite_cache.get(guild.id)
                self.invite_cache[guild.id] = new_map
            if old_map is None:  # أول مرة نشوف السيرفر: مفيش مقارنة ممكنة
                return ctx

            used = None
            for code, (uses, inv_id, inv_name) in new_map.items():
                if uses > old_map.get(code, (0,))[0]:
                    used = (inv_id, inv_name)
                    break
            if used is None:  # دعوة اتمسحت (غالباً استخدام واحد وخلصت)
                missing = [v for c, v in old_map.items() if c not in new_map]
                if len(missing) == 1:
                    used = (missing[0][1], missing[0][2])
            if used and used[0]:
                total = sum(u for (u, i, _n) in new_map.values() if i == used[0])
                ctx.update(inviter=f"<@{used[0]}>", inviter_name=used[1] or "غير معروف", invites=total)
        except Exception:
            log.exception("فشل تحديد الداعي")
        return ctx

    # ---------- الحماية من الغارات ----------
    def raid_suppressed(self, gid: int) -> bool:
        now = time.monotonic()
        dq = self.join_times.setdefault(gid, collections.deque())
        dq.append(now)
        while dq and now - dq[0] > RAID_WINDOW:
            dq.popleft()
        return len(dq) > RAID_JOINS

    # ---------- الرتب التلقائية ----------
    async def apply_autoroles(self, member: discord.Member, cfg: dict, from_screening: bool = False) -> list[discord.Role]:
        guild = member.guild
        enabled = cfg["autorole_bots_enabled"] if member.bot else cfg["autorole_members_enabled"]
        ids = cfg["autorole_bot_ids"] if member.bot else cfg["autorole_member_ids"]
        if not enabled or not ids:
            return []
        if cfg["autorole_wait_screening"] and member.pending and not from_screening:
            return []  # هتتدّي بعد ما العضو يعدّي فحص الانضمام
        if not guild.me.guild_permissions.manage_roles:
            log.warning("البوت معندوش Manage Roles في %s", guild.id)
            return []
        min_age = cfg["autorole_min_account_age"]
        if min_age and not member.bot and (discord.utils.utcnow() - member.created_at).days < min_age:
            return []
        if cfg["autorole_delay"] > 0 and not from_screening:
            await asyncio.sleep(cfg["autorole_delay"])
            member = guild.get_member(member.id)
            if member is None:  # العضو مشي قبل ما الرتب تتدّي
                return []
        roles = []
        for rid in ids:
            role = guild.get_role(rid)
            if role and not role_problem(guild, role) and role not in member.roles:
                roles.append(role)
        if not roles:
            return []
        try:
            await member.add_roles(*roles, reason="Welcome System: auto roles")
        except discord.HTTPException:
            log.warning("فشل إعطاء الرتب التلقائية للعضو %s", member.id, exc_info=True)
            return []
        return roles

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.pending and not after.pending:  # عدّى فحص الانضمام
            try:
                cfg = await STORE.get(after.guild.id)
                if cfg["autorole_wait_screening"]:
                    roles = await self.apply_autoroles(after, cfg, from_screening=True)
                    if roles:
                        await self._log_text(after.guild, cfg, f"🛡️ {after.mention} عدّى فحص الانضمام واستلم: {' '.join(r.mention for r in roles)}")
            except Exception:
                log.exception("خطأ في معالجة فحص الانضمام")

    # ---------- الدخول ----------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            await self._handle_join(member)
        except Exception:
            log.exception("خطأ في معالجة دخول العضو %s", member.id)

    async def _handle_join(self, member: discord.Member):
        guild = member.guild
        cfg = await STORE.get(guild.id)
        raid = self.raid_suppressed(guild.id)
        ctx = await self.detect_inviter(member)

        if cfg["welcome_enabled"] and (cfg["bot_messages"] or not member.bot):
            if raid:
                log.warning("تم إيقاف رسائل الترحيب مؤقتاً في %s (دخول سريع جداً)", guild.id)
            else:
                chan = guild.get_channel(cfg["welcome_channel_id"]) if cfg["welcome_channel_id"] else None
                if chan:
                    ping = member if (cfg["ping_member"] and not member.bot) else None
                    ok, note = await deliver(guild, chan, build_welcome_embed(member, cfg, ctx), content=member.mention if ping else None, mention=ping)
                    if not ok:
                        log.warning("فشل إرسال الترحيب في %s: %s", guild.id, note)

        if cfg["dm_welcome_enabled"] and not member.bot and not raid:
            try:
                await member.send(embed=build_dm_embed(member, cfg, ctx))
            except discord.HTTPException:
                try:
                    await member.send(embed=strip_media(build_dm_embed(member, cfg, ctx)))
                except discord.HTTPException:
                    pass

        roles = await self.apply_autoroles(member, cfg)
        await self._send_join_log(member, cfg, ctx, roles)

    async def _log_channel(self, guild: discord.Guild, cfg: dict):
        if not cfg["log_enabled"] or not cfg["log_channel_id"]:
            return None
        return guild.get_channel(cfg["log_channel_id"])

    async def _log_text(self, guild: discord.Guild, cfg: dict, text: str):
        chan = await self._log_channel(guild, cfg)
        if chan:
            await deliver(guild, chan, discord.Embed(description=text, color=COLOR_BLUE, timestamp=discord.utils.utcnow()))

    async def _send_join_log(self, member: discord.Member, cfg: dict, ctx: dict, roles: list[discord.Role]):
        chan = await self._log_channel(member.guild, cfg)
        if not chan:
            return
        created = int(member.created_at.timestamp())
        new_account = (discord.utils.utcnow() - member.created_at).days < NEW_ACCOUNT_DAYS
        embed = discord.Embed(
            title="🤖 دخول بوت جديد" if member.bot else "📥 دخول عضو جديد",
            description=("⚠️ **حساب جديد!**\n" if new_account and not member.bot else "") + f"{member.mention} (`{member.name}`)",
            color=COLOR_ORANGE if new_account and not member.bot else COLOR_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 الأيدي", value=f"`{member.id}`", inline=True)
        embed.add_field(name="👥 عدد الأعضاء", value=f"`{member.guild.member_count}`", inline=True)
        embed.add_field(name="📅 إنشاء الحساب", value=f"<t:{created}:F>\n(<t:{created}:R>)", inline=False)
        embed.add_field(name="🤖 أضافه" if member.bot else "📨 الداعي", value=f"{ctx['inviter']}" + (f" (`{ctx['invites']}` دعوة)" if ctx["invites"] and not member.bot else ""), inline=False)
        embed.add_field(name="🏷️ الرتب الممنوحة", value=" ".join(r.mention for r in roles) if roles else "—", inline=False)
        await deliver(member.guild, chan, embed)

    # ---------- المغادرة ----------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            await self._handle_leave(member)
        except Exception:
            log.exception("خطأ في معالجة مغادرة العضو %s", member.id)

    async def leave_reason(self, member: discord.Member) -> Optional[str]:
        guild = member.guild
        if not guild.me.guild_permissions.view_audit_log:
            return None
        await asyncio.sleep(1)
        cutoff = discord.utils.utcnow() - datetime.timedelta(seconds=15)
        try:
            for action, label in ((discord.AuditLogAction.kick, "👢 تم طرده"), (discord.AuditLogAction.ban, "🔨 تم حظره")):
                async for entry in guild.audit_logs(limit=5, action=action):
                    if entry.target and entry.target.id == member.id and entry.created_at >= cutoff:
                        text = f"{label} بواسطة {entry.user.mention}"
                        return text + (f"\nالسبب: {entry.reason}" if entry.reason else "")
        except discord.HTTPException:
            pass
        return None

    async def _handle_leave(self, member: discord.Member):
        guild = member.guild
        cfg = await STORE.get(guild.id)

        if cfg["leave_enabled"] and (cfg["bot_messages"] or not member.bot):
            chan = guild.get_channel(cfg["leave_channel_id"]) if cfg["leave_channel_id"] else None
            if chan:
                ok, note = await deliver(guild, chan, build_leave_embed(member, cfg))
                if not ok:
                    log.warning("فشل إرسال رسالة المغادرة في %s: %s", guild.id, note)

        log_chan = await self._log_channel(guild, cfg)
        if log_chan:
            reason = await self.leave_reason(member)
            roles = [r.mention for r in member.roles if not r.is_default()][:15]
            embed = discord.Embed(title="🤖 خروج بوت" if member.bot else "📤 مغادرة عضو", description=f"**{member.name}** (`{member.id}`)", color=COLOR_RED, timestamp=discord.utils.utcnow())
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="👥 عدد الأعضاء", value=f"`{guild.member_count}`", inline=True)
            if member.joined_at:
                embed.add_field(name="⏱️ انضم", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
            embed.add_field(name="🏷️ الرتب", value=" ".join(roles) or "—", inline=False)
            if reason:
                embed.add_field(name="📌 السبب", value=clip(reason, 1000), inline=False)
            await deliver(guild, log_chan, embed)

    # ---------- الأمر ----------
    @app_commands.command(name="welcome", description="[الإدارة] لوحة التحكم الكاملة في نظام الترحيب والمغادرة والرتب التلقائية")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_manager(self, interaction: discord.Interaction):
        cfg = await STORE.get(interaction.guild.id)
        await interaction.response.send_message(embed=build_panel_embed(interaction.guild, cfg), view=WelcomePanelView(), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ الأمر ده للإدارة فقط.", ephemeral=True)
            return
        log.exception("خطأ في أمر سلاش", exc_info=error)
        await report_error(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(MegaWelcomeSystemCog(bot))
