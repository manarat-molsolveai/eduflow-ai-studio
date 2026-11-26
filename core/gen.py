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
Q_TYPES = {"mcq": "اختيار من متعدد", "tf": "صح/خطأ", "matching": "مطابقة", "ordering": "ترتيب",
           "short": "إجابة قصيرة", "fill": "أكمل الفراغ", "essay": "مقالي"}
WORKSHEET_STYLES = {"print": "طباعة", "color": "ملوّن", "minimal": "بسيط", "class": "صفّي"}
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
    d.setdefault("instructions", "")
    if d.get("style") not in WORKSHEET_STYLES:
        d["style"] = "print"
    d["objectives"] = [str(o).strip() for o in (d.get("objectives") or []) if str(o).strip()][:10]
    acts = []
    for a in (d.get("activities") or [])[:8]:
        if isinstance(a, dict) and (a.get("title") or a.get("body")):
            acts.append({"title": str(a.get("title") or "نشاط"), "body": str(a.get("body", ""))})
    d["activities"] = acts
    rub = []
    for r in (d.get("rubric") or [])[:8]:
        if isinstance(r, dict) and str(r.get("criterion", "")).strip():
            try:
                w = min(100.0, max(0.0, float(r.get("weight", 0) or 0)))
            except (TypeError, ValueError):
                w = 0.0
            rub.append({"criterion": str(r["criterion"]).strip()[:200], "weight": w,
                        "excellent": str(r.get("excellent", "")), "good": str(r.get("good", "")), "poor": str(r.get("poor", ""))})
    d["rubric"] = rub
    for q in d["questions"]:
        if not q.get("text"):
            raise ValueError("question without text")
        if q.get("type") not in Q_TYPES:
            q["type"] = "short"
        q.setdefault("options", [])
        q.setdefault("answer", "")
        q.setdefault("points", 1)
        q.setdefault("skill", "")
        q.setdefault("difficulty", "متوسط")
        pairs = []
        for pr in (q.get("pairs") or [])[:12]:
            if isinstance(pr, (list, tuple)) and len(pr) == 2 and str(pr[0]).strip() and str(pr[1]).strip():
                pairs.append([str(pr[0]).strip(), str(pr[1]).strip()])
        q["pairs"] = pairs
        q["items"] = [str(x).strip() for x in (q.get("items") or []) if str(x).strip()][:12]
        if q["type"] == "matching" and len(pairs) < 2:
            q["type"] = "short"
        if q["type"] == "ordering" and len(q["items"]) < 3:
            q["type"] = "short"


def q_answer(q):
    """The stored answer, or the answer derived from pairs/items for matching/ordering."""
    if q.get("answer"):
        return q["answer"]
    if q.get("type") == "matching" and q.get("pairs"):
        return " | ".join(f"{a} ⇐ {b}" for a, b in q["pairs"])
    if q.get("type") == "ordering" and q.get("items"):
        return " ثم ".join(q["items"])
    return ""


def suggest_rubric(content):
    """Rules-based rubric draft built from the assessment's own skills. Not AI; a starting point the teacher edits."""
    skills = []
    for q in content.get("questions", []):
        s = (q.get("skill") or "").strip()
        if s and s not in skills:
            skills.append(s)
    if not skills:
        skills = ["الفهم والاستيعاب", "التطبيق", "الدقة في الإجابة"]
    skills = skills[:5]
    base = 100 // len(skills)
    rubric = []
    for i, s in enumerate(skills):
        w = base + (100 - base * len(skills) if i == len(skills) - 1 else 0)
        rubric.append({"criterion": s, "weight": float(w),
                       "excellent": "إجابات كاملة ودقيقة في أسئلة هذه المهارة",
                       "good": "إجابات صحيحة في معظمها مع أخطاء بسيطة",
                       "poor": "إجابات ناقصة أو غير دقيقة؛ يحتاج إعادة تعلّم"})
    return rubric


