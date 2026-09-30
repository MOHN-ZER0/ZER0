import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os

CONFIG_FILE = "warnings_config.json"
DATA_FILE = "warnings_data.json"

# ==============================================================================
# 🗄️ إدارة حفظ واسترجاع البيانات بملفات JSON دائمية
# ==============================================================================
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# هيكل الإعدادات الافتراضي
DEFAULT_CONFIG = {
    "warn_names": ["التحذير الأول ✦ [1]", "التحذير الثاني ✦ [2]", "التحذير الثالث ✦ [3]"],
    "warn_roles": {}, # {"0": role_id_int, ...}
    "log_channel_id": None,
    "punishments": {} # {"0": {"type": "timeout", "duration_minutes": 120}, ...} types: none, timeout, kick, ban
}

SERVER_WARNING_CONFIGS = load_json(CONFIG_FILE, DEFAULT_CONFIG)
WARNINGS_DB = load_json(DATA_FILE, {}) # {str(user_id): [list of warns]}

def save_configs():
    save_json(CONFIG_FILE, SERVER_WARNING_CONFIGS)

def save_db():
    save_json(DATA_FILE, WARNINGS_DB)


# ==============================================================================
# 📝 نماذج الإدخال التفاعلية (Modals) لتخصيص الإعدادات والنظام
# ==============================================================================
class WarningNamesModal(discord.ui.Modal, title="✏️ تخصيص أسماء التحذيرات"):
    warnings_input = discord.ui.TextInput(
        label="أسماء التحذيرات (كل اسم في سطر مستقل)",
        style=discord.TextStyle.paragraph,
        placeholder="تحذير اول\nتحذير ثاني\nتحذير ثالث",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        lines = [line.strip() for line in self.warnings_input.value.split("\n") if line.strip()]
        if not lines:
            await interaction.response.send_message("❌ يجب إدخال اسم تحذير واحد على الأقل!", ephemeral=True)
            return
        
        SERVER_WARNING_CONFIGS["warn_names"] = lines
        save_configs()
        await interaction.response.send_message(
            f"✅ **تم تحديث وحفظ أسماء التحذيرات بنجاح!**\nالعدد الإجمالي: `{len(lines)}` مستويات.",
            ephemeral=True
        )

class WarningRolesModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="🔗 ربط رتب التحذيرات")
        self.inputs_map = {}
        names = SERVER_WARNING_CONFIGS.get("warn_names", [])
        for idx, name in enumerate(names[:5]):
            current_role_id = SERVER_WARNING_CONFIGS["warn_roles"].get(str(idx), "")
            text_input = discord.ui.TextInput(
                label=f"آيدي رتبة: {name}",
                placeholder="اكتب آيدي الرتبة هنا (اختياري)",
                default=str(current_role_id) if current_role_id else "",
                required=False,
                max_length=30
            )
            self.add_item(text_input)
            self.inputs_map[idx] = text_input

    async def on_submit(self, interaction: discord.Interaction):
        new_roles_map = {}
        for idx, text_input in self.inputs_map.items():
            val = text_input.value.strip()
            if val.isdigit():
                new_roles_map[str(idx)] = int(val)
        
        SERVER_WARNING_CONFIGS["warn_roles"] = new_roles_map
        save_configs()
        await interaction.response.send_message("✅ **تم تحديث وحفظ ربط رتب التحذيرات بنجاح!**", ephemeral=True)

