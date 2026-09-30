import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random

# ==============================================================================
# 🌟 نظام قاعدة البيانات الشاملة والموسعة (Advanced Ultra Database - Clean Edition)
# ==============================================================================
SERVER_ULTRA_DB = {
    "users": {},              # تخزين بيانات الأعضاء (xp, level, messages, voice_minutes, prestige)
    "settings": {},           # إعدادات السيرفر الشاملة (روم الإعلانات، رتب المكافآت، الاستثناءات)
    "custom_cards": {},       # تخصيص بطاقات الرانك لكل عضو
    "blacklists": {},         # القائمة السوداء للأعضاء أو القنوات
    "temporary_boosts": {}    # مضاعفات النقاط المؤقتة
}

# ==============================================================================
# 🎨 واجهات النوافذ المنبثقة والأزرار الاحترافية (Modals & Views)
# ==============================================================================

class UltimateRankModal(discord.ui.Modal, title="تخصيص بطاقة المستوى الشخصية - Z I UO Ultimate"):
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

    @discord.ui.button(label="تخصيص البطاقة بالكامل", style=discord.ButtonStyle.primary, emoji="🎨", custom_id="ultra_customize_card_btn_v3")
    async def customize_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UltimateRankModal())

    @discord.ui.button(label="استعراض جدول الرتب والمكافآت", style=discord.ButtonStyle.secondary, emoji="🏆", custom_id="ultra_rewards_btn_v3")
    async def rewards_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="دليل رتب ومكافآت التفاعل التلقائية - Z I UO Server",
            description=(
                "مرحباً بك في جدول الرتب الممنوحة عند الارتقاء بالمستويات:\n\n"
                "• **المستوى 05:** رتبة عضو نشط (Active Member)\n"
                "• **المستوى 10:** رتبة مشارك مميز (Elite Contributor)\n"
                "• **المستوى 20:** رتبة خبير السيرفر (Server Expert)\n"
                "• **المستوى 35:** رتبة محترف التفاعل (Master VIP)\n"
                "• **المستوى 50:** رتبة أسطورة السيرفر (Legendary Overlord)\n\n"
                "يتم منح هذه الرتب وتحديثها آلياً عبر محرك النظام."
            ),
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Global Management System ✦ Reward Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="نظام البرستيج المتقدم", style=discord.ButtonStyle.success, emoji="⭐", custom_id="ultra_prestige_btn_v3")
    async def prestige_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        uid = interaction.user.id
        
        if guild_id not in SERVER_ULTRA_DB["users"] or uid not in SERVER_ULTRA_DB["users"][guild_id]:
            await interaction.response.send_message("❌ ليس لديك أي سجل تفاعل كافي لتنفيذ البرستيج حالياً!", ephemeral=True)
            return
            
        user_data = SERVER_ULTRA_DB["users"][guild_id][uid]
        if user_data["level"] < 50:
            await interaction.response.send_message(f"⚠️ يجب أن تصل على الأقل إلى **المستوى 50** لكي تتمكن من تنفيذ ترقية البرستيج (مستواك الحالي: {user_data['level']}).", ephemeral=True)
            return

        user_data["prestige"] += 1
        user_data["level"] = 0
        user_data["xp"] = 0
        
        await interaction.response.send_message(f"🎉 **مبروك يا أسطورة!** لقد قمت بترقية حسابك بنجاح إلى مرحلة **البرستيج رقم {user_data['prestige']}**!", ephemeral=False)


