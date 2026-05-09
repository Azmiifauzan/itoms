"""
db/hris.py
Query ke database HRIS untuk cari data karyawan berdasarkan no absen.
"""

import psycopg2.extras
from db.connections import get_hris_connection
import logging

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
