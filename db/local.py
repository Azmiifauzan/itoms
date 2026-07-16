import psycopg2
import psycopg2.extras
from config import Config


class _CursorResult:
   

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
        
        return None


class PGConnection:
    

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
    """
    with get_conn() as conn:
        conn.execute(ddl)
        conn.commit()


# ──────────────────────────────────────────
# Whitelist operations
# ──────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ? OR telegram_id_2 = ?",
            (user_id, user_id)
        ).fetchone()
        return row is not None


def add_user(user_id: int, nama: str) -> bool:
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