class LogChannelModal(discord.ui.Modal, title="📢 تعيين قناة لوج التحذيرات"):
    channel_id_input = discord.ui.TextInput(
        label="اكتب آيدي (ID) قناة اللوج المطلوبة",
        style=discord.TextStyle.short,
        placeholder="123456789012345678",
        required=True,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        ch_id_str = self.channel_id_input.value.strip()
        if not ch_id_str.isdigit():
            await interaction.response.send_message("❌ الآيدي المدخل غير صحيح!", ephemeral=True)
            return
        
        ch_id = int(ch_id_str)
        channel = interaction.guild.get_channel(ch_id)
        if not channel:
            await interaction.response.send_message("❌ لم يتم العثور على القناة بهذا الآيدي!", ephemeral=True)
            return

        SERVER_WARNING_CONFIGS["log_channel_id"] = ch_id
        save_configs()
        await interaction.response.send_message(f"✅ **تم بنجاح!** تم تعيين قناة اللوج لتكون: {channel.mention}", ephemeral=True)


# ==============================================================================
# ⚙️ تخصيص العقوبات التصاعدية لكل مستوى تحذير
# ==============================================================================
class PunishmentSettingsSelect(discord.ui.Select):
    def __init__(self):
        options = []
        names = SERVER_WARNING_CONFIGS.get("warn_names", [])
        for idx, name in enumerate(names):
            current_p = SERVER_WARNING_CONFIGS.get("punishments", {}).get(str(idx), {"type": "none", "duration": 0})
            p_desc = f"العقوبة الحالية: {current_p['type']} ({current_p.get('duration', 0)} دقيقة)"
            options.append(discord.SelectOption(label=f"مستوى {idx+1}: {name}", description=p_desc[:100], value=str(idx)))
        
        super().__init__(placeholder="⚙️ اختر التحذير لتعديل عقوبته التصاعدية...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        warn_idx = self.values[0]
        await interaction.response.send_modal(PunishmentEditModal(warn_idx))

class PunishmentEditModal(discord.ui.Modal):
    def __init__(self, warn_idx):
        names = SERVER_WARNING_CONFIGS.get("warn_names", [])
        warn_name = names[int(warn_idx)] if int(warn_idx) < len(names) else f"مستوى {warn_idx}"
        super().__init__(title=f"تعديل عقوبة: {warn_name}")
        self.warn_idx = warn_idx

        current = SERVER_WARNING_CONFIGS.get("punishments", {}).get(str(warn_idx), {"type": "none", "duration": 60})
        
        self.p_type = discord.ui.TextInput(
            label="نوع العقوبة (اكتب: none, timeout, kick, ban)",
            placeholder="timeout",
            default=current.get("type", "none"),
            required=True,
            max_length=20
        )
        self.p_duration = discord.ui.TextInput(
            label="مدة التايم أوت بالدقائق (لو العقوبة timeout)",
            placeholder="120 (مثال تعني ساعتين)",
            default=str(current.get("duration", 0)),
            required=False,
            max_length=10
        )
        self.add_item(self.p_type)
        self.add_item(self.p_duration)

    async def on_submit(self, interaction: discord.Interaction):
        ptype = self.p_type.value.strip().lower()
        if ptype not in ["none", "timeout", "kick", "ban"]:
            await interaction.response.send_message("❌ نوع العقوبة غير صحيح! يجب إدخال: none أو timeout أو kick أو ban", ephemeral=True)
            return
        
        dur = 0
        if ptype == "timeout":
            dur_str = self.p_duration.value.strip()
            if dur_str.isdigit():
                dur = int(dur_str)

        if "punishments" not in SERVER_WARNING_CONFIGS:
            SERVER_WARNING_CONFIGS["punishments"] = {}

        SERVER_WARNING_CONFIGS["punishments"][str(self.warn_idx)] = {
            "type": ptype,
            "duration": dur
        }
        save_configs()
        await interaction.response.send_message(f"✅ **تم حفظ العقوبة التصاعدية بنجاح** لهذا المستوى!", ephemeral=True)

class PunishmentSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PunishmentSettingsSelect())


# ==============================================================================
# 🗑️ قوائم الحذف والتصفير التفاعلية (Select Menus)
# ==============================================================================
class RemoveSingleWarningSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for uid, warns in WARNINGS_DB.items():
            if warns:
                options.append(
                    discord.SelectOption(label=f"User ID: {uid}", description=f"عدد التحذيرات: {len(warns)}", value=str(uid))
                )
        if not options:
            options.append(discord.SelectOption(label="لا توجد تحذيرات نشطة حالياً", value="none"))

        super().__init__(placeholder="🔽 اختر العضو لإزالة آخر تحذير عنه...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ لا توجد تحذيرات لإزالتها.", ephemeral=True)
            return

        user_id = str(self.values[0])
        if user_id not in WARNINGS_DB or not WARNINGS_DB[user_id]:
            await interaction.response.send_message("❌ سجل هذا العضو فارغ.", ephemeral=True)
            return

        removed = WARNINGS_DB[user_id].pop()
        if not WARNINGS_DB[user_id]:
            del WARNINGS_DB[user_id]
        save_db()

        member = interaction.guild.get_member(int(user_id))
        if member:
            for r_id in SERVER_WARNING_CONFIGS["warn_roles"].values():
                role = interaction.guild.get_role(r_id)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Unwarned via Dashboard")
                    except:
                        pass

        await interaction.response.send_message(f"✅ **تم بنجاح!** تم إزالة التحذير (`{removed['name']}`) عن العضو (ID: `{user_id}`).", ephemeral=True)

class ClearAllUserWarningsSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for uid, warns in WARNINGS_DB.items():
            if warns:
                options.append(
                    discord.SelectOption(label=f"User ID: {uid}", description=f"مسح كامل لعدد {len(warns)} تحذيرات", value=str(uid))
                )
        if not options:
            options.append(discord.SelectOption(label="لا توجد تحذيرات نشطة حالياً", value="none"))

        super().__init__(placeholder="🗑️ اختر العضو لمسح سجله بالكامل...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ لا توجد سجلات لتصفيرها.", ephemeral=True)
            return

        user_id = str(self.values[0])
        if user_id in WARNINGS_DB:
            del WARNINGS_DB[user_id]
            save_db()

        member = interaction.guild.get_member(int(user_id))
        if member:
            for r_id in SERVER_WARNING_CONFIGS["warn_roles"].values():
                role = interaction.guild.get_role(r_id)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Full warning logs cleared")
                    except:
                        pass

        await interaction.response.send_message(f"🧹 **تم التصفير بنجاح!** تم مسح سجل التحذيرات بالكامل للعضو (ID: `{user_id}`).", ephemeral=True)

class RemoveWarningView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RemoveSingleWarningSelect())

class ClearAllWarningsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ClearAllUserWarningsSelect())


# ==============================================================================
# 🎛️ لوحة التحكم الرئيسية التفاعلية (Dashboard)
# ==============================================================================
class AdvancedWarningsDashboard(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="✏️ تعديل الأسماء", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def edit_names(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ للمسؤولين فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(WarningNamesModal())

    @discord.ui.button(label="🔗 تعيين الرتب", style=discord.ButtonStyle.secondary, emoji="🛡️", row=0)
    async def edit_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ للمسؤولين فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(WarningRolesModal())

    @discord.ui.button(label="⚙️ عقوبات تصاعدية", style=discord.ButtonStyle.secondary, emoji="⚡", row=0)
    async def set_punishments(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ لمدربي السيرفر (Administrator) فقط!", ephemeral=True)
            return
        await interaction.response.send_message("⚙️ **اختر التحذير لتحديد عقوبته التلقائية:**", view=PunishmentSettingsView(), ephemeral=True)

    @discord.ui.button(label="📢 قناة اللوج", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ لمدربي السيرفر فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(LogChannelModal())

    @discord.ui.button(label="📊 عرض المخالفين", style=discord.ButtonStyle.primary, emoji="👥", row=1)
    async def show_all_warnings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 **سجل نظيف تماماً!** مفيش أي شخص واخد تحذيرات حالياً.", ephemeral=True)
            return
        
        desc = "> 📋 **قائمة الأعضاء المخالفين حالياً:**\n━━━━━━━━━━━━━━━━━━━━━\n"
        for uid, warns in WARNINGS_DB.items():
            member = interaction.guild.get_member(int(uid))
            m_name = member.mention if member else f"عضو مغادر (`{uid}`)"
            desc += f"👤 **{m_name}** ── ｢ الإنذارات: **{len(warns)}** ｣\n"
            for w in warns:
                desc += f" └ ⚡ `{w['name']}` | ⏳ المدة: `{w['duration']}` | السبب: `{w['reason']}`\n"
            desc += "\n"
        
        if len(desc) > 4000:
            desc = desc[:3996] + "..."

        embed = discord.Embed(title="📊 ╎ سجـل الـتـحـذيـرات الـنـشـطة", description=desc, color=0x111111)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🛠️ إزالة تحذير مفرد", style=discord.ButtonStyle.danger, emoji="⚡", row=2)
    async def remove_warn_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ للمسؤولين فقط!", ephemeral=True)
            return
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 لا توجد تحذيرات لإزالتها.", ephemeral=True)
            return
        await interaction.response.send_message("🔽 **اختر العضو لسحب آخر تحذير عنه:**", view=RemoveWarningView(), ephemeral=True)

    @discord.ui.button(label="🧹 مسح سجل عضو بالكامل", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def clear_all_user_warns(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ للمسؤولين فقط!", ephemeral=True)
            return
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 لا توجد أي سجلات تحذيرات لتصفيرها.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ **اختر العضو المراد تصفير ومسح سجله بالكامل:**", view=ClearAllWarningsView(), ephemeral=True)


# ==============================================================================
# 🛡️ كوج إدارة التحذيرات الخارق والمدمج
# ==============================================================================
class UltimateWarningSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_warn_choices(self, interaction: discord.Interaction, current: str):
        choices = []
        names = SERVER_WARNING_CONFIGS["warn_names"]
        for idx, name in enumerate(names):
            if current.lower() in name.lower() and idx < 25:
                choices.append(app_commands.Choice(name=name, value=idx))
        return choices

    @app_commands.command(name="warn", description="[إدارة] إعطاء تحذير رسمي لعضو وتطبيق العقوبة التصاعدية المخصصة")
    @app_commands.describe(
        member="العضو المراد تحذيره",
        warn_level="مستوى التحذير المطلوب",
        duration="مدة التحذير (مثال: 1d أو 1h)",
        reason="سبب إصدار التحذير (اختياري)"
    )
    @app_commands.autocomplete(warn_level=get_warn_choices)
    @app_commands.checks.has_permissions(manage_roles=True, moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, warn_level: int, duration: str = "دائم", reason: str = "بدون سبب مخصص"):
        if member.id == interaction.user.id or member.bot or member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ لا يمكنك تحذير هذا الشخص!", ephemeral=True)
            return

        names = SERVER_WARNING_CONFIGS["warn_names"]
        if warn_level < 0 or warn_level >= len(names):
            await interaction.response.send_message("❌ مستوى التحذير غير صالح.", ephemeral=True)
            return
        
        warn_name = names[warn_level]
        role_id = SERVER_WARNING_CONFIGS["warn_roles"].get(str(warn_level))
        
        await interaction.response.defer(ephemeral=False)

        # منح رتبة التحذير الخاصة بهذا المستوى
        assigned_role_text = "بدون رتبة تلقائية"
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"Warned by {interaction.user} | Reason: {reason}")
                    assigned_role_text = role.mention
                except discord.HTTPException as e:
                    assigned_role_text = f"فشل منح الرتبة: `{e}`"

        user_key = str(member.id)
        if user_key not in WARNINGS_DB:
            WARNINGS_DB[user_key] = []
        
        warning_record = {
            "level": warn_level,
            "name": warn_name,
            "reason": reason,
            "duration": duration,
            "moderator": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y/%m/%d %H:%M")
        }
        WARNINGS_DB[user_key].append(warning_record)
        save_db()
        total_user_warns = len(WARNINGS_DB[user_key])

        # تنفيذ العقوبة التصاعدية المخصصة لهذا التحذير من الإعدادات
        punishments_config = SERVER_WARNING_CONFIGS.get("punishments", {})
        p_info = punishments_config.get(str(warn_level), {"type": "none", "duration": 0})
        p_type = p_info.get("type", "none")
        p_dur = p_info.get("duration", 0)

        auto_action_text = "لا توجد عقوبة محددة لهذا المستوى"
        try:
            if p_type == "timeout" and p_dur > 0:
                td = datetime.timedelta(minutes=p_dur)
                await member.timeout(td, reason=f"Auto-punishment for warning: {warn_name}")
                auto_action_text = f"⚡ تم تنفيذ (Timeout) تلقائي لمدة `{p_dur}` دقيقة بناءً على الإعدادات!"
            elif p_type == "kick":
                await member.kick(reason=f"Auto-kick for warning: {warn_name}")
                auto_action_text = "🚪 تم طرد العضو (Kick) أوتوماتيكياً!"
            elif p_type == "ban":
                await member.ban(reason=f"Auto-ban for warning: {warn_name}")
                auto_action_text = "🔨 تم حظر العضو (Ban) نهائياً أوتوماتيكياً!"
        except Exception as e:
            auto_action_text = f"⚠️ فشل تطبيق العقوبة التلقائية: {e}"

        embed = discord.Embed(
            title="⚠️ ╎ نـظـام الـتـحـذيـرات والـعـقـوبات الـمـركـزي",
            description=f"> تم تسجيل وإصدار تحذير رسمي بحق أحد المخالفين.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المخالف", value=f"> ｢ {member.mention} ｣", inline=False)
        embed.add_field(name="⚠️ ╎ نـوع الـتـحـذيـر", value=f"> ｢ {warn_name} ｣ (إجمالي سجله: {total_user_warns})", inline=False)
        embed.add_field(name="⏳ ╎ الـمـدة", value=f"> ｢ {duration} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب", value=f"> ｢ {reason} ｣", inline=False)
        embed.add_field(name="🎖 ╎ الرتبة المرتبطة", value=f"> {assigned_role_text}", inline=False)
        if p_type != "none":
            embed.add_field(name="🚨 ╎ العقوبة التصاعدية", value=f"> {auto_action_text}", inline=False)

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="𝐙 𝐈 𝐔𝐎 ╎ Warnings Engine")
        
        sent_msg = await interaction.followup.send(embed=embed)
        warning_record["log_message_id"] = sent_msg.id

        log_ch_id = SERVER_WARNING_CONFIGS.get("log_channel_id")
        if log_ch_id:
            log_channel = interaction.guild.get_channel(log_ch_id)
            if log_channel:
                try:
                    log_embed = embed.copy()
                    log_embed.title = "📢 ╎ سـجـل تـحـذيـر جـديـد (System Audit Log)"
                    log_sent = await log_channel.send(embed=log_embed)
                    warning_record["channel_log_message_id"] = log_sent.id
                except:
                    pass

    @app_commands.command(name="warnings", description="[إدارة] فتح لوحة تحكم التحذيرات الشاملة أو عرض سجل عضو معين")
    @app_commands.describe(member="العضو المراد الاستعلام عنه (اتركه فارغاً لفتح اللوحة)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        if member:
            user_key = str(member.id)
            if user_key not in WARNINGS_DB or not WARNINGS_DB[user_key]:
                await interaction.response.send_message(f"✅ العضو {member.mention} لا يمتلك أي تحذيرات مسجلة.", ephemeral=True)
                return
            
            warns = WARNINGS_DB[user_key]
            desc = f"> سجّلات التحذيرات الخاصة بالعضو {member.mention} (الإجمالي: {len(warns)}):\n━━━━━━━━━━━━━━━━━━━━━\n"
            for idx, w in enumerate(warns, 1):
                desc += f"**{idx}.** المستوى: `{w['name']}`\n"
                desc += f" ✦ **السبب:** `{w['reason']}` | **المدة:** `{w['duration']}`\n\n"
                
            embed = discord.Embed(title=f"📋 ╎ تـحـذيـرات: {member.display_name}", description=desc, color=0x2B2D31)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="🛡️ ╎ لـوحـة تـحـكـم ونـظـام الـتـحـذيـرات الـمـركـزي",
                description="> أهلاً بك في لوحة تحكم التحذيرات المرنة لسيرفر 𝐙𝐈𝐔𝐎.\n> اختر الإجراء أو قم بتعديل العقوبات التصاعدية من الأزرار:",
                color=0x2B2D31
            )
            await interaction.response.send_message(embed=embed, view=AdvancedWarningsDashboard(self.bot), ephemeral=True)

    @app_commands.command(name="unwarn", description="[إدارة] إزالة آخر تحذير مسجل وسحب رتبته عن العضو بدقة")
    @app_commands.describe(member="العضو المراد إزالة التحذير عنه")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member):
        user_key = str(member.id)
        if user_key not in WARNINGS_DB or not WARNINGS_DB[user_key]:
            await interaction.response.send_message(f"❌ العضو {member.mention} ليس لديه تحذيرات لإزالتها.", ephemeral=True)
            return

        removed = WARNINGS_DB[user_key].pop()
        if not WARNINGS_DB[user_key]:
            del WARNINGS_DB[user_key]
        save_db()

        for r_id in SERVER_WARNING_CONFIGS["warn_roles"].values():
            role = interaction.guild.get_role(r_id)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Unwarn executed by {interaction.user}")
                except:
                    pass

        log_ch_id = SERVER_WARNING_CONFIGS.get("log_channel_id")
        if log_ch_id and "channel_log_message_id" in removed:
            try:
                log_ch = interaction.guild.get_channel(log_ch_id)
                if log_ch:
                    msg_to_del = await log_ch.fetch_message(removed["channel_log_message_id"])
                    if msg_to_del:
                        await msg_to_del.delete()
            except:
                pass

        await interaction.response.send_message(f"✅ **تم بنجاح!** تم إزالة آخر تحذير (`{removed['name']}`) عن العضو {member.mention} وحذف رسالة السجل المرتبطة.", ephemeral=False)

async def setup(bot):
    await bot.add_cog(UltimateWarningSystemCog(bot))
