"""SQLite persistence: businesses (tenants), users, sessions, and jobs.

All job data is scoped to a business; every user in a business shares it.
The data directory is env-configurable (TITLEAPP_DATA_DIR) so it can point at a
persistent Railway volume in production.
"""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("TITLEAPP_DATA_DIR", os.path.join(ROOT, "data"))
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

SESSION_DAYS = 14


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS businesses (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id          INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                email                TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name                 TEXT NOT NULL,
                password_hash        TEXT NOT NULL,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                created_at           TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )"""
        )
        # Platform owners (you). Deliberately separate from business users.
        c.execute(
            """CREATE TABLE IF NOT EXISTS admins (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name          TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS admin_sessions (
                token      TEXT PRIMARY KEY,
                admin_id   INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                label       TEXT,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )"""
        )
        # Migrate older tables that predate newer columns.
        job_cols = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        if "business_id" not in job_cols:
            c.execute("ALTER TABLE jobs ADD COLUMN business_id INTEGER")
        user_cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        if "must_change_password" not in user_cols:
            c.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1")


# ----------------------------------------------------------------- businesses
def create_business(name: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO businesses (name, active, created_at) VALUES (?, 1, ?)",
            (name, _now()),
        )
        return cur.lastrowid


def get_business(business_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
    return dict(row) if row else None


def set_business_active(business_id: int, active: bool) -> None:
    with _conn() as c:
        c.execute("UPDATE businesses SET active=? WHERE id=?", (1 if active else 0, business_id))


def list_businesses() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM businesses ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------- users
def create_user(business_id: int, email: str, name: str, password_hash: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO users (business_id, email, name, password_hash, created_at) VALUES (?,?,?,?,?)",
            (business_id, email.strip(), name.strip(), password_hash, _now()),
        )
        return cur.lastrowid


def get_user_by_email(email: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone()
    return dict(row) if row else None


def get_user(user_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users(business_id: Optional[int] = None) -> list[dict]:
    with _conn() as c:
        if business_id is None:
            rows = c.execute("SELECT * FROM users ORDER BY business_id, id").fetchall()
        else:
            rows = c.execute("SELECT * FROM users WHERE business_id=? ORDER BY id", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def set_user_password(user_id: int, password_hash: str, must_change: bool = True) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE users SET password_hash=?, must_change_password=? WHERE id=?",
            (password_hash, 1 if must_change else 0, user_id),
        )


# ------------------------------------------------------------------- sessions
def create_session(user_id: int, token: str) -> None:
    now = datetime.now()
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, user_id, now.isoformat(timespec="seconds"),
             (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")),
        )


def get_session(token: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    if row["expires_at"] < _now():
        delete_session(token)
        return None
    return dict(row)


def delete_session(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ----------------------------------------------------------------------- jobs
def save_job(job_id: str, business_id: int, label: str, data: dict) -> None:
    now = _now()
    payload = json.dumps(data)
    with _conn() as c:
        exists = c.execute(
            "SELECT 1 FROM jobs WHERE id=? AND business_id=?", (job_id, business_id)
        ).fetchone()
        if exists:
            c.execute(
                "UPDATE jobs SET label=?, data=?, updated_at=? WHERE id=? AND business_id=?",
                (label, payload, now, job_id, business_id),
            )
        else:
            c.execute(
                "INSERT INTO jobs (id, business_id, label, data, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (job_id, business_id, label, payload, now, now),
            )


def get_job(job_id: str, business_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE id=? AND business_id=?", (job_id, business_id)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "data": json.loads(row["data"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_jobs(business_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, label, created_at, updated_at FROM jobs WHERE business_id=? ORDER BY updated_at DESC",
            (business_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str, business_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM jobs WHERE id=? AND business_id=?", (job_id, business_id))


# --------------------------------------------------------------------- admins
def create_admin(email: str, name: str, password_hash: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO admins (email, name, password_hash, created_at) VALUES (?,?,?,?)",
            (email.strip(), name.strip(), password_hash, _now()),
        )
        return cur.lastrowid


def get_admin_by_email(email: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM admins WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone()
    return dict(row) if row else None


def get_admin(admin_id: int) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM admins WHERE id=?", (admin_id,)).fetchone()
    return dict(row) if row else None


def list_admins() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT id, email, name, created_at FROM admins ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def create_admin_session(admin_id: int, token: str) -> None:
    now = datetime.now()
    with _conn() as c:
        c.execute(
            "INSERT INTO admin_sessions (token, admin_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, admin_id, now.isoformat(timespec="seconds"),
             (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")),
        )


def get_admin_session(token: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM admin_sessions WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    if row["expires_at"] < _now():
        delete_admin_session(token)
        return None
    return dict(row)


def delete_admin_session(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM admin_sessions WHERE token=?", (token,))
