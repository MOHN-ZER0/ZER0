import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional

# ==============================================================================
# 🌟 إعدادات وقاعدة بيانات نظام الترحيب والمغادرة (Enterprise Core)
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
    "leave_image_url": "https://probot.media/leave_default.png",
    "dm_image_url": "https://probot.media/dm_default.png",
    
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
# 📝 القوائم التفاعلية (Modals) للتحكم الشامل
# ==============================================================================

# 1. قائمة تفعيل أو تعطيل الأنظمة
class SystemsToggleModal(discord.ui.Modal, title="⚙️ إعدادات تشغيل وتوقف الأنظمة"):
    w_status = discord.ui.TextInput(
        label="دخول العضو (اكتب: مفعل أو معطل)",
        style=discord.TextStyle.short,
        default="مفعل" if MEGA_WELCOME_CONFIG["welcome_enabled"] else "معطل",
        max_length=10
    )
    l_status = discord.ui.TextInput(
        label="خروج العضو (اكتب: مفعل أو معطل)",
        style=discord.TextStyle.short,
        default="مفعل" if MEGA_WELCOME_CONFIG["leave_enabled"] else "معطل",
        max_length=10
    )
    card_status = discord.ui.TextInput(
        label="الصورة الترحيبية (اكتب: مفعل أو معطل)",
        style=discord.TextStyle.short,
        default="مفعل" if MEGA_WELCOME_CONFIG["card_enabled"] else "معطل",
        max_length=10
    )
    dm_status = discord.ui.TextInput(
        label="الرسالة الخاصة DM (اكتب: مفعل أو معطل)",
        style=discord.TextStyle.short,
        default="مفعل" if MEGA_WELCOME_CONFIG["dm_welcome_enabled"] else "معطل",
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["welcome_enabled"] = self.w_status.value.strip().lower() in ["مفعل", "true", "1", "yes", "on"]
        MEGA_WELCOME_CONFIG["leave_enabled"] = self.l_status.value.strip().lower() in ["مفعل", "true", "1", "yes", "on"]
        MEGA_WELCOME_CONFIG["card_enabled"] = self.card_status.value.strip().lower() in ["مفعل", "true", "1", "yes", "on"]
        MEGA_WELCOME_CONFIG["dm_welcome_enabled"] = self.dm_status.value.strip().lower() in ["مفعل", "true", "1", "yes", "on"]
        
        await interaction.response.send_message("✅ **تم تحديث حالات الأنظمة بنجاح!**", ephemeral=True)


# 2. قائمة تحديد رومات الترحيب والمغادرة
class ChannelsEditModal(discord.ui.Modal, title="📌 تحديد رومات الترحيب والمغادرة"):
    w_channel = discord.ui.TextInput(
        label="آيدي أو اسم روم الترحيب",
        style=discord.TextStyle.short,
        placeholder="اكتب آيدي الروم أو اسمها هنا...",
        default=str(MEGA_WELCOME_CONFIG["welcome_channel_id"]) if MEGA_WELCOME_CONFIG["welcome_channel_id"] else "",
        required=False,
        max_length=50
    )
    l_channel = discord.ui.TextInput(
        label="آيدي أو اسم روم المغادرة",
        style=discord.TextStyle.short,
        placeholder="اكتب آيدي الروم أو اسمها هنا...",
        default=str(MEGA_WELCOME_CONFIG["leave_channel_id"]) if MEGA_WELCOME_CONFIG["leave_channel_id"] else "",
        required=False,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        
        # معالجة روم الترحيب
        w_val = self.w_channel.value.strip()
        if w_val:
            if w_val.isdigit():
                ch = guild.get_channel(int(w_val))
            else:
                ch = discord.utils.get(guild.text_channels, name=w_val)
            if ch:
                MEGA_WELCOME_CONFIG["welcome_channel_id"] = ch.id
        else:
            MEGA_WELCOME_CONFIG["welcome_channel_id"] = None

        # معالجة روم المغادرة
        l_val = self.l_channel.value.strip()
        if l_val:
            if l_val.isdigit():
                ch_l = guild.get_channel(int(l_val))
            else:
                ch_l = discord.utils.get(guild.text_channels, name=l_val)
            if ch_l:
                MEGA_WELCOME_CONFIG["leave_channel_id"] = ch_l.id
        else:
            MEGA_WELCOME_CONFIG["leave_channel_id"] = None

        await interaction.response.send_message("✅ **تم تحديث رومات الترحيب والمغادرة بنجاح!**", ephemeral=True)


# 3. قائمة تعديل الرسائل مع الشرح الكامل في الأسفل
class MessagesEditModal(discord.ui.Modal, title="💬 تعديل الرسائل والاختصارات"):
    w_msg = discord.ui.TextInput(
        label="رسالة الترحيب",
        style=discord.TextStyle.paragraph,
        default=MEGA_WELCOME_CONFIG["welcome_message"],
        max_length=1000
    )
    l_msg = discord.ui.TextInput(
        label="رسالة المغادرة",
        style=discord.TextStyle.paragraph,
        default=MEGA_WELCOME_CONFIG["leave_message"],
        max_length=1000
    )
    dm_msg = discord.ui.TextInput(
        label="رسالة الترحيب الخاصة (DM)",
        style=discord.TextStyle.paragraph,
        default=MEGA_WELCOME_CONFIG["dm_message"],
        max_length=1000
    )
    variables_guide = discord.ui.TextInput(
        label="📌 شرح الاختصارات (للقراءة فقط - لا تعدلها)",
        style=discord.TextStyle.paragraph,
        default=(
            "[user] / [userName] = منشن أو اسم العضو\n"
            "[server] = اسم السيرفر | [memberCount] = عدد الأعضاء\n"
            "[inviterName] = اسم الداعي | [invites] = عدد الدعوات\n"
            "[accountCreated] = تاريخ إنشاء الحساب"
        ),
        max_length=300,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["welcome_message"] = self.w_msg.value
        MEGA_WELCOME_CONFIG["leave_message"] = self.l_msg.value
        MEGA_WELCOME_CONFIG["dm_message"] = self.dm_msg.value
        await interaction.response.send_message("✅ **تم حفظ وتعديل رسائل الإمبراطورية بنجاح!**", ephemeral=True)


# 4. قائمة تعديل روابط الصور
class ImagesEditModal(discord.ui.Modal, title="🖼️ تعديل روابط صور الترحيب والمغادرة"):
    card_img = discord.ui.TextInput(
        label="رابط صورة الترحيب",
        style=discord.TextStyle.short,
        default=MEGA_WELCOME_CONFIG["card_image_url"],
        max_length=300
    )
    leave_img = discord.ui.TextInput(
        label="رابط صورة المغادرة",
        style=discord.TextStyle.short,
        default=MEGA_WELCOME_CONFIG["leave_image_url"],
        max_length=300
    )
    dm_img = discord.ui.TextInput(
        label="رابط صورة رسالة الخاص",
        style=discord.TextStyle.short,
        default=MEGA_WELCOME_CONFIG["dm_image_url"],
        max_length=300
    )

    async def on_submit(self, interaction: discord.Interaction):
        MEGA_WELCOME_CONFIG["card_image_url"] = self.card_img.value
        MEGA_WELCOME_CONFIG["leave_image_url"] = self.leave_img.value
        MEGA_WELCOME_CONFIG["dm_image_url"] = self.dm_img.value
        await interaction.response.send_message("✅ **تم تحديث روابط الصور بنجاح!**", ephemeral=True)


# ==============================================================================
# 🎛️ لوحة التحكم الرئيسية بالأزرار المنسقة
# ==============================================================================
class MegaWelcomeControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="⚙️ تشغيل/إيقاف الأنظمة", style=discord.ButtonStyle.blurple, row=0)
    async def btn_toggle_systems(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(SystemsToggleModal())

    @discord.ui.button(label="📌 تحديد رومات الترحيب والمغادرة", style=discord.ButtonStyle.green, row=0)
    async def btn_edit_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ChannelsEditModal())

    @discord.ui.button(label="💬 تعديل الرسائل والاختصارات", style=discord.ButtonStyle.blurple, row=1)
    async def btn_edit_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(MessagesEditModal())

    @discord.ui.button(label="🖼️ روابط الصور الترحيبية", style=discord.ButtonStyle.grey, row=1)
    async def btn_edit_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للمدراء فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ImagesEditModal())


# ==============================================================================
# 🌟 Cog النظام الرئيسي للترحيب والمغادرة
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
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_manager(self, interaction: discord.Interaction):
        wch = MEGA_WELCOME_CONFIG["welcome_channel_id"]
        lch = MEGA_WELCOME_CONFIG["leave_channel_id"]

        embed = discord.Embed(
            title="⚡ لوحة تحكم إمبراطورية ZIUO - نظام الترحيب والفعاليات 〣",
            description=(
                "مرحباً بك في لوحة الإدارة المركزية المتطورة.\n"
                "يمكنك التحكم بكافة الأجزاء بسلاسة عبر الأزرار أدناه:\n\n"
                f"📥 **روم الترحيب:** {f'<#{wch}>' if wch else '`غير محدد ❌`'}\n"
                f"📤 **روم المغادرة:** {f'<#{lch}>' if lch else '`غير محدد ❌`'}\n"
                f"🟢 **حالة الترحيب:** `{'مفعل ✅' if MEGA_WELCOME_CONFIG['welcome_enabled'] else 'معطل ❌'}`\n"
                f"🔴 **حالة المغادرة:** `{'مفعل ✅' if MEGA_WELCOME_CONFIG['leave_enabled'] else 'معطل ❌'}`\n"
                f"🖼️ **صورة البطاقة:** `{'مفعل ✅' if MEGA_WELCOME_CONFIG['card_enabled'] else 'معطل ❌'}`\n"
                f"✉️ **ترحيب الخاص:** `{'مفعل ✅' if MEGA_WELCOME_CONFIG['dm_welcome_enabled'] else 'معطل ❌'}`\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 **ملاحظة:** اضغط على الأزرار أدناه لتعديل الرومات، حالات الأنظمة، الرسائل، أو الصور فوراً!"
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

        inviter_name = "رابط عام"
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
        except Exception:
            pass

        formatted_msg = self.format_text(MEGA_WELCOME_CONFIG["welcome_message"], member, inviter_name, invites_count)

        try:
            embed = discord.Embed(color=0x2B2D31, description=formatted_msg)
            if MEGA_WELCOME_CONFIG["card_enabled"]:
                embed.set_image(url=MEGA_WELCOME_CONFIG["card_image_url"])
            embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
            embed.set_footer(text=f"ID: {member.id} ✦ ZIUO Enterprise")
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[WELCOME ERROR]: {e}")

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
            embed = discord.Embed(color=0xE74C3C, description=formatted_msg)
            if MEGA_WELCOME_CONFIG["card_enabled"] and MEGA_WELCOME_CONFIG["leave_image_url"]:
                embed.set_image(url=MEGA_WELCOME_CONFIG["leave_image_url"])
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[LEAVE ERROR]: {e}")

async def setup(bot):
    await bot.add_cog(MegaWelcomeSystemCog(bot))
