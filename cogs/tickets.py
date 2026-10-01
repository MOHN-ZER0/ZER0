import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import json
import os
import io
import asyncio

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
        
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        t_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(str(self.ticket_channel.id), {})
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
            await interaction.response.edit_message(content=f"❤ ╎ شكراً لتقييمك الرائع ({stars_str})! سيتم إزالة التذكرة وتطهير السجل خلال 3 ثوانٍ...", view=self)
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

            voice_chan_id = ticket_data.get("temp_voice_id")
            if voice_chan_id:
                v_chan = interaction.guild.get_channel(int(voice_chan_id))
                if v_chan:
                    try:
                        await v_chan.delete()
                    except:
                        pass

            messages_history = []
            try:
                async for msg in channel.history(limit=500, oldest_first=True):
                    time_str = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    messages_history.append(f"[{time_str}] {msg.author.name}: {msg.content}")
            except:
                pass

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

                    try:
                        await log_chan.send(embed=log_embed, file=file)
                    except:
                        pass

        try:
            await interaction.response.send_message("⭐ ╎ **يرجى تقييم جودة الدعم المقدم من طاقم العمل:**", view=TicketRatingView(channel), ephemeral=True)
        except:
            pass

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
# ⚡ قائمة الردود السريعة للمشرفين
# ==============================================================================
class QuickRepliesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="أهلاً بك، تفضل بطرح مشكلتك.", emoji="👋", value="r1"),
            discord.SelectOption(label="يرجى الانتظار قليلاً جاري التحقق...", emoji="⏳", value="r2"),
            discord.SelectOption(label="تم حل المشكلة، هل تحتاج لمساعدة؟", emoji="✅", value="r3"),
            discord.SelectOption(label="يرجى عدم الإشارة المتكررة للإدارة.", emoji="⚠", value="r4")
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
# 🎛️ واجهات تحكم التذاكر الداخلية (بدون زر إعادة التعيين)
# ==============================================================================
class TicketInsideView(discord.ui.View):
    def __init__(self, guild_id: int, panel_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_name = panel_name
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

    @discord.ui.button(label="إنشاء فويس مؤقت", style=discord.ButtonStyle.success, emoji="🔊", custom_id="create_temp_voice_btn", row=2)
    async def create_temp_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = interaction.channel.category
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            interaction.user: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True)
        }
        
        db = load_tickets_db()
        t_info = db.get(str(guild.id), {}).get("active_tickets", {}).get(str(interaction.channel.id), {})
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

        await interaction.response.send_message(f"🔊 ╎ تم إنشاء غرفة صوتية مؤقتة خاصة بهذه التذكرة بنجاح: {voice_chan.mention}", ephemeral=False)

    @discord.ui.button(label="تنبيه ذكي", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="smart_ping_ticket_btn_v7", row=2)
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

    @discord.ui.button(label="طلب مسؤول أعلى", style=discord.ButtonStyle.primary, emoji="👑", custom_id="escalate_ticket_btn", row=3)
    async def escalate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        support_role_ids = ticket_info.get("support_role_ids", [])
        mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "الإدارة العليا"
        
        await interaction.channel.send(f"👑 ╎ **تصعيد عاجل:** قام {interaction.user.mention} بطلب تدخل مسؤول أعلى أو الإدارة (`{mentions}`). يرجى التفقد الفوري!")
        await interaction.response.send_message("✅ ╎ تم إرسال طلب التصعيد للإدارة بنجاح.", ephemeral=True)

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

        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
            await interaction.response.send_message(f"✅ ╎ تم منح العضو {member.mention} صلاحية الوصول وعرض هذه التذكرة.")
        except:
            await interaction.response.send_message("❌ ╎ حدث خطأ أثناء تعديل صلاحيات الروم.", ephemeral=True)


