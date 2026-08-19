import os
import time
import random
import asyncio
import json
import discord
from discord.ext import commands
import config
import economy
from fak import keep_alive
from supabase import create_client, Client
from tickets.utils import TicketControlView, TicketButtonView

# =========================================================
# Intents
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# =========================================================
# Extensions
# =========================================================

INITIAL_EXTENSIONS = [
    "cogs.levels",
    "cogs.tickets",
]



# =========================================================
# Bot Class
# =========================================================

class SebraBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if supabase_url and supabase_key:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            print("✅ Connected to Supabase successfully!")
        else:
            self.supabase = None
            print("❌ Warning: Supabase environment variables are missing!")

    async def setup_hook(self):
        print("========================================")
        print("🔧 Starting bot setup...")
        print("========================================")

        # تسجيل أزرار التحكم داخل التذاكر الدائمة لتظل تعمل بعد إعادة التشغيل
        try:
            self.add_view(TicketControlView())
            print("✅ Registered persistent TicketControlView successfully!")
        except Exception as e:
            print(f"❌ Failed to register persistent view: {e}")

        # استرجاع وإعادة تسجيل جميع لوحات التذاكر من قاعدة البيانات لمنع أخطاء الأزرار عند إعادة التشغيل
        if self.supabase:
            try:
                response = self.supabase.table("ticket_panels").select("*").execute()
                if response.data:
                    for item in response.data:
                        panel_data = json.loads(item["data"])
                        buttons_info = panel_data.get("buttons_info", [])
                        # إنشاء وإضافة الـ View الخاص بلوحة التذاكر
                        view = TicketButtonView(None, buttons_info, panel_data)
                        self.add_view(view)
                    print(f"✅ Successfully reloaded {len(response.data)} ticket panels from database!")
            except Exception as e:
                print(f"❌ Failed to reload ticket panels: {e}")

        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                print(f"✅ Loaded: {extension}")
            except Exception as e:
                print(f"❌ Failed to load {extension}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"✅ Global slash commands synced: {len(synced)}")
        except Exception as e:
            print(f"❌ Slash command sync failed: {e}")


# =========================================================
# Create Bot
# =========================================================

bot = SebraBot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True
)


# =========================================================
# Ready
# =========================================================

@bot.event
async def on_ready():
    print("========================================")
    print(f"🤖 Logged in as: {bot.user}")
    print("========================================")

    if not getattr(bot, "_economy_initialized", False):
        try:
            await economy.init_db()
            bot._economy_initialized = True
            print("✅ Economy database initialized.")
        except Exception as e:
            print(f"❌ Economy database error: {e}")


# =========================================================
# Keep Alive + Run
# =========================================================

keep_alive()

# استخدام التوكن اللي بعته في رسالتك أو سحبه من ملف config
bot.run("MTUzMzEzNjUzNDkwNjMzOTUyOQ.GZxjg1.oAw6oXBnFQSC--YmUZaGf8z5cC1d1OEmNBtqGU")
