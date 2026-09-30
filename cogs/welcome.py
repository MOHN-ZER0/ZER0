import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, Literal

# ==============================================================================
# 🌟 إعدادات وقاعدة بيانات نظام الترحيب والمغادرة المحصن (Enterprise Safe Core)
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
# 🎛️ لوحة التحكم التفاعلية الكبرى بالزرار (Dashboard UI)
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

        self.btn_dm.label = f"ترحيب الخاص: {'[مفعل ✅]' if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else '[معطل ❌]'}"
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
                print(f"[CACHE LOAD ERROR for {guild.name}]: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        try:
            MEGA_SERVER_INVITES_CACHE[guild.id] = await guild.invites()
        except Exception as e:
            print(f"[GUILD JOIN INVITES ERROR]: {e}")

    @app_commands.command(
        name="welcome",
        description="[نظام إمبراطوري موحد] لوحة التحكم والتحكم الحر بنصوص وإعدادات الترحيب والمغادرة"
    )
    @app_commands.describe(
        action="الإجراء أو التعديل المطلوب تنفيذه على النظام",
        welcome_channel="تحديد روم الترحيب العام",
        leave_channel="تحديد روم المغادرة",
        autorole="تحديد الرتبة التلقائية عند الدخول",
        custom_text="النص الجديد (في حالة تعديل رسالة ترحيب، مغادرة، أو خاص)",
        image_url="رابط خلفية البطاقة الجديد"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="فتح لوحة التحكم المركزية والروابط (Dashboard)", value="setup"),
            app_commands.Choice(name="تعديل رسالة الترحيب العامة (Welcome Text)", value="set_welcome"),
            app_commands.Choice(name="تعديل رسالة المغادرة (Leave Text)", value="set_leave"),
            app_commands.Choice(name="تعديل رسالة الخاص DM (Direct Message)", value="set_dm"),
            app_commands.Choice(name="تغيير رابط صورة البطاقة (Card Image)", value="set_card"),
            app_commands.Choice(name="محاكاة وتجربة الترحيب فورياً (Test Simulation)", value="test")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_manager(
        self,
        interaction: discord.Interaction,
        action: Literal["setup", "set_welcome", "set_leave", "set_dm", "set_card", "test"],
        welcome_channel: Optional[discord.TextChannel] = None,
        leave_channel: Optional[discord.TextChannel] = None,
        autorole: Optional[discord.Role] = None,
        custom_text: Optional[str] = None,
        image_url: Optional[str] = None
    ):
        if action == "setup":
            if welcome_channel:
                MEGA_WELCOME_CONFIG["welcome_channel_id"] = welcome_channel.id
            if leave_channel:
                MEGA_WELCOME_CONFIG["leave_channel_id"] = leave_channel.id
            if autorole:
                MEGA_WELCOME_CONFIG["autorole_id"] = autorole.id
                MEGA_WELCOME_CONFIG["autorole_enabled"] = True

            embed = discord.Embed(
                title="⚡ ╎ لـوحـة تـحـكـم الـتـرحـيـب والـمـغـادرة الإمبراطورية 〣",
                description=(
                    f"> إدارة شاملة ومتقدمة لإمبراطورية ZIUO:\n\n"
                    f"📥 **روم الترحيب:** {f'<#{MEGA_WELCOME_CONFIG[\"welcome_channel_id\"]}>' if MEGA_WELCOME_CONFIG['welcome_channel_id'] else '`غير محدد ❌`'}\n"
                    f"📤 **روم المغادرة:** {f'<#{MEGA_WELCOME_CONFIG[\"leave_channel_id\"]}>' if MEGA_WELCOME_CONFIG['leave_channel_id'] else '`غير محدد ❌`'}\n"
                    f"🛡️ **الرتبة التلقائية:** {f'<@&{MEGA_WELCOME_CONFIG[\"autorole_id\"]}>' if MEGA_WELCOME_CONFIG['autorole_enabled'] and MEGA_WELCOME_CONFIG['autorole_id'] else '`معطلة ❌`'}\n"
                    f"🖼️ **صورة البطاقة:** [معاينة الرابط]({MEGA_WELCOME_CONFIG['card_image_url']})\n\n"
                    "💡 **طريقة التعديل الحر:** استخدم الأمر `/welcome` واختار نوع التعديل (`set_welcome` مثلاً) واكتب النص المطلوب في خانة `custom_text`!\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0x2B2D31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Z I UO Enterprise Architecture ✦ Welcome Engine")
            await interaction.response.send_message(embed=embed, view=MegaWelcomeControlView(), ephemeral=True)
            return

        if action == "set_welcome":
            if not custom_text:
                await interaction.response.send_message("❌ **يجب كتابة النص الجديد في خانة `custom_text`!**", ephemeral=True)
                return
            MEGA_WELCOME_CONFIG["welcome_message"] = custom_text
            embed = discord.Embed(
                title="✅ تـم تـحـديـث رسـالـة الـتـرحـيـب بـنـجـاح",
                description=f"> **المعاينة الجديدة:**\n{custom_text}",
                color=0x2ECC71
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if action == "set_leave":
            if not custom_text:
                await interaction.response.send_message("❌ **يجب كتابة النص الجديد في خانة `custom_text`!**", ephemeral=True)
                return
            MEGA_WELCOME_CONFIG["leave_message"] = custom_text
            await interaction.response.send_message(f"✅ **تم تحديث رسالة المغادرة بنجاح!**\n> المعاينة:\n{custom_text}", ephemeral=True)
            return

        if action == "set_dm":
            if not custom_text:
                await interaction.response.send_message("❌ **يجب كتابة النص الجديد في خانة `custom_text`!**", ephemeral=True)
                return
            MEGA_WELCOME_CONFIG["dm_message"] = custom_text
            MEGA_WELCOME_CONFIG["dm_welcome_enabled"] = True
            await interaction.response.send_message(f"✅ **تم تحديث وتفعيل رسالة الخاص (DM) بنجاح!**\n> المعاينة:\n{custom_text}", ephemeral=True)
            return

        if action == "set_card":
            if not image_url:
                await interaction.response.send_message("❌ **يجب وضع رابط الصورة المباشر في خانة `image_url`!**", ephemeral=True)
                return
            MEGA_WELCOME_CONFIG["card_image_url"] = image_url
            await interaction.response.send_message(f"🖼️ **تم تغيير خلفية البطاقة الترحيبية بنجاح!**\n> الرابط: {image_url}", ephemeral=True)
            return

        if action == "test":
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
            embed.set_footer(text=f"ID: {member.id} ✦ ZIUO Simulation Test")
            
            await interaction.response.send_message("🧪 **معاينة تجريبية لنظام الترحيب في هذا الروم:**", ephemeral=True)
            await interaction.channel.send(embed=embed)
            return

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

    # 📥 حدث دخول العضو (محصن بالكامل ضد الانهيار)
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # 1. الرتبة التلقائية
        if MEGA_WELCOME_CONFIG["autorole_enabled"] and MEGA_WELCOME_CONFIG["autorole_id"]:
            try:
                role = member.guild.get_role(MEGA_WELCOME_CONFIG["autorole_id"])
                if role:
                    await member.add_roles(role, reason="ZIUO Auto-Role System")
            except Exception as e:
                print(f"[AUTOROLE ERROR]: {e}")

        # 2. رسالة الخاص
        if MEGA_WELCOME_CONFIG["dm_welcome_enabled"]:
            try:
                dm_text = MEGA_WELCOME_CONFIG["dm_message"].replace("[userName]", member.name).replace("[server]", member.guild.name)
                await member.send(dm_text)
            except Exception:
                pass

        # 3. التحقق من تفعيل الترحيب وروم الترحيب
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
        
        # محاولة تتبع الدعوات بشكل آمن تماماً (لن يوقف النظام لو فشل)
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
            print(f"[INVITE TRACKER SAFE BYPASS]: {e}")

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
            print(f"[WELCOME SEND ERROR]: {e}")

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
            print(f"[LEAVE SEND ERROR]: {e}")

async def setup(bot):
    await bot.add_cog(MegaWelcomeSystemCog(bot))
