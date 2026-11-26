import streamlit as st
from core import svc, gen, ai, db, export as ex
from ui import *
import v_work


def library(uid):
    st.markdown("## المكتبة والملفات")
    t1, t2 = st.tabs(["المراجع والمصادر", "الملفات المصدّرة"])
    with t1:
        c1, c2, c3 = st.columns(3)
        q = c1.text_input("بحث في العنوان والمحتوى", key="lq")
        tag = c2.text_input("وسم", key="ltag")
        cat = c3.text_input("تصنيف", key="lcat")
        srcs = svc.list_sources(uid, None, q, tag, cat)
        with st.expander("رفع ملف إلى المكتبة (يمكن ربطه بمشروع)"):
            projs = svc.list_projects(uid)
            link = st.selectbox("ربط بمشروع", [None] + [p["id"] for p in projs], format_func=lambda x: "بدون ربط" if x is None else next(p["name"] for p in projs if p["id"] == x), key="llink")
            up = st.file_uploader("ملف", key="lup", type=["pdf", "docx", "pptx", "txt", "md", "csv", "xlsx", "png", "jpg", "jpeg", "webp"])
            ltags = st.text_input("وسوم (مفصولة بفواصل)", key="ltags")
            lcat = st.text_input("التصنيف", key="lcats")
            if up and st.button("حفظ في المكتبة", type="primary", key="lsave"):
                sid, ok, note = svc.add_source(uid, link, up.name, "other", filename=up.name, data=up.getvalue(), category=lcat, tags=ltags)
                st.success("تم الحفظ. " + note); st.rerun()
        if not srcs: empty("المكتبة فارغة", "ارفع ملفًا أو أضف مصادر من مشروع.")
        for s in srcs:
            with st.expander(f"{s['title']} • {s['kind']} • v{s['version']}"):
                st.markdown((badge("نص مقروء") if s["readable"] else badge("غير مقروء", "warn")) + f" {esc(s['read_note'])} {badge(s['category'] or 'بلا تصنيف', 'pur')} {esc(s['tags'])}", unsafe_allow_html=True)
                st.caption(f"سجل المصدر: النوع {s['kind']} • الحجم {s['size']//1024} KB • أُضيف {fmt_dt(s['created_at'])}" + (f" • الرابط {s['url']}" if s["url"] else "") + f" • مرتبط بمشروع {s['project_id'] or '—'}")
                if s["content"]: st.text(s["content"][:1200])
                full = svc.get_source(uid, s["id"])
                if s["kind"] == "image" and full["blob"]:
                    try: st.image(full["blob"], width=240)
                    except Exception: st.caption("تعذر عرض الصورة")
                a, b = st.columns(2)
                if full["blob"]: a.download_button("تنزيل", full["blob"], s["filename"], key=f"ld{s['id']}")
                if b.button("حذف", key=f"lx{s['id']}"): svc.delete_source(uid, s["id"]); st.rerun()
    with t2:
        exps = svc.list_exports(uid)
        if not exps: empty("لا توجد ملفات مصدّرة", "صدّر مخرجًا من مساحة المشروع.")
        v_work.export_list(uid, exps)


