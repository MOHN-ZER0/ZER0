import discord
from discord import app_commands
from discord.ext import commands
import datetime
import time

class PingSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="[أداء] فحص سرعة استجابة البنج وخوادم ديسكورد بشكل تفصيلي واحترافي")
    async def ping(self, interaction: discord.Interaction):
        # قياس زمن الاستجابة الفعلي (Round-Trip Latency)
        start_time = time.monotonic()
        await interaction.response.defer(ephemeral=False)
        end_time = time.monotonic()

        api_latency = round((end_time - start_time) * 1000)
        websocket_latency = round(self.bot.latency * 1000)

        # تقييم ذكي لحالة الاتصال بناءً على قيمة البنج
        if websocket_latency < 120:
            status_text = "ممتازة وثابتة جداً 🟢"
            status_color = 0x2ECC71 # أخضر
        elif websocket_latency < 250:
            status_text = "جيدة ومستقرة 🟡"
            status_color = 0xF1C40F # أصفر
        else:
            status_text = "يوجد بطء أو ضغط في الشبكة 🔴"
            status_color = 0xE74C3C # أحمر

        embed = discord.Embed(
            title="🏓 ╎ سـرعـة اسـتـجـابـة بـوت ZER0 〣 ｢⚡｣",
            description=f"> فحص شامل لسرعة خوادم البوت وشبكة ديسكورد المركزية.\n━━━━━━━━━━━━━━━━━━━━━",
            color=status_color,
            timestamp=datetime.datetime.utcnow()
        )
        
        embed.add_field(
            name="📡 ╎ بنج الـ WebSocket (سرعة الاتصال بالديسكورد)",
            value=f"> ｢ **{websocket_latency}ms** ｣",
            inline=False
        )
        embed.add_field(
            name="⚡ ╎ بنج الـ API (سرعة استجابة الأوامر)",
            value=f"> ｢ **{api_latency}ms** ｣",
            inline=False
        )
        embed.add_field(
            name="🟢 ╎ الـحـالـة الـعـامـة لـلـنـظام",
            value=f"> ｢ {status_text} ｣",
            inline=False
        )
        
        embed.set_footer(text="Z I UO - MC Server ✦ Advanced Ping System", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PingSystemCog(bot))
