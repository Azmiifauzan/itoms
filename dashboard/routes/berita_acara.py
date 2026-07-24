"""
dashboard/routes/berita_acara.py
Fitur "Berita Acara" — form kerusakan unit di outlet, auto-generate PDF
dengan 4 tanda tangan:
  1. Kasir/Leader/PIC/SPV outlet -> diupload manual tiap kali (orang outlet
     gak punya akun sistem)
  2. Support -> otomatis dari user yang login & bikin BA ini, tanda tangan
     diambil dari whitelist.signature_path
  3. MIC -> sengaja DIKOSONGIN di PDF, ditandatangan manual belakangan
  4. Manager IT -> fixed 1 orang (whitelist.is_manager_it = true), tanda
     tangan diambil dari whitelist.signature_path

PDF di-generate pakai WeasyPrint (HTML -> PDF) lalu disimpan langsung ke
folder storage yang sama dengan "File Kita Bersama", biar bisa diakses juga
dari situ.
"""

import os
import base64
import uuid
from datetime import datetime, timezone, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    send_from_directory, abort,
)
from werkzeug.utils import secure_filename
from weasyprint import HTML
from dashboard.auth import login_required, get_current_user, has_permission
from db.local import get_conn
from db.hris import get_company_list, get_outlet_list, search_employee

berita_acara_bp = Blueprint("berita_acara", __name__, url_prefix="/berita-acara")

COMPANY_MODE_OFFICE = {42, 36}
WIB = timezone(timedelta(hours=7))

BASE_PATH = os.environ.get("STORAGE_BASE_PATH", "/app/data-internal")
SIGNATURE_DIR = os.path.join(BASE_PATH, "signatures")              # TTD user (whitelist), dipakai berulang
OUTLET_SIG_DIR = os.path.join(BASE_PATH, "berita-acara-ttd-outlet")  # TTD outlet, sekali pakai per-BA
BA_PDF_DIR = os.path.join(BASE_PATH, "Berita Acara")               # PDF hasil generate (ikut nongol di Storage)

ALLOWED_IMG_EXT = {".png", ".jpg", ".jpeg"}


def _now_wib():
    return datetime.now(WIB)


def _simpan_gambar(file_storage, folder, prefix="") -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_IMG_EXT:
        return None
    os.makedirs(folder, exist_ok=True)
    nama_file = f"{prefix}{uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(folder, nama_file))
    return nama_file


def _img_data_uri(folder, filename) -> str | None:
    """Baca file gambar dan ubah jadi base64 data-uri, biar WeasyPrint gak
    perlu resolve path filesystem sama sekali (paling aman & portable)."""
    if not filename:
        return None
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        return None
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = "jpeg" if ext == "jpg" else ext
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def _get_manager_it():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM whitelist WHERE is_manager_it = TRUE LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


# ──────────────────────────────────────────
# List + input
# ──────────────────────────────────────────

@berita_acara_bp.route("/")
@login_required
def index():
    user = get_current_user()
    bisa_edit = has_permission("edit_berita_acara")
    manager_it = _get_manager_it()

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT ba.*, w.nama as dibuat_oleh_nama
            FROM berita_acara ba
            LEFT JOIN whitelist w ON ba.dibuat_oleh = w.user_id
            ORDER BY ba.created_at DESC
            LIMIT 200
        """).fetchall()
        artikel_list = conn.execute("SELECT nama FROM artikel ORDER BY nama").fetchall()

    company_list = get_company_list()

    company_id_str = request.args.get("company_id", "").strip()
    selected_company_id = int(company_id_str) if company_id_str.isdigit() else None
    mode = None
    outlet_list = []
    nama_pt = None
    if selected_company_id:
        mode = "office" if selected_company_id in COMPANY_MODE_OFFICE else "outlet"
        if mode == "outlet":
            outlet_list = get_outlet_list(selected_company_id)
        match = next((c for c in company_list if c["company_id"] == selected_company_id), None)
        nama_pt = match["nama_pt"] if match else None

    return render_template("berita_acara.html",
        user=user, rows=rows, bisa_edit=bisa_edit,
        artikel_list=artikel_list, manager_it=manager_it,
        user_punya_ttd=bool(user.get("signature_path")),
        company_list=company_list, selected_company_id=selected_company_id,
        mode=mode, outlet_list=outlet_list, nama_pt=nama_pt,
    )


@berita_acara_bp.route("/search-karyawan")
@login_required
def search_karyawan():
    from flask import jsonify
    q = request.args.get("q", "").strip()
    company_id = request.args.get("company_id", type=int)
    if not q or not company_id or len(q) < 2:
        return jsonify([])
    return jsonify(search_employee(q, company_id))


@berita_acara_bp.route("/buat", methods=["POST"])
@login_required
def buat():
    user = get_current_user()
    company_id_str = request.form.get("company_id", "").strip()
    company_id = int(company_id_str) if company_id_str.isdigit() else None
    nama_pt = request.form.get("nama_pt", "").strip()
    mode = "office" if company_id in COMPANY_MODE_OFFICE else "outlet"

    if mode == "office":
        nama_karyawan = request.form.get("nama_karyawan", "").strip()
        divisi = request.form.get("divisi", "").strip()
        kode_outlet = ""
        nama_outlet = f"{nama_karyawan} — {divisi}" if divisi else nama_karyawan
    else:
        kode_outlet = request.form.get("kode_outlet", "").strip()
        nama_outlet = request.form.get("nama_outlet", "").strip()

    tanggal_kejadian = request.form.get("tanggal_kejadian", "").strip()
    nama_unit = request.form.get("nama_unit", "").strip()
    penyebab_list = [p.strip() for p in request.form.getlist("penyebab[]") if p.strip()]
    sparepart_list = [s.strip() for s in request.form.getlist("sparepart[]") if s.strip()]
    nama_outlet_signer = request.form.get("nama_outlet_signer", "").strip()
    outlet_signature = request.files.get("outlet_signature")

    if not (nama_outlet and tanggal_kejadian and nama_unit and nama_outlet_signer):
        return redirect(url_for("berita_acara.index"))

    outlet_sig_file = _simpan_gambar(outlet_signature, OUTLET_SIG_DIR, prefix="outlet_")
    manager_it = _get_manager_it()

    with get_conn() as conn:
        from psycopg2.extras import Json
        cur = conn.execute("""
            INSERT INTO berita_acara
                (kode_outlet, nama_outlet, tanggal_kejadian, nama_unit, penyebab, sparepart,
                 nama_outlet_signer, outlet_signature_path, support_id, manager_it_id, dibuat_oleh,
                 company_id, nama_pt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (kode_outlet, nama_outlet, tanggal_kejadian, nama_unit,
              Json(penyebab_list), Json(sparepart_list),
              nama_outlet_signer, outlet_sig_file, user["user_id"],
              manager_it["user_id"] if manager_it else None, user["user_id"],
              company_id, nama_pt))
        ba_id = cur.fetchone()["id"]
        conn.commit()

    _generate_pdf(ba_id)
    return redirect(url_for("berita_acara.index"))


