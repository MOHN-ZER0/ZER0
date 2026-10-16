"""
🛡️ نظام الحماية والمودريشن الاحترافي (Security & Automod)

- كشف ذكي للكلمات المسيئة (عربي + إنجليزي) بيتعامل مع: التشكيل والتطويل، الهمزات، تكرار الحروف، رموز/أرقام بدل الحروف،
  فواصل ومسافات بين الحروف، النجوم، السوابق واللواحق العربية — بمطابقة كلمة كاملة (مش جزء من كلمة) عشان ما يحصلش تايم أوت غلط.
- كل كلمة ليها إعداداتها: طريقة المطابقة، الخطورة، العقوبة، وصارم/ذكي — وتتعدل فوراً بعد إضافة الكلمة.
- مستويات جاهزة: ضعيف (Low) / عادي (Medium) / متوسط (High) / شديد (Extreme) — وبعدها تقدر تفعّل/توقف أي ميزة وتعدّل أي حد.
- عقوبات بنظام نقاط مخالفات (Strikes) بتتلاشى مع الوقت: تحذير ← تايم أوت (بيتضاعف) ← طرد ← حظر، وكلها قابلة للتخصيص.
- روم سجلات بإيمبدات واضحة، وتحقق من صلاحيات البوت وترتيب الرتب قبل أي عقوبة (من غير أخطاء صامتة).
- كل الإعدادات والكلمات والمخالفات بتتحفظ في MongoDB (MONGODB_URI).
- محتاج Intents: message_content + members. وصلاحيات البوت: Manage Messages, Moderate Members (+ Kick/Ban لو مفعّلين).
"""
import asyncio
import copy
import datetime
import logging
import math
import os
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()
log = logging.getLogger("security")

# ==============================================================================
# ⚙️ الثوابت
# ==============================================================================
MONGO_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = "ZeroPro_Security_DB"
DEBUG = os.getenv("SECURITY_DEBUG", "1") == "1"
DB_TIMEOUT = 15.0

COLOR_DARK = 0x111111
COLOR_GREEN = 0x00FF88
COLOR_ORANGE = 0xFFA500
COLOR_RED = 0xE74C3C
COLOR_DARKRED = 0x992D22
COLOR_BLUE = 0x3498DB

RECENT_GUARD = 4.0                 # ثواني: ما نكرّرش عقوبة على نفس العضو (رسايل متزامنة في نفس الرشق)
ESCALATION_WINDOW = 7 * 86400      # تايم أوت متكرر خلال أسبوع = مدة مضاعفة
MAX_TIMEOUT = 28 * 86400           # حد ديسكورد
WORDS_PER_PAGE = 15
MAX_WORDS_PER_ADD = 25

RULE_LABEL = {
    "badwords": "🤬 كلمات مسيئة", "invites": "📨 روابط دعوات", "links": "🔗 روابط خارجية", "mentions": "📣 منشن مفرط",
    "emoji": "😀 سبام إيموجي", "caps": "🔠 حروف كبيرة مفرطة", "zalgo": "🌀 رموز مشوّهة (Zalgo)", "char_spam": "♾️ تكرار حروف مفرط",
    "repeat": "🔁 تكرار رسالة", "spam": "⚡ سبام / فلود",
}
RULE_POINTS = {"invites": 2, "links": 1, "mentions": 2, "emoji": 1, "caps": 1, "zalgo": 1, "char_spam": 1, "repeat": 1, "spam": 2}
HOW_LABEL = {"plain": "مطابقة مباشرة", "separators": "فواصل/رموز بين الحروف", "leet": "رموز وأرقام بدل الحروف", "collapse": "حروف مكررة",
             "affix": "سوابق/لواحق عربية", "joined": "حروف مفصولة بمسافات", "split": "كلمة متقطعة", "substring": "كلمة داخل كلمة", "wildcard": "نجمة بدل حرف"}
ACTION_ORDER = ["none", "warn", "timeout", "kick", "ban"]
ACTION_LABEL = {"none": "حذف فقط", "warn": "تحذير", "timeout": "تايم أوت", "kick": "طرد", "ban": "حظر"}
WORD_ACTIONS = {"auto": "تلقائي (حسب نظام النقاط)", "delete": "حذف فقط (من غير نقاط)", "warn": "تحذير على الأقل", "timeout": "تايم أوت على الأقل", "kick": "طرد", "ban": "حظر"}
MATCH_TYPES = {"word": "كلمة كاملة (ذكي)", "exact": "مطابقة تامة فقط", "contains": "يحتوي في أي مكان"}
SEVERITY = {1: "🟢 خفيفة (نقطة)", 2: "🟠 متوسطة (نقطتين)", 3: "🔴 شديدة (3 نقاط)"}

FEATURES = [
    ("badwords", "🤬", "الكلمات المحظورة", "فلتر ذكي للكلمات المسيئة"),
    ("invites", "📨", "روابط الدعوات", "منع دعوات سيرفرات ديسكورد"),
    ("links", "🔗", "الروابط الخارجية", "منع الروابط عدا الدومينات المسموحة"),
    ("mentions", "📣", "المنشن المفرط", "منشن عدد كبير من الأعضاء/الرتب"),
    ("spam", "⚡", "السبام والفلود", "رسائل متتالية بسرعة"),
    ("repeat", "🔁", "تكرار الرسائل", "نفس الرسالة أكتر من مرة"),
    ("caps", "🔠", "الحروف الكبيرة", "كتابة إنجليزي بحروف كبيرة مفرطة"),
    ("emoji", "😀", "سبام الإيموجي", "إيموجيات كتير في رسالة واحدة"),
    ("zalgo", "🌀", "الرموز المشوّهة", "نصوص Zalgo المخربشة"),
    ("char_spam", "♾️", "تكرار الحروف", "حرف واحد مكرر بشكل مفرط"),
    ("edits", "✏️", "فحص التعديل", "فحص الرسائل بعد ما تتعدل"),
]
DETECTION = [
    ("leet", "🔣", "رموز وأرقام بدل الحروف", "sh!t / $hit / 5h1t"),
    ("separators", "✂️", "فواصل بين الحروف", "ك.ل.ب / ك ل ب / f-u-c-k"),
    ("collapse", "🔁", "تجاهل تكرار الحروف", "كلللب / fuuuck"),
    ("affixes", "🏷️", "السوابق واللواحق العربية", "والكلب / كلبك / بكلبهم"),
    ("wildcards", "⭐", "نجمة بدل حرف", "f*ck / ك*ب"),
    ("split", "🧩", "كلمة متقطعة بمسافة", "كل ب / ني ك"),
    ("substring", "🔬", "كلمة داخل كلمة (الأعنف)", "احتمال خطأ أعلى — للمستوى الشديد"),
]
PUNISH_TOGGLES = [
    ("delete", "🗑️", "حذف رسالة المخالفة", "بيحذف الرسالة المخالفة"),
    ("notify_channel", "📢", "تنبيه في الشات", "رسالة تنبيه بتتمسح لوحدها"),
    ("dm_user", "✉️", "رسالة خاصة للعضو", "بيبعت للعضو تفاصيل المخالفة"),
    ("escalate", "📈", "تصعيد مدة التايم أوت", "المدة بتتضاعف مع تكرار التايم أوت"),
]

LEVELS = {
    "low": {"label": "ضعيف (Low)", "emoji": "🟢", "desc": "حماية خفيفة: حذف + تحذير فقط، من غير تايم أوت. للسيرفرات الهادية.",
            "features": dict(badwords=True, invites=True, links=False, mentions=True, spam=True, repeat=False, caps=False, emoji=False, zalgo=False, char_spam=False, edits=False),
            "thresholds": dict(spam_messages=8, spam_seconds=6, repeat_count=4, repeat_seconds=60, caps_percent=85, caps_min_letters=12, max_emojis=15, max_mentions=10, char_repeat=25, zalgo_marks=15),
            "detection": dict(leet=False, separators=False, collapse=True, affixes=False, wildcards=False, split=False, substring=False),
            "punish": dict(delete=True, notify_channel=True, dm_user=False, escalate=False, warn_at=1, timeout_at=0, kick_at=0, ban_at=0, timeout_seconds=300, max_timeout_seconds=3600, decay_seconds=12 * 3600),
            "block_bare": False},
    "medium": {"label": "عادي (Medium)", "emoji": "🟡", "desc": "التوازن الأفضل: كشف ذكي للتحايل، وتايم أوت بعد عدة مخالفات.",
               "features": dict(badwords=True, invites=True, links=True, mentions=True, spam=True, repeat=True, caps=True, emoji=True, zalgo=True, char_spam=True, edits=True),
               "thresholds": dict(spam_messages=6, spam_seconds=5, repeat_count=3, repeat_seconds=45, caps_percent=80, caps_min_letters=10, max_emojis=10, max_mentions=6, char_repeat=20, zalgo_marks=10),
               "detection": dict(leet=True, separators=True, collapse=True, affixes=True, wildcards=False, split=False, substring=False),
               "punish": dict(delete=True, notify_channel=True, dm_user=False, escalate=True, warn_at=1, timeout_at=4, kick_at=0, ban_at=0, timeout_seconds=600, max_timeout_seconds=86400, decay_seconds=24 * 3600),
               "block_bare": False},
    "high": {"label": "متوسط (High)", "emoji": "🟠", "desc": "حماية قوية: كشف أوسع للتحايل وتايم أوت أسرع بمدد أطول.",
             "features": dict(badwords=True, invites=True, links=True, mentions=True, spam=True, repeat=True, caps=True, emoji=True, zalgo=True, char_spam=True, edits=True),
             "thresholds": dict(spam_messages=5, spam_seconds=5, repeat_count=3, repeat_seconds=60, caps_percent=70, caps_min_letters=8, max_emojis=8, max_mentions=5, char_repeat=15, zalgo_marks=8),
             "detection": dict(leet=True, separators=True, collapse=True, affixes=True, wildcards=True, split=True, substring=False),
             "punish": dict(delete=True, notify_channel=True, dm_user=True, escalate=True, warn_at=1, timeout_at=3, kick_at=0, ban_at=0, timeout_seconds=1800, max_timeout_seconds=7 * 86400, decay_seconds=48 * 3600),
             "block_bare": False},
    "extreme": {"label": "شديد (Extreme)", "emoji": "🔴", "desc": "أقصى حماية: كل أنواع الكشف + حدود ضيقة + تايم أوت سريع وطرد/حظر عند التكرار.",
                "features": dict(badwords=True, invites=True, links=True, mentions=True, spam=True, repeat=True, caps=True, emoji=True, zalgo=True, char_spam=True, edits=True),
                "thresholds": dict(spam_messages=4, spam_seconds=4, repeat_count=3, repeat_seconds=90, caps_percent=60, caps_min_letters=6, max_emojis=6, max_mentions=4, char_repeat=12, zalgo_marks=6),
                "detection": dict(leet=True, separators=True, collapse=True, affixes=True, wildcards=True, split=True, substring=True),
                "punish": dict(delete=True, notify_channel=True, dm_user=True, escalate=True, warn_at=1, timeout_at=2, kick_at=6, ban_at=10, timeout_seconds=3600, max_timeout_seconds=14 * 86400, decay_seconds=72 * 3600),
                "block_bare": True},
}

