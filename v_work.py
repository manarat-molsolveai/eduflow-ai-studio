import json, copy
import streamlit as st
from core import svc, gen
from core import export as ex
from ui import *

KIND_AR = {"presentation": "عرض تقديمي", "document": "مستند", "worksheet": "ورقة عمل", "assessment": "اختبار"}
FMT_AR = {"pptx": "PPTX", "pdf": "PDF", "docx": "DOCX", "xlsx": "XLSX", "csv": "CSV", "html": "HTML"}


def workspace(uid):
    pid = st.session_state.get("pid")
    p = svc.get_project(uid, pid) if pid else None
    if not p:
        empty("المشروع غير موجود"); st.button("العودة للمشاريع", on_click=lambda: st.session_state.update(page="projects")); return
    st.markdown(f"## {esc(p['name'])} {status_badge(p['status'])}", unsafe_allow_html=True)
    st.caption(f"{type_label(p['ptype'])} • {p['stage']} {p['grade']} • {p['subject']} • أُنشئ {fmt_dt(p['created_at'])} • آخر تحديث {fmt_dt(p['updated_at'])}")
    tabs = st.tabs(["نظرة عامة", "المخرجات", "المصادر", "المهام", "السجل"])
    with tabs[0]:
        overview(uid, p)
    with tabs[1]:
        outputs(uid, p)
    with tabs[2]:
        sources(uid, p)
    with tabs[3]:
        tasks(uid, p)
    with tabs[4]:
        for a in svc.activity(uid, pid, 40):
            st.markdown(f"- `{fmt_dt(a['at'])}` **{a['action']}** {esc(a['detail'])}")
        if not svc.activity(uid, pid, 1):
            empty("لا يوجد نشاط بعد")


def overview(uid, p):
    with st.form(f"ov{p['id']}"):
        name = st.text_input("اسم المشروع", p["name"])
        desc = st.text_area("الوصف", p["description"])
        c1, c2 = st.columns(2)
        subject = c1.text_input("المادة", p["subject"])
        grade = c2.text_input("الصف", p["grade"])
        stages = gen.STAGES
        stage = c1.selectbox("المرحلة", stages, index=stages.index(p["stage"]) if p["stage"] in stages else 2)
        diffs = ["سهل", "متوسط", "صعب"]
        diff = c2.selectbox("الصعوبة", diffs, index=diffs.index(p["difficulty"]) if p["difficulty"] in diffs else 1)
        objs = st.text_area("الأهداف (هدف في كل سطر)", "\n".join(p["objectives"]))
        notes = st.text_area("ملاحظات", p["notes"])
        rating = st.slider("تقييمك للمشروع (0 = بلا تقييم)", 0, 5, p["rating"] or 0)
        if st.form_submit_button("حفظ التعديلات", type="primary"):
            if not name.strip():
                st.error("اسم المشروع مطلوب")
            else:
                svc.update_project(uid, p["id"], name=name.strip(), description=desc, subject=subject, grade=grade, stage=stage,
                                   difficulty=diff, objectives=[l.strip() for l in objs.splitlines() if l.strip()], notes=notes, rating=rating)
                st.success("تم الحفظ"); st.rerun()
    sts = list(svc.STATUS_AR)[:7]
    ns = st.selectbox("حالة المشروع", sts, index=sts.index(p["status"]) if p["status"] in sts else 0, format_func=svc.STATUS_AR.get, key=f"st{p['id']}")
    if ns != p["status"]:
        svc.update_project(uid, p["id"], status=ns); st.rerun()
    c1, c2, c3 = st.columns(3)
    if c1.button("نسخ المشروع كمشروع جديد", key="dup"):
        n = svc.duplicate_project(uid, p["id"]); go("project", pid=n)
    if c2.button("إنتاج مخرجات إضافية", key="more"):
        st.session_state["add_out"] = True
    if st.session_state.get("add_out"):
        add_output(uid, p)
    with c3:
        with st.popover("حذف المشروع"):
            st.warning("سيُحذف المشروع ومخرجاته وملفاته المصدّرة نهائيًا ولا يمكن التراجع.")
            if st.checkbox("أؤكد الحذف", key="delconf") and st.button("احذف نهائيًا", type="primary", key="delgo"):
                svc.delete_project(uid, p["id"]); go("projects")
    z = svc.zip_project(uid, p["id"])
    if z:
        st.download_button("تنزيل كل الملفات المصدّرة (ZIP)", z, f"{p['name']}.zip", "application/zip")


