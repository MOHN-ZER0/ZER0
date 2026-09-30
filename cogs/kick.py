import discord
from discord import app_commands
from discord.ext import commands
import datetime

class CompleteKickManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------------------------------------------------------------------------
    # 1. أمر الطرد المتقدم (Kick)
    # --------------------------------------------------------------------------
    @app_commands.command(name="kick", description="[إدارة متقدمة] طرد عضو من السيرفر مع فحص الرتب، تنبيه خاص، وتوثيق التقرير")
    @app_commands.describe(
        member="العضو المراد طرده من السيرفر",
        reason="السبب المخصص لعملية الطرد (اختياري)"
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self, 
        interaction: discord.Interaction, 
        member: discord.Member, 
        reason: str = "لا يوجد سبب محدد"
    ):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ لا يمكنك طرد نفسك يا أسطورة!", ephemeral=True)
            return

        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ لا يمكنك طرد البوت باستخدام هذا الأمر!", ephemeral=True)
            return

        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ خطأ أحمر! لا يمكنك طرد مالك السيرفر (Owner) أبداً!", ephemeral=True)
            return

        if interaction.user.id != interaction.guild.owner_id:
            if interaction.user.top_role <= member.top_role:
                await interaction.response.send_message("❌ لا يمكنك طرد هذا العضو لأن رتبته تساوى أو أعلى من رتبتك!", ephemeral=True)
                return

        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ لا أستطيع طرد هذا العضو لأن رتبته أعلى من رتبة البوت أو تساويه!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        dm_sent = True
        try:
            dm_embed = discord.Embed(
                title=f"🚨 ╎ تـم طـردك مـن سـيـرفـر {interaction.guild.name}",
                description=f"> لقد تم اتخاذ إجراء تأديبي بحقك وطرْدك من السيرفر.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x990000,
                timestamp=datetime.datetime.utcnow()
            )
            dm_embed.add_field(name="🛡️ ╎ المسؤول المباشر", value=f"> ｢ {interaction.user.name} ｣", inline=False)
            dm_embed.add_field(name="📝 ╎ السبب", value=f"> ｢ {reason} ｣", inline=False)
            dm_embed.set_footer(text="Z I UO - MC Server ✦ Moderation Department")
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            dm_sent = False

        try:
            await member.kick(reason=f"Kicked by {interaction.user} ({interaction.user.id}) | Reason: {reason}")
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ غير متوقع أثناء الطرد: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🚨 ╎ تـقـريـر طـرد عـضـو (Kicked) 〣 ｢⚡｣",
            description=f"> تم اتخاذ الإجراء التأديبي بنجاح واستبعاد العضو من السيرفر.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x990000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المـطـرود", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="🛡 ╎ الـمـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب المـحـدد", value=f"> ｢ {reason} ｣", inline=False)
        embed.add_field(name="📬 ╎ حالة التنبيه الخاص", value=f"> ｢ {'تم إرسال تنبيه بالخاص ✉️' if dm_sent else 'الخاص مغلق 🔕'} ｣", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Advanced Kick System")
        
        await interaction.followup.send(embed=embed)

    # --------------------------------------------------------------------------
    # 2. أمر عرض سجلات الطرد الأخيرة (Kick Logs)
    # --------------------------------------------------------------------------
    @app_commands.command(name="kicklogs", description="[إدارة] عرض سجل آخر عمليات الطرد (Kick) التي تمت في السيرفر عبر الـ Audit Logs")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kicklogs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            kick_entries = []
            # جلب آخر عمليات الطرد من سجل التدقيق (Audit Logs) للسيرفر
            async for entry in interaction.guild.audit_logs(limit=10, action=discord.AuditLogAction.kick):
                target = entry.target
                moderator = entry.user
                reason = entry.reason or "لا يوجد سبب محدد"
                time_ago = discord.utils.format_dt(entry.created_at, style="R") # عرض الوقت المنقضي بشكل احترافي
                
                kick_entries.append(
                    f"• **العضو:** {target} (`{target.id}`)\n"
                    f"  └ **بواسطة:** {moderator.mention}\n"
                    f"  └ **السبب:** {reason}\n"
                    f"  └ **الوقت:** {time_ago}"
                )

            if not kick_entries:
                await interaction.followup.send("🌟 سجل نظيف! لا توجد أي عمليات طرد مسجلة حديثاً في هذا السيرفر.", ephemeral=True)
                return

            embed = discord.Embed(
                title="📋 ╎ سـجـل عـمـليـات الطـرد الأخـيـرة 〣 ｢⚡｣",
                description=f"> آخر عمليات الطرد المسجلة في سجل تدقيق السيرفر (Audit Logs):\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(kick_entries),
                color=0x990000,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Z I UO - MC Server ✦ Kick Audit Logs")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("❌ البوت لا يمتلك صلاحية قراءة سجلات السيرفر (`View Audit Log`)!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء جلب السجلات: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CompleteKickManagementCog(bot))
