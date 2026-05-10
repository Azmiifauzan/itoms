"""
dashboard/routes/support.py
Route untuk role kepala_support dan support.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from dashboard.auth import login_required, get_current_user
from db.local import get_conn

support_bp = Blueprint("support", __name__, url_prefix="/support")


def support_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("kepala_support", "support"):
            return redirect(url_for("auth.index"))
        return func(*args, **kwargs)
    return wrapper


@support_bp.route("/dashboard")
@login_required
@support_required
def dashboard():
    user = get_current_user()
    with get_conn() as conn:
        # Support biasa: lihat task sendiri aja
        # Kepala support: lihat semua task support
        if user["role"] == "kepala_support":
            tasks = conn.execute("""
                SELECT DISTINCT t.*, u.nama as dibuat_oleh_nama
                FROM task t
                LEFT JOIN users_dashboard u ON t.dibuat_oleh = u.id
                JOIN task_assignee ta ON t.id = ta.task_id
                JOIN users_dashboard ua ON ta.user_id = ua.id
                WHERE ua.role IN ('support', 'kepala_support')                
                ORDER BY t.created_at DESC
            """).fetchall()
        else:
            tasks = conn.execute("""
                SELECT t.*, u.nama as dibuat_oleh_nama
                FROM task t
                LEFT JOIN users_dashboard u ON t.dibuat_oleh = u.id
                JOIN task_assignee ta ON t.id = ta.task_id
                WHERE ta.user_id = ?                
                ORDER BY t.created_at DESC
            """, (user["id"],)).fetchall()

        # Komplain hari ini
        komplain = conn.execute("""
            SELECT * FROM komplain
            WHERE DATE(masuk_at) = DATE('now','localtime')
            ORDER BY masuk_at DESC
        """).fetchall()

        stats = {
            "total_task": len(tasks),
            "open": sum(1 for t in tasks if t["status"] == "open"),
            "on_progress": sum(1 for t in tasks if t["status"] == "on_progress"),
            "done": sum(1 for t in tasks if t["status"] == "done"),
        }

        # Untuk kepala support: list user support buat assign
        users_support = []
        if user["role"] == "kepala_support":
            users_support = conn.execute("""
                SELECT id, nama FROM users_dashboard
                WHERE role IN ('support', 'kepala_support')
                ORDER BY nama
            """).fetchall()

    return render_template("dashboard.html",
        user=user, tasks=tasks, komplain=komplain,
        stats=stats, users=users_support
    )


@support_bp.route("/task/buat", methods=["POST"])
@login_required
@support_required
def buat_task():
    user = get_current_user()
    judul = request.form.get("judul", "").strip()
    deskripsi = request.form.get("deskripsi", "").strip()
    deadline = request.form.get("deadline", "").strip()
    prioritas = request.form.get("prioritas", "normal")
    assignees = request.form.getlist("assignees")

    if not judul:
        return redirect(url_for("support.dashboard"))

    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO task (judul, deskripsi, deadline, prioritas, dibuat_oleh)
            VALUES (?, ?, ?, ?, ?)
        """, (judul, deskripsi, deadline or None, prioritas, user["id"]))
        task_id = cur.lastrowid

        # Support biasa: assign ke diri sendiri otomatis
        # Kepala support: bisa assign ke siapa aja
        if user["role"] == "support" or not assignees:
            conn.execute(
                "INSERT OR IGNORE INTO task_assignee (task_id, user_id) VALUES (?, ?)",
                (task_id, user["id"])
            )
        else:
            for uid in assignees:
                conn.execute(
                    "INSERT OR IGNORE INTO task_assignee (task_id, user_id) VALUES (?, ?)",
                    (task_id, int(uid))
                )
        conn.commit()

    return redirect(url_for("support.dashboard"))


