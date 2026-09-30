import discord
from discord import app_commands
from discord.ext import commands
import datetime

class UserInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="[معلومات] عرض ملف شخصي وإحصائيات شاملة ومفصلة لأبعد الحدود لأي عضو")
    @app_commands.describe(member="العضو المراد استعراض معلوماته (اتركه فارغاً لمعلوماتك الشخصية)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        m = member or interaction.user
        await interaction.response.defer(ephemeral=False)

        # جلب معلومات الحساب والبانر (إن وجد)
        try:
            user_full = await self.bot.fetch_user(m.id)
            banner_url = user_full.banner.url if user_full.banner else None
        except Exception:
            banner_url = None

        # تنسيق الرتب (باستثناء رتبة @everyone)
        roles = [role.mention for role in reversed(m.roles[1:])]
        roles_str = " ".join(roles) if roles else "لا توجد رتب"
        if len(roles_str) > 1024:
            # إذا كانت الرتب كثيرة جداً، نعرض العدد ونبذة مختصرة
            roles_str = f"عدد الرتب كبير جداً: ｢ {len(roles)} ｣ رتبة"

        # تواريخ الانضمام والإنشاء مع حساب الفترات الزمنية بدقة
        now = datetime.datetime.now(datetime.timezone.utc)
        
        created_at = m.created_at
        created_date_str = created_at.strftime("%Y/%m/%d")
        created_age = now - created_at
        created_age_str = f"{created_age.days // 365} سنة، {(created_age.days % 365) // 30} شهر"

        joined_at = m.joined_at
        joined_date_str = joined_at.strftime("%Y/%m/%d") if joined_at else "غير معروف"
        if joined_at:
            joined_age = now - joined_at
            joined_age_str = f"{joined_age.days // 365} سنة، {(joined_age.days % 365) // 30} شهر ({joined_age.days} يوم)"
        else:
            joined_age_str = "غير معروف"

        # تحديد نوع الحساب (بشري أو بوت)
        account_type = "🤖 بوت نظام (Bot)" if m.bot else "👤 عضو بشري (Human)"

        embed = discord.Embed(
            title=f"👤 ╎ مـعـلـومـات الـعـضـو: {m.display_name} 〣 ｢🛡️｣",
            description=f"> الملف الشخصي والإحصائيات الكاملة والعميقة داخل سيرفر ZIUO.\n━━━━━━━━━━━━━━━━━━━━━",
            color=m.color if m.color.value != 0 else 0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.set_thumbnail(url=m.display_avatar.url)
        if banner_url:
            embed.set_image(url=banner_url)
            
        # 1. المعلومات الهوية
        embed.add_field(
            name="🆔 ╎ الـهـويـة والأسـمـاء",
            value=(
                f"> **الاسم الكامل:** ｢ {m} ｣\n"
                f"> **الأيدي (ID):** ｢ `{m.id}` ｣\n"
                f"> **نوع الحساب:** ｢ {account_type} ｣\n"
                f"> **اللقب في السيرفر:** ｢ {m.nick or 'بدون لقب'} ｣"
            ),
            inline=False
        )

        # 2. التواريخ والأعمار
        embed.add_field(
            name="📅 ╎ تـواريـخ الإنـشـاء والإنـضـمـام",
            value=(
                f"> **تاريخ إنشاء الحساب:** ｢ {created_date_str} ｣\n"
                f"> **عمر الحساب:** ｢ {created_age_str} ｣\n"
                f"> **تاريخ الانضمام للسيرفر:** ｢ {joined_date_str} ｣\n"
                f"> **مدة التواجد بالسيرفر:** ｢ {joined_age_str} ｣"
            ),
            inline=False
        )

        # 3. الرتب والصلاحيات
        embed.add_field(
            name=f"🎭 ╎ الـرتب المـمنوحة (إجمالي: {len(roles)})",
            value=f"> {roles_str}",
            inline=False
        )
        
        embed.set_footer(text=f"Z I UO - MC Server ✦ Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UserInfoCog(bot))
