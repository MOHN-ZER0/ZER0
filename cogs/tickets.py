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
            embed = discord.Embed(title="❤️ ╎ شكراً لتقييمك", description=f"شكراً لتقييمك الرائع ({stars_str})! سيتم إزالة التذكرة وتطهير السجل خلال 3 ثوانٍ...", color=0x00FF88)
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
                embed = discord.Embed(title="❌ ╎ خطأ في الصلاحيات", description="عذراً، لا تمتلك الصلاحية الكافية لحذف هذه التذكرة!", color=0xFF3333)
                await interaction.response.send_message(embed=embed, ephemeral=True)
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

            transcript_text = f"=== {interaction.guild.name.upper()} TICKET TRANSCRIPT: {channel.name} ===\n" + "\n".join(messages_history)
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
                    log_embed.set_footer(text=f"{interaction.guild.name} Security & Logging")

                    try:
                        await log_chan.send(embed=log_embed, file=file)
                    except:
                        pass

        try:
            embed_rate = discord.Embed(title="⭐ ╎ تقييم الدعم", description="يرجى تقييم جودة الدعم المقدم من طاقم العمل:", color=0x2B2D31)
            await interaction.response.send_message(embed=embed_rate, view=TicketRatingView(channel), ephemeral=True)
        except:
            pass

    @discord.ui.button(label="فتح التذكرة", style=discord.ButtonStyle.success, emoji="🔓", custom_id="confirm_unlock_ticket_btn")
    async def unlock_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            embed = discord.Embed(title="❌ ╎ خطأ", description="ليس لديك صلاحية فتح التذكرة!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        channel = interaction.channel
        default_role = interaction.guild.default_role
        overwrite = channel.overwrites_for(default_role)
        overwrite.send_messages = True
        await channel.set_permissions(default_role, overwrite=overwrite)
        embed = discord.Embed(title="🔓 ╎ تم فتح التذكرة", description="تم فتح التذكرة وإعادة تفعيل المحادثة بنجاح.", color=0x00FF88)
        await interaction.response.send_message(embed=embed)


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
        embed = discord.Embed(description=text, color=0x2B2D31)
        await interaction.channel.send(embed=embed)
        embed_resp = discord.Embed(title="✅ ╎ تم إرسال الرد", description="تم إرسال الرد السريع بنجاح.", color=0x00FF88)
        await interaction.response.send_message(embed=embed_resp, ephemeral=True)


# ==============================================================================
# 🔄 واجهة تأكيد تبديل أو إلغاء استلام التذكرة
# ==============================================================================
class ClaimConfirmView(discord.ui.View):
    def __init__(self, new_claimer: discord.Member, old_claimer_id: int, channel_id: str):
        super().__init__(timeout=60)
        self.new_claimer = new_claimer
        self.old_claimer_id = old_claimer_id
        self.channel_id = channel_id

    @discord.ui.button(label="موافقة وتبديل", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_switch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.old_claimer_id and not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(title="❌ ╎ خطأ", description="هذا الطلب مخصص للمشرف المستلم الحالي فقط للموافقة على التبديل!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(self.channel_id)
        if ticket_info:
            ticket_info["claimed_by"] = self.new_claimer.id
            save_tickets_db(db)

        old_claimer_obj = interaction.guild.get_member(self.old_claimer_id)
        old_mention = old_claimer_obj.mention if old_claimer_obj else f"<@{self.old_claimer_id}>"
        
        embed = discord.Embed(
            title="🔄 ╎ تم تبديل مشرف التذكرة",
            description=f"✦ تم نقل المسؤولية بنجاح من {old_mention} إلى {self.new_claimer.mention}",
            color=0x00FF88,
            timestamp=datetime.datetime.utcnow()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="رفض وحذف الطلب", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny_switch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.old_claimer_id and not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(title="❌ ╎ خطأ", description="هذا الطلب مخصص للمشرف المستلم الحالي فقط!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.message.delete()


# ==============================================================================
# 🎛️ واجهات تحكم التذاكر الداخلية
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
            embed = discord.Embed(title="❌ ╎ خطأ", description="هذه القناة ليست تذكرة نشطة في النظام!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        ticket_info = active_tickets[channel_id_str]
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        is_staff = interaction.user.guild_permissions.administrator
        if not is_staff and support_role_ids:
            if any(role.id in support_role_ids for role in interaction.user.roles):
                is_staff = True

        if not is_staff:
            embed = discord.Embed(title="🛡️ ╎ صلاحيات مرفوضة", description="عذراً، هذه الصلاحية مخصصة لفريق الدعم الفني فقط!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        old_claimer_id = ticket_info.get("claimed_by")

        # الحالة الأولى: المشرف الحالي هو نفسه من ضغط على زر الاستلام مرة أخرى
        if old_claimer_id == interaction.user.id:
            class UnclaimConfirmView(discord.ui.View):
                def __init__(self, ch_id):
                    super().__init__(timeout=30)
                    self.ch_id = ch_id

                @discord.ui.button(label="نعم، إلغاء الاستلام", style=discord.ButtonStyle.danger, emoji="هن")
                async def confirm_unclaim(self, inter: discord.Interaction, btn: discord.ui.Button):
                    db_inner = load_tickets_db()
                    t_inf = db_inner.get(str(inter.guild.id), {}).get("active_tickets", {}).get(self.ch_id)
                    if t_inf:
                        t_inf.pop("claimed_by", None)
                        save_tickets_db(db_inner)
                    embed_res = discord.Embed(title="💼 ╎ تم إلغاء الاستلام", description=f"✦ قام {inter.user.mention} بإلغاء استلام التذكرة وأصبحت متاحة للجميع.", color=0xFF3333)
                    await inter.response.edit_message(embed=embed_res, view=None)

                @discord.ui.button(label="تجاهل", style=discord.ButtonStyle.secondary, emoji="✖")
                async def cancel_unclaim(self, inter: discord.Interaction, btn: discord.ui.Button):
                    await inter.message.delete()

            embed_ask = discord.Embed(title="💼 ╎ حالة التذكرة", description="أنت مسجل بالفعل كالمشرف المستلم لهذه التذكرة.\nهل تريد **إلغاء الاستلام** وإتاحتها للآخرين؟", color=0xFFA500)
            await interaction.response.send_message(embed=embed_ask, view=UnclaimConfirmView(channel_id_str), ephemeral=True)
            return

        # الحالة الثانية: مشرف آخر يحاول استلام تذكرة مستلمة بالفعل
        if old_claimer_id and old_claimer_id != interaction.user.id:
            old_claimer_obj = interaction.guild.get_member(old_claimer_id)
            old_mention = old_claimer_obj.mention if old_claimer_obj else f"<@{old_claimer_id}>"
            
            embed_switch = discord.Embed(
                title="⚠️ ╎ التذكرة مستلمة بالفعل",
                description=f"✦ هذه التذكرة مستلمة حالياً بواسطة {old_mention}.\nهل توافق على تبديل المشرف وإعطاء المسؤولية لـ {interaction.user.mention}؟",
                color=0xFFA500
            )
            await interaction.channel.send(
                content=f"🔔 ╎ تنبيه للمشرف الأساسي {old_mention}:",
                embed=embed_switch,
                view=ClaimConfirmView(interaction.user, old_claimer_id, channel_id_str)
            )
            embed_sent = discord.Embed(title="✅ ╎ تم إرسال الطلب", description="تم إرسال طلب تبديل المشرف للموافقة عليه.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_sent, ephemeral=True)
            return

        # الحالة الطبيعية: تذكرة جديدة بدون مشرف
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

        embed = discord.Embed(title="🔊 ╎ تم إنشاء الفويس المؤقت", description=f"تم إنشاء غرفة صوتية مؤقتة خاصة بهذه التذكرة بنجاح: {voice_chan.mention}", color=0x00FF88)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @discord.ui.button(label="تنبيه ذكي", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="smart_ping_ticket_btn_v7", row=2)
    async def smart_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        
        if not ticket_info:
            embed_err = discord.Embed(title="❌ ╎ خطأ", description="خطأ في قراءة بيانات التذكرة.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        creator_id = ticket_info.get("user_id")
        support_role_ids = ticket_info.get("support_role_ids", [])
        
        if interaction.user.id == creator_id:
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "فريق الدعم الفني"
            embed_ping = discord.Embed(title="🔔 ╎ تنبيه جديد", description=f"تنبيه من صاحب التذكرة {interaction.user.mention} إلى {mentions}: يرجى الرد في أقرب وقت!", color=0xFFA500)
            await interaction.channel.send(embed=embed_ping)
            embed_ok = discord.Embed(title="✅ ╎ تم الإرسال", description="تم إرسال التنبيه لطاقم الدعم.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok, ephemeral=True)
        else:
            creator_obj = interaction.guild.get_member(creator_id)
            creator_mention = creator_obj.mention if creator_obj else f"<@{creator_id}>"
            embed_ping2 = discord.Embed(title="🔔 ╎ تنبيه إداري", description=f"تنبيه من الإدارة إلى العضو {creator_mention}: يرجى الرد على التذكرة لاستكمال الإجراءات.", color=0xFFA500)
            await interaction.channel.send(embed=embed_ping2)
            embed_ok2 = discord.Embed(title="✅ ╎ تم الإرسال", description="تم تنبيه العضو بنجاح.", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok2, ephemeral=True)

    @discord.ui.button(label="طلب مسؤول أعلى", style=discord.ButtonStyle.primary, emoji="👑", custom_id="escalate_ticket_btn", row=3)
    async def escalate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        ticket_info = db.get(guild_id_str, {}).get("active_tickets", {}).get(channel_id_str, {})
        higher_role_id = ticket_info.get("higher_support_role_id")
        
        if higher_role_id:
            mentions = f"<@&{higher_role_id}>"
        else:
            support_role_ids = ticket_info.get("support_role_ids", [])
            mentions = " ".join([f"<@&{r_id}>" for r_id in support_role_ids]) if support_role_ids else "الإدارة العليا"
        
        embed_esc = discord.Embed(title="👑 ╎ تصعيد عاجل", description=f"قام {interaction.user.mention} بطلب تدخل مسؤول أعلى أو الإدارة (`{mentions}`). يرجى التفقد الفوري!", color=0xFF3333)
        await interaction.channel.send(embed=embed_esc)
        embed_done = discord.Embed(title="✅ ╎ تم التصعيد", description="تم إرسال طلب التصعيد للإدارة بنجاح.", color=0x00FF88)
        await interaction.response.send_message(embed=embed_done, ephemeral=True)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_v7_btn", row=3)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed_close = discord.Embed(title="🔒 ╎ إغلاق التذكرة", description="اختر الإجراء المطلوب لتنفيذه على التذكرة:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_close, view=CloseConfirmationView(), ephemeral=True)


class AddMemberModal(discord.ui.Modal, title="➕ ╎ إضافة عضو إلى التذكرة"):
    member_box = discord.ui.TextInput(label="أيدي العضو (User ID)", placeholder="اكتب أيدي العضو هنا...", max_length=30, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        member_id_text = self.member_box.value.strip()
        if not member_id_text.isdigit():
            embed = discord.Embed(title="❌ ╎ خطأ", description="يرجى إدخال أيدي صحيح ومطابق!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        member = interaction.guild.get_member(int(member_id_text))
        if not member:
            embed = discord.Embed(title="❌ ╎ خطأ", description="لم يتم العثور على هذا العضو في السيرفر!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
            embed = discord.Embed(title="✅ ╎ تم الإضافة", description=f"تم منح العضو {member.mention} صلاحية الوصول وعرض هذه التذكرة.", color=0x00FF88)
            await interaction.response.send_message(embed=embed)
        except:
            embed = discord.Embed(title="❌ ╎ خطأ", description="حدث خطأ أثناء تعديل صلاحيات الروم.", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)


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
            embed = discord.Embed(title="❌ ╎ خطأ", description="لا توجد أقسام مفعلة حالياً في هذا البانل!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        sec_key = self.values[0]
        db = load_tickets_db()
        sec_data = db.get(str(self.guild_id), {}).get("panels", {}).get(self.panel_name, {}).get("sections", {}).get(sec_key, {})
        custom_q = sec_data.get("custom_questions") # قائمة أسئلة القسم أو فارغة
        
        panel_data = db.get(str(self.guild_id), {}).get("panels", {}).get(self.panel_name, {})
        has_questions = panel_data.get("has_questions", False)

        if has_questions and custom_q:
            await interaction.response.send_modal(CustomMultiQuestionModal(self.panel_name, sec_key, custom_q))
        else:
            await interaction.response.send_modal(TicketReasonModal(self.panel_name, sec_key))


class CustomMultiQuestionModal(discord.ui.Modal):
    def __init__(self, panel_name: str, section_key: str, questions_list: list):
        super().__init__(title="📝 ╎ إجابة أسئلة التذكرة")
        self.panel_name = panel_name
        self.section_key = section_key
        self.inputs_map = {}

        for idx, q_text in enumerate(questions_list[:5]):
            box = discord.ui.TextInput(
                label=f"سؤال {idx+1}: {q_text[:30]}",
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
        
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, answers_combined, is_custom_answer=True)


class TicketReasonModal(discord.ui.Modal, title="🎫 ╎ تفاصيل طلب التذكرة"):
    problem_box = discord.ui.TextInput(
        label="ما هي المشكلة أو الطلب الذي ستتعامل به؟",
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
        await create_user_ticket_execution(interaction, self.panel_name, self.section_key, [reason_text])


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
            p_data = db.get(str(guild_id), {}).get("panels", {}).get(panel_name, {})
            sections = p_data.get("sections", {})
            has_questions = p_data.get("has_questions", False)

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
                async def btn_cb(inter, p=panel_name, k=key, q_list=data.get("custom_questions"), h_q=has_questions):
                    if h_q and q_list:
                        await inter.response.send_modal(CustomMultiQuestionModal(p, k, q_list))
                    else:
                        await inter.response.send_modal(TicketReasonModal(p, k))
                btn.callback = btn_cb
                self.add_item(btn)

    @discord.ui.button(label="إعادة تعيين الفئة والبانل", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="reset_panel_main_btn_v7", row=4)
    async def reset_panel_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        p_data = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {})
        if not p_data:
            embed_err = discord.Embed(title="❌ ╎ خطأ", description="هذا البانل لم يعد موجوداً في قاعدة البيانات.", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=p_data.get("title"),
            description=p_data.get("desc") + "\n\n____________________________________________________________________\n✦ **اختر القسم المناسب لطلبك من القائمة أدناه:**",
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        if p_data.get("image_url"):
            embed.set_image(url=p_data["image_url"])
        embed.set_footer(text=f"{interaction.guild.name} ✦ Panel: {self.panel_name}")

        is_m = p_data.get("display_type", "menu") == "menu"
        
        try:
            await interaction.message.edit(embed=embed, view=PanelControlView(interaction.guild.id, self.panel_name, is_m))
            embed_ok = discord.Embed(title="🔄 ╎ تم التحديث", description="تم إعادة تعيين وتحديث بانل الأقسام بنجاح دون إرسال رسائل مكررة!", color=0x00FF88)
            await interaction.response.send_message(embed=embed_ok, ephemeral=True)
        except Exception as e:
            embed_ex = discord.Embed(title="❌ ╎ خطأ", description=f"حدث خطأ أثناء التحديث: {e}", color=0xFF3333)
            await interaction.response.send_message(embed=embed_ex, ephemeral=True)


async def create_user_ticket_execution(interaction: discord.Interaction, panel_name: str, section_key: str, answers_list: list, is_custom_answer: bool = False):
    guild = interaction.guild
    db = load_tickets_db()
    guild_data = db.get(str(guild.id), {})
    
    active_tickets = guild_data.get("active_tickets", {})
    for ch_id, t_info in active_tickets.items():
        if t_info.get("user_id") == interaction.user.id:
            existing_chan = guild.get_channel(int(ch_id))
            if existing_chan:
                try:
                    embed_dup = discord.Embed(title="❌ ╎ تذكرة مفتوحة", description=f"عذراً يا فنان، لديك تذكرة مفتوحة بالفعل ولا يمكنك فتح أكثر من تذكرة في نفس الوقت: {existing_chan.mention}", color=0xFF3333)
                    await interaction.followup.send(embed=embed_dup, ephemeral=True)
                except:
                    pass
                return

    panel_data = guild_data.get("panels", {}).get(panel_name, {})
    section_data = panel_data.get("sections", {}).get(section_key)
    
    if not section_data:
        try:
            embed_no = discord.Embed(title="❌ ╎ خطأ", description="عذراً، هذا القسم غير موجود أو تم حذفه.", color=0xFF3333)
            await interaction.followup.send(embed=embed_no, ephemeral=True)
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
            embed_err = discord.Embed(title="❌ ╎ خطأ", description=f"حدث خطأ أثناء إنشاء روم التذكرة: {e}", color=0xFF3333)
            await interaction.followup.send(embed=embed_err, ephemeral=True)
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
        "higher_support_role_id": higher_role_id,
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
    
    if is_custom_answer and section_data.get("custom_questions"):
        questions = section_data.get("custom_questions", [])
        for idx, ans in enumerate(answers_list):
            q_title = questions[idx] if idx < len(questions) else f"سؤال {idx+1}"
            embed.add_field(name=f"📝 ╎ {q_title}", value=f"```{ans}```", inline=False)
    else:
        reason_val = answers_list[0] if answers_list else "لا توجد تفاصيل"
        embed.add_field(name="📝 ╎ تفاصيل المشكلة", value=f"```{reason_val}```", inline=False)
        
    embed.add_field(name="🛡 ╎ طاقم الدعم المختص", value=f"{staff_mentions}", inline=False)

    if section_data.get("image_url"):
        embed.set_image(url=section_data["image_url"])
        
    embed.set_footer(text=f"{guild.name} ✦ Ticket ID: {ticket_channel.id}")

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
        embed_suc = discord.Embed(title="✅ ╎ تم إنشاء التذكرة", description=f"تم إنشاء تذكرتك بنجاح بالرقم التسلسلي داخل الروم: {ticket_channel.mention}", color=0x00FF88)
        await interaction.followup.send(embed=embed_suc, ephemeral=True)
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
            embed_err = discord.Embed(title="⚠️ ╎ تنبيه", description="لا توجد أي بانلات تذاكر مسجلة لتعديلها.", color=0xFFA500)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
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
        embed_sel = discord.Embed(title="⚙️ ╎ تعديل البانل", description="اختر البانل المراد تعديله من القائمة أدناه:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_sel, view=view, ephemeral=True)

    @discord.ui.button(label="حذف بانل تذكرة", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="setup_delete_panel_btn_v7")
    async def delete_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panels = db.get(guild_id_str, {}).get("panels", {})
        if not panels:
            embed_err = discord.Embed(title="⚠ ╎ تنبيه", description="لا توجد بانلات تذاكر لحذفها.", color=0xFFA500)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="اختر البانل المراد حذفه...")
        for name in panels.keys():
            select.add_option(label=name, value=name)

        async def del_cb(inter: discord.Interaction):
            chosen = select.values[0]
            db[guild_id_str]["panels"].pop(chosen, None)
            save_tickets_db(db)
            embed_del = discord.Embed(title="🗑️ ╎ تم الحذف", description=f"تم حذف البانل **{chosen}** بنجاح تام!", color=0x00FF88)
            await inter.response.send_message(embed=embed_del, ephemeral=True)

        select.callback = del_cb
        view.add_item(select)
        embed_del_sel = discord.Embed(title="🗑️ ╎ حذف البانل", description="اختر البانل المراد حذفه:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_del_sel, view=view, ephemeral=True)

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
                
        embed.set_footer(text=f"{interaction.guild.name} Staff Leaderboard System")
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
            embed = discord.Embed(title="❌ ╎ خطأ", description="يرجى إدخال أيدي صحيح ومطابق لروم اللوج!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in db:
            db[guild_id_str] = {}
        
        db[guild_id_str]["log_channel_id"] = ch_id_text
        save_tickets_db(db)

        embed = discord.Embed(title="✅ ╎ تم الحفظ", description=f"تم ربط روم اللوج بنجاح بالروم المخصص: <#{ch_id_text}>", color=0x00FF88)
        await interaction.response.send_message(embed=embed, ephemeral=True)


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
            embed = discord.Embed(title="❌ ╎ خطأ", description="أيدي فئة التذاكر غير صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed=embed, ephemeral=True)
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

        embed = discord.Embed(title="✅ ╎ حفظ بيانات البانل", description=f"تم حفظ بيانات البانل **{p_name}** بنجاح!\n✦ اختر الآن طريقة وشكل عرض الأقسام:", color=0x00FF88)
        await interaction.response.send_message(
            embed=embed,
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


class SectionsConfigModal(discord.ui.Modal, title="📝 ╎ أسماء الفئات والأقسام"):
    def __init__(self, panel_name: str):
        super().__init__()
        self.panel_name = panel_name
        self.sections_box = discord.ui.TextInput(
            label="أسماء الفئات (كل فئة في سطر)",
            placeholder="دعم فني\nشراء منتج\nتقديم إدارة",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.sections_box)

    async def on_submit(self, interaction: discord.Interaction):
        sections_lines = [s.strip() for s in self.sections_box.value.split("\n") if s.strip()]

        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        panel_data = db[guild_id_str]["panels"][self.panel_name]
        
        panel_data["temp_sections"] = sections_lines
        save_tickets_db(db)

        embed = discord.Embed(title="❓ ╎ رتب الدعم", description="هل تريد إضافة رتب دعم لكل فئة من الفئات التي قمت بإنشائها؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskSupportRolesChoiceView(self.panel_name),
            ephemeral=True
        )


class AskSupportRolesChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، إضافة رتب دعم", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsSupportRolesModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي رتب الدعم", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        guild_id_str = str(interaction.guild.id)
        sections = db.get(guild_id_str, {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        db[guild_id_str]["panels"][self.panel_name]["temp_roles_map"] = {sec: [] for sec in sections}
        save_tickets_db(db)

        embed = discord.Embed(title="❓ ╎ وصف الفئات", description="هل تريد إضافة وصف مخصص لكل فئة؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskDescriptionChoiceView(self.panel_name),
            ephemeral=True
        )


class DynamicSectionsSupportRolesModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="🛡️ ╎ رتب الدعم لكل فئة")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"آيدي رتب الدعم لـ: {sec[:25]}",
                placeholder="اكتب آيديهات الرتب (كل آيدي في سطر)...",
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
        db[str(interaction.guild.id)]["panels"][self.panel_name]["temp_roles_map"] = roles_map
        save_tickets_db(db)

        embed = discord.Embed(title="❓ ╎ وصف الفئات", description="هل تريد إضافة وصف مخصص لكل فئة؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskDescriptionChoiceView(self.panel_name),
            ephemeral=True
        )


class AskDescriptionChoiceView(discord.ui.View):
    def __init__(self, panel_name: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name

    @discord.ui.button(label="نعم، أريد إضافة وصف", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsDescriptionsModal(self.panel_name, sections))

    @discord.ui.button(label="لا، تخطي هذه الخطوة", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="❓ ╎ أسئلة التذكرة", description="هل تريد تفعيل أسئلة مخصصة تظهر للعضو عند فتح التذكرة؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskCustomQuestionsChoiceView(self.panel_name, use_descriptions=False),
            ephemeral=True
        )


class DynamicSectionsDescriptionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, sections: list):
        super().__init__(title="✍️ ╎ وصف الفئات بشكل منفصل")
        self.panel_name = panel_name
        self.inputs_map = {}

        for sec in sections[:5]:
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

        embed = discord.Embed(title="❓ ╎ أسئلة التذكرة", description="هل تريد تفعيل أسئلة مخصصة تظهر للعضو عند فتح التذكرة؟", color=0x2B2D31)
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

    @discord.ui.button(label="نعم، أريد تعيين أسئلة", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(DynamicSectionsQuestionsModal(self.panel_name, self.use_descriptions, sections))

    @discord.ui.button(label="لا، بدون أسئلة", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="👑 ╎ رتبة الدعم العليا", description="هل تريد تعيين (رتبة دعم عليا) خاصة بالتذاكر؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskHigherRoleChoiceView(self.panel_name, use_descriptions=self.use_descriptions, use_questions=False),
            ephemeral=True
        )


class DynamicSectionsQuestionsModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, sections: list):
        super().__init__(title="❓ ╎ الأسئلة المخصصة")
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

        embed = discord.Embed(title="👑 ╎ رتبة الدعم العليا", description="هل تريد تعيين (رتبة دعم عليا) خاصة بالتذاكر؟", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=AskHigherRoleChoiceView(self.panel_name, use_descriptions=self.use_descriptions, use_questions=True),
            ephemeral=True
        )


class AskHigherRoleChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    @discord.ui.button(label="نعم، أريد التعيين", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="👑 ╎ خيارات رتبة الدعم العليا", description="اختر طريقة تعيين رتبة الدعم العليا المناسبة لك:", color=0x2B2D31)
        await interaction.response.send_message(
            embed=embed,
            view=HigherRoleTypeChoiceView(self.panel_name, self.use_descriptions, self.use_questions),
            ephemeral=True
        )

    @discord.ui.button(label="لا، تخطي", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = PublishTargetChoiceView(self.panel_name, self.use_descriptions, self.use_questions, higher_mode="none")
        embed_pub = discord.Embed(title="📌 ╎ نشر البانل", description="اختر مكان نشر البانل المطلوب:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_pub, view=view, ephemeral=True)


class HigherRoleTypeChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    @discord.ui.button(label="رتبة واحدة للكل", style=discord.ButtonStyle.primary, emoji="⭐")
    async def single_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SingleHigherRoleModal(self.panel_name, self.use_descriptions, self.use_questions))

    @discord.ui.button(label="تخصيص رتب لكل فئة", style=discord.ButtonStyle.success, emoji="🛠️")
    async def custom_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = load_tickets_db()
        sections = db.get(str(interaction.guild.id), {}).get("panels", {}).get(self.panel_name, {}).get("temp_sections", [])
        await interaction.response.send_modal(CustomHigherRolesModal(self.panel_name, self.use_descriptions, self.use_questions, sections))


class SingleHigherRoleModal(discord.ui.Modal, title="⭐ ╎ رتبة دعم عليا موحدة للكل"):
    role_box = discord.ui.TextInput(label="آيدي رتبة الدعم العليا", placeholder="اكتب آيدي الرتبة هنا...", max_length=30, required=True)

    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool):
        super().__init__()
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions

    async def on_submit(self, interaction: discord.Interaction):
        r_text = self.role_box.value.strip()
        if not r_text.isdigit():
            embed_err = discord.Embed(title="❌ ╎ خطأ", description="يرجى إدخال آيدي رتبة صحيح!", color=0xFF3333)
            await interaction.response.send_message(embed=embed_err, ephemeral=True)
            return

        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["temp_single_higher"] = int(r_text)
        save_tickets_db(db)

        view = PublishTargetChoiceView(self.panel_name, self.use_descriptions, self.use_questions, higher_mode="single")
        embed_pub = discord.Embed(title="📌 ╎ نشر البانل", description="اختر مكان نشر البانل المطلوب:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_pub, view=view, ephemeral=True)


class CustomHigherRolesModal(discord.ui.Modal):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, sections: list):
        super().__init__(title="🛠️ ╎ رتب الدعم العليا لكل فئة")
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.inputs_map = {}

        for sec in sections[:5]:
            box = discord.ui.TextInput(
                label=f"رتبة عليا لقسم: {sec[:25]}",
                placeholder="اكتب آيدي الرتبة...",
                max_length=30,
                required=True
            )
            self.inputs_map[sec] = box
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        map_higher = {}
        for sec, box in self.inputs_map.items():
            val = box.value.strip()
            if val.isdigit():
                map_higher[sec] = int(val)

        db = load_tickets_db()
        db[str(interaction.guild.id)]["panels"][self.panel_name]["temp_map_higher"] = map_higher
        save_tickets_db(db)

        view = PublishTargetChoiceView(self.panel_name, self.use_descriptions, self.use_questions, higher_mode="custom")
        embed_pub = discord.Embed(title="📌 ╎ نشر البانل", description="اختر مكان نشر البانل المطلوب:", color=0x2B2D31)
        await interaction.response.send_message(embed=embed_pub, view=view, ephemeral=True)


class PublishTargetChoiceView(discord.ui.View):
    def __init__(self, panel_name: str, use_descriptions: bool, use_questions: bool, higher_mode: str):
        super().__init__(timeout=60)
        self.panel_name = panel_name
        self.use_descriptions = use_descriptions
        self.use_questions = use_questions
        self.higher_mode = higher_mode

    @discord.ui.button(label="نعم اريد ان انشر هنا", style=discord.ButtonStyle.success, emoji="📍")
    async def publish_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        await finalize_and_publish_panel(interaction, interaction.channel, self.panel_name, self.use_descriptions, self.use_questions, self.higher_mode)

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
                embed_err = discord.Embed(title="❌ ╎ خطأ", description="الروم المحدد غير موجود!", color=0xFF3333)
                await inter.response.send_message(embed=embed_err, ephemeral=True)
                return
            await finalize_and_publish_panel(inter, target_ch, self.panel_name, self.use_descriptions, self.use_questions, self.higher_mode)

        select.callback = select_ch_cb
        view.add_item(select)
        embed_sel = discord.Embed(title="🎯 ╎ اختيار روم النشر", description="اختر الروم المخصص من القائمة أدناه:", color=0x2B2D31)
        await interaction.response.edit_message(embed=embed_sel, view=view)


async def finalize_and_publish_panel(interaction: discord.Interaction, target_channel: discord.TextChannel, panel_name: str, use_descriptions: bool, use_questions: bool, higher_mode: str):
    db = load_tickets_db()
    guild_id_str = str(interaction.guild.id)
    panel_data = db[guild_id_str]["panels"][panel_name]

    sections_lines = panel_data.pop("temp_sections", [])
    roles_map = panel_data.pop("temp_roles_map", {})
    descs_list = panel_data.pop("temp_descs", []) if use_descriptions else []
    questions_list = panel_data.pop("temp_questions", []) if use_questions else []
    
    single_higher = panel_data.pop("temp_single_higher", None)
    map_higher = panel_data.pop("temp_map_higher", {})
    
    panel_data["has_questions"] = use_questions
    panel_data["sections"] = {}

    for idx, sec_name in enumerate(sections_lines):
        key = f"sec_{idx}_{int(datetime.datetime.utcnow().timestamp())}"
        sec_desc = descs_list[idx] if use_descriptions and idx < len(descs_list) else f"قسم خاص بـ {sec_name}"
        sec_roles = roles_map.get(sec_name, [])
        
        sec_higher = None
        if higher_mode == "single":
            sec_higher = single_higher
        elif higher_mode == "custom":
            sec_higher = map_higher.get(sec_name)

        panel_data["sections"][key] = {
            "label": sec_name,
            "description": sec_desc,
            "custom_questions": questions_list if use_questions else [],
            "emoji": "🎫",
            "support_role_ids": sec_roles,
            "higher_support_role_id": sec_higher,
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
    embed.set_footer(text=f"{interaction.guild.name} ✦ Panel: {panel_name}")

    guild_id = interaction.guild.id
    is_menu = panel_data.get("display_type", "menu") == "menu"
    view = PanelControlView(guild_id, panel_name, is_menu)

    try:
        await target_channel.send(embed=embed, view=view)
    except:
        pass
    
    embed_done = discord.Embed(title="🚀 ╎ تم نشر البانل", description=f"تم نشر بانل التذاكر ({panel_name}) بنجاح كامل في الروم {target_channel.mention}!", color=0x00FF88)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed_done, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed_done, ephemeral=True)
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
                            embed_warn = discord.Embed(title="⚠ ╎ تنبيه تلقائي", description="مرّت ساعتان بدون أي تفاعل أو نشاط في هذه التذكرة، سيتم إغلاقها تلقائياً.", color=0xFFA500)
                            await channel.send(embed=embed_warn)
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
            title=f"⚙️ ╎ مركز إدارة ونظام التذاكر المتقدم - {interaction.guild.name}",
            description=(
                "مرحباً بك في لوحة تحكم التذاكر المركزية الشاملة.\n"
                "من خلال الأزرار أدناه يمكنك إدارة البانرات، إعداد الأسئلة المخصصة، ومتابعة إحصائيات المشرفين:"
            ),
            color=0x2B2D31,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"{interaction.guild.name} Tickets Core ✦ 2026")
        await interaction.response.send_message(embed=embed, view=TicketSetupMainView(), ephemeral=False)


async def setup(bot):
    await bot.add_cog(ZiuoUltimateTicketsCog(bot))
