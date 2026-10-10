import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random
import time
import sqlite3
import re
import os

LEVELS_DB_FILE = "ultimate_levels_database.db"

def init_levels_db():
    conn = sqlite3.connect(LEVELS_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            guild_id INTEGER PRIMARY KEY,
            status INTEGER DEFAULT 1,
            announcement_channel INTEGER,
            msg_type TEXT DEFAULT 'embed',
            level_message TEXT DEFAULT 'تهانينا يا {user}! لقد صعدت إلى مستوى جديد، استمر في تفاعلك الرائع!',
            level_embed_title TEXT DEFAULT '♦ ترقية إلى المستوى [{level}]',
            level_image TEXT,
            dm_notifications INTEGER DEFAULT 0,
            text_xp_enabled INTEGER DEFAULT 1,
            min_text_xp INTEGER DEFAULT 5,
            max_text_xp INTEGER DEFAULT 45,
            text_cooldown INTEGER DEFAULT 60,
            voice_xp_enabled INTEGER DEFAULT 1,
            min_voice_xp INTEGER DEFAULT 2,
            max_voice_xp INTEGER DEFAULT 5,
            voice_cooldown INTEGER DEFAULT 4,
            reaction_xp_enabled INTEGER DEFAULT 0,
            min_reaction_xp INTEGER DEFAULT 2,
            max_reaction_xp INTEGER DEFAULT 5,
            event_multiplier REAL DEFAULT 1.0,
            event_type TEXT DEFAULT 'both',
            event_end_timestamp INTEGER DEFAULT 0,
            event_target_roles TEXT DEFAULT 'all'
        )
    """)
    
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_roles (guild_id INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, role_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_voice_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS role_multipliers (guild_id INTEGER, role_id INTEGER, multiplier REAL, PRIMARY KEY (guild_id, role_id))")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_rewards (
            guild_id INTEGER,
            level INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, level, role_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            guild_id INTEGER,
            user_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            messages INTEGER DEFAULT 0,
            voice_minutes INTEGER DEFAULT 0,
            voice_xp INTEGER DEFAULT 0,
            day_text_xp INTEGER DEFAULT 0,
            day_voice_xp INTEGER DEFAULT 0,
            week_text_xp INTEGER DEFAULT 0,
            week_voice_xp INTEGER DEFAULT 0,
            month_text_xp INTEGER DEFAULT 0,
            month_voice_xp INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    
    conn.commit()
    conn.close()

init_levels_db()

def parse_time_duration(time_str: str) -> int:
    """تحويل ترميز الوقت (1m, 2h, 1d) إلى ثوانٍ"""
    match = re.match(r"^(\d+)\s*([mhdMHD])$", time_str.strip())
    if not match:
        return 0
    val, unit = int(match.group(1)), match.group(2).lower()
    if unit == 'm':
        return val * 60
    elif unit == 'h':
        return val * 3600
    elif unit == 'd':
        return val * 86400
    return 0

def get_levels_settings(guild_id: int):
    conn = sqlite3.connect(LEVELS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, announcement_channel, msg_type, level_message, level_embed_title, level_image, dm_notifications,
               text_xp_enabled, min_text_xp, max_text_xp, text_cooldown,
               voice_xp_enabled, min_voice_xp, max_voice_xp, voice_cooldown,
               reaction_xp_enabled, min_reaction_xp, max_reaction_xp,
               event_multiplier, event_type, event_end_timestamp, event_target_roles
        FROM server_settings WHERE guild_id = ?
    """, (guild_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO server_settings (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        cursor.execute("""
            SELECT status, announcement_channel, msg_type, level_message, level_embed_title, level_image, dm_notifications,
                   text_xp_enabled, min_text_xp, max_text_xp, text_cooldown,
                   voice_xp_enabled, min_voice_xp, max_voice_xp, voice_cooldown,
                   reaction_xp_enabled, min_reaction_xp, max_reaction_xp,
                   event_multiplier, event_type, event_end_timestamp, event_target_roles
            FROM server_settings WHERE guild_id = ?
        """, (guild_id,))
        row = cursor.fetchone()

    cursor.execute("SELECT level, role_id FROM role_rewards WHERE guild_id = ?", (guild_id,))
    role_rewards = {}
    for lvl, r_id in cursor.fetchall():
        role_rewards.setdefault(str(lvl), []).append(r_id)

    cursor.execute("SELECT role_id FROM ignored_roles WHERE guild_id = ?", (guild_id,))
    ignored_roles = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT channel_id FROM ignored_channels WHERE guild_id = ?", (guild_id,))
    ignored_channels = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT channel_id FROM ignored_voice_channels WHERE guild_id = ?", (guild_id,))
    ignored_voice = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT role_id, multiplier FROM role_multipliers WHERE guild_id = ?", (guild_id,))
    role_mults = dict(cursor.fetchall())

    conn.close()
    
    return {
        "status": bool(row[0]),
        "announcement_channel": row[1],
        "msg_type": row[2],
        "level_message": row[3],
        "level_embed_title": row[4],
        "level_image": row[5],
        "dm_notifications": bool(row[6]),
        "text_xp_enabled": bool(row[7]),
        "min_text_xp": row[8],
        "max_text_xp": row[9],
        "text_cooldown": row[10],
        "voice_xp_enabled": bool(row[11]),
        "min_voice_xp": row[12],
        "max_voice_xp": row[13],
        "voice_cooldown": row[14],
        "reaction_xp_enabled": bool(row[15]),
        "min_reaction_xp": row[16],
        "max_reaction_xp": row[17],
        "event_multiplier": row[18],
        "event_type": row[19],
        "event_end_timestamp": row[20],
        "event_target_roles": row[21] if len(row) > 21 else "all",
        "role_rewards": role_rewards,
        "ignored_roles": ignored_roles,
        "ignored_channels": ignored_channels,
        "ignored_voice": ignored_voice,
        "role_multipliers": role_mults
    }

def update_levels_setting(guild_id: int, column: str, value):
    conn = sqlite3.connect(LEVELS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE server_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()

def create_progress_bar(current_xp, req_xp, length=10):
    percent = min(1.0, max(0.0, current_xp / req_xp)) if req_xp > 0 else 0
    filled = int(length * percent)
    empty = length - filled
    return "🟩" * filled + "⬛" * empty

def generate_levels_panel_embed(guild: discord.Guild):
    cfg = get_levels_settings(guild.id)
    status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "القناة الافتراضية 💬"
    
    if cfg["event_multiplier"] > 1.0 and cfg["event_end_timestamp"] > time.time():
        target_str = "السيرفر بالكامل" if cfg["event_target_roles"] == "all" else "رتب محددة 🎯"
        event_str = f"`x{cfg['event_multiplier']}` ({cfg['event_type']}) | المدى: {target_str}"
    else:
        event_str = "لا يوجد حدث نشط ⚪"
    
    embed = discord.Embed(
        title="⚙️ [ ] : لوحة تحكم نظام المستويات الشاملة",
        description=(
            "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل والمستويات.\n\n"
            f"• **حالة النظام العامة:** {status_str}\n"
            f"• **قناة إعلانات الترقية:** {chan_disp}\n"
            f"• **نوع الإشعار:** `{cfg['msg_type'].upper()}` | **إشعارات الخاصة (DM):** `{'مفعل ✅' if cfg['dm_notifications'] else 'معطل ❌'}`\n"
            f"• **نظام مضاعف الـ XP:** {event_str}\n\n"
            f"⚙️ **نطاقات وتفعيل الـ XP:**\n"
            f"┗ **النص:** `{'مفعل ✅' if cfg['text_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_text_xp']}-{cfg['max_text_xp']}` XP\n"
            f"┗ **الصوت:** `{'مفعل ✅' if cfg['voice_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_voice_xp']}-{cfg['max_voice_xp']}` XP\n"
            f"┗ **الرياكشنت:** `{'مفعل ✅' if cfg['reaction_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_reaction_xp']}-{cfg['max_reaction_xp']}` XP\n\n"
            f"🚫 **الاستثناءات والمكافآت:**\n"
            f"┗ **رولات مستبعدة:** `{len(cfg['ignored_roles'])}` | **قنوات مستبعدة:** `{len(cfg['ignored_channels'])}`\n"
            f"┗ **رولات المكافآت المربوطة (لا محدود):** `{sum(len(v) for v in cfg['role_rewards'].values())}` رتبة\n"
        ),
        color=0x2B2D31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="نظام إدارة المستويات والتفاعل الفائق")
    return embed


# ==============================================================================
# 🛠️ الواجهات المنبثقة (Modals & Multiplier Engine)
# ==============================================================================
class AdvancedEventConfigModal(discord.ui.Modal, title="🔥 إعداد مضاعف الـ XP"):
    mult_box = discord.ui.TextInput(label="قيمة المضاعف (مثال: 1.5, 2, 3)", default="2", max_length=5)
    time_box = discord.ui.TextInput(label="مدة المضاعف (مثال: 30m / 2h / 1d)", default="1h", placeholder="30m, 2h, 1d", max_length=10)
    type_box = discord.ui.TextInput(label="النطاق (text / voice / both)", default="both", max_length=10)

    def __init__(self, target_roles="all"):
        super().__init__()
        self.target_roles = target_roles

    async def on_submit(self, interaction: discord.Interaction):
        try:
            m_val = float(self.mult_box.value)
            secs = parse_time_duration(self.time_box.value)
            if secs <= 0:
                embed_err = discord.Embed(title="❌ صيغة وقت غير صحيحة", description="يرجى كتابة المدة بأسلوب صحيح، مثل:\n`30m` للدقائق، `2h` للساعات، `1d` للأيام.", color=0xFF3333)
                await interaction.response.send_message(embed=embed_err, ephemeral=True)
                return

            t_val = self.type_box.value.strip().lower()
            if t_val not in ["text", "voice", "both"]:
                t_val = "both"

            end_ts = int(time.time()) + secs
            update_levels_setting(interaction.guild.id, "event_multiplier", m_val)
            update_levels_setting(interaction.guild.id, "event_type", t_val)
            update_levels_setting(interaction.guild.id, "event_end_timestamp", end_ts)
            update_levels_setting(interaction.guild.id, "event_target_roles", self.target_roles)

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            
            target_desc = "على السيرفر بالكامل" if self.target_roles == "all" else f"على الرتب المحددة (`{self.target_roles}`)"
            embed_ok = discord.Embed(title="🔥 تم تفعيل نظام المضاعف", description=f"تم إطلاق مضاعف الـ XP بقيمة `x{m_val}` لمدة `{self.time_box.value}` {target_desc} بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة لـ قيمة المضاعف.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class SpecificRolesInputModal(discord.ui.Modal, title="🎯 تحديد الرتب المشمولة بالمضاعف"):
    roles_box = discord.ui.TextInput(
        label="أيديهات الرتب (Role IDs) - كل أيدي في سطر",
        style=discord.TextStyle.paragraph,
        placeholder="1234567890\n0987654321",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_lines = self.roles_box.value.strip().split("\n")
        valid_roles = []
        for line in raw_lines:
            cleaned = line.strip()
            if cleaned.isdigit() and interaction.guild.get_role(int(cleaned)):
                valid_roles.append(cleaned)

        if not valid_roles:
            embed_err = discord.Embed(title="❌ خطأ في أيديهات الرتب", description="لم نتمكن من العثور على أي رتبة بهذه الأيديهات في السيرفر.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        target_roles_str = ",".join(valid_roles)
        await interaction.response.send_modal(AdvancedEventConfigModal(target_roles=target_roles_str))


class MultiplierScopeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="السيرفر بالكامل 🌐", style=discord.ButtonStyle.primary, custom_id="mult_scope_all_v7")
    async def scope_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdvancedEventConfigModal(target_roles="all"))

    @discord.ui.button(label="رتب معينة 🎯", style=discord.ButtonStyle.secondary, custom_id="mult_scope_roles_v7")
    async def scope_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SpecificRolesInputModal())


class LevelsXpModal(discord.ui.Modal, title="⚙️ ضبط نطاقات وكولدلاون الـ XP"):
    min_text = discord.ui.TextInput(label="أدنى XP نصي", default="5", max_length=5)
    max_text = discord.ui.TextInput(label="أقصى XP نصي", default="45", max_length=5)
    cd_text = discord.ui.TextInput(label="كولدلاون الرسائل (بالثواني)", default="60", max_length=5)
    min_voice = discord.ui.TextInput(label="أدنى XP صوتي", default="2", max_length=5)
    max_voice = discord.ui.TextInput(label="أقصى XP صوتي", default="5", max_length=5)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            update_levels_setting(interaction.guild.id, "min_text_xp", int(self.min_text.value))
            update_levels_setting(interaction.guild.id, "max_text_xp", int(self.max_text.value))
            update_levels_setting(interaction.guild.id, "text_cooldown", int(self.cd_text.value))
            update_levels_setting(interaction.guild.id, "min_voice_xp", int(self.min_voice.value))
            update_levels_setting(interaction.guild.id, "max_voice_xp", int(self.max_voice.value))
            
            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="✅ تم التحديث", description="تم حفظ إعدادات ونطاقات الـ XP بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class ReactionXpModal(discord.ui.Modal, title="⚙️ ضبط XP الريأكشنات"):
    min_react = discord.ui.TextInput(label="أدنى XP للريأكشن", default="2", max_length=5)
    max_react = discord.ui.TextInput(label="أقصى XP للريأكشن", default="5", max_length=5)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            update_levels_setting(interaction.guild.id, "min_reaction_xp", int(self.min_react.value))
            update_levels_setting(interaction.guild.id, "max_reaction_xp", int(self.max_react.value))
            
            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="✅ تم التحديث", description="تم حفظ نطاق XP الريأكشنات بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class LevelsMessageModal(discord.ui.Modal, title="💬 رسائل وشكل الترقية الاحترافي"):
    title_box = discord.ui.TextInput(label="عنوان الـ Embed (استخدم {level})", default="♦ ترقية إلى المستوى [{level}]", max_length=256, required=True)
    msg_box = discord.ui.TextInput(label="محتوى الرسالة (استخدم {user} و {level})", default="تهانينا يا {user}! لقد صعدت إلى مستوى جديد، استمر في تفاعلك الرائع!", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    img_box = discord.ui.TextInput(label="رابط صورة / بانر الترقية (اختياري)", placeholder="https://...", max_length=300, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        update_levels_setting(interaction.guild.id, "level_embed_title", self.title_box.value)
        update_levels_setting(interaction.guild.id, "level_message", self.msg_box.value)
        img_val = self.img_box.value.strip() or None
        update_levels_setting(interaction.guild.id, "level_image", img_val)

        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        embed_ok = discord.Embed(title="✅ تم الحفظ", description="تم تحديث رسالة وشكل ترقية المستوى بنجاح.", color=0x00FF88)
        await interaction.followup.send(embed=embed_ok, ephemeral=True)

class LevelsRewardModal(discord.ui.Modal, title="🎁 إضافة رول مكافأة لا محدود"):
    lvl_box = discord.ui.TextInput(label="المستوى المطلوب", placeholder="مثال: 5", max_length=5)
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", placeholder="Role ID", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lvl = int(self.lvl_box.value)
            rid = int(self.role_box.value)
            role_obj = interaction.guild.get_role(rid)
            if not role_obj:
                raise ValueError

            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (interaction.guild.id, lvl, rid))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="✅ تم إضافة المكافأة", description=f"تم ربط المستوى `{lvl}` بالرتبة {role_obj.mention} بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="تأكد من صحة أيدي الرتبة ورقم المستوى.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class IgnoreRoleModal(discord.ui.Modal, title="🚫 استبعاد رتبة من كسب الـ XP"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", placeholder="Role ID", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rid = int(self.role_box.value)
            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO ignored_roles (guild_id, role_id) VALUES (?, ?)", (interaction.guild.id, rid))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="✅ تم الاستبعاد", description=f"تم حظر الرتبة <@&{rid}> من كسب الـ XP بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أيدي رتبة صحيح.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class IgnoreChannelModal(discord.ui.Modal, title="🚫 استبعاد روم من كسب الـ XP"):
    chan_box = discord.ui.TextInput(label="أيدي الروم (Channel ID)", placeholder="Channel ID", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cid = int(self.chan_box.value)
            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO ignored_channels (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, cid))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="✅ تم الاستبعاد", description=f"تم حظر الروم <#{cid}> من كسب الـ XP بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أيدي روم صحيح.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)


# ==============================================================================
# 🎛️ القوائم والـ Views
# ==============================================================================
class TopDurationSelect(discord.ui.Select):
    def __init__(self, current_duration="global"):
        options = [
            discord.SelectOption(label="Global", value="global", description="عرض المتصدرين على مستوى السيرفر بالكامل", emoji="🌐", default=(current_duration == "global")),
            discord.SelectOption(label="Day", value="day", description="عرض متصدري اليوم فقط", emoji="📅", default=(current_duration == "day")),
            discord.SelectOption(label="Week", value="week", description="عرض متصدري الأسبوع فقط", emoji="🗓️", default=(current_duration == "week")),
            discord.SelectOption(label="Month", value="month", description="عرض متصدري الشهر فقط", emoji="📆", default=(current_duration == "month")),
        ]
        super().__init__(placeholder="Select the duration", min_values=1, max_values=1, options=options, custom_id="top_duration_select_persistent_v7")

    async def callback(self, interaction: discord.Interaction):
        view: TopLeaderboardView = self.view
        view.duration = self.values[0]
        view.page = 0
        view.update_select()
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class TopLeaderboardView(discord.ui.View):
    def __init__(self, interaction_guild=None, duration="global", page=0):
        super().__init__(timeout=None)
        self.guild = interaction_guild
        self.duration = duration
        self.page = page
        self.per_page = 5
        self.update_select()

    def update_select(self):
        self.clear_items()
        self.add_item(TopDurationSelect(self.duration))
        self.add_item(self.prev_btn)
        self.add_item(self.my_rank_btn)
        self.add_item(self.next_btn)

    def fetch_data(self):
        if not self.guild:
            return []
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        
        if self.duration == "day":
            cursor.execute("SELECT user_id, day_text_xp, day_voice_xp, level FROM user_stats WHERE guild_id = ? ORDER BY (day_text_xp + day_voice_xp) DESC", (self.guild.id,))
        elif self.duration == "week":
            cursor.execute("SELECT user_id, week_text_xp, week_voice_xp, level FROM user_stats WHERE guild_id = ? ORDER BY (week_text_xp + week_voice_xp) DESC", (self.guild.id,))
        elif self.duration == "month":
            cursor.execute("SELECT user_id, month_text_xp, month_voice_xp, level FROM user_stats WHERE guild_id = ? ORDER BY (month_text_xp + month_voice_xp) DESC", (self.guild.id,))
        else:
            cursor.execute("SELECT user_id, xp, voice_xp, level FROM user_stats WHERE guild_id = ? ORDER BY (xp + voice_xp) DESC", (self.guild.id,))
        
        rows = cursor.fetchall()
        conn.close()
        return rows

    def create_embed(self):
        if not self.guild:
            return discord.Embed(title="Top Leaderboard", description="Panel initialized.", color=0x2B2D31)
        
        rows = self.fetch_data()
        cfg = get_levels_settings(self.guild.id)
        
        text_list = sorted(rows, key=lambda x: x[1], reverse=True)[:5]
        voice_list = sorted(rows, key=lambda x: x[2], reverse=True)[:5]

        text_lines = []
        for idx, (uid, t_xp, v_xp, lvl) in enumerate(text_list, start=1):
            if t_xp <= 0:
                continue
            m_obj = self.guild.get_member(uid)
            name_str = m_obj.mention if m_obj else f"عضو (`{uid}`)"
            
            reward_role_str = ""
            rewards = cfg["role_rewards"].get(str(lvl), [])
            if rewards:
                r_obj = self.guild.get_role(rewards[0])
                if r_obj:
                    reward_role_str = f" | Reward: {r_obj.mention}"

            text_lines.append(f"#{idx}• {name_str}: {t_xp:,} XP{reward_role_str}")

        voice_lines = []
        for idx, (uid, t_xp, v_xp, lvl) in enumerate(voice_list, start=1):
            if v_xp <= 0:
                continue
            m_obj = self.guild.get_member(uid)
            name_str = m_obj.mention if m_obj else f"عضو (`{uid}`)"
            voice_lines.append(f"#{idx}• {name_str}: {v_xp:,} XP")

        title_duration = "global" if self.duration == "global" else f"{self.duration}"
        embed = discord.Embed(
            title=f"📋 Top {title_duration} XP",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )

        embed.description = "📋 **Top 5 text 💬**\n" + ("\n".join(text_lines) if text_lines else "لا توجد بيانات تفاعل نصي.")
        embed.description += "\n\n📋 **Top 5 voice 🎙️**\n" + ("\n".join(voice_lines) if voice_lines else "لا توجد بيانات تفاعل صوتي.")

        max_pages = max(1, (len(rows) + self.per_page - 1) // self.per_page)
        embed.set_footer(text=f"Page {self.page + 1} of {max_pages} ✦ نظام المستويات")
        return embed

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="◀", custom_id="t_prev_persistent_v7")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="My Rank", style=discord.ButtonStyle.secondary, custom_id="t_myrank_persistent_v7")
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        rows = self.fetch_data()
        uid = interaction.user.id
        found_idx = None
        for i, row in enumerate(rows, start=1):
            if row[0] == uid:
                found_idx = i
                break
        
        if found_idx:
            embed_rank = discord.Embed(title="📍 ترتيبك الحالي", description=f"ترتيبك الحالي في قائمة **{self.duration.capitalize()}** هو: `#{found_idx}`", color=0x00FF88)
            await interaction.response.send_message(embed=embed_rank, ephemeral=True)
        else:
            embed_err = discord.Embed(title="❌ خطأ", description="ليس لديك تفاعل مسجل في هذه القائمة بعد.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="▶", custom_id="t_next_persistent_v7")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        self.page += 1
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class LevelsAdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل / إيقاف النظام", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_levels_persistent_v7")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_status = 0 if cfg["status"] else 1
        update_levels_setting(interaction.guild.id, "status", new_status)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="نوع الإشعار (Embed/Text)", style=discord.ButtonStyle.secondary, emoji="🔄", row=0, custom_id="p_tgl_msgtype_v7")
    async def toggle_msg_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_type = "text" if cfg["msg_type"] == "embed" else "embed"
        update_levels_setting(interaction.guild.id, "msg_type", new_type)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="إشعارات الخاصة (DM)", style=discord.ButtonStyle.secondary, emoji="📩", row=0, custom_id="p_tgl_dm_v7")
    async def toggle_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_dm = 0 if cfg["dm_notifications"] else 1
        update_levels_setting(interaction.guild.id, "dm_notifications", new_dm)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="تبديل Text XP", style=discord.ButtonStyle.primary, emoji="💬", row=1, custom_id="p_tgl_text_v7")
    async def toggle_text_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_val = 0 if cfg["text_xp_enabled"] else 1
        update_levels_setting(interaction.guild.id, "text_xp_enabled", new_val)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="تبديل Voice XP", style=discord.ButtonStyle.primary, emoji="🎙️", row=1, custom_id="p_tgl_voice_v7")
    async def toggle_voice_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_val = 0 if cfg["voice_xp_enabled"] else 1
        update_levels_setting(interaction.guild.id, "voice_xp_enabled", new_val)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="تبديل Reaction XP", style=discord.ButtonStyle.primary, emoji="😀", row=1, custom_id="p_tgl_react_v7")
    async def toggle_react_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        new_val = 0 if cfg["reaction_xp_enabled"] else 1
        update_levels_setting(interaction.guild.id, "reaction_xp_enabled", new_val)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="إعدادات الـ XP", style=discord.ButtonStyle.primary, emoji="⚙️", row=2, custom_id="p_xp_cfg_levels_persistent_v7")
    async def xp_cfg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(LevelsXpModal())

    @discord.ui.button(label="إعدادات XP الريأكشن", style=discord.ButtonStyle.primary, emoji="⚙️", row=2, custom_id="p_react_cfg_levels_v7")
    async def react_cfg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(ReactionXpModal())

    @discord.ui.button(label="رسالة الترقية والـ Embed", style=discord.ButtonStyle.secondary, emoji="💬", row=2, custom_id="p_msg_cfg_levels_persistent_v7")
    async def msg_cfg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(LevelsMessageModal())

    @discord.ui.button(label="نظام مضاعف الـ XP", style=discord.ButtonStyle.success, emoji="🔥", row=3, custom_id="p_event_btn_levels_persistent_v7")
    async def event_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        embed_scope = discord.Embed(
            title="🔥 إعداد نطاق مضاعف الـ XP",
            description="هل تريد تطبيق المضاعف على **السيرفر بالكامل** أم على **رتب مخصصة**؟",
            color=0x2B2D31
        )
        await interaction.response.send_message(embed=embed_scope, view=MultiplierScopeView(), ephemeral=True)

    @discord.ui.button(label="إضافة رول مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=3, custom_id="p_reward_btn_levels_persistent_v7")
    async def reward_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(LevelsRewardModal())

    @discord.ui.button(label="استبعاد رتبة", style=discord.ButtonStyle.danger, emoji="🚫", row=4, custom_id="p_ignore_role_v7")
    async def ignore_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(IgnoreRoleModal())

    @discord.ui.button(label="استبعاد روم", style=discord.ButtonStyle.danger, emoji="🚫", row=4, custom_id="p_ignore_chan_v7")
    async def ignore_chan_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(IgnoreChannelModal())


# ==============================================================================
# 🚀 محرك التشغيل البرمجي والمنطق الأساسي (Cog Core Engine)
# ==============================================================================
class UltimateLevelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_tracker.start()

    def cog_unload(self):
        self.voice_tracker.cancel()

    async def cog_load(self):
        self.bot.add_view(LevelsAdminPanelView())
        self.bot.add_view(TopLeaderboardView())
        self.bot.add_view(MultiplierScopeView())

    @tasks.loop(minutes=1)
    async def voice_tracker(self):
        for guild in self.bot.guilds:
            cfg = get_levels_settings(guild.id)
            if not cfg["status"] or not cfg["voice_xp_enabled"]:
                continue

            for voice_channel in guild.voice_channels:
                if voice_channel.id in cfg["ignored_voice"]:
                    continue

                for member in voice_channel.members:
                    if member.bot or member.voice.self_mute or member.voice.self_deaf:
                        continue

                    if any(r.id in cfg["ignored_roles"] for r in member.roles):
                        continue

                    base_v_xp = random.randint(cfg["min_voice_xp"], cfg["max_voice_xp"])
                    
                    if cfg["event_end_timestamp"] > time.time() and cfg["event_type"] in ["voice", "both"]:
                        is_eligible = False
                        if cfg["event_target_roles"] == "all":
                            is_eligible = True
                        else:
                            allowed_role_ids = [int(r_id.strip()) for r_id in cfg["event_target_roles"].split(",") if r_id.strip().isdigit()]
                            if any(r.id in allowed_role_ids for r in member.roles):
                                is_eligible = True

                        if is_eligible:
                            base_v_xp = int(base_v_xp * cfg["event_multiplier"])

                    conn = sqlite3.connect(LEVELS_DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT voice_xp, voice_minutes, day_voice_xp, week_voice_xp, month_voice_xp, xp, level
                        FROM user_stats WHERE guild_id = ? AND user_id = ?
                    """, (guild.id, member.id))
                    row = cursor.fetchone()

                    if not row:
                        cursor.execute("""
                            INSERT INTO user_stats (guild_id, user_id, voice_xp, voice_minutes, day_voice_xp, week_voice_xp, month_voice_xp, xp)
                            VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                        """, (guild.id, member.id, base_v_xp, base_v_xp, base_v_xp, base_v_xp, base_v_xp))
                    else:
                        v_xp = row[0] + base_v_xp
                        v_m = row[1] + 1
                        d_v = row[2] + base_v_xp
                        w_v = row[3] + base_v_xp
                        m_v = row[4] + base_v_xp
                        tot_xp = row[5] + base_v_xp
                        
                        cursor.execute("""
                            UPDATE user_stats SET voice_xp = ?, voice_minutes = ?, day_voice_xp = ?, week_voice_xp = ?, month_voice_xp = ?, xp = ?
                            WHERE guild_id = ? AND user_id = ?
                        """, (v_xp, v_m, d_v, w_v, m_v, tot_xp, guild.id, member.id))

                    conn.commit()
                    conn.close()

                    udata = {"xp": (row[5] + base_v_xp) if row else base_v_xp, "level": row[6] if row else 0, "messages": 0}
                    await self.check_level_up(member, guild.id, udata, cfg)

    @voice_tracker.before_loop
    async def before_voice_tracker(self):
        await self.bot.wait_until_ready()

    async def check_level_up(self, member, gid, udata, cfg):
        lvl = udata["level"]
        xp = udata["xp"]
        req_xp = (lvl + 1) * 300 + (lvl ** 1.2 * 120)

        if xp >= req_xp:
            new_lvl = lvl + 1
            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_stats SET level = ? WHERE guild_id = ? AND user_id = ?", (new_lvl, gid, member.id))
            conn.commit()
            conn.close()

            role_rewards = cfg.get("role_rewards", {})
            assigned_roles = role_rewards.get(str(new_lvl), [])
            role_earned_str = ""
            for rid in assigned_roles:
                r_target = member.guild.get_role(int(rid))
                if r_target:
                    try:
                        await member.add_roles(r_target, reason=f"Level System: Reached level {new_lvl}")
                        role_earned_str += f"\n🎁 **المكافأة:** تم منحك رتبة {r_target.mention}"
                    except:
                        pass

            try:
                template = cfg.get("level_message", "تهانينا يا {user}! لقد صعدت إلى مستوى جديد، استمر في تفاعلك الرائع!")
                final_text = template.replace("{user}", member.mention).replace("{level}", f"`{new_lvl}`")

                chan_id = cfg.get("announcement_channel")
                target_channel = member.guild.get_channel(chan_id) if chan_id else member.guild.system_channel

                if cfg["msg_type"] == "text":
                    if target_channel:
                        await target_channel.send(content=f"🌟 {final_text}{role_earned_str}")
                else:
                    embed_title = cfg.get("level_embed_title", "♦ ترقية إلى المستوى [{level}]").replace("{level}", str(new_lvl))
                    embed = discord.Embed(
                        title=embed_title,
                        description=f"{final_text}{role_earned_str}\n\n• **المستوى الحالي:** `{new_lvl}` 🏆",
                        color=0x00FF88,
                        timestamp=datetime.datetime.utcnow()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    if cfg.get("level_image"):
                        embed.set_image(url=cfg["level_image"])
                    embed.set_footer(text="نظام المستويات والتفاعل")

                    if target_channel:
                        await target_channel.send(content=f"🌟 مبروك يا {member.mention}!", embed=embed)

                if cfg["dm_notifications"]:
                    try:
                        await member.send(content=f"🎉 **مبروك ترقيتك بداخل سيرفر {member.guild.name}:**\n{final_text}")
                    except:
                        pass
            except:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        gid = message.guild.id
        uid = message.author.id
        cfg = get_levels_settings(gid)

        if not cfg["status"] or not cfg["text_xp_enabled"]:
            return

        if message.channel.id in cfg["ignored_channels"]:
            return

        if any(role.id in cfg["ignored_roles"] for role in message.author.roles):
            return

        now_ts = time.time()
        if not hasattr(self, "cooldowns"):
            self.cooldowns = {}
        if gid not in self.cooldowns:
            self.cooldowns[gid] = {}
        
        if now_ts - self.cooldowns[gid].get(uid, 0) < cfg["text_cooldown"]:
            return
        self.cooldowns[gid][uid] = now_ts

        base_xp = random.randint(cfg["min_text_xp"], cfg["max_text_xp"])
        
        role_mult = 1.0
        for r in message.author.roles:
            if r.id in cfg["role_multipliers"]:
                role_mult = max(role_mult, cfg["role_multipliers"][r.id])

        final_xp = int(base_xp * role_mult)
        if cfg["event_end_timestamp"] > time.time() and cfg["event_type"] in ["text", "both"]:
            is_eligible = False
            if cfg["event_target_roles"] == "all":
                is_eligible = True
            else:
                allowed_role_ids = [int(r_id.strip()) for r_id in cfg["event_target_roles"].split(",") if r_id.strip().isdigit()]
                if any(r.id in allowed_role_ids for r in message.author.roles):
                    is_eligible = True

            if is_eligible:
                final_xp = int(final_xp * cfg["event_multiplier"])

        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages, day_text_xp, week_text_xp, month_text_xp FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, uid))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level, messages, day_text_xp, week_text_xp, month_text_xp) VALUES (?, ?, ?, 0, 1, ?, ?, ?)", (gid, uid, final_xp, final_xp, final_xp, final_xp))
            conn.commit()
            row = (final_xp, 0, 1, final_xp, final_xp, final_xp)
        else:
            new_xp = row[0] + final_xp
            new_msgs = row[2] + 1
            d_xp = row[3] + final_xp
            w_xp = row[4] + final_xp
            m_xp = row[5] + final_xp
            cursor.execute("UPDATE user_stats SET xp = ?, messages = ?, day_text_xp = ?, week_text_xp = ?, month_text_xp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_msgs, d_xp, w_xp, m_xp, gid, uid))
            conn.commit()

        udata = {"xp": row[0] + final_xp, "level": row[1], "messages": row[2] + 1}
        conn.close()

        await self.check_level_up(message.author, gid, udata, cfg)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        cfg = get_levels_settings(guild.id)
        if not cfg["status"] or not cfg["reaction_xp_enabled"]:
            return

        if payload.channel_id in cfg["ignored_channels"]:
            return

        if any(role.id in cfg["ignored_roles"] for role in member.roles):
            return

        base_xp = random.randint(cfg["min_reaction_xp"], cfg["max_reaction_xp"])
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level FROM user_stats WHERE guild_id = ? AND user_id = ?", (guild.id, member.id))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level) VALUES (?, ?, ?, 0)", (guild.id, member.id, base_xp))
        else:
            new_xp = row[0] + base_xp
            cursor.execute("UPDATE user_stats SET xp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, guild.id, member.id))

        conn.commit()
        conn.close()

    @app_commands.command(name="top", description="عرض لوحة المتصدرين لأعضاء السيرفر مع القائمة المنبثقة")
    async def top(self, interaction: discord.Interaction):
        view = TopLeaderboardView(interaction.guild, duration="global", page=0)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=False)

    @app_commands.command(name="level", description="استعراض بطاقة الرانك الخاصة بك مع تفاصيل مضاعفات الـ XP والرتب")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = interaction.guild.id
        cfg = get_levels_settings(gid)

        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM user_stats WHERE guild_id = ? ORDER BY (xp + voice_xp) DESC", (gid,))
        all_users = cursor.fetchall()
        rank_pos = "غير محدد"
        for idx, (u_id,) in enumerate(all_users, start=1):
            if u_id == target.id:
                rank_pos = f"#{idx}"
                break

        cursor.execute("SELECT xp, level, messages, voice_xp, voice_minutes FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, target.id))
        row = cursor.fetchone()
        conn.close()

        udata = {"xp": row[0], "level": row[1], "messages": row[2], "voice_xp": row[3], "v_mins": row[4]} if row else {"xp": 0, "level": 0, "messages": 0, "voice_xp": 0, "v_mins": 0}
        req_xp = (udata["level"] + 1) * 300 + (udata["level"] ** 1.2 * 120)
        progress_bar = create_progress_bar(udata["xp"], req_xp)

        has_double = f"نعم (x{cfg['event_multiplier']}) ⚡" if cfg["event_multiplier"] > 1.0 else "لا ⚪"
        active_role_mult = 1.0
        for r in target.roles:
            if r.id in cfg["role_multipliers"]:
                active_role_mult = max(active_role_mult, cfg["role_multipliers"][r.id])

        earned_roles = []
        for lvl_key, r_ids in cfg["role_rewards"].items():
            if udata["level"] >= int(lvl_key):
                for rid in r_ids:
                    r_obj = interaction.guild.get_role(rid)
                    if r_obj:
                        earned_roles.append(r_obj.mention)

        roles_earned_str = ", ".join(earned_roles) if earned_roles else "لا توجد رتب مكتسبة بعد"

        embed = discord.Embed(
            title=f"📊 [ ] : مستوي ✦ {target.display_name}",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(name="🏆 [ ] : المستوى", value=f"```{udata['level']}```", inline=True)
        embed.add_field(name="✨ [ ] : نقاط الـ XP", value=f"```{udata['xp']} / {int(req_xp)}```", inline=True)
        embed.add_field(name="📍 [ ] : الترتيب بالسيرفر", value=f"```{rank_pos}```", inline=True)
        embed.add_field(name="⚡ [ ] : مضاعف السيرفر", value=f"`{has_double}`", inline=True)
        embed.add_field(name="🛡️ [ ] : مضاعف رتبتك", value=f"`x{active_role_mult}`", inline=True)
        embed.add_field(name="📝 [ ] : إجمالي الرسائل", value=f"`{udata['messages']}`", inline=True)
        embed.add_field(name="🎙️ [ ] : دقائق الصوت", value=f"`{udata['v_mins']}` دقيقة", inline=True)
        embed.add_field(name="🎁 [ ] : رتب المكافآت المكتسبة", value=roles_earned_str, inline=False)
        embed.add_field(name="📈 [ ] : شريط التقدم", value=progress_bar, inline=False)

        embed.set_footer(text="نظام المستويات والتفاعل", icon_url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="setup_levels", description="[الإدارة] لوحة التحكم وإعدادات نظام المستويات")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_levels(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ [ ] : لوحة إعدادات المستويات",
            description="اختر من الأزرار التالية لإدارة وتعديل خصائص النظام:",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, view=LevelsAdminPanelView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(UltimateLevelsCog(bot))
