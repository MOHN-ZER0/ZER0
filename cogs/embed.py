"""
🎨 نظام الإيمبد الاحترافي (مركز الإيمبدات)

- أمر واحد /embed بيفتح قائمة: ➕ إضافة | ✏️ تعديل | 🗑️ حذف | 📋 إيمبداتي.
- لوحة إنشاء بمعاينة حية: عنوان (اختياري) ووصف وصورة وصورة مصغرة ولون وفوتر وأوثر وحقول وأزرار روابط ونص خارج الإيمبد.
- تعديل مباشر: لو الإيمبد متبعت في روم، أي تعديل بتعمله بيتطبق فوراً على الرسالة نفسها من غير زرار "تطبيق".
- كل الإيمبدات بتتحفظ في MongoDB (MONGODB_URI)، وكل عضو يشوف إيمبداته بس (ومن معاه Manage Server يشوف الكل).
- لو حد مسح رسالة الإيمبد، أول تعديل بيعيد إرسالها لوحده في نفس الروم.
- /embed_edit مع اقتراحات تلقائية: لفتح أي إيمبد بالرقم أو بجزء من عنوانه مباشرة.
"""
import asyncio
import copy
import datetime
import logging
import math
import os
import random
import re
import time
from typing import Any, Awaitable, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()
log = logging.getLogger("embeds")

# ==============================================================================
# ⚙️ الثوابت
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Embeds_DB"
EMBED_DEBUG = os.getenv("EMBED_DEBUG", "1") == "1"

DEFAULT_COLOR = 0x2B2D31
COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_BLUE = 0x3498DB

MAX_FIELDS = 25
MAX_BUTTONS = 5
MAX_TOTAL = 6000
MAX_RECORDS_PER_GUILD = 500
PER_PAGE = 6
DB_TIMEOUT = 15.0

COLOR_NAMES = {
    "red": 0xE74C3C, "احمر": 0xE74C3C, "green": 0x2ECC71, "اخضر": 0x2ECC71, "blue": 0x004cd2, "ازرق": 0x004cd2,
    "yellow": 0xF1C40F, "اصفر": 0xF1C40F, "orange": 0xE67E22, "برتقالي": 0xE67E22, "purple": 0x9B59B6, "بنفسجي": 0x9B59B6,
    "pink": 0xFF69B4, "وردي": 0xFF69B4, "black": 0x000001, "اسود": 0x000001, "white": 0xFFFFFF, "ابيض": 0xFFFFFF,
    "gold": 0xFFD700, "ذهبي": 0xFFD700, "cyan": 0x1ABC9C, "سماوي": 0x1ABC9C, "gray": 0x95A5A6, "رمادي": 0x95A5A6,
    "dark": DEFAULT_COLOR, "داكن": DEFAULT_COLOR,
}

# ==============================================================================
# 💾 قاعدة البيانات
# ==============================================================================
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None
embeds_col = _db["embeds"] if _db is not None else None


async def run_db(fn, *args, **kwargs):
    """عمليات pymongo (المتزامنة) في thread وبمهلة، عشان بطء الداتابيز ما يعلّقش الأوامر."""
    return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), DB_TIMEOUT)


def ensure_indexes_sync():
    for keys in ([("guild_id", 1), ("owner_id", 1), ("created_at", -1)], [("guild_id", 1), ("created_at", -1)], [("message_id", 1)]):
        try:
            embeds_col.create_index(keys)
        except Exception:
            log.warning("تعذر إنشاء index %s", keys, exc_info=True)


def insert_record_sync(doc: dict):
    embeds_col.insert_one(doc)


def get_record_sync(eid: str) -> Optional[dict]:
    return embeds_col.find_one({"_id": eid})


def update_record_sync(eid: str, sets: dict):
    embeds_col.update_one({"_id": eid}, {"$set": sets})


def delete_record_sync(eid: str):
    embeds_col.delete_one({"_id": eid})


def _scope(guild_id: int, owner_id: Optional[int]) -> dict:
    q: dict[str, Any] = {"guild_id": guild_id}
    if owner_id is not None:
        q["owner_id"] = owner_id
    return q


def count_sync(guild_id: int, owner_id: Optional[int]) -> int:
    return embeds_col.count_documents(_scope(guild_id, owner_id))


def list_records_sync(guild_id: int, owner_id: Optional[int], skip: int, limit: int) -> tuple[int, list]:
    q = _scope(guild_id, owner_id)
    return embeds_col.count_documents(q), list(embeds_col.find(q).sort("created_at", -1).skip(skip).limit(limit))


def search_records_sync(guild_id: int, owner_id: Optional[int], text: str, limit: int = 25) -> list:
    q = _scope(guild_id, owner_id)
    if text:
        rx = {"$regex": re.escape(text), "$options": "i"}
        q["$or"] = [{"_id": {"$regex": "^" + re.escape(text)}}, {"data.title": rx}, {"data.description": rx}]
    return list(embeds_col.find(q).sort("created_at", -1).limit(limit))


def live_message_ids_sync() -> list:
    return [d["message_id"] for d in embeds_col.find({"message_id": {"$ne": None}}, projection={"message_id": 1})]


def mark_message_deleted_sync(mid: int):
    embeds_col.update_many({"message_id": mid}, {"$set": {"message_id": None, "message_deleted": True}})


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
    if EMBED_DEBUG:
        text += f"\n```{type(exc).__name__}: {clip(exc, 300)}```"
    return text


_URL_RE = re.compile(r"^https?://\S{3,2000}$")
_CUSTOM_EMOJI_RE = re.compile(r"^<a?:\w{2,32}:\d{15,25}>$")


