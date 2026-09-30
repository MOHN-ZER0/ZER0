import discord
from discord import app_commands
from discord.ext import commands
import datetime

class CompleteTimeoutManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------------------------------------------------------------------------
    # 1. أمر إعطاء التايم آウト (Timeout)
    # --------------------------------------------------------------------------
    @app_commands.command(name="timeout", description="[إدارة صارمة] تقييد وإسكات عضو لفترة زمنية محددة مع فحص الرتب والتنبيه الخاص")
    @app_commands.describe(
        member="العضو المراد عمل تايم آウト له",
        minutes="عدد الدقائق (مثال: 5 للدقائق، 60 لساعة، الخ)",
        reason="السبب المخصص للإسكات (اختياري)"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(
        self, 
        interaction: discord.Interaction, 
        member: discord.Member, 
        minutes: int, 
        reason: str = "لا يوجد سبب محدد"
    ):
        if minutes < 1:
            await interaction.response.send_message("❌ يجب أن تكون المدة أكثر من دقيقة واحدة على الأقل!", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ لا يمكنك إعطاء تايم آウト لنفسك يا أسطورة!", ephemeral=True)
            return

        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ لا يمكنك إعطاء تايم آウト للبوت!", ephemeral=True)
            return

        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ خطأ أحمر! لا يمكنك عمل تايم آウト لمالك السيرفر (Owner) أبداً!", ephemeral=True)
            return

        # فحص رتبة الإداري والبوت مقارنة بالمستهدف
        if interaction.user.id != interaction.guild.owner_id:
            if interaction.user.top_role <= member.top_role:
                await interaction.response.send_message("❌ لا يمكنك عمل تايم آウト لهذا العضو لأن رتبته تساوي أو أعلى من رتبتك!", ephemeral=True)
                return

        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ لا أستطيع تقييد هذا العضو لأن رتبته أعلى من رتبة البوت أو تساويه!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        # حساب وقت الانتهاء وإرسال تنبيه بالخاص
        duration = datetime.timedelta(minutes=minutes)
        dm_sent = True
        try:
            dm_embed = discord.Embed(
                title=f"🤐 ╎ تـم إسـكـاتـك مؤقتاً في سـيـرفـر {interaction.guild.name}",
                description=f"> لقد تم تقييد حركتك ومنعك مؤقتاً من إرسال الرسائل.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.utcnow()
            )
            dm_embed.add_field(name="⏱️ ╎ الـمـدة", value=f"> ｢ {minutes} ｣ دقيقة", inline=False)
            dm_embed.add_field(name="🛡️ ╎ المسؤول", value=f"> ｢ {interaction.user.name} ｣", inline=False)
            dm_embed.add_field(name="📝 ╎ السبب", value=f"> ｢ {reason} ｣", inline=False)
            dm_embed.set_footer(text="Z I UO - MC Server ✦ Timeout Department")
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            dm_sent = False

        try:
            await member.timeout(duration, reason=f"Timeout by {interaction.user} | Reason: {reason}")
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء تنفيذ التايم آウト: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🤐 ╎ تـقـريـر إسـكـات (TimeOut) 〣 ｢⚠️｣",
            description=f"> تم تقييد حركة العضو مؤقتاً ومنعه من إرسال الرسائل أو التحدث.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0xCC0000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المـقـيـد", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="⏱ ╎ الـمـدة", value=f"> ｢ {minutes} ｣ دقيقة", inline=False)
        embed.add_field(name="🛡️ ╎ الـمـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب", value=f"> ｢ {reason} ｣", inline=False)
        embed.add_field(name="📬 ╎ حالة التنبيه", value=f"> ｢ {'تم إرسال تنبيه بالخاص ✉️' if dm_sent else 'الخاص مغلق 🔕'} ｣", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Timeout System")
        
        await interaction.followup.send(embed=embed)

    # --------------------------------------------------------------------------
    # 2. أمر رفع التايم آウト (Untimeout)
    # --------------------------------------------------------------------------
    @app_commands.command(name="untimeout", description="[إدارة] إلغاء الإسكات ورفع القيود عن عضو محدد مسبقاً")
    @app_commands.describe(
        member="العضو المراد فك التايم آウト عنه",
        reason="سبب رفع الإسكات (اختياري)"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(
        self, 
        interaction: discord.Interaction, 
        member: discord.Member, 
        reason: str = "لم يتم ذكر سبب"
    ):
        if not member.is_timed_out():
            await interaction.response.send_message("❌ هذا العضو ليس عليه أي تايم آウト أساساً!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        try:
            await member.timeout(None, reason=f"Un-timed out by {interaction.user} | Reason: {reason}")
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء رفع التايم آウト: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔊 ╎ فـك الإسـكـات (Un-TimeOut) 〣 ｢✅｣",
            description=f"> تم رفع القيود وعودة العضو للحديث بشكل طبيعي في السيرفر.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x00CC66,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المُفك عنه القيود", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="🛡️ ╎ المسؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ السبب", value=f"> ｢ {reason} ｣", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Moderation System")
        
        await interaction.followup.send(embed=embed)

    # --------------------------------------------------------------------------
    # 3. أمر عرض قائمة المقيدين حالياً (Timeouts List)
    # --------------------------------------------------------------------------
    @app_commands.command(name="timeouts", description="[إدارة] عرض قائمة بأسماء الأعضاء الذين عليهم تايم آウト نشط حالياً")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeouts(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        timed_out_members = []
        # المرور على أعضاء السيرفر والتحقق من وجود تايم آウト نشط
        for member in interaction.guild.members:
            if member.is_timed_out():
                # حساب وقت انتهاء التايم آウト وتنسيقه
                time_left = discord.utils.format_dt(member.timed_out_until, style="R")
                timed_out_members.append(f"• **{member.mention}** (`{member.id}`)\n  └ *ينتهي:* {time_left}")

        if not timed_out_members:
            await interaction.followup.send("🌟 سجل نظيف! لا يوجد أي أعضاء معاقبين بتايم آウト حالياً في السيرفر.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🤐 ╎ قـائـمـة المـقـيـديـن حالياً (Active Timeouts) 〣 ｢⚠️｣",
            description=f"> الأعضاء الخاضعون لعقوبة التايم آウト النشطة في الوقت الحالي:\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(timed_out_members[:20]),
            color=0xCC0000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO - MC Server ✦ Timeouts Monitor")

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CompleteTimeoutManagementCog(bot))
