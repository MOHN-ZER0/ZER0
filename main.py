import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

# تحميل المتغيرات السرية من ملف .env المحلي
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def setup_hook():
    # تحميل ملفات الأوامر (Cogs)
    if os.path.exists("./cogs"):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                try:
                    await bot.load_extension(f"cogs.{filename[:-3]}")
                    print(f"📦 Loaded Cog: {filename}")
                except Exception as e:
                    print(f"⚠️ Failed to load Cog {filename}: {e}")

    # مزامنة الأوامر عالمياً لجميع السيرفرات (Global Sync)
    try:
        synced = await bot.tree.sync()
        print(f"🌍 Synced {len(synced)} command(s) globally across all servers!")
    except Exception as e:
        print(f"⚠️ Global Sync Error: {e}")

@bot.event
async def on_ready():
    # جلب عدد السيرفرات الحالية التي يتواجد بها البوت
    guild_count = len(bot.guilds)
    
    # إعداد النص المطلوب مع إضافة عدد السيرفرات
    status_text = f"افضل بوت دعم مجاني متوفر به كل ما تريده و عدد مستخدمينا الحالي هو  `{guild_count}`"
    
    # ضبط الحالة لتظهر بنوع Watching ومع العلامة الصفراء/الهلال (Idle 🌙)
    activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
    await bot.change_presence(status=discord.Status.idle, activity=activity)
    
    print(f"✅ Zero Bot is Online as {bot.user}!")

# جلب التوكن بأمان من متغيرات البيئة
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("⚠️ Error: DISCORD_TOKEN is not set in environment variables or .env file!")
else:
    bot.run(TOKEN)
