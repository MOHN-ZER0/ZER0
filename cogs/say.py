import discord
from discord import app_commands
from discord.ext import commands

class CustomSayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="[إدارة] إرسال رسالة نصية عادية عبر البوت بالصيغة والنص الذي تحدده")
    @app_commands.describe(
        message="النص المراد إرساله (يدعم النزول لسطر جديد عبر كتابة نص مرتب)",
        channel="القناة المراد إرسال الرسالة فيها (اختياري: افتراضياً الروم الحالية)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
        # تحديد الروم المستهدفة (نفس الروم أو روم أخرى يختارها الإداري)
        target_channel = channel or interaction.channel
        
        # معالجة النصوص لدعم الأسطر الجديدة بشكل صحيح لو كتبت بالمسافات العادية
        formatted_message = message.replace("\\n", "\n")

        try:
            # إرسال الرسالة النقية بالبوت بدون ذكر اسم أي شخص
            await target_channel.send(formatted_message)
            
            # تأكيد سري للإداري أن الرسالة اتبعتت بنجاح
            await interaction.response.send_message(
                f"✅ **تم بنجاح!** تم إرسال رسالتك إلى روم {target_channel.mention} بشكل مخفي ونظيف.", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ حدث خطأ أثناء إرسال الرسالة، تأكد من صلاحيات البوت في الروم المحددة. (الخطأ: `{e}`)", 
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(CustomSayCog(bot))
