import discord
from discord import app_commands
from discord.ext import commands
import datetime

class VoicePresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="joinvc", description="[إدارة] إدخال البوت للروم الصوتي ليبقى متواجداً واستقراره 24/7")
    @app_commands.describe(
        channel="الروم الصوتي المراد دخول البوت إليه (اختياري: لو تركتها فارغة سيدخل رومك الحالي)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def joinvc(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        # لو المستخدم ما حددش روم، نشوف لو هو قاعد في روم صوتي وندخل معاك أوتوماتيك
        target_channel = channel
        if not target_channel:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.response.send_message("❌ يرجى تحديد روم صوتي، أو الانضمام إلى روم صوتي أولاً لكي يدخل البوت معك!", ephemeral=True)
                return

        try:
            # التحقق مما إذا كان البوت متصلاً بالفعل بروم صوتي في نفس السيرفر
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.channel.id == target_channel.id:
                    await interaction.response.send_message(f"⚠️ البوت متواجد بالفعل في روم {target_channel.mention}!", ephemeral=True)
                    return
                await interaction.guild.voice_client.move_to(target_channel)
                action_status = "نقل البوت وتحديث التواجد بنجاح"
            else:
                # الاتصال بالروم الصوتي المحدد
                await target_channel.connect()
                action_status = "انضمام البوت وتثبيت الاتصال 24/7"

            embed = discord.Embed(
                title="🎧 ╎ نـظـام الـتـواجـد الصـوتـي الـدائـم 〣 ｢⚡｣",
                description=f"> تم تنفيذ أمر الاتصال الصوتي واستقرار البوت داخل الغرفة بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="🔊 ╎ الـروم الصـوتـي", value=f"> ｢ {target_channel.mention} ｣", inline=False)
            embed.add_field(name="🛡️️ ╎ بـواسـطـة", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📌 ╎ الحـالـة", value=f"> ｢ {action_status} ｣", inline=False)
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice Presence Engine")
            
            await interaction.response.send_message(embed=embed)

        except discord.ClientException:
            await interaction.response.send_message("❌ البوت متصل بالفعل بروم صوتي آخر في هذا السيرفر.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ لا أمتلك صلاحيات كافية لدخول هذا الروم الصوتي (تأكد من صلاحيات Connect و Speak).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ غير متوقع أثناء محاولة الاتصال بالروم: `{e}`", ephemeral=True)

    @app_commands.command(name="leavevc", description="[إدارة] إخراج البوت من الروم الصوتي وقفل الاتصال يدوياً")
    @app_commands.checks.has_permissions(administrator=True)
    async def leavevc(interaction_or_self, interaction: discord.Interaction = None):
        # دعم التوافقية لو تم استدعاؤها داخل الكلاس
        if isinstance(interaction_or_self, discord.Interaction):
            interaction = interaction_or_self
            self_obj = None
        else:
            self_obj = interaction_or_self

        if interaction.guild.voice_client:
            channel_name = interaction.guild.voice_client.channel.name
            await interaction.guild.voice_client.disconnect()
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم قطع اتصال البوت وإخراجه من روم ` {channel_name} ` بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="🛡️ ╎ بواسطة الإداري", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice System")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ البوت غير متصل بأي روم صوتي في هذا السيرفر أساساً!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VoicePresenceCog(bot))