# ==============================================================================
# 📋 الأسئلة المخصصة وإنشاء التذاكر
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
                desc_str = data["description"][:100] if data.get("description") else "قسم التذاكر"
                
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
            options = [discord.SelectOption(label="لا توجد أقسام متاحة", value="none")]

        super().__init__(placeholder=f"📂 ✦ [ اختر قسم التذكرة المناسب لطلبك ]", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ ╎ لا توجد أقسام مفعلة حالياً في هذا البانل!", ephemeral=True)
            return
        
        sec_key = self.values[0]
        db = load_tickets_db()
        sec_data = db.get(str(self.guild_id), {}).get("panels", {}).get(self.panel_name, {}).get("sections", {}).get(sec_key, {})
        custom_q = sec_data.get("custom_question")
        
        if custom_q:
            await interaction.response.send_modal(CustomQuestionModal(self.panel_name, sec_key, custom_q))
        else:
            await interaction.response.send_modal(TicketReasonModal(self.panel_name, sec_key))


class CustomQuestionModal(discord.ui.Modal):
    def __init__(self, panel_name: str, section_key: str, question_text: str):
        super().__init__(title="📝 ╎ إجابة أسئلة القسم")
        self.panel_name = panel_name
        self.section_key = section_key
        
        self.answer_box = discord.ui.TextInput(
            label=f"السؤال: {question_text[:35]}",
            placeholder="اكتب إجابتك هنا بشكل مفصل...",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.add_item(self.answer_box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        ans = self.answer_box.value
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, ans, is_custom_answer=True)


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
        await interaction.response.defer(thinking=True, ephemeral=True)
        reason_text = self.problem_box.value
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, reason_text)


# ==============================================================================
# 🎛️ بانل التحكم وزر إعادة تعيين الفئة تحت الأقسام في البانل الأساسي
# ==============================================================================
class PanelControlView(discord.ui.View):
    def __init__(self, guild_id: int, panel_name: str, is_menu: bool):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_name = panel_name
        
        if is_menu:
            self.add_item(DynamicTicketSelect(guild_id, panel_name))
        else:
            db = load_tickets_db()
            sections = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {}).get("sections", {})
            for key, data in sections.items():
                emoji_val = data.get("emoji", "🎫")
                try:
                    if emoji_val.isdigit():
                        emoji_obj = discord.PartialEmoji(name="emoji", id=int(emoji_val))
                    else:
                        emoji_obj = emoji_val
                except:
                    emoji_obj = "🎫"

                btn = discord.ui.Button(label=data["label"][:80], style=discord.ButtonStyle.secondary, emoji=emoji_obj)
                async def btn_cb(inter, p=panel_name, k=key, d_q=data.get("custom_question")):
                    if d_q:
                        await inter.response.send_modal(CustomQuestionModal(p, k, d_q))
                    else:
                        await inter.response.send_modal(TicketReasonModal(p, k))
                btn.callback = btn_cb
                self.add_item(btn)

    # زر إعادة تعيين الفئة / البانل أصبح هنا تحت الأقسام في البانل الأساسي!
    @discord.ui.button(label="إعادة تعيين الفئة والبانل", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="reset_panel_main_btn_v7", row=4)
    async def reset_panel_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        p_data = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {})
        if not p_data:
            await interaction.response.send_message("❌ ╎ هذا البانل لم يعد موجوداً في قاعدة البيانات.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=p_data.get("title"),
            description=p_data.get("desc") + "\n\n____________________________________________________________________\n✦ **اختر القسم المناسب لطلبك من القائمة أدناه:**",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        if p_data.get("image_url"):
            embed.set_image(url=p_data["image_url"])
        embed.set_footer(text=f"Z I UO Community ✦ Panel: {self.panel_name}")

        is_m = p_data.get("display_type", "menu") == "menu"
        
        try:
            # تحديث الرسالة الحالية مباشرة دون إرسال بانل جديد بالخطأ
            await interaction.message.edit(embed=embed, view=PanelControlView(interaction.guild.id, self.panel_name, is_m))
            await interaction.response.send_message("🔄 ╎ تم إعادة تعيين وتحديث بانل الأقسام بنجاح دون إرسال رسائل مكررة!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ ╎ حدث خطأ أثناء التحديث: {e}", ephemeral=True)


async def create_user_ticket_execution(interaction: discord.Interaction, panel_name: str, section_key: str, input_text: str, is_custom_answer: bool = False):
    guild = interaction.guild
    db = load_tickets_db()
    guild_data = db.get(str(guild.id), {})
    
    active_tickets = guild_data.get("active_tickets", {})
    for ch_id, t_info in active_tickets.items():
        if t_info.get("user_id") == interaction.user.id:
            existing_chan = guild.get_channel(int(ch_id))
            if existing_chan:
                try:
                    await interaction.followup.send(f"❌ ╎ عذراً يا فنان، لديك تذكرة مفتوحة بالفعل ولا يمكنك فتح أكثر من تذكرة في نفس الوقت: {existing_chan.mention}", ephemeral=True)
                except:
                    pass
                return

    panel_data = guild_data.get("panels", {}).get(panel_name, {})
    section_data = panel_data.get("sections", {}).get(section_key)
    
    if not section_data:
        try:
            await interaction.followup.send("❌ ╎ عذراً، هذا القسم غير موجود أو تم حذفه.", ephemeral=True)
        except:
            pass
        return

    category_id_str = panel_data.get("category_id")
    category = guild.get_channel(int(category_id_str)) if category_id_str and category_id_str.isdigit() else None
    if not category:
        try:
            category = await guild.create_category("🎫 ╎ TICKETS ARCHIVE")
        except:
            pass

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
    
    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )
    except Exception as e:
        try:
            await interaction.followup.send(f"❌ ╎ حدث خطأ أثناء إنشاء روم التذكرة: {e}", ephemeral=True)
        except:
            pass
        return

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
    embed.add_field(name="🛡️ ╎ رتبة الدعم المسؤول", value=f"{staff_mentions}", inline=True)
    
    if is_custom_answer:
        q_title = section_data.get("custom_question", "إجابة العضو المطلوبة")
        embed.add_field(name=f"📝 ╎ {q_title}", value=f"```{input_text}```", inline=False)
    else:
        embed.add_field(name="📝 ╎ تفاصيل المشكلة", value=f"```{input_text}```", inline=False)
        
    embed.add_field(name="🛡 ╎ طاقم الدعم المختص", value=f"{staff_mentions}", inline=False)

    if section_data.get("image_url"):
        embed.set_image(url=section_data["image_url"])
        
    embed.set_footer(text=f"Z I UO Community ✦ Ticket ID: {ticket_channel.id}")

    try:
        sent_msg = await ticket_channel.send(
            content=f"🔔 ╎ تنبيه للطاقم: {interaction.user.mention} {staff_mentions}", 
            embed=embed, 
            view=TicketInsideView(guild.id, panel_name)
        )
        await sent_msg.pin()
    except:
        pass

    try:
        await interaction.followup.send(f"✅ ╎ تم إنشاء تذكرتك بنجاح بالرقم التسلسلي داخل الروم: {ticket_channel.mention}", ephemeral=True)
    except:
        pass


