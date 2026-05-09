"""
dashboard/routes/manager.py
Route untuk role manager - bisa lihat semua.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from dashboard.auth import login_required, get_current_user
from db.local import get_conn

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


def manager_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "manager":
            return redirect(url_for("auth.index"))
        return func(*args, **kwargs)
    return wrapper


@manager_bp.route("/dashboard")
@login_required
@manager_required
def dashboard():
    user = get_current_user()
    with get_conn() as conn:
        # Semua task
        tasks = conn.execute("""
            SELECT t.*, u.nama as dibuat_oleh_nama
            FROM task t
            LEFT JOIN users_dashboard u ON t.dibuat_oleh = u.id            
            ORDER BY t.created_at DESC
        """).fetchall()

        # Ranking responder komplain
        ranking = conn.execute("""
            SELECT responder_nama, COUNT(*) as total
            FROM response_komplain
            GROUP BY responder_id
            ORDER BY total DESC
            LIMIT 10
        """).fetchall()

        # Statistik
        stats = {
            "total_task": conn.execute("SELECT COUNT(*) FROM task").fetchone()[0],
            "open": conn.execute("SELECT COUNT(*) FROM task WHERE status='open'").fetchone()[0],
            "on_progress": conn.execute("SELECT COUNT(*) FROM task WHERE status='on_progress'").fetchone()[0],
            "done": conn.execute("SELECT COUNT(*) FROM task WHERE status='done'").fetchone()[0],
            "komplain_hari_ini": conn.execute("""
                SELECT COUNT(*) FROM komplain
                WHERE DATE(masuk_at) = DATE('now','localtime')
            """).fetchone()[0],
        }

        # Semua user untuk assign task
        users = conn.execute(
            "SELECT id, nama, role FROM users_dashboard ORDER BY nama"
        ).fetchall()

    return render_template("dashboard.html",
        user=user, tasks=tasks, ranking=ranking,
        stats=stats, users=users
    )


@manager_bp.route("/task/buat", methods=["POST"])
@login_required
@manager_required
def buat_task():
    user = get_current_user()
    judul = request.form.get("judul", "").strip()
    deskripsi = request.form.get("deskripsi", "").strip()
    deadline = request.form.get("deadline", "").strip()
    prioritas = request.form.get("prioritas", "normal")
    assignees = request.form.getlist("assignees")

    if not judul:
        return redirect(url_for("manager.dashboard"))

    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO task (judul, deskripsi, deadline, prioritas, dibuat_oleh)
            VALUES (?, ?, ?, ?, ?)
        """, (judul, deskripsi, deadline or None, prioritas, user["id"]))
        task_id = cur.lastrowid

        for uid in assignees:
            conn.execute(
                "INSERT OR IGNORE INTO task_assignee (task_id, user_id) VALUES (?, ?)",
                (task_id, int(uid))
            )
        conn.commit()

    # Kirim notif Telegram ke assignee
    from dashboard.notif import kirim_notif_task_baru
    kirim_notif_task_baru(task_id, judul, assignees)

    return redirect(url_for("manager.dashboard"))

@manager_bp.route("/task/<int:task_id>")
@login_required
@manager_required
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
            "SELECT id, nama FROM users_dashboard ORDER BY nama"
        ).fetchall()

    return render_template("task.html",
        user=user, task=task, comments=comments, assignees=assignees, users=users
    )


@manager_bp.route("/task/<int:task_id>/komentar", methods=["POST"])
@login_required
@manager_required
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
    return redirect(url_for("manager.detail_task", task_id=task_id))
# ──────────────────────────────────────────
# Manajemen User
# ──────────────────────────────────────────
@manager_bp.route("/users")
@login_required
@manager_required
def users():
    with get_conn() as conn:
        all_users = conn.execute(
            "SELECT * FROM users_dashboard ORDER BY role, nama"
        ).fetchall()
    return render_template("users.html", user=get_current_user(), users=all_users)


@manager_bp.route("/users/tambah", methods=["POST"])
@login_required
@manager_required
def tambah_user():
    import hashlib
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    nama = request.form.get("nama", "").strip()
    role = request.form.get("role", "").strip()
    telegram_user_id = request.form.get("telegram_user_id", "").strip()

    if not all([username, password, nama, role]):
        return redirect(url_for("manager.users"))

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    telegram_id = int(telegram_user_id) if telegram_user_id.isdigit() else None

    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO users_dashboard (username, password_hash, nama, role, telegram_user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (username, password_hash, nama, role, telegram_id))
            conn.commit()
        except Exception:
            pass  # username duplikat
    return redirect(url_for("manager.users"))


@manager_bp.route("/users/<int:user_id>/hapus", methods=["POST"])
@login_required
@manager_required
def hapus_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM users_dashboard WHERE id = ?", (user_id,))
        conn.commit()
    return redirect(url_for("manager.users"))


@manager_bp.route("/users/<int:user_id>/reset", methods=["POST"])
@login_required
@manager_required
def reset_password(user_id):
    import hashlib
    password_baru = request.form.get("password_baru", "").strip()
    if password_baru:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users_dashboard SET password_hash = ? WHERE id = ?",
                (hashlib.sha256(password_baru.encode()).hexdigest(), user_id)
            )
            conn.commit()
    return redirect(url_for("manager.users"))

@manager_bp.route("/profile/ganti-password", methods=["POST"])
@login_required
@manager_required
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
    return redirect(url_for("manager.profile"))


@manager_bp.route("/profile/edit-nama", methods=["POST"])
@login_required
@manager_required
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
    return redirect(url_for("manager.profile"))


@manager_bp.route("/profile")
@login_required
@manager_required
def profile():
    user = get_current_user()
    return render_template("profile.html", user=user)

@manager_bp.route("/task/<int:task_id>/hapus", methods=["POST"])
@login_required
@manager_required
def hapus_task(task_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM task_assignee WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_comment WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
        conn.commit()
    return redirect(url_for("manager.dashboard"))
@manager_bp.route("/task/<int:task_id>/edit", methods=["POST"])
@login_required
@manager_required
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
    return redirect(url_for("manager.detail_task", task_id=task_id))