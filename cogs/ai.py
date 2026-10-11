import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import requests
import asyncio
import random

# ==================== الإعدادات والمفاتيح ====================
# مفتاح Groq API
GROQ_API_KEY = "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"

CONFIG_FILE = "ai_system_config.json"

def load_ai_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_ai_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

AI_SETTINGS = load_ai_config()

# نظام محلي احتياطي باللغة العربية لو حصلت أي مشكلة في الـ API
LOCAL_SMART_RESPONSES = [
    "أهلاً بك! فكرت في كلامك وأرى أن الموضوع يحتاج إلى نظرة أعمق بكثير.",
    "مرحباً بك! فهمت قصدك تماماً وسجلت أفكارك.. أخبرني المزيد!",
    "كلامك منطقي جداً وتتابع الأفكار لديك ممتاز وواضح.",
    "مرحباً! كلماتك تدل على تفكير ذكي وعالي المستوى.",
    "أهلاً بك! جمعت لك الرد المناسب والسريع بناءً على سؤالك.",
]

class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==================== أمر التحكم بالذكاء الاصطناعي (Slash Command) ====================
    @app_commands.command(name="ai", description="[إدارة] تفعيل أو إيقاف نظام الذكاء الاصطناعي في هذه القناة")
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
                await interaction.response.send_message(f"✅ تم تفعيل الذكاء الاصطناعي في <#{channel_id}>", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ مفعّل بالفعل في هذه القناة!", ephemeral=True)
                
        elif action == "disable":
            if channel_id in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].remove(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message("🛑 تم إيقاف الذكاء الاصطناعي في هذه القناة.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ غير مفعّل أصلاً هنا!", ephemeral=True)

    # ==================== دالة جلب الرد من Groq API ====================
    async def get_ai_response(self, user_prompt):
        try:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "أنت مساعد ذكاء اصطناعي ذكي جداً، وردودك سريعة ومترابطة ومفيدة باللغة العربية الفصحى الواضحة والراقية."},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7
            }

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
            )
            
            if response.status_code == 200:
                data = response.json()
                reply_text = data["choices"][0]["message"]["content"].strip()
                if reply_text:
                    return reply_text
            
            raise Exception(f"Groq API Error Status: {response.status_code}")

        except Exception as e:
            print(f"⚠️ واجه الـ API مشكلة ({e})، تم التحويل للنظام المحلي الاحتياطي.")
            base_reply = random.choice(LOCAL_SMART_RESPONSES)
            return f"{base_reply} (بخصوص: {user_prompt[:30]}..)"

    # ==================== مستمع الرسائل للرد التلقائي ====================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        channel_id = message.channel.id
        
        is_channel_enabled = (guild_id in AI_SETTINGS and channel_id in AI_SETTINGS[guild_id]["channels"])
        is_bot_mentioned = self.bot.user.mentioned_in(message)
        content_lower = message.content.strip()

        # التحقق من عبارة التفعيل "يا ذكاء اصطناعي"
        trigger_phrase = "يا ذكاء اصطناعي"
        starts_with_trigger = content_lower.startswith(trigger_phrase)

        if not is_channel_enabled and not is_bot_mentioned and not starts_with_trigger:
            return

        # تنظيف النص وتجهيزه
        clean_content = message.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
        
        # إذا كانت الرسالة فقط "يا ذكاء اصطناعي"
        if clean_content == trigger_phrase:
            await message.reply("مرحباً بك! أنا نظام الذكاء الاصطناعي، كيف يمكنني مساعدتك اليوم؟ أخبرني بما تريد أن أفعله.")
            return

        # إزالة الكلمة المفتاحية من بداية النص إذا كتبت في البداية
        if clean_content.startswith(trigger_phrase):
            clean_content = clean_content[len(trigger_phrase):].strip()

        if clean_content:
            async with message.channel.typing():
                await asyncio.sleep(0.3)
                reply = await self.get_ai_response(clean_content)
                await message.reply(reply)

    # ==================== أمر اختبار بسيط ====================
    @commands.command(name='ai_ping')
    async def ai_ping(self, ctx):
        await ctx.send('Pong! 🏓 بوت الذكاء الاصطناعي يعمل بشكل ممتاز ورسمي!')

async def setup(bot):
    await bot.add_cog(AICog(bot))
