import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
log = logging.getLogger("ai_cog")


def _env(name: str, default: str = "") -> str:
    """قراءة متغير بيئة مع تنظيف المسافات وعلامات التنصيص الزائدة."""
    return os.getenv(name, default).strip().strip('"').strip("'")


# ==================== الإعدادات ====================
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

# اختياري: لو حطيت مفتاح Gemini هيشتغل كاحتياطي لو Groq وقع
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# AI_DEBUG=1 يعرض سبب الفشل في الرد
DEBUG_ERRORS = _env("AI_DEBUG", "0") == "1"

TRIGGER = "زيرو"
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

# ==================== MongoDB ====================
MONGO_URI = _env("MONGODB_URI")
ai_config_col = None
if MONGO_URI:
    try:
        _mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        ai_config_col = _mongo["Global_Bot_DB"]["ai_system_config"]
    except Exception as e:
        log.error("فشل الاتصال بـ MongoDB: %s", e)
else:
    log.warning("MONGODB_URI غير موجود، الإعدادات مش هتتحفظ بعد إعادة التشغيل.")


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
        log.info(
            "AI keys -> Groq: %s | Gemini: %s",
            "موجود" if GROQ_API_KEY else "غير موجود",
            "موجود" if GEMINI_API_KEY else "غير موجود",
        )

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ---------- قاعدة البيانات ----------
    def _load_config_db(self) -> dict:
        if ai_config_col is None:
            return {}
        try:
            doc = ai_config_col.find_one({"_id": "ai_config_main"})
            if not doc:
                ai_config_col.insert_one({"_id": "ai_config_main", "guilds": {}})
                return {}
            return doc.get("guilds", {})
        except Exception as e:
            log.error("فشل قراءة الإعدادات من MongoDB: %s", e)
            return {}

    def _save_config_sync(self):
        if ai_config_col is None:
            return
        ai_config_col.update_one(
            {"_id": "ai_config_main"},
            {"$set": {"guilds": self.settings}},
            upsert=True,
        )

    async def save_config(self):
        async with self._save_lock:
            try:
                await asyncio.to_thread(self._save_config_sync)
            except Exception as e:
                log.error("فشل حفظ الإعدادات في MongoDB: %s", e)

    # ---------- مزودو الذكاء الاصطناعي ----------
    async def _call_groq(self, messages: list[dict]) -> tuple[str | None, str]:
        if not GROQ_API_KEY:
            return None, "Groq: المفتاح GROQ_API_KEY غير موجود"

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        last_error = "Groq: فشل غير معروف"

        for model in GROQ_MODELS:
            payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 1024}
            for attempt in range(2):
                try:
                    async with self.session.post(GROQ_URL, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            text = (data["choices"][0]["message"]["content"] or "").strip()
                            if text:
                                return text, ""
                            last_error = f"Groq ({model}): رد فاضي"
                            break
                        body = (await resp.text())[:200].replace("\n", " ")
                        last_error = f"Groq {resp.status} ({model}): {body}"
                        log.warning(last_error)
                        if resp.status in (401, 403):
                            return None, last_error
                        if resp.status == 429 or resp.status >= 500:
                            await asyncio.sleep(1.5 * (attempt + 1))
                            continue
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_error = f"Groq اتصال: {type(e).__name__}: {e}"
                    log.warning(last_error)
                    await asyncio.sleep(1)
                except (KeyError, IndexError, ValueError) as e:
                    last_error = f"Groq رد غير متوقع: {e}"
                    log.error(last_error)
                    break
        return None, last_error

    async def _call_gemini(self, messages: list[dict]) -> tuple[str | None, str]:
        if not GEMINI_API_KEY:
            return None, "Gemini: المفتاح غير موجود"

        system_text = messages[0]["content"]
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages[1:]
        ]
        payload = {
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
        }
        headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
        url = GEMINI_URL.format(model=GEMINI_MODEL)

        err = "Gemini: فشل غير معروف"
        for attempt in range(2):
            try:
                async with self.session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        parts = data["candidates"][0]["content"]["parts"]
                        text = "".join(p.get("text", "") for p in parts).strip()
                        if text:
                            return text, ""
                        return None, "Gemini: رد فاضي"
                    body = (await resp.text())[:200].replace("\n", " ")
                    err = f"Gemini {resp.status} ({GEMINI_MODEL}): {body}"
                    log.warning(err)
                    if resp.status == 429 or resp.status >= 500:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    return None, err
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                err = f"Gemini اتصال: {type(e).__name__}: {e}"
                log.warning(err)
                await asyncio.sleep(1)
            except (KeyError, IndexError, ValueError) as e:
                err = f"Gemini رد غير متوقع: {e}"
                log.error(err)
                return None, err
        return None, err

    async def _generate(self, messages: list[dict]) -> tuple[str | None, str]:
        if self.session is None:
            return None, "الجلسة غير مفعّلة"
        errors = []
        for provider in (self._call_groq, self._call_gemini):
            text, err = await provider(messages)
            if text:
                return text, ""
            errors.append(err)
        return None, "\n".join(errors)

    async def get_ai_response(self, key: tuple[int, int], prompt: str) -> tuple[str | None, str]:
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + list(self.history[key])
            + [{"role": "user", "content": prompt}]
        )
        text, err = await self._generate(messages)
        if text:
            self.history[key].append({"role": "user", "content": prompt})
            self.history[key].append({"role": "assistant", "content": text})
            if len(self.history) > 1000:
                self.history.clear()
        return text, err

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

    @app_commands.command(name="ai_test", description="[إدارة] اختبار الاتصال بالذكاء الاصطناعي")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        lines = [
            f"Groq: {'✅ مفتاح موجود' if GROQ_API_KEY else '❌ مفتاح غير موجود'}"
            + (f" (طوله {len(GROQ_API_KEY)}، {'يبدأ بـ gsk_ ✅' if GROQ_API_KEY.startswith('gsk_') else 'لا يبدأ بـ gsk_ ❌'})" if GROQ_API_KEY else ""),
            f"Gemini: {'✅ مفتاح موجود' if GEMINI_API_KEY else '➖ غير مستخدم'}",
            f"MongoDB: {'✅ متصل' if ai_config_col is not None else '❌ غير مفعّل'}",
            "",
        ]
        text, err = await self._generate([
            {"role": "system", "content": "رد بكلمة واحدة فقط."},
            {"role": "user", "content": "قل: يعمل"},
        ])
        if text:
            lines.append(f"✅ الاتصال شغال! رد الذكاء الاصطناعي: {text[:100]}")
        else:
            lines.append(f"❌ فشل الاتصال:\n```{err[:900]}```")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="ai_reset", description="مسح ذاكرة المحادثة بينك وبين الذكاء الاصطناعي")
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
            reply, err = await self.get_ai_response(key, clean)

        if reply is None:
            reply = "⚠️ مش قادر أوصل للذكاء الاصطناعي دلوقتي."
            if DEBUG_ERRORS and err:
                reply += f"\n```{err[:600]}```"

        chunks = split_message(reply)
        await message.reply(chunks[0], allowed_mentions=no_ping, mention_author=False)
        for chunk in chunks[1:]:
            await message.channel.send(chunk, allowed_mentions=no_ping)

    # ---------- أمر اختبار ----------
    @commands.command(name="ai_ping")
    async def ai_ping(self, ctx: commands.Context):
        status = "✅ موجود" if GROQ_API_KEY else "❌ غير موجود"
        await ctx.send(f"Pong! 🏓 البوت شغال. مفتاح Groq: {status}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
