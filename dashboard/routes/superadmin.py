"""
dashboard/routes/superadmin.py
Route khusus superadmin — kelola tanggal merah, daftar piket, multiple Telegram ID.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from dashboard.auth import login_required, get_current_user
from db.local import get_conn, get_telegram_ids, add_telegram_id, remove_telegram_id

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/superadmin")


def superadmin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "superadmin":
            return redirect(url_for("auth.index"))
        return func(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────
# Dashboard superadmin
# ──────────────────────────────────────────
@superadmin_bp.route("/dashboard")
@login_required
@superadmin_required
def dashboard():
    user = get_current_user()
    with get_conn() as conn:
        whitelist = conn.execute(
            "SELECT * FROM whitelist ORDER BY nama"
        ).fetchall()
        total_libur = conn.execute(
            "SELECT COUNT(*) FROM hari_libur"
        ).fetchone()[0]
        total_piket = conn.execute(
            "SELECT COUNT(*) FROM daftar_piket"
        ).fetchone()[0]
    return render_template("superadmin/dashboard.html",
        user=user,
        whitelist=whitelist,
        total_libur=total_libur,
        total_piket=total_piket,
    )


# ──────────────────────────────────────────
# Kelola Multiple Telegram ID
# ──────────────────────────────────────────
@superadmin_bp.route("/telegram")
@login_required
@superadmin_required
def telegram():
    user = get_current_user()
    with get_conn() as conn:
        whitelist = conn.execute(
            "SELECT rowid as id, * FROM whitelist ORDER BY nama"
        ).fetchall()
    # Ambil telegram IDs per user
    whitelist_data = []
    for w in whitelist:
        tg_ids = get_telegram_ids(w["id"])
        whitelist_data.append({
            "user": dict(w),
            "telegram_ids": tg_ids
        })
    return render_template("superadmin/telegram.html",
        user=user,
        whitelist_data=whitelist_data,
    )


@superadmin_bp.route("/telegram/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_telegram():
    whitelist_id = int(request.form.get("whitelist_id", 0))
    telegram_user_id = request.form.get("telegram_user_id", "").strip()
    label = request.form.get("label", "").strip()

    if whitelist_id and telegram_user_id.isdigit():
        add_telegram_id(whitelist_id, int(telegram_user_id), label or None)

    return redirect(url_for("superadmin.telegram"))


@superadmin_bp.route("/telegram/hapus/<int:tid>", methods=["POST"])
@login_required
@superadmin_required
def hapus_telegram(tid):
    remove_telegram_id(tid)
    return redirect(url_for("superadmin.telegram"))


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
            "SELECT * FROM hari_libur WHERE tanggal LIKE ? ORDER BY tanggal",
            (f"{tahun}%",)
        ).fetchall()
    return render_template("superadmin/libur.html",
        user=user,
        libur_list=libur_list,
        tahun=tahun,
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
                pass
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
            "SELECT rowid as id, user_id, nama FROM whitelist ORDER BY nama"
        ).fetchall()
    return render_template("superadmin/piket.html",
        user=user,
        daftar=daftar,
        whitelist=whitelist,
    )


@superadmin_bp.route("/piket/tambah", methods=["POST"])
@login_required
@superadmin_required
def tambah_piket():
    whitelist_id = int(request.form.get("whitelist_id", 0))
    if whitelist_id:
        with get_conn() as conn:
            max_urutan = conn.execute(
                "SELECT COALESCE(MAX(urutan), 0) FROM daftar_piket"
            ).fetchone()[0]
            try:
                conn.execute(
                    "INSERT INTO daftar_piket (whitelist_id, urutan) VALUES (?, ?)",
                    (whitelist_id, max_urutan + 1)
                )
                conn.commit()
            except Exception:
                pass
    return redirect(url_for("superadmin.piket"))


@superadmin_bp.route("/piket/hapus/<int:pid>", methods=["POST"])
@login_required
@superadmin_required
def hapus_piket(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM daftar_piket WHERE id = ?", (pid,))
        conn.commit()
    return redirect(url_for("superadmin.piket"))