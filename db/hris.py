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

def search_employee(query: str, company_id: int, limit: int = 15) -> list[dict]:
    """
    Cari karyawan by EmployeeNo ATAU FullName sekaligus -- dipakai buat
    autocomplete field 'Nama Karyawan' di form Berita Acara mode Office.
    Discope per company_id biar hasilnya relevan sama PT yang lagi dipilih.
    Balikin FullName + DivisionName, siap langsung dipakai ngisi form
    (gak perlu request tambahan lagi pas user milih salah satu hasil).
    """
    like = f"%{query}%"
    sql = """
        SELECT e."EmployeeNo", v."FullName", TRIM(d."Name") AS "DivisionName"
        FROM "Member"."CM_Employee" e
        JOIN "Member"."V_EmployeeName" v ON e."EmployeeId" = v."EmployeeId"
        LEFT JOIN "Member"."CM_JobTitle" jt ON e."JobTitleId" = jt."JobTitleId"
        LEFT JOIN "Member"."CM_Division" d ON jt."DivisionId" = d."Id"
        WHERE e."CompanyId" = %s
          AND e."DeletedDate" IS NULL
          AND (e."EmployeeNo" ILIKE %s OR v."FullName" ILIKE %s)
        ORDER BY v."FullName"
        LIMIT %s
    """
    conn = None
    try:
        conn = get_hris_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (company_id, like, like, limit))
            return [
                {
                    "employee_no": r["EmployeeNo"],
                    "full_name": r["FullName"],
                    "division_name": r["DivisionName"] or "",
                }
                for r in cur.fetchall()
            ]
    except Exception as e:
        logger.error(f"[HRIS] Error saat search karyawan '{query}': {e}")
        return []
    finally:
        if conn:
            conn.close()