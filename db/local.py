"""
db/local.py
Koneksi PostgreSQL buat ITOMS.

Nama file/module ini tetap "local" (bukan "postgres") biar semua file lain yang
udah nulis `from db.local import get_conn` gak perlu diubah satu-satu — cukup
ganti isi module ini aja.

Info koneksi diambil dari config.py (Config.LOCAL_DB_*), konsisten sama HRIS/WEBSERV
yang udah ada di config.py — bukan bikin cara baru sendiri.

PENTING — beda sama versi SQLite lama:
- Placeholder tetap boleh pakai "?" di query (otomatis di-translate ke "%s").
- "INSERT OR IGNORE" SQLite TIDAK otomatis diterjemahkan — itu harus di-edit manual
  per file jadi "INSERT ... ON CONFLICT (...) DO NOTHING" (sintaks Postgres).
- conn.execute(...) tetap ada (dibungkus biar mirip sqlite3.Connection), return-nya
  punya .fetchall() / .fetchone() kayak biasa. Row hasil query tetap bisa diakses
  pakai row["nama_kolom"] (pakai RealDictCursor).
"""

import psycopg2
import psycopg2.extras
from config import Config


class _CursorResult:
    """Wrapper cursor psycopg2 biar mirip return value sqlite3 (.fetchall/.fetchone)."""

    def __init__(self, cursor):
        self._cursor = cursor

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        # Postgres gak punya lastrowid otomatis kayak SQLite.
        # Kalau butuh id abis INSERT, tambahin "RETURNING id" di query-nya,
        # terus ambil lewat .fetchone()["id"] bukan lewat .lastrowid ini.
        return None


