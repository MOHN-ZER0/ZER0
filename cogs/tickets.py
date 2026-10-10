import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
import io
import asyncio

TICKETS_DB_FILE = "ultimate_tickets_database.json"

def load_tickets_db():
    if os.path.exists(TICKETS_DB_FILE):
        try:
            with open(TICKETS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_tickets_db(data):
    with open(TICKETS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==============================================================================
# ⭐ نظام التقييم والحذف السريع
# ==============================================================================
class TicketRatingView(discord.ui.View):
    def __init__(self, ticket_channel: discord.TextChannel = None, ticket_creator_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.ticket_creator_id = ticket_creator_id

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.danger, custom_id="rate_1_v7")
    async def rate_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 1)

    @discord.ui.button(label="⭐⭐ 2", style=discord.ButtonStyle.danger, custom_id="rate_2_v7")
    async def rate_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 2)

    @discord.ui.button(label="⭐⭐⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rate_3_v7")
    async def rate_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 3)

    @discord.ui.button(label="⭐⭐⭐⭐ 4", style=discord.ButtonStyle.success, custom_id="rate_4_v7")
    async def rate_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 4)

    @discord.ui.button(label="⭐⭐⭐⭐⭐ 5", style=discord.ButtonStyle.success, custom_id="rate_5_v7")
    async def rate_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 5)

    async def handle_rating_and_delete(self, interaction: discord.Interaction, stars: int):
        if self.ticket_creator_id and interaction.user.id != self.ticket_creator_id:
            embed_err = discord.Embed(title="❌ تنبيه", description="التقييم مخصص لصاحب التذكرة فقط.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        
        target_chan = self.ticket_channel or interaction.channel

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        t_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(str(target_chan.id), {})
        claimer_id = t_info.get("claimed_by")
        if claimer_id:
            if "staff_stats" not in db[guild_id_str]:
                db[guild_id_str]["staff_stats"] = {}
            c_str = str(claimer_id)
            if c_str not in db[guild_id_str]["staff_stats"]:
                db[guild_id_str]["staff_stats"][c_str] = {"claimed": 0, "total_stars": 0, "ratings_count": 0}
            db[guild_id_str]["staff_stats"][c_str]["total_stars"] += stars
            db[guild_id_str]["staff_stats"][c_str]["ratings_count"] += 1
            save_tickets_db(db)

        stars_str = "⭐" * stars
        try:
            embed = discord.Embed(title="شكراً لتقييمك", description=f"تم تسجيل تقييمك ({stars_str}). سيتم حذف التذكرة خلال 3 ثوانٍ...", color=0x00FF88)
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            pass
        
        await asyncio.sleep(3)
        
        voice_chan_id = t_info.get("temp_voice_id")
        if voice_chan_id:
            v_chan = interaction.guild.get_channel(int(voice_chan_id))
            if v_chan:
                try:
                    await v_chan.delete()
                except:
                    pass

        try:
            await target_chan.delete()
        except:
            pass


# ==============================================================================
# 📝 نافذة كتابة سبب الحذف للإداري
# ==============================================================================
class DeleteReasonModal(discord.ui.Modal, title="🗑️ سبب حذف التذكرة"):
    reason_box = discord.ui.TextInput(
        label="سبب الإغلاق / الحذف",
        placeholder="اكتب سبب حذف التذكرة هنا...",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.reason_box.value.strip()
        channel = interaction.channel
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        
        db = load_tickets_db()
        guild_data = db.get(guild_id_str, {})
        ticket_data = guild_data.get("active_tickets", {}).pop(channel_id_str, None)
        
        if ticket_data:
            ticket_data["status"] = "مغلقة ومحذوفة"
            ticket_data["closed_by"] = interaction.user.id
            ticket_data["close_reason"] = reason_text
            ticket_data["closed_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            if "closed_tickets_archive" not in guild_data:
                guild_data["closed_tickets_archive"] = []
            guild_data["closed_tickets_archive"].append(ticket_data)
            save_tickets_db(db)

            # إرسال الترانسكريبت إلى روم اللوج
            messages_history = []
            try:
                async for msg in channel.history(limit=500, oldest_first=True):
                    time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    messages_history.append(f"[{time_str}] {msg.author.name}: {msg.content}")
            except:
                pass

            transcript_text = f"=== TRANSCRIPT: {channel.name} ===\n" + "\n".join(messages_history)
            file_bytes = io.BytesIO(transcript_text.encode("utf-8"))
            file = discord.File(file_bytes, filename=f"transcript-{channel.name}.txt")

            log_channel_id = guild_data.get("log_channel_id")
            if log_channel_id:
                log_chan = interaction.guild.get_channel(int(log_channel_id))
                if log_chan:
                    creator_obj = interaction.guild.get_member(ticket_data.get("user_id"))
                    closer_obj = interaction.user
                    claimer_id = ticket_data.get("claimed_by")
                    claimer_obj = interaction.guild.get_member(claimer_id) if claimer_id else None

                    log_embed = discord.Embed(
                        title="📁 سجل تذكرة مغلقة",
                        color=0xFF3333,
                        timestamp=datetime.datetime.utcnow()
                    )
                    log_embed.add_field(name="🎫 التذكرة", value=f"`{channel.name}`", inline=True)
                    log_embed.add_field(name="📂 القسم", value=f"`{ticket_data.get('section')}`", inline=True)
                    log_embed.add_field(name="👤 صاحب التذكرة", value=f"{creator_obj.mention if creator_obj else 'غير معروف'}", inline=True)
                    log_embed.add_field(name="💼 المشرف", value=f"{claimer_obj.mention if claimer_obj else 'مفيش'}", inline=True)
                    log_embed.add_field(name="🗑️ اتنفت بواسطة", value=f"{closer_obj.mention}", inline=True)
                    log_embed.add_field(name="📌 سبب الحذف", value=f"```{reason_text}```", inline=False)

                    try:
                        await log_chan.send(embed=log_embed, file=file)
                    except:
                        pass

        # إرسال رسالة سبب الحذف وإتاحة التقييم مباشرة للعضو
        creator_id_val = ticket_data.get("user_id", interaction.user.id) if ticket_data else interaction.user.id
        
        embed_reason_msg = discord.Embed(
            title="🗑️ تقرر حذف التذكرة",
            description=f"**السبب:** {reason_text}\n**بواسطة:** {interaction.user.mention}",
            color=0xFF3333
        )
        embed_rate = discord.Embed(
            title="⭐ تقييم الخدمة",
            description=f"يا <@{creator_id_val}> يرجى تقييم مستوى الدعم الفني قبل إغلاق التذكرة نهائياً:",
            color=0x2B2D31
        )

        await interaction.response.send_message(embed=embed_reason_msg)
        await channel.send(embed=embed_rate, view=TicketRatingView(channel, creator_id_val))


# ==============================================================================
# 🔒 خيارات قفل/فتح التذكرة (مع مهلة حماية 5 ثوانٍ)
# ==============================================================================
class CloseConfirmationView(discord.ui.View):
    def __init__(self, closed_timestamp: float = 0):
        super().__init__(timeout=None)
        self.closed_timestamp = closed_timestamp

    @discord.ui.button(label="إعادة فتح", style=discord.ButtonStyle.success, emoji="🔓", custom_id="confirm_reopen_ticket_btn_v7")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = datetime.datetime.utcnow().timestamp()
        if self.closed_timestamp and (current_time - self.closed_timestamp) < 5:
            remaining = round(5 - (current_time - self.closed_timestamp), 1)
            await interaction.response.send_message(f"⏳ يجب الانتظار لمدة {remaining} ثوانٍ إضافية قبل إمكانية فتح التذكرة مرة أخرى.", ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        t_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str)
        
        if not t_info:
            await interaction.response.send_message("❌ التذكرة دي مش مسجلة في النظام.", ephemeral=True)
            return

        t_info["status"] = "مفتوحة"
        save_tickets_db(db)

        embed_reopened = discord.Embed(
            title="🔓 تم إعادة فتح التذكرة",
            description=f"تم فتح التذكرة بواسطة {interaction.user.mention}.",
            color=0x00FF88,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed_reopened)

    @discord.ui.button(label="حذف التذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="confirm_delete_ticket_btn_v7")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        t_info = db.get(str(interaction.guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id), {})
        
        if interaction.user.id == t_info.get("user_id"):
            embed_err_creator = discord.Embed(title="❌ غير مسموح", description="صاحب التذكرة يقدر يقفلها بس، الحذف للإدارة فقط.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err_creator, ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_channels and not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(title="❌ خطأ", description="معندكش صلاحية لحذف التذكرة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # فتح المودال للإداري ليكتب سبب الحذف
        await interaction.response.send_modal(DeleteReasonModal())


# ==============================================================================
# ⚡ الردود السريعة (للمشرفين وفريق الدعم فقط)
# ==============================================================================
class QuickRepliesSelect(discord.ui.Select):
    def __init__(self, quick_replies_list: list = None):
        options = []
        if quick_replies_list and isinstance(quick_replies_list, list):
            for idx, resp_text in enumerate(quick_replies_list):
                if resp_text.strip():
                    options.append(discord.SelectOption(
                        label=resp_text[:95], 
                        emoji="⚡", 
                        value=f"qr_custom_{idx}"
                    ))
        
        self.quick_replies_list = quick_replies_list or []

        if not options:
            options.append(discord.SelectOption(label="مفيش ردود سريعة جاهزة", value="none", emoji="❌"))

        super().__init__(
            placeholder="⚡ اختر رد سريع لارسال...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="quick_replies_select_v7"
        )

    async def callback(self, interaction: discord.Interaction):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        t_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        
        support_role_ids = t_info.get("support_role_ids", [])
        is_staff = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        if not is_staff and support_role_ids:
            if any(role.id in support_role_ids for role in interaction.user.roles):
                is_staff = True

        if not is_staff:
            await interaction.response.send_message("❌ الإدارة فقط من تستطيع استخدام هذه الردود.", ephemeral=True)
            return

        if self.values[0] == "none":
            await interaction.response.send_message("❌ مفيش ردود سريعة مضافة هنا.", ephemeral=True)
            return

        val = self.values[0]
        text = "أهلاً بك."
        
        if val.startswith("qr_custom_"):
            try:
                idx = int(val.split("_")[-1])
                if idx < len(self.quick_replies_list):
                    text = self.quick_replies_list[idx]
            except:
                pass

        embed = discord.Embed(description=text, color=0x2B2D31)
        await interaction.channel.send(embed=embed)
        
        if t_info:
            t_info["last_activity"] = datetime.datetime.utcnow().timestamp()
            save_tickets_db(db)

        embed_resp = discord.Embed(title="✅ تم الإرسال", description="تم إرسال الرد السريع.", color=0x00FF88)
        await interaction.response.send_message(embed=embed_resp, ephemeral=True)


# ==============================================================================
# 🔄 نقل التذكرة لمشرف تاني
# ==============================================================================
class ClaimSwitchSelect(discord.ui.Select):
    def __init__(self, channel_id: str, support_role_ids: list, guild: discord.Guild):
        options = []
        for member in guild.members:
            if not member.bot:
                if not support_role_ids or any(r.id in support_role_ids for r in member.roles):
                    options.append(discord.SelectOption(label=member.display_name[:95], value=str(member.id), emoji="👤"))
        
        if not options:
            options.append(discord.SelectOption(label="مفيش أعضاء برتبة الدعم", value="none"))

        super().__init__(placeholder="اختر المشرف الجديد...", min_values=1, max_values=1, options=options)
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ مفيش أعضاء متاحين.", ephemeral=True)
            return

        new_claimer_id = int(self.values[0])
        new_claimer = interaction.guild.get_member(new_claimer_id)

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(self.channel_id)
        
        if ticket_info:
            ticket_info["claimed_by"] = new_claimer_id
            ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
            save_tickets_db(db)

        old_mention = interaction.user.mention
        new_mention = new_claimer.mention if new_claimer else f"<@{new_claimer_id}>"

        embed = discord.Embed(
            title="🔄 تم تحويل التذكرة",
            description=f"تم نقل متابعة التذكرة من {old_mention} إلى {new_mention}.",
            color=0x00FF88,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ تم نقل التذكرة بنجاح.", ephemeral=True)


class ClaimSwitchView(discord.ui.View):
    def __init__(self, channel_id: str, support_role_ids: list, guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(ClaimSwitchSelect(channel_id, support_role_ids, guild))


# ==============================================================================
# 🎛️ أزرار التحكم داخل التذكرة
# ==============================================================================
class TicketInsideView(discord.ui.View):
    def __init__(self, guild_id: int = 0, panel_name: str = "", quick_replies: list = None, higher_role_id: int = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_name = panel_name
        self.quick_replies = quick_replies
        self.higher_role_id = higher_role_id
        
        if quick_replies and len(quick_replies) > 0:
            self.add_item(QuickRepliesSelect(quick_replies))

        if not higher_role_id:
            for child in list(self.children):
                if getattr(child, "custom_id", "") == "escalate_ticket_btn_v7":
                    self.remove_item(child)

    @discord.ui.button(label="استلام", style=discord.ButtonStyle.primary, emoji="💼", custom_id="claim_ticket_v7_btn", row=1)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        guild_data = db.get(guild_id_str, {})
        active_tickets = guild_data.get("active_tickets", {})
        
        if channel_id_str not in active_tickets:
            embed = discord.Embed(title="❌ خطأ", description="التذكرة دي غير مسجلة في النظام.", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        ticket_info = active_tickets[channel_id_str]
        
        creator_id = ticket_info.get("user_id")
        if interaction.user.id == creator_id:
            embed_creator_err = discord.Embed(
                title="❌ غير مسموح",
                description="متقدرش تستلم تذكرتك بنفسك!",
                color=0xFF3333
            )
            await interaction.response.send_message(embed=embed_creator_err, ephemeral=True)
            return

        support_role_ids = ticket_info.get("support_role_ids", [])
        
        is_staff = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        if not is_staff and support_role_ids:
            if any(role.id in support_role_ids for role in interaction.user.roles):
                is_staff = True

        if not is_staff:
            embed = discord.Embed(title="❌ غير مسموح", description="الزر ده خاص بفريق الدعم بس.", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        old_claimer_id = ticket_info.get("claimed_by")

        if old_claimer_id == interaction.user.id:
            class UnclaimConfirmView(discord.ui.View):
                def __init__(self, ch_id, sup_roles, guild_obj):
                    super().__init__(timeout=30)
                    self.ch_id = ch_id
                    self.sup_roles = sup_roles
                    self.guild_obj = guild_obj

                @discord.ui.button(label="إلغاء الاستلام", style=discord.ButtonStyle.danger, emoji="🔓", custom_id="confirm_unclaim_v7")
                async def confirm_unclaim(self, inter: discord.Interaction, btn: discord.ui.Button):
                    db_inner = load_tickets_db()
                    t_inf = db_inner.get(str(inter.guild.id), {}).get("active_tickets", {}).get(self.ch_id)
                    if t_inf:
                        t_inf.pop("claimed_by", None)
                        t_inf["last_activity"] = datetime.datetime.utcnow().timestamp()
                        save_tickets_db(db_inner)
                    embed_res = discord.Embed(title="🔓 تم إلغاء الاستلام", description=f"قام {inter.user.mention} بترك استلام التذكرة وأصبحت متاحة للجميع.", color=0xFF3333)
                    await inter.channel.send(embed=embed_res)
                    await inter.response.send_message("✅ تم إلغاء استلامك للتذكرة بنجاح.", ephemeral=True)

                @discord.ui.button(label="تحويل لمشرف", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="switch_claim_v7")
                async def switch_claim(self, inter: discord.Interaction, btn: discord.ui.Button):
                    embed_switch = discord.Embed(title="🔄 تحويل التذكرة", description="اختر المشرف اللي عاوز تحول التذكرة ليه:", color=0x2B2D31)
                    await inter.response.send_message(embed=embed_switch, view=ClaimSwitchView(self.ch_id, self.sup_roles, self.guild_obj), ephemeral=True)

            embed_ask = discord.Embed(title="💼 حالة التذكرة", description="أنت مستلم التذكرة دي بالفعل. حابب تعمل ايه؟", color=0xFFA500)
            await interaction.response.send_message(embed=embed_ask, view=UnclaimConfirmView(channel_id_str, support_role_ids, interaction.guild), ephemeral=True)
            return

        if old_claimer_id and old_claimer_id != interaction.user.id:
            ticket_info["claimed_by"] = interaction.user.id
            ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
            save_tickets_db(db)
            
            old_claimer_obj = interaction.guild.get_member(old_claimer_id)
            old_mention = old_claimer_obj.mention if old_claimer_obj else f"<@{old_claimer_id}>"
            
            embed_switched = discord.Embed(
                title="🔄 تم تغيير المشرف",
                description=f"تم نقل التذكرة من {old_mention} إلى {interaction.user.mention}.",
                color=0x00FF88,
                timestamp=datetime.datetime.utcnow()
            )
            await interaction.channel.send(embed=embed_switched)
            await interaction.response.send_message("✅ تم استلام التذكرة بنجاح.", ephemeral=True)
            return

        ticket_info["claimed_by"] = interaction.user.id
        ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
        
        if "staff_stats" not in guild_data:
            guild_data["staff_stats"] = {}
        c_str = str(interaction.user.id)
        if c_str not in guild_data["staff_stats"]:
            guild_data["staff_stats"][c_str] = {"claimed": 0, "total_stars": 0, "ratings_count": 0}
        guild_data["staff_stats"][c_str]["claimed"] += 1
        save_tickets_db(db)

        try:
            await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)
        except:
            pass
        
        embed = discord.Embed(
            title="💼 تم استلام التذكرة",
            description=f"المشرف المسؤول: {interaction.user.mention}",
            color=0x00FF88,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="add_member_ticket_btn_v7", row=2)
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        t_info = db.get(str(interaction.guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id), {})
        
        if interaction.user.id == t_info.get("user_id"):
            embed_err = discord.Embed(
                title="❌ غير مسموح",
                description="صاحب التذكرة ميعرفش يضيف أعضاء للتذكرة.",
                color=0xFF3333
            )
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        await interaction.response.send_modal(AddMemberModal())

    @discord.ui.button(label="غرفة صوتية", style=discord.ButtonStyle.success, emoji="🔊", custom_id="create_temp_voice_btn_v7", row=2)
    async def create_temp_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = interaction.channel.category
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            interaction.user: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)
        }
        
        db = load_tickets_db()
        t_info = db.get(str(guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id), {})
        t_info["last_activity"] = datetime.datetime.utcnow().timestamp()
        save_tickets_db(db)

        creator_id = t_info.get("user_id")
        creator = guild.get_member(creator_id)
        if creator:
            overwrites[creator] = discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)
            
        for r_id in t_info.get("support_role_ids", []):
            role = guild.get_role(r_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)

        channel_name_parts = interaction.channel.name.split("・")
        ticket_number_str = channel_name_parts[-1] if len(channel_name_parts) > 1 else "1"

        voice_chan = await guild.create_voice_channel(
            name=f"🎫・Voice・{ticket_number_str}",
            category=category,
            overwrites=overwrites
        )

        t_info["temp_voice_id"] = str(voice_chan.id)
        save_tickets_db(db)

        embed = discord.Embed(title="🔊 تم إنشاء الفويس", description=f"تم عمل روم صوتي خاص بالتذكرة: {voice_chan.mention}", color=0x00FF88)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @discord.ui.button(label="تنبيه", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="smart_ping_ticket_btn_v7", row=2)
    async def smart_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        
        if not ticket_info:
            embed_err = discord.Embed(title="❌ خطأ", description="مش قادرين نقرأ بيانات التذكرة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
        save_tickets_db(db)

        creator_id = ticket_info.get("user_id")
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        if interaction.user.id == creator_id:
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "الدعم الفني"
            content_msg = f"🔔 تنبيه من {interaction.user.mention} لـ {mentions}: يرجى الرد في أقرب وقت."
            await interaction.channel.send(content=content_msg)
            
            embed_ok = discord.Embed(title="✅ تم التنبيه", description="تم إرسال تنبيه لفريق الدعم.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok, ephemeral=True)
        else:
            creator_obj = interaction.guild.get_member(creator_id)
            creator_mention = creator_obj.mention if creator_obj else f"<@{creator_id}>"
            
            content_msg = f"🔔 تنبيه من الإدارة لـ {creator_mention}: يرجى الرد لمتابعة تذكرتك."
            await interaction.channel.send(content=content_msg)
            
            embed_ok2 = discord.Embed(title="✅ تم التنبيه", description="تم إرسال التنبيه للعضو.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok2, ephemeral=True)

    @discord.ui.button(label="تصعيد للإدارة", style=discord.ButtonStyle.primary, emoji="👑", custom_id="escalate_ticket_btn_v7", row=3)
    async def escalate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        if ticket_info:
            ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
            save_tickets_db(db)

        higher_role_id = ticket_info.get("higher_support_role_id")
        
        if higher_role_id:
            mentions = f"<@&{higher_role_id}>"
        else:
            support_role_ids = ticket_info.get("support_role_ids", [])
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "الإدارة العليا"
        
        content_msg = f"👑 **طلب مسؤول أعلى:** قام {interaction.user.mention} بطلب إشراف أعلى ({mentions})."
        await interaction.channel.send(content=content_msg)
        
        embed_done = discord.Embed(title="✅ تم التصعيد", description="تم إرسال إشعار للإدارة العليا.", color=0x00FF88)
        await interaction.response.send_message(embed=embed_done, ephemeral=True)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_v7_btn", row=3)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        t_info = db.get(str(interaction.guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id))
        if t_info:
            t_info["last_activity"] = datetime.datetime.utcnow().timestamp()
            save_tickets_db(db)

        closed_time = datetime.datetime.utcnow().timestamp()
        embed_close = discord.Embed(title="🔒 تم إغلاق التذكرة", description="اختر الخيار المناسب لتنفيذه:", color=0x2B2D31)
        await interaction.channel.send(embed=embed_close, view=CloseConfirmationView(closed_timestamp=closed_time))
        await interaction.response.send_message("✅ تم إغلاق التذكرة بنجاح.", ephemeral=True)


class AddMemberModal(discord.ui.Modal, title="➕ إضافة عضو للتذكرة"):
    member_box = discord.ui.TextInput(label="أيدي العضو (User ID)", placeholder="اكتب أيدي العضو هنا...", max_length=30, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        member_id_text = self.member_box.value.strip()
        if not member_id_text.isdigit():
            embed = discord.Embed(title="❌ خطأ", description="يرجى كتابة أيدي صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        member = interaction.guild.get_member(int(member_id_text))
        if not member:
            embed = discord.Embed(title="❌ خطأ", description="العضو ده مش موجود في السيرفر!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
            db = load_tickets_db()
            t_info = db.get(str(interaction.guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id))
            if t_info:
                t_info["last_activity"] = datetime.datetime.utcnow().timestamp()
                save_tickets_db(db)

            embed = discord.Embed(title="✅ تم الإضافة", description=f"تم إضافة {member.mention} للتذكرة بنجاح.", color=0x00FF88)
            await interaction.response.send_message(embed=embed)
        except:
            embed = discord.Embed(title="❌ خطأ", description="حصلت مشكلة وأنا بغير الصلاحيات.", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# 📋 اختيار القسم وإنشاء التذكرة
# ==============================================================================
class DynamicTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_name: str):
        self.guild_id = guild_id
        self.panel_name = panel_name
        db = load_tickets_db()
        sections = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {}).get("sections", {})
        
        options = []
        if sections:
            for key, data in sections.items():
                label_str = data["label"][:100]
                desc_str = data["description"][:100] if data.get("description") else None
                
                emoji_val = data.get("emoji", "🎫")
                try:
                    if emoji_val.isdigit():
                        emoji_obj = discord.PartialEmoji(name="emoji", id=int(emoji_val))
                    else:
                        emoji_obj = emoji_val
                except:
                    emoji_obj = "🎫"

                options.append(discord.SelectOption(label=label_str, description=desc_str, emoji=emoji_obj, value=key))
        else:
            options = [discord.SelectOption(label="مفيش أقسام متاحة حالياً", value="none")]

        super().__init__(placeholder="📂 اختر القسم المناسب لطلبك...", min_values=1, max_values=1, options=options, custom_id=f"dynamic_select_{panel_name}")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ مفيش أقسام شغالة في البانل ده.", ephemeral=True)
            return
        
        sec_key = self.values[0]
        db = load_tickets_db()
        sec_data = db.get(str(self.guild_id), {}).get("panels", {}).get(self.panel_name, {}).get("sections", {}).get(sec_key, {})
        custom_q = sec_data.get("custom_questions")
        
        if custom_q and len(custom_q) > 0:
            await interaction.response.send_modal(CustomMultiQuestionModal(self.panel_name, sec_key, custom_q))
        else:
            await interaction.response.defer(thinking=True, ephemeral=True)
            await create_user_ticket_execution(interaction, self.panel_name, sec_key, [])


class CustomMultiQuestionModal(discord.ui.Modal):
    def __init__(self, panel_name: str, section_key: str, questions_list: list):
        super().__init__(title="📝 الإجابة على الأسئلة")
        self.panel_name = panel_name
        self.section_key = section_key
        self.inputs_map = {}

        for idx, q_text in enumerate(questions_list[:5]):
            box = discord.ui.TextInput(
                label=f"{q_text[:45]}",
                placeholder="اكتب إجابتك هنا...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True
            )
            self.inputs_map[f"q_{idx}"] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        answers_combined = []
        for q_key, box in self.inputs_map.items():
            answers_combined.append(box.value.strip())
        
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, answers_combined)


# ==============================================================================
# 🎛️ واجهة البانل وزر التحديث
# ==============================================================================
class PanelControlView(discord.ui.View):
    def __init__(self, guild_id: int = 0, panel_name: str = "", is_menu: bool = True):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_name = panel_name
        
        if is_menu and guild_id and panel_name:
            self.add_item(DynamicTicketSelect(guild_id, panel_name))
        elif not is_menu and guild_id and panel_name:
            db = load_tickets_db()
            p_data = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {})
            sections = p_data.get("sections", {})

            for key, data in sections.items():
                emoji_val = data.get("emoji", "🎫")
                try:
                    if emoji_val.isdigit():
                        emoji_obj = discord.PartialEmoji(name="emoji", id=int(emoji_val))
                    else:
                        emoji_obj = emoji_val
                except:
                    emoji_obj = "🎫"

                btn = discord.ui.Button(
                    label=data["label"][:80],
                    style=discord.ButtonStyle.secondary,
                    emoji=emoji_obj,
                    custom_id=f"panel_btn_{panel_name}_{key}"
                )
                
                p_val = panel_name
                k_val = key
                q_list = data.get("custom_questions")

                async def dynamic_button_cb(inter: discord.Interaction, p=p_val, k=k_val, q=q_list):
                    if q and len(q) > 0:
                        await inter.response.send_modal(CustomMultiQuestionModal(p, k, q))
                    else:
                        await inter.response.defer(thinking=True, ephemeral=True)
                        await create_user_ticket_execution(inter, p, k, [])

                btn.callback = dynamic_button_cb
                self.add_item(btn)

    @discord.ui.button(label="تحديث البانل", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="reset_panel_main_btn_v7", row=4)
    async def reset_panel_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        p_data = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {})
        if not p_data:
            embed_err = discord.Embed(title="❌ خطأ", description="البانل ده اتمسح من البيانات.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return
        
        color_int = int(p_data.get("color_hex", "2b2d31").replace("#", ""), 16)
        embed = discord.Embed(
            title=p_data.get("title"),
            description=p_data.get("desc"),
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        if p_data.get("image_url"):
            embed.set_image(url=p_data["image_url"])
        if p_data.get("thumbnail_url"):
            embed.set_thumbnail(url=p_data["thumbnail_url"])
        embed.set_footer(text=f"{self.panel_name}")

        is_m = p_data.get("display_type", "menu") == "menu"
        
        try:
            await interaction.message.edit(embed=embed, view=PanelControlView(interaction.guild.id, self.panel_name, is_m))
            embed_ok = discord.Embed(title="🔄 تم التحديث", description="تم تحديث البانل بنجاح.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok, ephemeral=True)
        except Exception as e:
            embed_ex = discord.Embed(title="❌ خطأ", description=f"حصلت مشكلة: {e}", color=0xFF3333)
            await interaction.response.send_message(embed=embed_ex, ephemeral=True)


async def create_user_ticket_execution(interaction: discord.Interaction, panel_name: str, section_key: str, answers_list: list):
    guild = interaction.guild
    db = load_tickets_db()
    guild_data = db.get(str(guild.id), {})
    
    active_tickets = guild_data.get("active_tickets", {})
    for ch_id, t_info in active_tickets.items():
        if t_info.get("user_id") == interaction.user.id:
            existing_chan = guild.get_channel(int(ch_id))
            if existing_chan:
                try:
                    embed_dup = discord.Embed(title="❌ عندك تذكرة مفتوحة", description=f"عندك تذكرة شغال فيها بالفعل: {existing_chan.mention}\nاقفل القديمة الأول عشان تفتح جديدة.", color=0xFF3333)
                    await interaction.followup.send(embed=embed_dup, ephemeral=True)
                except:
                    pass
                return

    panel_data = guild_data.get("panels", {}).get(panel_name, {})
    section_data = panel_data.get("sections", {}).get(section_key)
    
    if not section_data:
        try:
            embed_no = discord.Embed(title="❌ خطأ", description="القسم ده مش موجود حالياً.", color=0xFF3333)
            await interaction.followup.send(embed=embed_no, ephemeral=True)
        except:
            pass
        return

    section_cat_id = section_data.get("category_id")
    category_id_str = section_cat_id if section_cat_id else panel_data.get("category_id")
    category = guild.get_channel(int(category_id_str)) if category_id_str and category_id_str.isdigit() else None
    
    if not category:
        try:
            if guild.me.guild_permissions.manage_channels:
                category = await guild.create_category("🎫・التذاكر")
            else:
                category = None
        except:
            category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
    }

    support_role_ids = section_data.get("support_role_ids", [])
    support_roles_objs = [guild.get_role(r_id) for r_id in support_role_ids if guild.get_role(r_id)]
    
    for r_obj in support_roles_objs:
        overwrites[r_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    higher_role_id = section_data.get("higher_support_role_id")
    if higher_role_id:
        higher_role_obj = guild.get_role(higher_role_id)
        if higher_role_obj:
            overwrites[higher_role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    closed_count = len(guild_data.get("closed_tickets_archive", []))
    total_ticket_number = len(active_tickets) + closed_count + 1
    channel_name = f"🎫・{total_ticket_number}"
    
    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )
    except Exception as e:
        try:
            embed_err = discord.Embed(title="❌ خطأ", description=f"تأكد من صلاحيات البوت (Manage Channels): {e}", color=0xFF3333)
            await interaction.followup.send(embed=embed_err, ephemeral=True)
        except:
            pass
        return

    if "active_tickets" not in guild_data:
        guild_data["active_tickets"] = {}
    
    current_dt = datetime.datetime.utcnow()
    current_ts = current_dt.timestamp()
    creation_time_str = current_dt.strftime('%A, %B %d, %Y %I:%M %p')
    
    guild_data["active_tickets"][str(ticket_channel.id)] = {
        "user_id": interaction.user.id,
        "panel": panel_name,
        "section": section_data["label"],
        "support_role_ids": support_role_ids,
        "higher_support_role_id": higher_role_id,
        "created_at": creation_time_str,
        "last_activity": current_ts,
        "status": "مفتوحة"
    }
    save_tickets_db(db)

    color_int = int(panel_data.get("color_hex", "2b2d31").replace("#", ""), 16)
    staff_mentions = " | ".join([r.mention for r in support_roles_objs]) if support_roles_objs else "فريق الدعم"

    embed = discord.Embed(color=color_int)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    embed.add_field(name="👤 [ ] : مالك التذكرة", value=f"{interaction.user.mention}\n\u200b", inline=False)
    embed.add_field(name="🛡️ [ ] : مشرفي التذاكر", value=f"{staff_mentions}\n\u200b", inline=False)
    embed.add_field(name="📅 [ ] : تاريخ إنشاء التذكرة", value=f"{creation_time_str}\n\u200b", inline=False)
    embed.add_field(name="🔢 [ ] : رقم التذكرة", value=f"```{total_ticket_number}```\n\u200b", inline=False)
    embed.add_field(name="❓ [ ] : قسم التذكرة", value=f"```{section_data['label']}```\n\u200b", inline=False)

    if section_data.get("custom_questions") and answers_list:
        questions = section_data.get("custom_questions", [])
        q_ans_text = ""
        for idx, ans in enumerate(answers_list):
            q_title = questions[idx] if idx < len(questions) else f"سؤال {idx+1}"
            q_ans_text += f"**{q_title}:** {ans}\n"
        embed.add_field(name="📝 [ ] : الإجابات", value=q_ans_text, inline=False)

    sec_thumb = section_data.get("thumbnail_url")
    panel_thumb = panel_data.get("thumbnail_url")
    final_footer_icon = sec_thumb if sec_thumb else panel_thumb
    
    embed.set_footer(text="نظام إدارة التذاكر", icon_url=final_footer_icon if final_footer_icon else None)

    sec_img = section_data.get("image_url")
    panel_img = panel_data.get("image_url")
    final_img = sec_img if sec_img else panel_img
    if final_img:
        embed.set_image(url=final_img)

    quick_replies_data = section_data.get("quick_replies", [])

    try:
        content_ping = f"{interaction.user.mention} | {staff_mentions}"
        sent_msg = await ticket_channel.send(
            content=content_ping, 
            embed=embed, 
            view=TicketInsideView(guild.id, panel_name, quick_replies_data, higher_role_id)
        )
        await sent_msg.pin()
    except:
        pass

    try:
        embed_suc = discord.Embed(title="✅ تم فتح التذكرة", description=f"تم عمل التذكرة بنجاح: {ticket_channel.mention}", color=0x00FF88)
        await interaction.followup.send(embed=embed_suc, ephemeral=True)
    except:
        pass


# ==============================================================================
# 🎨 ألوان الإيمبد
# ==============================================================================
class EmbedColorChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies

    @discord.ui.button(label="🟢 أخضر", style=discord.ButtonStyle.success, custom_id="color_green_v7")
    async def color_green(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_color_and_finish(interaction, "00FF88")

    @discord.ui.button(label="🔵 أزرق داكن", style=discord.ButtonStyle.primary, custom_id="color_blue_v7")
    async def color_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_color_and_finish(interaction, "2B2D31")

    @discord.ui.button(label="🔴 أحمر", style=discord.ButtonStyle.danger, custom_id="color_red_v7")
    async def color_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_color_and_finish(interaction, "FF3333")

    @discord.ui.button(label="🟡 أصفر", style=discord.ButtonStyle.secondary, custom_id="color_gold_v7")
    async def color_gold(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_color_and_finish(interaction, "FFA500")

    @discord.ui.button(label="🟣 بنفسجي", style=discord.ButtonStyle.secondary, custom_id="color_purple_v7")
    async def color_purple(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_color_and_finish(interaction, "9B59B6")

    async def save_color_and_finish(self, interaction: discord.Interaction, color_hex: str):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        
        guild_data = db.setdefault(guild_id_str, {})
        panels_data = guild_data.setdefault("panels", {})
        panel_data = panels_data.get(self.panel_name, {})
        
        panel_data["color_hex"] = color_hex

        sections_lines = panel_data.pop("temp_sections", [])
        roles_map = panel_data.pop("temp_roles_map", {})
        cats_map = panel_data.pop("temp_cats_map", {})
        thumbs_map = panel_data.pop("temp_thumbs_map", {})
        descs_list = panel_data.pop("temp_descs", []) if self.use_descriptions else []
        questions_map = panel_data.pop("temp_questions_map", {}) if self.use_questions else {}
        single_qr = panel_data.pop("temp_single_quick_replies", []) if self.use_quick_replies else []
        qr_map = panel_data.pop("temp_quick_replies_map", {}) if self.use_quick_replies else {}
        higher_role_data = panel_data.pop("temp_higher_role", None)
        higher_roles_map = panel_data.pop("temp_higher_roles_map", {})
        
        panel_data["has_questions"] = self.use_questions
        panel_data["sections"] = {}

        for idx, sec_name in enumerate(sections_lines):
            key = f"sec_{idx}_{int(datetime.datetime.utcnow().timestamp())}"
            sec_desc = descs_list[idx] if self.use_descriptions and idx < len(descs_list) else None
            sec_roles = roles_map.get(sec_name, [])
            sec_cat = cats_map.get(sec_name)
            sec_thumb = thumbs_map.get(sec_name)
            sec_questions = questions_map.get(sec_name, []) if self.use_questions else []
            sec_qr = single_qr if single_qr else qr_map.get(sec_name, [])
            
            higher_id = higher_role_data if higher_role_data else higher_roles_map.get(sec_name)

            panel_data["sections"][key] = {
                "label": sec_name,
                "description": sec_desc,
                "custom_questions": sec_questions,
                "quick_replies": sec_qr,
                "emoji": "🎫",
                "support_role_ids": sec_roles,
                "higher_support_role_id": higher_id,
                "category_id": sec_cat,
                "thumbnail_url": sec_thumb,
                "color_hex": color_hex,
                "image_url": panel_data.get("image_url")
            }

        panels_data[self.panel_name] = panel_data
        save_tickets_db(db)

        embed_done = discord.Embed(
            title="🎨 تم حفظ البانل",
            description=f"تم حفظ البانل (**{self.panel_name}**).\nاستخدم الأمر `/ticket` عشان تنشره في أي روم.",
            color=int(color_hex, 16)
        )
        await interaction.response.send_message(embed=embed_done, ephemeral=True)


class AskEmbedColorChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies

    @discord.ui.button(label="نعم، حدد لون الإيمبد", style=discord.ButtonStyle.success, emoji="🎨", custom_id="embed_color_yes_v7")
    async def yes_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎨 اختيار اللون", description="اختر اللون المناسب للإيمبد:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed, view=EmbedColorChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies), ephemeral=True)

    @discord.ui.button(label="لا، تخطي باللون الافتراضي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="embed_color_no_v7")
    async def no_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await EmbedColorChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies).save_color_and_finish(interaction, "2B2D31")


# ==============================================================================
# 🛠 إعدادات البانلات وتعديلها
# ==============================================================================
class TicketSetupMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إنشاء بانل جديد", style=discord.ButtonStyle.success, emoji="🚀", custom_id="setup_create_panel_btn_v7")
    async def create_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelInfoModal(guild_id=interaction.guild.id, is_editing=False))

    @discord.ui.button(label="تعديل بانل", style=discord.ButtonStyle.primary, emoji="⚙️", custom_id="setup_edit_panel_btn_v7")
    async def edit_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        panels = db.get(str(interaction.guild.id), {}).get("panels", {})
        if not panels:
            embed_err = discord.Embed(title="⚠️ تنبيه", description="مفيش أي بانلات مضافة حالياً لتعديلها.", color=0xFFA500)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل المراد تعديله...", custom_id="edit_panel_select_v7")
        for name in panels.keys():
            select.add_option(label=name, value=name)

        async def select_cb(inter: discord.Interaction):
            chosen = select.values[0]
            await inter.response.send_message(embed=discord.Embed(title="⚙️ تعديل البانل", description="عاوز تعدل ايه في البانل ده؟", color=0x2B2D31), view=EditPanelOptionsView(chosen), ephemeral=True)

        select.callback = select_cb
        view.add_item(select)
        embed_sel = discord.Embed(title="⚙️ تعديل بانل", description="اختر البانل من القائمة:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_sel, view=view, ephemeral=True)

    @discord.ui.button(label="حذف بانل", style=discord.ButtonStyle.danger, emoji="🗑", custom_id="setup_delete_panel_btn_v7")
    async def delete_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panels = db.get(guild_id_str, {}).get("panels", {})
        if not panels:
            embed_err = discord.Embed(title="⚠️ تنبيه", description="مفيش بانلات لحذفها.", color=0xFFA500)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل لحذفه...", custom_id="delete_panel_select_v7")
        for name in panels.keys():
            select.add_option(label=name, value=name)

        async def del_cb(inter: discord.Interaction):
            chosen = select.values[0]
            db[guild_id_str]["panels"].pop(chosen, None)
            save_tickets_db(db)
            embed_del = discord.Embed(title="🗑️ تم الحذف", description=f"تم حذف البانل **{chosen}** بنجاح.", color=0x00FF88)
            await inter.response.send_message(embed=embed_del, ephemeral=True)

        select.callback = del_cb
        view.add_item(select)
        embed_del_sel = discord.Embed(title="🗑 حذف بانل", description="اختر البانل اللي عاوز تمسحه:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_del_sel, view=view, ephemeral=True)

    @discord.ui.button(label="روم اللوج", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="setup_log_channel_btn_v7")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LogChannelModal())

    @discord.ui.button(label="إحصائيات المشرفين", style=discord.ButtonStyle.primary, emoji="📊", custom_id="setup_staff_stats_btn_v7")
    async def show_staff_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        staff_stats = guild_data.get("staff_stats", {})
        
        embed = discord.Embed(
            title="📊 إحصائيات الدعم الفني",
            description="ترتيب وأداء المشرفين حسب إجمالي النجوم/النقاط المجمعة:\n",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        
        if not staff_stats:
            embed.add_field(name="مفيش بيانات", value="مفيش تذاكر اتستلمت أو اتقيمت لحد دلوقتي.", inline=False)
        else:
            sorted_staff = sorted(
                staff_stats.items(),
                key=lambda x: x[1].get("total_stars", 0),
                reverse=True
            )
            
            medals = ["🥇", "🥈", "🥉"]
            for idx, (s_id, data) in enumerate(sorted_staff):
                member = interaction.guild.get_member(int(s_id))
                m_name = member.mention if member else f"<@{s_id}>"
                claimed = data.get("claimed", 0)
                total_stars = data.get("total_stars", 0)
                
                prefix_medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
                
                embed.add_field(
                    name=f"{prefix_medal} المشرف: {m_name}",
                    value=f"💼 التذاكر المستلمة: `{claimed}`\n⭐ مجموع النقاط/النجوم: `{total_stars}`\n\u200b",
                    inline=False
                )
                
        embed.set_footer(text="نظام إدارة التذاكر")
        await interaction.response.send_message(embed=embed, ephemeral=False)


class EditPanelOptionsView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="تعديل الوصف والمعلومات", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="edit_panel_info_v7")
    async def edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelInfoModal(guild_id=interaction.guild.id, is_editing=True, panel_name=self.panel_name))

    @discord.ui.button(label="تعديل الأقسام والأسئلة", style=discord.ButtonStyle.success, emoji="📝", custom_id="edit_panel_secs_v7")
    async def edit_sections(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        guild_data = db.setdefault(guild_id_str, {})
        panels_data = guild_data.setdefault("panels", {})
        p_data = panels_data.get(self.panel_name, {})
        
        sections = p_data.get("sections", {})
        sec_names = [d["label"] for d in sections.values()]
        
        p_data["temp_sections"] = sec_names
        save_tickets_db(db)
        
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name, is_editing=True))


class LogChannelModal(discord.ui.Modal, title="📋 تحديد روم اللوج"):
    channel_id_box = discord.ui.TextInput(
        label="أيدي الروم (Channel ID)",
        placeholder="اكتب أيدي الروم هنا...",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        ch_id_text = self.channel_id_box.value.strip()
        if not ch_id_text.isdigit():
            embed = discord.Embed(title="❌ خطأ", description="يرجى كتابة أيدي روم صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        guild_data = db.setdefault(guild_id_str, {})
        
        guild_data["log_channel_id"] = ch_id_text
        save_tickets_db(db)

        embed = discord.Embed(title="✅ تم الحفظ", description=f"تم تحديد روم اللوج: <#{ch_id_text}>", color=0x00FF88)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PanelInfoModal(discord.ui.Modal):
    def __init__(self, guild_id: int, is_editing=False, panel_name=""):
        super().__init__(title="⚙️ إعدادات البانل")
        self.is_editing = is_editing
        self.old_panel_name = panel_name

        db = load_tickets_db() if is_editing else {}
        p_data = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {}) if is_editing else {}

        self.name_box = discord.ui.TextInput(label="اسم البانل", default=panel_name if is_editing else "", max_length=50, required=True)
        self.desc_box = discord.ui.TextInput(label="الوصف (بدون أي إضافات أوتوماتيكية)", default=p_data.get("desc", "محتوى البانل الخاص بك..."), style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.images_box = discord.ui.TextInput(label="روابط الصور (صورة البانل | الثامبنيل)", default=f"{p_data.get('image_url', '')} | {p_data.get('thumbnail_url', '')}".strip(" |"), placeholder="رابط الصورة الكبيرة | رابط الثامبنيل (اختياري)", required=False)
        self.footer_info_box = discord.ui.TextInput(label="نص التذييل (Footer)", default=p_data.get("custom_footer_info", ""), placeholder="معلومات إضافية تحت في الإيمبد", required=False)
        self.category_box = discord.ui.TextInput(label="أيدي الكاتيجوري (Category ID)", default=p_data.get("category_id", ""), max_length=30, required=True)

        self.add_item(self.name_box)
        self.add_item(self.desc_box)
        self.add_item(self.images_box)
        self.add_item(self.footer_info_box)
        self.add_item(self.category_box)

    async def on_submit(self, interaction: discord.Interaction):
        p_name = self.name_box.value.strip()
        cat_id_text = self.category_box.value.strip()
        
        if not cat_id_text.isdigit():
            embed = discord.Embed(title="❌ خطأ", description="أيدي الكاتيجوري غير صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        img_raw = self.images_box.value.strip()
        img_url = None
        thumb_url = None
        if "|" in img_raw:
            parts = img_raw.split("|", 1)
            img_url = parts[0].strip() or None
            thumb_url = parts[1].strip() or None
        elif img_raw.startswith("http"):
            img_url = img_raw

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        
        guild_data = db.setdefault(guild_id_str, {})
        guild_data.setdefault("active_tickets", {})
        guild_data.setdefault("closed_tickets_archive", [])
        guild_data.setdefault("staff_stats", {})
        panels_dict = guild_data.setdefault("panels", {})

        if self.is_editing and self.old_panel_name != p_name:
            panels_dict.pop(self.old_panel_name, None)

        if p_name not in panels_dict:
            panels_dict[p_name] = {"sections": {}}

        panels_dict[p_name].update({
            "title": "🎫 الدعم الفني والمساعدة",
            "desc": self.desc_box.value,
            "image_url": img_url,
            "thumbnail_url": thumb_url,
            "custom_footer_info": self.footer_info_box.value if self.footer_info_box.value else "",
            "category_id": cat_id_text,
            "color_hex": "2b2d31"
        })
        save_tickets_db(db)

        embed = discord.Embed(title="✅ تم حفظ معلومات البانل", description=f"تم حفظ بيانات **{p_name}**.\nاختر طريقة عرض الأقسام:", color=0x00FF88)
        await interaction.response.send_message(
            embed=embed,
            view=PanelDisplayTypeView(p_name),
            ephemeral=True
        )


class PanelDisplayTypeView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="قائمة منسدلة", style=discord.ButtonStyle.primary, emoji="📂", custom_id="disp_menu_v7")
    async def select_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["display_type"] = "menu"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))

    @discord.ui.button(label="أزرار", style=discord.ButtonStyle.success, emoji="🔘", custom_id="disp_buttons_v7")
    async def select_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["display_type"] = "buttons"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))


class SectionsConfigModal(discord.ui.Modal, title="📝 كتابة أسماء الأقسام"):
    def __init__(self, panel_name: str, is_editing: bool = False):
        super().__init__()
        self.panel_name = panel_name
        self.is_editing = is_editing

        self.sections_box = discord.ui.TextInput(
            label="أسماء الأقسام (كل قسم في سطر)",
            default="دعم فني\nاستفسارات\nتقديم إدارة",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.sections_box)

    async def on_submit(self, interaction: discord.Interaction):
        sections_lines = [s.strip() for s in self.sections_box.value.split("\n") if s.strip()]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        
        panel_data["temp_sections"] = sections_lines
        save_tickets_db(db)

        embed = discord.Embed(title="❓ رتب الدعم", description="عاوز تضيف رتب دعم معينة لكل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskSupportRolesChoiceView(self.panel_name),
            ephemeral=True
        )


class AskSupportRolesChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، حدد الرتب", style=discord.ButtonStyle.success, emoji="✅", custom_id="ask_support_yes_v7")
    async def yes_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsSupportRolesModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭", custom_id="ask_support_no_v7")
    async def no_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        sections = panel_data.get("temp_sections", [])
        panel_data["temp_roles_map"] = {sec: [] for sec in sections}
        save_tickets_db(db)

        embed = discord.Embed(title="❓ كاتيجوري لكل قسم", description="عاوز تخصص كاتيجوري مختلف لكل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskCategoriesChoiceView(self.panel_name),
            ephemeral=True
        )


class DynamicSectionsSupportRolesModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="🛡️ رتب الدعم لكل قسم")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"أيدي رتب قسم: {sec[:25]}",
                placeholder="اكتب أيديهات الرتب (كل أيدي في سطر)...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        roles_map = {}
        for sec, box in self.inputs_map.items():
            lines = [r.strip() for r in box.value.split("\n") if r.strip() and r.strip().isdigit()]
            roles_map[sec] = [int(r) for r in lines]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_roles_map"] = roles_map
        save_tickets_db(db)

        embed = discord.Embed(title="❓ كاتيجوري لكل قسم", description="عاوز تخصص كاتيجوري مختلف لكل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskCategoriesChoiceView(self.panel_name),
            ephemeral=True
        )


class AskCategoriesChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، حدد الكاتيجوري", style=discord.ButtonStyle.success, emoji="✅", custom_id="ask_cat_yes_v7")
    async def yes_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsCategoriesModal(self.panel_name, sections))

    @discord.ui.button(label="لا، استخدم الرئيسي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="ask_cat_no_v7")
    async def no_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        sections = panel_data.get("temp_sections", [])
        panel_data["temp_cats_map"] = {sec: None for sec in sections}
        save_tickets_db(db)

        embed = discord.Embed(title="❓ صور مصغرة (Thumbnails)", description="عاوز تضيف صورة مصغرة (Thumbnail) لكل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskThumbnailsChoiceView(self.panel_name),
            ephemeral=True
        )


class DynamicSectionsCategoriesModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="📂 أيدي الكاتيجوري لكل قسم")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"أيدي كاتيجوري: {sec[:30]}",
                placeholder="اكتب أيدي الكاتيجوري...",
                max_length=30,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        cats_map = {}
        for sec, box in self.inputs_map.items():
            val = box.value.strip()
            cats_map[sec] = val if val.isdigit() else None

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_cats_map"] = cats_map
        save_tickets_db(db)

        embed = discord.Embed(title="❓ صور مصغرة (Thumbnails)", description="عاوز تضيف صورة مصغرة (Thumbnail) لكل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskThumbnailsChoiceView(self.panel_name),
            ephemeral=True
        )


class AskThumbnailsChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، ضيف صور", style=discord.ButtonStyle.success, emoji="🖼️", custom_id="ask_thumb_yes_v7")
    async def yes_thumb(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsThumbnailsModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="ask_thumb_no_v7")
    async def no_thumb(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        sections = panel_data.get("temp_sections", [])
        panel_data["temp_thumbs_map"] = {sec: None for sec in sections}
        save_tickets_db(db)

        embed = discord.Embed(title="❓ وصف الأقسام", description="عاوز تحط وصف مخصص يظهر تحت اسم كل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskDescriptionChoiceView(self.panel_name),
            ephemeral=True
        )


class DynamicSectionsThumbnailsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="🖼️ روابط الصور المصغرة")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"صورة قسم: {sec[:30]}",
                placeholder="حط رابط الصورة هنا...",
                max_length=300,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        thumbs_map = {}
        for sec, box in self.inputs_map.items():
            thumbs_map[sec] = box.value.strip()

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_thumbs_map"] = thumbs_map
        save_tickets_db(db)

        embed = discord.Embed(title="❓ وصف الأقسام", description="عاوز تحط وصف مخصص يظهر تحت اسم كل قسم؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskDescriptionChoiceView(self.panel_name),
            ephemeral=True
        )


class AskDescriptionChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، ضيف وصف", style=discord.ButtonStyle.success, emoji="✅", custom_id="ask_desc_yes_v7")
    async def yes_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsDescriptionsModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="ask_desc_no_v7")
    async def no_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        sections = panel_data.get("temp_sections", [])
        panel_data["temp_descs"] = [None for _ in sections]
        save_tickets_db(db)

        embed = discord.Embed(title="❓ أسئلة التذكرة", description="عاوز تعمل أسئلة تظهر للعضو لما يفتح التذكرة؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskCustomQuestionsChoiceView(self.panel_name, use_descriptions=False),
            ephemeral=True
        )


class DynamicSectionsDescriptionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="✍️ وصف الأقسام")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"وصف: {sec[:35]}",
                placeholder=f"اكتب الوصف بخصوص ({sec})...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        descs_list = []
        for sec, box in self.inputs_map.items():
            descs_list.append(box.value.strip())

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_descs"] = descs_list
        save_tickets_db(db)

        embed = discord.Embed(title="❓ أسئلة التذكرة", description="عاوز تعمل أسئلة تظهر للعضو لما يفتح التذكرة؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskCustomQuestionsChoiceView(self.panel_name, use_descriptions=True),
            ephemeral=True
        )


class AskCustomQuestionsChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions

    @discord.ui.button(label="نعم، ضيف أسئلة", style=discord.ButtonStyle.success, emoji="✅", custom_id="ask_q_yes_v7")
    async def yes_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="❓ نظام الأسئلة", description="حدد طريقة إضافة الأسئلة:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed, view=QuestionModeChoiceView(self.panel_name, self.use_descriptions), ephemeral=True)

    @discord.ui.button(label="لا، بدون أسئلة", style=discord.ButtonStyle.secondary, emoji="⏭", custom_id="ask_q_no_v7")
    async def no_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        panel_data["temp_questions_map"] = {}
        save_tickets_db(db)

        embed = discord.Embed(title="⚡ الردود السريعة", description="عاوز تعمل ردود سريعة جاهزة للمشرفين يختاروا منها؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskQuickRepliesChoiceView(self.panel_name, use_descriptions=self.use_descriptions, use_questions=False),
            ephemeral=True
        )


class QuestionModeChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions

    @discord.ui.button(label="سؤال واحد لكل قسم", style=discord.ButtonStyle.primary, emoji="📌", custom_id="q_mode_single_v7")
    async def single_q(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsSingleQuestionModal(self.panel_name, self.use_descriptions, sections))

    @discord.ui.button(label="أكثر من سؤال لكل قسم", style=discord.ButtonStyle.success, emoji="📋", custom_id="q_mode_multi_v7")
    async def multi_q(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsQuestionsModal(self.panel_name, self.use_descriptions, sections))


class DynamicSectionsSingleQuestionModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, sections: list):
        super().__init__(title="📌 سؤال واحد لكل قسم")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.questions_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"سؤال قسم: {sec[:35]}",
                placeholder=f"اكتب السؤال هنا...",
                style=discord.TextStyle.short,
                max_length=200,
                required=True
            )
            self.questions_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        questions_map_dict = {}
        for sec, box in self.questions_map.items():
            questions_map_dict[sec] = [box.value.strip()]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_questions_map"] = questions_map_dict
        save_tickets_db(db)

        embed = discord.Embed(title="⚡ الردود السريعة", description="عاوز تعمل ردود سريعة جاهزة للمشرفين يختاروا منها؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskQuickRepliesChoiceView(self.panel_name, use_descriptions=self.use_descriptions, use_questions=True),
            ephemeral=True
        )


class DynamicSectionsQuestionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, sections: list):
        super().__init__(title="❓ الأسئلة المتعددة")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.questions_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"أسئلة قسم: {sec[:30]}",
                placeholder="اكتب كل سؤال في سطر جديد...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True
            )
            self.questions_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        questions_map_dict = {}
        for sec, box in self.questions_map.items():
            questions_map_dict[sec] = [q.strip() for q in box.value.split("\n") if q.strip()]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_questions_map"] = questions_map_dict
        save_tickets_db(db)

        embed = discord.Embed(title="⚡ الردود السريعة", description="عاوز تعمل ردود سريعة جاهزة للمشرفين يختاروا منها؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskQuickRepliesChoiceView(self.panel_name, use_descriptions=self.use_descriptions, use_questions=True),
            ephemeral=True
        )


class AskQuickRepliesChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    @discord.ui.button(label="نعم، ضيف ردود سريعة", style=discord.ButtonStyle.success, emoji="✅", custom_id="ask_qr_yes_v7")
    async def yes_qr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="⚡ الردود السريعة", description="حدد طريقة إدخال الردود السريعة:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed, view=QuickRepliesModeChoiceView(self.panel_name, self.use_descriptions, self.use_questions), ephemeral=True)

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="ask_qr_no_v7")
    async def no_qr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="👑 رتبة الإدارة العليا", description="عاوز تخصص رتبة إدارة عليا للتصعيد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskHigherRoleChoiceView(self.panel_name, self.use_descriptions, self.use_questions, use_quick_replies=False),
            ephemeral=True
        )


class QuickRepliesModeChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    @discord.ui.button(label="ردود موحدة لكل الأقسام", style=discord.ButtonStyle.primary, emoji="🌐", custom_id="qr_mode_all_v7")
    async def qr_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SingleQuickRepliesForAllModal(self.panel_name, self.use_descriptions, self.use_questions))

    @discord.ui.button(label="ردود مختلفة لكل قسم", style=discord.ButtonStyle.success, emoji="🛠", custom_id="qr_mode_custom_v7")
    async def qr_custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(CustomQuickRepliesPerSectionModal(self.panel_name, self.use_descriptions, self.use_questions, sections))


