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
        if session.get("role") not in ("manager", "kepala_support", "support", "superadmin"):
            return redirect(url_for("auth.index"))
        return func(*args, **kwargs)
    return wrapper

def can_edit():
    """"cek boleh edit apa ga."""
    return session.get("role") in ("manager", "kepala_support","superadmin")

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
    with get_conn() as conn:
        whitelist_all = conn.execute(
            "SELECT user_id, nama FROM whitelist ORDER BY nama"
        ).fetchall()
        blackout_list = conn.execute("""
            SELECT b.*, w.nama as nama_user
            FROM blackout b
            JOIN whitelist w ON b.whitelist_id = w.user_id
            WHERE b.tanggal LIKE ?
            ORDER BY b.tanggal, w.nama
        """, (f"{tahun}-{bulan:02d}%",)).fetchall()


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
        whitelist_all=whitelist_all,
        blackout_list=blackout_list,        
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
# ──────────────────────────────────────────
# Blackout (Request Tanggal)
# ──────────────────────────────────────────
@jadwal_bp.route("/blackout/tambah", methods=["POST"])
@login_required
def tambah_blackout():
    if session.get("role") not in ("superadmin", "manager", "kepala_support"):
        return redirect(url_for("jadwal.index"))

    from datetime import timedelta
    whitelist_id = request.form.get("whitelist_id", "").strip()
    tanggal_mulai = request.form.get("tanggal_mulai", "").strip()
    tanggal_selesai = request.form.get("tanggal_selesai", "").strip()
    keterangan = request.form.get("keterangan", "").strip()
    tahun = request.form.get("tahun", date.today().year)
    bulan = request.form.get("bulan", date.today().month)

    if whitelist_id.isdigit() and tanggal_mulai:
        start = datetime.strptime(tanggal_mulai, "%Y-%m-%d").date()
        end = datetime.strptime(tanggal_selesai, "%Y-%m-%d").date() if tanggal_selesai else start
        with get_conn() as conn:
            current = start
            while current <= end:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO blackout (whitelist_id, tanggal, keterangan, dibuat_oleh) VALUES (?, ?, ?, ?)",
                        (int(whitelist_id), current.strftime("%Y-%m-%d"), keterangan or None, session.get("user_id"))
                    )
                    current += timedelta(days=1)
                except Exception:
                    break
            conn.commit()

    return redirect(url_for("jadwal.index", tahun=tahun, bulan=bulan))


@jadwal_bp.route("/blackout/hapus/<int:bid>", methods=["POST"])
@login_required
def hapus_blackout(bid):
    if session.get("role") not in ("superadmin", "manager", "kepala_support"):
        return redirect(url_for("jadwal.index"))
    tahun = request.form.get("tahun", date.today().year)
    bulan = request.form.get("bulan", date.today().month)
    with get_conn() as conn:
        conn.execute("DELETE FROM blackout WHERE id = ?", (bid,))
        conn.commit()
    return redirect(url_for("jadwal.index", tahun=tahun, bulan=bulan))