def add_output(uid, p):
    kinds = {"presentation": "عرض تقديمي", "worksheet": "ورقة عمل", "assessment": "اختبار", **{f"doc:{k}": v[0] for k, v in gen.DOC_TYPES.items()}}
    k = st.selectbox("المخرج", list(kinds), format_func=kinds.get, key="addk")
    n = st.slider("العدد (شرائح / أسئلة)", 3, 20, 8, key="addn")
    if st.button("أنشئ", type="primary", key="addgo"):
        kind, sub = (k.split(":")[0], k.split(":")[1]) if k.startswith("doc:") else (k, "")
        with st.spinner("جارٍ الإنتاج..."):
            oid, err = svc.produce(uid, p["id"], kind, sub, n)
        st.session_state.pop("add_out", None)
        (st.error(err) if err else st.success("تم الإنتاج")); st.rerun()


def outputs(uid, p):
    oid = st.session_state.get("oid")
    outs = svc.list_outputs(uid, p["id"])
    if oid and any(o["id"] == oid for o in outs):
        editor(uid, p, svc.get_output(uid, oid)); return
    if not outs:
        empty("لا توجد مخرجات بعد", "أنشئ مخرجات من تبويب «نظرة عامة» ثم «إنتاج مخرجات إضافية».")
    for o in outs:
        rv = svc.latest_review(uid, o["id"])
        c1, c2 = st.columns([4, 1])
        c1.markdown(f'<div class="ef-card"><b>{esc(o["title"] or o["kind"])}</b> {badge(KIND_AR.get(o["kind"], o["kind"]), "pur")} {status_badge(o["status"])}<br>'
                    f'<small>المولّد: {esc(o["generator"])} • الإصدار {o["version"]}' + (f' • الجودة {rv["score"]}/100' if rv else "") + "</small></div>", unsafe_allow_html=True)
        if o["status"] != "failed":
            if c2.button("فتح وتحرير", key=f"open{o['id']}"):
                st.session_state["oid"] = o["id"]; st.rerun()
        else:
            c2.button("حذف", key=f"fd{o['id']}", on_click=lambda i=o["id"]: svc.delete_output(uid, i))
    exps = svc.list_exports(uid, p["id"])
    if exps:
        st.subheader("الملفات المصدّرة")
        export_list(uid, exps)


def export_list(uid, exps):
    for f in exps:
        c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
        c1.markdown(f"**{esc(f['name'])}**<br><small>{esc(f['verified'])} • {f['size']//1024} KB • {fmt_dt(f['created_at'])}</small>", unsafe_allow_html=True)
        d = svc.get_export(uid, f["id"])
        c2.download_button("تنزيل", d["blob"], d["name"], ex.MIME.get(d["fmt"], "application/octet-stream"), key=f"dl{f['id']}")
        with c3.popover("إعادة تسمية"):
            nn = st.text_input("الاسم", f["name"], key=f"rn{f['id']}")
            if st.button("حفظ", key=f"rns{f['id']}"):
                svc.rename_export(uid, f["id"], nn); st.rerun()
        if c4.button("حذف", key=f"dx{f['id']}"):
            svc.delete_export(uid, f["id"]); st.rerun()


# ---------------- editor ----------------
def _wk(oid): return f"ed{oid}"


def _clear(oid):
    for k in [k for k in st.session_state if k.startswith(f"w{oid}_")]:
        del st.session_state[k]


