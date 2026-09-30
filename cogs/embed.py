import discord
from discord import app_commands
from discord.ext import commands
import datetime

class CustomEmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="embed",
        description="[نظام إمبراطوري] إرسال إيمبد احترافي مخصص مع تحكم كامل بالصورة، الصورة المصغرة، واللون"
    )
    @app_commands.describe(
        description="محتوى ووصف الإيمبد الأساسي (يدعم النزول لسطر جديد تلقائياً)",
        title="عنوان الإيمبد (اختياري)",
        color_hex="لون الإيمبد بنظام الهيكس (مثال: #2b2d31 أو 2ecc71)",
        image_url="رابط الصورة الكبيرة في أسفل الإيمبد (اختياري)",
        thumbnail_url="رابط الصورة المصغرة الجانبية (اختياري)",
        footer_text="النص أو الحقوق في أسفل الإيمبد (اختياري)",
        channel="القناة المراد إرسال الإيمبد فيها (افتراضياً: الروم الحالية)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_cmd(
        self,
        interaction: discord.Interaction, 
        description: str, 
        title: str = None, 
        color_hex: str = "2b2d31",
        image_url: str = None, 
        thumbnail_url: str = None,
        footer_text: str = None,
        channel: discord.TextChannel = None
    ):
        # 1. معالجة اللون وتحويله من Hex لـ Integer بشكل آمن ومحمي من الأخطاء
        try:
            clean_hex = color_hex.replace("#", "").strip()
            color_int = int(clean_hex, 16)
        except ValueError:
            color_int = 0x2b2d31 # لون افتراضي داكن في حال كتب قيمة غير صالحة

        # 2. بناء الإيمبد الاحترافي
        embed = discord.Embed(
            description=description.replace("\\n", "\n"), # دعم النزول لسطر جديد بالطريقة العادية
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        
        if title:
            embed.title = title
            
        if image_url:
            embed.set_image(url=image_url)
            
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
            
        if footer_text:
            embed.set_footer(text=footer_text)
        else:
            embed.set_footer(
                text=f"Z I UO Empire ✦ Requested by {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url
            )

        # 3. تحديد الروم المستهدفة
        target_channel = channel or interaction.channel

        try:
            # إرسال الإيمبد للروم المطلوبة
            await target_channel.send(embed=embed)
            
            # الرد السري للإداري بدون إزعاج الشات العام
            await interaction.response.send_message(
                f"✅ **تم بنجاح!** تم إرسال الإيمبد المخصص إلى روم {target_channel.mention}.", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ **حدث خطأ أثناء الإرسال:** تأكد من صحة الروابط أو صلاحيات البوت. (`{e}`)", 
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(CustomEmbedCog(bot))
