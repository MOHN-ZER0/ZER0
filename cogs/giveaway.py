import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
import random
from typing import Optional, Literal

# ==============================================================================
# 🌟 قاعدة البيانات ونظام الذاكرة المركزي
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
# 🌟 نوافذ الـ Modals المخصصة لإدخال البيانات بسلاسة
# ==============================================================================
class StartGiveawayModal(discord.ui.Modal, title="إطلاق جيف أواي جديد إمبراطوري"):
    prize_input = discord.ui.TextInput(
        label="اسم الجائزة",
        placeholder="مثال: رتبة VIP أو نيترو أو رصيد...",
        style=discord.TextStyle.short,
        required=True
    )
    duration_input = discord.ui.TextInput(
        label="المدة بالدقائق",
        placeholder="مثال: 60 (يعني ساعة)",
        style=discord.TextStyle.short,
        required=True
    )
    winners_input = discord.ui.TextInput(
        label="عدد الفائزين",
        placeholder="مثال: 1 أو 3",
        style=discord.TextStyle.short,
        default="1",
        required=True
    )
    message_input = discord.ui.TextInput(
        label="رسالة أو وصف إضافي (اختياري)",
        placeholder="شروط أو تفاصيل إضافية...",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(self, bot, channel):
        super().__init__()
        self.bot = bot
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration = int(self.duration_input.value)
            winners_count = int(self.winners_input.value)
        except ValueError:
            await interaction.response.send_message("❌ **خطأ:** المدة وعدد الفائزين يجب أن تكون أرقام صحيحة!", ephemeral=True)
            return

        prize_name = self.prize_input.value
        custom_msg = self.message_input.value
        guild_id = str(interaction.guild.id)
        
        db = load_gw_db()
        if guild_id not in db:
            db[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}

        gw_id = str(random.randint(100000, 999999))
        ends_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration)
        min_days = db[guild_id]["settings"].get("min_account_days", 0)

        desc = (f"💬 **{custom_msg}**\n\n" if custom_msg else "") + \
               f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n" \
               f"🎁 **الجائزة الكبرى:** {prize_name}\n" \
               f"🏆 **عدد الفائزين:** `{winners_count}` فائز\n" \
               f"⏳ **الوقت المتبقي:** <t:{int(ends_at.timestamp())}:R>\n" \
               f"👤 **المُنشئ:** {interaction.user.mention}\n" \
               f"🛡 **أدنى عمر للحساب:** `{min_days}` يوم\n" \
               f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

        embed = discord.Embed(
            title="<a:giveaway:1234567890> **مسـابـقـة جـيـف أواي جـديـدّة**",
            description=desc,
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Giveaway ID: {gw_id} • النظام الاحترافي")

        view = EnterpriseGiveawayButtonView(self.bot, gw_id)
        msg = await self.channel.send(embed=embed, view=view)

        db[guild_id]["giveaways"][gw_id] = {
            "channel_id": self.channel.id,
            "message_id": msg.id,
            "prize": prize_name,
            "prize_type": "custom",
            "winners_count": winners_count,
            "ends_at": ends_at.strftime("%Y-%m-%d %H:%M:%S"),
            "participants": [],
            "active": True,
            "entry_method": "button",
            "min_account_days": min_days
        }
        save_gw_db(db)

        await interaction.response.send_message(f"✅ **تم إطلاق الجيف أواي بنجاح في روم** {self.channel.mention} برقم مرجعي `{gw_id}`!", ephemeral=True)


class RerollModal(discord.ui.Modal, title="إعادة سحب (Reroll) فائز جديد"):
    gw_id_input = discord.ui.TextInput(
        label="رقم الجيف أواي المرجعي (ID)",
        placeholder="أدخل رقم السحب المكون من أرقام...",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        gw_id = self.gw_id_input.value.strip()
        guild_id = str(interaction.guild.id)
        db = load_gw_db()

        if guild_id not in db or gw_id not in db[guild_id]["giveaways"]:
            await interaction.response.send_message("❌ **رقم السحب غير صحيح أو غير موجود في السيرفر!**", ephemeral=True)
            return

        gw = db[guild_id]["giveaways"][gw_id]
        if not gw["participants"]:
            await interaction.response.send_message("❌ **لا توجد مشاركات متاحة في هذا السحب لإعادة السحب!**", ephemeral=True)
            return

        winner_id = random.choice(gw["participants"])
        winner_member = interaction.guild.get_member(int(winner_id))
        winner_mention = winner_member.mention if winner_member else f"<@{winner_id}>"

        await interaction.response.send_message(f"🔄 **تمت إعادة السحب بنجاح!**\n👑 **الفائز البديل الجديد:** {winner_mention}\n🎁 **الجائزة:** {gw['prize']}")


# ==============================================================================
# 🌟 واجهة الأزرار والقوائم المنسدلة التفاعلية الرئيسية (Dashboard)
# ==============================================================================
class GiveawayDashboardSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="إطلاق جيف أواي جديد", description="إنشاء مسابقة جديدة مع زر مشاركة", emoji="🎉", value="start_gw"),
            discord.SelectOption(label="إعادة سحب (Reroll)", description="اختيار فائز بديل لسحب منتهي", emoji="🔄", value="reroll_gw"),
            discord.SelectOption(label="إدارة القائمة السوداء", description="حظر أو إزالة مستخدم من المشاركة", emoji="🚫", value="blacklist_mgmt"),
            discord.SelectOption(label="ضبط روم السجلات (Logs)", description="تحديد الروم الخاصة بتسجيل العمليات", emoji="📊", value="set_logs"),
            discord.SelectOption(label="إعدادات الحماية والأمان", description="تحديد أدنى عمر لحساب المشارك", emoji="⚙️", value="settings_gw")
        ]
        super().__init__(placeholder="اختر الإجراء المطلوب إدارته من القائمة...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        guild_id = str(interaction.guild.id)
        db = load_gw_db()
        if guild_id not in db:
            db[guild_id] = {"giveaways": {}, "blacklist": [], "templates": {}, "logs": {}, "settings": {}}

        if val == "start_gw":
            # نطلب منه تحديد الروم أولاً أو نفتح المودال في نفس الروم الحالية
            await interaction.response.send_modal(StartGiveawayModal(self.bot, interaction.channel))

        elif val == "reroll_gw":
            await interaction.response.send_modal(RerollModal())

        elif val == "blacklist_mgmt":
            await interaction.response.send_message("💡 **لإدارة القائمة السوداء، استخدم الأمر المباشر مع تحديد العضو:**\n`/giveaway-manage blacklist [add/remove] [العضو]`", ephemeral=True)

        elif val == "set_logs":
            db[guild_id]["logs"]["channel_id"] = interaction.channel.id
            save_gw_db(db)
            await interaction.response.send_message(f"✅ **تم تعيين هذه الروم ({interaction.channel.mention}) كروم رسمية لسجلات الجيف أواي بنجاح!**", ephemeral=True)

        elif val == "settings_gw":
            current_days = db[guild_id]["settings"].get("min_account_days", 0)
            await interaction.response.send_message(f"⚙️ **إعدادات الحماية الحالية:**\n- أدنى عمر للحساب للمشاركة: `{current_days}` يوم.\n*(يمكنك تعديلها لاحقاً)*", ephemeral=True)


class GiveawayDashboardView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.add_item(GiveawayDashboardSelect(bot))


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
        if user_id in db[guild_id].get("blacklist", []):
            await interaction.response.send_message("❌ **أنت مسجل في القائمة السوداء لهذا السحب ولا يمكنك المشاركة!**", ephemeral=True)
            return

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
# 🌟 الـ Cog الرئيسي والـ Dashboard المتكاملة
# ==============================================================================
class ZiuoGiveawayDashboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.database = load_gw_db()
        self.check_giveaways_loop.start()

    def cog_unload(self):
        self.check_giveaways_loop.cancel()

    # أمر واحد رئيسي يفتح لك اللوحة المنسدلة بالكامل
    @app_commands.command(
        name="giveaway",
        description="[لوحة التحكم الشاملة] إدارة جميع سحوبات السيرفر من قائمة واحدة تفاعلية"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def giveaway_dashboard(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ **لـوحـة تـحـكـم الـجـيـف أواي الإمـبـراطـوريـة**",
            description=(
                "مرحباً بك يا محمد في لوحة التحكم المركزية للسحوبات والجوائز.\n\n"
                "👇 **اختر الإجراء المناسب من القائمة المنسدلة بالأسفل للتحكم الفوري:**"
            ),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        view = GiveawayDashboardView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # حلقة تلقائية (Loop) للتحقق من انتهاء السحوبات وإعلان الفائزين
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

                    participants = gw["participants"]
                    winners_count = gw["winners_count"]

                    if not participants:
                        result_text = f"❌ **انتهى السحب على ({gw['prize']}) ولم يشارك أي شخص للأسف!**"
                    else:
                        winners = random.sample(participants, min(len(participants), winners_count))
                        winners_mentions = []
                        
                        for idx, wid in enumerate(winners, start=1):
                            member = guild.get_member(int(wid))
                            if member:
                                winners_mentions.append(f"**{idx}.** {member.mention}")
                            else:
                                winners_mentions.append(f"**{idx}.** <@{wid}>")
                        
                        formatted_winners = "\n".join(winners_mentions)
                        result_text = (
                            f"╭━━━ 🎊 **إنـتـهـى الـسـحـب بـنـجـاح** 🎊 ━━━╮\n"
                            f"🎁 **الجائزة:** {gw['prize']}\n"
                            f"👑 **الفائزون بالترتيب:**\n{formatted_winners}\n"
                            f"╰━━━━━━━━━━━━━━━━━━━━╯"
                        )

                    if msg:
                        try:
                            embed_msg = msg.embeds[0]
                            embed_msg.color = 0x2b2d31
                            embed_msg.title = "🔒 **انـتـهـى الـجـيـف أواي (مغلق)** 🔒"
                            await msg.edit(embed=embed_msg, view=None)
                        except:
                            pass

                    await channel.send(result_text)

    @check_giveaways_loop.before_loop
    async def before_check_giveaways_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(ZiuoGiveawayDashboardCog(bot))
ge="رسالة أو نص إضافي يظهر داخل الجيف أواي (اختياري)",
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
