import discord
from discord.ext import commands, tasks
from discord import ui
import datetime
import asyncio
import io
import json
import os
import random

# ==============================================================================
# 📌 CONFIGURATION & CONSTANTS (ZERO SYSTEM ADVANCED ULTRA MODULE)
# ==============================================================================
CATEGORY_ID = 1520514282133913621
PANEL_IMAGE_URL = "https://cdn.discordapp.com/attachments/1534504185171677267/1539598207678681169/Picsart_26-08-19_14-33-25-925.jpg?ex=6a86e611&is=6a859491&hm=c83ba0799c4074bf49d737731eddf9c00022d601da6dc9fa71da41aad64a9ad1&"
BACKUP_FILE_PATH = "ticket_database_backup.json"

# ==============================================================================
# 📊 DATABASE & ANALYTICS MANAGER CLASS
# ==============================================================================
class TicketDatabaseManager:
    def __init__(self, filepath=BACKUP_FILE_PATH):
        self.filepath = filepath
        self.data = self.load_database()

    def load_database(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"total_created": 0, "active_tickets": {}, "closed_tickets": [], "blacklisted_users": []}
        return {"total_created": 0, "active_tickets": {}, "closed_tickets": [], "blacklisted_users": []}

    def save_database(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] Failed to save database: {e}")

    def add_ticket(self, channel_id, user_id, ticket_type, number):
        self.data["total_created"] += 1
        self.data["active_tickets"][str(channel_id)] = {
            "owner_id": user_id,
            "type": ticket_type,
            "number": number,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "claimed_by": None,
            "notes": [],
            "rating": None
        }
        self.save_database()

    def remove_ticket(self, channel_id):
        str_id = str(channel_id)
        if str_id in self.data["active_tickets"]:
            ticket_info = self.data["active_tickets"].pop(str_id)
            self.data["closed_tickets"].append(ticket_info)
            self.save_database()

    def get_ticket(self, channel_id):
        return self.data["active_tickets"].get(str(channel_id))

    def update_claim(self, channel_id, admin_id):
        str_id = str(channel_id)
        if str_id in self.data["active_tickets"]:
            self.data["active_tickets"][str_id]["claimed_by"] = admin_id
            self.save_database()

    def add_note_to_ticket(self, channel_id, note):
        str_id = str(channel_id)
        if str_id in self.data["active_tickets"]:
            self.data["active_tickets"][str_id]["notes"].append(note)
            self.save_database()

    def is_blacklisted(self, user_id):
        return user_id in self.data.get("blacklisted_users", [])

    def toggle_blacklist(self, user_id):
        if user_id in self.data["blacklisted_users"]:
            self.data["blacklisted_users"].remove(user_id)
            self.save_database()
            return False
        else:
            self.data["blacklisted_users"].append(user_id)
            self.save_database()
            return True


