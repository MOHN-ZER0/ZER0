import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os
from typing import Optional, Literal

# ==============================================================================
# 🌟 قاعدة البيانات المركزية لنظام التفاعل التلقائي الخارق
# ==============================================================================
MEGA_AUTOTRAP_DB_FILE = "ziuo_mega_autotrap_database.json"

def load_autotrap_db():
    if os.path.exists(MEGA_AUTOTRAP_DB_FILE):
        try:
            with open(MEGA_AUTOTRAP_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_autotrap_db(data):
    with open(MEGA_AUTOTRAP_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==============================================================================
# 🌟 الـ Cog العملاق والمبسط لإدارة التفاعلات والأنظمة الذكية (أمر واحد شامل)
# ==============================================================================
class ZiuoEnterpriseAutoTrapCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.database = load_autotrap_db()

    @app_commands.command(
        name="autotrap",
        description="[نظام إمبراطوري موحد] إنشاء، تعديل، حذف أو استعراض قواعد التفاعل التلقائي"
    )
    @app_commands.describe(
        action="الإجراء المطلوب تنفيذه على القاعدة",
        action_name="اسم القاعدة الفريد (مثل: support أو welcome)",
        channel="الروم المستهدفة (مطلوبة عند الإنشاء)",
        system_type="نوع النظام الذكي المراد تطبيقه",
        custom_keyword="الكلمة المفتاحية (اختياري)",
        reply_type="نوع الرد (text أو embed أو none)",
        message_content="محتوى الرد أو نص الإمبد (يدعم [user], [userName], [server])",
        image_url="رابط صورة مباشر مرفق (اختياري)",
        reactions="الإيموجيات التلقائية مفصولة بمسافة (مثال: 👍 ❤️)",
        target_role="رتبة يتم منشنها تلقائياً (اختياري)",
        allow_bots="السماح بتفاعل البوت مع البوتات الأخرى (True / False)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="إنشاء قاعدة جديدة (Create)", value="create"),
            app_commands.Choice(name="تعديل قاعدة موجودة (Edit)", value="edit"),
            app_commands.Choice(name="حذف قاعدة (Remove)", value="remove"),
            app_commands.Choice(name="استعراض القواعد (List)", value="list")
        ],
        system_type=[
            app_commands.Choice(name="1. تفاعلات إيموجي ذكية حسب الكلمات (Keyword Reactions)", value="keyword_emoji"),
            app_commands.Choice(name="2. فتح سلسلة نقاش تلقائية Thread (Auto-Thread)", value="auto_thread"),
            app_commands.Choice(name="3. رسالة ترحيب أو رد مع صور (Media & Button Trap)", value="media_trap"),
            app_commands.Choice(name="4. حماية الروابط ومنع السبام (Anti-Link / Spam Shield)", value="anti_spam"),
            app_commands.Choice(name="5. منشن رتبة معينة عند الطلب (Role Mention Trigger)", value="role_mention"),
            app_commands.Choice(name="6. تصويت تلقائي للاقتراحات (Voting Polls Reactions)", value="voting_polls")
        ],
        reply_type=[
            app_commands.Choice(name="رسالة نصية عادية (Text)", value="text"),
            app_Choice_embed=app_commands.Choice(name="قالب إمبد احترافي (Embed)", value="embed"),
            app_Choice_none=app_commands.Choice(name="بدون رسالة (تنفيذ الإجراء فقط)", value="none")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autotrap_manager(
        self,
        interaction: discord.Interaction,
        action: Literal["create", "edit", "remove", "list"],
        action_name: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        system_type: Optional[str] = "keyword_emoji",
        custom_keyword: Optional[str] = None,
        reply_type: Optional[Literal["text", "embed", "none"]] = "text",
        message_content: Optional[str] = None,
        image_url: Optional[str] = None,
        reactions: Optional[str] = None,
        target_role: Optional[discord.Role] = None,
        allow_bots: Optional[bool] = False
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.database:
            self.database[guild_id] = {}

        # 1. استعراض القواعد (List)
        if action == "list":
            if not self.database[guild_id]:
                await interaction.response.send_message("📌 **لا توجد أي قواعد تفاعل تلقائي مسجلة في هذا السيرفر حالياً.**", ephemeral=True)
                return

            embed = discord.Embed(
                title="📋 ╎ قـائـمـة قـواعـد الـتـفـاعـل الـتـلـقـائـي الإمبراطورية",
                color=0x2B2D31,
                timestamp=datetime.datetime.utcnow()
            )
            for name, data in self.database[guild_id].items():
                ch = interaction.guild.get_channel(data["channel_id"])
                ch_mention = ch.mention if ch else "`روم محذوف`"
                embed.add_field(
                    name=f"⚡ اسم القاعدة: `{name}`",
                    value=(
                        f"> ⚙️ النظام: `{data['system_type']}`\n"
                        f"> 📂 الروم: {ch_mention}\n"
                        f"> 🔑 الكلمة: `{data['custom_keyword'] if data['custom_keyword'] else 'عام'}`"
                    ),
                    inline=False
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # التحقق من وجود اسم القاعدة للعمليات الأخرى
        if not action_name:
            await interaction.response.send_message("❌ **يجب تحديد اسم القاعدة (`action_name`) لإتمام هذا الإجراء!**", ephemeral=True)
            return

        rule_key = action_name.lower().strip()

        # 2. حذف قاعدة (Remove)
        if action == "remove":
            if rule_key in self.database[guild_id]:
                del self.database[guild_id][rule_key]
                save_autotrap_db(self.database)
                await interaction.response.send_message(f"🗑️ **تم بنجاح حذف قاعدة التفاعل التلقائي:** `{rule_key}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ **لم يتم العثور على قاعدة بهذا الاسم:** `{rule_key}`", ephemeral=True)
            return

        # 3. إنشاء قاعدة جديدة (Create)
        if action == "create":
            if not channel:
                await interaction.response.send_message("❌ **يجب تحديد الروم المستهدفة (`channel`) عند إنشاء قاعدة جديدة!**", ephemeral=True)
                return
            if rule_key in self.database[guild_id]:
                await interaction.response.send_message(f"❌ **توجد قاعدة مسجلة بهذا الاسم مسبقاً (`{rule_key}`). استخدم إجراء التعديل (`edit`) بدلاً منها!**", ephemeral=True)
                return

            reactions_list = [r.strip() for r in reactions.split()] if reactions else []

            self.database[guild_id][rule_key] = {
                "channel_id": channel.id,
                "system_type": system_type,
                "custom_keyword": custom_keyword.lower().strip() if custom_keyword else "",
                "reply_type": reply_type,
                "message_content": message_content or "",
                "image_url": image_url or "",
                "reactions": reactions_list,
                "target_role_id": target_role.id if target_role else None,
                "allow_bots": allow_bots,
                "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            }
            save_autotrap_db(self.database)

            embed = discord.Embed(
                title="⚡ ╎ تـم إنـشـاء قـاعـدة الـتـفـاعـل الـتـلـقـائـي بنجاح تام",
                description=(
                    f"> 📌 **اسم القاعدة:** `{rule_key}`\n"
                    f"> ⚙️ **نوع النظام:** `{system_type}`\n"
                    f"> 📂 **الروم المستهدفة:** {channel.mention}"
                ),
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 4. تعديل قاعدة موجودة (Edit)
        if action == "edit":
            if rule_key not in self.database[guild_id]:
                await interaction.response.send_message(f"❌ **لا توجد قاعدة مسجلة بهذا الاسم للتعديل عليها:** `{rule_key}`", ephemeral=True)
                return

            rule = self.database[guild_id][rule_key]
            if channel:
                rule["channel_id"] = channel.id
            if custom_keyword is not None:
                rule["custom_keyword"] = custom_keyword.lower().strip()
            if message_content is not None:
                rule["message_content"] = message_content
            if image_url is not None:
                rule["image_url"] = image_url
            if reactions is not None:
                rule["reactions"] = [r.strip() for r in reactions.split()]
            if target_role:
                rule["target_role_id"] = target_role.id

            save_autotrap_db(self.database)
            await interaction.response.send_message(f"✅ **تم تحديث قاعدة التفاعل `{rule_key}` وتطبيق التعديلات بنجاح!**", ephemeral=True)

    # 🧠 محرك الاستماع والتشغيل الذكي الشامل لكل الأنظمة بالخلفية
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        guild_id = str(message.guild.id)
        if guild_id not in self.database or not self.database[guild_id]:
            return

        content_lower = message.content.lower().strip()

        for name, data in self.database[guild_id].items():
            if message.channel.id != data["channel_id"]:
                continue
            if message.author.bot and not data.get("allow_bots", False):
                continue

            sys_type = data.get("system_type")
            keyword = data.get("custom_keyword", "")

            try:
                # النظام 1: تفاعلات إيموجي ذكية حسب الكلمات
                if sys_type == "keyword_emoji":
                    if not keyword or keyword in content_lower:
                        for emoji in data.get("reactions", []):
                            try:
                                await message.add_reaction(emoji)
                            except:
                                pass

                # النظام 2: فتح سلسلة نقاش تلقائية Thread
                elif sys_type == "auto_thread":
                    try:
                        thread_name = f"نقاش: {message.author.name}"
                        await message.create_thread(name=thread_name[:100], auto_archive_duration=1440)
                    except:
                        pass

                # النظام 3: رسالة ترحيب أو رد مع صور Media & Button Trap
                elif sys_type == "media_trap":
                    reply_type = data.get("reply_type", "text")
                    content_tpl = data.get("message_content", "")
                    img_url = data.get("image_url", "")

                    formatted = (
                        content_tpl.replace("[user]", message.author.mention)
                                   .replace("[userName]", message.author.name)
                                   .replace("[server]", message.guild.name)
                    )

                    if reply_type == "embed":
                        res_embed = discord.Embed(description=formatted, color=0x2B2D31)
                        if img_url:
                            res_embed.set_image(url=img_url)
                        await message.channel.send(embed=res_embed)
                    elif reply_type == "text":
                        final_txt = formatted
                        if img_url:
                            final_txt += f"\n{img_url}"
                        await message.channel.send(final_txt)

                # النظام 4: حماية الروابط ومنع السبام Anti-Link / Spam Shield
                elif sys_type == "anti_spam":
                    if "http://" in content_lower or "https://" in content_lower or "discord.gg/" in content_lower:
                        try:
                            await message.delete()
                            warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, ممنوع إرسال الروابط هنا!")
                            await warn_msg.delete(delay=5)
                        except:
                            pass

                # النظام 5: منشن رتبة معينة عند الطلب Role Mention Trigger
                elif sys_type == "role_mention":
                    if not keyword or keyword in content_lower:
                        role_id = data.get("target_role_id")
                        if role_id:
                            role = message.guild.get_role(role_id)
                            if role:
                                await message.channel.send(f"🔔 {role.mention} - تم طلب الدعم بواسطة {message.author.mention}")

                # النظام 6: تصويت تلقائي للاقتراحات Voting Polls Reactions
                elif sys_type == "voting_polls":
                    try:
                        await message.add_reaction("⬆️")
                        await message.add_reaction("⬇️")
                    except:
                        pass

            except Exception as e:
                print(f"[MEGA AUTOTRAP ERROR] {e}")

async def setup(bot):
    await bot.add_cog(ZiuoEnterpriseAutoTrapCog(bot))
