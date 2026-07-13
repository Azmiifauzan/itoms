import logging
from config import Config
from db.local import init_db
from handlers.commands import (
    cmd_start,
    cmd_myid,
    cmd_daftar,
    cmd_status,
    cmd_adduser,
    cmd_removeuser,
    cmd_listuser,
    cmd_cekid,
    cmd_share,
    grup_listener,
)
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from handlers.adempiere import (
    cmd_restart_adempiere,
    cmd_stop_adempiere,
    cmd_start_adempiere,
    adempiere_callback,
)


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    if not Config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN belum diisi di file .env!")

    # Inisialisasi SQLite (buat tabel kalau belum ada)
    init_db()

    app = ApplicationBuilder()\
        .token(Config.TELEGRAM_BOT_TOKEN)\
        .connect_timeout(30)\
        .read_timeout(30)\
        .write_timeout(30)\
        .pool_timeout(30)\
        .http_version("1.1")\
        .build()
        

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("myid",        cmd_myid))
    app.add_handler(CommandHandler("daftar",      cmd_daftar))
    app.add_handler(CommandHandler("status",      cmd_status))
    app.add_handler(CommandHandler("adduser",     cmd_adduser))
    app.add_handler(CommandHandler("removeuser",  cmd_removeuser))
    app.add_handler(CommandHandler("listuser",    cmd_listuser))
    app.add_handler(CommandHandler("cekid",       cmd_cekid))
    app.add_handler(CommandHandler("share",       cmd_share))
    app.add_handler(CommandHandler("restart_adempiere", cmd_restart_adempiere))
    app.add_handler(CommandHandler("stop_adempiere",    cmd_stop_adempiere))
    app.add_handler(CommandHandler("start_adempiere",   cmd_start_adempiere))
    app.add_handler(CallbackQueryHandler(adempiere_callback, pattern="^adempiere:"))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, grup_listener))


    logger.info("Bot mulai berjalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
