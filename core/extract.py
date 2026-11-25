"""Real text extraction. Unreadable types are reported as unreadable, never faked."""
import io, csv

MAX_CHARS = 200_000


def extract(filename, data):
    """Return (kind, text, readable, note)."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    try:
        if ext in ("txt", "md"):
            for enc in ("utf-8-sig", "utf-8", "cp1256"):
                try:
                    return "text", data.decode(enc)[:MAX_CHARS], True, ""
                except UnicodeDecodeError:
                    continue
            return "text", "", False, "تعذر تحديد ترميز النص"
        if ext == "pdf":
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            txt = "\n".join((p.extract_text() or "") for p in r.pages)
            if not txt.strip():
                return "pdf", "", False, "ملف PDF لا يحتوي نصًا قابلًا للاستخراج (غالبًا صور ممسوحة). لا يوجد OCR في هذا الإصدار"
            return "pdf", txt[:MAX_CHARS], True, f"{len(r.pages)} صفحة"
        if ext == "docx":
            import docx
            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            return "docx", "\n".join(parts)[:MAX_CHARS], True, ""
        if ext == "pptx":
            from pptx import Presentation
            p = Presentation(io.BytesIO(data))
            parts = []
            for i, sl in enumerate(p.slides, 1):
                parts.append(f"[شريحة {i}]")
                for sh in sl.shapes:
                    if sh.has_text_frame and sh.text_frame.text.strip():
                        parts.append(sh.text_frame.text)
            return "pptx", "\n".join(parts)[:MAX_CHARS], True, f"{len(p.slides)} شريحة"
        if ext == "csv":
            txt = data.decode("utf-8-sig", errors="replace")
            return "csv", txt[:MAX_CHARS], True, ""
        if ext in ("xlsx", "xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
            parts = []
            for ws in wb.worksheets:
                parts.append(f"[ورقة {ws.title}]")
                for row in ws.iter_rows(values_only=True):
                    parts.append(" | ".join("" if v is None else str(v) for v in row))
            return "xlsx", "\n".join(parts)[:MAX_CHARS], True, ""
        if ext in ("png", "jpg", "jpeg", "gif", "webp"):
            from PIL import Image
            try:
                Image.open(io.BytesIO(data)).verify()
            except Exception:
                return "other", "", False, "الملف ليس صورة صالحة"
            return "image", "", False, "صورة محفوظة وتصلح للإدراج في الشرائح. لا يوجد قراءة نصية (OCR) في هذا الإصدار"
        if ext == "doc" or ext == "ppt":
            return "other", "", False, "صيغة Office القديمة غير مدعومة. احفظها بصيغة docx أو pptx"
    except Exception as e:
        return ext or "other", "", False, f"تعذرت القراءة: {type(e).__name__}"
    return ext or "other", "", False, "صيغة غير مدعومة للقراءة. الملف محفوظ فقط"
