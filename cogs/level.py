import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random

# ==============================================================================
# 🌟 نظام قاعدة البيانات الشاملة والموسعة
# ==============================================================================
SERVER_ULTRA_DB = {
    "users": {},              # تخزين بيانات الأعضاء (xp, level, messages, voice_minutes, prestige)
    "settings": {},           # إعدادات السيرفر الشاملة
    "custom_cards": {},       # تخصيص بطاقات الرانك لكل عضو
    "blacklists": {},         # القائمة السوداء للأعضاء أو القنوات
    "temporary_boosts": {}    # مضاعفات النقاط المؤقتة
}

def get_guild_settings(guild_id: int):
    if guild_id not in SERVER_ULTRA_DB["settings"]:
        SERVER_ULTRA_DB["settings"][guild_id] = {
            "status": True,
            "multiplier": 1,
            "ignored_channels": [],
            "target_role_id": None,
            "admin_role_id": None,
            "reset_type": "none",
            "announcement_channel": None,
            "custom_level_message": "أهلاً بك يا {user}، لقد صعدت بنجاح إلى المستوى {level}!",
            "role_rewards": {}
        }
    return SERVER_ULTRA_DB["settings"][guild_id]

# ==============================================================================
# 🎨 واجهات التحكم الإدارية ولوحة الإعدادات التفاعلية
# ==============================================================================

class LevelMessageModal(discord.ui.Modal, title="تعديل رسالة الترقية"):
    message_input = discord.ui.TextInput(
        label="نص الرسالة الجديدة",
        placeholder="مثال: كفو {user} صرت لفل {level}!",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        settings = get_guild_settings(interaction.guild.id)
        settings["custom_level_message"] = self.message_input.value
        await interaction.response.send_message(f"✅ تم تحديث رسالة الترقية بنجاح إلى:\n> `{self.message_input.value}`", ephemeral=True)


class LevelImageModal(discord.ui.Modal, title="تعديل صورة الترقية"):
    image_input = discord.ui.TextInput(
        label="رابط الصورة (Image URL)",
        placeholder="https://example.com/image.png (للازالة اكتب none)",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        settings = get_guild_settings(interaction.guild.id)
        val = self.image_input.value.strip()
        if val.lower() == "none":
            settings["level_image"] = None
            await interaction.response.send_message("✅ تم إزالة صورة الترقية بنجاح.", ephemeral=True)
        else:
            settings["level_image"] = val
            await interaction.response.send_message(f"✅ تم تحديث صورة الترقية بنجاح:\n> `{val}`", ephemeral=True)


class LevelRewardModal(discord.ui.Modal, title="إضافه رتبة لمستوى معين"):
    level_input = discord.ui.TextInput(
        label="رقم اللفل المطلوب",
        placeholder="مثال: 5 أو 10",
        required=True,
        max_length=5
    )
    role_input = discord.ui.TextInput(
        label="أيدي الرتبة (Role ID)",
        placeholder="قم بنسخ أيدي الرتبة هنا",
        required=True,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lvl = int(self.level_input.value.strip())
            role_id = int(self.role_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ تأكد من كتابة أرقام صحيحة للفلفل وأيدي الرتبة!", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ لم يتم العثور على الرتبة بهذا الأيدي في السيرفر!", ephemeral=True)
            return

        settings = get_guild_settings(interaction.guild.id)
        settings["role_rewards"][str(lvl)] = role.id
        await interaction.response.send_message(f"✅ تم ربط اللفل **{lvl}** بالرتبة {role.mention} بنجاح!", ephemeral=True)


class ResetConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        placeholder="اختر نظام التصفير والريسيت الدوري...",
        options=[
            discord.SelectOption(label="إيقاف نظام الريسيت", value="none", description="تعطيل التصفير التلقائي", emoji="⏹"),
            discord.SelectOption(label="يومي (مرتين في اليوم)", value="daily", description="إرسال تقرير وتنفيذ دورة كل 12 ساعة", emoji="☀️"),
            discord.SelectOption(label="أسبوعي (مرتين في اليوم طوال الأسبوع)", value="weekly", description="تحديث ومراجعة دورية أسبوعية", emoji="📅"),
            discord.SelectOption(label="شهري (مرتين في اليوم طوال الشهر)", value="monthly", description="دورة تصفير وإحصائيات شهرية", emoji="🗓️")
        ]
    )
    async def select_reset_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        settings = get_guild_settings(interaction.guild.id)
        settings["reset_type"] = select.values[0]
        await interaction.response.send_message(f"✅ تم تحديث نظام الريسيت الدوري إلى: **{select.values[0].upper()}** بنجاح!", ephemeral=True)


class LevelAdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل النظام", style=discord.ButtonStyle.success, emoji="🟢", custom_id="enable_levels_sys")
    async def enable_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_guild_settings(interaction.guild.id)
        settings["status"] = True
        await interaction.response.send_message("🟢 تم **تشغيل** نظام المستويات بنجاح في السيرفر!", ephemeral=True)

    @discord.ui.button(label="إيقاف النظام", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="disable_levels_sys")
    async def disable_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_guild_settings(interaction.guild.id)
        settings["status"] = False
        await interaction.response.send_message("🔴 تم **إيقاف** نظام المستويات مؤقتاً في السيرفر!", ephemeral=True)

    @discord.ui.button(label="تحديد روم الترقية", style=discord.ButtonStyle.primary, emoji="💬", custom_id="set_lvl_chan_btn")
    async def set_chan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💬 يرجى استخدام الأمر `/level_reset_config` لتحديد روم إعلانات الترقية.", ephemeral=True)

    @discord.ui.button(label="تعديل رسالة الترقية", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="edit_lvl_msg_btn")
    async def edit_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelMessageModal())

    @discord.ui.button(label="تعديل صورة الترقية", style=discord.ButtonStyle.secondary, emoji="🖼️", custom_id="edit_lvl_img_btn")
    async def edit_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelImageModal())

    @discord.ui.button(label="إضافة مكافأة رتبة", style=discord.ButtonStyle.success, emoji="🎁", custom_id="add_lvl_reward_btn")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelRewardModal())

    @discord.ui.button(label="إعدادات الريسيت الدوري", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="reset_config_menu_btn")
    async def reset_config_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚙️️ اختر نوع الريسيت الدوري من القائمة أدناه:", view=ResetConfigView(), ephemeral=True)


