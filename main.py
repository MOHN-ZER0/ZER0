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

# أيدي السيرفر الخاص بكم للمزامنة الفورية للأوامر
MY_GUILD = discord.Object(id=1515399068694614087)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Zero Bot | ZIUO - MC Ultimate"))
    
    # تحميل ملفات الأوامر (Cogs)
    if os.path.exists("./cogs"):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                try:
                    await bot.load_extension(f"cogs.{filename[:-3]}")
                    print(f"📦 Loaded Cog: {filename}")
                except Exception as e:
                    print(f"⚠️ Failed to load Cog {filename}: {e}")

    try:
        bot.tree.clear_commands(guild=MY_GUILD)
        bot.tree.copy_global_to(guild=MY_GUILD)
        await bot.tree.sync(guild=MY_GUILD)
        print(f"✅ Synced commands successfully to ZIUO MC Server!")
    except Exception as e:
        print(f"⚠️ Sync Error: {e}")
        
    print(f"✅ Zero Bot is Online as {bot.user}!")

# جلب التوكن بأمان من متغيرات البيئة
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("⚠️ Error: DISCORD_TOKEN is not set in environment variables or .env file!")
else:
    bot.run(TOKEN)
