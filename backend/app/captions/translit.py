"""Roman Urdu / Hinglish without an AI model.

Hindi and Urdu are the same spoken language (Hindustani). Devanagari writes every vowel, so speech
transcribed as Hindi can be romanised word by word, keeping each word's timing. That is how Roman Urdu
works when no AI key is configured. Urdu script leaves most short vowels out, so `urdu_to_roman` is only
an approximation (a dictionary of common words plus letter mapping); the AI path is used when available.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- Devanagari -> Roman

_VIRAMA = "्"
_NUKTA = "़"

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "w", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
}
_NUKTA_CONS = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "ड": "r", "ढ": "rh", "फ": "f", "य": "y"}
_PRECOMPOSED = {"क़": "क", "ख़": "ख", "ग़": "ग", "ज़": "ज", "ड़": "ड", "ढ़": "ढ",
                "फ़": "फ", "य़": "य"}
_MATRA = {"ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
          "ॅ": "e", "ॉ": "o"}
_VOWEL = {"अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o",
          "औ": "au", "ऍ": "e", "ऑ": "o"}
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}

# Everyday words, spelled the way people write Roman Urdu / Hinglish on social media.
_COMMON = {
    "है": "hai", "हैं": "hain", "में": "mein", "मैं": "main", "नहीं": "nahi", "नही": "nahi", "क्या": "kya",
    "यह": "ye", "ये": "ye", "वह": "wo", "वो": "wo", "और": "aur", "भी": "bhi", "तो": "to", "के": "ke", "की": "ki",
    "का": "ka", "को": "ko", "से": "se", "पर": "par", "एक": "ek", "हम": "hum", "तुम": "tum", "आप": "aap",
    "मुझे": "mujhe", "तुम्हें": "tumhein", "क्यों": "kyun", "कैसे": "kaise", "था": "tha", "थी": "thi", "थे": "the",
    "रहा": "raha", "रही": "rahi", "रहे": "rahe", "गया": "gaya", "गई": "gayi", "गए": "gaye", "हाँ": "haan",
    "हां": "haan", "जी": "ji", "अब": "ab", "सब": "sab", "कुछ": "kuch", "बहुत": "bohat", "ठीक": "theek",
    "अच्छा": "acha", "अच्छी": "achi", "अच्छे": "ache", "लेकिन": "lekin", "इस": "is", "उस": "us", "यहाँ": "yahan",
    "यहां": "yahan", "वहाँ": "wahan", "वहां": "wahan", "बात": "baat", "लोग": "log", "दिन": "din", "साल": "saal",
    "पैसा": "paisa", "पैसे": "paise", "प्यार": "pyar", "दोस्त": "dost", "दोस्तों": "doston", "ज़िंदगी": "zindagi",
    "जिंदगी": "zindagi", "अल्लाह": "Allah", "शुक्रिया": "shukriya", "धन्यवाद": "dhanyavaad", "कर": "kar",
    "करना": "karna", "करो": "karo", "करें": "karein", "करते": "karte", "करता": "karta", "करती": "karti",
    "हो": "ho", "होगा": "hoga", "होगी": "hogi", "होता": "hota", "होती": "hoti", "हुआ": "hua", "हुई": "hui",
    "जो": "jo", "जब": "jab", "तब": "tab", "कब": "kab", "कहाँ": "kahan", "कहां": "kahan", "कौन": "kaun",
    "मेरा": "mera", "मेरी": "meri", "मेरे": "mere", "तेरा": "tera", "तेरी": "teri", "हमारा": "hamara",
    "आज": "aaj", "कल": "kal", "फिर": "phir", "बस": "bas", "सिर्फ": "sirf", "सिर्फ़": "sirf", "ज़्यादा": "zyada",
    "ज्यादा": "zyada", "कम": "kam", "बड़ा": "bara", "छोटा": "chota", "सच": "sach", "भाई": "bhai", "यार": "yaar",
    "चलो": "chalo", "देखो": "dekho", "सुनो": "suno", "बोलो": "bolo", "आओ": "aao", "जाओ": "jao", "ना": "na",
    "न": "na", "हमें": "humein", "उन्हें": "unhein", "इसे": "ise", "उसे": "use", "वाला": "wala", "वाली": "wali",
    "वाले": "wale", "दुनिया": "duniya", "पाकिस्तान": "Pakistan", "भारत": "Bharat", "इंडिया": "India",
    # English words people say in Urdu/Hindi videos
    "सब्सक्राइब": "subscribe", "चैनल": "channel", "वीडियो": "video", "लाइक": "like", "शेयर": "share",
    "कमेंट": "comment", "कमेंट्स": "comments", "फॉलो": "follow", "लिंक": "link", "बटन": "button",
    "प्रोडक्ट": "product", "ऑफर": "offer", "फ्री": "free", "ऑनलाइन": "online", "मोबाइल": "mobile",
    "फ़ोन": "phone", "फोन": "phone", "बिज़नेस": "business", "बिजनेस": "business", "मार्केटिंग": "marketing",
}


def _schwa_flags(units: list[dict]) -> None:
    """Hindi drops the inherent 'a' at the end of a word and in V-C-a-C-V (samajhnaa, not samajhanaa)."""
    n = len(units)
    for i in range(n - 1, -1, -1):
        u = units[i]
        if u["kind"] != "cons" or u["vowel"] != "a":
            continue
        if i == n - 1:
            if n > 1:
                u["vowel"] = ""
            continue
        nxt = units[i + 1]
        prev = units[i - 1] if i > 0 else None
        next_has_vowel = nxt["kind"] == "vowel" or (nxt["kind"] == "cons" and nxt["vowel"] != "")
        prev_has_vowel = prev is not None and (prev["kind"] == "vowel" or prev["vowel"] != "")
        if prev_has_vowel and nxt["kind"] == "cons" and next_has_vowel and i + 1 < n - 0:
            u["vowel"] = ""


def _deva_word(word: str, style: str) -> str:
    units: list[dict] = []
    i = 0
    chars = [_PRECOMPOSED.get(c, c) + (_NUKTA if c in _PRECOMPOSED else "") for c in word]
    s = "".join(chars)
    while i < len(s):
        c = s[i]
        if c in _CONS:
            base = _CONS[c]
            if i + 1 < len(s) and s[i + 1] == _NUKTA:
                base = _NUKTA_CONS.get(c, base)
                i += 1
            if style == "hindi" and c == "व":
                base = "v"
            unit = {"kind": "cons", "text": base, "vowel": "a"}
            if i + 1 < len(s) and s[i + 1] == _VIRAMA:
                unit["vowel"] = ""
                i += 1
            elif i + 1 < len(s) and s[i + 1] in _MATRA:
                unit["vowel"] = _MATRA[s[i + 1]]
                i += 1
            units.append(unit)
        elif c in _VOWEL:
            units.append({"kind": "vowel", "text": _VOWEL[c], "vowel": ""})
        elif c in ("ं", "ँ"):
            units.append({"kind": "nasal", "text": "n", "vowel": ""})
        elif c == "ः":
            units.append({"kind": "other", "text": "h", "vowel": ""})
        elif c in ("।", "॥"):
            units.append({"kind": "other", "text": ".", "vowel": ""})
        elif c in _DIGITS:
            units.append({"kind": "other", "text": _DIGITS[c], "vowel": ""})
        elif c == _NUKTA:
            pass
        else:
            units.append({"kind": "other", "text": c, "vowel": ""})
        i += 1
    core = [u for u in units if u["kind"] in ("cons", "vowel")]
    _schwa_flags(core)
    out = []
    for k, u in enumerate(units):
        v = u["vowel"]
        if v == "aa" and k == len(units) - 1:
            v = "a"                    # word-final long a: "kya", "raha"
        if u["kind"] == "nasal" and out and out[-1].endswith(("i", "e")) and k == len(units) - 1:
            out.append("n")
            continue
        out.append(u["text"] + v)
    text = "".join(out)
    text = re.sub(r"aa(?=n?$)", "a", text) if len(text) > 4 else text
    return text


def deva_to_roman(text: str, style: str = "urdu") -> str:
    """Devanagari -> casual Roman ("kya haal hai"). style: urdu (w, bohat) | hindi (v)."""
    words = []
    for token in text.split(" "):
        m = re.match(r"^([^ऀ-ॿ]*)([ऀ-ॿ]+)([^ऀ-ॿ]*)$", token)
        if not m:
            words.append(token)
            continue
        pre, core, post = m.groups()
        key = core.replace("।", "")
        roman = _COMMON.get(key)
        if roman is None:
            roman = _deva_word(core, style)
        elif "।" in core:
            roman += "."
        if style == "hindi":
            roman = {"bohat": "bahut", "wo": "vo", "wala": "vala", "wali": "vali", "wale": "vale"}.get(roman, roman)
        words.append(pre + roman + post.replace("।", "."))
    return " ".join(words)


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= c <= "ॿ" for c in text)


# ---------------------------------------------------------------- Urdu script -> Roman (approximate)

_URDU_COMMON = {
    "ہے": "hai", "ہیں": "hain", "میں": "mein", "نہیں": "nahi", "کیا": "kya", "یہ": "ye", "وہ": "wo", "اور": "aur",
    "بھی": "bhi", "تو": "to", "کے": "ke", "کی": "ki", "کا": "ka", "کو": "ko", "سے": "se", "پر": "par", "ایک": "ek",
    "ہم": "hum", "تم": "tum", "آپ": "aap", "مجھے": "mujhe", "کیوں": "kyun", "کیسے": "kaise", "تھا": "tha",
    "تھی": "thi", "تھے": "the", "رہا": "raha", "رہی": "rahi", "رہے": "rahe", "گیا": "gaya", "ہاں": "haan",
    "جی": "ji", "اب": "ab", "سب": "sab", "کچھ": "kuch", "بہت": "bohat", "ٹھیک": "theek", "اچھا": "acha",
    "لیکن": "lekin", "اس": "is", "اُس": "us", "یہاں": "yahan", "وہاں": "wahan", "بات": "baat", "لوگ": "log",
    "دن": "din", "سال": "saal", "پیسہ": "paisa", "پیسے": "paise", "پیار": "pyar", "دوست": "dost",
    "زندگی": "zindagi", "اللہ": "Allah", "شکریہ": "shukriya", "کر": "kar", "کرنا": "karna", "کرو": "karo",
    "کریں": "karein", "ہو": "ho", "ہوگا": "hoga", "ہوا": "hua", "جو": "jo", "جب": "jab", "کب": "kab",
    "کہاں": "kahan", "کون": "kaun", "میرا": "mera", "میری": "meri", "میرے": "mere", "آج": "aaj", "کل": "kal",
    "پھر": "phir", "بس": "bas", "صرف": "sirf", "زیادہ": "zyada", "کم": "kam", "بڑا": "bara", "سچ": "sach",
    "بھائی": "bhai", "یار": "yaar", "چلو": "chalo", "دیکھو": "dekho", "سنو": "suno", "نا": "na", "ہمیں": "humein",
    "والا": "wala", "والی": "wali", "والے": "wale", "دنیا": "duniya", "پاکستان": "Pakistan", "السلام": "Assalam",
    "علیکم": "alaikum", "ماشاءاللہ": "MashaAllah", "انشاءاللہ": "InshaAllah", "حال": "haal", "کیسا": "kaisa",
    "کیسی": "kaisi", "آپکا": "aapka", "آپ کا": "aap ka", "ویڈیو": "video", "چینل": "channel",
}
_URDU_MAP = {
    "ا": "a", "آ": "aa", "ب": "b", "پ": "p", "ت": "t", "ٹ": "t", "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh",
    "د": "d", "ڈ": "d", "ذ": "z", "ر": "r", "ڑ": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q", "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m",
    "ن": "n", "ں": "n", "و": "o", "ہ": "h", "ه": "h", "ھ": "h", "ء": "", "ی": "i", "ي": "i", "ے": "e", "ئ": "i",
    "ۓ": "e", "ۃ": "a", "ة": "a", "ؤ": "o", "۔": ".", "؟": "?", "،": ",",
    "َ": "a", "ِ": "i", "ُ": "u", "ّ": "", "ْ": "", "ٰ": "a",
}
_URDU_DIGITS = {chr(0x06F0 + i): str(i) for i in range(10)} | {chr(0x0660 + i): str(i) for i in range(10)}
_CONSONANTS = set("bcdfghjklmnpqrstvwxz")


def _urdu_word(word: str) -> str:
    if word in _URDU_COMMON:
        return _URDU_COMMON[word]
    out = []
    for i, c in enumerate(word):
        r = _URDU_DIGITS.get(c) or _URDU_MAP.get(c)
        if r is None:
            r = c
        if c == "و":
            r = "w" if i == 0 else ("o" if i == len(word) - 1 else "o")
        elif c in ("ی", "ي"):
            r = "y" if i == 0 else ("i" if i == len(word) - 1 else "e")
        elif c == "ہ" and i == len(word) - 1 and i > 0:
            r = "a"
        elif c == "ا" and i > 0:
            r = "a"
        out.append(r)
    s = "".join(out)
    # Urdu leaves short vowels unwritten: put an "a" between two consonants at the start ("ktab" -> "katab").
    s = re.sub(r"^([bcdfgjklmnpqrstvwxz])(?=[bcdfgjklmnpqrstvwxz])(?!h)", r"\1a", s)
    s = re.sub(r"([bcdfgjklmnpqrstvwxz])([bcdfgjklmnpqrstvwxz])([bcdfgjklmnpqrstvwxz])", r"\1\2a\3", s)
    return s


def urdu_to_roman(text: str) -> str:
    words = []
    for token in text.split(" "):
        m = re.match(r"^([^؀-ۿ]*)([؀-ۿ]+)([^؀-ۿ]*)$", token)
        if not m:
            words.append(token)
            continue
        pre, core, post = m.groups()
        tail = ""
        while core and core[-1] in "۔؟،":
            tail = {"۔": ".", "؟": "?", "،": ","}[core[-1]] + tail
            core = core[:-1]
        words.append(pre + (_urdu_word(core) if core else "") + tail + post)
    return " ".join(words)


def has_arabic_script(text: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in text)


def to_roman(text: str, style: str = "urdu") -> str:
    """Best offline romanisation for a piece of Hindustani text in any script."""
    text = unicodedata.normalize("NFC", text)
    if has_devanagari(text):
        text = deva_to_roman(text, style)
    if has_arabic_script(text):
        text = urdu_to_roman(text)
    return text
