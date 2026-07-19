"""
dashboard/routes/superadmin.py
Route khusus superadmin — kelola hari libur, daftar piket, dan whitelist user
(termasuk permissions & login dashboard, karena sekarang 1 tabel buat semuanya).
"""

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash
from psycopg2.extras import Json
from dashboard.auth import login_required, get_current_user
from db.local import get_conn

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/superadmin")

# Daftar permission yang tersedia di sistem. Tambahin di sini kalau ada fitur baru
# yang butuh permission baru.
AVAILABLE_PERMISSIONS = [
    ("assign_task", "Assign Task"),
    ("ranking", "Lihat Ranking"),
    ("generate_jadwal", "Kelola & Generate Jadwal"),
    ("config_bot", "Konfigurasi Bot"),
    ("edit_check_retur", "Edit Data Check Retur"),
]


def superadmin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("is_superadmin"):
            return redirect(url_for("dashboard.index"))
        return func(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────
# Ringkasan admin
# ──────────────────────────────────────────
@superadmin_bp.route("/dashboard")
@login_required
@superadmin_required
def dashboard():
    user = get_current_user()
    with get_conn() as conn:
        whitelist = conn.execute("SELECT * FROM whitelist ORDER BY nama").fetchall()
        total_libur = conn.execute("SELECT COUNT(*) as c FROM hari_libur").fetchone()["c"]
        total_piket = conn.execute("SELECT COUNT(*) as c FROM daftar_piket").fetchone()["c"]
    return render_template("superadmin/dashboard.html",
        user=user, whitelist=whitelist,
        total_libur=total_libur, total_piket=total_piket,
    )


# ──────────────────────────────────────────
# Kelola Hari Libur
# ──────────────────────────────────────────
@superadmin_bp.route("/libur")
@login_required
@superadmin_required
def libur():
    user = get_current_user()
    tahun = int(request.args.get("tahun", __import__("datetime").date.today().year))
    with get_conn() as conn:
        libur_list = conn.execute(
            "SELECT * FROM hari_libur WHERE EXTRACT(YEAR FROM tanggal) = ? ORDER BY tanggal",
            (tahun,)
        ).fetchall()
    return render_template("superadmin/libur.html",
        user=user, libur_list=libur_list, tahun=tahun,
    )


@superadmin_bp.route("/libur/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_libur():
    tanggal = request.form.get("tanggal", "").strip()
    nama = request.form.get("nama", "").strip()
    if tanggal and nama:
        with get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO hari_libur (tanggal, nama) VALUES (?, ?)",
                    (tanggal, nama)
                )
                conn.commit()
            except Exception:
                pass  # tanggal duplikat
    return redirect(url_for("superadmin.libur", tahun=tanggal[:4] if tanggal else ""))


@superadmin_bp.route("/libur/hapus/<int:lid>", methods=["POST"])
@login_required
@superadmin_required
def hapus_libur(lid):
    with get_conn() as conn:
        conn.execute("DELETE FROM hari_libur WHERE id = ?", (lid,))
        conn.commit()
    return redirect(url_for("superadmin.libur"))


# ──────────────────────────────────────────
# Kelola Daftar Piket
# ──────────────────────────────────────────
@superadmin_bp.route("/piket")
@login_required
@superadmin_required
def piket():
    user = get_current_user()
    with get_conn() as conn:
        daftar = conn.execute("""
            SELECT dp.*, w.nama as nama_user
            FROM daftar_piket dp
            JOIN whitelist w ON dp.whitelist_id = w.user_id
            ORDER BY dp.urutan
        """).fetchall()
        whitelist = conn.execute(
            "SELECT user_id, nama FROM whitelist ORDER BY nama"
        ).fetchall()
    return render_template("superadmin/piket.html",
        user=user, daftar=daftar, whitelist=whitelist,
    )


@superadmin_bp.route("/piket/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_piket():
    whitelist_id_str = request.form.get("whitelist_id", "").strip()
    whitelist_id = int(whitelist_id_str) if whitelist_id_str.isdigit() else 0
    if whitelist_id:
        with get_conn() as conn:
            max_urutan = conn.execute(
                "SELECT COALESCE(MAX(urutan), 0) as m FROM daftar_piket"
            ).fetchone()["m"]
            try:
                conn.execute(
                    "INSERT INTO daftar_piket (whitelist_id, urutan) VALUES (?, ?)",
                    (whitelist_id, max_urutan + 1)
                )
                conn.commit()
            except Exception:
                pass  # udah ada di daftar piket
    return redirect(url_for("superadmin.piket"))


@superadmin_bp.route("/piket/hapus/<int:pid>", methods=["POST"])
@login_required
@superadmin_required
def hapus_piket(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM daftar_piket WHERE id = ?", (pid,))
        conn.commit()
    return redirect(url_for("superadmin.piket"))


# ──────────────────────────────────────────
# Kelola Whitelist (user: telegram + login dashboard + permissions)
# ──────────────────────────────────────────
@superadmin_bp.route("/whitelist")
@login_required
@superadmin_required
def whitelist():
    user = get_current_user()
    with get_conn() as conn:
        wl = conn.execute("SELECT * FROM whitelist ORDER BY nama").fetchall()
    return render_template("superadmin/whitelist.html",
        user=user, whitelist=wl, available_permissions=AVAILABLE_PERMISSIONS,
    )


@superadmin_bp.route("/whitelist/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_whitelist():
    user_id = request.form.get("user_id", "").strip()
    nama = request.form.get("nama", "").strip()
    no_hp = request.form.get("no_hp", "").strip()
    telegram_id_2 = request.form.get("telegram_id_2", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    is_superadmin = request.form.get("is_superadmin") == "on"
    permissions = request.form.getlist("permissions")

    if not (user_id.isdigit() and nama and username and password):
        return redirect(url_for("superadmin.whitelist"))

    password_hash = generate_password_hash(password)
    tg2 = int(telegram_id_2) if telegram_id_2.isdigit() else None

    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO whitelist
                    (user_id, nama, no_hp, telegram_id_2, username, password_hash,
                     is_superadmin, permissions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (int(user_id), nama, no_hp or None, tg2, username, password_hash,
                  is_superadmin, Json(permissions)))
            conn.commit()
        except Exception:
            pass  # user_id atau username udah dipakai

    return redirect(url_for("superadmin.whitelist"))


@superadmin_bp.route("/whitelist/edit/<int:user_id>", methods=["POST"])
@login_required
@superadmin_required
def edit_whitelist(user_id):
    nama = request.form.get("nama", "").strip()
    no_hp = request.form.get("no_hp", "").strip()
    telegram_id_2 = request.form.get("telegram_id_2", "").strip()
    username = request.form.get("username", "").strip()
    password_baru = request.form.get("password_baru", "").strip()
    is_superadmin = request.form.get("is_superadmin") == "on"
    permissions = request.form.getlist("permissions")

    if not nama:
        return redirect(url_for("superadmin.whitelist"))

    tg2 = int(telegram_id_2) if telegram_id_2.isdigit() else None

    with get_conn() as conn:
        if password_baru:
            conn.execute("""
                UPDATE whitelist SET
                    nama = ?, no_hp = ?, telegram_id_2 = ?, username = ?,
                    password_hash = ?, is_superadmin = ?, permissions = ?
                WHERE user_id = ?
            """, (nama, no_hp or None, tg2, username, generate_password_hash(password_baru),
                  is_superadmin, Json(permissions), user_id))
        else:
            conn.execute("""
                UPDATE whitelist SET
                    nama = ?, no_hp = ?, telegram_id_2 = ?, username = ?,
                    is_superadmin = ?, permissions = ?
                WHERE user_id = ?
            """, (nama, no_hp or None, tg2, username,
                  is_superadmin, Json(permissions), user_id))
        conn.commit()

    return redirect(url_for("superadmin.whitelist"))


@superadmin_bp.route("/whitelist/hapus/<int:user_id>", methods=["POST"])
@login_required
@superadmin_required
def hapus_whitelist(user_id):
    with get_conn() as conn:
        try:
            conn.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            # Gagal hapus -> biasanya karena user ini masih tercatat sebagai pembuat
            # task/blackout/komplain (foreign key). Sengaja gak dipaksa hapus biar
            # histori data gak jadi nyasar/rusak.
            pass
    return redirect(url_for("superadmin.whitelist"))

# ──────────────────────────────────────────
# Kelola Master Artikel (kode + nama) — dipakai di form Check Retur
# ──────────────────────────────────────────
@superadmin_bp.route("/artikel")
@login_required
@superadmin_required
def artikel():
    user = get_current_user()
    with get_conn() as conn:
        artikel_list = conn.execute(
            "SELECT * FROM artikel ORDER BY nama"
        ).fetchall()
    return render_template("superadmin/artikel.html",
        user=user, artikel_list=artikel_list,
    )


@superadmin_bp.route("/artikel/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_artikel():
    kode = request.form.get("kode", "").strip().upper()
    nama = request.form.get("nama", "").strip()
    if kode and nama:
        with get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO artikel (kode, nama) VALUES (?, ?)",
                    (kode, nama)
                )
                conn.commit()
            except Exception:
                conn.rollback()  # kode atau nama udah dipakai
    return redirect(url_for("superadmin.artikel"))


@superadmin_bp.route("/artikel/edit/<int:artikel_id>", methods=["POST"])
@login_required
@superadmin_required
def edit_artikel(artikel_id):
    kode = request.form.get("kode", "").strip().upper()
    nama = request.form.get("nama", "").strip()
    if kode and nama:
        with get_conn() as conn:
            try:
                conn.execute(
                    "UPDATE artikel SET kode = ?, nama = ? WHERE id = ?",
                    (kode, nama, artikel_id)
                )
                conn.commit()
            except Exception:
                conn.rollback()
    return redirect(url_for("superadmin.artikel"))


@superadmin_bp.route("/artikel/hapus/<int:artikel_id>", methods=["POST"])
@login_required
@superadmin_required
def hapus_artikel(artikel_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM artikel WHERE id = ?", (artikel_id,))
        conn.commit()
    return redirect(url_for("superadmin.artikel"))
