import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import requests

# ==============================================================================
# ⚙ إعدادات Pollinations API
# ==============================================================================
POLLINATIONS_API_KEY = "sk_anMHgjpb65le6nbBBRoYTaDjb38VBKLN"

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

# شخصيتك (كوميديا مصرية + قصف جبهات + جدية وقت الجد)
EGYPTIAN_SYSTEM_PROMPT = """
أنت بوت ذكاء اصطناعي داخل سيرفر ديسكورد مصري، اسمك "صاحب السيرفر"، جوك كوميدي، ساخر، ابن نكتة، وبتتكلم مصري صميم. 
ولما الشخص بيكون محتاج منك مساعدة، أنت بتكلمه بكل جِدية وتفهم منه إيه المشكلة وتتكلم معاه بكل احترافية بدون مزح نهائياً. 
وغير كده، أنت بتعرف تعمل قصف جبهات محترم جداً على أي شخص لو حد مثلاً قال لك انك غبي أو قلل منك؛ تقدر تعمل عليه قصف جبهة تخلي كرامته تنزل تحت الأرض.
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
                await interaction.response.send_message("⚠️ مفعّل بالفعل!", ephemeral=True)
                
        elif action == "disable":
            if channel_id in AI_SETTINGS[guild_id]["channels"]:
                AI_SETTINGS[guild_id]["channels"].remove(channel_id)
                save_ai_config(AI_SETTINGS)
                await interaction.response.send_message(f"🛑 تم إيقاف الذكاء الاصطناعي.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠ غير مفعّل أصلاً!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        is_channel_enabled = (guild_id in AI_SETTINGS and message.channel.id in AI_SETTINGS[guild_id]["channels"])
        is_bot_mentioned = self.bot.user.mentioned_in(message)

        if not is_channel_enabled and not is_bot_mentioned:
            return

        user_message = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not user_message:
            return

        async with message.channel.typing():
            try:
                # إرسال الطلب مع المفتاح الجديد لموقع Pollinations
                headers = {
                    "Authorization": f"Bearer {POLLINATIONS_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "messages": [
                        {"role": "system", "content": EGYPTIAN_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    "model": "openai"
                }

                response = requests.post("https://text.pollinations.ai/chat", headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    # محاولة استخراج الرد من صيغة الشات بتاعتهم
                    try:
                        res_json = response.json()
                        reply_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if not reply_text:
                            reply_text = str(res_json)
                    except:
                        reply_text = response.text
                else:
                    reply_text = f"يا اسطى السيرفر رد عليّ بكود خطأ: {response.status_code}"

                if len(reply_text) > 1990:
                    reply_text = reply_text[:1987] + "..."

                await message.reply(reply_text)

            except Exception as e:
                print(f"❌ Pollinations Auth Error: {e}")
                await message.reply(f"⚠ يا اسطى حصل خطأ في الاتصال:\n`{e}`")

async def setup(bot):
    await bot.add_cog(EgyptianAISystem(bot))
