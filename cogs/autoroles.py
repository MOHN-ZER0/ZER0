import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
from typing import Optional, Literal, List

# ==============================================================================
# 🌟 قاعدة البيانات الإمبراطورية المركزية والشاملة لجميع أنظمة الرولات
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
# 🌟 واجهات التفاعل الإمبراطورية المتقدمة (أزرار + قوائم منسدلة)
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
    db = load_mega_db()
    guild_id_str = str(guild.id)
    
    # جلب إعدادات السلوك والإشعارات من قاعدة البيانات
    guild_settings = db.get(guild_id_str, {})
    behavior = guild_settings.get("panel_behavior", "toggle") # toggle, add_only, remove_only
    notifications_enabled = guild_settings.get("notifications_enabled", False)
    assign_msg = guild_settings.get("assign_message", "تم إعطاؤك رول [Role] بنجاح!")
    remove_msg = guild_settings.get("remove_message", "تم إزالة رول [Role] منك بنجاح.")

    has_role = role in member.roles
    response_text = ""

    # تطبيق السلوك المتقدم المأخوذ من لوحة التحكم الاحترافية
    if behavior == "add_only":
        if not has_role:
            await member.add_roles(role)
            response_text = assign_msg.replace("[Role]", role.mention)
        else:
            response_text = f"⚠️ **أنت تمتلك رول {role.mention} بالفعل ولا يمكن إضافته مرة أخرى!**"
    elif behavior == "remove_only":
        if has_role:
            await member.remove_roles(role)
            response_text = remove_msg.replace("[Role]", role.mention)
        else:
            response_text = f"⚠️ **أنت لا تمتلك رول {role.mention} أساساً لكي تقوم بإزالته!**"
    else: # الوضع الافتراضي: تبديل (Toggle)
        if has_role:
            await member.remove_roles(role)
            response_text = remove_msg.replace("[Role]", role.mention)
        else:
            await member.add_roles(role)
            response_text = assign_msg.replace("[Role]", role.mention)

    await interaction.response.send_message(response_text, ephemeral=True)

    # إرسال إشعارات خاصة إذا كانت مفعلة
    if notifications_enabled:
        try:
            if not has_role:
                await member.send(f"🎉 **إشعار سيرفر {guild.name}:** {assign_msg.replace('[Role]', role.name)}")
            else:
                await member.send(f"🔔 **إشعار سيرفر {guild.name}:** {remove_msg.replace('[Role]', role.name)}")
        except:
            pass


