import discord
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, Literal

# ==============================================================================
# 🎛️ قائمة اختيار الرومات والفئات التفاعلية المتقدمة
# ==============================================================================
class AdvancedChannelSelect(discord.ui.Select):
    def __init__(self, targets, action: str):
        self.action = action
        options = []
        
        # ترتيب العناصر بحيث تظهر الفئات أولاً ثم الرومات
        for item in targets[:25]:
            if isinstance(item, discord.CategoryChannel):
                options.append(discord.DiscordException or discord.SelectOption(
                    label=f"[فئة] {item.name[:90]}"[:100],
                    value=f"cat_{item.id}",
                    description="فئة كاملة مع كافة روماتها 📁",
                    emoji="📁"
                ))
            elif isinstance(item, discord.TextChannel):
                options.append(discord.SelectOption(
                    label=item.name[:100],
                    value=f"text_{item.id}",
                    description="روم كتابية 💬",
                    emoji="💬"
                ))
            elif isinstance(item, discord.VoiceChannel):
                options.append(discord.SelectOption(
                    label=item.name[:100],
                    value=f"voice_{item.id}",
                    description="روم صوتية 🔊",
                    emoji="🔊"
                ))

        super().__init__(
            placeholder="اختر الرومات أو الفئات المطلوبة (حد أقصى 25)...",
            min_values=1,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        everyone_role = guild.default_role
        modified_channels_count = 0
        modified_categories_count = 0
        failed_count = 0

        for val in self.values:
            try:
                if val.startswith("cat_"):
                    cat_id = int(val.split("_")[1])
                    category = guild.get_channel(cat_id)
                    if category and isinstance(category, discord.CategoryChannel):
                        # تطبيق الصلاحية على الفئة نفسها
                        if self.action == "hide":
                            await category.set_permissions(everyone_role, view_channel=False, reason=f"Mass hide category by {interaction.user.display_name}")
                        elif self.action == "show":
                            await category.set_permissions(everyone_role, view_channel=None, reason=f"Mass show category by {interaction.user.display_name}")
                        
                        # تطبيق الصلاحية على كافة الرومات الموجودة داخل الفئة لضمان الشمولية التامة
                        for ch in category.channels:
                            if self.action == "hide":
                                await ch.set_permissions(everyone_role, view_channel=False, reason=f"Mass hide via category by {interaction.user.display_name}")
                            elif self.action == "show":
                                await ch.set_permissions(everyone_role, view_channel=None, reason=f"Mass show via category by {interaction.user.display_name}")
                            modified_channels_count += 1
                        
                        modified_categories_count += 1

                elif val.startswith("text_") or val.startswith("voice_"):
                    ch_id = int(val.split("_")[1])
                    channel = guild.get_channel(ch_id)
                    if channel:
                        if self.action == "hide":
                            await channel.set_permissions(everyone_role, view_channel=False, reason=f"Mass hide by {interaction.user.display_name}")
                        elif self.action == "show":
                            await channel.set_permissions(everyone_role, view_channel=None, reason=f"Mass show by {interaction.user.display_name}")
                        modified_channels_count += 1
            except Exception as e:
                failed_count += 1
                print(f"Error updating item {val}: {e}")

        action_titles = {
            "hide": ("إخفاء الفئات والرومات المحددة", 0xCC0000, "🔒"),
            "show": ("إظهار الفئات والرومات المحددة", 0x00CC66, "🔓")
        }
        
        title_text, embed_color, emoji_icon = action_titles.get(self.action, ("تعديل الرومات", 0x2b2d31, "⚡"))

        embed = discord.Embed(
            title=f"{emoji_icon} ╎ تـم تنفيذ: {title_text} 〣 ｢Z I UO｣",
            description=(
                f"> تم تعديل صلاحيات ` {modified_categories_count} ` فئة كاملة.\n"
                f"> تم تعديل صلاحيات ` {modified_channels_count} ` روم بشكل مباشر.\n"
                + (f"> ⚠️ فشل تعديل: {failed_count} عنصر.\n" if failed_count > 0 else "") +
                f"━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=embed_color,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Imperial Enterprise ✦ Categories & Channels Security Engine")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==============================================================================
# 🎛️ واجهة أزرار التحكم الشاملة بالفئات والرومات والطوارئ
# ==============================================================================
class AdvancedRoomManagerView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.guild = guild

    @discord.ui.button(label="إخفاء فئات/رومات", style=discord.ButtonStyle.danger, emoji="🔒", row=0)
    async def hide_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # جلب الفئات أولاً ثم الرومات غير المرتبطة أو تجميع الكل
        targets = list(self.guild.categories) + [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        view = discord.ui.View(timeout=180)
        view.add_item(AdvancedChannelSelect(targets, "hide"))
        await interaction.response.send_message("> 🔒 **اختر الفئات أو الرومات التي تريد إخفاءها عن الأعضاء:**", view=view, ephemeral=True)

    @discord.ui.button(label="إظهار فئات/رومات", style=discord.ButtonStyle.success, emoji="🔓", row=0)
    async def show_channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        targets = list(self.guild.categories) + [ch for ch in self.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
        view = discord.ui.View(timeout=180)
        view.add_item(AdvancedChannelSelect(targets, "show"))
        await interaction.response.send_message("> 🔓 **اختر الفئات أو الرومات التي تريد إظهارها للأعضاء:**", view=view, ephemeral=True)

    @discord.ui.button(label="طوارئ: إخفاء الكل", style=discord.ButtonStyle.secondary, emoji="🛡️", row=1)
    async def hide_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        everyone_role = self.guild.default_role
        count = 0
        # إخفاء كافة الفئات والرومات دفعة واحدة
        for cat in self.guild.categories:
            try:
                await cat.set_permissions(everyone_role, view_channel=False, reason=f"Emergency hide all categories by {interaction.user.display_name}")
                count += 1
            except:
                pass
        for ch in self.guild.channels:
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await ch.set_permissions(everyone_role, view_channel=False, reason=f"Emergency hide all channels by {interaction.user.display_name}")
                    count += 1
                except:
                    pass
        
        embed = discord.Embed(
            title="🛡️ ╎ طـوارئ الـسـيـرفـر ╎ تـم إخـفـاء الـجـمـيـع",
            description=f"> تم تفعيل وضع الطوارئ الشامل وإخفاء إجمالي ` {count} ` فئة وروم عن الأعضاء بنجاح تام.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x990000,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Emergency Lockdown System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="إنهاء الطوارئ: إظهار الكل", style=discord.ButtonStyle.primary, emoji="🌟", row=1)
    async def show_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        everyone_role = self.guild.default_role
        count = 0
        for cat in self.guild.categories:
            try:
                await cat.set_permissions(everyone_role, view_channel=None, reason=f"Emergency show all categories by {interaction.user.display_name}")
                count += 1
            except:
                pass
        for ch in self.guild.channels:
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
                try:
                    await ch.set_permissions(everyone_role, view_channel=None, reason=f"Emergency show all channels by {interaction.user.display_name}")
                    count += 1
                except:
                    pass
        
        embed = discord.Embed(
            title="🌟 ╎ إنـهـاء الـطـوارئ ╎ تـم إظـهـار الـجـمـيـع",
            description=f"> تم إلغاء حالة الطوارئ وإعادة إظهار إجمالي ` {count} ` فئة وروم للأعضاء بنجاح.\n━━━━━━━━━━━━━━━━━━━━━",
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Emergency Lockdown System")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==============================================================================
# ⚙️ أمر لوحة تحكم الرومات والفئات الموحد
# ==============================================================================
class RoomManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="room", description="[إدارة متقدمة] لوحة تحكم ذكية لإدارة ظهور وإخفاء الفئات والرومات وطوارئ الحماية")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def room_manager(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎛️ ╎ لـوحـة تـحـكـم الـفـئـات والـرومـات 〣 ｢Z I UO｣",
            description=(
                "> أهلاً بك يا محمد في لوحة إدارة الفئات والرومات الذكية.\n"
                "> عند اختيار أي **فئة** سيتم إخفاءها مع كافة الرومات الموجودة بداخلها تلقائياً.\n"
                "━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2b2d31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text="Z I UO - Categories & Channels Engine")
        
        await interaction.response.send_message(embed=embed, view=AdvancedRoomManagerView(interaction.guild), ephemeral=True)

async def setup(bot):
    await bot.add_cog(RoomManagerCog(bot))
