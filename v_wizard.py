import streamlit as st
from core import svc, gen, ai, templates
from ui import *

STEPS = ["نوع المشروع", "الجمهور", "المحتوى", "الأهداف", "المخرجات", "التصميم", "خطة الإنتاج"]
BLOOM = [("تذكر", "أن يتعرف الطالب على {t}"), ("فهم", "أن يشرح الطالب {t} بأسلوبه"), ("تطبيق", "أن يطبق الطالب ما تعلمه عن {t} في مثال جديد"),
         ("تحليل", "أن يقارن الطالب بين عناصر {t}"), ("تقويم", "أن يقيّم الطالب فهمه لـ {t}")]


def render(uid):
    hero("مشروع جديد", "معالج من 7 خطوات. يُحفظ المشروع كمسودة بعد الخطوة الأولى ويمكنك العودة إليه في أي وقت.")
    pid = st.session_state.get("wz_pid")
    step = st.session_state.get("wz_step", 0)
    st.progress((step + 1) / len(STEPS), text=f"الخطوة {step + 1} من {len(STEPS)}: {STEPS[step]}")
    p = svc.get_project(uid, pid) if pid else None
    if pid and not p:
        st.session_state.pop("wz_pid", None); st.rerun()

    def nav(can_next=True, last=False):
        c1, c2 = st.columns(2)
        if step > 0 and c1.button("→ السابق", key=f"prev{step}"):
            st.session_state["wz_step"] = step - 1; st.rerun()
        return c2.button("ابدأ الإنتاج ✓" if last else "التالي ←", type="primary", key=f"next{step}", disabled=not can_next)

    if step == 0:
        name = st.text_input("اسم المشروع *", value=p["name"] if p else "", placeholder="مثال: دورة الماء - علوم الصف الخامس")
        keys = list(gen.PROJECT_TYPES)
        pt = st.selectbox("نوع المشروع", keys, index=keys.index(p["ptype"]) if p else 0, format_func=gen.PROJECT_TYPES.get)
        desc = st.text_area("وصف مختصر (اختياري)", value=p["description"] if p else "")
        tpl = ""
        if not p:
            tpl = st.selectbox("ابدأ من قالب (اختياري)", list(templates.TEMPLATES), format_func=lambda k: templates.TEMPLATES[k]["label"] + (" - " + templates.TEMPLATES[k]["desc"] if k else ""))
            st.caption("القالب يملأ الأهداف وخطة المخرجات مسبقًا فقط، ويمكنك تعديلها بالكامل في الخطوات التالية. لا يضيف محتوى من عنده.")
        if nav(bool(name.strip())):
            if p:
                svc.update_project(uid, pid, name=name.strip(), ptype=pt, description=desc)
            else:
                data = {"name": name, "ptype": pt, "description": desc, "settings": {"language": "العربية"}}
                data.update({k: v for k, v in templates.apply(tpl, name.strip()).items() if k != "ptype"})
                st.session_state["wz_pid"] = svc.create_project(uid, data)
            st.session_state["wz_step"] = 1; st.rerun()
        return
    if not p:
        st.session_state["wz_step"] = 0; st.rerun()
    if step == 1:
        stage = st.selectbox("المرحلة / الجمهور", gen.STAGES, index=gen.STAGES.index(p["stage"]) if p["stage"] in gen.STAGES else 2)
        grade = st.text_input("الصف", value=p["grade"], placeholder="مثال: الخامس")
        subject = st.text_input("المادة", value=p["subject"], placeholder="مثال: العلوم")
        diffs = ["سهل", "متوسط", "صعب"]
        diff = st.select_slider("مستوى الصعوبة", diffs, value=p["difficulty"] if p["difficulty"] in diffs else "متوسط")
        aud = st.text_area("وصف الجمهور (اختياري)", value=p["audience"], placeholder="مثال: طلاب يحتاجون دعمًا بصريًا")
        lang = st.radio("لغة المحتوى", ["العربية", "English"], horizontal=True, index=0 if p["settings"].get("language", "العربية") == "العربية" else 1)
        if nav():
            s = p["settings"]; s["language"] = lang
            svc.update_project(uid, pid, stage=stage, grade=grade, subject=subject, difficulty=diff, audience=aud, settings=s)
            st.session_state["wz_step"] = 2; st.rerun()
    elif step == 2:
        st.caption("هذه الخطوة اختيارية. أضف مراجعك إن أردت، أو تابع بدونها. المحتوى المستخرج فقط هو ما يُستخدم من المصادر.")
        t1, t2, t3 = st.tabs(["نص / ملاحظات", "رفع ملفات", "رابط"])
        with t1:
            title = st.text_input("عنوان المصدر", key="wz_t_title")
            txt = st.text_area("الصق النص هنا", height=180, key="wz_t_text")
            if st.button("إضافة النص", key="wz_add_t", disabled=not txt.strip()):
                svc.add_source(uid, pid, title or "نص مدخل", "text", content=txt); st.rerun()
        with t2:
            ups = st.file_uploader("PDF, DOCX, PPTX, TXT, CSV, XLSX, صور", accept_multiple_files=True,
                                   type=["pdf", "docx", "pptx", "txt", "md", "csv", "xlsx", "png", "jpg", "jpeg", "webp"], key="wz_files")
            known = {(s["filename"], s["size"]) for s in svc.list_sources(uid, pid)}
            for f in ups or []:
                data = f.getvalue()
                if (f.name, len(data)) in known:
                    continue
                sid, ok, note = svc.add_source(uid, pid, f.name, "other", filename=f.name, data=data)
                (st.success if ok else st.warning)(f"{f.name}: " + ("تمت قراءة النص. " if ok else "حُفظ الملف لكن لم تتم قراءته. ") + note)
                known.add((f.name, len(data)))
        with t3:
            u = st.text_input("الرابط (يُسجل كمرجع فقط، ولا يُجلب محتواه)", key="wz_url")
            ut = st.text_input("عنوان الرابط", key="wz_url_t")
            if st.button("إضافة الرابط", disabled=not u.startswith("http"), key="wz_add_u"):
                svc.add_source(uid, pid, ut or u, "link", url=u); st.rerun()
        srcs = svc.list_sources(uid, pid)
        for s in srcs:
            st.markdown(f"- **{esc(s['title'])}** `{s['kind']}` " + (badge("نص مقروء") if s["readable"] else badge("غير مقروء", "warn")) + f" {esc(s['read_note'])}", unsafe_allow_html=True)
        if not srcs:
            st.info("لم تضف مصادر بعد، وهذا مسموح. بدون مصادر: إن كان الذكاء الاصطناعي متصلًا يُنتج المحتوى من موضوع المشروع وأهدافه (ويحتاج مراجعتك)، وإلا يُنتج هيكلًا بعلامات [اكتب هنا].")
            if st.button("متابعة بدون مصادر ←", type="primary", key="wz_skip_src"):
                st.session_state["wz_step"] = 3; st.rerun()
            nav(False)
        elif nav():
            st.session_state["wz_step"] = 3; st.rerun()
    elif step == 3:
        objs = p["objectives"]
        topic = p["name"]
        st.caption("الأهداف قابلة للتعديل بالكامل.")
        if st.button("اقتراح أهداف من قوالب بلوم (من اسم الموضوع)"):
            objs = [t.format(t=topic) for _, t in BLOOM]
            svc.update_project(uid, pid, objectives=objs); st.rerun()
        if ai.active(uid):
            st.caption("مزود ذكاء اصطناعي مُختبر متصل. أهداف AI ستضاف في الإصدار القادم.")
        text = st.text_area("الأهداف (هدف في كل سطر)", value="\n".join(objs), height=200)
        prior = st.text_input("المعرفة السابقة", value=p["settings"].get("prior", ""))
        crit = st.text_input("معايير التقويم", value=p["settings"].get("criteria", ""))
        if nav():
            s = p["settings"]; s["prior"], s["criteria"] = prior, crit
            svc.update_project(uid, pid, objectives=[l.strip() for l in text.splitlines() if l.strip()], settings=s)
            st.session_state["wz_step"] = 4; st.rerun()
    elif step == 4:
        plan = p["settings"].get("plan", [])
        cur = {(x["kind"], x.get("subtype", "")) for x in plan}
        st.caption("اختر مخرجًا واحدًا أو أكثر.")
        sel = []
        c1, c2 = st.columns(2)
        if c1.checkbox("عرض تقديمي", value=("presentation", "") in cur): sel.append({"kind": "presentation", "n": p["settings"].get("n_slides", 8)})
        if c1.checkbox("ورقة عمل", value=("worksheet", "") in cur): sel.append({"kind": "worksheet", "n": 8})
        if c1.checkbox("اختبار", value=("assessment", "") in cur): sel.append({"kind": "assessment", "n": 8})
        for k, (lab, _) in gen.DOC_TYPES.items():
            if c2.checkbox(lab, value=("document", k) in cur, key=f"doc_{k}"): sel.append({"kind": "document", "subtype": k})
        if nav(bool(sel)):
            s = p["settings"]; s["plan"] = sel
            svc.update_project(uid, pid, settings=s)
            st.session_state["wz_step"] = 5; st.rerun()
    elif step == 5:
        s = p["settings"]
        st.caption("الخيارات المعروضة هنا فقط هي التي تؤثر فعلًا على الناتج في هذا الإصدار.")
        n = st.slider("عدد الشرائح (للعرض)", 4, 20, s.get("n_slides", 8))
        dens = st.radio("كثافة المحتوى في الشرائح", ["خفيفة", "متوسطة", "كثيفة"], horizontal=True, index=["خفيفة", "متوسطة", "كثيفة"].index(s.get("density", "متوسطة")))
        brand = st.text_input("نص العلامة التجارية في تذييل الشرائح (اختياري)", value=s.get("brand", ""))
        if nav():
            s["n_slides"], s["density"], s["brand"] = n, dens, brand
            for x in s.get("plan", []):
                if x["kind"] == "presentation": x["n"] = n
            svc.update_project(uid, pid, settings=s, status="planning")
            st.session_state["wz_step"] = 6; st.rerun()
    elif step == 6:
        s = p["settings"]
        st.subheader("خطة الإنتاج")
        mode = ai.active(uid)
        st.markdown("**طريقة التوليد:** " + (f"ذكاء اصطناعي ({ai.PROVIDERS[mode[0]]['label']} / {mode[1]})" if mode else
                    "قواعد محلية (بدون ذكاء اصطناعي): يُنظّم نصوصك وأهدافك فقط ولا يؤلف معلومات. اربط مزودًا من الإعدادات للتوليد الذكي."))
        plan = s.get("plan", [])
        keep = []
        for i, x in enumerate(plan):
            lab = gen.DOC_TYPES[x["subtype"]][0] if x["kind"] == "document" else gen.OUTPUT_KINDS[x["kind"]]
            if st.checkbox(lab, value=True, key=f"plan_{i}"): keep.append(x)
        st.caption(f"المصادر المقروءة: {len([x for x in svc.list_sources(uid, pid) if x['readable']])} • الأهداف: {len(p['objectives'])}")
        if nav(bool(keep), last=True):
            bar = st.progress(0.0, text="بدء الإنتاج")
            res = svc.run_production(uid, pid, keep, progress=lambda f, m: bar.progress(f, text=m))
            for kind, oid, err in res:
                if err: st.error(f"{kind}: {err}")
            st.session_state.pop("wz_pid", None); st.session_state["wz_step"] = 0
            go("project", pid=pid)