def editor(uid, p, o):
    oid = o["id"]
    if st.button("→ العودة للمخرجات"):
        st.session_state.pop("oid", None); _clear(oid); st.session_state.pop(_wk(oid), None); st.rerun()
    st.markdown(f"### {esc(o['title'])} {status_badge(o['status'])}", unsafe_allow_html=True)
    if _wk(oid) not in st.session_state or st.session_state.get(_wk(oid) + "v") != o["version"]:
        st.session_state[_wk(oid)] = copy.deepcopy(o["content"]); st.session_state[_wk(oid) + "v"] = o["version"]; _clear(oid)
    c = st.session_state[_wk(oid)]
    t_edit, t_prev, t_q, t_ex, t_v = st.tabs(["تحرير", "معاينة", "مراجعة الجودة", "تصدير", "الإصدارات"])
    with t_edit:
        if o["kind"] == "presentation": edit_slides(uid, p, oid, c)
        elif o["kind"] == "document": edit_doc(oid, c)
        else: edit_questions(oid, c)
        if st.button("حفظ التعديلات", type="primary", key=f"save{oid}"):
            sync(oid, o["kind"], c)
            svc.save_output(uid, oid, c, title=c.get("title"))
            st.success("تم الحفظ وإنشاء إصدار جديد. أعد مراجعة الجودة قبل التصدير."); st.rerun()
    with t_prev:
        preview(o["kind"], c)
    with t_q:
        quality_tab(uid, o)
    with t_ex:
        export_tab(uid, p, o)
    with t_v:
        vs = svc.versions(uid, oid)
        st.caption(f"الإصدار الحالي: {o['version']}")
        if not vs: st.info("لا توجد إصدارات سابقة بعد.")
        for v in vs:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"v{v['version']} • {fmt_dt(v['created_at'])} • {esc(v['note'])}")
            if c2.button("استرجاع", key=f"rv{v['id']}"):
                svc.save_output(uid, oid, v["content"], note=f"استرجاع v{v['version']}"); st.rerun()


def sync(oid, kind, c):
    """Copy widget values into the working copy."""
    g = lambda k, d: st.session_state.get(f"w{oid}_{k}", d)
    c["title"] = g("title", c.get("title", ""))
    if kind == "presentation":
        for i, s in enumerate(c["slides"]):
            s["title"] = g(f"t{i}", s["title"]); s["layout"] = g(f"l{i}", s["layout"])
            s["bullets"] = [x.strip() for x in g(f"b{i}", "\n".join(s["bullets"])).splitlines() if x.strip()]
            s["notes"] = g(f"n{i}", s.get("notes", ""))
            im = g(f"im{i}", s.get("image_source_id"))
            if im: s["image_source_id"] = im
            else: s.pop("image_source_id", None)
    elif kind == "document":
        for i, s in enumerate(c["sections"]):
            s["heading"] = g(f"h{i}", s["heading"]); s["body"] = g(f"b{i}", s["body"])
    else:
        c["instructions"] = g("instr", c.get("instructions", ""))
        for i, q in enumerate(c["questions"]):
            q["type"] = g(f"ty{i}", q["type"]); q["text"] = g(f"q{i}", q["text"])
            q["options"] = [x.strip() for x in g(f"op{i}", "\n".join(q.get("options", []))).splitlines() if x.strip()]
            q["answer"] = g(f"an{i}", q.get("answer", "")); q["points"] = g(f"pt{i}", q.get("points", 1))
            q["skill"] = g(f"sk{i}", q.get("skill", "")); q["difficulty"] = g(f"df{i}", q.get("difficulty", "متوسط"))


def _move(oid, kind, c, key, i, d):
    sync(oid, kind, c)
    L = c[key]; j = i + d
    if 0 <= j < len(L):
        L[i], L[j] = L[j], L[i]
    _clear(oid); st.rerun()


def _del(oid, kind, c, key, i):
    sync(oid, kind, c); c[key].pop(i); _clear(oid); st.rerun()


def _add(oid, kind, c, key, item):
    sync(oid, kind, c); c[key].append(item); _clear(oid); st.rerun()


