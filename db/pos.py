"""
db/pos.py
Operasi ke database Webserv (webserv_sci) untuk create user POS.

Tabel : web.m_userpos
Schema dikonfirmasi dari data existing:
  name         → full_name dari HRIS
  username     → employee_no (no absen) — data baru pakai no absen
  password     → employee_no (plain text)
  pin          → employee_no
  nik          → employee_no
  m_rolepos_id → 13 (Casier)
  isactive     → 'Y'
  id           → auto increment (nextval)
  syncpjk      → default 'N'
  created_at   → default now()
  updated_at   → default now()
"""

import psycopg2.extras
from db.connections import get_webserv_connection
import logging

logger = logging.getLogger(__name__)

ROLE_CASIER_ID = 13  # m_rolepos_id untuk Casier (konfirmasi dari web.m_rolepos)


def is_user_exists(no_absen: str) -> tuple[bool, str]:
    """
    Cek apakah user sudah ada berdasarkan username ATAU pin.
    Return (True, alasan) kalau sudah ada, (False, "") kalau belum.
    """
    conn = None
    try:
        conn = get_webserv_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, username FROM web.m_userpos WHERE username = %s LIMIT 1",
                (no_absen,),
            )
            row = cur.fetchone()
            if row:
                return True, f"username <code>{no_absen}</code> sudah terdaftar atas nama <b>{row[0]}</b>"

            cur.execute(
                "SELECT name, username FROM web.m_userpos WHERE pin = %s LIMIT 1",
                (no_absen,),
            )
            row = cur.fetchone()
            if row:
                return True, f"PIN <code>{no_absen}</code> sudah dipakai oleh <b>{row[0]}</b> (username: {row[1]})"

            return False, ""
    except Exception as e:
        logger.error(f"[POS] Error cek user {no_absen}: {e}")
        raise
    finally:
        if conn:
            conn.close()


def create_pos_user(employee_no: str, full_name: str) -> bool:
    """
    Insert user baru ke web.m_userpos.

    Mapping field (sesuai data existing di DB):
      name         = full_name   (nama lengkap dari HRIS)
      username     = employee_no (no absen)
      password     = employee_no (plain text)
      pin          = employee_no
      nik          = employee_no
      m_rolepos_id = 13 (Casier)
      isactive     = 'Y'
    """
    conn = None
    try:
        conn = get_webserv_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO web.m_userpos
                    (name, username, password, pin, nik, m_rolepos_id, isactive)
                VALUES
                    (%s, %s, %s, %s, %s, %s, 'Y')
                """,
                (
                    full_name,       # name
                    employee_no,     # username  ← no absen
                    employee_no,     # password  ← plain text = no absen
                    employee_no,     # pin
                    employee_no,     # nik
                    ROLE_CASIER_ID,  # 13
                ),
            )
        conn.commit()
        logger.info(f"[POS] User dibuat: {employee_no} ({full_name})")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"[POS] Gagal create user {employee_no}: {e}")
        raise
    finally:
        if conn:
            conn.close()
