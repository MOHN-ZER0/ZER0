import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import time

# ==============================================================================
# 🌟 قاعدة البيانات الداخلية للنظام (Global Server Database)
# ==============================================================================
SERVER_DATABASE = {
    "users": {},          
    "settings": {},       
    "custom_cards": {},   
    "cooldowns": {}       
}

def fetch_guild_config(guild_id: int):
    if guild_id not in SERVER_DATABASE["settings"]:
        SERVER_DATABASE["settings"][guild_id] = {
            "status": True,
            "multiplier": 1,
            "announcement_channel": None,
            "level_message": "✨ كفو يا {user}! لقد أثبتَّ حضورك وصعدت بنجاح إلى المستوى **`{level}`**!",
            "level_image": None,
            "role_rewards": {},
            "reset_type": "يومي",
            "allowed_role_id": None,
            "blacklisted_channels": [] # قائمة الرومات المستثناة من الـ XP
        }
    return SERVER_DATABASE["settings"][guild_id]

# دالة توليد إيمبد لوحة التحكم المحدثة لحظياً
def generate_panel_embed(guild: discord.Guild):
    cfg = fetch_guild_config(guild.id)
    status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "روم الإعلانات الافتراضي 💬"
    allowed_role_disp = f"<@&{cfg['allowed_role_id']}>" if cfg['allowed_role_id'] else "متاح للجميع 🌐"
    
    blacklist_disp = ", ".join([f"<#{cid}>" for cid in cfg["blacklisted_channels"]]) if cfg["blacklisted_channels"] else "لا توجد رومات مستثناة 📭"

    embed = discord.Embed(
        title="⚙️ لـوحـة تـحـكـم نـظام الـمـسـتـويـات (Pro Core)",
        description=(
            "مرحباً بك في لوحة الإدارة المركزية المحدثة لنظام التفاعل.\n"
            "جميع التعديلات تظهر هنا فوراً:\n\n"
            f"• **حالة النظام العامة:** {status_str}\n"
            f"• **نوع الريسيت المختار:** `{cfg['reset_type']}` 📅\n"
            f"• **روم إعلانات الترقية:** {chan_disp}\n"
            f"• **رتبة التفاعل المخصصة:** {allowed_role_disp}\n"
            f"• **مضاعف النقاط النشط:** `{cfg['multiplier']}x` ⚡\n"
            f"• **رتب المكافآت المربوطة:** `{len(cfg['role_rewards'])}` رتبة\n"
            f"• **رومات منع الـ XP:** {blacklist_disp}\n"
        ),
        color=0x2B2D31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Admin Core ✦ Pro Live Update")
    return embed

# ==============================================================================
# 🛠️ الواجهات المنبثقة (Modals) للتعديل الفوري
# ==============================================================================
class ResetConfigModal(discord.ui.Modal, title="⚙️ إعدادات الريسيت وروم الإعلانات"):
    reset_type_box = discord.ui.TextInput(
        label="نوع ونظام الريسيت (يومي / اسبوعي / شهري)",
        default="يومي",
        max_length=50,
        required=True
    )
    channel_id_box = discord.ui.TextInput(
        label="أيدي روم الإعلانات والتوب (Channel ID)",
        placeholder="أيدي الروم (اختياري)",
        max_length=30,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        raw_type = self.reset_type_box.value.strip()
        
        if "اسبوع" in raw_type.lower() or "أسبوع" in raw_type.lower():
            cfg["reset_type"] = "اسبوعي"
        elif "شهر" in raw_type.lower():
            cfg["reset_type"] = "شهري"
        else:
            cfg["reset_type"] = "يومي"

        chan_text = self.channel_id_box.value.strip()
        if chan_text.isdigit():
            cfg["announcement_channel"] = int(chan_text)

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send("🔄 **تم تحديث إعدادات الريسيت بنجاح!**", ephemeral=True)

class AllowedRoleModal(discord.ui.Modal, title="🛡️ تحديد رتبة التفاعل المخصصة"):
    role_id_box = discord.ui.TextInput(
        label="أيدي الرتبة (أو اكتب none للإلغاء)",
        placeholder="Role ID أو none",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        val = self.role_id_box.value.strip()
        
        if val.lower() == "none":
            cfg["allowed_role_id"] = None
        elif val.isdigit():
            r_obj = interaction.guild.get_role(int(val))
            if r_obj:
                cfg["allowed_role_id"] = r_obj.id

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send("🔒 **تم تحديث رتبة التفاعل بنجاح!**", ephemeral=True)

class BlacklistChannelModal(discord.ui.Modal, title="🚫 إدارة رومات منع احتساب الـ XP"):
    action_box = discord.ui.TextInput(
        label="اكتب (add) للإضافة أو (remove) للحذف",
        default="add",
        max_length=10,
        required=True
    )
    channel_id_box = discord.ui.TextInput(
        label="أيدي الروم المراد تعديلها (Channel ID)",
        placeholder="قم بلصق أيدي الروم هنا",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        action = self.action_box.value.strip().lower()
        chan_text = self.channel_id_box.value.strip()

        if not chan_text.isdigit():
            await interaction.response.send_message("❌ يرجى إدخال أيدي روم صحيح (أرقام فقط)!", ephemeral=True)
            return

        cid = int(chan_text)
        if action == "add":
            if cid not in cfg["blacklisted_channels"]:
                cfg["blacklisted_channels"].append(cid)
            await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
            await interaction.followup.send(f"🚫 **تمت إضافة الروم <#{cid}> لقائمة الحظر بنجاح!**", ephemeral=True)
        elif action == "remove":
            if cid in cfg["blacklisted_channels"]:
                cfg["blacklisted_channels"].remove(cid)
            await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
            await interaction.followup.send(f"✅ **تمت إزالة الروم <#{cid}> من قائمة الحظر بنجاح!**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ العملية غير صحيحة، اكتب add أو remove فقط!", ephemeral=True)

class AddRewardRoleModal(discord.ui.Modal, title="🎁 ربط رتبة مكافأة بمستوى معين"):
    lvl_box = discord.ui.TextInput(
        label="رقم المستوى المطلوب",
        placeholder="مثال: 5، 10، 20",
        max_length=5,
        required=True
    )
    role_box = discord.ui.TextInput(
        label="أيدي الرتبة (Role ID)",
        placeholder="أيدي الرتبة",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level_num = int(self.lvl_box.value.strip())
            role_id = int(self.role_box.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال أرقام صحيحة!", ephemeral=True)
            return

        role_obj = interaction.guild.get_role(role_id)
        if not role_obj:
            await interaction.response.send_message("❌ لم يتم العثور على رتبة بهذا الأيدي!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["role_rewards"][str(level_num)] = role_obj.id

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send(f"🎁 تم ربط المستوى **`{level_num}`** بالرتبة بنجاح!", ephemeral=True)

class SetMultiplierModal(discord.ui.Modal, title="⚡ تحديد مضاعف النقاط (Multiplier)"):
    mult_box = discord.ui.TextInput(
        label="قيمة المضاعف (مثال: 1, 2, 3)",
        default="1",
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.mult_box.value.strip())
            if val < 1 or val > 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال رقم بين 1 و 10!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["multiplier"] = val

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send(f"⚡ تم ضبط مضاعف النقاط ليصبح **`{val}x`** بنجاح!", ephemeral=True)

# ==============================================================================
# 🎛 لوحة التحكم الإدارية والأزرار
# ==============================================================================
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_v11")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["status"] = not cfg["status"]
        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="الريسيت والتوب", style=discord.ButtonStyle.primary, emoji="📅", row=0, custom_id="p_reset_v11")
    async def reset_config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ResetConfigModal())

    @discord.ui.button(label="استثناء الرومات (XP)", style=discord.ButtonStyle.secondary, emoji="🚫", row=0, custom_id="p_blacklist_v11")
    async def blacklist_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(BlacklistChannelModal())

    @discord.ui.button(label="إضافة رتبة مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=1, custom_id="p_reward_v11")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AddRewardRoleModal())

    @discord.ui.button(label="رتبة التفاعل", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1, custom_id="p_role_v11")
    async def allowed_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AllowedRoleModal())

    @discord.ui.button(label="ضبط المضاعف", style=discord.ButtonStyle.danger, emoji="⚡", row=1, custom_id="p_mult_v11")
    async def set_mult(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(SetMultiplierModal())

# ==============================================================================
# 🏆 لوحة شرف التوب مع أزرار التنقل
# ==============================================================================
class TopLeaderboardView(discord.ui.View):
    def __init__(self, interaction_guild, users_list, page=0):
        super().__init__(timeout=120)
        self.guild = interaction_guild
        self.users_list = users_list
        self.page = page
        self.per_page = 5
        self.max_pages = max(1, (len(users_list) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.max_pages - 1

    def create_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        chunk = self.users_list[start:end]

        lines = []
        for idx, (uid, udata) in enumerate(chunk, start=start + 1):
            m_obj = self.guild.get_member(uid)
            name_str = m_obj.mention if m_obj else f"عضو مغادر (`{uid}`)"
            badge = "👑" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
            lines.append(f"{badge} ╎ {name_str}\n ┗ المستوى: **`{udata['level']}`** | XP: **`{udata['xp']}`** | الرسائل: **`{udata['messages']}`**\n")

        embed = discord.Embed(
            title="📋 لوحة شرف تفاعل السيرفر (Top List)",
            description="أبرز الأعضاء تفاعلاً:\n\n" + ("\n".join(lines) if lines else "لا توجد بيانات مسجلة."),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_pages}")
        return embed

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="◀", custom_id="t_prev_v11")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="My Rank", style=discord.ButtonStyle.secondary, custom_id="t_myrank_v11")
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        found_idx = None
        for i, (u_id, _) in enumerate(self.users_list):
            if u_id == uid:
                found_idx = i + 1
                break
        
        if found_idx:
            self.page = (found_idx - 1) // self.per_page
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
            await interaction.followup.send(f"📍 رتبتك الحالية في التوب هي: `#{found_idx}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ليس لديك تفاعل مسجل بعد!", ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="▶", custom_id="t_next_v11")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

# ==============================================================================
# 🚀 محرك التشغيل البرمجي والمنطق الأساسي (Pro Level System)
# ==============================================================================
class AdvancedLevelSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def check_allowed_member(self, member, cfg):
        allowed_role_id = cfg.get("allowed_role_id")
        if not allowed_role_id:
            return True
        return any(role.id == allowed_role_id for role in member.roles)

    async def check_level_up(self, member, gid, udata):
        cfg = fetch_guild_config(gid)
        # الفكرة 2: معادلة صعود تصاعدية واقعية
        req_xp = (udata["level"] + 1) * 300 + (udata["level"] ** 1.2 * 120)

        if udata["xp"] >= req_xp:
            udata["level"] += 1
            udata["xp"] = 0

            role_rewards = cfg.get("role_rewards", {})
            assigned_role_id = role_rewards.get(str(udata["level"]))
            if assigned_role_id:
                r_target = member.guild.get_role(int(assigned_role_id))
                if r_target:
                    try:
                        await member.add_roles(r_target, reason=f"Level Engine: Reached level {udata['level']}")
                    except:
                        pass

            try:
                template = cfg.get("level_message", "✨ كفو يا {user}! صرت لفل {level}!")
                final_text = template.replace("{user}", member.mention).replace("{level}", f"`{udata['level']}`")

                embed = discord.Embed(
                    title="🎉 تـرقـيـة مـسـتـوى جـديـد!",
                    description=f"{final_text}\n\n• **المستوى الحالي:** `{udata['level']}` 🏆\n• **إجمالي الرسائل:** `{udata['messages']}` 📝",
                    color=0x00FF88,
                    timestamp=datetime.datetime.utcnow()
                )
                if cfg.get("level_image"):
                    embed.set_image(url=cfg["level_image"])

                embed.set_footer(text="Leveling Protocol ✦ Pro Engine")
                
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

        # الفكرة 1: فحص إذا كان الروم الحالي مستثنى من الـ XP
        if message.channel.id in cfg.get("blacklisted_channels", []):
            return

        if not cfg["status"] or not self.check_allowed_member(message.author, cfg):
            return

        now_ts = time.time()
        cd_dict = SERVER_DATABASE["cooldowns"]
        if gid not in cd_dict:
            cd_dict[gid] = {}
        
        if now_ts - cd_dict[gid].get(uid, 0) < 5:
            return
        cd_dict[gid][uid] = now_ts

        if random.random() < 0.15:
            return

        if gid not in SERVER_DATABASE["users"]:
            SERVER_DATABASE["users"][gid] = {}
        if uid not in SERVER_DATABASE["users"][gid]:
            SERVER_DATABASE["users"][gid][uid] = {
                "xp": 0, "level": 0, "messages": 0
            }

        udata = SERVER_DATABASE["users"][gid][uid]
        udata["xp"] += random.randint(5, 15) * cfg["multiplier"]
        udata["messages"] += 1

        await self.check_level_up(message.author, gid, udata)

    @app_commands.command(name="levels_panel", description="[الإدارة] لوحة التحكم الكاملة والمتقدمة لنظام الليفلات")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView(), ephemeral=False)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية الخاصة بك أو بأي عضو")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = interaction.guild.id
        udata = SERVER_DATABASE["users"].get(gid, {}).get(target.id, {"xp": 0, "level": 0, "messages": 0})
        
        req_xp = (udata["level"] + 1) * 300 + (udata["level"] ** 1.2 * 120)

        embed = discord.Embed(
            title=f"📊 بطاقة إحصائيات المستوى - {target.display_name}",
            description=(
                f"سجل التفاعل والنشاط الكامل للشات:\n\n"
                f"• **المستوى الحالي:** `{udata['level']}` 🏆\n"
                f"• **نقاط الخبرة (XP):** `{udata['xp']}` / `{int(req_xp)}` 🌟\n"
                f"• **الرسائل المرسلة:** `{udata['messages']}` رسالة 📝"
            ),
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Rank System ✦ بطاقة العضو النشط")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="top", description="عرض لوحة شرف المتصدرين لأعضاء السيرفر مع أزرار التنقل")
    async def top(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        users_data = SERVER_DATABASE["users"].get(gid, {})
        if not users_data:
            await interaction.response.send_message("❌ لا توجد أي بيانات تفاعل مسجلة في النظام حتى الآن!", ephemeral=True)
            return

        sorted_members = sorted(users_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
        view = TopLeaderboardView(interaction.guild, sorted_members, page=0)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=False)

    @app_commands.command(name="setlevel", description="[الإدارة] تعيين مستوى معين لعضو وفحص رتب المكافآت التلقائية")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        gid = interaction.guild.id
        cfg = fetch_guild_config(gid)

        if gid not in SERVER_DATABASE["users"]:
            SERVER_DATABASE["users"][gid] = {}
        if member.id not in SERVER_DATABASE["users"][gid]:
            SERVER_DATABASE["users"][gid][member.id] = {
                "xp": 0, "level": 0, "messages": 0
            }

        udata = SERVER_DATABASE["users"][gid][member.id]
        old_level = udata["level"]
        udata["level"] = max(0, level)
        udata["xp"] = 0

        # الفكرة 3: سحب رتب المكافآت القديمة أو إضافتها بذكاء
        role_rewards = cfg.get("role_rewards", {})
        
        # منح الرتبة الجديدة إن وجدت
        assigned_role_id = role_rewards.get(str(udata["level"]))
        role_mention_str = "لا توجد رتبة مكافأة لهذا المستوى"
        if assigned_role_id:
            r_target = interaction.guild.get_role(int(assigned_role_id))
            if r_target:
                try:
                    await member.add_roles(r_target, reason=f"Admin SetLevel: Set to level {udata['level']}")
                    role_mention_str = r_target.mention
                except:
                    role_mention_str = "فشل منح الرتبة (تأكد من الصلاحيات)"

        # سحب الرتب القديمة لو العضو ليفله نزل وبقى أقل
        for lvl_str, r_id in role_rewards.items():
            if int(lvl_str) > udata["level"]:
                old_r = interaction.guild.get_role(int(r_id))
                if old_r and old_r in member.roles:
                    try:
                        await member.remove_roles(old_r, reason="Level Revoke: Level decreased by admin")
                    except:
                        pass

        await interaction.response.send_message(
            f"🎯 **تم تحديث مستوى العضو بنجاح تام!**\n"
            f"• العضو: {member.mention}\n"
            f"• المستوى الجديد: **`{udata['level']}`** 🏆\n"
            f"• رتبة المكافأة المرتبطة: {role_mention_str}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(AdvancedLevelSystem(bot))