@support_bp.route("/task/<int:task_id>/progres", methods=["POST"])
@login_required
@support_required
def update_progres(task_id):
    progres = int(request.form.get("progres", 0))
    status = "done" if progres == 100 else "on_progress" if progres > 0 else "open"
    with get_conn() as conn:
        conn.execute("""
            UPDATE task SET progres = ?, status = ?,
            updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (progres, status, task_id))
        conn.commit()
    return redirect(url_for("support.dashboard"))


@support_bp.route("/task/<int:task_id>/komentar", methods=["POST"])
@login_required
@support_required
def tambah_komentar(task_id):
    user = get_current_user()
    isi = request.form.get("isi", "").strip()
    if isi:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO task_comment (task_id, user_id, isi) VALUES (?, ?, ?)",
                (task_id, user["id"], isi)
            )
            conn.commit()
    return redirect(url_for("support.detail_task", task_id=task_id))


@support_bp.route("/task/<int:task_id>")
@login_required
@support_required
def detail_task(task_id):
    user = get_current_user()
    with get_conn() as conn:
        task = conn.execute(
            "SELECT * FROM task WHERE id = ?", (task_id,)
        ).fetchone()
        comments = conn.execute("""
            SELECT tc.*, u.nama
            FROM task_comment tc
            JOIN users_dashboard u ON tc.user_id = u.id
            WHERE tc.task_id = ?
            ORDER BY tc.created_at ASC
        """, (task_id,)).fetchall()
        assignees = conn.execute("""
            SELECT u.nama FROM task_assignee ta
            JOIN users_dashboard u ON ta.user_id = u.id
            WHERE ta.task_id = ?
        """, (task_id,)).fetchall()
        users = conn.execute(
            "SELECT id, nama FROM users_dashboard WHERE role IN ('support','kepala_support') ORDER BY nama"
        ).fetchall()

    return render_template("task.html",
        user=user, task=task, comments=comments, assignees=assignees, users=users
    )
@support_bp.route("/profile/ganti-password", methods=["POST"])
@login_required
@support_required
def ganti_password():
    import hashlib
    user = get_current_user()
    password_lama = request.form.get("password_lama", "").strip()
    password_baru = request.form.get("password_baru", "").strip()

    hash_lama = hashlib.sha256(password_lama.encode()).hexdigest()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM users_dashboard WHERE id = ? AND password_hash = ?",
            (user["id"], hash_lama)
        ).fetchone()
        if row and password_baru:
            conn.execute(
                "UPDATE users_dashboard SET password_hash = ? WHERE id = ?",
                (hashlib.sha256(password_baru.encode()).hexdigest(), user["id"])
            )
            conn.commit()
    return redirect(url_for("support.profile"))


@support_bp.route("/profile/edit-nama", methods=["POST"])
@login_required
@support_required
def edit_nama():
    user = get_current_user()
    nama_baru = request.form.get("nama", "").strip()
    if nama_baru:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users_dashboard SET nama = ? WHERE id = ?",
                (nama_baru, user["id"])
            )
            conn.commit()
        session["nama"] = nama_baru
    return redirect(url_for("support.profile"))


@support_bp.route("/profile")
@login_required
@support_required
def profile():
    user = get_current_user()
    return render_template("profile.html", user=user)

@support_bp.route("/task/<int:task_id>/edit", methods=["POST"])
@login_required
@support_required
def edit_task(task_id):
    deskripsi = request.form.get("deskripsi", "").strip()
    deadline = request.form.get("deadline", "").strip()
    prioritas = request.form.get("prioritas", "normal")
    assignees = request.form.getlist("assignees")

    with get_conn() as conn:
        conn.execute("""
            UPDATE task SET deskripsi = ?, deadline = ?, prioritas = ?,
            updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (deskripsi, deadline or None, prioritas, task_id))

        if assignees:
            conn.execute("DELETE FROM task_assignee WHERE task_id = ?", (task_id,))
            for uid in assignees:
                conn.execute(
                    "INSERT OR IGNORE INTO task_assignee (task_id, user_id) VALUES (?, ?)",
                    (task_id, int(uid))
                )
        conn.commit()
    return redirect(url_for("support.detail_task", task_id=task_id))