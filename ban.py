import discord
from discord import app_commands
from discord.ext import commands
import datetime

class CompleteBanManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --------------------------------------------------------------------------
    # 1. أمر الحظر النهائي (Ban)
    # --------------------------------------------------------------------------
    @app_commands.command(name="ban", description="[إدارة صارمة] حظر عضو نهائياً مع فحص الرتب، تنبيه خاص، ومسح الرسائل")
    @app_commands.describe(
        member="العضو المراد حظره نهائياً من السيرفر",
        reason="السبب المخصص لحالة الحظر (اختياري)",
        delete_messages="حذف رسائل العضو المحظور لآخر (عدد الأيام من 0 إلى 7)"
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self, 
        interaction: discord.Interaction, 
        member: discord.Member, 
        reason: str = "لا يوجد سبب محدد",
        delete_messages: int = 1
    ):
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ لا يمكنك حظر نفسك يا أسطورة!", ephemeral=True)
            return

        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ لا يمكنك حظر البوت باستخدام هذا الأمر!", ephemeral=True)
            return

        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ خطأ أحمر قاطع! لا يمكنك حظر مالك السيرفر (Owner) نهائياً!", ephemeral=True)
            return

        if interaction.user.id != interaction.guild.owner_id:
            if interaction.user.top_role <= member.top_role:
                await interaction.response.send_message("❌ لا يمكنك حظر هذا العضو لأن رتبته تساوي أو أعلى من رتبتك!", ephemeral=True)
                return

        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ لا أستطيع حظر هذا العضو لأن رتبته أعلى من رتبة البوت أو تساويه!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        dm_sent = True
        try:
            dm_embed = discord.Embed(
                title=f"⛔ ╎ تـم حـظـرك نهائياً من سـيـرفـر {interaction.guild.name}",
                description=f"> لقد تم اتخاذ إجراء صارم بحقك وحظرك نهائياً من خوادم مجتمعنا.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x330000,
                timestamp=datetime.datetime.utcnow()
            )
            dm_embed.add_field(name="🛡️ ╎ المسؤول المباشر", value=f"> ｢ {interaction.user.name} ｣", inline=False)
            dm_embed.add_field(name="📝 ╎ سبب الحظر", value=f"> ｢ {reason} ｣", inline=False)
            dm_embed.set_footer(text="Z I UO - MC Server ✦ Security & Ban Department")
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            dm_sent = False

        try:
            days = max(0, min(delete_messages, 7))
            await member.ban(reason=f"Banned by {interaction.user} ({interaction.user.id}) | Reason: {reason}", delete_message_days=days)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء تنفيذ الحظر: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="⛔ ╎ تـقـريـر حـظـر نـهـائـي (Banned) 〣 ｢❌｣",
            description=f"> تم حظر العضو نهائياً من خوادم ZIUO - MC لحماية أمان السيرفر.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x330000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المحـظـور", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="🛡️ ╎ الـمـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ السـبـب المـحـدد", value=f"> ｢ {reason} ｣", inline=False)
        embed.add_field(name="🧹 ╎ رسائل العضو المحذوفة", value=f"> ｢ مسح رسائل آخر {days} أيام 🗑️ ｣", inline=True)
        embed.add_field(name="📬 ╎ حالة التنبيه الخاص", value=f"> ｢ {'تم إرسال تنبيه بالخاص ✉️' if dm_sent else 'الخاص مغلق 🔕'} ｣", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Advanced Ban System")
        
        await interaction.followup.send(embed=embed)

    # --------------------------------------------------------------------------
    # 2. أمر فك الحظر (Unban) باستخدام ID العضو
    # --------------------------------------------------------------------------
    @app_commands.command(name="unban", description="[إدارة] رفع الحظر عن عضو مسبقاً باستخدام آي دي (ID) الحساب الخاص به")
    @app_commands.describe(
        user_id="الآي دي (User ID) الخاص بالعضو المراد فك الحظر عنه",
        reason="سبب رفع الحظر (اختياري)"
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "لم يتم ذكر سبب"):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # تحويل الـ ID لعدد صحيح
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("❌ آي دي (ID) العضو غير صالح، تأكد من كتابة أرقام صحيحة!", ephemeral=True)
            return

        try:
            # جلب قائمة البانات والبحث عن المستخدم
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=uid))
            user = ban_entry.user

            await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user} | Reason: {reason}")

            embed = discord.Embed(
                title="🔓 ╎ رَفـع الحـظـر (Unbanned) 〣 ｢✅｣",
                description=f"> تم رفع الحظر بنجاح وإعادة السماح للعضو بالدخول للسيرفر.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="👤 ╎ العضو المُفك عنه الحظر", value=f"> ｢ {user.name} ｣\n> (`{user.id}`)", inline=False)
            embed.add_field(name="🛡️ ╎ المسؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📝 ╎ السبب", value=f"> ｢ {reason} ｣", inline=False)
            embed.set_thumbnail(url=user.display_avatar.url if user.avatar else None)
            embed.set_footer(text="Z I UO - MC Server ✦ Unban Department")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.NotFound:
            await interaction.followup.send("❌ هذا العضو غير محظور أساساً، أو أن الآي دي (ID) الذي كتبته خاطئ!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء محاولة فك الحظر: `{e}`", ephemeral=True)

    # --------------------------------------------------------------------------
    # 3. أمر عرض قائمة المحظورين (BanList)
    # --------------------------------------------------------------------------
    @app_commands.command(name="banlist", description="[إدارة] عرض قائمة بأسماء وآي دي الأعضاء المحظورين حالياً في السيرفر")
    @app_commands.checks.has_permissions(ban_members=True)
    async def banlist(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        banned_users = []
        async for ban_entry in interaction.guild.bans(limit=20):  # جلب أول 20 بان كحد أقصى لمنع تعليق البوت
            banned_users.append(f"• **{ban_entry.user.name}** (`{ban_entry.user.id}`)\n  └ *السبب:* {ban_entry.reason or 'لا يوجد سبب'}")

        if not banned_users:
            await interaction.followup.send("🌟 سجل نظيف! لا يوجد أي أعضاء محظورين في هذا السيرفر حالياً.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 ╎ قـائـمـة الأعـضـاء المحـظـورين 〣 ｢🔒｣",
            description=f"> إجمالي الأعضاء المحظورين في القائمة (حتى 20 شخصاً):\n━━━━━━━━━━━━━━━━━━━━━\n\n" + "\n\n".join(banned_users),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO - MC Server ✦ Ban List System")

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CompleteBanManagementCog(bot))
