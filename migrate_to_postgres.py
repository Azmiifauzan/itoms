"""
migrate_to_postgres.py
Jalankan SEKALI aja buat:
  1. Pindahin data hari_libur, komplain, response_komplain dari local.db (SQLite lama)
  2. Bikin 1 akun superadmin pertama di tabel whitelist Postgres

Cara pakai:
  python3 migrate_to_postgres.py

Pastikan:
  - schema.sql udah dijalankan duluan ke database itoms_db
  - Environment variable DATABASE_URL udah keset (atau edit default di db/local.py)
  - File local.db (SQLite lama) ada di folder yang sama / sesuaikan SQLITE_PATH di bawah
"""

import sqlite3
import os
import getpass
from werkzeug.security import generate_password_hash

# ── Config ──
SQLITE_PATH = os.environ.get("OLD_SQLITE_PATH", "local.db")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://itoms:itmos123@127.0.0.1:5432/itoms_db"
)

import psycopg2
import psycopg2.extras


def get_sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn():
    return psycopg2.connect(DATABASE_URL)


def migrate_hari_libur(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute("SELECT tanggal, nama FROM hari_libur").fetchall()
    cur = pg_conn.cursor()
    count = 0
    for r in rows:
        cur.execute(
            "INSERT INTO hari_libur (tanggal, nama) VALUES (%s, %s) ON CONFLICT (tanggal) DO NOTHING",
            (r["tanggal"], r["nama"])
        )
        count += 1
    pg_conn.commit()
    print(f"[OK] hari_libur: {count} baris dipindah")


def migrate_komplain(sqlite_conn, pg_conn):
    rows = sqlite_conn.execute(
        "SELECT id, message_id, chat_id, grup_nama, isi_pesan, pengirim, masuk_at FROM komplain"
    ).fetchall()
    cur = pg_conn.cursor()
    id_map = {}  # id lama -> id baru, dipake buat migrasi response_komplain
    count = 0
    for r in rows:
        cur.execute("""
            INSERT INTO komplain (message_id, chat_id, grup_nama, isi_pesan, pengirim, masuk_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (r["message_id"], r["chat_id"], r["grup_nama"], r["isi_pesan"], r["pengirim"], r["masuk_at"]))
        new_id = cur.fetchone()[0]
        id_map[r["id"]] = new_id
        count += 1
    pg_conn.commit()
    print(f"[OK] komplain: {count} baris dipindah")
    return id_map


def migrate_response_komplain(sqlite_conn, pg_conn, id_map):
    rows = sqlite_conn.execute("""
        SELECT komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan, bales_at
        FROM response_komplain
    """).fetchall()
    cur = pg_conn.cursor()
    count = 0
    skipped = 0
    for r in rows:
        new_komplain_id = id_map.get(r["komplain_id"])
        if new_komplain_id is None:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO response_komplain
                (komplain_id, message_id, chat_id, responder_id, responder_nama, isi_balasan, bales_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (new_komplain_id, r["message_id"], r["chat_id"], r["responder_id"],
              r["responder_nama"], r["isi_balasan"], r["bales_at"]))
        count += 1
    pg_conn.commit()
    print(f"[OK] response_komplain: {count} baris dipindah ({skipped} dilewatin karena komplain induknya gak ketemu)")


def buat_superadmin_pertama(pg_conn):
    print("\n--- Bikin akun superadmin pertama ---")
    user_id = input("Telegram User ID superadmin: ").strip()
    nama = input("Nama: ").strip()
    username = input("Username buat login dashboard: ").strip()
    password = getpass.getpass("Password buat login dashboard: ")

    password_hash = generate_password_hash(password)

    cur = pg_conn.cursor()
    cur.execute("""
        INSERT INTO whitelist (user_id, nama, username, password_hash, is_superadmin, permissions)
        VALUES (%s, %s, %s, %s, TRUE, '[]'::jsonb)
        ON CONFLICT (user_id) DO UPDATE SET
            nama = EXCLUDED.nama,
            username = EXCLUDED.username,
            password_hash = EXCLUDED.password_hash,
            is_superadmin = TRUE
    """, (int(user_id), nama, username, password_hash))
    pg_conn.commit()
    print(f"[OK] Superadmin '{username}' dibikin.")


def main():
    print(f"Baca dari SQLite: {SQLITE_PATH}")
    print(f"Tulis ke Postgres: {DATABASE_URL.split('@')[-1]}")  # sembunyiin password di log

    sqlite_conn = get_sqlite_conn()
    pg_conn = get_pg_conn()

    migrate_hari_libur(sqlite_conn, pg_conn)
    id_map = migrate_komplain(sqlite_conn, pg_conn)
    migrate_response_komplain(sqlite_conn, pg_conn, id_map)

    buat_superadmin_pertama(pg_conn)

    sqlite_conn.close()
    pg_conn.close()
    print("\nSelesai! Database Postgres siap dipakai.")


if __name__ == "__main__":
    main()
