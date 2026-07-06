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
                role              TEXT NOT NULL CHECK(role IN ('superadmin','manager','kepala_support','support','programmer')),
                telegram_user_id  INTEGER,
                created_at        TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whitelist_telegram (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                whitelist_id     INTEGER NOT NULL REFERENCES whitelist(id),
                telegram_user_id INTEGER NOT NULL,
                label            TEXT,
                UNIQUE(whitelist_id, telegram_user_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS hari_libur (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT NOT NULL UNIQUE,
                nama    TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS daftar_piket (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                whitelist_id INTEGER NOT NULL UNIQUE REFERENCES whitelist(id),
                urutan       INTEGER NOT NULL
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jadwal (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nama        TEXT NOT NULL,
                tanggal     TEXT NOT NULL,
                tipe        TEXT NOT NULL CHECK(tipe IN ('oc', 'piket', 'off')),
                created_at  TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(nama, tanggal, tipe)
            )
        """)
        conn.commit()
    logger.info(f"[DB Local] SQLite siap di {DB_PATH}")


# ──────────────────────────────────────────
# Whitelist operations
# ──────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    """Cek apakah user_id ada di whitelist — cek tabel utama dan whitelist_telegram."""
    with get_conn() as conn:
        # Cek tabel utama
        row = conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return True
        # Cek tabel whitelist_telegram
        row = conn.execute(
            "SELECT 1 FROM whitelist_telegram WHERE telegram_user_id = ?", (user_id,)
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
# Whitelist Telegram operations
# ──────────────────────────────────────────

def get_telegram_ids(whitelist_user_id: int) -> list[dict]:
    """Ambil semua telegram ID untuk satu whitelist user."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM whitelist_telegram WHERE whitelist_id = ? ORDER BY id",
            (whitelist_user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_telegram_id(whitelist_user_id: int, telegram_user_id: int, label: str = None) -> bool:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO whitelist_telegram (whitelist_id, telegram_user_id, label) VALUES (?, ?, ?)",
                (whitelist_user_id, telegram_user_id, label)
            )
            conn.commit()
        return True
    except Exception:
        return False

def remove_telegram_id(telegram_id: int):
    """Hapus telegram ID berdasarkan ID row."""
    with get_conn() as conn:
        conn.execute("DELETE FROM whitelist_telegram WHERE id = ?", (telegram_id,))
        conn.commit()


def get_all_telegram_ids_for_user(whitelist_id: int) -> list[int]:
    """Return list telegram_user_id untuk satu whitelist user."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT telegram_user_id FROM whitelist_telegram WHERE whitelist_id = ?",
            (whitelist_id,)
        ).fetchall()
        return [r["telegram_user_id"] for r in rows]


def get_whitelist_by_telegram_id(telegram_user_id: int) -> dict | None:
    """Cari whitelist user berdasarkan telegram_user_id (cek tabel lama dan baru)."""
    with get_conn() as conn:
        # Cek tabel whitelist_telegram dulu
        row = conn.execute("""
            SELECT w.* FROM whitelist w
            JOIN whitelist_telegram wt ON w.id = wt.whitelist_id
            WHERE wt.telegram_user_id = ?
            LIMIT 1
        """, (telegram_user_id,)).fetchone()
        if row:
            return dict(row)
        # Fallback ke kolom lama
        row = conn.execute(
            "SELECT * FROM whitelist WHERE user_id = ? LIMIT 1",
            (telegram_user_id,)
        ).fetchone()
        return dict(row) if row else None

# ──────────────────────────────────────────
# Jadwal operations
# ──────────────────────────────────────────

def get_jadwal_by_tanggal(tanggal: str) -> list[dict]:
    """Ambil semua jadwal di tanggal tertentu."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jadwal WHERE tanggal = ? ORDER BY tipe",
            (tanggal,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_jadwal_by_bulan(tahun: int, bulan: int) -> list[dict]:
    """Ambil semua jadwal dalam satu bulan."""
    prefix = f"{tahun}-{bulan:02d}"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jadwal WHERE tanggal LIKE ? ORDER BY tanggal, tipe",
            (f"{prefix}%",)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_jadwal(nama: str, tanggal: str, tipe: str):
    """Insert atau update jadwal."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO jadwal (nama, tanggal, tipe)
            VALUES (?, ?, ?)
            ON CONFLICT(nama, tanggal, tipe) DO NOTHING
        """, (nama, tanggal, tipe))
        conn.commit()


def delete_jadwal(jadwal_id: int):
    """Hapus jadwal berdasarkan ID."""
    with get_conn() as conn:
        conn.execute("DELETE FROM jadwal WHERE id = ?", (jadwal_id,))
        conn.commit()


def get_jadwal_hari_ini(tipe: str) -> list[dict]:
    """Ambil jadwal hari ini berdasarkan tipe (oc/piket)."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT j.*, w.telegram_user_id FROM jadwal j "
            "LEFT JOIN whitelist w ON j.nama = w.nama_jadwal "
            "WHERE j.tanggal = ? AND j.tipe = ?",
            (today, tipe)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_nama_jadwal() -> list[str]:
    """Ambil semua nama unik yang ada di jadwal."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT nama FROM jadwal ORDER BY nama"
        ).fetchall()
        return [r["nama"] for r in rows]

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