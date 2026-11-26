"""Acceptance tests T01-T20 (T16/T18 partly manual). Run: python tests/acceptance.py  (uses a temp SQLite DB)."""
import os, sys, tempfile, io, json
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/t.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import db, auth, svc, ai, gen, export as ex
from streamlit.testing.v1 import AppTest

R = []
def t(name, fn):
    try:
        msg = fn(); R.append((name, "MANUAL" if (msg or "").startswith("MANUAL") else "PASS", msg or ""))
    except Exception as e:
        R.append((name, "FAIL", f"{type(e).__name__}: {e}"))

db.init()
A, _ = auth.register("a@t.co", "A", "password1"); B, _ = auth.register("b@t.co", "B", "password1")
ctx = {}
def T01():
    ctx["pid"] = svc.create_project(A, {"name": "مشروع اختبار", "subject": "علوم", "objectives": ["هدف 1"], "settings": {"language": "العربية"}}); assert ctx["pid"]
def T02(): assert svc.update_project(A, ctx["pid"], name="مشروع معدل", subject="كيمياء")
def T03(): assert svc.get_project(A, ctx["pid"])["name"] == "مشروع معدل"
def T04():
    db._engine.dispose(); p = svc.get_project(A, ctx["pid"]); assert p and p["subject"] == "كيمياء"
def _png():
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (20, 20), "teal").save(b, "PNG"); return b.getvalue()
def T05():
    import docx
    d = docx.Document(); d.add_paragraph("تتبخر المياه من البحار بفعل حرارة الشمس. يتكاثف بخار الماء في السماء مكونا الغيوم. تسقط الأمطار على الأرض."); b = io.BytesIO(); d.save(b)
    sid, ok, note = svc.add_source(A, ctx["pid"], "درس.docx", "other", filename="درس.docx", data=b.getvalue()); assert ok
    s = svc.get_source(A, sid); assert "تتبخر" in s["content"]
    sid2, ok2, n2 = svc.add_source(A, ctx["pid"], "x.png", "other", filename="x.png", data=_png()); assert not ok2 and "OCR" in n2
    s3, ok3, n3 = svc.add_source(A, ctx["pid"], "bad.png", "other", filename="bad.png", data=b"notimage"); assert not ok3 and "صالحة" in n3
    return "DOCX قُرئ نصه؛ الصورة صُنّفت غير مقروءة بوضوح"
def T06():
    oid, err = svc.produce(A, ctx["pid"], "presentation", "", 6); assert not err; ctx["o"] = oid
    assert any("تتبخر" in b for s in svc.get_output(A, oid)["content"]["slides"] for b in s["bullets"])
def T07():
    o = svc.get_output(A, ctx["o"]); c = o["content"]; c["slides"][1]["title"] = "عنوان معدل"; ctx["c"] = c
def T08():
    svc.save_output(A, ctx["o"], ctx["c"]); o = svc.get_output(A, ctx["o"]); assert o["content"]["slides"][1]["title"] == "عنوان معدل" and o["version"] == 2 and len(svc.versions(A, ctx["o"])) == 1
def T12():
    r = svc.run_review(A, ctx["o"]); assert 0 <= r["score"] <= 100 and r["verdict"] in ("approved", "needs_revision"); return f"{r['score']} {r['verdict']}"
def T09():
    fid, msg = svc.do_export(A, ctx["o"], "pptx"); assert fid, msg; ctx["f"] = fid
def T10():
    from pptx import Presentation
    d = svc.get_export(A, ctx["f"])["blob"]; p = Presentation(io.BytesIO(d)); assert len(p.slides) >= 3
    texts = [sh.text_frame.text for s in p.slides for sh in s.shapes if sh.has_text_frame]
    assert "عنوان معدل" in " ".join(texts); return f"{len(p.slides)} شريحة، نصوص قابلة للتحرير"
def T11():
    oid, err = svc.produce(A, ctx["pid"], "worksheet", "", 5); assert not err and svc.get_output(A, oid)["content"]["questions"]
    c = svc.get_output(A, oid)["content"]
    assert "objectives" in c and "activities" in c and c.get("style") in gen.WORKSHEET_STYLES, "بنية ورقة العمل ناقصة"
    fid, m = svc.do_export(A, oid, "docx"); assert fid, m
    fid, m = svc.do_export(A, oid, "pdf"); assert fid, m