# ──────────────────────────────────────────
# Generate Jadwal
# ──────────────────────────────────────────
def _generate_jadwal(tahun: int, bulan: int) -> dict:
    """Logic generate jadwal — return dict hasil per tanggal."""
    import calendar as cal_module
    from datetime import timedelta

    with get_conn() as conn:
        oc_list = conn.execute(
            "SELECT user_id, nama FROM whitelist ORDER BY added_at, user_id"
        ).fetchall()
        piket_list = conn.execute("""
            SELECT dp.whitelist_id as user_id, w.nama
            FROM daftar_piket dp
            JOIN whitelist w ON dp.whitelist_id = w.user_id
            ORDER BY dp.urutan
        """).fetchall()
        oc_state = conn.execute(
            "SELECT last_whitelist_id FROM rolling_state WHERE tipe = 'oc'"
        ).fetchone()
        piket_state = conn.execute(
            "SELECT last_whitelist_id FROM rolling_state WHERE tipe = 'piket'"
        ).fetchone()

    oc_ids = [r["user_id"] for r in oc_list]
    oc_names = {r["user_id"]: r["nama"] for r in oc_list}
    piket_ids = [r["user_id"] for r in piket_list]
    piket_names = {r["user_id"]: r["nama"] for r in piket_list}

    if not oc_ids:
        return {}

    last_oc = oc_state["last_whitelist_id"] if oc_state else None
    last_piket = piket_state["last_whitelist_id"] if piket_state else None

    oc_start = (oc_ids.index(last_oc) + 1) % len(oc_ids) if last_oc and last_oc in oc_ids else 0
    piket_start = (piket_ids.index(last_piket) + 1) % len(piket_ids) if last_piket and last_piket in piket_ids else 0

    hari_libur = get_hari_libur(tahun)

    prefix = f"{tahun}-{bulan:02d}"
    with get_conn() as conn:
        bo_rows = conn.execute(
            "SELECT whitelist_id, tanggal FROM blackout WHERE tanggal LIKE ?",
            (f"{prefix}%",)
        ).fetchall()
    blackout = {}
    for r in bo_rows:
        blackout.setdefault(r["whitelist_id"], set()).add(r["tanggal"])

    _, days = cal_module.monthrange(tahun, bulan)
    result = {}
    oc_idx = oc_start
    piket_idx = piket_start

    for day in range(1, days + 1):
        tgl = f"{tahun}-{bulan:02d}-{day:02d}"
        dow = date(tahun, bulan, day).weekday()
        is_weekend = dow >= 5
        is_libur = tgl in hari_libur
        need_piket = is_weekend or is_libur

        result[tgl] = {
            "oc": None, "oc_wid": None, "oc_merah": False,
            "piket": None, "piket_wid": None, "piket_merah": False
        }

        # Generate Piket
        if need_piket and piket_ids:
            assigned = False
            for _ in range(len(piket_ids)):
                candidate = piket_ids[piket_idx % len(piket_ids)]
                piket_idx += 1
                if tgl not in blackout.get(candidate, set()):
                    result[tgl]["piket"] = piket_names[candidate]
                    result[tgl]["piket_wid"] = candidate
                    assigned = True
                    break
            if not assigned:
                result[tgl]["piket_merah"] = True

        # Generate OC
        if oc_ids:
            assigned = False
            piket_today = result[tgl].get("piket_wid")
            for _ in range(len(oc_ids)):
                candidate = oc_ids[oc_idx % len(oc_ids)]
                oc_idx += 1
                if tgl not in blackout.get(candidate, set()) and candidate != piket_today:
                    result[tgl]["oc"] = oc_names[candidate]
                    result[tgl]["oc_wid"] = candidate
                    assigned = True
                    break
            if not assigned:
                result[tgl]["oc_merah"] = True

    return result


