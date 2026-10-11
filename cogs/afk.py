import discord
from discord import app_commands
from discord.ext import commands
import datetime
import time
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# تحميل متغيرات البيئة للاتصال بقاعدة البيانات
load_dotenv()
MONGO_URI = os.getenv("MONGODB_URI")

# الاتصال بقاعدة بيانات MongoDB السحابية
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["Global_Bot_DB"]
afk_col = db["afk_users_data"]

# ==============================================================================
# 🧠 وظائف إدارة قاعدة البيانات السحابية للـ AFK
# ==============================================================================
def load_afk_db():
    doc = afk_col.find_one({"_id": "main_afk_db"})
    if not doc:
        initial_data = {
            "_id": "main_afk_db",
            "users": {}
        }
        afk_col.insert_one(initial_data)
        return {}
    return doc.get("users", {})

def save_afk_db(data):
    afk_col.update_one(
        {"_id": "main_afk_db"},
        {"$set": {"users": data}},
        upsert=True
    )

def set_user_afk(user_id: int, reason: str):
    db_data = load_afk_db()
    u_str = str(user_id)
    is_update = u_str in db_data
    
    current_time = time.time()
    db_data[u_str] = {
        "reason": reason,
        "time": current_time if not is_update else db_data[u_str].get("time", current_time)
    }
    save_afk_db(db_data)
    return is_update

def remove_user_afk(user_id: int):
    db_data = load_afk_db()
    u_str = str(user_id)
    if u_str in db_data:
        afk_info = db_data.pop(u_str)
        save_afk_db(db_data)
        return afk_info
    return None

def get_user_afk(user_id: int):
    db_data = load_afk_db()
    return db_data.get(str(user_id))


