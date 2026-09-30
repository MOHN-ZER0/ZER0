import discord
from discord.ext import commands
import asyncio

class DynamicSongPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # لو كتبت جملة البداية، البوت يبدأ يغني خطوة بخطوة بتعديل الرسالة الحية
        if message.content.strip().lower() == "i'll never be like you":
            
            # الكلمات بترتيب المغني الدقيق مع التدرج التلقائي للحجم عند التكرار
            song_lines = [
                "I'll never be like you",
                "### I'll never be like you",
                "## I'll never be like you!",
                "# **I'll never be like you!!**",
                "I'm risin' up and I'm ready to fight you",
                "Ready to fight you!",
                "🔥 **I'm all in!**",
                "I've seen you before, you all are the same",
                "You're just another goin' up in the flames",
                "And if I'm gon' die in the fight",
                "It'll be while I am bringing you down to the grave",
                "I see who you are, **you are my enemy**",
                "My enemy, **you are my enemy!**"
            ]

            # إرسال الرسالة الابتدائية
            sent_msg = await message.reply("🎶 *[بيظبط اللحن...]*")
            await asyncio.sleep(1)

            # حلقة التعديل الحية (Live Editing) سطر بـ سطر وكل ثانية
            for line in song_lines:
                try:
                    await sent_msg.edit(content=line)
                    await asyncio.sleep(1.2) # سرعة الانتقال بين الجملة والتانية
                except discord.HTTPException:
                    pass

async def setup(bot):
    await bot.add_cog(DynamicSongPlayer(bot))
  