# ==============================================================================
# 🎫 ADVANCED ULTRA TICKET SYSTEM COG
# ==============================================================================
class UltraAdvancedTicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = TicketDatabaseManager()
        self.ticket_counter = self.db.data.get("total_created", 0) + 1
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

    @tasks.loop(minutes=30)
    async def auto_backup_task(self):
        self.db.save_database()
        print("[⚡ ZERO SYSTEM] Automated database synchronization completed securely.")

    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        print("[⚡ ZERO SYSTEM] Ultra Advanced Ticket System Cog Loaded Successfully with full features.")

    # --------------------------------------------------------------------------
    # أمر إرسال البانل الاحترافي الرئيسي
    # --------------------------------------------------------------------------
    @commands.command(name="setup_ticket", aliases=["تكت", "بانل_التذاكر"])
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, ctx):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        
        embed = discord.Embed(
            title="⚡ 《 Z E R O • ULTRA TICKET SYSTEM 》 ⚡",
            description=(
                "**📌 نظام التذاكر والمساعدة الشامل والذكي**\n\n"
                "أهلاً بكم يا أبطال سيرفر ZERO العظماء! 🌟\n"
                "لقد صممنا هذا النظام بتقنيات متقدمة جداً لضمان تقديم أسرع وأرقى خدمة دعم فني وإداري ممكنة:\n\n"
                "**📌 إرشادات هامة لضمان سرعة إنجاز طلبك:**\n"
                "📁 اختيار القسم بدقة: توجه للقسم المخصص لطلبك لضمان تحويله للمختصين فوراً.\n"
                "💬 التفاصيل الكاملة: اكتب مشكلتك أو استفسارك بوضوح تام في رسالتك الأولى.\n"
                "⏳ الهدوء والصبر: فريق العمل متواجد لخدمتكم على مدار الساعة.\n\n"
                "⚡ **[ أقسام النظام والخدمات المتاحة ]** ⚡\n"
                "🛠️ تقديم إدارة ديسكورد (DISCORD STAFF)\n"
                "⛏️ تقديم إدارة ماين كرافت (MINECRAFT STAFF)\n"
                "🚨 البلاغات والشكاوى الرسمية (REPORTS)\n"
                "💻 تقديم قسم المطورين (DEVELOPERS)\n"
                "🎧 الدعم الفني الشامل والتقني (SUPPORT)\n"
                "🎉 مسؤول الفعاليات والمسابقات (EVENTS)\n"
                "🤝 الشراكات الاستراتيجية (PARTNERSHIPS)\n"
                "💎 شراء الرتب والمميزات (VIP STORE)\n"
                "📢 الإعلانات والترويج (ADVERTISEMENTS)\n"
                "❓ الاستفسارات العامة (GENERAL INQUIRIES)\n\n"
                "🚀 نتشرف بخدمتكم دائماً في مجتمعنا الراقي والمميز!\n\n"
                "✨ **ZERO COMMUNITY - ALWAYS BETTER • 2026** ✨"
            ),
            color=discord.Color.from_rgb(15, 15, 15)
        )
        embed.set_image(url=PANEL_IMAGE_URL)
        embed.set_footer(text="ZERO SYSTEM • Ultra Secure Core Management", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        view = UltraMainTicketPanelView(self)
        await ctx.send(embed=embed, view=view)

    # --------------------------------------------------------------------------
    # أمر إدارة القائمة السوداء للتذاكر (Blacklist)
    # --------------------------------------------------------------------------
    @commands.command(name="ticket_blacklist", aliases=["حظر_تكت"])
    @commands.has_permissions(administrator=True)
    async def ticket_blacklist(self, ctx, member: discord.Member):
        status = self.db.toggle_blacklist(member.id)
        if status:
            await ctx.send(f"✅ تم إدراج العضو {member.mention} في القائمة السوداء للتذاكر بنجاح.")
        else:
            await ctx.send(f"✅ تم إزالة العضو {member.mention} من القائمة السوداء للتذاكر بنجاح.")

    # --------------------------------------------------------------------------
    # دالة إنشاء القناة المركزية المحترفة
    # --------------------------------------------------------------------------
    async def create_ticket_channel(self, interaction: discord.Interaction, ticket_type: str):
        guild = interaction.guild
        
        # فحص القائمة السوداء
        if self.db.is_blacklisted(interaction.user.id):
            await interaction.response.send_message("❌ عذراً، أنت ممنوع من فتح تذاكر جديدة بناءً على قرارات الإدارة.", ephemeral=True)
            return

        category = guild.get_channel(CATEGORY_ID)
        if not category:
            await interaction.response.send_message("❌ خطأ حرج: لم يتم العثور على الفئة المخصصة للتذاكر في السيرفر!", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                attach_files=True, 
                embed_links=True,
                read_message_history=True
            ),
        }

        for role in guild.roles:
            role_name = role.name.lower()
            if any(k in role_name for k in ["staff", "مشرف", "إداري", "admin", "moderator"]):
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_channels=False,
                    read_message_history=True
                )

        current_number = self.ticket_counter
        self.ticket_counter += 1
        channel_name = f"🎫・𝐓𝐈𝐂𝐊𝐄𝐓・{current_number}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"مالك التذكرة: {interaction.user.id} | القسم: {ticket_type} | الرقم: {current_number}"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إنشاء قناة التذكرة: {e}", ephemeral=True)
            return

        # حفظ في قاعدة البيانات المحلية
        self.db.add_ticket(channel.id, interaction.user.id, ticket_type, current_number)

        created_str = datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
        
        embed = discord.Embed(
            title="🛡️ نظام إدارة التذاكر الاحترافي المتقدم",
            description=f"أهلاً بك يا {interaction.user.mention} في غرفتك الخاصة. يرجى كتابة تفاصيل طلبك أو مشكلتك بالكامل.",
            color=discord.Color.from_rgb(25, 25, 25)
        )
        embed.add_field(name="👤 ] : مالك التذكرة", value=interaction.user.mention, inline=False)
        embed.add_field(name="🛡️ ] : طاقم الإدارة", value="@STAFF | ║『🔗』", inline=False)
        embed.add_field(name="📅 ] : وقت الفتح", value=created_str, inline=False)
        embed.add_field(name="🔢 ] : رقم التذكرة", value=str(current_number), inline=False)
        embed.add_field(name="❓ ] : القسم المختار", value=ticket_type, inline=False)
        embed.set_footer(text="ZERO ULTRA SYSTEM • Secure Department Engine", icon_url=guild.icon.url if guild.icon else None)

        view = UltraTicketInsideView(self.bot, self)
        msg_content = f"@STAFF | ║『🔗』 {interaction.user.mention}"
        
        try:
            ticket_msg = await channel.send(content=msg_content, embed=embed, view=view)
            await ticket_msg.pin()
        except Exception:
            pass

        await interaction.response.send_message(f"✅ تم إنشاء تذكرتك السرية بنجاح تام: {channel.mention}", ephemeral=True)


