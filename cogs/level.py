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
            periodic_type TEXT DEFAULT 'week'
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
        event_str = f"`x{cfg['event_multiplier']}` | المدى: {target_str}"
    else:
        event_str = "لا يوجد حدث نشط ⚪"
    
    periodic_disp = f"<@&{cfg['periodic_reward_role']}> ({cfg['periodic_type'].upper()})" if cfg['periodic_reward_role'] else "غير مفعّلة ⚪"
    
    embed = discord.Embed(
        title="⚙️ [ ] : لوحة تحكم نظام المستويات الشاملة",
        description=(
            "مرحباً بك في لوحة الإدارة المركزية لنظام التفاعل والمستويات.\n\n"
            f"• **حالة النظام العامة:** {status_str}\n"
            f"• **قناة إعلانات الترقية:** {chan_disp}\n"
            f"• **نظام مضاعف الـ XP:** {event_str}\n"
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

class Step5PeriodicRewardModal(discord.ui.Modal, title="🏆 الخطوة 5: مكافأة التفاعل الدوري"):
    role_box = discord.ui.TextInput(label="أيدي رتبة المكافأة التفاعلية", placeholder="Role ID", max_length=30, required=True)
    type_box = discord.ui.TextInput(label="النوع (day / week / month)", default="week", max_length=10, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rid = int(self.role_box.value.strip())
            ptype = self.type_box.value.strip().lower()
            if ptype not in ["day", "week", "month"]:
                ptype = "week"
            
            if not interaction.guild.get_role(rid):
                raise ValueError

            update_levels_setting(interaction.guild.id, "periodic_reward_role", rid)
            update_levels_setting(interaction.guild.id, "periodic_type", ptype)

            embed_ok = discord.Embed(title="✅ تم الحفظ بنجاح", description=f"تم حفظ إعدادات مكافأة التفاعل الدوري (`{ptype}`) بنجاح!", color=0x00FF88)
            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="تأكد من صحة أيدي الرتبة.", color=0xFF3333), ephemeral=True)

class Step5QueryView(discord.ui.View):
    def __init__(self, cfg):
        super().__init__(timeout=60)
        self.cfg = cfg

    @discord.ui.button(label="نعم، تعيين رتبة مكافأة تفاعل ✅", style=discord.ButtonStyle.success, custom_id="q_yes_periodic_v7")
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(Step5PeriodicRewardModal())

    @discord.ui.button(label="لا، إنهاء وتخطي ❌", style=discord.ButtonStyle.secondary, custom_id="q_no_periodic_v7")
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        embed_ok = discord.Embed(title="✅ تم حفظ المعلومات", description="تم حفظ كافة إعدادات النظام بنجاح.", color=0x00FF88)
        await interaction.followup.send(embed=embed_ok, ephemeral=True)

class Step3XpValuesModal(discord.ui.Modal, title="⚙️ الخطوة 3: تحديد نطاق نقاط الـ XP"):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

        if cfg["text_xp_enabled"]:
            self.text_min = discord.ui.TextInput(label="أدنى XP نصي", default=str(cfg["min_text_xp"]), max_length=5)
            self.text_max = discord.ui.TextInput(label="أقصى XP نصي", default=str(cfg["max_text_xp"]), max_length=5)
            self.add_item(self.text_min)
            self.add_item(self.text_max)
        
        if cfg["voice_xp_enabled"]:
            self.voice_min = discord.ui.TextInput(label="أدنى XP صوتي", default=str(cfg["min_voice_xp"]), max_length=5)
            self.voice_max = discord.ui.TextInput(label="أقصى XP صوتي", default=str(cfg["max_voice_xp"]), max_length=5)
            self.add_item(self.voice_min)
            self.add_item(self.voice_max)

        if cfg["reaction_xp_enabled"]:
            self.react_min = discord.ui.TextInput(label="أدنى XP للريأكشن", default=str(cfg["min_reaction_xp"]), max_length=5)
            self.react_max = discord.ui.TextInput(label="أقصى XP للريأكشن", default=str(cfg["max_reaction_xp"]), max_length=5)
            self.add_item(self.react_min)
            self.add_item(self.react_max)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.cfg["text_xp_enabled"]:
                update_levels_setting(interaction.guild.id, "min_text_xp", int(self.text_min.value))
                update_levels_setting(interaction.guild.id, "max_text_xp", int(self.text_max.value))
            if self.cfg["voice_xp_enabled"]:
                update_levels_setting(interaction.guild.id, "min_voice_xp", int(self.voice_min.value))
                update_levels_setting(interaction.guild.id, "max_voice_xp", int(self.voice_max.value))
            if self.cfg["reaction_xp_enabled"]:
                update_levels_setting(interaction.guild.id, "min_reaction_xp", int(self.react_min.value))
                update_levels_setting(interaction.guild.id, "max_reaction_xp", int(self.react_max.value))

            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🏆 الخطوة 4: رتبة مكافأة التفاعل الدوري",
                    description="هل تريد تعيين رتبة مكافأة أسبوعية أو شهرية لأعلى شخص تفاعلاً في السيرفر؟",
                    color=0x2B2D31
                ),
                view=Step5QueryView(self.cfg),
                ephemeral=True
            )
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة فقط في نطاق النقاط.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class Step2XpMessageModal(discord.ui.Modal, title="💬 الخطوة 2: رسالة وشكل الترقية"):
    msg_box = discord.ui.TextInput(
        label="أدخل رسالة الترقية",
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

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        m_type = self.type_box.value.strip().lower()
        if m_type not in ["embed", "text"]:
            m_type = "text"

        update_levels_setting(interaction.guild.id, "level_message", self.msg_box.value)
        update_levels_setting(interaction.guild.id, "msg_type", m_type)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ الخطوة 3: تعديل نقاط الـ XP",
                description="هل تريد تعديل نقاط الـ XP للأنظمة المفعلة حالياً؟",
                color=0x2B2D31
            ),
            view=Step3QueryView(self.cfg),
            ephemeral=True
        )

