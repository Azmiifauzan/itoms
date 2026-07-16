import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import timezone, timedelta
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
from handlers.jadwal_reminder import jadwal_job_off, jadwal_job_piket, jadwal_job_oncall
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

WIB = timezone(timedelta(hours=7))


async def _setup_scheduler(app):
    """Dipanggil otomatis sama python-telegram-bot pas startup (post_init),
    di titik ini event loop asyncio-nya udah jalan jadi aman buat AsyncIOScheduler."""
    scheduler = AsyncIOScheduler(timezone=WIB)
    scheduler.add_job(jadwal_job_off, "cron", hour=8, minute=0, args=[app])
    scheduler.add_job(jadwal_job_piket, "cron", hour=8, minute=30, args=[app])
    scheduler.add_job(jadwal_job_oncall, "cron", hour=17, minute=0, args=[app])
    scheduler.start()
    logger.info("Scheduler jadwal reminder aktif (off 08:00, piket 08:30, oncall 17:00 WIB).")


def main():
    if not Config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN belum diisi di file .env!")

    # Pastikan semua tabel Postgres ada (idempotent)
    init_db()

    app = ApplicationBuilder()\
        .token(Config.TELEGRAM_BOT_TOKEN)\
        .connect_timeout(30)\
        .read_timeout(30)\
        .write_timeout(30)\
        .pool_timeout(30)\
        .http_version("1.1")\
        .post_init(_setup_scheduler)\
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