# ==============================================================================
# 🎛️ PANELS, DROPDOWNS & BUTTONS UI (MAIN)
# ==============================================================================
class UltraMainTicketPanelView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(UltraTicketSelectDropdown(cog))

    @ui.button(label="MINECRAFT • تقديم إدارة", style=discord.ButtonStyle.success, emoji="⛏️", custom_id="ultra_persistent_mc_apply_btn")
    async def mc_apply_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.create_ticket_channel(interaction, "تقديم إدارة ماين كرافت")


class UltraTicketSelectDropdown(ui.Select):
    def __init__(self, cog):
        self.cog = cog
        options = [
            discord.SelectOption(label="DISCORD STAFF", description="تقديم إدارة ديسكورد الرسمية", emoji="🛡️", value="apply_discord"),
            discord.SelectOption(label="REPORTS", description="تقديم بلاغ أو شكوى ضد أي مخالفة", emoji="🚨", value="reports"),
            discord.SelectOption(label="DEVELOPERS", description="تقديم قسم المطورين والبرمجة", emoji="💻", value="developers"),
            discord.SelectOption(label="SUPPORT", description="الدعم الفني الشامل والمساعدة التقنية", emoji="🎧", value="support"),
            discord.SelectOption(label="EVENTS", description="مسؤول الفعاليات والأنشطة", emoji="🎉", value="events"),
            discord.SelectOption(label="PARTNERSHIPS", description="عقد الشراكات الاستراتيجية المتبادلة", emoji="🤝", value="partnerships"),
            discord.SelectOption(label="VIP STORE", description="شراء الرتب والمميزات الخاصة", emoji="💎", value="vip_store"),
            discord.SelectOption(label="ADVERTISEMENTS", description="الإعلانات والترويج للمشاريع", emoji="📢", value="ads"),
            discord.SelectOption(label="GENERAL INQUIRY", description="الاستفسارات العامة والأسئلة", emoji="❓", value="inquiry"),
        ]
        super().__init__(placeholder="اختر القسم المناسب لتذكرتك من القائمة المنسدلة...", min_values=1, max_values=1, options=options, custom_id="ultra_persistent_dropdown")

    async def callback(self, interaction: discord.Interaction):
        mapping = {
            "apply_discord": "تقديم إدارة ديسكورد",
            "reports": "البلاغات والشكاوى",
            "developers": "تقديم المطورين",
            "support": "الدعم الفني الشامل",
            "events": "مسؤول الفعاليات",
            "partnerships": "الشراكات الاستراتيجية",
            "vip_store": "شراء الرتب والمميزات",
            "ads": "الإعلانات والترويج",
            "inquiry": "الاستفسارات العامة"
        }
        ticket_type = mapping.get(self.values[0], "دعم عام")
        await self.cog.create_ticket_channel(interaction, ticket_type)


