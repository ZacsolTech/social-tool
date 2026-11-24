"""Keyword highlights, emojis and hook titles without an AI model (the AI path in llm.py does it better
when a key is configured; this one is instant, free and works offline)."""

from __future__ import annotations

import re

from .transcript import Transcript, Word

_STRIP = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)

STOPWORDS = set("""
a an the and or but if then so to of in on at by for with from up down out over under again further once is are was
were be been being am do does did doing have has had having i me my myself we our ours you your yours he him his she
her hers it its they them their what which who whom this that these those here there when where why how all any both
each few more most other some such no nor not only own same than too very can will just don should now its it's i'm
you're we're they're that's there's let's gonna wanna gotta yeah okay ok oh um uh like really also get got going go
one two lot thing things know think say said see make made way well right even back still into about because
hai hain mein main nahi nahin kya ye yeh wo woh aur bhi to toh ke ki ka ko se par pe ek hum tum aap mujhe tha thi
the raha rahi rahe gaya gayi gaye haan ji ab sab kuch is us yahan wahan na ho hota hoti hua hui kar karo karna jo jab
tab kab kahan kaun mera meri mere tera teri apna apni apne hamara phir bas
ہے ہیں میں نہیں کیا یہ وہ اور بھی تو کے کی کا کو سے پر ایک ہم تم آپ مجھے تھا تھی تھے رہا رہی رہے گیا ہاں جی اب سب کچھ
اس ان کر ہو جو جب
है हैं में मैं नहीं क्या यह ये वह वो और भी तो के की का को से पर एक हम तुम आप मुझे था थी थे रहा रही रहे गया हाँ जी अब सब
कुछ इस उस कर हो जो जब
""".split())

POWER = set("""
free secret never always best worst biggest huge amazing crazy insane shocking money rich win winner mistake mistakes
important must stop now today new truth hack hacks easy fast simple warning dangerous love hate million billion
percent proven guaranteed powerful ultimate exclusive viral trick tricks fail success growth profit sale discount
zabardast kamaal paisa paise pyar sach galti zaroori zaruri asaan muft naya behtareen khatarnak
""".split())

EMOJI = {
    # money / business
    "money": "💰", "cash": "💵", "dollar": "💵", "dollars": "💵", "rich": "🤑", "profit": "📈", "sales": "📈",
    "growth": "📈", "grow": "📈", "business": "💼", "work": "💼", "job": "💼", "price": "🏷️", "sale": "🏷️",
    "discount": "🏷️", "free": "🆓", "paisa": "💰", "paise": "💰", "rupees": "💰", "rupay": "💰", "kamai": "💰",
    "پیسہ": "💰", "پیسے": "💰", "पैसा": "💰", "पैसे": "💰",
    # feelings
    "love": "❤️", "heart": "❤️", "pyar": "❤️", "pyaar": "❤️", "mohabbat": "❤️", "پیار": "❤️", "محبت": "❤️",
    "प्यार": "❤️", "happy": "😊", "khush": "😊", "خوش": "😊", "खुश": "😊", "sad": "😢", "cry": "😢", "angry": "😡",
    "funny": "😂", "laugh": "😂", "lol": "😂", "haha": "😂", "scared": "😱", "shocking": "😱", "shocked": "😱",
    "crazy": "🤯", "insane": "🤯", "mind": "🧠", "amazing": "🤩", "wow": "🤩", "zabardast": "🔥", "kamaal": "🔥",
    "fire": "🔥", "hot": "🔥", "best": "🏆", "win": "🏆", "winner": "🏆", "champion": "🏆", "success": "🏆",
    "fail": "❌", "mistake": "❌", "mistakes": "❌", "wrong": "❌", "galti": "❌", "no": "🚫", "stop": "🛑",
    "warning": "⚠️", "danger": "⚠️", "dangerous": "⚠️", "yes": "✅", "right": "✅", "correct": "✅", "done": "✅",
    "secret": "🤫", "idea": "💡", "tip": "💡", "tips": "💡", "hack": "💡", "think": "🤔", "question": "❓",
    "why": "🤔", "kyun": "🤔", "kyon": "🤔", "کیوں": "🤔", "क्यों": "🤔",
    # life
    "time": "⏰", "fast": "⚡", "quick": "⚡", "speed": "⚡", "power": "⚡", "energy": "⚡", "new": "✨", "magic": "✨",
    "food": "🍔", "eat": "🍽️", "khana": "🍛", "کھانا": "🍛", "खाना": "🍛", "biryani": "🍛", "chai": "☕",
    "tea": "☕", "coffee": "☕", "water": "💧", "pani": "💧", "paani": "💧", "home": "🏠", "ghar": "🏠", "گھر": "🏠",
    "घर": "🏠", "family": "👨‍👩‍👧", "friend": "🤝", "friends": "🤝", "dost": "🤝", "doston": "🤝", "دوست": "🤝",
    "दोस्त": "🤝", "car": "🚗", "gaari": "🚗", "travel": "✈️", "world": "🌍", "duniya": "🌍", "دنیا": "🌍",
    "दुनिया": "🌍", "phone": "📱", "mobile": "📱", "video": "🎬", "music": "🎵", "song": "🎵", "book": "📚",
    "study": "📚", "school": "🏫", "learn": "🧠", "brain": "🧠", "health": "💪", "gym": "💪", "strong": "💪",
    "body": "💪", "sleep": "😴", "game": "🎮", "gaming": "🎮", "cricket": "🏏", "football": "⚽", "goal": "🎯",
    "goals": "🎯", "target": "🎯", "focus": "🎯", "rocket": "🚀", "launch": "🚀", "start": "🚀", "grow": "🌱",
    "god": "🙏", "allah": "🤲", "pray": "🙏", "thanks": "🙏", "thank": "🙏", "shukriya": "🙏", "شکریہ": "🙏",
    "subscribe": "🔔", "like": "👍", "share": "📤", "comment": "💬", "comments": "💬", "follow": "👉",
    "sun": "☀️", "rain": "🌧️", "night": "🌙", "party": "🎉", "eid": "🌙", "wedding": "💍", "shaadi": "💍",
    "baby": "👶", "dog": "🐶", "cat": "🐱", "camera": "📸", "photo": "📸", "doctor": "🩺", "medicine": "💊",
}


