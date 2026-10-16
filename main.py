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

async def update_bot_status():
    """دالة مسلّكة لتحديث حالة البوت وعدد السيرفرات تلقائياً"""
    guild_count = len(bot.guilds)
    status_text = f"افضل بوت دعم مجاني متوفر به كل ما تريده و عدد مستخدمينا الحالي هو  {guild_count}"
    activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
    await bot.change_presence(status=discord.Status.idle, activity=activity)

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
    # تحديث الحالة فور تشغيل البوت
    await update_bot_status()
    print(f"✅ Zero Bot is Online as {bot.user}!")

@bot.event
async def on_guild_join(guild):
    """بيتنفذ تلقائياً أول ما البوت يتضاف لسيرفر جديد (الرقم يزيد 📈)"""
    await update_bot_status()
    print(f"➕ Bot added to a new server: {guild.name} (Total: {len(bot.guilds)})")

@bot.event
async def on_guild_remove(guild):
    """بيتنفذ تلقائياً أول ما البوت يخرج أو يطرد من سيرفر (الرقم يقل 📉)"""
    await update_bot_status()
    print(f"➖ Bot removed from server: {guild.name} (Total: {len(bot.guilds)})")

# جلب التوكن بأمان من متغيرات البيئة
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("⚠️ Error: DISCORD_TOKEN is not set in environment variables or .env file!")
else:
    bot.run(TOKEN)
