import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
from typing import Optional, Literal

# ==============================================================================
# 🌟 قاعدة البيانات المركزية لأنظمة الرولات التلقائية
# ==============================================================================
MEGA_DB_FILE = "ziuo_mega_autoroles_enterprise_database.json"

def load_mega_db():
    if os.path.exists(MEGA_DB_FILE):
        try:
            with open(MEGA_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_mega_db(data):
    with open(MEGA_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==============================================================================
# 🌟 واجهات التفاعل الأزرار والقوائم المنسدلة للرولات الذاتية
# ==============================================================================
class EnterpriseMegaInteractiveView(discord.ui.View):
    def __init__(self, bot, guild_id, panel_data):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.panel_data = panel_data
        
        interaction_type = panel_data.get("interaction_type", "button")
        roles_config = panel_data.get("roles", [])

        if interaction_type == "button":
            for item in roles_config:
                self.add_item(EnterpriseMegaButton(item))
        elif interaction_type == "select":
            self.add_item(EnterpriseMegaSelectMenu(roles_config, panel_data))

class EnterpriseMegaButton(discord.ui.Button):
    def __init__(self, item_data):
        super().__init__(
            label=item_data.get("label"),
            emoji=item_data.get("emoji"),
            style=discord.ButtonStyle.secondary,
            custom_id=f"mega_role_btn_{item_data['role_id']}"
        )
        self.role_id = int(item_data["role_id"])

    async def callback(self, interaction: discord.Interaction):
        await process_enterprise_role_action(interaction, self.role_id)

class EnterpriseMegaSelectMenu(discord.ui.Select):
    def __init__(self, roles_config, panel_data):
        options = []
        for item in roles_config:
            options.append(discord.SelectOption(
                label=item.get("label", "رول مخصص"),
                value=str(item["role_id"]),
                emoji=item.get("emoji"),
                description=item.get("description", "اضغط للحصول على الرول أو إزالته")
            ))
        super().__init__(
            placeholder=panel_data.get("placeholder", "اختر رولاتك التفاعلية بكل حرية..."),
            min_values=1,
            max_values=1,
            options=options,
            custom_id="mega_role_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        await process_enterprise_role_action(interaction, role_id)


async def process_enterprise_role_action(interaction: discord.Interaction, role_id: int):
    guild = interaction.guild
    role = guild.get_role(role_id)
    if not role:
        await interaction.response.send_message("❌ **عذراً، هذا الرول لم يعد موجوداً في السيرفر!**", ephemeral=True)
        return

    member = interaction.user
    has_role = role in member.roles

    if has_role:
        await member.remove_roles(role)
        await interaction.response.send_message(f"📤 **تم إزالة رول {role.mention} منك بنجاح.**", ephemeral=True)
    else:
        await member.add_roles(role)
        await interaction.response.send_message(f"📥 **تم إعطاؤك رول {role.mention} بنجاح!**", ephemeral=True)


# ==============================================================================
# 🌟 الـ Cog المبسط والاحترافي لإدارة الرولات (أمران فقط لكل النظام)
# ==============================================================================
class ZiuoMegaAutoRolesEnterpriseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.database = load_mega_db()
        self.invites_cache = {}
        self.delayed_roles_check.start()
        self.save_cache_loop.start()

    def cog_unload(self):
        self.delayed_roles_check.cancel()
        self.save_cache_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self.invites_cache[guild.id] = await guild.invites()
            except:
                pass

    @tasks.loop(minutes=10)
    async def save_cache_loop(self):
        save_mega_db(self.database)

    # --------------------------------------------------------------------------
    # 1. الأمر الشامل المدمج للرولات التلقائية (Auto, Sticky, Delayed, Invite)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="autorole",
        description="[نظام الرولات التلقائية] إدارة الرولات التلقائية، اللاصقة، المؤجلة، ودعوات السيرفر"
    )
    @app_commands.describe(
        action="اختر نوع النظام المراد ضبطه",
        target_type="نوع العضو (للأعضاء الجدد أو للبوتات - يستخدم مع خيار autorole)",
        role="الرول المراد إضافته أو تعديله",
        status="حالة التفعيل (للصاق - True / False)",
        minutes_delay="مدة التأخير بالدقائق (للـ Delayed)",
        invite_code="كود دعوة السيرفر (للـ Invite)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="رول تلقائي فوري (Auto-Role)", value="autorole"),
            app_commands.Choice(name="رول لاصق عند العودة (Sticky-Role)", value="sticky"),
            app_commands.Choice(name="رول مؤجل بعد فترة (Delayed-Role)", value="delayed"),
            app_commands.Choice(name="رول برابط دعوة محدد (Invite-Role)", value="invite")
        ],
        target_type=[
            app_commands.Choice(name="أعضاء (Members)", value="member"),
            app_commands.Choice(name="بوتات (Bots)", value="bot")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autorole_manager(
        self,
        interaction: discord.Interaction,
        action: Literal["autorole", "sticky", "delayed", "invite"],
        target_type: Optional[Literal["member", "bot"]] = "member",
        role: Optional[discord.Role] = None,
        status: Optional[bool] = None,
        minutes_delay: Optional[int] = None,
        invite_code: Optional[str] = None
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        db_guild = self.database[guild_id]

        if action == "autorole":
            if not role:
                await interaction.response.send_message("❌ **يجب تحديد الرول المطلوب!**", ephemeral=True)
                return
            if role.id not in db_guild["auto_roles"][target_type]:
                db_guild["auto_roles"][target_type].append(role.id)
                save_mega_db(self.database)
                await interaction.response.send_message(f"✅ **تمت إضافة الرول {role.mention} لقائمة الرولات التلقائية لـ ({target_type}).**", ephemeral=True)
            else:
                db_guild["auto_roles"][target_type].remove(role.id)
                save_mega_db(self.database)
                await interaction.response.send_message(f"🗑️ **تم إزالة الرول {role.mention} من قائمة الرولات التلقائية.**", ephemeral=True)

        elif action == "sticky":
            if status is None:
                await interaction.response.send_message("❌ **يجب تحديد حالة التفعيل (True أو False)!**", ephemeral=True)
                return
            db_guild["sticky"]["enabled"] = status
            save_mega_db(self.database)
            await interaction.response.send_message(f"📌 **تم تحديث نظام الرولات اللاصقة إلى:** `{'مفعل ✅' if status else 'معطل ❌'}`", ephemeral=True)

        elif action == "delayed":
            if not role or minutes_delay is None:
                await interaction.response.send_message("❌ **يجب تحديد الرول ومدة الدقائق المطلوبة!**", ephemeral=True)
                return
            db_guild["delayed"].append({"role_id": role.id, "delay_minutes": minutes_delay})
            save_mega_db(self.database)
            await interaction.response.send_message(f"⏳ **تمت إضافة قاعدة منح رول {role.mention} تلقائياً بعد {minutes_delay} دقيقة.**", ephemeral=True)

        elif action == "invite":
            if not role or not invite_code:
                await interaction.response.send_message("❌ **يجب تحديد الرول وكود الدعوة!**", ephemeral=True)
                return
            db_guild["invites"].append({"code": invite_code.strip(), "role_id": role.id})
            save_mega_db(self.database)
            await interaction.response.send_message(f"🔗 **تم ربط كود الدعوة `{invite_code}` بمنح رول {role.mention} فور الانضمام.**", ephemeral=True)

    # --------------------------------------------------------------------------
    # 2. أمر إنشاء لوحة الرولات الذاتية (Self-Roles Panel)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="autopanel",
        description="[الرولات ذاتية التعيين] إنشاء لوحة تفاعلية متكاملة (أزرار أو قوائم منسدلة)"
    )
    @app_commands.describe(
        channel="روم إرسال لوحة الرولات",
        title="عنوان اللوحة البارز",
        interaction_type="نوع التفاعل: أزرار تفاعلية (button) أم قائمة منسدلة (select)",
        role1="الرول الأول", label1="اسم الزر/الخيار الأول", emoji1="إيموجي الزر الأول (اختياري)",
        role2="الرول الثاني (اختياري)", label2="اسم الزر الثاني (اختياري)", emoji2="إيموجي الزر الثاني (اختياري)"
    )
    @app_commands.choices(
        interaction_type=[
            app_commands.Choice(name="أزرار تفاعلية (Buttons)", value="button"),
            app_commands.Choice(name="قائمة منسدلة (Select Menu)", value="select")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autopanel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        interaction_type: Literal["button", "select"],
        role1: discord.Role,
        label1: str,
        emoji1: Optional[str] = None,
        role2: Optional[discord.Role] = None,
        label2: Optional[str] = None,
        emoji2: Optional[str] = None
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        roles_config = [{"role_id": role1.id, "label": label1, "emoji": emoji1, "description": f"الحصول على رول {role1.name}"}]
        if role2 and label2:
            roles_config.append({"role_id": role2.id, "label": label2, "emoji": emoji2, "description": f"الحصول على رول {role2.name}"})

        panel_data = {
            "interaction_type": interaction_type,
            "roles": roles_config,
            "placeholder": "اختر رولاتك التفاعلية بكل حرية من هنا..."
        }

        embed = discord.Embed(
            title=f"🎨 **{title}**",
            description="> **اختر رولاتك المفضلة وتفاعل مع اللوحة بالأسفل بكل سهولة!** 👇",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="ZIUO Imperial Enterprise Auto-Roles System")

        view = EnterpriseMegaInteractiveView(self.bot, guild_id, panel_data)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ **تم إنشاء لوحة الرولات الذاتية بنجاح في روم** {channel.mention}!", ephemeral=True)

    # --------------------------------------------------------------------------
    # ⚙️ هيكل البيانات الافتراضي للسيرفر
    # --------------------------------------------------------------------------
    def _default_guild_structure(self):
        return {
            "auto_roles": {"member": [], "bot": []},
            "sticky": {"enabled": False},
            "delayed": [],
            "invites": [],
            "saved_members_roles": {},
            "pending_delayed": []
        }

    # --- 🛡️ مستمعو الأحداث الآلية بالخلفية ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        if guild_id not in self.database:
            return

        db_guild = self.database[guild_id]

        # 1. الرولات الفورية
        target_key = "bot" if member.bot else "member"
        for r_id in db_guild.get("auto_roles", {}).get(target_key, []):
            role = member.guild.get_role(r_id)
            if role:
                try:
                    await member.add_roles(role)
                except:
                    pass

        # 2. الرولات اللاصقة
        if db_guild.get("sticky", {}).get("enabled", False):
            saved = db_guild.get("saved_members_roles", {})
            if str(member.id) in saved:
                for r_id in saved[str(member.id)]:
                    role = member.guild.get_role(r_id)
                    if role:
                        try:
                            await member.add_roles(role)
                        except:
                            pass

        # 3. قواعد الدعوات
        try:
            old_invites = self.invites_cache.get(member.guild.id, [])
            new_invites = await member.guild.invites()
            self.invites_cache[member.guild.id] = new_invites

            used_invite = None
            for new_inv in new_invites:
                for old_inv in old_invites:
                    if new_inv.code == old_inv.code and new_inv.uses > old_inv.uses:
                        used_invite = new_inv
                        break

            if used_invite:
                for inv_rule in db_guild.get("invites", []):
                    if inv_rule["code"] == used_invite.code:
                        role = member.guild.get_role(inv_rule["role_id"])
                        if role:
                            await member.add_roles(role)
        except:
            pass

        # 4. الرولات المؤجلة
        if "pending_delayed" not in db_guild:
            db_guild["pending_delayed"] = []
        db_guild["pending_delayed"].append({
            "member_id": member.id,
            "joined_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_mega_db(self.database)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = str(member.guild.id)
        if guild_id not in self.database:
            return
        db_guild = self.database[guild_id]

        if db_guild.get("sticky", {}).get("enabled", False):
            member_roles = [r.id for r in member.roles if r != member.guild.default_role]
            if "saved_members_roles" not in db_guild:
                db_guild["saved_members_roles"] = {}
            db_guild["saved_members_roles"][str(member.id)] = member_roles
            save_mega_db(self.database)

    @tasks.loop(minutes=1)
    async def delayed_roles_check(self):
        db = load_mega_db()
        now = datetime.datetime.utcnow()

        for guild_id, db_guild in db.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            delayed_rules = db_guild.get("delayed", [])
            pending = db_guild.get("pending_delayed", [])
            if not delayed_rules or not pending:
                continue

            remaining_pending = []
            for item in pending:
                member = guild.get_member(item["member_id"])
                if not member:
                    continue

                joined_time = datetime.datetime.strptime(item["joined_at"], "%Y-%m-%d %H:%M:%S")
                elapsed_minutes = (now - joined_time).total_seconds() / 60

                for rule in delayed_rules:
                    if elapsed_minutes >= rule["delay_minutes"]:
                        role = guild.get_role(rule["role_id"])
                        if role and role not in member.roles:
                            try:
                                await member.add_roles(role)
                            except:
                                pass
                remaining_pending.append(item)

            db_guild["pending_delayed"] = remaining_pending
            save_mega_db(db)

    @delayed_roles_check.before_loop
    async def before_delayed_roles_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ZiuoMegaAutoRolesEnterpriseCog(bot))
