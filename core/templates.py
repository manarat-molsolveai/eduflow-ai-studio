"""Built-in starter templates. They only prefill wizard fields and the output plan; they invent no content."""
TEMPLATES = {
    "": {"label": "بدون قالب", "desc": "ابدأ من الصفر."},
    "lesson_pack": {"label": "حزمة درس كاملة", "desc": "عرض + ورقة عمل + اختبار قصير، بمستوى متوسط.",
                    "ptype": "lesson", "difficulty": "متوسط", "n_slides": 8,
                    "plan": [{"kind": "presentation", "n": 8}, {"kind": "worksheet", "n": 8}, {"kind": "assessment", "n": 8}],
                    "objectives": ["أن يتعرف الطالب على {t}", "أن يشرح الطالب {t} بأسلوبه", "أن يطبق الطالب ما تعلمه عن {t} في مثال جديد"]},
    "quick_review": {"label": "مراجعة سريعة", "desc": "عرض قصير (5 شرائح) + اختبار.",
                     "ptype": "lesson", "difficulty": "سهل", "n_slides": 5,
                     "plan": [{"kind": "presentation", "n": 5}, {"kind": "assessment", "n": 8}],
                     "objectives": ["أن يستعيد الطالب أهم أفكار موضوع {t}", "أن يقيّم الطالب فهمه لموضوع {t}"]},
    "practice": {"label": "تدريب وتقويم", "desc": "ورقة عمل + اختبار بمستوى صعب.",
                 "ptype": "lesson", "difficulty": "صعب", "n_slides": 8,
                 "plan": [{"kind": "worksheet", "n": 8}, {"kind": "assessment", "n": 8}],
                 "objectives": ["أن يحلل الطالب مسائل موضوع {t}", "أن يقيّم الطالب حلولًا مختلفة لموضوع {t}"]},
}


def apply(key, topic):
    """Return project fields for a template key; {} for none/unknown."""
    t = TEMPLATES.get(key)
    if not t or not key:
        return {}
    return {"ptype": t["ptype"], "difficulty": t["difficulty"],
            "objectives": [o.format(t=topic) for o in t["objectives"]],
            "settings": {"language": "العربية", "plan": [dict(x) for x in t["plan"]], "n_slides": t["n_slides"]}}
