"""
db/hris.py
Query ke database HRIS untuk cari data karyawan berdasarkan no absen.
"""

import psycopg2.extras
from db.connections import get_hris_connection
import logging
import psycopg2
from config import Config

logger = logging.getLogger(__name__)


def get_employee_by_noabsen(no_absen: str) -> dict | None:
    """
    Cari karyawan berdasarkan EmployeeNo.
    Return dict {'employee_no': ..., 'full_name': ...} atau None kalau tidak ketemu.
    """
    query = """
        SELECT e."EmployeeNo", v."FullName"
        FROM "Member"."CM_Employee" e
        JOIN "Member"."V_EmployeeName" v ON e."EmployeeId" = v."EmployeeId"
        WHERE e."EmployeeNo" = %s
        LIMIT 1
    """
    conn = None
    try:
        conn = get_hris_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, (no_absen,))
            row = cur.fetchone()
            if row:
                return {
                    "employee_no": row["EmployeeNo"],
                    "full_name": row["FullName"],
                }
            return None
    except Exception as e:
        logger.error(f"[HRIS] Error saat query karyawan {no_absen}: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_outlet_list() -> list[dict]:
    """
    Daftar outlet (kode + nama) dari CM_Division, khusus DivisionTypeId=4
    (tipe outlet) & belum dihapus. Kolom "Name" formatnya gabungan
    "KODE-NAMA" (misal "R010101-ROTI'O STASIUN JAKARTA KOTA 1"), di-split
    di sini biar cocok sama kolom Kode Outlet / Nama Outlet di form
    Berita Acara.
    """
    query = """
        SELECT "Name"
        FROM "Member"."CM_Division"
        ORDER BY "Name"
    """
    conn = None
    try:
        conn = get_hris_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query)
            hasil = []
            for row in cur.fetchall():
                kode, _, nama = row["Name"].partition("-")
                hasil.append({
                    "kode_outlet": kode.strip(),
                    "nama_outlet": (nama.strip() or kode.strip()),
                })
            return hasil
    except Exception as e:
        logger.error(f"[HRIS] Error saat ambil daftar outlet: {e}")
        return []  # gagal ambil -> form Berita Acara tetap jalan (manual), gak nge-crash
    finally:
        if conn:
            conn.close()