import discord
from discord import app_commands
from discord.ext import commands
import datetime
import re
from collections import defaultdict, deque

# ==============================================================================
# 🛡️ الإعدادات العامة وقاعدة بيانات الحماية الشاملة (Ultimate Security Config)
# ==============================================================================
SECURITY_SETTINGS = {
    "anti_invite": True,          # منع روابط ديسكورد والترويج
    "anti_links": True,           # منع الروابط الخارجية الضارة
    "anti_spam": True,            # منع الفلود والرسائل المتتالية السريعة
    "anti_caps": True,            # منع الحروف الكبيرة المفرطة (تشويه بصري)
    "anti_repeat": True,          # منع تكرار نفس الرسالة
    "anti_emoji": True,           # منع سبام الإيموجي الكثيرة
    "max_caps_percent": 75,       # نسبة الحروف الكبيرة المسموحة في الرسالة
    "max_emojis": 6,              # أقصى عدد مسموح به من الإيموجي في الرسالة الواحدة
    "punishment_mode": "timeout", # خيارات العقوبة التلقائية: timeout أو warn أو delete
    "timeout_duration": 300       # مدة التايم آوت بالثواني عند تكرار المخالفة (مثلاً 5 دقائق)
}

# قاعدة بيانات الكلمات المسيئة والمحظورة (قابلة للتعديل الحي بالكامل)
BAD_WORDS_DB = [
    "طز", "عمك", "متخلف", "قحب", "وسخ", "كلب", "منقرض", 
    "هكر", "شاتم", "حسابات للبيع", "فواكه للبيع", "نيك", "قحبة"
]

# تتبع السجلات والسبام (Anti-Flood / Anti-Repeat Caches)
USER_MESSAGE_TRACKER = defaultdict(lambda: deque(maxlen=5))
USER_LAST_MESSAGE = {}

# ==============================================================================
# 🎛️ لوحة التحكم التفاعلية المتقدمة (Interactive Dashboard UI)
# ==============================================================================
class UltimateSecurityControlPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.update_buttons()

    def update_buttons(self):
        self.btn_invite.label = f"مانع الدعوات: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_invite'] else '[معطل ❌]'}"
        self.btn_invite.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_invite'] else discord.ButtonStyle.red

        self.btn_links.label = f"مانع الروابط: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_links'] else '[معطل ❌]'}"
        self.btn_links.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_links'] else discord.ButtonStyle.red

        self.btn_spam.label = f"مانع السبام والفلود: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_spam'] else '[معطل ❌]'}"
        self.btn_spam.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_spam'] else discord.ButtonStyle.red

        self.btn_caps.label = f"مانع الحروف الكبيرة: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_caps'] else '[معطل ❌]'}"
        self.btn_caps.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_caps'] else discord.ButtonStyle.red

        self.btn_repeat.label = f"مانع التكرار: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_repeat'] else '[معطل ❌]'}"
        self.btn_repeat.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_repeat'] else discord.ButtonStyle.red

        self.btn_emoji.label = f"مانع سبام الإيموجي: {'[مفعل ✅]' if SECURITY_SETTINGS['anti_emoji'] else '[معطل ❌]'}"
        self.btn_emoji.style = discord.ButtonStyle.green if SECURITY_SETTINGS['anti_emoji'] else discord.ButtonStyle.red

    @discord.ui.button(label="مانع الدعوات", style=discord.ButtonStyle.green, custom_id="sec_invite", row=0)
    async def btn_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_invite'] = not SECURITY_SETTINGS['anti_invite']
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="مانع الروابط", style=discord.ButtonStyle.green, custom_id="sec_links", row=0)
    async def btn_links(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_links'] = not SECURITY_SETTINGS['anti_links']
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="مانع السبام", style=discord.ButtonStyle.green, custom_id="sec_spam", row=1)
    async def btn_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_spam'] = not SECURITY_SETTINGS['anti_spam']
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="مانع الحروف الكبيرة", style=discord.ButtonStyle.green, custom_id="sec_caps", row=1)
    async def btn_caps(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_caps'] = not SECURITY_SETTINGS['anti_caps']
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="مانع التكرار", style=discord.ButtonStyle.green, custom_id="sec_repeat", row=2)
    async def btn_repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_repeat'] = not SECURITY_SETTINGS['anti_repeat']
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="مانع سبام الإيموجي", style=discord.ButtonStyle.green, custom_id="sec_emoji", row=2)
    async def btn_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر مخصص لمدراء السيرفر فقط!", ephemeral=True)
            return
        SECURITY_SETTINGS['anti_emoji'] = not SECURITY_SETTINGS['anti_emoji']
        self.update_buttons()
        await interaction.response.edit_message(view=self)


