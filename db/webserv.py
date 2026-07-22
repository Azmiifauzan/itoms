"""
db/webserv.py
Koneksi (read-only) ke database webserv/Adempiere -- dipakai buat ambil
data referensi kayak daftar outlet. Sengaja dipisah dari db/local.py karena
ini database yang beda & cuma dibaca doang, gak pernah ditulis dari sini.
"""

import logging
import psycopg2
import psycopg2.extras
from config import Config

logger = logging.getLogger(__name__)


def get_webserv_conn():
    return psycopg2.connect(
        host=Config.WEBSERV_HOST,
        port=Config.WEBSERV_PORT,
        dbname=Config.WEBSERV_DATABASE,
        user=Config.WEBSERV_USER,
        password=Config.WEBSERV_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=5,
    )


def get_outlet_list() -> list[dict]:
    """Daftar outlet aktif (kode + nama) dari m_warehouse, buat referensi
    form Berita Acara (dan form lain yang butuh pilih outlet).

    Kalau koneksi ke webserv lagi gak bisa (server down, dsb), balikin list
    kosong aja -- biar form tetap bisa dipakai manual (ketik bebas), gak
    bikin seluruh halaman Berita Acara error cuma gara-gara ini.
    """
    try:
        conn = get_webserv_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT value AS kode_outlet, name AS nama_outlet
                FROM web.m_warehouse
                WHERE isactive = 'Y'
                ORDER BY name
            """)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[webserv] Gagal ambil daftar outlet: {e}")
        return []