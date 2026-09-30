import discord
from discord import app_commands
from discord.ext import commands
import datetime

# ==============================================================================
# 🗄️ قواعد البيانات الديناميكية المؤقتة للإعدادات والسجلات
# ==============================================================================
SERVER_WARNING_CONFIGS = {
    "warn_names": ["التحذير الأول ✦ [1]", "التحذير الثاني ✦ [2]", "التحذير الثالث ✦ [3]"],
    "warn_roles": {}, # صيغة التخزين: {index_int: role_id_int}
    "log_channel_id": None # أيدي قناة اللوج الخاصة بالتحذيرات
}

WARNINGS_DB = {} # {user_id: [{"level": int, "name": str, "reason": str, "duration": str, "moderator": str, "date": str}]}

# ==============================================================================
# 📝 نماذج الإدخال التفاعلية (Modals) لتخصيص الإعدادات
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
        await interaction.response.send_message(
            f"✅ **تم تحديث أسماء التحذيرات بنجاح!**\nالعدد الإجمالي: `{len(lines)}` مستويات.",
            ephemeral=True
        )

class WarningRolesModal(discord.ui.Modal, title="🔗 ربط أيديهات رتب التحذيرات"):
    roles_input = discord.ui.TextInput(
        label="اكتب الـ ID الخاص بكل رتبة (كل ID في سطر بالترتيب)",
        style=discord.TextStyle.paragraph,
        placeholder="1543880992069132370\n1543880990668095610",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        lines = [line.strip() for line in self.roles_input.value.split("\n") if line.strip()]
        new_roles_map = {}
        
        for idx, role_id_str in enumerate(lines):
            if role_id_str.isdigit():
                new_roles_map[idx] = int(role_id_str)
        
        SERVER_WARNING_CONFIGS["warn_roles"] = new_roles_map
        await interaction.response.send_message("✅ **تم تحديث ربط رتب التحذيرات بنجاح!**", ephemeral=True)

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
            await interaction.response.send_message("❌ الآيدي المدخل غير صحيح! يجب أن يتكون من أرقام فقط.", ephemeral=True)
            return
        
        ch_id = int(ch_id_str)
        channel = interaction.guild.get_channel(ch_id)
        if not channel:
            await interaction.response.send_message("❌ لم يتم العثور على القناة بهذا الآيدي في السيرفر!", ephemeral=True)
            return

        SERVER_WARNING_CONFIGS["log_channel_id"] = ch_id
        await interaction.response.send_message(f"✅ **تم بنجاح!** تم تعيين قناة اللوج الرسمية للتحذيرات لتكون: {channel.mention}", ephemeral=True)


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

        user_id = int(self.values[0])
        if user_id not in WARNINGS_DB or not WARNINGS_DB[user_id]:
            await interaction.response.send_message("❌ سجل هذا العضو أصبح فارغاً.", ephemeral=True)
            return

        removed = WARNINGS_DB[user_id].pop()
        if not WARNINGS_DB[user_id]:
            del WARNINGS_DB[user_id]

        member = interaction.guild.get_member(user_id)
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
            await interaction.response.send_message("❌ لا توجد سجلات لتحذيرات لتصفيرها.", ephemeral=True)
            return

        user_id = int(self.values[0])
        if user_id not in WARNINGS_DB:
            await interaction.response.send_message("❌ هذا العضو ليس لديه سجل نشط.", ephemeral=True)
            return

        # مسح السجل بالكامل من القاموس
        del WARNINGS_DB[user_id]

        # سحب جميع رتب التحذيرات المرتبطة من العضو
        member = interaction.guild.get_member(user_id)
        if member:
            for r_id in SERVER_WARNING_CONFIGS["warn_roles"].values():
                role = interaction.guild.get_role(r_id)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Full warning logs cleared by Admin")
                    except:
                        pass

        await interaction.response.send_message(f"🧹 **تم التصفير بنجاح!** تم مسح سجل التحذيرات بالكامل للعضو (ID: `{user_id}`) وإزالة جميع رتبه المرتبطة.", ephemeral=True)

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

    @discord.ui.button(label="📢 قناة اللوج", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدربي السيرفر (Administrator) فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(LogChannelModal())

    @discord.ui.button(label="📊 عرض المخالفين", style=discord.ButtonStyle.primary, emoji="👥", row=1)
    async def show_all_warnings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 **سجل نظيف تماماً!** مفيش أي شخص واخد تحذيرات حالياً.", ephemeral=True)
            return
        
        desc = "> 📋 **قائمة الأعضاء المخالفين حالياً:**\n━━━━━━━━━━━━━━━━━━━━━\n"
        for uid, warns in WARNINGS_DB.items():
            member = interaction.guild.get_member(uid)
            m_name = member.mention if member else f"عضو مغادر (`{uid}`)"
            desc += f"👤 **{m_name}** ── ｢ الإنذارات: **{len(warns)}** ｣\n"
            for w in warns:
                desc += f" └ ⚡ `{w['name']}` | ⏳ المدة: `{w['duration']}` | السبب: `{w['reason']}`\n"
            desc += "\n"
        
        if len(desc) > 4000:
            desc = desc[:3996] + "..."

        embed = discord.Embed(title="📊 ╎ سجـل الـتـحـذيـرات الـنـشـطة", description=desc, color=0x111111)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🛠️ إزالة تحذير مفرد", style=discord.ButtonStyle.danger, emoji="⚡", row=1)
    async def remove_warn_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ للمسؤولين فقط!", ephemeral=True)
            return
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 لا توجد تحذيرات لإزالتها.", ephemeral=True)
            return
        await interaction.response.send_message("🔽 **اختر العضو لسحب آخر تحذير عنه:**", view=RemoveWarningView(), ephemeral=True)

    @discord.ui.button(label="🧹 مسح سجل عضو بالكامل", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
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

    # دالة الإكمال التلقائي المعدلة والصحيحة
    async def get_warn_choices(self, interaction: discord.Interaction, current: str):
        choices = []
        names = SERVER_WARNING_CONFIGS["warn_names"]
        for idx, name in enumerate(names):
            if current.lower() in name.lower() and idx < 25:
                choices.append(app_commands.Choice(name=name, value=idx))
        return choices

    # 1. أمر إعطاء التحذير (/warn)
    @app_commands.command(name="warn", description="[إدارة] إعطاء تحذير رسمي لعضو مع تحديد المستوى، السبب، والمدة بدقة")
    @app_commands.describe(
        member="العضو المراد تحذيره",
        warn_level="مستوى التحذير المطلوب",
        duration="مدة التحذير (مثال: 1d أو 1h أو 1m)",
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
        role_id = SERVER_WARNING_CONFIGS["warn_roles"].get(warn_level)
        
        await interaction.response.defer(ephemeral=False)

        # إزالة الرتب القديمة والتحديث التلقائي
        removed_roles_names = []
        for idx, r_id in SERVER_WARNING_CONFIGS["warn_roles"].items():
            old_role = interaction.guild.get_role(r_id)
            if old_role and old_role in member.roles and idx != warn_level:
                try:
                    await member.remove_roles(old_role, reason="Upgrading warning level automatically")
                    removed_roles_names.append(old_role.name)
                except:
                    pass

        assigned_role_text = "بدون رتبة تلقائية"
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"Warned by {interaction.user} | Reason: {reason}")
                    assigned_role_text = role.mention
                except discord.HTTPException as e:
                    assigned_role_text = f"فشل منح الرتبة: `{e}`"

        if member.id not in WARNINGS_DB:
            WARNINGS_DB[member.id] = []
        
        warning_record = {
            "level": warn_level,
            "name": warn_name,
            "reason": reason,
            "duration": duration,
            "moderator": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y/%m/%d %H:%M")
        }
        WARNINGS_DB[member.id].append(warning_record)
        total_user_warns = len(WARNINGS_DB[member.id])

        # ميزة العقوبات التلقائية الذكية (Auto-Punishment) عند التحذير الثالث
        auto_action_text = "لا توجد عقوبة تلقائية"
        if total_user_warns >= 3:
            try:
                timeout_duration = datetime.timedelta(hours=2)
                await member.timeout(timeout_duration, reason="Auto-punishment: Reached 3 warnings threshold")
                auto_action_text = "⚡ تم تطبيق (Timeout) تلقائي لمدة ساعتين لتجاوز الحد الأقصى للإنذارات!"
            except Exception as e:
                auto_action_text = f"⚠️ فشل تطبيق الإسكات التلقائي: {e}"

        embed = discord.Embed(
            title="⚠️ ╎ نـظـام الـتـحـذيـرات والـعـقـوبات الـمـركـزي",
            description=f"> تم تسجيل وإصدار تحذير رسمي بحق أحد المخالفين.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المخالف", value=f"> ｢ {member.mention} ｣", inline=False)
        embed.add_field(name="⚠️ ╎ نـوع الـتـحـذيـر", value=f"> ｢ {warn_name} ｣ (إجمالي: {total_user_warns})", inline=False)
        embed.add_field(name="⏳ ╎ الـمـدة", value=f"> ｢ {duration} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب", value=f"> ｢ {reason} ｣", inline=False)
        embed.add_field(name="🎖 ╎ الرتبة المرتبطة", value=f"> {assigned_role_text}", inline=False)
        if total_user_warns >= 3:
            embed.add_field(name="🚨 ╎ إجراء تلقائي", value=f"> {auto_action_text}", inline=False)

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="𝐙 𝐈 𝐔𝐎 ╎ Warnings Engine")
        
        sent_msg = await interaction.followup.send(embed=embed)

        # حفظ آيدي الرسالة في السجل لكي يمكن حذفه مستقبلاً عند تصفير السجل
        warning_record["log_message_id"] = sent_msg.id

        # إرسال لوج التحذير إلى القناة المخصصة تلقائياً إن وجدت
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

    # 2. أمر استعراض التحذيرات واللوحة (/warnings)
    @app_commands.command(name="warnings", description="[إدارة] فتح لوحة تحكم التحذيرات الشاملة أو عرض سجل عضو معين")
    @app_commands.describe(member="العضو المراد الاستعلام عنه (اتركه فارغاً لفتح اللوحة)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        if member:
            if member.id not in WARNINGS_DB or not WARNINGS_DB[member.id]:
                await interaction.response.send_message(f"✅ العضو {member.mention} لا يمتلك أي تحذيرات مسجلة.", ephemeral=True)
                return
            
            warns = WARNINGS_DB[member.id]
            desc = f"> سجّلات التحذيرات الخاصة بالعضو {member.mention} (الإجمالي: {len(warns)}):\n━━━━━━━━━━━━━━━━━━━━━\n"
            for idx, w in enumerate(warns, 1):
                desc += f"**{idx}.** المستوى: `{w['name']}`\n"
                desc += f" ✦ **السبب:** `{w['reason']}` | **المدة:** `{w['duration']}`\n\n"
                
            embed = discord.Embed(title=f"📋 ╎ تـحـذيـرات: {member.display_name}", description=desc, color=0x2B2D31)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="🛡️ ╎ لـوحـة تـحـكـم ونـظـام الـتـحـذيـرات الـمـركـزي",
                description="> أهلاً بك في لوحة تحكم التحذيرات المرنة لسيرفر 𝐙𝐈𝐔Ο.\n> اختر الإجراء المناسب من الأزرار الشاملة بالأسفل:",
                color=0x2B2D31
            )
            await interaction.response.send_message(embed=embed, view=AdvancedWarningsDashboard(self.bot), ephemeral=True)

    # 3. أمر إزالة التحذير المباشر (/unwarn)
    @app_commands.command(name="unwarn", description="[إدارة] إزالة آخر تحذير مسجل وسحب رتبته عن العضو بدقة")
    @app_commands.describe(member="العضو المراد إزالة التحذير عنه")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member):
        if member.id not in WARNINGS_DB or not WARNINGS_DB[member.id]:
            await interaction.response.send_message(f"❌ العضو {member.mention} ليس لديه تحذيرات لإزالتها.", ephemeral=True)
            return

        removed = WARNINGS_DB[member.id].pop()
        if not WARNINGS_DB[member.id]:
            del WARNINGS_DB[member.id]

        for r_id in SERVER_WARNING_CONFIGS["warn_roles"].values():
            role = interaction.guild.get_role(r_id)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Unwarn executed by {interaction.user}")
                except:
                    pass

        # محاولة حذف رسالة اللوج الخاصة بهذا التحذير إن وجدت في قناة اللوج
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