DEFAULT_WHITELIST = ["class", "classic", "pass", "passage", "passport", "password", "glass", "grass", "bass", "mass", "massive", "assist", "assistant",
                     "assume", "assess", "assassin", "scunthorpe", "therapist", "analysis", "cocktail", "shell", "hello"]
DEFAULT_ALLOWED_DOMAINS = ["tenor.com", "giphy.com", "cdn.discordapp.com", "media.discordapp.net", "discord.com"]

# كلمات افتراضية (بإعداداتها): الكلمات اللي بتتشابه مع كلمات عادية بتتعامل بحذف فقط ومطابقة تامة عشان ما يحصلش تايم أوت غلط
DEFAULT_WORDS = [
    ("قحبة", "word", 3, "auto", False), ("قحب", "word", 3, "auto", False), ("نيك", "word", 3, "auto", False), ("متخلف", "word", 2, "auto", False),
    ("وسخ", "word", 1, "delete", False), ("طز", "exact", 1, "delete", True), ("كلب", "exact", 1, "delete", True), ("عمك", "exact", 1, "delete", True),
    ("منقرض", "exact", 1, "delete", True), ("هكر", "exact", 1, "delete", True), ("شاتم", "exact", 1, "delete", True),
    ("حسابات للبيع", "word", 1, "auto", False), ("فواكه للبيع", "word", 1, "auto", False),
    ("fuck", "word", 3, "auto", False), ("shit", "word", 2, "auto", False), ("bitch", "word", 2, "auto", False), ("asshole", "word", 2, "auto", False),
    ("bastard", "word", 2, "auto", False), ("cunt", "word", 3, "auto", False), ("slut", "word", 2, "auto", False), ("whore", "word", 2, "auto", False),
    ("dick", "exact", 1, "delete", True),
]


def default_settings() -> dict:
    st = {
        "enabled": False, "level": None, "modified": False, "words_seeded": False,
        "log_channel_id": None, "log_content": True,
        "exempt_staff": True, "exempt_roles": [], "exempt_channels": [],
        "features": {}, "thresholds": {}, "detection": {}, "punish": {},
        "links": {"allowed_domains": list(DEFAULT_ALLOWED_DOMAINS), "block_bare": False, "allow_own_invite": True},
        "whitelist_words": list(DEFAULT_WHITELIST),
        "notify_delete_after": 8,
    }
    base = LEVELS["medium"]
    for section in ("features", "thresholds", "detection", "punish"):
        st[section] = dict(base[section])
    return st


def deep_merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(base.get(k), dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def apply_level(st: dict, level: str):
    p = LEVELS[level]
    for section in ("features", "thresholds", "detection", "punish"):
        st[section].update(copy.deepcopy(p[section]))
    st["links"]["block_bare"] = p["block_bare"]
    st["level"], st["modified"] = level, False


# ==============================================================================
# 💾 قاعدة البيانات
# ==============================================================================
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000) if MONGO_URI else None
_db = _client[DB_NAME] if _client is not None else None
settings_col = _db["settings"] if _db is not None else None
words_col = _db["words"] if _db is not None else None
strikes_col = _db["strikes"] if _db is not None else None


async def run_db(fn, *args, **kwargs):
    return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), DB_TIMEOUT)


def ensure_indexes_sync():
    for col, keys in ((words_col, [("guild_id", 1), ("key", 1)]), (strikes_col, [("guild_id", 1), ("user_id", 1)])):
        try:
            col.create_index(keys, unique=True)
        except Exception:
            log.warning("تعذر إنشاء index %s", keys, exc_info=True)


def load_all_sync() -> tuple[list, list]:
    return list(settings_col.find({})), list(words_col.find({}))


def save_settings_sync(gid: int, st: dict):
    settings_col.replace_one({"_id": gid}, {"_id": gid, **st}, upsert=True)


def add_words_sync(docs: list) -> list:
    added = []
    for d in docs:
        try:
            words_col.insert_one(d)
            added.append(d)
        except DuplicateKeyError:
            continue
    return added


def update_words_sync(gid: int, keys: list, sets: dict):
    words_col.update_many({"guild_id": gid, "key": {"$in": keys}}, {"$set": sets})


def delete_words_sync(gid: int, keys: list) -> int:
    return words_col.delete_many({"guild_id": gid, "key": {"$in": keys}}).deleted_count


def get_strikes_sync(gid: int, uid: int) -> dict:
    return strikes_col.find_one({"guild_id": gid, "user_id": uid}) or {}


def save_strikes_sync(gid: int, uid: int, entries: list, timeouts: list):
    strikes_col.update_one({"guild_id": gid, "user_id": uid}, {"$set": {"entries": entries, "timeouts": timeouts, "updated_at": int(time.time())}}, upsert=True)


# ==============================================================================
# 🧠 التطبيع والكشف الذكي عن الكلمات
# ==============================================================================
_ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\ufeff\u00ad\u061c\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u180e"), None)
_AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه", "ک": "ك", "ی": "ي", "ې": "ي", "ۍ": "ي", "ھ": "ه", "ۀ": "ه",
                          "ہ": "ه", "ە": "ه", "گ": "ك", "پ": "ب", "چ": "ج", "ڤ": "ف", "ڨ": "ق", "ں": "ن", "ء": None, "ـ": None})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_HOMO = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b",
                       "α": "a", "ο": "o", "ν": "v", "ε": "e", "ι": "i", "κ": "k", "ρ": "p", "τ": "t", "υ": "u"})
_LEET = str.maketrans({"@": "a", "4": "a", "^": "a", "3": "e", "€": "e", "1": "i", "!": "i", "|": "i", "0": "o", "$": "s", "5": "s", "7": "t", "+": "t",
                       "8": "b", "(": "c", "<": "c", "¢": "c", "9": "g", "6": "g", "£": "l"})
_LEET_KEYS = set("@4^3€1!|0$57+8(<¢96£")
_AR_RE = re.compile(r"[\u0600-\u06FF]")
PREFIXES = sorted(["وال", "بال", "كال", "فال", "ولل", "لل", "ال", "و", "ف", "ب", "ل", "ك", "س", "ي", "ت", "ن", "م"], key=len, reverse=True)
SUFFIXES = sorted(["ها", "هم", "هن", "كم", "كن", "نا", "ني", "ون", "ين", "ان", "ات", "وا", "ه", "ك", "ي", "ا", "ت", "ن"], key=len, reverse=True)


