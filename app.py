import streamlit as st

st.set_page_config(page_title="استوديو الإنتاج التعليمي الذكي | EduFlow AI Studio", page_icon="🎓", layout="wide", initial_sidebar_state="auto")

# Hot-reload edited app modules so a redeploy takes effect without a restart (a restart wipes the temporary database).
import importlib, os, sys
_HOT = ["core.ai", "core.templates", "core.gen", "core.quality", "core.export", "core.svc", "ui", "v_work", "v_misc", "v_wizard"]
_seen = sys.__dict__.setdefault("_ef_mtimes", {})
_changed = False
for _n in _HOT:
    try:
        _m = importlib.import_module(_n)
        _mt = os.path.getmtime(_m.__file__)
        if _seen.get(_n) != _mt:
            if _n in _seen or _changed is False:
                pass
            _seen[_n] = _mt
            _changed = True
    except Exception:
        pass
if _changed:
    for _n in _HOT:
        try:
            importlib.reload(sys.modules[_n])
        except Exception:
            pass

from core import db, auth, svc, gen, ai
from ui import *
import v_wizard, v_work, v_misc

st.markdown(CSS, unsafe_allow_html=True)

try:
    db.init()
except Exception as e:  # visible error state, not hidden
    st.error("تعذر الاتصال بقاعدة البيانات. لم يُحفظ أي شيء.")
    st.code(f"{type(e).__name__}: {str(e)[:300]}")
    st.stop()


