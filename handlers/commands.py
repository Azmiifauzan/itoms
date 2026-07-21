"""
handlers/commands.py
Semua command handler untuk bot Telegram.
"""

import subprocess
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import Config
from db.hris import get_employee_by_noabsen
from db.pos import create_pos_user, is_user_exists
from db.connections import test_all_connections
from db.local import (is_allowed, add_user, remove_user, list_users,
                      simpan_komplain, get_komplain_by_message, simpan_response,
                      track_group, get_komplain_keywords, get_auto_reply_keywords,
                      simpan_live_chat)


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# Decorator: cek whitelist dari SQLite
# ──────────────────────────────────────────
def restricted(func):
    """Tolak user yang tidak ada di whitelist SQLite."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_allowed(user_id):
            await update.message.reply_text(
                f"⛔ Akses ditolak.\n",        
                parse_mode="HTML",
            )
            logger.warning(f"Akses ditolak untuk user_id={user_id}")
            return
        return await func(update, ctx)
    return wrapper


def admin_only(func):
    """Hanya ADMIN_USER_IDS yang boleh akses (untuk add/remove user)."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in Config.ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Command ini hanya untuk admin.")
            return
        return await func(update, ctx)
    return wrapper


# ──────────────────────────────────────────
# /start
# ──────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id in Config.ADMIN_USER_IDS

    text = (
        "👋 <b>Bot POS</b>\n\n"
        "<b>Command tersedia:</b>\n"
        "• /daftar &lt;noabsen&gt; — Buat user POS dari data HRIS\n"
        "• /status — Cek koneksi semua database\n"
        "• /myid — Lihat Telegram User ID kamu\n"
    )
    if is_admin:
        text += (
            "\n<b>Command admin:</b>\n"
            "• /adduser &lt;user_id&gt; &lt;nama&gt; — Tambah user ke whitelist\n"
            "• /removeuser &lt;user_id&gt; — Hapus user dari whitelist\n"
            "• /listuser — Lihat semua user di whitelist\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")


# ──────────────────────────────────────────
# /myid
# ──────────────────────────────────────────
async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"ℹ️ Info akun kamu:\n"
        f"• <b>User ID:</b> <code>{user.id}</code>\n"
        f"• <b>Username:</b> @{user.username or '-'}\n"
        f"• <b>Nama:</b> {user.full_name}",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────
# /daftar <noabsen>
# ──────────────────────────────────────────
@restricted
async def cmd_daftar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Format: <code>/daftar &lt;noabsen&gt;</code>\nContoh: <code>/daftar 12345</code>",
            parse_mode="HTML",
        )
        return

    no_absen = ctx.args[0].strip()
    msg = await update.message.reply_text(
        f"🔍 Mencari karyawan <code>{no_absen}</code>...", parse_mode="HTML"
    )

    try:
        # 1. Cari di HRIS
        employee = get_employee_by_noabsen(no_absen)
        if not employee:
            await msg.edit_text(
                f"❌ No absen <code>{no_absen}</code> tidak ditemukan di HRIS.",
                parse_mode="HTML",
            )
            return

        full_name = employee["full_name"]
        await msg.edit_text(
            f"✅ Ditemukan: <b>{full_name}</b> (<code>{no_absen}</code>)\n"
            f"⏳ Mengecek DB POS...",
            parse_mode="HTML",
        )

        # 2. Cek apakah sudah ada di POS
        already, reason = is_user_exists(no_absen)
        if already:
            await msg.edit_text(
            f"⚠️ Tidak bisa daftarkan <b>{full_name}</b>:\n{reason}",
            parse_mode="HTML",
            )
            return

        # 3. Create user POS
        await msg.edit_text(
            f"✅ Ditemukan: <b>{full_name}</b>\n⏳ Membuat user POS...",
            parse_mode="HTML",
        )
        create_pos_user(no_absen, full_name)

        await msg.edit_text(
            f"✅ <b>User POS berhasil dibuat!</b>\n\n"
            f"• Nama     : <b>{full_name}</b>\n"
            f"• Username : <code>{no_absen}</code>\n"
            f"• Password : <code>{no_absen}</code>\n"                                  
            f"• Aktif    : Y ✅\n"
            f"Silahkan Sync user",
            parse_mode="HTML",
        )
        logger.info(f"User POS dibuat: {no_absen} - {full_name} oleh {update.effective_user.id}")

    except Exception as e:
        await msg.edit_text(
            f"❌ <b>Error:</b> {str(e)}\n\nCek log untuk detail.",
            parse_mode="HTML",
        )
        logger.error(f"cmd_daftar error: {e}")


