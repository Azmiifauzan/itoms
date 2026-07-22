"""
dashboard/routes/bot.py
Menu BOT — Live Chat, daftar Grup, dan Konfigurasi (keyword komplain & auto-reply).

Live Chat & lihat Grup kebuka semua orang yang login.
Ubah tipe grup & kelola keyword butuh permission "config_bot".
"""

import requests
from flask import Blueprint, render_template, request, redirect, url_for
from dashboard.auth import login_required, get_current_user, has_permission
from config import Config
from db.local import (
    get_live_chat_threads, get_live_chat_messages, simpan_live_chat,
    get_bot_groups, update_bot_group_tipe,
    get_komplain_keywords_full, add_komplain_keyword, delete_komplain_keyword,
    get_auto_reply_keywords, add_auto_reply_keyword, delete_auto_reply_keyword,
)

bot_bp = Blueprint("bot", __name__, url_prefix="/bot")


def _kirim_telegram(chat_id: int, text: str) -> bool:
    """Kirim pesan langsung lewat Telegram Bot API (HTTP) — gak lewat proses bot.py sama sekali."""
    try:
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


@bot_bp.route("/")
@login_required
def index():
    user = get_current_user()
    tab = request.args.get("tab", "chat")
    bisa_config = has_permission("config_bot")

    context = {"user": user, "tab": tab, "bisa_config": bisa_config}

    if tab == "grup":
        context["groups"] = get_bot_groups()
    elif tab == "config":
        if not bisa_config:
            tab = "chat"
            context["tab"] = "chat"
            context["threads"] = get_live_chat_threads()
        else:
            context["komplain_keywords"] = get_komplain_keywords_full()
            context["auto_reply_keywords"] = get_auto_reply_keywords()
    else:
        tab = "chat"
        context["tab"] = "chat"
        context["threads"] = get_live_chat_threads()

    return render_template("bot.html", **context)


@bot_bp.route("/chat/<int:telegram_user_id>")
@login_required
def chat_detail(telegram_user_id):
    user = get_current_user()
    messages = get_live_chat_messages(telegram_user_id)
    nama = next((m["nama_pengirim"] for m in reversed(messages) if m["nama_pengirim"]), str(telegram_user_id))
    return render_template("bot_chat_detail.html",
        user=user, messages=messages, telegram_user_id=telegram_user_id, nama=nama,
    )


@bot_bp.route("/chat/<int:telegram_user_id>/kirim", methods=["POST"])
@login_required
def chat_kirim(telegram_user_id):
    user = get_current_user()
    isi = request.form.get("isi", "").strip()
    if isi:
        ok = _kirim_telegram(telegram_user_id, isi)
        if ok:
            simpan_live_chat(
                telegram_user_id=telegram_user_id,
                nama_pengirim=None,
                arah="keluar",
                isi_pesan=isi,
                dibalas_oleh=user["nama"],
            )
    return redirect(url_for("bot.chat_detail", telegram_user_id=telegram_user_id))


@bot_bp.route("/grup/<int:chat_id>/tipe", methods=["POST"])
@login_required
def grup_tipe(chat_id):
    if not has_permission("config_bot"):
        return redirect(url_for("bot.index", tab="grup"))
    tipe = request.form.get("tipe", "internal")
    if tipe in ("internal", "kasir"):
        update_bot_group_tipe(chat_id, tipe)
    return redirect(url_for("bot.index", tab="grup"))


@bot_bp.route("/keyword/komplain/tambah", methods=["POST"])
@login_required
def keyword_komplain_tambah():
    if not has_permission("config_bot"):
        return redirect(url_for("bot.index", tab="config"))
    kw = request.form.get("keyword", "").strip().upper()
    if kw:
        add_komplain_keyword(kw)
    return redirect(url_for("bot.index", tab="config"))


@bot_bp.route("/keyword/komplain/hapus/<int:kid>", methods=["POST"])
@login_required
def keyword_komplain_hapus(kid):
    if not has_permission("config_bot"):
        return redirect(url_for("bot.index", tab="config"))
    delete_komplain_keyword(kid)
    return redirect(url_for("bot.index", tab="config"))


@bot_bp.route("/keyword/auto-reply/tambah", methods=["POST"])
@login_required
def keyword_auto_reply_tambah():
    if not has_permission("config_bot"):
        return redirect(url_for("bot.index", tab="config"))
    kw = request.form.get("keyword", "").strip()
    balasan = request.form.get("balasan", "").strip()
    if kw and balasan:
        add_auto_reply_keyword(kw, balasan)
    return redirect(url_for("bot.index", tab="config"))


@bot_bp.route("/keyword/auto-reply/hapus/<int:kid>", methods=["POST"])
@login_required
def keyword_auto_reply_hapus(kid):
    if not has_permission("config_bot"):
        return redirect(url_for("bot.index", tab="config"))
    delete_auto_reply_keyword(kid)
    return redirect(url_for("bot.index", tab="config"))