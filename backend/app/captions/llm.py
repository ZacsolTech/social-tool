"""AI text features: translation, Roman Urdu / Hinglish, keyword + emoji picks and hook titles.

Provider: Claude when CF_ANTHROPIC_API_KEY is set (best quality, paid), else Groq's free tier with an
open-weight model (CF_GROQ_API_KEY, the same key as speech-to-text, no cost). Only the transcript *text*
is sent, never the audio or video. Without either key the tool falls back to Whisper translation (English
only), offline romanisation and the heuristics in enhance.py.
"""

from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from typing import Any

import anthropic
import httpx

from ..config import get_settings

log = logging.getLogger("uvicorn.error")
BATCH = 80     # lines per request: keeps each answer well inside the output limit
GROQ_BATCH = 30  # smaller requests for the free tier's tokens-per-minute limit


class LlmError(Exception):
    pass


def api_key() -> str | None:
    s = get_settings()
    key = (s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip("\"'")
    return key or None


def groq_key() -> str | None:
    k = (get_settings().groq_api_key or os.environ.get("GROQ_API_KEY") or "").strip().strip("\"'")
    return k or None


def provider() -> str | None:
    return "claude" if api_key() else "groq" if groq_key() else None


def available() -> bool:
    return provider() is not None


@lru_cache
def _client(key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=key, timeout=150.0, max_retries=2)


def _ask(system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    key = api_key()
    if key is None:
        if groq_key():
            return _ask_groq(system, payload, schema)
        raise LlmError("AI features aren't set up on this server.")
    s = get_settings()
    try:
        resp = _client(key).beta.messages.create(
            model=s.anthropic_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
    except anthropic.RateLimitError as e:
        raise LlmError("The AI is busy right now. Please try again in a minute.") from e
    except anthropic.APIConnectionError as e:
        raise LlmError("Couldn't reach the AI service. Please try again.") from e
    except anthropic.APIStatusError as e:
        log.warning("claude error %s: %s", e.status_code, e.message)
        raise LlmError("The AI service had a problem. Please try again.") from e
    if resp.stop_reason == "refusal":
        raise LlmError("The AI couldn't process this transcript.")
    if resp.stop_reason == "max_tokens":
        raise LlmError("This transcript is too long for one go. Please try again.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LlmError("The AI answer couldn't be read. Please try again.") from e


def _ask_groq(system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Groq free tier (OpenAI-compatible chat API) with an open-weight model, JSON output."""
    s = get_settings()
    body = {
        "model": s.groq_llm_model,
        "messages": [
            {"role": "system", "content": system + "\n\nAnswer with one JSON object only, matching this JSON schema:\n"
                                          + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_completion_tokens": 8000,
    }
    for attempt in range(3):
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {groq_key()}"}, timeout=httpx.Timeout(120, connect=15))
        except httpx.HTTPError as e:
            raise LlmError("Couldn't reach the AI service. Please try again.") from e
        if r.status_code == 429 and attempt < 2:
            # Free tier: a few thousand tokens per minute. Wait as told, then try again.
            try:
                wait = min(30.0, float(r.headers.get("retry-after", "8")))
            except ValueError:
                wait = 8.0
            time.sleep(wait)
            continue
        if r.status_code == 429:
            raise LlmError("The free AI limit is reached for now. Please try again later.")
        if r.status_code >= 400:
            log.warning("groq llm %s: %s", r.status_code, r.text[:300])
            raise LlmError("The AI service had a problem. Please try again.")
        try:
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            raise LlmError("The AI answer couldn't be read. Please try again.") from e
        if not isinstance(data, dict):
            raise LlmError("The AI answer couldn't be read. Please try again.")
        return data
    raise LlmError("The AI is busy right now. Please try again in a minute.")


def _batches(items: list, size: int | None = None):
    size = size or (BATCH if api_key() else GROQ_BATCH)
    for i in range(0, len(items), size):
        yield i, items[i:i + size]


# ---------------------------------------------------------------- translation

_TRANSLATE_SYSTEM = (
    "You translate video captions. You get caption lines in order, as JSON. Translate each line into the "
    "target language so it reads naturally when spoken, keeping the meaning, tone and slang level. Keep names, "
    "brand names and numbers. Return exactly one translation per input line, in the same order, with the same "
    "ids. Captions are short: don't add words, explanations or quotes. If the target is 'Roman Urdu' or "
    "'Hinglish', write it in Latin letters the way people type on social media (e.g. 'kya haal hai')."
)


def translate(lines: list[tuple[str, str]], source: str, target: str) -> dict[str, str]:
    """lines: (id, text). Returns id -> translated text."""
    schema = {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["id", "text"], "additionalProperties": False}}},
        "required": ["lines"], "additionalProperties": False,
    }
    out: dict[str, str] = {}
    for _, chunk in _batches(lines):
        data = _ask(_TRANSLATE_SYSTEM, {"source_language": source, "target_language": target,
                                        "lines": [{"id": i, "text": t} for i, t in chunk]}, schema)
        for row in data.get("lines", []):
            if isinstance(row, dict) and row.get("id") and isinstance(row.get("text"), str):
                out[str(row["id"])] = row["text"].strip()
    missing = [i for i, _ in lines if i not in out]
    if len(missing) > len(lines) * 0.2:
        raise LlmError("The translation came back incomplete. Please try again.")
    return out


# ---------------------------------------------------------------- proofreading (misheard words)

_PROOF_SYSTEM = (
    "You proofread automatic speech-recognition captions. Each line is the list of words the recogniser heard, "
    "in order. Using the context of the whole video, fix ONLY words that were clearly misheard: a wrong word that "
    "sounds similar, a broken or misspelled word, a name or term from the hints written wrongly, a word in the "
    "wrong script. Keep the speaker's own words, slang, grammar and meaning: never paraphrase, translate, "
    "summarise, add or remove words. Return every line with the same id and EXACTLY the same number of words "
    "(one output word for each input word, punctuation attached). When unsure, keep the word as it is."
)


def proofread(lines: list[tuple[str, list[str]]], language: str, hints: str | None) -> dict[str, list[str]]:
    schema = {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "words": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "words"], "additionalProperties": False}}},
        "required": ["lines"], "additionalProperties": False,
    }
    out: dict[str, list[str]] = {}
    for _, chunk in _batches(lines):
        payload = {"language": language, "hints": hints or "", "lines": [{"id": i, "words": w} for i, w in chunk]}
        data = _ask(_PROOF_SYSTEM, payload, schema)
        for row in data.get("lines", []):
            if isinstance(row, dict) and row.get("id") and isinstance(row.get("words"), list):
                out[str(row["id"])] = [str(x) for x in row["words"]]
    return out


# ---------------------------------------------------------------- romanisation

_ROMAN_SYSTEM = (
    "You convert caption words from Urdu or Hindi script into Roman Urdu / Hinglish: Latin letters, spelled the "
    "way people type on social media in Pakistan and India (e.g. 'kya haal hai', 'bohat', 'zindagi', 'InshaAllah'). "
    "Each input line is a list of words. Return the same lines with the same ids and EXACTLY the same number of "
    "words, word for word (one output word per input word, keeping punctuation attached). Words already in Latin "
    "letters (English words) stay as they are."
)


def romanize(lines: list[tuple[str, list[str]]], style: str) -> dict[str, list[str]]:
    schema = {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "words": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "words"], "additionalProperties": False}}},
        "required": ["lines"], "additionalProperties": False,
    }
    out: dict[str, list[str]] = {}
    for _, chunk in _batches(lines):
        data = _ask(_ROMAN_SYSTEM, {"style": "Roman Urdu" if style == "urdu" else "Hinglish",
                                    "lines": [{"id": i, "words": w} for i, w in chunk]}, schema)
        for row in data.get("lines", []):
            if isinstance(row, dict) and row.get("id") and isinstance(row.get("words"), list):
                out[str(row["id"])] = [str(x) for x in row["words"]]
    return out


# ---------------------------------------------------------------- highlights, emojis, hooks

_ENHANCE_SYSTEM = (
    "You make short-form video captions more engaging (TikTok, Reels, Shorts). For each caption line (a list of "
    "words), pick the index of the ONE most important word to highlight (a number, a strong or emotional word, "
    "a key noun; -1 if none stands out), and optionally ONE fitting emoji for the line (empty string if nothing "
    "fits naturally; don't force it, use emojis on about half the lines). Also write 3 short hook titles "
    "(max 8 words each) in the same language and script as the transcript, that would make viewers stop "
    "scrolling, based only on what is actually said."
)


def enhance(lines: list[tuple[str, list[str]]], language: str) -> tuple[dict[str, tuple[int, str]], list[str]]:
    schema = {
        "type": "object",
        "properties": {
            "lines": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "keyword": {"type": "integer"}, "emoji": {"type": "string"}},
                "required": ["id", "keyword", "emoji"], "additionalProperties": False}},
            "hooks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["lines", "hooks"], "additionalProperties": False,
    }
    picks: dict[str, tuple[int, str]] = {}
    hooks: list[str] = []
    for start, chunk in _batches(lines):
        data = _ask(_ENHANCE_SYSTEM, {"language": language, "lines": [{"id": i, "words": w} for i, w in chunk]}, schema)
        for row in data.get("lines", []):
            if isinstance(row, dict) and row.get("id"):
                picks[str(row["id"])] = (int(row.get("keyword", -1)), str(row.get("emoji") or "")[:8])
        if start == 0:
            hooks = [h.strip() for h in data.get("hooks", []) if isinstance(h, str) and h.strip()][:3]
    return picks, hooks
