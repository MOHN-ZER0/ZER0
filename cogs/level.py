import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random
import time

# ==============================================================================
# 🌟 قاعدة البيانات الداخلية الموسعة والمؤمنة (MOHN ULTRA ENGINE v3.0)
# ==============================================================================
MOHN_SERVER_DATABASE = {
    "users": {},          # تخزين بيانات الأعضاء (xp, level, messages, voice_minutes, prestige)
    "settings": {},       # إعدادات السيرفر المخصصة
    "custom_cards": {},   # بطاقات الأعضاء وتخصيصاتها
    "cooldowns": {},      # نظام الحماية من السبام
    "audit_logs": {}      # سجلات نشاط النظام وإدارته
}

# ==============================================================================
# 🛠️ الدوال المساعدة للتحقق وجلب الإعدادات والتحليلات
# ==============================================================================
def fetch_guild_config(guild_id: int):
    """جلب أو إنشاء إعدادات السيرفر الافتراضية بنجاح"""
    if guild_id not in MOHN_SERVER_DATABASE["settings"]:
        MOHN_SERVER_DATABASE["settings"][guild_id] = {
            "status": True,
            "multiplier": 1,
            "announcement_channel": None,
            "level_message": "كفو يا {user}! لقد حققت إنجازاً ووصلت للمستوى **{level}** بنجاح مستمر!",
            "level_image": None,
            "role_rewards": {},
            "max_level": 100
        }
    return MOHN_SERVER_DATABASE["settings"][guild_id]

def record_guild_audit(guild_id: int, action_text: str):
    """تسجيل العمليات الإدارية وأحداث النظام الداخلية"""
    if guild_id not in MOHN_SERVER_DATABASE["audit_logs"]:
        MOHN_SERVER_DATABASE["audit_logs"][guild_id] = []
    
    timestamp_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp_str}] {action_text}"
    
    # الاحتفاظ بأخر 50 سجل فقط لتجنب امتلاء الذاكرة
    MOHN_SERVER_DATABASE["audit_logs"][guild_id].append(log_entry)
    if len(MOHN_SERVER_DATABASE["audit_logs"][guild_id]) > 50:
        MOHN_SERVER_DATABASE["audit_logs"][guild_id].pop(0)

