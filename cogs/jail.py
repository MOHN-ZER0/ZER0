import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime

# ==============================================================================
# 🔒 قاعدة بيانات وقيم نظام السجن المتقدم والآمن
# ==============================================================================
JAIL_DB = {}  # لتخزين بيانات الأعضاء المسجونين {user_id: {"guild_id": id, "old_roles": [...], "duration": str, "reason": str, "moderator": str, "date": str, "un_timestamp": datetime}}

# [!] أيدي رتبة السجن الخاصة بسيرفر ZIUO
JAIL_ROLE_ID = 1546195501374898226 

class CompleteJailManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_jails.start()

    def cog_unload(self):
        self.check_expired_jails.cancel()

    # مهمة خلفية تلقائية تفحص انتهاء مدد السجن كل 60 ثانية وفكها تلقائياً
    @tasks.loop(seconds=60)
    async def check_expired_jails(self):
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            guild_id = guild.id
            for uid, data in list(JAIL_DB.items()):
                if data.get("guild_id") == guild_id and "un_timestamp" in data:
                    if now >= data["un_timestamp"]:
                        member = guild.get_member(uid)
                        if member:
                            jail_role = guild.get_role(JAIL_ROLE_ID)
                            if jail_role and jail_role in member.roles:
                                try:
                                    await member.remove_roles(jail_role, reason="Jail duration expired automatically")
                                    # استرجاع الرتب القديمة
                                    roles_to_restore = [guild.get_role(r_id) for r_id in data.get("old_roles", []) if guild.get_role(r_id)]
                                    if roles_to_restore:
                                        await member.add_roles(*roles_to_restore, reason="Restoring roles after jail expiration")
                                except Exception:
                                    pass
                        # حذف من القاعدة بعد انتهاء المدة
                        del JAIL_DB[uid]

    @check_expired_jails.before_loop
    async def before_check_jails(self):
        await self.bot.wait_until_ready()

    # ==========================================================================
    # 1. أمر سجن العضو (Jail Command)
    # ==========================================================================
    @app_commands.command(name="jail", description="[إدارة صارمة] سجن عضو مخالف وعزله عن رومات السيرفر لفترة محددة مع سحب رتبه")
    @app_commands.describe(
        member="العضو المراد إيداعه في الزنزانة",
        hours="عدد ساعات السجن (مثلاً: 1, 2, 12, 24...)",
        reason="سبب السجن بالتفصيل"
    )
    @app_commands.checks.has_permissions(moderate_members=True, manage_roles=True)
    async def jail(self, interaction: discord.Interaction, member: discord.Member, hours: int, reason: str = "لا يوجد سبب محدد"):
        if member.id in JAIL_DB:
            await interaction.response.send_message(f"⚠️ العضو {member.mention} مسجون بالفعل في السجلات ولا يمكن سجنه مرة أخرى!", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ لا يمكنك سجن نفسك يا أسطورة!", ephemeral=True)
            return

        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ لا يمكنك سجن البوت!", ephemeral=True)
            return

        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ خطأ أحمر! لا يمكنك سجن مالك السيرفر (Owner) أبداً!", ephemeral=True)
            return

        guild = interaction.guild
        jail_role = guild.get_role(JAIL_ROLE_ID)
        
        if not jail_role:
            await interaction.response.send_message("❌ خطأ: لم يتم العثور على رتبة السجن في السيرفر، تأكد من أيدي الرتبة.", ephemeral=True)
            return

        # حفظ الرتب القديمة للعضو (باستثناء @everyone والرتب المدارة مثل البوتات)
        old_role_ids = [r.id for r in member.roles if r.name != "@everyone" and not r.managed and r < guild.me.top_role]
        
        await interaction.response.defer(ephemeral=False)

        # إزالة الرتب القديمة ومنح رتبة السجن
        try:
            roles_to_remove = [r for r in member.roles if r.id in old_role_ids]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Jailed by {interaction.user} | Reason: {reason}")
            await member.add_roles(jail_role, reason=f"Jailed by {interaction.user} | Reason: {reason}")
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ فشل في تطبيق رتب السجن، تأكد أن رتبة البوت أعلى من الرتب المستهدفة: `{e}`", ephemeral=True)
            return

        un_time = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)
        
        # تسجيل البيانات في قاعدة البيانات الداخلية
        JAIL_DB[member.id] = {
            "guild_id": guild.id,
            "old_roles": old_role_ids,
            "duration": f"{hours} ساعة",
            "reason": reason,
            "moderator": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y/%m/%d %H:%M"),
            "un_timestamp": un_time
        }

        embed = discord.Embed(
            title="🔒 ╎ نـظـام الـسـجـن والـعـقـوبات الـمـركـزي 〣 ｢⚠️｣",
            description=f"> تم إيداع أحد المخالفين في زنزانة السيرفر وعزله عن الرومات.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x111111,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـعـضـو المسجون", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="⏱️ ╎ مـدة الـعـقـوبـة", value=f"> ｢ {hours} ساعة ｣", inline=False)
        embed.add_field(name="🛡️ ╎ المـسـؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ الـسـبـب", value=f"> ｢ {reason} ｣", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Secure Jail Engine")

        await interaction.followup.send(embed=embed)

    # ==========================================================================
    # 2. أمر فك سجن العضو (Unjail Command)
    # ==========================================================================
    @app_commands.command(name="unjail", description="[إدارة] فك السجن عن عضو مسجون واسترجاع رتبه السابقة فوراً")
    @app_commands.describe(
        member="العضو المراد فك سجنه وإرجاع رتبه",
        reason="سبب رفع السجن (اختياري)"
    )
    @app_commands.checks.has_permissions(moderate_members=True, manage_roles=True)
    async def unjail(self, interaction: discord.Interaction, member: discord.Member, reason: str = "لم يتم ذكر سبب"):
        if member.id not in JAIL_DB:
            await interaction.response.send_message(f"❌ العضو {member.mention} ليس مسجوناً في السجلات حالياً!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        guild = interaction.guild
        data = JAIL_DB.pop(member.id)
        jail_role = guild.get_role(JAIL_ROLE_ID)

        try:
            if jail_role and jail_role in member.roles:
                await member.remove_roles(jail_role, reason=f"Unjailed by {interaction.user} | Reason: {reason}")
            
            # استرجاع الرتب القديمة
            restored_roles = [guild.get_role(r_id) for r_id in data.get("old_roles", []) if guild.get_role(r_id)]
            if restored_roles:
                await member.add_roles(*restored_roles, reason=f"Restored roles after unjail by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء استرجاع الرتب: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔓 ╎ فـك سـجـن عـضـو (Unjail) 〣 ｢✅｣",
            description=f"> تم رفع العقوبة بنجاح وإعادة رتب العضو الأساسية.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ العضو المُفك عنه السجن", value=f"> ｢ {member.mention} ｣\n> (`{member.id}`)", inline=False)
        embed.add_field(name="🛡️ ╎ المسؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        embed.add_field(name="📝 ╎ السبب", value=f"> ｢ {reason} ｣", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Z I UO - MC Server ✦ Unjail Department")

        await interaction.followup.send(embed=embed)

    # ==========================================================================
    # 3. أمر استعراض السجون النشطة (Jails Command المطور والمدمج)
    # ==========================================================================
    @app_commands.command(name="jails", description="[إدارة] عرض قائمة الأعضاء المسجونين حالياً، مدد العقوبات، الوقت المتبقي والمسؤولين")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def jails(self, interaction: discord.Interaction):
        if not JAIL_DB:
            await interaction.response.send_message("🌟 سجل نظيف! لا توجد أي حالات سجن نشطة حالياً في السيرفر.", ephemeral=True)
            return
        
        desc = "> سجل الأعضاء المسجونين والعقوبات النشطة حالياً:\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for uid, data in JAIL_DB.items():
            member = interaction.guild.get_member(uid)
            m_name = member.mention if member else f"عضو مغادر (`{uid}`)"
            
            # حساب الوقت المتبقي لفك السجن
            time_left = "قريباً جداً"
            if "un_timestamp" in data:
                delta = data["un_timestamp"] - datetime.datetime.utcnow()
                total_secs = int(delta.total_seconds())
                if total_secs > 0:
                    hrs = total_secs // 3600
                    mins = (total_secs % 3600) // 60
                    time_left = f"{hrs} ساعة و {mins} دقيقة"

            desc += f"👤 **{m_name}**\n"
            desc += f" ✦ **المدة الكلية:** `{data['duration']}` | ⏳ **المتبقي:** `{time_left}`\n"
            desc += f" ✦ **المسؤول:** {data['moderator']} | التاريخ: `{data['date']}`\n"
            desc += f" ✦ **السبب:** `{data['reason']}`\n\n"
            
        embed = discord.Embed(
            title="🔒 ╎ قـائـمـة الـعـضـاء الـمـسـجونـين 〣 ｢Z I UO｣",
            description=desc,
            color=0x111111,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Enterprise Jail Management System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CompleteJailManagementCog(bot))
