"""
dashboard/auth.py
Handle login, logout, dan session.
"""

import hashlib
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session
from db.local import get_conn

auth_bp = Blueprint("auth", __name__)


def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper


def get_current_user() -> dict | None:
    if "user_id" not in session:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users_dashboard WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
        return dict(row) if row else None


@auth_bp.route("/", methods=["GET"])
def index():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    user = get_current_user()
    if user["role"] == "manager":
        return redirect(url_for("manager.dashboard"))
    elif user["role"] in ("kepala_support", "support"):
        return redirect(url_for("support.dashboard"))
    else:
        return redirect(url_for("programmer.dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users_dashboard WHERE username = ? AND password_hash = ?",
                (username, hash_password(password))
            ).fetchone()
        if row:
            session["user_id"] = row["id"]
            session["role"] = row["role"]
            session["nama"] = row["nama"]
            return redirect(url_for("auth.index"))
        else:
            error = "Username atau password salah."
    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))