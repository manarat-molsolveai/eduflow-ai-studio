import html, datetime as dt
import streamlit as st
from core import svc, gen

NAVY, TEAL, LIGHT, PURPLE, GOLD = "#14263D", "#16A6A1", "#F5F7FA", "#7568D8", "#E6B85C"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap');
html, body, .stApp, p, label, h1, h2, h3, h4, li, input, textarea {{ font-family: 'Tajawal','Noto Sans Arabic','Segoe UI',Tahoma,sans-serif; }}
[data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded','Material Symbols Outlined' !important; }}
.stApp {{ direction: rtl; background: {LIGHT}; color: {NAVY}; }}
.block-container {{ padding-top: 1.4rem; max-width: 1180px; }}
input, textarea {{ direction: rtl; text-align: right; }}
section[data-testid="stSidebar"] {{ background: {NAVY}; direction: rtl; }}
section[data-testid="stSidebar"] * {{ color: #E8EEF5 !important; }}
section[data-testid="stSidebar"] .stButton > button {{ width: 100%; justify-content: flex-start; background: transparent; border: 0; border-radius: 10px; padding: .55rem .8rem; text-align: right; font-weight: 500; }}
section[data-testid="stSidebar"] .stButton > button:hover {{ background: rgba(255,255,255,.09); }}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{ background: {TEAL}; }}
h1, h2, h3 {{ color: {NAVY}; font-weight: 700; letter-spacing: 0; }}
.ef-card {{ background: #fff; border: 1px solid #E4E9F0; border-radius: 16px; padding: 1.1rem 1.25rem; margin-bottom: .8rem; box-shadow: 0 1px 2px rgba(20,38,61,.04); transition: box-shadow .2s, transform .2s; }}
.ef-card:hover {{ box-shadow: 0 6px 18px rgba(20,38,61,.08); transform: translateY(-1px); }}
.ef-stat {{ background:#fff; border:1px solid #E4E9F0; border-radius:16px; padding: 1rem 1.2rem; border-top: 4px solid {TEAL}; }}
.ef-stat .n {{ font-size: 2rem; font-weight: 700; color: {NAVY}; line-height:1.1; }}
.ef-stat .l {{ color:#5B6B7D; font-size:.9rem; }}
.ef-hero {{ background: linear-gradient(135deg, {NAVY} 0%, #1d3a5c 100%); color:#fff; border-radius: 20px; padding: 1.6rem 1.8rem; margin-bottom: 1.2rem; }}
.ef-hero h2 {{ color:#fff; margin:0 0 .3rem 0; }} .ef-hero p {{ color:#C9D6E4; margin:0; }}
.ef-badge {{ display:inline-block; padding:.15rem .65rem; border-radius:999px; font-size:.78rem; font-weight:500; background:#E9F7F6; color:#0B7C78; margin-left:.3rem; }}
.ef-badge.warn {{ background:#FFF4DC; color:#8A6410; }} .ef-badge.err {{ background:#FDE8E8; color:#A12626; }} .ef-badge.pur {{ background:#EEEBFB; color:#4B3FB3; }}
.ef-empty {{ text-align:center; padding:2rem 1rem; color:#5B6B7D; background:#fff; border:2px dashed #D5DDE8; border-radius:16px; }}
.ef-slide {{ background:#fff; border:1px solid #E4E9F0; border-radius:12px; aspect-ratio:16/9; padding:1rem 1.3rem; border-top: 36px solid {NAVY}; overflow:hidden; position:relative; }}
.ef-slide.title {{ background:{NAVY}; color:#fff; border-top: 0; display:flex; flex-direction:column; justify-content:center; }}
.ef-slide h4 {{ margin:.1rem 0 .5rem; color:{NAVY}; font-size:1.05rem; }} .ef-slide.title h4 {{ color:#fff; font-size:1.5rem; }}
.ef-slide ul {{ margin:0; padding-right:1.1rem; font-size:.82rem; }}
.stButton > button[kind="primary"] {{ background:{TEAL}; border:0; border-radius:10px; font-weight:700; }}
.stButton > button {{ border-radius:10px; }}
div[data-testid="stMetric"] {{ background:#fff; border-radius:14px; padding:.6rem 1rem; border:1px solid #E4E9F0; }}
@media (max-width: 768px) {{ .block-container {{ padding: .8rem .7rem; }} .ef-hero {{ padding: 1.1rem; }} .ef-stat .n {{ font-size:1.5rem; }} .stButton > button {{ min-height: 44px; }} }}
</style>
"""


def esc(x):
    return html.escape(str(x or ""))


def card(inner):
    st.markdown(f'<div class="ef-card">{inner}</div>', unsafe_allow_html=True)


def badge(text, kind=""):
    return f'<span class="ef-badge {kind}">{esc(text)}</span>'


def status_badge(s):
    k = {"completed": "", "ready": "", "review": "pur", "needs_review": "warn", "failed": "err", "processing": "warn"}.get(s, "pur")
    return badge(svc.STATUS_AR.get(s, s), k)


def stat(n, label):
    return f'<div class="ef-stat"><div class="n">{n}</div><div class="l">{esc(label)}</div></div>'


def empty(msg, sub=""):
    st.markdown(f'<div class="ef-empty"><b>{esc(msg)}</b><br><span>{esc(sub)}</span></div>', unsafe_allow_html=True)


def fmt_dt(d):
    if not d:
        return ""
    return (d + dt.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")  # displayed in UTC+3 (Arabia Standard Time)


def go(page, **kw):
    st.session_state["page"] = page
    for k, v in kw.items():
        st.session_state[k] = v
    st.rerun()


def hero(title, sub):
    st.markdown(f'<div class="ef-hero"><h2>{esc(title)}</h2><p>{esc(sub)}</p></div>', unsafe_allow_html=True)


def type_label(t):
    return gen.PROJECT_TYPES.get(t, t)
