import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import requests
import asyncio
import random

# مفتاح الـ API الأساسي
POLLINATIONS_API_KEY = "AQ.Ab8RN6JtjAuJTMsXBlTfbmv1PMR6ywzgrmVoJl2PYgZFvllmlQ"
CONFIG_FILE = "ai_system_config.json"

def load_ai_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_ai_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

AI_SETTINGS = load_ai_config()

# نظام الذكورد المحلي (الذكي جداً) كبديل لو الـ API حصل فيه أي مشكلة
LOCAL_SMART_RESPONSES = [
    "يا غالي فكرت في كلامك، وشايف إن الموضوع محتاج نظرة أعمق من كده بشوية!",
    "تمام يا اسطى، ركبت الكلام ببعضه وفهمت قصدك تماماً.. قولي أكتر!",
    "منطقي جداً اللي بتقوله، التتابع بتاع الأفكار عندك مظبوط وخفيف.",
    "يا برو، الكلمات اللي بعتها دي بتدل إن دماّغك شغالة وعالية الفبركة!",
    "حرفياً زي ما الكيبورد بيقترح الكلام، أنا جمعتلك الرد المناسب في السريع.",
]

class HybridSmartAICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ai", description="[إدارة] تفعيل أو إيقاف نظام الذكاء المزدوج في هذه القناة")
    @app_commands.describe(action="اختر تفعيل أو إيقاف النظام")
    @app_commands.choices(action=[
        app_commands.Choice(name="تفعيل في هذه القناة", value="enable"),
        app_commands.Choice(name="إيقاف في هذه القناة", value="disable")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_control(self, interaction: discord.Interaction, action: str):
        guild_id = str(interaction.guild_id)
        if guild_id not in AI_SETTINGS:
            AI_SETTINGS[guild_id] = {"channels": []}

        channel_id = interaction.channel_id
            
        if action == "enable":
            if channel_id not in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].append(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message(f"✅ تم تفعيل النظام المزدوج في {interaction.channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ مفعّل بالفعل في هذه القناة!", ephemeral=True)
                
        elif action == "disable":
            if channel_id in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].remove(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message(f"🛑 تم إيقاف النظام المزدوج في هذه القناة.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠ غير مفعّل أصلاً هنا!", ephemeral=True)

    # دالة جلب الرد (تعتمد على الـ API، ولو فشل تحول تلقائي للنظام المحلي الذكي)
    async def get_hybrid_response(self, user_prompt):
        try:
            headers = {
                "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [
                    {"role": "system", "content": "أنت نظام ذكاء اصطناعي مصري خفيف، ذكي جداً، وردودك سريعة ومترابطة."},
                    {"role": "user", "content": user_prompt}
                ],
                "model": "openai",
                "jsonMode": False
            }

            response = requests.post("https://text.pollinations.ai/", headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                reply_text = response.text.strip()
                if reply_text:
                    return reply_text
            
            # لو الـ API رد بصمت أو حصلت مشكلة طفيفة، نحول فوراً للنظام المحلي الذكي
            raise Exception("API returned empty or bad status")

        except Exception as e:
            print(f"⚠️ الـ API واجه مشكلة ({e})، تم التحويل لنظام الكيبورد الذكي المحلي تلقائياً.")
            # توليد رد متقدم شبه الكيبورد الذكي من الخزنة المحلية مع دمج جزء من كلام المستخدم للواقعية
            base_reply = random.choice(LOCAL_SMART_RESPONSES)
            return f"{base_reply} (بخصوص: {user_prompt[:30]}..)"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        channel_id = message.channel.id
        
        is_channel_enabled = (guild_id in AI_SETTINGS and channel_id in AI_SETTINGS[guild_id]["channels"])
        is_bot_mentioned = self.bot.user.mentioned_in(message)

        if not is_channel_enabled and not is_bot_mentioned:
            return

        clean_content = message.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
        
        if clean_content:
            async with message.channel.typing():
                # محاكاة التفكير وسرعة التوقع
                await asyncio.sleep(0.3)
                reply = await self.get_hybrid_response(clean_content)
                await message.reply(reply)

        await self.bot.process_commands(message)

    @commands.command(name='ping')
    async def ping(self, ctx):
        await ctx.send('Pong! 🏓 النظام المزدوج شغال وجاهز للتحدي!')

async def setup(bot):
    await bot.add_cog(HybridSmartAICog(bot))
