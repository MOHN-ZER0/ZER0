import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging

# إعداد نظام الـ Logger لمراقبة وتتبع أداء الأغنية بدقة
logger = logging.getLogger("ZIUO_Empire.ExactSongPlayer")

class ExactSongPlayerCog(commands.Cog):
    """
    نظام تشغيل الأغاني التفاعلي الدقيق (Exact Lyrics Live Animator).
    يقوم بعرض الكلمات التي أرسلها المستخدم بحذافيرها مع تطبيق أنيميشن تدرج الحجم 
    وتعديل الرسائل الحية (Live Message Editing) خطوة بخطوة.
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # كلمات الأغنية بالضبط كما أرسلتها يا فنان، بالترتيب الحرفي وبدون أي تغيير
        self.exact_lyrics_sequence = [
            "I'll never be like you",
            "### I'll never be like you",
            "## I'll never be like you",
            "I'm risin' up and I'm ready to fight you",
            "Ready to fight you",
            "🔥 **I'm all in!**",
            "I've seen you before, you all are the same",
            "You're just another goin' up in the flames",
            "And if I'm gon' die in the fight",
            "It'll be while I am bringing you down to the grave",
            "I see who you are, you are my enemy",
            "### My enemy, you are my enemy",
            "I see who you are, **you are my enemy**",
            "💀 **My enemy, you are my enemy**"
        ]

    async def _animate_lyrics(self, channel: discord.abc.Messageable, trigger_author: str) -> None:
        """
        دالة مسؤولة عن إرسال الرسالة الابتدائية وإجراء حلقة التحديث الزمنية 
        لتطبيق الأنيميشن وتعديل الرسالة الحية كل ثانية.
        """
        try:
            # رسالة التحضير الأولى
            active_msg = await channel.send("🎶 *[جاري تشغيل الأنيميشن الصوتي والكتابي...]*")
            await asyncio.sleep(1.0)

            # حلقة التعديل الحية لكل سطر بالترتيب الدقيق
            for idx, line_text in enumerate(self.exact_lyrics_sequence):
                try:
                    # تعديل محتوى الرسالة الحية
                    await active_msg.edit(content=line_text)
                    
                    # ضبط سرعة الأداء الزمني (1.2 ثانية لكل سطر لتعطي إحساس الأنيميشن الحقيقي)
                    await asyncio.sleep(1.2)
                    
                except discord.HTTPException as http_error:
                    logger.warning(f"⚠ تنبيه HTTP أثناء تحديث السطر رقم {idx}: {http_error}")
                    continue
                except Exception as line_error:
                    logger.error(f"❌ خطأ داخلي أثناء تحديث سطر الأغنية: {line_error}")
                    break
                    
        except Exception as general_error:
            logger.error(f"❌ فشل تنفيذ الأنيميشن بواسطة العضو ({trigger_author}): {general_error}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        مستمع رسائل تلقائي يتحقق من جملة التفعيل الأولى ليبدأ العرض الحي فوراً
        مع مسح رسالة المستخدم لتنظيم القناة.
        """
        if message.author.bot or not message.guild:
            return

        # تنظيف النص ومقارنته بجملة البداية الدقيقة
        user_text_clean = message.content.strip().lower()
        start_trigger = "i'll never be like you"

        if user_text_clean == start_trigger:
            # مسح رسالة المستخدم الحالية لتكون الشاشة نظيفة لعرض الأنيميشن
            try:
                await message.delete(delay=0.4)
            except:
                pass
                
            # بدء عرض الأنيميشن في نفس القناة
            await self._animate_lyrics(message.channel, trigger_author=str(message.author))

    @app_commands.command(
        name="sing_exact",
        description="[ترفيه] تشغيل أنيميشن الأغنية بدقة مطابقة لكلماتك المفضلة"
    )
    async def slash_sing_exact(self, interaction: discord.Interaction) -> None:
        """
        أمر سلاش بديل يتيح تشغيل الأغنية والأنيميشن التلقائي بضغطة زر واحدة.
        """
        await interaction.response.send_message("🎤 *[تم تفعيل نظام الأغنية الدقيق، جاري العرض...]*", ephemeral=True)
        await self._animate_lyrics(interaction.channel, trigger_author=str(interaction.user))

async def setup(bot: commands.Bot) -> None:
    """
    دالة تسجيل الـ Cog رسمياً في البوت الرئيسي.
    """
    await bot.add_cog(ExactSongPlayerCog(bot))
