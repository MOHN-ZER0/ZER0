import discord
from discord import app_commands
from discord.ext import commands
import datetime

class ServerInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="[معلومات] عرض لوحة معلومات وإحصائيات سيرفر ZIUO الشاملة والعملاقة")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        await interaction.response.defer(ephemeral=False)
        
        # إحصائيات الأعضاء
        total_members = g.member_count
        humans = len([m for m in g.members if not m.bot])
        bots = len([m for m in g.members if m.bot])
        
        # إحصائيات الرومات
        text_channels = len(g.text_channels)
        voice_channels = len(g.voice_channels)
        forums = len(g.forum_channels)
        categories_count = len(g.categories)
        total_channels = len(g.channels)
        
        # إحصائيات الرتب والإيموجيات
        roles_count = len(g.roles)
        highest_role = g.roles[-1].mention if len(g.roles) > 1 else "لا يوجد"
        animated_emojis = len([e for e in g.emojis if e.animated])
        static_emojis = len(g.emojis) - animated_emojis
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
            discord.VerificationLevel.high: "عالية (عضو بالسرير لأكثر من 10 دقائق)",
            discord.VerificationLevel.highest: "عالية جداً (تحتاج هاتف موثق)"
        }
        verification = verification_levels.get(g.verification_level, "عادية")

        # معلومات البوست (Boost Info)
        boost_tier = g.premium_tier
        boost_count = g.premium_subscription_count
        boosters_count = len(g.premium_subscribers)
        
        # حساب شريط التقدم للبوستات
        boost_goals = {0: 2, 1: 7, 2: 14, 3: 30} # تقريبي أو حسب نظام ديسكورد
        next_goal_text = "الحد الأقصى متاح 🚀"
        if boost_tier == 0:
            next_goal_text = f"متبقي {max(0, 2 - boost_count)} بوست للوصول للمستوى 1"
        elif boost_tier == 1:
            next_goal_text = f"متبقي {max(0, 7 - boost_count)} بوست للوصول للمستوى 2"
        elif boost_tier == 2:
            next_goal_text = f"متبقي {max(0, 14 - boost_count)} بوست للوصول للمستوى 3"

        embed = discord.Embed(
            title="📇 ╎ مـعـلـومـات سـيـرفـر ZIUO - MC 〣 ｢🛡️｣",
            description=f"> لوحة القيادة المركزية وإحصائيات السيرفر الرسمية والمحدثة بكافة التفاصيل والخصائص العميقـة ⚡.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        if g.banner:
            embed.set_image(url=g.banner.url)
            
        # 1. المعلومات الأساسية
        embed.add_field(
            name="📋 ╎ الـمـعـلـومـات الـأسـاسـيـة",
            value=(
                f"> **الـمـالـك:** ｢ {g.owner.mention} ｣\n"
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
                f"> **الإجمالي:** ｢ {total_members} ｣ ✦ **بشر:** ｢ {humans} 👤 ｣ ✦ **بوتات:** ｢ {bots} 🤖 ｣"
            ),
            inline=False
        )
        
        # 3. تفاصيل الرومات
        embed.add_field(
            name="💬 ╎ تـفـاصـيـل الـرومـات والـقـنـوات",
            value=(
                f"> **الإجمالي:** ｢ {total_channels} ｣ ✦ **الفئات:** ｢ {categories_count} ｣\n"
                f"> **الكتابية:** ｢ {text_channels} 📝 ｣ ✦ **الصوتية:** ｢ {voice_channels} 🔊 ｣ ✦ **المنديات:** ｢ {forums} 📂 ｣"
            ),
            inline=False
        )
        
        # 4. الرتب والإيموجي
        embed.add_field(
            name="🎭 ╎ الـرتـب والـإيـمـوجـيـات والـمـلـصـقـات",
            value=(
                f"> **عدد الرتب:** ｢ {roles_count} ｣ ✦ **أعلى رتبة:** {highest_role}\n"
                f"> **الإيموجيات:** ｢ {len(g.emojis)} ｣ (عادي: ｢ {static_emojis} ｣ ✦ متحرك: ｢ {animated_emojis} ｣)\n"
                f"> **الملصقات (Stickers):** ｢ {stickers_count} ｣"
            ),
            inline=False
        )

        # 5. البوست والحماية
        embed.add_field(
            name="🚀 ╎ الـبـوسـت والـحـمـايـة والـأمـان",
            value=(
                f"> **مستوى البوست (Tier):** ｢ المستوى {boost_tier} ｣ ✦ **عدد البوستات:** ｢ {boost_count} 💎 ｣\n"
                f"> **عدد الداعمين (Boosters):** ｢ {boosters_count} 👥 ｣ ({next_goal_text})\n"
                f"> **مستوى الحماية:** ｢ {verification} ｣\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            ),
            inline=False
        )
        
        embed.set_footer(text="Z I UO - MC Server ✦ Enhanced Server Dashboard", icon_url=g.icon.url if g.icon else None)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfoCog(bot))
