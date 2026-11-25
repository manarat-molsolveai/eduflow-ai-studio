"""AI provider layer. Calls happen server-side only. Nothing is claimed to work until tested."""
import os, json, base64, hashlib, time
import requests
from . import db
from .db import UserSetting, AIJob
from sqlalchemy import select

PROVIDERS = {
    "github": {"label": "GitHub Models (مفتاح المنصة المشترك)", "models": ["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4.1-mini"]},
    "openai": {"label": "OpenAI", "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]},
    "gemini": {"label": "Google Gemini", "models": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]},
    "anthropic": {"label": "Anthropic", "models": ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"]},
}


def _secret():
    v = os.environ.get("APP_SECRET", "")
    try:
        import streamlit as st
        v = v or st.secrets.get("APP_SECRET", "")
    except Exception:
        pass
    return v


def platform_key():
    v = os.environ.get("GITHUB_MODELS_TOKEN", "")
    try:
        import streamlit as st
        v = v or st.secrets.get("GITHUB_MODELS_TOKEN", "")
    except Exception:
        pass
    return str(v or "").strip()


def can_store_keys():
    return bool(_secret())


def _fernet():
    from cryptography.fernet import Fernet
    k = base64.urlsafe_b64encode(hashlib.sha256(_secret().encode()).digest())
    return Fernet(k)


def get_setting(uid, key, default=""):
    with db.session() as s:
        r = s.execute(select(UserSetting).where(UserSetting.user_id == uid, UserSetting.key == key)).scalar_one_or_none()
        return r.value if r else default


def set_setting(uid, key, value):
    with db.session() as s:
        r = s.execute(select(UserSetting).where(UserSetting.user_id == uid, UserSetting.key == key)).scalar_one_or_none()
        if r:
            r.value = value
        else:
            s.add(UserSetting(user_id=uid, key=key, value=value))


def save_key(uid, provider, key):
    if not can_store_keys():
        return False
    set_setting(uid, f"key_{provider}", _fernet().encrypt(key.encode()).decode())
    return True


def get_key(uid, provider):
    raw = get_setting(uid, f"key_{provider}")
    if not raw and provider == "github":
        return platform_key()
    if not raw or not can_store_keys():
        return ""
    try:
        return _fernet().decrypt(raw.encode()).decode()
    except Exception:
        return ""


def has_key(uid, provider):
    return bool(get_setting(uid, f"key_{provider}")) or (provider == "github" and bool(platform_key()))


def active(uid):
    """Return (provider, model, key) if a tested, configured provider exists, else None."""
    p = get_setting(uid, "provider")
    if not p and platform_key() and get_setting(uid, "tested_github") != "fail":
        m = PROVIDERS["github"]["models"][0]
        ok, _ = test_connection(uid, "github", m, platform_key())
        if ok:
            set_setting(uid, "provider", "github"); set_setting(uid, "model", m)
    p = get_setting(uid, "provider")
    if not p or p not in PROVIDERS:
        return None
    if get_setting(uid, f"tested_{p}") != "ok":
        return None
    k = get_key(uid, p)
    if not k:
        return None
    return p, get_setting(uid, "model", PROVIDERS[p]["models"][0]), k


def _call(provider, model, key, system, prompt, max_tokens=4000, timeout=90):
    if provider in ("openai", "github"):
        url = "https://models.github.ai/inference/chat/completions" if provider == "github" else "https://api.openai.com/v1/chat/completions"
        r = requests.post(url, timeout=timeout,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "max_tokens": max_tokens, "messages": [
                              {"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"], j.get("usage", {}).get("prompt_tokens", 0), j.get("usage", {}).get("completion_tokens", 0)
    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=timeout,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": max_tokens, "system": system,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        j = r.json()
        return "".join(b.get("text", "") for b in j["content"]), j.get("usage", {}).get("input_tokens", 0), j.get("usage", {}).get("output_tokens", 0)
    if provider == "gemini":
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          timeout=timeout, headers={"x-goog-api-key": key},
                          json={"systemInstruction": {"parts": [{"text": system}]},
                                "contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": max_tokens}})
        r.raise_for_status()
        j = r.json()
        u = j.get("usageMetadata", {})
        return j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)
    raise ValueError("unknown provider")


def test_connection(uid, provider, model, key):
    """Real round trip. Returns (ok, message). Records result only when it really succeeded."""
    try:
        out, _, _ = _call(provider, model, key, "Reply with the single word OK.", "ping", max_tokens=16, timeout=30)
        ok = bool(out and out.strip())
        set_setting(uid, f"tested_{provider}", "ok" if ok else "fail")
        return ok, ("اتصال ناجح" if ok else "رد فارغ")
    except requests.HTTPError as e:
        set_setting(uid, f"tested_{provider}", "fail")
        code = e.response.status_code if e.response is not None else "?"
        return False, f"فشل الاتصال (HTTP {code}). تحقق من المفتاح والنموذج"
    except Exception as e:
        set_setting(uid, f"tested_{provider}", "fail")
        return False, f"فشل الاتصال: {type(e).__name__}"


def extract_json(txt):
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[1] if "\n" in txt else txt
        txt = txt.rsplit("```", 1)[0]
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("no json")
    return json.loads(txt[a:b + 1])


def generate_json(uid, project_id, module, system, prompt, validator, retries=2):
    """Run provider with retry + validation; log job. Raises RuntimeError on final failure."""
    act = active(uid)
    if not act:
        raise RuntimeError("no_provider")
    provider, model, key = act
    with db.session() as s:
        job = AIJob(user_id=uid, project_id=project_id, module=module, provider=provider, model=model)
        s.add(job)
        s.flush()
        jid = job.id
    err = ""
    tin = tout = 0
    for attempt in range(1, retries + 2):
        try:
            p = prompt if not err else prompt + f"\n\nالمحاولة السابقة فشلت بسبب: {err}\nأعد إخراج JSON صالحًا فقط."
            out, a, b = _call(provider, model, key, system, p)
            tin += a
            tout += b
            data = extract_json(out)
            validator(data)
            _finish(jid, "done", attempt, "", tin, tout)
            return data, provider, model
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(1)
    _finish(jid, "failed", retries + 1, err, tin, tout)
    raise RuntimeError(err)


def _finish(jid, status, attempts, err, tin, tout):
    import datetime as dt
    with db.session() as s:
        j = s.get(AIJob, jid)
        j.status, j.attempts, j.error, j.tokens_in, j.tokens_out = status, attempts, err, tin, tout
        j.finished_at = dt.datetime.utcnow()
