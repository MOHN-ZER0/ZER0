import discord
from discord import app_commands
from discord.ext import commands
import datetime

# ==============================================================================
# ⚠️ جدول رتب التحذيرات المترتبة من الأول للسابع بالأيديهات المحددة
# ==============================================================================
WARN_ROLES = [
    {"level": 1, "id": 1543880992069132370, "name": "التحذير الأول ✦ [1]"},
    {"level": 2, "id": 1543880990668095610, "name": "التحذير الثاني ✦ [2]"},
    {"level": 3, "id": 1546194848342610021, "name": "التحذير الثالث ✦ [3]"},
    {"level": 4, "id": 1546194915938279464, "name": "التحذير الرابع ✦ [4]"},
    {"level": 5, "id": 1546195079440502814, "name": "التحذير الخامس ✦ [5]"},
    {"level": 6, "id": 1546195378175746188, "name": "التحذير السادس ✦ [6]"},
    {"level": 7, "id": 1546195501374898226, "name": "التحذير السابع ✦ [7]"},
]

WARNINGS_DB = {} # قاعدة بيانات مؤقتة لتخزين سجل تحذيرات الأعضاء {user_id: [{"level": int, "role_name": str, "reason": str, "moderator": str, "date": str}]}

# ==============================================================================
# 🎛️ واجهة لوحة تحكم التحذيرات التفاعلية المتقدمة
# ==============================================================================
class AdvancedWarningsDashboard(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="📋 عرض جميع المحذرين", style=discord.ButtonStyle.primary, emoji="📊", custom_id="ziuo_all_warns_btn")
    async def show_all_warnings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not WARNINGS_DB:
            await interaction.response.send_message("🌟 سجل نظيف! لا توجد أي تحذيرات نشطة مسجلة في السيرفر حالياً.", ephemeral=True)
            return
        
        desc = "> 📋 **قائمة المخالفين وسجلات التحذيرات النشطة:**\n━━━━━━━━━━━━━━━━━━━━━\n"
        for uid, warns in WARNINGS_DB.items():
            member = interaction.guild.get_member(uid)
            m_name = member.mention if member else f"عضو مغادر (`{uid}`)"
            desc += f"👤 **{m_name}** ── ｢ إجمالي الإنذارات: **{len(warns)}** ｣\n"
            for w in warns:
                desc += f" └ ⚡ `{w['role_name']}` | السبب: `{w['reason']}`\n"
            desc += "\n"
        
        if len(desc) > 4000:
            desc = desc[:3996] + "..."

        embed = discord.Embed(
            title="📊 ╎ سـجـل تـحـذيـرات الأعـضـاء الـشـامـل 〣 ｢Z I UO｣",
            description=desc,
            color=0x111111,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Enterprise Management System ✦ Warnings Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🧹 تنظيف السجلات الفارغة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="ziuo_clean_warns_btn")
    async def clean_database(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط (Administrator)!", ephemeral=True)
            return
        
        count = 0
        for uid in list(WARNINGS_DB.keys()):
            if not WARNINGS_DB[uid]:
                del WARNINGS_DB[uid]
                count += 1

        await interaction.response.send_message(f"✅ تم فحص وتنظيف قاعدة البيانات بنجاح! (تمت إزالة سجلات فارغة عديمة الحاجه: {count})", ephemeral=True)


# ==============================================================================
# 🛡️️ Cog إدارة التحذيرات الخارق والمدمج
# ==============================================================================
class UltimateWarningSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================================================
    # 1. أمر إعطاء التحذير (Warn Command)
    # ==========================================================================
    @app_commands.command(name="warn", description="[إدارة] إعطاء تحذير رسمي متطور لعضو واختيار رتبة التحذير من الأول للسابع مع السبب")
    @app_commands.describe(
        member="العضو المراد تحذيره",
        warn_level="مستوى التحذير المطلوب (من 1 إلى 7)",
        reason="سبب إصدار التحذير بالتفصيل"
    )
    @app_commands.choices(warn_level=[
        app_commands.Choice(name="التحذير الأول ✦ [1]", value=1),
        app_commands.Choice(name="التحذير الثاني ✦ [2]", value=2),
        app_commands.Choice(name="التحذير الثالث ✦ [3]", value=3),
        app_commands.Choice(name="التحذير الرابع ✦ [4]", value=4),
        app_commands.Choice(name="التحذير الخامس ✦ [5]", value=5),
        app_commands.Choice(name="التحذير السادس ✦ [6]", value=6),
        app_commands.Choice(name="التحذير السابع ✦ [7]", value=7),
    ])
    @app_commands.checks.has_permissions(manage_roles=True, moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, warn_level: int, reason: str):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ لا يمكنك تحذير نفسك يا أسطورة!", ephemeral=True)
            return

        if member.bot:
            await interaction.response.send_message("❌ لا يمكنك تحذير بوت في السيرفر!", ephemeral=True)
            return

        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ خطأ أحمر! لا يمكنك تحذير مالك السيرفر (Owner) أبداً!", ephemeral=True)
            return

        selected_warn = next((r for r in WARN_ROLES if r["level"] == warn_level), None)
        if not selected_warn:
            await interaction.response.send_message("❌ خطأ: مستوى التحذير المختار غير صالح.", ephemeral=True)
            return

        role = interaction.guild.get_role(selected_warn["id"])
        if not role:
            await interaction.response.send_message("❌ خطأ: لم يتم العثور على رتبة التحذير المطابقة في رتب السيرفر، تأكد من الأيديهات.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        # إزالة رتب التحذير القديمة لمنع تداخل الرتب وتنظيم الهرمية
        removed_roles_names = []
        for w_info in WARN_ROLES:
            old_role = interaction.guild.get_role(w_info["id"])
            if old_role and old_role in member.roles and old_role.id != role.id:
                try:
                    await member.remove_roles(old_role, reason="Upgrading or changing warning level automatically")
                    removed_roles_names.append(old_role.name)
                except:
                    pass

        # منح رتبة التحذير الجديدة
        try:
            await member.add_roles(role, reason=f"Warned by {interaction.user} | Reason: {reason}")
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ فشل في منح الرتبة للعضو، تأكد أن رتبة البوت أعلى من رتبة التحذير: `{e}`", ephemeral=True)
            return
        
        # حفظ السجل في قاعدة البيانات
        if member.id not in WARNINGS_DB:
            WARNINGS_DB[member.id] = []
        
        warning_record = {
            "level": warn_level,
            "role_name": selected_warn["name"],
            "reason": reason,
            "moderator": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y/%m/%d %H:%M")
        }
        WARNINGS_DB[member.id].append(warning_record)

        total_user_warns = len(WARNINGS_DB[member.id])

        # ميزة ذكية إضافية: تنبيه إذا وصل لعدد تحذيرات خطير (مثلاً 3 أو أكثر)
        auto_action_note = ""
        if warn_level >= 3:
            auto_action_note = "⚠️ **تنبيه إداري:** العضو وصل لمستوى متقدم من التحذيرات ويستوجب مراقبة مشددة أو عقوبة إضافية!"

        embed = discord.Embed(
            title="⚠️ ╎ نـظـام الـتـحـذيـرات والـعـقـوبات الـمـركـزي 〣 ｢🛡️｣",
            description=f"> تم تسجيل وإصدار تحذير رسمي بحق أحد المخالفين.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المخالف", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="⚠️ ╎ مـسـتـوى الـتـحـذيـر", value=f"> ｢ {selected_warn['name']} ｣ (إجمالي: {total_user_warns})", inline=False)
        embed.add_field(name="🛡️ ╎ المـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب", value=f"> ｢ {reason} ｣", inline=False)
        
        if removed_roles_names:
            embed.add_field(name="🔄 ╎ التحديثات التلقائية", value=f"> تم إزالة رتب التحذير القديمة: `{' ، '.join(removed_roles_names)}`", inline=False)
        
        if auto_action_note:
            embed.add_field(name="🚨 ╎ ملاحظة النظام", value=f"> {auto_action_note}", inline=False)

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Enterprise Warnings Engine")
        
        await interaction.followup.send(embed=embed)

    # ==========================================================================
    # 2. أمر استعراض التحذيرات أو لوحة التحكم (Warnings Command)
    # ==========================================================================
    @app_commands.command(name="warnings", description="[إدارة] عرض سجل التحذيرات الشامل لعضو معين أو فتح لوحة التحكم الرئيسية")
    @app_commands.describe(member="العضو المراد الاستعلام عن تحذيراته (اتركه فارغاً لفتح اللوحة التفاعلية)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        if member:
            if member.id not in WARNINGS_DB or not WARNINGS_DB[member.id]:
                await interaction.response.send_message(f"✅ العضو {member.mention} لا يمتلك أي تحذيرات مسجلة في السجلات حالياً.", ephemeral=True)
                return
            
            warns = WARNINGS_DB[member.id]
            desc = f"> سجّلات التحذيرات الخاصة بالعضو {member.mention} (الإجمالي: {len(warns)}):\n━━━━━━━━━━━━━━━━━━━━━\n"
            for idx, w in enumerate(warns, 1):
                desc += f"**{idx}.** المستوى: `{w['role_name']}`\n"
                desc += f" ✦ **السبب:** `{w['reason']}`\n"
                desc += f" ✦ **المسؤول:** {w['moderator']} | التاريخ: `{w['date']}`\n\n"
                
            embed = discord.Embed(
                title=f"📋 ╎ تـحـذيـرات العـضـو: {member.display_name} 〣 ｢⚡｣",
                description=desc,
                color=0x2b2d31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Z I UO Warnings Archive System")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="🛡️ ╎ لـوحـة تـحـكـم ونـظـام الـتـحـذيـرات الـمـركـزي 〣 ｢Z I UO｣",
                description="> أهلاً بك يا أسطورة في لوحة إدارة التحذيرات المتقدمة لسيرفر ZIUO.\n> استخدم الأزرار بالأسفل لتصفح وتقييم الحالات بكل سهولة وأمان.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Z I UO Enterprise Global Management System")
            await interaction.response.send_message(embed=embed, view=AdvancedWarningsDashboard(self.bot), ephemeral=True)

    # ==========================================================================
    # 3. أمر إزالة التحذير (Unwarn Command)
    # ==========================================================================
    @app_commands.command(name="unwarn", description="[إدارة] إزالة آخر تحذير مسجل وسحب رتبته عن العضو بدقة")
    @app_commands.describe(member="العضو المراد إزالة التحذير عنه")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member):
        if member.id not in WARNINGS_DB or not WARNINGS_DB[member.id]:
            await interaction.response.send_message(f"❌ العضو {member.mention} ليس لديه أي تحذيرات مسجلة لإزالتها.", ephemeral=True)
            return

        removed = WARNINGS_DB[member.id].pop()
        
        # إذا تم تفريغ قائمة تحذيرات العضو تماماً، نمسح أيديه من القاعدة لتوفير المساحة
        if not WARNINGS_DB[member.id]:
            del WARNINGS_DB[member.id]

        # سحب رتبة التحذير المرتبطة من العضو
        for w_info in WARN_ROLES:
            role = interaction.guild.get_role(w_info["id"])
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Unwarn executed by {interaction.user}")
                except:
                    pass

        await interaction.response.send_message(f"✅ **تم بنجاح!** تم إزالة آخر تحذير مسجل بحق العضو {member.mention} (التحذير كان: **{removed['role_name']}**).", ephemeral=False)

async def setup(bot):
    await bot.add_cog(UltimateWarningSystemCog(bot))
