"""Content generation. Two honest modes:
 - AI mode: a tested provider writes structured JSON (validated, retried, logged).
 - Local mode: deterministic structuring of the user's OWN text and wizard answers. No AI, no invented facts.
Placeholders are marked with PH so the quality review can flag unfinished parts."""
import re, json
from . import ai

PH = "[اكتب هنا]"

PROJECT_TYPES = {
    "lesson": "درس", "presentation": "عرض تقديمي", "video": "فيديو", "broadcast": "إذاعة مدرسية",
    "workshop": "ورشة", "program": "برنامج تعليمي", "assessment": "اختبار", "worksheet": "ورقة عمل",
    "research": "بحث إجرائي", "report": "تقرير مدرسي", "portfolio": "ملف إنجاز", "game": "لعبة",
    "package": "حقيبة تعليمية متكاملة", "custom": "مشروع مخصص"}
STAGES = ["الطفولة المبكرة", "رياض الأطفال", "المرحلة الابتدائية", "المرحلة المتوسطة", "المرحلة الثانوية",
          "الجامعة", "معلمون", "مشرفون", "قيادة مدرسية", "جمهور عام"]
OUTPUT_KINDS = {"presentation": "عرض تقديمي (PPTX/PDF)", "document": "مستند (DOCX/PDF)",
                "worksheet": "ورقة عمل (DOCX/PDF)", "assessment": "اختبار (DOCX/PDF/XLSX)"}
DOC_TYPES = {
    "lesson_plan": ("خطة درس", ["معلومات الدرس", "الأهداف التعليمية", "المعرفة السابقة", "التمهيد", "عرض الدرس والأنشطة", "التقويم", "الواجب والإثراء"]),
    "teacher_guide": ("دليل المعلم", ["نظرة عامة", "الأهداف", "المواد المطلوبة", "خطوات التنفيذ", "أسئلة نقاش", "نصائح وتكييف"]),
    "workshop_guide": ("دليل ورشة", ["عنوان الورشة والفئة", "الأهداف", "الجدول الزمني", "الأنشطة", "التقويم", "المتطلبات"]),
    "report": ("تقرير", ["المقدمة", "الأهداف", "التنفيذ", "النتائج", "التوصيات"]),
    "action_research": ("بحث إجرائي", ["عنوان البحث", "مشكلة البحث", "أسئلة البحث", "الإجراءات", "الأدوات", "النتائج", "التوصيات"]),
    "activity_plan": ("خطة نشاط", ["اسم النشاط", "الأهداف", "الفئة المستهدفة", "الإجراءات", "الموارد", "التقويم"]),
    "weekly_plan": ("خطة أسبوعية", ["الأهداف الأسبوعية", "الجدول", "الأنشطة", "التقويم"]),
    "remedial_plan": ("خطة علاجية", ["تحديد المشكلة", "الأهداف", "الإجراءات", "المتابعة"]),
    "enrichment_plan": ("خطة إثرائية", ["الفئة", "الأهداف", "الأنشطة", "المتابعة"]),
    "portfolio": ("ملف إنجاز", ["نبذة", "الإنجازات", "الشواهد", "التقويم الذاتي"]),
}


def sentences(text):
    text = re.sub(r"\s+", " ", text or "")
    parts = re.split(r"(?<=[\.\!\?؟\u061F])\s+|\n", text)
    return [p.strip() for p in parts if len(p.strip()) > 12]


def source_text(sources, limit=14000):
    out, n = [], 0
    for s in sources:
        if not s["content"]:
            continue
        chunk = f"[مصدر #{s['id']}: {s['title']}]\n{s['content']}\n"
        out.append(chunk[: max(0, limit - n)])
        n += len(out[-1])
        if n >= limit:
            break
    return "\n".join(out)


# ---------------- validators ----------------
def validate_slides(d):
    if not isinstance(d, dict) or not isinstance(d.get("slides"), list) or not d["slides"]:
        raise ValueError("slides missing")
    for s in d["slides"]:
        if not isinstance(s.get("title"), str) or not s["title"].strip():
            raise ValueError("slide without title")
        s["bullets"] = [str(b) for b in (s.get("bullets") or [])]
        s.setdefault("notes", "")
        s.setdefault("layout", "bullets")
    d.setdefault("title", d["slides"][0]["title"])


