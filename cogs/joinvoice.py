import discord
from discord import app_commands
from discord.ext import commands
import datetime
import asyncio
from db import db

class VoiceControlView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="إخراج البوت 🔌", style=discord.ButtonStyle.danger, custom_id="voice_leave_btn")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذا الزر مخصص للإداريين فقط!", ephemeral=True)
            return

        guild = interaction.guild
        if guild.voice_client:
            db.remove(str(guild.id))

            channel_name = guild.voice_client.channel.name
            await guild.voice_client.disconnect()
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم إيقاف النظام الدائم وقطع اتصال البوت وإخراجه من روم ` {channel_name} ` عبر الزر بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🛡️ ╎ بواسطة الإداري", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice System")
            
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ البوت غير متصل بأي روم صوتي في هذا السيرفر أساساً!", ephemeral=True)

    @discord.ui.button(label="إعادة الاتصال 🔄", style=discord.ButtonStyle.success, custom_id="voice_reconnect_btn")
    async def reconnect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذا الزر مخصص للإداريين فقط!", ephemeral=True)
            return

        target_channel_id = db.get(str(self.guild_id))
        if not target_channel_id:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
                db.set(str(self.guild_id), target_channel.id)
            else:
                await interaction.response.send_message("❌ لا يوجد روم صوتي مستهدف محفوظ، يرجى الدخول لروم أو استخدام `/joinvc` أولاً.", ephemeral=True)
                return
        else:
            target_channel = interaction.client.get_channel(target_channel_id)

        if not target_channel:
            await interaction.response.send_message("❌ لم يتم العثور على الروم الصوتي المستهدف!", ephemeral=True)
            return

        try:
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(target_channel)
            else:
                await target_channel.connect(reconnect=True, timeout=60.0)
            
            await interaction.response.send_message(f"✅ تم إعادة اتصال البوت بنجاح بروم {target_channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إعادة الاتصال: `{e}`", ephemeral=True)

class VoicePresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.auto_reconnect_on_startup())

    async def auto_reconnect_on_startup(self):
        await self.bot.wait_until_ready()
        for guild_id_str, channel_id in list(db.data.items()):
            guild = self.bot.get_guild(int(guild_id_str))
            if guild:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    if not guild.voice_client:
                        try:
                            await channel.connect(reconnect=True, timeout=60.0)
                        except Exception:
                            pass
            await asyncio.sleep(1)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            guild_id_str = str(member.guild.id)
            
            if before.channel and not after.channel:
                target_channel_id = db.get(guild_id_str)
                if target_channel_id:
                    target_channel = self.bot.get_channel(target_channel_id)
                    if target_channel:
                        await asyncio.sleep(2)
                        try:
                            await target_channel.connect(reconnect=True, timeout=60.0)
                        except Exception:
                            pass

    @app_commands.command(name="joinvc", description="[إدارة] إدخال البوت للروم الصوتي ليبقى متواجداً 24/7")
    @app_commands.describe(channel="الروم الصوتي المراد دخول البوت إليه (اختياري)")
    @app_commands.checks.has_permissions(administrator=True)
    async def joinvc(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        await interaction.response.defer(ephemeral=True)

        target_channel = channel
        if not target_channel:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send("❌ يرجى تحديد روم صوتي، أو الانضمام إلى روم صوتي أولاً!", ephemeral=True)
                return

        if not isinstance(target_channel, discord.VoiceChannel):
            await interaction.followup.send("❌ العنصر المحدد ليس روم صوتياً صالحاً!", ephemeral=True)
            return

        guild_id_str = str(interaction.guild.id)
        db.set(guild_id_str, target_channel.id)

        try:
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.channel.id == target_channel.id:
                    view = VoiceControlView(self, interaction.guild.id)
                    await interaction.followup.send(f"⚠️ البوت متواجد بالفعل في روم {target_channel.mention} ومحفوظ بنظام 24/7!", view=view, ephemeral=True)
                    return
                await interaction.guild.voice_client.move_to(target_channel)
                action_status = "نقل البوت وحفظ التواجد الدائم بنجاح"
            else:
                await target_channel.connect(reconnect=True, timeout=60.0)
                action_status = "انضمام البوت وحفظ التواجد الدائم بنجاح"

            embed = discord.Embed(
                title="🎧 ╎ نـظـام الـتـواجـد الصـوتـي الـدائـم 24/7 〣 ｢⚡｣",
                description=f"> تم تثبيت وحفظ البوت داخل الغرفة بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🔊 ╎ الـروم الصـوتـي", value=f"> ｢ {target_channel.mention} ｣", inline=False)
            embed.add_field(name="🛡 ╎ بـواسـطـة", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📌 ╎ الحـالـة", value=f"> ｢ {action_status} ｣", inline=False)
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice Presence Engine 24/7")
            
            view = VoiceControlView(self, interaction.guild.id)
            await interaction.followup.send(embed=embed, view=view)

        except discord.ClientException as e:
            await interaction.followup.send(f"❌ خطأ في الاتصال الصوتي: `{e}`", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ لا أمتلك صلاحيات كافية لدخول هذا الروم الصوتي.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ انتهت مهلة الاتصال بالروم الصوتي.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ: `{e}`", ephemeral=True)

    @app_commands.command(name="leavevc", description="[إدارة] إخراج البوت من الروم الصوتي ومسح حفظه نهائياً")
    @app_commands.checks.has_permissions(administrator=True)
    async def leavevc(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)
        
        if interaction.guild.voice_client:
            db.remove(guild_id_str)
            channel_name = interaction.guild.voice_client.channel.name
            await interaction.guild.voice_client.disconnect()
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم مسح الحفظ وإخراج البوت من روم ` {channel_name} ` بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🛡️ ╎ بواسطة الإداري", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice System")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ البوت غير متصل بأي روم صوتي في هذا السيرفر أساساً!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VoicePresenceCog(bot))
hemeral=True)

async def setup(bot):
    await bot.add_cog(VoicePresenceCog(bot))
