import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

class AdvancedCoinFlipCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coinflip", description="[ألعاب وتسلية] لعبة قلب العملة المتقدمة مع إمكانية التوقع والتحدي الثنائي")
    @app_commands.describe(
        guess="توقعك للعملة قبل رميها (اختياري: صورة أو كتابة)",
        opponent="تحدي عضو آخر في السيرفر برمي العملة بينكم (اختياري)"
    )
    @app_commands.choices(guess=[
        app_commands.Choice(name="🪙 صورة (Heads)", value="صورة (Heads)"),
        app_commands.Choice(name="🦅 كتابة (Tails)", value="كتابة (Tails)"),
    ])
    async def coinflip(
        self, 
        interaction: discord.Interaction, 
        guess: str = None, 
        opponent: discord.Member = None
    ):
        # 1. حالة التحدي الثنائي بين لاعبين (PvP)
        if opponent:
            if opponent.bot:
                await interaction.response.send_message("❌ لا يمكنك تحدي بوت في لعبة العملة!", ephemeral=True)
                return
            if opponent.id == interaction.user.id:
                await interaction.response.send_message("❌ لا يمكنك تحدي نفسك!", ephemeral=True)
                return

            # اختيار الفائز عشوائياً بين الاثنين
            winner = random.choice([interaction.user, opponent])
            loser = opponent if winner == interaction.user else interaction.user
            outcome = random.choice(["صورة (Heads)", "كتابة (Tails)"])

            embed = discord.Embed(
                title="🪙 ╎ تـحـدي قـلـب الـعـمـلـة (PvP CoinFlip) 〣 ｢🔥｣",
                description=f"> معركة سريعة بين {interaction.user.mention} و {opponent.mention}!\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xF1C40F,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="🪙 ╎ وجه العملة الظاهر", value=f"> ｢ {outcome} ｣", inline=False)
            embed.add_field(name="👑 ╎ البطل الفائز", value=f"> ｢ {winner.mention} ｣ مبروك الفوز!", inline=False)
            embed.add_field(name="💀 ╎ الخاسر الحظ سيء", value=f"> ｢ {loser.mention} ｣ هظماً حظك في المرة القادمة", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ PvP Fun System")

            await interaction.response.send_message(embed=embed)
            return

        # 2. حالة اللعب الفردي (مع أو بدون توقع)
        outcome = random.choice(["صورة (Heads)", "كتابة (Tails)"])
        
        # تحديد حالة الفوز أو الخسارة لو المستخدم كتب توقع
        embed_color = 0x2b2d31
        status_text = "تم استقرار العملة المعدنية وإظهار الوجه الظاهر."
        
        if guess:
            if guess == outcome:
                embed_color = 0x00CC66  # أخضر للفوز
                status_text = f"🎉 مبروك! توقعك الصحيح (`{guess}`) تطابق مع نتيجة العملة!"
            else:
                embed_color = 0xCC0000  # أحمر للخسارة
                status_text = f"❌ حظ أوفر! توقعك كان (`{guess}`) بينما النتيجة كانت (`{outcome}`)."

        embed = discord.Embed(
            title="🪙 ╎ لـعـبـة قـلـب الـعـمـلـة (CoinFlip) 〣 ｢🎮｣",
            description=f"> {status_text}\n━━━━━━━━━━━━━━━━━━━━━",
            color=embed_color,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="👤 ╎ الـلاعب", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
        if guess:
            embed.add_field(name="🎯 ╎ توقعك", value=f"> ｢ {guess} ｣", inline=True)
        embed.add_field(name="🪙 ╎ الوجه الظاهر", value=f"> ｢ {outcome} ｣", inline=True)
        embed.set_footer(text="Z I UO - MC Server ✦ Fun System")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AdvancedCoinFlipCog(bot))
