import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, Literal

# ==============================================================================
# 🌟 إعدادات وقاعدة بيانات نظام الترحيب والمغادرة (Enterprise Safe Core)
# ==============================================================================
MEGA_WELCOME_CONFIG = {
    "welcome_enabled": True,
    "leave_enabled": True,
    "dm_welcome_enabled": False,
    "card_enabled": True,
    "autorole_enabled": False,
    
    "welcome_channel_id": None,
    "leave_channel_id": None,
    "autorole_id": None,
    
    "card_image_url": "https://probot.media/Bwt5SOHnkM.png",
    
    "welcome_message": (
        "## ⚡ ╎ WELCOME TO ZIUO EMPIRE ⚡\n\n"
        "أهلاً بك يا بطل `[userName]` في سيرفر **[server]**! ⚡\n"
        "نورتنا وشرفتنا بانضمامك لعائلتنا الكبيرة، ونتمنى لك أوقات ممتعة.\n\n"
        "> أنت العضو رقم **[memberCount]** في إمبراطوريتنا!\n"
        "> 👤 **تمت دعوتك بواسطة:** [inviterName] (عدد الدعوات: [invites])\n"
        "> 📅 **تاريخ إنشاء حسابك:** [accountCreated]"
    ),
    
    "leave_message": (
        "👋 ╎ غادرنا العضو **[userName]**...\n"
        "نتمنى له التوفيق، وأصبح عدد الأعضاء الحالي **[memberCount]**."
    ),
    
    "dm_message": (
        "مرحباً بك يا [userName] في سيرفر ZIUO! نأمل أن تستمتع بوقتك معنا وتلتزم بالقوانين."
    )
}

MEGA_SERVER_INVITES_CACHE = {}


