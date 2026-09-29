import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# أيدي السيرفر الخاص بكم للمزامنة الفورية للأوامر
MY_GUILD = discord.Object(id=1515399068694614087)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Zero Bot | ZIUO - MC Ultimate"))
    
    try:
        bot.tree.clear_commands(guild=MY_GUILD)
        bot.tree.copy_global_to(guild=MY_GUILD)
        await bot.tree.sync(guild=MY_GUILD)
        print(f"✅ Synced commands successfully to ZIUO MC Server!")
    except Exception as e:
        print(f"⚠️ Sync Error: {e}")
        
    print(f"✅ Zero Bot is Online as {bot.user}!")

# تشغيل البوت بالتوكن الصحيح
bot.run("MTU1NDU3MTkwNDMyNzc0OTcxMw.GM_ui7.ctGCi1r4FqjVtbe0hjYwdiDcmITYN2zjo0K96A")