def clean_url(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value if _URL_RE.match(value) else None


def clean_emoji(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    if _CUSTOM_EMOJI_RE.match(value) or (len(value) <= 8 and not value.isascii()):
        return value
    return None


def parse_color(text: Optional[str]) -> Optional[int]:
    """لون من Hex (#2b2d31 / 2ecc71 / fff) أو اسم (red / أحمر). فاضي = الافتراضي، وغير صالح = None."""
    t = (text or "").strip().lower()
    if not t:
        return DEFAULT_COLOR
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        t = t.replace(a, b)
    if t in COLOR_NAMES:
        return COLOR_NAMES[t]
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


def parse_yes(text: str, default: bool = True) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return default
    return t not in {"لا", "no", "n", "false", "0", "off", "مش", "لأ"}


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def edit_ui(interaction: discord.Interaction, **kwargs):
    """يعدّل رسالة الواجهة سواء اتعمل defer قبل كده ولا لأ."""
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


def can_manage_all(member: discord.Member) -> bool:
    return member.guild_permissions.manage_guild


def can_edit(member: discord.Member, rec: dict) -> bool:
    return rec["owner_id"] == member.id or can_manage_all(member)


# ==============================================================================
# 🧬 بيانات الإيمبد وبناؤه
# ==============================================================================
def new_data() -> dict:
    return {"title": None, "description": "", "color": DEFAULT_COLOR, "image_url": None, "thumbnail_url": None,
            "footer_text": None, "footer_icon_url": None, "author_name": None, "author_icon_url": None,
            "content": None, "timestamp": False, "ts": None, "signature": False, "fields": [], "buttons": []}


def sanitize(data: Optional[dict]) -> dict:
    merged = new_data()
    merged.update(copy.deepcopy(data or {}))
    return merged


def has_body(d: dict) -> bool:
    return bool(d.get("title") or (d.get("description") or "").strip() or d.get("fields") or d.get("image_url")
                or d.get("thumbnail_url") or d.get("author_name") or d.get("footer_text") or d.get("signature"))


def build_embed(d: dict, sig_name: Optional[str] = None, sig_icon: Optional[str] = None) -> Optional[discord.Embed]:
    if not has_body(d):
        return None
    desc = (d.get("description") or "").replace("\\n", "\n").strip()
    embed = discord.Embed(description=desc or None, color=int(d.get("color") or DEFAULT_COLOR))
    if d.get("title"):
        embed.title = d["title"]
    if d.get("timestamp"):
        embed.timestamp = datetime.datetime.fromtimestamp(d.get("ts") or int(time.time()), tz=datetime.timezone.utc)
    if d.get("author_name"):
        embed.set_author(name=d["author_name"], icon_url=d.get("author_icon_url") or None)
    if d.get("image_url"):
        embed.set_image(url=d["image_url"])
    if d.get("thumbnail_url"):
        embed.set_thumbnail(url=d["thumbnail_url"])
    if d.get("footer_text"):
        embed.set_footer(text=d["footer_text"], icon_url=d.get("footer_icon_url") or None)
    elif d.get("signature") and sig_name:
        embed.set_footer(text=f"Z I UO Empire ✦ Requested by {sig_name}", icon_url=sig_icon or None)
    for f in d.get("fields") or []:
        embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", True))
    return embed


def build_link_view(d: dict) -> Optional[discord.ui.View]:
    buttons = d.get("buttons") or []
    if not buttons:
        return None
    view = discord.ui.View(timeout=None)
    for b in buttons[:MAX_BUTTONS]:
        view.add_item(discord.ui.Button(label=b["label"], url=b["url"], emoji=b.get("emoji") or None))
    return view


def record_label(rec: dict) -> str:
    d = rec.get("data") or {}
    text = d.get("title") or (d.get("description") or "").replace("\n", " ").strip() or d.get("author_name") or d.get("footer_text")
    return clip(text or "(صورة/حقول فقط)", 60)


def allowed_mentions_for(member: discord.Member, channel) -> discord.AllowedMentions:
    """اللي معندوش صلاحية Mention Everyone مينفعش يعمل منشن جماعي عن طريق البوت."""
    try:
        if channel.permissions_for(member).mention_everyone:
            return discord.AllowedMentions.all()
    except Exception:
        pass
    return discord.AllowedMentions(everyone=False, roles=False, users=True)


def send_problems(guild: discord.Guild, channel, member: discord.Member) -> list[str]:
    if channel is None or not hasattr(channel, "send"):
        return ["الروم مش موجودة أو مش روم كتابي."]
    bot_p, user_p = channel.permissions_for(guild.me), channel.permissions_for(member)
    problems = []
    if not (bot_p.view_channel and bot_p.send_messages and bot_p.embed_links):
        problems.append(f"البوت محتاج View Channel + Send Messages + Embed Links في {channel.mention}.")
    if not (user_p.view_channel and user_p.send_messages):
        problems.append(f"أنت معندكش صلاحية الإرسال في {channel.mention}.")
    return problems


# ==============================================================================
# 🏗️ جلسة التحرير (مسودة جديدة أو إيمبد محفوظ بتعديل مباشر)
# ==============================================================================
class Session:
    def __init__(self, cog: "CustomEmbedCog", guild: discord.Guild, user: discord.Member, data: dict, channel_id: int, record: Optional[dict] = None):
        self.cog, self.guild, self.user = cog, guild, user
        self.data, self.channel_id, self.record = data, channel_id, record

    @property
    def live(self) -> bool:
        return self.record is not None

    def sig(self) -> tuple[Optional[str], Optional[str]]:
        if self.record:
            return self.record.get("owner_name"), self.record.get("owner_avatar")
        return self.user.display_name, self.user.display_avatar.url

    def jump_url(self) -> Optional[str]:
        if self.record and self.record.get("message_id"):
            return f"https://discord.com/channels/{self.guild.id}/{self.record['channel_id']}/{self.record['message_id']}"
        return None

    def embeds(self, note: Optional[str] = None) -> list[discord.Embed]:
        d = self.data
        preview = build_embed(d, *self.sig())
        size = len(preview) if preview else 0
        if self.live:
            url = self.jump_url()
            where = f"<#{self.record['channel_id']}>" + (f" ([فتح الرسالة]({url}))" if url else " ⚠️ _(الرسالة اتمسحت، هتتبعت تاني مع أول تعديل)_")
            mode = f"📍 **إيمبد محفوظ** `#{self.record['_id']}` في {where}\n⚡ **أي تعديل بيتطبق فوراً على الرسالة** — مفيش زرار تطبيق."
        else:
            mode = f"🆕 **مسودة جديدة** — جهّز الإيمبد واضغط 🚀 إرسال.\n📢 هيتبعت في <#{self.channel_id}>"
        lines = [mode, f"🧩 حقول `{len(d['fields'])}/{MAX_FIELDS}` ┊ 🔗 أزرار `{len(d['buttons'])}/{MAX_BUTTONS}` ┊ 📏 الحجم `{size}/{MAX_TOTAL}`"]
        if d.get("content"):
            lines.append("💬 **نص خارج الإيمبد:** " + clip(d["content"], 150))
        if not has_body(d) and not d.get("content"):
            lines.append("⚠️ _الإيمبد فاضي لسه — اضغط 📝 المحتوى._")
        if note:
            lines.append("\n" + note)
        banner = discord.Embed(description="\n".join(lines), color=COLOR_BLUE)
        shown = preview or discord.Embed(description="*(معاينة الإيمبد هتظهر هنا)*", color=DEFAULT_COLOR)
        return [banner, shown]

    def check(self, data: dict) -> Optional[str]:
        embed = build_embed(data, *self.sig())
        if embed is not None and len(embed) > MAX_TOTAL:
            return f"الإيمبد عدّى الحد الأقصى ({MAX_TOTAL} حرف). قلّل النص أو الحقول."
        if self.live and embed is None and not (data.get("content") or "").strip():
            return "مينفعش تفضّي الإيمبد بالكامل وهو منشور. لو عاوز تشيله استخدم 🗑️ حذف."
        return None

    async def show(self, interaction: discord.Interaction, note: Optional[str] = None):
        await edit_ui(interaction, content=None, embeds=self.embeds(note), view=BuilderView(self))

    async def apply(self, interaction: discord.Interaction, mutate: Callable[[dict], None]):
        """بيطبق التعديل: لو الإيمبد منشور بيتحدّث فوراً في الروم وبيتحفظ، ولو مسودة بيحدّث المعاينة بس."""
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
            ok, note = await self.cog.push_live(self, new, interaction.user)
            if not ok:
                await interaction.followup.send(embed=err_embed(note), ephemeral=True)
                await self.show(interaction)
                return
        self.data = new
        await self.show(interaction, note)


# ==============================================================================
# ✏️ المودالات
# ==============================================================================
class TextModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="📝 محتوى الإيمبد")
        self.s, d = s, s.data
        self.title_in = discord.ui.TextInput(label="العنوان (اختياري — سيبه فاضي لو مش عايزه)", default=clip(d.get("title"), 256) if d.get("title") else None, required=False, max_length=256)
        self.desc_in = discord.ui.TextInput(label="الوصف / المحتوى", style=discord.TextStyle.paragraph, default=clip(d.get("description"), 4000) or None, required=False, max_length=4000)
        self.footer_in = discord.ui.TextInput(label="نص الفوتر (اختياري)", default=clip(d.get("footer_text"), 2048) if d.get("footer_text") else None, required=False, max_length=2048)
        self.author_in = discord.ui.TextInput(label="اسم الأوثر فوق الإيمبد (اختياري)", default=clip(d.get("author_name"), 256) if d.get("author_name") else None, required=False, max_length=256)
        self.content_in = discord.ui.TextInput(label="نص خارج الإيمبد / منشن (اختياري)", style=discord.TextStyle.paragraph, default=clip(d.get("content"), 2000) if d.get("content") else None, required=False, max_length=2000)
        for box in (self.title_in, self.desc_in, self.footer_in, self.author_in, self.content_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        vals = {"title": self.title_in.value.strip() or None, "description": self.desc_in.value.strip(), "footer_text": self.footer_in.value.strip() or None,
                "author_name": self.author_in.value.strip() or None, "content": self.content_in.value.strip() or None}
        await self.s.apply(interaction, lambda d: d.update(vals))


class StyleModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="🎨 الألوان والصور")
        self.s, d = s, s.data
        self.color_in = discord.ui.TextInput(label="اللون (Hex أو اسم: #2b2d31 / red / أحمر)", default=f"#{int(d.get('color') or DEFAULT_COLOR):06x}", required=False, max_length=20)
        self.image_in = discord.ui.TextInput(label="رابط الصورة الكبيرة (اختياري)", default=d.get("image_url") or None, required=False, max_length=500)
        self.thumb_in = discord.ui.TextInput(label="رابط الصورة المصغرة (اختياري)", default=d.get("thumbnail_url") or None, required=False, max_length=500)
        self.aicon_in = discord.ui.TextInput(label="صورة الأوثر (محتاج اسم أوثر)", default=d.get("author_icon_url") or None, required=False, max_length=500)
        self.ficon_in = discord.ui.TextInput(label="صورة الفوتر (محتاج نص فوتر)", default=d.get("footer_icon_url") or None, required=False, max_length=500)
        for box in (self.color_in, self.image_in, self.thumb_in, self.aicon_in, self.ficon_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        color = parse_color(self.color_in.value)
        if color is None:
            await respond(interaction, embed=err_embed("اللون غير صالح. اكتب Hex مثل `#2b2d31` أو اسم مثل `red` / `أحمر`."), ephemeral=True)
            return
        urls = {}
        for key, box, name in (("image_url", self.image_in, "الصورة الكبيرة"), ("thumbnail_url", self.thumb_in, "الصورة المصغرة"),
                               ("author_icon_url", self.aicon_in, "صورة الأوثر"), ("footer_icon_url", self.ficon_in, "صورة الفوتر")):
            raw = box.value.strip()
            if raw and not clean_url(raw):
                await respond(interaction, embed=err_embed(f"رابط {name} لازم يبدأ بـ http أو https."), ephemeral=True)
                return
            urls[key] = raw or None
        await self.s.apply(interaction, lambda d: d.update(color=color, **urls))


class FieldModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="➕ إضافة حقل")
        self.s = s
        self.name_in = discord.ui.TextInput(label="اسم الحقل", required=True, max_length=256)
        self.value_in = discord.ui.TextInput(label="محتوى الحقل", style=discord.TextStyle.paragraph, required=True, max_length=1024)
        self.inline_in = discord.ui.TextInput(label="جنب بعض؟ (نعم / لا)", default="نعم", required=False, max_length=5)
        for box in (self.name_in, self.value_in, self.inline_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        field = {"name": self.name_in.value.strip(), "value": self.value_in.value.strip(), "inline": parse_yes(self.inline_in.value)}
        if not field["name"] or not field["value"]:
            await respond(interaction, embed=err_embed("اسم ومحتوى الحقل لازم يكونوا مش فاضيين."), ephemeral=True)
            return
        await self.s.apply(interaction, lambda d: d["fields"].append(field))


class LinkModal(SafeModal):
    def __init__(self, s: Session):
        super().__init__(title="🔗 إضافة زرار رابط")
        self.s = s
        self.label_in = discord.ui.TextInput(label="نص الزرار", required=True, max_length=80)
        self.url_in = discord.ui.TextInput(label="الرابط (http أو https)", required=True, max_length=500)
        self.emoji_in = discord.ui.TextInput(label="إيموجي (اختياري)", required=False, max_length=60)
        for box in (self.label_in, self.url_in, self.emoji_in):
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        url = clean_url(self.url_in.value)
        if not url:
            await respond(interaction, embed=err_embed("الرابط لازم يبدأ بـ http أو https."), ephemeral=True)
            return
        raw_emoji = self.emoji_in.value.strip()
        emoji = clean_emoji(raw_emoji)
        if raw_emoji and emoji is None:
            await respond(interaction, embed=err_embed("الإيموجي غير صالح. استخدم إيموجي عادي أو إيموجي سيرفر بصيغة `<:name:id>`."), ephemeral=True)
            return
        button = {"label": self.label_in.value.strip(), "url": url, "emoji": emoji}
        await self.s.apply(interaction, lambda d: d["buttons"].append(button))


# ==============================================================================
# 🧭 واجهات مساعدة (اختيار من قائمة، اختيار روم، تأكيد حذف)
# ==============================================================================
class PickView(SafeView):
    def __init__(self, owner_id: int, options: list[discord.SelectOption], on_pick: Callable[[discord.Interaction, str], Awaitable[None]],
                 back: Callable[[discord.Interaction], Awaitable[None]], placeholder: str):
        super().__init__(timeout=300)
        self.owner_id = owner_id
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await respond(interaction, content="🔒 القائمة دي مش بتاعتك.", ephemeral=True)
        return False


class ChannelPickView(SafeView):
    def __init__(self, s: Session):
        super().__init__(timeout=300)
        self.s = s

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.s.user.id

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📢 اختر الروم", channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=1, max_values=1, row=0)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel_or_thread(select.values[0].id)
        problems = send_problems(interaction.guild, channel, interaction.user)
        if problems:
            await respond(interaction, embed=err_embed("\n".join(f"• {p}" for p in problems)), ephemeral=True)
            return
        if not self.s.live:
            self.s.channel_id = channel.id
            await self.s.show(interaction)
            return
        await interaction.response.defer()
        ok, note = await self.s.cog.move_live(self.s, channel, interaction.user)
        if not ok:
            await interaction.followup.send(embed=err_embed(note), ephemeral=True)
        await self.s.show(interaction, note if ok else None)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.show(interaction)


class DeleteConfirmView(SafeView):
    def __init__(self, cog: "CustomEmbedCog", rec: dict, owner_id: int, back: Callable[[discord.Interaction], Awaitable[None]]):
        super().__init__(timeout=60)
        self.cog, self.rec, self.owner_id, self.back = cog, rec, owner_id, back

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def _do(self, interaction: discord.Interaction, delete_message: bool):
        await interaction.response.defer()
        await self.cog.delete_embed(self.rec, delete_message)
        await self.back(interaction)
        await interaction.followup.send(embed=ok_embed("🗑️ تم الحذف", "اتحذف الإيمبد" + (" والرسالة من الروم." if delete_message else " من السجل (الرسالة فضلت في الروم).")), ephemeral=True)

    @discord.ui.button(label="حذف الرسالة والسجل", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def both_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, True)

    @discord.ui.button(label="حذف السجل فقط", emoji="📁", style=discord.ButtonStyle.secondary)
    async def record_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do(interaction, False)

    @discord.ui.button(label="إلغاء", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.back(interaction)


# ==============================================================================
# 🏗️ لوحة البناء (Builder)
# ==============================================================================
class BuilderView(SafeView):
    def __init__(self, s: Session):
        super().__init__(timeout=900)
        self.s = s
        d = s.data
        self.ts_btn.style = discord.ButtonStyle.success if d.get("timestamp") else discord.ButtonStyle.secondary
        self.sig_btn.style = discord.ButtonStyle.success if d.get("signature") else discord.ButtonStyle.secondary
        if s.live:
            self.remove_item(self.send_btn)
            url = s.jump_url()
            if url:
                self.add_item(discord.ui.Button(label="فتح الرسالة", emoji="🔗", url=url, row=2))
        else:
            self.remove_item(self.copy_btn)
            self.remove_item(self.delete_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.s.user.id:
            return True
        await respond(interaction, content="🔒 اللوحة دي مش بتاعتك.", ephemeral=True)
        return False

    @discord.ui.button(label="المحتوى", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def text_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal(self.s))

    @discord.ui.button(label="الألوان والصور", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def style_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StyleModal(self.s))

    @discord.ui.button(label="حقل", emoji="➕", style=discord.ButtonStyle.secondary, row=0)
    async def add_field_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.s.data["fields"]) >= MAX_FIELDS:
            await respond(interaction, embed=err_embed(f"وصلت للحد الأقصى ({MAX_FIELDS} حقل)."), ephemeral=True)
            return
        await interaction.response.send_modal(FieldModal(self.s))

    @discord.ui.button(label="حقل", emoji="🗑️", style=discord.ButtonStyle.secondary, row=0)
    async def del_field_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        fields = self.s.data["fields"]
        if not fields:
            await respond(interaction, embed=err_embed("مفيش حقول تتحذف."), ephemeral=True)
            return
        options = [discord.SelectOption(label=clip(f["name"], 100) or "—", description=clip(f["value"], 100) or None, value=str(i)) for i, f in enumerate(fields)]

        async def on_pick(i: discord.Interaction, value: str):
            idx = int(value)
            await self.s.apply(i, lambda d: d["fields"].pop(idx) if 0 <= idx < len(d["fields"]) else None)

        await interaction.response.edit_message(embeds=[discord.Embed(title="🗑️ حذف حقل", description="اختار الحقل اللي عاوز تحذفه:", color=COLOR_BLUE)],
                                                view=PickView(self.s.user.id, options, on_pick, self.s.show, "اختر الحقل"))

    @discord.ui.button(label="زرار رابط", emoji="🔗", style=discord.ButtonStyle.secondary, row=0)
    async def add_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.s.data["buttons"]) >= MAX_BUTTONS:
            await respond(interaction, embed=err_embed(f"وصلت للحد الأقصى ({MAX_BUTTONS} أزرار)."), ephemeral=True)
            return
        await interaction.response.send_modal(LinkModal(self.s))

    @discord.ui.button(label="زرار", emoji="🗑️", style=discord.ButtonStyle.secondary, row=1)
    async def del_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        buttons = self.s.data["buttons"]
        if not buttons:
            await respond(interaction, embed=err_embed("مفيش أزرار تتحذف."), ephemeral=True)
            return
        options = [discord.SelectOption(label=clip(b["label"], 100), description=clip(b["url"], 100), value=str(i)) for i, b in enumerate(buttons)]

        async def on_pick(i: discord.Interaction, value: str):
            idx = int(value)
            await self.s.apply(i, lambda d: d["buttons"].pop(idx) if 0 <= idx < len(d["buttons"]) else None)

        await interaction.response.edit_message(embeds=[discord.Embed(title="🗑️ حذف زرار", description="اختار الزرار اللي عاوز تحذفه:", color=COLOR_BLUE)],
                                                view=PickView(self.s.user.id, options, on_pick, self.s.show, "اختر الزرار"))

    @discord.ui.button(label="التوقيت", emoji="🕒", style=discord.ButtonStyle.secondary, row=1)
    async def ts_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        def mutate(d: dict):
            d["timestamp"] = not d.get("timestamp")
            if d["timestamp"] and not d.get("ts"):
                d["ts"] = int(time.time())
        await self.s.apply(interaction, mutate)

    @discord.ui.button(label="التوقيع", emoji="✍️", style=discord.ButtonStyle.secondary, row=1)
    async def sig_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.apply(interaction, lambda d: d.update(signature=not d.get("signature")))

    @discord.ui.button(label="الروم", emoji="📢", style=discord.ButtonStyle.secondary, row=1)
    async def channel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = "اختار الروم اللي هيتنشر فيه الإيمبد:" if not self.s.live else "اختار روم جديد — **الإيمبد هيتنقل ليه والرسالة القديمة هتتمسح.**"
        await interaction.response.edit_message(embeds=[discord.Embed(title="📢 اختيار الروم", description=desc, color=COLOR_BLUE)], view=ChannelPickView(self.s))

    @discord.ui.button(label="إرسال", emoji="🚀", style=discord.ButtonStyle.success, row=2)
    async def send_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.s.cog.publish(interaction, self.s)

    @discord.ui.button(label="نسخ كإيمبد جديد", emoji="📄", style=discord.ButtonStyle.primary, row=2)
    async def copy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = copy.deepcopy(self.s.data)
        data["ts"] = None
        draft = Session(self.s.cog, self.s.guild, interaction.user, data, self.s.record["channel_id"])
        await draft.show(interaction, "📄 دي نسخة جديدة (مسودة) — اضغط 🚀 إرسال لما تخلص.")

    @discord.ui.button(label="حذف", emoji="🗑️", style=discord.ButtonStyle.danger, row=2)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rec = self.s.record
        embed = discord.Embed(title="⚠️ تأكيد الحذف", description=f"هتحذف الإيمبد `#{rec['_id']}` — **{record_label({'data': self.s.data})}**\nعاوز تمسح الرسالة من الروم كمان ولا تحذف السجل بس؟", color=COLOR_RED)
        await interaction.response.edit_message(embeds=[embed], view=DeleteConfirmView(self.s.cog, rec, self.s.user.id, lambda i: go_dashboard(i, self.s.cog)))

    @discord.ui.button(label="القائمة", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await go_dashboard(interaction, self.s.cog)


# ==============================================================================
# 🏠 القائمة الرئيسية والقوائم
# ==============================================================================
def dashboard_embed(user: discord.Member, mine: Optional[int]) -> discord.Embed:
    count = f"`{mine}`" if mine is not None else "`؟` _(الداتابيز مش متاحة دلوقتي)_"
    desc = (
        f"أهلاً بيك يا {user.mention} في **مركز الإيمبدات** 🎨\n\n"
        "➕ **إضافة إيمبد جديد** — لوحة بمعاينة حية، والعنوان اختياري.\n"
        "✏️ **تعديل إيمبد** — اختار من إيمبداتك واتعدل **مباشرة** على الرسالة في الروم، من غير زرار تطبيق.\n"
        "🗑️ **حذف إيمبد** — احذف الرسالة والسجل أو السجل بس.\n"
        "📋 **إيمبداتي** — شوف كل إيمبد ضفته، وأماكنه، وروابط رسايله.\n\n"
        f"📦 إيمبداتك المحفوظة: {count}"
    )
    return discord.Embed(title="🎨 مركز الإيمبدات", description=desc, color=DEFAULT_COLOR)


async def go_dashboard(interaction: discord.Interaction, cog: "CustomEmbedCog"):
    if not interaction.response.is_done():
        await interaction.response.defer()
    try:
        mine = await run_db(count_sync, interaction.guild.id, interaction.user.id)
    except Exception:
        log.warning("تعذر عدّ الإيمبدات", exc_info=True)
        mine = None
    await interaction.edit_original_response(content=None, embeds=[dashboard_embed(interaction.user, mine)], view=DashboardView(cog, interaction.user))


class DashboardView(SafeView):
    def __init__(self, cog: "CustomEmbedCog", user: discord.Member):
        super().__init__(timeout=600)
        self.cog, self.user = cog, user
        select = discord.ui.Select(placeholder="اختر ما تريد من القائمة...", options=[
            discord.SelectOption(label="إضافة إيمبد جديد", description="لوحة إنشاء بمعاينة حية", emoji="➕", value="add"),
            discord.SelectOption(label="تعديل إيمبد", description="تعديل مباشر على الرسالة المنشورة", emoji="✏️", value="edit"),
            discord.SelectOption(label="حذف إيمبد", description="حذف الرسالة والسجل أو السجل فقط", emoji="🗑️", value="delete"),
            discord.SelectOption(label="إيمبداتي", description="عرض كل الإيمبدات اللي ضفتها", emoji="📋", value="list"),
        ])

        async def cb(i: discord.Interaction):
            await cog.handle_dashboard(i, select.values[0])

        select.callback = cb
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user.id:
            return True
        await respond(interaction, content="🔒 القائمة دي مش بتاعتك، اكتب `/embed` وافتح قائمتك.", ephemeral=True)
        return False


class ListView(SafeView):
    def __init__(self, cog: "CustomEmbedCog", user: discord.Member, scope_all: bool, page: int, pages: int):
        super().__init__(timeout=300)
        self.user = user

        def add(label: str, emoji: str, style: discord.ButtonStyle, cb, disabled: bool = False):
            btn = discord.ui.Button(label=label or None, emoji=emoji, style=style, disabled=disabled, row=0)
            btn.callback = cb
            self.add_item(btn)

        async def prev_cb(i): await cog.render_list(i, scope_all, page - 1)
        async def next_cb(i): await cog.render_list(i, scope_all, page + 1)
        async def toggle_cb(i): await cog.render_list(i, not scope_all, 0)
        async def back_cb(i): await go_dashboard(i, cog)

        add("", "⬅️", discord.ButtonStyle.primary, prev_cb, page <= 0)
        add("", "➡️", discord.ButtonStyle.primary, next_cb, page + 1 >= pages)
        if can_manage_all(user):
            add("إيمبداتي فقط" if scope_all else "كل إيمبدات السيرفر", "👥" if not scope_all else "👤", discord.ButtonStyle.secondary, toggle_cb)
        add("القائمة", "↩️", discord.ButtonStyle.secondary, back_cb)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id


# ==============================================================================
# 🌟 الـ Cog الرئيسي
# ==============================================================================
class CustomEmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.msg_ids: set[int] = set()

    async def cog_load(self):
        try:
            await run_db(ensure_indexes_sync)
            self.msg_ids = set(await run_db(live_message_ids_sync))
        except Exception:
            log.warning("فشل تحميل بيانات الإيمبد الأولية", exc_info=True)

    # ---------- حفظ وتحديث الرسائل ----------
    async def push_live(self, s: Session, new_data: dict, editor: discord.Member) -> tuple[bool, str]:
        """بيطبق التعديل على الرسالة المنشورة فوراً (وبيعيد إرسالها لو اتمسحت) وبعدها بيحفظ في الداتابيز."""
        rec = s.record
        embed = build_embed(new_data, *s.sig())
        content = (new_data.get("content") or "").strip() or None
        view = build_link_view(new_data)
        channel = s.guild.get_channel_or_thread(rec["channel_id"])
        if channel is None:
            return False, "الروم الأصلية اتمسحت. اختار روم جديد من زرار 📢 الروم وهتتنقل الرسالة."
        mentions = allowed_mentions_for(editor, channel)
        note = "✅ اتحدّث الإيمبد في الروم وتم الحفظ."
        message_id = rec.get("message_id")
        edited = False
        if message_id:
            try:
                await channel.get_partial_message(message_id).edit(content=content, embed=embed, view=view, allowed_mentions=mentions)
                edited = True
            except discord.NotFound:
                pass
            except discord.Forbidden:
                return False, "البوت مش قادر يعدّل الرسالة (صلاحيات ناقصة في الروم)."
            except discord.HTTPException as e:
                return False, f"ديسكورد رفض التعديل: {clip(e, 200)}"
        if not edited:
            try:
                kwargs = {"view": view} if view else {}
                msg = await channel.send(content=content, embed=embed, allowed_mentions=mentions, **kwargs)
            except discord.HTTPException as e:
                return False, f"تعذر إعادة إرسال الإيمبد: {clip(e, 200)}"
            message_id = msg.id
            self.msg_ids.add(message_id)
            rec["message_id"] = message_id
            rec.pop("message_deleted", None)
            note = "♻️ الرسالة الأصلية كانت متمسحة، فاتبعتت من جديد واتحفظت."
        sets = {"data": new_data, "updated_at": int(time.time()), "updated_by": editor.id, "message_id": message_id}
        try:
            await run_db(update_record_sync, rec["_id"], sets)
        except Exception:
            log.exception("فشل حفظ تعديل الإيمبد %s", rec["_id"])
            note += "\n⚠️ اتعدّلت الرسالة لكن الداتابيز مردتش، ممكن التعديل مايتحفظش."
        rec["data"] = new_data
        return True, note

    async def move_live(self, s: Session, channel, editor: discord.Member) -> tuple[bool, str]:
        rec = s.record
        embed = build_embed(s.data, *s.sig())
        content = (s.data.get("content") or "").strip() or None
        view = build_link_view(s.data)
        try:
            kwargs = {"view": view} if view else {}
            msg = await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions_for(editor, channel), **kwargs)
        except discord.HTTPException as e:
            return False, f"تعذر الإرسال في الروم الجديدة: {clip(e, 200)}"
        old_id, old_channel = rec.get("message_id"), s.guild.get_channel_or_thread(rec["channel_id"])
        if old_id:
            self.msg_ids.discard(old_id)
            if old_channel:
                try:
                    await old_channel.get_partial_message(old_id).delete()
                except discord.HTTPException:
                    pass
        self.msg_ids.add(msg.id)
        rec.update(channel_id=channel.id, message_id=msg.id)
        rec.pop("message_deleted", None)
        try:
            await run_db(update_record_sync, rec["_id"], {"channel_id": channel.id, "message_id": msg.id, "updated_at": int(time.time())})
        except Exception:
            log.exception("فشل حفظ نقل الإيمبد")
        s.channel_id = channel.id
        return True, f"📦 اتنقل الإيمبد إلى {channel.mention}."

    async def publish(self, interaction: discord.Interaction, s: Session):
        await interaction.response.defer()
        guild = interaction.guild
        channel = guild.get_channel_or_thread(s.channel_id)
        problems = send_problems(guild, channel, interaction.user)
        embed = build_embed(s.data, *s.sig())
        content = (s.data.get("content") or "").strip() or None
        if embed is None and not content:
            problems.append("الإيمبد فاضي — اكتب أي محتوى الأول.")
        size_problem = s.check(s.data)
        if size_problem:
            problems.append(size_problem)
        try:
            if await run_db(count_sync, guild.id, None) >= MAX_RECORDS_PER_GUILD:
                problems.append(f"السيرفر وصل للحد الأقصى من الإيمبدات المحفوظة ({MAX_RECORDS_PER_GUILD}). احذف إيمبدات قديمة.")
        except Exception:
            log.warning("تعذر فحص عدد الإيمبدات", exc_info=True)
        if problems:
            await interaction.followup.send(embed=err_embed("\n".join(f"• {p}" for p in problems), "⚠️ مينفعش يتبعت"), ephemeral=True)
            return
        view = build_link_view(s.data)
        try:
            kwargs = {"view": view} if view else {}
            msg = await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions_for(interaction.user, channel), **kwargs)
        except discord.HTTPException as e:
            await interaction.followup.send(embed=err_embed(f"ديسكورد رفض الإرسال (غالباً رابط صورة/زرار غير صالح):\n`{clip(e, 250)}`"), ephemeral=True)
            return
        now = int(time.time())
        rec = None
        for _ in range(6):
            doc = {"_id": str(random.randint(100000, 999999)), "guild_id": guild.id, "owner_id": interaction.user.id,
                   "owner_name": interaction.user.display_name, "owner_avatar": interaction.user.display_avatar.url,
                   "channel_id": channel.id, "message_id": msg.id, "data": copy.deepcopy(s.data), "created_at": now, "updated_at": now}
            try:
                await run_db(insert_record_sync, doc)
                rec = doc
                break
            except DuplicateKeyError:
                continue
            except Exception:
                log.exception("فشل حفظ الإيمبد")
                break
        if rec is None:
            note = "⚠️ الإيمبد اتبعت لكن الداتابيز مش متاحة فمش هقدر أعدّله بعدين."
        else:
            s.record = rec
            self.msg_ids.add(msg.id)
            note = f"🚀 اتنشر في {channel.mention} واتحفظ برقم `#{rec['_id']}` — من دلوقتي **أي تعديل بيتطبق فوراً**."
        await s.show(interaction, note)

    async def delete_embed(self, rec: dict, delete_message: bool):
        mid = rec.get("message_id")
        if mid:
            self.msg_ids.discard(mid)
        if delete_message and mid:
            guild = self.bot.get_guild(rec["guild_id"])
            channel = guild.get_channel_or_thread(rec["channel_id"]) if guild else None
            if channel:
                try:
                    await channel.get_partial_message(mid).delete()
                except discord.HTTPException:
                    pass
        await run_db(delete_record_sync, rec["_id"])

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id in self.msg_ids:
            self.msg_ids.discard(payload.message_id)
            try:
                await run_db(mark_message_deleted_sync, payload.message_id)
            except Exception:
                log.warning("تعذر تعليم الإيمبد كمتمسح", exc_info=True)

    # ---------- القائمة الرئيسية ----------
    async def open_live(self, interaction: discord.Interaction, rec: dict):
        """بيفتح إيمبد محفوظ للتعديل المباشر (مفترض interaction اتعمله defer)."""
        if not can_edit(interaction.user, rec):
            await interaction.followup.send(embed=err_embed("مش مسموح لك تعدّل إيمبد حد تاني."), ephemeral=True)
            return
        s = Session(self, interaction.guild, interaction.user, sanitize(rec.get("data")), rec["channel_id"], rec)
        await s.show(interaction)

    async def handle_dashboard(self, interaction: discord.Interaction, choice: str):
        guild, user = interaction.guild, interaction.user
        if choice == "add":
            channel = interaction.channel
            if channel is None or not hasattr(channel, "send"):
                await respond(interaction, embed=err_embed("الأمر لازم يتنفذ في روم كتابي."), ephemeral=True)
                return
            s = Session(self, guild, user, new_data(), channel.id)
            await s.show(interaction)
            return
        await interaction.response.defer()
        scope_all = can_manage_all(user)
        if choice == "list":
            await self.render_list(interaction, scope_all=False, page=0)
            return
        try:
            _, rows = await run_db(list_records_sync, guild.id, None if scope_all else user.id, 0, 25)
        except Exception as e:
            log.exception("فشل جلب الإيمبدات")
            await interaction.followup.send(content=error_text(e), ephemeral=True)
            return
        if not rows:
            await interaction.followup.send(embed=err_embed("مفيش إيمبدات محفوظة لسه. ابدأ بـ ➕ إضافة إيمبد جديد."), ephemeral=True)
            return
        options = []
        for r in rows:
            channel = guild.get_channel_or_thread(r["channel_id"])
            owner = f" • {r.get('owner_name', '')}" if scope_all else ""
            options.append(discord.SelectOption(label=record_label(r) or "—", description=clip(f"#{r['_id']} • {'#' + channel.name if channel else 'روم محذوفة'}{owner}", 100), value=r["_id"]))

        async def on_pick(i: discord.Interaction, eid: str):
            await i.response.defer()
            rec = await run_db(get_record_sync, eid)
            if rec is None or rec["guild_id"] != guild.id:
                await i.followup.send(embed=err_embed("الإيمبد ده مش موجود."), ephemeral=True)
                return
            if choice == "edit":
                await self.open_live(i, rec)
            elif not can_edit(i.user, rec):
                await i.followup.send(embed=err_embed("مش مسموح لك تحذف إيمبد حد تاني."), ephemeral=True)
            else:
                embed = discord.Embed(title="⚠️ تأكيد الحذف", description=f"هتحذف الإيمبد `#{rec['_id']}` — **{record_label(rec)}**\nعاوز تمسح الرسالة من الروم كمان ولا تحذف السجل بس؟", color=COLOR_RED)
                await i.edit_original_response(embeds=[embed], view=DeleteConfirmView(self, rec, i.user.id, lambda x: go_dashboard(x, self)))

        title = "✏️ تعديل إيمبد" if choice == "edit" else "🗑️ حذف إيمبد"
        note = "اختار الإيمبد — هيتفتح للتعديل **المباشر** على رسالته في الروم:" if choice == "edit" else "اختار الإيمبد اللي عاوز تحذفه:"
        if scope_all:
            note += "\n👥 _بتشوف إيمبدات كل السيرفر لأن معاك Manage Server._"
        if len(rows) == 25:
            note += "\n_(معروض آخر 25 إيمبد. لو عاوز أقدم، استخدم `/embed_edit` وابحث بالرقم أو العنوان.)_"
        await interaction.edit_original_response(embeds=[discord.Embed(title=title, description=note, color=COLOR_BLUE)],
                                                 view=PickView(user.id, options, on_pick, lambda x: go_dashboard(x, self), "اختر الإيمبد"))

    async def render_list(self, interaction: discord.Interaction, scope_all: bool, page: int):
        if not interaction.response.is_done():
            await interaction.response.defer()
        guild, user = interaction.guild, interaction.user
        page = max(0, page)
        try:
            total, rows = await run_db(list_records_sync, guild.id, None if scope_all else user.id, page * PER_PAGE, PER_PAGE)
            if not rows and page > 0:
                page = 0
                total, rows = await run_db(list_records_sync, guild.id, None if scope_all else user.id, 0, PER_PAGE)
        except Exception as e:
            log.exception("فشل عرض قائمة الإيمبدات")
            await interaction.followup.send(content=error_text(e), ephemeral=True)
            return
        pages = max(1, math.ceil(total / PER_PAGE))
        lines = []
        for n, r in enumerate(rows, page * PER_PAGE + 1):
            where = f"[الرسالة](https://discord.com/channels/{guild.id}/{r['channel_id']}/{r['message_id']})" if r.get("message_id") else "⚠️ الرسالة اتمسحت"
            owner = f" • <@{r['owner_id']}>" if scope_all else ""
            lines.append(f"**{n}.** {record_label(r)}\n└ `#{r['_id']}` • <#{r['channel_id']}> • {where}{owner} • <t:{int(r.get('created_at', 0))}:R>")
        title = "📋 كل إيمبدات السيرفر" if scope_all else "📋 إيمبداتي"
        embed = discord.Embed(title=title, description="\n\n".join(lines) or "مفيش إيمبدات لسه. ابدأ بـ ➕ إضافة إيمبد جديد.", color=DEFAULT_COLOR)
        embed.set_footer(text=f"صفحة {page + 1} من {pages} • الإجمالي {total}")
        await interaction.edit_original_response(content=None, embeds=[embed], view=ListView(self, user, scope_all, page, pages))

    # ---------- الأوامر ----------
    @app_commands.command(name="embed", description="[نظام إمبراطوري] مركز الإيمبدات: إضافة، تعديل مباشر، حذف، وعرض إيمبداتك")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await go_dashboard(interaction, self)

    @app_commands.command(name="embed_edit", description="[نظام إمبراطوري] فتح إيمبد محفوظ للتعديل المباشر بالرقم أو بجزء من العنوان")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(embed_id="رقم الإيمبد (هيظهر لك اقتراحات وانت بتكتب)")
    async def embed_edit(self, interaction: discord.Interaction, embed_id: str):
        await interaction.response.defer(ephemeral=True)
        rec = await run_db(get_record_sync, embed_id.strip().lstrip("#"))
        if rec is None or rec["guild_id"] != interaction.guild.id:
            await interaction.followup.send(embed=err_embed("الإيمبد ده مش موجود."), ephemeral=True)
            return
        await self.open_live(interaction, rec)

    @embed_edit.autocomplete("embed_id")
    async def embed_edit_ac(self, interaction: discord.Interaction, current: str):
        try:
            owner = None if can_manage_all(interaction.user) else interaction.user.id
            rows = await run_db(search_records_sync, interaction.guild.id, owner, current.strip().lstrip("#"), 25)
            return [app_commands.Choice(name=clip(f"#{r['_id']} • {record_label(r)}", 100), value=r["_id"]) for r in rows]
        except Exception:
            return []

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ محتاج صلاحية **Manage Messages** لاستخدام الأمر ده.", ephemeral=True)
            return
        log.exception("خطأ في أمر الإيمبد", exc_info=error)
        await report_error(interaction, getattr(error, "original", error))


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير موجود في ملف .env، نظام الإيمبد محتاج قاعدة بيانات لحفظ الإيمبدات.")
    await bot.add_cog(CustomEmbedCog(bot))
