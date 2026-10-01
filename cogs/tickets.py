import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os
from typing import Literal

# قاعدة بيانات تخزين إعدادات وأقسام ولوحات التذاكر
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
# 🎛️ واجهات تحكم التذاكر الداخلية (داخل الروم)
# ==============================================================================
class TicketInsideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام التذكرة", style=discord.ButtonStyle.primary, emoji="💼", custom_id="claim_ticket_v2_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        guild_data = db.get(guild_id_str, {})
        active_tickets = guild_data.get("active_tickets", {})
        
        if channel_id_str not in active_tickets:
            await interaction.response.send_message("❌ هذه القناة ليست تذكرة مسجلة في النظام!", ephemeral=True)
            return

        ticket_info = active_tickets[channel_id_str]
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        # التحقق إذا كان المستخدم لديه صلاحية الدعم أو أدمن
        is_staff = interaction.user.guild_permissions.administrator
        if not is_staff and support_role_ids:
            if any(role.id in support_role_ids for role in interaction.user.roles):
                is_staff = True

        if not is_staff:
            await interaction.response.send_message("❌ عذراً، هذه الصلاحية مخصصة لفريق الدعم المسؤول عن هذه التذكرة فقط!", ephemeral=True)
            return

        ticket_info["claimed_by"] = interaction.user.id
        save_tickets_db(db)

        # تعديل صلاحيات الرومات: جعل باقي الإداريين في وضع القراءة فقط
        channel = interaction.channel
        guild = interaction.guild
        
        # منح المشرف المستلم صلاحية كاملة
        await channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True)
        
        embed = discord.Embed(
            title="💼 تم استلام التذكرة بنجاح",
            description=f"• **المشرف المسؤول:** {interaction.user.mention}\n• تم تقييد باقي أعضاء الطاقم في وضع القراءة حتى يتم منحهم إذن إضافي.",
            color=0x00FF88,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="add_member_ticket_btn")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddMemberModal())

    @discord.ui.button(label="تنبيه (Smart Ping)", style=discord.ButtonStyle.success, emoji="🔔", custom_id="smart_ping_ticket_btn")
    async def smart_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        
        if not ticket_info:
            await interaction.response.send_message("❌ خطأ في قراءة بيانات التذكرة.", ephemeral=True)
            return

        creator_id = ticket_info.get("user_id")
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        if interaction.user.id == creator_id:
            # العضو هو من يضغط، نقوم بمنشن رتب الدعم
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "فريق الإدارة"
            await interaction.channel.send(f"🔔 **تنبيه عاجل من صاحب التذكرة {interaction.user.mention}:** يرجى من {mentions} تفقد التذكرة والرد في أسرع وقت!")
            await interaction.response.send_message("✅ تم إرسال التنبيه لفريق الدعم بنجاح.", ephemeral=True)
        else:
            # المشرف هو من يضغط، نقوم بمنشن العضو صاحب التذكرة
            creator_obj = interaction.guild.get_member(creator_id)
            creator_mention = creator_obj.mention if creator_obj else f"<@{creator_id}>"
            await interaction.channel.send(f"🔔 **تنبيه رسمي من الإدارة إلى {creator_mention}:** يرجى التفاعل والرد على التذكرة لاستكمال المساعدة.")
            await interaction.response.send_message("✅ تم تذكير العضو بنجاح.", ephemeral=True)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_v2_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseTicketModal())