# ==============================================================================
# 🎨 واجهة تفاعلية لاستعراض الأعضاء الغائبين
# ==============================================================================
class AFKListPaginationView(discord.ui.View):
    def __init__(self, afk_members_list, author_id: int, guild_name: str):
        super().__init__(timeout=60)
        self.afk_members_list = afk_members_list
        self.author_id = author_id
        self.guild_name = guild_name
        self.current_page = 0
        self.per_page = 5
        self.max_pages = (len(afk_members_list) - 1) // self.per_page + 1

    def create_embed(self):
        embed = discord.Embed(
            title="🛑 ╎ قائمة الغائبين حالياً (AFK)",
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_items = self.afk_members_list[start_idx:end_idx]

        for item in page_items:
            m_mention = item["mention"]
            reason = item["reason"]
            time_str = item["time_str"]
            embed.add_field(
                name=f"👤 العضو: {item['name']}",
                value=f"> 📌 **السبب:** `{reason}`\n> ⏱️ **غائب منذ:** `{time_str}`\n> 🆔 **المنشن:** {m_mention}\n\u200b",
                inline=False
            )

        embed.set_footer(text=f"صفحة {self.current_page + 1} من {self.max_pages} ✦ {self.guild_name} AFK Engine")
        return embed

    @discord.ui.button(label="السابق ◀️", style=discord.ButtonStyle.primary, custom_id="afk_prev_page")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك!", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.send_message("⚠️ أنت في الصفحة الأولى بالفعل!", ephemeral=True)

    @discord.ui.button(label="التالي ▶️", style=discord.ButtonStyle.primary, custom_id="afk_next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك!", ephemeral=True)
            return
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.send_message("⚠️ أنت في الصفحة الأخيرة بالفعل!", ephemeral=True)


# ==============================================================================
# 🚀 الكوج الرئيسي لنظام الـ AFK المطور
# ==============================================================================
class AFKSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. أمر السلاش /afk
    @app_commands.command(name="afk", description="الدخول في وضع الـ AFK وتنبيه من يمنشنك تلقائياً")
    @app_commands.describe(reason="السبب وراء خروجك أو غيابك (اختياري)")
    async def slash_afk(self, interaction: discord.Interaction, reason: str = "مشغول في مصلحة سرية 🕵️‍♂️"):
        await interaction.response.defer()
        
        user_id = interaction.user.id
        is_update = set_user_afk(user_id, reason)
        guild_name = interaction.guild.name if interaction.guild else "AFK System"

        if is_update:
            msg = f"🔄 يا عم إنت لسه قايل رايح فين! ماشي يا سيدي، **عدلنا السبب** وخليناه: `{reason}`.. كمل غيابك على نظافة بقى 😂"
        else:
            msg = (
                f"☕ **استريح يا بطل `{interaction.user.name}`، قطعت كارت إنك غايب وخلاص!**\n"
                f"📌 **السبب الموثق:** `{reason}`\n"
                f"🤖 *توكل على الله ومتقلقش، واقفين حراس لأي حد يمنشنك في الشات!*"
            )

        embed = discord.Embed(
            description=msg,
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"{guild_name} AFK System ✦ ترجع بالسلامة يا فنان")
        await interaction.followup.send(embed=embed)

    # 2. أمر السلاش /afk_list لاستعراض كافة الغائبين
    @app_commands.command(name="afk_list", description="عرض قائمة بجميع الأعضاء المتواجدين في وضع الـ AFK حالياً")
    async def afk_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        db_data = load_afk_db()
        if not db_data:
            embed_empty = discord.Embed(
                title="✨ القائمة فارغة",
                description="مفيش أي عضو في وضع الـ AFK حالياً في السيرفر! الكل صاحي ومصحصح 🦅",
                color=0x2ECC71
            )
            await interaction.followup.send(embed=embed_empty, ephemeral=True)
            return

        afk_members_list = []
        for u_id_str, info in db_data.items():
            member = interaction.guild.get_member(int(u_id_str))
            m_name = member.display_name if member else f"عضو مغادر ({u_id_str})"
            m_mention = member.mention if member else f"<@{u_id_str}>"
            
            elapsed_seconds = int(time.time() - info.get("time", time.time()))
            hours, rem = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            
            if hours > 0:
                time_str = f"{hours} ساعة و {minutes:02d} دقيقة"
            else:
                time_str = f"{minutes:02d} دقيقة و {seconds:02d} ثانية"

            afk_members_list.append({
                "name": m_name,
                "mention": m_mention,
                "reason": info.get("reason", "بدون سبب"),
                "time_str": time_str
            })

        guild_name = interaction.guild.name if interaction.guild else "Server"
        view = AFKListPaginationView(afk_members_list, interaction.user.id, guild_name)
        await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=True)

    # 3. أمر إداري لفك الـ AFK يدوياً لعضو
    @app_commands.command(name="afk_clear", description="[إدارة] إزالة وضع الـ AFK لعضو معين يدوياً")
    @app_commands.describe(member="العضو المراد إزالة الـ AFK عنه")
    @app_commands.checks.has_permissions(administrator=True)
    async def afk_clear(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        afk_info = remove_user_afk(member.id)
        if afk_info:
            embed = discord.Embed(
                title="✅ تم إزالة وضع الـ AFK",
                description=f"قام الأدمن {interaction.user.mention} بإزالة وضع الـ AFK عن العضو {member.mention} بنجاح.",
                color=0x2ECC71
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ العضو {member.mention} ليس في وضع الـ AFK أساساً!", ephemeral=True)

    # 4. الاستماع للرسائل (الرد على الكتابة العادية + الرد الكوميدي على المنشنات + الفك التلقائي)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_name = message.guild.name

        # أ. إذا كتب العضو الغائب رسالة -> يتم فك الـ AFK فوراً مع رد حماسي
        user_afk_data = get_user_afk(user_id)
        if user_afk_data:
            afk_info = remove_user_afk(user_id)
            start_time = afk_info.get("time", time.time())
            reason = afk_info.get("reason", "غير معروف")
            
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
            welcome_back_embed.set_footer(text=f"{guild_name} AFK Core ✦ نورت بيتك يا فنان")
            try:
                await message.reply(embed=welcome_back_embed)
            except Exception:
                pass

        # ب. التفعيل السريع بالكتابة العادية في الشات (مثال: afk رايح أشرب)
        content_lower = message.content.strip().lower()
        if content_lower.startswith("afk ") or content_lower.startswith("باَفْك ") or content_lower.startswith("بافك "):
            parts = message.content.split(maxsplit=1)
            reason = parts[1] if len(parts) > 1 else "بيعمل حاجات مهمة وراجع 🚶‍♂️"
            
            is_update = set_user_afk(user_id, reason)

            if is_update:
                quick_msg = f"🔄 يابن الحلال إنت لسه مفعله! بس ولا يهمك، غيرنا السبب وخليناه: `{reason}`.. كمل مشوارك 😂"
            else:
                quick_msg = f"🚀 تمام يا فنان `{message.author.name}`، طار في وضع الـ AFK!\n📝 **السبب:** `{reason}`\n☕ *سيبك من الشات خالص وأنا هظبط أي حد يجيب سيرتك.*"

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

        # ج. الرد الكوميدي الساخر عند منشن الأعضاء الغائبين
        if message.mentions:
            for mentioned_user in message.mentions:
                afk_data = get_user_afk(mentioned_user.id)
                if afk_data:
                    reason = afk_data.get("reason", "مشغول")
                    
                    elapsed_seconds = int(time.time() - afk_data.get("time", time.time()))
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
                    comedy_embed.set_footer(text=f"{guild_name} Comedy Protection ✦ الشخص مشغول وبايع السيرفر حالياً")
                    try:
                        await message.reply(embed=comedy_embed)
                    except Exception:
                        pass
                    break


async def setup(bot):
    await bot.add_cog(AFKSystemCog(bot))
