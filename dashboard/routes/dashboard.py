"""
dashboard/routes/dashboard.py
Dashboard utama — 1 halaman buat semua orang (gantiin dashboard terpisah
manager/programmer/support yang lama).

Isinya otomatis nyesuain berdasarkan permission:
  - "assign_task" -> liat SEMUA task (bukan cuma punya sendiri), bisa assign ke siapa aja
  - "ranking"     -> liat leaderboard ranking responder komplain
Superadmin (is_superadmin) otomatis lolos semua permission di atas.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, send_from_directory, abort
from werkzeug.security import check_password_hash, generate_password_hash
from dashboard.auth import login_required, get_current_user, has_permission
from db.local import get_conn

# Folder simpen tanda tangan user (dipakai berulang di Berita Acara)
SIGNATURE_DIR = os.environ.get("STORAGE_BASE_PATH", "/app/data-internal") + "/signatures"
ALLOWED_SIGNATURE_EXT = {".png", ".jpg", ".jpeg"}

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

WIB = timezone(timedelta(hours=7))


def _now_wib_str() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")


# ──────────────────────────────────────────
# Dashboard utama
# ──────────────────────────────────────────

@dashboard_bp.route("/")
@login_required
def index():
    user = get_current_user()
    bisa_assign = has_permission("assign_task")
    bisa_ranking = has_permission("ranking")

    # Filter tanggal buat card komplain — default 7 hari terakhir
    today_wib = datetime.now(WIB).date()
    dari_str = request.args.get("dari_tanggal", "").strip()
    sampai_str = request.args.get("sampai_tanggal", "").strip()
    dari_tanggal = datetime.strptime(dari_str, "%Y-%m-%d").date() if dari_str else (today_wib - timedelta(days=6))
    sampai_tanggal = datetime.strptime(sampai_str, "%Y-%m-%d").date() if sampai_str else today_wib

    with get_conn() as conn:
        if bisa_assign:
            tasks = conn.execute("""
                SELECT t.*, u.nama as dibuat_oleh_nama
                FROM task t
                LEFT JOIN whitelist u ON t.dibuat_oleh = u.user_id
                ORDER BY t.created_at DESC
            """).fetchall()
        else:
            tasks = conn.execute("""
                SELECT t.*, u.nama as dibuat_oleh_nama
                FROM task t
                LEFT JOIN whitelist u ON t.dibuat_oleh = u.user_id
                JOIN task_assignee ta ON t.id = ta.task_id
                WHERE ta.user_id = ?
                ORDER BY t.created_at DESC
            """, (user["user_id"],)).fetchall()

        stats = {
            "total_task": len(tasks),
            "open": sum(1 for t in tasks if t["status"] == "open"),
            "on_progress": sum(1 for t in tasks if t["status"] == "on_progress"),
            "done": sum(1 for t in tasks if t["status"] == "done"),
        }

        ranking = []
        if bisa_ranking:
            ranking = conn.execute("""
                SELECT responder_nama, COUNT(*) as total
                FROM response_komplain
                GROUP BY responder_nama
                ORDER BY total DESC
                LIMIT 10
            """).fetchall()

        # ── Card Komplain: isi asli + balasan (kalau ada) + filter tanggal ──
        komplain_rows = conn.execute("""
            SELECT * FROM komplain
            WHERE (masuk_at AT TIME ZONE 'Asia/Jakarta')::date BETWEEN ? AND ?
            ORDER BY masuk_at DESC
        """, (dari_tanggal, sampai_tanggal)).fetchall()

        komplain_ids = [k["id"] for k in komplain_rows]
        response_map = {}
        if komplain_ids:
            placeholders = ",".join("?" for _ in komplain_ids)
            resp_rows = conn.execute(f"""
                SELECT * FROM response_komplain
                WHERE komplain_id IN ({placeholders})
                ORDER BY bales_at ASC
            """, komplain_ids).fetchall()
            for r in resp_rows:
                response_map.setdefault(r["komplain_id"], []).append(dict(r))

        komplain = []
        for k in komplain_rows:
            kd = dict(k)
            kd["responses"] = response_map.get(k["id"], [])
            komplain.append(kd)

        users_list = []
        if bisa_assign:
            users_list = conn.execute(
                "SELECT user_id, nama FROM whitelist ORDER BY nama"
            ).fetchall()

    return render_template("dashboard.html",
        user=user, tasks=tasks, ranking=ranking,
        stats=stats, users=users_list, komplain=komplain,
        bisa_assign=bisa_assign, bisa_ranking=bisa_ranking,
        dari_tanggal=dari_tanggal.isoformat(), sampai_tanggal=sampai_tanggal.isoformat(),
    )


# ──────────────────────────────────────────
# Task
# ──────────────────────────────────────────

@dashboard_bp.route("/task/buat", methods=["POST"])
@login_required
def buat_task():
    user = get_current_user()
    judul = request.form.get("judul", "").strip()
    deskripsi = request.form.get("deskripsi", "").strip()
    deadline = request.form.get("deadline", "").strip()
    prioritas = request.form.get("prioritas", "normal")
    assignees = request.form.getlist("assignees")

    if not judul:
        return redirect(url_for("dashboard.index"))

    bisa_assign = has_permission("assign_task")

    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO task (judul, deskripsi, deadline, prioritas, dibuat_oleh)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        """, (judul, deskripsi, deadline or None, prioritas, user["user_id"]))
        task_id = cur.fetchone()["id"]

        # Kalau gak punya izin assign_task (atau gak milih siapa-siapa), auto-assign ke diri sendiri
        target_assignees = assignees if (bisa_assign and assignees) else [str(user["user_id"])]
        for uid in target_assignees:
            conn.execute("""
                INSERT INTO task_assignee (task_id, user_id) VALUES (?, ?)
                ON CONFLICT (task_id, user_id) DO NOTHING
            """, (task_id, int(uid)))
        conn.commit()

    if bisa_assign and assignees:
        try:
            from dashboard.notif import kirim_notif_task_baru
            kirim_notif_task_baru(task_id, judul, assignees)
        except Exception:
            pass  # notif gagal gak boleh gagalin pembuatan task

    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/task/<int:task_id>")