# ==============================================================================
# 🛠️ INTERNAL TICKET CONTROLS VIEW (INSIDE ROOM)
# ==============================================================================
class UltraTicketInsideView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @ui.button(label="استلام التذكرة", style=discord.ButtonStyle.primary, emoji="💼", custom_id="ultra_claim_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        channel_id = interaction.channel.id
        ticket_data = self.cog.db.get_ticket(channel_id)
        
        if ticket_data and ticket_data.get("owner_id") == interaction.user.id:
            await interaction.response.send_message("❌ تحذير أمني: لا يمكنك استلام تذكرتك الخاصة بنفسك مطلقاً!", ephemeral=True)
            return

        if ticket_data and ticket_data.get("claimed_by"):
            await interaction.response.send_message(f"⚠️ هذه التذكرة مستلمة بالفعل بواسطة المسؤول: <@{ticket_data['claimed_by']}>", ephemeral=True)
            return

        self.cog.db.update_claim(channel_id, interaction.user.id)

        button.disabled = True
        button.label = f"استلمها: {interaction.user.name}"
        button.style = discord.ButtonStyle.success
        
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await interaction.response.send_message(f"✅ **تم استلام التذكرة بنجاح!** المشرف المسؤول عن المتابعة الآن: {interaction.user.mention}")

    @ui.select(
        placeholder="اختر إجراءً متقدماً للتحكم بالتذكرة...",
        options=[
            discord.SelectOption(label="إغلاق التذكرة مع سبب", description="إغلاق نهائي مع إرسال تقرير خاص للعميل", emoji="🔒", value="close"),
            discord.SelectOption(label="إضافة ملاحظة إدارية", description="تدوين ملاحظة سرية داخل قاعدة بيانات التذكرة", emoji="📝", value="add_note"),
            discord.SelectOption(label="تنبيه مالك التذكرة", description="إرسال منشن وتنبيه متحرك في الروم", emoji="🔔", value="ping_owner"),
            discord.SelectOption(label="استخراج سجل الترانزكريبت", description="تصدير نسخة نصية كاملة للمحادثات", emoji="📄", value="transcript")
        ],
        custom_id="ultra_options_dropdown"
    )
    async def options_callback(self, interaction: discord.Interaction, select: ui.Select):
        val = select.values[0]
        
        if val == "close":
            await interaction.response.send_modal(UltraCloseModal(self.bot, self.cog))
            
        elif val == "add_note":
            await interaction.response.send_modal(UltraNoteModal(self.cog))
            
        elif val == "ping_owner":
            ticket_data = self.cog.db.get_ticket(interaction.channel.id)
            if ticket_data:
                owner = interaction.guild.get_member(ticket_data["owner_id"])
                if owner:
                    await interaction.channel.send(f"🔔 تنبيه رسمي من الإدارة إلى {owner.mention}: يرجى الرد والتفاعل مع تذكرتك.")
                    await interaction.response.send_message("✅ تم إرسال التنبيه بنجاح.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ لم يتم العثور على صاحب التذكرة.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ بيانات التذكرة غير مسجلة في قاعدة البيانات.", ephemeral=True)
                
        elif val == "transcript":
            await interaction.response.defer(ephemeral=True)
            try:
                messages_history = []
                async for message in interaction.channel.history(limit=500, oldest_first=True):
                    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    messages_history.append(f"[{timestamp}] {message.author}: {message.content}")
                
                content_str = "\n".join(messages_history)
                file = discord.File(io.BytesIO(content_str.encode('utf-8')), filename=f"ultra-transcript-{interaction.channel.name}.txt")
                await interaction.followup.send("📄 تفضل سجل الترانزكريبت الشامل للمحادثة:", file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ حدث خطأ أثناء استخراج السجل: {e}", ephemeral=True)


# ==============================================================================
# 📝 MODALS (CLOSE & NOTE SYSTEMS)
# ==============================================================================
class UltraCloseModal(ui.Modal, title='تأكيد إغلاق تذكرة الدعم'):
    reason = ui.TextInput(
        label='سبب الإغلاق بالتفصيل:',
        style=discord.TextStyle.paragraph,
        placeholder='اكتب سبب إغلاق التذكرة بوضوح تام...',
        required=True,
        max_length=400
    )

    def __init__(self, bot, cog):
        super().__init__()
        self.bot = bot
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        closed_by = interaction.user
        close_reason = self.reason.value
        
        ticket_data = self.cog.db.get_ticket(channel.id) or {}
        owner_id = ticket_data.get("owner_id")
        ticket_num = ticket_data.get("number", "غير معروف")
        created_at = ticket_data.get("created_at", "غير معروف")
        closed_at = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

        if not owner_id and channel.topic:
            for word in channel.topic.split():
                if word.isdigit() and len(word) > 15:
                    owner_id = int(word)
                    break

        # إرسال تقارير خاصة للعميل في الـ DM
        if owner_id:
            try:
                owner = await interaction.guild.fetch_member(owner_id)
                if owner:
                    dm_embed = discord.Embed(
                        title="🔒     # ------------------------------------------
    # دالة مركزية لإنشاء رومات التذاكر
    # ------------------------------------------
    async def create_ticket_channel(self, interaction: discord.Interaction, ticket_type: str):
        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("❌ خطأ حرج: لم يتم العثور على فئة الدعم الأساسية المحددة في الإعدادات!", ephemeral=True)
            return

        # إعداد الأذونات الأساسية (منع الجميع، السماح لصاحب التذكرة وطاقم الإدارة)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                attach_files=True, 
                embed_links=True,
                read_message_history=True
            ),
        }

        # منح صلاحيات الإدارة للرتب التي تحتوي على كلمة staff أو مشرف أو إداري
        for role in guild.roles:
            role_name_lower = role.name.lower()
            if any(kw in role_name_lower for kw in ["staff", "مشرف", "إداري", "admin", "moderator"]):
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    manage_channels=False,
                    read_message_history=True
                )

        current_ticket_number = self.ticket_counter
        channel_name = f"🎫・𝐓𝐈𝐂𝐊𝐄𝐓・{current_ticket_number}"
        self.ticket_counter += 1

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"مالك التذكرة: {interaction.user.id} | القسم: {ticket_type} | الرقم: {current_ticket_number}"
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إنشاء الروم: {e}", ephemeral=True)
            return

        # تسجيل البيانات في الذاكرة المؤقتة
        self.active_tickets[channel.id] = {
            "owner_id": interaction.user.id,
            "type": ticket_type,
            "number": current_ticket_number,
            "created_at": datetime.datetime.now(),
            "claimed_by": None
        }

        # إرسال رسالة الإمبد الترحيبية داخل التذكرة
        created_at_str = datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
        
        embed = discord.Embed(
            title="🛡️ نظام إدارة التذاكر الفردية",
            description=f"أهلاً بك يا {interaction.user.mention} في تذكرتك الخاصة. يرجى توضيح مشكلتك أو طلبك بالكامل ليتم خدمتك في أسرع وقت.",
            color=discord.Color.from_rgb(35, 35, 35)
        )
        embed.add_field(name="👤 ] : مالك التذكرة", value=interaction.user.mention, inline=False)
        embed.add_field(name="🛡️ ] : مشرفي التذكرة", value="@STAFF | ║『🔗』", inline=False)
        embed.add_field(name="📅 ] : تاريخ التذكرة", value=created_at_str, inline=False)
        embed.add_field(name="🔢 ] : رقم التذكرة", value=str(current_ticket_number), inline=False)
        embed.add_field(name="❓ ] : قسم التذكرة", value=ticket_type, inline=False)
        embed.set_footer(text="ZERO SYSTEM • Secure Department", icon_url=guild.icon.url if guild.icon else None)

        view = TicketInsideView(self.bot, self)
        msg_content = f"@STAFF | ║『🔗』 {interaction.user.mention}"
        
        try:
            ticket_msg = await channel.send(content=msg_content, embed=embed, view=view)
            await ticket_msg.pin()
        except Exception:
            pass

        await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح وبسرية تامة: {channel.mention}", ephemeral=True)