class Step3QueryView(discord.ui.View):
    def __init__(self, cfg):
        super().__init__(timeout=60)
        self.cfg = cfg

    @discord.ui.button(label="نعم، أريد التعديل ✅", style=discord.ButtonStyle.success, custom_id="q_yes_xp_v7")
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(Step3XpValuesModal(self.cfg))

    @discord.ui.button(label="لا، تخطي ❌", style=discord.ButtonStyle.secondary, custom_id="q_no_xp_v7")
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏆 الخطوة 4: رتبة مكافأة التفاعل الدوري",
                description="هل تريد تعيين رتبة مكافأة أسبوعية أو شهرية لأعلى شخص تفاعلاً في السيرفر؟",
                color=0x2B2D31
            ),
            view=Step5QueryView(self.cfg),
            ephemeral=True
        )

class Step2QueryView(discord.ui.View):
    def __init__(self, cfg):
        super().__init__(timeout=60)
        self.cfg = cfg

    @discord.ui.button(label="نعم، تعيين رسالة ترقية ✅", style=discord.ButtonStyle.success, custom_id="q_yes_msg_v7")
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        examples_embed = discord.Embed(
            title="💡 أمثلة وشرح متغيرات رسالة الترقية",
            description=(
                "• لاستخدام منشن العضو: اكتب `{user}`\n"
                "• لاستخدام رقم المستوى الجديد: اكتب `{level}`\n\n"
                "📌 **مثال جاهز:**\n`مبروك يا {user} وصولك للمستوى {level} بنجاح! 🚀`"
            ),
            color=0x00AAFF
        )
        await interaction.response.send_message(embed=examples_embed, ephemeral=True)
        await interaction.followup.send_modal(Step2XpMessageModal(self.cfg))

    @discord.ui.button(label="لا، لا أريد ❌", style=discord.ButtonStyle.secondary, custom_id="q_no_msg_v7")
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ الخطوة 3: تعديل نقاط الـ XP",
                description="هل تريد تعديل نقاط الـ XP للأنظمة المفعلة حالياً؟",
                color=0x2B2D31
            ),
            view=Step3QueryView(self.cfg),
            ephemeral=True
        )

class Step1XpStatesModal(discord.ui.Modal, title="⚙️ الخطوة 1: تفعيل أو تعطيل أنظمة الـ XP"):
    text_st = discord.ui.TextInput(label="الإكس بي النصي (مفعل / غير مفعل)", default="مفعل", max_length=15)
    voice_st = discord.ui.TextInput(label="الإكس بي الصوتي (مفعل / غير مفعل)", default="مفعل", max_length=15)
    react_st = discord.ui.TextInput(label="إكس بي الريأكشن (مفعل / غير مفعل)", default="غير مفعل", max_length=15)

    async def on_submit(self, interaction: discord.Interaction):
        t_en = 1 if "مفعل" in self.text_st.value.strip() else 0
        v_en = 1 if "مفعل" in self.voice_st.value.strip() else 0
        r_en = 1 if "مفعل" in self.react_st.value.strip() else 0

        update_levels_setting(interaction.guild.id, "text_xp_enabled", t_en)
        update_levels_setting(interaction.guild.id, "voice_xp_enabled", v_en)
        update_levels_setting(interaction.guild.id, "reaction_xp_enabled", r_en)

        cfg = get_levels_settings(interaction.guild.id)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="💬 الخطوة 2: إعلانات الترقية",
                description="هل تريد تعيين رسالة ترقية عند صعود الأعضاء للمستويات؟",
                color=0x2B2D31
            ),
            view=Step2QueryView(cfg),
            ephemeral=True
        )

