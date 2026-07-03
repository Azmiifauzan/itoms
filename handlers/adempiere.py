import paramiko
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import Config
from handlers.commands import restricted

logger = logging.getLogger(__name__)

ADEMPIERE_CMD = "/etc/init.d/adempiere"


def ssh_exec(server_key: str, command: str) -> tuple[str, str]:
    """
    Konek SSH ke server dan jalankan command.
    Return (stdout, stderr).
    """
    server = Config.SSH_SERVERS[server_key]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=server["hostname"],
            username=server["username"],
            password=server["password"],
            timeout=15,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=30)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        return out, err
    finally:
        client.close()


def build_server_keyboard(action: str) -> InlineKeyboardMarkup:
    buttons = []
    for key, server in Config.SSH_SERVERS.items():
        buttons.append([
            InlineKeyboardButton(
                server["label"],
                callback_data=f"adempiere:{action}:{key}"
            )
        ])
    buttons.append([InlineKeyboardButton("❌ Batal", callback_data="adempiere:cancel")])
    return InlineKeyboardMarkup(buttons)


# ──────────────────────────────────────────
# /restart_adempiere
# ──────────────────────────────────────────
@restricted
async def cmd_restart_adempiere(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔄 <b>Restart Adempiere</b>\nPilih server:",
        parse_mode="HTML",
        reply_markup=build_server_keyboard("restart"),
    )


# ──────────────────────────────────────────
# /stop_adempiere
# ──────────────────────────────────────────
@restricted
async def cmd_stop_adempiere(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛑 <b>Stop Adempiere</b>\nPilih server:",
        parse_mode="HTML",
        reply_markup=build_server_keyboard("stop"),
    )


# ──────────────────────────────────────────
# /start_adempiere
# ──────────────────────────────────────────
@restricted
async def cmd_start_adempiere(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "▶️ <b>Start Adempiere</b>\nPilih server:",
        parse_mode="HTML",
        reply_markup=build_server_keyboard("start"),
    )


# ──────────────────────────────────────────
# Callback handler — proses setelah pilih server
# ──────────────────────────────────────────
async def adempiere_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # format: "adempiere:action:key"
    parts = data.split(":")

    if parts[1] == "cancel":
        await query.edit_message_text("❌ Dibatalkan.")
        return

    action = parts[1]  # restart / stop / start
    key = parts[2]
    server = Config.SSH_SERVERS[key]

    action_map = {
        "restart": ("🔄 Restarting", f"{ADEMPIERE_CMD} restart"),
        "stop":    ("🛑 Stopping",   f"{ADEMPIERE_CMD} stop"),
        "start":   ("▶️ Starting",   f"{ADEMPIERE_CMD} start"),
    }
    label, command = action_map[action]

    await query.edit_message_text(
        f"{label} <b>{server['label']}</b>...\n⏳ Sabar lagi di restartin.",
        parse_mode="HTML",
    )

    try:
        out, err = ssh_exec(key, command)
        result = out or err or "Tidak ada output."
        await query.edit_message_text(
            f"✅ <b>{action.capitalize()}</b> {server['label']} selesai.\n\n"
            f"<code>{result}</code>",
            parse_mode="HTML",
        )
        logger.info(f"[SSH] {action} {server['label']} oleh {query.from_user.full_name}: {result}")
    except Exception as e:
        await query.edit_message_text(
            f"❌ Gagal {action} <b>{server['label']}</b>:\n<code>{str(e)}</code>",
            parse_mode="HTML",
        )
        logger.error(f"[SSH] Error {action} {key}: {e}")