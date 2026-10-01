import discord
from discord import app_commands
from discord.ext import commands, tasks
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
            "allowed_role_id": None
        }
    return SERVER_DATABASE["settings"][guild_id]

# ==============================================================================
# 🛠️ الواجهات المنبثقة (Modals) المحسنة
# ==============================================================================
class ResetConfigModal(discord.ui.Modal, title="⚙️ إعدادات نظام الريسيت وتوب السيرفر"):
    reset_type_box = discord.ui.TextInput(
        label="نوع ونظام الريسيت (يومي / اسبوعي / شهري)",
        placeholder="اكتب: يومي، اسبوعي، أو شهري",
        default="يومي",
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
        raw_type = self.reset_type_box.value.strip()
        
        # تصحيح ذكي لنوع الريسيت بناءً على إدخال المستخدم
        if "اسبوع" in raw_type.lower() or "أسبوع" in raw_type.lower():
            cfg["reset_type"] = "اسبوعي"
        elif "شهر" in raw_type.lower():
            cfg["reset_type"] = "شهري"
        else:
            cfg["reset_type"] = "يومي"

        chan_text = self.channel_id_box.value.strip()
        if chan_text.isdigit():
            cfg["announcement_channel"] = int(chan_text)

        await interaction.response.send_message(
            f"🔄 **تم تحديث إعدادات نظام الريسيت بنجاح تام!**\n"
            f"• **نوع الريسيت المختار:** `{cfg['reset_type']}`\n"
            f"• **روم الإعلانات:** <#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "• **روم الإعلانات:** الروم الحالي الافتراضي",
            ephemeral=True
        )

class AllowedRoleModal(discord.ui.Modal, title="🛡️ تحديد رتبة التفاعل المخصصة"):
    role_id_box = discord.ui.TextInput(
        label="أيدي الرتبة (أو اكتب none للإلغاء)",
        placeholder="123456789012345678 أو none",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        val = self.role_id_box.value.strip()
        
        if val.lower() == "none":
            cfg["allowed_role_id"] = None
            await interaction.response.send_message("🌐 **تم إلغاء قيد الرتبة؛** أصبح نظام التفاعل متاحاً لجميع أعضاء السيرفر!", ephemeral=True)
        elif val.isdigit():
            r_obj = interaction.guild.get_role(int(val))
            if r_obj:
                cfg["allowed_role_id"] = r_obj.id
                await interaction.response.send_message(f"🔒 **تم قيد النظام بنجاح!** التفاعل مخصص الآن لأصحاب رتبة {r_obj.mention}.", ephemeral=True)
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
            await interaction.response.send_message("❌ لم يتم العثور على رتبة بهذا الأيدي في السيرفر!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["role_rewards"][str(level_num)] = role_obj.id
        await interaction.response.send_message(f"🎁 تم ربط المستوى **`{level_num}`** بالرتبة المميزة {role_obj.mention} بنجاح تام!", ephemeral=True)

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
            await interaction.response.send_message("❌ يرجى إدخال رقم صحيح بين 1 و 10!", ephemeral=True)
            return

        cfg = fetch_guild_config(interaction.guild.id)
        cfg["multiplier"] = val
        await interaction.response.send_message(f"⚡ تم ضبط مضاعف النقاط في السيرفر ليصبح **`{val}x`** بنجاح!", ephemeral=True)

# ==============================================================================
# 🎛 لوحة التحكم الإدارية والأزرار الاحترافية
# ==============================================================================
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="sys_tgl_v9")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        cfg = fetch_guild_config(interaction.guild.id)
        cfg["status"] = not cfg["status"]
        state_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        await interaction.response.send_message(f"⚙️ أصبحت حالة النظام الآن: **{state_str}**", ephemeral=True)

    @discord.ui.button(label="الريسيت والتوب", style=discord.ButtonStyle.primary, emoji="📅", row=0, custom_id="sys_reset_cfg_v9")
    async def reset_config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ResetConfigModal())

    @discord.ui.button(label="إضافة رتبة مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=0, custom_id="sys_reward_v9")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AddRewardRoleModal())

    @discord.ui.button(label="تحديد رتبة التفاعل", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1, custom_id="sys_allowed_role_v9")
    async def allowed_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AllowedRoleModal())

    @discord.ui.button(label="تعديل رسالة الصعود", style=discord.ButtonStyle.secondary, emoji="💬", row=1, custom_id="sys_msg_v9")
    async def edit_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(CustomMessageModal())

    @discord.ui.button(label="ضبط المضاعف", style=discord.ButtonStyle.danger, emoji="⚡", row=1, custom_id="sys_mult_v9")
    async def set_mult(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الأزرار مخصصة للإدارة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(SetMultiplierModal())

    @discord.ui.button(label="إحصائيات السيرفر", style=discord.ButtonStyle.secondary, emoji="📊", row=2, custom_id="sys_stats_v9")
    async def server_stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild.id
        users_data = SERVER_DATABASE["users"].get(gid, {})
        total_users = len(users_data)
        total_msgs = sum(u.get("messages", 0) for u in users_data.values())
        cfg = fetch_guild_config(gid)
        
        embed = discord.Embed(
            title="📊 إحصائيات ونشاط نظام الليفلات في السيرفر",
            description=(
                f"• **عدد الأعضاء النشطين:** `{total_users}` عضو\n"
                f"• **إجمالي الرسائل المحتسبة:** `{total_msgs}` رسالة\n"
                f"• **مضاعف النقاط الحالي:** `{cfg['multiplier']}x`\n"
                f"• **نوع الريسيت النشط:** `{cfg['reset_type']}`"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CardCustomModal(discord.ui.Modal, title="🎨 تخصيص بطاقة الرانك الخاصة بك"):
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
        if uid not in SERVER_DATABASE["custom_cards"]:
            SERVER_DATABASE["custom_cards"][uid] = {}
        
        SERVER_DATABASE["custom_cards"][uid]["color"] = self.color_box.value
        SERVER_DATABASE["custom_cards"][uid]["status"] = self.status_box.value
        await interaction.response.send_message("✨ تم حفظ تخصيص بطاقتك الشخصية بنجاح!", ephemeral=True)

class CardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تخصيص بطاقتي", style=discord.ButtonStyle.primary, emoji="🎨", custom_id="card_custom_v9")
    async def custom_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CardCustomModal())

# ==============================================================================
# 🏆 لوحة شرف التوب مع أزرار التنقل التفاعلية
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
            title="📋 Top global XP (الشات فقط)",
            description="أبرز أعضاء السيرفر تفاعلاً في الشات:\n\n" + ("\n".join(lines) if lines else "لا توجد بيانات مسجلة."),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_pages}")
        return embed

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="◀", custom_id="top_prev_v9")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="My Rank", style=discord.ButtonStyle.secondary, custom_id="top_my_rank_v9")
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
            await interaction.followup.send(f"📍 رتبتك الحالية في السيرفر هي: `#{found_idx}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ليس لديك أي تفاعل مسجل في لوحة الشرف حتى الآن!", ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="▶", custom_id="top_next_v9")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