# ──────────────────────────────────────────
# /status
# ──────────────────────────────────────────
@restricted
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Mengecek semua koneksi...", parse_mode="HTML")
    try:
        results = test_all_connections()
        lines = ["<b>Status Koneksi Database:</b>\n"]
        for name, status in results.items():
            icon = "✅" if status == "OK" else "❌"
            lines.append(f"{icon} <b>{name}</b>: {status}")
        await msg.edit_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}", parse_mode="HTML")


# ──────────────────────────────────────────
# /adduser <user_id> <nama>   (admin only)
# ──────────────────────────────────────────
@admin_only
async def cmd_adduser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "⚠️ Format: <code>/adduser &lt;user_id&gt; &lt;nama&gt;</code>\n"
            "Contoh: <code>/adduser 123456789 Budi</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(ctx.args[0])
        nama = " ".join(ctx.args[1:])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    ok = add_user(target_id, nama)
    if ok:
        await update.message.reply_text(
            f"✅ <b>{nama}</b> (<code>{target_id}</code>) berhasil ditambahkan ke whitelist.",
            parse_mode="HTML",
        )
        logger.info(f"Whitelist: {target_id} ({nama}) ditambah oleh {update.effective_user.id}")
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{target_id}</code> sudah ada di whitelist.",
            parse_mode="HTML",
        )


# ──────────────────────────────────────────
# /removeuser <user_id>   (admin only)
# ──────────────────────────────────────────
@admin_only
async def cmd_removeuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Format: <code>/removeuser &lt;user_id&gt;</code>\n"
            "Contoh: <code>/removeuser 123456789</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    ok = remove_user(target_id)
    if ok:
        await update.message.reply_text(
            f"✅ User <code>{target_id}</code> berhasil dihapus dari whitelist.",
            parse_mode="HTML",
        )
        logger.info(f"Whitelist: {target_id} dihapus oleh {update.effective_user.id}")
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{target_id}</code> tidak ditemukan di whitelist.",
            parse_mode="HTML",
        )


# ──────────────────────────────────────────
# /listuser   (admin only)
# ──────────────────────────────────────────
@admin_only
async def cmd_listuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = list_users()
    if not users:
        await update.message.reply_text("📋 Whitelist masih kosong.")
        return

    lines = [f"📋 <b>Whitelist ({len(users)} user):</b>\n"]
    for u in users:
        ditambah = u['added_at'].strftime('%Y-%m-%d %H:%M') if u['added_at'] else '-'
        lines.append(
            f"• <b>{u['nama']}</b> — <code>{u['user_id']}</code>\n"
            f"  <i>ditambah {ditambah}</i>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

# ──────────────────────────────────────────
# /cekid — reply pesan seseorang untuk cek user ID-nya
# ──────────────────────────────────────────
@admin_only
async def cmd_cekid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Cara pakai: <b>reply</b> pesan seseorang, lalu ketik <code>/cekid</code>",
            parse_mode="HTML",
        )
        return

    target = update.message.reply_to_message.from_user
    already = is_allowed(target.id)

    await update.message.reply_text(
        f"👤 <b>{target.full_name}</b>\n"
        f"• User ID  : <code>{target.id}</code>\n"
        f"• Username : @{target.username or '-'}\n"
        f"• Whitelist: {'✅ sudah ada' if already else '❌ belum didaftarkan'}\n\n"
        f"{'Untuk tambahkan: ' if not already else ''}"
        f"{'<code>/adduser ' + str(target.id) + ' ' + target.first_name + '</code>' if not already else ''}",
        parse_mode="HTML",
    )

# ──────────────────────────────────────────
# /share <pesan> — kirim ke semua grup
# ──────────────────────────────────────────
@restricted
async def cmd_share(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Format: <code>/share &lt;pesan&gt;</code>\n"
            "Contoh: <code>/share Ada maintenance malam ini jam 22.00</code>",
            parse_mode="HTML",
        )
        return

    pesan = " ".join(ctx.args)
    pengirim = update.effective_user.full_name
    msg = await update.message.reply_text("⏳ Mengirim ke semua grup...", parse_mode="HTML")

    sukses, gagal = 0, 0
    for group_id in Config.GROUP_IDS:
        try:
            await ctx.bot.send_message(
                chat_id=group_id,
                text=f"📢 {pesan}",
                parse_mode="HTML",
            )
            sukses += 1
        except Exception as e:
            gagal += 1
            logger.error(f"Gagal kirim ke grup {group_id}: {e}")

    await msg.edit_text(
        f"✅ Pesan terkirim ke <b>{sukses} grup</b>"
        + (f"\n❌ Gagal: <b>{gagal} grup</b> (cek bot.log)" if gagal else ""),
        parse_mode="HTML",
    )


