import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict, deque

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

TRIGGER = "يا ذكاء اصطناعي"
HISTORY_LEN = 10
COOLDOWN_SECONDS = 3
MAX_INPUT_CHARS = 2000
DISCORD_LIMIT = 1900

SYSTEM_PROMPT = (
    "أنت مساعد ذكاء اصطناعي ذكي وودود داخل سيرفر ديسكورد. "
    "رد بنفس لغة ولهجة المستخدم؛ وإن كتب بالعربية فاستخدم عربية واضحة وسهلة. "
    "اجعل ردودك مفيدة ومباشرة ومختصرة قدر الإمكان، ولا تطل إلا إذا طُلب منك. "
    "استخدم تنسيق ماركداون بسيط (قوائم وأكواد عند الحاجة)."
)

# الاتصال بقاعدة بيانات MongoDB السحابية العامة
MONGO_URI = os.getenv("MONGODB_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["Global_Bot_DB"]
ai_config_col = db["ai_system_config"]

log = logging.getLogger("ai_cog")


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.settings: dict = self._load_config_db()
        self._save_lock = asyncio.Lock()
        self.history: dict[tuple[int, int], deque] = defaultdict(
            lambda: deque(maxlen=HISTORY_LEN)
        )
        self.last_used: dict[int, float] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        if not GROQ_API_KEY:
            log.warning("GROQ_API_KEY غير موجود في متغيرات البيئة! الذكاء الاصطناعي لن يرد.")

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ---------- قاعدة بيانات MongoDB للإعدادات ----------
    def _load_config_db(self) -> dict:
        doc = ai_config_col.find_one({"_id": "ai_config_main"})
        if not doc:
            initial_data = {
                "_id": "ai_config_main",
                "guilds": {}
            }
            ai_config_col.insert_one(initial_data)
            return {}
        return doc.get("guilds", {})

    async def save_config(self):
        async with self._save_lock:
            ai_config_col.update_one(
                {"_id": "ai_config_main"},
                {"$set": {"guilds": self.settings}},
                upsert=True
            )

    # ---------- أوامر السلاش ----------
    @app_commands.command(name="ai", description="[إدارة] التحكم في الذكاء الاصطناعي داخل هذه القناة")
    @app_commands.describe(action="اختر الإجراء")
    @app_commands.choices(action=[
        app_commands.Choice(name="تفعيل في هذه القناة", value="enable"),
        app_commands.Choice(name="إيقاف في هذه القناة", value="disable"),
        app_commands.Choice(name="حالة القناة", value="status"),
    ])
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_control(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        guild_id = str(interaction.guild_id)
        channel_id = interaction.channel_id
        channels: list = self.settings.setdefault(guild_id, {"channels": []})["channels"]
        value = action.value

        if value == "enable":
            if channel_id in channels:
                msg = "⚠️ مفعّل بالفعل في هذه القناة!"
            else:
                channels.append(channel_id)
                await self.save_config()
                msg = f"✅ تم تفعيل الذكاء الاصطناعي في <#{channel_id}>"
        elif value == "disable":
            if channel_id not in channels:
                msg = "⚠️ غير مفعّل أصلاً هنا!"
            else:
                channels.remove(channel_id)
                await self.save_config()
                msg = "🛑 تم إيقاف الذكاء الاصطناعي في هذه القناة."
        else:
            state = "مفعّل ✅" if channel_id in channels else "متوقف 🛑"
            msg = f"حالة الذكاء الاصطناعي في <#{channel_id}>: **{state}**"

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="ai_reset", description="مسح ذاكرة المحادثة بينك وبين الذكاء الاصطناعي في هذه القناة")
    @app_commands.guild_only()
    async def ai_reset(self, interaction: discord.Interaction):
        self.history.pop((interaction.channel_id, interaction.user.id), None)
        await interaction.response.send_message("🧹 تم مسح ذاكرة المحادثة.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            text = "❌ الأمر ده للإدارة فقط."
        else:
            log.exception("خطأ في أمر سلاش", exc_info=error)
            text = "❌ حصل خطأ غير متوقع."
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    # ---------- الاتصال بـ Groq ----------
    async def get_ai_response(self, key: tuple[int, int], prompt: str) -> str | None:
        if not GROQ_API_KEY or self.session is None:
            return None

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + list(self.history[key])
            + [{"role": "user", "content": prompt}]
        )

        for model in MODELS:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            for attempt in range(3):
                try:
                    async with self.session.post(GROQ_URL, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            reply = (data["choices"][0]["message"]["content"] or "").strip()
                            if reply:
                                self.history[key].append({"role": "user", "content": prompt})
                                self.history[key].append({"role": "assistant", "content": reply})
                                if len(self.history) > 1000:
                                    self.history.clear()
                                return reply
                            break

                        body = (await resp.text())[:300]
                        log.warning("Groq %s (model=%s, attempt=%d): %s", resp.status, model, attempt + 1, body)

                        if resp.status in (401, 403):
                            return None
                        if resp.status == 429 or resp.status >= 500:
                            retry_after = resp.headers.get("retry-after")
                            delay = min(float(retry_after), 8) if retry_after and retry_after.replace(".", "", 1).isdigit() else 1.5 * (attempt + 1)
                            await asyncio.sleep(delay)
                            continue
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    log.warning("خطأ اتصال (model=%s, attempt=%d): %s", model, attempt + 1, e)
                    await asyncio.sleep(1.5 * (attempt + 1))
                except (KeyError, IndexError, ValueError) as e:
                    log.error("رد غير متوقع من Groq: %s", e)
                    break
        return None

    # ---------- الرد التلقائي ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or self.bot.user is None:
            return

        channels = self.settings.get(str(message.guild.id), {}).get("channels", [])
        is_enabled = message.channel.id in channels
        is_mentioned = self.bot.user in message.mentions
        has_trigger = message.content.strip().startswith(TRIGGER)

        if not (is_enabled or is_mentioned or has_trigger):
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        clean = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()
        if clean.startswith(TRIGGER):
            clean = clean[len(TRIGGER):].lstrip(" ,،:؛-").strip()

        no_ping = discord.AllowedMentions.none()

        if not clean:
            if is_mentioned or has_trigger:
                await message.reply(
                    "مرحباً بك! أنا نظام الذكاء الاصطناعي، كيف يمكنني مساعدتك اليوم؟",
                    allowed_mentions=no_ping,
                    mention_author=False,
                )
            return

        now = time.monotonic()
        if now - self.last_used.get(message.author.id, 0) < COOLDOWN_SECONDS:
            return
        self.last_used[message.author.id] = now

        clean = clean[:MAX_INPUT_CHARS]
        key = (message.channel.id, message.author.id)

        async with message.channel.typing():
            reply = await self.get_ai_response(key, clean)

        if reply is None:
            reply = "⚠️ عذراً، مش قادر أوصل للذكاء الاصطناعي دلوقتي. جرب تاني بعد شوية."

        chunks = split_message(reply)
        await message.reply(chunks[0], allowed_mentions=no_ping, mention_author=False)
        for chunk in chunks[1:]:
            await message.channel.send(chunk, allowed_mentions=no_ping)

    # ---------- أمر اختبار ----------
    @commands.command(name="ai_ping")
    async def ai_ping(self, ctx: commands.Context):
        status = "✅ موجود" if GROQ_API_KEY else "❌ غير موجود"
        await ctx.send(f"Pong! 🏓 البوت شغال في سيرفر **{ctx.guild.name}**. مفتاح Groq: {status}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