def validate_doc(d):
    if not isinstance(d, dict) or not isinstance(d.get("sections"), list) or not d["sections"]:
        raise ValueError("sections missing")
    for s in d["sections"]:
        if not s.get("heading"):
            raise ValueError("section without heading")
        s["body"] = str(s.get("body", ""))


def validate_questions(d):
    if not isinstance(d, dict) or not isinstance(d.get("questions"), list) or not d["questions"]:
        raise ValueError("questions missing")
    for q in d["questions"]:
        if not q.get("text"):
            raise ValueError("question without text")
        q.setdefault("type", "short")
        q.setdefault("options", [])
        q.setdefault("answer", "")
        q.setdefault("points", 1)
        q.setdefault("skill", "")
        q.setdefault("difficulty", "متوسط")


SYS = ("أنت مصمم تعليمي محترف. أخرج JSON صالحًا فقط بلا شرح. اعتمد على نص المصادر المقدم فقط للمعلومات الواقعية، "
       "ولا تخترع حقائق أو أرقامًا أو روابط. إن نقصت المعلومات فاترك الحقل فارغًا. اكتب بلغة المشروع المطلوبة.")


def _ctx(p, sources):
    return (f"اسم المشروع: {p['name']}\nالنوع: {PROJECT_TYPES.get(p['ptype'], p['ptype'])}\nالمرحلة: {p['stage']} {p['grade']}\n"
            f"المادة: {p['subject']}\nالصعوبة: {p['difficulty']}\nالجمهور: {p['audience']}\n"
            f"الأهداف: {json.dumps(p['objectives'], ensure_ascii=False)}\nاللغة: {p['settings'].get('language', 'العربية')}\n"
            f"المصادر:\n{source_text(sources) or '(لا توجد مصادر: اعتمد على موضوع المشروع وأهدافه ومعرفتك العامة المؤكدة فقط، وبسّط ولا تذكر أرقامًا أو اقتباسات أو روابط غير مؤكدة)'}")


# ---------------- presentations ----------------
def make_presentation(uid, p, sources, n_slides=8):
    objs = p["objectives"]
    if ai.active(uid):
        dens = p["settings"].get("density", "متوسطة")
        prompt = (_ctx(p, sources) + f"\n\nأنشئ عرضًا من {n_slides} شرائح تقريبًا بالشكل: "
                  '{"title":"","slides":[{"layout":"title|bullets|two_column|closing","title":"","bullets":["..."],"notes":"ملاحظات المعلم"}]} '
                  f"كثافة المحتوى المطلوبة: {dens}. بحد أقصى 6 نقاط للشريحة، كل نقطة قصيرة ومناسبة للمرحلة.")
        data, prov, model = ai.generate_json(uid, p["id"], "presentation", SYS, prompt, validate_slides)
        return data, f"ai:{prov}:{model}"
    return local_presentation(p, sources, n_slides), "local-rules"


def local_presentation(p, sources, n_slides=8):
    slides = [{"layout": "title", "title": p["name"],
               "bullets": [x for x in [p["subject"], f"{p['stage']} {p['grade']}".strip()] if x], "notes": ""}]
    if objs := [o for o in p["objectives"] if o.strip()]:
        slides.append({"layout": "bullets", "title": "أهداف الدرس", "bullets": objs[:6], "notes": ""})
    sents = []
    for s in sources:
        sents += sentences(s["content"])
    body_slots = max(1, n_slides - len(slides) - 1)
    if sents:
        dens = {"خفيفة": 2, "متوسطة": 4, "كثيفة": 6}.get(p["settings"].get("density", "متوسطة"), 4)
        per = dens
        chunks = [sents[i:i + per] for i in range(0, len(sents), per)][:body_slots]
        for i, ch in enumerate(chunks, 1):
            slides.append({"layout": "bullets", "title": f"المحور {i}", "bullets": [c[:220] for c in ch],
                           "notes": "هذه الشريحة مبنية من نص مصدرك مباشرة. عدّل العنوان والصياغة."})
    else:
        for i in range(1, body_slots + 1):
            slides.append({"layout": "bullets", "title": f"المحور {i}: {PH}", "bullets": [PH], "notes": ""})
    slides.append({"layout": "closing", "title": "شكرًا لكم", "bullets": ["أسئلة ومناقشة"], "notes": ""})
    return {"title": p["name"], "slides": slides}