def edit_slides(uid, p, oid, c):
    st.text_input("عنوان العرض", c.get("title", ""), key=f"w{oid}_title")
    imgs = {s["id"]: s["title"] for s in svc.list_sources(uid, p["id"]) if s["kind"] == "image"}
    layouts = ["title", "bullets", "two_column", "closing"]
    LAY = {"title": "عنوان", "bullets": "نقاط", "two_column": "عمودان", "closing": "ختام"}
    for i, s in enumerate(c["slides"]):
        with st.expander(f"{i+1}. {s['title'][:50]}", expanded=i == 0):
            st.selectbox("التخطيط", layouts, index=layouts.index(s["layout"]) if s["layout"] in layouts else 1, format_func=LAY.get, key=f"w{oid}_l{i}")
            st.text_input("العنوان", s["title"], key=f"w{oid}_t{i}")
            st.text_area("النقاط (نقطة في كل سطر)", "\n".join(s["bullets"]), key=f"w{oid}_b{i}", height=140)
            st.text_area("ملاحظات المعلم", s.get("notes", ""), key=f"w{oid}_n{i}", height=70)
            opts = [None] + list(imgs)
            cur = s.get("image_source_id")
            st.selectbox("صورة (من الصور المرفوعة للمشروع)", opts, index=opts.index(cur) if cur in opts else 0,
                         format_func=lambda x: "بدون" if x is None else imgs.get(x, str(x)), key=f"w{oid}_im{i}")
            a, b, d = st.columns(3)
            if a.button("↑ أعلى", key=f"up{oid}{i}"): _move(oid, "presentation", c, "slides", i, -1)
            if b.button("↓ أسفل", key=f"dn{oid}{i}"): _move(oid, "presentation", c, "slides", i, 1)
            if d.button("حذف الشريحة", key=f"rm{oid}{i}"): _del(oid, "presentation", c, "slides", i)
    if st.button("+ إضافة شريحة", key=f"add{oid}"):
        _add(oid, "presentation", c, "slides", {"layout": "bullets", "title": "شريحة جديدة", "bullets": [], "notes": ""})


def edit_doc(oid, c):
    st.text_input("عنوان المستند", c.get("title", ""), key=f"w{oid}_title")
    for i, s in enumerate(c["sections"]):
        with st.expander(f"{i+1}. {s['heading']}", expanded=i == 0):
            st.text_input("عنوان القسم", s["heading"], key=f"w{oid}_h{i}")
            st.text_area("المحتوى", s["body"], key=f"w{oid}_b{i}", height=160)
            a, b, d = st.columns(3)
            if a.button("↑ أعلى", key=f"up{oid}{i}"): _move(oid, "document", c, "sections", i, -1)
            if b.button("↓ أسفل", key=f"dn{oid}{i}"): _move(oid, "document", c, "sections", i, 1)
            if d.button("حذف القسم", key=f"rm{oid}{i}"): _del(oid, "document", c, "sections", i)
    if st.button("+ إضافة قسم", key=f"add{oid}"):
        _add(oid, "document", c, "sections", {"heading": "قسم جديد", "body": ""})


def edit_questions(oid, c):
    st.text_input("العنوان", c.get("title", ""), key=f"w{oid}_title")
    st.text_area("التعليمات", c.get("instructions", ""), key=f"w{oid}_instr")
    types = ["mcq", "tf", "short", "fill", "essay"]
    TY = {"mcq": "اختيار من متعدد", "tf": "صح/خطأ", "short": "إجابة قصيرة", "fill": "أكمل الفراغ", "essay": "مقالي"}
    for i, q in enumerate(c["questions"]):
        with st.expander(f"{i+1}. {q['text'][:50]}", expanded=i == 0):
            st.selectbox("النوع", types, index=types.index(q["type"]) if q["type"] in types else 2, format_func=TY.get, key=f"w{oid}_ty{i}")
            st.text_area("نص السؤال", q["text"], key=f"w{oid}_q{i}")
            st.text_area("الخيارات (خيار في كل سطر)", "\n".join(q.get("options", [])), key=f"w{oid}_op{i}", height=80)
            st.text_input("الإجابة الصحيحة", q.get("answer", ""), key=f"w{oid}_an{i}")
            x, y, z = st.columns(3)
            x.number_input("الدرجة", 0.0, 100.0, float(q.get("points", 1)), key=f"w{oid}_pt{i}")
            y.text_input("المهارة", q.get("skill", ""), key=f"w{oid}_sk{i}")
            dfs = ["سهل", "متوسط", "صعب"]
            z.selectbox("الصعوبة", dfs, index=dfs.index(q.get("difficulty")) if q.get("difficulty") in dfs else 1, key=f"w{oid}_df{i}")
            a, b, d = st.columns(3)
            if a.button("↑ أعلى", key=f"up{oid}{i}"): _move(oid, "q", c, "questions", i, -1)
            if b.button("↓ أسفل", key=f"dn{oid}{i}"): _move(oid, "q", c, "questions", i, 1)
            if d.button("حذف السؤال", key=f"rm{oid}{i}"): _del(oid, "q", c, "questions", i)
    if st.button("+ إضافة سؤال", key=f"add{oid}"):
        _add(oid, "q", c, "questions", {"type": "short", "text": "سؤال جديد", "options": [], "answer": "", "points": 1, "skill": "", "difficulty": "متوسط"})


