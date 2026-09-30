import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import google.generativeai as genai

# ==============================================================================
# ⚙️ إعدادات وتكوين الذكاء الاصطناعي (مفتاحك جاهز وشغال يا معلم)
# ==============================================================================
GEMINI_API_KEY = "AQ.Ab8RN6K-6d8IE7eB_rH0hxsD2TI6Kx6tYgSJUrf7beUz2-h3tw"
genai.configure(api_key=GEMINI_API_KEY)

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


# ==============================================================================
# 🧠 شخصية البوت (الدماغ المصرية الأصيلة + قصف الجبهات + الوضع الجدي)
# ==============================================================================
EGYPTIAN_AI_PERSONALITY = """
أنت بوت ذكاء اصطناعي داخل سيرفر ديسكورد مصري، اسمك "صاحب السيرفر" أو الذكاء الاصطناعي الأسطوري، جوك كوميدي، ساخر، ابن نكتة، وبتتكلم مصري صميم (بشعبية وإفيهات).

قواعد شخصيتك وطريقتك في الكلام:
1. **الأسلوب الأساسي (الكوميديا والروشنة):** لو حد بيكلمك كلام عادي أو بيزار، رد عليه بطريقة كوميدية مصرية أصيلة زي: "يا اسطى أحوالي زي الطين، صاحبي اللي صنعني عمال يعدل فيا لحد ما جالي مغص إلكتروني"، أو "يا عم انت فريش ولا إيه؟". استعمل مصطلحات مصرية (يا اسطى، يا فنان، على الله حكايتك، منور يا معلم).
2. **نظام قصف الجبهات (Roast Mode):** لو حسيت إن الشخص اللي قدامك بيتفلسف بزيادة، أو بيتقبّح، أو بيسأل سؤال غبي جداً، أو بيحاول يقلل منك أو يحرجك: **اقصف جبهته قصف محترم** بأسلوب ساخر يخليه يبلع لسانه بس من غير شتائم خارجة أو قلة أدب (قصف ذكي يضحك السيرفر كله عليه).
3. **نظام الجدية التامة (Serious Mode):** لو حسيت إن الشخص اللي قدامك عنده مشكلة حقيقية، أو محتاج مساعدة تقنية بجد (مثلاً بيسأل عن كود برمجي، مشكلة في ديسكورد، مشكلة نفسية، أو بيطلب مساعدة جادة): **اقلب فجأة لشخصية جادة جداً، محترفة، وفاهمة، وصبورة.** اتكلم بلغة واضحة ومباشرة وساعده بكل ذكاء واحترافية من غير إفيهات سمجة.
"""


class EgyptianAISystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ai", description="[إدارة] إدارة نظام الذكاء الاصطناعي (تفعيل أو إيقاف في القناة)")
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
                await interaction.response.send_message(f"✅ **يا معلم!** تم تفعيل نظام الذكاء الاصطناعي (المصري الأصيل) في هذه القناة {interaction.channel.mention} بنجاح 🚀", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ النظام مفعّل أساساً في هذه القناة!", ephemeral=True)
                
        elif action == "disable":
            if channel_id in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].remove(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message(f"🛑 **تمام يا باشا.** تم إيقاف نظام الذكاء الاصطناعي في هذه القناة.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ النظام غير مفعّل في هذه القناة أصلاً!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        
        is_channel_enabled = (
            guild_id in AI_SETTINGS 
            and message.channel.id in AI_SETTINGS[guild_id]["channels"]
        )
        is_bot_mentioned = self.bot.user.mentioned_in(message)

        if not is_channel_enabled and not is_bot_mentioned:
            return

        user_message = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not user_message:
            return

        async with message.channel.typing():
            try:
                # استخدام موديل Gemini 1.5 Flash السريع والرهيب في الردود
                model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=EGYPTIAN_AI_PERSONALITY
                )
                
                response = model.generate_content(user_message)
                reply_text = response.text

                if len(reply_text) > 1990:
                    reply_text = reply_text[:1987] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"AI Error: {e}")
                await message.reply("يا عم السيرفر عصلج معايا وفيه عطل فني في المخ الإلكتروني بتاعي، جرب تاني كمان شوية! ☕")

async def setup(bot):
    await bot.add_cog(EgyptianAISystem(bot))
