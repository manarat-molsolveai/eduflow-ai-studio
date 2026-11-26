"""Rule-based quality review (documented, deterministic). Dimensions that rules cannot judge are marked
'needs human/AI review' and excluded from the numeric score."""
import re, json
from .gen import PH, q_answer

WEIGHTS = {"structure": 20, "completeness": 25, "language": 15, "audience": 15, "usability": 10, "source_integrity": 15}
RULES = [
    "structure: عنوان لكل عنصر، وعدد النقاط/الأقسام ضمن الحدود",
    "completeness: خلو المحتوى من علامات [اكتب هنا] والحقول الفارغة",
    "language: نسبة الحروف العربية تطابق لغة المشروع",
    "audience: طول النقاط والجمل مناسب للمرحلة",
    "usability: ملاحظات المعلم/تعليمات/مفتاح إجابة/سلم تقييم موجودة",
    "source_integrity: وجود مصادر مرتبطة، وتوضيح طريقة التوليد",
]
UNJUDGED = ["accuracy (الدقة العلمية)", "educational_alignment (المواءمة مع المنهج)", "visual_quality (الجودة البصرية)"]


def _texts(kind, c):
    if kind == "presentation":
        return [s["title"] for s in c["slides"]] + [b for s in c["slides"] for b in s["bullets"]]
    if kind == "document":
        return [s["heading"] for s in c["sections"]] + [s["body"] for s in c["sections"]]
    ts = [c.get("instructions", "")]
    for q in c["questions"]:
        ts.append(q.get("text", ""))
        ts += [str(o) for o in q.get("options", [])]
        ts += [str(x) for pr in q.get("pairs", []) for x in pr]
        ts += [str(x) for x in q.get("items", [])]
    ts += [str(o) for o in c.get("objectives", [])]
    ts += [str(a.get("title", "")) + " " + str(a.get("body", "")) for a in c.get("activities", [])]
    ts += [str(r.get("criterion", "")) for r in c.get("rubric", [])]
    return ts


def review(kind, c, project, n_sources, generator):
    warn, err, tips = [], [], []
    dims = {}
    # structure
    st = 100
    if kind == "presentation":
        sl = c["slides"]
        if len(sl) < 3:
            st -= 40; err.append("عدد الشرائح أقل من 3")
        over = [i + 1 for i, s in enumerate(sl) if len(s["bullets"]) > 7]
        if over:
            st -= 20; warn.append(f"شرائح فيها أكثر من 7 نقاط: {over}")
        if sl and sl[0].get("layout") != "title":
            st -= 10; warn.append("الشريحة الأولى ليست شريحة عنوان")
    elif kind == "document":
        if len(c["sections"]) < 3:
            st -= 40; err.append("أقل من 3 أقسام")
    else:
        if len(c["questions"]) < 3:
            st -= 40; err.append("أقل من 3 أسئلة")
    dims["structure"] = max(st, 0)
    # completeness
    texts = [t for t in _texts(kind, c) if isinstance(t, str)]
    ph = sum(1 for t in texts if PH in t)
    empty = sum(1 for t in texts if not t.strip())
    comp = 100 - min(100, ph * 15 + empty * 10)
    if ph:
        err.append(f"{ph} عنصر لم يكتمل ([اكتب هنا])")
        tips.append("املأ العناصر المعلّمة أو أعد التوليد بعد إضافة مصدر نصي أو ربط مزود ذكاء اصطناعي")
    if empty:
        warn.append(f"{empty} عنصر فارغ")
    dims["completeness"] = max(comp, 0)
    # language
    joined = " ".join(texts)
    letters = re.findall(r"[A-Za-z\u0600-\u06FF]", joined)
    ar = len(re.findall(r"[\u0600-\u06FF]", joined))
    ratio = ar / len(letters) if letters else 0
    lang = project["settings"].get("language", "العربية")
    if lang == "العربية":
        lg = 100 if ratio >= 0.7 else int(ratio / 0.7 * 100)
        if ratio < 0.7:
            warn.append(f"نسبة العربية {int(ratio*100)}% بينما لغة المشروع العربية")
        # كلمات مختلطة: حروف لاتينية ملتصقة بأحرف عربية داخل الكلمة نفسها (مثل ما يحدث أحيانًا في مخرجات النماذج)
        mixed = [w for w in re.findall(r"[A-Za-z\u0600-\u06FF]+", joined)
                 if re.search(r"[A-Za-z]", w) and re.search(r"[\u0600-\u06FF]", w)]
        if mixed:
            lg = max(0, lg - min(30, 10 * len(mixed)))
            err.append(f"كلمات فيها حروف لاتينية داخل النص العربي: {len(mixed)}")
            tips.append("أعد التوليد أو عدّل الكلمات المختلطة يدويًا من المحرر")
    else:
        lg = 100 if ratio <= 0.3 else int((1 - ratio) / 0.7 * 100)
        if ratio > 0.3:
            warn.append("المحتوى عربي بينما لغة المشروع إنجليزية")
    dims["language"] = max(lg, 0)
    # audience
    avg = sum(len(t.split()) for t in texts) / max(1, len(texts))
    young = project["stage"] in ("الطفولة المبكرة", "رياض الأطفال", "المرحلة الابتدائية")
    limit = 18 if young else 30
    au = 100 if avg <= limit else max(0, 100 - int((avg - limit) * 4))
    if avg > limit:
        warn.append(f"متوسط طول النص {avg:.0f} كلمة، أطول من المناسب للمرحلة ({limit})")
        tips.append("قصّر الجمل وقسّم النقاط الطويلة")
    dims["audience"] = au
    # usability
    us = 100
    if kind == "presentation" and not any(s.get("notes", "").strip() for s in c["slides"]):
        us -= 40; tips.append("أضف ملاحظات للمعلم في الشرائح المهمة")
    if kind == "assessment" and any(not q_answer(q) for q in c["questions"]):
        us -= 40; warn.append("أسئلة بلا مفتاح إجابة")
    if kind == "assessment":
        if not c.get("rubric"):
            us -= 15; tips.append("أضف سلم تقييم (Rubric) من تبويب التحرير — زر «اقتراح سلم» يبني مسودة من أسئلتك")
        else:
            tot = sum(float(r.get("weight", 0) or 0) for r in c["rubric"])
            if abs(tot - 100) > 5:
                warn.append(f"أوزان سلم التقييم مجموعها {tot:g}% وليس 100%")
    if kind == "worksheet" and not c.get("instructions"):
        us -= 30; warn.append("لا توجد تعليمات")
    dims["usability"] = max(us, 0)
    # sources
    si = 100
    if n_sources == 0:
        si -= 50; warn.append("لا توجد مصادر مرتبطة بالمخرج")
        tips.append("ارفع مصدرًا أو أضف نصًا مرجعيًا ليستند إليه المحتوى")
    dims["source_integrity"] = si
    score = round(sum(dims[k] * w for k, w in WEIGHTS.items()) / sum(WEIGHTS.values()), 1)
    if err or score < 70:
        verdict = "needs_revision"
    else:
        verdict = "approved"
    return {"score": score, "verdict": verdict, "dims": dims, "weights": WEIGHTS, "warnings": warn, "errors": err,
            "suggestions": tips, "unjudged": UNJUDGED, "rules": RULES, "method": "rules-v2", "generator": generator}
