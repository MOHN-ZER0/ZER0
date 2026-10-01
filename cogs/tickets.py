import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
import io

TICKETS_DB_FILE = "ziuo_ultimate_tickets_database.json"

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
# 🌟 نظام التقييم والحذف السريع (Rating View)
# ==============================================================================
class TicketRatingView(discord.ui.View):
    def __init__(self, ticket_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.danger, custom_id="rate_1")
    async def rate_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 1)

    @discord.ui.button(label="⭐⭐ 2", style=discord.ButtonStyle.danger, custom_id="rate_2")
    async def rate_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 2)

    @discord.ui.button(label="⭐⭐⭐ 3", style=discord.ButtonStyle.secondary, custom_id="rate_3")
    async def rate_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 3)

    @discord.ui.button(label="⭐⭐⭐⭐ 4", style=discord.ButtonStyle.success, custom_id="rate_4")
    async def rate_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 4)

    @discord.ui.button(label="⭐⭐⭐⭐⭐ 5", style=discord.ButtonStyle.success, custom_id="rate_5")
    async def rate_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating_and_delete(interaction, 5)

    async def handle_rating_and_delete(self, interaction: discord.Interaction, stars: int):
        for child in self.children:
            child.disabled = True
        stars_str = "⭐" * stars
        await interaction.response.edit_message(content=f"❤ ╎ شكراً لتقييمك الرائع ({stars_str})! سيتم إزالة التذكرة وتطهير السجل خلال 3 ثوانٍ...", view=self)
        
        import asyncio
        await asyncio.sleep(3)
        try:
            await self.ticket_channel.delete()
        except:
            pass


# ==============================================================================
# 🔒 واجهة تأكيد الإغلاق (حذف أو فتح)
# ==============================================================================
class CloseConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="حذف التذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="confirm_delete_ticket_btn")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels and not interaction.user.guild_permissions.administrator:
            db = load_tickets_db()
            t_info = db.get(str(interaction.guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id), {})
            if interaction.user.id != t_info.get("user_id"):
                await interaction.response.send_message("❌ ╎ عذراً، لا تمتلك الصلاحية الكافية لحذف هذه التذكرة!", ephemeral=True)
                return

        channel = interaction.channel
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        
        guild_data = db.get(guild_id_str, {})
        if "active_tickets" in guild_data and channel_id_str in guild_data["active_tickets"]:
            ticket_data = guild_data["active_tickets"].pop(channel_id_str)
            ticket_data["status"] = "مغلقة ومحذوفة"
            ticket_data["closed_by"] = interaction.user.id
            ticket_data["closed_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            if "closed_tickets_archive" not in guild_data:
                guild_data["closed_tickets_archive"] = []
            guild_data["closed_tickets_archive"].append(ticket_data)
            save_tickets_db(db)

            messages_history = []
            async for msg in channel.history(limit=500, oldest_first=True):
                time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                messages_history.append(f"[{time_str}] {msg.author.name}: {msg.content}")

            transcript_text = f"=== ZIUO TICKET TRANSCRIPT: {channel.name} ===\n" + "\n".join(messages_history)
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
                        title="📁 ╎ سجل تذكرة أرشيفية مغلقة",
                        color=0xFF3333,
                        timestamp=datetime.datetime.utcnow()
                    )
                    log_embed.add_field(name="🎫 ╎ اسم التذكرة", value=f"`{channel.name}`", inline=True)
                    log_embed.add_field(name="📂 ╎ القسم", value=f"`{ticket_data.get('section')}`", inline=True)
                    log_embed.add_field(name="👤 ╎ صاحب التذكرة", value=f"{creator_obj.mention if creator_obj else 'غير متوفر'}", inline=True)
                    log_embed.add_field(name="💼 ╎ المشرف المسؤول", value=f"{claimer_obj.mention if claimer_obj else 'بدون استلام'}", inline=True)
                    log_embed.add_field(name="🗑️ ╎ حُذِفَت بواسطة", value=f"{closer_obj.mention}", inline=True)
                    log_embed.set_footer(text="Z I UO Ultimate Security & Logging")

                    await log_chan.send(embed=log_embed, file=file)

        await interaction.response.send_message("⭐ ╎ **يرجى تقييم جودة الدعم المقدم من طاقم العمل:**", view=TicketRatingView(channel))

    @discord.ui.button(label="فتح التذكرة", style=discord.ButtonStyle.success, emoji="🔓", custom_id="confirm_unlock_ticket_btn")
    async def unlock_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ ╎ ليس لديك صلاحية فتح التذكرة!", ephemeral=True)
            return

        channel = interaction.channel
        default_role = interaction.guild.default_role
        overwrite = channel.overwrites_for(default_role)
        overwrite.send_messages = True
        await channel.set_permissions(default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 ╎ تم فتح التذكرة وإعادة تفعيل المحادثة بنجاح.")


# ==============================================================================
# ⚡ قائمة الردود السريعة للمشرفين (Quick Replies)
# ==============================================================================
class QuickRepliesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="أهلاً بك، تفضل بطرح مشكلتك بالتفصيل.", emoji="👋", value="r1"),
            discord.SelectOption(label="يرجى الانتظار قليلاً جاري التحقق...", emoji="⏳", value="r2"),
            discord.SelectOption(label="تم حل المشكلة، هل تحتاج لأي مساعدة أخرى؟", emoji="✅", value="r3"),
            discord.SelectOption(label="يرجى عدم الإشارة المتكررة لطاقم الإدارة.", emoji="⚠️", value="r4")
        ]
        super().__init__(placeholder="⚡ ╎ الردود السريعة المتاحة للمشرفين...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        mapping = {
            "r1": "👋 ╎ أهلاً بك، تفضل بطرح مشكلتك بالتفصيل وسيقوم فريق الدعم بمساعدتك فوراً.",
            "r2": "⏳ ╎ يرجى الانتظار قليلاً جاري فحص المشكلة والتحقق منها.",
            "r3": "✅ ╎ تم حل المشكلة بنجاح، هل تحتاج لأي مساعدة إضافية قبل إغلاق التذكرة؟",
            "r4": "⚠ ╎ يرجى تجنب الإشارة المتكررة لطاقم الإدارة لكي نتمكن من خدمة الجميع بنظام."
        }
        text = mapping.get(self.values[0], "مرحباً بك.")
        await interaction.channel.send(text)
        await interaction.response.send_message("✅ ╎ تم إرسال الرد السريع.", ephemeral=True)


