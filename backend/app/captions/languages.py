"""Languages the caption tool offers: speech languages (Whisper) plus Roman Urdu / Hinglish outputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lang:
    code: str           # our id ("ur", "ur-Latn", ...)
    name: str           # English name
    native: str         # name in the language
    script: str         # writing system of the captions (fonts.SCRIPT_FONT keys)
    rtl: bool = False
    whisper: str | None = None     # language code sent to speech-to-text (None = same as code)
    popular: bool = False

    @property
    def stt(self) -> str:
        return self.whisper or self.code

    def public(self) -> dict:
        return {"code": self.code, "name": self.name, "native": self.native, "script": self.script, "rtl": self.rtl,
                "popular": self.popular}


# Order = order in the picker (popular first). South Asian and Arabic languages are the focus.
LANGS: list[Lang] = [
    Lang("en", "English", "English", "latin", popular=True),
    Lang("ur", "Urdu", "اردو", "urdu", rtl=True, popular=True),
    Lang("ur-Latn", "Roman Urdu", "Roman Urdu", "latin", whisper="ur", popular=True),
    Lang("hi", "Hindi", "हिन्दी", "devanagari", popular=True),
    Lang("hi-Latn", "Hinglish (Roman Hindi)", "Hinglish", "latin", whisper="hi", popular=True),
    Lang("ar", "Arabic", "العربية", "arabic", rtl=True, popular=True),
    Lang("bn", "Bengali", "বাংলা", "bengali", popular=True),
    Lang("pa", "Punjabi", "ਪੰਜਾਬੀ", "gurmukhi", popular=True),
    Lang("es", "Spanish", "Español", "latin", popular=True),
    Lang("pt", "Portuguese", "Português", "latin", popular=True),
    Lang("fr", "French", "Français", "latin", popular=True),
    Lang("id", "Indonesian", "Bahasa Indonesia", "latin", popular=True),
    Lang("tr", "Turkish", "Türkçe", "latin", popular=True),
    Lang("fa", "Persian", "فارسی", "arabic", rtl=True),
    Lang("ps", "Pashto", "پښتو", "arabic", rtl=True),
    Lang("sd", "Sindhi", "سنڌي", "arabic", rtl=True),
    Lang("ta", "Tamil", "தமிழ்", "tamil"),
    Lang("te", "Telugu", "తెలుగు", "telugu"),
    Lang("mr", "Marathi", "मराठी", "devanagari"),
    Lang("gu", "Gujarati", "ગુજરાતી", "gujarati"),
    Lang("kn", "Kannada", "ಕನ್ನಡ", "kannada"),
    Lang("ml", "Malayalam", "മലയാളം", "malayalam"),
    Lang("ne", "Nepali", "नेपाली", "devanagari"),
    Lang("si", "Sinhala", "සිංහල", "sinhala"),
    Lang("de", "German", "Deutsch", "latin"),
    Lang("it", "Italian", "Italiano", "latin"),
    Lang("nl", "Dutch", "Nederlands", "latin"),
    Lang("pl", "Polish", "Polski", "latin"),
    Lang("ru", "Russian", "Русский", "latin"),
    Lang("uk", "Ukrainian", "Українська", "latin"),
    Lang("ro", "Romanian", "Română", "latin"),
    Lang("cs", "Czech", "Čeština", "latin"),
    Lang("sv", "Swedish", "Svenska", "latin"),
    Lang("el", "Greek", "Ελληνικά", "latin"),
    Lang("he", "Hebrew", "עברית", "hebrew", rtl=True),
    Lang("ms", "Malay", "Bahasa Melayu", "latin"),
    Lang("tl", "Filipino", "Filipino", "latin"),
    Lang("vi", "Vietnamese", "Tiếng Việt", "latin"),
    Lang("th", "Thai", "ไทย", "thai"),
    Lang("sw", "Swahili", "Kiswahili", "latin"),
    Lang("ja", "Japanese", "日本語", "japanese"),
    Lang("ko", "Korean", "한국어", "korean"),
    Lang("zh", "Chinese", "中文", "cjk"),
]

BY_CODE = {lang.code: lang for lang in LANGS}

# Whisper reports languages by English name in some APIs ("urdu"); map both ways.
_NAME_TO_CODE = {lang.name.lower(): lang.code for lang in LANGS if "-" not in lang.code}
_NAME_TO_CODE.update({"panjabi": "pa", "chinese": "zh", "mandarin": "zh", "persian": "fa", "farsi": "fa",
                      "tagalog": "tl", "filipino": "tl", "malay": "ms", "hindi": "hi", "urdu": "ur"})


def get(code: str | None) -> Lang | None:
    return BY_CODE.get(code or "")


def normalize(reported: str | None) -> str | None:
    """Whisper's language (code or English name) -> our code, None if we don't know it."""
    if not reported:
        return None
    r = reported.strip().lower()
    if r in BY_CODE:
        return r
    if r in _NAME_TO_CODE:
        return _NAME_TO_CODE[r]
    base = r.split("-")[0].split("_")[0]
    return base if base in BY_CODE else None


def info(code: str | None) -> Lang:
    """A Lang for any code: unknown languages get Latin script and their code as name."""
    lang = get(code)
    if lang:
        return lang
    return Lang(code or "und", (code or "unknown").upper(), code or "", "latin")


# Languages the captions can be translated into (AI translation). Whisper alone can only translate to English.
TRANSLATE_TARGETS = [c for c in ("en", "ur", "ur-Latn", "hi", "hi-Latn", "ar", "bn", "pa", "es", "pt", "fr", "id", "tr",
                                 "fa", "ta", "te", "mr", "de", "it", "ru", "ms", "vi", "th", "ja", "ko", "zh")]
