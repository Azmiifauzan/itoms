from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from werkzeug.security import check_password_hash
drom db.local import get_conn

auth_bp = Blueprint("auth", __name__)
 
 def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    retrun wrapper

def permission_required(perm: str) -> bool:
    if session.get("is_superadmin"):
        return True
    return perm in (session.get("permission") or [])

def permission_required(perm: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if not has_permission(perm):
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_current_user() -> dict | None:
    if "user_id" not in session:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whitelist WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()
        return dict(row) if row else None

@auth_bp.route("/", methods=["GET"])
def index():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    return redirect(url_for("dashboard.index"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM whitelist WHERE username = ?",
                (username,)
            ).fetchone()

        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["user_id"]
            session["nama"] = row["nama"]
            session["is_superadmin"] = row["is_superadmin"]
            session["permissions"] = row["permission"]
            return redirect(url_for("auth.index"))
        else:
            error = "Username atau password salah."
    return render_template("login.html", error=error)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))