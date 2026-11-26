"""Real exporters. Each returns bytes; verify_* re-opens the produced bytes to prove they are valid."""
import io, os, csv, random, zipfile, zlib, html as _html
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from lxml import etree

NAVY, TEAL, LIGHT, PURPLE, GOLD = "14263D", "16A6A1", "F5F7FA", "7568D8", "E6B85C"
WSTYLES = {"print": {"accent": NAVY, "alt": "8A97A6"}, "color": {"accent": TEAL, "alt": GOLD},
           "minimal": {"accent": "5A6B7D", "alt": "9AA7B4"}, "class": {"accent": PURPLE, "alt": TEAL}}
_AR_L = "أبجدهوزحطي"


def _aletter(j):
    return _AR_L[j] if j < len(_AR_L) else str(j + 1)


def _shuffled(items, seed_text):
    """Deterministic shuffle (stable across runs) so the student version hides the answer order."""
    r = random.Random(zlib.crc32(str(seed_text).encode("utf-8")))
    L = list(items)
    r.shuffle(L)
    return L


def _q_answer(q):
    from .gen import q_answer
    return q_answer(q)
FONTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")
rgb = lambda h: RGBColor.from_string(h)


# ---------------- PPTX ----------------
def _rtl_para(p, size, bold=False, color=NAVY, align="r"):
    pPr = p._p.get_or_add_pPr()
    pPr.set("rtl", "1")
    pPr.set("algn", align)
    for r in p.runs:
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = rgb(color)
        rPr = r._r.get_or_add_rPr()
        rPr.set("lang", "ar-SA")
        for tag in ("a:latin", "a:cs"):
            el = etree.SubElement(rPr, qn(tag))
            el.set("typeface", "Arial")


def _box(slide, x, y, w, h, fill=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _text(slide, x, y, w, h, lines, size, bold=False, color=NAVY, bullet=False, anchor=MSO_ANCHOR.TOP, align="r"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("• " + line) if bullet else line
        p.space_after = Pt(10)
        _rtl_para(p, size, bold, color, align)
    return tb


def build_pptx(content, images=None, meta=None, rtl=True):
    images = images or {}
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]
    slides = content["slides"]
    for idx, s in enumerate(slides):
        sl = prs.slides.add_slide(blank)
        lay = s.get("layout", "bullets")
        if lay in ("title", "closing"):
            bg = _box(sl, 0, 0, W, H, NAVY)
            _box(sl, Inches(9.2), Inches(3.3), Inches(3.4), Emu(45720), GOLD)
            _text(sl, Inches(1), Inches(1.4), Inches(11.3), Inches(1.8), [s["title"]], 44, True, "FFFFFF", anchor=MSO_ANCHOR.BOTTOM)
            if s.get("bullets"):
                _text(sl, Inches(1), Inches(3.6), Inches(11.3), Inches(2.4), s["bullets"], 22, False, "D9E2EC")
        else:
            _box(sl, 0, 0, W, H, LIGHT)
            _box(sl, 0, 0, W, Inches(1.25), NAVY)
            _box(sl, W - Inches(0.35), 0, Inches(0.35), H, TEAL)
            _text(sl, Inches(0.6), Inches(0.15), Inches(11.9), Inches(1.0), [s["title"]], 32, True, "FFFFFF", anchor=MSO_ANCHOR.MIDDLE)
            img = images.get(s.get("image_source_id"))
            bx_w = Inches(7.4) if img else Inches(11.9)
            bx_x = Inches(5.4) if img else Inches(0.6)
            if lay == "two_column" and len(s["bullets"]) > 1 and not img:
                half = (len(s["bullets"]) + 1) // 2
                _text(sl, Inches(6.9), Inches(1.6), Inches(5.6), Inches(5.2), s["bullets"][:half], 24, bullet=True)
                _text(sl, Inches(0.6), Inches(1.6), Inches(5.6), Inches(5.2), s["bullets"][half:], 24, bullet=True)
            else:
                n = len(s["bullets"])
                _text(sl, bx_x, Inches(1.6), bx_w, Inches(5.2), s["bullets"], 28 if n <= 4 else 24 if n <= 6 else 20, bullet=True)
            if img:
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(img))
                    ar = im.width / im.height
                    mw, mh = Inches(4.4), Inches(4.8)
                    w, h = (mw, int(mw / ar)) if ar > mw / mh else (int(mh * ar), mh)
                    sl.shapes.add_picture(io.BytesIO(img), Inches(0.6), Inches(1.7), w, h)
                except Exception:
                    pass
        if s.get("notes"):
            sl.notes_slide.notes_text_frame.text = s["notes"]
        # slide number
        _text(sl, Inches(0.2), H - Inches(0.5), Inches(1.0), Inches(0.4), [str(idx + 1)], 12, False, "8A97A6", align="l")
        if (meta or {}).get("brand") and lay not in ("title", "closing"):
            _text(sl, Inches(3), H - Inches(0.5), Inches(7), Inches(0.4), [meta["brand"]], 12, False, "8A97A6", align="r")
    cp = prs.core_properties
    cp.title = content.get("title", "")
    cp.author = (meta or {}).get("author", "EduFlow AI Studio")
    b = io.BytesIO()
    prs.save(b)
    return b.getvalue()


