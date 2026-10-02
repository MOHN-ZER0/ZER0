import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import requests

# ==============================================================================
# ⚙ إعدادات Pollinations API (المفتاح الجديد)
# ==============================================================================
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

# نظام حفظ السجل لكل قناة (الذاكرة المؤقتة)
CHANNEL_HISTORIES = {}
MAX_HISTORY_LENGTH = 5  # عدد الرسائل السابقة عشان الذاكرة تكون خفيفة والردود سريعة

EGYPTIAN_SYSTEM_PROMPT = """
أنت بوت ذكاء اصطناعي داخل سيرفر ديسكورد مصري، اسمك "ZERO". 
أسلوبك كوميدي، ساخر، ابن نكتة، وبتتكلم مصري صميم وخفيف. 
قاعدة صارمة جداً: ردودك لازم تكون **مختصرة جداً وقصيرة** (في سطر أو سطرين بالكتير)، وبلاش رغ أو محاضرات طويلة نهائياً!
لو حد محتاج مساعدة حقيقية، رد عليه بجدية وتفهم مشكلته باختصار شديد.
ولو حد قلل منك أو استفزك، اديله قصف جبهة محترم وموجز.
"""

class EgyptianAISystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ai", description="[إدارة] إدارة نظام الذكاء الاصطناعي")
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
                await interaction.response.send_message(f"✅ تم تفعيل الذكاء الاصطناعي في {interaction.channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ مفعّل بالفعل في هذه القناة!", ephemeral=True)
                
        elif action == "disable":
            if channel_id in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].remove(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message(f"🛑 تم إيقاف الذكاء الاصطناعي في هذه القناة.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠ غير مفعّل أصلاً هنا!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # تجاهل رسائل البوتات أو الرسائل التي خارج السيرفرات
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        channel_id = message.channel.id
        is_channel_enabled = (guild_id in AI_SETTINGS and channel_id in AI_SETTINGS[guild_id]["channels"])
        is_bot_mentioned = self.bot.user.mentioned_in(message)

        # لو القناة مش مفعلة البوت مش هيرد إلا لو تم منشنته
        if not is_channel_enabled and not is_bot_mentioned:
            return

        # تنظيف محتوى الرسالة من المنشن
        user_message = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not user_message:
            return

        # تجهيز السجل الخاص بالقناة
        if channel_id not in CHANNEL_HISTORIES:
            CHANNEL_HISTORIES[channel_id] = []

        async with message.channel.typing():
            try:
                headers = {
                    "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                # بناء رسائل الـ API مع إضافة النظام والسجل التاريخي
                messages_payload = [{"role": "system", "content": EGYPTIAN_SYSTEM_PROMPT}]
                
                for hist in CHANNEL_HISTORIES[channel_id]:
                    messages_payload.append(hist)
                
                messages_payload.append({"role": "user", "content": user_message})

                payload = {
                    "messages": messages_payload,
                    "model": "openai",
                    "jsonMode": False
                }

                # طلب مباشر لـ Pollinations API مع وقت إضافي لتجنب الـ Timeout
                response = requests.post("https://text.pollinations.ai/", headers=headers, json=payload, timeout=20)
                
                print(f"API Status Code: {response.status_code}") 
                print(f"API Response: {response.text}")

                if response.status_code == 200:
                    reply_text = response.text.strip()
                    if not reply_text:
                        reply_text = "يا اسطى البوت رد بصمت.. مفيش كلام رجع!"
                elif response.status_code == 402:
                    reply_text = "يا اسطى مفتاح الـ API محتاج رصيد أو خلص الحصة بتاعتـه!"
                else:
                    reply_text = "يا اسطى السيرفر بيشرب شاي، جرب تاني كمان شوية!"

                if len(reply_text) > 1990:
                    reply_text = reply_text[:1987] + "..."

                # حفظ الرسالة والرد في سجل القناة (الذاكرة)
                CHANNEL_HISTORIES[channel_id].append({"role": "user", "content": user_message})
                CHANNEL_HISTORIES[channel_id].append({"role": "assistant", "content": reply_text})

                # الحفاظ على حجم السجل لكي لا يصبح كبيراً جداً
                if len(CHANNEL_HISTORIES[channel_id]) > MAX_HISTORY_LENGTH * 2:
                    CHANNEL_HISTORIES[channel_id] = CHANNEL_HISTORIES[channel_id][-MAX_HISTORY_LENGTH * 2:]

                await message.reply(reply_text)

            except requests.exceptions.Timeout:
                print("❌ Pollinations Timeout Error")
                await message.reply("⚠ يا اسطى السيرفر أخد وقت أطول من اللازم ورد متأخر، حاول تاني.")
            except Exception as e:
                print(f"❌ Pollinations Error: {e}")
                await message.reply("⚠ حصل خطأ خفيف في الاتصال، ظبط حالك وجرب تاني.")

async def setup(bot):
    await bot.add_cog(EgyptianAISystem(bot))
