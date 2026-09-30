import discord
from discord import app_commands
from discord.ext import commands
import datetime

class CustomClearCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="clear", description="[إدارة] مسح عدد معين من الرسائل بتصميم فخم ومطور مع حماية ضد الرسائل القديمة")
    @app_commands.describe(
        amount="عدد الرسائل المراد مسحها (يُفضل بين 1 إلى 100 رسالة)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ يرجى تحديد عدد صحيح أكبر من صفر لمسح الرسائل.", ephemeral=True)
            return

        # تأخير الاستجابة بشكل سري لحين إتمام عملية الحذف بنجاح
        await interaction.response.defer(ephemeral=True)

        try:
            # مسح الرسائل مع استبعاد الرسائل الأقدم من 14 يوماً لتجنب قيود ديسكورد البرمجية
            deleted = await interaction.channel.purge(limit=amount)
            deleted_count = len(deleted)

            if deleted_count == 0:
                await interaction.followup.send("⚠️ لم يتم العثور على رسائل صالحة للمسح (قد تكون الرسائل أقدم من 14 يوماً).", ephemeral=True)
                return

            # بناء إيمبد التقرير الفخم للإدارة
            embed = discord.Embed(
                title="🧹 ╎ نـظـام الـتـنـظـيـف والـمـسـح 〣 ｢⚡｣",
                description=f"> تم تنظيف القناة بنجاح وإزالة الرسائل المحددة.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="📌 ╎ عـدد الـرسـائـل", value=f"> ｢ {deleted_count} ｣ رسالة تم مسحها", inline=False)
            embed.add_field(name="👤 ╎ بـواسـطـة", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📁 ╎ الـقـنـاة", value=f"> ｢ {interaction.channel.mention} ｣", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ Advanced Moderation System")
            
            # إرسال إيمبد مؤقت في الشات ويتم حذفه تلقائياً بعد 5 ثواني لمنع الإزعاج
            await interaction.channel.send(embed=embed, delete_after=5)
            
            # تأكيد سري ونهائي للإداري
            await interaction.followup.send(f"✅ **تم بنجاح!** تم مسح `{deleted_count}` رسالة من هذه القناة.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("❌ لاልي صلاحيات كافية لتنفيذ الأمر، تأكد أن البوت يمتلك صلاحية `Manage Messages`.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ حدث خطأ أثناء تنفيذ عملية المسح. (الخطأ: `{e}`)", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CustomClearCog(bot))