def settings(uid):
    st.markdown("## الإعدادات والذكاء الاصطناعي")
    st.markdown("### مزود الذكاء الاصطناعي")
    if not ai.can_store_keys():
        st.error("حفظ مفاتيح API غير متاح: لم يُضبط سر الخادم APP_SECRET. المفاتيح لا تُحفظ بدونه ولا تظهر للمتصفح أبدًا.")
    act = ai.active(uid)
    st.markdown("الحالة الحالية: " + (badge(f"متصل ومُختبر: {ai.PROVIDERS[act[0]]['label']}") if act else badge("غير متصل: التوليد بالقواعد المحلية فقط", "warn")), unsafe_allow_html=True)
    prov = st.selectbox("المزود", list(ai.PROVIDERS), format_func=lambda k: ai.PROVIDERS[k]["label"], index=list(ai.PROVIDERS).index(ai.get_setting(uid, "provider") or ("github" if ai.platform_key() else "openai")))
    models = ai.PROVIDERS[prov]["models"]
    cur = ai.get_setting(uid, "model", models[0])
    model = st.selectbox("النموذج", models, index=models.index(cur) if cur in models else 0)
    key = st.text_input("مفتاح API (يُحفظ مشفرًا على الخادم ولا يُعرض مرة أخرى)", type="password", placeholder="مفتاح محفوظ" if ai.has_key(uid, prov) else "")
    c1, c2 = st.columns(2)
    if c1.button("حفظ واختبار الاتصال", type="primary", disabled=not ai.can_store_keys()):
        if key.strip():
            ai.save_key(uid, prov, key.strip())
        k = ai.get_key(uid, prov)
        if not k: st.error("أدخل مفتاحًا أولًا")
        else:
            ai.set_setting(uid, "provider", prov); ai.set_setting(uid, "model", model)
            with st.spinner("جاري المحاولة... اختبار حقيقي للاتصال، وقد يستغرق بضع دقائق مع شبكة بطيئة (إعادة محاولة تلقائية بمهلة أطول)"):
                ok, msg = ai.test_connection(uid, prov, model, k)
            (st.success if ok else st.error)(msg)
            db.log(uid, "ai_test", f"{prov} {'ok' if ok else 'fail'}")
    st.caption("لا يُعتبر المزود متصلًا إلا بعد نجاح اختبار فعلي. عند فشله يرجع النظام للقواعد المحلية ولا يدّعي توليدًا ذكيًا.")
    s = svc.stats(uid)
    st.markdown(f"**الاستخدام:** {s['ai_jobs']} مهمة ذكاء اصطناعي • {s['tokens_in']} رمز مُدخل • {s['tokens_out']} رمز مُخرج")
    with st.expander("سجل مهام الذكاء الاصطناعي"):
        js = svc.ai_jobs(uid)
        if not js: st.caption("لا مهام بعد.")
        for j in js: st.markdown(f"- {fmt_dt(j['at'])} `{j['module']}` {j['provider']}/{j['model']} **{j['status']}** محاولات {j['attempts']} {esc(j['error'])}")
    st.divider()
    st.markdown("### كلمة المرور")
    with st.form("pw"):
        o = st.text_input("الحالية", type="password"); n = st.text_input("الجديدة", type="password")
        if st.form_submit_button("تغيير"):
            ok, msg = __import__("core.auth", fromlist=["x"]).change_password(uid, o, n)
            (st.success("تم التغيير") if ok else st.error(msg))
    delete_account_ui(uid)


def delete_account_ui(uid):
    st.divider()
    st.markdown("### حذف الحساب")
    with st.expander("حذف حسابي وكل بياناتي نهائيًا"):
        st.warning("يحذف الحساب وجميع المشاريع والملفات والمخرجات. لا يمكن التراجع.")
        # st.form: كل الحقول تُرسل دفعة واحدة عند الضغط، فلا يصل زر الحذف قبل مزامنة كلمة المرور.
        with st.form("del_account_form"):
            pw = st.text_input("كلمة المرور للتأكيد", type="password")
            sure = st.checkbox("أفهم أن الحذف نهائي")
            submitted = st.form_submit_button("حذف الحساب نهائيًا")
        if submitted:
            if not sure:
                st.error("أكّد أنك تفهم أن الحذف نهائي")
            else:
                ok, msg = __import__("core.auth", fromlist=["x"]).delete_account(uid, pw)
                if ok:
                    st.session_state.clear(); st.query_params.clear(); st.rerun()
                else:
                    st.error(msg)


FEATURES = [
    ("المصادقة (تسجيل/دخول/خروج، جلسات، قفل بعد 5 محاولات)", "منفّذ ومُختبر"),
    ("المشاريع: إنشاء/تعديل/بحث/نسخ/حذف بتأكيد", "منفّذ ومُختبر"),
    ("معالج المشروع (7 خطوات + الإنتاج والمراجعة والتصدير داخل المساحة)", "منفّذ"),
    ("رفع الملفات: PDF/DOCX/PPTX/TXT/CSV/XLSX قراءة نصية حقيقية", "منفّذ ومُختبر"),
    ("الصور: تُحفظ وتُدرج في الشرائح، بدون OCR", "منفّذ جزئيًا"),
    ("الروابط: تُسجل كمراجع فقط، لا يُجلب محتواها", "منفّذ جزئيًا"),
    ("محرر العروض (شرائح JSON، تحرير/ترتيب/حذف/إضافة/صور) + PPTX حقيقي + PDF", "منفّذ ومُختبر"),
    ("المستندات (10 أنواع) + DOCX/PDF", "منفّذ ومُختبر"),
    ("أوراق العمل والاختبارات (أساسي، توليد من نصك) + DOCX/PDF/XLSX", "منفّذ أساسي"),
    ("مراجعة الجودة بقواعد موثقة + بوابة جودة + تجاوز مسجّل", "منفّذ"),
    ("إصدارات المخرجات والاسترجاع", "منفّذ"),
    ("إدارة الملفات المصدّرة (تنزيل/إعادة تسمية/حذف/ZIP)", "منفّذ"),
    ("المهام وسجل النشاط والإشعارات", "منفّذ"),
    ("طبقة مزودي الذكاء الاصطناعي (OpenAI/Gemini/Anthropic)", "مبنية، تتطلب مفتاحًا. لم تُختبر مع مزود حقيقي بعد"),
    ("تصدير ZIP/XLSX/CSV/HTML", "منفّذ"),
    ("الواجهة بالإنجليزية", "غير منفّذ (المحتوى يدعم الإنجليزية، الواجهة عربية)"),
    ("Video Studio / Game Studio", "غير منفّذ (المرحلة 3)"),
    ("إدارة العملاء / المالية / الأتمتة", "غير منفّذ (المرحلة 3)"),
    ("التحليلات (أرقام حقيقية من بياناتك)", "منفّذ"),
    ("قوالب جاهزة (3) تملأ الأهداف وخطة المخرجات", "منفّذ أساسي"),
    ("قوالب يحفظها المستخدم / سير عمل مخصص / متعدد المستخدمين", "غير منفّذ"),
    ("الحفظ التلقائي أثناء الكتابة", "غير منفّذ: الحفظ بزر «حفظ»"),
]


