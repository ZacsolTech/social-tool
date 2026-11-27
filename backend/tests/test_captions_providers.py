"""Speech-to-text provider chain (Groq -> Cloudflare -> local) and the free Groq text model, with the HTTP
calls mocked: what is sent, how answers are read, and how quota errors move to the next provider."""

from __future__ import annotations

import base64
import json
import httpx
import pytest

from app.captions import llm, stt
from app.config import get_settings


class Resp:
    def __init__(self, status: int, body: dict | None = None, headers: dict | None = None, text: str | None = None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(self._body)

    def json(self):
        return self._body


WHISPER = {
    "language": "urdu",
    "segments": [{"start": 0.0, "end": 2.0, "text": "آج ہم بات کریں گے", "no_speech_prob": 0.01, "avg_logprob": -0.2,
                  "compression_ratio": 1.2,
                  "words": [{"word": " آج", "start": 0.1, "end": 0.4}, {"word": " ہم", "start": 0.5, "end": 0.8}]},
                 {"start": 5.0, "end": 9.0, "text": "Thanks for watching", "no_speech_prob": 0.9, "avg_logprob": -1.5,
                  "compression_ratio": 1.1, "words": [{"word": "Thanks", "start": 5.0, "end": 6.0}]}],
}


@pytest.fixture
def keys(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "groq_api_key", "gk")
    monkeypatch.setattr(s, "cloudflare_account_id", "acct")
    monkeypatch.setattr(s, "cloudflare_api_token", "cft")
    monkeypatch.setattr(s, "anthropic_api_key", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stt._cooldown.clear()
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3" + b"\0" * 5000)
    yield audio
    stt._cooldown.clear()


def test_prompt_is_only_the_visitors_words():
    # No sample sentence: large-v3 copied it into the captions and skipped the speech on a real clip.
    assert stt.build_prompt("ur", None) is None
    assert stt.build_prompt("en", " Klyprima, Karachi ") == "Klyprima, Karachi"


def test_prompt_echo_is_detected():
    echo = [(0.0, 1.9, "admission chahiye"), (11.0, 41.0, "aaj hum iske bare mein baat karenge."),
            (41.0, 60.0, "aaj hum iske bare mein baat karenge.")]
    good = [(0.0, 1.9, "admission chahiye"), (13.2, 15.9, "to phir ek pre-medical entrance exam deni hogi")]
    assert stt._suspicious(echo) and not stt._suspicious(good)


def test_prompt_echo_is_transcribed_again_without_the_prompt(keys, monkeypatch):
    prompts = []

    def post(url, **kw):
        prompts.append(kw["data"].get("prompt"))
        if kw["data"].get("prompt"):
            seg = {"start": 0.0, "end": 40.0, "text": "Klyprima", "no_speech_prob": 0, "avg_logprob": -0.1,
                   "compression_ratio": 1.0}
            return Resp(200, {"segments": [seg], "words": [{"word": "Klyprima", "start": 0, "end": 40}]})
        return Resp(200, {**WHISPER, "words": [w for s in WHISPER["segments"] for w in s["words"]]})
    monkeypatch.setattr(stt.httpx, "post", post)
    res = stt.transcribe(keys, "ur", prompt="Klyprima")
    assert prompts == ["Klyprima", None] and [w.text for w in res.words] == ["آج", "ہم"]


def test_provider_order(keys, monkeypatch):
    assert stt.providers() == ["groq", "cloudflare", "local"]
    monkeypatch.setattr(get_settings(), "cloudflare_api_token", None)
    assert stt.providers() == ["groq", "local"]


def test_groq_quota_moves_to_cloudflare_and_cools_down(keys, monkeypatch):
    calls = []

    def post(url, **kw):
        calls.append(url)
        if "groq" in url:
            return Resp(429, {"error": "rate limit"}, {"retry-after": "120"})
        body = kw["json"]
        assert base64.b64decode(body["audio"]).startswith(b"ID3")
        assert body["language"] == "ur" and body["vad_filter"] is True and body["task"] == "transcribe"
        assert "initial_prompt" not in body           # no visitor words -> no prompt at all
        assert kw["headers"]["Authorization"] == "Bearer cft"
        return Resp(200, {"success": True, "result": {"transcription_info": {"language": "ur"},
                                                      "segments": WHISPER["segments"]}})
    monkeypatch.setattr(stt.httpx, "post", post)
    res = stt.transcribe(keys, "ur")
    assert res.provider == "cloudflare" and res.language == "ur"
    assert [w.text for w in res.words] == ["آج", "ہم"]          # the "Thanks for watching" hallucination is dropped
    assert "accounts/acct/ai/run/@cf/openai/whisper-large-v3-turbo" in calls[1]
    # Groq is skipped while it cools down.
    calls.clear()
    stt.transcribe(keys, "ur")
    assert all("groq" not in c for c in calls)
    assert stt.provider_name() == "cloudflare"


def test_cloudflare_daily_allocation_error_is_a_quota(keys, monkeypatch):
    def post(url, **kw):
        if "groq" in url:
            raise httpx.ConnectError("down")
        return Resp(400, text='{"errors":[{"message":"you have used up your daily free allocation of 10,000 neurons"}]}')
    monkeypatch.setattr(stt.httpx, "post", post)
    monkeypatch.setattr(stt, "_local_run", lambda *a, **k: ("ur", [stt.Word("local", 0, 1)], []))
    res = stt.transcribe(keys, None)
    assert res.provider == "local" and res.words[0].text == "local"
    assert stt._cooldown["cloudflare"] - __import__("time").time() > 60     # until next UTC midnight
    assert stt._cooldown["groq"] > 0                                          # outage: short pause


def test_groq_sends_word_timestamps_and_prompt(keys, monkeypatch):
    seen = {}

    def post(url, **kw):
        seen.update(kw["data"])
        return Resp(200, {**WHISPER, "words": [w for s in WHISPER["segments"] for w in s["words"]]})
    monkeypatch.setattr(stt.httpx, "post", post)
    res = stt.transcribe(keys, "ur", prompt="Klyprima")
    assert res.provider == "groq" and seen["model"] == "whisper-large-v3"      # Urdu: the full model
    assert seen["timestamp_granularities[]"] == ["word", "segment"] and seen["prompt"].endswith("Klyprima")
    assert [w.text for w in res.words] == ["آج", "ہم"]


def test_everything_down_gives_a_clear_error(keys, monkeypatch):
    monkeypatch.setattr(get_settings(), "local_whisper_fallback", False)
    monkeypatch.setattr(stt.httpx, "post", lambda url, **kw: Resp(500, text="boom"))
    with pytest.raises(stt.SttError):
        stt.transcribe(keys, "en")


# ---------------------------------------------------------------- free text model (Groq)


def test_groq_llm_is_used_without_anthropic_key(keys, monkeypatch):
    assert llm.provider() == "groq" and llm.available()
    sent = []

    def post(url, **kw):
        sent.append(kw["json"])
        if len(sent) == 1:
            return Resp(429, {}, {"retry-after": "0"})        # free-tier minute limit: wait and retry
        lines = json.loads(kw["json"]["messages"][1]["content"])["lines"]
        out = {"lines": [{"id": x["id"], "text": f"EN {x['text']}"} for x in lines]}
        return Resp(200, {"choices": [{"message": {"content": json.dumps(out)}}]})
    monkeypatch.setattr(llm.httpx, "post", post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    res = llm.translate([("a", "آج"), ("b", "ہم")], "Urdu", "English")
    assert res == {"a": "EN آج", "b": "EN ہم"}
    body = sent[-1]
    assert body["model"] == "openai/gpt-oss-120b" and body["response_format"] == {"type": "json_object"}
    assert "JSON schema" in body["messages"][0]["content"]


def test_groq_llm_bad_answer_is_an_llm_error(keys, monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: Resp(200, {"choices": [{"message": {"content": "not json"}}]}))
    with pytest.raises(llm.LlmError):
        llm.translate([("a", "x")], "English", "Urdu")


def test_claude_is_preferred_when_configured(keys, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "ak")
    assert llm.provider() == "claude"


def test_config_reports_providers(keys):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        f = c.get("/api/captions/config").json()["features"]
    assert f["stt_providers"] == ["groq", "cloudflare", "local"] and f["ai_provider"] == "groq" and f["ai"] is True


def test_urdu_uses_the_full_model_and_auto_detect_listens_again(keys, monkeypatch):
    models = []

    def post(url, **kw):
        models.append((kw["data"]["model"], kw["data"].get("language")))
        return Resp(200, {**WHISPER, "words": [w for s in WHISPER["segments"] for w in s["words"]]})
    monkeypatch.setattr(stt.httpx, "post", post)
    stt.transcribe(keys, "ur")
    assert models[-1] == ("whisper-large-v3", "ur")
    models.clear()
    stt.transcribe(keys, "en")
    assert models == [("whisper-large-v3-turbo", "en")]
    models.clear()
    res = stt.transcribe(keys, None)            # auto: turbo detects Urdu -> second pass with the full model
    assert models == [("whisper-large-v3-turbo", None), ("whisper-large-v3", "ur")] and res.language == "ur"


def test_ai_judge_reads_answers_and_skips_a_failed_batch(keys, monkeypatch):
    calls = []

    def post(url, **kw):
        lines = json.loads(kw["json"]["messages"][1]["content"])["lines"]
        calls.append(lines)
        if len(calls) == 2:
            return Resp(500, {}, text="boom")               # one batch fails: the others still count
        out = [{"id": x["id"], "text": x.get("alt") or x["heard"], "sure": x["id"] != "a"} for x in lines]
        return Resp(200, {"choices": [{"message": {"content": json.dumps({"lines": out})}}]})
    monkeypatch.setattr(llm.httpx, "post", post)
    items = [{"id": f"x{i}", "heard": "w", "unsure": False, "before": "", "after": ""} for i in range(40)]
    items[0] = {"id": "a", "heard": "یہ كتاب", "alt": "یہ کتاب", "unsure": True, "before": "", "after": ""}
    res = llm.verify(items, "Urdu", "Klyprima", "Title")
    assert len(calls) == 2 and len(calls[0]) == 20             # Groq free tier: small batches
    assert res["a"] == ("یہ کتاب", False) and res["x1"] == ("w", True) and "x25" not in res
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: Resp(500, {}, text="down"))
    with pytest.raises(llm.LlmError):
        llm.verify(items[:3], "Urdu", None, None)


def test_word_confidence_comes_from_the_segment(keys, monkeypatch):
    body = {**WHISPER, "words": [w for s in WHISPER["segments"] for w in s["words"]]}
    monkeypatch.setattr(stt.httpx, "post", lambda url, **kw: Resp(200, body))
    res = stt.transcribe(keys, "ur")
    assert res.model == "whisper-large-v3"
    assert all(abs(w.prob - __import__("math").exp(-0.2)) < 1e-9 for w in res.words)


def test_second_listen_uses_the_other_model_then_cloudflare(keys, monkeypatch):
    models = []
    body = {**WHISPER, "words": [w for s in WHISPER["segments"] for w in s["words"]]}

    def post(url, **kw):
        if "groq" in url:
            models.append(kw["data"]["model"])
            if kw["data"]["model"] == "whisper-large-v3-turbo" and len(models) > 1:
                return Resp(429, {}, {"retry-after": "60"})
            return Resp(200, body)
        models.append("cloudflare")
        return Resp(200, {"result": {"segments": WHISPER["segments"], "transcription_info": {"language": "ur"}}})
    monkeypatch.setattr(stt.httpx, "post", post)
    first = stt.SttResult("en", [], "groq", [], "whisper-large-v3-turbo")
    res = stt.second_listen(keys, "en", None, first)
    assert models == ["whisper-large-v3"] and res.model == "whisper-large-v3"
    models.clear()
    first = stt.SttResult("ur", [], "groq", [], "whisper-large-v3")
    models.append("x")
    res = stt.second_listen(keys, "ur", None, first)          # turbo is over its quota -> Cloudflare
    assert models == ["x", "whisper-large-v3-turbo", "cloudflare"] and res.provider == "cloudflare"
    assert "groq" not in stt._cooldown                          # the main chain isn't slowed down by it
    assert stt.second_listen(keys, "en", None, stt.SttResult("en", [], "fake")) is None
