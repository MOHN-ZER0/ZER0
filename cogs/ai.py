import discord
from discord.ext import commands
import requests

# مفتاح الـ API اللي طلبته
POLLINATIONS_API_KEY = "AQ.Ab8RN6JtjAuJTMsXBlTfbmv1PMR6ywzgrmVoJl2PYgZFvllmlQ"

class PollinationsAICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # دالة للحصول على رد من الـ API
    async def get_ai_response(self, prompt):
        try:
            headers = {
                "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "openai",
                "jsonMode": False
            }

            # طلب مباشر لـ Pollinations API
            response = requests.post("https://text.pollinations.ai/", headers=headers, json=payload, timeout=20)
            
            if response.status_code == 200:
                reply_text = response.text.strip()
                return reply_text if reply_text else "يا اسطى البوت رد بصمت.. مفيش كلام رجع!"
            elif response.status_code == 402:
                return "يا اسطى مفتاح الـ API محتاج رصيد أو خلص الحصة بتاعتـه!"
            else:
                return "يا اسطى السيرفر بيشرب شاي، جرب تاني كمان شوية!"
                
        except Exception as e:
            print(f"Error في الطلب: {e}")
            return "عذرًا، حدث خطأ أثناء الاتصال بالـ API."

    # حدث عند استقبال رسالة
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # تجاهل رسائل البوت نفسه
        if message.author == self.bot.user:
            return

        # التحقق من أن الرسالة موجهة للبوت (منشن) أو في قناة خاصة (DM)
        if self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
            clean_content = message.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
            
            if clean_content:
                async with message.channel.typing():
                    reply = await self.get_ai_response(clean_content)
                    await message.reply(reply)

        # السماح للـ commands بالعمل
        await self.bot.process_commands(message)

    # أمر اختبار بسيط
    @commands.command(name='ping')
    async def ping(self, ctx):
        await ctx.send('Pong! 🏓 الكود شغال والمفتاح مظبوط زي الفل!')

async def setup(bot):
    await bot.add_cog(PollinationsAICog(bot))
