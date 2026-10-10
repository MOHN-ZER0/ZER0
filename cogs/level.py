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
            msg_type TEXT DEFAULT 'text',
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
            event_target_roles TEXT DEFAULT 'all',
            periodic_reward_role INTEGER,
            periodic_type TEXT DEFAULT 'week',
            last_weekly_reset INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_roles (guild_id INTEGER, role_id INTEGER, PRIMARY KEY (guild_id, role_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS ignored_voice_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS role_multipliers (guild_id INTEGER, role_id INTEGER, multiplier REAL, PRIMARY KEY (guild_id, role_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS user_multipliers (guild_id INTEGER, user_id INTEGER, multiplier REAL, PRIMARY KEY (guild_id, user_id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS channel_multipliers (guild_id INTEGER, channel_id INTEGER, multiplier REAL, PRIMARY KEY (guild_id, channel_id))")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_rewards (
            guild_id INTEGER,
            level INTEGER,
            role_id INTEGER,
            req_type TEXT DEFAULT 'all',
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

def get_levels_settings(guild_id: int):
    conn = sqlite3.connect(LEVELS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, announcement_channel, msg_type, level_message, level_embed_title, level_image, dm_notifications,
               text_xp_enabled, min_text_xp, max_text_xp, text_cooldown,
               voice_xp_enabled, min_voice_xp, max_voice_xp, voice_cooldown,
               reaction_xp_enabled, min_reaction_xp, max_reaction_xp,
               event_multiplier, event_type, event_end_timestamp, event_target_roles,
               periodic_reward_role, periodic_type
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
                   event_multiplier, event_type, event_end_timestamp, event_target_roles,
                   periodic_reward_role, periodic_type
            FROM server_settings WHERE guild_id = ?
        """, (guild_id,))
        row = cursor.fetchone()

    cursor.execute("SELECT level, role_id, req_type FROM role_rewards WHERE guild_id = ?", (guild_id,))
    role_rewards = {}
    for lvl, r_id, r_type in cursor.fetchall():
        type_str = r_type if r_type else "all"
        role_rewards.setdefault(str(lvl), []).append({"role_id": r_id, "req_type": type_str})

    cursor.execute("SELECT role_id FROM ignored_roles WHERE guild_id = ?", (guild_id,))
    ignored_roles = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT channel_id FROM ignored_channels WHERE guild_id = ?", (guild_id,))
    ignored_channels = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT channel_id FROM ignored_voice_channels WHERE guild_id = ?", (guild_id,))
    ignored_voice = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT role_id, multiplier FROM role_multipliers WHERE guild_id = ?", (guild_id,))
    role_mults = dict(cursor.fetchall())

    cursor.execute("SELECT user_id, multiplier FROM user_multipliers WHERE guild_id = ?", (guild_id,))
    user_mults = dict(cursor.fetchall())

    cursor.execute("SELECT channel_id, multiplier FROM channel_multipliers WHERE guild_id = ?", (guild_id,))
    channel_mults = dict(cursor.fetchall())

    conn.close()
    
    return {
        "status": bool(row[0]),
        "announcement_channel": row[1],
        "msg_type": row[2] if row[2] else "text",
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
        "periodic_reward_role": row[22] if len(row) > 22 else None,
        "periodic_type": row[23] if len(row) > 23 else "week",
        "role_rewards": role_rewards,
        "ignored_roles": ignored_roles,
        "ignored_channels": ignored_channels,
        "ignored_voice": ignored_voice,
        "role_multipliers": role_mults,
        "user_multipliers": user_mults,
        "channel_multipliers": channel_mults
    }

def update_levels_setting(guild_id: int, column: str, value):
    conn = sqlite3.connect(LEVELS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE server_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()

def generate_levels_panel_embed(guild: discord.Guild):
    cfg = get_levels_settings(guild.id)
    status_str = "مفعّل 🟢" if cfg["status"] else "متوقف 🔴"
    chan_disp = f"<#{cfg['announcement_channel']}>" if cfg['announcement_channel'] else "القناة الافتراضية 💬"
    
    if cfg["event_multiplier"] > 1.0 and cfg["event_end_timestamp"] > time.time():
        target_str = "السيرفر بالكامل" if cfg["event_target_roles"] == "all" else "رتب محددة 🎯"
        event_str = f"`x{cfg['event_multiplier']}` | المدى: {target_str}"
    else:
        event_str = "لا يوجد حدث عام نشط ⚪"
    
    periodic_disp = f"<@&{cfg['periodic_reward_role']}> ({cfg['periodic_type'].upper()})" if cfg['periodic_reward_role'] else "غير مفعّلة ⚪"
    
    embed = discord.Embed(
        title="⚙️ [ ] : لوحة تحكم نظام المستويات الشاملة",
        description=(
            "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل والمستويات.\n\n"
            f"• **حالة النظام العامة:** {status_str}\n"
            f"• **قناة إعلانات الترقية:** {chan_disp}\n"
            f"• **نظام المضاعف العام:** {event_str}\n"
            f"• **رتبة مكافأة التفاعل الدوري:** {periodic_disp}\n\n"
            f"⚙️ **أنظمة الـ XP الفعالة:**\n"
            f"┗ **النص:** `{'مفعل ✅' if cfg['text_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_text_xp']}-{cfg['max_text_xp']}` XP\n"
            f"┗ **الصوت:** `{'مفعل ✅' if cfg['voice_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_voice_xp']}-{cfg['max_voice_xp']}` XP\n"
            f"┗ **الرياكشنت:** `{'مفعل ✅' if cfg['reaction_xp_enabled'] else 'معطل ❌'}` | النطاق: `{cfg['min_reaction_xp']}-{cfg['max_reaction_xp']}` XP\n\n"
            f"🚫 **الاستثناءات والمكافآت:**\n"
            f"┗ **رولات مستبعدة:** `{len(cfg['ignored_roles'])}` | **قنوات مستبعدة:** `{len(cfg['ignored_channels'])}`\n"
            f"┗ **رولات المكافآت الثابتة:** `{sum(len(v) for v in cfg['role_rewards'].values())}` رتبة\n"
        ),
        color=0x2B2D31,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="نظام إدارة المستويات والتفاعل الفائق")
    return embed

class AnnouncementChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📢 اختر قناة إعلانات الترقية", channel_types=[discord.ChannelType.text], min_values=1, max_values=1, custom_id="sel_announce_chan_v7")

    async def callback(self, interaction: discord.Interaction):
        selected_chan = self.values[0]
        update_levels_setting(interaction.guild.id, "announcement_channel", selected_chan.id)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        await interaction.followup.send(embed=discord.Embed(title="✅ تم تحديد القناة", description=f"تم تعيين قناة إعلانات الترقية إلى {selected_chan.mention} بنجاح.", color=0x00FF88), ephemeral=True)

class Step3XpValuesModal(discord.ui.Modal, title="⚙️ تحديد نقاط الـ XP"):
    text_min = discord.ui.TextInput(label="أدنى XP نصي", default="5", max_length=5)
    text_max = discord.ui.TextInput(label="أقصى XP نصي", default="45", max_length=5)
    voice_min = discord.ui.TextInput(label="أدنى XP صوتي", default="2", max_length=5)
    voice_max = discord.ui.TextInput(label="أقصى XP صوتي", default="5", max_length=5)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            update_levels_setting(interaction.guild.id, "min_text_xp", int(self.text_min.value))
            update_levels_setting(interaction.guild.id, "max_text_xp", int(self.text_max.value))
            update_levels_setting(interaction.guild.id, "min_voice_xp", int(self.voice_min.value))
            update_levels_setting(interaction.guild.id, "max_voice_xp", int(self.voice_max.value))

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            await interaction.followup.send(embed=discord.Embed(title="✅ تم التعديل بنجاح", description="تم تحديث نطاق نقاط الـ XP بنجاح.", color=0x00FF88), ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة فقط في نطاق النقاط.", color=0xFF3333), ephemeral=True)

class Step2XpMessageModal(discord.ui.Modal, title="💬 رسالة وشكل الترقية"):
    msg_box = discord.ui.TextInput(
        label="أدخل رسالة الترقية الجديدة",
        style=discord.TextStyle.paragraph,
        default="تهانينا يا {user}! لقد صعدت إلى مستوى {level}.",
        max_length=1000,
        required=True
    )
    type_box = discord.ui.TextInput(
        label="نوع الرسالة (أكتب: embed أو text)",
        default="text",
        max_length=10,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        m_type = self.type_box.value.strip().lower()
        if m_type not in ["embed", "text"]:
            m_type = "text"

        update_levels_setting(interaction.guild.id, "level_message", self.msg_box.value)
        update_levels_setting(interaction.guild.id, "msg_type", m_type)

        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        await interaction.followup.send(embed=discord.Embed(title="✅ تم التعديل", description="تم حفظ رسالة ونوع الترقية بنجاح.", color=0x00FF88), ephemeral=True)

class MultiplierValueModal(discord.ui.Modal, title="⚡ تعيين قيمة المضاعف"):
    mult_box = discord.ui.TextInput(label="قيمة المضاعف (مثال: 1.5 أو 2 أو 3.5)", default="2.0", max_length=5, required=True)

    def __init__(self, target_type, target_ids):
        super().__init__()
        self.target_type = target_type
        self.target_ids = target_ids

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.mult_box.value)
            if val < 1.0 or val > 5.0:
                raise ValueError
            
            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            
            if self.target_type == "user":
                for uid in self.target_ids:
                    cursor.execute("INSERT OR REPLACE INTO user_multipliers (guild_id, user_id, multiplier) VALUES (?, ?, ?)", (interaction.guild.id, uid, val))
            elif self.target_type == "role":
                for rid in self.target_ids:
                    cursor.execute("INSERT OR REPLACE INTO role_multipliers (guild_id, role_id, multiplier) VALUES (?, ?, ?)", (interaction.guild.id, rid, val))
            elif self.target_type == "channel":
                for cid in self.target_ids:
                    cursor.execute("INSERT OR REPLACE INTO channel_multipliers (guild_id, channel_id, multiplier) VALUES (?, ?, ?)", (interaction.guild.id, cid, val))
            
            conn.commit()
            conn.close()

            await interaction.response.send_message(embed=discord.Embed(title="✅ تم الحفظ بنجاح", description=f"تم تعيين مضاعف بقيمة `x{val}` بنجاح!", color=0x00FF88), ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="يرجى إدخال قيمة صحيحة بين 1.0 و 5.0", color=0xFF3333), ephemeral=True)

class SelectUsersForMultiplier(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="اختر الأعضاء لتطبيق المضاعف عليهم", min_values=1, max_values=10, custom_id="sel_mult_users")

    async def callback(self, interaction: discord.Interaction):
        u_ids = [u.id for u in self.values]
        await interaction.response.send_modal(MultiplierValueModal("user", u_ids))

class SelectRolesForMultiplier(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="اختر الرتب لتطبيق المضاعف عليها", min_values=1, max_values=10, custom_id="sel_mult_roles")

    async def callback(self, interaction: discord.Interaction):
        r_ids = [r.id for r in self.values]
        await interaction.response.send_modal(MultiplierValueModal("role", r_ids))

class SelectChannelsForMultiplier(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="اختر الرومات لتطبيق المضاعف عليها", min_values=1, max_values=10, custom_id="sel_mult_chans")

    async def callback(self, interaction: discord.Interaction):
        c_ids = [c.id for c in self.values]
        await interaction.response.send_modal(MultiplierValueModal("channel", c_ids))

class MultiplierTypeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="مضاعف لأعضاء 👤", style=discord.ButtonStyle.primary, custom_id="m_type_user")
    async def mult_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = discord.ui.View()
        v.add_item(SelectUsersForMultiplier())
        await interaction.response.send_message(embed=discord.Embed(title="👤 اختر الأعضاء", description="حدد الأعضاء من القائمة أدناه:", color=0x2B2D31), view=v, ephemeral=True)

    @discord.ui.button(label="مضاعف لرتب 🛡️", style=discord.ButtonStyle.secondary, custom_id="m_type_role")
    async def mult_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = discord.ui.View()
        v.add_item(SelectRolesForMultiplier())
        await interaction.response.send_message(embed=discord.Embed(title="🛡️ اختر الرتب", description="حدد الرتب من القائمة أدناه:", color=0x2B2D31), view=v, ephemeral=True)

    @discord.ui.button(label="مضاعف لرومات 💬/🎙️", style=discord.ButtonStyle.success, custom_id="m_type_chan")
    async def mult_chan(self, interaction: discord.Interaction, button: discord.ui.Button):
        v = discord.ui.View()
        v.add_item(SelectChannelsForMultiplier())
        await interaction.response.send_message(embed=discord.Embed(title="💬 اختر الرومات", description="حدد الرومات من القائمة أدناه:", color=0x2B2D31), view=v, ephemeral=True)

class IgnoreRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="اختر الرتب المراد استبعادها من الـ XP", min_values=1, max_values=10, custom_id="sel_ignore_role_v7")

    async def callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        for r in self.values:
            cursor.execute("INSERT OR IGNORE INTO ignored_roles (guild_id, role_id) VALUES (?, ?)", (interaction.guild.id, r.id))
        conn.commit()
        conn.close()
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        await interaction.followup.send(embed=discord.Embed(title="✅ تم الحفظ", description="تم استبعاد الرتب المحددة بنجاح.", color=0x00FF88), ephemeral=True)

class IgnoreChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="اختر الرومات المراد استبعادها من الـ XP", min_values=1, max_values=10, custom_id="sel_ignore_chan_v7")

    async def callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        for c in self.values:
            cursor.execute("INSERT OR IGNORE INTO ignored_channels (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, c.id))
        conn.commit()
        conn.close()
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        await interaction.followup.send(embed=discord.Embed(title="✅ تم الحفظ", description="تم استبعاد الرومات المحددة بنجاح.", color=0x00FF88), ephemeral=True)

class IgnoreSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(IgnoreRoleSelect())
        self.add_item(IgnoreChannelSelect())

class AnnouncementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(AnnouncementChannelSelect())

class LevelsRewardModal(discord.ui.Modal, title="🎁 إضافة رول مكافأة"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", placeholder="1234567890", max_length=30, required=True)
    lvl_box = discord.ui.TextInput(label="المستوى المطلوب للحصول عليها", placeholder="5", max_length=5, required=True)
    type_box = discord.ui.TextInput(
        label="نوع التفاعل المطلوب (نصي / صوتي / رياكشن / الكل)",
        default="الكل",
        placeholder="أكتب: نصي أو صوتي أو رياكشن أو الكل",
        max_length=15,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lvl = int(self.lvl_box.value)
            rid = int(self.role_box.value)
            raw_type = self.type_box.value.strip().lower()

            if "نص" in raw_type or "text" in raw_type:
                req_type = "text"
                req_disp = "نصي 💬"
            elif "صوت" in raw_type or "voice" in raw_type:
                req_type = "voice"
                req_disp = "صوتي 🎙️"
            elif "رياض" in raw_type or "ريا" in raw_type or "react" in raw_type:
                req_type = "reaction"
                req_disp = "ريأكشن 😄"
            else:
                req_type = "all"
                req_disp = "جميع التفاعلات 🌐"

            if not interaction.guild.get_role(rid):
                raise ValueError

            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO role_rewards (guild_id, level, role_id, req_type) VALUES (?, ?, ?, ?)", (interaction.guild.id, lvl, rid, req_type))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            await interaction.followup.send(embed=discord.Embed(title="✅ تم إضافة المكافأة", description=f"تم ربط المستوى `{lvl}` بالرتبة <@&{rid}>\n• **نوع التفاعل المطلوب:** {req_disp}", color=0x00FF88), ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="تأكد من صحة البيانات وأيدي الرتبة.", color=0xFF3333), ephemeral=True)

class LevelsAdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تشغيل / إيقاف النظام", style=discord.ButtonStyle.blurple, emoji="🔄", row=0, custom_id="p_tgl_v7")
    async def toggle_sys(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        cfg = get_levels_settings(interaction.guild.id)
        update_levels_setting(interaction.guild.id, "status", 0 if cfg["status"] else 1)
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="قناة إعلانات الترقية", style=discord.ButtonStyle.secondary, emoji="📢", row=0, custom_id="p_ann_chan_v7")
    async def set_announce_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_message(embed=discord.Embed(title="📢 قناة الإعلانات", description="اختر قناة إعلانات الترقية من القائمة أدناه:", color=0x2B2D31), view=AnnouncementView(), ephemeral=True)

    @discord.ui.button(label="إعدادات الـ XP", style=discord.ButtonStyle.primary, emoji="⚙️", row=0, custom_id="p_xp_unified_v7")
    async def xp_unified_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(Step3XpValuesModal())

    @discord.ui.button(label="مضاعفات الـ XP المخصصة", style=discord.ButtonStyle.success, emoji="⚡", row=1, custom_id="p_mult_custom_v7")
    async def custom_mult_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_message(embed=discord.Embed(title="⚡ إدارة مضاعفات الـ XP", description="اختر الفئة المراد تطبيق المضاعف عليها:", color=0x2B2D31), view=MultiplierTypeSelectView(), ephemeral=True)

    @discord.ui.button(label="رسالة الترقية", style=discord.ButtonStyle.secondary, emoji="💬", row=1, custom_id="p_msg_v7")
    async def msg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(Step2XpMessageModal())

    @discord.ui.button(label="إضافة رول مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=1, custom_id="p_reward_v7")
    async def reward_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(LevelsRewardModal())

    @discord.ui.button(label="استبعاد روم أو رول", style=discord.ButtonStyle.danger, emoji="🚫", row=2, custom_id="p_ignore_combined_v7")
    async def ignore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_message(embed=discord.Embed(title="🚫 استبعاد رومات أو رتب", description="اختر من القوائم أدناه مباشرة:", color=0x2B2D31), view=IgnoreSelectView(), ephemeral=True)

class TopDurationSelect(discord.ui.Select):
    def __init__(self, current_duration="global"):
        options = [
            discord.SelectOption(label="Global / العالمي", value="global", emoji="🌐", default=(current_duration == "global")),
            discord.SelectOption(label="Day / اليومي", value="day", emoji="📅", default=(current_duration == "day")),
            discord.SelectOption(label="Week / أسبوعي", value="week", emoji="🗓️", default=(current_duration == "week")),
            discord.SelectOption(label="Month / شهري", value="month", emoji="📆", default=(current_duration == "month")),
        ]
        super().__init__(placeholder="Select duration / اختر فترة الترتيب", options=options, custom_id="top_sel_v7")

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
            cursor.execute("SELECT user_id, day_text_xp, level FROM user_stats WHERE guild_id = ? ORDER BY day_text_xp DESC", (self.guild.id,))
        elif self.duration == "week":
            cursor.execute("SELECT user_id, week_text_xp, level FROM user_stats WHERE guild_id = ? ORDER BY week_text_xp DESC", (self.guild.id,))
        elif self.duration == "month":
            cursor.execute("SELECT user_id, month_text_xp, level FROM user_stats WHERE guild_id = ? ORDER BY month_text_xp DESC", (self.guild.id,))
        else:
            cursor.execute("SELECT user_id, xp, level FROM user_stats WHERE guild_id = ? ORDER BY xp DESC", (self.guild.id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def create_embed(self):
        if not self.guild:
            return discord.Embed(title="Top", color=0x2B2D31)
        rows = self.fetch_data()
        lines = []
        for i, r in enumerate(rows[:5], 1):
            lines.append(f"#{i}• <@{r[0]}>: {r[1]} XP")
        return discord.Embed(title=f"📋 Top Leaderboard ({self.duration})", description="\n".join(lines) if lines else "لا توجد بيانات تفاعل.", color=0x2B2D31)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="◀", custom_id="t_prev_v7")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="My Rank", style=discord.ButtonStyle.secondary, custom_id="t_my_v7")
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        rows = self.fetch_data()
        pos = next((i for i, r in enumerate(rows, 1) if r[0] == interaction.user.id), None)
        await interaction.response.send_message(embed=discord.Embed(title="📍 ترتيبك", description=f"ترتيبك: `#{pos}`" if pos else "ليس لديك تفاعل.", color=0x00FF88), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="▶", custom_id="t_next_v7")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild = interaction.guild
        self.page += 1
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

class UltimateLevelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_tracker.start()
        self.weekly_reset_loop.start()

    def cog_unload(self):
        self.voice_tracker.cancel()
        self.weekly_reset_loop.cancel()

    async def cog_load(self):
        self.bot.add_view(LevelsAdminPanelView())
        self.bot.add_view(TopLeaderboardView())
        self.bot.add_view(MultiplierTypeSelectView())

    @tasks.loop(minutes=1)
    async def weekly_reset_loop(self):
        now = datetime.datetime.now()
        if now.weekday() == 4 and now.hour == 12 and now.minute == 0:
            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT guild_id FROM server_settings")
            guilds = cursor.fetchall()
            for g in guilds:
                gid = g[0]
                cursor.execute("SELECT last_weekly_reset FROM server_settings WHERE guild_id = ?", (gid,))
                res = cursor.fetchone()
                last_reset = res[0] if res else 0
                today_date = int(now.strftime("%Y%m%d"))
                if last_reset != today_date:
                    cursor.execute("UPDATE user_stats SET week_text_xp = 0, week_voice_xp = 0 WHERE guild_id = ?", (gid,))
                    cursor.execute("UPDATE server_settings SET last_weekly_reset = ? WHERE guild_id = ?", (today_date, gid))
            conn.commit()
            conn.close()

    @weekly_reset_loop.before_loop
    async def before_weekly_reset(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def voice_tracker(self):
        for guild in self.bot.guilds:
            cfg = get_levels_settings(guild.id)
            if not cfg["status"] or not cfg["voice_xp_enabled"]:
                continue
            for vc in guild.voice_channels:
                if vc.id in cfg["ignored_voice"]:
                    continue
                for m in vc.members:
                    if m.bot or m.voice.self_mute or m.voice.self_deaf:
                        continue
                    if any(r.id in cfg["ignored_roles"] for r in m.roles):
                        continue
                    
                    mult = cfg["event_multiplier"]
                    if m.id in cfg["user_multipliers"]:
                        mult = max(mult, cfg["user_multipliers"][m.id])
                    for r in m.roles:
                        if r.id in cfg["role_multipliers"]:
                            mult = max(mult, cfg["role_multipliers"][r.id])
                    if vc.id in cfg["channel_multipliers"]:
                        mult = max(mult, cfg["channel_multipliers"][vc.id])

                    base_xp = int(random.randint(cfg["min_voice_xp"], cfg["max_voice_xp"]) * mult)
                    conn = sqlite3.connect(LEVELS_DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("SELECT xp, level, voice_minutes, week_voice_xp FROM user_stats WHERE guild_id = ? AND user_id = ?", (guild.id, m.id))
                    row = cursor.fetchone()
                    if not row:
                        cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level, voice_minutes, week_voice_xp) VALUES (?, ?, ?, 0, 1, ?)", (guild.id, m.id, base_xp, base_xp))
                    else:
                        cursor.execute("UPDATE user_stats SET xp = ?, voice_minutes = ?, week_voice_xp = ? WHERE guild_id = ? AND user_id = ?", (row[0] + base_xp, row[2] + 1, row[3] + base_xp, guild.id, m.id))
                    conn.commit()
                    conn.close()

                    udata = {"xp": row[0] + base_xp if row else base_xp, "level": row[1] if row else 0}
                    await self.check_level_up(m, guild.id, udata, cfg, trigger_type="voice")

    @voice_tracker.before_loop
    async def before_voice_tracker(self):
        await self.bot.wait_until_ready()

    async def check_level_up(self, member, gid, udata, cfg, trigger_type="text"):
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
            for item in assigned_roles:
                rid = item["role_id"]
                req_t = item["req_type"]
                
                if req_t == "all" or req_t == trigger_type:
                    r_target = member.guild.get_role(int(rid))
                    if r_target and r_target not in member.roles:
                        try:
                            await member.add_roles(r_target, reason=f"Level System: Reached level {new_lvl} via {trigger_type}")
                            role_earned_str += f"\n🎁 **المكافأة:** تم منحك رتبة {r_target.mention}"
                        except:
                            pass

            try:
                template = cfg.get("level_message", "تهانينا يا {user}! لقد صعدت إلى مستوى جديد، استمر في تفاعلك الرائع!")
                final_text = template.replace("{user}", member.mention).replace("{level}", f"`{new_lvl}`")

                chan_id = cfg.get("announcement_channel")
                target_channel = member.guild.get_channel(chan_id) if chan_id else member.guild.system_channel

                if target_channel:
                    if cfg["msg_type"] == "embed":
                        embed = discord.Embed(
                            title=f"♦ ترقية إلى المستوى [{new_lvl}]",
                            description=f"{final_text}{role_earned_str}\n\n• **المستوى الحالي:** `{new_lvl}` 🏆",
                            color=0x00FF88,
                            timestamp=datetime.datetime.utcnow()
                        )
                        embed.set_thumbnail(url=member.display_avatar.url)
                        await target_channel.send(content=f"🌟 مبروك يا {member.mention}!", embed=embed)
                    else:
                        await target_channel.send(content=f"🌟 {final_text}{role_earned_str}")
            except:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        gid = message.guild.id
        cfg = get_levels_settings(gid)
        if not cfg["status"] or not cfg["text_xp_enabled"] or message.channel.id in cfg["ignored_channels"]:
            return
        if any(r.id in cfg["ignored_roles"] for r in message.author.roles):
            return
        
        mult = cfg["event_multiplier"]
        if message.author.id in cfg["user_multipliers"]:
            mult = max(mult, cfg["user_multipliers"][message.author.id])
        for r in message.author.roles:
            if r.id in cfg["role_multipliers"]:
                mult = max(mult, cfg["role_multipliers"][r.id])
        if message.channel.id in cfg["channel_multipliers"]:
            mult = max(mult, cfg["channel_multipliers"][message.channel.id])

        base_xp = int(random.randint(cfg["min_text_xp"], cfg["max_text_xp"]) * mult)
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages, day_text_xp, week_text_xp, month_text_xp FROM user_stats WHERE guild_id = ? AND user_id = ?", (gid, message.author.id))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level, messages, day_text_xp, week_text_xp, month_text_xp) VALUES (?, ?, ?, 0, 1, ?, ?, ?)", (gid, message.author.id, base_xp, base_xp, base_xp, base_xp))
            row = (base_xp, 0, 1, base_xp, base_xp, base_xp)
        else:
            new_xp = row[0] + base_xp
            new_msgs = row[2] + 1
            d_xp = row[3] + base_xp
            w_xp = row[4] + base_xp
            m_xp = row[5] + base_xp
            cursor.execute("UPDATE user_stats SET xp = ?, messages = ?, day_text_xp = ?, week_text_xp = ?, month_text_xp = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_msgs, d_xp, w_xp, m_xp, gid, message.author.id))
        conn.commit()
        conn.close()

        udata = {"xp": row[0] + base_xp, "level": row[1]}
        await self.check_level_up(message.author, gid, udata, cfg, trigger_type="text")

    @app_commands.command(name="top", description="عرض المتصدرين")
    async def top(self, interaction: discord.Interaction):
        view = TopLeaderboardView(interaction.guild, duration="global", page=0)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @app_commands.command(name="level", description="استعراض رانكك الحالي")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages, voice_minutes FROM user_stats WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, target.id))
        row = cursor.fetchone()
        
        cursor.execute("SELECT user_id FROM user_stats WHERE guild_id = ? ORDER BY xp DESC", (interaction.guild.id,))
        all_users = [r[0] for r in cursor.fetchall()]
        rank = all_users.index(target.id) + 1 if target.id in all_users else "غير محدد"
        conn.close()

        xp, lvl, msgs, v_mins = row if row else (0, 0, 0, 0)
        req_xp = int((lvl + 1) * 300 + (lvl ** 1.2 * 120))
        cfg = get_levels_settings(interaction.guild.id)

        has_mult = "نعم 🟡" if cfg["event_multiplier"] > 1.0 else "لا ⚪"
        
        user_mult = 1.0
        if target.id in cfg["user_multipliers"]:
            user_mult = max(user_mult, cfg["user_multipliers"][target.id])
        for rid, mult in cfg["role_multipliers"].items():
            if any(r.id == rid for r in target.roles):
                if mult > user_mult:
                    user_mult = mult

        earned_roles = []
        for l_str, r_list in cfg["role_rewards"].items():
            if int(l_str) <= lvl:
                for item in r_list:
                    r_obj = interaction.guild.get_role(item["role_id"])
                    if r_obj:
                        earned_roles.append(r_obj.mention)
        
        earned_roles_str = " ، ".join(earned_roles) if earned_roles else "لا توجد رتب مكتسبة بعد"

        pct = min(1.0, xp / req_xp) if req_xp > 0 else 0
        filled = int(pct * 12)
        
        # نظام تلوين شريط التقدم الدقيق بناءً على الألوان والأوصاص المطلوبة (1x لحد 5x)
        if user_mult >= 4.5:
            bar = "⬜" * filled + "⬛" * (12 - filled)
        elif user_mult >= 3.5:
            bar = "🟨" * filled + "⬛" * (12 - filled)
        elif user_mult >= 2.5:
            bar = "🟧" * filled + "⬛" * (12 - filled)
        elif user_mult >= 1.5:
            bar = "🟥" * filled + "⬛" * (12 - filled)
        elif user_mult > 1.0:
            bar = "🟥🟩" * (filled // 2) + "🟩" * (filled % 2) + "⬛" * (12 - filled)
        else:
            bar = "🟩" * filled + "⬛" * (12 - filled)

        mult_display = f"x{user_mult}" if user_mult > 1.0 else "x1.0"

        embed = discord.Embed(color=0x2B2D31)
        embed.set_author(name=f"📊 [ ] : مستوي ✦ {target.display_name}")
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="🏆 [ ] : المستوى", value=f"```\n{lvl}\n```", inline=False)
        embed.add_field(name="✨ [ ] : نقاط الـ XP", value=f"```\n{xp} / {req_xp}\n```", inline=False)
        embed.add_field(name="📍 [ ] : الترتيب بالسيرفر", value=f"```\n{rank}\n```", inline=False)
        embed.add_field(name="⚡ [ ] : مضاعف السيرفر", value=f"{has_mult}", inline=False)
        embed.add_field(name="🛡️ [ ] : مضاعف رتبتك / حسابك", value=f"```\n{mult_display}\n```", inline=False)
        embed.add_field(name="📝 [ ] : إجمالي الرسائل", value=f"```\n{msgs}\n```", inline=False)
        embed.add_field(name="🎙️ [ ] : دقائق الصوت", value=f"```\n{v_mins} دقيقة\n```", inline=False)
        embed.add_field(name="🎁 [ ] : رتب المكافآت المكتسبة", value=f"{earned_roles_str}", inline=False)
        embed.add_field(name="📈 [ ] : شريط التقدم", value=f"{bar}", inline=False)

        embed.set_footer(text=f"نظام المستويات والتفاعل | {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup_levels", description="[الإدارة] لوحة تحكم المستويات الشاملة")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_levels(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(UltimateLevelsCog(bot))