class SingleQuickRepliesForAllModal(discord.ui.Modal, title="🌐 ردود سريعة موحدة"):
    qr_box = discord.ui.TextInput(
        label="الردود السريعة (كل رد في سطر)", 
        style=discord.TextStyle.paragraph, 
        placeholder="اكتب كل رد في سطر جديد...\nمثال:\nأهلاً بك، تفضل بطرح مشكلتك.\nمن فضلك انتظر رد الإدارة.", 
        max_length=500, 
        required=True
    )

    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__()
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    async def on_submit(self, interaction: discord.Interaction):
        replies_list = [r.strip() for r in self.qr_box.value.split("\n") if r.strip()]
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_single_quick_replies"] = replies_list
        save_tickets_db(db)

        embed = discord.Embed(title="👑 رتبة الإدارة العليا", description="عاوز تخصص رتبة إدارة عليا للتصعيد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskHigherRoleChoiceView(self.panel_name, self.use_descriptions, self.use_questions, use_quick_replies=True),
            ephemeral=True
        )


class CustomQuickRepliesPerSectionModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, sections: list):
        super().__init__(title="🛠 ردود سريعة مخصصة")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"ردود قسم: {sec[:25]}",
                placeholder=f"اكتب الردود هنا (كل رد في سطر)...",
                style=discord.TextStyle.paragraph,
                max_length=400,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        qr_map = {}
        for sec, box in self.inputs_map.items():
            lines = [l.strip() for l in box.value.split("\n") if l.strip()]
            qr_map[sec] = lines

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})["temp_quick_replies_map"] = qr_map
        save_tickets_db(db)

        embed = discord.Embed(title="👑 رتبة الإدارة العليا", description="عاوز تخصص رتبة إدارة عليا للتصعيد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskHigherRoleChoiceView(self.panel_name, self.use_descriptions, self.use_questions, use_quick_replies=True),
            ephemeral=True
        )


class AskHigherRoleChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies

    @discord.ui.button(label="نعم، ضيف رتبة عليا", style=discord.ButtonStyle.success, emoji="✅", custom_id="higher_yes_v7")
    async def yes_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="👑 رتبة الإدارة العليا", description="حدد طريقة إدخال رتبة الإدارة العليا:", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=HigherRoleTypeChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies),
            ephemeral=True
        )

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="higher_no_v7")
    async def no_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        panel_data["temp_higher_role"] = None
        panel_data["temp_higher_roles_map"] = {}
        save_tickets_db(db)

        embed = discord.Embed(title="🎨 لون الإيمبد", description="عاوز تختار لون مخصص للإيمبد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskEmbedColorChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies),
            ephemeral=True
        )


class HigherRoleTypeChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies

    @discord.ui.button(label="رتبة واحدة للكل", style=discord.ButtonStyle.primary, emoji="⭐", custom_id="higher_type_single_v7")
    async def single_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SingleHigherRoleModal(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies))

    @discord.ui.button(label="رتبة مختلفة لكل قسم", style=discord.ButtonStyle.success, emoji="🛠", custom_id="higher_type_custom_v7")
    async def custom_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(CustomHigherRolesModal(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies, sections))


class SingleHigherRoleModal(discord.ui.Modal, title="⭐ رتبة إدارية موحدة"):
    role_box = discord.ui.TextInput(label="أيدي الرتبة", placeholder="اكتب أيدي الرتبة هنا...", max_length=30, required=True)

    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool):
        super().__init__()
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies

    async def on_submit(self, interaction: discord.Interaction):
        r_text = self.role_box.value.strip()
        if not r_text.isdigit():
            embed_err = discord.Embed(title="❌ خطأ", description="يرجى كتابة أيدي رتبة صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed_err, ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        panel_data["temp_higher_role"] = int(r_text)
        save_tickets_db(db)

        embed = discord.Embed(title="🎨 لون الإيمبد", description="عاوز تختار لون مخصص للإيمبد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskEmbedColorChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies),
            ephemeral=True
        )


class CustomHigherRolesModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, use_quick_replies: bool, sections: list):
        super().__init__(title="🛠 رتبة عليا لكل قسم")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.use_quick_replies = use_quick_replies
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"رتبة عليا لـ: {sec[:25]}",
                placeholder="اكتب أيدي الرتبة (أو سيبها فاضية)...",
                max_length=30,
                required=False
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        map_higher = {}
        for sec, box in self.inputs_map.items():
            val = box.value.strip()
            if val.isdigit():
                map_higher[sec] = int(val)
            else:
                map_higher[sec] = None

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db.setdefault(guild_id_str, {}).setdefault("panels", {}).setdefault(self.panel_name, {})
        panel_data["temp_higher_roles_map"] = map_higher
        save_tickets_db(db)

        embed = discord.Embed(title="🎨 لون الإيمبد", description="عاوز تختار لون مخصص للإيمبد؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskEmbedColorChoiceView(self.panel_name, self.use_descriptions, self.use_questions, self.use_quick_replies),
            ephemeral=True
        )


