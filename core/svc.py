"""Service layer. Every function takes uid and filters by it: users never see each other's data."""
import json, datetime as dt, io
from sqlalchemy import select, delete, func, or_
from . import db, gen, quality, export as ex, extract as xt, ai
from .db import (Project, Source, Output, OutputVersion, ExportFile, Task, Activity, Notification,
                 QualityReview, AIJob)

STATUS_AR = {"draft": "مسودة", "planning": "تخطيط", "processing": "قيد الإنتاج", "review": "مراجعة",
             "revision": "تعديل", "completed": "مكتمل", "failed": "فشل",
             "pending": "بانتظار", "ready": "جاهز", "needs_review": "يحتاج مراجعة", "exported": "تم التصدير"}


def _p(r):
    return {"id": r.id, "name": r.name, "description": r.description, "ptype": r.ptype, "stage": r.stage,
            "grade": r.grade, "subject": r.subject, "difficulty": r.difficulty, "audience": r.audience,
            "objectives": db.jl(r.objectives, []), "settings": db.jl(r.settings, {}), "status": r.status,
            "notes": r.notes, "rating": r.rating, "created_at": r.created_at, "updated_at": r.updated_at}


def _s(r, with_blob=False):
    d = {"id": r.id, "project_id": r.project_id, "title": r.title, "kind": r.kind, "url": r.url, "filename": r.filename,
         "category": r.category, "tags": r.tags, "version": r.version, "content": r.content, "readable": r.readable,
         "read_note": r.read_note, "size": r.size, "created_at": r.created_at, "accessed_at": r.accessed_at}
    if with_blob:
        d["blob"] = r.blob
    return d


def _o(r):
    return {"id": r.id, "project_id": r.project_id, "kind": r.kind, "subtype": r.subtype, "title": r.title,
            "content": db.jl(r.content, {}), "status": r.status, "generator": r.generator, "version": r.version,
            "source_ids": db.jl(r.source_ids, []), "quality_override": r.quality_override,
            "created_at": r.created_at, "updated_at": r.updated_at}


# ---------- projects ----------
def create_project(uid, data):
    with db.session() as s:
        p = Project(user_id=uid, name=data["name"].strip()[:255], description=data.get("description", ""),
                    ptype=data.get("ptype", "lesson"), stage=data.get("stage", ""), grade=data.get("grade", ""),
                    subject=data.get("subject", ""), difficulty=data.get("difficulty", "متوسط"),
                    audience=data.get("audience", ""), objectives=json.dumps(data.get("objectives", []), ensure_ascii=False),
                    settings=json.dumps(data.get("settings", {}), ensure_ascii=False), status=data.get("status", "draft"))
        s.add(p)
        s.flush()
        pid = p.id
    db.log(uid, "project_created", data["name"], pid)
    return pid


def get_project(uid, pid):
    with db.session() as s:
        r = s.get(Project, pid)
        return _p(r) if r and r.user_id == uid else None


def update_project(uid, pid, **fields):
    with db.session() as s:
        r = s.get(Project, pid)
        if not r or r.user_id != uid:
            return False
        for k, v in fields.items():
            if k in ("objectives", "settings"):
                v = json.dumps(v, ensure_ascii=False)
            setattr(r, k, v)
    db.log(uid, "project_updated", ",".join(fields), pid)
    return True


def list_projects(uid, q="", status="", ptype=""):
    with db.session() as s:
        stmt = select(Project).where(Project.user_id == uid)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Project.name.ilike(like), Project.description.ilike(like), Project.subject.ilike(like), Project.notes.ilike(like)))
        if status:
            stmt = stmt.where(Project.status == status)
        if ptype:
            stmt = stmt.where(Project.ptype == ptype)
        return [_p(r) for r in s.execute(stmt.order_by(Project.updated_at.desc())).scalars()]


def delete_project(uid, pid):
    with db.session() as s:
        r = s.get(Project, pid)
        if not r or r.user_id != uid:
            return False
        name = r.name
        oids = [o for (o,) in s.execute(select(Output.id).where(Output.project_id == pid))]
        if oids:
            s.execute(delete(OutputVersion).where(OutputVersion.output_id.in_(oids)))
            s.execute(delete(QualityReview).where(QualityReview.output_id.in_(oids)))
        s.execute(delete(Output).where(Output.project_id == pid))
        s.execute(delete(ExportFile).where(ExportFile.project_id == pid))
        s.execute(delete(Task).where(Task.project_id == pid))
        s.execute(delete(Source).where(Source.project_id == pid, Source.user_id == uid))
        s.delete(r)
    db.log(uid, "project_deleted", name)
    return True