# ==============================================================================
# 🌟 الـ Cog العملاق والمطلق لإدارة كافة أنظمة الرولات الاحترافية
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
    # 1. نظام الرولات التلقائية (Auto Roles) للأعضاء والبوتات
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="mega_ar_autoroles",
        description="[الرولات التلقائية] تحديد رولات تلقائية فورية تُمنح للأعضاء الجدد أو البوتات عند انضمامهم"
    )
    @app_commands.describe(
        target_type="هل الرول مخصص للأعضاء العاديين (member) أم للبوتات (bot)",
        role="الرول المراد إضافته أو إزالته من القائمة التلقائية"
    )
    @app_commands.choices(
        target_type=[
            app_commands.Choice(name="رولات المستخدمين (Members)", value="member"),
            app_commands.Choice(name="رولات البوتات (Bots)", value="bot")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mega_ar_autoroles(self, interaction: discord.Interaction, target_type: Literal["member", "bot"], role: discord.Role):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        if role.id not in self.database[guild_id]["auto_roles"][target_type]:
            self.database[guild_id]["auto_roles"][target_type].append(role.id)
            save_mega_db(self.database)
            await interaction.response.send_message(f"✅ **تمت إضافة الرول {role.mention} إلى قائمة الرولات التلقائية لـ ({target_type}) بنجاح.**", ephemeral=True)
        else:
            self.database[guild_id]["auto_roles"][target_type].remove(role.id)
            save_mega_db(self.database)
            await interaction.response.send_message(f"🗑️ **تم إزالة الرول {role.mention} من قائمة الرولات التلقائية لـ ({target_type}).**", ephemeral=True)

    # --------------------------------------------------------------------------
    # 2. نظام الرولات اللاصقة (Sticky Roles)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="mega_ar_sticky",
        description="[الرولات اللاصقة] تفعيل أو إلغاء حفظ رولات الأعضاء عند مغادرتهم واستعادتها تلقائياً عند عودتهم"
    )
    @app_commands.describe(status="حالة التفعيل (True للتفعيل الكامل، False للإيقاف)")
    @app_commands.checks.has_permissions(administrator=True)
    async def mega_ar_sticky(self, interaction: discord.Interaction, status: bool):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        self.database[guild_id]["sticky"]["enabled"] = status
        save_mega_db(self.database)
        await interaction.response.send_message(f"📌 **تم تحديث نظام الرولات اللاصقة إلى:** `{'مفعل ✅' if status else 'معطل ❌'}`", ephemeral=True)

    # --------------------------------------------------------------------------
    # 3. نظام الرولات المؤجلة (Delayed Roles)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="mega_ar_delayed",
        description="[الرولات المؤجلة] منح رول تلقائي للأعضاء الجدد بعد بقائهم في السيرفر لفترة زمنية محددة"
    )
    @app_commands.describe(
        role="الرول المراد منحه بعد انقضاء الوقت",
        minutes_delay="مدة البقاء اللازمة في السيرفر بالدقائق"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mega_ar_delayed(self, interaction: discord.Interaction, role: discord.Role, minutes_delay: int):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        self.database[guild_id]["delayed"].append({
            "role_id": role.id,
            "delay_minutes": minutes_delay
        })
        save_mega_db(self.database)
        await interaction.response.send_message(f"⏳ **تمت إضافة قاعدة رولات مؤجلة: منح {role.mention} تلقائياً بعد {minutes_delay} دقيقة من الانضمام.**", ephemeral=True)

    # --------------------------------------------------------------------------
    # 4. نظام قواعد الدعوات (Invite Roles)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="mega_ar_invite",
        description="[قواعد الدعوات] منح رول تلقائي عند دخول العضو باستخدام رابط دعوة مخصص ومحدد"
    )
    @app_commands.describe(
        invite_code="كود الدعوة فقط (مثال: إذا كان الرابط discord.gg/ziuo اكتب ziuo)",
        role="الرول المرتبط بهذه الدعوة"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mega_ar_invite(self, interaction: discord.Interaction, invite_code: str, role: discord.Role):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = self._default_guild_structure()

        self.database[guild_id]["invites"].append({
            "code": invite_code.strip(),
            "role_id": role.id
        })
        save_mega_db(self.database)
        await interaction.response.send_message(f"🔗 **تم ربط كود الدعوة `{invite_code}` بمنح رول {role.mention} فور انضمام العضو.**", ephemeral=True)

    # --------------------------------------------------------------------------
    # 5. النظام الخارق للرولات ذاتية التعيين (Self-Roles Panels & Behaviors)
    # --------------------------------------------------------------------------
    @app_commands.command(
        name="mega_ar_panel",
        description="[الرولات ذاتية التعيين] إنشاء لوحة تفاعلية متكاملة (أزرار أو قوائم) مع تحديد السلوك والإشعارات"
    )
    @app_commands.describe(
        channel="روم إرسال لوحة الرولات",
        title="عنوان اللوحة البارز",
        interaction_type="نوع التفاعل: أزرار تفاعلية (button) أم قائمة منسدلة (select)",
        behavior="سلوك التفاعل: تبديل (toggle)، إضافة فقط (add_only)، أو إزالة فقط (remove_only)",
        notifications="تفعيل الإشعارات الخاصة عند استلام أو فقدان الرول (True / False)",
        role1="الرول الأول", label1="اسم الزر/الخيار الأول", emoji1="إيموجي الزر الأول (اختياري)",
        role2="الرول الثاني (اختياري)", label2="اسم الزر الثاني (اختياري)", emoji2="إيموجي الزر الثاني (اختياري)"
    )
    @app_choices(
        interaction_type=[
            app_commands.Choice(name="أزرار تفاعلية (Buttons)", value="button"),
            app_commands.Choice(name="قائمة منسدلة (Select Menu)", value="select")
        ],
        behavior=[
            app_commands.Choice(name="تبديل - Toggle (امتلاك عدة رولات وتغييرها)", value="toggle"),
            app_commands.Choice(name="إضافة فقط - Add Only (منح رول جديد بكل مرة)", value="add_only"),
            app_commands.Choice(name="إزالة فقط - Remove Only (عكس الوضع القياسي)", value="remove_only")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mega_ar_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        interaction_type: Literal["button", "select"],
        behavior: Literal["toggle", "add_only", "remove_only"],
        notifications: bool,
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

        # حفظ الإعدادات المتقدمة والسلوك في قاعدة البيانات الخاصة بالسيرفر
        self.database[guild_id]["panel_behavior"] = behavior
        self.database[guild_id]["notifications_enabled"] = notifications
        save_mega_db(self.database)

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
            description="> **اختر رولاتك المفضلة وتفاعل مع اللوحة بالأسفل بكل سهولة وحرية مطلقة!** 👇",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="ZIUO Imperial Enterprise Auto-Roles System")

        view = EnterpriseMegaInteractiveView(self.bot, guild_id, panel_data)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ **تم إنشاء لوحة الرولات الذاتية الإمبراطورية بنجاح في روم** {channel.mention}!", ephemeral=True)

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
            "pending_delayed": [],
            "panel_behavior": "toggle",
            "notifications_enabled": False,
            "assign_message": "تم إعطاؤك رول [Role] بنجاح!",
            "remove_message": "تم إزالة رول [Role] منك بنجاح."
        }

    # --- 🛡️ مستمعو الأحداث الآلية والتنفيذ التلقائي بالخلفية ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        if guild_id not in self.database:
            return

        db_guild = self.database[guild_id]

        # 1. تطبيق الرولات التلقائية الفورية للأعضاء أو البوتات
        target_key = "bot" if member.bot else "member"
        for r_id in db_guild.get("auto_roles", {}).get(target_key, []):
            role = member.guild.get_role(r_id)
            if role:
                try:
                    await member.add_roles(role)
                except:
                    pass

        # 2. تطبيق الرولات اللاصقة واسترجاع رولات العضو السابقة عند العودة
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

        # 3. تتبع قواعد الدعوات ومنح الرولات المرتبطة بالرابط
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

        # 4. تسجيل الموقت للرولات المؤجلة
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

        # حفظ الرولات الحالية للرولات اللاصقة عند المغادرة
        if db_guild.get("sticky", {}).get("enabled", False):
            member_roles = [r.id for r in member.roles if r != member.guild.default_role]
            if "saved_members_roles" not in db_guild:
                db_guild["saved_members_roles"] = {}
            db_guild["saved_members_roles"][str(member.id)] = member_roles
            save_mega_db(self.database)

    # اللوب الآلي لفحص ومنح الرولات المؤجلة بدقة فائقة
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
