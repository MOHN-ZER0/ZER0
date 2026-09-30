import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os
from typing import Optional, Literal

# قاعدة بيانات تخزين إعدادات وأقسام ولوحات التذاكر لكل سيرفر مع الإحصائيات
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


class MultiPanelTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_name: str):
        self.guild_id = guild_id
        self.panel_name = panel_name
        db = load_tickets_db()
        guild_data = db.get(str(guild_id), {})
        panels = guild_data.get("panels", {})
        panel_data = panels.get(panel_name, {})
        sections = panel_data.get("sections", {})
        
        if not sections:
            options = [discord.SelectOption(label="لا توجد أقسام مضافة في هذه اللوحة", description="قم بإضافة أقسام عبر الأوامر", emoji="⚠️", value="none")]
        else:
            options = [
                discord.SelectOption(
                    label=data["label"], 
                    description=data["description"][:100], 
                    emoji=data.get("emoji", "🎫"), 
                    value=key
                ) for key, data in sections.items()
            ]
        super().__init__(placeholder=f"📂 [ اختر قسم التذكرة للوحة: {panel_name} ]", min_values=1, max_values=1, options=options, custom_id=f"multi_panel_select_{guild_id}_{panel_name}")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ عذراً، لا توجد أقسام متاحة في هذه اللوحة حالياً!", ephemeral=True)
            return

        guild = interaction.guild
        db = load_tickets_db()
        guild_data = db.get(str(guild.id), {})
        panel_data = guild_data.get("panels", {}).get(self.panel_name, {})
        section_data = panel_data.get("sections", {}).get(self.values[0])
        
        if not section_data:
            await interaction.response.send_message("❌ هذا القسم غير موجود أو تم حذفه.", ephemeral=True)
            return

        category_id = guild_data.get("category_id")
        category = guild.get_channel(category_id) if category_id else None
        if not category:
            category = await guild.create_category("TICKETS SYSTEM - SECURE")

        # منع فتح أكثر من تذكرة لنفس المستخدم في السيرفر
        for channel in category.text_channels:
            if f"-{interaction.user.id}" in channel.name:
                await interaction.response.send_message(f"❌ لديك تذكرة مفتوحة بالفعل هنا: {channel.mention}، يرجى إغلاقها أو التوجه إليها أولاً!", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }

        support_role_id = section_data.get("support_role_id") or guild_data.get("support_role_id")
        support_role = guild.get_role(support_role_id) if support_role_id else None
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)

        ticket_number = len(category.text_channels) + 1
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{ticket_number}-{interaction.user.id}",
            category=category,
            overwrites=overwrites
        )

        if "active_tickets" not in guild_data:
            guild_data["active_tickets"] = {}
        
        creation_time_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        guild_data["active_tickets"][str(ticket_channel.id)] = {
            "user_id": interaction.user.id,
            "panel": self.panel_name,
            "section": section_data["label"],
            "created_at": creation_time_str,
            "status": "مفتوحة"
        }
        save_tickets_db(db)

        color_int = int(section_data.get("color_hex", "2b2d31").replace("#", ""), 16)
        
        embed = discord.Embed(
            title=f"مركز الدعم الفني المعتمد - لوحة [{self.panel_name}]",
            description=(
                f"أهلاً بك يا {interaction.user.mention} في قسم **{section_data['label']}**.\n"
                f"تم تأمين وتشفير هذه المحادثة بالكامل لضمان سرية معلوماتك وجودة خدمة الدعم المقدمة من الفريق المختص.\n"
                f"____________________________________________________________________\n\n"
                f"يرجى كتابة تفاصيل مشكلتك أو استفسارك كاملاً مع إرفاق الأدلة أو الصور لتسهيل خدمة العملاء."
            ),
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        
        staff_mentions = support_role.mention if support_role else "فريق الإدارة العليا ودعم السيرفر"
        
        embed.add_field(name="معلومات العضو وصاحب التذكرة", value=f"> **العضو:** {interaction.user.mention}\n> **المعرف:** `{interaction.user.id}`", inline=True)
        embed.add_field(name="الطاقم المسؤول عن القسم", value=f"> **الرتبة المختصة:** {staff_mentions}", inline=True)
        embed.add_field(name="تفاصيل تقنية", value=f"> **رقم السجل:** `#00{ticket_number}`\n> **اللوحة:** `{self.panel_name}`\n> **وقت الفتح:** `{creation_time_str}`", inline=False)
        
        if section_data.get("image_url"):
            embed.set_image(url=section_data["image_url"])
            
        embed.set_footer(text=f"Z I UO Ultimate Tickets System ✦ Ticket ID: {ticket_channel.id}")

        sent_message = await ticket_channel.send(
            content=f"تنبيه للطاقم المختص: {interaction.user.mention} {support_role.mention if support_role else ''} ╎ **تم فتح تذكرة جديدة بنجاح!**", 
            embed=embed, 
            view=TicketInsideView()
        )
        try:
            await sent_message.pin()
        except:
            pass

        await interaction.response.send_message(f"✅ تم إنشاء تذكرتك بنجاح تام داخل الروم: {ticket_channel.mention}", ephemeral=True)


class MultiPanelTicketButtonsView(discord.ui.View):
    def __init__(self, guild_id: int, panel_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_name = panel_name
        db = load_tickets_db()
        guild_data = db.get(str(guild_id), {})
        panel_data = guild_data.get("panels", {}).get(panel_name, {})
        sections = panel_data.get("sections", {})
        
        for key, data in sections.items():
            button = discord.ui.Button(
                label=data["label"], 
                style=discord.ButtonStyle.secondary, 
                emoji=data.get("emoji", "🎫"),
                custom_id=f"multi_btn_{guild_id}_{panel_name}_{key}"
            )
            button.callback = self.create_button_callback(panel_name, key)
            self.add_item(button)

    def create_button_callback(self, panel_name, section_key):
        async def button_callback(interaction: discord.Interaction):
            guild = interaction.guild
            db = load_tickets_db()
            guild_data = db.get(str(guild.id), {})
            panel_data = guild_data.get("panels", {}).get(panel_name, {})
            section_data = panel_data.get("sections", {}).get(section_key)
            
            if not section_data:
                await interaction.response.send_message("❌ عذراً، هذا القسم لم يعد موجوداً.", ephemeral=True)
                return
            
            category_id = guild_data.get("category_id")
            category = guild.get_channel(category_id) if category_id else guild.categories[0]

            for channel in category.text_channels:
                if f"-{interaction.user.id}" in channel.name:
                    await interaction.response.send_message(f"❌ لديك تذكرة مفتوحة بالفعل هنا: {channel.mention}", ephemeral=True)
                    return

            ticket_number = len(category.text_channels) + 1
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            
            support_role_id = section_data.get("support_role_id") or guild_data.get("support_role_id")
            support_role = guild.get_role(support_role_id) if support_role_id else None
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            ticket_channel = await guild.create_text_channel(name=f"ticket-{ticket_number}-{interaction.user.id}", category=category, overwrites=overwrites)
            
            if "active_tickets" not in guild_data:
                guild_data["active_tickets"] = {}
            creation_time_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            guild_data["active_tickets"][str(ticket_channel.id)] = {
                "user_id": interaction.user.id,
                "panel": panel_name,
                "section": section_data["label"],
                "created_at": creation_time_str,
                "status": "مفتوحة"
            }
            save_tickets_db(db)

            color_int = int(section_data.get("color_hex", "2b2d31").replace("#", ""), 16)
            embed = discord.Embed(
                title=f"نظام التذاكر الذكي - لوحة [{panel_name}]",
                description=f"أهلاً بك يا {interaction.user.mention} في قسم **{section_data['label']}**.\nيرجى شرح طلبك بالتفصيل.",
                color=color_int,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="معلومات العضو", value=f"> {interaction.user.mention} (`{interaction.user.id}`)", inline=False)
            embed.add_field(name="القسم والتصنيف", value=f"> `{section_data['label']}`", inline=False)
            
            if section_data.get("image_url"):
                embed.set_image(url=section_data["image_url"])
                
            sent_msg = await ticket_channel.send(
                content=f"تنبيه للطاقم: {interaction.user.mention} {support_role.mention if support_role else ''}", 
                embed=embed, 
                view=TicketInsideView()
            )
            try: 
                await sent_msg.pin()
            except: 
                pass
            
            await interaction.response.send_message(f"✅ تم فتح التذكرة بنجاح في القناة: {ticket_channel.mention}", ephemeral=True)
        return button_callback


class TicketInsideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام التذكرة", style=discord.ButtonStyle.primary, emoji="💼", custom_id="claim_ticket_ultimate_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"💼 تم استلام التذكرة رسمياً بواسطة المشرف: {interaction.user.mention}.")

    @discord.ui.button(label="خيارات إضافية", style=discord.ButtonStyle.secondary, emoji="⚙", custom_id="options_ticket_ultimate_btn")
    async def ticket_options(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TicketSubControlView()
        await interaction.response.send_message("⚙️ قائمة التحكم الإضافية بالتذكرة:", view=view, ephemeral=True)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_ultimate_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        if guild_id_str in db and "active_tickets" in db[guild_id_str]:
            if channel_id_str in db[guild_id_str]["active_tickets"]:
                db[guild_id_str]["active_tickets"][channel_id_str]["status"] = "مغلقة"
                if "closed_tickets_archive" not in db[guild_id_str]:
                    db[guild_id_str]["closed_tickets_archive"] = []
                db[guild_id_str]["closed_tickets_archive"].append(db[guild_id_str]["active_tickets"].pop(channel_id_str))
                save_tickets_db(db)

        await interaction.response.send_message("🔒 جاري إغلاق التذكرة وحذف القناة خلال 5 ثوانٍ...")
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass


class TicketSubControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تنبيه صاحب التذكرة", style=discord.ButtonStyle.success, emoji="🔔", custom_id="ping_user_ultimate_btn")
    async def ping_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🔔 تنبيه رسمي موجه لصاحب التذكرة: يرجى التفاعل والرد في أسرع وقت.")
        await interaction.response.send_message("✅ تم إرسال التنبيه بنجاح.", ephemeral=True)


class CustomTicketsUltimateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket_config", description="تحديد الفئة الرئيسية والرتبة الافتراضية العامة للتذاكر")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_config(self, interaction: discord.Interaction, category: discord.CategoryChannel, support_role: discord.Role):
        db = load_tickets_db()
        guild_id = str(interaction.guild.id)
        if guild_id not in db:
            db[guild_id] = {"panels": {}, "active_tickets": {}, "closed_tickets_archive": []}
        
        db[guild_id]["category_id"] = category.id
        db[guild_id]["support_role_id"] = support_role.id
        save_tickets_db(db)
        await interaction.response.send_message("✅ تم حفظ إعدادات الفئة والرتبة العامة بنجاح تام!", ephemeral=True)

    @app_commands.command(name="ticket_create_panel", description="إنشاء لوحة تذاكر جديدة مستقلة باسم مخصص")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_create_panel(self, interaction: discord.Interaction, panel_name: str):
        db = load_tickets_db()
        guild_id = str(interaction.guild.id)
        if guild_id not in db:
            db[guild_id] = {"panels": {}, "active_tickets": {}, "closed_tickets_archive": []}
        
        if panel_name in db[guild_id]["panels"]:
            await interaction.response.send_message(f"❌ لوحة بهذا الاسم (`{panel_name}`) موجودة مسبقاً!", ephemeral=True)
            return

        db[guild_id]["panels"][panel_name] = {"sections": {}}
        save_tickets_db(db)
        await interaction.response.send_message(f"✅ تم إنشاء لوحة التذاكر الجديدة باسم: **{panel_name}** بنجاح!", ephemeral=True)

    @app_commands.command(name="ticket_list_panels", description="عرض جميع لوحات التذاكر التي قمت بإنشائها وأسمائها")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_list_panels(self, interaction: discord.Interaction):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        panels = guild_data.get("panels", {})
        
        if not panels:
            await interaction.response.send_message("⚠️ لا توجد أي لوحات تذاكر أنشأتها حتى الآن.", ephemeral=True)
            return

        embed = discord.Embed(title="📊 لوحات التذاكر النشطة في السيرفر", color=0x2b2d31, timestamp=datetime.datetime.utcnow())
        for name, data in panels.items():
            sections_count = len(data.get("sections", {}))
            embed.add_field(name=f"📌 لوحة: {name}", value=f"> عدد الأقسام الداخلية: `{sections_count}` قسم", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ticket_add_section", description="إضافة قسم تذاكر داخل لوحة معينة مع تحديد رتبة دعم خاصة بالقسم")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_add_section(
        self, 
        interaction: discord.Interaction, 
        panel_name: str,
        key: str, 
        title: str, 
        description: str, 
        emoji: str, 
        section_support_role: discord.Role = None,
        color_hex: str = "2b2d31", 
        image_url: str = None
    ):
        db = load_tickets_db()
        guild_id = str(interaction.guild.id)
        if guild_id not in db or panel_name not in db[guild_id]["panels"]:
            await interaction.response.send_message(f"❌ لوحة التذاكر باسم `{panel_name}` غير موجودة! أنشئها أولاً عبر `/ticket_create_panel`.", ephemeral=True)
            return

        db[guild_id]["panels"][panel_name]["sections"][key] = {
            "label": title,
            "description": description,
            "emoji": emoji,
            "support_role_id": section_support_role.id if section_support_role else None,
            "color_hex": color_hex,
            "image_url": image_url
        }
        save_tickets_db(db)
        role_mention = section_support_role.mention if section_support_role else "رتبة السيرفر العامة"
        await interaction.response.send_message(f"✅ تم إضافة القسم ｢ **{title}** ｣ بنجاح إلى اللوحة **{panel_name}** مع ربطه برتبة دعم: {role_mention}!", ephemeral=True)

    @app_commands.command(name="ticket_panel_deploy", description="نشر لوحة تذاكر معينة في القناة الحالية (قائمة منسدلة أو أزرار)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel_deploy(
        self, 
        interaction: discord.Interaction, 
        panel_name: str,
        title: str, 
        description: str, 
        display_type: Literal["menu", "buttons"], 
        color_hex: str = "2b2d31", 
        image_url: str = None
    ):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in db or panel_name not in db[guild_id_str]["panels"]:
            await interaction.response.send_message(f"❌ عذراً، اللوحة باسم `{panel_name}` غير موجودة!", ephemeral=True)
            return

        try:
            color_int = int(color_hex.replace("#", ""), 16)
        except:
            color_int = 0x2b2d31

        embed = discord.Embed(
            title=title,
            description=description + "\n\n____________________________________________________________________\n• اختر القسم المناسب لطلبك من الأسفل.",
            color=color_int,
            timestamp=datetime.datetime.utcnow()
        )
        if image_url:
            embed.set_image(url=image_url)
            
        embed.set_footer(text=f"Z I UO Community ✦ Panel: {panel_name}")

        guild_id = interaction.guild.id
        if display_type == "menu":
            view = discord.ui.View(timeout=None)
            view.add_item(MultiPanelTicketSelect(guild_id, panel_name))
        else:
            view = MultiPanelTicketButtonsView(guild_id, panel_name)

        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ تم نشر لوحة التذاكر **{panel_name}** بنجاح في هذه القناة!", ephemeral=True)

    @app_commands.command(name="ticket_stats", description="عرض إحصائيات التذاكر (المفتوحة، المغلقة، تفاصيل من فتح ومتى)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        active = guild_data.get("active_tickets", {})
        closed = guild_data.get("closed_tickets_archive", [])

        embed = discord.Embed(title="📊 لوحة إحصائيات ومعلومات نظام التذاكر", color=0x2b2d31, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="التذاكر المفتوحة حالياً", value=f"> `{len(active)}` تذكرة نشطة", inline=True)
        embed.add_field(name="التذاكر المغلقة والأرشيف", value=f"> `{len(closed)}` تذكرة مقفولة", inline=True)

        if active:
            active_desc = ""
            for ch_id, data in list(active.items())[:5]:
                member_obj = interaction.guild.get_member(data['user_id'])
                member_str = member_obj.mention if member_obj else f"مستخدم (`{data['user_id']}`)"
                active_desc += f"• صاحبها: {member_str} | القسم: `{data['section']}` | في: `{data['created_at']}`\n"
            embed.add_field(name="📌 عينة من التذاكر المفتوحة الحالية", value=active_desc, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CustomTicketsUltimateCog(bot))