def _generate_pdf(ba_id: int):
    with get_conn() as conn:
        ba = conn.execute("SELECT * FROM berita_acara WHERE id = ?", (ba_id,)).fetchone()
        if not ba:
            return
        ba = dict(ba)
        support = conn.execute("SELECT * FROM whitelist WHERE user_id = ?", (ba["support_id"],)).fetchone()
        support = dict(support) if support else None
        manager_it = conn.execute("SELECT * FROM whitelist WHERE user_id = ?", (ba["manager_it_id"],)).fetchone() if ba["manager_it_id"] else None
        manager_it = dict(manager_it) if manager_it else None

    outlet_sig_uri = _img_data_uri(OUTLET_SIG_DIR, ba["outlet_signature_path"])
    support_sig_uri = _img_data_uri(SIGNATURE_DIR, support["signature_path"]) if support else None
    # Manager IT: namanya tetap auto-terisi (biar formatnya kayak dokumen asli
    # "Manager IT (Nurullah)"), TAPI tanda tangannya sengaja TIDAK ditempel
    # otomatis -- tetap manual kayak MIC, sesuai instruksi.
    manager_sig_uri = None

    html_string = render_template("berita_acara_pdf.html",
        ba=ba, support=support, manager_it=manager_it,
        outlet_sig_uri=outlet_sig_uri, support_sig_uri=support_sig_uri,
        manager_sig_uri=manager_sig_uri,
    )
    pdf_bytes = HTML(string=html_string).write_pdf()

    tgl = ba["tanggal_kejadian"]
    subfolder = f"{tgl.year:04d}-{tgl.month:02d}"
    folder = os.path.join(BA_PDF_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    nama_file = f"BA-{ba['kode_outlet']}-{tgl.isoformat()}-{ba_id}.pdf"
    with open(os.path.join(folder, nama_file), "wb") as f:
        f.write(pdf_bytes)

    rel_path = f"Berita Acara/{subfolder}/{nama_file}"
    with get_conn() as conn:
        conn.execute("UPDATE berita_acara SET pdf_path = ? WHERE id = ?", (rel_path, ba_id))
        conn.commit()


@berita_acara_bp.route("/<int:ba_id>/hapus", methods=["POST"])
@login_required
def hapus(ba_id):
    if not has_permission("edit_berita_acara"):
        abort(403)
    with get_conn() as conn:
        row = conn.execute("SELECT outlet_signature_path, pdf_path FROM berita_acara WHERE id = ?", (ba_id,)).fetchone()
        if row:
            if row["outlet_signature_path"]:
                p = os.path.join(OUTLET_SIG_DIR, row["outlet_signature_path"])
                if os.path.isfile(p):
                    os.remove(p)
            if row["pdf_path"]:
                p = os.path.join(BASE_PATH, row["pdf_path"])
                if os.path.isfile(p):
                    os.remove(p)
        conn.execute("DELETE FROM berita_acara WHERE id = ?", (ba_id,))
        conn.commit()
    return redirect(url_for("berita_acara.index"))

@berita_acara_bp.route("/<int:ba_id>/toggle-rdo", methods=["POST"])
@login_required
def toggle_rdo(ba_id):
    with get_conn() as conn:
        conn.execute("UPDATE berita_acara SET rdo_dibuat = NOT rdo_dibuat WHERE id = ?", (ba_id,))
        conn.commit()
    return redirect(url_for("berita_acara.index"))


@berita_acara_bp.route("/<int:ba_id>/toggle-gudang", methods=["POST"])
@login_required
def toggle_gudang(ba_id):
    with get_conn() as conn:
        conn.execute("UPDATE berita_acara SET dikirim_gudang = NOT dikirim_gudang WHERE id = ?", (ba_id,))
        conn.commit()
    return redirect(url_for("berita_acara.index"))


@berita_acara_bp.route("/<int:ba_id>/download")
@login_required
def download(ba_id):
    with get_conn() as conn:
        row = conn.execute("SELECT pdf_path FROM berita_acara WHERE id = ?", (ba_id,)).fetchone()
    if not row or not row["pdf_path"]:
        abort(404)
    folder = os.path.join(BASE_PATH, os.path.dirname(row["pdf_path"]))
    filename = os.path.basename(row["pdf_path"])
    return send_from_directory(folder, filename, as_attachment=False)