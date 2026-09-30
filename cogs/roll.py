import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

class AdvancedRollSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roll", description="[فعاليات] نظام رمي النرد العشوائي أو السحب العشوائي للأعضاء (من السيرفر بالكامل أو برتبة مخصصة)")
    @app_commands.describe(
        mode="اختر نوع الـ Roll (نرد رقمي عادي، أو سحب عشوائي لشخص من السيرفر، أو سحب من رتبة)",
        maximum="الحد الأقصى للنرد الرقمي (افتراضياً: 100 - يُستخدم فقط في وضع النرد)",
        role="الرتبة المطلوبة للسحب العشوائي (اختياري - يُستخدم فقط لو اخترت وضع السحب برتبة)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="🎲 نرد رقمي عادي (Roll Number)", value="number"),
        app_commands.Choice(name="🏆 سحب عضو عشوائي من السيرفر بالكامل", value="all_members"),
        app_commands.Choice(name="🎖️ سحب عضو عشوائي من حاملي رتبة معينة", value="role_members"),
    ])
    async def roll(
        self, 
        interaction: discord.Interaction, 
        mode: str = "number", 
        maximum: int = 100, 
        role: discord.Role = None
    ):
        # 1. حالة النرد الرقمي العادي
        if mode == "number":
            if maximum < 1:
                maximum = 100
            result = random.randint(1, maximum)
            
            embed = discord.Embed(
                title="🎲 ╎ لـعـبـة الـنـرد (Roll) 〣 ｢🎮｣",
                description=f"> تم رمي النرد بنجاح وإليك النتيجة.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="👤 ╎ الـلاعب", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="🎯 ╎ النـتـيـجـة", value=f"> ｢ {result} ｣ من أصل ｢ {maximum} ｣", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ Fun System")
            
            await interaction.response.send_message(embed=embed)
            return

        # تأخير الاستجابة لأن جلب الأعضاء قد يستغرق ثانية
        await interaction.response.defer(ephemeral=False)

        # 2. حالة السحب العشوائي من السيرفر بالكامل (استبعاد البوتات)
        if mode == "all_members":
            # تصفية الأعضاء (استبعاد البوتات)
            valid_members = [m for m in interaction.guild.members if not m.bot]
            
            if not valid_members:
                await interaction.followup.send("❌ لا توجد أعضاء حقيقيون متاحون للسحب في السيرفر حالياً!", ephemeral=True)
                return
            
            winner = random.choice(valid_members)

            embed = discord.Embed(
                title="🏆 ╎ نـتـيـجـة السـحـب العـشـوائـي 〣 ｢🎉｣",
                description=f"> تم إجراء عملية السحب العشوائي بنجاح من بين جميع أعضاء السيرفر!\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xF1C40F,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="👑 ╎ العـضـو الفـائـز", value=f"> ｢ {winner.mention} ｣ (`{winner.name}`)", inline=False)
            embed.add_field(name="🛡️ ╎ المُشرف المسؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📊 ╎ إجمالي المشاركين", value=f"> ｢ {len(valid_members)} ｣ عضواً", inline=False)
            embed.set_thumbnail(url=winner.display_avatar.url)
            embed.set_footer(text="Z I UO - MC Server ✦ Global Giveaway & Roll System")

            await interaction.followup.send(content=f"🎉 مبروك يا {winner.mention} لقد فزت في السحب العشوائي!", embed=embed)
            return

        # 3. حالة السحب العشوائي من حاملي رتبة معينة
        if mode == "role_members":
            if not role:
                await interaction.followup.send("❌ يجب عليك تحديد الرتبة المطلوبة في خانة `role` عندما تختار وضع السحب برتبة!", ephemeral=True)
                return

            # تصفية الأعضاء الذين يمتلكون الرتبة المحددة (مع استبعاد البوتات)
            valid_members = [m for m in role.members if not m.bot]

            if not valid_members:
                await interaction.followup.send(f"❌ لا يوجد أي أعضاء حقيقيون يمتلكون رتبة {role.mention} حالياً لإجراء السحب عليها!", ephemeral=True)
                return

            winner = random.choice(valid_members)

            embed = discord.Embed(
                title=f"🎖️ ╎ سـحـب رتـبـة: {role.name} 〣 ｢🎉｣",
                description=f"> تم إجراء السحب العشوائي بنجاح من بين أعضاء رتبة {role.mention}!\n━━━━━━━━━━━━━━━━━━━━━",
                color=role.color if role.color.value != 0 else 0x3498DB,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="👑 ╎ العـضـو الفـائـز", value=f"> ｢ {winner.mention} ｣ (`{winner.name}`)", inline=False)
            embed.add_field(name="🛡️ ╎ المُشرف المسؤول", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📌 ╎ الرتبة المستهدفة", value=f"> ｢ {role.mention} ｣ (عدد المؤهلين: {len(valid_members)})", inline=False)
            embed.set_thumbnail(url=winner.display_avatar.url)
            embed.set_footer(text="Z I UO - MC Server ✦ Role Giveaway & Roll System")

            await interaction.followup.send(content=f"🎉 مبروك يا {winner.mention} لقد فزت بالسحب المخصص لرتبة {role.name}!", embed=embed)
            return

async def setup(bot):
    await bot.add_cog(AdvancedRollSystemCog(bot))