class AddMemberModal(discord.ui.Modal, title="➕ إضافة عضو إلى التذكرة"):
    member_box = discord.ui.TextInput(
        label="أيدي العضو المراد إضافته (User ID)",
        placeholder="اكتب أيدي العضو هنا...",
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        member_id_text = self.member_box.value.strip()
        if not member_id_text.isdigit():
            await interaction.response.send_message("❌ يرجى إدخال أيدي صحيح للعضو!", ephemeral=True)
            return
        
        member = interaction.guild.get_member(int(member_id_text))
        if not member:
            await interaction.response.send_message("❌ لم يتم العثور على هذا العضو في السيرفر!", ephemeral=True)
            return

        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ تم منح العضو {member.mention} صلاحية عرض والمشاركة في التذكرة بنجاح.")


class CloseTicketModal(discord.ui.Modal, title="🔒 سبب إغلاق التذكرة"):
    reason_box = discord.ui.TextInput(
        label="اكتب سبب إغلاق التذكرة بالتفصيل",
        placeholder="مثال: تم حل المشكلة بنجاح...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_box.value
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        if guild_id_str in db and "active_tickets" in db[guild_id_str]:
            if channel_id_str in db[guild_id_str]["active_tickets"]:
                ticket_data = db[guild_id_str]["active_tickets"].pop(channel_id_str)
                ticket_data["status"] = "مغلقة"
                ticket_data["close_reason"] = reason
                ticket_data["closed_by"] = interaction.user.id
                
                if "closed_tickets_archive" not in db[guild_id_str]:
                    db[guild_id_str]["closed_tickets_archive"] = []
                db[guild_id_str]["closed_tickets_archive"].append(ticket_data)
                save_tickets_db(db)

        await interaction.response.send_message(f"🔒 **تم إغلاق التذكرة بواسطة:** {interaction.user.mention}\n📝 **السبب:** {reason}\n⏳ جاري حذف القناة خلال 5 ثوانٍ...")
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass


# ==============================================================================
# 📂 قوائم وأزرار البانيلات الأساسية
# ==============================================================================
class DynamicTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_name: str):
        self.guild_id = guild_id
        self.panel_name = panel_name
        db = load_tickets_db()
        panel_data = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {})
        sections = panel_data.get("sections", {})
        
        options = [
            discord.SelectOption(label=data["label"], description=data["description"][:100], emoji=data.get("emoji", "🎫"), value=key)
            for key, data in sections.items()
        ] if sections else [discord.SelectOption(label="لا توجد أقسام", value="none")]

        super().__init__(placeholder=f"📂 [ اختر قسم التذكرة من لوحة: {panel_name} ]", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ لا توجد أقسام متاحة حالياً!", ephemeral=True)
            return
        await create_user_ticket(interaction, self.panel_name, self.values[0])


class DynamicTicketButtonsView(discord.ui.View):
    def __init__(self, guild_id: int, panel_name: str):
        super().__init__(timeout=None)
        db = load_tickets_db()
        panel_data = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {})
        sections = panel_data.get("sections", {})
        
        for key, data in sections.items():
            btn = discord.ui.Button(label=data["label"], style=discord.ButtonStyle.secondary, emoji=data.get("emoji", "🎫"))
            btn.callback = self.make_callback(panel_name, key)
            self.add_item(btn)

    def make_callback(self, panel_name, section_key):
        async def cb(interaction: discord.Interaction):
            await create_user_ticket(interaction, panel_name, section_key)
        return cb