class PGConnection:
    """Wrapper psycopg2.connection biar cara pakainya semirip mungkin sqlite3.Connection lama."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql, params=None):
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return _CursorResult(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    # Biar tetap bisa dipakai gaya "with get_conn() as conn:" kayak sebelumnya
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


def get_conn() -> PGConnection:
    raw = psycopg2.connect(
        host=Config.LOCAL_DB_HOST,
        port=Config.LOCAL_DB_PORT,
        dbname=Config.LOCAL_DB_NAME,
        user=Config.LOCAL_DB_USER,
        password=Config.LOCAL_DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    return PGConnection(raw)


def init_db():
    """Bikin semua tabel kalau belum ada (idempotent, aman dipanggil berkali-kali)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS whitelist (
        user_id BIGINT PRIMARY KEY, nama TEXT NOT NULL, no_hp TEXT,
        telegram_id_2 BIGINT, username TEXT UNIQUE, password_hash TEXT,
        is_superadmin BOOLEAN NOT NULL DEFAULT FALSE,
        permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS hari_libur (
        id SERIAL PRIMARY KEY, tanggal DATE NOT NULL UNIQUE, nama TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS jadwal (
        id SERIAL PRIMARY KEY, nama TEXT NOT NULL, tanggal DATE NOT NULL,
        tipe TEXT NOT NULL CHECK (tipe IN ('oc','piket','off')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (nama, tanggal, tipe)
    );
    CREATE TABLE IF NOT EXISTS daftar_piket (
        id SERIAL PRIMARY KEY,
        whitelist_id BIGINT NOT NULL REFERENCES whitelist(user_id) ON DELETE CASCADE,
        urutan INTEGER NOT NULL, UNIQUE (whitelist_id)
    );
    CREATE TABLE IF NOT EXISTS blackout (
        id SERIAL PRIMARY KEY,
        whitelist_id BIGINT NOT NULL REFERENCES whitelist(user_id) ON DELETE CASCADE,
        tanggal DATE NOT NULL, keterangan TEXT,
        dibuat_oleh BIGINT REFERENCES whitelist(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (whitelist_id, tanggal)
    );
    CREATE TABLE IF NOT EXISTS rolling_state (
        tipe TEXT PRIMARY KEY, last_whitelist_id BIGINT, updated_at TIMESTAMPTZ
    );
    CREATE TABLE IF NOT EXISTS komplain (
        id SERIAL PRIMARY KEY, message_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
        grup_nama TEXT, isi_pesan TEXT, pengirim TEXT,
        masuk_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS response_komplain (
        id SERIAL PRIMARY KEY,
        komplain_id INTEGER REFERENCES komplain(id) ON DELETE CASCADE,
        message_id BIGINT, chat_id BIGINT, responder_id BIGINT, responder_nama TEXT,
        isi_balasan TEXT, bales_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS task (
        id SERIAL PRIMARY KEY, judul TEXT NOT NULL, deskripsi TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','on_progress','done')),
        prioritas TEXT NOT NULL DEFAULT 'normal' CHECK (prioritas IN ('low','normal','high')),
        deadline DATE, dibuat_oleh BIGINT REFERENCES whitelist(user_id),
        komplain_id INTEGER REFERENCES komplain(id),
        progres INTEGER DEFAULT 0 CHECK (progres BETWEEN 0 AND 100),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS task_assignee (
        id SERIAL PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES whitelist(user_id),
        UNIQUE (task_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS task_comment (
        id SERIAL PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES whitelist(user_id),
        isi TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS file_meta (
        rel_path TEXT PRIMARY KEY, uploaded_by TEXT, uploaded_at TEXT,
        edited_by TEXT, edited_at TEXT
    );
    CREATE TABLE IF NOT EXISTS folder_perm (
        rel_path TEXT PRIMARY KEY,
        mode TEXT NOT NULL CHECK (mode IN ('public','private','password')),
        owner TEXT, password_hash TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS artikel (
        id SERIAL PRIMARY KEY,
        kode INTEGER NOT NULL UNIQUE,
        nama TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS check_retur (
        id SERIAL PRIMARY KEY,
        no_surat TEXT NOT NULL,
        nama_artikel TEXT NOT NULL,
        kode_artikel INTEGER,
        serial_number TEXT,
        kondisi TEXT NOT NULL CHECK (kondisi IN ('waste','ok','service')),
        foto_path TEXT,
        keterangan TEXT,
        dicek_oleh BIGINT NOT NULL REFERENCES whitelist(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        conn.execute(ddl)
        conn.commit()

        # Migrasi jaga-jaga: kalau tabel `artikel`/`check_retur` udah kebuat
        # duluan pas `kode_artikel` masih TEXT, dan/atau kolom `serial_number`
        # belum ada. Aman dijalanin berkali-kali (idempotent).
        migrasi = [
            "ALTER TABLE artikel ALTER COLUMN kode TYPE INTEGER USING kode::integer",
            "ALTER TABLE check_retur ALTER COLUMN kode_artikel TYPE INTEGER USING NULLIF(kode_artikel, '')::integer",
            "ALTER TABLE check_retur ADD COLUMN IF NOT EXISTS serial_number TEXT",
        ]
        for stmt in migrasi:
            try:
                conn.execute(stmt)
                conn.commit()
            except Exception:
                conn.rollback()  # kolomnya udah sesuai / gak perlu diubah


# ──────────────────────────────────────────
# Whitelist operations
# ──────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    """Cek apakah user_id boleh akses bot (cek user_id utama ATAU telegram_id_2)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ? OR telegram_id_2 = ?",
            (user_id, user_id)
        ).fetchone()
        return row is not None


def add_user(user_id: int, nama: str) -> bool:
    """Tambah user ke whitelist (cuma telegram, belum ada login dashboard).
    Return False kalau user_id udah ada."""
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO whitelist (user_id, nama) VALUES (?, ?)",
                (user_id, nama)
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False


def remove_user(user_id: int) -> bool:
    """Hapus user dari whitelist. Return False kalau gak ketemu atau gagal
    (misal dia masih tercatat sebagai pembuat task/blackout)."""
    with get_conn() as conn:
        try:
            cur = conn.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            return False


def list_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, nama, added_at FROM whitelist ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]


# ──────────────────────────────────────────
# Komplain operations
# ──────────────────────────────────────────

def simpan_komplain(message_id: int, chat_id: int, grup_nama: str, isi_pesan: str, pengirim: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO komplain (message_id, chat_id, grup_nama, isi_pesan, pengirim)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        """, (message_id, chat_id, grup_nama, isi_pesan, pengirim))
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id


def get_komplain_by_message(message_id: int, chat_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM komplain WHERE message_id = ? AND chat_id = ?",
            (message_id, chat_id)
        ).fetchone()
        return dict(row) if row else None


def get_komplain_terakhir(chat_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM komplain WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id,)
        ).fetchone()
        return dict(row) if row else None


def simpan_response(komplain_id: int, message_id: int, chat_id: int,
                     responder_id: int, responder_nama: str, isi_balasan: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO response_komplain
                (komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan))
        conn.commit()


# ──────────────────────────────────────────
# Jadwal operations
# ──────────────────────────────────────────

def get_jadwal_by_bulan(tahun: int, bulan: int) -> list[dict]:
    """Ambil semua jadwal dalam 1 bulan. tanggal dikembalikan sebagai string YYYY-MM-DD
    (biar cocok sama cara template jadwal.html bikin key tanggal)."""
    awal_bulan = f"{tahun}-{bulan:02d}-01"
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, nama, tanggal, tipe FROM jadwal
            WHERE tanggal >= ? AND tanggal < (?::date + INTERVAL '1 month')
            ORDER BY tanggal, tipe
        """, (awal_bulan, awal_bulan)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tanggal"] = d["tanggal"].isoformat()
            result.append(d)
        return result


def upsert_jadwal(nama: str, tanggal: str, tipe: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO jadwal (nama, tanggal, tipe) VALUES (?, ?, ?)
            ON CONFLICT (nama, tanggal, tipe) DO NOTHING
        """, (nama, tanggal, tipe))
        conn.commit()


def delete_jadwal(jadwal_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM jadwal WHERE id = ?", (jadwal_id,))
        conn.commit()


def get_all_nama_jadwal() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT nama FROM jadwal ORDER BY nama").fetchall()
        return [r["nama"] for r in rows]