# ==============================================================================
# 📝 نوافذ الإدخال التفاعلية (Modals) لتعديل النصوص
# ==============================================================================
class WelcomeTextModal(discord.ui.Modal, title="تعديل رسالة الترحيب العامة"):
    text_input = discord.ui.TextInput(
        label="رسالة الترحيب الجديدة",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب رسالتك هنا... (يمكنك استخدام الاختصارات مثل [userName], [server], [memberCount])",
        default=MEGA_WELCOME_CONFIG["welcome_message"],
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["welcome_message"] = self.text_input.value
        await interaction.response.send_message("✅ **تم تحديث رسالة الترحيب بنجاح!**", ephemeral=True)


class LeaveTextModal(discord.ui.Modal, title="تعديل رسالة المغادرة"):
    text_input = discord.ui.TextInput(
        label="رسالة المغادرة الجديدة",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب رسالة المغادرة هنا...",
        default=MEGA_WELCOME_CONFIG["leave_message"],
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["leave_message"] = self.text_input.value
        await interaction.response.send_message("✅ **تم تحديث رسالة المغادرة بنجاح!**", ephemeral=True)


class DMTextModal(discord.ui.Modal, title="تعديل رسالة الخاص (DM)") :
    text_input = discord.ui.TextInput(
        label="رسالة الخاص الجديدة",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب رسالة الخاص هنا...",
        default=MEGA_WELCOME_CONFIG["dm_message"],
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["dm_message"] = self.text_input.value
        MEGA_WELCOME_CONFIG["dm_welcome_enabled"] = True
        await interaction.response.send_message("✅ **تم تحديث وتفعيل رسالة الخاص (DM) بنجاح!**", ephemeral=True)


# ==============================================================================
# 🎛️ لوحة التحكم التفاعلية الكبرى بالزرار (Dashboard UI) نفس استايل الصورة
# ==============================================================================
class MegaWelcomeControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.refresh_labels()

    def refresh_labels(self):
        self.btn_w_toggle.label = f"الترحيب: {'مفعل ✅' if MEGA_WELCOME_CONFIG['welcome_enabled'] else 'مفعل ❌'}"
        self.btn_w_toggle.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['welcome_enabled'] else discord.ButtonStyle.red

        self.btn_l_toggle.label = f"المغادرة: {'مفعل ✅' if MEGA_WELCOME_CONFIG['leave_enabled'] else 'مفعل ❌'}"
        self.btn_l_toggle.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['leave_enabled'] else discord.ButtonStyle.red

        self.btn_dm_toggle.label = f"ترحيب الخاص: {'مفعل ✅' if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else 'مفعل ❌'}"
        self.btn_dm_toggle.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else discord.ButtonStyle.red

        self.btn_card_toggle.label = f"بطاقة الصورة: {'مفعل ✅' if MEGA_WELCOME_CONFIG['card_enabled'] else 'مفعل ❌'}"
        self.btn_card_toggle.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['card_enabled'] else discord.ButtonStyle.red

    @discord.ui.button(label="الترحيب: مفعل ✅", style=discord.ButtonStyle.green, row=0)
    async def btn_w_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['welcome_enabled'] = not MEGA_WELCOME_CONFIG['welcome_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="تعديل رسالة الترحيب", style=discord.ButtonStyle.blurple, row=0)
    async def btn_edit_w(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(WelcomeTextModal())

    @discord.ui.button(label="المغادرة: مفعل ✅", style=discord.ButtonStyle.green, row=1)
    async def btn_l_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['leave_enabled'] = not MEGA_WELCOME_CONFIG['leave_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="تعديل رسالة المغادرة", style=discord.ButtonStyle.blurple, row=1)
    async def btn_edit_l(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(LeaveTextModal())

    @discord.ui.button(label="ترحيب الخاص: مفعل ❌", style=discord.ButtonStyle.red, row=2)
    async def btn_dm_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['dm_welcome_enabled'] = not MEGA_WELCOME_CONFIG['dm_welcome_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="تعديل رسالة الخاص", style=discord.ButtonStyle.blurple, row=2)
    async def btn_edit_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(DMTextModal())

    @discord.ui.button(label="بطاقة الصورة: مفعل ✅", style=discord.ButtonStyle.green, row=3)
    async def btn_card_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['card_enabled'] = not MEGA_WELCOME_CONFIG['card_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="اختصارات الترحيب (Variables)", style=discord.ButtonStyle.gray, row=3)
    async def btn_variables(self, interaction: discord.Interaction, button: discord.ui.Button):
        vars_text = (
            "📌 **قائمة الاختصارات المتاحة للاستخدام في النصوص:**\n\n"
            "🔹 `[user]` أو `[userName]` ⟵ لإرسال منشن أو اسم العضو الجديد.\n"
            "🔹 `[server]` ⟵ اسم السيرفر الحالي.\n"
            "🔹 `[memberCount]` ⟵ عدد أعضاء السيرفر الحالي.\n"
            "🔹 `[inviterName]` ⟵ اسم الشخص اللي دعى العضو.\n"
            "🔹 `[invites]` ⟵ عدد دعوات الشخص الداعي.\n"
            "🔹 `[accountCreated]` ⟵ تاريخ إنشاء حساب العضو."
        )
        await interaction.response.send_message(vars_text, ephemeral=True)


# ==============================================================================
# 🌟 Cog النظام المحصن للترحيب والمغادرة (Safe Welcome Cog)
# ==============================================================================
class MegaWelcomeSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        for guild in self.bot.guilds:
            try:
                MEGA_SERVER_INVITES_CACHE[guild.id] = await guild.invites()
            except Exception as e:
                print(f"[CACHE LOAD ERROR]: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        try:
            MEGA_SERVER_INVITES_CACHE[guild.id] = await guild.invites()
        except Exception as e:
            print(f"[GUILD JOIN ERROR]: {e}")

    @app_commands.command(
        name="welcome",
        description="[نظام إمبراطوري موحد] لوحة التحكم والأزرار التفاعلية للترحيب والمغادرة"
    )
    @app_commands.describe(
        welcome_channel="تحديد روم الترحيب العام (اختياري)",
        leave_channel="تحديد روم المغادرة (اختياري)",
        autorole="تحديد الرتبة التلقائية عند الدخول (اختياري)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_manager(
        self,
        interaction: discord.Interaction,
        welcome_channel: Optional[discord.TextChannel] = None,
        leave_channel: Optional[discord.TextChannel] = None,
        autorole: Optional[discord.Role] = None,
    ):
        if welcome_channel:
            MEGA_WELCOME_CONFIG["welcome_channel_id"] = welcome_channel.id
        if leave_channel:
            MEGA_WELCOME_CONFIG["leave_channel_id"] = leave_channel.id
        if autorole:
            MEGA_WELCOME_CONFIG["autorole_id"] = autorole.id
            MEGA_WELCOME_CONFIG["autorole_enabled"] = True

        wch = MEGA_WELCOME_CONFIG["welcome_channel_id"]
        lch = MEGA_WELCOME_CONFIG["leave_channel_id"]
        arh = MEGA_WELCOME_CONFIG["autorole_id"]
        
        embed = discord.Embed(
            title="⚙️ لوحة تحكم نظام الترحيب والمغادرة - ZIUO CORE",
            description=(
                f"مرحباً بك في لوحة الإدارة المركزية لنظام الترحيب والأحداث.\n"
                f"يمكنك التحكم بكافة الخصائص والإعدادات بسلاسة عبر الأزرار أدناه:\n\n"
                f"📥 **روم الترحيب:** {f'<#{wch}>' if wch else '`غير محدد ❌`'}\n"
                f"📤 **روم المغادرة:** {f'<#{lch}>' if lch else '`غير محدد ❌`'}\n"
                f"🛡️ **الرتبة التلقائية:** {f'<@&{arh}>' if MEGA_WELCOME_CONFIG['autorole_enabled'] and arh else '`معطلة ❌`'}\n"
                f"🖼️ **صورة البطاقة:** [معاينة الرابط]({MEGA_WELCOME_CONFIG['card_image_url']})\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="ZIUO Admin Core ✦ Ultimate Management Panel")
        await interaction.response.send_message(embed=embed, view=MegaWelcomeControlView(), ephemeral=True)

    def format_text(self, text: str, member: discord.Member, inviter_name: str, invites_count: int) -> str:
        return (
            text.replace("[user]", member.mention)
                .replace("[userName]", member.name)
                .replace("[memberCount]", str(member.guild.member_count))
                .replace("[server]", member.guild.name)
                .replace("[inviterName]", inviter_name)
                .replace("[invites]", str(invites_count))
                .replace("[accountCreated]", member.created_at.strftime("%Y-%m-%d"))
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if MEGA_WELCOME_CONFIG["autorole_enabled"] and MEGA_WELCOME_CONFIG["autorole_id"]:
            try:
                role = member.guild.get_role(MEGA_WELCOME_CONFIG["autorole_id"])
                if role:
                    await member.add_roles(role, reason="ZIUO Auto-Role System")
            except Exception as e:
                print(f"[AUTOROLE ERROR]: {e}")

        if MEGA_WELCOME_CONFIG["dm_welcome_enabled"]:
            try:
                dm_text = self.format_text(MEGA_WELCOME_CONFIG["dm_message"], member, "خاص", 0)
                await member.send(dm_text)
            except Exception:
                pass

        if not MEGA_WELCOME_CONFIG["welcome_enabled"]:
            return

        channel_id = MEGA_WELCOME_CONFIG["welcome_channel_id"]
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        inviter_name = "رابط دعوة عامة / غير معروف"
        invites_count = 0
        
        try:
            old_invites = MEGA_SERVER_INVITES_CACHE.get(member.guild.id, [])
            new_invites = await member.guild.invites()
            MEGA_SERVER_INVITES_CACHE[member.guild.id] = new_invites

            for new_inv in new_invites:
                for old_inv in old_invites:
                    if new_inv.code == old_inv.code and new_inv.uses > old_inv.uses:
                        if new_inv.inviter:
                            inviter_name = new_inv.inviter.name
                            invites_count = sum(inv.uses for inv in new_invites if inv.inviter and inv.inviter.id == new_inv.inviter.id)
                        break
        except Exception as e:
            print(f"[INVITE TRACKER ERROR]: {e}")

        formatted_msg = self.format_text(MEGA_WELCOME_CONFIG["welcome_message"], member, inviter_name, invites_count)

lnb = "\n"