def _key(text: str) -> str:
    return _STRIP.sub("", text).lower()


def emoji_for(text: str) -> str | None:
    k = _key(text)
    if not k:
        return None
    if k in EMOJI:
        return EMOJI[k]
    if len(k) > 4 and k.endswith("s") and k[:-1] in EMOJI:
        return EMOJI[k[:-1]]
    return None


def _score(w: Word, first: bool) -> float:
    k = _key(w.text)
    if not k or k in STOPWORDS or len(k) < 3 and not k.isdigit():
        return 0.0
    s = 0.5 + min(len(k), 12) / 6
    if re.search(r"\d", k) or re.search(r"[$€£₹%]", w.text):
        s += 3
    if k in POWER:
        s += 2.5
    if emoji_for(w.text):
        s += 1.5
    raw = _STRIP.sub("", w.text)
    if raw.isupper() and len(raw) > 1:
        s += 1
    elif raw[:1].isupper() and not first:
        s += 0.8
    return s


def auto_highlight(t: Transcript, keywords: bool = True, emojis: bool = True) -> Transcript:
    """Mark about one keyword per line (two in long lines) and one emoji per line."""
    for ln in t.lines:
        for w in ln.words:
            if keywords:
                w.keyword = False
            if emojis:
                w.emoji = None
        scored = sorted(((_score(w, i == 0), i) for i, w in enumerate(ln.words)), reverse=True)
        picks = [i for s, i in scored if s >= 1.6][: 2 if len(ln.words) > 8 else 1]
        if keywords:
            for i in picks:
                ln.words[i].keyword = True
        if emojis:
            # The emoji goes on the most important word that has one.
            for _, i in scored:
                e = emoji_for(ln.words[i].text)
                if e:
                    ln.words[i].emoji = e
                    break
    return t


def suggest_hooks(t: Transcript, n: int = 3) -> list[str]:
    """Short title ideas for the top of the video, taken from the transcript itself."""
    out: list[str] = []
    texts = [ln.text(t.language) for ln in t.lines]
    questions = [x for x in texts if x.rstrip().endswith(("?", "؟"))]
    for x in questions[:2] + texts[:4]:
        words = x.split()
        hook = " ".join(words[:9]).rstrip(",.;:،۔")
        if len(words) > 9:
            hook += "…"
        if hook and hook not in out:
            out.append(hook)
        if len(out) >= n:
            break
    return out
