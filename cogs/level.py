import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random
import time
import sqlite3

# ==============================================================================
# 🗄️ إعدادات وتجهيز قاعدة البيانات الدائمة (SQLite3 Database Core)
# ==============================================================================
DB_FILE = "level_system.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            guild_id INTEGER PRIMARY KEY,
            status INTEGER DEFAULT 1,
            multiplier INTEGER DEFAULT 1,
            announcement_channel INTEGER,
            level_message TEXT DEFAULT '✨ كفو يا {user}! لقد أثبتَّ حضورك وصعدت بنجاح إلى المستوى **`{level}`**!',
            level_image TEXT,
            reset_type TEXT DEFAULT 'يومي',
            reset_time TEXT DEFAULT '00:00',
            allowed_role_id INTEGER,
            custom_shortcut TEXT DEFAULT '/top'
        )
    """)
    
    # التأكد من وجود الأعمدة الجديدة لو القاعدة قديمة
    try:
        cursor.execute("ALTER TABLE server_settings ADD COLUMN reset_time TEXT DEFAULT '00:00'")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE server_settings ADD COLUMN custom_shortcut TEXT DEFAULT '/top'")
    except:
        pass
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_rewards (
            guild_id INTEGER,
            level INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, level)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blacklisted_channels (
            guild_id INTEGER,
            channel_id INTEGER,
            PRIMARY KEY (guild_id, channel_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            guild_id INTEGER,
            user_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            messages INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def get_db_settings(guild_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, multiplier, announcement_channel, level_message, level_image, reset_type, reset_time, allowed_role_id, custom_shortcut FROM server_settings WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("""
            INSERT INTO server_settings (guild_id, status, multiplier, level_message, reset_type, reset_time, custom_shortcut)
            VALUES (?, 1, 1, '✨ كفو يا {user}! لقد أثبتَّ حضورك وصعدت بنجاح إلى المستوى **`{level}`**!', 'يومي', '00:00', '/top')
        """, (guild_id,))
        conn.commit()
        cursor.execute("SELECT status, multiplier, announcement_channel, level_message, level_image, reset_type, reset_time, allowed_role_id, custom_shortcut FROM server_settings WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
    
    cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ?", (guild_id,))
    rewards_rows = cursor.fetchall()
    role_rewards = {str(lvl): r_id for lvl, r_id in rewards_rows}

    cursor.execute("SELECT channel_id FROM blacklisted_channels WHERE guild_id = ?", (guild_id,))
    blacklist_rows = cursor.fetchall()
    blacklisted_channels = [r[0] for r in blacklist_rows]

    conn.close()
    
    return {
        "status": bool(row[0]),
        "multiplier": row[1],
        "announcement_channel": row[2],
        "level_message": row[3],
        "level_image": row[4],
        "reset_type": row[5],
        "reset_time": row[6] or "00:00",
        "allowed_role_id": row[7],
        "custom_shortcut": row[8] or "/top",
        "role_rewards": role_rewards,
        "blacklisted_channels": blacklisted_channels
    }

def update_db_setting(guild_id: int, column: str, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE server_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()

def generate_panel_embed(guild: discord.Guild):
    cfg = get_db_settings(guild.id)
    status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "روم الإعلانات الافتراضي 💬"
    allowed_role_disp = f"<@&{cfg['allowed_role_id']}>" if cfg['allowed_role_id'] else "متاح للجميع 🌐"
    blacklist_disp = ", ".join([f"<#{cid}>" for cid in cfg["blacklisted_channels"]]) if cfg["blacklisted_channels"] else "لا توجد رومات مستثناة 📭"
    
    embed = discord.Embed(
        title="⚙ لـوحـة تـحـكـم نـظام الـمـسـتـويـات (Pro + Shortcuts)",
        description=(
            "مرحباً بك في لوحة الإدارة المركزية المحدثة لنظام التفاعل.\n"
            "جميع الخيارات والإعدادات محفوظة بداخل قاعدة البيانات:\n\n"
            f"• **حالة النظام العامة:** {status_str}\n"
            f"• **نوع ونظام الريسيت:** `{cfg['reset_type']}` 📅\n"
            f"• **وقت إرسال التوب المحدد:** `{cfg['reset_time']}` ⏰\n"
            f"• **الاختصار المخصص النشط:** `{cfg['custom_shortcut']}` ⚡\n"
            f"• **روم إعلانات الترقية والتوب:** {chan_disp}\n"
            f"• **رتبة التفاعل المخصصة:** {allowed_role_disp}\n"
            f"• **مضاعف النقاط النشط:** `{cfg['multiplier']}x` ⚡\n"
            f"• **رتب المكافآت المربوطة:** `{len(cfg['role_rewards'])}` رتبة\n"
            f"• **رومات منع الـ XP:** {blacklist_disp}\n"
        ),
        color=0x2B2D31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="Advanced Core ✦ Custom Shortcuts Update")
    return embed

# ==============================================================================
# 🛠️ الواجهات المنبثقة (Modals)
# ==============================================================================
class ResetConfigModal(discord.ui.Modal, title="⚙️ إعدادات الريسيت وجدولة التوب المتقدمة"):
    reset_type_box = discord.ui.TextInput(
        label="نوع نظام الريسيت (يومي / اسبوعي / شهري)",
        default="يومي",
        max_length=50,
        required=True
    )
    time_box = discord.ui.TextInput(
        label="وقت إرسال التوب (مثال: 15:00 أو 00:00)",
        default="00:00",
        max_length=10,
        required=True
    )
    channel_id_box = discord.ui.TextInput(
        label="أيدي روم إعلانات التوب والترقية (Channel ID)",
        placeholder="أيدي الروم هنا (اختياري)",
        max_length=30,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الصلاحية مخصصة لإدارة السيرفر فقط!", ephemeral=True)
            return

        raw_type = self.reset_type_box.value.strip()
        if "اسبوع" in raw_type.lower() or "أسبوع" in raw_type.lower():
            r_type = "اسبوعي"
        elif "شهر" in raw_type.lower():
            r_type = "شهري"
        else:
            r_type = "يومي"
        update_db_setting(interaction.guild.id, "reset_type", r_type)

        t_val = self.time_box.value.strip()
        update_db_setting(interaction.guild.id, "reset_time", t_val)

        chan_text = self.channel_id_box.value.strip()
        if chan_text.isdigit():
            update_db_setting(interaction.guild.id, "announcement_channel", int(chan_text))

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send("🔄 **تم تحديث إعدادات الريسيت، الوقت، والروم بنجاح تام!**", ephemeral=True)

class ShortcutConfigModal(discord.ui.Modal, title="⚡ إعدادات اختصارات الأوامر السريعة"):
    shortcut_box = discord.ui.TextInput(
        label="اكتب أمر الاختصار (مثال: /top أو /level)",
        default="/top",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذه الصلاحية مخصصة للإدارة فقط!", ephemeral=True)
            return

        sc_val = self.shortcut_box.value.strip()
        if not sc_val.startswith("/"):
            sc_val = "/" + sc_val

        update_db_setting(interaction.guild.id, "custom_shortcut", sc_val)
        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send(f"⚡ **تم تعيين الاختصار المخصص بنجاح ليصبح:** `{sc_val}`", ephemeral=True)

class AllowedRoleModal(discord.ui.Modal, title="🛡️ تحديد رتبة التفاعل المخصصة"):
    role_id_box = discord.ui.TextInput(
        label="أيدي الرتبة (أو اكتب none للإلغاء)",
        placeholder="Role ID أو none",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return

        val = self.role_id_box.value.strip()
        if val.lower() == "none":
            update_db_setting(interaction.guild.id, "allowed_role_id", None)
        elif val.isdigit():
            r_obj = interaction.guild.get_role(int(val))
            if r_obj:
                update_db_setting(interaction.guild.id, "allowed_role_id", r_obj.id)

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
        placeholder="أيدي الروم",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return

        action = self.action_box.value.strip().lower()
        chan_text = self.channel_id_box.value.strip()

        if not chan_text.isdigit():
            await interaction.response.send_message("❌ يرجى إدخال أيدي روم صحيح!", ephemeral=True)
            return

        cid = int(chan_text)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        if action == "add":
            cursor.execute("INSERT OR IGNORE INTO blacklisted_channels (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, cid))
            conn.commit()
            conn.close()
            await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
            await interaction.followup.send(f"🚫 **تمت إضافة الروم <#{cid}> لقائمة الحظر!**", ephemeral=True)
        elif action == "remove":
            cursor.execute("DELETE FROM blacklisted_channels WHERE guild_id = ? AND channel_id = ?", (interaction.guild.id, cid))
            conn.commit()
            conn.close()
            await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
            await interaction.followup.send(f"✅ **تمت إزالة الروم <#{cid}> من قائمة الحظر!**", ephemeral=True)
        else:
            conn.close()
            await interaction.response.send_message("❌ اكتب add للإضافة أو remove للحذف فقط!", ephemeral=True)

class CustomMessageModal(discord.ui.Modal, title="💬 تعديل رسالة الصعود المخصصة"):
    msg_box = discord.ui.TextInput(
        label="اكتب الرسالة (استخدم {user} و {level})",
        default="✨ كفو يا {user}! لقد أثبتَّ حضورك وصعدت بنجاح إلى المستوى **`{level}`**!",
        style=discord.TextStyle.paragraph,
        max_length=800,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return

        update_db_setting(interaction.guild.id, "level_message", self.msg_box.value)
        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send("✨ **تم تحديث رسالة الترقية بنجاح!**", ephemeral=True)

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
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return

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

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (interaction.guild.id, level_num, role_id))
        conn.commit()
        conn.close()

        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send(f"🎁 **تم ربط المستوى `{level_num}` بالرتبة بنجاح!**", ephemeral=True)

class SetMultiplierModal(discord.ui.Modal, title="⚡ تحديد مضاعف النقاط (Multiplier)"):
    mult_box = discord.ui.TextInput(
        label="قيمة المضاعف (مثال: 1, 2, 3)",
        default="1",
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return

        try:
            val = int(self.mult_box.value.strip())
            if val < 1 or val > 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال رقم بين 1 و 10!", ephemeral=True)
            return

        update_db_setting(interaction.guild.id, "multiplier", val)
        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView())
        await interaction.followup.send(f"⚡ **تم ضبط مضاعف النقاط ليصبح `{val}x`!**", ephemeral=True)

# ==============================================================================
# 🎛 لوحة التحكم الإدارية المتكاملة مع الأزرار كاملة
# ==============================================================================
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل/إيقاف", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_v15")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        cfg = get_db_settings(interaction.guild.id)
        new_status = 0 if cfg["status"] else 1
        update_db_setting(interaction.guild.id, "status", new_status)
        await interaction.response.edit_message(embed=generate_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="الريسيت وجدولة التوب", style=discord.ButtonStyle.primary, emoji="📅", row=0, custom_id="p_reset_v15")
    async def reset_config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ResetConfigModal())

    @discord.ui.button(label="تعيين الاختصارات", style=discord.ButtonStyle.secondary, emoji="⚡", row=0, custom_id="p_shortcut_v15")
    async def shortcut_config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(ShortcutConfigModal())

    @discord.ui.button(label="استثناء الرومات (XP)", style=discord.ButtonStyle.secondary, emoji="🚫", row=1, custom_id="p_blacklist_v15")
    async def blacklist_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(BlacklistChannelModal())

    @discord.ui.button(label="إضافة رتبة مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=1, custom_id="p_reward_v15")
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AddRewardRoleModal())

    @discord.ui.button(label="تعديل رسالة الصعود", style=discord.ButtonStyle.secondary, emoji="💬", row=1, custom_id="p_msg_v15")
    async def edit_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(CustomMessageModal())

    @discord.ui.button(label="رتبة التفاعل", style=discord.ButtonStyle.secondary, emoji="🛡️", row=2, custom_id="p_role_v15")
    async def allowed_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(AllowedRoleModal())

    @discord.ui.button(label="ضبط المضاعف", style=discord.ButtonStyle.danger, emoji="⚡", row=2, custom_id="p_mult_v15")
    async def set_mult(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ للأدرة فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(SetMultiplierModal())

    @discord.ui.button(label="إحصائيات السيرفر", style=discord.ButtonStyle.secondary, emoji="📊", row=2, custom_id="p_stats_v15")
    async def server_stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.guild.id
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(messages) FROM user_stats WHERE guild_id = ?", (gid,))
        row = cursor.fetchone()
        conn.close()

        total_users = row[0] or 0
        total_msgs = row[1] or 0
        cfg = get_db_settings(gid)
        
        embed = discord.Embed(
            title="📊 إحصائيات ونشاط نظام الليفلات",
            description=(
                f"• **عدد الأعضاء النشطين:** `{total_users}` عضو\n"
                f"• **إجمالي الرسائل المحتسبة:** `{total_msgs}` رسالة\n"
                f"• **مضاعف النقاط الحالي:** `{cfg['multiplier']}x`\n"
                f"• **الاختصار المخصص النشط:** `{cfg['custom_shortcut']}`\n"
                f"• **وقت الإرسال المحدد:** `{cfg['reset_time']}`"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        for idx, (uid, lvl, xp, msgs) in enumerate(chunk, start=start + 1):
            m_obj = self.guild.get_member(uid)
            name_str = m_obj.mention if m_obj else f"عضو مغادر (`{uid}`)"
            badge = "👑" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
            lines.append(f"{badge} ╎ {name_str}\n ┗ المستوى: **`{lvl}`** | XP: **`{xp}`** | الرسائل: **`{msgs}`**\n")

        embed = discord.Embed(
            title="📋 لوحة شرف تفاعل السيرفر (Top List)",
            description="أبرز الأعضاء تفاعلاً:\n\n" + ("\n".join(lines) if lines else "لا توجد بيانات مسجلة."),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_pages}")
        return embed

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="◀", custom_id="t_prev_v15")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="My Rank", style=discord.ButtonStyle.secondary, custom_id="t_myrank_v15")
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        found_idx = None
        for i, (u_id, _, _, _) in enumerate(self.users_list):
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

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="▶", custom_id="t_next_v15")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

# ==============================================================================
# 🚀 محرك التشغيل البرمجي والمنطق الأساسي
# ==============================================================================
class AdvancedLevelSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_top_announcement.start()

    def cog_unload(self):
        self.auto_top_announcement.cancel()

    @tasks.loop(minutes=1)
    async def auto_top_announcement(self):
        now_time = datetime.datetime.now().strftime("%H:%M")
        for guild in self.bot.guilds:
            gid = guild.id
            cfg = get_db_settings(gid)
            if not cfg["status"]:
                continue
            
            if cfg.get("reset_time") != now_time:
                continue

            chan_id = cfg.get("announcement_channel")
            target_channel = guild.get_channel(chan_id) if chan_id else guild.system_channel
            if not target_channel:
                continue

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, level, xp, messages FROM user_stats WHERE guild_id = ? ORDER BY level DESC, xp DESC", (gid,))
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                continue

            view = TopLeaderboardView(guild, rows, page=0)
            try:
                await target_channel.send("📢 **تقرير توب السيرفر التلقائي في الموعد المحدد:**", embed=view.create_embed(), view=view)
            except:
                pass

    @auto_top_announcement.before_loop
    async def before_auto_top(self):
        await self.bot.wait_until_ready()

    def check_allowed_member(self, member, cfg):
        allowed_role_id = cfg.get("allowed_role_id")
        if not allowed_role_id:
            return True
        return any(role.id == allowed_role_id for role in member.roles)

    async def check_level_up(self, member, gid, udata, cfg):
        lvl = udata["level"]
        xp = udata["xp"]
        req_xp = (lvl + 1) * 300 + (lvl ** 1.2 * 120)

        if xp >= req_xp:
            new_lvl = lvl + 1
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_stats SET level = ?, xp = 0 WHERE guild_id = ? AND user_id = ?", (new_lvl, gid, member.id))
            conn.commit()
            conn.close()

            role_rewards = cfg.get("role_rewards", {})
            assigned_role_id = role_rewards.get(str(new_lvl))
            if assigned_role_id:
                r_target = member.guild.get_role(int(assigned_role_id))
                if r_target:
                    try:
                        await member.add_roles(r_target, reason=f"Level Engine: Reached level {new_lvl}")
                    except:
                        pass

            try:
                template = cfg.get("level_message", "✨ كفو يا {user}! صرت لفل {level}!")
                final_text = template.replace("{user}", member.mention).replace("{level}", f"`{new_lvl}`")

                embed = discord.Embed(
                    title="🎉 تـرقـيـة مـسـتـوى جـديـد!",
                    description=f"{final_text}\n\n• **المستوى الحالي:** `{new_lvl}` 🏆\n• **إجمالي الرسائل:** `{udata['messages']}` 📝",
                    color=0x00FF88,
                    timestamp=datetime.datetime.utcnow()
                )
                if cfg.get("level_image"):
                    embed.set_image(url=cfg["level_image"])

                embed.set_footer(text="Level System ✦ Pro Engine")
                
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
        cfg = get_db_settings(gid)

        if message.channel.id in cfg.get("blacklisted_channels", []):
            return

        if not cfg["status"] or not self.check_allowed_member(message.author, cfg):
            return

        now_ts = time.time()
        if not hasattr(self, "cooldowns"):
            self.cooldowns = {}
        if gid not in self.cooldowns:
            self.cooldowns[gid] = {}
        
        if now_ts - self.cooldowns[gid].get(uid, 0) < 5:
            return
        self.cooldowns[gid][uid] = now_ts

        if random.random() < 0.15:
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, uid))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level, messages) VALUES (?, ?, ?, 0, 1)", (gid, uid, random.randint(5, 15) * cfg["multiplier"]))
            conn.commit()
            cursor.execute("SELECT xp, level, messages FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, uid))
            row = cursor.fetchone()
        else:
            new_xp = row[0] + (random.randint(5, 15) * cfg["multiplier"])
            new_msgs = row[2] + 1
            cursor.execute("UPDATE user_stats SET xp = ?, messages = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_msgs, gid, uid))
            conn.commit()

        udata = {"xp": row[0], "level": row[1], "messages": row[2] + 1}
        conn.close()

        await self.check_level_up(message.author, gid, udata, cfg)

    @app_commands.command(name="levels_panel", description="[الإدارة] لوحة التحكم الكاملة والمتقدمة لنظام الليفلات")
    @app_commands.checks.has_permissions(administrator=True)
    async def levels_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=generate_panel_embed(interaction.guild), view=AdminPanelView(), ephemeral=False)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك والمستوى الاحترافية الخاصة بك أو بأي عضو")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = interaction.guild.id
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, target.id))
        row = cursor.fetchone()
        conn.close()

        udata = {"xp": row[0], "level": row[1], "messages": row[2]} if row else {"xp": 0, "level": 0, "messages": 0}
        req_xp = (udata["level"] + 1) * 300 + (udata["level"] ** 1.2 * 120)

        embed = discord.Embed(
            title=f"📊 بطاقة إحصائيات المستوى - {target.display_name}",
            description=(
                f"سجل التفاعل والنشاط:\n\n"
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
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level, xp, messages FROM user_stats WHERE guild_id = ? ORDER BY level DESC, xp DESC", (gid,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("❌ لا توجد أي بيانات تفاعل مسجلة في النظام حتى الآن!", ephemeral=True)
            return

        view = TopLeaderboardView(interaction.guild, rows, page=0)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=False)

    @app_commands.command(name="setlevel", description="[الإدارة] تعيين مستوى معين لعضو وفحص رتب المكافآت التلقائية")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        gid = interaction.guild.id
        cfg = get_db_settings(gid)
        new_lvl = max(0, level)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO user_stats (guild_id, user_id, xp, level, messages) VALUES (?, ?, 0, ?, COALESCE((SELECT messages FROM user_stats WHERE guild_id = ? AND user_id = ?), 0))", (gid, member.id, new_lvl, gid, member.id))
        conn.commit()
        conn.close()

        role_rewards = cfg.get("role_rewards", {})
        assigned_role_id = role_rewards.get(str(new_lvl))
        role_mention_str = "لا توجد رتبة مكافأة لهذا المستوى"
        
        if assigned_role_id:
            r_target = interaction.guild.get_role(int(assigned_role_id))
            if r_target:
                try:
                    await member.add_roles(r_target, reason=f"Admin SetLevel: Set to level {new_lvl}")
                    role_mention_str = r_target.mention
                except:
                    role_mention_str = "فشل منح الرتبة (تأكد من الصلاحيات)"

        await interaction.response.send_message(
            f"🎯 **تم تحديث مستوى العضو بنجاح تام!**\n"
            f"• العضو: {member.mention}\n"
            f"• المستوى الجديد: **`{new_lvl}`** 🏆\n"
            f"• رتبة المكافأة المرتبطة: {role_mention_str}",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(AdvancedLevelSystem(bot))
