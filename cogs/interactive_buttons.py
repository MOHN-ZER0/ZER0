"""
🎛️ النظام الإمبراطوري المتكامل لإدارة الأزرار والقوائم والرتب التفاعلية (Ultimate Empire Interactive System)
- متوافق تماماً مع بنية وقواعد نظام الإيمبد الاحترافي الخاص بك ومزود بنظام حفظ دائم (MongoDB).
- لوحة تحكم رسومية متكاملة ومتقدمة مع معالجة ذكية للأخطاء والصلاحيات الهرمية.
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
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("empire_interactive_system")

# ==============================================================================
# ⚙️ الثوابت وقاعدة البيانات المركزية
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Embeds_DB"
SYSTEM_DEBUG = os.getenv("EMBED_DEBUG", "1") == "1"

_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None
buttons_col = _db["empire_interactive_buttons"] if _db is not None else None
embeds_col = _db["embeds"] if _db is not None else None

MAX_BUTTONS_PER_VIEW = 5
MAX_MENUS_PER_VIEW = 3
MAX_SELECT_OPTIONS = 25
DB_TIMEOUT = 15.0

COLOR_GREEN = 0x00FF88
COLOR_RED = 0xFF3333
COLOR_BLUE = 0x3498DB
DEFAULT_COLOR = 0x2B2D31


async def run_db(fn, *args, **kwargs):
    """تنفيذ عمليات PyMongo في Thread منفصل لعدم تجميد الأحداث."""
    return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), DB_TIMEOUT)


def ensure_indexes_sync():
    if buttons_col is not None:
        try:
            buttons_col.create_index([("guild_id", 1), ("message_id", 1)], unique=True)
            buttons_col.create_index([("guild_id", 1), ("embed_id", 1)])
        except Exception:
            log.warning("تعذر إنشاء الفهارس الخاصة بنظام الأزرار", exc_info=True)


# ==============================================================================
# 🧰 أدوات المساعدة والتحقق
# ==============================================================================
def ok_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_GREEN)


def err_embed(description: str, title: str = "❌ خطأ إمبراطوري") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_RED)


def clip(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


_CUSTOM_EMOJI_RE = re.compile(r"^<a?:\w{2,32}:\d{15,25}>$")


def parse_emoji(raw: Optional[str]) -> Optional[discord.PartialEmoji | str]:
    raw = (raw or "").strip()
    if not raw:
        return None
    if _CUSTOM_EMOJI_RE.match(raw):
        parts = raw.rstrip(">").split(":")
        try:
            return discord.PartialEmoji(name=parts[1], id=int(parts[-1]), animated=parts[0].startswith("<a"))
        except Exception:
            return None
    if len(raw) <= 8 and not raw.isascii():
        return raw
    return None


def can_manage_server(member: discord.Member) -> bool:
    return member.guild_permissions.manage_guild


# ==============================================================================
# 🔘 الأزرار والقوائم الدائمة (Persistent Views)
# ==============================================================================
class EmpireDynamicButton(discord.ui.Button):
    def __init__(self, button_data: dict):
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger
        }
        style = style_map.get(button_data.get("style", "primary"), discord.ButtonStyle.primary)
        super().__init__(
            style=style,
            label=button_data.get("label") or None,
            emoji=parse_emoji(button_data.get("emoji")),
            custom_id=button_data.get("custom_id")
        )
        self.action_data = button_data

    async def callback(self, interaction: discord.Interaction):
        action_type = self.action_data.get("action_type", "role")

        if action_type == "ephemeral_msg":
            msg = self.action_data.get("message_content", "محتوى تفاعلي سري.")
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if action_type == "role":
            role_id = self.action_data.get("role_id")
            role_action = self.action_data.get("role_action", "toggle")
            guild = interaction.guild
            member = interaction.user

            if not guild or not isinstance(member, discord.Member):
                return

            role = guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("❌ عذراً، هذه الرتبة لم تعد موجودة في السيرفر.", ephemeral=True)
                return

            if guild.me.top_role <= role:
                await interaction.response.send_message("❌ لا يمكنني إدارة هذه الرتبة نظراً لتجاوزها رتبتي في الهرم التنظيمي.", ephemeral=True)
                return

            try:
                if role_action == "add":
                    if role not in member.roles:
                        await member.add_roles(role, reason="Empire System: Add Role Button")
                        await interaction.response.send_message(f"✅ تمت إضافة رتبة **{role.name}** بنجاح!", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"ℹ️ أنت تمتلك هذه الرتبة بالفعل.", ephemeral=True)
                elif role_action == "remove":
                    if role in member.roles:
                        await member.remove_roles(role, reason="Empire System: Remove Role Button")
                        await interaction.response.send_message(f"🗑️ تمت إزالة رتبة **{role.name}** بنجاح.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"ℹ️ أنت لا تمتلك هذه الرتبة أساساً.", ephemeral=True)
                else:  # toggle
                    if role in member.roles:
                        await member.remove_roles(role, reason="Empire System: Toggle Role Button")
                        await interaction.response.send_message(f"🗑️ تم إزالة رتبة **{role.name}** منك.", ephemeral=True)
                    else:
                        await member.add_roles(role, reason="Empire System: Toggle Role Button")
                        await interaction.response.send_message(f"✅ تمت إضافة رتبة **{role.name}** بنجاح!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ ليس لدي الصلاحيات الكافية لتعديل رتبتك.", ephemeral=True)
            except Exception as e:
                log.exception("خطأ أثناء معالجة زر الرتبة", exc_info=e)
                await interaction.response.send_message("❌ حدث خطأ داخلي أثناء معالجة طلب الرتبة.", ephemeral=True)


class EmpireDynamicSelectMenu(discord.ui.Select):
    def __init__(self, menu_data: dict):
        options = []
        for opt in menu_data.get("options", []):
            options.append(discord.SelectOption(
                label=clip(opt.get("label", "خيار"), 100),
                description=clip(opt.get("description", ""), 100) or None,
                emoji=parse_emoji(opt.get("emoji")),
                value=str(opt.get("role_id"))
            ))

        super().__init__(
            placeholder=clip(menu_data.get("placeholder", "اختر رتبتك من القائمة..."), 150),
            min_values=1,
            max_values=1,
            options=options[:MAX_SELECT_OPTIONS],
            custom_id=menu_data.get("custom_id")
        )
        self.menu_data = menu_data

    async def callback(self, interaction: discord.Interaction):
        try:
            role_id = int(self.values[0])
        except ValueError:
            return await interaction.response.send_message("❌ قيمة الرتبة غير صالحة.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user

        if not guild or not isinstance(member, discord.Member):
            return

        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ هذه الرتبة حُذفت من السيرفر.", ephemeral=True)
            return

        if guild.me.top_role <= role:
            await interaction.response.send_message("❌ البوت لا يمتلك صلاحية إدارية كافية لهذه الرتبة.", ephemeral=True)
            return

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Empire System: Select Menu Toggle")
                await interaction.response.send_message(f"🗑️ تم إزالة رتبة **{role.name}** بنجاح.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Empire System: Select Menu Toggle")
                await interaction.response.send_message(f"✅ تمت إضافة رتبة **{role.name}** بنجاح!", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ تعذر تغيير الرتبة بسبب نقص الصلاحيات.", ephemeral=True)


class EmpirePersistentView(discord.ui.View):
    def __init__(self, view_config: dict):
        super().__init__(timeout=None)
        for btn in view_config.get("buttons", []):
            self.add_item(EmpireDynamicButton(btn))
        for menu in view_config.get("select_menus", []):
            self.add_item(EmpireDynamicSelectMenu(menu))


# ==============================================================================
# 📝 مودالات الإدخال المتقدمة
# ==============================================================================
class EmpireButtonModal(discord.ui.Modal, title="➕ إضافة زر تفاعلي جديد"):
    label = discord.ui.TextInput(label="نص الزر (Label)", placeholder="مثال: رتبة الإشعارات", required=True, max_length=80)
    style = discord.ui.TextInput(label="اللون (primary, secondary, success, danger)", placeholder="success", default="success", required=True, max_length=20)
    emoji = discord.ui.TextInput(label="إيموجي الزر (اختياري)", placeholder="🔔", required=False, max_length=60)
    role_id = discord.ui.TextInput(label="آي دي الرتبة (Role ID)", placeholder="123456789012345678", required=True, max_length=25)
    role_action = discord.ui.TextInput(label="نوع الإجراء (add, remove, toggle)", placeholder="toggle", default="toggle", required=True, max_length=15)

    def __init__(self, embed_record_id: str, cog: "EmpireInteractiveCog"):
        super().__init__()
        self.embed_record_id = embed_record_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            r_id = int(self.role_id.value.strip())
        except ValueError:
            return await interaction.response.send_message(embed=err_embed("آي دي الرتبة يجب أن يتكون من أرقام صحيحة فقط."), ephemeral=True)

        style_val = self.style.value.strip().lower()
        if style_val not in ["primary", "secondary", "success", "danger"]:
            style_val = "primary"

        action_val = self.role_action.value.strip().lower()
        if action_val not in ["add", "remove", "toggle"]:
            action_val = "toggle"

        btn_config = {
            "custom_id": f"emp_btn_{random.randint(100000, 999999)}",
            "label": self.label.value.strip(),
            "style": style_val,
            "emoji": self.emoji.value.strip() or None,
            "action_type": "role",
            "role_id": r_id,
            "role_action": action_val
        }

        await self.cog.register_and_apply_component(interaction, self.embed_record_id, button_cfg=btn_config)


# ==============================================================================
# 🎛️ واجهة لوحة التحكم الإمبراطورية للأزرار
# ==============================================================================
class EmpireDashboardView(discord.ui.View):
    def __init__(self, cog: "EmpireInteractiveCog", embed_record: dict, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.embed_record = embed_record
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id or can_manage_server(interaction.user):
            return True
        await interaction.response.send_message("🔒 هذه اللوحة مخصصة للمشرف فقط.", ephemeral=True)
        return False

    @discord.ui.button(label="إضافة زر رتبة", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmpireButtonModal(self.embed_record["_id"], self.cog))

    @discord.ui.button(label="تحديث المظهر في الروم", emoji="🔄", style=discord.ButtonStyle.primary, row=0)
    async def sync_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.cog.sync_message_with_db(interaction, self.embed_record["_id"])

    @discord.ui.button(label="مسح كافة الأزرار", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.cog.clear_all_components(interaction, self.embed_record["_id"])


# ==============================================================================
# 🌟 الـ Cog الإمبراطوري الرئيسي (EmpireInteractiveCog)
# ==============================================================================
class EmpireInteractiveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await run_db(ensure_indexes_sync)
        await self.restore_persistent_views_async()

    async def restore_persistent_views_async(self):
        if buttons_col is None:
            return
        try:
            cursor = buttons_col.find({})
            records = await run_db(lambda: list(cursor))
            for doc in records:
                cfg = {
                    "buttons": doc.get("buttons", []),
                    "select_menus": doc.get("select_menus", [])
                }
                if cfg["buttons"] or cfg["select_menus"]:
                    view = EmpirePersistentView(cfg)
                    self.bot.add_view(view)
        except Exception:
            log.warning("فشل استرجاع الأزرار المستمرة من قاعدة البيانات", exc_info=True)

    async def fetch_embed_record(self, embed_id: str) -> Optional[dict]:
        if embeds_col is None:
            return None
        return await run_db(lambda: embeds_col.find_one({"_id": embed_id}))

    async def register_and_apply_component(self, interaction: discord.Interaction, embed_id: str, button_cfg: Optional[dict] = None):
        rec = await self.fetch_embed_record(embed_id)
        if not rec:
            return await interaction.response.send_message(embed=err_embed("الإيمبد المستهدف غير موجود."), ephemeral=True)

        msg_id = rec.get("message_id")
        doc = await run_db(lambda: buttons_col.find_one({"guild_id": interaction.guild.id, "message_id": msg_id}))

        if not doc:
            doc = {
                "guild_id": interaction.guild.id,
                "message_id": msg_id,
                "embed_id": embed_id,
                "buttons": [],
                "select_menus": []
            }

        if button_cfg:
            if len(doc.get("buttons", [])) >= MAX_BUTTONS_PER_VIEW:
                return await interaction.response.send_message(embed=err_embed(f"عذراً، الحد الأقصى للأزرار هو {MAX_BUTTONS_PER_VIEW} أزرار لكل رسالة."), ephemeral=True)
            doc["buttons"].append(button_cfg)

        await run_db(lambda: buttons_col.update_one(
            {"guild_id": interaction.guild.id, "message_id": msg_id},
            {"$set": doc},
            upsert=True
        ))

        await interaction.response.send_message(embed=ok_embed("✅ تم حفظ الزر بنجاح", "جاري تحديث الرسالة في القناة فوراً."), ephemeral=True)
        await self.execute_message_sync(interaction.guild, rec)

    async def clear_all_components(self, interaction: discord.Interaction, embed_id: str):
        rec = await self.fetch_embed_record(embed_id)
        if not rec:
            return
        await run_db(lambda: buttons_col.delete_one({"guild_id": interaction.guild.id, "message_id": rec.get("message_id")}))
        await self.execute_message_sync(interaction.guild, rec)
        await interaction.followup.send(embed=ok_embed("🗑️ تم التطهير", "تمت إزالة كافة الأزرار والمكونات بنجاح."), ephemeral=True)

    async def sync_message_with_db(self, interaction: discord.Interaction, embed_id: str):
        rec = await self.fetch_embed_record(embed_id)
        if not rec or not rec.get("message_id"):
            return await interaction.followup.send(embed=err_embed("هذا الإيمبد غير منشور في أي قناة حالياً."), ephemeral=True)

        success = await self.execute_message_sync(interaction.guild, rec)
        if success:
            await interaction.followup.send(embed=ok_embed("🔄 تم المزامنة بنجاح", "تم تحديث رسالة الإيمبد والأزرار في القناة."), ephemeral=True)
        else:
            await interaction.followup.send(embed=err_embed("تعذر العثور على الرسالة في القناة الأصلية (ربما تم حذفها)."), ephemeral=True)

    async def execute_message_sync(self, guild: discord.Guild, rec: dict) -> bool:
        channel_id = rec.get("channel_id")
        message_id = rec.get("message_id")
        if not channel_id or not message_id:
            return False

        channel = guild.get_channel_or_thread(channel_id)
        if not channel or not hasattr(channel, "fetch_message"):
            return False

        try:
            msg = await channel.fetch_message(message_id)
        except discord.HTTPException:
            return False

        btn_doc = await run_db(lambda: buttons_col.find_one({"guild_id": guild.id, "message_id": message_id}))
        view = None
        if btn_doc and (btn_doc.get("buttons") or btn_doc.get("select_menus")):
            view = EmpirePersistentView(btn_doc)
            self.bot.add_view(view)

        data = rec.get("data", {})
        embed = discord.Embed(
            description=(data.get("description") or "").replace("\\n", "\n").strip() or None,
            color=int(data.get("color") or DEFAULT_COLOR)
        )
        if data.get("title"):
            embed.title = data["title"]
        if data.get("image_url"):
            embed.set_image(url=data["image_url"])
        if data.get("thumbnail_url"):
            embed.set_thumbnail(url=data["thumbnail_url"])
        if data.get("footer_text"):
            embed.set_footer(text=data["footer_text"])

        for f in data.get("fields", []):
            embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", True))

        content = (data.get("content") or "").strip() or None
        await msg.edit(content=content, embed=embed, view=view)
        return True

    # ---------- الأوامر ----------
    @app_commands.command(name="button_panel", description="[نظام إمبراطوري] لوحة التحكم المركزية لإدارة أزرار ورتب الإيمبدات")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(embed_id="آي دي أو رقم الإيمبد المراد ربط الأزرار به")
    async def button_panel_cmd(self, interaction: discord.Interaction, embed_id: str):
        await interaction.response.defer(ephemeral=True)
        eid = embed_id.strip().lstrip("#")
        rec = await self.fetch_embed_record(eid)

        if not rec or rec["guild_id"] != interaction.guild.id:
            return await interaction.followup.send(embed=err_embed("لم يتم العثور على أي إيمبد مسجل بهذا الرقم."), ephemeral=True)

        panel_embed = discord.Embed(
            title="🎛️ لوحة التحكم الإمبراطورية للأزرار",
            description=f"إدارة الأزرار التفاعلية المرتبطة بالإيمبد المحفوظ `#{rec['_id']}`\nاختر الإجراء المناسب أدناه لتحديث واجهة السيرفر.",
            color=COLOR_BLUE
        )
        await interaction.followup.send(embed=panel_embed, view=EmpireDashboardView(self, rec, interaction.user.id), ephemeral=True)

    @button_panel_cmd.autocomplete("embed_id")
    async def button_panel_autocomplete(self, interaction: discord.Interaction, current: str):
        if embeds_col is None:
            return []
        try:
            rows = await run_db(lambda: list(embeds_col.find({"guild_id": interaction.guild.id}).sort("created_at", -1).limit(25)))
            return [app_commands.Choice(name=clip(f"#{r['_id']} • {r.get('data', {}).get('title', 'بدون عنوان')}", 100), value=str(r["_id"])) for r in rows]
        except Exception:
            return []

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            return await respond_safe(interaction, content="❌ أنت بحاجة لصلاحية **Manage Server** لاستخدام هذه اللوحة.", ephemeral=True)
        log.exception("خطأ في نظام الأزرار", exc_info=error)


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير متوفر في متغيرات البيئة.")
    await bot.add_cog(EmpireInteractiveCog(bot))
