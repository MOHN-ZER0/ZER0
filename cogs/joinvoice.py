import discord
from discord import app_commands
from discord.ext import commands
import datetime
import asyncio

class VoiceControlView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None) # البقاء نشطاً دائماً
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="إخراج البوت 🔌", style=discord.ButtonStyle.danger, custom_id="voice_leave_btn")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # التحقق من أن المستخدم لديه صلاحية الإدارة
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ عذراً، هذا الزر مخصص للإداريين فقط!", ephemeral=True)
            return

        guild = interaction.guild
        if guild.voice_client:
            self.cog.manual_disconnects.add(self.guild_id)
            if self.guild_id in self.cog.target_channels:
                del self.cog.target_channels[self.guild_id]

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
            
            # تعديل الرسالة لإلغاء تفعيل الأزرار بعد الخروج
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

        target_channel_id = self.cog.target_channels.get(self.guild_id)
        if not target_channel_id:
            # إذا لم يكن هناك روم مخزن، نأخذ روم المستخدم الحالي
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
                self.cog.target_channels[self.guild_id] = target_channel.id
            else:
                await interaction.response.send_message("❌ لا يوجد روم صوتي مستهدف محفوظ، يرجى الدخول لروم أو استخدام `/joinvc` أولاً.", ephemeral=True)
                return
        else:
            target_channel = interaction.client.get_channel(target_channel_id)

        if not target_channel:
            await interaction.response.send_message("❌ لم يتم العثور على الروم الصوتي المستهدف!", ephemeral=True)
            return

        # إزالة السيرفر من قائمة الخروج اليدوي لضمان عمل الحماية
        if self.guild_id in self.cog.manual_disconnects:
            self.cog.manual_disconnects.remove(self.guild_id)

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
        self.target_channels = {}
        self.manual_disconnects = set()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            guild_id = member.guild.id
            
            if guild_id in self.manual_disconnects:
                return

            if before.channel and not after.channel:
                target_channel_id = self.target_channels.get(guild_id)
                if target_channel_id:
                    target_channel = self.bot.get_channel(target_channel_id)
                    if target_channel:
                        await asyncio.sleep(2)
                        try:
                            await target_channel.connect(reconnect=True, timeout=60.0)
                        except Exception:
                            pass

    @app_commands.command(name="joinvc", description="[إدارة] إدخال البوت للروم الصوتي ليبقى متواجداً واستقراره 24/7 مع أزرار تحكم")
    @app_commands.describe(
        channel="الروم الصوتي المراد دخول البوت إليه (اختياري: لو تركتها فارغة سيدخل رومك الحالي)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def joinvc(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        await interaction.response.defer(ephemeral=True)

        target_channel = channel
        if not target_channel:
            if interaction.user.voice and interaction.user.voice.channel:
                target_channel = interaction.user.voice.channel
            else:
                await interaction.followup.send("❌ يرجى تحديد روم صوتي، أو الانضمام إلى روم صوتي أولاً لكي يدخل البوت معك!", ephemeral=True)
                return

        if not isinstance(target_channel, discord.VoiceChannel):
            await interaction.followup.send("❌ العنصر المحدد ليس روم صوتياً صالحاً!", ephemeral=True)
            return

        guild_id = interaction.guild.id
        if guild_id in self.manual_disconnects:
            self.manual_disconnects.remove(guild_id)

        self.target_channels[guild_id] = target_channel.id

        try:
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.channel.id == target_channel.id:
                    view = VoiceControlView(self, guild_id)
                    await interaction.followup.send(f"⚠️ البوت متواجد بالفعل في روم {target_channel.mention} ومثبت بنظام 24/7!", view=view, ephemeral=True)
                    return
                await interaction.guild.voice_client.move_to(target_channel)
                action_status = "نقل البوت وتثبيت التواجد الدائم 24/7"
            else:
                await target_channel.connect(reconnect=True, timeout=60.0)
                action_status = "انضمام البوت وتثبيت الاتصال الدائم 24/7"

            embed = discord.Embed(
                title="🎧 ╎ نـظـام الـتـواجـد الصـوتـي الـدائـم 24/7 〣 ｢⚡｣",
                description=f"> تم تثبيت البوت داخل الغرفة بنجاح. يمكنك التحكم بالبوت عبر الأزرار أدناه.\n━━━━━━━━━━━━━━━━━━━━━",
                color=0x2b2d31,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="🔊 ╎ الـروم الصـوتـي", value=f"> ｢ {target_channel.mention} ｣", inline=False)
            embed.add_field(name="🛡 ╎ بـواسـطـة", value=f"> ｢ {interaction.user.mention} ｣", inline=False)
            embed.add_field(name="📌 ╎ الحـالـة", value=f"> ｢ {action_status} ｣", inline=False)
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.set_footer(text="Z I UO - MC Server ✦ Voice Presence Engine 24/7")
            
            # ربط الأزرار بالرسالة
            view = VoiceControlView(self, guild_id)
            await interaction.followup.send(embed=embed, view=view)

        except discord.ClientException as e:
            await interaction.followup.send(f"❌ خطأ في الاتصال الصوتي: `{e}`", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ لا أمتلك صلاحيات كافية لدخول هذا الروم الصوتي (تأكد من صلاحيات Connect و Speak).", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ انتهت مهلة الاتصال بالروم الصوتي (Timeout). حاول مرة أخرى.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ. **تأكد من تثبيت مكتبة PyNaCl** عبر الأوامر (`pip install PyNaCl`). الخطأ: `{e}`", ephemeral=True)

    @app_commands.command(name="leavevc", description="[إدارة] إخراج البوت من الروم الصوتي وقفل الاتصال يدوياً وإيقاف التواجد الدائم")
    @app_commands.checks.has_permissions(administrator=True)
    async def leavevc(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if interaction.guild.voice_client:
            self.manual_disconnects.add(guild_id)
            if guild_id in self.target_channels:
                del self.target_channels[guild_id]

            channel_name = interaction.guild.voice_client.channel.name
            await interaction.guild.voice_client.disconnect()
            
            embed = discord.Embed(
                title="🔌 ╎ مـغـادرة الروم الصوتي 〣 ｢⚠️｣",
                description=f"> تم إيقاف النظام الدائم وقطع اتصال البوت وإخراجه من روم ` {channel_name} ` بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
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
