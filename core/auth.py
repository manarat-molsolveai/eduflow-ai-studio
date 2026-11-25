import os, hashlib, hmac, secrets, re, datetime as dt
from sqlalchemy import select, delete
from . import db
from .db import User, SessionTok

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash(pw, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + h.hex()


def _verify(pw, stored):
    try:
        _, salt, h = stored.split("$")
        c = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(c.hex(), h)
    except Exception:
        return False


def register(email, name, pw):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return None, "البريد الإلكتروني غير صالح"
    if len(pw or "") < 8:
        return None, "كلمة المرور يجب ألا تقل عن 8 أحرف"
    with db.session() as s:
        if s.execute(select(User).where(User.email == email)).scalar_one_or_none():
            return None, "هذا البريد مسجل مسبقًا"
        u = User(email=email, name=(name or "").strip()[:100], pw_hash=_hash(pw))
        s.add(u)
        s.flush()
        uid = u.id
    db.log(uid, "register", email)
    return uid, ""


def login(email, pw):
    email = (email or "").strip().lower()
    with db.session() as s:
        u = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not u:
            _verify(pw or "", _hash("x"))  # equalise timing
            return None, "بيانات الدخول غير صحيحة"
        if u.locked_until and u.locked_until > dt.datetime.utcnow():
            return None, "الحساب مقفل مؤقتًا بسبب محاولات متكررة. حاول بعد 10 دقائق"
        if not _verify(pw or "", u.pw_hash):
            u.failed = (u.failed or 0) + 1
            if u.failed >= 5:
                u.locked_until = dt.datetime.utcnow() + dt.timedelta(minutes=10)
                u.failed = 0
            return None, "بيانات الدخول غير صحيحة"
        u.failed = 0
        u.locked_until = None
        uid = u.id
    db.log(uid, "login")
    return uid, ""


def new_session(uid, days=14):
    tok = secrets.token_urlsafe(32)
    with db.session() as s:
        s.add(SessionTok(token_hash=hashlib.sha256(tok.encode()).hexdigest(), user_id=uid,
                         expires_at=dt.datetime.utcnow() + dt.timedelta(days=days)))
    return tok


def user_from_token(tok):
    if not tok:
        return None
    h = hashlib.sha256(tok.encode()).hexdigest()
    with db.session() as s:
        r = s.execute(select(SessionTok).where(SessionTok.token_hash == h)).scalar_one_or_none()
        if not r or r.expires_at < dt.datetime.utcnow():
            return None
        return r.user_id


def end_session(tok):
    if not tok:
        return
    h = hashlib.sha256(tok.encode()).hexdigest()
    with db.session() as s:
        s.execute(delete(SessionTok).where(SessionTok.token_hash == h))


def get_user(uid):
    with db.session() as s:
        u = s.get(User, uid)
        return {"id": u.id, "email": u.email, "name": u.name} if u else None


def change_password(uid, old, new):
    if len(new or "") < 8:
        return False, "كلمة المرور الجديدة قصيرة"
    with db.session() as s:
        u = s.get(User, uid)
        if not _verify(old or "", u.pw_hash):
            return False, "كلمة المرور الحالية غير صحيحة"
        u.pw_hash = _hash(new)
    db.log(uid, "password_changed")
    return True, ""