class AdvancedEventConfigModal(discord.ui.Modal, title="🔥 إعداد نظام مضاعف الـ XP"):
    mult_box = discord.ui.TextInput(label="قيمة المضاعف (بحد أقصى 5)", default="2", max_length=3)
    days_box = discord.ui.TextInput(label="مدة المضاعف بالأيام (مثال: 1 أو 2)", default="1", max_length=3)

    def __init__(self, target_roles="all"):
        super().__init__()
        self.target_roles = target_roles

    async def on_submit(self, interaction: discord.Interaction):
        try:
            m_val = float(self.mult_box.value)
            if m_val > 5.0 or m_val < 1.0:
                embed_err = discord.Embed(title="❌ قيمة غير مسموحة", description="عذراً، الحد الأقصى لمضاعف الـ XP هو `5`.", color=0xFF3333)
                await interaction.response.send_message(embed=embed_err, ephemeral=True)
                return

            days_val = int(self.days_box.value)
            secs = days_val * 86400

            end_ts = int(time.time()) + secs
            update_levels_setting(interaction.guild.id, "event_multiplier", m_val)
            update_levels_setting(interaction.guild.id, "event_type", "both")
            update_levels_setting(interaction.guild.id, "event_end_timestamp", end_ts)
            update_levels_setting(interaction.guild.id, "event_target_roles", self.target_roles)

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            embed_ok = discord.Embed(title="🔥 تم تفعيل نظام المضاعف", description=f"تم إطلاق مضاعف الـ XP بقيمة `x{m_val}` لمدة `{days_val}` يوم بنجاح.", color=0x00FF88)
            await interaction.followup.send(embed=embed_ok, ephemeral=True)
        except ValueError:
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى إدخال أرقام صحيحة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)

class SpecificRolesInputModal(discord.ui.Modal, title="🎯 تحديد الرتب للمضاعف"):
    roles_box = discord.ui.TextInput(label="أيديهات الرتب - كل أيدي في سطر", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        raw_lines = self.roles_box.value.strip().split("\n")
        valid_roles = [l.strip() for l in raw_lines if l.strip().isdigit()]
        if not valid_roles:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="أيديهات غير صحيحة.", color=0xFF3333), ephemeral=True)
            return
        await interaction.response.send_modal(AdvancedEventConfigModal(target_roles=",".join(valid_roles)))

class MultiplierScopeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="السيرفر بالكامل 🌐", style=discord.ButtonStyle.primary, custom_id="mult_all_v7")
    async def scope_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdvancedEventConfigModal(target_roles="all"))

    @discord.ui.button(label="رتب معينة 🎯", style=discord.ButtonStyle.secondary, custom_id="mult_roles_v7")
    async def scope_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SpecificRolesInputModal())