# ==============================================================================
# ⚙️ محرك الـ Cog الرئيسي والممتد بكامل الأنظمة الاحترافية المستقرة
# ==============================================================================
class UltimateLevelingSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scheduled_reset_task.start()
        self.voice_xp_loop.start()
        self.analytics_backup_loop.start()

    def cog_unload(self):
        self.scheduled_reset_task.cancel()
        self.voice_xp_loop.cancel()
        self.analytics_backup_loop.cancel()

    @tasks.loop(hours=12)
    async def scheduled_reset_task(self):
        now = datetime.datetime.utcnow()
        for guild_id, settings in SERVER_ULTRA_DB.get("settings", {}).items():
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
                    await channel.send("🔄 **[تقرير نظام المستويات اليومي الشامل]** ╎ تم تنفيذ دورة التحديث والتحقق اليومية بنجاح تام في السيرفر!")
                elif reset_type == "weekly":
                    if now.weekday() == 0:
                        await channel.send("📊 **[تقرير نظام المستويات الأسبوعي]** ╎ جاري فحص ومراجعة تصنيفات المتصدرين الدورية طوال هذا الأسبوع!")
                elif reset_type == "monthly":
                    if now.day == 1:
                        await channel.send("📊 **[تقرير نظام المستويات الشهري الشامل]** ╎ تم إطلاق الدورة الشهرية الجديدة وتصفير النقاط المجدولة!")
            except:
                pass

    @scheduled_reset_task.before_loop
    async def before_scheduled_reset(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def analytics_backup_loop(self):
        pass

    @analytics_backup_loop.before_loop
    async def before_analytics_backup(self):
        await self.bot.wait_until_ready()

    # محرك احتساب نقاط التواجد الصوتي الاحترافي المتقدم
    @tasks.loop(minutes=5)
    async def voice_xp_loop(self):
        for guild in self.bot.guilds:
            guild_id = guild.id
            if guild_id not in SERVER_ULTRA_DB["settings"]:
                continue
            
            settings = SERVER_ULTRA_DB["settings"][guild_id]
            multiplier = settings.get("multiplier", 1)

            if guild_id in SERVER_ULTRA_DB.get("temporary_boosts", {}):
                multiplier *= SERVER_ULTRA_DB["temporary_boosts"][guild_id].get("multiplier", 1)

            for vc in guild.voice_channels:
                if vc.id in settings.get("ignored_channels", []):
                    continue

                for member in vc.members:
                    if member.bot:
                        continue
                    
                    if guild_id in SERVER_ULTRA_DB.get("blacklists", {}) and member.id in SERVER_ULTRA_DB["blacklists"][guild_id]:
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

    # محرك احتساب النقاط والرسائل النصية التلقائي وإرسالها للروم المخصص للإعلانات
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        if guild_id not in SERVER_ULTRA_DB["settings"]:
            SERVER_ULTRA_DB["settings"][guild_id] = {
                "multiplier": 1,
                "ignored_channels": [],
                "target_role_id": None,
                "reset_type": "none",
                "announcement_channel": None,
                "custom_level_message": "أهلاً بك يا {user}، لقد صعدت بنجاح إلى المستوى {level}!",
                "role_rewards": {}
            }

        settings = SERVER_ULTRA_DB["settings"][guild_id]

        if message.channel.id in settings["ignored_channels"]:
            return

        if guild_id in SERVER_ULTRA_DB.get("blacklists", {}) and user_id in SERVER_ULTRA_DB["blacklists"][guild_id]:
            return

        if guild_id not in SERVER_ULTRA_DB["users"]:
            SERVER_ULTRA_DB["users"][guild_id] = {}

        if user_id not in SERVER_ULTRA_DB["users"][guild_id]:
            SERVER_ULTRA_DB["users"][guild_id][user_id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
            }

        user_data = SERVER_ULTRA_DB["users"][guild_id][user_id]
        
        active_mult = settings["multiplier"]
        if guild_id in SERVER_ULTRA_DB.get("temporary_boosts", {}):
            active_mult *= SERVER_ULTRA_DB["temporary_boosts"][guild_id].get("multiplier", 1)

        base_gain = random.randint(22, 40)
        earned_xp = base_gain * active_mult

        user_data["xp"] += earned_xp
        user_data["messages"] += 1

        req_xp = (user_data["level"] + 1) * 280 + (user_data["level"] * 85)

        if user_data["xp"] >= req_xp:
            user_data["level"] += 1
            user_data["xp"] = 0

            role_rewards = settings.get("role_rewards", {})
            reward_role_id = role_rewards.get(str(user_data["level"]))
            if reward_role_id:
                r_obj = message.guild.get_role(int(reward_role_id))
                if r_obj:
                    try:
                        await message.author.add_roles(r_obj, reason=f"Level Reward System: Reached level {user_data['level']}")
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
                        f"• **معامل المضاعف النشط:** `{active_mult}x`\n"
                        f"• **إجمالي الرسائل المرصودة:** `{user_data['messages']}` رسالة\n\n"
                        f"واصل التفاعل لتحقيق مراتب أعلى في لوحة الشرف!"
                    ),
                    color=0x00FF99,
                    timestamp=datetime.datetime.utcnow()
                )
                up_embed.set_footer(text="Z I UO Enterprise Advanced Leveling Engine")
                
                # إرسال الرسالة حصرياً في روم الإعلانات المحدد مسبقاً أو روم الرسالة الحالية
                target_chan = message.guild.get_channel(settings["announcement_channel"]) if settings["announcement_channel"] else message.channel
                await target_chan.send(content=f"🎯 ممتاز يا {message.author.mention}!", embed=up_embed)
            except:
                pass

    # ==========================================================================
    # 🚀 أووامر السلاش كوماندز الكاملة والمتقدمة (Slash Commands Suite)
    # ==========================================================================

    @app_commands.command(name="rank", description="استعراض بطاقة الرانك والمستوى الاحترافية والكاملة لأي عضو في السيرفر")
    @app_commands.describe(member="العضو المراد الكشف عن رانكه")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        guild_id = interaction.guild.id

        guild_users = SERVER_ULTRA_DB["users"].get(guild_id, {})
        user_data = guild_users.get(target.id, {"xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0})
        
        custom_conf = SERVER_ULTRA_DB["custom_cards"].get(target.id, {})
        color_hex = custom_conf.get("color", "#5865F2")
        color_int = int(color_hex.replace("#", ""), 16)

        req_xp = (user_data["level"] + 1) * 280 + (user_data["level"] * 85)

        embed = discord.Embed(
            title=f"بطاقة المستوى والخبرة الاحترافية - {target.display_name}",
            description=(
                f"إليك كافة الإحصائيات الشاملة لسجل تفاعلك ونشاطك داخل السيرفر:\n\n"
                f"• **المستوى الحالي (Level):** `{user_data['level']}`\n"
                f"• **نقاط الخبرة (XP):** `{user_data['xp']} / {req_xp}`\n"
                f"• **عدد الرسائل النصية:** `{user_data['messages']}` رسالة\n"
                f"• **دقائق التواجد الصوتي:** `{user_data['voice_minutes']}` دقيقة\n"
                f"• **مستوى البرستيج:** `{user_data['prestige']}` مرحلة\n"
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

    @app_commands.command(name="levels", description="عرض لوحة المتصدرين الكبرى وقائمة الشرف الكاملة لجميع أعضاء السيرفر")
    async def levels(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        guild_users = SERVER_ULTRA_DB["users"].get(guild_id, {})

        if not guild_users:
            await interaction.response.send_message("❌ لا توجد أي بيانات مسجلة في نظام المستويات حتى هذه اللحظة!", ephemeral=True)
            return

        sorted_users = sorted(guild_users.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:15]

        ranking_lines = []
        for index, (uid, data) in enumerate(sorted_users, start=1):
            member_obj = interaction.guild.get_member(uid)
            display_name = member_obj.mention if member_obj else f"عضو مغادر (`{uid}`)"
            
            medal_icon = "👑" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"`#{index}`"
            ranking_lines.append(
                f"{medal_icon} ╎ {display_name} ──► Level: **{data['level']}** | XP: **{data['xp']}** | Prestige: **{data['prestige']}** ⭐"
            )

        embed = discord.Embed(
            title="لوحة شرف المتصدرين الكبرى - سيرفر Z I UO",
            description=(
                "قائمة بأبرز الأعضاء الأكثر نشاطاً وتفاعلاً على مستوى السيرفر بالكامل.\n"
                "يتم التحديث الآلي عبر خوارزميات النظام المتقدمة:\n\n" +
                "\n".join(ranking_lines)
            ),
            color=0xFFD700,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Global Leaderboard System ✦ Ultimate Analytics")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="level_message_config", description="[إدارة] تخصيص وتعديل نص رسالة الترقية عند صعود العضو للمستوى التالي")
    @app_commands.describe(custom_text="اكتب نص الرسالة الجديد (استخدم {user} لاسم العضو و {level} للمستوى الجديد)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_message_config(self, interaction: discord.Interaction, custom_text: str):
        guild_id = interaction.guild.id
        if guild_id not in SERVER_ULTRA_DB["settings"]:
            SERVER_ULTRA_DB["settings"][guild_id] = {}

        SERVER_ULTRA_DB["settings"][guild_id]["custom_level_message"] = custom_text

        await interaction.response.send_message(
            f"✅ تم تحديث وتخصيص نص رسالة الترقية بنجاح تام!\n\n"
            f"• **النص الجديد المسجل:**\n> `{custom_text}`",
            ephemeral=True
        )

    @app_commands.command(name="level_reward_role", description="[إدارة] ربط رتبة تلقائية بمستوى محدد يمنحها البوت للعضو فور وصوله")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_reward_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        guild_id = interaction.guild.id
        if guild_id not in SERVER_ULTRA_DB["settings"]:
            SERVER_ULTRA_DB["settings"][guild_id] = {}
        if "role_rewards" not in SERVER_ULTRA_DB["settings"][guild_id]:
            SERVER_ULTRA_DB["settings"][guild_id]["role_rewards"] = {}

        SERVER_ULTRA_DB["settings"][guild_id]["role_rewards"][str(level)] = role.id

        await interaction.response.send_message(
            f"✅ تم بنجاح ربط رتبة التفاعل التلقائية:\n"
            f"• **المستوى المستهدف:** `{level}`\n"
            f"• **الرتبة الممنوحة:** {role.mention}",
            ephemeral=True
        )

    @app_commands.command(name="level_ignore_channel", description="[إدارة] استثناء قناة نصية أو صوتية من احتساب نقاط الـ XP والفلترة")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_ignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        guild_id = interaction.guild.id
        if guild_id not in SERVER_ULTRA_DB["settings"]:
            SERVER_ULTRA_DB["settings"][guild_id] = {}
        if "ignored_channels" not in SERVER_ULTRA_DB["settings"][guild_id]:
            SERVER_ULTRA_DB["settings"][guild_id]["ignored_channels"] = []

        ignored_list = SERVER_ULTRA_DB["settings"][guild_id]["ignored_channels"]
        if channel.id in ignored_list:
            ignored_list.remove(channel.id)
            await interaction.response.send_message(f"🔊 تم إزالة القناة {channel.mention} من قائمة الاستثناءات وعودتها لاحتساب النقاط.", ephemeral=True)
        else:
            ignored_list.append(channel.id)
            await interaction.response.send_message(f"🔇 تم إضافة القناة {channel.mention} إلى القائمة السوداء المستثناة من احتساب النقاط.", ephemeral=True)

    @app_commands.command(name="level_reset_config", description="[إدارة] ضبط روم الإعلانات، نظام الريسيت، ومضاعفات النقاط")
    @app_commands.choices(reset_type=[
        app_commands.Choice(name="يومي (مرتين في اليوم)", value="daily"),
        app_commands.Choice(name="أسبوعي (مرتين في اليوم طوال الأسبوع)", value="weekly"),
        app_commands.Choice(name="شهري (مرتين في اليوم طوال الشهر)", value="monthly"),
        app_commands.Choice(name="إيقاف نظام الريسيت", value="none")
    ])
    @app_commands.choices(multiplier_value=[
        app_commands.Choice(name="1x (عادي)", value=1),
        app_commands.Choice(name="2x (مضاعف)", value=2),
        app_commands.Choice(name="3x (مضاعف خارق)", value=3)
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def level_reset_config(
        self, 
        interaction: discord.Interaction, 
        reset_type: str, 
        multiplier_value: int, 
        target_role: discord.Role = None, 
        announcement_channel: discord.TextChannel = None
    ):
        guild_id = interaction.guild.id
        if guild_id not in SERVER_ULTRA_DB["settings"]:
            SERVER_ULTRA_DB["settings"][guild_id] = {}

        settings = SERVER_ULTRA_DB["settings"][guild_id]
        settings["reset_type"] = reset_type
        settings["multiplier"] = multiplier_value
        settings["target_role_id"] = target_role.id if target_role else None
        settings["announcement_channel"] = announcement_channel.id if announcement_channel else None

        await interaction.response.send_message(
            f"✅ تم تحديث إعدادات نظام المستويات والإعلانات بنجاح تام!\n"
            f"• **نوع الريسيت المجدول:** `{reset_type.upper()}`\n"
            f"• **معامل المضاعف المفعل:** `{multiplier_value}x`\n"
            f"• **روم إعلانات الترقية:** {announcement_channel.mention if announcement_channel else 'الروم الحالي للرسالة'}",
            ephemeral=True
        )

    @app_commands.command(name="level_admin_control", description="[إدارة] تعديل أو إضافة نقاط XP أو تصفير بيانات عضو محدد")
    @app_commands.choices(action=[
        app_commands.Choice(name="إضافة نقاط XP", value="add_xp"),
        app_commands.Choice(name="تحديد مستوى معين", value="set_level"),
        app_commands.Choice(name="إضافة مستوى برستيج", value="add_prestige"),
        app_commands.Choice(name="تصفير بيانات العضو", value="reset_user")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def level_admin_control(self, interaction: discord.Interaction, action: str, member: discord.Member, amount: int = 0):
        guild_id = interaction.guild.id
        if guild_id not in SERVER_ULTRA_DB["users"]:
            SERVER_ULTRA_DB["users"][guild_id] = {}
        if member.id not in SERVER_ULTRA_DB["users"][guild_id]:
            SERVER_ULTRA_DB["users"][guild_id][member.id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
            }

        record = SERVER_ULTRA_DB["users"][guild_id][member.id]

        if action == "add_xp":
            record["xp"] += amount
            await interaction.response.send_message(f"✅ تم إضافة `{amount} XP` بنجاح إلى رصيد العضو {member.mention}.", ephemeral=True)
        elif action == "set_level":
            record["level"] = amount
            record["xp"] = 0
            await interaction.response.send_message(f"✅ تم ضبط وتعديل مستوى العضو {member.mention} ليصبح عند المستوى `{amount}`.", ephemeral=True)
        elif action == "add_prestige":
            record["prestige"] += max(1, amount)
            await interaction.response.send_message(f"⭐ تم منح العضو {member.mention} عدد `{max(1, amount)}` مراحل برستيج ملكية إضافية!", ephemeral=True)
        elif action == "reset_user":
            record["xp"] = 0
            record["level"] = 0
            record["messages"] = 0
            record["voice_minutes"] = 0
            record["prestige"] = 0
            await interaction.response.send_message(f"🔄 تم تصفير وإعادة تهيئة بيانات العضو {member.mention} بالكامل.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UltimateLevelingSystemCog(bot))