def _update_rolling_state(tahun: int, bulan: int, hasil: dict):
    """Update rolling state setelah generate."""
    last_oc = last_piket = None
    for tgl in sorted(hasil.keys(), reverse=True):
        if hasil[tgl]["oc_wid"] and not last_oc:
            last_oc = hasil[tgl]["oc_wid"]
        if hasil[tgl]["piket_wid"] and not last_piket:
            last_piket = hasil[tgl]["piket_wid"]
        if last_oc and last_piket:
            break
    with get_conn() as conn:
        if last_oc:
            conn.execute(
                "UPDATE rolling_state SET last_whitelist_id = ?, updated_at = ? WHERE tipe = 'oc'",
                (last_oc, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        if last_piket:
            conn.execute(
                "UPDATE rolling_state SET last_whitelist_id = ?, updated_at = ? WHERE tipe = 'piket'",
                (last_piket, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        conn.commit()


@jadwal_bp.route("/preview", methods=["POST"])
@login_required
def preview():
    if session.get("role") not in ("superadmin", "manager", "kepala_support"):
        return redirect(url_for("jadwal.index"))

    tahun = int(request.form.get("tahun", date.today().year))
    bulan = int(request.form.get("bulan", date.today().month))
    bulan_nama = ["Januari","Februari","Maret","April","Mei","Juni",
                  "Juli","Agustus","September","Oktober","November","Desember"][bulan-1]

    hasil = _generate_jadwal(tahun, bulan)

    with get_conn() as conn:
        whitelist = conn.execute(
            "SELECT user_id, nama, no_hp FROM whitelist ORDER BY nama"
        ).fetchall()

    ringkasan = {}
    for w in whitelist:
        ringkasan[w["nama"]] = {
            "no_hp": w["no_hp"] or "-",
            "oc": [], "oc_merah": [],
            "piket": [], "piket_merah": []
        }

    for tgl, data in sorted(hasil.items()):
        day = int(tgl.split("-")[2])
        if data["oc"] and data["oc"] in ringkasan:
            if data["oc_merah"]:
                ringkasan[data["oc"]]["oc_merah"].append(str(day))
            else:
                ringkasan[data["oc"]]["oc"].append(str(day))
        if data["piket"] and data["piket"] in ringkasan:
            if data["piket_merah"]:
                ringkasan[data["piket"]]["piket_merah"].append(str(day))
            else:
                ringkasan[data["piket"]]["piket"].append(str(day))

    user = get_current_user()
    return render_template("jadwal_preview.html",
        user=user,
        tahun=tahun,
        bulan=bulan,
        bulan_nama=bulan_nama,
        ringkasan=ringkasan,
        hasil=hasil,
    )


@jadwal_bp.route("/simpan", methods=["POST"])
@login_required
def simpan_generate():
    if session.get("role") not in ("superadmin", "manager", "kepala_support"):
        return redirect(url_for("jadwal.index"))

    tahun = int(request.form.get("tahun", date.today().year))
    bulan = int(request.form.get("bulan", date.today().month))

    hasil = _generate_jadwal(tahun, bulan)

    with get_conn() as conn:
        conn.execute(
            "DELETE FROM jadwal WHERE tanggal LIKE ?",
            (f"{tahun}-{bulan:02d}%",)
        )
        for tgl, data in hasil.items():
            if data["oc"] and not data["oc_merah"]:
                conn.execute(
                    "INSERT OR IGNORE INTO jadwal (nama, tanggal, tipe) VALUES (?, ?, 'oc')",
                    (data["oc"], tgl)
                )
            if data["piket"] and not data["piket_merah"]:
                conn.execute(
                    "INSERT OR IGNORE INTO jadwal (nama, tanggal, tipe) VALUES (?, ?, 'piket')",
                    (data["piket"], tgl)
                )
        conn.commit()

    _update_rolling_state(tahun, bulan, hasil)
    return redirect(url_for("jadwal.index", tahun=tahun, bulan=bulan))


@jadwal_bp.route("/download/excel")
@login_required
def download_excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    tahun = int(request.args.get("tahun", date.today().year))
    bulan = int(request.args.get("bulan", date.today().month))
    bulan_nama = ["Januari","Februari","Maret","April","Mei","Juni",
                  "Juli","Agustus","September","Oktober","November","Desember"][bulan-1]

    hasil = _generate_jadwal(tahun, bulan)

    with get_conn() as conn:
        whitelist = conn.execute(
            "SELECT user_id, nama, no_hp FROM whitelist ORDER BY nama"
        ).fetchall()

    ringkasan = {}
    for w in whitelist:
        ringkasan[w["nama"]] = {"no_hp": w["no_hp"] or "-", "oc": [], "piket": []}

    for tgl, data in sorted(hasil.items()):
        day = int(tgl.split("-")[2])
        if data["oc"] and data["oc"] in ringkasan:
            ringkasan[data["oc"]]["oc"].append(str(day))
        if data["piket"] and data["piket"] in ringkasan:
            ringkasan[data["piket"]]["piket"].append(str(day))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Jadwal {bulan_nama} {tahun}"

    blue_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    ws.merge_cells("A1:D1")
    ws["A1"] = f"JADWAL ON CALL MALAM & PIKET — {bulan_nama.upper()} {tahun}"
    ws["A1"].font = Font(bold=True, size=13, color="1F4E79")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 30

    headers = ["NAMA", "NO HANDPHONE", "TANGGAL ON CALL MALAM",
               "TANGGAL PIKET WEEKEND\nDAN HARI LIBUR MASUK KANTOR"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.fill = blue_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = thin
    ws.row_dimensions[2].height = 40

    for row_idx, (nama, data) in enumerate(ringkasan.items(), 3):
        ws.cell(row=row_idx, column=1, value=nama).border = thin
        ws.cell(row=row_idx, column=2, value=data["no_hp"]).border = thin
        oc_cell = ws.cell(row=row_idx, column=3, value=", ".join(data["oc"]) if data["oc"] else "-")
        oc_cell.border = thin
        oc_cell.alignment = center
        piket_cell = ws.cell(row=row_idx, column=4, value=", ".join(data["piket"]) if data["piket"] else "-")
        piket_cell.border = thin
        piket_cell.alignment = center
        ws.row_dimensions[row_idx].height = 20

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 35

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"jadwal_{bulan_nama}_{tahun}.xlsx"
    )