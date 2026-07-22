"""
dashboard/routes/bot.py
Halaman "BOT" - Konfigurasi Bot Telegram (grup, keyword, live chat).
Semua route di sini butuh permission "config_bot" (atau superadmin).
"""

from flask import Blueprint, render_template
from dashboard.auth import login_required, permission_required, has_permission, get_current_user
from db.local import (
    get_live_chat_conversations, get_live_chat_messages, simpan_live_chat,
)
from dashboard.notif import kirim_live_chat_reply

bot_bp = Blueprint("bot", __name__, url_prefix="/bot")

@bot_bp.route("/")
@login_required
def index():
    bisa_config = has_permission("config_bot")
    conversations = get_live_chat_conversations()
    return render_template("bot/live_chat.html", bisa_config=bisa_config, conversations=conversations)

@bot_bp.route("/config")
@login_required
@permission_required("config_bot")
def config():
    return render_template("bot/config.html")

@bot_bp.route("/chat/<int:telegram_user_id>")
@login_required
def chat_detail(telegram_user_id):
    messages = get_live_chat_messages(telegram_user_id)
    return render_template(
        "bot/chat_detail.html",
        messages=messages,
        telegram_user_id=telegram_user_id,
    )

@bot_bp.route("/chat/<int:telegram_user_id>/reply", methods=["POST"])
@login_required
def chat_reply(telegram_user_id):
    text = request.form .get("pesan", "").strip()
    if text:
        user = get_current_user()
        kirim_live_chat_reply(telegram_user_id, text)
        simpan_live_chat(
            telegram_user_id=telegram_user_id,
            nama_pengirim=user["nama"] if user else "Admin",
            arah="keluar"
            isi_pesan=text,
            dibalas_oleh=user["nama"] if user else None,
        )
    return rediect(url_for("bot.chat_detail", telegram_user_id=telegram_user_id))