def duplicate_project(uid, pid):
    p = get_project(uid, pid)
    if not p:
        return None
    p["name"] = p["name"] + " (نسخة)"
    p["status"] = "draft"
    new = create_project(uid, p)
    for src in list_sources(uid, pid):
        full = get_source(uid, src["id"])
        with db.session() as s:
            r = s.get(Source, src["id"])
            s.add(Source(user_id=uid, project_id=new, title=r.title, kind=r.kind, url=r.url, filename=r.filename, mime=r.mime,
                         category=r.category, tags=r.tags, content=r.content, readable=r.readable, read_note=r.read_note,
                         blob=r.blob, size=r.size))
    for o in list_outputs(uid, pid):
        with db.session() as s:
            s.add(Output(user_id=uid, project_id=new, kind=o["kind"], subtype=o["subtype"], title=o["title"],
                         content=json.dumps(o["content"], ensure_ascii=False), status="needs_review", generator=o["generator"],
                         source_ids="[]"))
    db.log(uid, "project_duplicated", f"{pid}->{new}", new)
    return new


# ---------- sources ----------
def add_source(uid, pid, title, kind, filename="", data=None, url="", content="", category="", tags=""):
    readable, note = True, ""
    if data is not None:
        kind, content, readable, note = xt.extract(filename, data)
    elif kind == "link":
        readable, note = False, "رابط مرجعي مسجل فقط. لم يتم جلب محتواه"
    with db.session() as s:
        ver = 1
        if filename:
            prev = s.execute(select(func.max(Source.version)).where(Source.user_id == uid, Source.filename == filename,
                                                                    Source.project_id == pid)).scalar()
            ver = (prev or 0) + 1
        r = Source(user_id=uid, project_id=pid, title=(title or filename or url)[:255], kind=kind, url=url[:1000],
                   filename=filename, content=content, readable=readable, read_note=note, blob=data,
                   size=len(data) if data else len(content.encode()), category=category, tags=tags, version=ver)
        s.add(r)
        s.flush()
        sid = r.id
    db.log(uid, "source_added", title or filename or url, pid)
    return sid, readable, note


def list_sources(uid, pid=None, q="", tag="", category=""):
    with db.session() as s:
        stmt = select(Source).where(Source.user_id == uid)
        if pid is not None:
            stmt = stmt.where(Source.project_id == pid)
        if q:
            stmt = stmt.where(or_(Source.title.ilike(f"%{q}%"), Source.content.ilike(f"%{q}%"), Source.filename.ilike(f"%{q}%")))
        if tag:
            stmt = stmt.where(Source.tags.ilike(f"%{tag}%"))
        if category:
            stmt = stmt.where(Source.category == category)
        return [_s(r) for r in s.execute(stmt.order_by(Source.created_at.desc())).scalars()]


def get_source(uid, sid):
    with db.session() as s:
        r = s.get(Source, sid)
        return _s(r, True) if r and r.user_id == uid else None


def update_source(uid, sid, **f):
    with db.session() as s:
        r = s.get(Source, sid)
        if not r or r.user_id != uid:
            return False
        for k, v in f.items():
            setattr(r, k, v)
    return True


def delete_source(uid, sid):
    with db.session() as s:
        r = s.get(Source, sid)
        if r and r.user_id == uid:
            s.delete(r)
            return True
    return False


# ---------- outputs ----------
def list_outputs(uid, pid):
    with db.session() as s:
        return [_o(r) for r in s.execute(select(Output).where(Output.user_id == uid, Output.project_id == pid).order_by(Output.id)).scalars()]


def get_output(uid, oid):
    with db.session() as s:
        r = s.get(Output, oid)
        return _o(r) if r and r.user_id == uid else None


def save_output(uid, oid, content, note="تعديل يدوي", title=None):
    with db.session() as s:
        r = s.get(Output, oid)
        if not r or r.user_id != uid:
            return False
        s.add(OutputVersion(output_id=oid, user_id=uid, version=r.version, content=r.content, note=note))
        r.content = json.dumps(content, ensure_ascii=False)
        r.version += 1
        r.status = "needs_review"
        if title:
            r.title = title
        pid = r.project_id
    db.log(uid, "output_saved", f"#{oid} v{r.version}", pid)
    return True