# ==============================================================================
# 🛡️ Cog الحماية والفلترة الشامل (Ultimate Security Cog Core)
# ==============================================================================
class UltimateSecurityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_pattern = re.compile(r"(https?://)?(www\.)?(discord\.(gg|io|me|li|club)|discord\.com/invite|discordapp\.com/invite)/\w+", re.IGNORECASE)
        self.url_pattern = re.compile(r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)", re.IGNORECASE)

    # ==========================================================================
    # ⚙ أوامر الإدارة والتحكم في الحماية (Admin Commands)
    # ==========================================================================
    security_group = app_commands.Group(name="security", description="[إدارة الحماية] لوحة التحكم والأوامر الخاصة بنظام الأمان")

    @security_group.command(name="panel", description="عرض لوحة التحكم التفاعلية الشاملة لإدارة أنظمة الحماية بالكامل")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ ╎ لـوحـة تـحـكـم نـظـام الـحـمـاية والـأمان الـشـامـل 〣 ｢ZIUO PRO｣",
            description=(
                "> أهلاً بك يا أسطورة في نظام الحماية والفلترة المركزي لسيرفر ZIUO.\n"
                "> يمكنك تفعيل أو تعطيل أي نظام أمان فورياً عبر الأزرار أدناه:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x111111,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Enterprise Security & Automod Engine")
        await interaction.response.send_message(embed=embed, view=UltimateSecurityControlPanel(), ephemeral=True)

    # مجموعة فرعية للتحكم في الكلمات المسيئة (إضافة وحذف)
    badwords_group = app_commands.Group(name="badwords", description="[إدارة الحماية] إضافة أو حذف الكلمات المسيئة من فلتر الحظر")

    @badwords_group.command(name="add", description="إضافة كلمة جديدة لقائمة الحظر الآلي")
    @app_commands.describe(word="الكلمة المراد حظرها ومنع تداولها في السيرفر")
    @app_commands.checks.has_permissions(administrator=True)
    async def badwords_add(self, interaction: discord.Interaction, word: str):
        clean_word = word.strip().lower()
        if clean_word in BAD_WORDS_DB:
            await interaction.response.send_message(f"⚠️ الكلمة (`{clean_word}`) موجودة مسبقاً في قاعدة بيانات الحظر!", ephemeral=True)
            return
        BAD_WORDS_DB.append(clean_word)
        await interaction.response.send_message(f"✅ **تمت الإضافة بنجاح!** تم إدراج الكلمة (`{clean_word}`) إلى قائمة الكلمات المسيئة والمحظورة.", ephemeral=True)

    @badwords_group.command(name="remove", description="إزالة كلمة من قائمة الحظر الآلي")
    @app_commands.describe(word="الكلمة المراد إزالتها من فلتر الحظر")
    @app_commands.checks.has_permissions(administrator=True)
    async def badwords_remove(self, interaction: discord.Interaction, word: str):
        clean_word = word.strip().lower()
        if clean_word not in BAD_WORDS_DB:
            await interaction.response.send_message(f"❌ الكلمة (`{clean_word}`) غير موجودة في القائمة أصلاً.", ephemeral=True)
            return
        BAD_WORDS_DB.remove(clean_word)
        await interaction.response.send_message(f"✅ **تمت الإزالة بنجاح!** تم رفع الحظر عن الكلمة (`{clean_word}`).", ephemeral=True)

    @badwords_group.command(name="list", description="استعراض جميع الكلمات المسيئة والمحظورة حالياً")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badwords_list(self, interaction: discord.Interaction):
        if not BAD_WORDS_DB:
            await interaction.response.send_message("🌟 قائمة الكلمات المحظورة فارغة حالياً.", ephemeral=True)
            return
        words_str = "، ".join([f"`{w}`" for w in BAD_WORDS_DB])
        embed = discord.Embed(
            title="🛡️ ╎ قـائمـة الـكـلـمـات الـمـحـظـورة 〣 ｢ZIUO Security｣",
            description=f"> الكلمات والعبارات الخاضعة للفلترة والحذف الفوري:\n\n{words_str}",
            color=0xE74C3C,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Z I UO Automod Protection Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================================================
    # 🤖 المحرك الآلي الفارق والمستشعر الشامل للرسائل (Ultimate Automod Listener)
    # ==========================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # تجاهل البوتات والرسائل الخاصة
        if message.author.bot or not message.guild:
            return

        # استثناء المشرفين والأدمن من القيود لضمان الحرية الإدارية الكاملة
        if message.author.guild_permissions.manage_messages:
            return

        content = message.content
        content_lower = content.lower()
        violation_reason = None

        # 1. فحص روابط الدعوات (Anti-Invite)
        if SECURITY_SETTINGS['anti_invite'] and self.invite_pattern.search(content):
            violation_reason = "نشر روابط إعلانية أو دعوات سيرفرات خارجية (البند 3)"

        # 2. فحص الروابط الخارجية الضارة (Anti-Links)
        elif SECURITY_SETTINGS['anti_links'] and self.url_pattern.search(content) and not self.invite_pattern.search(content):
            violation_reason = "نشر روابط خارجية غير مصرح بها"

        # 3. فحص الكلمات المسيئة والمستفزة (Bad Words Filter - البنود 1، 8، 9)
        elif any(bad_word in content_lower for bad_word in BAD_WORDS_DB):
            violation_reason = "استخدام كلمات مسيئة، مستفزة أو محظورة"

        # 4. فحص التشويه البصري والحروف الكبيرة المفرطة (Anti-Caps - البند 12)
        elif SECURITY_SETTINGS['anti_caps'] and len(content) > 8:
            caps_count = sum(1 for c in content if c.isupper())
            caps_percent = (caps_count / len(content)) * 100
            if caps_percent >= SECURITY_SETTINGS['max_caps_percent']:
                violation_reason = "الكتابة بخط كبير ومفرط (تشويه بصري)"

        # 5. فحص سبام الإيموجي (Anti-Emoji Spam)
        elif SECURITY_SETTINGS['anti_emoji']:
            emoji_count = len(re.findall(r'<a?:\w+:\d+>', content)) + sum(1 for c in content if ord(c) > 127300)
            if emoji_count > SECURITY_SETTINGS['max_emojis']:
                violation_reason = "إرسال كمية مفرطة من الإيموجي (Emoji Spam)"

        # 6. فحص تكرار نفس الرسالة (Anti-Repeat)
        if SECURITY_SETTINGS['anti_repeat'] and not violation_reason and len(content) > 3:
            last_msg = USER_LAST_MESSAGE.get(message.author.id)
            if last_msg == content:
                violation_reason = "تكرار نفس الرسالة عدة مرات متتالية (Spam)"
            else:
                USER_LAST_MESSAGE[message.author.id] = content

        # 7. فحص السبام السريع والفلود (Anti-Flood / Spam)
        if SECURITY_SETTINGS['anti_spam'] and not violation_reason:
            now = datetime.datetime.utcnow()
            user_history = USER_MESSAGE_TRACKER[message.author.id]
            user_history.append(now)
            if len(user_history) >= 5:
                time_diff = (user_history[-1] - user_history[0]).total_seconds()
                if time_diff < 4:
                    violation_reason = "إرسال رسائل متتالية بسرعة فائقة (Flood & Spam)"

        # التنفيذ الفوري للعقوبة ورصد المخالفة
        if violation_reason:
            try:
                await message.delete()
            except:
                pass

            # تطبيق إجراءات الحماية والعقوبة المحددة
            try:
                if SECURITY_SETTINGS['punishment_mode'] == "timeout":
                    # إعطاء تايم آوت مؤقت للعضو عند المخالفة
                    await message.author.timeout(datetime.timedelta(seconds=SECURITY_SETTINGS['timeout_duration']), reason=f"Automod: {violation_reason}")
                    action_msg = f"تم حذف رسالتك وإعطاؤك تايم آوت لمدة {SECURITY_SETTINGS['timeout_duration']//60} دقائق."
                else:
                    action_msg = "تم حذف رسالتك تلقائياً لضمان الانضباط."

                alert = await message.channel.send(
                    f"⚠️ ╎ {message.author.mention} **تنبيه نظام الحماية الآلي:**\n"
                    f" └ **السبب:** {violation_reason}\n"
                    f" └ **الإجراء:** {action_msg}"
                )
                await alert.delete(delay=5)
            except Exception as e:
                print(f"[SECURITY ERROR] Could not apply punishment: {e}")

            print(f"[ZIUO ENTERPRISE SECURITY] Blocked message from {message.author} | Reason: {violation_reason}")

async def setup(bot):
    await bot.add_cog(UltimateSecurityCog(bot))