# ==============================================================================
# 🛠️ لوحة التحكم وإعدادات البانرات
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

    @discord.ui.button(label="إحصائيات المشرفين", style=discord.ButtonStyle.primary, emoji="📊", custom_id="setup_staff_stats_btn")
    async def show_staff_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_data = db.get(str(interaction.guild.id), {})
        staff_stats = guild_data.get("staff_stats", {})
        
        embed = discord.Embed(
            title="📊 ╎ لوحة إحصائيات وأداء طاقم الدعم",
            description="✦ نظرة تفصيلية على نشاط المشرفين وتقييمات الأعضاء لهم:",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        
        if not staff_stats:
            embed.add_field(name="لا توجد بيانات بعد", value="لم يتم استلام أو تقييم أي تذاكر بواسطة المشرفين حتى الآن.", inline=False)
        else:
            for s_id, data in staff_stats.items():
                member = interaction.guild.get_member(int(s_id))
                m_name = member.mention if member else f"<@{s_id}>"
                claimed = data.get("claimed", 0)
                total_s = data.get("total_stars", 0)
                count = data.get("ratings_count", 0)
                avg = round(total_s / count, 1) if count > 0 else 0.0
                
                embed.add_field(
                    name=f"👤 ╎ المشرف: {m_name}",
                    value=f"💼 التذاكر المستلمة: `{claimed}`\n⭐ متوسط التقييم: `{avg} / 5` ({count} تقييم)",
                    inline=False
                )
                
        embed.set_footer(text="Z I UO Staff Leaderboard System")
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
            db[guild_id_str] = {"panels": {}, "active_tickets": {}, "closed_tickets_archive": [], "staff_stats": {}}

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
        self.sections_box = discord.ui.TextInput(label="أسماء الأقسام (كل قسم في سطر)", placeholder="دعم فني\nشراء منتج\nتقديم إدارة", style=discord.TextStyle.paragraph, max_length=500, required=True)
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
        
        panel_data["temp_sections"] = sections_lines
        panel_data["temp_role_ids"] = role_ids
        save_tickets_db(db)

        await interaction.response.send_message(
            "❓ ╎ هل تريد إضافة وصف مخصص لكل فئة من الفئات التي قمت بإنشائها؟",
            view=AskDescriptionChoiceView(self.panel_name),
            ephemeral=True
        )


class AskDescriptionChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، أريد إضافة وصف", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ديناميكي منفصل لكل قسم تم إنشاؤه مسبقاً
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsDescriptionsModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي هذه الخطوة", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "❓ ╎ هل تريد تعيين (أسئلة مخصصة) لكل فئة قبل فتح التذكرة؟",
            view=AskCustomQuestionsChoiceView(self.panel_name, use_descriptions=False),
            ephemeral=True
        )


