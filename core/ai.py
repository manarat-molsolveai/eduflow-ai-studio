"""AI provider layer. Calls happen server-side only. Nothing is claimed to work until tested."""
import os, json, base64, hashlib, time
import requests
from . import db
from .db import UserSetting, AIJob
from sqlalchemy import select

PROVIDERS = {
    "github": {"label": "GitHub Models (مفتاح المنصة المشترك)", "models": ["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4.1-mini"]},
    "openai": {"label": "OpenAI", "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]},
    "gemini": {"label": "Google Gemini", "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-pro"]},
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


def _err_detail(r):
    """Readable reason from a provider error response (never includes the key)."""
    try:
        j = r.json()
        e = j.get("error", j) if isinstance(j, dict) else {}
        msg = e.get("message") if isinstance(e, dict) else str(e)
        st = e.get("status", "") if isinstance(e, dict) else ""
        return f"HTTP {r.status_code} {st}: {str(msg)[:220]}"
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:120]!r}"


def gemini_models(key, timeout=30):
    """Models this key can really call with generateContent (live ListModels).
    Slow networks: a timeout/connection error retries once with a longer wait."""
    r = None
    for tmo in (timeout, max(90, timeout)):
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", timeout=tmo,
                             headers={"x-goog-api-key": key})
            break
        except (requests.Timeout, requests.ConnectionError):
            continue
    if r is None:
        raise RuntimeError("تعذر الوصول إلى خوادم Google (مهلة أو انقطاع في الشبكة) رغم إعادة المحاولة بمهلة أطول")
    if r.status_code >= 400:
        raise RuntimeError(_err_detail(r))
    out = []
    for m in r.json().get("models", []):
        n = m.get("name", "").replace("models/", "")
        if "generateContent" in m.get("supportedGenerationMethods", []) and n.startswith("gemini-"):
            out.append(n)
    return out


def _pick_gemini(avail, want):
    if want in avail:
        return want
    bad = ("tts", "image", "live", "audio", "embed", "transcribe", "translate", "preview", "exp", "robotics", "computer", "thinking")
    ok = [n for n in avail if "flash" in n and not any(b in n for b in bad)]
    for pref in PROVIDERS["gemini"]["models"]:
        if pref in ok:
            return pref
    return sorted(ok, reverse=True)[0] if ok else (avail[0] if avail else want)


def _call(provider, model, key, system, prompt, max_tokens=4000, timeout=90):
    if provider == "github":
        body = {"max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        errs = []
        for url, mname in (("https://models.github.ai/inference/chat/completions", model),
                           ("https://models.inference.ai.azure.com/chat/completions", model.split("/")[-1])):
            try:
                r = requests.post(url, timeout=timeout, headers={"Authorization": f"Bearer {key}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
                                  json={**body, "model": mname})
                if r.status_code >= 400:
                    errs.append(f"HTTP {r.status_code} {r.text[:120]}")
                    continue
                j = r.json()
                return j["choices"][0]["message"]["content"], j.get("usage", {}).get("prompt_tokens", 0), j.get("usage", {}).get("completion_tokens", 0)
            except ValueError:
                errs.append(f"non-JSON {url.split('/')[2]} HTTP {r.status_code} {r.headers.get('content-type')} {r.text[:80]!r}")
            except requests.RequestException as e:
                errs.append(f"{type(e).__name__} {url.split('/')[2]}")
        raise RuntimeError(" | ".join(errs) or "فشل")
    if provider == "openai":
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=timeout,
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
        order = [model] + [m for m in PROVIDERS["gemini"]["models"] if m != model]
        last, net_errs = None, []
        for m in order:
            r = None
            # Slow networks: retry each model once with a longer wait before moving on.
            for tmo in (timeout, min(120, max(90, timeout))):
                try:
                    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                      timeout=tmo, headers={"x-goog-api-key": key},
                                      json={"systemInstruction": {"parts": [{"text": system}]},
                                            "contents": [{"parts": [{"text": prompt}]}],
                                            "generationConfig": {"maxOutputTokens": max_tokens}})
                    break
                except (requests.Timeout, requests.ConnectionError) as e:
                    net_errs.append(f"{type(e).__name__}@{m}")
                    continue
            if r is None:
                if last is None:
                    break  # no HTTP response at all: network unreachable, more models would just waste minutes
                continue
            if r.status_code in (429, 500, 503, 404):
                last = r
                continue
            r.raise_for_status()
            j = r.json()
            u = j.get("usageMetadata", {})
            _call.last_model = m
            return j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)
        if last is not None:
            last.raise_for_status()
        raise RuntimeError("تعذر الوصول إلى خوادم Google (مهلة أو انقطاع في الشبكة) رغم إعادة المحاولة بمهلة أطول وتجربة نماذج أخرى")
    raise ValueError("unknown provider")