# ==========================================
# 🎛️ PANELS, DROPDOWNS & BUTTONS UI
# ==========================================
class MainTicketPanelView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(TicketSelectDropdown(cog))

    @ui.button(label="MINECRAFT • تقديم إدارة", style=discord.ButtonStyle.success, emoji="⛏️", custom_id="persistent_mc_staff_apply_btn")
    async def mc_apply_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.create_ticket_channel(interaction, "تقديم إدارة ماين كرافت")


class TicketSelectDropdown(ui.Select):
    def __init__(self, cog):
        self.cog = cog
        options = [
            discord.SelectOption(label="APPLICATION", description="تقديم إدارة: هل تستطيع تحمل المسؤولية؟", emoji="🛡️", value="apply"),
            discord.SelectOption(label="REPORT", description="إبلاغ أو شكوى ضد أي مخالفة أو إزعاج", emoji="🚨", value="report"),
            discord.SelectOption(label="DEVELOPER", description="تقديم مطور: هل تمتلك خبرة برمجية؟", emoji="💻", value="dev"),
            discord.SelectOption(label="SUPPORT", description="الدعم الفني: لمساعدة أو حل مشاكل تقنية", emoji="🎧", value="support"),
            discord.SelectOption(label="EVENTS", description="مسؤول فعاليات: أفكار لحماس السيرفر", emoji="🎉", value="events"),
            discord.SelectOption(label="PARTNERS", description="شراكة: لعقد وتطوير الشراكات المتبادلة", emoji="🤝", value="partners"),
            discord.SelectOption(label="BUY", description="شراء رتبة: للحصول على مميزات حصرية", emoji="💎", value="buy"),
            discord.SelectOption(label="ADS", description="إعلانات: الترويج للسيرفر أو مشروعك", emoji="📢", value="ads"),
            discord.SelectOption(label="INQUIRY", description="استفسار: للإجابة على أي تساؤلات", emoji="❓", value="inquiry"),
        ]
        super().__init__(placeholder="اختر خيار التذكرة المناسب من القائمة...", min_values=1, max_values=1, options=options, custom_id="persistent_main_ticket_dropdown")

    async def callback(self, interaction: discord.Interaction):
        mapping = {
            "apply": "تقديم إدارة ديسكورد",
            "report": "البلاغات والشكاوى",
            "dev": "تقديم المطورين",
            "support": "الدعم الفني الشامل",
            "events": "مسؤول الفعاليات",
            "partners": "الشراكات الاستراتيجية",
            "buy": "شراء الرتب والشراعية",
            "ads": "الإعلانات والترويج",
            "inquiry": "الاستفسارات العامة"
        }
        ticket_type = mapping.get(self.values[0], "دعم عام")
        await self.cog.create_ticket_channel(interaction, ticket_type)


