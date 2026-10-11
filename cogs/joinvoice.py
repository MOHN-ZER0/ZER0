import discord
from discord import app_commands
from discord.ext import commands
import datetime
import asyncio
import json
import os

DB_FILE = "voice_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

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
            data = load_db()
            if str(guild.id) in data:
                del data[str(guild.id)]
                save_db(data)
                
            channel_name = guild.voice_client.channel.name
            await guild.voice_client.disconnect(force=True)
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم إيقاف النظام الدائم وقطع اتصال البوت وإخراجه من روم ` {channel_name} ` عبر الزر بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🛡️ ╎ بواسطة الإداري", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.set_footer(text=f"{guild.name} ✦ Voice System")
            
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

        data = load_db()
        target_channel_id = data.get(str(self.guild_id))
        
        if not target_channel_id:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
                data[str(self.guild_id)] = target_channel.id
                save_db(data)
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
                await target_channel.connect(reconnect=True, timeout=20.0, self_deaf=True)
            
            await interaction.response.send_message(f"✅ تم إعادة اتصال البوت بنجاح بروم {target_channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إعادة الاتصال: `{e}`", ephemeral=True)

class VoicePresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        asyncio.create_task(self.auto_reconnect_on_startup())

    async def auto_reconnect_on_startup(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        data = load_db()
        for guild_id_str, channel_id in list(data.items()):
            guild = self.bot.get_guild(int(guild_id_str))
            if guild:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    if not guild.voice_client:
                        try:
                            await channel.connect(reconnect=True, timeout=20.0, self_deaf=True)
                        except Exception:
                            pass
            await asyncio.sleep(2)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            guild_id_str = str(member.guild.id)
            if before.channel and not after.channel:
                data = load_db()
                target_channel_id = data.get(guild_id_str)
                if target_channel_id:
                    target_channel = self.bot.get_channel(target_channel_id)
                    if target_channel:
                        await asyncio.sleep(3)
                        try:
                            if not member.guild.voice_client:
                                await target_channel.connect(reconnect=True, timeout=20.0, self_deaf=True)
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

        if not isinstance(target_channel, (discord.VoiceChannel, discord.StageChannel)):
            await interaction.followup.send("❌ العنصر المحدد ليس روم صوتياً صالحاً!", ephemeral=True)
            return

        guild_id_str = str(interaction.guild.id)
        data = load_db()
        data[guild_id_str] = target_channel.id
        save_db(data)

        try:
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.channel.id == target_channel.id:
                    view = VoiceControlView(self, interaction.guild.id)
                    await interaction.followup.send(f"⚠️ البوت متواجد بالفعل في روم {target_channel.mention} ومحفوظ بنظام 24/7!", view=view, ephemeral=True)
                    return
                await interaction.guild.voice_client.move_to(target_channel)
                action_status = "نقل البوت وحفظ التواجد الدائم بنجاح"
            else:
                await target_channel.connect(reconnect=True, timeout=20.0, self_deaf=True)
                action_status = "انضمام البوت وحفظ التواجد الدائم بنجاح"

            embed = discord.Embed(
                title="🎧 ╎ نـظـام الـتـواجـد الصـوتـي الـدائـم 24/7 〣 ｢⚡｣",
                description="> تم تثبيت وحفظ البوت داخل الغرفة بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🔊 ╎ الـروم الصـوتـي", value=f"> ｢ {target_channel.mention} ｣", inline=False)
            embed.add_field(name="🛡 ╎ بـواسـطـة", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📌 ╎ الحـالـة", value=f"> ｢ {action_status} ｣", inline=False)
            embed.set_footer(text=f"{interaction.guild.name} ✦ Voice Presence Engine 24/7")
            
            view = VoiceControlView(self, interaction.guild.id)
            await interaction.followup.send(embed=embed, view=view)

        except discord.ClientException as e:
            await interaction.followup.send(f"❌ خطأ في الاتصال الصوتي: `{e}`", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ لا أمتلك صلاحيات كافية (Connect / Speak) لدخول هذا الروم الصوتي.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ انتهت مهلة الاتصال بالروم الصوتي.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ غير متوقع: `{e}`", ephemeral=True)

    @app_commands.command(name="leavevc", description="[إدارة] إخراج البوت من الروم الصوتي ومسح حفظه نهائياً")
    @app_commands.checks.has_permissions(administrator=True)
    async def leavevc(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)
        
        if interaction.guild.voice_client:
            data = load_db()
            if guild_id_str in data:
                del data[guild_id_str]
                save_db(data)
                
            channel_name = interaction.guild.voice_client.channel.name
            await interaction.guild.voice_client.disconnect(force=True)
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم مسح الحفظ وإخراج البوت من روم ` {channel_name} ` بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0xCC0000,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🛡️ ╎ بواسطة الإداري", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.set_footer(text=f"{interaction.guild.name} ✦ Voice System")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ البوت غير متصل بأي روم صوتي في هذا السيرفر أساساً!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VoicePresenceCog(bot))