# ──────────────────────────────────────────
# Listener: dengerin pesan di grup
# ──────────────────────────────────────────
async def grup_listener(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    chat_id = msg.chat_id
    grup_nama = msg.chat.title or str(chat_id)
    text = msg.text
    user = msg.from_user

    logger.info(f"[REKAP DEBUG] Pesan masuk dari {user.full_name if user else '?'} di {grup_nama}: {text[:50]}")

    # 0. Catat/update grup ini (biar keliatan di menu Bot > Grup)
    try:
        track_group(chat_id, grup_nama)
    except Exception as e:
        logger.error(f"[BOT] Gagal track_group: {e}")

    # 1. Deteksi komplain — keyword sekarang diambil dari database (bisa diatur di dashboard),
    #    bukan hardcode lagi. Kalau tabel keyword kosong, JANGAN anggap semua pesan komplain.
    keywords = get_komplain_keywords()
    is_komplain = bool(keywords) and all(k.upper() in text.upper() for k in keywords)

    if is_komplain:
        try:
            simpan_komplain(
                message_id=msg.message_id,
                chat_id=chat_id,
                grup_nama=grup_nama,
                isi_pesan=text,
                pengirim=user.full_name if user else "Unknown",
            )
            logger.info(f"[REKAP] Komplain baru di {grup_nama}")
        except Exception as e:
            logger.error(f"[REKAP] Gagal simpan komplain: {e}")

        # Auto-reply — kalau isi komplain ini mengandung salah satu keyword auto-reply
        # yang diatur di dashboard, bot langsung bales otomatis.
        try:
            for ar in get_auto_reply_keywords():
                if ar["keyword"].upper() in text.upper():
                    await msg.reply_text(ar["balasan"])
                    logger.info(f"[AUTO-REPLY] Trigger '{ar['keyword']}' di {grup_nama}")
                    break
        except Exception as e:
            logger.error(f"[AUTO-REPLY] Gagal kirim auto-reply: {e}")

        return

    # 2. Cek whitelist
    if not user:
        logger.info("[REKAP DEBUG] Skip: user None")
        return

    allowed = is_allowed(user.id)
    logger.info(f"[REKAP DEBUG] User {user.full_name} (id={user.id}) whitelist={allowed}")

    if not allowed:
        return

    # 3. WAJIB reply spesifik ke pesan komplain — gak ada lagi fallback "komplain terakhir"
    #    (itu penyebab balasan suka nyambung ke komplain yang salah kalau ada 2 komplain numpuk).
    if not msg.reply_to_message:
        logger.info("[REKAP DEBUG] Bukan reply ke pesan manapun, diabaikan")
        return

    komplain = get_komplain_by_message(
        message_id=msg.reply_to_message.message_id,
        chat_id=chat_id,
    )
    logger.info(f"[REKAP DEBUG] Reply ke message_id={msg.reply_to_message.message_id}, komplain={komplain}")

    if not komplain:
        logger.info("[REKAP DEBUG] Reply bukan ke pesan komplain, diabaikan")
        return

    try:
        simpan_response(
            komplain_id=komplain["id"],
            message_id=msg.message_id,
            chat_id=chat_id,
            responder_id=user.id,
            responder_nama=user.full_name,
            isi_balasan=text,
        )
        logger.info(f"[REKAP] Response dari {user.full_name} untuk komplain id={komplain['id']}")
    except Exception as e:
        logger.error(f"[REKAP] Gagal simpan response: {e}")


async def live_chat_listener(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """DM 1-on-1 dari orang yang BUKAN whitelist (misal kasir) -> masuk Live Chat.
    Kalau pengirimnya whitelist (staff internal), biarin command handler lain yang proses,
    jangan dianggap live chat."""
    msg = update.message
    if not msg or not msg.text:
        return
    user = msg.from_user
    if not user:
        return
    if is_allowed(user.id):
        return

    try:
        simpan_live_chat(
            telegram_user_id=user.id,
            nama_pengirim=user.full_name,
            arah="masuk",
            isi_pesan=msg.text,
        )
        logger.info(f"[LIVE CHAT] Pesan masuk dari {user.full_name} ({user.id})")
    except Exception as e:
        logger.error(f"[LIVE CHAT] Gagal simpan pesan: {e}")