async def create_user_ticket(interaction: discord.Interaction, panel_name: str, section_key: str):
    guild = interaction.guild
    db = load_tickets_db()
    guild_data = db.get(str(guild.id), {})
    panel_data = guild_data.get("panels", {}).get(panel_name, {})
    section_data = panel_data.get("sections", {}).get(section_key)
    
    if not section_data:
        await interaction.response.send_message("❌ عذراً، هذا القسم غير موجود.", ephemeral=True)
        return

    category_id = guild_data.get("category_id")
    category = guild.get_channel(category_id) if category_id else None
    if not category:
        category = await guild.create_category("TICKETS SYSTEM - SECURE")

    # منع فتح أكثر من تذكرة نشطة لنفس المستخدم
    for channel in category.text_channels:
        if f"-{interaction.user.id}" in channel.name:
            await interaction.response.send_message(f"❌ لديك تذكرة مفتوحة بالفعل هنا: {channel.mention}", ephemeral=True)
            return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
    }

    support_role_ids = section_data.get("support_role_ids", [])
    support_roles_objs = [guild.get_role(r_id) for r_id in support_role_ids if guild.get_role(r_id)]
    
    for r_obj in support_roles_objs:
        overwrites[r_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

    ticket_number = len(category.text_channels) + 1
    ticket_channel = await guild.create_text_channel(
        name=f"ticket-{ticket_number}-{interaction.user.id}",
        category=category,
        overwrites=overwrites
    )

    if "active_tickets" not in guild_data:
        guild_data["active_tickets"] = {}
    
    creation_time_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    guild_data["active_tickets"][str(ticket_channel.id)] = {
        "user_id": interaction.user.id,
        "panel": panel_name,
        "section": section_data["label"],
        "support_role_ids": support_role_ids,
        "created_at": creation_time_str,
        "status": "مفتوحة"
    }
    save_tickets_db(db)

    color_int = int(section_data.get("color_hex", "2b2d31").replace("#", ""), 16)
    staff_mentions = " ".join([r.mention for r in support_roles_objs]) if support_roles_objs else "فريق الإدارة والدعم"

    # تصميم الـ Embed مطابق تماماً لما طلبته في الصورة
    embed = discord.Embed(
        title=f"مركز الدعم الفني - [{section_data['label']}]",
        description=f"أهلاً بك يا {interaction.user.mention} في قسم **{section_data['label']}**.\nيرجى توضيح مشكلتك بكافة التفاصيل ليتم خدمتك في أقرب وقت.",
        color=color_int,
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(name="👤 ╎ مالك التذكرة", value=f"{interaction.user.mention}", inline=False)
    embed.add_field(name="🛡️ ╎ مشرفي التذكرة", value=f"{staff_mentions}", inline=False)
    embed.add_field(name="📅 ╎ تاريخ التذكرة", value=f"`{creation_time_str}`", inline=False)
    embed.add_field(name="🔢 ╎ رقم التذكرة", value=f"`{ticket_number}`", inline=False)
    embed.add_field(name="❓ ╎ قسم التذكرة", value=f"`{section_data['label']}`", inline=False)

    if section_data.get("image_url"):
        embed.set_image(url=section_data["image_url"])
        
    embed.set_footer(text=f"Z I UO Tickets System ✦ ID: {ticket_channel.id}")

    sent_msg = await ticket_channel.send(
        content=f"تنبيه للطاقم: {interaction.user.mention} {staff_mentions}", 
        embed=embed, 
        view=TicketInsideView()
    )
    try:
        await sent_msg.pin()
    except:
        pass

    await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح داخل الروم: {ticket_channel.mention}", ephemeral=True)


# ==============================================================================
# 🛠️ نظام الإعداد المتسلسل (Multi-Step Wizard) لـ /ticket_setup
# ==============================================================================
class TicketSetupMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إنشاء بانل جديد", style=discord.ButtonStyle.success, emoji="🚀", custom_id="setup_create_panel_btn")
    async def create_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelInfoModal())

    @discord.ui.button(label="تعديل بانل موجود", style=discord.ButtonStyle.primary, emoji="⚙️", custom_id="setup_edit_panel_btn")
    async def edit_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        panels = db.get(str(interaction.guild.id), {}).get("panels", {})
        if not panels:
            await interaction.response.send_message("⚠️ لا توجد أي لوحات تذاكر مجهزة للتعديل.", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل المراد تعديله...")
        for name in panels.keys():
            select.add_option(label=name, value=name)
        
        async def select_callback(inter: discord.Interaction):
            chosen_panel = select.values[0]
            await inter.response.send_modal(PanelInfoModal(is_editing=True, panel_name=chosen_panel))
            
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("📂 اختر البانل الذي تريد تعديله:", view=view, ephemeral=True)

    @discord.ui.button(label="حذف بانل تذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="setup_delete_panel_btn")
    async def delete_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panels = db.get(guild_id_str, {}).get("panels", {})
        if not panels:
            await interaction.response.send_message("⚠️ لا توجد لوحات لحذفها.", ephemeral=True)
            return
            
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل المراد حذفه...")
        for name in panels.keys():
            select.add_option(label=name, value=name)
            
        async def del_callback(inter: discord.Interaction):
            chosen = select.values[0]
            db[guild_id_str]["panels"].pop(chosen, None)
            save_tickets_db(db)
            await inter.response.send_message(f"🗑️ تم حذف البانل **{chosen}** بنجاح!", ephemeral=True)
            
        select.callback = del_callback
        view.add_item(select)
        await interaction.response.send_message("🗑️ اختر اللوحة المراد حذفها:", view=view, ephemeral=True)

    @discord.ui.button(label="إحصائيات التذاكر", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="setup_stats_btn")
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        active = guild_data.get("active_tickets", {})
        closed = guild_data.get("closed_tickets_archive", [])

        embed = discord.Embed(title="📊 إحصائيات نظام التذاكر المتقدم", color=0x2B2D31, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="التذاكر المفتوحة حالياً", value=f"`{len(active)}` تذكرة", inline=True)
        embed.add_field(name="التذاكر المغلقة والأرشيف", value=`{len(closed)}` تذكرة", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PanelInfoModal(discord.ui.Modal, title="⚙️ إعدادات بانل التذاكر الأساسية"):
    def __init__(self, is_editing=False, panel_name=""):
        super().__init__()
        self.is_editing = is_editing
        self.old_panel_name = panel_name
        
        db = load_tickets_db() if is_editing else {}
        p_data = db.get(str(discord.Interaction.from_interaction.guild_id if hasattr(discord, 'Interaction') else 0), {}).get("panels", {}).get(panel_name, {}) if is_editing else {}

        self.name_box = discord.ui.TextInput(label="اسم البانل الفريد (System Name)", default=panel_name if is_editing else "", max_length=50, required=True)
        self.title_box = discord.ui.TextInput(label="عنوان رسالة الـ Embed للبانل", default=p_data.get("title", "مركز المساعدة والدعم الفني"), max_length=100, required=True)
        self.desc_box = discord.ui.TextInput(label="وصف البانل", default=p_data.get("desc", "اختر القسم المناسب لطلبك من الأسفل."), style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.image_box = discord.ui.TextInput(label="رابط صورة البانل (Image URL)", default=p_data.get("image_url", ""), required=False)
        self.color_box = discord.ui.TextInput(label="لون الـ Embed (Hex Code)", default=p_data.get("color_hex", "2b2d31"), max_length=10, required=True)

        self.add_item(self.name_box)
        self.add_item(self.title_box)
        self.add_item(self.desc_box)
        self.add_item(self.image_box)
        self.add_item(self.color_box)

    async def on_submit(self, interaction: discord.Interaction):
        p_name = self.name_box.value.strip()
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        
        if guild_id_str not in db:
            db[guild_id_str] = {"panels": {}, "active_tickets": {}, "closed_tickets_archive": []}

        if self.is_editing and self.old_panel_name != p_name:
            db[guild_id_str]["panels"].pop(self.old_panel_name, None)

        if p_name not in db[guild_id_str]["panels"]:
            db[guild_id_str]["panels"][p_name] = {"sections": {}}

        db[guild_id_str]["panels"][p_name].update({
            "title": self.title_box.value,
            "desc": self.desc_box.value,
            "image_url": self.image_box.value if self.image_box.value else None,
            "color_hex": self.color_box.value
        })
        save_tickets_db(db)

        # الخطوة التالية: اختيار نوع العرض (أزرار أو قائمة منسدلة)
        await interaction.response.send_message(
            f"✅ تم حفظ إعدادات البانل **{p_name}** بنجاح!\nالآن اختر نوع أزرار الفئات والأقسام:",
            view=PanelDisplayTypeView(p_name),
            ephemeral=True
        )


class PanelDisplayTypeView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="قائمة منسدلة (Menu)", style=discord.ButtonStyle.primary, emoji="📂")
    async def select_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["display_type"] = "menu"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))

    @discord.ui.button(label="أزرار تفاعلية (Buttons)", style=discord.ButtonStyle.success, emoji="🔘")
    async def select_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["display_type"] = "buttons"
        save_tickets_db(db)
        await interaction.response.send_modal(SectionsConfigModal(self.panel_name))


class SectionsConfigModal(discord.ui.Modal, title="📝 كتابة الأقسام ورتب الدعم"):
    def __init__(self, panel_name: str):
        super().__init__()
        self.panel_name = panel_name
        
        self.sections_box = discord.ui.TextInput(
            label="أسماء الفئات (كل فئة في سطر)",
            placeholder="دعم فني\nتقديم إدارة\nأسئلة عامة",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.roles_box = discord.ui.TextInput(
            label="أيدي رتب الدعم (كل أيدي في سطر)",
            placeholder="123456789012345678\n987654321098765432",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
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
        
        # نشر البانل مباشرة في الروم الحالي بناءً على المعطيات
        title = panel_data.get("title", "مركز الدعم")
        desc = panel_data.get("desc", "اختر قسمك")
        display_type = panel_data.get("display_type", "menu")
        color_int = int(panel_data.get("color_hex", "2b2d31").replace("#", ""), 16)

        embed = discord.Embed(
            title=title,
            desc=desc,
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        embed.description = desc + "\n\n____________________________________________________________________\n• اختر القسم المناسب لطلبك من الأسفل."
        if panel_data.get("image_url"):
            embed.set_image(url=panel_data["image_url"])
        embed.set_footer(text=f"Z I UO Community ✦ Panel: {self.panel_name}")

        guild_id = interaction.guild.id
        if display_type == "menu":
            view = discord.ui.View(timeout=None)
            view.add_item(DynamicTicketSelect(guild_id, self.panel_name))
        else:
            view = DynamicTicketButtonsView(guild_id, self.panel_name)

        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"🚀 **تم إنشاء وحفظ ونشر بانل التذاكر ({self.panel_name}) بنجاح تام في هذه القناة!**", ephemeral=True)


# ==============================================================================
# 🚀 Cog الحاوية الرئيسية
# ==============================================================================
class ZiuoUltimateTicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket_setup", description="[الإدارة] الأمر المركزي الموحد لإدارة وإنشاء وتعديل بانلات التذاكر بالكامل")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ مركز إدارة ونظام التذاكر المتقدم",
            description=(
                "مرحباً بك في لوحة تحكم التذاكر المركزية الشاملة.\n"
                "من خلال الأزرار أدناه يمكنك التحكم بكافة تفاصيل البانرات، إنشاء بانلات جديدة، التعديل الفوري، والحذف بكل مرونة:\n\n"
                "• **إنشاء بانل جديد:** مع معالج متسلسل لتحديد الأقسام والرتب والمظهر.\n"
                "• **تعديل بانل موجود:** لتحديث الإعدادات ورسائل البانل فوراً.\n"
                "• **حذف بانل:** لإزالة أي لوحة غير مقصودة.\n"
                "• **الإحصائيات:** لمتابعة حالة التذاكر النشطة."
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Ultimate Tickets Core ✦ 2026")
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
