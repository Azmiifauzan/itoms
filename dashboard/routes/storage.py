"""
dashboard/routes/storage.py
Menu Penyimpanan — file manager sederhana ke folder /app/data-internal
(mount dari disk host /mnt/data-internal, dipakai bareng aplikasi lain).

Semua role yang login boleh: lihat, upload (file/folder/drag-drop), rename, hapus,
download file, download folder (di-zip), buat folder.

Privasi folder (cuma bisa diset pas folder BARU dibikin):
  - public   : semua orang bisa lihat & akses (default, sama seperti sebelumnya)
  - private  : cuma owner + superadmin yang bisa lihat folder itu ada (invisible buat yang lain)
  - password : semua orang bisa LIHAT nama foldernya, tapi harus masukin password buat masuk
               (owner & superadmin selalu bisa masuk tanpa password)

Tracking "diupload oleh" / "diedit oleh" disimpan di tabel file_meta.
Privasi folder disimpan di tabel folder_perm.
"""

import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    send_file, abort, session
)
from werkzeug.security import generate_password_hash, check_password_hash
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
    rel_path = (rel_path or "").strip().lstrip("/")
    candidate = os.path.normpath(os.path.join(BASE_PATH, rel_path))
    base_abs = os.path.abspath(BASE_PATH)
    candidate_abs = os.path.abspath(candidate)
    if not (candidate_abs == base_abs or candidate_abs.startswith(base_abs + os.sep)):
        abort(400, "Path tidak valid")
    return candidate_abs


def _sanitize_relative_filename(raw_name: str) -> list:
    raw_name = (raw_name or "").replace("\\", "/")
    return [p for p in raw_name.split("/") if p not in ("", ".", "..")]


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
    crumbs, acc = [], []
    for p in parts:
        acc.append(p)
        crumbs.append((p, "/".join(acc)))
    return crumbs


def _current_nama() -> str:
    user = get_current_user()
    if user and isinstance(user, dict):
        return user.get("nama") or session.get("nama") or "Unknown"
    return session.get("nama", "Unknown")


def _current_role() -> str:
    return session.get("role", "")


