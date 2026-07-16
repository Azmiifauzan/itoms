"""
handlers/jadwal_reminder.py
Reminder harian: siapa yang OFF, piket, dan on-call malam.
Dijadwalin lewat APScheduler (AsyncIOScheduler) di bot.py.
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


def _format_tanggal_id(d) -> str:
    return f"{HARI_ID[d.weekday()]}, {d.day} {BULAN_ID[d.month]} {d.year}"


def _ambil_jadwal_hari_ini(tipe: str) -> list[str]:
    today = datetime.now(WIB).date()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nama FROM jadwal WHERE tanggal = ? AND tipe = ? ORDER BY nama",
            (today, tipe)
        ).fetchall()
        return [r["nama"] for r in rows]


async def _kirim_ke_semua_grup(app, text: str):
    if not Config.GROUP_IDS:
        logger.warning("[Reminder] GROUP_IDS kosong, gak ada grup buat dikirimin.")
        return
    for group_id in Config.GROUP_IDS:
        try:
            await app.bot.send_message(chat_id=group_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"[Reminder] Gagal kirim ke grup {group_id}: {e}")


async def jadwal_job_off(app):
    nama_list = _ambil_jadwal_hari_ini("off")
    if not nama_list:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(f"• {n}" for n in nama_list)
    text = (
        f"🌴 <b>Jadwal OFF Hari Ini</b>\n"
        f"{_format_tanggal_id(today)}\n\n{isi}"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] OFF terkirim: {nama_list}")


async def jadwal_job_piket(app):
    nama_list = _ambil_jadwal_hari_ini("piket")
    if not nama_list:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(f"• {n}" for n in nama_list)
    text = (
        f"🛡️ <b>Jadwal Piket Hari Ini</b>\n"
        f"{_format_tanggal_id(today)}\n\n{isi}\n\n"
        f"Jangan lupa masuk kantor ya!"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] Piket terkirim: {nama_list}")


async def jadwal_job_oncall(app):
    nama_list = _ambil_jadwal_hari_ini("oc")
    if not nama_list:
        return
    today = datetime.now(WIB).date()
    isi = "\n".join(f"• {n}" for n in nama_list)
    text = (
        f"📞 <b>On Call Malam Ini</b>\n"
        f"{_format_tanggal_id(today)}\n\n{isi}"
    )
    await _kirim_ke_semua_grup(app, text)
    logger.info(f"[Reminder] On call terkirim: {nama_list}")