def preview(kind, c):
    if kind == "presentation":
        cols = st.columns(2)
        for i, s in enumerate(c["slides"]):
            cls = "title" if s["layout"] in ("title", "closing") else ""
            li = "".join(f"<li>{esc(b)}</li>" for b in s["bullets"][:7])
            cols[i % 2].markdown(f'<div class="ef-slide {cls}"><h4>{esc(s["title"])}</h4><ul>{li}</ul></div><br>', unsafe_allow_html=True)
        st.caption("معاينة تقريبية. الملف المصدّر هو المرجع النهائي للشكل.")
    elif kind == "document":
        st.markdown(f"## {esc(c.get('title',''))}", unsafe_allow_html=True)
        for s in c["sections"]:
            st.markdown(f"**{esc(s['heading'])}**"); st.text(s["body"])
    else:
        st.markdown(f"## {esc(c.get('title',''))}", unsafe_allow_html=True); st.write(c.get("instructions", ""))
        for i, q in enumerate(c["questions"], 1):
            st.markdown(f"**{i}. {esc(q['text'])}** ({q.get('points',1)})")
            for o in q.get("options", []): st.markdown(f"- {esc(o)}")


def quality_tab(uid, o):
    oid = o["id"]
    if st.button("تشغيل مراجعة الجودة الآن", key=f"rq{oid}", type="primary"):
        svc.run_review(uid, oid); st.rerun()
    r = svc.latest_review(uid, oid)
    if not r:
        empty("لم تُجرَ مراجعة بعد"); return
    stale = r.get("output_version") != o["version"]
    if stale: st.warning("هذه المراجعة لإصدار أقدم. أعد المراجعة.")
    (st.success if r["verdict"] == "approved" else st.warning)(f"النتيجة {r['score']}/100 — " + ("معتمد" if r["verdict"] == "approved" else "يحتاج مراجعة"))
    names = {"structure": "البنية", "completeness": "الاكتمال", "language": "اللغة", "audience": "ملاءمة الجمهور", "usability": "قابلية الاستخدام", "source_integrity": "سلامة المصادر"}
    for k, v in r["dims"].items():
        st.progress(int(v) / 100, text=f"{names[k]}: {v}/100 (الوزن {r['weights'][k]})")
    for e in r["errors"]: st.error(e)
    for w in r["warnings"]: st.warning(w)
    for s in r["suggestions"]: st.info(s)
    st.caption("لا تُقاس بالقواعد (تحتاج مراجعة بشرية أو AI): " + "، ".join(r["unjudged"]))
    with st.expander("قواعد التقييم المستخدمة"):
        for x in r["rules"]: st.markdown(f"- {x}")
        st.caption("الدرجة = متوسط مرجّح للأبعاد الستة. معتمد إذا لا أخطاء والدرجة 70 أو أعلى.")
    if r["verdict"] != "approved" and not o["quality_override"]:
        with st.expander("تجاوز بوابة الجودة (يُسجَّل في السجل)"):
            why = st.text_input("سبب التجاوز", key=f"why{oid}")
            if st.button("سجّل التجاوز", key=f"ov{oid}"):
                if svc.override_gate(uid, oid, why): st.rerun()
                else: st.error("اكتب سببًا واضحًا (5 أحرف على الأقل)")
    if o["quality_override"]:
        st.info("تم تجاوز البوابة. السبب: " + o["quality_override"])


def export_tab(uid, p, o):
    oid = o["id"]
    open_ = svc.gate_open(uid, oid)
    if not open_:
        st.warning("بوابة الجودة مغلقة. شغّل مراجعة الجودة وعالج الملاحظات، أو سجّل تجاوزًا مع السبب.")
    fmts = ex.FORMATS[o["kind"]]
    st.caption("الصيغ غير المدعومة لهذا المخرج غير معروضة. بعد التصدير يُعاد فتح الملف للتحقق من سلامته.")
    cols = st.columns(len(fmts))
    for col, f in zip(cols, fmts):
        if col.button(FMT_AR[f], key=f"ex{oid}{f}", disabled=not open_):
            with st.spinner("جارٍ التصدير والتحقق..."):
                fid, msg = svc.do_export(uid, oid, f)
            (st.success(msg) if fid else st.error(msg))
            if fid: st.rerun()
    exps = [e for e in svc.list_exports(uid, p["id"])]
    if exps:
        export_list(uid, exps)