# ==============================================================================
# 🎛️ واجهات تحكم التذاكر الداخلية (داخل الروم)
# ==============================================================================
class TicketInsideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(QuickRepliesSelect())

    @discord.ui.button(label="استلام", style=discord.ButtonStyle.primary, emoji="💼", custom_id="claim_ticket_v7_btn", row=1)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        guild_data = db.get(guild_id_str, {})
        active_tickets = guild_data.get("active_tickets", {})
        
        if channel_id_str not in active_tickets:
            await interaction.response.send_message("❌ ╎ هذه القناة ليست تذكرة نشطة في النظام!", ephemeral=True)
            return

        ticket_info = active_tickets[channel_id_str]
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        is_staff = interaction.user.guild_permissions.administrator
        if not is_staff and support_role_ids:
            if any(role.id in support_role_ids for role in interaction.user.roles):
                is_staff = True

        if not is_staff:
            await interaction.response.send_message("🛡️ ╎ عذراً، هذه الصلاحية مخصصة لفريق الدعم الفني فقط!", ephemeral=True)
            return

        old_claimer_id = ticket_info.get("claimed_by")
        ticket_info["claimed_by"] = interaction.user.id
        ticket_info["last_activity"] = datetime.datetime.utcnow().timestamp()
        save_tickets_db(db)

        await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)
        
        if old_claimer_id and old_claimer_id != interaction.user.id:
            old_claimer_obj = interaction.guild.get_member(old_claimer_id)
            old_mention = old_claimer_obj.mention if old_claimer_obj else f"<@{old_claimer_id}>"
            await interaction.response.send_message(f"🔄 ╎ تم تغيير مستلم التذكرة من {old_mention} إلى {interaction.user.mention}")
        else:
            embed = discord.Embed(
                title="💼 ╎ تم استلام التذكرة بنجاح",
                description=f"✦ **المشرف المسؤول عن المتابعة:** {interaction.user.mention}",
                color=0x00FF88,
                timestamp=datetime.datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="add_member_ticket_btn_v7", row=2)
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddMemberModal())

    @discord.ui.button(label="تنبيه ذكي", style=discord.ButtonStyle.success, emoji="🔔", custom_id="smart_ping_ticket_btn_v7", row=2)
    async def smart_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        
        if not ticket_info:
            await interaction.response.send_message("❌ ╎ خطأ في قراءة بيانات التذكرة.", ephemeral=True)
            return

        creator_id = ticket_info.get("user_id")
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        if interaction.user.id == creator_id:
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "فريق الدعم الفني"
            await interaction.channel.send(f"🔔 ╎ **تنبيه من صاحب التذكرة {interaction.user.mention}:** يرجى من {mentions} الرد على التذكرة في أقرب وقت!")
            await interaction.response.send_message("✅ ╎ تم إرسال التنبيه لطاقم الدعم.", ephemeral=True)
        else:
            creator_obj = interaction.guild.get_member(creator_id)
            creator_mention = creator_obj.mention if creator_obj else f"<@{creator_id}>"
            await interaction.channel.send(f"🔔 ╎ **تنبيه من إدارة السيرفر إلى {creator_mention}:** يرجى الرد على التذكرة لاستكمال الإجراءات.")
            await interaction.response.send_message("✅ ╎ تم تنبيه العضو بنجاح.", ephemeral=True)

    @discord.ui.button(label="طلب مسؤول أعلى", style=discord.ButtonStyle.primary, emoji="👑", custom_id="escalate_ticket_btn", row=2)
    async def escalate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        support_role_ids = ticket_info.get("support_role_ids", [])
        mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "الإدارة العليا"
        
        await interaction.channel.send(f"👑 ╎ **تصعيد عاجل:** قام {interaction.user.mention} بطلب تدخل مسؤول أعلى أو الإدارة (`{mentions}`). يرجى التفقد الفوري!")
        await interaction.response.send_message("✅ ╎ تم إرسال طلب التصعيد للإدارة بنجاح.", ephemeral=True)

    @discord.ui.button(label="إعادة تعيين", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="reset_categories_btn_v7", row=3)
    async def reset_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔄 ╎ تم تحديث ومزامنة إعدادات وفئات التذكرة الحالية مع قاعدة البيانات المركزية بنجاح.", ephemeral=True)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_v7_btn", row=3)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 ╎ **اختر الإجراء المطلوب لتنفيذه على التذكرة:**", view=CloseConfirmationView(), ephemeral=True)