# ==============================================================================
# 🎛️ النوافذ التفاعلية (Modals) المتقدمة لتعديل إعدادات اللفلات والرسائل
# ==============================================================================
class CustomMessageModal(discord.ui.Modal, title="تعديل رسالة الصعود المخصصة"):
    msg_box = discord.ui.TextInput(
        label="اكتب الرسالة (استخدم {user} و {level})",
        placeholder="مثال: وحش يا {user} صرت لفل {level}!",
        style=discord.TextStyle.paragraph,
        max_length=800,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["level_message"] = self.msg_box.value
        record_guild_audit(interaction.guild.id, f"Admin {interaction.user} updated level up message template.")
        await interaction.response.send_message(f"✨ تم تحديث رسالة الترقية بنجاح إلى:\n> `{self.msg_box.value}`", ephemeral=True)


class CustomImageModal(discord.ui.Modal, title="تعديل رابط صورة الترقية"):
    img_box = discord.ui.TextInput(
        label="رابط الصورة المباشر (أو اكتب none للإزالة)",
        placeholder="https://imgur.com/...",
        max_length=400,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        val = self.img_box.value.strip()
        if val.lower() == "none":
            cfg["level_image"] = None
            record_guild_audit(interaction.guild.id, f"Admin {interaction.user} removed level up banner image.")
            await interaction.response.send_message("🗑️ تم إزالة صورة الترقية بنجاح.", ephemeral=True)
        else:
            cfg["level_image"] = val
            record_guild_audit(interaction.guild.id, f"Admin {interaction.user} updated level up banner image.")
            await interaction.response.send_message(f"🖼️ تم حفظ صورة الترقية الجديدة بنجاح.", ephemeral=True)


class AddRewardRoleModal(discord.ui.Modal, title="ربط رتبة بمستوى معين"):
    lvl_box = discord.ui.TextInput(
        label="رقم المستوى المطلوب",
        placeholder="مثال: 5، 10، 20",
        max_length=5,
        required=True
    )
    role_box = discord.ui.TextInput(
        label="أيدي الرتبة (Role ID)",
        placeholder="قم بلصق أيدي الرتبة هنا",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level_num = int(self.lvl_box.value.strip())
            role_id = int(self.role_box.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال أرقام صحيحة ومقبولة للمستوى وأيدي الرتبة!", ephemeral=True)
            return

        role_obj = interaction.guild.get_role(role_id)
        if not role_obj:
            await interaction.response.send_message("❌ لم يتم العثور على رتبة بهذا الأيدي في هذا السيرفر!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["role_rewards"][str(level_num)] = role_obj.id
        record_guild_audit(interaction.guild.id, f"Admin {interaction.user} linked level {level_num} to role {role_obj.name}.")
        await interaction.response.send_message(f"🎁 تم بنجاح ربط المستوى **{level_num}** بالرتبة المميزة {role_obj.mention}!", ephemeral=True)


class SetMultiplierModal(discord.ui.Modal, title="تحديد مضاعف النقاط (Multiplier)"):
    mult_box = discord.ui.TextInput(
        label="قيمة المضاعف (مثال: 1, 2, 3)",
        placeholder="2",
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.mult_box.value.strip())
            if val < 1 or val > 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال رقم صحيح للمضاعف بين 1 و 10!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["multiplier"] = val
        record_guild_audit(interaction.guild.id, f"Admin {interaction.user} changed XP multiplier to {val}x.")
        await interaction.response.send_message(f"⚡ تم ضبط مضاعف الـ XP في السيرفر ليصبح **{val}x** بنجاح!", ephemeral=True)


# ==============================================================================
# 🎛️ أزرار لوحة التحكم الإدارية المتقدمة والمطورة بالكامل
# ==============================================================================
class MohnAdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف النظام", style=discord.ButtonStyle.blurple, emoji="🔄", custom_id="mohn_toggle_sys_v3")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["status"] = not cfg["status"]
        state_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        record_guild_audit(interaction.guild.id, f"Admin {interaction.user} toggled system status to {state_str}.")
        await interaction.response.send_message(f"⚙️ أصبحت حالة نظام المستويات الآن: **{state_str}**", ephemeral=True)

    @discord.ui.button(label="تعديل رسالة الصعود", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="mohn_edit_msg_v3")
    async def edit_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomMessageModal())

    @discord.ui.button(label="تعديل صورة الصعود", style=discord.ButtonStyle.secondary, emoji="🖼️", custom_id="mohn_edit_img_v3")
    async def edit_img(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomImageModal())

    @discord.ui.button(label="إضافة مكافأة رتبة", style=discord.ButtonStyle.success, emoji="🎁", custom_id="mohn_add_reward_v3")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRewardRoleModal())

    @discord.ui.button(label="ضبط مضاعف الـ XP", style=discord.ButtonStyle.danger, emoji="⚡", custom_id="mohn_set_mult_v3")
    async def set_mult(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetMultiplierModal())


class MohnCardCustomModal(discord.ui.Modal, title="تخصيص بطاقة الرانك الخاصة بك"):
    color_box = discord.ui.TextInput(
        label="كود لون البطاقة (Hex Code)",
        placeholder="#5865F2",
        default="#5865F2",
        max_length=7,
        required=True
    )
    status_box = discord.ui.TextInput(
        label="نبذتك الشخصية أو شعارك",
        placeholder="اكتب شيئاً مميزاً عنك هنا...",
        max_length=100,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid not in MOHN_SERVER_DATABASE["custom_cards"]:
            MOHN_SERVER_DATABASE["custom_cards"][uid] = {}
        
        MOHN_SERVER_DATABASE["custom_cards"][uid]["color"] = self.color_box.value
        MOHN_SERVER_DATABASE["custom_cards"][uid]["status"] = self.status_box.value
        await interaction.response.send_message("✨ تم حفظ تخصيص بطاقتك الشخصية بنجاح تام!", ephemeral=True)


class MohnCardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تخصيص بطاقتي", style=discord.ButtonStyle.primary, emoji="🎨", custom_id="mohn_custom_card_btn_v3")
    async def custom_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MohnCardCustomModal())


# ==============================================================================
# 🚀 محرك التشغيل البرمجي الموسع والمحترف (Listeners & Advanced Loops)
# ==============================================================================
class MohnAdvancedLevelSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.voice_xp_loop.cancel()

    # نظام فحص أصوات الأعضاء ومنح XP عشوائي (5 إلى 25) كل دقيقة بدقة فائقة
    @tasks.loop(minutes=1)
    async def voice_xp_loop(self):
        for guild in self.bot.guilds:
            gid = guild.id
            cfg = fetch_guild_config(gid)
            if not cfg["status"]:
                continue
            
            mult = cfg["multiplier"]

            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot or member.voice.self_mute or member.voice.self_deaf:
                        continue
                    
                    if gid not in MOHN_SERVER_DATABASE["users"]:
                        MOHN_SERVER_DATABASE["users"][gid] = {}
                    if member.id not in MOHN_SERVER_DATABASE["users"][gid]:
                        MOHN_SERVER_DATABASE["users"][gid][member.id] = {
                            "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
                        }

                    udata = MOHN_SERVER_DATABASE["users"][gid][member.id]
                    udata["voice_minutes"] += 1
                    
                    # منح إكس بي صوتي عشوائي بين 5 و 25 مع تطبيق المضاعف
                    gained = random.randint(5, 25) * mult
                    udata["xp"] += gained

                    # فحص الصعود التلقائي للفويس
                    await self.check_level_up(member, gid, udata)

    @voice_xp_loop.before_loop
    async def before_voice(self):
        await self.bot.wait_until_ready()

    async def check_level_up(self, member, gid, udata):
        """دالة مركزية لفحص وتأكيد الارتقاء بالمستوى ومنح الرتب التلقائية"""
        cfg = fetch_guild_config(gid)
        req_xp = (udata["level"] + 1) * 250 + (udata["level"] * 110)

        if udata["xp"] >= req_xp:
            udata["level"] += 1
            udata["xp"] = 0 # تصفير الباقي للصعود للمستوى التالي

            # فحص مكافآت الرتب التلقائية المرتبطة بهذا المستوى
            role_rewards = cfg.get("role_rewards", {})
            assigned_role_id = role_rewards.get(str(udata["level"]))
            if assigned_role_id:
                r_target = member.guild.get_role(int(assigned_role_id))
                if r_target:
                    try:
                        await member.add_roles(r_target, reason=f"Mohn Level Engine: Reached level {udata['level']}")
                    except:
                        pass

            try:
                template = cfg.get("level_message", "كفو يا {user}! صرت لفل {level}!")
                final_text = template.replace("{user}", member.mention).replace("{level}", str(udata["level"]))

                embed = discord.Embed(
                    title="🎉 ترقية جديدة في مستويات السيرفر!",
                    description=f"{final_text}\n\n• **المستوى الحالي:** `{udata['level']}`\n• **إجمالي الرسائل:** `{udata['messages']}`",
                    color=0x00FF88,
                    timestamp=datetime.datetime.utcnow()
                )
                
                if cfg.get("level_image"):
                    embed.set_image(url=cfg["level_image"])

                embed.set_footer(text="MOHN Leveling Protocol ✦ نظام الارتقاء التلقائي")
                
                chan_id = cfg.get("announcement_channel")
                target_channel = member.guild.get_channel(chan_id) if chan_id else member.guild.system_channel
                if target_channel:
                    await target_channel.send(content=f"🌟 مبروك يا {member.mention}!", embed=embed)
            except:
                pass

    # نظام الرسائل مع إكس بي عشوائي (5 إلى 15) وحالات نادرة لعدم احتساب إكس بي لمنع السبام مع كولداون دقيق
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        gid = message.guild.id
        uid = message.author.id
        cfg = fetch_guild_config(gid)

        if not cfg["status"]:
            return

        # نظام الكولداون الصارم لمنع السبام (5 ثوانٍ بين الرسائل المحسوبة)
        now_ts = time.time()
        cd_dict = MOHN_SERVER_DATABASE["cooldowns"]
        if gid not in cd_dict:
            cd_dict[gid] = {}
        
        last_time = cd_dict[gid].get(uid, 0)
        if now_ts - last_time < 5:
            return
        cd_dict[gid][uid] = now_ts

        # حالات نادرة جداً (بنسبة عشوائية 15%) لا يتم فيها منح XP لمنع السبام العشوائي والواقعية
        if random.random() < 0.15:
            return

        if gid not in MOHN_SERVER_DATABASE["users"]:
            MOHN_SERVER_DATABASE["users"][gid] = {}
        if uid not in MOHN_SERVER_DATABASE["users"][gid]:
            MOHN_SERVER_DATABASE["users"][gid][uid] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
            }

        udata = MOHN_SERVER_DATABASE["users"][gid][uid]
        mult = cfg["multiplier"]

        # إكس بي عشوائي بين 5 و 15 حصراً (لا يزيد عن 15 أبداً)
        gained_xp = random.randint(5, 15) * mult
        udata["xp"] += gained_xp
        udata["messages"] += 1

        await self.check_level_up(message.author, gid, udata)

    # ==========================================================================
    # ⚙️ الأوامر الرئيسية الموسعة (Slash Commands)
    # ==========================================================================

    @app_commands.command(name="levels_panel", description="[الإدارة] لوحة التحكم الكاملة والمتقدمة لإدارة نظام الليفلات بالكامل")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction, announcement_channel: discord.TextChannel = None):
        cfg = fetch_guild_config(interaction.guild.id)
        if announcement_channel:
            cfg["announcement_channel"] = announcement_channel.id

        status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        chan_display = announcement_channel.mention if announcement_channel else (interaction.guild.get_channel(cfg["announcement_channel"]).mention if cfg["announcement_channel"] else "روم الرسالة الحالية 💬")
        rewards_count = len(cfg["role_rewards"])

        embed = discord.Embed(
            title="⚙️ لوحة تحكم نظام المستويات الاحترافية - MOHN",
            description=(
                "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل واللفلات.\n"
                "يمكنك التحكم بكافة الخصائص عبر الأزرار التفاعلية أدناه:\n\n"
                f"• **حالة النظام:** {status_str}\n"
                f"• **روم إعلانات الترقية:** {chan_display}\n"
                f"• **مضاعف النقاط الحالي:** `{cfg['multiplier']}x` ⚡\n"
                f"• **عدد رتب المكافآت المضافة:** `{rewards_count}` رتبة\n"
                f"• **الرسالة الحالية:** `{cfg['level_message']}`"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="MOHN Admin Core ✦ Powered for Server Management")
        await interaction.response.send_message(embed=embed, view=MohnAdminPanelView(), ephemeral=True)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية الخاصة بك أو بأي عضو")
    @app_commands.describe(member="العضو المراد الكشف عن مستواه")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = interaction.guild.id

        users_data = MOHN_SERVER_DATABASE["users"].get(gid, {})
        udata = users_data.get(target.id, {"xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0})
        
        card_conf = MOHN_SERVER_DATABASE["custom_cards"].get(target.id, {})
        hex_color = card_conf.get("color", "#5865F2")
        try:
            color_val = int(hex_color.replace("#", ""), 16)
        except:
            color_val = 0x5865F2

        req_xp = (udata["level"] + 1) * 250 + (udata["level"] * 110)

        embed = discord.Embed(
            title=f"📊 بطاقة إحصائيات المستوى - {target.display_name}",
            description=(
                f"سجل التفاعل والنشاط الكامل:\n\n"
                f"• **المستوى الحالي:** `{udata['level']}` 🏆\n"
                f"• **نقاط الخبرة (XP):** `{udata['xp']} / {req_xp}` 🌟\n"
                f"• **الرسائل المرسلة:** `{udata['messages']}` رسالة 📝\n"
                f"• **الوقت الصوتي:** `{udata['voice_minutes']}` دقيقة 🔊\n"
                f"• **مستوى البريستيج:** `{udata.get('prestige', 0)}` ✨\n"
                f"• **النبذة الشخصية:** `{card_conf.get('status', 'لا توجد نبذة مضافة')}`"
            ),
            color=color_val,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="MOHN Rank System ✦ بطاقة العضو النشط")
        
        await interaction.response.send_message(embed=embed, view=MohnCardView(), ephemeral=False)

    @app_commands.command(name="top", description="عرض لوحة شرف المتصدرين لأعلى 10 أعضاء في السيرفر مع ترتيبك الشخصي")
    async def top(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        users_data = MOHN_SERVER_DATABASE["users"].get(gid, {})

        if not users_data:
            await interaction.response.send_message("❌ لا توجد أي بيانات تفاعل مسجلة في النظام حتى الآن!", ephemeral=True)
            return

        sorted_members = sorted(users_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
        top_ten = sorted_members[:10]

        lines = []
        for rank_idx, (uid, udata) in enumerate(top_ten, start=1):
            m_obj = interaction.guild.get_member(uid)
            name_str = m_obj.mention if m_obj else f"عضو مغادر (`{uid}`)"
            
            badge = "👑" if rank_idx == 1 else "🥈" if rank_idx == 2 else "🥉" if rank_idx == 3 else f"`#{rank_idx}`"
            lines.append(
                f"{badge} ╎ {name_str}\n"
                f" ┗ المستوى: **{udata['level']}** | XP: **{udata['xp']}** | الرسائل: **{udata['messages']}**\n"
            )

        embed = discord.Embed(
            title="🏆 لوحة شرف المتصدرين الكبرى - MOHN Rankings",
            description="أبرز 10 أعضاء الأكثر تفاعلاً ونشاطاً في السيرفر:\n\n" + "\n".join(lines),
            color=0xFFD700,
            timestamp=datetime.datetime.utcnow()
        )

        current_uid = interaction.user.id
        user_rank_pos = None
        user_record = None

        for pos, (uid, udata) in enumerate(sorted_members, start=1):
            if uid == current_uid:
                user_rank_pos = pos
                user_record = udata
                break

        if user_rank_pos and user_rank_pos > 10:
            if not user_record:
                user_record = users_data.get(current_uid, {"xp": 0, "level": 0, "messages": 0})
            
            cfg = fetch_guild_config(gid)
            r_rewards = cfg.get("role_rewards", {})
            reward_role_id = r_rewards.get(str(user_record["level"]))
            role_mention_str = ""
            if reward_role_id:
                r_found = interaction.guild.get_role(int(reward_role_id))
                if r_found:
                    role_mention_str = f" | الرتبة: {r_found.mention}"

            embed.add_field(
                name="📌 مركزك وترتيبك الشخصي",
                value=(
                    f"• **الترتيب:** `#{user_rank_pos}` من الأعضاء\n"
                    f"• **المستوى:** `{user_record['level']}` | **XP:** `{user_record['xp']}`{role_mention_str}"
                ),
                inline=False
            )
        elif user_rank_pos and user_rank_pos <= 10:
            embed.set_footer(text=f"أنت في المركز #{user_rank_pos} ضمن قائمة العشرة الأوائل! استمر 🌟")
        else:
            embed.add_field(
                name="📌 مركزك وترتيبك الشخصي",
                value="ليس لديك تفاعل مسجل بعد، ابدأ بالمشاركة في الرومات لتظهر في لوحة الشرف!",
                inline=False
            )

        if not embed.footer.text:
            embed.set_footer(text="MOHN Leaderboard System ✦ All Rights Reserved")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="level_manage", description="[الإدارة] إضافة أو إزالة نقاط أو لفلات لأي عضو في السيرفر")
    @app_commands.describe(member="العضو المستهدف", action="إضافة أو خصم", amount="قيمة النقاط أو اللفلات")
    @app_commands.choices(action=[
        app_commands.Choice(name="إضافة XP", value="add_xp"),
        app_commands.Choice(name="خصم XP", value="remove_xp"),
        app_commands.Choice(name="تعيين مستوى", value="set_level")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def level_manage(self, interaction: discord.Interaction, member: discord.Member, action: str, amount: int):
        gid = interaction.guild.id
        if gid not in MOHN_SERVER_DATABASE["users"]:
            MOHN_SERVER_DATABASE["users"][gid] = {}
        if member.id not in MOHN_SERVER_DATABASE["users"][gid]:
            MOHN_SERVER_DATABASE["users"][gid][member.id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0, "prestige": 0
            }

        udata = MOHN_SERVER_DATABASE["users"][gid][member.id]

        if action == "add_xp":
            udata["xp"] += amount
            record_guild_audit(gid, f"Admin {interaction.user} added {amount} XP to {member}.")
            await interaction.response.send_message(f"✅ تمت إضافة `{amount} XP` بنجاح للعضو {member.mention}!", ephemeral=True)
        elif action == "remove_xp":
            udata["xp"] = max(0, udata["xp"] - amount)
            record_guild_audit(gid, f"Admin {interaction.user} removed {amount} XP from {member}.")
            await interaction.response.send_message(f"✅ تم خصم `{amount} XP` بنجاح من العضو {member.mention}!", ephemeral=True)
        elif action == "set_level":
            udata["level"] = max(0, amount)
            udata["xp"] = 0
            record_guild_audit(gid, f"Admin {interaction.user} set level of {member} to {amount}.")
            await interaction.response.send_message(f"✅ تم تغيير مستوى العضو {member.mention} إلى المستوى `{amount}` بنجاح!", ephemeral=True)

    @app_commands.command(name="server_stats", description="عرض إحصائيات عامة حول نشاط نظام الليفلات والسيرفر")
    @app_commands.checks.has_permissions(administrator=True)
    async def server_stats(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        users_data = MOHN_SERVER_DATABASE["users"].get(gid, {})
        
        total_tracked_users = len(users_data)
        total_messages_all = sum(u.get("messages", 0) for u in users_data.values())
        total_voice_all = sum(u.get("voice_minutes", 0) for u in users_data.values())
        
        cfg = fetch_guild_config(gid)
        
        embed = discord.Embed(
            title="📈 إحصائيات ونشاط نظام المستويات - MOHN Analytics",
            description=(
                "نظرة عامة على بيانات التفاعل داخل السيرفر:\n\n"
                f"• **إجمالي الأعضاء النشطين في النظام:** `{total_tracked_users}` عضو\n"
                f"• **إجمالي الرسائل المحتسبة:** `{total_messages_all}` رسالة\n"
                f"• **إجمالي دقائق التواجد الصوتي:** `{total_voice_all}` دقيقة\n"
                f"• **حالة مضاعف النقاط:** `{cfg['multiplier']}x`\n"
                f"• **عدد رتب المكافآت:** `{len(cfg['role_rewards'])}` رتبة مجهزة"
            ),
            color=0x00AE86,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="MOHN System Monitoring ✦ Analytics Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MohnAdvancedLevelSystem(bot))