@login_required
def detail_task(task_id):
    user = get_current_user()
    bisa_assign = has_permission("assign_task")

    with get_conn() as conn:
        task = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
        comments = conn.execute("""
            SELECT tc.*, u.nama
            FROM task_comment tc
            JOIN whitelist u ON tc.user_id = u.user_id
            WHERE tc.task_id = ?
            ORDER BY tc.created_at ASC
        """, (task_id,)).fetchall()
        assignees = conn.execute("""
            SELECT u.nama FROM task_assignee ta
            JOIN whitelist u ON ta.user_id = u.user_id
            WHERE ta.task_id = ?
        """, (task_id,)).fetchall()
        users_list = []
        if bisa_assign:
            users_list = conn.execute("SELECT user_id, nama FROM whitelist ORDER BY nama").fetchall()

    return render_template("task.html",
        user=user, task=task, comments=comments, assignees=assignees,
        users=users_list, bisa_assign=bisa_assign,
    )


@dashboard_bp.route("/task/<int:task_id>/komentar", methods=["POST"])
@login_required
def tambah_komentar(task_id):
    user = get_current_user()
    isi = request.form.get("isi", "").strip()
    if isi:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO task_comment (task_id, user_id, isi) VALUES (?, ?, ?)",
                (task_id, user["user_id"], isi)
            )
            conn.commit()
    return redirect(url_for("dashboard.detail_task", task_id=task_id))


@dashboard_bp.route("/task/<int:task_id>/progres", methods=["POST"])
@login_required
def update_progres(task_id):
    progres = int(request.form.get("progres", 0))
    status = "done" if progres == 100 else "on_progress" if progres > 0 else "open"
    with get_conn() as conn:
        conn.execute("""
            UPDATE task SET progres = ?, status = ?, updated_at = ?
            WHERE id = ?
        """, (progres, status, _now_wib_str(), task_id))
        conn.commit()
    return redirect(url_for("dashboard.detail_task", task_id=task_id))