class AddMemberModal(discord.ui.Modal, title="➕ ╎ إضافة عضو إلى التذكرة"):
    member_box = discord.ui.TextInput(label="أيدي العضو (User ID)", placeholder="اكتب أيدي العضو هنا...", max_length=30, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        member_id_text = self.member_box.value.strip()
        if not member_id_text.isdigit():
            await interaction.response.send_message("❌ ╎ يرجى إدخال أيدي صحيح ومطابق!", ephemeral=True)
            return
        
        member = interaction.guild.get_member(int(member_id_text))
        if not member:
            await interaction.response.send_message("❌ ╎ لم يتم العثور على هذا العضو في السيرفر!", ephemeral=True)
            return

        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ ╎ تم منح العضو {member.mention} صلاحية الوصول وعرض هذه التذكرة.")


# ==============================================================================
# 📋 الأسئلة الاستباقية وإنشاء التذاكر
# ==============================================================================
class TicketReasonModal(discord.ui.Modal, title="🎫 ╎ تفاصيل طلب التذكرة"):
    problem_box = discord.ui.TextInput(
        label="اشرح مشكلتك أو طلبك باختصار شديد",
        placeholder="اكتب تفاصيل طلبك هنا...",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True
    )

    def __init__(self, panel_name: str, section_key: str):
        super().__init__()
        self.panel_name = panel_name
        self.section_key = section_key

    async def on_submit(self, interaction: discord.Interaction):
        reason_text = self.problem_box.value
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, reason_text)


class DynamicTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_name: str):
        self.guild_id = guild_id
        self.panel_name = panel_name
        db = load_tickets_db()
        sections = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {}).get("sections", {})
        
        options = [
            discord.SelectOption(label=data["label"], description=data["description"][:100], emoji=data.get("emoji", "🎫"), value=key)
            for key, data in sections.items()
        ] if sections else [discord.SelectOption(label="لا توجد أقسام متاحة", value="none")]

        super().__init__(placeholder=f"📂 ✦ [ اختر قسم التذكرة المناسب لطلبك ]", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ ╎ لا توجد أقسام مفعلة حالياً في هذا البانل!", ephemeral=True)
            return
        await interaction.response.send_modal(TicketReasonModal(self.panel_name, self.values[0]))


class DynamicTicketButtonsView(discord.ui.View):
    def __init__(self, guild_id: int, panel_name: str):
        super().__init__(timeout=None)
        db = load_tickets_db()
        sections = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {}).get("sections", {})
        
        for key, data in sections.items():
            btn = discord.ui.Button(label=data["label"], style=discord.ButtonStyle.secondary, emoji=data.get("emoji", "🎫"))
            btn.callback = self.make_callback(panel_name, key)
            self.add_item(btn)

    def make_callback(self, panel_name, section_key):
        async def cb(interaction: discord.Interaction):
            await interaction.response.send_modal(TicketReasonModal(panel_name, section_key))
        return cb


