import discord
from discord import app_commands
from discord.ext import commands
import datetime
import time

# ==============================================================================
# 🧠 قاعدة بيانات الـ AFK المؤقتة
# ==============================================================================
AFK_USERS_DATABASE = {}

class AFKSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. أمر السلاش /afk بوصف رسمي ومحدد
    @app_commands.command(
        name="afk",
        description="الدخول في وضع الـ AFK"
    )
    @app_commands.describe(reason="السبب وراء خروجك (اختياري)")
    async def slash_afk(self, interaction: discord.Interaction, reason: str = "مشغول حالياً 🕵️‍♂️"):
        user_id = interaction.user.id
        current_time = time.time()
        
        # ميزة ذكية: لو العضو مسجل AFK بالفعل وتم تحديث أمره
        is_update = user_id in AFK_USERS_DATABASE
        
        AFK_USERS_DATABASE[user_id] = {
            "reason": reason,
            "time": current_time if not is_update else AFK_USERS_DATABASE[user_id]["time"]
        }

        embed = discord.Embed(
            description=(
                f"🚨 **{ '🔄 تم تحديث' if is_update else '🚨 تم تفعيل' } وضع الـ AFK للعضو `{interaction.user.name}` بنجاح!**\n\n"
                f"📌 **السبب:** `{reason}`\n\n"
                f"🤖 *سيتم الرد على أي شخص يقوم بمنشنك حتى تقوم بالعودة.*"
            ),
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="ZIUO AFK System ✦ ترجع بالسلامة")
        await interaction.response.send_message(embed=embed)

    # 2. الاستماع للرسائل (كتابة عادية، فك الـ AFK، والرد الكوميدي على المنشنات)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id

        # أ. إذا رجع العضو وكتب رسالة -> فك الـ AFK والرد برسالة ثابتة لا تُحذف للكل
        if user_id in AFK_USERS_DATABASE:
            afk_data = AFK_USERS_DATABASE.pop(user_id)
            start_time = afk_data["time"]
            reason = afk_data["reason"]
            
            elapsed_seconds = int(time.time() - start_time)
            hours, rem = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            
            if hours > 0:
                time_str = f"{hours}:{minutes:02d} ساعة"
            else:
                time_str = f"{minutes:02d}:{seconds:02d}"

            if hours > 0 or minutes >= 30:
                comedy_reply = (
                    f"😂 **إيه يا اسطى هو إنت غبت `{time_str}` عشان `{reason}`؟!**\n"
                    f"يا راجل ده إحنا كنا قربنا نفتح عزاء ونقسم تركتك في السيرفر! نورت يا عريس 🦅"
                )
            else:
                comedy_reply = (
                    f"😏 **متأخرتش يعني.. طيب كويس، يعني كنت قاعد `{time_str}`.**\n"
                    f"بس الصراحة أنا كنت حاسه إنك عامل كده تمثيل وخلاص عشان تشغل الناس بيك! منور يا بطل ✨"
                )

            welcome_back_embed = discord.Embed(
                description=comedy_reply,
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            welcome_back_embed.set_footer(text="ZIUO AFK Core ✦ نورت بيتك يا فنان")
            try:
                await message.reply(embed=welcome_back_embed)
            except Exception:
                pass

        # ب. التفعيل السريع بالكتابة العادية في الشات مع ميزة منع التكرار الذكية
        content_lower = message.content.strip().lower()
        if content_lower.startswith("afk ") or content_lower.startswith("باَفْك ") or content_lower.startswith("بافك "):
            parts = message.content.split(maxsplit=1)
            reason = parts[1] if len(parts) > 1 else "قاعد بيخلص مصلحة وراجع 🚶‍♂️"
            
            is_update = user_id in AFK_USERS_DATABASE
            
            AFK_USERS_DATABASE[user_id] = {
                "reason": reason,
                "time": time.time() if not is_update else AFK_USERS_DATABASE[user_id]["time"]
            }

            quick_embed = discord.Embed(
                description=(
                    f"⚡ **{ '🔄 تم تحديث' if is_update else '⚡ تم تفعيل' } وضع الـ AFK لـ `{message.author.name}` بنجاح!**\n"
                    f"📝 **السبب:** `{reason}`\n\n"
                    f"☕ سيتم إبلاغ الجميع عند محاولة منشنك."
                ),
                color=0xE67E22,
                timestamp=datetime.datetime.utcnow()
            )
            try:
                await message.reply(embed=quick_embed)
            except Exception:
                pass
            return

        # ج. الرد الكوميدي الساخر على منشن الأعضاء الغائبين (مرئية للكل وثابتة)
        if message.mentions:
            for mentioned_user in message.mentions:
                if mentioned_user.id in AFK_USERS_DATABASE:
                    data = AFK_USERS_DATABASE[mentioned_user.id]
                    reason = data["reason"]
                    
                    elapsed_seconds = int(time.time() - data["time"])
                    hours, rem = divmod(elapsed_seconds, 3600)
                    minutes, seconds = divmod(rem, 60)
                    
                    if hours > 0:
                        time_str = f"{hours}:{minutes:02d} ساعة"
                    else:
                        time_str = f"{minutes:02d}:{seconds:02d}"

                    comedy_embed = discord.Embed(
                        description=(
                            f"⚠️ **يا اسطى `{message.author.name}` سيبه في حاله شوية يا عم!**\n"
                            f"هو تقريباً `{mentioned_user.name}` عمل حركة الـ AFK دي عشان يهرب منك أصلاً 😂\n\n"
                            f"📌 **السبب اللي كاتبه:** `{reason}`\n"
                            f"⏱️ **غایب بقاله:** `{time_str}`\n\n"
                            f"🤖 *بطل منشنات بقى لحد ما يشرف لوحده!*"
                        ),
                        color=0xE74C3C,
                        timestamp=datetime.datetime.utcnow()
                    )
                    comedy_embed.set_footer(text="ZIUO Comedy Protection ✦ الشخص مشغول حالياً")
                    try:
                        await message.reply(embed=comedy_embed)
                    except Exception:
                        pass
                    break

async def setup(bot):
    await bot.add_cog(AFKSystemCog(bot))