# ==========================================
# 🛠️ INTERNAL TICKET CONTROLS VIEW
# ==========================================
class TicketInsideView(ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    # زر استلام التذكرة (Claim)
    @ui.button(label="استلام", style=discord.ButtonStyle.primary, emoji="💼", custom_id="persistent_claim_ticket_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        channel_id = interaction.channel.id
        ticket_data = self.cog.active_tickets.get(channel_id)
        
        # حماية صارمة: منع مالك التذكرة من استلام تذكرته بنفسه
        if ticket_data and ticket_data.get("owner_id") == interaction.user.id:
            await interaction.response.send_message("❌ خطأ أمني: لا يمكنك استلام تذكرتك الخاصة بنفسك مطلقاً!", ephemeral=True)
            return

        if ticket_data and ticket_data.get("claimed_by"):
            await interaction.response.send_message(f"⚠️ هذه التذكرة مستلمة بالفعل بواسطة العضو: <@{ticket_data['claimed_by']}>", ephemeral=True)
            return

        if ticket_data:
            ticket_data["claimed_by"] = interaction.user.id

        button.disabled = True
        button.label = f"استلمها: {interaction.user.name}"
        button.style = discord.ButtonStyle.success
        
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await interaction.response.send_message(f"✅ **تم استلام التذكرة بنجاح!** المسؤول المتابع حالياً: {interaction.user.mention}")

    # القائمة المنسدلة للخيارات الداخلية (إغلاق، إضافة، تذكير، ترانزكريبت)
    @ui.select(
        placeholder="اختر خياراً للتحكم بالتذكرة...",
        options=[
            discord.SelectOption(label="إغلاق بسبب", description="إغلاق التذكرة نهائياً مع كتابة السبب", emoji="🔒", value="close_ticket"),
            discord.SelectOption(label="إضافة شخص للتذكرة", description="تعليمات لإضافة عضو آخر", emoji="👥", value="add_member"),
            discord.SelectOption(label="تذكير عبر الرسائل", description="إرسال منشن وتنبيه لصاحب التذكرة", emoji="✉️", value="remind_user"),
            discord.SelectOption(label="طلب نسخة من التذكرة", description="استخراج سجل محادثات مؤقت (Transcript)", emoji="📄", value="transcript")
        ],
        custom_id="persistent_ticket_options_dropdown"
    )
    async def ticket_options_callback(self, interaction: discord.Interaction, select: ui.Select):
        val = select.values[0]
        
        if val == "close_ticket":
            # إظهار المودال الخاص بسبب الإغلاق
            await interaction.response.send_modal(CloseReasonModal(self.bot, self.cog))
            
        elif val == "add_member":
            await interaction.response.send_message("📌 لإضافة شخص، يرجى كتابة اسمه أو استخدام إعدادات القناة (Add members or roles) أعلى الروم.", ephemeral=True)
            
        elif val == "remind_user":
            channel_id = interaction.channel.id
            ticket_data = self.cog.active_tickets.get(channel_id)
            if ticket_data:
                owner = interaction.guild.get_member(ticket_data["owner_id"])
                if owner:
                    await interaction.channel.send(f"🔔 تنبيه وتذكير إلى {owner.منشن if hasattr(owner, 'mention') else f'<@{owner.id}>'}: يرجى الرد على الإداريين ومتابعة تذكرتك.")
                    await interaction.response.send_message("✅ تم إرسال تذكير في الروم بنجاح.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ لم يتم العثور على صاحب التذكرة.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ بيانات التذكرة غير موجودة بالذاكرة المؤقتة.", ephemeral=True)
                
        elif val == "transcript":
            await interaction.response.defer(ephemeral=True)
            try:
                # توليد ترانزكريبت نصي مبسط ومحترف
                messages_history = []
                async for message in interaction.channel.history(limit=200, oldest_first=True):
                    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    messages_history.append(f"[{timestamp}] {message.author}: {message.content}")
                
                transcript_content = "\n".join(messages_history)
                file = discord.File(io.BytesIO(transcript_content.encode('utf-8')), filename=f"transcript-{interaction.channel.name}.txt")
                await interaction.followup.send("📄 تفضل نسخة المحادثة المطلوبة:", file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ حدث خطأ أثناء استخراج الترانزكريبت: {e}", ephemeral=True)


# ==========================================
# 🔒 CLOSE MODAL & SECURE DM TRANSCRIPT LOGIC
# ==========================================
class CloseReasonModal(ui.Modal, title='سبب إغلاق التذكرة'):
    reason = ui.TextInput(
        label='اكتب سبب إغلاق التذكرة بالتفصيل:',
        style=discord.TextStyle.paragraph,
        placeholder='مثال: تم حل المشكلة بنجاح، أو مخالفة الشروط العامة...',
        required=True,
        max_length=400
    )

    def __init__(self, bot, cog):
        super().__init__()
        self.bot = bot
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        closed_by = interaction.user
        close_reason = self.reason.value
        
        ticket_data = self.cog.active_tickets.get(channel.id, {})
        owner_id = ticket_data.get("owner_id")
        ticket_num = ticket_data.get("number", "غير معروف")
        created_at = ticket_data.get("created_at", datetime.datetime.now())
        closed_at = datetime.datetime.now()

        # محاولة استخراج أيدي المالك من الـ Topic لو الذاكرة فاضية
        if not owner_id and channel.topic:
            for word in channel.topic.split():
                if word.isdigit() and len(word) > 15:
                    owner_id = int(word)
                    break

        # إرسال رسالة خاصة (DM) تفصيلية وآمنة لصاحب التذكرة
        if owner_id:
            try:
                owner = await interaction.guild.fetch_member(owner_id)
                if owner:
                    dm_embed = discord.Embed(
                        title="🔒 تقرير إغلاق تذكرة الدعم",
                        description=f"تم إغلاق تذكرتك رقم `#{ticket_num}` في سيرفر **{interaction.guild.name}** بشكل رسمي.",
                        color=discord.Color.from_rgb(200, 40, 40)
                    )
                    dm_embed.add_field(name="👤 بواسطة الإداري:", value=closed_by.mention, inline=False)
                    dm_embed.add_field(name="📝 سبب الإغلاق:", value=close_reason, inline=False)
                    dm_embed.add_field(name="📥 وقت فتح التذكرة:", value=created_at.strftime("%Y-%m-%d %I:%M %p"), inline=False)
                    dm_embed.add_field(name="📤 وقت إغلاق التذكرة:", value=closed_at.strftime("%Y-%m-%d %I:%M %p"), inline=False)
                    dm_embed.set_footer(text="شكراً لتواصلك معنا • ZERO SYSTEM")
                    
                    await owner.send(embed=dm_embed)
            except Exception as e:
                print(f"[WARN] Could not send DM to user {owner_id}: {e}")

        # مسح التذكرة من القاموس النشط
        if channel.id in self.cog.active_tickets:
            del self.cog.active_tickets[channel.id]

        await interaction.response.send_message(f"🔒 **سيتم إغلاق وحذف هذه القناة نهائياً خلال 5 ثوانٍ** بواسطة {closed_by.mention}\n📌 **السبب:** {close_reason}")

        # حذف الروم بعد 5 ثوانٍ بأمان
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Closed by {closed_by} - Reason: {close_reason}")
        except Exception as e:
            print(f"[ERROR] Failed to delete channel: {e}")

# ==========================================
# ⚙️ COG SETUP FUNCTION
# ==========================================
async def setup(bot):
    await bot.add_cog(AdvancedTicketSystem(bot))
  