@dashboard_bp.route("/task/<int:task_id>/edit", methods=["POST"])
@login_required
def edit_task(task_id):
    deskripsi = request.form.get("deskripsi", "").strip()
    deadline = request.form.get("deadline", "").strip()
    prioritas = request.form.get("prioritas", "normal")
    assignees = request.form.getlist("assignees")

    with get_conn() as conn:
        conn.execute("""
            UPDATE task SET deskripsi = ?, deadline = ?, prioritas = ?, updated_at = ?
            WHERE id = ?
        """, (deskripsi, deadline or None, prioritas, _now_wib_str(), task_id))

        if assignees and has_permission("assign_task"):
            conn.execute("DELETE FROM task_assignee WHERE task_id = ?", (task_id,))
            for uid in assignees:
                conn.execute("""
                    INSERT INTO task_assignee (task_id, user_id) VALUES (?, ?)
                    ON CONFLICT (task_id, user_id) DO NOTHING
                """, (task_id, int(uid)))
        conn.commit()
    return redirect(url_for("dashboard.detail_task", task_id=task_id))


@dashboard_bp.route("/task/<int:task_id>/hapus", methods=["POST"])
@login_required
def hapus_task(task_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM task_assignee WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_comment WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
        conn.commit()
    return redirect(url_for("dashboard.index"))


# ──────────────────────────────────────────
# Profile — gabungan dari manager/programmer/support/superadmin (isinya sama persis dulu)
# ──────────────────────────────────────────

@dashboard_bp.route("/profile")
@login_required
def profile():
    user = get_current_user()
    return render_template("profile.html", user=user)


@dashboard_bp.route("/profile/ganti-password", methods=["POST"])
@login_required
def ganti_password():
    user = get_current_user()
    password_lama = request.form.get("password_lama", "").strip()
    password_baru = request.form.get("password_baru", "").strip()

    if password_baru and user["password_hash"] and check_password_hash(user["password_hash"], password_lama):
        with get_conn() as conn:
            conn.execute(
                "UPDATE whitelist SET password_hash = ? WHERE user_id = ?",
                (generate_password_hash(password_baru), user["user_id"])
            )
            conn.commit()
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/profile/edit-nama", methods=["POST"])
@login_required
def edit_nama():
    user = get_current_user()
    nama_baru = request.form.get("nama", "").strip()
    if nama_baru:
        with get_conn() as conn:
            conn.execute(
                "UPDATE whitelist SET nama = ? WHERE user_id = ?",
                (nama_baru, user["user_id"])
            )
            conn.commit()
        session["nama"] = nama_baru
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/profile/ttd-preview")
@login_required
def ttd_preview():
    user = get_current_user()
    if not user.get("signature_path"):
        abort(404)
    return send_from_directory(SIGNATURE_DIR, user["signature_path"])


@dashboard_bp.route("/profile/upload-ttd", methods=["POST"])
@login_required
def upload_ttd():
    """Upload tanda tangan sekali, dipakai berulang tiap bikin Berita Acara
    (sebagai Support atau kalau ybs ditandai jadi Manager IT)."""
    user = get_current_user()
    file = request.files.get("signature")
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in ALLOWED_SIGNATURE_EXT:
            os.makedirs(SIGNATURE_DIR, exist_ok=True)
            nama_file = f"sig_{user['user_id']}_{uuid.uuid4().hex[:8]}{ext}"
            file.save(os.path.join(SIGNATURE_DIR, nama_file))

            # hapus file lama biar gak numpuk sampah
            if user.get("signature_path"):
                lama = os.path.join(SIGNATURE_DIR, user["signature_path"])
                if os.path.isfile(lama):
                    os.remove(lama)

            with get_conn() as conn:
                conn.execute(
                    "UPDATE whitelist SET signature_path = ? WHERE user_id = ?",
                    (nama_file, user["user_id"])
                )
                conn.commit()
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/profile/hapus-ttd", methods=["POST"])
@login_required
def hapus_ttd():
    user = get_current_user()
    if user.get("signature_path"):
        p = os.path.join(SIGNATURE_DIR, user["signature_path"])
        if os.path.isfile(p):
            os.remove(p)
        with get_conn() as conn:
            conn.execute("UPDATE whitelist SET signature_path = NULL WHERE user_id = ?", (user["user_id"],))
            conn.commit()
    return redirect(url_for("dashboard.profile"))