# ---------------- documents ----------------
def make_document(uid, p, sources, doc_type):
    label, heads = DOC_TYPES[doc_type]
    if ai.active(uid):
        prompt = (_ctx(p, sources) + f"\n\nأنشئ مستند «{label}» بالأقسام التالية بالترتيب: {heads}. "
                  'الشكل: {"title":"","sections":[{"heading":"","body":"نص أو نقاط مفصولة بسطر جديد"}]}')
        data, prov, model = ai.generate_json(uid, p["id"], "document", SYS, prompt, validate_doc)
        return data, f"ai:{prov}:{model}"
    return local_document(p, sources, doc_type), "local-rules"


def local_document(p, sources, doc_type):
    label, heads = DOC_TYPES[doc_type]
    objs = [o for o in p["objectives"] if o.strip()]
    sents = []
    for s in sources:
        sents += sentences(s["content"])
    secs = []
    for h in heads:
        body = PH
        if "معلومات" in h or "عنوان" in h or "نظرة" in h or "نبذة" in h or "المقدمة" in h:
            body = f"المادة: {p['subject'] or '-'}\nالمرحلة: {p['stage']} {p['grade']}\nالجمهور: {p['audience'] or '-'}\nالمستوى: {p['difficulty']}"
            if p["description"]:
                body += f"\nالوصف: {p['description']}"
        elif "الأهداف" in h or "هدف" in h:
            body = "\n".join(f"- {o}" for o in objs) or PH
        elif ("الأنشطة" in h or "عرض" in h or "الإجراءات" in h or "التنفيذ" in h) and sents:
            body = "من مصدرك:\n" + "\n".join(f"- {x[:200]}" for x in sents[:6]) + "\n\n" + PH
        secs.append({"heading": h, "body": body})
    return {"title": f"{label}: {p['name']}", "sections": secs}


# ---------------- worksheets / assessments ----------------
def make_questions(uid, p, sources, kind, n=8):
    if ai.active(uid):
        prompt = (_ctx(p, sources) + f"\n\nأنشئ {n} أسئلة متنوعة. الشكل: "
                  '{"title":"","instructions":"","questions":[{"type":"mcq|tf|short|fill|essay","text":"","options":["..."],'
                  '"answer":"الإجابة الصحيحة","points":1,"skill":"","difficulty":"سهل|متوسط|صعب"}]} '
                  "الأسئلة مبنية على المصادر فقط.")
        data, prov, model = ai.generate_json(uid, p["id"], kind, SYS, prompt, validate_questions)
        return data, f"ai:{prov}:{model}"
    return local_questions(p, sources, kind, n), "local-rules"


def local_questions(p, sources, kind, n=8):
    sents = []
    for s in sources:
        sents += sentences(s["content"])
    qs = []
    for sent in sents:
        words = [w for w in re.findall(r"[\w\u0600-\u06FF]{4,}", sent)]
        if len(words) < 5:
            continue
        key = max(words[1:], key=len)
        qs.append({"type": "fill", "text": sent.replace(key, "________", 1)[:300], "options": [], "answer": key,
                   "points": 1, "skill": "استدعاء", "difficulty": p["difficulty"]})
        if len(qs) >= n:
            break
    for o in [o for o in p["objectives"] if o.strip()][: max(0, n - len(qs))]:
        qs.append({"type": "short", "text": f"اشرح بأسلوبك: {o}", "options": [], "answer": "", "points": 2,
                   "skill": "فهم", "difficulty": p["difficulty"]})
    if not qs:
        qs = [{"type": "short", "text": PH, "options": [], "answer": "", "points": 1, "skill": "", "difficulty": p["difficulty"]}
              for _ in range(3)]
    label = "اختبار" if kind == "assessment" else "ورقة عمل"
    return {"title": f"{label}: {p['name']}", "instructions": "اقرأ كل سؤال بعناية وأجب في المكان المخصص.", "questions": qs}
