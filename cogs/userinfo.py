import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# تحميل متغيرات البيئة للاتصال بقاعدة البيانات السحابية
load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI")

# الاتصال بقاعدة بيانات MongoDB السحابية العامة
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["Global_Bot_DB"]
analytics_col = db["user_info_analytics"]

def log_userinfo_usage(guild_id: int, guild_name: str, requester_id: int, target_user_id: int):
    """حفظ إحصائيات استخدام أمر userinfo في قاعدة البيانات السحابية"""
    try:
        analytics_col.update_one(
            {"_id": str(guild_id)},
            {
                "$set": {
                    "guild_name": guild_name,
                    "last_used_at": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                },
                "$inc": {"total_command_uses": 1},
                "$push": {
                    "usage_history": {
                        "requester_id": requester_id,
                        "target_user_id": target_user_id,
                        "used_at": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"[MongoDB Error] UserInfo Logging Failed: {e}")

class UserInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="[معلومات] عرض ملف شخصي وإحصائيات شاملة ومفصلة لأبعد الحدود لأي عضو")
    @app_commands.describe(member="العضو المراد استعراض معلوماته (اتركه فارغاً لمعلوماتك الشخصية)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        # الرد بشكل مبدئي وسريع لمنع تعليق ديسكورد (The application did not respond)
        await interaction.response.defer(ephemeral=False)

        m = member or interaction.user
        g = interaction.guild
        guild_name = g.name if g else "Server"
        bot_name = self.bot.user.name if self.bot.user else "Bot"

        # تسجيل الاستخدام في قاعدة البيانات السحابية
        if g:
            log_userinfo_usage(g.id, guild_name, interaction.user.id, m.id)

        # جلب معلومات الحساب والبانر (إن وجد) بأمان
        try:
            user_full = await self.bot.fetch_user(m.id)
            banner_url = user_full.banner.url if user_full.banner else None
        except Exception:
            banner_url = None

        # تنسيق الرتب (باستثناء رتبة @everyone)
        roles = [role.mention for role in reversed(m.roles[1:])] if hasattr(m, "roles") else []
        roles_str = " ".join(roles) if roles else "لا توجد رتب"
        if len(roles_str) > 1024:
            roles_str = f"عدد الرتب كبير جداً: ｢ {len(roles)} ｣ رتبة"

        # تواريخ الانضمام والإنشاء مع حساب الفترات الزمنية بدقة
        now = datetime.datetime.now(datetime.timezone.utc)
        
        created_at = m.created_at
        created_date_str = created_at.strftime("%Y/%m/%d")
        created_age = now - created_at
        created_age_str = f"{created_age.days // 365} سنة، {(created_age.days % 365) // 30} شهر"

        joined_at = getattr(m, "joined_at", None)
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
            description=f"> الملف الشخصي والإحصائيات الكاملة والعميقة داخل سيرفر {guild_name}.\n━━━━━━━━━━━━━━━━━━━━━",
            color=m.color if hasattr(m, "color") and m.color.value != 0 else 0x2b2d31,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        embed.set_thumbnail(url=m.display_avatar.url)
        if banner_url:
            embed.set_image(url=banner_url)
            
        # 1. معلومات الهوية
        embed.add_field(
            name="🆔 ╎ الـهـويـة والأسـمـاء",
            value=(
                f"> **الاسم الكامل:** ｢ {m} ｣\n"
                f"> **الأيدي (ID):** ｢ `{m.id}` ｣\n"
                f"> **نوع الحساب:** ｢ {account_type} ｣\n"
                f"> **اللقب في السيرفر:** ｢ {getattr(m, 'nick', None) or 'بدون لقب'} ｣"
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
        
        embed.set_footer(
            text=f"{guild_name} ✦ Requested by {interaction.user.name}", 
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UserInfoCog(bot))
