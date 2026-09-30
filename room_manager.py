import discord
from discord import app_commands
from discord.ext import commands
import datetime

# ==============================================================================
# 🎛️ قائمة اختيار الرومات التفاعلية المتقدمة
# ==============================================================================
class AdvancedChannelSelect(discord.ui.Select):
    def __init__(self, channels, action: str):
        self.action = action
        # أخذ أول 25 روم نظراً لقيود ديسكورد للقوائم المنسدلة
        options = [
            discord.SelectOption(
                label=ch.name[:100], 
                value=str(ch.id), 
                description=f"النوع: {'روم كتابية 💬' if isinstance(ch, discord.TextChannel) else 'روم صوتية 🔊'}",
                emoji="💬" if isinstance(ch, discord.TextChannel) else "🔊"
            ) for ch in channels[:25]
        ]
        
        placeholder_text = "اختر الرومات المطلوبة بدقة (حد أقصى 25)..."
        if action == "hide_all":
            placeholder_text = "قائمة إخفاء جميع الرومات دفعة واحدة..."
        elif action == "show_all":
            placeholder_text = "قائمة إظهار جميع الرومات دفعة واحدة..."

        super().__init__(
            placeholder=placeholder_text, 
            min_values=1, 
            max_values=len(options), 
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        everyone_role = guild.default_role
        modified_count = 0
        failed_count = 0

        for ch_id in self.values:
            channel = guild.get_channel(int(ch_id))
            if channel:
                try:
                    if self.action in ["hide", "hide_all"]:
                        await channel.set_permissions(everyone_role, view_channel=False, reason=f"Mass hide by {interaction.user.display_name}")
                    elif self.action in ["show", "show_all"]:
                        await channel.set_permissions(everyone_role, view_channel=None, reason=f"Mass show by {interaction.user.display_name}")
                    elif self.action == "lock":
                        if isinstance(channel, discord.TextChannel):
                            await channel.set_permissions(everyone_role, send_messages=False, reason=f"Mass lock by {interaction.user.display_name}")
                    elif self.action == "unlock":
                        if isinstance(channel, discord.TextChannel):
                            await channel.set_permissions(everyone_role, send_messages=None, reason=f"Mass unlock by {interaction.user.display_name}")
                    
                    modified_count += 1
                except Exception as e:
                    failed_count += 1
                    print(f"Error updating channel {channel.name}: {e}")

        # تحديد عنوان ونوع الرد بناءً على الإجراء
        action_titles = {
            "hide": ("إخفاء الرومات المحددة", 0xCC0000, "🔒"),
            "show": ("إظهار الرومات المحددة", 0x00CC66, "🔓"),
            "hide_all": ("إخفاء كافة رومات السيرفر", 0x990000, "🛡️"),
            "show_all": ("إظهار كافة رومات السيرفر", 0x2ECC71, "🌟"),
            "lock": ("قفل المحادثة في الرومات", 0xE67E22, "🔒"),
            "unlock": ("فتح المحادثة في الرومات", 0x3498DB, "📂")
        }
        
        title_text, embed_color, emoji_icon = action_titles.get(self.action, ("تعديل الرومات", 0x2b2d31, "⚡"))

        embed = discord.Embed(
            title=f"{emoji_icon} ╎ تـم تنفيذ: {title_text} 〣 ｢Z I UO｣",
            description=f"> تم بنجاح تعديل صلاحيات ｢ {modified_count} ｣ روم في السيرفر.\n" + (f"> ⚠️ فشل تعديل: {failed_count} روم.\n" if failed_count > 0 else "") + f"━━━━━━━━━━━━━━━━━━━━━",
            color=embed_color,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO - MC Server ✦ Advanced Room Security Engine")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==============================================================================
# 🎛️ واجهة أزرار التحكم الشاملة بالرومات
# ==============================================================================
class AdvancedRoomManagerView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.guild = guild

    @discord.ui.button(label="إخفاء رومات محددة", style=discord.ButtonStyle.danger, emoji="🔒", row=0)
    async def hide_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channels = [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        if not channels:
            await interaction.response.send_message("❌ لا توجد رومات متاحة للتعديل.", ephemeral=True)
            return
        view = discord.ui.View(timeout=180)
        view.add_item(AdvancedChannelSelect(channels, "hide"))
        await interaction.response.send_message("> 🔒 **اختر الرومات التي تريد إخفاءها عن الأعضاء:**", view=view, ephemeral=True)

    @discord.ui.button(label="إظهار رومات محددة", style=discord.ButtonStyle.success, emoji="🔓", row=0)
    async def show_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channels = [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        if not channels:
            await interaction.response.send_message("❌ لا توجد رومات متاحة للتعديل.", ephemeral=True)
            return
        view = discord.ui.View(timeout=180)
        view.add_item(AdvancedChannelSelect(channels, "show"))
        await interaction.response.send_message("> 🔓 **اختر الرومات التي تريد إظهارها للأعضاء:**", view=view, ephemeral=True)

    @discord.ui.button(label="إخفاء كل الرومات (طوارئ)", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1)
    async def hide_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # إخفاء جميع الرومات دفعة واحدة كإجراء طوارئ سريع
        await interaction.response.defer(ephemeral=True)
        everyone_role = self.guild.default_role
        count = 0
        for ch in self.guild.channels:
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await ch.set_permissions(everyone_role, view_channel=False, reason=f"Emergency hide all by {interaction.user.display_name}")
                    count += 1
                except:
                    pass
        
        embed = discord.Embed(
            title="🛡️ ╎ طـوارئ الـسـيـرفـر ╎ تـم إخـفـاء الـجـمـيـع",
            description=f"> تم تفعيل وضع الطوارئ وإخفاء إجمالي ` {count} ` روم عن الأعضاء بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x990000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Emergency Lockdown System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="إظهار كل الرومات (إلغاء الطوارئ)", style=discord.ButtonStyle.primary, emoji="🌟", row=1)
    async def show_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        everyone_role = self.guild.default_role
        count = 0
        for ch in self.guild.channels:
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await ch.set_permissions(everyone_role, view_channel=None, reason=f"Emergency show all by {interaction.user.display_name}")
                    count += 1
                except:
                    pass
        
        embed = discord.Embed(
            title="🌟 ╎ إنـهـاء الـطـوارئ ╎ تـم إظـهـار الـجـمـيـع",
            description=f"> تم إلغاء حالة الطوارئ وإعادة إظهار إجمالي ` {count} ` روم للأعضاء بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Emergency Lockdown System")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==============================================================================
# ⚙️ أمر لوحة تحكم الرومات الرئيسي
# ==============================================================================
class RoomManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="room_manager", description="[إدارة متقدمة] لوحة تحكم ذكية لإخفاء أو إظهار رومات السيرفر بشكل جماعي وفوري")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def room_manager(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎛️ ╎ لـوحـة تـحـكـم ظـهـور وإدارة الـرومـات 〣 ｢Z I UO｣",
            description=(
                "> أهلاً بك يا أسطورة في نظام التحكم المتقدم بالرومات والسيرفر.\n"
                "> يتيح لك هذا النظام إدارة ظهور ورؤية الرومات بدقة، أو تفعيل وضع الطوارئ الشامل.\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🔹 **إخفاء/إظهار رومات محددة:** لاختيار رومات معينة من القائمة المنسدلة.\n"
                "🔸 **إخفاء/إظهار كل الرومات:** كزر طوارئ فوري لكافة رومات السيرفر بلمسة واحدة."
            ),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        >
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text="Z I UO - MC Server ✦ Channel Management Engine")
        
        await interaction.response.send_message(embed=embed, view=AdvancedRoomManagerView(interaction.guild), ephemeral=True)

async def setup(bot):
    await bot.add_cog(RoomManagerCog(bot))
