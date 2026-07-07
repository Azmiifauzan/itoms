"""
dashboard/routes/storage.py
Menu Penyimpanan — file manager sederhana ke folder /app/data-internal
(mount dari disk host /mnt/data-internal, dipakai bareng aplikasi lain).
Semua role yang login boleh: lihat, upload (file/folder/drag-drop), rename, hapus, download, buat folder.
Tracking "diupload oleh" dan "diedit oleh" disimpan di tabel file_meta.
"""

import os
import shutil
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, send_file, abort, session
from dashboard.auth import login_required, get_current_user
from db.local import get_conn

storage_bp = Blueprint("storage", __name__, url_prefix="/storage")

# Path folder di dalam container. Harus di-mount di docker-compose.yml:
#   volumes:
#     - /mnt/data-internal:/app/data-internal
BASE_PATH = os.environ.get("STORAGE_BASE_PATH", "/app/data-internal")


# ──────────────────────────────────────────
# Helper umum
# ──────────────────────────────────────────

def _safe_join(rel_path: str) -> str:
    """Gabungkan BASE_PATH + rel_path dengan aman, cegah path traversal."""
    rel_path = (rel_path or "").strip().lstrip("/")
    candidate = os.path.normpath(os.path.join(BASE_PATH, rel_path))
    base_abs = os.path.abspath(BASE_PATH)
    candidate_abs = os.path.abspath(candidate)
    if not (candidate_abs == base_abs or candidate_abs.startswith(base_abs + os.sep)):
        abort(400, "Path tidak valid")
    return candidate_abs


def _sanitize_relative_filename(raw_name: str) -> list:
    """
    Terima nama file yang mungkin mengandung subfolder (dari upload folder
    atau drag-drop), pecah jadi list bagian yang aman (tanpa '..' atau kosong).
    """
    raw_name = (raw_name or "").replace("\\", "/")
    parts = [p for p in raw_name.split("/") if p not in ("", ".", "..")]
    return parts


def _fmt_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _breadcrumbs(rel_path: str):
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


def _current_nama() -> str:
    user = get_current_user()
    if user and isinstance(user, dict):
        return user.get("nama") or session.get("nama") or "Unknown"
    return session.get("nama", "Unknown")


# ──────────────────────────────────────────
# Metadata (siapa upload / edit) — tabel file_meta
# ──────────────────────────────────────────

