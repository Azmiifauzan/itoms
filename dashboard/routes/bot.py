"""
dashboard/routes/bot.py
Halaman "BOT" - Konfigurasi Bot Telegram (grup, keyword, live chat).
Semua route di sini butuh permission "config_bot" (atau superadmin).
"""

from flask import Blueprint, render_template
from dashboard.auth import login_required, permission_required

bot_bp = Blueprint("bot", __name__, url_prefix="/bot")

@bot_bp.route("/")
@login_required
def index():
    bisa_config = has_permission("config_bot")
    return render_template("bot/live_chat.html", bisa_config=bisa_config)

@bot_bp.route("/config")
@login_required
@permission_required("config_bot")
def config():
    return render_template("bot/config.html")