async def create_user_ticket_execution(interaction: discord.Interaction, panel_name: str, section_key: str, reason_text: str):
    guild = interaction.guild
    db = load_tickets_db()
    guild_data = db.get(str(guild.id), {})
    
    active_tickets = guild_data.get("active_tickets", {})
    for ch_id, t_info in active_tickets.items():
        if t_info.get("user_id") == interaction.user.id:
            existing_chan = guild.get_channel(int(ch_id))
            if existing_chan:
                await interaction.followup.send(f"❌ ╎ عذراً يا فنان، لديك تذكرة مفتوحة بالفعل ولا يمكنك فتح أكثر من تذكرة في نفس الوقت: {existing_chan.mention}", ephemeral=True)
                return

    panel_data = guild_data.get("panels", {}).get(panel_name, {})
    section_data = panel_data.get("sections", {}).get(section_key)
    
    if not section_data:
        await interaction.followup.send("❌ ╎ عذراً، هذا القسم غير موجود أو تم حذفه.", ephemeral=True)
        return

    category_id_str = panel_data.get("category_id")
    category = guild.get_channel(int(category_id_str)) if category_id_str and category_id_str.isdigit() else None
    if not category:
        category = await guild.create_category("🎫 ╎ TICKETS ARCHIVE")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
    }

    support_role_ids = section_data.get("support_role_ids", [])
    support_roles_objs = [guild.get_role(r_id) for r_id in support_role_ids if guild.get_role(r_id)]
    
    for r_obj in support_roles_objs:
        overwrites[r_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    closed_count = len(guild_data.get("closed_tickets_archive", []))
    total_ticket_number = len(active_tickets) + closed_count + 1
    channel_name = f"🎫・{total_ticket_number}"
    
    ticket_channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites
    )

    if "active_tickets" not in guild_data:
        guild_data["active_tickets"] = {}
    
    current_ts = datetime.datetime.utcnow().timestamp()
    creation_time_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    guild_data["active_tickets"][str(ticket_channel.id)] = {
        "user_id": interaction.user.id,
        "panel": panel_name,
        "section": section_data["label"],
        "support_role_ids": support_role_ids,
        "created_at": creation_time_str,
        "last_activity": current_ts,
        "status": "مفتوحة"
    }
    save_tickets_db(db)

    color_int = int(section_data.get("color_hex", "2b2d31").replace("#", ""), 16)
    staff_mentions = " ".join([r.mention for r in support_roles_objs]) if support_roles_objs else "فريق الإدارة والدعم"

    embed = discord.Embed(
        title=f"🎫 ╎ مركز المساعدة والدعم الفني ✦ [{section_data['label']}]",
        description=f"أهلاً بك يا {interaction.user.mention} في قسم **{section_data['label']}**.",
        color=color_int,
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(name="🔢 ╎ رقم التذكرة", value=f"`{total_ticket_number}`", inline=True)
    embed.add_field(name="📂 ╎ قسم التذكرة", value=f"`{section_data['label']}`", inline=True)
    embed.add_field(name="📝 ╎ تفاصيل المشكلة", value=f"```{reason_text}```", inline=False)
    embed.add_field(name="🛡️ ╎ طاقم الدعم المختص", value=f"{staff_mentions}", inline=False)

    if section_data.get("image_url"):
        embed.set_image(url=section_data["image_url"])
        
    embed.set_footer(text=f"Z I UO Community ✦ Ticket ID: {ticket_channel.id}")

    sent_msg = await ticket_channel.send(
        content=f"🔔 ╎ تنبيه للطاقم: {interaction.user.mention} {staff_mentions}", 
        embed=embed, 
        view=TicketInsideView()
    )
    try:
        await sent_msg.pin()
    except:
        pass

    await interaction.followup.send(f"✅ ╎ تم إنشاء تذكرتك بنجاح بالرقم التسلسلي داخل الروم: {ticket_channel.mention}", ephemeral=True)


# ==============================================================================
# 🛠️ لوحة التحكم والإعدادات المركزية
# ==============================================================================
class TicketSetupMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إنشاء بانل جديد", style=discord.ButtonStyle.success, emoji="🚀", custom_id="setup_create_panel_btn_v7")
    async def create_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelInfoModal(is_editing=False))

    @discord.ui.button(label="تعديل بانل موجود", style=discord.ButtonStyle.primary, emoji="⚙️", custom_id="setup_edit_panel_btn_v7")
    async def edit_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        panels = db.get(str(interaction.guild.id), {}).get("panels", {})
        if not panels:
            await interaction.response.send_message("⚠️ ╎ لا توجد أي بانلات تذاكر مسجلة لتعديلها.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل الذي تريد تعديله...")
        for name in panels.keys():
            select.add_option(label=name, value=name)

        async def select_cb(inter: discord.Interaction):
            chosen = select.values[0]
            await inter.response.send_modal(PanelInfoModal(is_editing=True, panel_name=chosen))

        select.callback = select_cb
        view.add_item(select)
        await interaction.response.send_message("⚙️ ╎ اختر البانل المراد تعديله من القائمة أدناه:", view=view, ephemeral=True)

    @discord.ui.button(label="حذف بانل تذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="setup_delete_panel_btn_v7")
    async def delete_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panels = db.get(guild_id_str, {}).get("panels", {})
        if not panels:
            await interaction.response.send_message("⚠ ╎ لا توجد بانلات تذاكر لحذفها.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل المراد حذفه...")
        for name in panels.keys():
            select.add_option(label=name, value=name)

        async def del_cb(inter: discord.Interaction):
            chosen = select.values[0]
            db[guild_id_str]["panels"].pop(chosen, None)
            save_tickets_db(db)
            await inter.response.send_message(f"🗑️ ╎ تم حذف البانل **{chosen}** بنجاح تام!", ephemeral=True)

        select.callback = del_cb
        view.add_item(select)
        await interaction.response.send_message("🗑️ ╎ اختر البانل المراد حذفه:", view=view, ephemeral=True)

    @discord.ui.button(label="تحديد روم اللوج", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="setup_log_channel_btn_v7")
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LogChannelModal())

    @discord.ui.button(label="الإحصائيات", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="setup_stats_btn_v7")
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        active = guild_data.get("active_tickets", {})
        closed = guild_data.get("closed_tickets_archive", [])

        embed = discord.Embed(
            title="📊 ╎ إحصائيات نظام التذاكر المتقدم",
            description="✦ نظرة عامة وشاملة على حالة التذاكر في السيرفر:",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="🟢 ╎ التذاكر المفتوحة حالياً", value=f"`{len(active)}` تذكرة", inline=True)
        embed.add_field(name="📁 ╎ التذاكر المغلقة والأرشيف", value=f"`{len(closed)}` تذكرة", inline=True)
        embed.set_footer(text="Z I UO Statistics System")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LogChannelModal(discord.ui.Modal, title="📋 ╎ إعداد روم اللوج (Ticket Logs)"):
    channel_id_box = discord.ui.TextInput(
        label="أيدي روم اللوج (Channel ID)",
        placeholder="اكتب أيدي الروم هنا...",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        ch_id_text = self.channel_id_box.value.strip()
        if not ch_id_text.isdigit():
            await interaction.response.send_message("❌ ╎ يرجى إدخال أيدي صحيح ومطابق لروم اللوج!", ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in db:
            db[guild_id_str] = {}
        
        db[guild_id_str]["log_channel_id"] = ch_id_text
        save_tickets_db(db)

        await interaction.response.send_message(f"✅ ╎ تم ربط روم اللوج بنجاح بالروم المخصص: <#{ch_id_text}>", ephemeral=True)


class PanelInfoModal(discord.ui.Modal, title="⚙️ ╎ إعدادات بانل التذاكر الأساسية"):
    def __init__(self, is_editing=False, panel_name=""):
        super().__init__()
        self.is_editing = is_editing
        self.old_panel_name = panel_name

        self.name_box = discord.ui.TextInput(label="اسم البانل الفريد", default=panel_name if is_editing else "", max_length=50, required=True)
        self.desc_box = discord.ui.TextInput(label="وصف البانل", default="اختر القسم المناسب لطلبك...", style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.image_box = discord.ui.TextInput(label="رابط صورة البانل (اختياري)", placeholder="https://...", required=False)
        self.category_box = discord.ui.TextInput(label="أيدي فئة التذاكر (Category ID)", placeholder="123456789...", max_length=30, required=True)

        self.add_item(self.name_box)
        self.add_item(self.desc_box)
        self.add_item(self.image_box)
        self.add_item(self.category_box)

    async def on_submit(self, interaction: discord.Interaction):
        p_name = self.name_box.value.strip()
        cat_id_text = self.category_box.value.strip()
        
        if not cat_id_text.isdigit():
            await interaction.response.send_message("❌ ╎ أيدي فئة التذاكر غير صحيح!", ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in db:
            db[guild_id_str] = {"panels": {}, "active_tickets": {}, "closed_tickets_archive": []}

        if self.is_editing and self.old_panel_name != p_name:
            db[guild_id_str]["panels"].pop(self.old_panel_name, None)

        if p_name not in db[guild_id_str]["panels"]:
            db[guild_id_str]["panels"][p_name] = {"sections": {}}

        db[guild_id_str]["panels"][p_name].update({
            "title": "🎫 ╎ مركز المساعدة والدعم الفني",
            "desc": self.desc_box.value,
            "image_url": self.image_box.value if self.image_box.value else None,
            "category_id": cat_id_text,
            "color_hex": "2b2d31"
        })
        save_tickets_db(db)

        await interaction.response.send_message(
            f"✅ ╎ تم حفظ بيانات البانل **{p_name}** بنجاح!\n✦ اختر الآن طريقة وشكل عرض الأقسام:",
            view=PanelDisplayTypeView(p_name),
            ephemeral=True
        )


class PanelDisplayTypeView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="قائمة منسدلة", style=discord.ButtonStyle.primary, emoji="📂")
    async def select_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["display_type"] = "menu"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))

    @discord.ui.button(label="أزرار تفاعلية", style=discord.ButtonStyle.success, emoji="🔘")
    async def select_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["display_type"] = "buttons"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))