def versions(uid, oid):
    with db.session() as s:
        return [{"id": v.id, "version": v.version, "note": v.note, "created_at": v.created_at, "content": db.jl(v.content, {})}
                for v in s.execute(select(OutputVersion).where(OutputVersion.output_id == oid, OutputVersion.user_id == uid)
                                   .order_by(OutputVersion.version.desc())).scalars()]


def delete_output(uid, oid):
    with db.session() as s:
        r = s.get(Output, oid)
        if not r or r.user_id != uid:
            return False
        s.execute(delete(OutputVersion).where(OutputVersion.output_id == oid))
        s.execute(delete(QualityReview).where(QualityReview.output_id == oid))
        s.delete(r)
    return True


def _selected_sources(uid, pid):
    return [x for x in list_sources(uid, pid) if x["readable"] and x["content"]]


def produce(uid, pid, kind, subtype="", n=8, progress=None):
    """Create one output. Status flow: processing -> needs_review (or failed). Returns (oid, error)."""
    p = get_project(uid, pid)
    if not p:
        return None, "المشروع غير موجود أو لا تملك صلاحية الوصول إليه"
    srcs = _selected_sources(uid, pid)
    with db.session() as s:
        o = Output(user_id=uid, project_id=pid, kind=kind, subtype=subtype, title="", status="processing",
                   source_ids=json.dumps([x["id"] for x in srcs]))
        s.add(o)
        s.flush()
        oid = o.id
    try:
        if kind == "presentation":
            content, gname = gen.make_presentation(uid, p, srcs, n)
        elif kind == "document":
            content, gname = gen.make_document(uid, p, srcs, subtype or "lesson_plan")
        elif kind in ("worksheet", "assessment"):
            content, gname = gen.make_questions(uid, p, srcs, kind, n)
        else:
            raise ValueError("نوع غير مدعوم")
        title = content.get("title") or p["name"]
        with db.session() as s:
            o = s.get(Output, oid)
            o.content, o.title, o.generator, o.status = json.dumps(content, ensure_ascii=False), title, gname, "needs_review"
        db.log(uid, "output_generated", f"{kind} via {gname}", pid)
        run_review(uid, oid)
        return oid, ""
    except Exception as e:
        msg = "لم يتوفر مزود ذكاء اصطناعي مُختبر" if "no_provider" in str(e) else f"{type(e).__name__}: {str(e)[:200]}"
        with db.session() as s:
            o = s.get(Output, oid)
            o.status, o.title = "failed", f"فشل: {kind}"
        db.log(uid, "output_failed", msg, pid)
        db.notify(uid, f"فشل إنتاج {kind}: {msg}", "error")
        return oid, msg


def run_production(uid, pid, plan, progress=None):
    update_project(uid, pid, status="processing")
    results = []
    order = {"document": 0, "presentation": 1, "worksheet": 2, "assessment": 3}
    plan = sorted(plan, key=lambda x: order.get(x["kind"], 9))
    for i, item in enumerate(plan):
        if progress:
            progress(i / max(1, len(plan)), f"إنتاج {gen.OUTPUT_KINDS.get(item['kind'], item['kind'])}...")
        oid, err = produce(uid, pid, item["kind"], item.get("subtype", ""), item.get("n", 8))
        if err:  # one retry for failed jobs (orchestrator-level)
            oid, err = produce(uid, pid, item["kind"], item.get("subtype", ""), item.get("n", 8))
        results.append((item["kind"], oid, err))
    failed = [r for r in results if r[2]]
    update_project(uid, pid, status="failed" if len(failed) == len(results) and results else "review")
    if progress:
        progress(1.0, "اكتمل")
    db.notify(uid, f"اكتمل إنتاج المشروع #{pid}: {len(results)-len(failed)} نجح، {len(failed)} فشل", "success" if not failed else "warning")
    return results


# ---------- quality ----------
def run_review(uid, oid):
    o = get_output(uid, oid)
    p = get_project(uid, o["project_id"])
    r = quality.review(o["kind"], o["content"], p, len(o["source_ids"]), o["generator"])
    r["output_version"] = o["version"]
    with db.session() as s:
        s.add(QualityReview(user_id=uid, output_id=oid, score=r["score"], verdict=r["verdict"], detail=json.dumps(r, ensure_ascii=False)))
        ob = s.get(Output, oid)
        ob.status = "ready" if r["verdict"] == "approved" else "needs_review"
    db.log(uid, "quality_review", f"#{oid} {r['score']} {r['verdict']}", o["project_id"])
    return r