class IgnoreCombinedModal(discord.ui.Modal, title="🚫 إدارة استثناءات الرومات والرتب"):
    roles_box = discord.ui.TextInput(label="أيديهات الرتب المستبعدة (كل أيدي في سطر)", style=discord.TextStyle.paragraph, required=False)
    channels_box = discord.ui.TextInput(label="أيديهات الرومات المستبعدة (كل أيدي في سطر)", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        
        if self.roles_box.value:
            for line in self.roles_box.value.strip().split("\n"):
                if line.strip().isdigit():
                    cursor.execute("INSERT OR IGNORE INTO ignored_roles (guild_id, role_id) VALUES (?, ?)", (interaction.guild.id, int(line.strip())))
        
        if self.channels_box.value:
            for line in self.channels_box.value.strip().split("\n"):
                if line.strip().isdigit():
                    cursor.execute("INSERT OR IGNORE INTO ignored_channels (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, int(line.strip())))
        
        conn.commit()
        conn.close()

        await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
        await interaction.followup.send(embed=discord.Embed(title="✅ تم الحفظ", description="تم تحديث الاستثناءات بنجاح.", color=0x00FF88), ephemeral=True)

class LevelsRewardModal(discord.ui.Modal, title="🎁 إضافة رول مكافأة"):
    lvl_box = discord.ui.TextInput(label="المستوى المطلوب", placeholder="5", max_length=5)
    role_box = discord.ui.TextInput(label="أيدي الرتبة (Role ID)", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lvl = int(self.lvl_box.value)
            rid = int(self.role_box.value)
            if not interaction.guild.get_role(rid):
                raise ValueError

            conn = sqlite3.connect(LEVELS_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (interaction.guild.id, lvl, rid))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView())
            await interaction.followup.send(embed=discord.Embed(title="✅ تم", description=f"تم ربط المستوى {lvl} بالرتبة بنجاح.", color=0x00FF88), ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="❌ خطأ", description="تأكد من صحة البيانات.", color=0xFF3333), ephemeral=True)

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

    @discord.ui.button(label="إعدادات الـ XP (شامل)", style=discord.ButtonStyle.primary, emoji="⚙️", row=0, custom_id="p_xp_unified_v7")
    async def xp_unified_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(Step1XpStatesModal())

    @discord.ui.button(label="نظام مضاعف الـ XP", style=discord.ButtonStyle.success, emoji="🔥", row=1, custom_id="p_event_v7")
    async def event_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_message(embed=discord.Embed(title="🔥 نطاق المضاعف", description="اختر نطاق تطبيق المضاعف:", color=0x2B2D31), view=MultiplierScopeView(), ephemeral=True)

    @discord.ui.button(label="إضافة رول مكافأة", style=discord.ButtonStyle.success, emoji="🎁", row=1, custom_id="p_reward_v7")
    async def reward_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(LevelsRewardModal())

    @discord.ui.button(label="استبعاد روم أو رول", style=discord.ButtonStyle.danger, emoji="🚫", row=2, custom_id="p_ignore_combined_v7")
    async def ignore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return
        await interaction.response.send_modal(IgnoreCombinedModal())

class TopDurationSelect(discord.ui.Select):
    def __init__(self, current_duration="global"):
        options = [
            discord.SelectOption(label="Global", value="global", emoji="🌐", default=(current_duration == "global")),
            discord.SelectOption(label="Day", value="day", emoji="📅", default=(current_duration == "day")),
            discord.SelectOption(label="Week", value="week", emoji="🗓️", default=(current_duration == "week")),
            discord.SelectOption(label="Month", value="month", emoji="📆", default=(current_duration == "month")),
        ]
        super().__init__(placeholder="Select duration", options=options, custom_id="top_sel_v7")

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
            lines.append(f"#{i}• <@{r[0]>: {r[1]} XP")
        return discord.Embed(title=f"📋 Top {self.duration} XP", description="\n".join(lines) if lines else "لا توجد بيانات.", color=0x2B2D31)

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
            for vc in guild.voice_channels:
                if vc.id in cfg["ignored_voice"]:
                    continue
                for m in vc.members:
                    if m.bot or m.voice.self_mute or m.voice.self_deaf:
                        continue
                    if any(r.id in cfg["ignored_roles"] for r in m.roles):
                        continue
                    base_xp = random.randint(cfg["min_voice_xp"], cfg["max_voice_xp"])
                    conn = sqlite3.connect(LEVELS_DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("SELECT xp, level FROM user_stats WHERE guild_id = ? AND user_id = ?", (guild.id, m.id))
                    row = cursor.fetchone()
                    if not row:
                        cursor.execute("INSERT INTO user_stats (guild_id, user_id, xp, level) VALUES (?, ?, ?, 0)", (guild.id, m.id, base_xp))
                    else:
                        cursor.execute("UPDATE user_stats SET xp = ? WHERE guild_id = ? AND user_id = ?", (row[0] + base_xp, guild.id, m.id))
                    conn.commit()
                    conn.close()

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
        
        base_xp = random.randint(cfg["min_text_xp"], cfg["max_text_xp"])
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
        await self.check_level_up(message.author, gid, udata, cfg)

    @app_commands.command(name="top", description="عرض المتصدرين")
    async def top(self, interaction: discord.Interaction):
        view = TopLeaderboardView(interaction.guild, duration="global", page=0)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @app_commands.command(name="level", description="استعراض رانكك الحالي")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        conn = sqlite3.connect(LEVELS_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, messages FROM user_stats WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, target.id))
        row = cursor.fetchone()
        conn.close()
        xp, lvl, msgs = row if row else (0, 0, 0)
        embed = discord.Embed(title=f"📊 رانك العضو {target.display_name}", description=f"🏆 المستوى: `{lvl}`\n✨ النقاط: `{xp}`\n📝 الرسائل: `{msgs}`", color=0x2B2D31)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup_levels", description="[الإدارة] لوحة تحكم المستويات الشاملة")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_levels(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=generate_levels_panel_embed(interaction.guild), view=LevelsAdminPanelView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(UltimateLevelsCog(bot))
