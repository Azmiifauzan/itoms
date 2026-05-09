"""
db/local.py
Database SQLite lokal untuk:
  - Tabel whitelist : manajemen user yang boleh akses bot
  - Tabel jadwal    : nanti (belum diimplementasi)
"""

import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Buat tabel-tabel yang dibutuhkan kalau belum ada."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id     INTEGER PRIMARY KEY,
                nama        TEXT NOT NULL,
                added_by    INTEGER,
                added_at    TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS komplain (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id   INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                grup_nama    TEXT,
                isi_pesan    TEXT,
                pengirim     TEXT,
                masuk_at     TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS response_komplain (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                komplain_id  INTEGER REFERENCES komplain(id),
                message_id   INTEGER,
                chat_id      INTEGER,
                responder_id INTEGER,
                responder_nama TEXT,
                isi_balasan  TEXT,
                bales_at     TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users_dashboard (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                username          TEXT NOT NULL UNIQUE,
                password_hash     TEXT NOT NULL,
                nama              TEXT NOT NULL,
                role              TEXT NOT NULL CHECK(role IN ('manager','kepala_support','support','programmer')),
                telegram_user_id  INTEGER,
                created_at        TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                judul        TEXT NOT NULL,
                deskripsi    TEXT,
                status       TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','on_progress','done')),
                prioritas    TEXT NOT NULL DEFAULT 'normal' CHECK(prioritas IN ('low','normal','high')),
                deadline     TEXT,
                dibuat_oleh  INTEGER REFERENCES users_dashboard(id),
                komplain_id  INTEGER REFERENCES komplain(id),
                progres      INTEGER DEFAULT 0 CHECK(progres BETWEEN 0 AND 100),
                created_at   TEXT DEFAULT (datetime('now','localtime')),
                updated_at   TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_assignee (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id  INTEGER NOT NULL REFERENCES task(id),
                user_id  INTEGER NOT NULL REFERENCES users_dashboard(id),
                UNIQUE(task_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_comment (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id    INTEGER NOT NULL REFERENCES task(id),
                user_id    INTEGER NOT NULL REFERENCES users_dashboard(id),
                isi        TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.commit()
    logger.info(f"[DB Local] SQLite siap di {DB_PATH}")


# ──────────────────────────────────────────
# Whitelist operations
# ──────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    """Cek apakah user_id ada di whitelist."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None


def add_user(user_id: int, nama: str, added_by: int) -> bool:
    """Tambah user ke whitelist. Return False kalau sudah ada."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO whitelist (user_id, nama, added_by) VALUES (?, ?, ?)",
                (user_id, nama, added_by),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # sudah ada (PRIMARY KEY conflict)


def remove_user(user_id: int) -> bool:
    """Hapus user dari whitelist. Return False kalau tidak ditemukan."""
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM whitelist WHERE user_id = ?", (user_id,)
        )
        conn.commit()
        return cur.rowcount > 0


def list_users() -> list[dict]:
    """Return semua user di whitelist."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, nama, added_by, added_at FROM whitelist ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]

# ──────────────────────────────────────────
# Komplain operations
# ──────────────────────────────────────────

def simpan_komplain(message_id: int, chat_id: int, grup_nama: str, isi_pesan: str, pengirim: str) -> int:
    """Simpan komplain baru, return id-nya."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO komplain (message_id, chat_id, grup_nama, isi_pesan, pengirim)
               VALUES (?, ?, ?, ?, ?)""",
            (message_id, chat_id, grup_nama, isi_pesan, pengirim),
        )
        conn.commit()
        return cur.lastrowid


def get_komplain_by_message(message_id: int, chat_id: int) -> dict | None:
    """Cari komplain berdasarkan message_id dan chat_id."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM komplain WHERE message_id = ? AND chat_id = ?",
            (message_id, chat_id),
        ).fetchone()
        return dict(row) if row else None


def get_komplain_terakhir(chat_id: int) -> dict | None:
    """Ambil komplain terakhir di grup ini."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM komplain WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None


def simpan_response(komplain_id: int, message_id: int, chat_id: int,
                    responder_id: int, responder_nama: str, isi_balasan: str):
    """Simpan response dari whitelist member."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO response_komplain
               (komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan),
        )
        conn.commit()