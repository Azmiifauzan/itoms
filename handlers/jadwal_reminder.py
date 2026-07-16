"""
handlers/jadwal_reminder.py
Reminder harian: siapa yang OFF, piket, dan on-call malam.
Dijadwalin lewat APScheduler (AsyncIOScheduler) di bot.py.

Update: sekarang tiap nama otomatis di-tag (mention) pakai Telegram ID-nya
(diambil dari tabel whitelist, di-JOIN lewat kecocokan nama), jadi orangnya
kena notifikasi beneran, bukan cuma nama doang yang ditulis di teks.
"""

import logging
from datetime import datetime, timezone, timedelta
from config import Config
from db.local import get_conn

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
            "Agustus", "September", "Oktober", "November", "Desember"]

# Karakter tak kasat mata, dipakai buat nge-tag telegram_id_2 (device/akun kedua)
# tanpa nambahin teks yang keliatan di pesan.
ZERO_WIDTH = "\u200b"

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬"


def _format_tanggal_id(d) -> str:
    return f"{HARI_ID[d.weekday()]}, {d.day} {BULAN_ID[d.month]} {d.year}"


def _esc(text: str) -> str:
    """Escape karakter HTML biar nama yang kebetulan ada <, >, & gak bikin
    Telegram nolak kirim pesan (parse_mode='HTML')."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ambil_jadwal_hari_ini(tipe: str) -> list[dict]:
    """Ambil nama + Telegram ID (kalau namanya kecocok sama whitelist) buat
    semua orang yang jadwalnya tipe tsb hari ini.

    Catatan: matching ke whitelist lewat kolom `nama` (case-insensitive), sesuai
    struktur whitelist yang ada sekarang. Kalau nama di jadwal (hasil upload
    Excel) ternyata beda format sama nama di whitelist, orang itu tetap
    ditampilin di pesan tapi gak ke-tag (fallback ke teks tebal biasa).
    """
    today = datetime.now(WIB).date()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT j.nama, w.user_id, w.telegram_id_2
            FROM jadwal j
            LEFT JOIN whitelist w ON LOWER(w.nama) = LOWER(j.nama)
            WHERE j.tanggal = ? AND j.tipe = ?
            ORDER BY j.nama
        """, (today, tipe)).fetchall()
        return [dict(r) for r in rows]


def _format_mention(row: dict) -> str:
    """Bikin satu baris '• Nama' yang otomatis nge-tag orangnya kalau
    Telegram ID-nya ketemu. Kalau dia punya telegram_id_2 juga, ditag diam-diam
    (invisible) biar kedua akun/device kena notifikasi."""
    nama = _esc(row["nama"])
    user_id = row.get("user_id")
    tg2 = row.get("telegram_id_2")

    if user_id:
        line = f'• <a href="tg://user?id={user_id}">{nama}</a>'
        if tg2:
            line += f'<a href="tg://user?id={tg2}">{ZERO_WIDTH}</a>'
    else:
        # Gak ketemu di whitelist -> tetep ditampilin, tapi gak bisa di-tag
        line = f"• <b>{nama}</b>"
    return line


async def _kirim_ke_semua_grup(app, text: str):
    if not Config.GROUP_IDS:
        logger.warning("[Reminder] GROUP_IDS kosong, gak ada grup buat dikirimin.")
        return
    for group_id in Config.GROUP_IDS:
        try:
            await app.bot.send_message(
                chat_id=group_id, text=text,
                parse_mode="HTML", disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"[Reminder] Gagal kirim ke grup {group_id}: {e}")


async def jadwal_job_off(app):
    rows = _ambil_jadwal_hari_ini("off")
    if not rows:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(_format_mention(r) for r in rows)
    text = (
        f"<b>Jadwal OFF Hari Ini</b>\n"
        f"🗓 {_format_tanggal_id(today)}\n"
        f"{DIVIDER}\n"
        f"{isi}\n\n"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] OFF terkirim: {[r['nama'] for r in rows]}")


async def jadwal_job_piket(app):
    rows = _ambil_jadwal_hari_ini("piket")
    if not rows:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(_format_mention(r) for r in rows)
    text = (
        f"<b>Jadwal Piket Hari Ini</b>\n"
        f"🗓 {_format_tanggal_id(today)}\n"
        f"{DIVIDER}\n"
        f"{isi}\n\n"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] Piket terkirim: {[r['nama'] for r in rows]}")


async def jadwal_job_oncall(app):
    rows = _ambil_jadwal_hari_ini("oc")
    if not rows:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(_format_mention(r) for r in rows)
    text = (
        f"<b>On Call Malam Ini</b>\n"
        f"🗓 {_format_tanggal_id(today)}\n"
        f"{DIVIDER}\n"
        f"{isi}\n\n"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] On call terkirim: {[r['nama'] for r in rows]}")