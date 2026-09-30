import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os
from typing import Optional, Literal

MEGA_AR_DB_FILE = "enterprise_autoresponder_database.json"

def load_mega_responses():
    if os.path.exists(MEGA_AR_DB_FILE):
        try:
            with open(MEGA_AR_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_mega_responses(data):
    with open(MEGA_AR_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class EnterpriseAutoResponderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.responses = load_mega_responses()

    @app_commands.command(
        name="ar",
        description="[نظام إمبراطوري موحد] إدارة قواعد الرد التلقائي بالكامل (إضافة، حذف، استعراض)"
    )
    @app_commands.describe(
        action="الإجراء المطلوب تنفيذه على النظام",
        keyword="الكلمة أو العبارة المفتاحية المستهدفة",
        reply_text="نص الرد (يدعم [user], [userName], [server], [memberCount])",
        match_type="طريقة المطابقة للكلمة",
        mode="طريقة إرسال الرد (Reply أو رسالة عادية)",
        message_type="شكل الرد (قالب إمبد فخم أو نص عادي)",
        delete_user_msg="حذف رسالة العضو الأصلية تلقائياً؟ (True/False)",
        delete_after_seconds="حذف رد البوت بعد ثوانٍ محددة (اختياري)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="إضافة قاعدة جديدة (Add)", value="add"),
            app_commands.Choice(name="حذف قاعدة مسجلة (Remove)", value="remove"),
            app_commands.Choice(name="استعراض كافة القواعد (List)", value="list")
        ],
        match_type=[
            app_commands.Choice(name="مطابقة تامة حصرياً (Exact)", value="exact"),
            app_commands.Choice(name="احتواء ضمني في أي مكان (Contains)", value="contains"),
            app_commands.Choice(name="بداية الرسالة فقط (StartsWith)", value="startswith")
        ],
        mode=[
            app_commands.Choice(name="رد مباشر على الرسالة (Reply)", value="reply"),
            app_commands.Choice(name="رسالة عادية في الروم (Normal)", value="normal")
        ],
        message_type=[
            app_commands.Choice(name="قالب إمبد احترافي (Embed)", value="embed"),
            app_commands.Choice(name="نص عادي (Text)", value="text")
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ar_manager(
        self,
        interaction: discord.Interaction,
        action: Literal["add", "remove", "list"],
        keyword: Optional[str] = None,
        reply_text: Optional[str] = None,
        match_type: Literal["exact", "contains", "startswith"] = "contains",
        mode: Literal["reply", "normal"] = "reply",
        message_type: Literal["embed", "text"] = "embed",
        delete_user_msg: bool = False,
        delete_after_seconds: Optional[int] = None
    ):
        guild_id = str(interaction.guild.id)
        if guild_id not in self.responses:
            self.responses[guild_id] = {}

        # 1. استعراض القواعد (List)
        if action == "list":
            if not self.responses[guild_id]:
                await interaction.response.send_message("📌 **لا توجد أي قواعد رد تلقائي مسجلة في هذا السيرفر حالياً.**", ephemeral=True)
                return

            embed = discord.Embed(
                title="📋 ╎ قـائـمـة قـواعـد الـرد الـتـلـقـائـي الإمبراطورية",
                color=0x2B2D31,
                timestamp=datetime.datetime.utcnow()
            )
            for kw, data in self.responses[guild_id].items():
                embed.add_field(
                    name=f"🔑 الكلمة: `{kw}`",
                    value=(
                        f"> 🔍 المطابقة: `{data['match_type']}` | النوع: `{data['message_type']}`\n"
                        f"> 🔄 عدد الاستخدامات: `{data.get('uses_count', 0)}`\n"
                        f"> 📄 الرد: `{data['reply'][:50]}...`"
                    ),
                    inline=False
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # التحقق من وجود الكلمة لعمليات الإضافة أو الحذف
        if not keyword:
            await interaction.response.send_message("❌ **يجب تحديد الكلمة المفتاحية (`keyword`) لإتمام هذا الإجراء!**", ephemeral=True)
            return

        clean_keyword = keyword.lower().strip()

        # 2. حذف قاعدة (Remove)
        if action == "remove":
            if clean_keyword in self.responses[guild_id]:
                del self.responses[guild_id][clean_keyword]
                save_mega_responses(self.responses)
                await interaction.response.send_message(f"🗑️ **تم بنجاح الحذف النهائي لقاعدة الرد المرتبطة بـ:** `{clean_keyword}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ **عذراً، لم يتم العثور على قاعدة مسجلة بهذا الاسم:** `{clean_keyword}`", ephemeral=True)
            return

        # 3. إضافة قاعدة جديدة (Add)
        if action == "add":
            if not reply_text:
                await interaction.response.send_message("❌ **يجب كتابة نص الرد (`reply_text`) عند إضافة قاعدة جديدة!**", ephemeral=True)
                return

            self.responses[guild_id][clean_keyword] = {
                "reply": reply_text,
                "match_type": match_type,
                "mode": mode,
                "message_type": message_type,
                "delete_user_msg": delete_user_msg,
                "delete_after_seconds": delete_after_seconds,
                "uses_count": 0,
                "author_id": interaction.user.id,
                "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            }
            save_mega_responses(self.responses)

            embed = discord.Embed(
                title="⚡ ╎ تـم إضـافـة قـاعـدة الـرد الـتـلـقـائـي بنجاح تام",
                description=(
                    f"> 🔑 **الكلمة:** `{clean_keyword}`\n"
                    f"> 🔍 **المطابقة:** `{match_type}` | **الإرسال:** `{mode}`\n"
                    f"> 🎨 **النوع:** `{message_type}`\n"
                    f"> 🗑️ **حذف رسالة العضو:** `{'مفعل ✅' if delete_user_msg else 'معطل ❌'}`\n"
                    f"> ⏳ **حذف رد البوت بعد:** `{f'{delete_after_seconds} ثانية' if delete_after_seconds else 'دائم'}`\n\n"
                    f"> 📄 **نص الرد:**\n{reply_text}"
                ),
                color=0x2ECC71,
                timestamp=datetime.datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # محرك الاستماع الذكي لتنفيذ الردود بالخلفية
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        if guild_id not in self.responses or not self.responses[guild_id]:
            return

        content = message.content.lower().strip()

        for keyword, data in self.responses[guild_id].items():
            match_type = data.get("match_type", "contains")
            matched = False

            if match_type == "exact" and content == keyword:
                matched = True
            elif match_type == "contains" and keyword in content:
                matched = True
            elif match_type == "startswith" and content.startswith(keyword):
                matched = True

            if matched:
                data["uses_count"] = data.get("uses_count", 0) + 1
                save_mega_responses(self.responses)

                reply_template = data["reply"]
                mode = data.get("mode", "reply")
                msg_type = data.get("message_type", "embed")
                delete_user = data.get("delete_user_msg", False)
                del_seconds = data.get("delete_after_seconds")

                formatted_reply = (
                    reply_template.replace("[user]", message.author.mention)
                                  .replace("[userName]", message.author.name)
                                  .replace("[server]", message.guild.name)
                                  .replace("[memberCount]", str(message.guild.member_count))
                )

                sent_msg = None
                try:
                    if msg_type == "embed":
                        res_embed = discord.Embed(description=formatted_reply, color=0x2B2D31)
                        res_embed.set_footer(text=f"Requested by {message.author.name}", icon_url=message.author.display_avatar.url)
                        res_embed.timestamp = datetime.datetime.utcnow()
                        
                        if mode == "reply":
                            sent_msg = await message.reply(embed=res_embed, mention_author=True)
                        else:
                            sent_msg = await message.channel.send(embed=res_embed)
                    else:
                        if mode == "reply":
                            sent_msg = await message.reply(formatted_reply, mention_author=True)
                        else:
                            sent_msg = await message.channel.send(formatted_reply)

                    if delete_user:
                        try:
                            await message.delete()
                        except:
                            pass

                    if sent_msg and del_seconds and del_seconds > 0:
                        await sent_msg.delete(delay=float(del_seconds))

                except Exception as e:
                    print(f"[ENTERPRISE AR ERROR] {e}")

                break

async def setup(bot):
    await bot.add_cog(EnterpriseAutoResponderCog(bot))