def status(uid):
    st.markdown("## حالة النظام")
    b = db.backend_name()
    c = st.columns(3)
    c[0].metric("قاعدة البيانات", b)
    c[1].metric("الذكاء الاصطناعي", "متصل" if ai.active(uid) else "غير متصل")
    c[2].metric("مفتاح الخادم", "مضبوط" if ai.can_store_keys() else "غير مضبوط")
    if b == "SQLite":
        st.warning("قاعدة البيانات الحالية SQLite على قرص مؤقت في الاستضافة. قد تُفقد البيانات عند إعادة تشغيل التطبيق أو إعادة بنائه. للاستمرارية الدائمة اضبط DATABASE_URL لقاعدة PostgreSQL خارجية. صدّر ملفاتك المهمة وحمّلها.")
    else:
        st.success("قاعدة PostgreSQL خارجية: البيانات دائمة.")
    st.markdown("### الصيغ المدعومة للتصدير")
    for k, f in ex.FORMATS.items(): st.markdown(f"- {v_work.KIND_AR[k]}: " + "، ".join(x.upper() for x in f))
    st.markdown("### الوظائف")
    for f, s in FEATURES:
        st.markdown(f"- {f} — " + (badge(s) if s.startswith("منفّذ") else badge(s, "warn" if "مبنية" in s else "err")), unsafe_allow_html=True)


def analytics(uid):
    st.markdown("## التحليلات")
    st.caption("أرقام حقيقية محسوبة من بياناتك فقط. لا توجد تقديرات ولا بيانات تجريبية. تتعلق بحسابك وحده.")
    a = svc.analytics(uid)
    if not a["outputs"]:
        empty("لا بيانات بعد", "أنتج مخرجًا واحدًا على الأقل لتظهر التحليلات.")
        return
    c = st.columns(4)
    c[0].markdown(stat(a["outputs"], "إجمالي المخرجات"), unsafe_allow_html=True)
    c[1].markdown(stat(a["edited"], "مخرجات عُدّلت"), unsafe_allow_html=True)
    c[2].markdown(stat(a["total_versions"], "إصدارات محفوظة"), unsafe_allow_html=True)
    c[3].markdown(stat(sum(a["exports"].values()), "ملفات مصدّرة"), unsafe_allow_html=True)
    st.write("")
    l, r = st.columns(2)
    with l:
        st.subheader("المخرجات حسب النوع")
        st.bar_chart({v_work.KIND_AR.get(k, k): n for k, n in a["kinds"].items()}, color="#16A6A1")
        st.subheader("طريقة التوليد")
        st.bar_chart({("قواعد محلية" if g == "local-rules" else g): n for g, n in a["generators"].items()}, color="#7C5CFC")
    with r:
        st.subheader("حالة المخرجات")
        st.bar_chart({{"needs_review": "يحتاج مراجعة", "approved": "معتمد", "failed": "فشل", "processing": "قيد المعالجة"}.get(k, k): n for k, n in a["status"].items()}, color="#16A6A1")
        st.subheader("الصيغ المصدّرة")
        if a["exports"]: st.bar_chart({k.upper(): n for k, n in a["exports"].items()}, color="#F5A524")
        else: st.caption("لا ملفات مصدّرة بعد.")
    st.subheader("نشاط آخر 14 يوم عمل")
    st.bar_chart(a["activity_days"], color="#16A6A1")
    ok = a["ai_jobs"].get("done", 0)
    tot = sum(a["ai_jobs"].values())
    st.markdown(f"**مهام الذكاء الاصطناعي الحقيقية:** {tot}" + (f" (نجح {ok}، فشل أو غير مكتمل: {tot - ok})" if tot else " (لم تُشغَّل بعد)"))
    st.markdown(f"**المصادر:** مقروءة {a['sources']['readable']} • غير مقروءة {a['sources']['unreadable']}")