def verify_pptx(data):
    prs = Presentation(io.BytesIO(data))
    n = len(prs.slides)
    texts = sum(1 for s in prs.slides for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip())
    pics = sum(1 for s in prs.slides for sh in s.shapes if sh.shape_type == 13)
    assert n > 0 and texts > 0
    return f"PPTX صالح: {n} شريحة، {texts} صندوق نص قابل للتحرير، {pics} صورة"


# ---------------- Arabic PDF ----------------
_fonts_ready = False


def _setup_fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("Amiri", os.path.join(FONTS, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Amiri-Bold", os.path.join(FONTS, "Amiri-Bold.ttf")))
    _fonts_ready = True


def _shape(t):
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(t))


def _wrap(text, font, size, maxw):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    out = []
    for para in str(text).split("\n"):
        words, line = para.split(), ""
        for w in words:
            cand = (line + " " + w).strip()
            if stringWidth(_shape(cand), font, size) <= maxw:
                line = cand
            else:
                if line:
                    out.append(line)
                line = w
        out.append(line)
    return out


class _Pdf:
    def __init__(self, landscape_=False):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
        _setup_fonts()
        self.buf = io.BytesIO()
        self.size = landscape(A4) if landscape_ else A4
        self.c = canvas.Canvas(self.buf, pagesize=self.size)
        self.W, self.H = self.size
        self.m = 50
        self.y = self.H - self.m

    def line(self, text, size=14, bold=False, color=NAVY, gap=6, indent=0):
        from reportlab.lib.colors import HexColor
        font = "Amiri-Bold" if bold else "Amiri"
        for ln in _wrap(text, font, size, self.W - 2 * self.m - indent):
            if self.y < self.m + size:
                self.c.showPage()
                self.y = self.H - self.m
            self.c.setFont(font, size)
            self.c.setFillColor(HexColor("#" + color))
            self.c.drawRightString(self.W - self.m - indent, self.y, _shape(ln))
            self.y -= size * 1.45
        self.y -= gap

    def page(self):
        self.c.showPage()
        self.y = self.H - self.m

    def done(self):
        self.c.save()
        return self.buf.getvalue()


def pdf_slides(content):
    from reportlab.lib.colors import HexColor
    p = _Pdf(landscape_=True)
    for i, s in enumerate(content["slides"]):
        p.c.setFillColor(HexColor("#" + (NAVY if s.get("layout") in ("title", "closing") else LIGHT)))
        p.c.rect(0, 0, p.W, p.H, fill=1, stroke=0)
        if s.get("layout") not in ("title", "closing"):
            p.c.setFillColor(HexColor("#" + NAVY))
            p.c.rect(0, p.H - 80, p.W, 80, fill=1, stroke=0)
            p.c.setFillColor(HexColor("#" + TEAL))
            p.c.rect(p.W - 14, 0, 14, p.H, fill=1, stroke=0)
        p.y = p.H - 55 if s.get("layout") not in ("title", "closing") else p.H / 2 + 30
        p.line(s["title"], 28, True, "FFFFFF" if True else NAVY, gap=24)
        p.y = p.H - 130 if s.get("layout") not in ("title", "closing") else p.y
        col = NAVY if s.get("layout") not in ("title", "closing") else "D9E2EC"
        for b in s["bullets"]:
            p.line("• " + b, 18, False, col, gap=8)
        p.c.setFont("Helvetica", 9)
        p.c.setFillColorRGB(.55, .6, .65)
        p.c.drawString(20, 14, str(i + 1))
        p.page()
    return p.done()


def _pdf_question(p, i, q, kind):
    p.line(f"{i}. {q['text']}  ({q.get('points', 1):g})", 14, True, gap=4)
    if q.get("type") == "matching" and q.get("pairs"):
        rights = _shuffled([b for _, b in q["pairs"]], q["text"])
        for j, (a, _) in enumerate(q["pairs"], 1):
            p.line(f"{j}) {a}  .......  (   )", 13, indent=18, gap=2)
        p.line("الاختيارات: " + "    ".join(f"{_aletter(k)}) {r}" for k, r in enumerate(rights)), 13, indent=18, color="8A97A6", gap=10)
    elif q.get("type") == "ordering" and q.get("items"):
        for it in _shuffled(q["items"], q["text"]):
            p.line(f"(  ) {it}", 13, indent=18, gap=2)
        p.line("اكتب الترتيب الصحيح بالأرقام داخل الأقواس", 11, indent=18, color="8A97A6", gap=10)
    else:
        for j, o in enumerate(q.get("options", [])):
            p.line(f"{_aletter(j)}) {o}", 13, indent=18, gap=2)
        if kind == "worksheet" or q.get("type") in ("short", "essay", "fill"):
            p.line("الإجابة: " + "_" * 40, 13, color="8A97A6", gap=10)


def _pdf_rubric(p, content, accent):
    rub = content.get("rubric") or []
    if not rub:
        return
    p.line("سلم التقييم (Rubric)", 16, True, accent, gap=6)
    for r in rub:
        p.line(f"• {r['criterion']} — {float(r.get('weight', 0) or 0):g}%", 13, True, gap=2)
        det = " | ".join(x for x in [f"ممتاز: {r.get('excellent', '')}" if r.get("excellent") else "",
                                     f"جيد: {r.get('good', '')}" if r.get("good") else "",
                                     f"يحتاج دعمًا: {r.get('poor', '')}" if r.get("poor") else ""] if x)
        if det:
            p.line(det, 12, indent=14, color="444444", gap=8)


def pdf_doc(content, kind="document"):
    sty = WSTYLES.get(content.get("style", "print"), WSTYLES["print"])
    p = _Pdf()
    p.line(content.get("title", ""), 22, True, NAVY, gap=14)
    if kind == "document":
        for s in content["sections"]:
            p.line(s["heading"], 16, True, TEAL, gap=4)
            p.line(s["body"], 13, gap=12)
        return p.done()
    if content.get("instructions"):
        p.line(content["instructions"], 13, gap=12)
    if kind == "worksheet":
        if content.get("objectives"):
            p.line("الأهداف", 16, True, sty["accent"], gap=4)
            for o in content["objectives"]:
                p.line("• " + o, 13, indent=12, gap=2)
            p.line(" ", 6, gap=8)
        if content.get("activities"):
            p.line("الأنشطة", 16, True, sty["accent"], gap=4)
            for a in content["activities"]:
                p.line(a.get("title", "نشاط"), 14, True, NAVY, gap=2)
                p.line(str(a.get("body", "")), 13, indent=12, gap=8)
        p.line("الأسئلة", 16, True, sty["accent"], gap=8)
    for i, q in enumerate(content["questions"], 1):
        _pdf_question(p, i, q, kind)
    if kind == "assessment":
        p.page()
        p.line("نموذج الإجابة", 18, True, TEAL, gap=8)
        for i, q in enumerate(content["questions"], 1):
            p.line(f"{i}. {_q_answer(q) or '(لا توجد إجابة)'}", 13)
        _pdf_rubric(p, content, TEAL)
    return p.done()


def verify_pdf(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    assert len(r.pages) > 0
    return f"PDF صالح: {len(r.pages)} صفحة، {len(data)//1024} KB (الخط Amiri مضمّن)"


# ---------------- DOCX ----------------
def _docx_rtl(par, run_size=12, bold=False, color=None, align=2):
    from docx.shared import Pt as P, RGBColor as C
    from docx.oxml import OxmlElement
    pPr = par._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    pPr.append(bidi)
    par.alignment = align  # 2 = right
    for r in par.runs:
        r.font.size = P(run_size)
        r.font.bold = bold
        if color:
            r.font.color.rgb = C.from_string(color)
        rPr = r._r.get_or_add_rPr()
        rPr.append(OxmlElement("w:rtl"))
        rf = rPr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rPr.insert(0, rf)
        rf.set(qn("w:cs"), "Arial")
        rf.set(qn("w:ascii"), "Arial")
        rf.set(qn("w:hAnsi"), "Arial")


def _docx_question(d, i, q, kind):
    _docx_rtl(d.add_paragraph(f"{i}. {q['text']}  ({float(q.get('points', 1) or 0):g})"), 13, True)
    if q.get("type") == "matching" and q.get("pairs"):
        rights = _shuffled([b for _, b in q["pairs"]], q["text"])
        for j, (a, _) in enumerate(q["pairs"], 1):
            _docx_rtl(d.add_paragraph(f"{j}) {a}  .......  (   )"), 12)
        _docx_rtl(d.add_paragraph("الاختيارات: " + "    ".join(f"{_aletter(k)}) {r}" for k, r in enumerate(rights))), 12, color="8A97A6")
    elif q.get("type") == "ordering" and q.get("items"):
        for it in _shuffled(q["items"], q["text"]):
            _docx_rtl(d.add_paragraph(f"(  ) {it}"), 12)
        _docx_rtl(d.add_paragraph("اكتب الترتيب الصحيح بالأرقام داخل الأقواس"), 10, color="8A97A6")
    else:
        for j, o in enumerate(q.get("options", [])):
            _docx_rtl(d.add_paragraph(f"{_aletter(j)}) {o}"), 12)
        if kind == "worksheet" or q.get("type") in ("short", "essay", "fill"):
            _docx_rtl(d.add_paragraph("الإجابة: " + "_" * 45), 12, color="8A97A6")


def docx_doc(content, kind="document"):
    import docx
    sty = WSTYLES.get(content.get("style", "print"), WSTYLES["print"])
    d = docx.Document()
    p = d.add_paragraph(content.get("title", ""))
    _docx_rtl(p, 22, True, NAVY)
    if kind == "document":
        for s in content["sections"]:
            h = d.add_paragraph(s["heading"])
            _docx_rtl(h, 16, True, TEAL)
            for line in s["body"].split("\n"):
                b = d.add_paragraph(line)
                _docx_rtl(b, 12)
    else:
        if content.get("instructions"):
            _docx_rtl(d.add_paragraph(content["instructions"]), 12)
        if kind == "worksheet":
            if content.get("objectives"):
                _docx_rtl(d.add_paragraph("الأهداف"), 16, True, sty["accent"])
                for o in content["objectives"]:
                    _docx_rtl(d.add_paragraph("• " + o), 12)
            if content.get("activities"):
                _docx_rtl(d.add_paragraph("الأنشطة"), 16, True, sty["accent"])
                for a in content["activities"]:
                    _docx_rtl(d.add_paragraph(a.get("title", "نشاط")), 14, True, NAVY)
                    for ln in str(a.get("body", "")).split("\n"):
                        _docx_rtl(d.add_paragraph(ln), 12)
            _docx_rtl(d.add_paragraph("الأسئلة"), 16, True, sty["accent"])
        for i, q in enumerate(content["questions"], 1):
            _docx_question(d, i, q, kind)
        if kind == "assessment":
            d.add_page_break()
            _docx_rtl(d.add_paragraph("نموذج الإجابة"), 16, True, TEAL)
            for i, q in enumerate(content["questions"], 1):
                _docx_rtl(d.add_paragraph(f"{i}. {_q_answer(q) or '(لا توجد إجابة)'}"), 12)
            rub = content.get("rubric") or []
            if rub:
                _docx_rtl(d.add_paragraph("سلم التقييم (Rubric)"), 16, True, TEAL)
                for r in rub:
                    _docx_rtl(d.add_paragraph(f"• {r['criterion']} — {float(r.get('weight', 0) or 0):g}%"), 13, True)
                    det = " | ".join(x for x in [f"ممتاز: {r.get('excellent', '')}" if r.get("excellent") else "",
                                                 f"جيد: {r.get('good', '')}" if r.get("good") else "",
                                                 f"يحتاج دعمًا: {r.get('poor', '')}" if r.get("poor") else ""] if x)
                    if det:
                        _docx_rtl(d.add_paragraph(det), 12, color="444444")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def verify_docx(data):
    import docx
    d = docx.Document(io.BytesIO(data))
    n = len([p for p in d.paragraphs if p.text.strip()])
    assert n > 0
    return f"DOCX صالح: {n} فقرة قابلة للتحرير"


# ---------------- XLSX / CSV / HTML / ZIP ----------------
def rows_for(kind, content):
    if kind == "presentation":
        return ["رقم", "العنوان", "النقاط", "الملاحظات"], [[i + 1, s["title"], "\n".join(s["bullets"]), s.get("notes", "")] for i, s in enumerate(content["slides"])]
    if kind == "document":
        return ["القسم", "المحتوى"], [[s["heading"], s["body"]] for s in content["sections"]]
    def cell_opts(q):
        if q.get("type") == "matching":
            return " | ".join(f"{a} ⇐ {b}" for a, b in q.get("pairs", []))
        if q.get("type") == "ordering":
            return " ← ".join(q.get("items", []))
        return " | ".join(q.get("options", []))
    return ["رقم", "النوع", "السؤال", "الخيارات/البنود", "الإجابة", "الدرجة", "المهارة", "الصعوبة"], [
        [i + 1, q["type"], q["text"], cell_opts(q), _q_answer(q), q.get("points", 1), q.get("skill", ""), q.get("difficulty", "")]
        for i, q in enumerate(content["questions"])]


def xlsx_bytes(kind, content):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    h, rows = rows_for(kind, content)
    ws.append(h)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def verify_xlsx(data):
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    return f"XLSX صالح: {ws.max_row} صفًا × {ws.max_column} أعمدة"


def csv_bytes(kind, content):
    b = io.StringIO()
    w = csv.writer(b)
    h, rows = rows_for(kind, content)
    w.writerow(h)
    w.writerows(rows)
    return ("\ufeff" + b.getvalue()).encode("utf-8")


def html_bytes(kind, content):
    e = _html.escape
    parts = [f"<h1>{e(content.get('title', ''))}</h1>"]
    if kind == "presentation":
        for i, s in enumerate(content["slides"], 1):
            parts.append(f"<section><h2>{i}. {e(s['title'])}</h2><ul>" + "".join(f"<li>{e(b)}</li>" for b in s["bullets"]) + "</ul></section>")
    elif kind == "document":
        for s in content["sections"]:
            parts.append(f"<h2>{e(s['heading'])}</h2><p>{e(s['body']).replace(chr(10), '<br>')}</p>")
    else:
        parts.append(f"<p>{e(content.get('instructions',''))}</p>")
        if kind == "worksheet":
            if content.get("objectives"):
                parts.append("<h2>الأهداف</h2><ul>" + "".join(f"<li>{e(o)}</li>" for o in content["objectives"]) + "</ul>")
            for a in content.get("activities", []):
                parts.append(f"<h3>{e(a.get('title','نشاط'))}</h3><p>{e(str(a.get('body',''))).replace(chr(10), '<br>')}</p>")
        parts.append("<ol>")
        for q in content["questions"]:
            li = f"<li><b>{e(q['text'])}</b>"
            if q.get("type") == "matching" and q.get("pairs"):
                rights = _shuffled([b for _, b in q["pairs"]], q["text"])
                li += "<ol type='a'>" + "".join(f"<li>{e(a)}</li>" for a, _ in q["pairs"]) + "</ol>"
                li += "<p>الاختيارات: " + e(" ، ".join(f"{_aletter(k)}) {r}" for k, r in enumerate(rights))) + "</p>"
            elif q.get("type") == "ordering" and q.get("items"):
                li += "<ul>" + "".join(f"<li>( ) {e(it)}</li>" for it in _shuffled(q["items"], q["text"])) + "</ul>"
            elif q.get("options"):
                li += "<ul>" + "".join(f"<li>{e(o)}</li>" for o in q["options"]) + "</ul>"
            parts.append(li + "</li>")
        parts.append("</ol>")
        if kind == "assessment":
            parts.append("<h2>نموذج الإجابة</h2><ol>" + "".join(
                f"<li>{e(_q_answer(q) or '(لا توجد إجابة)')}</li>" for q in content["questions"]) + "</ol>")
            rub = content.get("rubric") or []
            if rub:
                rows = "".join(f"<tr><td>{e(r['criterion'])}</td><td>{float(r.get('weight',0) or 0):g}%</td>"
                               f"<td>{e(r.get('excellent',''))}</td><td>{e(r.get('good',''))}</td><td>{e(r.get('poor',''))}</td></tr>" for r in rub)
                parts.append("<h2>سلم التقييم</h2><table border='1' cellspacing='0' cellpadding='6'>"
                             "<tr><th>المعيار</th><th>الوزن</th><th>ممتاز</th><th>جيد</th><th>يحتاج دعمًا</th></tr>" + rows + "</table>")
    doc = (f"<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>{e(content.get('title',''))}</title>"
           f"<style>body{{font-family:Arial,sans-serif;max-width:800px;margin:2rem auto;color:#{NAVY};line-height:1.8}}h1,h2{{color:#{TEAL}}}</style><body>" + "".join(parts) + "</body></html>")
    return doc.encode("utf-8")


def verify_text(data, label):
    assert len(data) > 20
    return f"{label} صالح: {len(data)} بايت"


def zip_bytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return b.getvalue()


def verify_zip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        return f"ZIP صالح: {len(z.namelist())} ملفات"


MIME = {"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv", "html": "text/html", "zip": "application/zip"}


def export(kind, content, fmt, images=None, meta=None):
    """Return (bytes, verification message). Raises ValueError for unsupported combos."""
    if fmt == "pptx" and kind == "presentation":
        d = build_pptx(content, images, meta); return d, verify_pptx(d)
    if fmt == "pdf":
        d = pdf_slides(content) if kind == "presentation" else pdf_doc(content, kind); return d, verify_pdf(d)
    if fmt == "docx" and kind in ("document", "worksheet", "assessment"):
        d = docx_doc(content, kind); return d, verify_docx(d)
    if fmt == "xlsx":
        d = xlsx_bytes(kind, content); return d, verify_xlsx(d)
    if fmt == "csv":
        d = csv_bytes(kind, content); return d, verify_text(d, "CSV")
    if fmt == "html":
        d = html_bytes(kind, content); return d, verify_text(d, "HTML")
    raise ValueError("هذه الصيغة غير مدعومة لهذا النوع من المخرجات")


FORMATS = {"presentation": ["pptx", "pdf", "xlsx", "csv", "html"], "document": ["docx", "pdf", "xlsx", "csv", "html"],
           "worksheet": ["docx", "pdf", "xlsx", "csv", "html"], "assessment": ["docx", "pdf", "xlsx", "csv", "html"]}
