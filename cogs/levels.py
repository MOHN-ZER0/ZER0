# -*- coding: utf-8 -*-
"""
=====================================================================================
PROJECT: UI Community Bot - Advanced Enterprise Leveling System
AUTHOR: MOHN-ZERO
DESCRIPTION: Full-featured text and voice ranking, XP management, automated rewards,
             progress bars, and administrative controls.
=====================================================================================
"""

import asyncio
import json
import math
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ===================================================================================
# SECTION 1: DATABASE & STORAGE CONFIGURATION
# ===================================================================================


class LevelingDatabaseManager:
    """مدير قاعدة البيانات المحلي لتخزين وإدارة مستويات ونقاط الأعضاء"""

    def __init__(self, filename: str = "levels_storage_data.json"):
        self.filename = filename
        self.storage = {
            "settings": {
                "text_status": True,
                "voice_status": True,
                "text_cooldown": 45,
                "min_text_xp": 15,
                "max_text_xp": 30,
                "voice_interval": 60,
                "min_voice_xp": 10,
                "max_voice_xp": 20,
                "announcement_channel": None,
                "level_up_msg": "🌊 **مبارك يا {user}!** لقد ارتفع مستواك في `{type}` إلى **المستوى {level}**! 🚀",
                "text_rewards": {},
                "voice_rewards": {},
            },
            "profiles": {},
        }
        self.load_data()

    def load_data(self) -> None:
        """تحميل البيانات من ملف الـ JSON إن وجد"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                    self.storage["settings"].update(loaded.get("settings", {}))
                    self.storage["profiles"] = loaded.get("profiles", {})
            except Exception as error:
                print(f"[Database Error] Could not load storage file: {error}")

    def save_data(self) -> None:
        """حفظ البيانات الحالية بشكل آمن"""
        try:
            with open(self.filename, "w", encoding="utf-8") as file:
                json.dump(self.storage, file, ensure_ascii=False, indent=4)
        except Exception as error:
            print(f"[Database Error] Could not save storage file: {error}")

    def fetch_user_profile(self, user_identifier: int) -> dict:
        """جلب أو إنشاء سجل العضو في قاعدة البيانات"""
        uid = str(user_identifier)
        if uid not in self.storage["profiles"]:
            self.storage["profiles"][uid] = {
                "text_xp": 0,
                "text_level": 0,
                "text_messages": 0,
                "voice_xp": 0,
                "voice_level": 0,
                "voice_seconds": 0,
            }
        return self.storage["profiles"][uid]


# ===================================================================================
# SECTION 2: INTERACTIVE UI VIEWS & DROPDOWNS
# ===================================================================================


class LeaderboardSelectMenu(discord.ui.Select):
    """قائمة منسدلة تفاعلية لعرض إحصائيات الليفل والمتصدرين"""

    def __init__(self, cog_instance: "AdvancedLevelsCog", target_guild: discord.Guild):
        self.cog = cog_instance
        self.guild = target_guild
        options_list = [
            discord.SelectOption(
                label="Text Chat Leaderboard",
                description="عرض قائمة أكثر الأعضاء تفاعلاً في الشات الكتابي",
                emoji="💬",
                value="txt_lb",
            ),
            discord.SelectOption(
                label="Voice Channels Leaderboard",
                description="عرض قائمة أكثر الأعضاء تواجداً في الرومات الصوتية",
                emoji="🔊",
                value="voc_lb",
            ),
            discord.SelectOption(
                label="My Personal Rank Card",
                description="عرض بطاقة مستواك الشخصية والإحصائيات",
                emoji="💳",
                value="my_card",
            ),
        ]
        super().__init__(
            placeholder="🌊 اختر قسم الليفل الذي تريد استعراضه...",
            min_values=1,
            max_values=1,
            options=options_list,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        database = self.cog.database

        if choice == "txt_lb":
            all_users = database.storage["profiles"]
            sorted_users = sorted(
                all_users.items(),
                key=lambda item: item[1].get("text_xp", 0),
                reverse=True,
            )[:10]

            embed = discord.Embed(
                title="💬 ┆ قائمة متصدري الشات الكتابي (Text Ranking)",
                description="ترتيب الأعضاء بناءً على التفاعل والرسائل النصية:",
                color=discord.Color.from_rgb(0, 120, 215),
            )

            if not sorted_users:
                embed.add_field(
                    name="لا توجد بيانات", value="لم يبدأ أحد بالتفاعل كتابياً بعد."
                )
            else:
                for rank, (user_id, stats) in enumerate(sorted_users, start=1):
                    member_obj = self.guild.get_member(int(user_id))
                    display_name = (
                        member_obj.display_name if member_obj else f"User ({user_id})"
                    )
                    lvl = stats.get("text_level", 0)
                    xp = stats.get("text_xp", 0)
                    msgs = stats.get("text_messages", 0)
                    embed.add_field(
                        name=f"#{rank} ┆ {display_name}",
                        value=f"🏆 **المستوى:** `{lvl}` | ✨ **النقاط:** `{xp} XP` | ✉️ **الرسائل:** `{msgs}`",
                        inline=False,
                    )

            embed.set_footer(
                text="استمر في إرسال الرسائل للصعود في قائمة المتصدرين!"
            )
            await interaction.response.edit_message(embed=embed, view=self.view)

        elif choice == "voc_lb":
            all_users = database.storage["profiles"]
            sorted_users = sorted(
                all_users.items(),
                key=lambda item: item[1].get("voice_xp", 0),
                reverse=True,
            )[:10]

            embed = discord.Embed(
                title="🔊 ┆ قائمة متصدري الرومات الصوتية (Voice Ranking)",
                description="ترتيب الأعضاء بناءً على التواجد في الرومات الصوتية:",
                color=discord.Color.from_rgb(138, 43, 226),
            )

            if not sorted_users:
                embed.add_field(
                    name="لا توجد بيانات", value="لم يتواجد أحد في الرومات الصوتية بعد."
                )
            else:
                for rank, (user_id, stats) in enumerate(sorted_users, start=1):
                    member_obj = self.guild.get_member(int(user_id))
                    display_name = (
                        member_obj.display_name if member_obj else f"User ({user_id})"
                    )
                    lvl = stats.get("voice_level", 0)
                    xp = stats.get("voice_xp", 0)
                    hours_count = round(stats.get("voice_seconds", 0) / 3600, 2)
                    embed.add_field(
                        name=f"#{rank} ┆ {display_name}",
                        value=f"🏆 **المستوى:** `{lvl}` | ✨ **النقاط:** `{xp} XP` | ⏱️ **الوقت:** `{hours_count} ساعة`",
                        inline=False,
                    )

            embed.set_footer(text="ابقَ في الرومات الصوتية لزيادة نقاطك ومستواك!")
            await interaction.response.edit_message(embed=embed, view=self.view)

        elif choice == "my_card":
            user_profile = database.fetch_user_profile(interaction.user.id)
            embed = self.cog.build_rank_card_embed(interaction.user, user_profile)
            await interaction.response.edit_message(embed=embed, view=self.view)


class LeaderboardInteractiveView(discord.ui.View):
    """لوحة تحكم الأزرار والقوائم الخاصة بأمر الليفل"""

    def __init__(self, cog_instance: "AdvancedLevelsCog", target_guild: discord.Guild):
        super().__init__(timeout=300)
        self.add_item(LeaderboardSelectMenu(cog_instance, target_guild))

    @discord.ui.button(
        label="تحديث اللوحة 🔄",
        style=discord.ButtonStyle.secondary,
        custom_id="refresh_panel_btn",
    )
    async def refresh_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = discord.Embed(
            title="🌊 ┆ نظام التلفيل والرتب الشامل (Levels Hub)",
            description=(
                "مرحباً بك في مركز إحصائيات السيرفر المتطور!\n"
                "يرجى استخدام القائمة المنسدلة بالأسفل لاختيار النظام المطلوب استعراضه بكل سهولة."
            ),
            color=discord.Color.from_rgb(30, 144, 255),
        )
        await interaction.response.edit_message(embed=embed, view=self)


# ===================================================================================
# SECTION 3: MAIN COG IMPLEMENTATION
# ===================================================================================


class AdvancedLevelsCog(commands.Cog):
    """نظام التلفيل المتقدم والاحترافي المتكامل للشات والصوت"""

    def __init__(self, bot_instance: commands.Bot):
        self.bot = bot_instance
        self.database = LevelingDatabaseManager()
        self.message_cooldowns: Dict[int, float] = {}
        self.voice_activity_loop.start()

    def cog_unload(self) -> None:
        self.voice_activity_loop.cancel()
        self.database.save_data()

    # -------------------------------------------------------------------------------
    # MATHEMATICAL CALCULATIONS & FORMATTING
    # -------------------------------------------------------------------------------
    @staticmethod
    def calculate_required_xp(level: int) -> int:
        """معادلة رياضية دقيقة لحساب الـ XP المطلوب للوصول للمستوى التالي"""
        return int(5 * (level**2) + (50 * level) + 100)

    def resolve_level_from_xp(self, total_xp: int) -> Tuple[int, int, int]:
        """تفكيك إجمالي الـ XP إلى مستوى حالي، نقاط حالية، ونقاط مطلوبة للتقدم"""
        current_level = 0
        while total_xp >= self.calculate_required_xp(current_level):
            total_xp -= self.calculate_required_xp(current_level)
            current_level += 1
        current_remainder = total_xp
        needed_for_next = self.calculate_required_xp(current_level)
        return current_level, current_remainder, needed_for_next

    def generate_visual_progress_bar(
        self, current: int, maximum: int, length: int = 12
    ) -> str:
        """توليد شريط تقدم بصري جميل ومناسب للتصميم"""
        if maximum <= 0:
            return "░" * length
        percentage = min(1.0, max(0.0, current / maximum))
        filled_blocks = int(length * percentage)
        return "█" * filled_blocks + "░" * (length - filled_blocks)

    def build_rank_card_embed(
        self, member: discord.Member, profile_data: dict
    ) -> discord.Embed:
        """بناء بطاقة إمبد احترافية تفصيلية لعرض إحصائيات العضو"""
        txt_xp = profile_data.get("text_xp", 0)
        t_lvl, t_curr, t_need = self.resolve_level_from_xp(txt_xp)
        t_bar = self.generate_visual_progress_bar(t_curr, t_need)
        t_percent = int((t_curr / t_need) * 100) if t_need > 0 else 0

        voc_xp = profile_data.get("voice_xp", 0)
        v_lvl, v_curr, v_need = self.resolve_level_from_xp(voc_xp)
        v_bar = self.generate_visual_progress_bar(v_curr, v_need)
        v_percent = int((v_curr / v_need) * 100) if v_need > 0 else 0

        embed = discord.Embed(
            title=f"💳 ┆ بطاقة إحصائيات العضو: {member.display_name}",
            color=member.color or discord.Color.blue(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💬 ┆ إحصائيات الشات الكتابي (Text Stats)",
            value=(
                f"• **المستوى:** `{t_lvl}`\n"
                f"• **النقاط:** `{t_curr} / {t_need} XP` (الإجمالي: `{txt_xp}`)\n"
                f"• **التقدم:** `[{t_bar}]` ({t_percent}%)\n"
                f"• **الرسائل:** `{profile_data.get('text_messages', 0)}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔊 ┆ إحصائيات الرومات الصوتية (Voice Stats)",
            value=(
                f"• **المستوى:** `{v_lvl}`\n"
                f"• **النقاط:** `{v_curr} / {v_need} XP` (الإجمالي: `{voc_xp}`)\n"
                f"• **التقدم:** `[{v_bar}]` ({v_percent}%)\n"
                f"• **وقت التواجد:** `{round(profile_data.get('voice_seconds', 0) / 3600, 2)} ساعة`"
            ),
            inline=False,
        )

        embed.set_footer(
            text=f"Requested ID: {member.id}",
            icon_url=self.bot.user.display_avatar.url,
        )
        return embed

    # -------------------------------------------------------------------------------
    # LEVEL UP & ROLE REWARD DISPATCHER
    # -------------------------------------------------------------------------------
    async def process_level_up_actions(
        self,
        member: discord.Member,
        new_level: int,
        system_type: str,
        channel: discord.TextChannel,
    ) -> None:
        """معالجة ترقيات المستوى ومنح رتب المكافآت التلقائية"""
        config = self.database.storage["settings"]
        rewards_dict = (
            config["text_rewards"]
            if system_type == "Text"
            else config["voice_rewards"]
        )

        string_level = str(new_level)
        if string_level in rewards_dict:
            target_role_id = rewards_dict[string_level]
            assigned_role = member.guild.get_role(target_role_id)
            if assigned_role and assigned_role not in member.roles:
                try:
                    await member.add_roles(
                        assigned_role,
                        reason=f"Automated Level Reward: Achieved {system_type} Level {new_level}",
                    )
                except Exception as ex:
                    print(f"[Reward Error] Failed to assign role: {ex}")

        template_message = config.get(
            "level_up_msg", "🎉 مبارك العضو {user} وصوله للمستوى {level}!"
        )
        formatted_message = template_message.format(
            user=member.mention, level=new_level, type=system_type
        )

        destination_channel = channel
        if config.get("announcement_channel"):
            custom_chan = member.guild.get_channel(config["announcement_channel"])
            if custom_chan and isinstance(custom_chan, discord.TextChannel):
                destination_channel = custom_chan

        try:
            await destination_channel.send(formatted_message)
        except Exception:
            pass

    # -------------------------------------------------------------------------------
    # EVENT LISTENERS (TEXT MESSAGES & VOICE ACTIVITY LOOP)
    # -------------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        settings = self.database.storage["settings"]
        if not settings.get("text_status", True):
            return

        author_id = message.author.id
        current_time = time.time()
        cooldown_duration = settings.get("text_cooldown", 45)

        if author_id in self.message_cooldowns:
            if current_time - self.message_cooldowns[author_id] < cooldown_duration:
                return

        self.message_cooldowns[author_id] = current_time

        user_profile = self.database.fetch_user_profile(author_id)
        old_lvl, _, _ = self.resolve_level_from_xp(user_profile["text_xp"])

        gained_xp = random.randint(
            settings.get("min_text_xp", 15), settings.get("max_text_xp", 30)
        )
        user_profile["text_xp"] += gained_xp
        user_profile["text_messages"] += 1

        new_lvl, _, _ = self.resolve_level_from_xp(user_profile["text_xp"])
        user_profile["text_level"] = new_lvl
        self.database.save_data()

        if new_lvl > old_lvl:
            await self.process_level_up_actions(
                message.author, new_lvl, "Text", message.channel
            )

    @tasks.loop(seconds=60)
    async def voice_activity_loop(self) -> None:
        """مهمة خلفية دورية لفحص وإعطاء نقاط XP للأعضاء المتواجدين في الصوت"""
        settings = self.database.storage["settings"]
        if not settings.get("voice_status", True):
            return

        for guild in self.bot.guilds:
            for v_channel in guild.voice_channels:
                for member in v_channel.members:
                    if (
                        member.bot
                        or member.voice.self_deaf
                        or member.voice.deaf
                        or member.voice.self_mute
                    ):
                        continue

                    user_profile = self.database.fetch_user_profile(member.id)
                    old_lvl, _, _ = self.resolve_level_from_xp(user_profile["voice_xp"])

                    gained_xp = random.randint(
                        settings.get("min_voice_xp", 10),
                        settings.get("max_voice_xp", 20),
                    )
                    user_profile["voice_xp"] += gained_xp
                    user_profile["voice_seconds"] += 60

                    new_lvl, _, _ = self.resolve_level_from_xp(user_profile["voice_xp"])
                    user_profile["voice_level"] = new_lvl

                    if new_lvl > old_lvl:
                        fallback_channel = (
                            v_channel.text_channel
                            if hasattr(v_channel, "text_channel")
                            and v_channel.text_channel
                            else guild.system_channel
                        )
                        if fallback_channel:
                            await self.process_level_up_actions(
                                member, new_lvl, "Voice", fallback_channel
                            )

        self.database.save_data()

    @voice_activity_loop.before_loop
    async def before_voice_activity_task(self) -> None:
        await self.bot.wait_until_ready()

    # -------------------------------------------------------------------------------
    # SLASH COMMANDS (USER INTERFACE)
    # -------------------------------------------------------------------------------
    @app_commands.command(
        name="levels",
        description="فتح لوحة التحكم المركزية لإحصائيات التلفيل والمتصدرين",
    )
    async def levels_main_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🌊 ┆ نظام التلفيل والرتب الشامل (Levels Hub)",
            description=(
                "مرحباً بك في مركز إحصائيات السيرفر المتطور!\n"
                "يرجى استخدام القائمة المنسدلة بالأسفل لاختيار النظام المطلوب استعراضه بكل سهولة."
            ),
            color=discord.Color.from_rgb(30, 144, 255),
        )
        embed.set_thumbnail(
            url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.add_field(
            name="📊 حالة الأنظمة الحالية",
            value=(
                f"• الشات الكتابي: `{'مفعل ✅' if self.database.storage['settings']['text_status'] else 'معطل ❌'}`\n"
                f"• الرومات الصوتية: `{'مفعل ✅' if self.database.storage['settings']['voice_status'] else 'معطل ❌'}`"
            ),
            inline=False,
        )

        interactive_view = LeaderboardInteractiveView(self, interaction.guild)
        await interaction.response.send_message(embed=embed, view=interactive_view)

    @app_commands.command(
        name="rank", description="استعراض بطاقة المستوى الخاصة بك أو بأي عضو"
    )
    async def rank_card_command(
        self,
        interaction: discord.Interaction,
        target_member: Optional[discord.Member] = None,
    ) -> None:
        selected_member = target_member or interaction.user
        user_profile = self.database.fetch_user_profile(selected_member.id)
        card_embed = self.build_rank_card_embed(selected_member, user_profile)
        await interaction.response.send_message(embed=card_embed)

    # -------------------------------------------------------------------------------
    # ADMINISTRATIVE CONTROL GROUP (ADMIN COMMANDS)
    # -------------------------------------------------------------------------------
    admin_group = app_commands.Group(
        name="level-config",
        description="لوحة إعدادات وتخصيص نظام الليفل الإدارية",
        default_permissions=discord.Permissions(administrator=True),
    )

    @admin_group.command(
        name="toggle", description="تشغيل أو إيقاف نظام معين (الشات أو الصوت)"
    )
    async def admin_toggle_subcommand(
        self,
        interaction: discord.Interaction,
        system_type: str,
        status_value: bool,
    ) -> None:
        system_key = system_type.lower()
        if system_key not in ["text", "voice"]:
            return await interaction.response.send_message(
                "❌ النوع يجب أن يكون تحديداً `text` أو `voice`.", ephemeral=True
            )

        config_key = f"{system_key}_status"
        self.database.storage["settings"][config_key] = status_value
        self.database.save_data()
        await interaction.response.send_message(
            f"✅ تم تغيير حالة نظام `{system_type}` بنجاح إلى: **{'مفعل' if status_value else 'معطل'}**.",
            ephemeral=True,
        )

    @admin_group.command(
        name="add-reward", description="ربط مستوى معين برتبة مكافأة تلقائية"
    )
    async def admin_add_reward_subcommand(
        self,
        interaction: discord.Interaction,
        system_type: str,
        target_level: int,
        reward_role: discord.Role,
    ) -> None:
        sys_key = system_type.lower()
        if sys_key not in ["text", "voice"]:
            return await interaction.response.send_message(
                "❌ نوع النظام يجب أن يكون `text` أو `voice`.", ephemeral=True
            )

        dictionary_key = "text_rewards" if sys_key == "text" else "voice_rewards"
        self.database.storage["settings"][dictionary_key][
            str(target_level)
        ] = reward_role.id
        self.database.save_data()
        await interaction.response.send_message(
            f"✅ تم بنجاح ربط المستوى `{target_level}` في نظام `{system_type}` بالرتبة {reward_role.mention}.",
            ephemeral=True,
        )

    @admin_group.command(
        name="set-xp-range", description="تعديل الحد الأدنى والأقصى لنقاط الـ XP"
    )
    async def admin_set_xp_subcommand(
        self,
        interaction: discord.Interaction,
        system_type: str,
        minimum_xp: int,
        maximum_xp: int,
    ) -> None:
        if minimum_xp >= maximum_xp:
            return await interaction.response.send_message(
                "❌ الحد الأدنى يجب أن يكون أقل من الحد الأقصى تماماً!",
                ephemeral=True,
            )

        sys_key = system_type.lower()
        if sys_key not in ["text", "voice"]:
            return await interaction.response.send_message(
                "❌ نوع النظام غير صحيح. استخدم `text` أو `voice`.", ephemeral=True
            )

        self.database.storage["settings"][f"min_{sys_key}_xp"] = minimum_xp
        self.database.storage["settings"][f"max_{sys_key}_xp"] = maximum_xp
        self.database.save_data()
        await interaction.response.send_message(
            f"⚙️ تم تحديث نطاق الـ XP لنظام `{system_type}` ليصبح بين `{minimum_xp}` و `{maximum_xp}` نقطة.",
            ephemeral=True,
        )


# ===================================================================================
# SECTION 4: COG SETUP LOADER
# ===================================================================================


async def setup(bot_instance: commands.Bot) -> None:
    await bot_instance.add_cog(AdvancedLevelsCog(bot_instance))