class UltimateRankModal(discord.ui.Modal, title="تخصيص بطاقة المستوى الشخصية"):
    bg_url_input = discord.ui.TextInput(
        label="رابط صورة الخلفية المخصصة للبطاقة",
        placeholder="https://imgur.com/...",
        required=False,
        max_length=400
    )
    color_input = discord.ui.TextInput(
        label="كود اللون الأساسي للبطاقة (Hex Color)",
        placeholder="#5865F2",
        default="#5865F2",
        required=True,
        max_length=7
    )
    status_input = discord.ui.TextInput(
        label="الحالة الشخصية أو الشعار المكتوب",
        placeholder="اكتب شعارك المميز هنا...",
        required=False,
        max_length=120
    )

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid not in SERVER_ULTRA_DB["custom_cards"]:
            SERVER_ULTRA_DB["custom_cards"][uid] = {}
        
        SERVER_ULTRA_DB["custom_cards"][uid]["bg_url"] = self.bg_url_input.value
        SERVER_ULTRA_DB["custom_cards"][uid]["color"] = self.color_input.value
        SERVER_ULTRA_DB["custom_cards"][uid]["status"] = self.status_input.value
        
        await interaction.response.send_message("✅ تم حفظ وتحديث تخصيص بطاقة المستوى الشخصية الخاصة بك بنجاح تام!", ephemeral=True)


class UltimateControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تخصيص البطاقة بالكامل", style=discord.ButtonStyle.primary, emoji="🎨", custom_id="ultra_customize_card_btn_v4")
    async def customize_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UltimateRankModal())

    @discord.ui.button(label="استعراض جدول الرتب والمكافآت", style=discord.ButtonStyle.secondary, emoji="🏆", custom_id="ultra_rewards_btn_v4")
    async def rewards_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_guild_settings(interaction.guild.id)
        rewards = settings.get("role_rewards", {})
        
        rewards_text = ""
        if rewards:
            for lvl, r_id in sorted(rewards.items(), key=lambda x: int(x[0])):
                r_obj = interaction.guild.get_role(r_id)
                r_mention = r_obj.mention if r_obj else f"رتبة محذوفة (`{r_id}`)"
                rewards_text += f"• **المستوى {lvl}:** {r_mention}\n"
        else:
            rewards_text = "لا توجد مكافآت رتب مضافة حالياً."

        embed = discord.Embed(
            title="دليل رتب ومكافآت التفاعل التلقائية",
            description=f"مرحباً بك في جدول الرتب الممنوحة عند الارتقاء بالمستويات:\n\n{rewards_text}",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Global Management System ✦ Reward Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# ⚙ محرك الـ Cog الرئيسي والممتد للأنظمة
# ==============================================================================
class UltimateLevelingSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduled_reset_task.start()
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.scheduled_reset_task.cancel()
        self.voice_xp_loop.cancel()

    @tasks.loop(hours=12)
    async def scheduled_reset_task(self):
        now = datetime.datetime.utcnow()
        for guild_id, settings in SERVER_ULTRA_DB.get("settings", {}).items():
            if not settings.get("status", True):
                continue
            reset_type = settings.get("reset_type")
            if not reset_type or reset_type == "none":
                continue
            
            target_channel_id = settings.get("announcement_channel")
            if not target_channel_id:
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            
            channel = guild.get_channel(target_channel_id)
            if not channel:
                continue

            try:
                if reset_type == "daily":
                    await channel.send("🔄 **[تقرير نظام المستويات اليومي]** ╎ تم تنفيذ دورة التحقق والتقرير اليومية (مرتين يومياً) بنجاح!")
                elif reset_type == "weekly":
                    if now.weekday() == 0:
                        await channel.send("📊 **[تقرير نظام المستويات الأسبوعي]** ╎ فحص ومراجعة تصنيفات المتصدرين الدورية لهذا الأسبوع!")
                elif reset_type == "monthly":
                    if now.day == 1:
                        await channel.send("📊 **[تقرير نظام المستويات الشهري]** ╎ إطلاق الدورة الشهرية الجديدة لنظام التفاعل!")
            except:
                pass

    @scheduled_reset_task.before_loop
    async def before_scheduled_reset(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def voice_xp_loop(self):
        for guild in self.bot.guilds:
            guild_id = guild.id
            settings = get_guild_settings(guild_id)
            if not settings.get("status", True):
                continue
            
            multiplier = settings.get("multiplier", 1)

            for vc in guild.voice_channels:
                if vc.id in settings.get("ignored_channels", []):
                    continue

                for member in vc.members:
                    if member.bot:
                        continue
                    
                    if guild_id not in SERVER_ULTRA_DB["users"]:
                        SERVER_ULTRA_DB["users"][guild_id] = {}
                    if member.id not in SERVER_ULTRA_DB["users"][guild_id]:
                        SERVER_ULTRA_DB["users"][guild_id][member.id] = {
                            "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
                        }

                    user_data = SERVER_ULTRA_DB["users"][guild_id][member.id]
                    
                    if member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf:
                        continue

                    user_data["voice_minutes"] += 5
                    voice_earned = random.randint(15, 30) * multiplier
                    user_data["xp"] += voice_earned

    @voice_xp_loop.before_loop
    async def before_voice_xp(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        settings = get_guild_settings(guild_id)

        if not settings.get("status", True):
            return

        if message.channel.id in settings.get("ignored_channels", []):
            return

        if guild_id not in SERVER_ULTRA_DB["users"]:
            SERVER_ULTRA_DB["users"][guild_id] = {}

        if user_id not in SERVER_ULTRA_DB["users"][guild_id]:
            SERVER_ULTRA_DB["users"][guild_id][user_id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
            }

        user_data = SERVER_ULTRA_DB["users"][guild_id][user_id]
        
        active_mult = settings.get("multiplier", 1)
        base_gain = random.randint(15, 25)
        earned_xp = base_gain * active_mult

        user_data["xp"] += earned_xp
        user_data["messages"] += 1

        req_xp = (user_data["level"] + 1) * 350 + (user_data["level"] * 120)

        if user_data["xp"] >= req_xp:
            user_data["level"] += 1
            user_data["xp"] = 0

            role_rewards = settings.get("role_rewards", {})
            reward_role_id = role_rewards.get(str(user_data["level"]))
            if reward_role_id:
                r_obj = message.guild.get_role(int(reward_role_id))
                if r_obj:
                    try:
                        await message.author.add_roles(r_obj, reason=f"Level Reward: Reached level {user_data['level']}")
                    except:
                        pass

            try:
                raw_msg_template = settings.get("custom_level_message", "أهلاً بك يا {user}، لقد صعدت بنجاح إلى المستوى {level}!")
                formatted_msg = raw_msg_template.replace("{user}", message.author.mention).replace("{level}", str(user_data["level"])).replace("{messages}", str(user_data["messages"]))

                up_embed = discord.Embed(
                    title="ترقية جديدة وصعود في مستويات السيرفر!",
                    description=(
                        f"{formatted_msg}\n\n"
                        f"• **المستوى المحقق:** `{user_data['level']}`\n"
                        f"• **إجمالي الرسائل:** `{user_data['messages']}` رسالة\n"
                    ),
                    color=0x00FF99,
                    timestamp=datetime.datetime.utcnow()
                )
                
                custom_img = settings.get("level_image")
                if custom_img:
                    up_embed.set_image(url=custom_img)

                up_embed.set_footer(text="Z I UO Enterprise Advanced Leveling Engine")
                
                target_chan_id = settings.get("announcement_channel")
                target_chan = message.guild.get_channel(target_chan_id) if target_chan_id else message.channel
                await target_chan.send(content=f"🎯 ممتاز يا {message.author.mention}!", embed=up_embed)
            except:
                pass

    # ==========================================================================
    # 🚀 الأوامر (Slash Commands)
    # ==========================================================================

    @app_commands.command(name="levels_panel", description="[لوحة التحكم] عرض لوحة إعدادات نظام اللفلات الكاملة مع الأزرار التفاعلية")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction):
        settings = get_guild_settings(interaction.guild.id)
        
        status_text = "🟢 مفعّل" if settings.get("status", True) else "🔴 مقفل"
        chan_obj = interaction.guild.get_channel(settings.get("announcement_channel"))
        chan_str = chan_obj.mention if chan_obj else "غير محدد ❌"
        
        rewards_count = len(settings.get("role_rewards", {}))
        rewards_str = f"{rewards_count} رتب مكافأة مضافة" if rewards_count > 0 else "لا توجد مكافآت مضافة"
        
        custom_img = settings.get("level_image")
        img_str = "مفعلة ✅" if custom_img else "غير مفعلة ❌"
        
        msg_template = settings.get("custom_level_message", "افتراضي")

        embed = discord.Embed(
            title="🏆 إعداد نظام اللفلات",
            description=(
                "من هنا يمكنك التحكم بالكامل بنظام اللفلات، الرومات، الرتب والمكافآت.\n\n"
                f"• **حالة النظام:**\n{status_text}\n"
                f"• **روم الترقية:**\n{chan_str}\n"
                f"• **صورة الترقية:**\n{img_str}\n"
                f"• **مكافآت الرتب:**\n{rewards_str}\n"
                f"• **رسالة الترقية:**\n{msg_template}\n\n"
                "إعدادات مستقلة لهذا السيرفر ✦ ZIUO - MC"
            ),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        
        await interaction.response.send_message(embed=embed, view=LevelAdminPanelView(), ephemeral=True)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية والكاملة لأي عضو في السيرفر")
    @app_commands.describe(member="العضو المراد الكشف عن رانكه")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        guild_id = interaction.guild.id

        guild_users = SERVER_ULTRA_DB["users"].get(guild_id, {})
        user_data = guild_users.get(target.id, {"xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0})
        
        custom_conf = SERVER_ULTRA_DB["custom_cards"].get(target.id, {})
        color_hex = custom_conf.get("color", "#5865F2")
        try:
            color_int = int(color_hex.replace("#", ""), 16)
        except:
            color_int = 0x5865F2

        req_xp = (user_data["level"] + 1) * 350 + (user_data["level"] * 120)

        embed = discord.Embed(
            title=f"📊 بطاقة المستوى والخبرة - {target.display_name}",
            description=(
                f"إليك كافة الإحصائيات الشاملة لسجل تفاعلك ونشاطك داخل السيرفر:\n\n"
                f"• **المستوى الحالي (Level):** `{user_data['level']}`\n"
                f"• **نقاط الخبرة (XP):** `{user_data['xp']} / {req_xp}` 🌟\n"
                f"• **عدد الرسائل النصية:** `{user_data['messages']}` رسالة 📝\n"
                f"• **دقائق التواجد الصوتي:** `{user_data['voice_minutes']}` دقيقة 🔊\n"
                f"• **الحالة الشخصية:** `{custom_conf.get('status', 'لا توجد حالة مضافة')}`"
            ),
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )

        if custom_conf.get("bg_url"):
            embed.set_image(url=custom_conf["bg_url"])

        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Z I UO Ultimate Rank System ✦ 2026 Edition")

        await interaction.response.send_message(embed=embed, view=UltimateControlView(), ephemeral=False)

    @app_commands.command(name="top", description="عرض لوحة الشرف الكبرى لأعلى 10 أعضاء متصدرين في السيرفر مع ترتيبك الشخصي")
    async def top(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        guild_users = SERVER_ULTRA_DB["users"].get(guild_id, {})

        if not guild_users:
            await interaction.response.send_message("❌ لا توجد أي بيانات مسجلة في نظام المستويات حتى هذه اللحظة!", ephemeral=True)
            return

        # ترتيب جميع الأعضاء تنازلياً حسب المستوى ثم الـ XP
        sorted_users = sorted(guild_users.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)

        # تجهيز أفضل 10 أعضاء
        top_10 = sorted_users[:10]
        ranking_lines = []

        for index, (uid, data) in enumerate(top_10, start=1):
            member_obj = interaction.guild.get_member(uid)
            display_name = member_obj.mention if member_obj else f"عضو مغادر (`{uid}`)"
            
            medal_icon = "👑" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"`#{index}`"
            ranking_lines.append(
                f"{medal_icon} ╎ {display_name}\n"
                f" ┗ المستوى: **{data['level']}** | XP: **{data['xp']}** | الرسائل: **{data['messages']}**\n"
            )

        embed = discord.Embed(
            title="🏆 لوحة شرف المتصدرين الكبرى - Z I UO",
            description=(
                "قائمة بأبرز 10 أعضاء الأكثر نشاطاً وتفاعلاً على مستوى السيرفر:\n\n" +
                "\n".join(ranking_lines)
            ),
            color=0xFFD700,
            timestamp=datetime.datetime.utcnow()
        )

        # البحث عن ترتيب المستخدم الحالي إذا لم يكن ضمن الـ Top 10
        user_id = interaction.user.id
        user_rank = None
        user_data = None

        for idx, (uid, data) in enumerate(sorted_users, start=1):
            if uid == user_id:
                user_rank = idx
                user_data = data
                break

        if user_rank and user_rank > 10:
            if not user_data:
                user_data = guild_users.get(user_id, {"xp": 0, "level": 0, "messages": 0})
            
            # جلب مكافأة الرتبة الحالية لو وجدت
            settings = get_guild_settings(guild_id)
            role_rewards = settings.get("role_rewards", {})
            reward_role_id = role_rewards.get(str(user_data["level"]))
            role_str = ""
            if reward_role_id:
                r_obj = interaction.guild.get_role(int(reward_role_id))
                if r_obj:
                    role_str = f" | المكافأة: {r_obj.mention}"

            embed.add_field(
                name="📌 ترتيبك الشخصي في السيرفر",
                value=(
                    f"• **المركز:** `#{user_rank}`\n"
                    f"• **العضو:** {interaction.user.mention}\n"
                    f"• **المستوى:** `{user_data['level']}` | **XP:** `{user_data['xp']}`{role_str}"
                ),
                inline=False
            )
        elif user_rank and user_rank <= 10:
            embed.set_footer(text=f"أنت ضمن قائمة العشرة الأوائل! ترتيبك الحالي هو #{user_rank} 🌟")
        else:
            embed.add_field(
                name="📌 ترتيبك الشخصي في السيرفر",
                value="ليس لديك تفاعل مسجل حتى الآن، ابدأ بالمشاركة لتظهر في القائمة!",
                inline=False
            )

        if not embed.footer.text:
            embed.set_footer(text="Z I UO Global Leaderboard System ✦ Ultimate Analytics")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="level_reset_config", description="[إدارة] ضبط روم الإعلانات ونظام الريسيت الدوري ومضاعفات النقاط")
    @app_commands.choices(reset_type=[
        app_commands.Choice(name="يومي (مرتين في اليوم)", value="daily"),
        app_commands.Choice(name="أسبوعي (مرتين في اليوم طوال الأسبوع)", value="weekly"),
        app_commands.Choice(name="شهري (مرتين في اليوم طوال الشهر)", value="monthly"),
        app_commands.Choice(name="إيقاف نظام الريسيت", value="none")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def level_reset_config(
        self, 
        interaction: discord.Interaction, 
        reset_type: str, 
        multiplier_value: int = 1, 
        announcement_channel: discord.TextChannel = None
    ):
        settings = get_guild_settings(interaction.guild.id)
        settings["reset_type"] = reset_type
        settings["multiplier"] = multiplier_value
        if announcement_channel:
            settings["announcement_channel"] = announcement_channel.id

        await interaction.response.send_message(
            f"✅ تم تحديث إعدادات نظام المستويات والإعلانات بنجاح تام!\n"
            f"• **نوع الريسيت المجدول:** `{reset_type.upper()}`\n"
            f"• **معامل المضاعف:** `{multiplier_value}x`\n"
            f"• **روم إعلانات الترقية:** {announcement_channel.mention if announcement_channel else 'الحالي'}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(UltimateLevelingSystemCog(bot))