# ==============================================================================
# 🚀 محرك التشغيل البرمجي المتكامل والنظام الأساسي
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

                embed.set_footer(text="Leveling Protocol ✦ نظام الارتقاء التلقائي")
                
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

        # نظام الاختصارات السريعة (Prefix Shortcuts)
        content = message.content.strip()
        if content.lower().startswith("l "):
            target_member = message.mentions[0] if message.mentions else message.author
            await self.send_level_card(message, target_member)
            return
        elif content.lower() == "top":
            await self.send_top_board(message)
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
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0
            }

        udata = SERVER_DATABASE["users"][gid][uid]
        udata["xp"] += random.randint(5, 15) * cfg["multiplier"]
        udata["messages"] += 1

        await self.check_level_up(message.author, gid, udata)

    async def send_level_card(self, message_or_interaction, target_member):
        gid = message_or_interaction.guild.id
        udata = SERVER_DATABASE["users"].get(gid, {}).get(target_member.id, {"xp": 0, "level": 0, "messages": 0, "voice_minutes": 0})
        
        card_conf = SERVER_DATABASE["custom_cards"].get(target_member.id, {})
        try:
            color_val = int(card_conf.get("color", "#5865F2").replace("#", ""), 16)
        except:
            color_val = 0x5865F2

        req_xp = (udata["level"] + 1) * 250 + (udata["level"] * 110)

        embed = discord.Embed(
            title=f"📊 بطاقة إحصائيات المستوى - {target_member.display_name}",
            description=(
                f"سجل التفاعل والنشاط الكامل للشات:\n\n"
                f"• **المستوى الحالي:** `{udata['level']}` 🏆\n"
                f"• **نقاط الخبرة (XP):** `{udata['xp']}` / `{req_xp}` 🌟\n"
                f"• **الرسائل المرسلة:** `{udata['messages']}` رسالة 📝\n"
                f"• **النبذة الشخصية:** `{card_conf.get('status', 'لا توجد نبذة مضافة')}`"
            ),
            color=color_val,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.set_footer(text="Rank System ✦ بطاقة العضو النشط")

        if isinstance(message_or_interaction, discord.Interaction):
            await message_or_interaction.response.send_message(embed=embed, view=CardView(), ephemeral=False)
        else:
            await message_or_interaction.channel.send(embed=embed, view=CardView())

    async def send_top_board(self, message):
        gid = message.guild.id
        users_data = SERVER_DATABASE["users"].get(gid, {})
        if not users_data:
            await message.channel.send("❌ لا توجد أي بيانات تفاعل مسجلة في النظام حتى الآن!")
            return

        sorted_members = sorted(users_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
        view = TopLeaderboardView(message.guild, sorted_members, page=0)
        await message.channel.send(embed=view.create_embed(), view=view)

    @app_commands.command(name="levels_panel", description="[الإدارة] لوحة التحكم الكاملة والمتقدمة لإدارة نظام الليفلات")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction):
        cfg = fetch_guild_config(interaction.guild.id)
        status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
        chan_disp = f"<#{cfg['announcement_channel']}>" if cfg["announcement_channel"] else "روم الإعلانات الافتراضي 💬"
        allowed_role_disp = f"<@&{cfg['allowed_role_id']}>" if cfg["allowed_role_id"] else "متاح للجميع 🌐"

        embed = discord.Embed(
            title="⚙️ لـوحـة تـحـكـم نـظام الـمـسـتـويـات",
            description=(
                "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل والنشاط.\n"
                "يمكنك التحكم بكافة الخصائص والإعدادات بسلاسة عبر الأزرار أدناه:\n\n"
                f"• **حالة النظام العامة:** {status_str}\n"
                f"• **نوع الريسيت المختار:** `{cfg['reset_type']}` 📅\n"
                f"• **روم إعلانات الترقية:** {chan_disp}\n"
                f"• **رتبة التفاعل المخصصة:** {allowed_role_disp}\n"
                f"• **مضاعف النقاط النشط:** `{cfg['multiplier']}x` ⚡\n"
                f"• **رتب المكافآت المربوطة:** `{len(cfg['role_rewards'])}` رتبة\n"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Admin Core ✦ Ultimate Management Panel")
        await interaction.response.send_message(embed=embed, view=AdminPanelView(), ephemeral=False)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية الخاصة بك أو بأي عضو")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await self.send_level_card(interaction, target)

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

    @app_commands.command(name="setxp", description="[الإدارة] تعيين أو تعديل نقاط الخبرة (XP) لعضو معين في السيرفر")
    @app_commands.checks.has_permissions(administrator=True)
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        gid = interaction.guild.id
        if gid not in SERVER_DATABASE["users"]:
            SERVER_DATABASE["users"][gid] = {}
        if member.id not in SERVER_DATABASE["users"][gid]:
            SERVER_DATABASE["users"][gid][member.id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0
            }

        udata = SERVER_DATABASE["users"][gid][member.id]
        udata["xp"] = max(0, amount)

        await interaction.response.send_message(f"⚡ **تم تحديث نقاط XP بنجاح!**\n• العضو: {member.mention}\n• نقاط XP الجديدة: **`{udata['xp']}`**", ephemeral=True)
        await self.check_level_up(member, gid, udata)

    @app_commands.command(name="setlevel", description="[الإدارة] تعيين مستوى معين لعضو وفحص رتب المكافآت التلقائية")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        gid = interaction.guild.id
        cfg = fetch_guild_config(gid)

        if gid not in SERVER_DATABASE["users"]:
            SERVER_DATABASE["users"][gid] = {}
        if member.id not in SERVER_DATABASE["users"][gid]:
            SERVER_DATABASE["users"][gid][member.id] = {
                "xp": 0, "level": 0, "messages": 0, "voice_minutes": 0
            }

        udata = SERVER_DATABASE["users"][gid][member.id]
        udata["level"] = max(0, level)
        udata["xp"] = 0  # تثبيت الـ XP عند بداية المستوى

        role_rewards = cfg.get("role_rewards", {})
        assigned_role_id = role_rewards.get(str(udata["level"]))
        role_mention_str = "لا توجد رتبة مكافأة لهذا المستوى"
        
        if assigned_role_id:
            r_target = interaction.guild.get_role(int(assigned_role_id))
            if r_target:
                try:
                    await member.add_roles(r_target, reason=f"Admin SetLevel: Set to level {udata['level']}")
                    role_mention_str = r_target.mention
                except:
                    role_mention_str = "فشل منح الرتبة (تأكد من صلاحيات البوت وتحريك رتبته للأعلى)"

        await interaction.response.send_message(
            f"🎯 **تم تحديث مستوى العضو بنجاح تام!**\n"
            f"• العضو: {member.mention}\n"
            f"• المستوى الجديد: **`{udata['level']}`** 🏆\n"
            f"• رتبة المكافأة المرتبطة: {role_mention_str}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(AdvancedLevelSystem(bot))
