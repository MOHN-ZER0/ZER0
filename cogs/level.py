import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random
import time

# ==============================================================================
# 🌟 قاعدة البيانات الداخلية (MOHN ULTIMATE CORE v5.0)
# ==============================================================================
MOHN_SERVER_DATABASE = {
    "users": {},          
    "settings": {},       
    "custom_cards": {},   
    "cooldowns": {}       
}

def fetch_guild_config(guild_id: int):
    if guild_id not in MOHN_SERVER_DATABASE["settings"]:
        MOHN_SERVER_DATABASE["settings"][guild_id] = {
            "status": True,
            "multiplier": 1,
            "announcement_channel": None,
            "level_message": "✨ كفو يا {user}! لقد أثبتَّ حضورك وصعدت بنجاح إلى المستوى **{level}**!",
            "level_image": None,
            "role_rewards": {},
            "reset_type": "أسبوعي (مرتين في الأسبوع)",
            "allowed_role_id": None
        }
    return MOHN_SERVER_DATABASE["settings"][guild_id]

# ==============================================================================
# 🛠️ الواجهات المنبثقة (Modals)
# ==============================================================================
class ResetConfigModal(discord.ui.Modal, title="⚙️ إعدادات نظام الريسيت الدوري وتوب السيرفر"):
    reset_type_box = discord.ui.TextInput(
        label="نوع التسيير (أسبوعي / شهري / يومي / متوقف)",
        placeholder="مثال: أسبوعي (مرتين في الأسبوع)",
        default="أسبوعي (مرتين في الأسبوع)",
        max_length=50,
        required=True
    )
    channel_id_box = discord.ui.TextInput(
        label="أيدي روم الإعلانات والتوب (Channel ID)",
        placeholder="قم بلصق أيدي الروم هنا (اختياري)",
        max_length=30,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["reset_type"] = self.reset_type_box.value
        chan_text = self.channel_id_box.value.strip()
        if chan_text.isdigit():
            cfg["announcement_channel"] = int(chan_text)

        await interaction.response.send_message(
            f"🔄 **تم تحديث إعدادات التسيير الدوري بنجاح تام!**\n"
            f"• **النظام النشط:** `{cfg['reset_type']}`\n"
            f"• **روم الإعلانات:** <#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "• **روم الإعلانات:** الروم الحالي",
            ephemeral=True
        )

class AllowedRoleModal(discord.ui.Modal, title="🛡️ تحديد رتبة التفاعل المخصصة"):
    role_id_box = discord.ui.TextInput(
        label="أيدي الرتبة (أو اكتب none للإلغاء وجعله للجميع)",
        placeholder="123456789012345678 أو none",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        val = self.role_id_box.value.strip()
        
        if val.lower() == "none":
            cfg["allowed_role_id"] = None
            await interaction.response.send_message("🌐 **تم إلغاء قيد الرتبة؛** أصبح النظام يعمل الآن لجميع أعضاء السيرفر!", ephemeral=True)
        elif val.isdigit():
            r_obj = interaction.guild.get_role(int(val))
            if r_obj:
                cfg["allowed_role_id"] = r_obj.id
                await interaction.response.send_message(f"🔒 **تم قيد النظام بنجاح!** لن يتم احتساب التفاعل إلا لأصحاب رتبة {r_obj.mention}.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ لم يتم العثور على رتبة بهذا الأيدي في السيرفر!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ يرجى إدخال أيدي صحيح أو كتابة `none`.", ephemeral=True)

class CustomMessageModal(discord.ui.Modal, title="💬 تعديل رسالة الصعود المخصصة"):
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
        await interaction.response.send_message(f"✨ تم تحديث رسالة الترقية بنجاح إلى:\n> `{self.msg_box.value}`", ephemeral=True)

class AddRewardRoleModal(discord.ui.Modal, title="🎁 ربط رتبة مكافأة بمستوى معين"):
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
        await interaction.response.send_message(f"🎁 تم بنجاح ربط المستوى **{level_num}** بالرتبة المميزة {role_obj.mention}!", ephemeral=True)

class SetMultiplierModal(discord.ui.Modal, title="⚡ تحديد مضاعف النقاط (Multiplier)"):
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
        await interaction.response.send_message(f"⚡ تم ضبط مضاعف الـ XP في السيرفر ليصبح **{val}x** بنجاح!", ephemeral=True)

# ==============================================================================
# 🎛 الأزرار الإدارية (عامة للجميع)
# ==============================================================================
class MohnAdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف النظام", style=discord.ButtonStyle.blurple, emoji="🔄", custom_id="mohn_tgl_v5")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["status"] = not cfg["status"]
        state_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        await interaction.response.send_message(f"⚙️ أصبحت حالة نظام المستويات الآن: **{state_str}**", ephemeral=True)

    @discord.ui.button(label="نظام الريسيت والتوب", style=discord.ButtonStyle.primary, emoji="📅", custom_id="mohn_reset_cfg_v5")
    async def reset_config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ResetConfigModal())

    @discord.ui.button(label="إضافة رتبة مكافأة", style=discord.ButtonStyle.success, emoji="🎁", custom_id="mohn_reward_v5")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AddRewardRoleModal())

    @discord.ui.button(label="تحديد رتبة التفاعل", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="mohn_allowed_role_v5")
    async def allowed_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AllowedRoleModal())

    @discord.ui.button(label="تعديل رسالة الصعود", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="mohn_msg_v5")
    async def edit_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(CustomMessageModal())

    @discord.ui.button(label="ضبط المضاعف", style=discord.ButtonStyle.danger, emoji="⚡", custom_id="mohn_mult_v5")
    async def set_mult(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(SetMultiplierModal())

    @discord.ui.button(label="إحصائيات السيرفر", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="mohn_stats_v5")
    async def server_stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild.id
        users_data = MOHN_SERVER_DATABASE["users"].get(gid, {})
        total_users = len(users_data)
        total_msgs = sum(u.get("messages", 0) for u in users_data.values())
        cfg = fetch_guild_config(gid)
        
        embed = discord.Embed(
            title="📊 إحصائيات ونشاط نظام الليفلات السريع - MOHN",
            description=(
                f"• **عدد الأعضاء النشطين:** `{total_users}` عضو\n"
                f"• **إجمالي الرسائل المحتسبة:** `{total_msgs}` رسالة\n"
                f"• **مضاعف النقاط الحالي:** `{cfg['multiplier']}x`\n"
                f"• **نوع الريسيت والتوب:** `{cfg['reset_type']}`"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MohnCardCustomModal(discord.ui.Modal, title="🎨 تخصيص بطاقة الرانك الخاصة بك"):
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

    @discord.ui.button(label="تخصيص بطاقتي", style=discord.ButtonStyle.primary, emoji="🎨", custom_id="mohn_card_custom_v5")
    async def custom_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MohnCardCustomModal())

# ==============================================================================
# 🚀 محرك التشغيل البرمجي المتكامل
# ==============================================================================
class MohnAdvancedLevelSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.voice_xp_loop.cancel()

    def check_allowed_member(self, member, cfg):
        allowed_role_id = cfg.get("allowed_role_id")
        if not allowed_role_id:
            return True
        return any(role.id == allowed_role_id for role in member.roles)

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
                    if not self.check_allowed_member(member, cfg):
                        continue
                    
                    if gid not in MOHN_SERVER_DATABASE["users"]:
                        MOHN_SERVER_DATABASE["users"][gid] = {}
                    if member.id not in MOHN_SERVER_DATABASE["users"][gid]:
                        MOHN_SERVER_DATABASE["users"][gid][member.id] = {
                            "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0
                        }

                    udata = MOHN_SERVER_DATABASE["users"][gid][member.id]
                    udata["voice_minutes"] += 1
                    udata["xp"] += random.randint(5, 25) * mult
                    await self.check_level_up(member, gid, udata)

    @voice_xp_loop.before_loop
    async def before_voice(self):
        await self.bot.wait_until_ready()

    async def check_level_up(self, member, gid, udata):
        cfg = fetch_guild_config(gid)
        req_xp = (udata["level"] + 1) * 250 + (udata["level"] * 110)

        if udata["xp"] >= req_xp:
            udata["level"] += 1
            udata["xp"] = 0

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
                template = cfg.get("level_message", "✨ كفو يا {user}! صرت لفل {level}!")
                final_text = template.replace("{user}", member.mention).replace("{level}", str(udata["level"]))

                embed = discord.Embed(
                    title="🎉 تـرقـيـة مـسـتـوى جـديـد!",
                    description=f"{final_text}\n\n• **المستوى الحالي:** `{udata['level']}` 🏆\n• **إجمالي الرسائل:** `{udata['messages']}` 📝",
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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        gid = message.guild.id
        uid = message.author.id
        cfg = fetch_guild_config(gid)

        if not cfg["status"] or not self.check_allowed_member(message.author, cfg):
            return

        now_ts = time.time()
        cd_dict = MOHN_SERVER_DATABASE["cooldowns"]
        if gid not in cd_dict:
            cd_dict[gid] = {}
        
        if now_ts - cd_dict[gid].get(uid, 0) < 5:
            return
        cd_dict[gid][uid] = now_ts

        if random.random() < 0.15:
            return

        if gid not in MOHN_SERVER_DATABASE["users"]:
            MOHN_SERVER_DATABASE["users"][gid] = {}
        if uid not in MOHN_SERVER_DATABASE["users"][gid]:
            MOHN_SERVER_DATABASE["users"][gid][uid] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0
            }

        udata = MOHN_SERVER_DATABASE["users"][gid][uid]
        udata["xp"] += random.randint(5, 15) * cfg["multiplier"]
        udata["messages"] += 1

        await self.check_level_up(message.author, gid, udata)

    @app_commands.command(name="levels_panel", description="[الإدارة] لوحة التحكم الكاملة والمتقدمة لإدارة نظام الليفلات بالكامل")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        chan_disp = f"<#{cfg['announcement_channel']}>" if cfg["announcement_channel"] else "روم الإعلانات الافتراضي 💬"
        allowed_role_disp = f"<@&{cfg['allowed_role_id']}>" if cfg["allowed_role_id"] else "متاح للجميع 🌐"

        embed = discord.Embed(
            title="⚙️ لـوحـة تـحـكـم نـظام الـمـسـتـويـات - MOHN CORE",
            description=(
                "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل والنشاط.\n"
                "يمكنك التحكم بكافة الخصائص والإعدادات بسلاسة عبر الأزرار أدناه:\n\n"
                f"• **حالة النظام العامة:** {status_str}\n"
                f"• **نوع الريسيت والتوب:** `{cfg['reset_type']}` 📅\n"
                f"• **روم إعلانات الترقية:** {chan_disp}\n"
                f"• **رتبة التفاعل المخصصة:** {allowed_role_disp}\n"
                f"• **مضاعف النقاط النشط:** `{cfg['multiplier']}x` ⚡\n"
                f"• **رتب المكافآت المربوطة:** `{len(cfg['role_rewards'])}` رتبة\n"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="MOHN Admin Core ✦ Ultimate Management Panel")
        await interaction.response.send_message(embed=embed, view=MohnAdminPanelView(), ephemeral=False)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية الخاصة بك أو بأي عضو")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = interaction.guild.id
        udata = MOHN_SERVER_DATABASE["users"].get(gid, {}).get(target.id, {"xp": 0, "level": 0, "messages": 0, "voice_minutes": 0})
        
        card_conf = MOHN_SERVER_DATABASE["custom_cards"].get(target.id, {})
        try:
            color_val = int(card_conf.get("color", "#5865F2").replace("#", ""), 16)
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
        cfg = fetch_guild_config(gid)

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
            lines.append(f"{badge} ╎ {name_str}\n ┗ المستوى: **{udata['level']}** | XP: **{udata['xp']}** | الرسائل: **{udata['messages']}**\n")

        embed = discord.Embed(
            title="🏆 لـوحـة شـرف المـتـصـدريـن الـكـبـرى - MOHN",
            description=f"نظام التسيير النشط: **{cfg['reset_type']}**\nأبرز 10 أعضاء تفاعلاً في السيرفر:\n\n" + "\n".join(lines),
            color=0xFFD700,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot):
    await bot.add_cog(MohnAdvancedLevelSystem(bot))