# ==============================================================================
# ✍️ مودال الوصف المنفصل تماماً لكل قسم على حدة (بدون سطر واحد لخبطة)
# ==============================================================================
class DynamicSectionsDescriptionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="✍️ ╎ وصف الفئات بشكل منفصل")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:  # أقصى حد مسموح من حقول الإدخال في الديسكورد هو 5 حقول
            box = discord.ui.TextInput(
                label=f"وصف قسم: {sec[:35]}",
                placeholder=f"اكتب الوصف الخاص بـ ({sec}) هنا...",
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
        db[str(interaction.guild.id)]["panels"][self.panel_name]["temp_descs"] = descs_list
        save_tickets_db(db)

        await interaction.response.send_message(
            "❓ ╎ هل تريد تعيين (أسئلة مخصصة) لكل فئة قبل فتح التذكرة؟",
            view=AskCustomQuestionsChoiceView(self.panel_name, use_descriptions=True),
            ephemeral=True
        )


class AskCustomQuestionsChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions

    @discord.ui.button(label="نعم، أريد تعيين أسئلة", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsQuestionsModal(self.panel_name, self.use_descriptions, sections))

    @discord.ui.button(label="لا، تخطي ونشر البانل", style=discord.ButtonStyle.secondary, emoji="🚀")
    async def no_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = PublishTargetChoiceView(self.panel_name, self.use_descriptions, use_questions=False)
        await interaction.response.send_message("📌 ╎ اختر مكان نشر البانل المطلوب:", view=view, ephemeral=True)


# ==============================================================================
# ❓ مودال الأسئلة المنفصل تماماً لكل قسم على حدة (القسم وتحته خانة السؤال الخاص به)
# ==============================================================================
class DynamicSectionsQuestionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, sections: list):
        super().__init__(title="❓ ╎ الأسئلة المخصصة لكل قسم")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.questions_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"سؤال قسم: {sec[:35]}",
                placeholder=f"اكتب السؤال الخاص بـ ({sec}) هنا...",
                style=discord.TextStyle.paragraph,
                max_length=300,
                required=True
            )
            self.questions_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        questions_list = []
        for sec, box in self.questions_map.items():
            questions_list.append(box.value.strip())

        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["temp_questions"] = questions_list
        save_tickets_db(db)

        view = PublishTargetChoiceView(self.panel_name, self.use_descriptions, use_questions=True)
        await interaction.response.send_message("📌 ╎ اختر مكان نشر البانل المطلوب:", view=view, ephemeral=True)


class PublishTargetChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    @discord.ui.button(label="نعم اريد ان انشر هنا", style=discord.ButtonStyle.success, emoji="📍")
    async def publish_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        await finalize_and_publish_panel(interaction, interaction.channel, self.panel_name, self.use_descriptions, self.use_questions)

    @discord.ui.button(label="سوف انشر في روم محدد", style=discord.ButtonStyle.primary, emoji="🎯")
    async def publish_in_specific_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر الروم المراد نشر البانل فيه...")
        for ch in interaction.guild.text_channels:
            if len(select.options) < 25:
                select.add_option(label=ch.name, value=str(ch.id), emoji="#️⃣")

        async def select_ch_cb(inter: discord.Interaction):
            target_ch_id = int(select.values[0])
            target_ch = inter.guild.get_channel(target_ch_id)
            if not target_ch:
                await inter.response.send_message("❌ ╎ الروم المحدد غير موجود!", ephemeral=True)
                return
            await finalize_and_publish_panel(inter, target_ch, self.panel_name, self.use_descriptions, self.use_questions)

        select.callback = select_ch_cb
        view.add_item(select)
        await interaction.response.edit_message(content="🎯 ╎ اختر الروم المخصص من القائمة أدناه:", view=view)


async def finalize_and_publish_panel(interaction: discord.Interaction, target_channel: discord.TextChannel, panel_name: str, use_descriptions: bool, use_questions: bool):
    db = load_tickets_db()
    guild_id_str = str(interaction.guild.id)
    panel_data = db[guild_id_str]["panels"][panel_name]

    sections_lines = panel_data.pop("temp_sections", [])
    role_ids = panel_data.pop("temp_role_ids", [])
    descs_list = panel_data.pop("temp_descs", []) if use_descriptions else []
    questions_list = panel_data.pop("temp_questions", []) if use_questions else []
    
    panel_data["sections"] = {}

    for idx, sec_name in enumerate(sections_lines):
        key = f"sec_{idx}_{int(datetime.datetime.utcnow().timestamp())}"
        sec_desc = descs_list[idx] if use_descriptions and idx < len(descs_list) else f"قسم خاص بـ {sec_name}"
        sec_q = questions_list[idx] if use_questions and idx < len(questions_list) else None

        panel_data["sections"][key] = {
            "label": sec_name,
            "description": sec_desc,
            "custom_question": sec_q,
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
    embed.set_footer(text=f"Z I UO Community ✦ Panel: {panel_name}")

    guild_id = interaction.guild.id
    is_menu = panel_data.get("display_type", "menu") == "menu"
    view = PanelControlView(guild_id, panel_name, is_menu)

    try:
        await target_channel.send(embed=embed, view=view)
    except:
        pass
    
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"🚀 ╎ **تم نشر بانل التذاكر ({panel_name}) بنجاح كامل في الروم {target_channel.mention}!**", ephemeral=True)
        else:
            await interaction.response.send_message(f"🚀 ╎ **تم نشر بانل التذاكر ({panel_name}) بنجاح كامل في الروم {target_channel.mention}!**", ephemeral=True)
    except:
        pass


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
                if (current_time - last_act) > 7200:
                    channel = guild.get_channel(int(channel_id_str))
                    if channel:
                        try:
                            await channel.send("⚠ ╎ **تنبيه تلقائي:** مرّت ساعتان بدون أي تفاعل أو نشاط في هذه التذكرة، سيتم إغلاقها تلقائياً.")
                            guild_data["active_tickets"].pop(channel_id_str, None)
                            t_info["status"] = "مغلقة تلقائياً (بعد ساعتين)"
                            t_info["closed_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                            if "closed_tickets_archive" not in guild_data:
                                guild_data["closed_tickets_archive"] = []
                            guild_data["closed_tickets_archive"].append(t_info)
                            save_tickets_db(db)
                            
                            voice_chan_id = t_info.get("temp_voice_id")
                            if voice_chan_id:
                                v_chan = guild.get_channel(int(voice_chan_id))
                                if v_chan:
                                    try:
                                        await v_chan.delete()
                                    except:
                                        pass

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
                "من خلال الأزرار أدناه يمكنك إدارة البانرات، إعداد الأسئلة المخصصة، ومتابعة إحصائيات المشرفين:"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Ultimate Tickets Core ✦ 2026")
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=False)


async def setup(bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
