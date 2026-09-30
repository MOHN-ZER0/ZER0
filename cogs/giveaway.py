import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
import random
from typing import Optional, Literal

# ==============================================================================
# 🌟 قاعدة البيانات ونظام الذاكرة المركزي للسحوبات الإمبراطورية
# ==============================================================================
GW_DB_FILE = "ziuo_giveaway_enterprise_database.json"

def load_gw_db():
    if os.path.exists(GW_DB_FILE):
        try:
            with open(GW_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_gw_db(data):
    with open(GW_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==============================================================================
# 🌟 واجهة الأزرار التفاعلية للمشاركة في السحب
# ==============================================================================
class EnterpriseGiveawayButtonView(discord.ui.View):
    def __init__(self, bot, gw_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.gw_id = gw_id

    @discord.ui.button(label="انضمام للسحب 🎉", style=discord.ButtonStyle.success, custom_id="enterprise_gw_join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_gw_db()
        guild_id = str(interaction.guild.id)
        
        if guild_id not in db or self.gw_id not in db[guild_id]["giveaways"]:
            await interaction.response.send_message("❌ **عذراً، هذا السحب غير مسجل أو انتهى تماماً!**", ephemeral=True)
            return

        gw = db[guild_id]["giveaways"][self.gw_id]
        if not gw["active"]:
            await interaction.response.send_message("❌ **هذا السحب منتهي ولا يمكن الانضمام إليه.**", ephemeral=True)
            return

        user_id = str(interaction.user.id)

        # فحص القائمة السوداء
        if user_id in db[guild_id].get("blacklist", []):
            await interaction.response.send_message("❌ **أنت مسجل في القائمة السوداء لهذا السحب ولا يمكنك المشاركة!**", ephemeral=True)
            return

        # فحص عمر الحساب
        min_days = gw.get("min_account_days", 0)
        if min_days > 0:
            account_age = (datetime.datetime.utcnow() - interaction.user.created_at).days
            if account_age < min_days:
                await interaction.response.send_message(f"❌ **يجب أن يكون عمر حسابك على الأقل {min_days} يوماً للمشاركة!**", ephemeral=True)
                return

        if user_id in gw["participants"]:
            gw["participants"].remove(user_id)
            save_gw_db(db)
            await interaction.response.send_message("📤 **تم إزالتك من قائمة المشاركين في السحب بنجاح.**", ephemeral=True)
        else:
            gw["participants"].append(user_id)
            save_gw_db(db)
            await interaction.response.send_message("📥 **تم تسجيل مشاركتك بنجاح في السحب! بالتوفيق 🎉**", ephemeral=True)


# ==============================================================================
# 🌟 الـ Cog العملاق والمتكامل لإدارة الجيف أواي بنظام الإمبراطورية الشامل
# ==============================================================================
class ZiuoGiveawayEnterpriseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.database = load_gw_db()
        self.check_giveaways_loop.start()

    def cog_unload(self):
        self.check_giveaways_loop.cancel()

    # دالة مساعدة لإرسال اللوقات (Logs)
    async def send_log(self, guild, action_title, description):
        guild_id = str(guild.id)
        if guild_id not in self.database:
            return
        log_channel_id = self.database[guild_id].get("logs", {}).get("channel_id")
        if not log_channel_id:
            return
        ch = guild.get_channel(log_channel_id)
        if ch:
            embed = discord.Embed(
                title=f"📊 [لوق الجيف أواي] {action_title}",
                description=description,
                color=0x3498DB,
                timestamp=datetime.datetime.utcnow()
            )
            try:
                await ch.send(embed=embed)
            except:
                pass

    # 1. إعدادات اللوقات العامة
    @app_commands.command(
        name="gw_set_log",
        description="[اللوقات] تحديد روم خاصة لتسجيل أحداث وإشعارات الجيف أواي تلقائياً"
    )
    @app_commands.describe(channel="روم اللوقات الجديدة")
    @app_commands.checks.has_permissions(administrator=True)
    async def gw_set_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}
        
        self.database[guild_id]["logs"]["channel_id"] = channel.id
        save_gw_db(self.database)
        await interaction.response.send_message(f"✅ **تم ضبط روم لوقات الجيف أواي بنجاح على:** {channel.mention}", ephemeral=True)

    # 2. إعدادات السحوبات الافتراضية (عمر الحساب والرسائل الخاصة)
    @app_commands.command(
        name="gw_settings",
        description="[الإعدادات] ضبط الحد الأدنى لعمر الحساب والرسائل الخاصة للفائزين"
    )
    @app_commands.describe(
        min_account_days="الحد الأدنى الافتراضي لأيام إنشاء الحساب",
        dm_winners="إرسال رسالة خاصة تلقائية للفائزين (True/False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def gw_settings(
        self,
        interaction: discord.Interaction,
        min_account_days: Optional[int] = None,
        dm_winners: Optional[bool] = None
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}

        if min_account_days is not None:
            self.database[guild_id]["settings"]["min_account_days"] = min_account_days
        if dm_winners is not None:
            self.database[guild_id]["settings"]["dm_winners"] = dm_winners

        save_gw_db(self.database)
        await interaction.response.send_message("⚙️ **تم تحديث إعدادات الجيف أواي الافتراضية بنجاح!**", ephemeral=True)

    # 3. إدارة القوالب (Templates)
    @app_commands.command(
        name="gw_template_create",
        description="[القوالب] إنشاء قالب جيف أواي جاهز ومحفوظ للاستخدام السريع"
    )
    @app_commands.describe(template_name="اسم القالب", prize_title="عنوان الجائزة", winners_count="عدد الفائزين")
    @app_commands.checks.has_permissions(administrator=True)
    async def gw_template_create(self, interaction: discord.Interaction, template_name: str, prize_title: str, winners_count: int = 1):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {"giveaways": {}, "blacklist": {}, "templates": {}, "logs": {}, "settings": {}}

        t_key = template_name.lower().strip()
        self.database[guild_id]["templates"][t_key] = {"prize": prize_title, "winners": winners_count}
        save_gw_db(self.database)
        await interaction.response.send_message(f"✅ **تم إنشاء وحفظ قالب الجيف أواي باسم:** `{t_key}`", ephemeral=True)

    # 4. إدارة القائمة السوداء (Blacklist)
    @app_commands.command(
        name="gw_blacklist",
        description="[القائمة السوداء] حظر أو إزالة مستخدم من المشاركة في كافة السحوبات"
    )
    @app_commands.describe(action="نوع الإجراء (إضافة أو إزالة)", user="العضو المستهدف")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="إضافة للقائمة السوداء", value="add"),
            app_commands.Choice(name="إزالة من القائمة السوداء", value="remove")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def gw_blacklist(self, interaction: discord.Interaction, action: Literal["add", "remove"], user: discord.Member):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}

        user_id = str(user.id)
        bl = self.database[guild_id]["blacklist"]

        if action == "add":
            if user_id not in bl:
                bl.append(user_id)
                save_gw_db(self.database)
                await interaction.response.send_message(f"🚫 **تم إضافة العضو {user.mention} إلى القائمة السوداء للجيف أواي.**", ephemeral=True)
                await self.send_log(interaction.guild, "إضافة للقائمة السوداء", f"تم حظر العضو {user.mention} بواسطة {interaction.user.mention}")
            else:
                await interaction.response.send_message("⚠️ **العضو موجود مسبقاً في القائمة السوداء.**", ephemeral=True)
        else:
            if user_id in bl:
                bl.remove(user_id)
                save_gw_db(self.database)
                await interaction.response.send_message(f"✅ **تم إزالة العضو {user.mention} من القائمة السوداء.**", ephemeral=True)
                await self.send_log(interaction.guild, "إزالة من القائمة السوداء", f"تم رفع الحظر عن العضو {user.mention} بواسطة {interaction.user.mention}")
            else:
                await interaction.response.send_message("⚠️ **العضو ليس موجوداً في القائمة السوداء.**", ephemeral=True)

    # 5. بدء جيف أواي احترافي جديد مع إمكانية اختيار طريقة المشاركة (زر أو رياكشن) وتخصيص الرسالة
    @app_commands.command(
        name="giveaway_start",
        description="[السحوبات] إنشاء وانطلاق جيف أواي جديد مع تحديد طريقة المشاركة (زر تفاعلي أو رياكشن)"
    )
    @app_commands.describe(
        channel="روم نشر الجيف أواي",
        prize="عنوان وجائزة السحب",
        duration_minutes="مدة السحب بالدقائق",
        winners_count="عدد الفائزين",
        entry_method="طريقة المشاركة: زر تفاعلي (button) أو رياكشن (reaction)",
        custom_message="رسالة أو نص إضافي يظهر داخل الجيف أواي (اختياري)",
        image_url="رابط صورة الجائزة (اختياري)"
    )
    @app_commands.choices(
        entry_method=[
            app_commands.Choice(name="زر تفاعلي (Interactive Button)", value="button"),
            app_commands.Choice(name="تفاعل رياكشن (Reaction Emoji)", value="reaction")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        prize: str,
        duration_minutes: int,
        winners_count: int = 1,
        entry_method: Literal["button", "reaction"] = "button",
        custom_message: Optional[str] = None,
        image_url: Optional[str] = None
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}

        gw_id = str(random.randint(100000, 999999))
        ends_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration_minutes)
        min_days = self.database[guild_id]["settings"].get("min_account_days", 0)

        desc = (
            f"{custom_message}\n\n" if custom_message else ""
        ) + (
            f"> 🎁 **الجائزة:** **{prize}**\n"
            f"> 🏆 **عدد الفائزين:** `{winners_count}`\n"
            f"> ⏳ **ينتهي في:** <t:{int(ends_at.timestamp())}:R>\n"
            f"> 🎮 **طريقة المشاركة:** `{'اضغط على الزر بالأسفل 👇' if entry_method == 'button' else 'اضغط على رياكشن 🎉 بالأسفل'}`\n"
            f"> 👤 **بواسطة:** {interaction.user.mention}\n"
            f"> 🛡 **أدنى عمر للحساب:** `{min_days} يوم`"
        )

        embed = discord.Embed(
            title="🎉 **جـيـف أواي جـديـد ومـمـيـز!** 🎉",
            description=desc,
            color=0xF1C40F,
            timestamp=datetime.datetime.utcnow()
        )
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text=f"Giveaway ID: {gw_id} | المشاركة عبر {entry_method}")

        view = EnterpriseGiveawayButtonView(self.bot, gw_id) if entry_method == "button" else None
        msg = await channel.send(embed=embed, view=view)

        if entry_method == "reaction":
            await msg.add_reaction("🎉")

        self.database[guild_id]["giveaways"][gw_id] = {
            "channel_id": channel.id,
            "message_id": msg.id,
            "prize": prize,
            "winners_count": winners_count,
            "ends_at": ends_at.strftime("%Y-%m-%d %H:%M:%S"),
            "participants": [],
            "active": True,
            "entry_method": entry_method,
            "min_account_days": min_days
        }
        save_gw_db(self.database)

        await interaction.response.send_message(f"✅ **تم بنجاح بدء الجيف أواي في روم** {channel.mention} برقم مرجعي `{gw_id}`!", ephemeral=True)
        await self.send_log(interaction.guild, "تم إنشاء جيف-اواي", f"تم إنشاء جيف أواي لجائزة **{prize}** بواسطة {interaction.user.mention}")

    # 6. إعادة سحب (Reroll)
    @app_commands.command(
        name="giveaway_reroll",
        description="[السحوبات] إعادة السحب واختيار فائز جديد بديل"
    )
    @app_commands.describe(gw_id="رقم الجيف أواي المرجعي")
    @app_commands.checks.has_permissions(administrator=True)
    async def giveaway_reroll(self, interaction: discord.Interaction, gw_id: str):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database or gw_id not in self.database[guild_id]["giveaways"]:
            await interaction.response.send_message("❌ **رقم السحب غير صحيح!**", ephemeral=True)
            return

        gw = self.database[guild_id]["giveaways"][gw_id]
        
        # إذا كانت المشاركة برياكشن، نقوم بتحديث قائمة المشاركين من الرسالة الحية فوراً
        if gw["entry_method"] == "reaction":
            try:
                channel = interaction.guild.get_channel(gw["channel_id"])
                msg = await channel.fetch_message(gw["message_id"])
                for reaction in msg.reactions:
                    if str(reaction.emoji) == "🎉":
                        async for user in reaction.users():
                            if not user.bot and str(user.id) not in gw["participants"]:
                                gw["participants"].append(str(user.id))
            except:
                pass

        if not gw["participants"]:
            await interaction.response.send_message("❌ **لا يوجد مشاركين متاحين لإعادة السحب!**", ephemeral=True)
            return

        winner_id = random.choice(gw["participants"])
        winner_member = interaction.guild.get_member(int(winner_id))
        winner_mention = winner_member.mention if winner_member else f"<@{winner_id}>"

        await interaction.response.send_message(f"🔄 **تمت إعادة السحب بنجاح! الفائز الجديد هو:** {winner_mention} مبروك جائزة ({gw['prize']})! 🎉")
        await self.send_log(interaction.guild, "إعادة سحب جيف-اواي", f"تم اختيار فائز بديل جديد: {winner_mention} للسحب `{gw_id}`")

    # 7. لووب تلقائي لفحص وإدارة السحوبات والنتائج
    @tasks.loop(seconds=30)
    async def check_giveaways_loop(self):
        db = load_gw_db()
        now = datetime.datetime.utcnow()

        for guild_id, data in db.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            for gw_id, gw in data.get("giveaways", {}).items():
                if not gw["active"]:
                    continue

                ends_at = datetime.datetime.strptime(gw["ends_at"], "%Y-%m-%d %H:%M:%S")
                if now >= ends_at:
                    gw["active"] = False
                    save_gw_db(db)

                    channel = guild.get_channel(gw["channel_id"])
                    if not channel:
                        continue

                    try:
                        msg = await channel.fetch_message(gw["message_id"])
                    except:
                        msg = None

                    # إذا كانت المشاركة عبر رياكشن، نجمع المشاركين من التفاعلات الحية للرسالة
                    if gw["entry_method"] == "reaction" and msg:
                        for reaction in msg.reactions:
                            if str(reaction.emoji) == "🎉":
                                async for user in reaction.users():
                                    if not user.bot and str(user.id) not in gw["participants"] and str(user.id) not in data.get("blacklist", []):
                                        gw["participants"].append(str(user.id))

                    participants = gw["participants"]
                    winners_count = gw["winners_count"]

                    if not participants:
                        result_text = f"❌ **انتهى السحب على ({gw['prize']})، ولم يشارك أي شخص للأسف!**"
                    else:
                        winners = random.sample(participants, min(len(participants), winners_count))
                        winners_mentions = []
                        for wid in winners:
                            member = guild.get_member(int(wid))
                            if member:
                                winners_mentions.append(member.mention)
                                if data["settings"].get("dm_winners", False):
                                    try:
                                        await member.send(f"🎉 **تهانينا! لقد فزت بجائزة ({gw['prize']}) في سيرفر {guild.name}!**")
                                    except:
                                        pass
                            else:
                                winners_mentions.append(f"<@{wid}>")
                        
                        result_text = f"🎊 **انتهى السحب! الفائزون هم:** {', '.join(winners_mentions)}\n🎁 **الجائزة:** **{gw['prize']}**"

                    if msg:
                        try:
                            embed = msg.embeds[0]
                            embed.color = 0xE74C3C
                            embed.title = "🔒 **انـتـهـى الـجـيـف أواي** 🔒"
                            await msg.edit(embed=embed, view=None)
                        except:
                            pass

                    await channel.send(result_text)
                    await self.send_log(guild, "انتهى جيف-اواي", f"انتهى السحب رقم `{gw_id}` للجائزة **{gw['prize']}** وتم إعلان النتائج.")

    @check_giveaways_loop.before_loop
    async def before_check_giveaways_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ZiuoGiveawayEnterpriseCog(bot))
