"""
dashboard/routes/storage.py
Menu Penyimpanan — file manager sederhana ke folder /app/data-internal
(mount dari disk host /mnt/data-internal, dipakai bareng aplikasi lain).
Semua role yang login boleh: lihat, upload, rename, hapus, download, buat folder.
"""

import os
import shutil
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, send_file, abort, flash
from dashboard.auth import login_required, get_current_user

storage_bp = Blueprint("storage", __name__, url_prefix="/storage")

# Path folder di dalam container. Harus di-mount di docker-compose.yml:
#   volumes:
#     - /mnt/data-internal:/app/data-internal
BASE_PATH = os.environ.get("STORAGE_BASE_PATH", "/app/data-internal")


def _safe_join(rel_path: str) -> str:
    """
    Gabungkan BASE_PATH + rel_path dengan aman, cegah path traversal
    (misal rel_path = '../../etc/passwd').
    Return absolute path yang sudah divalidasi.
    """
    rel_path = (rel_path or "").strip().lstrip("/")
    candidate = os.path.normpath(os.path.join(BASE_PATH, rel_path))
    base_abs = os.path.abspath(BASE_PATH)
    candidate_abs = os.path.abspath(candidate)
    if not (candidate_abs == base_abs or candidate_abs.startswith(base_abs + os.sep)):
        abort(400, "Path tidak valid")
    return candidate_abs


def _fmt_size(num_bytes: int) -> str:
    """Format ukuran file jadi human-readable (KB/MB/GB)."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _breadcrumbs(rel_path: str):
    """Return list [(label, rel_path_sampai_situ), ...] buat navigasi breadcrumb."""
    rel_path = (rel_path or "").strip("/")
    if not rel_path:
        return []
    parts = rel_path.split("/")
    crumbs = []
    acc = []
    for p in parts:
        acc.append(p)
        crumbs.append((p, "/".join(acc)))
    return crumbs


@storage_bp.route("/")
@login_required
def index():
    user = get_current_user()
    rel_path = request.args.get("path", "").strip("/")
    abs_path = _safe_join(rel_path)

    if not os.path.isdir(abs_path):
        # kalau folder gak ketemu (misal disk belum ke-mount), balik ke root
        rel_path = ""
        abs_path = _safe_join("")
        os.makedirs(abs_path, exist_ok=True)

    folders = []
    files = []
    try:
        entries = sorted(os.listdir(abs_path), key=lambda x: x.lower())
    except FileNotFoundError:
        entries = []

    for name in entries:
        full = os.path.join(abs_path, name)
        entry_rel = f"{rel_path}/{name}".strip("/") if rel_path else name
        try:
            if os.path.isdir(full):
                folders.append({"name": name, "rel_path": entry_rel})
            else:
                stat = os.stat(full)
                files.append({
                    "name": name,
                    "rel_path": entry_rel,
                    "size": _fmt_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                })
        except OSError:
            continue

    # Info disk (mount point /mnt/data-internal di host, ke-mirror di container)
    try:
        total, used, free = shutil.disk_usage(BASE_PATH)
    except OSError:
        total = used = free = 0
    disk = {
        "total": _fmt_size(total),
        "used": _fmt_size(used),
        "free": _fmt_size(free),
        "percent": round((used / total) * 100, 1) if total else 0,
    }

    return render_template(
        "storage.html",
        user=user,
        rel_path=rel_path,
        breadcrumbs=_breadcrumbs(rel_path),
        folders=folders,
        files=files,
        disk=disk,
    )


@storage_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    rel_path = request.form.get("path", "").strip("/")
    abs_dir = _safe_join(rel_path)
    os.makedirs(abs_dir, exist_ok=True)

    uploaded = request.files.getlist("files")
    for f in uploaded:
        if not f or not f.filename:
            continue
        filename = os.path.basename(f.filename)  # cegah path traversal dari nama file
        dest = os.path.join(abs_dir, filename)
        f.save(dest)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/mkdir", methods=["POST"])
@login_required
def mkdir():
    rel_path = request.form.get("path", "").strip("/")
    nama_folder = request.form.get("nama_folder", "").strip()
    nama_folder = os.path.basename(nama_folder)  # cegah traversal

    if nama_folder:
        abs_dir = _safe_join(rel_path)
        new_dir = os.path.join(abs_dir, nama_folder)
        os.makedirs(new_dir, exist_ok=True)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/rename", methods=["POST"])
@login_required
def rename():
    rel_path = request.form.get("path", "").strip("/")       # folder tempat item berada
    old_name = request.form.get("old_name", "").strip()
    new_name = request.form.get("new_name", "").strip()
    new_name = os.path.basename(new_name)  # cegah traversal

    if old_name and new_name:
        abs_dir = _safe_join(rel_path)
        old_full = os.path.join(abs_dir, os.path.basename(old_name))
        new_full = os.path.join(abs_dir, new_name)
        if os.path.exists(old_full) and not os.path.exists(new_full):
            os.rename(old_full, new_full)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/delete", methods=["POST"])
@login_required
def delete():
    rel_path = request.form.get("path", "").strip("/")        # folder tempat item berada
    target_name = request.form.get("target_name", "").strip()
    target_name = os.path.basename(target_name)  # cegah traversal

    if target_name:
        abs_dir = _safe_join(rel_path)
        target_full = os.path.join(abs_dir, target_name)
        if os.path.isdir(target_full):
            shutil.rmtree(target_full, ignore_errors=True)
        elif os.path.isfile(target_full):
            os.remove(target_full)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/download")
@login_required
def download():
    rel_path = request.args.get("path", "").strip("/")
    abs_path = _safe_join(rel_path)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))