def basic_norm(text: str) -> str:
    """تطبيع أساسي: توحيد الشكل، شيل التشكيل والتطويل والرموز الخفية، توحيد الهمزات والياء والتاء المربوطة، أرقام عربية، وأحرف مشابهة."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.translate(_ZW).translate(_AR_FOLD).translate(_DIGITS).translate(_HOMO).casefold()


def alnum(s: str) -> str:
    return "".join(c for c in s if c.isalnum())


def letters(s: str) -> str:
    return "".join(c for c in s if c.isalpha())


def collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def has_arabic(s: str) -> bool:
    return bool(_AR_RE.search(s))


def word_key(word: str) -> str:
    return " ".join(basic_norm(word).split())[:100]


def affix_variants(word: str, lengths: set) -> list[str]:
    out = []
    for p in [""] + [p for p in PREFIXES if word.startswith(p) and len(word) - len(p) >= 3]:
        rest = word[len(p):]
        for s in [""] + SUFFIXES:
            if s and not rest.endswith(s):
                continue
            r = rest[: len(rest) - len(s)] if s else rest
            if (p or s) and len(r) >= 3 and len(r) in lengths:
                out.append(r)
    return out


def single_runs(tokens: list, leet: bool) -> list[str]:
    """حروف مفصولة بمسافات/رموز (ك ل ب / f u c k): بيجمع كل 3 حروف أو أكتر متتالية."""
    runs: list[str] = []
    cur: list[str] = []

    def flush():
        if len(cur) >= 3:
            runs.append("".join(cur))
        cur.clear()

    for t in tokens:
        a = alnum(t)
        if len(a) == 1:
            cur.append(a)
        elif len(t) == 1 and leet and t in _LEET_KEYS:
            cur.append(t.translate(_LEET))
        elif not a and t:
            continue
        else:
            flush()
    flush()
    return runs


@dataclass
class Hit:
    entry: "Entry"
    text: str
    how: str


class Entry:
    __slots__ = ("word", "key", "match", "severity", "action", "strict", "is_phrase", "base", "compact", "skel", "skel_compact", "forms")

    def __init__(self, doc: dict):
        self.word, self.key = doc["word"], doc["key"]
        self.match = doc.get("match", "word") if doc.get("match") in MATCH_TYPES else "word"
        self.severity = max(1, min(3, int(doc.get("severity", 2))))
        self.action = doc.get("action", "auto") if doc.get("action") in WORD_ACTIONS else "auto"
        self.strict = bool(doc.get("strict", False))
        toks = [t for t in (alnum(x) for x in self.key.split()) if t]
        self.is_phrase = len(toks) > 1
        self.base = " ".join(toks)
        self.compact = "".join(toks)
        self.skel = self.skel_compact = None
        if not self.strict:
            sk = collapse(self.compact)
            if self.is_phrase and len(self.compact) >= 5:
                self.skel = " ".join(collapse(t) for t in toks)
            elif not self.is_phrase and len(sk) >= 3:
                self.skel = sk
            if len(sk) >= 4:
                self.skel_compact = sk
        self.forms = [self.base]
        if not self.is_phrase and self.base.startswith("ال") and len(self.base) - 2 >= 3:
            self.forms.append(self.base[2:])  # "الموسيقى" تطابق كمان "موسيقى"


class Matcher:
    def __init__(self, docs: list, whitelist: list):
        self.exact: dict[str, Entry] = {}
        self.skel: dict[str, Entry] = {}
        self.phrases: list[Entry] = []
        self.contains: list[Entry] = []
        self.long: list[Entry] = []
        self.by_len: dict[int, list[Entry]] = {}
        self.lengths: set[int] = set()
        for doc in docs:
            try:
                e = Entry(doc)
            except Exception:
                continue
            if not e.base:
                continue
            if e.match == "contains":
                self.contains.append(e)
            elif e.is_phrase:
                self.phrases.append(e)
            else:
                for f in e.forms:
                    self.exact[f] = e
                    self.lengths.add(len(f))
                    self.by_len.setdefault(len(f), []).append(e)
                    if e.skel:
                        sk = collapse(f)
                        if len(sk) >= 3:
                            self.skel[sk] = e
                            self.lengths.add(len(sk))
                if e.match == "word" and not e.strict and len(e.base) >= 4:
                    self.long.append(e)
        self.white = {alnum(basic_norm(w)) for w in whitelist if alnum(basic_norm(w))}
        self.white_skel = {collapse(w) for w in self.white if len(collapse(w)) >= 3}

    def _lookup(self, f: str, kind: str, o: dict) -> Optional[tuple]:
        loose = kind != "plain"
        e = self.exact.get(f)
        if e and not (loose and (e.strict or e.match == "exact")):
            return e, kind
        if o.get("collapse"):
            c = collapse(f)
            e = self.skel.get(c)
            if e and e.match == "word" and not e.strict:
                return e, ("collapse" if c != f else kind)
        if o.get("affixes") and has_arabic(f):
            for r in affix_variants(f, self.lengths):
                e = self.exact.get(r)
                if e and e.match == "word" and not e.strict:
                    return e, "affix"
                if o.get("collapse"):
                    e = self.skel.get(collapse(r))
                    if e and e.match == "word" and not e.strict:
                        return e, "affix"
        return None

    def _token_forms(self, tok: str, o: dict) -> list[tuple]:
        edge = re.sub(r"^\W+|\W+$", "", tok)
        forms: list[tuple] = []
        plain = edge if edge.isalnum() else ""
        if plain:
            forms.append((plain, "plain"))
        if o.get("separators"):
            for f in (alnum(tok), letters(tok)):
                if f and all(f != x for x, _ in forms):
                    forms.append((f, "separators"))
        if o.get("leet") and any(c.isalpha() for c in tok):
            for f in (alnum(tok.translate(_LEET)), letters(tok.translate(_LEET))):
                if f and all(f != x for x, _ in forms):
                    forms.append((f, "leet"))
        return forms

    def _allowed(self, f: str) -> bool:
        return f in self.white or collapse(f) in self.white_skel

    def _wild(self, tok: str) -> Optional[Entry]:
        t = re.sub(r"^[^\w*#]+|[^\w*#]+$", "", tok)
        wild = t.count("*") + t.count("#")
        if len(t) < 3 or wild == 0 or wild > len(t) // 2:
            return None
        for e in self.by_len.get(len(t), []):
            if e.match == "word" and not e.strict and all(c in "*#" or c == w for c, w in zip(t, e.base)):
                return e
        return None

    def match_token(self, tok: str, o: dict) -> Optional[Hit]:
        forms = self._token_forms(tok, o)
        if any(self._allowed(f) for f, _ in forms):
            return None
        for f, kind in forms:
            r = self._lookup(f, kind, o)
            if r:
                return Hit(r[0], tok, r[1])
        if o.get("wildcards") and ("*" in tok or "#" in tok):
            e = self._wild(tok)
            if e:
                return Hit(e, tok, "wildcard")
        if o.get("substring"):
            for f, _ in forms:
                if 4 <= len(f) <= 60:
                    for e in self.long:
                        if e.base in f:
                            return Hit(e, tok, "substring")
        return None

    def find(self, text: str, o: dict) -> Optional[Hit]:
        norm = basic_norm(text)
        tokens = norm.split()[:400]
        if not tokens:
            return None
        for tok in tokens:
            h = self.match_token(tok, o)
            if h:
                return h
        if o.get("separators"):
            for run in single_runs(tokens, bool(o.get("leet"))):
                for f in {run, run.translate(_LEET)} if o.get("leet") else {run}:
                    if not self._allowed(f):
                        r = self._lookup(f, "joined", o)
                        if r:
                            return Hit(r[0], run, "joined")
        if o.get("split"):
            cs = [c for c in (alnum(t) for t in tokens) if c]
            for a, b in zip(cs, cs[1:]):
                if min(len(a), len(b)) <= 2 and 3 <= len(a) + len(b) <= 20 and not (self._allowed(a) or self._allowed(b)):
                    e = self.exact.get(a + b)
                    if e and e.match == "word" and not e.strict:
                        return Hit(e, f"{a} {b}", "split")
        if self.phrases:
            forms = [f for f in (alnum(t) for t in tokens) if f]
            joined, jc = " " + " ".join(forms) + " ", " " + " ".join(collapse(f) for f in forms) + " "
            for e in self.phrases:
                if f" {e.base} " in joined:
                    return Hit(e, e.base, "plain")
                if o.get("collapse") and e.skel and f" {e.skel} " in jc:
                    return Hit(e, e.base, "collapse")
        if self.contains:
            compact = alnum(norm)
            cc = collapse(compact) if o.get("collapse") else None
            for e in self.contains:
                if e.compact in compact:
                    return Hit(e, e.compact, "plain")
                if cc and e.skel_compact and e.skel_compact in cc:
                    return Hit(e, e.compact, "collapse")
        return None


# ==============================================================================
# 🔎 كشف باقي المخالفات (روابط، دعوات، كابس...)
# ==============================================================================
INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.(?:gg|io|me|li)|dsc\.gg|invite\.gg)\s*/\s*([\w-]{2,32})"
                       r"|discord\s*(?:\.|dot|\(dot\)|\[dot\])\s*gg\s*/\s*([\w-]{2,32})", re.I)
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.I)
BARE_RE = re.compile(r"\b[a-z0-9][a-z0-9\-]{0,62}(?:\.[a-z0-9\-]{1,63})*\.(?:com|net|org|io|gg|me|xyz|tk|ru|cn|info|biz|link|club|online|site|shop|top|vip|cc|tv|co|app|dev|ly|gl|to|ws|pw|ml|ga|cf)\b", re.I)
EMOJI_RE = re.compile(r"<a?:\w+:\d+>|[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF\u2600-\u27BF\u2B50\u2B55\u2300-\u23FF]")
ZALGO_RE = re.compile("[\u0300-\u036f\u0483-\u0489\u20d0-\u20ff]")


def extract_hosts(content: str, bare: bool) -> list[str]:
    hosts = []
    for m in URL_RE.findall(content):
        rest = re.sub(r"^(?:https?://)?(?:www\.)?", "", m, flags=re.I)
        host = re.split(r"[/?#:]", rest, maxsplit=1)[0].lower().strip(".,)")
        if host:
            hosts.append(host)
    if bare:
        for m in BARE_RE.findall(URL_RE.sub(" ", content)):
            hosts.append(re.sub(r"^www\.", "", m.lower()))
    return hosts


def domain_allowed(host: str, allowed: list) -> bool:
    return any(host == d or host.endswith("." + d) for d in (a.lower().strip() for a in allowed) if d)


@dataclass
class Violation:
    rule: str
    reason: str
    points: int = 1
    action: str = "auto"
    detail: str = ""
    how: str = ""
    purge: bool = False


def content_violation(content: str, st: dict, matcher: Matcher, mentions: int = 0, vanity: Optional[str] = None) -> Optional[Violation]:
    """كل الفحوصات اللي بتعتمد على نص الرسالة بس (من غير تتبع سبام) — بتستخدم كمان في أداة الاختبار."""
    f, th, det, lk = st["features"], st["thresholds"], st["detection"], st["links"]
    if f["badwords"] and content:
        hit = matcher.find(content, det)
        if hit:
            e = hit.entry
            return Violation("badwords", "استخدام كلمات مسيئة أو محظورة", points=e.severity, action=e.action, detail=e.word, how=HOW_LABEL.get(hit.how, hit.how))
    invite_codes = [m.group(1) or m.group(2) for m in INVITE_RE.finditer(content)]
    if f["invites"] and invite_codes:
        foreign = [c for c in invite_codes if not (lk.get("allow_own_invite") and vanity and c.lower() == vanity.lower())]
        if foreign:
            return Violation("invites", "نشر دعوات سيرفرات خارجية", points=RULE_POINTS["invites"], detail=foreign[0])
    if f["links"]:
        hosts = [h for h in extract_hosts(content, bool(lk.get("block_bare"))) if not re.match(r"^(?:discord(?:app)?\.(?:gg|com|io|me|li)|dsc\.gg|invite\.gg)$", h)]
        bad = [h for h in hosts if not domain_allowed(h, lk.get("allowed_domains", []))]
        if bad:
            return Violation("links", "نشر روابط خارجية غير مسموحة", points=RULE_POINTS["links"], detail=bad[0])
    if f["mentions"] and mentions > th["max_mentions"]:
        return Violation("mentions", "منشن عدد كبير من الأعضاء/الرتب", points=RULE_POINTS["mentions"], detail=f"{mentions} منشن")
    if f["zalgo"] and len(ZALGO_RE.findall(content)) > th["zalgo_marks"]:
        return Violation("zalgo", "كتابة نص مشوّه (Zalgo)", points=RULE_POINTS["zalgo"])
    if f["char_spam"] and content:
        n = max(2, int(th["char_repeat"]))
        if re.search(r"(\S)\1{%d,}" % (n - 1), content):
            return Violation("char_spam", "تكرار حرف واحد بشكل مفرط", points=RULE_POINTS["char_spam"])
    if f["emoji"]:
        count = len(EMOJI_RE.findall(content))
        if count > th["max_emojis"]:
            return Violation("emoji", "إرسال كمية مفرطة من الإيموجي", points=RULE_POINTS["emoji"], detail=f"{count} إيموجي")
    if f["caps"]:
        cased = [c for c in content if c.isalpha() and c.casefold() != c.upper().casefold() or (c.isalpha() and c.upper() != c.lower())]
        if len(cased) >= th["caps_min_letters"]:
            ratio = 100 * sum(1 for c in cased if c.isupper()) / len(cased)
            if ratio >= th["caps_percent"]:
                return Violation("caps", "الكتابة بحروف كبيرة بشكل مفرط", points=RULE_POINTS["caps"], detail=f"{ratio:.0f}%")
    return None


def decide_action(total: int, p: dict) -> str:
    for key, name in (("ban_at", "ban"), ("kick_at", "kick"), ("timeout_at", "timeout"), ("warn_at", "warn")):
        if p.get(key) and total >= p[key]:
            return name
    return "none"


def stronger(a: str, b: str) -> str:
    return a if ACTION_ORDER.index(a) >= ACTION_ORDER.index(b) else b


def timeout_seconds(p: dict, previous_timeouts: int) -> int:
    dur = p["timeout_seconds"] * (2 ** previous_timeouts if p.get("escalate") else 1)
    return int(max(60, min(dur, p.get("max_timeout_seconds", MAX_TIMEOUT), MAX_TIMEOUT)))


# ==============================================================================
# 🧰 دوال مساعدة
# ==============================================================================
def clip(text: Any, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def ok_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_GREEN)


def err_embed(description: str, title: str = "❌ خطأ") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=COLOR_RED)


def error_text(exc: BaseException) -> str:
    text = "❌ حصل خطأ أثناء تنفيذ الأمر، حاول تاني."
    if DEBUG:
        text += f"\n```{type(exc).__name__}: {clip(exc, 300)}```"
    return text


_DUR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z\u0600-\u06FF]*)")


def parse_duration(text: str, default_unit: int = 60) -> Optional[int]:
    """مدة بالثواني: 90 / 10m / 2h / 1d12h / 30 دقيقة / ساعتين. الرقم لوحده بياخد default_unit."""
    total, found = 0.0, False
    for num, unit in _DUR_RE.findall(basic_norm(text)):
        n = float(num.replace(",", "."))
        u = unit[:1]
        if not u:
            mult = default_unit
        elif u in ("s", "ث"):
            mult = 1
        elif u in ("m", "د"):
            mult = 60
        elif u in ("h", "س"):
            mult = 3600
        elif u in ("d", "ي"):
            mult = 86400
        elif u in ("w", "ا"):
            mult = 604800
        else:
            return None
        total += n * mult
        found = True
    return int(total) if found else None


def fmt_dur(seconds: int) -> str:
    seconds = int(seconds)
    if seconds <= 0:
        return "0"
    for unit, name in ((86400, "يوم"), (3600, "ساعة"), (60, "دقيقة")):
        if seconds >= unit:
            v = seconds / unit
            return f"{v:g} {name}"
    return f"{seconds} ثانية"


def fmt_short(seconds: int) -> str:
    seconds = int(seconds)
    if seconds and seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


async def respond(interaction: discord.Interaction, **kwargs):
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def report_error(interaction: discord.Interaction, exc: Optional[BaseException] = None):
    try:
        await respond(interaction, content=error_text(exc) if exc else "❌ حصل خطأ غير متوقع، حاول تاني.", ephemeral=True)
    except discord.HTTPException:
        pass


class SafeView(discord.ui.View):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction, error)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("خطأ في %s", type(self).__name__, exc_info=error)
        await report_error(interaction, error)


class AdminView(SafeView):
    def __init__(self, cog: "UltimateSecurityCog", gid: int, owner_id: int, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.cog, self.gid, self.owner_id = cog, gid, owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and interaction.user.guild_permissions.administrator:
            return True
        await respond(interaction, content="🔒 اللوحة دي للأدمن اللي فتحها بس. اكتب `/security panel`.", ephemeral=True)
        return False

    @property
    def st(self) -> dict:
        return self.cog.settings[self.gid]


async def show_page(cog: "UltimateSecurityCog", interaction: discord.Interaction, gid: int, owner_id: int, page: str, **kw):
    if not interaction.response.is_done():
        await interaction.response.defer()
    embed, view = cog.build_page(gid, owner_id, page, **kw)
    await interaction.edit_original_response(content=None, embed=embed, view=view)


# ==============================================================================
# 🎛️ المودالات
# ==============================================================================
class SettingsModal(SafeModal):
    """مودال عام لتعديل أرقام ومدد في الإعدادات. spec = (section, key, label, kind, lo, hi, unit)."""

    def __init__(self, view: AdminView, title: str, spec: list, page: str):
        super().__init__(title=title)
        self.view, self.spec, self.page = view, spec, page
        self.boxes = []
        for section, key, label, kind, lo, hi, unit in spec:
            val = view.st[section][key] if section else view.st[key]
            box = discord.ui.TextInput(label=label[:45], default=fmt_short(val) if kind == "dur" else str(val), required=True, max_length=12)
            self.boxes.append(box)
            self.add_item(box)

    async def on_submit(self, interaction: discord.Interaction):
        parsed = []
        for (section, key, label, kind, lo, hi, unit), box in zip(self.spec, self.boxes):
            try:
                v = parse_duration(box.value, unit) if kind == "dur" else int(box.value.strip())
                if v is None or not lo <= v <= hi:
                    raise ValueError
            except ValueError:
                rng = f"{fmt_dur(lo)} → {fmt_dur(hi)}" if kind == "dur" else f"{lo} → {hi}"
                await respond(interaction, embed=err_embed(f"قيمة **{label}** غير صالحة. المسموح: {rng}"), ephemeral=True)
                return
            parsed.append((section, key, v))
        await interaction.response.defer()
        for section, key, v in parsed:
            (self.view.st[section] if section else self.view.st)[key] = v
        self.view.st["modified"] = True
        await self.view.cog.save_settings(self.view.gid)
        await show_page(self.view.cog, interaction, self.view.gid, self.view.owner_id, self.page)


class ListModal(SafeModal):
    """مودال عام لقوائم نصية (دومينات / كلمات مسموحة)."""

    def __init__(self, view: AdminView, title: str, label: str, current: list, on_save: Callable[[list], Awaitable[None]], page: str):
        super().__init__(title=title)
        self.view, self.on_save, self.page = view, on_save, page
        self.box = discord.ui.TextInput(label=label[:45], style=discord.TextStyle.paragraph, default=clip("\n".join(current), 3900) or None, required=False, max_length=4000)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        items = []
        for part in re.split(r"[\n,،;|]+", self.box.value):
            part = part.strip().lower()
            if part and part not in items:
                items.append(part[:100])
        await interaction.response.defer()
        await self.on_save(items[:300])
        await show_page(self.view.cog, interaction, self.view.gid, self.view.owner_id, self.page)


class AddWordsModal(SafeModal):
    def __init__(self, view: AdminView):
        super().__init__(title="➕ إضافة كلمة محظورة")
        self.view = view
        self.box = discord.ui.TextInput(label="الكلمة أو العبارة (كل واحدة في سطر)", style=discord.TextStyle.paragraph, required=True, max_length=1500,
                                        placeholder="الموسيقى\nحسابات للبيع")
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        words = []
        for line in re.split(r"[\n,،;|]+", self.box.value):
            line = line.strip()
            if line and word_key(line) and word_key(line) not in [word_key(w) for w in words]:
                words.append(line[:100])
        if not words:
            await respond(interaction, embed=err_embed("اكتب كلمة واحدة على الأقل."), ephemeral=True)
            return
        await interaction.response.defer()
        keys = await self.view.cog.add_words(self.view.gid, words[:MAX_WORDS_PER_ADD], interaction.user)
        await show_page(self.view.cog, interaction, self.view.gid, self.view.owner_id, "editor", keys=keys)


class RemoveWordsModal(SafeModal):
    def __init__(self, view: AdminView):
        super().__init__(title="🗑️ حذف كلمات")
        self.view = view
        self.box = discord.ui.TextInput(label="الكلمات اللي هتتحذف (كل واحدة في سطر)", style=discord.TextStyle.paragraph, required=True, max_length=1500)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        keys = [word_key(w) for w in re.split(r"[\n,،;|]+", self.box.value) if word_key(w)]
        await interaction.response.defer()
        removed = await self.view.cog.remove_words(self.view.gid, keys, interaction.user)
        await show_page(self.view.cog, interaction, self.view.gid, self.view.owner_id, "words", note=f"🗑️ اتحذف `{removed}` كلمة.")


class TestModal(SafeModal):
    def __init__(self, view: AdminView):
        super().__init__(title="🧪 اختبار الفلتر")
        self.view = view
        self.box = discord.ui.TextInput(label="اكتب أي نص لتجربته على الفلتر", style=discord.TextStyle.paragraph, required=True, max_length=1500,
                                        placeholder="مثال: ك.ل.ب أو sh!t أو الموسيقى")
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog, gid, text = self.view.cog, self.view.gid, self.box.value
        st = cog.settings[gid]
        v = content_violation(text, st, cog.get_matcher(gid), 0, interaction.guild.vanity_url_code)
        norm = clip(basic_norm(text), 300)
        if v is None:
            embed = ok_embed("✅ مفيش مخالفة", f"الفلتر ما لقاش حاجة في النص.\n**النص بعد التطبيع:** `{norm}`\n_(السبام/التكرار بيتفحصوا على الرسايل الحقيقية بس.)_")
        else:
            embed = discord.Embed(title="🚫 النص ده هيتعتبر مخالفة", color=COLOR_ORANGE, description=f"**القاعدة:** {RULE_LABEL[v.rule]}\n**السبب:** {v.reason}")
            if v.detail:
                embed.add_field(name="المطابقة", value=f"`{clip(v.detail, 100)}`" + (f" — {v.how}" if v.how else ""), inline=False)
            embed.add_field(name="النقاط / العقوبة", value=f"{v.points} نقطة ┊ {WORD_ACTIONS.get(v.action, v.action)}" if v.rule == "badwords" else f"{v.points} نقطة", inline=False)
            embed.add_field(name="النص بعد التطبيع", value=f"`{norm}`", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ==============================================================================
# 🧭 صفحات اللوحة
# ==============================================================================
class MainView(AdminView):
    def __init__(self, cog, gid, owner_id):
        super().__init__(cog, gid, owner_id)
        st = self.st
        select = discord.ui.Select(placeholder="🎚️ اختر مستوى الحماية الجاهز", row=0, options=[
            discord.SelectOption(label=v["label"], description=clip(v["desc"], 100), emoji=v["emoji"], value=k, default=(st["level"] == k)) for k, v in LEVELS.items()])

        async def level_cb(i: discord.Interaction):
            await i.response.defer()
            await cog.set_level(gid, select.values[0], i.user)
            await show_page(cog, i, gid, owner_id, "main", note=f"✅ اتطبق مستوى **{LEVELS[select.values[0]]['label']}** — تقدر تعدّل أي حاجة فيه من الأزرار.")

        select.callback = level_cb
        self.add_item(select)
        self.power_btn.label = "إيقاف النظام" if st["enabled"] else "تشغيل النظام"
        self.power_btn.style = discord.ButtonStyle.danger if st["enabled"] else discord.ButtonStyle.success

    async def _go(self, interaction: discord.Interaction, page: str):
        await show_page(self.cog, interaction, self.gid, self.owner_id, page)

    @discord.ui.button(label="تشغيل النظام", emoji="⏯️", style=discord.ButtonStyle.success, row=1)
    async def power_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.st["enabled"] and not self.st["level"]:
            apply_level(self.st, "medium")
            await self.cog.ensure_seed(self.gid)
        self.st["enabled"] = not self.st["enabled"]
        await self.cog.save_settings(self.gid)
        await self.cog.audit(interaction.guild, interaction.user, "تشغيل نظام الحماية" if self.st["enabled"] else "إيقاف نظام الحماية")
        await show_page(self.cog, interaction, self.gid, self.owner_id, "main")

    @discord.ui.button(label="الميزات", emoji="🧩", style=discord.ButtonStyle.primary, row=1)
    async def features_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "features")

    @discord.ui.button(label="العقوبات", emoji="⚖️", style=discord.ButtonStyle.primary, row=1)
    async def punish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "punish")

    @discord.ui.button(label="الكشف الذكي", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
    async def detect_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "detect")

    @discord.ui.button(label="الحدود", emoji="📏", style=discord.ButtonStyle.primary, row=1)
    async def limits_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "limits")

    @discord.ui.button(label="الكلمات المحظورة", emoji="🔤", style=discord.ButtonStyle.secondary, row=2)
    async def words_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "words")

    @discord.ui.button(label="الروابط", emoji="🌐", style=discord.ButtonStyle.secondary, row=2)
    async def links_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "links")

    @discord.ui.button(label="قناة السجلات", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def log_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "log")

    @discord.ui.button(label="الاستثناءات", emoji="🛡️", style=discord.ButtonStyle.secondary, row=2)
    async def exempt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, "exempt")

    @discord.ui.button(label="اختبار نص", emoji="🧪", style=discord.ButtonStyle.secondary, row=2)
    async def test_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TestModal(self))


class TogglePage(AdminView):
    """صفحة أزرار تشغيل/إيقاف عامة (ميزات / كشف / عقوبات) + أزرار إضافية."""

    def __init__(self, cog, gid, owner_id, section: str, spec: list, page: str, extras: Optional[list] = None):
        super().__init__(cog, gid, owner_id)
        for key, emoji, label, _ in spec:
            on = self.st[section][key]
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(section, key, page)
            self.add_item(btn)
        for label, emoji, cb in extras or []:
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            btn.callback = cb
            self.add_item(btn)
        back = discord.ui.Button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary)

        async def back_cb(i: discord.Interaction):
            await show_page(cog, i, gid, owner_id, "main")

        back.callback = back_cb
        self.add_item(back)

    def _make_cb(self, section: str, key: str, page: str):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            self.st[section][key] = not self.st[section][key]
            self.st["modified"] = True
            await self.cog.save_settings(self.gid)
            await show_page(self.cog, interaction, self.gid, self.owner_id, page)
        return cb


class WordsView(AdminView):
    def __init__(self, cog, gid, owner_id, page: int):
        super().__init__(cog, gid, owner_id)
        self.page = page
        entries = cog.sorted_entries(gid)
        pages = max(1, math.ceil(len(entries) / WORDS_PER_PAGE))
        self.page = min(max(0, page), pages - 1)
        chunk = entries[self.page * WORDS_PER_PAGE:(self.page + 1) * WORDS_PER_PAGE]
        if chunk:
            select = discord.ui.Select(placeholder="✏️ اختر كلمة لتعديل إعداداتها", row=0, options=[
                discord.SelectOption(label=clip(d["word"], 100), description=clip(f"{MATCH_TYPES.get(d.get('match'), '')} • {WORD_ACTIONS.get(d.get('action', 'auto'), '')}", 100),
                                     emoji={1: "🟢", 2: "🟠", 3: "🔴"}.get(d.get("severity", 2), "🟠"), value=d["key"][:100]) for d in chunk])

            async def pick_cb(i: discord.Interaction):
                await show_page(cog, i, gid, owner_id, "editor", keys=[select.values[0]])

            select.callback = pick_cb
            self.add_item(select)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page + 1 >= pages

    @discord.ui.button(label="إضافة كلمة", emoji="➕", style=discord.ButtonStyle.success, row=1)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordsModal(self))

    @discord.ui.button(label="حذف كلمات", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveWordsModal(self))

    @discord.ui.button(label="استيراد الافتراضية", emoji="📥", style=discord.ButtonStyle.primary, row=1)
    async def seed_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        added = await self.cog.ensure_seed(self.gid, force=True)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "words", note=f"📥 اتضاف `{added}` كلمة افتراضية جديدة.")

    @discord.ui.button(label="كلمات مسموحة", emoji="✅", style=discord.ButtonStyle.secondary, row=1)
    async def white_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def save(items: list):
            self.st["whitelist_words"] = items
            self.cog.matchers.pop(self.gid, None)
            await self.cog.save_settings(self.gid)
        await interaction.response.send_modal(ListModal(self, "✅ الكلمات المسموحة", "كلمات مستثناة من الفلتر (سطر لكل كلمة)", self.st["whitelist_words"], save, "words"))

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.primary, row=2)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "words", page=self.page - 1)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.primary, row=2)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "words", page=self.page + 1)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "main")


class WordEditorView(AdminView):
    """تعديل مباشر لإعدادات كلمة (أو مجموعة كلمات اتضافت مع بعض): كل تغيير بيتحفظ فوراً."""

    def __init__(self, cog, gid, owner_id, keys: list):
        super().__init__(cog, gid, owner_id)
        self.keys = keys
        d = cog.entries.get(gid, {}).get(keys[0]) or {}
        specs = (
            ("match", "🎯 طريقة المطابقة", {k: (v, "") for k, v in MATCH_TYPES.items()}, d.get("match", "word"), 0),
            ("severity", "⚠️ درجة الخطورة (النقاط)", {k: (v, "") for k, v in SEVERITY.items()}, d.get("severity", 2), 1),
            ("action", "⚖️ العقوبة", {k: (v, "") for k, v in WORD_ACTIONS.items()}, d.get("action", "auto"), 2),
        )
        for field, placeholder, options, current, row in specs:
            select = discord.ui.Select(placeholder=placeholder, row=row, options=[
                discord.SelectOption(label=label, value=str(k), default=(str(k) == str(current))) for k, (label, _) in options.items()])
            select.callback = self._make_cb(field, select)
            self.add_item(select)
        strict = bool(d.get("strict", False))
        self.strict_btn.label = "كشف التحايل: متوقف (صارم)" if strict else "كشف التحايل: شغال (ذكي)"
        self.strict_btn.style = discord.ButtonStyle.secondary if strict else discord.ButtonStyle.success

    def _make_cb(self, field: str, select: discord.ui.Select):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            value = int(select.values[0]) if field == "severity" else select.values[0]
            await self.cog.update_words(self.gid, self.keys, {field: value}, interaction.user)
            await show_page(self.cog, interaction, self.gid, self.owner_id, "editor", keys=self.keys)
        return cb

    @discord.ui.button(label="كشف التحايل", emoji="🕵️", row=3)
    async def strict_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        d = self.cog.entries.get(self.gid, {}).get(self.keys[0]) or {}
        await self.cog.update_words(self.gid, self.keys, {"strict": not d.get("strict", False)}, interaction.user)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "editor", keys=self.keys)

    @discord.ui.button(label="حذف", emoji="🗑️", style=discord.ButtonStyle.danger, row=3)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        removed = await self.cog.remove_words(self.gid, self.keys, interaction.user)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "words", note=f"🗑️ اتحذف `{removed}` كلمة.")

    @discord.ui.button(label="قائمة الكلمات", emoji="↩️", style=discord.ButtonStyle.secondary, row=3)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "words")


class LinksView(AdminView):
    def __init__(self, cog, gid, owner_id):
        super().__init__(cog, gid, owner_id)
        lk = self.st["links"]
        self.bare_btn.style = discord.ButtonStyle.success if lk["block_bare"] else discord.ButtonStyle.secondary
        self.own_btn.style = discord.ButtonStyle.success if lk["allow_own_invite"] else discord.ButtonStyle.secondary

    @discord.ui.button(label="الدومينات المسموحة", emoji="🌐", style=discord.ButtonStyle.primary, row=0)
    async def domains_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def save(items: list):
            self.st["links"]["allowed_domains"] = [re.sub(r"^(?:https?://)?(?:www\.)?", "", d).split("/")[0] for d in items]
            await self.cog.save_settings(self.gid)
        await interaction.response.send_modal(ListModal(self, "🌐 الدومينات المسموحة", "دومين في كل سطر (مثال: youtube.com)", self.st["links"]["allowed_domains"], save, "links"))

    @discord.ui.button(label="كشف الدومينات من غير http", emoji="🔎", row=0)
    async def bare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.st["links"]["block_bare"] = not self.st["links"]["block_bare"]
        self.st["modified"] = True
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "links")

    @discord.ui.button(label="السماح بدعوة سيرفرنا (Vanity)", emoji="📨", row=1)
    async def own_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.st["links"]["allow_own_invite"] = not self.st["links"]["allow_own_invite"]
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "links")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "main")


class LogView(AdminView):
    def __init__(self, cog, gid, owner_id):
        super().__init__(cog, gid, owner_id)
        self.content_btn.style = discord.ButtonStyle.success if self.st["log_content"] else discord.ButtonStyle.secondary

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📋 اختر روم السجلات (امسح الاختيار للإيقاف)", channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=0, max_values=1, row=0)
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        note = None
        if select.values:
            channel = interaction.guild.get_channel(select.values[0].id)
            perms = channel.permissions_for(interaction.guild.me) if channel else None
            if channel is None or not (perms.send_messages and perms.embed_links):
                note = "⚠️ البوت معندوش Send Messages + Embed Links في الروم دي — السجلات مش هتوصل."
            self.st["log_channel_id"] = select.values[0].id
        else:
            self.st["log_channel_id"] = None
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "log", note=note)

    @discord.ui.button(label="محتوى الرسالة في السجل", emoji="💬", row=1)
    async def content_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.st["log_content"] = not self.st["log_content"]
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "log")

    @discord.ui.button(label="رسالة تجريبية", emoji="🧪", style=discord.ButtonStyle.primary, row=1)
    async def test_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        ok = await self.cog.send_log(interaction.guild, discord.Embed(title="🧪 رسالة تجريبية", description="لو شايف الرسالة دي يبقى السجلات شغالة تمام ✅", color=COLOR_BLUE, timestamp=discord.utils.utcnow()))
        await interaction.followup.send(embed=ok_embed("✅ اتبعتت", "شوف روم السجلات.") if ok else err_embed("مقدرتش أبعت: اختار روم والبوت محتاج Send Messages + Embed Links فيها."), ephemeral=True)

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "main")


class ExemptView(AdminView):
    def __init__(self, cog, gid, owner_id):
        super().__init__(cog, gid, owner_id)
        self.staff_btn.style = discord.ButtonStyle.success if self.st["exempt_staff"] else discord.ButtonStyle.secondary

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🛡️ رتب مستثناة (امسح الاختيار للإزالة)", min_values=0, max_values=10, row=0)
    async def roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await interaction.response.defer()
        self.st["exempt_roles"] = [r.id for r in select.values if not r.is_default()]
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "exempt")

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="📁 رومات مستثناة (امسح الاختيار للإزالة)", channel_types=[discord.ChannelType.text, discord.ChannelType.news, discord.ChannelType.voice, discord.ChannelType.category, discord.ChannelType.forum], min_values=0, max_values=25, row=1)
    async def channels(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.defer()
        self.st["exempt_channels"] = [c.id for c in select.values]
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "exempt")

    @discord.ui.button(label="استثناء المشرفين (Manage Messages)", emoji="👮", row=2)
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.st["exempt_staff"] = not self.st["exempt_staff"]
        await self.cog.save_settings(self.gid)
        await show_page(self.cog, interaction, self.gid, self.owner_id, "exempt")

    @discord.ui.button(label="رجوع", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_page(self.cog, interaction, self.gid, self.owner_id, "main")


# ==============================================================================
# 🛡️ الـ Cog الرئيسي
# ==============================================================================
class UltimateSecurityCog(commands.Cog):
    security_group = app_commands.Group(name="security", description="[إدارة الحماية] لوحة التحكم وسجل المخالفات", guild_only=True)
    badwords_group = app_commands.Group(name="badwords", description="[إدارة الحماية] إضافة وتعديل وحذف الكلمات المحظورة", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: dict[int, dict] = {}
        self.entries: dict[int, dict[str, dict]] = {}
        self.matchers: dict[int, Matcher] = {}
        self.strikes: dict[tuple, dict] = {}
        self.flood: dict[tuple, deque] = {}
        self.repeat: dict[tuple, deque] = {}
        self.recent_action: dict[tuple, float] = {}
        self.locks: dict[tuple, asyncio.Lock] = {}
        self.loaded = False

    async def cog_load(self):
        try:
            await run_db(ensure_indexes_sync)
        except Exception:
            log.warning("فشل إنشاء الـ indexes", exc_info=True)
        self.maintenance.start()

    async def cog_unload(self):
        self.maintenance.cancel()

    # ---------- التحميل والصيانة ----------
    async def load_all(self):
        settings_docs, word_docs = await run_db(load_all_sync)
        self.settings = {}
        for doc in settings_docs:
            st = deep_merge(default_settings(), {k: v for k, v in doc.items() if k != "_id"})
            self.settings[int(doc["_id"])] = st
        self.entries = {}
        for d in word_docs:
            self.entries.setdefault(d["guild_id"], {})[d["key"]] = d
        self.matchers.clear()
        self.loaded = True

    @tasks.loop(seconds=60)
    async def maintenance(self):
        try:
            if not self.loaded:
                await self.load_all()
            now = time.monotonic()
            for store, ttl in ((self.flood, 300), (self.repeat, 600)):
                for k in [k for k, q in store.items() if not q or now - q[-1][0] > ttl]:
                    store.pop(k, None)
            for k in [k for k, t in self.recent_action.items() if now - t > 60]:
                self.recent_action.pop(k, None)
                lock = self.locks.get(k)
                if lock is not None and not lock.locked():
                    self.locks.pop(k, None)
        except Exception:
            log.exception("خطأ في مهمة الصيانة")

    @maintenance.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()
        if not self.bot.intents.message_content:
            log.warning("Intent الـ message_content مقفول: فلتر الكلمات والروابط مش هيشتغل.")

    # ---------- الإعدادات والكلمات ----------
    def get_settings(self, gid: int) -> dict:
        if gid not in self.settings:
            self.settings[gid] = default_settings()
        return self.settings[gid]

    async def save_settings(self, gid: int):
        await run_db(save_settings_sync, gid, self.settings[gid])

    def get_matcher(self, gid: int) -> Matcher:
        m = self.matchers.get(gid)
        if m is None:
            m = self.matchers[gid] = Matcher(list(self.entries.get(gid, {}).values()), self.get_settings(gid)["whitelist_words"])
        return m

    def sorted_entries(self, gid: int) -> list[dict]:
        return sorted(self.entries.get(gid, {}).values(), key=lambda d: (-int(d.get("severity", 2)), d["word"]))

    async def set_level(self, gid: int, level: str, actor: discord.abc.User):
        st = self.get_settings(gid)
        apply_level(st, level)
        st["enabled"] = True
        await self.save_settings(gid)
        await self.ensure_seed(gid)
        guild = self.bot.get_guild(gid)
        if guild:
            await self.audit(guild, actor, f"تطبيق مستوى الحماية **{LEVELS[level]['label']}**")

    async def ensure_seed(self, gid: int, force: bool = False) -> int:
        st = self.get_settings(gid)
        if st["words_seeded"] and not force:
            return 0
        docs = [self.make_word_doc(gid, w, 0, match=m, severity=s, action=a, strict=strict) for w, m, s, a, strict in DEFAULT_WORDS]
        added = await run_db(add_words_sync, [d for d in docs if d["key"]])
        for d in added:
            self.entries.setdefault(gid, {})[d["key"]] = d
        st["words_seeded"] = True
        self.matchers.pop(gid, None)
        await self.save_settings(gid)
        return len(added)

    @staticmethod
    def make_word_doc(gid: int, word: str, user_id: int, match="word", severity=2, action="auto", strict=False) -> dict:
        return {"guild_id": gid, "word": word.strip(), "key": word_key(word), "match": match, "severity": severity, "action": action,
                "strict": strict, "added_by": user_id, "added_at": int(time.time())}

    async def add_words(self, gid: int, words: list[str], actor: discord.abc.User) -> list[str]:
        docs = [self.make_word_doc(gid, w, actor.id) for w in words]
        keys = [d["key"] for d in docs if d["key"]]
        added = await run_db(add_words_sync, [d for d in docs if d["key"]])
        for d in added:
            self.entries.setdefault(gid, {})[d["key"]] = d
        if not self.get_settings(gid)["words_seeded"]:
            self.get_settings(gid)["words_seeded"] = True  # الأدمن بدأ قائمته بنفسه: ما نزودش الافتراضي أوتوماتيك
            await self.save_settings(gid)
        self.matchers.pop(gid, None)
        guild = self.bot.get_guild(gid)
        if guild and added:
            await self.audit(guild, actor, "إضافة كلمات محظورة: " + "، ".join(f"`{clip(d['word'], 30)}`" for d in added[:10]))
        return keys

    async def update_words(self, gid: int, keys: list, sets: dict, actor: discord.abc.User):
        await run_db(update_words_sync, gid, keys, sets)
        for k in keys:
            if k in self.entries.get(gid, {}):
                self.entries[gid][k].update(sets)
        self.matchers.pop(gid, None)

    async def remove_words(self, gid: int, keys: list, actor: discord.abc.User) -> int:
        removed = await run_db(delete_words_sync, gid, keys)
        for k in keys:
            self.entries.get(gid, {}).pop(k, None)
        self.matchers.pop(gid, None)
        guild = self.bot.get_guild(gid)
        if guild and removed:
            await self.audit(guild, actor, f"حذف `{removed}` كلمة من الحظر")
        return removed

    # ---------- السجلات ----------
    async def send_log(self, guild: discord.Guild, embed: discord.Embed) -> bool:
        st = self.get_settings(guild.id)
        channel = guild.get_channel(st["log_channel_id"]) if st["log_channel_id"] else None
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            return False
        perms = channel.permissions_for(guild.me)
        if not (perms.send_messages and perms.embed_links):
            return False
        try:
            embed.set_footer(text="Z I UO Enterprise Security & Automod Engine")
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return True
        except discord.HTTPException:
            log.warning("فشل إرسال سجل الحماية", exc_info=True)
            return False

    async def audit(self, guild: discord.Guild, actor: discord.abc.User, text: str):
        await self.send_log(guild, discord.Embed(title="🛠️ تعديل في نظام الحماية", description=f"{actor.mention} — {text}", color=COLOR_BLUE, timestamp=discord.utils.utcnow()))

    # ---------- العقوبات والنقاط ----------
    async def get_strikes(self, gid: int, uid: int) -> dict:
        key = (gid, uid)
        data = self.strikes.get(key)
        if data is None:
            try:
                doc = await run_db(get_strikes_sync, gid, uid)
            except Exception:
                log.warning("تعذر تحميل مخالفات العضو %s", uid, exc_info=True)
                doc = {}
            data = {"entries": [list(e) for e in doc.get("entries", [])], "timeouts": list(doc.get("timeouts", []))}
            self.strikes[key] = data
        return data

    @staticmethod
    def active_points(data: dict, decay: int) -> int:
        cutoff = time.time() - decay
        return sum(int(e[1]) for e in data["entries"] if e[0] > cutoff)

    async def persist_strikes(self, gid: int, uid: int, data: dict, decay: int):
        now = time.time()
        data["entries"] = [e for e in data["entries"] if e[0] > now - max(decay, 30 * 86400)][-60:]
        data["timeouts"] = [t for t in data["timeouts"] if t > now - ESCALATION_WINDOW]
        try:
            await run_db(save_strikes_sync, gid, uid, data["entries"], data["timeouts"])
        except Exception:
            log.warning("تعذر حفظ مخالفات العضو %s", uid, exc_info=True)

    async def do_action(self, guild: discord.Guild, member: discord.Member, action: str, st: dict, data: dict, v: Violation) -> tuple[str, int, Optional[str]]:
        """بينفّذ العقوبة بعد فحص الصلاحيات. بيرجّع (العقوبة الفعلية, مدة التايم أوت, سبب الفشل)."""
        if action in ("none", "warn"):
            return action, 0, None
        p, me = st["punish"], guild.me
        reason = clip(f"Automod: {v.reason}", 400)
        if member.id == guild.owner_id or member.top_role >= me.top_role:
            return "warn", 0, "رتبة العضو أعلى من رتبة البوت (أو صاحب السيرفر)"
        try:
            if action == "timeout":
                if not me.guild_permissions.moderate_members:
                    return "warn", 0, "البوت محتاج صلاحية Timeout Members"
                if member.guild_permissions.administrator:
                    return "warn", 0, "ديسكورد مابيسمحش بتايم أوت للأدمن"
                prev = sum(1 for t in data["timeouts"] if t > time.time() - ESCALATION_WINDOW)
                dur = timeout_seconds(p, prev)
                await member.timeout(datetime.timedelta(seconds=dur), reason=reason)
                data["timeouts"].append(time.time())
                return "timeout", dur, None
            if action == "kick":
                if not me.guild_permissions.kick_members:
                    return "warn", 0, "البوت محتاج صلاحية Kick Members"
                await member.kick(reason=reason)
                return "kick", 0, None
            if action == "ban":
                if not me.guild_permissions.ban_members:
                    return "warn", 0, "البوت محتاج صلاحية Ban Members"
                await guild.ban(member, reason=reason, delete_message_seconds=0)
                return "ban", 0, None
        except discord.Forbidden:
            return "warn", 0, "ديسكورد رفض التنفيذ (صلاحيات)"
        except discord.HTTPException as e:
            return "warn", 0, f"خطأ من ديسكورد: {clip(e, 100)}"
        return "warn", 0, None

    async def punish(self, message: discord.Message, member: discord.Member, st: dict, v: Violation, stale: list):
        guild, p = message.guild, st["punish"]
        key = (guild.id, member.id)
        if p["delete"] or v.rule in ("spam",):
            targets = [message] + [m for m in stale if m.id != message.id]
            results = await asyncio.gather(*[m.delete() for m in targets], return_exceptions=True)
            if isinstance(results[0], discord.Forbidden):
                log.warning("البوت معندوش Manage Messages في %s", message.channel)
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            if now - self.recent_action.get(key, 0) < RECENT_GUARD:
                return  # رشق رسايل متزامن: عقوبة واحدة بس
            self.recent_action[key] = now
            data = await self.get_strikes(guild.id, member.id)
            counted = v.action != "delete" and v.points > 0
            if counted:
                data["entries"].append([time.time(), v.points, v.rule, clip(v.reason, 80)])
            total = self.active_points(data, p["decay_seconds"])
            ladder = decide_action(total, p) if counted else "none"
            forced = v.action if v.action in ("warn", "timeout", "kick", "ban") else "none"
            wanted = stronger(ladder, forced)
            applied, dur, failure = await self.do_action(guild, member, wanted, st, data, v)
            await self.persist_strikes(guild.id, member.id, data, p["decay_seconds"])
        await self.notify(message, member, st, v, applied, dur, total)
        await self.log_violation(message, member, st, v, wanted, applied, dur, total, failure)

    async def notify(self, message: discord.Message, member: discord.Member, st: dict, v: Violation, applied: str, dur: int, total: int):
        p = st["punish"]
        action_text = {"none": "تم حذف الرسالة", "warn": "تحذير + حذف الرسالة", "timeout": f"تايم أوت لمدة {fmt_dur(dur)}", "kick": "طرد من السيرفر", "ban": "حظر من السيرفر"}[applied]
        if p["notify_channel"] and applied not in ("kick", "ban"):
            embed = discord.Embed(color=COLOR_ORANGE, description=f"⚠️ {member.mention} **تنبيه نظام الحماية الآلي**\n└ **السبب:** {v.reason}\n└ **الإجراء:** {action_text}\n└ **نقاط المخالفات:** {total}")
            try:
                await message.channel.send(embed=embed, delete_after=max(3, int(st.get("notify_delete_after", 8))), allowed_mentions=discord.AllowedMentions(users=[member]))
            except discord.HTTPException:
                pass
        if p["dm_user"]:
            try:
                await member.send(embed=discord.Embed(title=f"⚠️ مخالفة في {message.guild.name}", color=COLOR_ORANGE,
                                                      description=f"**السبب:** {v.reason}\n**الإجراء:** {action_text}\n**نقاطك الحالية:** {total}\nلو شايف إن ده خطأ، كلّم الإدارة."))
            except discord.HTTPException:
                pass

    async def log_violation(self, message: discord.Message, member: discord.Member, st: dict, v: Violation, wanted: str, applied: str, dur: int, total: int, failure: Optional[str]):
        colors = {"none": COLOR_ORANGE, "warn": COLOR_ORANGE, "timeout": COLOR_RED, "kick": COLOR_DARKRED, "ban": COLOR_DARKRED}
        titles = {"none": "🗑️ مخالفة — حذف رسالة", "warn": "⚠️ مخالفة — تحذير", "timeout": "⏳ مخالفة — تايم أوت", "kick": "👢 مخالفة — طرد", "ban": "🔨 مخالفة — حظر"}
        embed = discord.Embed(title=titles[applied], color=colors[applied], timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 العضو", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="📍 القناة", value=message.channel.mention, inline=True)
        embed.add_field(name="🧩 القاعدة", value=RULE_LABEL[v.rule], inline=True)
        embed.add_field(name="📝 السبب", value=v.reason, inline=False)
        if v.detail:
            embed.add_field(name="🔎 المطابقة", value=f"`{clip(v.detail, 100)}`" + (f" — {v.how}" if v.how else ""), inline=False)
        action_text = ACTION_LABEL[applied] + (f" ({fmt_dur(dur)})" if applied == "timeout" else "")
        embed.add_field(name="⚖️ الإجراء", value=action_text, inline=True)
        embed.add_field(name="📊 النقاط", value=f"+{v.points if v.action != 'delete' else 0} (الإجمالي {total})", inline=True)
        if failure:
            embed.add_field(name="❗ تعذر تنفيذ العقوبة", value=f"المطلوب: {ACTION_LABEL[wanted]} — {failure}", inline=False)
        if st["log_content"] and message.content:
            embed.add_field(name="💬 محتوى الرسالة", value="```" + clip(message.content.replace("`", "ˋ"), 900) + "```", inline=False)
        await self.send_log(message.guild, embed)

    # ---------- محرك الفحص ----------
    def exempt(self, member: discord.Member, channel, st: dict) -> bool:
        if member.id == member.guild.owner_id:
            return True
        if st["exempt_staff"] and (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            return True
        if st["exempt_roles"] and any(r.id in st["exempt_roles"] for r in member.roles):
            return True
        ids = {channel.id, getattr(channel, "category_id", None), getattr(channel, "parent_id", None)}
        return bool(st["exempt_channels"] and ids & set(st["exempt_channels"]))

    def track_spam(self, message: discord.Message, st: dict) -> Optional[Violation]:
        f, th = st["features"], st["thresholds"]
        key, now = (message.guild.id, message.author.id), time.monotonic()
        if f["spam"]:
            q = self.flood.setdefault(key, deque(maxlen=20))
            q.append((now, message))
            recent = [m for t, m in q if now - t <= th["spam_seconds"]]
            if len(recent) >= th["spam_messages"]:
                q.clear()
                v = Violation("spam", "إرسال رسائل متتالية بسرعة كبيرة", points=RULE_POINTS["spam"], detail=f"{len(recent)} رسالة", purge=True)
                v.detail += ""
                self._purge = recent
                return v
        if f["repeat"] and len(message.content) >= 4:
            norm = alnum(basic_norm(message.content))
            if len(norm) >= 4:
                q = self.repeat.setdefault(key, deque(maxlen=12))
                q.append((now, norm))
                same = sum(1 for t, n in q if n == norm and now - t <= th["repeat_seconds"])
                if same >= th["repeat_count"]:
                    q.clear()
                    return Violation("repeat", "تكرار نفس الرسالة عدة مرات", points=RULE_POINTS["repeat"], detail=f"{same} مرات")
        return None

    async def scan(self, message: discord.Message, edited: bool):
        if not self.loaded or message.guild is None or message.author.bot or message.webhook_id:
            return
        st = self.settings.get(message.guild.id)
        if not st or not st["enabled"]:
            return
        if edited and not st["features"]["edits"]:
            return
        member = message.author
        if not isinstance(member, discord.Member) or self.exempt(member, message.channel, st):
            return
        mentions = len({m.id for m in message.mentions}) + len(message.role_mentions)
        v = content_violation(message.content or "", st, self.get_matcher(message.guild.id), mentions, message.guild.vanity_url_code)
        stale: list = []
        if v is None and not edited:
            self._purge = []
            v = self.track_spam(message, st)
            stale = getattr(self, "_purge", [])
        if v is not None:
            try:
                await self.punish(message, member, st, v, stale)
            except Exception:
                log.exception("خطأ أثناء تنفيذ عقوبة الحماية")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.scan(message, edited=False)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content != after.content:
            await self.scan(after, edited=True)

    # ---------- بناء صفحات اللوحة ----------
    def build_page(self, gid: int, owner_id: int, page: str, **kw) -> tuple[discord.Embed, discord.ui.View]:
        st = self.get_settings(gid)
        note = kw.get("note")
        guild = self.bot.get_guild(gid)
        if page == "features":
            lines = [f"{'✅' if st['features'][k] else '⬜'} {e} **{n}** — {d}" for k, e, n, d in FEATURES]
            return self.page_embed("🧩 الميزات", "اضغط أي زرار عشان تشغّل/توقف الميزة فوراً:\n\n" + "\n".join(lines), note), TogglePage(self, gid, owner_id, "features", FEATURES, "features")
        if page == "detect":
            lines = [f"{'✅' if st['detection'][k] else '⬜'} {e} **{n}** — `{d}`" for k, e, n, d in DETECTION]
            desc = "كل خيار بيخلي الفلتر يفهم نوع تحايل مختلف (والمطابقة دايماً بكلمة كاملة عشان ما يحصلش تايم أوت غلط):\n\n" + "\n".join(lines)
            return self.page_embed("🔎 الكشف الذكي", desc, note), TogglePage(self, gid, owner_id, "detection", DETECTION, "detect")
        if page == "punish":
            p = st["punish"]
            lines = [f"{'✅' if p[k] else '⬜'} {e} **{n}** — {d}" for k, e, n, d in PUNISH_TOGGLES]
            ladder = (f"⚠️ تحذير من **{p['warn_at'] or '—'}** نقطة • ⏳ تايم أوت من **{p['timeout_at'] or '—'}** ({fmt_dur(p['timeout_seconds'])}، أقصى {fmt_dur(p['max_timeout_seconds'])})\n"
                      f"👢 طرد من **{p['kick_at'] or '—'}** • 🔨 حظر من **{p['ban_at'] or '—'}** • ♻️ النقاط بتتلاشى بعد **{fmt_dur(p['decay_seconds'])}**\n_(0 = الخطوة دي متوقفة)_")
            view_holder: dict = {}

            async def thresholds_cb(i: discord.Interaction):
                await i.response.send_modal(SettingsModal(view_holder["v"], "⚖️ عتبات العقوبات (بالنقاط)", [
                    ("punish", "warn_at", "تحذير من كام نقطة؟", "int", 0, 100, 0), ("punish", "timeout_at", "تايم أوت من كام نقطة؟", "int", 0, 100, 0),
                    ("punish", "kick_at", "طرد من كام نقطة؟ (0 = متوقف)", "int", 0, 100, 0), ("punish", "ban_at", "حظر من كام نقطة؟ (0 = متوقف)", "int", 0, 100, 0)], "punish"))

            async def durations_cb(i: discord.Interaction):
                await i.response.send_modal(SettingsModal(view_holder["v"], "⏱️ المدد", [
                    ("punish", "timeout_seconds", "مدة التايم أوت (10m / 1h)", "dur", 60, MAX_TIMEOUT, 60), ("punish", "max_timeout_seconds", "أقصى مدة تايم أوت", "dur", 60, MAX_TIMEOUT, 60),
                    ("punish", "decay_seconds", "تلاشي النقاط بعد (24h)", "dur", 600, 30 * 86400, 3600), (None, "notify_delete_after", "مسح التنبيه بعد (ثواني)", "int", 3, 120, 1)], "punish"))

            view = TogglePage(self, gid, owner_id, "punish", PUNISH_TOGGLES, "punish", [("عتبات العقوبات", "⚖️", thresholds_cb), ("المدد", "⏱️", durations_cb)])
            view_holder["v"] = view
            return self.page_embed("⚖️ العقوبات", "\n".join(lines) + "\n\n**سلّم العقوبات (بنقاط المخالفات):**\n" + ladder, note), view
        if page == "limits":
            th = st["thresholds"]
            desc = (f"⚡ سبام: `{th['spam_messages']}` رسائل في `{th['spam_seconds']}`ث • 🔁 تكرار: `{th['repeat_count']}` مرات في `{th['repeat_seconds']}`ث\n"
                    f"🔠 حروف كبيرة: `{th['caps_percent']}%` (من `{th['caps_min_letters']}` حرف) • 😀 إيموجي: `{th['max_emojis']}` • 📣 منشن: `{th['max_mentions']}`\n"
                    f"♾️ تكرار حرف: `{th['char_repeat']}` • 🌀 Zalgo: `{th['zalgo_marks']}` علامة")
            holder: dict = {}

            async def a_cb(i: discord.Interaction):
                await i.response.send_modal(SettingsModal(holder["v"], "⚡ حدود السبام والتكرار", [
                    ("thresholds", "spam_messages", "عدد رسائل السبام", "int", 2, 30, 0), ("thresholds", "spam_seconds", "خلال كام ثانية؟", "int", 1, 60, 0),
                    ("thresholds", "repeat_count", "عدد مرات التكرار", "int", 2, 20, 0), ("thresholds", "repeat_seconds", "نافذة التكرار (ثواني)", "int", 5, 600, 0),
                    ("thresholds", "caps_percent", "نسبة الحروف الكبيرة %", "int", 30, 100, 0)], "limits"))

            async def b_cb(i: discord.Interaction):
                await i.response.send_modal(SettingsModal(holder["v"], "📏 حدود المحتوى", [
                    ("thresholds", "caps_min_letters", "أقل عدد حروف لفحص الكابس", "int", 3, 100, 0), ("thresholds", "max_emojis", "أقصى عدد إيموجي", "int", 1, 50, 0),
                    ("thresholds", "max_mentions", "أقصى عدد منشن", "int", 1, 50, 0), ("thresholds", "char_repeat", "حد تكرار الحرف", "int", 4, 100, 0),
                    ("thresholds", "zalgo_marks", "حد علامات Zalgo", "int", 2, 50, 0)], "limits"))

            view = TogglePage(self, gid, owner_id, "features", [], "limits", [("حدود السبام والتكرار", "⚡", a_cb), ("حدود المحتوى", "📏", b_cb)])
            holder["v"] = view
            return self.page_embed("📏 الحدود", desc, note), view
        if page == "words":
            entries = self.sorted_entries(gid)
            view = WordsView(self, gid, owner_id, kw.get("page", 0))
            chunk = entries[view.page * WORDS_PER_PAGE:(view.page + 1) * WORDS_PER_PAGE]
            lines = [f"{ {1: '🟢', 2: '🟠', 3: '🔴'}.get(d.get('severity', 2), '🟠') } `{clip(d['word'], 40)}` — {MATCH_TYPES.get(d.get('match'), '')}" + (" • 🔒 صارم" if d.get("strict") else "") + f" • {WORD_ACTIONS.get(d.get('action', 'auto'), '').split(' (')[0]}" for d in chunk]
            pages = max(1, math.ceil(len(entries) / WORDS_PER_PAGE))
            desc = (f"عدد الكلمات: **{len(entries)}** • الكلمات المسموحة: **{len(st['whitelist_words'])}**\n\n" + ("\n".join(lines) or "_مفيش كلمات لسه — اضغط ➕ إضافة كلمة أو 📥 استيراد الافتراضية._")
                    + "\n\n✏️ اختار كلمة من القائمة عشان تعدّل إعداداتها (التعديل فوري).")
            embed = self.page_embed("🔤 الكلمات المحظورة", desc, note)
            embed.set_footer(text=f"صفحة {view.page + 1} من {pages}")
            return embed, view
        if page == "editor":
            keys = [k for k in kw.get("keys", []) if k in self.entries.get(gid, {})]
            if not keys:
                return self.build_page(gid, owner_id, "words", note="⚠️ الكلمة مش موجودة.")
            d = self.entries[gid][keys[0]]
            shown = "، ".join(f"`{clip(self.entries[gid][k]['word'], 30)}`" for k in keys[:10])
            desc = (f"**الكلمة:** {shown}" + (f" _(+{len(keys) - 10})_" if len(keys) > 10 else "") + ("\n_التعديلات هتتطبق على كل الكلمات اللي اتضافت مع بعض._" if len(keys) > 1 else "") + "\n\n"
                    f"🎯 **المطابقة:** {MATCH_TYPES.get(d.get('match', 'word'))}\n⚠️ **الخطورة:** {SEVERITY.get(d.get('severity', 2))}\n⚖️ **العقوبة:** {WORD_ACTIONS.get(d.get('action', 'auto'))}\n"
                    f"🕵️ **كشف التحايل:** {'متوقف (مطابقة حرفية صارمة)' if d.get('strict') else 'شغال (بيفهم الرموز والفواصل والتكرار)'}\n\n"
                    "• **كلمة كاملة (ذكي):** بتتطابق مع الكلمة نفسها بس، مش جزء من كلمة تانية.\n• **مطابقة تامة:** الكلمة زي ما هي بالظبط.\n• **يحتوي:** في أي مكان (استخدمه بحذر).")
            return self.page_embed("✏️ إعدادات الكلمة", desc, note), WordEditorView(self, gid, owner_id, keys)
        if page == "links":
            lk = st["links"]
            desc = (f"🌐 **الدومينات المسموحة:** " + (" ".join(f"`{d}`" for d in lk["allowed_domains"][:20]) or "_مفيش_") + "\n"
                    f"🔎 **كشف الدومينات من غير http:** {'✅' if lk['block_bare'] else '⬜'}\n📨 **السماح بدعوة سيرفرنا:** {'✅' if lk['allow_own_invite'] else '⬜'}")
            return self.page_embed("🌐 الروابط", desc, note), LinksView(self, gid, owner_id)
        if page == "log":
            ch = f"<#{st['log_channel_id']}>" if st["log_channel_id"] else "`غير محددة`"
            desc = f"📋 **روم السجلات:** {ch}\n💬 **محتوى الرسالة في السجل:** {'✅' if st['log_content'] else '⬜'}\n\nبتتسجل: المخالفات، التايم أوت، الطرد، الحظر، وتعديلات الإعدادات."
            return self.page_embed("📋 السجلات", desc, note), LogView(self, gid, owner_id)
        if page == "exempt":
            roles = " ".join(f"<@&{r}>" for r in st["exempt_roles"]) or "_مفيش_"
            chans = " ".join(f"<#{c}>" for c in st["exempt_channels"]) or "_مفيش_"
            desc = f"👮 **استثناء المشرفين:** {'✅' if st['exempt_staff'] else '⬜'}\n🛡️ **رتب مستثناة:** {roles}\n📁 **رومات مستثناة:** {chans}"
            return self.page_embed("🛡️ الاستثناءات", desc, note), ExemptView(self, gid, owner_id)
        # الرئيسية
        level = LEVELS.get(st["level"] or "", None)
        level_text = (f"{level['emoji']} {level['label']}" + (" _(معدّل)_" if st["modified"] else "")) if level else "`لم يتم اختيار مستوى`"
        on = [n for k, e, n, d in FEATURES if st["features"][k]]
        ch = f"<#{st['log_channel_id']}>" if st["log_channel_id"] else "`غير محددة`"
        p = st["punish"]
        desc = (f"> نظام الحماية والفلترة المركزي — اختار مستوى جاهز من القائمة وبعدها عدّل أي حاجة.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**الحالة:** {'🟢 شغال' if st['enabled'] else '🔴 متوقف'}\n**المستوى:** {level_text}\n**السجلات:** {ch}\n"
                f"**الميزات المفعلة ({len(on)}/{len(FEATURES)}):** {'، '.join(on) or '—'}\n"
                f"**العقوبات:** ⚠️ {p['warn_at'] or '—'} • ⏳ {p['timeout_at'] or '—'} • 👢 {p['kick_at'] or '—'} • 🔨 {p['ban_at'] or '—'}\n"
                f"**الكلمات المحظورة:** {len(self.entries.get(gid, {}))} • **استثناءات:** {len(st['exempt_roles'])} رتبة / {len(st['exempt_channels'])} روم")
        embed = self.page_embed("🛡️ لوحة تحكم نظام الحماية 〣 ZIUO PRO", desc, note)
        if not st["enabled"]:
            embed.set_footer(text="النظام متوقف — اختار مستوى أو اضغط تشغيل النظام")
        return embed, MainView(self, gid, owner_id)

    @staticmethod
    def page_embed(title: str, desc: str, note: Optional[str] = None) -> discord.Embed:
        return discord.Embed(title=title, description=clip(desc + (f"\n\n{note}" if note else ""), 4000), color=COLOR_DARK, timestamp=discord.utils.utcnow())

    # ---------- الأوامر ----------
    @security_group.command(name="panel", description="لوحة التحكم الشاملة لنظام الحماية (المستويات، الميزات، العقوبات، الكلمات، السجلات)")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await show_page(self, interaction, interaction.guild.id, interaction.user.id, "main")

    @security_group.command(name="history", description="عرض سجل مخالفات عضو ونقاطه الحالية")
    @app_commands.describe(member="العضو")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def security_history(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        st = self.get_settings(interaction.guild.id)
        data = await self.get_strikes(interaction.guild.id, member.id)
        entries = sorted(data["entries"], key=lambda e: e[0], reverse=True)[:12]
        lines = [f"<t:{int(e[0])}:R> • {RULE_LABEL.get(e[2], e[2])} • `+{e[1]}` — {clip(e[3], 50)}" for e in entries]
        total = self.active_points(data, st["punish"]["decay_seconds"])
        embed = discord.Embed(title=f"📚 سجل مخالفات {member.display_name}", color=COLOR_BLUE, description="\n".join(lines) or "✅ مفيش مخالفات مسجلة.")
        embed.add_field(name="النقاط الحالية", value=f"`{total}`", inline=True)
        embed.add_field(name="تايم أوت (آخر أسبوع)", value=f"`{sum(1 for t in data['timeouts'] if t > time.time() - ESCALATION_WINDOW)}`", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="pardon", description="مسح نقاط مخالفات عضو (عفو)")
    @app_commands.describe(member="العضو")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_pardon(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        data = await self.get_strikes(interaction.guild.id, member.id)
        data["entries"], data["timeouts"] = [], []
        await self.persist_strikes(interaction.guild.id, member.id, data, self.get_settings(interaction.guild.id)["punish"]["decay_seconds"])
        await self.audit(interaction.guild, interaction.user, f"عفو ومسح مخالفات {member.mention}")
        await interaction.followup.send(embed=ok_embed("🕊️ تم العفو", f"اتمسحت نقاط ومخالفات {member.mention}."), ephemeral=True)

    @badwords_group.command(name="add", description="إضافة كلمة محظورة وتظبيط إعداداتها فوراً")
    @app_commands.describe(word="الكلمة أو العبارة المراد حظرها")
    @app_commands.checks.has_permissions(administrator=True)
    async def badwords_add(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        if not word_key(word):
            await interaction.followup.send(embed=err_embed("الكلمة فاضية."), ephemeral=True)
            return
        keys = await self.add_words(gid, [word[:100]], interaction.user)
        embed, view = self.build_page(gid, interaction.user.id, "editor", keys=keys)
        await interaction.edit_original_response(embed=embed, view=view)

    @badwords_group.command(name="edit", description="تعديل إعدادات كلمة محظورة (المطابقة، الخطورة، العقوبة)")
    @app_commands.describe(word="الكلمة (هيظهر لك اقتراحات)")
    @app_commands.checks.has_permissions(administrator=True)
    async def badwords_edit(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer(ephemeral=True)
        gid, key = interaction.guild.id, word_key(word)
        if key not in self.entries.get(gid, {}):
            await interaction.followup.send(embed=err_embed(f"الكلمة `{clip(word, 40)}` مش موجودة في القائمة."), ephemeral=True)
            return
        embed, view = self.build_page(gid, interaction.user.id, "editor", keys=[key])
        await interaction.edit_original_response(embed=embed, view=view)

    @badwords_edit.autocomplete("word")
    async def badwords_edit_ac(self, interaction: discord.Interaction, current: str):
        cur = word_key(current)
        words = [d["word"] for d in self.sorted_entries(interaction.guild.id) if cur in d["key"]][:25]
        return [app_commands.Choice(name=clip(w, 100), value=clip(w, 100)) for w in words]

    @badwords_group.command(name="remove", description="إزالة كلمة من قائمة الحظر")
    @app_commands.describe(word="الكلمة المراد إزالتها")
    @app_commands.checks.has_permissions(administrator=True)
    async def badwords_remove(self, interaction: discord.Interaction, word: str):
        await interaction.response.defer(ephemeral=True)
        removed = await self.remove_words(interaction.guild.id, [word_key(word)], interaction.user)
        await interaction.followup.send(embed=ok_embed("✅ تمت الإزالة", f"اتحذفت `{clip(word, 40)}`.") if removed else err_embed("الكلمة مش موجودة في القائمة."), ephemeral=True)

    @badwords_remove.autocomplete("word")
    async def badwords_remove_ac(self, interaction: discord.Interaction, current: str):
        return await self.badwords_edit_ac(interaction, current)

    @badwords_group.command(name="list", description="استعراض الكلمات المحظورة وإعداداتها")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badwords_list(self, interaction: discord.Interaction):
        entries = self.sorted_entries(interaction.guild.id)
        if not entries:
            await interaction.response.send_message("🌟 قائمة الكلمات المحظورة فارغة حالياً.", ephemeral=True)
            return
        sev = {1: "🟢", 2: "🟠", 3: "🔴"}
        words = "، ".join(f"{sev.get(d.get('severity', 2), '🟠')}`{clip(d['word'], 30)}`" for d in entries)
        embed = discord.Embed(title="🛡️ قائمة الكلمات المحظورة", description=clip(f"> 🟢 خفيفة • 🟠 متوسطة • 🔴 شديدة\n\n{words}", 4000), color=COLOR_RED, timestamp=discord.utils.utcnow())
        embed.set_footer(text=f"{len(entries)} كلمة • للتعديل: /security panel")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await respond(interaction, content="❌ ليس لديك صلاحية استخدام هذا الأمر.", ephemeral=True)
            return
        log.exception("خطأ في أمر الحماية", exc_info=error)
        await report_error(interaction, getattr(error, "original", error))


async def setup(bot: commands.Bot):
    if _db is None:
        raise RuntimeError("MONGODB_URI غير موجود في ملف .env، نظام الحماية محتاج قاعدة بيانات لحفظ الإعدادات والكلمات.")
    await bot.add_cog(UltimateSecurityCog(bot))
