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
analytics_col = db["server_info_analytics"]

def log_serverinfo_usage(guild_id: int, guild_name: str, user_id: int, member_count: int):
    """حفظ إحصائيات استخدام الأمر في قاعدة البيانات السحابية"""
    try:
        analytics_col.update_one(
            {"_id": str(guild_id)},
            {
                "$set": {
                    "guild_name": guild_name,
                    "last_member_count": member_count,
                    "last_used_at": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                },
                "$inc": {"total_command_uses": 1},
                "$push": {
                    "usage_history": {
                        "user_id": user_id,
                        "used_at": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"[MongoDB Error] ServerInfo Logging Failed: {e}")

class ServerInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="[معلومات] عرض لوحة معلومات وإحصائيات السيرفر الشاملة والعملاقة")
    async def serverinfo(self, interaction: discord.Interaction):
        # الرد بشكل مبدئي وبسرعة لمنع تعليق ديسكورد (The application did not respond)
        await interaction.response.defer(ephemeral=False)
        
        g = interaction.guild
        if not g:
            await interaction.followup.send("❌ هذا الأمر يعمل فقط داخل السيرفرات!", ephemeral=True)
            return

        guild_name = g.name
        bot_name = self.bot.user.name if self.bot.user else "Bot"
        
        # إحصائيات الأعضاء الأساسية
        total_members = g.member_count or 0
        
        # تسجيل الاستخدام وحفظ بيانات السيرفر في قاعدة البيانات السحابية
        log_serverinfo_usage(g.id, guild_name, interaction.user.id, total_members)
        
        # حساب الرومات بدقة وأمان
        text_channels = len(g.text_channels)
        voice_channels = len(g.voice_channels)
        forums = len(g.forum_channels)
        categories_count = len(g.categories)
        total_channels = len(g.channels)
        
        # الرتب والإيموجيات
        roles_count = len(g.roles)
        highest_role = g.roles[-1].mention if len(g.roles) > 1 else "لا يوجد"
        
        emojis_list = g.emojis
        animated_emojis = len([e for e in emojis_list if e.animated])
        static_emojis = len(emojis_list) - animated_emojis
        stickers_count = len(g.stickers)
        
        # حساب عمر السيرفر بالتفصيل
        created_at = g.created_at
        created_date_str = created_at.strftime("%Y/%m/%d")
        server_age = datetime.datetime.now(datetime.timezone.utc) - created_at
        age_years = server_age.days // 365
        age_months = (server_age.days % 365) // 30
        age_days = (server_age.days % 365) % 30
        
        age_str = ""
        if age_years > 0:
            age_str += f"{age_years} سنة، "
        if age_months > 0:
            age_str += f"{age_months} شهر، "
        age_str += f"{age_days} يوم"

        # ترجمة مستويات الحماية والفلتر
        verification_levels = {
            discord.VerificationLevel.none: "ضعيفة (بدون قيود)",
            discord.VerificationLevel.low: "منخفضة (تحتاج بريد إلكتروني)",
            discord.VerificationLevel.medium: "متوسطة (مسجل لأكثر من 5 دقائق)",
            discord.VerificationLevel.high: "عالية (عضو بالسيرفر لأكثر من 10 دقائق)",
            discord.VerificationLevel.highest: "عالية جداً (تحتاج هاتف موثق)"
        }
        verification = verification_levels.get(g.verification_level, "عادية")

        # معلومات البوست (Boost Info)
        boost_tier = g.premium_tier
        boost_count = g.premium_subscription_count or 0
        
        # محاولة جلب المالك بأمان تام بدون تعليق
        try:
            owner = g.owner or await g.fetch_member(g.owner_id)
            owner_mention = owner.mention if owner else f"مستخدِم (`{g.owner_id}`)"
        except Exception:
            owner_mention = f"مستخدِم (`{g.owner_id}`)"

        # حساب شريط التقدم للبوستات
        if boost_tier == 0:
            next_goal_text = f"متبقي {max(0, 2 - boost_count)} بوست للوصول للمستوى 1"
        elif boost_tier == 1:
            next_goal_text = f"متبقي {max(0, 7 - boost_count)} بوست للوصول للمستوى 2"
        elif boost_tier == 2:
            next_goal_text = f"متبقي {max(0, 14 - boost_count)} بوست للوصول للمستوى 3"
        else:
            next_goal_text = "الحد الأقصى متاح 🚀"

        embed = discord.Embed(
            title=f"📇 ╎ مـعـلـومـات سـيـرفـر {guild_name} 〣 ｢🛡️｣",
            description=f"> لوحة القيادة المركزية وإحصائيات السيرفر الرسمية والمحدثة بكافة التفاصيل والخصائص العميقـة ⚡.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x2b2d31,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        if g.banner:
            embed.set_image(url=g.banner.url)
            
        # 1. المعلومات الأساسية
        embed.add_field(
            name="📋 ╎ الـمـعـلـومـات الـأسـاسـيـة",
            value=(
                f"> **الـمـالـك:** ｢ {owner_mention} ｣\n"
                f"> **أيدي الـسـيـرفـر:** ｢ `{g.id}` ｣\n"
                f"> **تـاريـخ الـتـأسـيـس:** ｢ {created_date_str} ｣\n"
                f"> **عـمـر السيرفر:** ｢ {age_str} ｣"
            ),
            inline=False
        )
        
        # 2. إحصائيات الأعضاء
        embed.add_field(
            name="👥 ╎ إحـصـائـيـات الـأعـضـاء",
            value=(
                f"> **إجمالي الأعضاء:** ｢ {total_members} 👤 ｣"
            ),
            inline=False
        )
        
        # 3. تفاصيل الرومات
        embed.add_field(
            name="💬 ╎ تـفـاصـيـل الـرومـات والـقـنـوات",
            value=(
                f"> **الإجمالي:** ｢ {total_channels} ｣ ✦ **الفئات:** ｢ {categories_count} ｣\n"
                f"> **الكتابية:** ｢ {text_channels} 📝 ｣ ✦ **الصوتية:** ｢ {voice_channels} 🔊 ｣ ✦ **المنتدى:** ｢ {forums} 📂 ｣"
            ),
            inline=False
        )
        
        # 4. الرتب والإيموجي
        embed.add_field(
            name="🎭 ╎ الـرتـب والـإيـمـوجـيـات والـمـلـصـقـات",
            value=(
                f"> **عدد الرتب:** ｢ {roles_count} ｣ ✦ **أعلى رتبة:** {highest_role}\n"
                f"> **الإيموجيات:** ｢ {len(emojis_list)} ｣ (عادي: ｢ {static_emojis} ｣ ✦ متحرك: ｢ {animated_emojis} ｣)\n"
                f"> **الملصقات (Stickers):** ｢ {stickers_count} ｣"
            ),
            inline=False
        )

        # 5. البوست والحماية
        embed.add_field(
            name="🚀 ╎ الـبـوسـت والـحـمـايـة والـأمـان",
            value=(
                f"> **مستوى البوست (Tier):** ｢ المستوى {boost_tier} ｣ ✦ **عدد البوستات:** ｢ {boost_count} 💎 ｣\n"
                f"> **الأهداف:** ({next_goal_text})\n"
                f"> **مستوى الحماية:** ｢ {verification} ｣\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"{guild_name} ✦ {bot_name} Enhanced Dashboard", icon_url=g.icon.url if g.icon else None)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfoCog(bot))
