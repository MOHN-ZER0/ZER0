"""
🎫 نظام التذاكر المتكامل (نسخة مصلّحة ومحسّنة)

ملاحظات مهمة:
- البيانات بتتحفظ في MongoDB على شكل: document لكل سيرفر (collection: guild_data)
  + collection للتذاكر المغلقة (closed_tickets). والبيانات القديمة (tickets_data) بتتنقل أوتوماتيك أول تشغيل.
- أزرار داخل التذاكر (استلام/إغلاق/..) محافظة على نفس الـ custom_id القديم، فالتذاكر المفتوحة هتكمل شغل.
- البانلات المنشورة قبل التحديث لازم تتنشر تاني بأمر /ticket (الـ custom_id اتغير عشان يبقى ثابت بعد الريستارت).
"""
import asyncio
import copy
import io
import logging
import os
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
log = logging.getLogger("tickets")

# ==============================================================================
# ⚙️ الإعدادات والثوابت
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Tickets_DB"

COLOR_RED = 0xFF3333
COLOR_GREEN = 0x00FF88
COLOR_DARK = 0x2B2D31
COLOR_ORANGE = 0xFFA500

STATUS_OPEN = "مفتوحة"
STATUS_CLOSED = "مغلقة"

RATING_TIMEOUT_SECONDS = 30 * 60   # لو العضو ما قيّمش، التذكرة بتتحذف بعد المدة دي
PING_COOLDOWN = 60                 # ثواني بين كل تنبيه/تصعيد
REOPEN_DELAY = 5                   # ثواني قبل ما يتفتح زرار إعادة الفتح
MAX_SECTIONS = 25
WIZARD_TIMEOUT = 300
DEFAULT_CATEGORY_NAME = "🎫・التذاكر"
DEFAULT_SECTIONS_TEXT = "دعم فني\nاستفسارات\nتقديم إدارة"

ButtonCB = Callable[[discord.Interaction], Awaitable[None]]


# ==============================================================================
# 🧰 دوال مساعدة
# ==============================================================================
def clip(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def err_embed(description: str, title: str = "❌ خطأ") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_RED)


def ok_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_GREEN)


def now_ts() -> float:
    return time.time()


def parse_color(value: Any, default: int = COLOR_DARK) -> int:
    try:
        return int(str(value).replace("#", ""), 16)
    except (ValueError, TypeError):
        return default


_URL_RE = re.compile(r"^https?://\S{3,2000}$")
_ID_RE = re.compile(r"\d{15,20}")


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def parse_ids(text: str) -> list[int]:
    return [int(x) for x in _ID_RE.findall(text or "")]


def clean_panel_name(name: str) -> str:
    # النقطة و$ بتعمل مشاكل كمفاتيح في MongoDB
    return re.sub(r"[.$]", "", name or "").strip()[:50]


def parse_emoji(value: Any):
    value = value or "🎫"
    if str(value).isdigit():
        return discord.PartialEmoji(name="emoji", id=int(value))
    return str(value)


async def respond(interaction: discord.Interaction, **kwargs):
    """يرد على التفاعل سواء اتعمله defer قبل كده ولا لأ (يمنع أخطاء الرد المزدوج)."""
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def report_error(interaction: discord.Interaction):
    msg = "❌ حصل خطأ غير متوقع، حاول تاني. لو المشكلة استمرت كلم الإدارة."
    try:
        await respond(interaction, content=msg, ephemeral=True)
    except discord.HTTPException:
        pass


async def get_member(guild: discord.Guild, user_id: Any) -> Optional[discord.Member]:
    if not user_id:
        return None
    member = guild.get_member(int(user_id))
    if member:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except discord.HTTPException:
        return None


_cooldowns: dict[tuple[str, int], float] = {}


def cooldown_remaining(action: str, channel_id: int, seconds: float) -> float:
    """بيرجع الوقت المتبقي، وإلا بيسجل الاستخدام ويرجع 0."""
    if len(_cooldowns) > 5000:
        _cooldowns.clear()
    key = (action, channel_id)
    now = time.monotonic()
    remaining = seconds - (now - _cooldowns.get(key, 0))
    if remaining > 0:
        return remaining
    _cooldowns[key] = now
    return 0.0


# ==============================================================================
# 💾 تخزين البيانات (MongoDB) — في الذاكرة + حفظ في الخلفية بدون تعطيل البوت
# ==============================================================================
class TicketStore:
    def __init__(self):
        self.guilds: dict[str, dict] = {}
        self._dirty: set[str] = set()
        self._flush_task: Optional[asyncio.Task] = None
        self._flush_lock: Optional[asyncio.Lock] = None
        self._bg_tasks: set[asyncio.Task] = set()
        self.guild_col = None
        self.closed_col = None
        self.legacy_col = None
        if MONGO_URI:
            try:
                client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                db = client[DB_NAME]
                self.guild_col = db["guild_data"]
                self.closed_col = db["closed_tickets"]
                self.legacy_col = db["tickets_data"]
            except Exception:
                log.exception("فشل إنشاء الاتصال بـ MongoDB")
        else:
            log.warning("MONGODB_URI غير موجود! البيانات هتشتغل في الذاكرة بس وهتضيع مع أي ريستارت.")

    # ---------- تحميل ----------
    @staticmethod
    def _normalize(g: dict) -> dict:
        g.setdefault("panels", {})
        g.setdefault("active_tickets", {})
        g.setdefault("pending_ratings", {})
        g.setdefault("staff_stats", {})
        g.setdefault("log_channel_id", None)
        g.setdefault("ticket_counter", len(g["active_tickets"]))
        g.pop("closed_tickets_archive", None)
        for panel in g["panels"].values():
            for k in [k for k in panel if k.startswith("temp_")]:
                panel.pop(k, None)
            panel.setdefault("pid", uuid.uuid4().hex[:8])
            panel.setdefault("sections", {})
            panel.setdefault("display_type", "menu")
            panel.setdefault("color_hex", "2b2d31")
            for fld in ("image_url", "thumbnail_url"):
                if panel.get(fld) in ("None", ""):
                    panel[fld] = None
            for sec in panel["sections"].values():
                for fld in ("image_url", "thumbnail_url"):
                    if sec.get(fld) in ("None", ""):
                        sec[fld] = None
        return g

    def _load_sync(self) -> dict[str, dict]:
        if self.guild_col is None:
            return {}
        loaded: dict[str, dict] = {}
        for doc in self.guild_col.find({}):
            gid = str(doc.pop("_id"))
            loaded[gid] = doc
        if loaded:
            return loaded

        # ترحيل البيانات القديمة (مرة واحدة)
        legacy = self.legacy_col.find_one({"_id": "main_db"}) if self.legacy_col is not None else None
        if not legacy:
            return {}
        log.info("جاري ترحيل بيانات التذاكر القديمة...")
        for gid, g in (legacy.get("guilds") or {}).items():
            archive = g.pop("closed_tickets_archive", None) or []
            g["ticket_counter"] = len(g.get("active_tickets", {})) + len(archive)
            recs = [dict(r, guild_id=str(gid)) for r in archive if isinstance(r, dict)]
            if recs and self.closed_col is not None:
                self.closed_col.insert_many(recs)
            self._normalize(g)
            self.guild_col.replace_one({"_id": str(gid)}, g, upsert=True)
            loaded[str(gid)] = g
        return loaded

    async def load(self):
        if self._flush_lock is None:
            self._flush_lock = asyncio.Lock()
        # لو فشل التحميل بنرمي الخطأ عشان ما نكتبش بيانات فاضية فوق البيانات الحقيقية
        loaded = await asyncio.to_thread(self._load_sync)
        for g in loaded.values():
            self._normalize(g)
        self.guilds = loaded
        log.info("تم تحميل بيانات %d سيرفر", len(loaded))

    # ---------- وصول ----------
    def guild(self, gid: Any) -> dict:
        gid = str(gid)
        g = self.guilds.get(gid)
        if g is None:
            g = self._normalize({})
            self.guilds[gid] = g
        return g

    # ---------- حفظ ----------
    def _write(self, gid: str, snapshot: dict):
        self.guild_col.replace_one({"_id": gid}, snapshot, upsert=True)

    def mark_dirty(self, gid: Any):
        self._dirty.add(str(gid))
        self._schedule()

    def _schedule(self, delay: float = 1.0):
        if self._flush_task is not None and not self._flush_task.done():
            return
        self._flush_task = asyncio.get_running_loop().create_task(self._delayed_flush(delay))

    async def _delayed_flush(self, delay: float):
        await asyncio.sleep(delay)
        for _ in range(5):
            await self.flush()
            if not self._dirty:
                return
            await asyncio.sleep(5)

    async def flush(self, final: bool = False):
        if self._flush_lock is None:
            self._flush_lock = asyncio.Lock()
        async with self._flush_lock:
            gids = list(self._dirty)
            self._dirty.clear()
            for gid in gids:
                g = self.guilds.get(gid)
                if g is None or self.guild_col is None:
                    continue
                snapshot = copy.deepcopy(g)
                try:
                    await asyncio.to_thread(self._write, gid, snapshot)
                except Exception:
                    log.exception("فشل حفظ بيانات السيرفر %s (هيتعاد المحاولة)", gid)
                    self._dirty.add(gid)

    def archive(self, record: dict):
        """حفظ تذكرة مغلقة في collection منفصل (في الخلفية)."""
        if self.closed_col is None:
            return
        data = copy.deepcopy(record)

        async def _go():
            try:
                await asyncio.to_thread(self.closed_col.insert_one, data)
            except Exception:
                log.exception("فشل أرشفة التذكرة")

        task = asyncio.get_running_loop().create_task(_go())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)


STORE = TicketStore()


# ==============================================================================
# 🔎 دوال البيانات المشتركة
# ==============================================================================
def find_panel(g: dict, pid: str) -> tuple[Optional[str], Optional[dict]]:
    for name, panel in g["panels"].items():
        if panel.get("pid") == pid:
            return name, panel
    return None, None


def get_ticket(interaction: discord.Interaction) -> tuple[dict, Optional[dict]]:
    g = STORE.guild(interaction.guild.id)
    return g, g["active_tickets"].get(str(interaction.channel.id))


def member_is_staff(member: discord.Member, ticket: dict) -> bool:
    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild:
        return True
    role_ids = {int(r) for r in ticket.get("support_role_ids", [])}
    higher = ticket.get("higher_support_role_id")
    if higher:
        role_ids.add(int(higher))
    return any(r.id in role_ids for r in member.roles)