def latest_review(uid, oid):
    with db.session() as s:
        r = s.execute(select(QualityReview).where(QualityReview.output_id == oid, QualityReview.user_id == uid)
                      .order_by(QualityReview.id.desc())).scalars().first()
        return {**db.jl(r.detail, {}), "at": r.created_at} if r else None


def override_gate(uid, oid, reason):
    with db.session() as s:
        o = s.get(Output, oid)
        if not o or o.user_id != uid or len(reason.strip()) < 5:
            return False
        o.quality_override = reason.strip()
        pid = o.project_id
    db.log(uid, "quality_gate_overridden", f"#{oid}: {reason[:200]}", pid)
    return True


def gate_open(uid, oid):
    o = get_output(uid, oid)
    r = latest_review(uid, oid)
    return bool(r and r["verdict"] == "approved" and r.get("output_version") == o["version"]) or bool(o["quality_override"])


# ---------- export ----------
def do_export(uid, oid, fmt):
    o = get_output(uid, oid)
    if not o:
        return None, "غير موجود"
    if not gate_open(uid, oid):
        return None, "بوابة الجودة مغلقة: أعد المراجعة بعد التعديل، أو سجّل تجاوزًا مع السبب"
    images = {}
    if o["kind"] == "presentation":
        for sl in o["content"]["slides"]:
            sid = sl.get("image_source_id")
            if sid:
                s_ = get_source(uid, sid)
                if s_ and s_["blob"] and s_["kind"] == "image":
                    images[sid] = s_["blob"]
    try:
        p = get_project(uid, o["project_id"])
        data, msg = ex.export(o["kind"], o["content"], fmt, images, {"brand": p["settings"].get("brand", "")})
    except Exception as e:
        db.log(uid, "export_failed", f"{fmt}: {type(e).__name__}", o["project_id"])
        return None, f"فشل التصدير: {type(e).__name__}: {str(e)[:150]}"
    name = f"{o['title'] or 'output'}-v{o['version']}.{fmt}".replace("/", "-").replace(":", "-")
    with db.session() as s:
        f = ExportFile(user_id=uid, project_id=o["project_id"], output_id=oid, name=name, fmt=fmt, blob=data, size=len(data), verified=msg)
        s.add(f)
        ob = s.get(Output, oid)
        ob.status = "ready" if ob.status == "ready" else ob.status
        s.flush()
        fid = f.id
    db.log(uid, "exported", f"{name} ({msg})", o["project_id"])
    return fid, msg


def list_exports(uid, pid=None):
    with db.session() as s:
        stmt = select(ExportFile.id, ExportFile.name, ExportFile.fmt, ExportFile.size, ExportFile.verified, ExportFile.created_at, ExportFile.project_id).where(ExportFile.user_id == uid)
        if pid is not None:
            stmt = stmt.where(ExportFile.project_id == pid)
        return [dict(zip(["id", "name", "fmt", "size", "verified", "created_at", "project_id"], r)) for r in s.execute(stmt.order_by(ExportFile.id.desc()))]


def get_export(uid, fid):
    with db.session() as s:
        r = s.get(ExportFile, fid)
        return {"name": r.name, "fmt": r.fmt, "blob": r.blob, "verified": r.verified} if r and r.user_id == uid else None


def rename_export(uid, fid, name):
    with db.session() as s:
        r = s.get(ExportFile, fid)
        if r and r.user_id == uid and name.strip():
            r.name = name.strip()[:255]
            return True
    return False


def delete_export(uid, fid):
    with db.session() as s:
        r = s.get(ExportFile, fid)
        if r and r.user_id == uid:
            s.delete(r)
            return True
    return False


def zip_project(uid, pid):
    files = [(f["name"], get_export(uid, f["id"])["blob"]) for f in list_exports(uid, pid)]
    if not files:
        return None
    d = ex.zip_bytes(files)
    ex.verify_zip(d)
    return d


# ---------- tasks / dashboard ----------
def add_task(uid, title, pid=None, priority="medium", due=""):
    with db.session() as s:
        s.add(Task(user_id=uid, project_id=pid, title=title[:300], priority=priority, due=due))
    db.log(uid, "task_added", title, pid)


def list_tasks(uid, pid=None, open_only=False):
    with db.session() as s:
        stmt = select(Task).where(Task.user_id == uid)
        if pid is not None:
            stmt = stmt.where(Task.project_id == pid)
        if open_only:
            stmt = stmt.where(Task.status != "done")
        return [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority, "due": t.due, "project_id": t.project_id}
                for t in s.execute(stmt.order_by(Task.id.desc())).scalars()]