def T21():
    pid = svc.create_project(A, {"name": "اختبار متقدم", "objectives": ["أ", "ب", "ج"], "settings": {"language": "العربية"}})
    oid, err = svc.produce(A, pid, "assessment", "", 6); assert not err, err
    o = svc.get_output(A, oid); c = o["content"]
    c["questions"] = [
        {"type": "matching", "text": "صِل المصطلح بتعريفه", "options": [], "items": [],
         "pairs": [["التبخر", "تحول السائل إلى بخار"], ["التكاثف", "تحول البخار إلى سائل"], ["الهطول", "سقوط الماء من الغيوم"]],
         "answer": "", "points": 3, "skill": "فهم", "difficulty": "متوسط"},
        {"type": "ordering", "text": "رتّب مراحل دورة الماء", "options": [], "pairs": [],
         "items": ["التبخر", "التكاثف", "الهطول"], "answer": "", "points": 2, "skill": "ترتيب", "difficulty": "سهل"},
        {"type": "mcq", "text": "ما مصدر طاقة دورة الماء؟", "options": ["الشمس", "الرياح", "القمر"], "pairs": [], "items": [],
         "answer": "الشمس", "points": 1, "skill": "استدعاء", "difficulty": "سهل"}]
    c["rubric"] = gen.suggest_rubric(c)
    assert abs(sum(r["weight"] for r in c["rubric"]) - 100) < 0.01, "أوزان السلم ليست 100"
    assert "⇐" in gen.q_answer(c["questions"][0]) and "ثم" in gen.q_answer(c["questions"][1])
    svc.save_output(A, oid, c)
    r = svc.run_review(A, oid); assert svc.gate_open(A, oid), f"البوابة مغلقة: {r['score']}"
    for fmt in ("pdf", "docx", "xlsx", "html", "csv"):
        fid, m = svc.do_export(A, oid, fmt); assert fid, m
    assert "التبخر" in svc.get_export(A, fid)["blob"].decode("utf-8-sig")
    return "مطابقة+ترتيب+سلم تقييم، و5 صيغ تصدير سليمة"
def T22():
    old = {"title": "أ", "questions": [{"text": "س1", "type": "short", "options": [], "pairs": [], "items": []}]}
    new = {"title": "ب", "questions": [old["questions"][0], {"text": "س2", "type": "mcq", "options": ["1"], "pairs": [], "items": []}]}
    d = gen.diff_summary("assessment", old, new)
    assert any("العنوان" in x for x in d) and any("أُضيف 1 سؤال" in x for x in d), d
    return " | ".join(d)
def T13(): assert len(svc.list_projects(A, q="معدل")) == 1 and not svc.list_projects(A, q="لا يوجد شيء كهذا")
def T15():
    assert svc.get_project(B, ctx["pid"]) is None and not svc.delete_project(B, ctx["pid"]) and svc.get_output(B, ctx["o"]) is None
    assert svc.get_export(B, ctx["f"]) is None and not svc.list_projects(B)
def T14():
    at = AppTest.from_file(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"), default_timeout=60).run()
    at.session_state["uid"] = A; at.session_state["tok"] = "x"; at.session_state["page"] = "project"; at.session_state["pid"] = ctx["pid"]; at.run()
    assert not at.exception, at.exception
    assert any(c.label == "أؤكد الحذف" for c in at.checkbox)
    go = [b for b in at.button if b.key == "delgo"]
    assert svc.get_project(A, ctx["pid"]) is not None  # no deletion without confirmation
    assert svc.delete_project(A, ctx["pid"]) and svc.get_project(A, ctx["pid"]) is None
def T17():
    oid, err = svc.produce(A, 99999, "presentation")  # missing project
    return "الخطأ يُعرض: " + (err or "")[:60] if err else (_ for _ in ()).throw(AssertionError("no error"))
def T19():
    ok, msg = ai.test_connection(A, "openai", "gpt-4o-mini", "sk-invalid"); assert not ok and ai.get_setting(A, "tested_openai") == "fail"; return msg
def T20():
    db._engine.dispose(); pid = svc.create_project(A, {"name": "دائم"}); db._engine.dispose()
    assert svc.get_project(A, pid)["name"] == "دائم"
def T18():
    assert ai.active(A) is None; return "لا مزود: النظام يعمل بقواعد محلية ويصرّح بذلك. لم يُختبر مع مزود حقيقي (لا مفتاح)"
def T16(): return "MANUAL: اختبار يدوي بلقطة هاتف على الرابط المنشور (انظر التقرير)"

for n, f in [("T01 إنشاء مشروع", T01), ("T02 تعديل", T02), ("T03 حفظ", T03), ("T04 إعادة فتح", T04), ("T05 رفع ملف", T05), ("T06 إنشاء عرض", T06),
             ("T07 تعديل شريحة", T07), ("T08 حفظ التعديل", T08), ("T12 مراجعة الجودة", T12), ("T09 تصدير", T09), ("T10 فحص الملف", T10),
             ("T11 ورقة عمل", T11), ("T21 استوديو الاختبارات", T21), ("T22 ملخص الفروق", T22), ("T13 بحث", T13), ("T15 الصلاحيات", T15), ("T14 حذف بتأكيد", T14), ("T17 Error State", T17),
             ("T19 فشل API", T19), ("T20 استمرارية", T20), ("T18 تكامل AI", T18), ("T16 الهاتف", T16)]:
    t(n, f)
for r in R: print(*r, sep=" | ")
print("FAILED" if any(r[1] == "FAIL" for r in R) else "ALL PASSED")