def can_delete(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.manage_channels or perms.administrator


def get_quick_replies(g: dict, t: dict) -> list[str]:
    if "quick_replies" in t:
        return t.get("quick_replies") or []
    # تذاكر قديمة قبل التحديث
    panel = g["panels"].get(t.get("panel"), {})
    for sec in panel.get("sections", {}).values():
        if sec.get("label") == t.get("section"):
            return sec.get("quick_replies") or []
    return []


def ticket_number(t: dict, channel: Optional[discord.abc.GuildChannel] = None) -> str:
    if t.get("number"):
        return str(t["number"])
    if channel is not None:
        m = re.search(r"(\d+)$", channel.name)
        if m:
            return m.group(1)
    return "1"


def staff_stat(g: dict, uid: Any) -> dict:
    return g["staff_stats"].setdefault(str(uid), {"claimed": 0, "total_stars": 0, "ratings_count": 0})


def set_claimer(g: dict, t: dict, new_id: Optional[int]):
    old = t.get("claimed_by")
    if old:
        s = staff_stat(g, old)
        s["claimed"] = max(0, s.get("claimed", 0) - 1)
    if new_id:
        t["claimed_by"] = new_id
        staff_stat(g, new_id)["claimed"] += 1
    else:
        t.pop("claimed_by", None)
    t["last_activity"] = now_ts()


def retire_ticket(guild_id: Any, channel_id: Any, reason: str):
    """نقل تذكرة نشطة للأرشيف (مثلاً لو الروم اتحذف يدوياً)."""
    g = STORE.guild(guild_id)
    t = g["active_tickets"].pop(str(channel_id), None)
    if not t:
        return
    t["status"] = "مغلقة ومحذوفة"
    t["close_reason"] = reason
    t["closed_at"] = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    STORE.mark_dirty(guild_id)
    STORE.archive(dict(t, guild_id=str(guild_id), channel_id=str(channel_id)))


def build_panel_embed(name: str, p: dict) -> discord.Embed:
    embed = discord.Embed(
        title=p.get("title"),
        description=p.get("desc"),
        color=parse_color(p.get("color_hex")),
        timestamp=discord.utils.utcnow(),
    )
    if p.get("image_url"):
        embed.set_image(url=p["image_url"])
    if p.get("thumbnail_url"):
        embed.set_thumbnail(url=p["thumbnail_url"])
    embed.set_footer(text=clip(p.get("custom_footer_info") or name, 2048))
    return embed


def strip_embed_media(embed: discord.Embed) -> discord.Embed:
    """نسخة من الإيمبد من غير صور (احتياطي لو رابط الصورة بايظ)."""
    fb = embed.copy()
    fb.set_image(url=None)
    fb.set_thumbnail(url=None)
    footer_text = embed.footer.text if embed.footer and embed.footer.text else "نظام إدارة التذاكر"
    fb.set_footer(text=footer_text)
    return fb


# ==============================================================================
# 🛡️ Views/Modals آمنة (أي خطأ بيتسجل ويتبلغ للمستخدم بدل "التفاعل فشل")
# ==============================================================================
class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction)


class ChoiceView(SafeView):
    """View عام بأزرار: كل عنصر = (النص, الإيموجي, الستايل, الدالة)."""

    def __init__(self, options: list[tuple[str, Optional[str], discord.ButtonStyle, ButtonCB]], timeout: float = WIZARD_TIMEOUT):
        super().__init__(timeout=timeout)
        for label, emoji, style, cb in options:
            btn = discord.ui.Button(label=label, emoji=emoji, style=style)
            btn.callback = cb
            self.add_item(btn)


async def send_step(interaction: discord.Interaction, title: str, description: str, options):
    await respond(interaction, embed=discord.Embed(title=title, description=description, color=COLOR_DARK),
                  view=ChoiceView(options), ephemeral=True)


# ==============================================================================
# ⭐ نظام التقييم والحذف السريع
# ==============================================================================
class TicketRatingView(SafeView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.danger, custom_id="rate_1_v7")
    async def rate_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 1)

    @discord.ui.button(label="⭐⭐ 2", style=discord.ButtonStyle.danger, custom_id="rate_2_v7")
    async def rate_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 2)

    @discord.ui.button(label="⭐⭐⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rate_3_v7")
    async def rate_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 3)

    @discord.ui.button(label="⭐⭐⭐⭐ 4", style=discord.ButtonStyle.success, custom_id="rate_4_v7")
    async def rate_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 4)

    @discord.ui.button(label="⭐⭐⭐⭐⭐ 5", style=discord.ButtonStyle.success, custom_id="rate_5_v7")
    async def rate_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 5)

    async def handle_rating_and_delete(self, interaction: discord.Interaction, stars: int):
        g = STORE.guild(interaction.guild.id)
        chan = interaction.channel
        pending = g["pending_ratings"].get(str(chan.id))

        if not pending:
            await respond(interaction, embed=err_embed("التقييم ده انتهت صلاحيته أو التذكرة اتحذفت بالفعل."), ephemeral=True)
            return
        if interaction.user.id != pending.get("user_id"):
            await respond(interaction, embed=err_embed("التقييم مخصص لصاحب التذكرة فقط.", "❌ تنبيه"), ephemeral=True)
            return
        if pending.get("rated"):
            await respond(interaction, embed=err_embed("تم تسجيل تقييمك بالفعل.", "⚠️ تنبيه"), ephemeral=True)
            return

        pending["rated"] = True  # قبل أي await، عشان الضغط المزدوج ما يتحسبش مرتين
        claimer_id = pending.get("claimed_by")
        if claimer_id:
            s = staff_stat(g, claimer_id)
            s["total_stars"] += stars
            s["ratings_count"] += 1
        STORE.mark_dirty(interaction.guild.id)

        done_view = TicketRatingView()
        for child in done_view.children:
            child.disabled = True
        embed = discord.Embed(
            title="شكراً لتقييمك",
            description=f"تم تسجيل تقييمك ({'⭐' * stars}). سيتم حذف التذكرة خلال 3 ثوانٍ...",
            color=COLOR_GREEN,
        )
        try:
            await interaction.response.edit_message(embed=embed, view=done_view)
        except discord.HTTPException:
            log.warning("تعذر تعديل رسالة التقييم", exc_info=True)

        await asyncio.sleep(3)
        await delete_ticket_channels(interaction.guild, chan, pending)
        g["pending_ratings"].pop(str(chan.id), None)
        STORE.mark_dirty(interaction.guild.id)


async def delete_ticket_channels(guild: discord.Guild, channel: discord.abc.GuildChannel, data: dict):
    voice_id = data.get("temp_voice_id")
    if voice_id:
        v_chan = guild.get_channel(int(voice_id))
        if v_chan:
            try:
                await v_chan.delete(reason="حذف تذكرة")
            except discord.HTTPException:
                log.warning("تعذر حذف الروم الصوتي", exc_info=True)
    try:
        await channel.delete(reason="حذف تذكرة")
    except discord.HTTPException:
        log.warning("تعذر حذف روم التذكرة", exc_info=True)


# ==============================================================================
# 📝 نافذة كتابة سبب الحذف للإداري
# ==============================================================================
async def build_transcript(channel: discord.TextChannel, number: str) -> discord.File:
    lines = []
    try:
        async for msg in channel.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            body = msg.content or ""
            if msg.attachments:
                body += " " + " ".join(a.url for a in msg.attachments)
            if not body.strip() and msg.embeds:
                e = msg.embeds[0]
                body = "[Embed] " + clip(e.title or e.description or "", 100)
            lines.append(f"[{ts}] {msg.author.name}: {body}".rstrip())
    except discord.HTTPException:
        log.warning("تعذر قراءة تاريخ الرسائل للـ transcript", exc_info=True)
    text = f"=== TRANSCRIPT: {channel.name} ===\n" + "\n".join(lines)
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=f"transcript-{number}.txt")


