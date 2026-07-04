"""
dahboard/routes/jadwal.py
Route manajemen jadwal
"""

import io
from datetime import datetime, date
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify
from dashboard.auth import login_required, get_current_user
from db.local import get_conn, upsert_jadwal, delete_jadwal, get_jadwal_by_bulan, get_all_nama_jadwal

jadwal_bp = Blueprint("jadwal", __name__, url_prefix="/jadwal")

def jadwal_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("manager", "kepala_support", "support"):
            return redirect(url_for("auth.index"))
        return func(*args, **kwargs)
    return wrapper

def can_edit():
    """"cek boleh edit apa ga."""
    return session.get("role") in ("manager", "kepala_support")

def get_hari_libur(tahun: int) -> dict:
    """Ambil hari libur dari database lokal."""
    from db.local import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tanggal, nama FROM hari_libur WHERE tanggal LIKE ?",
            (f"{tahun}%",)
        ).fetchall()
        return {r["tanggal"]: r["nama"] for r in rows}
    
# Kalender
@jadwal_bp.route("/")
@login_required
@jadwal_required
def index():
    user = get_current_user()
    tahun = int(request.args.get("tahun", date.today().year))
    bulan = int(request.args.get("bulan", date.today().month))

    jadwal_list = get_jadwal_by_bulan(tahun, bulan)
    hari_libur = get_hari_libur(tahun)

    #kelompokin pertanggal
    jadwal_map = {}
    for j in jadwal_list:
        tgl = j["tanggal"]
        if tgl not in jadwal_map:
            jadwal_map[tgl] = {"oc": [], "piket": [], "off": []}
        jadwal_map[tgl][j["tipe"]].append(j)
    
    #hitung hari dalam bulan
    import calendar
    _, days_in_month = calendar.monthrange(tahun, bulan)
    first_weekday = date(tahun, bulan, 1).weekday()  #0=senin

    nama_list = get_all_nama_jadwal()
    with get_conn() as conn:
        whitelist = conn.execute(
            "SELECT nama_jadwal, telegram_user_id FROM whitelist WHERE nama_jadwal IS NOT NULL"
        ).fetchall()

    return render_template("jadwal.html",
        user=user,
        tahun=tahun,
        bulan=bulan,
        bulan_nama=["Januari","Februari","Maret","April","Mei","Juni",
                    "Juli","Agustus","September","Oktober","November","Desember"][bulan-1],
        days_in_month=days_in_month,
        first_weekday=first_weekday,
        jadwal_map=jadwal_map,
        hari_libur=hari_libur,
        nama_list=nama_list,
        can_edit=can_edit(),
        whitelist=whitelist,
        today_str=date.today().strftime("%Y-%m-%d"),
        )

#UPLOAD EXCEL
@jadwal_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    if not can_edit():
        return redirect(url_for("jadwal.index"))

    file = request.files.get("file")
    if not file or not file.filename.endswith(".xlsx"):
        return redirect(url_for("jadwal.index"))

    wb = openpyxl.load_workbook(file)
    ws = wb.active

    headers = [str(cell.value).strip().lower() if cell.value else "" for cell in ws[1]]

    try:
        idx_nama    = headers.index("nama")
        idx_tanggal = headers.index("tanggal")
        idx_oc      = headers.index("oc")
        idx_piket   = headers.index("piket")
        idx_off     = headers.index("off")
    except ValueError:
        return redirect(url_for("jadwal.index"))

    count = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        nama    = str(row[idx_nama]).strip() if row[idx_nama] else None
        tanggal = row[idx_tanggal]
        oc      = row[idx_oc]
        piket   = row[idx_piket]
        off     = row[idx_off]

        if not nama or not tanggal:
            continue

        if isinstance(tanggal, datetime):
            tanggal_str = tanggal.strftime("%Y-%m-%d")
        else:
            tanggal_str = str(tanggal).strip()

        if oc and str(oc).upper() in ("Y", "YES", "1", "TRUE", "✓"):
            upsert_jadwal(nama, tanggal_str, "oc")
            count += 1
        if piket and str(piket).upper() in ("Y", "YES", "1", "TRUE", "✓"):
            upsert_jadwal(nama, tanggal_str, "piket")
            count += 1
        if off and str(off).upper() in ("Y", "YES", "1", "TRUE", "✓"):
            upsert_jadwal(nama, tanggal_str, "off")
            count += 1

    return redirect(url_for("jadwal.index"))

#input manual
@jadwal_bp.route("/tambah", methods=["POST"])
@login_required
def tambah():
    if not can_edit():
        return redirect(url_for("jadwal.index"))

    nama    = request.form.get("nama", "").strip()
    tanggal = request.form.get("tanggal", "").strip()
    tipe    = request.form.get("tipe", "").strip()

    if nama and tanggal and tipe in ("oc", "piket", "off"):
        upsert_jadwal(nama, tanggal, tipe)

    return redirect(url_for("jadwal.index") + f"?tahun={tanggal[:4]}&bulan={int(tanggal[5:7])}")

#apus jadwal
@jadwal_bp.route("/hapus/<int:jadwal_id>", methods=["POST"])
@login_required
def hapus(jadwal_id):
    if not can_edit():
        return redirect(url_for("jadwal.index"))
    delete_jadwal(jadwal_id)
    return redirect(url_for("jadwal.index"))

#template excel
@jadwal_bp.route("/template")
@login_required
def download_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jadwal"

    # Header
    headers = ["nama", "tanggal", "oc", "piket", "off"]
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h.upper())
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Contoh data
    contoh = [
        ["Azmii", "2026-07-01", "Y", "", ""],
        ["Noval", "2026-07-01", "", "Y", ""],
        ["Febry", "2026-07-02", "", "", "Y"],
    ]
    for row_data in contoh:
        ws.append(row_data)

    # Lebar kolom
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 8
    ws.column_dimensions["E"].width = 8

    # Catatan
    ws.append([])
    ws.append(["Keterangan: isi kolom OC/Piket/Off dengan Y jika bertugas"])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="template_jadwal.xlsx"
    )