def sources(uid, p):
    st.caption("مراجع المشروع. المحتوى المقروء هو ما يستند إليه الإنتاج.")
    ups = st.file_uploader("رفع ملفات", accept_multiple_files=True, key="wsup", type=["pdf", "docx", "pptx", "txt", "md", "csv", "xlsx", "png", "jpg", "jpeg", "webp"])
    known = {(s["filename"], s["size"]) for s in svc.list_sources(uid, p["id"])}
    for f in ups or []:
        d = f.getvalue()
        if (f.name, len(d)) in known: continue
        sid, ok, note = svc.add_source(uid, p["id"], f.name, "other", filename=f.name, data=d)
        (st.success if ok else st.warning)(f"{f.name}: {note or 'تمت القراءة'}")
        known.add((f.name, len(d)))
    with st.expander("إضافة نص أو رابط"):
        t = st.text_input("العنوان", key="wst")
        tx = st.text_area("نص", key="wstx")
        u = st.text_input("رابط (يُسجل فقط)", key="wsu")
        if st.button("إضافة", key="wsadd"):
            if tx.strip(): svc.add_source(uid, p["id"], t or "نص", "text", content=tx); st.rerun()
            elif u.startswith("http"): svc.add_source(uid, p["id"], t or u, "link", url=u); st.rerun()
            else: st.error("أدخل نصًا أو رابطًا صحيحًا")
    srcs = svc.list_sources(uid, p["id"])
    if not srcs: empty("لا توجد مصادر")
    for s in srcs:
        with st.expander(f"{s['title']} ({s['kind']}) v{s['version']}"):
            st.markdown((badge("نص مقروء") if s["readable"] else badge("غير مقروء", "warn")) + f" {esc(s['read_note'])} • {s['size']//1024} KB • أُضيف {fmt_dt(s['created_at'])}", unsafe_allow_html=True)
            if s["url"]: st.write(s["url"])
            if s["content"]: st.text(s["content"][:1500] + ("..." if len(s["content"]) > 1500 else ""))
            full = svc.get_source(uid, s["id"])
            if s["kind"] == "image" and full["blob"]:
                try: st.image(full["blob"], width=240)
                except Exception: st.caption("تعذر عرض الصورة")
            if full["blob"]: st.download_button("تنزيل الأصل", full["blob"], s["filename"], key=f"sd{s['id']}")
            if st.button("حذف", key=f"sdel{s['id']}"): svc.delete_source(uid, s["id"]); st.rerun()


def tasks(uid, p):
    with st.form("newtask", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        t = c1.text_input("مهمة جديدة")
        pr = c2.selectbox("الأولوية", ["low", "medium", "high"], index=1, format_func={"low": "منخفضة", "medium": "متوسطة", "high": "عالية"}.get)
        due = c3.date_input("الاستحقاق", value=None)
        if st.form_submit_button("إضافة") and t.strip():
            svc.add_task(uid, t, p["id"], pr, str(due) if due else ""); st.rerun()
    ts = svc.list_tasks(uid, p["id"])
    if not ts: empty("لا توجد مهام")
    for t in ts:
        c1, c2, c3 = st.columns([5, 2, 1])
        c1.markdown(("~~" + t["title"] + "~~") if t["status"] == "done" else t["title"])
        c1.caption(f"{t['priority']} {t['due']}")
        ns = c2.selectbox("الحالة", ["todo", "doing", "done"], index=["todo", "doing", "done"].index(t["status"]), format_func={"todo": "للتنفيذ", "doing": "جارٍ", "done": "تم"}.get, key=f"ts{t['id']}", label_visibility="collapsed")
        if ns != t["status"]: svc.set_task(uid, t["id"], ns); st.rerun()
        if c3.button("حذف", key=f"td{t['id']}"): svc.delete_task(uid, t["id"]); st.rerun()