class DeleteReasonModal(SafeModal, title="🗑️ سبب حذف التذكرة"):
    reason_box = discord.ui.TextInput(
        label="سبب الإغلاق / الحذف",
        placeholder="اكتب سبب حذف التذكرة هنا...",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()  # قراءة الرسائل بتاخد وقت
        reason_text = self.reason_box.value.strip()
        channel = interaction.channel
        guild = interaction.guild
        g = STORE.guild(guild.id)

        ticket = g["active_tickets"].pop(str(channel.id), None)
        if ticket is None:
            await interaction.followup.send(embed=err_embed("التذكرة دي مش مسجلة (يمكن اتحذفت بالفعل)."), ephemeral=True)
            return

        number = ticket_number(ticket, channel)
        ticket["status"] = "مغلقة ومحذوفة"
        ticket["closed_by"] = interaction.user.id
        ticket["close_reason"] = reason_text
        ticket["closed_at"] = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        creator_id = ticket.get("user_id") or interaction.user.id
        g["pending_ratings"][str(channel.id)] = {
            "user_id": creator_id,
            "claimed_by": ticket.get("claimed_by"),
            "section": ticket.get("section"),
            "temp_voice_id": ticket.get("temp_voice_id"),
            "created": now_ts(),
            "rated": False,
        }
        STORE.mark_dirty(guild.id)
        STORE.archive(dict(ticket, guild_id=str(guild.id), channel_id=str(channel.id)))

        # سجل التذكرة في روم اللوج
        log_channel_id = g.get("log_channel_id")
        log_chan = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if log_chan:
            claimer_id = ticket.get("claimed_by")
            log_embed = discord.Embed(title="📁 سجل تذكرة مغلقة", color=COLOR_RED, timestamp=discord.utils.utcnow())
            log_embed.add_field(name="🎫 التذكرة", value=f"`{channel.name}`", inline=True)
            log_embed.add_field(name="📂 القسم", value=f"`{clip(ticket.get('section'), 100)}`", inline=True)
            log_embed.add_field(name="👤 صاحب التذكرة", value=f"<@{creator_id}>", inline=True)
            log_embed.add_field(name="💼 المشرف", value=f"<@{claimer_id}>" if claimer_id else "مفيش", inline=True)
            log_embed.add_field(name="🗑️ اتنفت بواسطة", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="📌 سبب الحذف", value=f"```{clip(reason_text, 900)}```", inline=False)
            try:
                file = await build_transcript(channel, number)
                await log_chan.send(embed=log_embed, file=file)
            except discord.HTTPException:
                log.warning("تعذر إرسال سجل التذكرة لروم اللوج", exc_info=True)

        embed_reason_msg = discord.Embed(
            title="🗑️ تقرر حذف التذكرة",
            description=f"**السبب:** {reason_text}\n**بواسطة:** {interaction.user.mention}",
            color=COLOR_RED,
        )
        embed_rate = discord.Embed(
            title="⭐ تقييم الخدمة",
            description=f"يا <@{creator_id}> يرجى تقييم مستوى الدعم الفني قبل إغلاق التذكرة نهائياً:",
            color=COLOR_DARK,
        )
        await interaction.followup.send(embed=embed_reason_msg)
        await channel.send(embed=embed_rate, view=TicketRatingView())


# ==============================================================================
# 🔒 خيارات قفل/فتح التذكرة
# ==============================================================================
class CloseConfirmationView(SafeView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إعادة فتح", style=discord.ButtonStyle.success, emoji="🔓", custom_id="confirm_reopen_ticket_btn_v7")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return
        if not (interaction.user.id == t.get("user_id") or member_is_staff(interaction.user, t)):
            await respond(interaction, embed=err_embed("معندكش صلاحية لإعادة فتح التذكرة."), ephemeral=True)
            return
        if t.get("status") != STATUS_CLOSED:
            await respond(interaction, embed=err_embed("التذكرة مفتوحة بالفعل.", "⚠️ تنبيه"), ephemeral=True)
            return

        age = (discord.utils.utcnow() - interaction.message.created_at).total_seconds()
        if age < REOPEN_DELAY:
            remaining = round(REOPEN_DELAY - age, 1)
            await respond(interaction, content=f"⏳ يجب الانتظار لمدة {remaining} ثوانٍ إضافية قبل إمكانية فتح التذكرة مرة أخرى.", ephemeral=True)
            return

        t["status"] = STATUS_OPEN
        t["last_activity"] = now_ts()
        STORE.mark_dirty(interaction.guild.id)
        await interaction.response.defer()

        creator = await get_member(interaction.guild, t.get("user_id"))
        if creator:
            try:
                await interaction.channel.set_permissions(creator, send_messages=True, view_channel=True)
            except discord.HTTPException:
                log.warning("تعذر استرجاع صلاحيات صاحب التذكرة", exc_info=True)

        embed = discord.Embed(
            title="🔓 تم إعادة فتح التذكرة",
            description=f"تم فتح التذكرة بواسطة {interaction.user.mention}.",
            color=COLOR_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.followup.send(embed=embed)
        try:
            await interaction.message.delete()  # رسالة الإغلاق القديمة ما بقاش ليها لازمة
        except discord.HTTPException:
            pass

    @discord.ui.button(label="حذف التذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="confirm_delete_ticket_btn_v7")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return
        if interaction.user.id == t.get("user_id"):
            await respond(interaction, embed=err_embed("صاحب التذكرة يقدر يقفلها بس، الحذف للإدارة فقط.", "❌ غير مسموح"), ephemeral=True)
            return
        if not can_delete(interaction.user):
            await respond(interaction, embed=err_embed("معندكش صلاحية لحذف التذكرة."), ephemeral=True)
            return
        await interaction.response.send_modal(DeleteReasonModal())


# ==============================================================================
# ⚡ الردود السريعة (للمشرفين وفريق الدعم فقط)
# ==============================================================================
class QuickRepliesSelect(discord.ui.Select):
    def __init__(self, quick_replies: Optional[list] = None):
        options = []
        for idx, text in enumerate((quick_replies or [])[:25]):
            if str(text).strip():
                options.append(discord.SelectOption(label=clip(text, 95), emoji="⚡", value=f"qr_custom_{idx}"))
        if not options:
            options.append(discord.SelectOption(label="مفيش ردود سريعة جاهزة", value="none", emoji="❌"))
        super().__init__(
            placeholder="⚡ اختر رد سريع لارسال...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="quick_replies_select_v7",
        )

    async def callback(self, interaction: discord.Interaction):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return
        if t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة، لا يمكن استخدام الردود السريعة حالياً.", ephemeral=True)
            return
        if not member_is_staff(interaction.user, t):
            await respond(interaction, content="❌ الإدارة فقط من تستطيع استخدام هذه الردود.", ephemeral=True)
            return

        val = self.values[0]
        replies = get_quick_replies(g, t)
        if val == "none" or not replies:
            await respond(interaction, content="❌ مفيش ردود سريعة مضافة هنا.", ephemeral=True)
            return

        text = "أهلاً بك."
        m = re.match(r"qr_custom_(\d+)$", val)
        if m and int(m.group(1)) < len(replies):
            text = replies[int(m.group(1))]

        await interaction.channel.send(embed=discord.Embed(description=clip(text, 4000), color=COLOR_DARK))
        t["last_activity"] = now_ts()
        STORE.mark_dirty(interaction.guild.id)
        await respond(interaction, embed=ok_embed("✅ تم الإرسال", "تم إرسال الرد السريع."), ephemeral=True)

        # رجّع القائمة لحالتها الطبيعية (عشان تقدر تختار نفس الرد تاني)
        try:
            await interaction.message.edit(view=build_inside_view(g, t))
        except discord.HTTPException:
            pass


# ==============================================================================
# 🔄 نقل التذكرة لمشرف تاني
# ==============================================================================
class ClaimSwitchView(SafeView):
    def __init__(self, channel_id: str):
        super().__init__(timeout=60)
        self.channel_id = channel_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="اختر المشرف الجديد...", min_values=1, max_values=1)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        g = STORE.guild(interaction.guild.id)
        t = g["active_tickets"].get(self.channel_id)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return

        target = select.values[0]
        member = target if isinstance(target, discord.Member) else await get_member(interaction.guild, target.id)
        if member is None or member.bot:
            await respond(interaction, content="❌ مفيش عضو صالح بالاختيار ده.", ephemeral=True)
            return
        if member.id == t.get("user_id"):
            await respond(interaction, content="❌ مينفعش تحول التذكرة لصاحبها.", ephemeral=True)
            return
        if not member_is_staff(member, t):
            await respond(interaction, content="❌ العضو ده مش من فريق الدعم الخاص بالقسم ده.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        old_mention = interaction.user.mention
        set_claimer(g, t, member.id)
        STORE.mark_dirty(interaction.guild.id)
        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        except discord.HTTPException:
            log.warning("تعذر إعطاء صلاحيات للمشرف الجديد", exc_info=True)

        embed = discord.Embed(
            title="🔄 تم تحويل التذكرة",
            description=f"تم نقل متابعة التذكرة من {old_mention} إلى {member.mention}.",
            color=COLOR_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ تم نقل التذكرة بنجاح.", ephemeral=True)


# ==============================================================================
# 🎛️ أزرار التحكم داخل التذكرة
# ==============================================================================
class AddMemberModal(SafeModal, title="➕ إضافة عضو للتذكرة"):
    member_box = discord.ui.TextInput(label="أيدي العضو (User ID)", placeholder="اكتب أيدي العضو هنا...", max_length=30, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        ids = parse_ids(self.member_box.value)
        if not ids:
            await respond(interaction, embed=err_embed("يرجى كتابة أيدي صحيح!"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        g, t = get_ticket(interaction)
        if not t or t.get("status") == STATUS_CLOSED:
            await interaction.followup.send(embed=err_embed("التذكرة مغلقة أو غير مسجلة."), ephemeral=True)
            return

        member = await get_member(interaction.guild, ids[0])
        if not member:
            await interaction.followup.send(embed=err_embed("العضو ده مش موجود في السيرفر!"), ephemeral=True)
            return

        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        except discord.HTTPException:
            await interaction.followup.send(embed=err_embed("حصلت مشكلة وأنا بغير الصلاحيات."), ephemeral=True)
            return

        t["last_activity"] = now_ts()
        STORE.mark_dirty(interaction.guild.id)
        await interaction.channel.send(embed=ok_embed("✅ تم الإضافة", f"تم إضافة {member.mention} للتذكرة بنجاح."))
        await interaction.followup.send("✅ تمت الإضافة.", ephemeral=True)


class TicketInsideView(SafeView):
    def __init__(self, quick_replies: Optional[list] = None, show_escalate: bool = True, with_select: bool = False):
        super().__init__(timeout=None)
        if not show_escalate:
            self.remove_item(self.escalate_ticket)
        if quick_replies or with_select:
            self.add_item(QuickRepliesSelect(quick_replies))

    # ---------- استلام ----------
    @discord.ui.button(label="استلام", style=discord.ButtonStyle.primary, emoji="💼", custom_id="claim_ticket_v7_btn", row=1)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي غير مسجلة في النظام."), ephemeral=True)
            return
        if t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة، لا يمكن استلامها.", ephemeral=True)
            return
        if interaction.user.id == t.get("user_id"):
            await respond(interaction, embed=err_embed("متقدرش تستلم تذكرتك بنفسك!", "❌ غير مسموح"), ephemeral=True)
            return
        if not member_is_staff(interaction.user, t):
            await respond(interaction, embed=err_embed("الزر ده خاص بفريق الدعم بس.", "❌ غير مسموح"), ephemeral=True)
            return

        old_claimer_id = t.get("claimed_by")
        if old_claimer_id == interaction.user.id:
            embed_ask = discord.Embed(title="💼 حالة التذكرة", description="أنت مستلم التذكرة دي بالفعل. حابب تعمل ايه؟", color=COLOR_ORANGE)
            channel_id = str(interaction.channel.id)

            async def do_unclaim(i: discord.Interaction):
                gg = STORE.guild(i.guild.id)
                tt = gg["active_tickets"].get(channel_id)
                if not tt or tt.get("claimed_by") != i.user.id:
                    await respond(i, content="❌ التذكرة دي مبقتش باسمك.", ephemeral=True)
                    return
                set_claimer(gg, tt, None)
                STORE.mark_dirty(i.guild.id)
                embed_res = discord.Embed(title="🔓 تم إلغاء الاستلام", description=f"قام {i.user.mention} بترك استلام التذكرة وأصبحت متاحة للجميع.", color=COLOR_RED)
                await i.channel.send(embed=embed_res)
                await respond(i, content="✅ تم إلغاء استلامك للتذكرة بنجاح.", ephemeral=True)

            async def do_switch(i: discord.Interaction):
                embed_switch = discord.Embed(title="🔄 تحويل التذكرة", description="اختر المشرف اللي عاوز تحول التذكرة ليه:", color=COLOR_DARK)
                await respond(i, embed=embed_switch, view=ClaimSwitchView(channel_id), ephemeral=True)

            view = ChoiceView([
                ("إلغاء الاستلام", "🔓", discord.ButtonStyle.danger, do_unclaim),
                ("تحويل لمشرف", "🔄", discord.ButtonStyle.primary, do_switch),
            ], timeout=30)
            await respond(interaction, embed=embed_ask, view=view, ephemeral=True)
            return

        await interaction.response.defer()
        set_claimer(g, t, interaction.user.id)
        STORE.mark_dirty(interaction.guild.id)
        try:
            await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)
        except discord.HTTPException:
            log.warning("تعذر إعطاء صلاحيات للمشرف المستلم", exc_info=True)

        if old_claimer_id:
            embed = discord.Embed(
                title="🔄 تم تغيير المشرف",
                description=f"تم نقل التذكرة من <@{old_claimer_id}> إلى {interaction.user.mention}.",
                color=COLOR_GREEN,
                timestamp=discord.utils.utcnow(),
            )
        else:
            embed = discord.Embed(
                title="💼 تم استلام التذكرة",
                description=f"المشرف المسؤول: {interaction.user.mention}",
                color=COLOR_GREEN,
                timestamp=discord.utils.utcnow(),
            )
        await interaction.followup.send(embed=embed)

    # ---------- إضافة عضو ----------
    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="add_member_ticket_btn_v7", row=2)
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return
        if t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة، لا يمكن إضافة أعضاء.", ephemeral=True)
            return
        if interaction.user.id == t.get("user_id"):
            await respond(interaction, embed=err_embed("صاحب التذكرة ميعرفش يضيف أعضاء للتذكرة.", "❌ غير مسموح"), ephemeral=True)
            return
        if not member_is_staff(interaction.user, t):
            await respond(interaction, embed=err_embed("إضافة الأعضاء لفريق الدعم بس.", "❌ غير مسموح"), ephemeral=True)
            return
        await interaction.response.send_modal(AddMemberModal())

    # ---------- غرفة صوتية ----------
    @discord.ui.button(label="غرفة صوتية", style=discord.ButtonStyle.success, emoji="🔊", custom_id="create_temp_voice_btn_v7", row=2)
    async def create_temp_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, embed=err_embed("التذكرة دي مش مسجلة في النظام."), ephemeral=True)
            return
        if t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة، لا يمكن إنشاء غرفة صوتية.", ephemeral=True)
            return
        if not member_is_staff(interaction.user, t):
            await respond(interaction, embed=err_embed("الغرفة الصوتية بيفتحها فريق الدعم بس.", "❌ غير مسموح"), ephemeral=True)
            return

        guild = interaction.guild
        existing_id = t.get("temp_voice_id")
        if existing_id:
            existing = guild.get_channel(int(existing_id))
            if existing:
                await respond(interaction, content=f"⚠️ فيه غرفة صوتية للتذكرة دي بالفعل: {existing.mention}", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True),
        }
        creator = await get_member(guild, t.get("user_id"))
        if creator:
            overwrites[creator] = discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)
        for r_id in t.get("support_role_ids", []):
            role = guild.get_role(int(r_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)

        try:
            voice_chan = await guild.create_voice_channel(
                name=f"🎫・Voice・{ticket_number(t, interaction.channel)}",
                category=interaction.channel.category,
                overwrites=overwrites,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(embed=err_embed(f"معرفتش أعمل الروم الصوتي، تأكد من صلاحيات البوت: {e}"), ephemeral=True)
            return

        t["temp_voice_id"] = str(voice_chan.id)
        t["last_activity"] = now_ts()
        STORE.mark_dirty(guild.id)
        embed = discord.Embed(title="🔊 تم إنشاء الفويس", description=f"تم عمل روم صوتي خاص بالتذكرة: {voice_chan.mention}", color=COLOR_GREEN)
        await interaction.channel.send(embed=embed)
        await interaction.followup.send("✅ تم.", ephemeral=True)

    # ---------- تنبيه ----------
    @discord.ui.button(label="تنبيه", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="smart_ping_ticket_btn_v7", row=2)
    async def smart_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t or t.get("status") == STATUS_CLOSED:
            await respond(interaction, embed=err_embed("التذكرة مغلقة أو غير متاحة للتنبيه."), ephemeral=True)
            return
        is_creator = interaction.user.id == t.get("user_id")
        if not (is_creator or member_is_staff(interaction.user, t)):
            await respond(interaction, embed=err_embed("التنبيه لصاحب التذكرة وفريق الدعم بس."), ephemeral=True)
            return
        wait = cooldown_remaining("ping", interaction.channel.id, PING_COOLDOWN)
        if wait:
            await respond(interaction, content=f"⏳ استنى {int(wait) + 1} ثانية قبل التنبيه تاني.", ephemeral=True)
            return

        t["last_activity"] = now_ts()
        STORE.mark_dirty(interaction.guild.id)
        if is_creator:
            role_ids = t.get("support_role_ids", [])
            mentions = " ".join(f"<@&{r}>" for r in role_ids) if role_ids else "الدعم الفني"
            content_msg = f"🔔 تنبيه من {interaction.user.mention} لـ {mentions}: يرجى الرد في أقرب وقت."
            ok = ok_embed("✅ تم التنبيه", "تم إرسال تنبيه لفريق الدعم.")
        else:
            content_msg = f"🔔 تنبيه من الإدارة لـ <@{t.get('user_id')}>: يرجى الرد لمتابعة تذكرتك."
            ok = ok_embed("✅ تم التنبيه", "تم إرسال التنبيه للعضو.")
        await interaction.channel.send(content=content_msg)
        await respond(interaction, embed=ok, ephemeral=True)

    # ---------- تصعيد ----------
    @discord.ui.button(label="تصعيد للإدارة", style=discord.ButtonStyle.primary, emoji="👑", custom_id="escalate_ticket_btn_v7", row=3)
    async def escalate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t or t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة.", ephemeral=True)
            return
        if not (interaction.user.id == t.get("user_id") or member_is_staff(interaction.user, t)):
            await respond(interaction, embed=err_embed("التصعيد لصاحب التذكرة وفريق الدعم بس."), ephemeral=True)
            return
        wait = cooldown_remaining("escalate", interaction.channel.id, PING_COOLDOWN)
        if wait:
            await respond(interaction, content=f"⏳ استنى {int(wait) + 1} ثانية قبل التصعيد تاني.", ephemeral=True)
            return

        t["last_activity"] = now_ts()
        STORE.mark_dirty(interaction.guild.id)
        higher = t.get("higher_support_role_id")
        if higher:
            mentions = f"<@&{higher}>"
        else:
            role_ids = t.get("support_role_ids", [])
            mentions = " ".join(f"<@&{r}>" for r in role_ids) if role_ids else "الإدارة العليا"
        await interaction.channel.send(content=f"👑 **طلب مسؤول أعلى:** قام {interaction.user.mention} بطلب إشراف أعلى ({mentions}).")
        await respond(interaction, embed=ok_embed("✅ تم التصعيد", "تم إرسال إشعار للإدارة العليا."), ephemeral=True)

    # ---------- إغلاق ----------
    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_v7_btn", row=3)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        g, t = get_ticket(interaction)
        if not t:
            await respond(interaction, content="❌ التذكرة غير مسجلة.", ephemeral=True)
            return
        if t.get("status") == STATUS_CLOSED:
            await respond(interaction, content="❌ التذكرة مغلقة بالفعل.", ephemeral=True)
            return
        if not (interaction.user.id == t.get("user_id") or member_is_staff(interaction.user, t)):
            await respond(interaction, embed=err_embed("إغلاق التذكرة لصاحبها وفريق الدعم بس."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        t["status"] = STATUS_CLOSED
        t["last_activity"] = now_ts()

        creator = await get_member(interaction.guild, t.get("user_id"))
        if creator:
            try:
                await interaction.channel.set_permissions(creator, send_messages=False)
            except discord.HTTPException:
                log.warning("تعذر سحب صلاحية الكتابة من صاحب التذكرة", exc_info=True)

        voice_id = t.pop("temp_voice_id", None)
        if voice_id:
            v_chan = interaction.guild.get_channel(int(voice_id))
            if v_chan:
                try:
                    await v_chan.delete(reason="إغلاق التذكرة")
                except discord.HTTPException:
                    log.warning("تعذر حذف الروم الصوتي", exc_info=True)
        STORE.mark_dirty(interaction.guild.id)

        embed_close = discord.Embed(title="🔒 تم إغلاق التذكرة وحذف الروم الصوتي تلقائياً", description="اختر الخيار المناسب لتنفيذه:", color=COLOR_DARK)
        await interaction.channel.send(embed=embed_close, view=CloseConfirmationView())
        await interaction.followup.send("✅ تم إغلاق التذكرة بنجاح.", ephemeral=True)


def build_inside_view(g: dict, t: dict) -> TicketInsideView:
    return TicketInsideView(quick_replies=get_quick_replies(g, t), show_escalate=bool(t.get("higher_support_role_id")))


# ==============================================================================
# 📋 اختيار القسم وإنشاء التذكرة
# ==============================================================================
class PanelSelect(discord.ui.Select):
    def __init__(self, pid: str, sections: dict):
        options = []
        for key, data in list(sections.items())[:25]:
            options.append(discord.SelectOption(
                label=clip(data.get("label"), 100) or "قسم",
                description=clip(data.get("description"), 100) if data.get("description") else None,
                emoji=parse_emoji(data.get("emoji")),
                value=key,
            ))
        if not options:
            options = [discord.SelectOption(label="مفيش أقسام متاحة حالياً", value="none")]
        super().__init__(placeholder="📂 اختر القسم المناسب لطلبك...", min_values=1, max_values=1, options=options, custom_id=f"tk:sel:{pid}")
        self.pid = pid

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await respond(interaction, content="❌ مفيش أقسام شغالة في البانل ده.", ephemeral=True)
            return
        await open_section(interaction, self.pid, self.values[0])
        # رجّع القائمة لحالتها (عشان نفس القسم يتختار تاني)
        try:
            await interaction.message.edit(view=PanelControlView(interaction.guild.id, self.pid))
        except discord.HTTPException:
            pass


async def open_section(interaction: discord.Interaction, pid: str, key: str):
    g = STORE.guild(interaction.guild.id)
    _, panel = find_panel(g, pid)
    if not panel:
        await respond(interaction, embed=err_embed("البانل ده اتمسح من البيانات."), ephemeral=True)
        return
    sec = panel["sections"].get(key)
    if not sec:
        await respond(interaction, embed=err_embed("القسم ده مش موجود حالياً."), ephemeral=True)
        return
    questions = sec.get("custom_questions")
    if questions:
        await interaction.response.send_modal(CustomMultiQuestionModal(pid, key, questions))
    else:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await create_user_ticket_execution(interaction, pid, key, [])


class CustomMultiQuestionModal(SafeModal):
    def __init__(self, pid: str, section_key: str, questions: list):
        super().__init__(title="📝 الإجابة على الأسئلة")
        self.pid = pid
        self.section_key = section_key
        self.inputs: list[discord.ui.TextInput] = []
        for q_text in questions[:5]:
            box = discord.ui.TextInput(
                label=clip(q_text, 45),
                placeholder="اكتب إجابتك هنا...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True,
            )
            self.inputs.append(box)
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        answers = [box.value.strip() for box in self.inputs]
        await create_user_ticket_execution(interaction, self.pid, self.section_key, answers)


_creating: set[tuple[int, int]] = set()


async def create_user_ticket_execution(interaction: discord.Interaction, pid: str, section_key: str, answers_list: list):
    """لازم يتعمل defer للتفاعل قبل ما ندخل هنا."""
    lock_key = (interaction.guild.id, interaction.user.id)
    if lock_key in _creating:
        await interaction.followup.send(embed=err_embed("استنى شوية، التذكرة بتتعمل دلوقتي..."), ephemeral=True)
        return
    _creating.add(lock_key)
    try:
        await _create_ticket(interaction, pid, section_key, answers_list)
    except Exception:
        log.exception("فشل إنشاء التذكرة")
        try:
            await interaction.followup.send(embed=err_embed("حصل خطأ غير متوقع وأنا بعمل التذكرة، حاول تاني."), ephemeral=True)
        except discord.HTTPException:
            pass
    finally:
        _creating.discard(lock_key)


async def _create_ticket(interaction: discord.Interaction, pid: str, section_key: str, answers_list: list):
    guild = interaction.guild
    user = interaction.user
    g = STORE.guild(guild.id)

    panel_name, panel = find_panel(g, pid)
    if not panel:
        await interaction.followup.send(embed=err_embed("البانل ده اتمسح من البيانات."), ephemeral=True)
        return
    section = panel["sections"].get(section_key)
    if not section:
        await interaction.followup.send(embed=err_embed("القسم ده مش موجود حالياً."), ephemeral=True)
        return

    # منع تذكرتين مفتوحتين لنفس العضو (وتنضيف التذاكر اللي رومها اتحذف)
    for ch_id, t in list(g["active_tickets"].items()):
        if t.get("user_id") != user.id or t.get("status") == STATUS_CLOSED:
            continue
        existing = guild.get_channel(int(ch_id))
        if existing:
            embed_dup = discord.Embed(
                title="❌ عندك تذكرة مفتوحة",
                description=f"عندك تذكرة شغال فيها بالفعل: {existing.mention}\nاقفل القديمة الأول عشان تفتح جديدة.",
                color=COLOR_RED,
            )
            await interaction.followup.send(embed=embed_dup, ephemeral=True)
            return
        retire_ticket(guild.id, ch_id, "الروم اتحذف يدوياً")

    # الكاتيجوري: القسم ← البانل ← كاتيجوري افتراضي موجودة ← إنشاء واحدة (مرة واحدة بس)
    category = None
    cat_id = section.get("category_id") or panel.get("category_id")
    if cat_id and str(cat_id).isdigit():
        ch = guild.get_channel(int(cat_id))
        if isinstance(ch, discord.CategoryChannel):
            category = ch
    if category is None:
        category = discord.utils.get(guild.categories, name=DEFAULT_CATEGORY_NAME)
    if category is None and guild.me.guild_permissions.manage_channels:
        try:
            category = await guild.create_category(DEFAULT_CATEGORY_NAME)
        except discord.HTTPException:
            category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
    }
    support_role_ids = [int(r) for r in section.get("support_role_ids", [])]
    support_roles = [r for r in (guild.get_role(r_id) for r_id in support_role_ids) if r]
    for role in support_roles:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    higher_role_id = section.get("higher_support_role_id")
    if higher_role_id:
        higher_role = guild.get_role(int(higher_role_id))
        if higher_role:
            overwrites[higher_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    g["ticket_counter"] += 1
    number = g["ticket_counter"]
    try:
        ticket_channel = await guild.create_text_channel(name=f"🎫・{number}", category=category, overwrites=overwrites)
    except discord.HTTPException as e:
        if g["ticket_counter"] == number:
            g["ticket_counter"] -= 1
        await interaction.followup.send(embed=err_embed(f"تأكد من صلاحيات البوت (Manage Channels): {e}"), ephemeral=True)
        return

    now = discord.utils.utcnow()
    created_str = now.strftime("%A, %B %d, %Y %I:%M %p")
    quick_replies = [q for q in (section.get("quick_replies") or []) if str(q).strip()]
    g["active_tickets"][str(ticket_channel.id)] = {
        "user_id": user.id,
        "panel": panel_name,
        "panel_id": pid,
        "section": section["label"],
        "section_key": section_key,
        "number": number,
        "support_role_ids": support_role_ids,
        "higher_support_role_id": higher_role_id,
        "quick_replies": quick_replies,
        "created_at": created_str,
        "last_activity": now_ts(),
        "status": STATUS_OPEN,
    }
    STORE.mark_dirty(guild.id)

    staff_mentions = " | ".join(r.mention for r in support_roles) if support_roles else "فريق الدعم"
    embed = discord.Embed(color=parse_color(panel.get("color_hex")))
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 [ ] : مالك التذكرة", value=f"{user.mention}\n\u200b", inline=False)
    embed.add_field(name="🛡️ [ ] : مشرفي التذاكر", value=clip(f"{staff_mentions}\n\u200b", 1024), inline=False)
    embed.add_field(name="📅 [ ] : تاريخ إنشاء التذكرة", value=f"{created_str}\n\u200b", inline=False)
    embed.add_field(name="🔢 [ ] : رقم التذكرة", value=f"```{number}```\n\u200b", inline=False)
    embed.add_field(name="❓ [ ] : قسم التذكرة", value=f"```{clip(section['label'], 900)}```\n\u200b", inline=False)

    questions = section.get("custom_questions") or []
    if questions and answers_list:
        for idx, ans in enumerate(answers_list):
            q_title = questions[idx] if idx < len(questions) else f"سؤال {idx + 1}"
            embed.add_field(name=clip(f"📝 {q_title}", 256), value=clip(ans, 1024) or "—", inline=False)

    footer_icon = section.get("thumbnail_url") or panel.get("thumbnail_url")
    embed.set_footer(text="نظام إدارة التذاكر", icon_url=footer_icon or None)
    final_img = section.get("image_url") or panel.get("image_url")
    if final_img:
        embed.set_image(url=final_img)

    view = TicketInsideView(quick_replies=quick_replies, show_escalate=bool(higher_role_id))
    content_ping = f"{user.mention} | {staff_mentions}"
    sent_msg = None
    try:
        sent_msg = await ticket_channel.send(content=content_ping, embed=embed, view=view)
    except discord.HTTPException:
        log.exception("فشل إرسال رسالة التذكرة، هجرب نسخة من غير صور")
        try:
            sent_msg = await ticket_channel.send(content=content_ping, embed=strip_embed_media(embed), view=build_inside_view(g, g["active_tickets"][str(ticket_channel.id)]))
        except discord.HTTPException:
            log.exception("فشل إرسال رسالة التذكرة نهائياً")
    if sent_msg:
        try:
            await sent_msg.pin()
        except discord.HTTPException:
            pass

    await interaction.followup.send(embed=ok_embed("✅ تم فتح التذكرة", f"تم عمل التذكرة بنجاح: {ticket_channel.mention}"), ephemeral=True)


# ==============================================================================
# 🎛️ واجهة البانل
# ==============================================================================
class PanelControlView(SafeView):
    def __init__(self, guild_id: int, pid: str):
        super().__init__(timeout=None)
        self.pid = pid
        g = STORE.guild(guild_id)
        _, panel = find_panel(g, pid)
        panel = panel or {}
        sections = panel.get("sections", {})
        buttons_mode = panel.get("display_type") == "buttons" and 0 < len(sections) <= 20

        if buttons_mode:
            for key, data in sections.items():
                btn = discord.ui.Button(
                    label=clip(data.get("label"), 80) or "قسم",
                    style=discord.ButtonStyle.secondary,
                    emoji=parse_emoji(data.get("emoji")),
                    custom_id=f"tk:btn:{pid}:{key}",
                )
                btn.callback = self._make_button_cb(key)
                self.add_item(btn)
        else:
            self.add_item(PanelSelect(pid, sections))

        refresh = discord.ui.Button(label="تحديث البانل", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id=f"tk:refresh:{pid}", row=4)
        refresh.callback = self._refresh
        self.add_item(refresh)

    def _make_button_cb(self, key: str) -> ButtonCB:
        async def cb(interaction: discord.Interaction):
            await open_section(interaction, self.pid, key)
        return cb

    async def _refresh(self, interaction: discord.Interaction):
        perms = interaction.user.guild_permissions
        if not (perms.administrator or perms.manage_guild):
            await respond(interaction, embed=err_embed("الزر ده للإدارة فقط.", "❌ غير مسموح"), ephemeral=True)
            return
        g = STORE.guild(interaction.guild.id)
        name, panel = find_panel(g, self.pid)
        if not panel:
            await respond(interaction, embed=err_embed("البانل ده اتمسح من البيانات."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.message.edit(embed=build_panel_embed(name, panel), view=PanelControlView(interaction.guild.id, self.pid))
        except discord.HTTPException as e:
            await interaction.followup.send(embed=err_embed(f"حصلت مشكلة: {e}"), ephemeral=True)
            return
        await interaction.followup.send(embed=ok_embed("🔄 تم التحديث", "تم تحديث البانل بنجاح."), ephemeral=True)


# ==============================================================================
# 🧙 معالج إنشاء/تعديل البانل (Wizard)
# ==============================================================================
class PanelWizard:
    def __init__(self, panel_name: str, editing: bool = False):
        self.panel_name = panel_name
        self.editing = editing
        self.sections: list[str] = []
        self.roles: dict[str, list[int]] = {}
        self.cats: dict[str, Optional[str]] = {}
        self.thumbs: dict[str, Optional[str]] = {}
        self.descs: dict[str, Optional[str]] = {}
        self.questions: dict[str, list[str]] = {}
        self.qr_all: list[str] = []
        self.qr_map: dict[str, list[str]] = {}
        self.higher_all: Optional[int] = None
        self.higher_map: dict[str, Optional[int]] = {}
        self.warnings: list[str] = []


class SectionChunkModal(SafeModal):
    """مودال بيسأل سؤال لكل قسم (5 أقسام في المرة بسبب حد ديسكورد)."""

    def __init__(self, cfg: dict, chunks: list[list[str]], index: int, results: dict):
        total = len(chunks)
        title = cfg["title"] + (f" ({index + 1}/{total})" if total > 1 else "")
        super().__init__(title=clip(title, 45))
        self.cfg, self.chunks, self.index, self.results = cfg, chunks, index, results
        self.boxes: dict[str, discord.ui.TextInput] = {}
        room = max(5, 45 - len(cfg["label_fmt"].replace("{sec}", "")))
        for sec in chunks[index]:
            box = discord.ui.TextInput(
                label=cfg["label_fmt"].format(sec=clip(sec, room)),
                placeholder=clip(cfg["placeholder"], 100),
                style=cfg["style"],
                max_length=cfg["max_length"],
                required=cfg["required"],
            )
            self.boxes[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        for sec, box in self.boxes.items():
            self.results[sec] = box.value.strip()
        if self.index + 1 < len(self.chunks):
            nxt = SectionChunkModal(self.cfg, self.chunks, self.index + 1, self.results)

            async def open_next(i: discord.Interaction):
                await i.response.send_modal(nxt)

            remaining = len(self.chunks) - self.index - 1
            embed = discord.Embed(title="📝 تم حفظ الدفعة", description=f"باقي {remaining} دفعة من الأقسام. اضغط للمتابعة.", color=COLOR_DARK)
            view = ChoiceView([("➡️ الدفعة التالية", None, discord.ButtonStyle.primary, open_next)])
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await self.cfg["on_done"](interaction, self.results)


async def ask_per_section(interaction: discord.Interaction, sections: list[str], *, title: str, label_fmt: str, placeholder: str,
                          style: discord.TextStyle, max_length: int, required: bool, on_done):
    chunks = [sections[i:i + 5] for i in range(0, len(sections), 5)]
    cfg = dict(title=title, label_fmt=label_fmt, placeholder=placeholder, style=style, max_length=max_length, required=required, on_done=on_done)
    await interaction.response.send_modal(SectionChunkModal(cfg, chunks, 0, {}))


# ----- خطوات الـ Wizard (نفس الترتيب والنصوص القديمة) -----
async def step_roles(inter: discord.Interaction, wiz: PanelWizard):
    async def done(i: discord.Interaction, values: dict):
        roles = {}
        for sec, text in values.items():
            valid = []
            for rid in parse_ids(text):
                if i.guild.get_role(rid):
                    valid.append(rid)
                else:
                    wiz.warnings.append(f"رتبة غير موجودة تم تجاهلها: {rid}")
            roles[sec] = valid
        wiz.roles = roles
        await step_categories(i, wiz)

    async def yes(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="🛡️ رتب الدعم لكل قسم", label_fmt="أيدي رتب قسم: {sec}",
                              placeholder="اكتب أيديهات الرتب (كل أيدي في سطر)...", style=discord.TextStyle.paragraph,
                              max_length=300, required=True, on_done=done)

    async def no(i: discord.Interaction):
        wiz.roles = {s: [] for s in wiz.sections}
        await step_categories(i, wiz)

    await send_step(inter, "❓ رتب الدعم", "عاوز تضيف رتب دعم معينة لكل قسم؟", [
        ("نعم، حدد الرتب", "✅", discord.ButtonStyle.success, yes),
        ("لا، تخطي", "⏭", discord.ButtonStyle.secondary, no),
    ])


async def step_categories(inter: discord.Interaction, wiz: PanelWizard):
    async def done(i: discord.Interaction, values: dict):
        for sec, text in values.items():
            cat = None
            ids = parse_ids(text)
            if ids and isinstance(i.guild.get_channel(ids[0]), discord.CategoryChannel):
                cat = str(ids[0])
            else:
                wiz.warnings.append(f"كاتيجوري غير صالحة لقسم «{clip(sec, 20)}» (هتستخدم الرئيسية)")
            wiz.cats[sec] = cat
        await step_thumbs(i, wiz)

    async def yes(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="📂 أيدي الكاتيجوري لكل قسم", label_fmt="أيدي كاتيجوري: {sec}",
                              placeholder="اكتب أيدي الكاتيجوري...", style=discord.TextStyle.short,
                              max_length=30, required=True, on_done=done)

    async def no(i: discord.Interaction):
        wiz.cats = {s: None for s in wiz.sections}
        await step_thumbs(i, wiz)

    await send_step(inter, "❓ كاتيجوري لكل قسم", "عاوز تخصص كاتيجوري مختلف لكل قسم؟", [
        ("نعم، حدد الكاتيجوري", "✅", discord.ButtonStyle.success, yes),
        ("لا، استخدم الرئيسي", "⏭️", discord.ButtonStyle.secondary, no),
    ])


async def step_thumbs(inter: discord.Interaction, wiz: PanelWizard):
    async def done(i: discord.Interaction, values: dict):
        for sec, text in values.items():
            url = clean_url(text)
            if text and not url:
                wiz.warnings.append(f"رابط صورة غير صالح لقسم «{clip(sec, 20)}» تم تجاهله")
            wiz.thumbs[sec] = url
        await step_descs(i, wiz)

    async def yes(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="🖼️ روابط الصور المصغرة", label_fmt="صورة قسم: {sec}",
                              placeholder="حط رابط الصورة هنا...", style=discord.TextStyle.short,
                              max_length=300, required=True, on_done=done)

    async def no(i: discord.Interaction):
        wiz.thumbs = {s: None for s in wiz.sections}
        await step_descs(i, wiz)

    await send_step(inter, "❓ صور مصغرة (Thumbnails)", "عاوز تضيف صورة مصغرة (Thumbnail) لكل قسم؟", [
        ("نعم، ضيف صور", "🖼️", discord.ButtonStyle.success, yes),
        ("لا، تخطي", "⏭️", discord.ButtonStyle.secondary, no),
    ])


async def step_descs(inter: discord.Interaction, wiz: PanelWizard):
    async def done(i: discord.Interaction, values: dict):
        wiz.descs = {sec: clip(text, 100) or None for sec, text in values.items()}
        await step_questions(i, wiz)

    async def yes(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="✍️ وصف الأقسام", label_fmt="وصف: {sec}",
                              placeholder="اكتب الوصف هنا...", style=discord.TextStyle.paragraph,
                              max_length=300, required=True, on_done=done)

    async def no(i: discord.Interaction):
        wiz.descs = {s: None for s in wiz.sections}
        await step_questions(i, wiz)

    await send_step(inter, "❓ وصف الأقسام", "عاوز تحط وصف مخصص يظهر تحت اسم كل قسم؟", [
        ("نعم، ضيف وصف", "✅", discord.ButtonStyle.success, yes),
        ("لا، تخطي", "⏭️", discord.ButtonStyle.secondary, no),
    ])


async def step_questions(inter: discord.Interaction, wiz: PanelWizard):
    async def single_done(i: discord.Interaction, values: dict):
        wiz.questions = {sec: [text] for sec, text in values.items() if text}
        await step_quick_replies(i, wiz)

    async def multi_done(i: discord.Interaction, values: dict):
        wiz.questions = {sec: [q.strip() for q in text.split("\n") if q.strip()][:5] for sec, text in values.items()}
        await step_quick_replies(i, wiz)

    async def single(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="📌 سؤال واحد لكل قسم", label_fmt="سؤال قسم: {sec}",
                              placeholder="اكتب السؤال هنا...", style=discord.TextStyle.short,
                              max_length=200, required=True, on_done=single_done)

    async def multi(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="❓ الأسئلة المتعددة", label_fmt="أسئلة قسم: {sec}",
                              placeholder="اكتب كل سؤال في سطر جديد...", style=discord.TextStyle.paragraph,
                              max_length=300, required=True, on_done=multi_done)

    async def yes(i: discord.Interaction):
        await send_step(i, "❓ نظام الأسئلة", "حدد طريقة إضافة الأسئلة:", [
            ("سؤال واحد لكل قسم", "📌", discord.ButtonStyle.primary, single),
            ("أكثر من سؤال لكل قسم", "📋", discord.ButtonStyle.success, multi),
        ])

    async def no(i: discord.Interaction):
        wiz.questions = {}
        await step_quick_replies(i, wiz)

    await send_step(inter, "❓ أسئلة التذكرة", "عاوز تعمل أسئلة تظهر للعضو لما يفتح التذكرة؟", [
        ("نعم، ضيف أسئلة", "✅", discord.ButtonStyle.success, yes),
        ("لا، بدون أسئلة", "⏭", discord.ButtonStyle.secondary, no),
    ])


class SingleQuickRepliesModal(SafeModal, title="🌐 ردود سريعة موحدة"):
    qr_box = discord.ui.TextInput(
        label="الردود السريعة (كل رد في سطر)",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب كل رد في سطر جديد...\nمثال:\nأهلاً بك، تفضل بطرح مشكلتك.\nمن فضلك انتظر رد الإدارة.",
        max_length=500,
        required=True,
    )

    def __init__(self, wiz: PanelWizard):
        super().__init__()
        self.wiz = wiz

    async def on_submit(self, interaction: discord.Interaction):
        self.wiz.qr_all = [r.strip() for r in self.qr_box.value.split("\n") if r.strip()][:25]
        await step_higher(interaction, self.wiz)


async def step_quick_replies(inter: discord.Interaction, wiz: PanelWizard):
    async def custom_done(i: discord.Interaction, values: dict):
        wiz.qr_map = {sec: [l.strip() for l in text.split("\n") if l.strip()][:25] for sec, text in values.items()}
        await step_higher(i, wiz)

    async def all_sections(i: discord.Interaction):
        await i.response.send_modal(SingleQuickRepliesModal(wiz))

    async def custom(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="🛠 ردود سريعة مخصصة", label_fmt="ردود قسم: {sec}",
                              placeholder="اكتب الردود هنا (كل رد في سطر)...", style=discord.TextStyle.paragraph,
                              max_length=400, required=True, on_done=custom_done)

    async def yes(i: discord.Interaction):
        await send_step(i, "⚡ الردود السريعة", "حدد طريقة إدخال الردود السريعة:", [
            ("ردود موحدة لكل الأقسام", "🌐", discord.ButtonStyle.primary, all_sections),
            ("ردود مختلفة لكل قسم", "🛠", discord.ButtonStyle.success, custom),
        ])

    async def no(i: discord.Interaction):
        await step_higher(i, wiz)

    await send_step(inter, "⚡ الردود السريعة", "عاوز تعمل ردود سريعة جاهزة للمشرفين يختاروا منها؟", [
        ("نعم، ضيف ردود سريعة", "✅", discord.ButtonStyle.success, yes),
        ("لا، تخطي", "⏭️", discord.ButtonStyle.secondary, no),
    ])


class SingleHigherRoleModal(SafeModal, title="⭐ رتبة إدارية موحدة"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة", placeholder="اكتب أيدي الرتبة هنا...", max_length=30, required=True)

    def __init__(self, wiz: PanelWizard):
        super().__init__()
        self.wiz = wiz

    async def on_submit(self, interaction: discord.Interaction):
        ids = parse_ids(self.role_box.value)
        if not ids or not interaction.guild.get_role(ids[0]):
            await respond(interaction, embed=err_embed("يرجى كتابة أيدي رتبة صحيحة وموجودة في السيرفر!"), ephemeral=True)
            return
        self.wiz.higher_all = ids[0]
        await step_color(interaction, self.wiz)


async def step_higher(inter: discord.Interaction, wiz: PanelWizard):
    async def custom_done(i: discord.Interaction, values: dict):
        for sec, text in values.items():
            ids = parse_ids(text)
            wiz.higher_map[sec] = ids[0] if ids and i.guild.get_role(ids[0]) else None
        await step_color(i, wiz)

    async def single(i: discord.Interaction):
        await i.response.send_modal(SingleHigherRoleModal(wiz))

    async def custom(i: discord.Interaction):
        await ask_per_section(i, wiz.sections, title="🛠 رتبة عليا لكل قسم", label_fmt="رتبة عليا لـ: {sec}",
                              placeholder="اكتب أيدي الرتبة (أو سيبها فاضية)...", style=discord.TextStyle.short,
                              max_length=30, required=False, on_done=custom_done)

    async def yes(i: discord.Interaction):
        await send_step(i, "👑 رتبة الإدارة العليا", "حدد طريقة إدخال رتبة الإدارة العليا:", [
            ("رتبة واحدة للكل", "⭐", discord.ButtonStyle.primary, single),
            ("رتبة مختلفة لكل قسم", "🛠", discord.ButtonStyle.success, custom),
        ])

    async def no(i: discord.Interaction):
        await step_color(i, wiz)

    await send_step(inter, "👑 رتبة الإدارة العليا", "عاوز تخصص رتبة إدارة عليا للتصعيد؟", [
        ("نعم، ضيف رتبة عليا", "✅", discord.ButtonStyle.success, yes),
        ("لا، تخطي", "⏭️", discord.ButtonStyle.secondary, no),
    ])


async def step_color(inter: discord.Interaction, wiz: PanelWizard):
    def pick(color_hex: str) -> ButtonCB:
        async def cb(i: discord.Interaction):
            await finish_wizard(i, wiz, color_hex)
        return cb

    async def yes(i: discord.Interaction):
        await send_step(i, "🎨 اختيار اللون", "اختر اللون المناسب للإيمبد:", [
            ("🟢 أخضر", None, discord.ButtonStyle.success, pick("00FF88")),
            ("🔵 أزرق", None, discord.ButtonStyle.primary, pick("3498DB")),
            ("🔴 أحمر", None, discord.ButtonStyle.danger, pick("FF3333")),
            ("🟡 أصفر", None, discord.ButtonStyle.secondary, pick("F1C40F")),
            ("🟣 بنفسجي", None, discord.ButtonStyle.secondary, pick("9B59B6")),
        ])

    await send_step(inter, "🎨 لون الإيمبد", "عاوز تختار لون مخصص للإيمبد؟", [
        ("نعم، حدد لون الإيمبد", "🎨", discord.ButtonStyle.success, yes),
        ("لا، تخطي باللون الافتراضي", "⏭️", discord.ButtonStyle.secondary, pick("2B2D31")),
    ])


async def finish_wizard(interaction: discord.Interaction, wiz: PanelWizard, color_hex: str):
    g = STORE.guild(interaction.guild.id)
    panel = g["panels"].get(wiz.panel_name)
    if not panel:
        await respond(interaction, embed=err_embed("البانل ده اتمسح من البيانات."), ephemeral=True)
        return

    # مفاتيح الأقسام القديمة بتفضل ثابتة (عشان البانلات المنشورة ما تبوظش)
    old_keys = {s.get("label"): k for k, s in panel.get("sections", {}).items()}
    new_sections: dict[str, dict] = {}
    for name in wiz.sections:
        key = old_keys.get(name)
        while not key or key in new_sections:
            key = uuid.uuid4().hex[:8]
        new_sections[key] = {
            "label": name,
            "description": wiz.descs.get(name),
            "custom_questions": wiz.questions.get(name, []),
            "quick_replies": wiz.qr_all or wiz.qr_map.get(name, []),
            "emoji": "🎫",
            "support_role_ids": wiz.roles.get(name, []),
            "higher_support_role_id": wiz.higher_all or wiz.higher_map.get(name),
            "category_id": wiz.cats.get(name),
            "thumbnail_url": wiz.thumbs.get(name),
            "color_hex": color_hex,
            "image_url": panel.get("image_url"),
        }

    panel["color_hex"] = color_hex
    panel["sections"] = new_sections
    panel["has_questions"] = any(wiz.questions.values())
    STORE.mark_dirty(interaction.guild.id)

    desc = f"تم حفظ البانل (**{wiz.panel_name}**).\nاستخدم الأمر `/ticket` عشان تنشره في أي روم."
    if wiz.warnings:
        desc += "\n\n⚠️ **تنبيهات:**\n" + "\n".join(f"• {w}" for w in wiz.warnings[:8])
    await respond(interaction, embed=discord.Embed(title="🎨 تم حفظ البانل", description=clip(desc, 4000), color=parse_color(color_hex)), ephemeral=True)


class SectionsConfigModal(SafeModal):
    def __init__(self, wiz: PanelWizard, default: str = DEFAULT_SECTIONS_TEXT):
        super().__init__(title="📝 كتابة أسماء الأقسام")
        self.wiz = wiz
        self.sections_box = discord.ui.TextInput(
            label="أسماء الأقسام (كل قسم في سطر)",
            default=clip(default, 1000),
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.add_item(self.sections_box)

    async def on_submit(self, interaction: discord.Interaction):
        sections: list[str] = []
        for line in self.sections_box.value.split("\n"):
            line = clip(line.strip(), 80)
            if line and line not in sections:
                sections.append(line)
        sections = sections[:MAX_SECTIONS]
        if not sections:
            await respond(interaction, embed=err_embed("لازم تكتب قسم واحد على الأقل!"), ephemeral=True)
            return
        self.wiz.sections = sections
        await step_roles(interaction, self.wiz)


class PanelInfoModal(SafeModal):
    def __init__(self, guild_id: int, editing: bool = False, panel_name: str = ""):
        super().__init__(title="⚙️ إعدادات البانل")
        self.editing = editing
        self.old_name = panel_name
        panel = STORE.guild(guild_id)["panels"].get(panel_name, {}) if editing else {}

        img = panel.get("image_url") or ""
        thumb = panel.get("thumbnail_url") or ""
        images_default = f"{img} | {thumb}" if img and thumb else (img or (f"| {thumb}" if thumb else ""))

        self.name_box = discord.ui.TextInput(label="اسم البانل", default=panel_name if editing else "", max_length=50, required=True)
        self.desc_box = discord.ui.TextInput(label="الوصف (بدون أي إضافات أوتوماتيكية)", default=clip(panel.get("desc") or "محتوى البانل الخاص بك...", 500),
                                             style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.images_box = discord.ui.TextInput(label="روابط الصور (صورة البانل | الثامبنيل)", default=clip(images_default, 1000),
                                               placeholder="رابط الصورة الكبيرة | رابط الثامبنيل (اختياري)", max_length=1000, required=False)
        self.footer_box = discord.ui.TextInput(label="نص التذييل (Footer)", default=clip(panel.get("custom_footer_info") or "", 200),
                                               placeholder="معلومات إضافية تحت في الإيمبد", max_length=200, required=False)
        self.category_box = discord.ui.TextInput(label="أيدي الكاتيجوري (Category ID)", default=str(panel.get("category_id") or ""), max_length=30, required=True)
        for box in (self.name_box, self.desc_box, self.images_box, self.footer_box, self.category_box):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        g = STORE.guild(guild.id)
        panels = g["panels"]
        p_name = clean_panel_name(self.name_box.value)
        if not p_name:
            await respond(interaction, embed=err_embed("اسم البانل غير صالح!"), ephemeral=True)
            return

        ids = parse_ids(self.category_box.value)
        if not ids or not isinstance(guild.get_channel(ids[0]), discord.CategoryChannel):
            await respond(interaction, embed=err_embed("أيدي الكاتيجوري غير صحيح أو مش موجود في السيرفر!"), ephemeral=True)
            return

        warnings = []
        raw = self.images_box.value.strip()
        img_url = thumb_url = None
        if "|" in raw:
            a, b = raw.split("|", 1)
            img_url, thumb_url = clean_url(a), clean_url(b)
            if (a.strip() and not img_url) or (b.strip() and not thumb_url):
                warnings.append("تم تجاهل رابط صورة غير صالح (لازم يبدأ بـ http أو https).")
        elif raw:
            img_url = clean_url(raw)
            if not img_url:
                warnings.append("تم تجاهل رابط الصورة لأنه غير صالح (لازم يبدأ بـ http أو https).")

        if self.editing:
            panel = panels.get(self.old_name)
            if not panel:
                await respond(interaction, embed=err_embed("البانل ده مش موجود."), ephemeral=True)
                return
            if p_name != self.old_name:
                if p_name in panels:
                    await respond(interaction, embed=err_embed("فيه بانل تاني بنفس الاسم ده!"), ephemeral=True)
                    return
                panels[p_name] = panels.pop(self.old_name)  # إعادة التسمية من غير ما الأقسام تضيع
                panel = panels[p_name]
        else:
            if p_name in panels:
                await respond(interaction, embed=err_embed("فيه بانل بنفس الاسم ده بالفعل! اختار اسم تاني أو عدّل القديم."), ephemeral=True)
                return
            if len(panels) >= 25:
                await respond(interaction, embed=err_embed("وصلت للحد الأقصى (25 بانل)."), ephemeral=True)
                return
            panel = {"pid": uuid.uuid4().hex[:8], "sections": {}, "display_type": "menu", "color_hex": "2b2d31"}
            panels[p_name] = panel

        panel.update({
            "title": "🎫 الدعم الفني والمساعدة",
            "desc": self.desc_box.value,
            "image_url": img_url,
            "thumbnail_url": thumb_url,
            "custom_footer_info": self.footer_box.value.strip(),
            "category_id": str(ids[0]),
        })
        STORE.mark_dirty(guild.id)

        wiz = PanelWizard(p_name, editing=self.editing)
        wiz.warnings = warnings

        def set_display(kind: str, continue_wizard: bool) -> ButtonCB:
            async def cb(i: discord.Interaction):
                p = STORE.guild(i.guild.id)["panels"].get(p_name)
                if not p:
                    await respond(i, embed=err_embed("البانل ده مش موجود."), ephemeral=True)
                    return
                p["display_type"] = kind
                STORE.mark_dirty(i.guild.id)
                if continue_wizard:
                    await i.response.send_modal(SectionsConfigModal(wiz))
                else:
                    await respond(i, embed=ok_embed("✅ تم", "تم تغيير طريقة العرض. اضغط 🔄 تحديث البانل في البانل المنشور."), ephemeral=True)
            return cb

        if self.editing:
            desc = f"تم حفظ بيانات **{p_name}**.\nلو عاوز تغير طريقة عرض الأقسام اختار:"
        else:
            desc = f"تم حفظ بيانات **{p_name}**.\nاختر طريقة عرض الأقسام:"
        if warnings:
            desc += "\n\n⚠️ " + "\n⚠️ ".join(warnings)
        embed = discord.Embed(title="✅ تم حفظ معلومات البانل", description=desc, color=COLOR_GREEN)
        view = ChoiceView([
            ("قائمة منسدلة", "📂", discord.ButtonStyle.primary, set_display("menu", not self.editing)),
            ("أزرار", "🔘", discord.ButtonStyle.success, set_display("buttons", not self.editing)),
        ])
        await respond(interaction, embed=embed, view=view, ephemeral=True)


class LogChannelModal(SafeModal, title="📋 تحديد روم اللوج"):
    channel_id_box = discord.ui.TextInput(label="أيدي الروم (Channel ID)", placeholder="اكتب أيدي الروم هنا...", max_length=30, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        ids = parse_ids(self.channel_id_box.value)
        chan = interaction.guild.get_channel(ids[0]) if ids else None
        if not isinstance(chan, discord.TextChannel):
            await respond(interaction, embed=err_embed("يرجى كتابة أيدي روم نصي صحيح وموجود في السيرفر!"), ephemeral=True)
            return
        STORE.guild(interaction.guild.id)["log_channel_id"] = str(chan.id)
        STORE.mark_dirty(interaction.guild.id)
        await respond(interaction, embed=ok_embed("✅ تم الحفظ", f"تم تحديد روم اللوج: {chan.mention}"), ephemeral=True)


# ==============================================================================
# 🛠 لوحة الإعدادات
# ==============================================================================
class PanelPickView(SafeView):
    def __init__(self, names: list[str], placeholder: str, on_pick: Callable[[discord.Interaction, str], Awaitable[None]], timeout: float = 120):
        super().__init__(timeout=timeout)
        select = discord.ui.Select(placeholder=placeholder, options=[discord.SelectOption(label=clip(n, 100), value=n) for n in names[:25]])

        async def cb(i: discord.Interaction):
            await on_pick(i, select.values[0])

        select.callback = cb
        self.add_item(select)


class TicketSetupMainView(SafeView):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions
        if perms.administrator or perms.manage_guild:
            return True
        await respond(interaction, embed=err_embed("اللوحة دي للإدارة فقط."), ephemeral=True)
        return False

    @discord.ui.button(label="إنشاء بانل جديد", style=discord.ButtonStyle.success, emoji="🚀", custom_id="setup_create_panel_btn_v7")
    async def create_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelInfoModal(interaction.guild.id, editing=False))

    @discord.ui.button(label="تعديل بانل", style=discord.ButtonStyle.primary, emoji="⚙️", custom_id="setup_edit_panel_btn_v7")
    async def edit_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        panels = STORE.guild(interaction.guild.id)["panels"]
        if not panels:
            await respond(interaction, embed=err_embed("مفيش أي بانلات مضافة حالياً لتعديلها.", "⚠️ تنبيه"), ephemeral=True)
            return

        async def on_pick(inter: discord.Interaction, name: str):
            if name not in STORE.guild(inter.guild.id)["panels"]:
                await respond(inter, embed=err_embed("البانل ده مش موجود."), ephemeral=True)
                return

            async def edit_info(i: discord.Interaction):
                await i.response.send_modal(PanelInfoModal(i.guild.id, editing=True, panel_name=name))

            async def edit_sections(i: discord.Interaction):
                panel = STORE.guild(i.guild.id)["panels"].get(name)
                if not panel:
                    await respond(i, embed=err_embed("البانل ده مش موجود."), ephemeral=True)
                    return
                labels = [s.get("label", "") for s in panel.get("sections", {}).values()]
                default = "\n".join(labels) if labels else DEFAULT_SECTIONS_TEXT
                await i.response.send_modal(SectionsConfigModal(PanelWizard(name, editing=True), default=default))

            view = ChoiceView([
                ("تعديل الوصف والمعلومات", "✏️", discord.ButtonStyle.primary, edit_info),
                ("تعديل الأقسام والأسئلة", "📝", discord.ButtonStyle.success, edit_sections),
            ], timeout=120)
            await respond(inter, embed=discord.Embed(title="⚙️ تعديل البانل", description="عاوز تعدل ايه في البانل ده؟", color=COLOR_DARK), view=view, ephemeral=True)

        embed = discord.Embed(title="⚙️ تعديل بانل", description="اختر البانل من القائمة:", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=PanelPickView(list(panels.keys()), "اختر البانل المراد تعديله...", on_pick), ephemeral=True)

    @discord.ui.button(label="حذف بانل", style=discord.ButtonStyle.danger, emoji="🗑", custom_id="setup_delete_panel_btn_v7")
    async def delete_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        panels = STORE.guild(interaction.guild.id)["panels"]
        if not panels:
            await respond(interaction, embed=err_embed("مفيش بانلات لحذفها.", "⚠️ تنبيه"), ephemeral=True)
            return

        async def on_pick(inter: discord.Interaction, name: str):
            # بنشتغل على البيانات الحالية مش نسخة قديمة، عشان ما نمسحش تذاكر اتفتحت في الوقت ده
            removed = STORE.guild(inter.guild.id)["panels"].pop(name, None)
            if removed is None:
                await respond(inter, embed=err_embed("البانل ده مش موجود."), ephemeral=True)
                return
            STORE.mark_dirty(inter.guild.id)
            await respond(inter, embed=ok_embed("🗑️ تم الحذف", f"تم حذف البانل **{name}** بنجاح."), ephemeral=True)

        embed = discord.Embed(title="🗑 حذف بانل", description="اختر البانل اللي عاوز تمسحه:", color=COLOR_DARK)
        await respond(interaction, embed=embed, view=PanelPickView(list(panels.keys()), "اختر البانل لحذفه...", on_pick), ephemeral=True)

    @discord.ui.button(label="روم اللوج", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="setup_log_channel_btn_v7")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LogChannelModal())

    @discord.ui.button(label="إحصائيات المشرفين", style=discord.ButtonStyle.primary, emoji="📊", custom_id="setup_staff_stats_btn_v7")
    async def show_staff_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = STORE.guild(interaction.guild.id)
        staff_stats = g["staff_stats"]
        embed = discord.Embed(
            title="📊 إحصائيات الدعم الفني",
            description="ترتيب وأداء المشرفين حسب إجمالي النجوم/النقاط المجمعة:\n",
            color=COLOR_DARK,
            timestamp=discord.utils.utcnow(),
        )
        if not staff_stats:
            embed.add_field(name="مفيش بيانات", value="مفيش تذاكر اتستلمت أو اتقيمت لحد دلوقتي.", inline=False)
        else:
            top = sorted(staff_stats.items(), key=lambda x: x[1].get("total_stars", 0), reverse=True)[:10]
            medals = ["🥇", "🥈", "🥉"]
            for idx, (s_id, data) in enumerate(top):
                member = interaction.guild.get_member(int(s_id))
                display = clip(member.display_name if member else s_id, 60)
                ratings = data.get("ratings_count", 0)
                total = data.get("total_stars", 0)
                avg = f"{total / ratings:.1f}" if ratings else "—"
                prefix = medals[idx] if idx < len(medals) else f"#{idx + 1}"
                embed.add_field(
                    name=f"{prefix} المشرف: {display}",
                    value=(f"👤 <@{s_id}>\n💼 التذاكر المستلمة: `{data.get('claimed', 0)}`\n"
                           f"⭐ مجموع النقاط/النجوم: `{total}`\n📈 المتوسط: `{avg}` ({ratings} تقييم)\n\u200b"),
                    inline=False,
                )
        embed.set_footer(text="نظام إدارة التذاكر")
        await interaction.response.send_message(embed=embed, ephemeral=False)


# ==============================================================================
# 🎯 إرسال البانل بأمر /ticket
# ==============================================================================
class TicketPublishSelectView(SafeView):
    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        panels = STORE.guild(guild_id)["panels"]
        ready = [name for name, p in panels.items() if p.get("sections")]
        select = discord.ui.Select(placeholder="اختر البانل لإرساله هنا...")
        if ready:
            for name in ready[:25]:
                select.add_option(label=clip(name, 100), description=clip(f"بانل: {name}", 100), emoji="🎫", value=name)
        else:
            select.add_option(label="مفيش بانلات جاهزة", value="none")

        async def select_callback(interaction: discord.Interaction):
            chosen = select.values[0]
            if chosen == "none":
                await respond(interaction, content="❌ مفيش بانلات جاهزة للإرسال.", ephemeral=True)
                return
            p_data = STORE.guild(interaction.guild.id)["panels"].get(chosen)
            if not p_data or not p_data.get("sections"):
                await respond(interaction, content="❌ البانل ده مش موجود أو مفيهوش أقسام.", ephemeral=True)
                return

            view = PanelControlView(interaction.guild.id, p_data["pid"])
            embed = build_panel_embed(chosen, p_data)
            try:
                try:
                    await interaction.channel.send(embed=embed, view=view)
                except discord.HTTPException:
                    log.exception("فشل نشر البانل بالصور، هجرب من غيرها")
                    await interaction.channel.send(embed=strip_embed_media(embed), view=PanelControlView(interaction.guild.id, p_data["pid"]))
            except discord.HTTPException as e:
                await respond(interaction, content=f"❌ حصلت مشكلة أثناء إرسال البانل: {e}", ephemeral=True)
                return
            await respond(interaction, content=f"✅ تم إرسال البانل **{chosen}** بنجاح.", ephemeral=True)

        select.callback = select_callback
        self.add_item(select)


# ==============================================================================
# 🧩 الـ Cog الرئيسي
# ==============================================================================
class ZiuoUltimateTicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await STORE.load()
        # Views ثابتة (Persistent) — بتشتغل بعد أي ريستارت
        self.bot.add_view(TicketSetupMainView())
        self.bot.add_view(CloseConfirmationView())
        self.bot.add_view(TicketRatingView())
        self.bot.add_view(TicketInsideView(with_select=True))
        for gid, g in STORE.guilds.items():
            for panel in g["panels"].values():
                self.bot.add_view(PanelControlView(int(gid), panel["pid"]))
        self.cleanup_loop.start()

    async def cog_unload(self):
        self.cleanup_loop.cancel()
        await STORE.flush(final=True)

    # ---------- تنظيف دوري ----------
    @tasks.loop(minutes=2)
    async def cleanup_loop(self):
        now = now_ts()
        for gid, g in list(STORE.guilds.items()):
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            for ch_id, pending in list(g["pending_ratings"].items()):
                chan = guild.get_channel(int(ch_id))
                expired = now - pending.get("created", now) >= RATING_TIMEOUT_SECONDS
                if chan is None or expired:
                    g["pending_ratings"].pop(ch_id, None)
                    STORE.mark_dirty(gid)
                    if chan is not None:
                        await delete_ticket_channels(guild, chan, pending)

    @cleanup_loop.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()

    @cleanup_loop.error
    async def _cleanup_error(self, error: BaseException):
        log.error("خطأ في مهمة التنظيف", exc_info=error)

    # ---------- لو روم اتحذف يدوياً ----------
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        g = STORE.guilds.get(str(channel.guild.id))
        if not g:
            return
        cid = str(channel.id)
        if cid in g["active_tickets"]:
            retire_ticket(channel.guild.id, cid, "الروم اتحذف يدوياً")
        if g["pending_ratings"].pop(cid, None) is not None:
            STORE.mark_dirty(channel.guild.id)
        for t in g["active_tickets"].values():
            if str(t.get("temp_voice_id")) == cid:
                t.pop("temp_voice_id", None)
                STORE.mark_dirty(channel.guild.id)

    # ---------- الأوامر ----------
    @app_commands.command(name="setup", description="لوحة إعدادات وإدارة التذاكر")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ لوحة إعدادات التذاكر",
            description="اختر من الأزرار التالية لإنشاء أو إدارة البانلات:",
            color=COLOR_DARK,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=True)

    @app_commands.command(name="ticket", description="إرسال بانل تذاكر للروم")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def publish_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎫 إرسال بانل التذاكر", description="اختر البانل اللي حابب تنشره في الروم دي:", color=COLOR_DARK)
        await interaction.response.send_message(embed=embed, view=TicketPublishSelectView(interaction.guild.id), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ الأمر ده للإدارة فقط.", ephemeral=True)
            return
        log.exception("خطأ في أمر سلاش", exc_info=error)
        await report_error(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