def diff_summary(kind, old, new):
    """Rules-based summary of what changed between two saved content versions."""
    lines = []
    if (old.get("title") or "") != (new.get("title") or ""):
        lines.append("تغيّر العنوان")
    key = {"presentation": "slides", "document": "sections"}.get(kind, "questions")
    unit = {"presentation": "شريحة", "document": "قسم"}.get(kind, "سؤال")
    A, B = old.get(key) or [], new.get(key) or []
    if len(B) > len(A):
        lines.append(f"أُضيف {len(B) - len(A)} {unit}")
    elif len(A) > len(B):
        lines.append(f"حُذف {len(A) - len(B)} {unit}")
    changed = min(len(A), len(B)) - sum(1 for a, b in zip(A, B) if a == b)
    if changed:
        lines.append(f"عُدّل {changed} {unit}")
    if kind in ("worksheet", "assessment"):
        if (old.get("instructions") or "") != (new.get("instructions") or ""):
            lines.append("تغيّرت التعليمات")
        if (old.get("objectives") or []) != (new.get("objectives") or []):
            lines.append("تغيّرت الأهداف")
        if (old.get("activities") or []) != (new.get("activities") or []):
            lines.append("تغيّرت الأنشطة")
        if (old.get("rubric") or []) != (new.get("rubric") or []):
            lines.append("تغيّر سلم التقييم")
        if (old.get("style") or "") != (new.get("style") or ""):
            lines.append("تغيّر نمط الورقة")
    return lines or ["لا فروق نصية بين الإصدارين"]


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
        shape = ('{"title":"","instructions":"","objectives":["هدف قابل للقياس"],'
                 '"activities":[{"title":"نشاط","body":"خطوات النشاط"}],'
                 '"rubric":[{"criterion":"المعيار","weight":25,"excellent":"وصف الإتقان","good":"وصف الجيد","poor":"وصف ما يحتاج دعمًا"}],'
                 '"questions":[{"type":"mcq|tf|matching|ordering|short|fill|essay","text":"نص السؤال","options":["خيارات mcq فقط"],'
                 '"pairs":[["مصطلح","تعريفه"]],"items":["بند بالترتيب الصحيح"],'
                 '"answer":"الإجابة الصحيحة (فارغة لـ matching/ordering)","points":1,"skill":"","difficulty":"سهل|متوسط|صعب"}]}')
        extra = ("\n\nهذه ورقة عمل: أدرج أهدافًا وأنشطة صفّية قصيرة مناسبة للمرحلة، ونوّع الأسئلة ومنها matching وordering حيث يلائم المحتوى."
                 if kind == "worksheet" else
                 "\n\nهذا اختبار: نوّع أنواع الأسئلة ومنها matching وordering حيث يلائم المحتوى، وأدرج سلم تقييم (rubric) من 3-5 معايير أوزانها مجموعها 100.")
        prompt = (_ctx(p, sources) + f"\n\nأنشئ {n} أسئلة متنوعة. الشكل: {shape} " + extra +
                  " الأسئلة مبنية على المصادر فقط.")
        data, prov, model = ai.generate_json(uid, p["id"], kind, SYS, prompt, validate_questions)
        return data, f"ai:{prov}:{model}"
    return local_questions(p, sources, kind, n), "local-rules"


def _definition_pairs(sources):
    """Extract 'term: definition' lines actually present in the user's sources. Returns up to 8 [term, definition] pairs."""
    pairs = []
    for s in sources:
        for line in (s["content"] or "").splitlines():
            m = re.match(r"^([^:：\n]{3,45})[:：]\s*(\S.{9,220})$", line.strip(" -\t"))
            if m and len(pairs) < 8:
                term, defin = m.group(1).strip(), m.group(2).strip()
                if len(term.split()) <= 5 and defin not in [b for _, b in pairs]:
                    pairs.append([term, defin])
    return pairs


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
        qs.append({"type": "fill", "text": sent.replace(key, "________", 1)[:300], "options": [], "pairs": [], "items": [],
                   "answer": key, "points": 1, "skill": "استدعاء", "difficulty": p["difficulty"]})
        if len(qs) >= n:
            break
    pairs = _definition_pairs(sources)
    if len(pairs) >= 3 and len(qs) < n:
        qs.append({"type": "matching", "text": "صِل كل مصطلح بتعريفه (المصطلحات والتعريفات منقولة حرفيًا من مصدرك).",
                   "options": [], "pairs": pairs[:6], "items": [], "answer": "", "points": len(pairs[:6]),
                   "skill": "فهم", "difficulty": p["difficulty"]})
    objs = [o for o in p["objectives"] if o.strip()]
    if len(objs) >= 3 and len(qs) < n:
        qs.append({"type": "ordering", "text": "رتّب العناصر التالية بالترتيب الذي حددته في أهداف المشروع.",
                   "options": [], "pairs": [], "items": objs[:6], "answer": "", "points": 2,
                   "skill": "ترتيب", "difficulty": p["difficulty"]})
    for o in objs[: max(0, n - len(qs))]:
        qs.append({"type": "short", "text": f"اشرح بأسلوبك: {o}", "options": [], "pairs": [], "items": [],
                   "answer": "", "points": 2, "skill": "فهم", "difficulty": p["difficulty"]})
    if not qs:
        qs = [{"type": "short", "text": PH, "options": [], "pairs": [], "items": [], "answer": "", "points": 1,
               "skill": "", "difficulty": p["difficulty"]} for _ in range(3)]
    label = "اختبار" if kind == "assessment" else "ورقة عمل"
    d = {"title": f"{label}: {p['name']}", "instructions": "اقرأ كل سؤال بعناية وأجب في المكان المخصص.",
         "questions": qs, "objectives": objs[:6], "activities": [], "rubric": []}
    if kind == "worksheet":
        d["style"] = "print"
        d["activities"] = ([{"title": "نشاط من مصدرك", "body": "من نص مصدرك:\n" + "\n".join(f"- {x[:160]}" for x in sents[:3])}] if sents else [])
    return d