# ──────────────────────────────────────────
# Metadata upload/edit — tabel file_meta
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
                uploaded_by = excluded.uploaded_by, uploaded_at = excluded.uploaded_at
        """, (rel_path, nama, now))
        conn.commit()


def _rename_meta(old_rel: str, new_rel: str, is_folder: bool, nama: str):
    with get_conn() as conn:
        _ensure_meta_table(conn)
        if is_folder:
            rows = conn.execute(
                "SELECT * FROM file_meta WHERE rel_path = ? OR rel_path LIKE ?",
                (old_rel, old_rel + "/%")
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM file_meta WHERE rel_path = ?", (old_rel,)).fetchall()

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for r in rows:
            new_path = new_rel + r["rel_path"][len(old_rel):]
            conn.execute("DELETE FROM file_meta WHERE rel_path = ?", (r["rel_path"],))
            conn.execute("""
                INSERT INTO file_meta (rel_path, uploaded_by, uploaded_at, edited_by, edited_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET
                    uploaded_by=excluded.uploaded_by, uploaded_at=excluded.uploaded_at,
                    edited_by=excluded.edited_by, edited_at=excluded.edited_at
            """, (new_path, r["uploaded_by"], r["uploaded_at"], nama, now))
        if not rows:
            conn.execute("""
                INSERT INTO file_meta (rel_path, edited_by, edited_at) VALUES (?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET edited_by=excluded.edited_by, edited_at=excluded.edited_at
            """, (new_rel, nama, now))
        conn.commit()


def _delete_meta(rel_path: str, is_folder: bool):
    with get_conn() as conn:
        _ensure_meta_table(conn)
        if is_folder:
            conn.execute("DELETE FROM file_meta WHERE rel_path = ? OR rel_path LIKE ?", (rel_path, rel_path + "/%"))
        else:
            conn.execute("DELETE FROM file_meta WHERE rel_path = ?", (rel_path,))
        conn.commit()


def _get_meta_map(rel_paths: list) -> dict:
    if not rel_paths:
        return {}
    with get_conn() as conn:
        _ensure_meta_table(conn)
        placeholders = ",".join("?" for _ in rel_paths)
        rows = conn.execute(f"SELECT * FROM file_meta WHERE rel_path IN ({placeholders})", rel_paths).fetchall()
        return {r["rel_path"]: dict(r) for r in rows}


# ──────────────────────────────────────────
# Privasi folder — tabel folder_perm
# ──────────────────────────────────────────

def _ensure_perm_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS folder_perm (
            rel_path      TEXT PRIMARY KEY,
            mode          TEXT NOT NULL CHECK(mode IN ('public','private','password')),
            owner         TEXT,
            password_hash TEXT,
            created_at    TEXT
        )
    """)


def _set_folder_perm(rel_path: str, mode: str, owner: str, password: str = None):
    with get_conn() as conn:
        _ensure_perm_table(conn)
        pw_hash = generate_password_hash(password) if (mode == "password" and password) else None
        conn.execute("""
            INSERT INTO folder_perm (rel_path, mode, owner, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rel_path) DO UPDATE SET mode=excluded.mode, owner=excluded.owner,
                password_hash=excluded.password_hash
        """, (rel_path, mode, owner, pw_hash, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()


def _rename_folder_perm(old_rel: str, new_rel: str):
    with get_conn() as conn:
        _ensure_perm_table(conn)
        rows = conn.execute(
            "SELECT * FROM folder_perm WHERE rel_path = ? OR rel_path LIKE ?",
            (old_rel, old_rel + "/%")
        ).fetchall()
        for r in rows:
            new_path = new_rel + r["rel_path"][len(old_rel):]
            conn.execute("DELETE FROM folder_perm WHERE rel_path = ?", (r["rel_path"],))
            conn.execute("""
                INSERT INTO folder_perm (rel_path, mode, owner, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (new_path, r["mode"], r["owner"], r["password_hash"], r["created_at"]))
        conn.commit()


def _delete_folder_perm(rel_path: str):
    with get_conn() as conn:
        _ensure_perm_table(conn)
        conn.execute("DELETE FROM folder_perm WHERE rel_path = ? OR rel_path LIKE ?", (rel_path, rel_path + "/%"))
        conn.commit()


def _get_perm_map(rel_paths: list) -> dict:
    """Ambil entri perm LANGSUNG (bukan warisan) buat sekumpulan path — dipakai buat nampilin list."""
    if not rel_paths:
        return {}
    with get_conn() as conn:
        _ensure_perm_table(conn)
        placeholders = ",".join("?" for _ in rel_paths)
        rows = conn.execute(f"SELECT * FROM folder_perm WHERE rel_path IN ({placeholders})", rel_paths).fetchall()
        return {r["rel_path"]: dict(r) for r in rows}


def _get_governing_perm(rel_path: str):
    """
    Cari aturan privasi yang berlaku buat rel_path ini — cek dari path itu sendiri,
    naik ke folder induk, sampai ke root. Entri terdekat yang menang.
    Return dict perm, atau None kalau publik (gak ada aturan sama sekali).
    """
    rel_path = (rel_path or "").strip("/")
    if not rel_path:
        return None
    parts = rel_path.split("/")
    with get_conn() as conn:
        _ensure_perm_table(conn)
        for i in range(len(parts), 0, -1):
            candidate = "/".join(parts[:i])
            row = conn.execute("SELECT * FROM folder_perm WHERE rel_path = ?", (candidate,)).fetchone()
            if row:
                return dict(row)
    return None


def _check_access(governing: dict, rel_path: str, nama: str, role: str) -> str:
    """Return 'allow' / 'deny' / 'need_password'."""
    if governing is None:
        return "allow"
    if role == "superadmin":
        return "allow"
    if governing.get("owner") == nama:
        return "allow"
    mode = governing.get("mode")
    if mode == "public":
        return "allow"
    if mode == "private":
        return "deny"
    if mode == "password":
        unlocked = session.get("unlocked_folders", [])
        if governing["rel_path"] in unlocked:
            return "allow"
        return "need_password"
    return "deny"


def _enforce_access(rel_path: str):
    """Dipakai di route non-interaktif (upload/rename/delete/download) — block kalau gak boleh."""
    governing = _get_governing_perm(rel_path)
    status = _check_access(governing, rel_path, _current_nama(), _current_role())
    if status != "allow":
        abort(403)


# ──────────────────────────────────────────
# Routes — browse
# ──────────────────────────────────────────

@storage_bp.route("/")
@login_required
def index():
    user = get_current_user()
    nama = _current_nama()
    role = _current_role()
    rel_path = request.args.get("path", "").strip("/")
    abs_path = _safe_join(rel_path)

    if not os.path.isdir(abs_path):
        rel_path = ""
        abs_path = _safe_join("")
        os.makedirs(abs_path, exist_ok=True)

    # Cek akses ke folder yang lagi dibuka
    governing = _get_governing_perm(rel_path)
    status = _check_access(governing, rel_path, nama, role)
    if status == "deny":
        return render_template("storage_locked.html", user=user, rel_path=rel_path, mode="denied")
    if status == "need_password":
        return render_template("storage_locked.html", user=user, rel_path=rel_path, mode="password")

    folders, files = [], []
    try:
        entries = sorted(os.listdir(abs_path), key=lambda x: x.lower())
    except FileNotFoundError:
        entries = []

    all_rel = []
    folder_rel_list = []
    for name in entries:
        full = os.path.join(abs_path, name)
        entry_rel = f"{rel_path}/{name}".strip("/") if rel_path else name
        all_rel.append(entry_rel)
        try:
            if os.path.isdir(full):
                folders.append({"name": name, "rel_path": entry_rel})
                folder_rel_list.append(entry_rel)
            else:
                stat = os.stat(full)
                files.append({"name": name, "rel_path": entry_rel, "size": _fmt_size(stat.st_size)})
        except OSError:
            continue

    meta_map = _get_meta_map(all_rel)
    perm_map = _get_perm_map(folder_rel_list)

    # Filter folder privat (invisible buat yang bukan owner/superadmin), tandain folder password
    visible_folders = []
    for f in folders:
        f["meta"] = meta_map.get(f["rel_path"])
        perm = perm_map.get(f["rel_path"])
        f["perm_mode"] = perm["mode"] if perm else "public"
        f["perm_owner"] = perm["owner"] if perm else None
        if perm and perm["mode"] == "private" and role != "superadmin" and perm["owner"] != nama:
            continue  # invisible
        visible_folders.append(f)

    for f in files:
        f["meta"] = meta_map.get(f["rel_path"])

    try:
        total, used, free = shutil.disk_usage(BASE_PATH)
    except OSError:
        total = used = free = 0
    disk = {
        "total": _fmt_size(total), "used": _fmt_size(used), "free": _fmt_size(free),
        "percent": round((used / total) * 100, 1) if total else 0,
    }

    return render_template(
        "storage.html",
        user=user, rel_path=rel_path, breadcrumbs=_breadcrumbs(rel_path),
        folders=visible_folders, files=files, disk=disk,
        current_nama=nama, current_role=role,
    )


@storage_bp.route("/unlock", methods=["POST"])
@login_required
def unlock():
    rel_path = request.form.get("path", "").strip("/")
    password = request.form.get("password", "")

    governing = _get_governing_perm(rel_path)
    if governing and governing["mode"] == "password" and governing["password_hash"]:
        if check_password_hash(governing["password_hash"], password):
            unlocked = session.get("unlocked_folders", [])
            if governing["rel_path"] not in unlocked:
                unlocked.append(governing["rel_path"])
            session["unlocked_folders"] = unlocked
            return redirect(url_for("storage.index", path=rel_path))

    return render_template(
        "storage_locked.html", user=get_current_user(), rel_path=rel_path,
        mode="password", error="Password salah, coba lagi."
    )


# ──────────────────────────────────────────
# Routes — upload / mkdir / rename / delete / download
# ──────────────────────────────────────────

@storage_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    rel_path = request.form.get("path", "").strip("/")
    _enforce_access(rel_path)

    abs_dir = _safe_join(rel_path)
    os.makedirs(abs_dir, exist_ok=True)
    nama = _current_nama()

    for f in request.files.getlist("files"):
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
    _enforce_access(rel_path)

    nama_folder = os.path.basename(request.form.get("nama_folder", "").strip())
    privasi = request.form.get("privasi", "public")
    password = request.form.get("privasi_password", "").strip()

    if nama_folder:
        abs_dir = _safe_join(rel_path)
        os.makedirs(os.path.join(abs_dir, nama_folder), exist_ok=True)
        meta_rel = f"{rel_path}/{nama_folder}".strip("/") if rel_path else nama_folder
        nama = _current_nama()
        _mark_uploaded(meta_rel, nama)

        if privasi in ("private", "password"):
            _set_folder_perm(meta_rel, privasi, nama, password if privasi == "password" else None)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/rename", methods=["POST"])
@login_required
def rename():
    rel_path = request.form.get("path", "").strip("/")
    _enforce_access(rel_path)

    old_name = request.form.get("old_name", "").strip()
    new_name = os.path.basename(request.form.get("new_name", "").strip())

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
            if is_folder:
                _rename_folder_perm(old_rel, new_rel)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/delete", methods=["POST"])
@login_required
def delete():
    rel_path = request.form.get("path", "").strip("/")
    _enforce_access(rel_path)

    target_name = os.path.basename(request.form.get("target_name", "").strip())
    if target_name:
        abs_dir = _safe_join(rel_path)
        target_full = os.path.join(abs_dir, target_name)
        target_rel = f"{rel_path}/{target_name}".strip("/") if rel_path else target_name
        if os.path.isdir(target_full):
            shutil.rmtree(target_full, ignore_errors=True)
            _delete_meta(target_rel, is_folder=True)
            _delete_folder_perm(target_rel)
        elif os.path.isfile(target_full):
            os.remove(target_full)
            _delete_meta(target_rel, is_folder=False)

    return redirect(url_for("storage.index", path=rel_path))


@storage_bp.route("/download")
@login_required
def download():
    rel_path = request.args.get("path", "").strip("/")
    parent = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    _enforce_access(parent)

    abs_path = _safe_join(rel_path)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True, download_name=os.path.basename(abs_path))


@storage_bp.route("/download-folder")
@login_required
def download_folder():
    rel_path = request.args.get("path", "").strip("/")
    _enforce_access(rel_path)

    abs_path = _safe_join(rel_path)
    if not os.path.isdir(abs_path):
        abort(404)

    folder_name = os.path.basename(abs_path) or "root"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(abs_path):
                for fn in files:
                    full = os.path.join(root, fn)
                    arcname = os.path.join(folder_name, os.path.relpath(full, abs_path))
                    zf.write(full, arcname)
    except Exception:
        os.remove(tmp_path)
        raise

    response = send_file(tmp_path, as_attachment=True, download_name=f"{folder_name}.zip", mimetype="application/zip")

    @response.call_on_close
    def _cleanup_tmp():
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return response