def _ensure_meta_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_meta (
            rel_path     TEXT PRIMARY KEY,
            uploaded_by  TEXT,
            uploaded_at  TEXT,
            edited_by    TEXT,
            edited_at    TEXT
        )
    """)


def _mark_uploaded(rel_path: str, nama: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        _ensure_meta_table(conn)
        conn.execute("""
            INSERT INTO file_meta (rel_path, uploaded_by, uploaded_at)
            VALUES (?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET
                uploaded_by = excluded.uploaded_by,
                uploaded_at = excluded.uploaded_at
        """, (rel_path, nama, now))
        conn.commit()


def _mark_edited(rel_path: str, nama: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        _ensure_meta_table(conn)
        conn.execute("""
            INSERT INTO file_meta (rel_path, edited_by, edited_at)
            VALUES (?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET
                edited_by = excluded.edited_by,
                edited_at = excluded.edited_at
        """, (rel_path, nama, now))
        conn.commit()


def _rename_meta(old_rel: str, new_rel: str, is_folder: bool, nama: str):
    """Pindahin baris metadata dari path lama ke path baru (support isi folder)."""
    with get_conn() as conn:
        _ensure_meta_table(conn)
        if is_folder:
            rows = conn.execute(
                "SELECT * FROM file_meta WHERE rel_path = ? OR rel_path LIKE ?",
                (old_rel, old_rel + "/%")
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM file_meta WHERE rel_path = ?", (old_rel,)
            ).fetchall()

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for r in rows:
            new_path = new_rel + r["rel_path"][len(old_rel):]
            conn.execute("DELETE FROM file_meta WHERE rel_path = ?", (r["rel_path"],))
            conn.execute("""
                INSERT INTO file_meta (rel_path, uploaded_by, uploaded_at, edited_by, edited_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET
                    uploaded_by = excluded.uploaded_by, uploaded_at = excluded.uploaded_at,
                    edited_by = excluded.edited_by, edited_at = excluded.edited_at
            """, (new_path, r["uploaded_by"], r["uploaded_at"], nama, now))

        if not rows:
            conn.execute("""
                INSERT INTO file_meta (rel_path, edited_by, edited_at)
                VALUES (?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET edited_by = excluded.edited_by, edited_at = excluded.edited_at
            """, (new_rel, nama, now))
        conn.commit()


def _delete_meta(rel_path: str, is_folder: bool):
    with get_conn() as conn:
        _ensure_meta_table(conn)
        if is_folder:
            conn.execute(
                "DELETE FROM file_meta WHERE rel_path = ? OR rel_path LIKE ?",
                (rel_path, rel_path + "/%")
            )
        else:
            conn.execute("DELETE FROM file_meta WHERE rel_path = ?", (rel_path,))
        conn.commit()


def _get_meta_map(rel_paths: list) -> dict:
    if not rel_paths:
        return {}
    with get_conn() as conn:
        _ensure_meta_table(conn)
        placeholders = ",".join("?" for _ in rel_paths)
        rows = conn.execute(
            f"SELECT * FROM file_meta WHERE rel_path IN ({placeholders})",
            rel_paths
        ).fetchall()
        return {r["rel_path"]: dict(r) for r in rows}


# ──────────────────────────────────────────
# Routes
# ──────────────────────────────────────────

@storage_bp.route("/")
@login_required
def index():
    user = get_current_user()
    rel_path = request.args.get("path", "").strip("/")
    abs_path = _safe_join(rel_path)

    if not os.path.isdir(abs_path):
        rel_path = ""
        abs_path = _safe_join("")
        os.makedirs(abs_path, exist_ok=True)

    folders, files = [], []
    try:
        entries = sorted(os.listdir(abs_path), key=lambda x: x.lower())
    except FileNotFoundError:
        entries = []

    all_rel = []
    for name in entries:
        full = os.path.join(abs_path, name)
        entry_rel = f"{rel_path}/{name}".strip("/") if rel_path else name
        all_rel.append(entry_rel)
        try:
            if os.path.isdir(full):
                folders.append({"name": name, "rel_path": entry_rel})
            else:
                stat = os.stat(full)
                files.append({
                    "name": name,
                    "rel_path": entry_rel,
                    "size": _fmt_size(stat.st_size),
                })
        except OSError:
            continue

    meta_map = _get_meta_map(all_rel)
    for f in folders:
        f["meta"] = meta_map.get(f["rel_path"])
    for f in files:
        f["meta"] = meta_map.get(f["rel_path"])

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
    """
    Terima upload file biasa, upload folder (webkitdirectory), atau drag & drop.
    Untuk folder/drag-drop, nama file yang dikirim dari JS berisi path relatif
    (contoh: "FotoAgustus/sub/gambar.jpg") — kita pecah dan buat subfoldernya.
    """
    rel_path = request.form.get("path", "").strip("/")
    abs_dir = _safe_join(rel_path)
    os.makedirs(abs_dir, exist_ok=True)
    nama = _current_nama()

    uploaded = request.files.getlist("files")
    for f in uploaded:
        if not f or not f.filename:
            continue
        parts = _sanitize_relative_filename(f.filename)
        if not parts:
            continue

        dest_abs = _safe_join(os.path.join(rel_path, *parts))
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        f.save(dest_abs)

        meta_rel = "/".join([rel_path] + parts).strip("/") if rel_path else "/".join(parts)
        _mark_uploaded(meta_rel, nama)

    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "redirect": url_for("storage.index", path=rel_path)}

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/mkdir", methods=["POST"])
@login_required
def mkdir():
    rel_path = request.form.get("path", "").strip("/")
    nama_folder = request.form.get("nama_folder", "").strip()
    nama_folder = os.path.basename(nama_folder)

    if nama_folder:
        abs_dir = _safe_join(rel_path)
        new_dir = os.path.join(abs_dir, nama_folder)
        os.makedirs(new_dir, exist_ok=True)
        meta_rel = f"{rel_path}/{nama_folder}".strip("/") if rel_path else nama_folder
        _mark_uploaded(meta_rel, _current_nama())

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/rename", methods=["POST"])
@login_required
def rename():
    rel_path = request.form.get("path", "").strip("/")
    old_name = request.form.get("old_name", "").strip()
    new_name = request.form.get("new_name", "").strip()
    new_name = os.path.basename(new_name)

    if old_name and new_name:
        abs_dir = _safe_join(rel_path)
        old_full = os.path.join(abs_dir, os.path.basename(old_name))
        new_full = os.path.join(abs_dir, new_name)
        if os.path.exists(old_full) and not os.path.exists(new_full):
            is_folder = os.path.isdir(old_full)
            os.rename(old_full, new_full)

            old_rel = f"{rel_path}/{old_name}".strip("/") if rel_path else old_name
            new_rel = f"{rel_path}/{new_name}".strip("/") if rel_path else new_name
            _rename_meta(old_rel, new_rel, is_folder, _current_nama())

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/delete", methods=["POST"])
@login_required
def delete():
    rel_path = request.form.get("path", "").strip("/")
    target_name = request.form.get("target_name", "").strip()
    target_name = os.path.basename(target_name)

    if target_name:
        abs_dir = _safe_join(rel_path)
        target_full = os.path.join(abs_dir, target_name)
        target_rel = f"{rel_path}/{target_name}".strip("/") if rel_path else target_name
        if os.path.isdir(target_full):
            shutil.rmtree(target_full, ignore_errors=True)
            _delete_meta(target_rel, is_folder=True)
        elif os.path.isfile(target_full):
            os.remove(target_full)
            _delete_meta(target_rel, is_folder=False)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/download")
@login_required
def download():
    rel_path = request.args.get("path", "").strip("/")
    abs_path = _safe_join(rel_path)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))