# ==============================================================================
# 🎯 إرسال البانل بأمر /ticket
# ==============================================================================
class TicketPublishSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        db = load_tickets_db()
        panels = db.get(str(guild_id), {}).get("panels", {})
        
        select = discord.ui.Select(placeholder="اختر البانل لإرساله هنا...", custom_id="select_panel_to_publish_v7")
        if panels:
            for p_name in panels.keys():
                select.add_option(label=p_name, description=f"بانل: {p_name}", emoji="🎫", value=p_name)
        else:
            select.add_option(label="مفيش بانلات جاهزة", value="none")

        async def select_callback(interaction: discord.Interaction):
            chosen = select.values[0]
            if chosen == "none":
                await interaction.response.send_message("❌ مفيش بانلات جاهزة للإرسال.", ephemeral=True)
                return

            db_inner = load_tickets_db()
            p_data = db_inner.get(str(interaction.guild.id), {}).get("panels", {}).get(chosen, {})
            if not p_data:
                await interaction.response.send_message("❌ البانل ده مش موجود.", ephemeral=True)
                return

            color_int = int(p_data.get("color_hex", "2b2d31").replace("#", ""), 16)
            embed = discord.Embed(
                title=p_data.get("title"),
                description=p_data.get("desc"),
                color=color_int,
                timestamp=datetime.datetime.utcnow()
            )
            if p_data.get("image_url"):
                embed.set_image(url=p_data["image_url"])
            if p_data.get("thumbnail_url"):
                embed.set_thumbnail(url=p_data["thumbnail_url"])
            embed.set_footer(text=f"{chosen}")

            is_m = p_data.get("display_type", "menu") == "menu"
            view = PanelControlView(interaction.guild.id, chosen, is_m)

            try:
                await interaction.channel.send(embed=embed, view=view)
                await interaction.response.send_message(f"✅ تم إرسال البانل **{chosen}** بنجاح.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ حصلت مشكلة أثناء إرسال البانل: {e}", ephemeral=True)

        select.callback = select_callback
        self.add_item(select)


class ZiuoUltimateTicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketSetupMainView())
        self.bot.add_view(CloseConfirmationView())
        self.bot.add_view(TicketRatingView())
        self.bot.add_view(TicketInsideView())
        self.bot.add_view(PanelControlView())

    @app_commands.command(name="setup", description="لوحة إعدادات وإدارة التذاكر")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ لوحة إعدادات التذاكر",
            description="اختر من الأزرار التالية لإنشاء أو إدارة البانلات:",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=True)

    @app_commands.command(name="ticket", description="إرسال بانل تذاكر للروم")
    @app_commands.checks.has_permissions(administrator=True)
    async def publish_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 إرسال بانل التذاكر",
            description="اختر البانل اللي حابب تنشره في الروم دي:",
            color=0x2B2D31
        )
        await interaction.response.send_message(embed=embed, view=TicketPublishSelectView(interaction.guild.id), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