def test_connection(uid, provider, model, key):
    """Real round trip. Returns (ok, message). Records result only when it really succeeded."""
    try:
        key = (key or "").strip().strip('"\'')
        if provider == "gemini":
            avail = gemini_models(key)
            if not avail:
                set_setting(uid, f"tested_{provider}", "fail")
                return False, "المفتاح صالح لكن لا توجد نماذج Gemini متاحة له"
            picked = _pick_gemini(avail, model)
            if picked != model:
                set_setting(uid, "model", picked)
                model = picked
            _call.last_model = model
        out, _, _ = _call(provider, model, key, "Reply with the single word OK.", "ping", max_tokens=16, timeout=30)
        if provider == "gemini" and getattr(_call, "last_model", model) != model:
            set_setting(uid, "model", _call.last_model)
        ok = bool(out and out.strip())
        set_setting(uid, f"tested_{provider}", "ok" if ok else "fail")
        return ok, ("اتصال ناجح" if ok else "رد فارغ")
    except requests.HTTPError as e:
        set_setting(uid, f"tested_{provider}", "fail")
        det = _err_detail(e.response) if e.response is not None else "?"
        return False, f"فشل الاتصال ({det}). تحقق من المفتاح والنموذج"
    except RuntimeError as e:
        set_setting(uid, f"tested_{provider}", "fail")
        return False, f"فشل الاتصال: {str(e)[:300]}"
    except Exception as e:
        set_setting(uid, f"tested_{provider}", "fail")
        return False, f"فشل الاتصال: {type(e).__name__} {str(e)[:300]}"


def extract_json(txt):
    txt = txt.strip()
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[1] if "\n" in txt else txt
        txt = txt.rsplit("```", 1)[0]
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("no json")
    return json.loads(txt[a:b + 1])


PROOF_SYS = ("أنت مدقق لغوي عربي محترف. مهمتك تنقيح JSON عربي تعليمي دون تغيير بنيته. "
             "صحّح الأخطاء الإملائية والنحوية والكلمات الخاطئة (مثل «الحزين» مكان «الحي»)، وحسّن الصياغات الركيكة أو غير الطبيعية، "
             "وأصلح أي حروف لاتينية أو كلمات أجنبية داخل النص العربي باستبدالها بالكلمة العربية الصحيحة من السياق. "
             "لا تغيّر: بنية JSON ولا أسماء الحقول ولا عدد العناصر وترتيبها ولا المعنى، ولا تضف حقائق أو أرقامًا. أخرج JSON صالحًا فقط.")


def _proofread(provider, model, key, data, validator):
    """One linguistic cleanup pass over generated content. Returns cleaned data or None (keep original)."""
    try:
        out, a, b = _call(provider, model, key, PROOF_SYS, json.dumps(data, ensure_ascii=False), max_tokens=8000)
        fixed = extract_json(out)
        validator(fixed)
        return fixed, a, b
    except Exception:
        return None


def generate_json(uid, project_id, module, system, prompt, validator, retries=2, max_tokens=6000):
    """Run provider with retry + validation + one proofreading pass; log job. Raises RuntimeError on final failure."""
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
            out, a, b = _call(provider, model, key, system, p, max_tokens=max_tokens)
            tin += a
            tout += b
            data = extract_json(out)
            validator(data)
            proofed = _proofread(provider, model, key, data, validator)
            if proofed:
                data, a2, b2 = proofed
                tin += a2
                tout += b2
            _finish(jid, "done", attempt, "", tin, tout)
            return data, provider, model
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:400]}"
            time.sleep(1)
    _finish(jid, "failed", retries + 1, err, tin, tout)
    raise RuntimeError(err)


def _finish(jid, status, attempts, err, tin, tout):
    import datetime as dt
    with db.session() as s:
        j = s.get(AIJob, jid)
        j.status, j.attempts, j.error, j.tokens_in, j.tokens_out = status, attempts, err, tin, tout
        j.finished_at = dt.datetime.utcnow()
