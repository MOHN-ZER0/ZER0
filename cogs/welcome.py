import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional

# ==============================================================================
# 🌟 إعدادات وقاعدة بيانات نظام الترحيب والمغادرة العملاق (Enterprise Mega Core)
# ==============================================================================
MEGA_WELCOME_CONFIG = {
    # الحالات العامة
    "welcome_enabled": True,
    "leave_enabled": True,
    "dm_welcome_enabled": False,
    "card_enabled": True,
    "autorole_enabled": False,
    
    # الرومات والرتب
    "welcome_channel_id": None,
    "leave_channel_id": None,
    "autorole_id": None,
    
    # إعدادات التصميم والصور
    "card_image_url": "https://probot.media/Bwt5SOHnkM.png",
    "embed_color": 0x2B2D31,
    
    # النصوص الافتراضية القابلة للتعديل المطلق
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

# ذاكرة مؤقتة لتتبع الدعوات بدقة فائقة
MEGA_SERVER_INVITES_CACHE = {}


# ==============================================================================
# 🎛️ لوحة التحكم التفاعلية الكبرى (Mega Enterprise Dashboard UI)
# ==============================================================================
class MegaWelcomeControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.refresh_labels()

    def refresh_labels(self):
        self.btn_w.label = f"الترحيب: {'[مفعل ✅]' if MEGA_WELCOME_CONFIG['welcome_enabled'] else '[معطل ❌]'}"
        self.btn_w.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['welcome_enabled'] else discord.ButtonStyle.red

        self.btn_l.label = f"المغادرة: {'[مفعل ✅]' if MEGA_WELCOME_CONFIG['leave_enabled'] else '[معطل ❌]'}"
        self.btn_l.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['leave_enabled'] else discord.ButtonStyle.red

        self.btn_dm.label = f"ترحيب الخاص (DM): {'[مفعل ✅]' if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else '[معطل ❌]'}"
        self.btn_dm.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else discord.ButtonStyle.red

        self.btn_card.label = f"بطاقة الصورة: {'[مفعل ✅]' if MEGA_WELCOME_CONFIG['card_enabled'] else '[معطل ❌]'}"
        self.btn_card.style = discord.ButtonStyle.green if MEGA_WELCOME_CONFIG['card_enabled'] else discord.ButtonStyle.red

    @discord.ui.button(label="الترحيب", style=discord.ButtonStyle.green, row=0)
    async def btn_w(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['welcome_enabled'] = not MEGA_WELCOME_CONFIG['welcome_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="المغادرة", style=discord.ButtonStyle.green, row=0)
    async def btn_l(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['leave_enabled'] = not MEGA_WELCOME_CONFIG['leave_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="ترحيب الخاص", style=discord.ButtonStyle.green, row=1)
    async def btn_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['dm_welcome_enabled'] = not MEGA_WELCOME_CONFIG['dm_welcome_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="بطاقة الصورة", style=discord.ButtonStyle.green, row=1)
    async def btn_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        MEGA_WELCOME_CONFIG['card_enabled'] = not MEGA_WELCOME_CONFIG['card_enabled']
        self.refresh_labels()
        await interaction.response.edit_message(view=self)


# ==============================================================================
# 🌟 Cog الترحيب والمغادرة الضخم والمتكامل (Mega Welcome Cog Engine)
# ==============================================================================
class MegaWelcomeSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        for guild in self.bot.guilds:
            try:
                MEGA_SERVER_INVITES_CACHE[guild.id] = await guild.invites()
            except:
                pass

    # 1. لوحة التحكم الكبرى وشبكة الإعدادات
    @app_commands.command(name="welcome_setup", description="[نظام عملاق] فتح لوحة التحكم المركزية الشاملة لإدارة الترحيب والمغادرة والرتب")
    @app_commands.describe(
        welcome_channel="روم الترحيب الرئيسي", 
        leave_channel="روم المغادرة الرئيسي",
        autorole="رتبة تلقائية تُعطى للعضو عند دخوله"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_setup(
        self, 
        interaction: discord.Interaction, 
        welcome_channel: Optional[discord.TextChannel] = None, 
        leave_channel: Optional[discord.TextChannel] = None,
        autorole: Optional[discord.Role] = None
    ):
        if welcome_channel:
            MEGA_WELCOME_CONFIG["welcome_channel_id"] = welcome_channel.id
        if leave_channel:
            MEGA_WELCOME_CONFIG["leave_channel_id"] = leave_channel.id
        if autorole:
            MEGA_WELCOME_CONFIG["autorole_id"] = autorole.id
            MEGA_WELCOME_CONFIG["autorole_enabled"] = True

        embed = discord.Embed(
            title="⚡ ╎ لـوحـة الـتـحـكـم الـمـركـزيـة الـكـبـرى (MEGA WELCOME ENGINE) 〣",
            description=(
                f"> إعدادات النظام الحالية في إمبراطورية ZIUO:\n\n"
                f"📥 **روم الترحيب:** {f'<#{MEGA_WELCOME_CONFIG[\"welcome_channel_id\"]}>' if MEGA_WELCOME_CONFIG['welcome_channel_id'] else '`غير محدد ❌`'}\n"
                f"📤 **روم المغادرة:** {f'<#{MEGA_WELCOME_CONFIG[\"leave_channel_id\"]}>' if MEGA_WELCOME_CONFIG['leave_channel_id'] else '`غير محدد ❌`'}\n"
                f"🛡️ **الرتبة التلقائية (Auto-Role):** {f'<@&{MEGA_WELCOME_CONFIG[\"autorole_id\"]}>' if MEGA_WELCOME_CONFIG['autorole_enabled'] and MEGA_WELCOME_CONFIG['autorole_id'] else '`معطلة ❌`'}\n"
                f"🖼️ **صورة البطاقة:** [معاينة الرابط]({MEGA_WELCOME_CONFIG['card_image_url']})\n\n"
                "🛠️ **أوامر الحرية والتعديل المتوفرة لك:**\n"
                "• `/welcome_message <النص>` لتغيير رسالة الترحيب.\n"
                "• `/leave_message <النص>` لتغيير رسالة المغادرة.\n"
                "• `/dm_welcome_message <النص>` لتغيير رسالة الخاص.\n"
                "• `/welcome_card <الرابط>` لتغيير خلفية البطاقة.\n"
                "• `/welcome_test` لتجربة رسالة الترحيب فورياً.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x111111,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Enterprise Architecture ✦ Mega Welcome System")
        await interaction.response.send_message(embed=embed, view=MegaWelcomeControlView(), ephemeral=True)

    # 2. أوامر التعديل الحر المطلق للنصوص والرسائل
    @app_commands.command(name="welcome_message", description="[تعديل حر] تخصيص نص رسالة الترحيب العامة بالكامل على ذوقك")
    @app_commands.describe(text="النص الجديد (استخدم المتغيرات: [user], [userName], [memberCount], [server], [inviterName], [invites])")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome_message(self, interaction: discord.Interaction, text: str):
        MEGA_WELCOME_CONFIG["welcome_message"] = text
        await interaction.response.send_message(f"✅ **تم تحديث رسالة الترحيب العامة بنجاح!**\n> المعاينة:\n{text}", ephemeral=True)

    @app_commands.command(name="leave_message", description="[تعديل حر] تخصيص نص رسالة المغادرة بالكامل على ذوقك")
    @app_commands.describe(text="النص الجديد (استخدم المتغيرات: [userName], [memberCount], [server])")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leave_message(self, interaction: discord.Interaction, text: str):
        MEGA_WELCOME_CONFIG["leave_message"] = text
        await interaction.response.send_message(f"✅ **تم تحديث رسالة المغادرة بنجاح!**\n> المعاينة:\n{text}", ephemeral=True)

    @app_commands.command(name="dm_welcome_message", description="[تعديل حر] تخصيص رسالة الترحيب الخاصة (DM) التي تُرسل لعخاص العضو")
    @app_commands.describe(text="النص الجديد للخاص")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_dm_message(self, interaction: discord.Interaction, text: str):
        MEGA_WELCOME_CONFIG["dm_message"] = text
        MEGA_WELCOME_CONFIG["dm_welcome_enabled"] = True
        await interaction.response.send_message(f"✅ **تم تحديث وتفعيل رسالة الخاص (DM) بنجاح!**\n> المعاينة:\n{text}", ephemeral=True)

    @app_commands.command(name="welcome_card", description="[تعديل حر] تغيير رابط صورة البطاقة الترحيبية المرفقة")
    @app_commands.describe(url="رابط الصورة المباشر")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome_card(self, interaction: discord.Interaction, url: str):
        MEGA_WELCOME_CONFIG["card_image_url"] = url
        await interaction.response.send_message(f"🖼️ **تم تغيير رابط خلفية البطاقة بنجاح!**\n> الرابط: {url}", ephemeral=True)

    # 3. أمر التجربة الفورية (Welcome Test Simulation)
    @app_commands.command(name="welcome_test", description="[أداة تطوير] محاكاة وتجربة رسالة الترحيب وبطاقة الصور الحالية عليك فوراً")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_test(self, interaction: discord.Interaction):
        member = interaction.user
        formatted_msg = (
            MEGA_WELCOME_CONFIG["welcome_message"]
            .replace("[user]", member.mention)
            .replace("[userName]", member.name)
            .replace("[memberCount]", str(member.guild.member_count))
            .replace("[server]", member.guild.name)
            .replace("[inviterName]", "مشرف النظام (محاكاة)")
            .replace("[invites]", "10")
            .replace("[accountCreated]", member.created_at.strftime("%Y-%m-%d"))
        )
        
        embed = discord.Embed(color=0x2B2D31)
        embed.description = formatted_msg
        if MEGA_WELCOME_CONFIG["card_enabled"]:
            embed.set_image(url=MEGA_WELCOME_CONFIG["card_image_url"])
        embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.set_footer(text=f"ID: {member.id} ✦ ZIUO Mega Welcome Simulation Test")
        
        await interaction.response.send_message("🧪 **معاينة تجريبية لنظام الترحيب:**", ephemeral=True)
        await interaction.channel.send(embed=embed)

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

    # 📥 حدث دخول العضو (مع تفعيل الرتبة التلقائية، الخاص، والبطاقة)
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # 1. إعطاء الرتبة التلقائية (Auto-Role)
        if MEGA_WELCOME_CONFIG["autorole_enabled"] and MEGA_WELCOME_CONFIG["autorole_id"]:
            try:
                role = member.guild.get_role(MEGA_WELCOME_CONFIG["autorole_id"])
                if role:
                    await member.add_roles(role, reason="ZIUO Auto-Role System")
            except Exception as e:
                print(f"[AUTOROLE ERROR] {e}")

        # 2. إرسال رسالة الخاص (DM Welcome)
        if MEGA_WELCOME_CONFIG["dm_welcome_enabled"]:
            try:
                dm_text = MEGA_WELCOME_CONFIG["dm_message"].replace("[userName]", member.name).replace("[server]", member.guild.name)
                await member.send(dm_text)
            except:
                pass # قد يكون العضو مغلق الرسائل الخاصة

        # 3. إرسال رسالة الترحيب في روم السيرفر
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
            print(f"[INVITE TRACKER ERROR] {e}")

        formatted_msg = self.format_text(MEGA_WELCOME_CONFIG["welcome_message"], member, inviter_name, invites_count)

        try:
            if MEGA_WELCOME_CONFIG["card_enabled"]:
                embed = discord.Embed(color=0x2B2D31)
                embed.description = formatted_msg
                embed.set_image(url=MEGA_WELCOME_CONFIG["card_image_url"])
                embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
                embed.set_footer(text=f"ID: {member.id} ✦ ZIUO Enterprise System")
                embed.timestamp = datetime.datetime.utcnow()
                await channel.send(embed=embed)
            else:
                await channel.send(formatted_msg)
        except Exception as e:
            print(f"[WELCOME ERROR] {e}")

    # 📤 حدث مغادرة العضو
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not MEGA_WELCOME_CONFIG["leave_enabled"]:
            return

        channel_id = MEGA_WELCOME_CONFIG["leave_channel_id"]
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        formatted_msg = (
            MEGA_WELCOME_CONFIG["leave_message"]
            .replace("[userName]", member.name)
            .replace("[memberCount]", str(member.guild.member_count))
            .replace("[server]", member.guild.name)
        )

        try:
            await channel.send(formatted_msg)
        except Exception as e:
            print(f"[LEAVE ERROR] {e}")

async def setup(bot):
    await bot.add_cog(MegaWelcomeSystemCog(bot))
