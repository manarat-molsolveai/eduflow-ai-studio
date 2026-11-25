"""Database layer (SQLAlchemy). SQLite by default; PostgreSQL when DATABASE_URL is set."""
import os, json, datetime as dt
from contextlib import contextmanager
from sqlalchemy import (create_engine, Column, Integer, String, Text, DateTime, LargeBinary,
                        ForeignKey, Boolean, Float, text, select, func)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()
SCHEMA_VERSION = 3


def now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), default="")
    pw_hash = Column(String(512), nullable=False)
    role = Column(String(30), default="teacher")
    failed = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


class SessionTok(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    token_hash = Column(String(128), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    expires_at = Column(DateTime)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    ptype = Column(String(60), default="lesson")
    stage = Column(String(60), default="")
    grade = Column(String(60), default="")
    subject = Column(String(120), default="")
    difficulty = Column(String(30), default="متوسط")
    audience = Column(Text, default="")
    objectives = Column(Text, default="[]")  # JSON list
    settings = Column(Text, default="{}")  # JSON dict (design prefs, plan)
    status = Column(String(30), default="draft")
    notes = Column(Text, default="")
    rating = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), default="")
    kind = Column(String(30), default="text")  # text|pdf|docx|pptx|image|link|note|csv|xlsx|other
    url = Column(String(1000), default="")
    filename = Column(String(255), default="")
    mime = Column(String(120), default="")
    category = Column(String(80), default="")
    tags = Column(String(500), default="")
    version = Column(Integer, default=1)
    content = Column(Text, default="")  # extracted text (empty when unreadable)
    readable = Column(Boolean, default=True)
    read_note = Column(String(300), default="")
    blob = Column(LargeBinary, nullable=True)
    size = Column(Integer, default=0)
    accessed_at = Column(DateTime, default=now)
    created_at = Column(DateTime, default=now)


class Output(Base):
    __tablename__ = "outputs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind = Column(String(30))  # presentation|document|worksheet|assessment
    subtype = Column(String(60), default="")
    title = Column(String(255), default="")
    content = Column(Text, default="{}")  # JSON
    status = Column(String(30), default="pending")
    generator = Column(String(80), default="")
    is_demo = Column(Boolean, default=False)
    version = Column(Integer, default=1)
    source_ids = Column(String(500), default="[]")
    quality_override = Column(Text, default="")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class OutputVersion(Base):
    __tablename__ = "output_versions"
    id = Column(Integer, primary_key=True)
    output_id = Column(Integer, ForeignKey("outputs.id", ondelete="CASCADE"), index=True)
    user_id = Column(Integer, index=True)
    version = Column(Integer)
    content = Column(Text)
    note = Column(String(300), default="")
    created_at = Column(DateTime, default=now)


class ExportFile(Base):
    __tablename__ = "export_files"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    output_id = Column(Integer, nullable=True)
    name = Column(String(255))
    fmt = Column(String(20))
    blob = Column(LargeBinary)
    size = Column(Integer, default=0)
    verified = Column(String(300), default="")
    created_at = Column(DateTime, default=now)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(300))
    status = Column(String(20), default="todo")  # todo|doing|done
    priority = Column(String(20), default="medium")
    due = Column(String(20), default="")
    created_at = Column(DateTime, default=now)


class Activity(Base):
    __tablename__ = "activity"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    action = Column(String(80))
    detail = Column(String(500), default="")
    created_at = Column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    message = Column(String(500))
    level = Column(String(20), default="info")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class QualityReview(Base):
    __tablename__ = "quality_reviews"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    output_id = Column(Integer, ForeignKey("outputs.id", ondelete="CASCADE"), index=True)
    score = Column(Float)
    verdict = Column(String(30))
    detail = Column(Text, default="{}")
    method = Column(String(60), default="rules-v1")
    created_at = Column(DateTime, default=now)


class AIJob(Base):
    __tablename__ = "ai_jobs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    project_id = Column(Integer, nullable=True)
    module = Column(String(60))
    provider = Column(String(30), default="local")
    model = Column(String(80), default="")
    status = Column(String(20), default="running")
    attempts = Column(Integer, default=0)
    error = Column(Text, default="")
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    finished_at = Column(DateTime, nullable=True)


class UserSetting(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    key = Column(String(80))
    value = Column(Text, default="")


class Meta(Base):
    __tablename__ = "meta"
    key = Column(String(50), primary_key=True)
    value = Column(String(200))


_engine = None
_Session = None


def db_url():
    url = os.environ.get("DATABASE_URL", "")
    try:
        import streamlit as st
        url = url or st.secrets.get("DATABASE_URL", "")
    except Exception:
        pass
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url or "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(__file__)), "eduflow.db")


def backend_name():
    return "PostgreSQL" if db_url().startswith("postgresql") else "SQLite"


def init():
    global _engine, _Session
    if _engine is not None:
        return _engine
    url = db_url()
    kw = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
    _engine = create_engine(url, **kw)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    migrate()
    return _engine


def migrate():
    """Tiny versioned migrations. v1: base tables; v2: outputs.quality_override; v3: sources.read_note."""
    with session() as s:
        row = s.get(Meta, "schema_version")
        cur = int(row.value) if row else 0
        insp_cols = lambda t: [r[1] if not hasattr(r, "_mapping") else r[1] for r in s.execute(text(f"PRAGMA table_info({t})"))] if backend_name() == "SQLite" else [r[0] for r in s.execute(text("select column_name from information_schema.columns where table_name=:t"), {"t": t})]
        def addcol(table, col, ddl):
            if col not in insp_cols(table):
                s.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        if cur < SCHEMA_VERSION:
            addcol("outputs", "quality_override", "TEXT DEFAULT ''")
            addcol("sources", "read_note", "VARCHAR(300) DEFAULT ''")
            if row:
                row.value = str(SCHEMA_VERSION)
            else:
                s.add(Meta(key="schema_version", value=str(SCHEMA_VERSION)))


@contextmanager
def session():
    init_needed = _Session is None
    if init_needed:
        init()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def log(uid, action, detail="", project_id=None):
    with session() as s:
        s.add(Activity(user_id=uid, project_id=project_id, action=action, detail=detail[:500]))


def notify(uid, message, level="info"):
    with session() as s:
        s.add(Notification(user_id=uid, message=message[:500], level=level))


def jl(v, default=None):
    try:
        return json.loads(v) if v else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}