def set_task(uid, tid, status):
    with db.session() as s:
        t = s.get(Task, tid)
        if t and t.user_id == uid:
            t.status = status


def delete_task(uid, tid):
    with db.session() as s:
        t = s.get(Task, tid)
        if t and t.user_id == uid:
            s.delete(t)


def activity(uid, pid=None, limit=30):
    with db.session() as s:
        stmt = select(Activity).where(Activity.user_id == uid)
        if pid is not None:
            stmt = stmt.where(Activity.project_id == pid)
        return [{"action": a.action, "detail": a.detail, "at": a.created_at} for a in s.execute(stmt.order_by(Activity.id.desc()).limit(limit)).scalars()]


def notifications(uid, limit=10):
    with db.session() as s:
        return [{"id": n.id, "message": n.message, "level": n.level, "read": n.read, "at": n.created_at}
                for n in s.execute(select(Notification).where(Notification.user_id == uid).order_by(Notification.id.desc()).limit(limit)).scalars()]


def mark_notifications_read(uid):
    with db.session() as s:
        for n in s.execute(select(Notification).where(Notification.user_id == uid, Notification.read == False)).scalars():
            n.read = True


def stats(uid):
    with db.session() as s:
        pr = dict(s.execute(select(Project.status, func.count()).where(Project.user_id == uid).group_by(Project.status)).all())
        out = dict(s.execute(select(Output.kind, func.count()).where(Output.user_id == uid).group_by(Output.kind)).all())
        ost = dict(s.execute(select(Output.status, func.count()).where(Output.user_id == uid).group_by(Output.status)).all())
        files = s.execute(select(func.count()).select_from(Source).where(Source.user_id == uid)).scalar()
        exps = s.execute(select(func.count()).select_from(ExportFile).where(Export_uid(uid))).scalar() if False else s.execute(
            select(func.count()).select_from(ExportFile).where(ExportFile.user_id == uid)).scalar()
        jobs = s.execute(select(func.count(), func.coalesce(func.sum(AIJob.tokens_in), 0), func.coalesce(func.sum(AIJob.tokens_out), 0))
                         .where(AIJob.user_id == uid, AIJob.provider != "local")).one()
    return {"projects": pr, "outputs": out, "output_status": ost, "sources": files, "exports": exps,
            "ai_jobs": jobs[0], "tokens_in": jobs[1], "tokens_out": jobs[2]}


def ai_jobs(uid, limit=20):
    with db.session() as s:
        return [{"module": j.module, "provider": j.provider, "model": j.model, "status": j.status, "attempts": j.attempts,
                 "error": j.error, "tin": j.tokens_in, "tout": j.tokens_out, "at": j.created_at}
                for j in s.execute(select(AIJob).where(AIJob.user_id == uid).order_by(AIJob.id.desc()).limit(limit)).scalars()]


def analytics(uid):
    """Real aggregates over the user's own data. Nothing is estimated."""
    from collections import Counter
    with db.session() as s:
        outs = s.execute(select(Output).where(Output.user_id == uid)).scalars().all()
        gens = Counter(o.generator or "?" for o in outs)
        kinds = Counter(o.kind for o in outs)
        status = Counter(o.status for o in outs)
        versions = dict(s.execute(select(OutputVersion.output_id, func.count()).where(OutputVersion.user_id == uid).group_by(OutputVersion.output_id)).all())
        fmts = Counter(f for (f,) in s.execute(select(ExportFile.fmt).where(ExportFile.user_id == uid)).all())
        jobs = s.execute(select(AIJob.status, func.count()).where(AIJob.user_id == uid, AIJob.provider != "local").group_by(AIJob.status)).all()
        days = Counter(a.created_at.strftime("%Y-%m-%d") for a in s.execute(select(Activity).where(Activity.user_id == uid)).scalars() if a.created_at)
        srcs = s.execute(select(Source.readable, func.count()).where(Source.user_id == uid).group_by(Source.readable)).all()
        edited = sum(1 for o in outs if versions.get(o.id, 0) > 0)
    return {"outputs": len(outs), "kinds": dict(kinds), "status": dict(status), "generators": dict(gens), "exports": dict(fmts),
            "ai_jobs": {k: n for k, n in jobs}, "activity_days": dict(sorted(days.items())[-14:]),
            "sources": {"readable": sum(n for r, n in srcs if r), "unreadable": sum(n for r, n in srcs if not r)},
            "edited": edited, "total_versions": sum(versions.values())}