class SectionsConfigModal(discord.ui.Modal, title="📝 ╎ الأقسام ورتب الدعم"):
    def __init__(self, panel_name: str):
        super().__init__()
        self.panel_name = panel_name
        self.sections_box = discord.ui.TextInput(label="أسماء الأقسام (كل قسم في سطر)", placeholder="دعم فني\nاستفسارات عامة", style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.roles_box = discord.ui.TextInput(label="أيدي رتب الدعم (كل أيدي في سطر)", placeholder="123456789...", style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.add_item(self.sections_box)
        self.add_item(self.roles_box)

    async def on_submit(self, interaction: discord.Interaction):
        sections_lines = [s.strip() for s in self.sections_box.value.split("\n") if s.strip()]
        roles_lines = [r.strip() for r in self.roles_box.value.split("\n") if r.strip() and r.strip().isdigit()]
        role_ids = [int(r) for r in roles_lines]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db[guild_id_str]["panels"][self.panel_name]
        panel_data["sections"] = {}

        for idx, sec_name in enumerate(sections_lines):
            key = f"sec_{idx}_{int(datetime.datetime.utcnow().timestamp())}"
            panel_data["sections"][key] = {
                "label": sec_name,
                "description": f"قسم خاص بـ {sec_name}",
                "emoji": "🎫",
                "support_role_ids": role_ids,
                "color_hex": panel_data.get("color_hex", "2b2d31"),
                "image_url": panel_data.get("image_url")
            }

        save_tickets_db(db)
        
        embed = discord.Embed(
            title=panel_data.get("title"),
            description=panel_data.get("desc") + "\n\n____________________________________________________________________\n✦ **اختر القسم المناسب لطلبك من القائمة أدناه:**",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        if panel_data.get("image_url"):
            embed.set_image(url=panel_data["image_url"])
        embed.set_footer(text=f"Z I UO Community ✦ Panel: {self.panel_name}")

        guild_id = interaction.guild.id
        if panel_data.get("display_type", "menu") == "menu":
            view = discord.ui.View(timeout=None)
            view.add_item(DynamicTicketSelect(guild_id, self.panel_name))
        else:
            view = DynamicTicketButtonsView(guild_id, self.panel_name)

        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"🚀 ╎ **تم نشر بانل التذاكر ({self.panel_name}) بنجاح كامل في الروم!**", ephemeral=True)


class ZiuoUltimateTicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_close_tickets_loop.start()

    def cog_unload(self):
        self.auto_close_tickets_loop.cancel()

    @tasks.loop(minutes=5)
    async def auto_close_tickets_loop(self):
        db = load_tickets_db()
        current_time = datetime.datetime.utcnow().timestamp()
        
        for guild_id_str, guild_data in list(db.items()):
            active_tickets = guild_data.get("active_tickets", {})
            if not active_tickets:
                continue
            
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                continue

            for channel_id_str, t_info in list(active_tickets.items()):
                last_act = t_info.get("last_activity", current_time)
                # ساعتين = 7200 ثانية
                if (current_time - last_act) > 7200:
                    channel = guild.get_channel(int(channel_id_str))
                    if channel:
                        try:
                            await channel.send("⚠️ ╎ **تنبيه تلقائي:** مرّت ساعتان بدون أي تفاعل أو نشاط في هذه التذكرة، سيتم إغلاقها تلقائياً للحفاظ على تنظيم السيرفر.")
                            # نقل للأرشيف وإغلاق
                            guild_data["active_tickets"].pop(channel_id_str, None)
                            t_info["status"] = "مغلقة تلقائياً (بعد ساعتين)"
                            t_info["closed_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                            if "closed_tickets_archive" not in guild_data:
                                guild_data["closed_tickets_archive"] = []
                            guild_data["closed_tickets_archive"].append(t_info)
                            save_tickets_db(db)
                            
                            import asyncio
                            await asyncio.sleep(4)
                            await channel.delete()
                        except:
                            pass

    @auto_close_tickets_loop.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="ticket_setup", description="[الإدارة] لوحة التحكم المركزية الشاملة لنظام التذاكر")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ ╎ مركز إدارة ونظام التذاكر المتقدم",
            description=(
                "مرحباً بك في لوحة تحكم التذاكر المركزية الشاملة.\n"
                "من خلال الأزرار أدناه يمكنك إدارة البانرات بالكامل، ربط روم اللوج، ومتابعة الإحصائيات الفورية:\n\n"
                "✦ **إنشاء بانل جديد**\n✦ **تعديل بانل موجود**\n✦ **حذف بانل**\n✦ **تحديد روم اللوج**\n✦ **الإحصائيات**"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Ultimate Tickets Core ✦ 2026")
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=False)


async def setup(bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