def auth_screen():
    st.markdown('<div class="ef-hero"><h2>🎓 استوديو الإنتاج التعليمي الذكي</h2><p>EduFlow AI Studio — حوّل أي درس أو ملف إلى مخرجات تعليمية قابلة للتعديل والتصدير.</p></div>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["تسجيل الدخول", "حساب جديد"])
    with t1:
        with st.form("login"):
            e = st.text_input("البريد الإلكتروني")
            p = st.text_input("كلمة المرور", type="password")
            if st.form_submit_button("دخول", type="primary"):
                uid, err = auth.login(e, p)
                if err: st.error(err)
                else: start(uid)
    with t2:
        with st.form("reg"):
            n = st.text_input("الاسم")
            e = st.text_input("البريد الإلكتروني", key="re")
            p = st.text_input("كلمة المرور (8 أحرف على الأقل)", type="password", key="rp")
            if st.form_submit_button("إنشاء الحساب", type="primary"):
                uid, err = auth.register(e, n, p)
                if err: st.error(err)
                else: start(uid)
    st.caption("بياناتك خاصة بحسابك فقط. لا تُعرض مشاريعك لأي مستخدم آخر.")


def start(uid):
    tok = auth.new_session(uid)
    st.session_state["uid"] = uid
    st.session_state["tok"] = tok
    st.query_params["t"] = tok
    st.session_state["page"] = "dashboard"
    st.rerun()


def logout():
    auth.end_session(st.session_state.get("tok"))
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()


if "uid" not in st.session_state:
    tok = st.query_params.get("t")
    uid = auth.user_from_token(tok) if tok else None
    if uid:
        st.session_state["uid"], st.session_state["tok"] = uid, tok
    else:
        auth_screen(); st.stop()

uid = st.session_state["uid"]
user = auth.get_user(uid)
if not user:
    logout()
page = st.session_state.get("page", "dashboard")

NAV = [("dashboard", "🏠  لوحة التحكم"), ("new", "➕  مشروع جديد"), ("projects", "📁  المشاريع"), ("library", "🗂️  المكتبة والملفات"), ("analytics", "📊  التحليلات"),
       ("settings", "⚙️  الإعدادات والذكاء الاصطناعي"), ("status", "✅  حالة النظام")]
with st.sidebar:
    st.markdown(f"### 🎓 EduFlow\n<small>استوديو الإنتاج التعليمي الذكي</small>", unsafe_allow_html=True)
    st.markdown(f"<small>{esc(user['name'] or user['email'])}</small>", unsafe_allow_html=True)
    for k, lab in NAV:
        if st.button(lab, key=f"nav_{k}", type="primary" if page == k else "secondary"):
            if k == "new":
                st.session_state.pop("wz_pid", None); st.session_state["wz_step"] = 0
            st.session_state.pop("oid", None)
            st.session_state["page"] = k; st.rerun()
    nots = svc.notifications(uid, 5)
    unread = sum(1 for n in nots if not n["read"])
    with st.expander(f"🔔 الإشعارات ({unread})"):
        if not nots: st.caption("لا إشعارات")
        for n in nots: st.markdown(f"<small>{'●' if not n['read'] else '○'} {esc(n['message'])}</small>", unsafe_allow_html=True)
        if unread and st.button("تعليم كمقروءة", key="readn"): svc.mark_notifications_read(uid); st.rerun()
    if st.button("🚪  تسجيل الخروج", key="logout"): logout()


def dashboard():
    name = (user["name"] or "").split(" ")[0] or "مرحبًا"
    hero(f"أهلًا {name}", "أنشئ مشروعًا، أضف مراجعك، ودع الاستوديو يبني لك المخرجات القابلة للتعديل والتصدير.")
    c = st.columns(4)
    s = svc.stats(uid)
    pr = s["projects"]
    c[0].markdown(stat(sum(pr.values()), "إجمالي المشاريع"), unsafe_allow_html=True)
    c[1].markdown(stat(pr.get("processing", 0) + pr.get("review", 0) + pr.get("planning", 0) + pr.get("revision", 0), "قيد العمل"), unsafe_allow_html=True)
    c[2].markdown(stat(pr.get("completed", 0), "مكتملة"), unsafe_allow_html=True)
    c[3].markdown(stat(sum(s["outputs"].values()), "المخرجات"), unsafe_allow_html=True)
    st.write("")
    q1, q2, q3, q4 = st.columns(4)
    if q1.button("➕ مشروع جديد", type="primary", key="qa1"): st.session_state["wz_step"] = 0; st.session_state.pop("wz_pid", None); go("new")
    if q2.button("📁 كل المشاريع", key="qa2"): go("projects")
    if q3.button("🗂️ رفع ملف للمكتبة", key="qa3"): go("library")
    if q4.button("⚙️ ربط الذكاء الاصطناعي", key="qa4"): go("settings")
    qs = st.text_input("🔎 بحث في المشاريع", placeholder="اسم المشروع أو المادة أو الملاحظات", key="dq")
    projs = svc.list_projects(uid, q=qs)
    if qs: st.subheader(f"نتائج البحث ({len(projs)})")
    else: st.subheader("المشاريع الأخيرة")
    if not projs:
        empty("لا توجد مشاريع بعد" if not qs else "لا نتائج مطابقة", "ابدأ بمشروعك الأول من زر «مشروع جديد».")
    for p in projs[:6]:
        a, b = st.columns([5, 1])
        a.markdown(f'<div class="ef-card"><b>{esc(p["name"])}</b> {status_badge(p["status"])} {badge(type_label(p["ptype"]), "pur")}<br><small>{esc(p["subject"])} {esc(p["stage"])} • تحديث {fmt_dt(p["updated_at"])}</small></div>', unsafe_allow_html=True)
        if b.button("فتح", key=f"dp{p['id']}"): go("project", pid=p["id"])
    l, r = st.columns(2)
    with l:
        st.subheader("المهام المفتوحة")
        ts = svc.list_tasks(uid, open_only=True)[:6]
        if not ts: st.caption("لا توجد مهام مفتوحة.")
        for t in ts: st.markdown(f"- {esc(t['title'])} `{t['priority']}`")
    with r:
        st.subheader("سجل النشاط")
        ac = svc.activity(uid, limit=8)
        if not ac: st.caption("لا نشاط بعد.")
        for a in ac: st.markdown(f"<small>{fmt_dt(a['at'])} • {esc(a['action'])} {esc(a['detail'])}</small>", unsafe_allow_html=True)
    if s["outputs"]:
        st.subheader("إحصاءات المخرجات")
        st.bar_chart({v_work.KIND_AR.get(k, k): n for k, n in s["outputs"].items()}, color="#16A6A1")


def projects_page():
    st.markdown("## المشاريع")
    c1, c2, c3 = st.columns([3, 2, 2])
    q = c1.text_input("بحث", key="pq")
    stt = c2.selectbox("الحالة", [""] + list(svc.STATUS_AR)[:7], format_func=lambda x: "الكل" if not x else svc.STATUS_AR[x], key="pst")
    ty = c3.selectbox("النوع", [""] + list(gen.PROJECT_TYPES), format_func=lambda x: "الكل" if not x else gen.PROJECT_TYPES[x], key="pty")
    ps = svc.list_projects(uid, q, stt, ty)
    if not ps: empty("لا توجد مشاريع مطابقة", "أنشئ مشروعًا جديدًا من الشريط الجانبي.")
    for p in ps:
        a, b = st.columns([5, 1])
        a.markdown(f'<div class="ef-card"><b>{esc(p["name"])}</b> {status_badge(p["status"])} {badge(type_label(p["ptype"]), "pur")}<br><small>{esc(p["subject"])} {esc(p["stage"])} {esc(p["grade"])} • أُنشئ {fmt_dt(p["created_at"])}</small></div>', unsafe_allow_html=True)
        if b.button("فتح", key=f"pp{p['id']}"): go("project", pid=p["id"])


if page == "dashboard": dashboard()
elif page == "new": v_wizard.render(uid)
elif page == "projects": projects_page()
elif page == "project": v_work.workspace(uid)
elif page == "library": v_misc.library(uid)
elif page == "analytics": v_misc.analytics(uid)
elif page == "settings": v_misc.settings(uid)
elif page == "status": v_misc.status(uid)
