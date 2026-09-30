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

    # 1. أمر السلاش /afk بردود حية وكوميدية
    @app_commands.command(
        name="afk",
        description="الدخول في وضع الـ AFK"
    )
    @app_commands.describe(reason="السبب وراء خروجك (اختياري)")
    async def slash_afk(self, interaction: discord.Interaction, reason: str = "مشغول في مصلحة سرية 🕵️‍♂️"):
        user_id = interaction.user.id
        current_time = time.time()
        
        is_update = user_id in AFK_USERS_DATABASE
        
        AFK_USERS_DATABASE[user_id] = {
            "reason": reason,
            "time": current_time if not is_update else AFK_USERS_DATABASE[user_id]["time"]
        }

        if is_update:
            msg = f"🔄 يا عم إنت لسه قايل رايح فين! ماشي يا سيدي، **عدلنا السبب** وخليناه: `{reason}`.. كمل غيابك على نظافة بقى 😂"
        else:
            msg = f"☕ استريح يا بطل `{interaction.user.name}`، قطعت كارت إنك غايب وخلاص!\n📌 السبب الموثق: `{reason}`\n🤖 *توكل على الله ومتقلقش، واقفين حراس لأي حد يمنشنك!*"

        embed = discord.Embed(
            description=msg,
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="ZIUO AFK System ✦ ترجع بالسلامة يا فنان")
        await interaction.response.send_message(embed=embed)

    # 2. الاستماع للرسائل (كتابة عادية، فك الـ AFK، والرد الكوميدي على المنشنات)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id

        # أ. إذا رجع العضو وكتب رسالة -> فك الـ AFK برد حماسي وكوميدي
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
                    f"😂 **يا هلا باللي نور الكل! إيه يا اسطى هو إنت غبت `{time_str}` عشان `{reason}`؟!**\n"
                    f"يا راجل ده إحنا كنا خلاص هنفرش العزاء ونقسم تركتك في السيرفر.. حمدالله على السلامة يا عريس 🦅"
                )
            else:
                comedy_reply = (
                    f"😏 **أوووه، الحج ظهر والنور طرد العتمة! يعني كنت قاعد `{time_str}` بس؟**\n"
                    f"بس الصراحة الصراحة.. أنا كنت حاسس إنك عامل الحوار ده تمثيل وخلاص عشان تشغل الناس بيك! منور يا بطل ✨"
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

        # ب. التفعيل السريع بالكتابة العادية في الشات (مثال: afk رايح أشرب)
        content_lower = message.content.strip().lower()
        if content_lower.startswith("afk ") or content_lower.startswith("باَفْك ") or content_lower.startswith("بافك "):
            parts = message.content.split(maxsplit=1)
            reason = parts[1] if len(parts) > 1 else "بيعمل حاجات مهمة وراجع 🚶‍♂️"
            
            is_update = user_id in AFK_USERS_DATABASE
            
            AFK_USERS_DATABASE[user_id] = {
                "reason": reason,
                "time": time.time() if not is_update else AFK_USERS_DATABASE[user_id]["time"]
            }

            if is_update:
                quick_msg = f"🔄 يابن الحلال إنت لسه مفعله! بس ولا يهمك، غيرنا السبب وخليناه: `{reason}`.. كمل مشوارك 😂"
            else:
                quick_msg = f"🚀 تمام يا فنان `{message.author.name}`، طار في وضع الـ AFK!\n📝 السبب: `{reason}`\n☕ سيبك من الشات خالص وأنا هظبط أي حد يجيب سيرتك."

            quick_embed = discord.Embed(
                description=quick_msg,
                color=0xE67E22,
                timestamp=datetime.datetime.utcnow()
            )
            try:
                await message.reply(embed=quick_embed)
            except Exception:
                pass
            return

        # ج. الرد الكوميدي الساخر على منشن الأعضاء الغائبين
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
                            f"⚠️ **يا عم `{message.author.name}` بالراحة عليه شوية سيبه في حاله!**\n"
                            f"هو تقريباً `{mentioned_user.name}` عمل حركة الـ AFK دي هرباً من إزعاجك الكوميدي أصلاً 😂\n\n"
                            f"📌 **السبب اللي كاتبه:** `{reason}`\n"
                            f"⏱️ **غایب بقاله:** `{time_str}`\n\n"
                            f"🤖 *ريح نفسك وبطل منشنات، مش هيرد عليك غير لما يشرف بنفسه!*"
                        ),
                        color=0xE74C3C,
                        timestamp=datetime.datetime.utcnow()
                    )
                    comedy_embed.set_footer(text="ZIUO Comedy Protection ✦ الشخص مشغول وبايع السيرفر حالياً")
                    try:
                        await message.reply(embed=comedy_embed)
                    except Exception:
                        pass
                    break

async def setup(bot):
    await bot.add_cog(AFKSystemCog(bot))
