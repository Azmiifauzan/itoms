"""
dashboard/notif.py
Kirim notifikasi Telegram dari dashboard.
"""

import asyncio
import logging
from telegram import Bot
from config import Config
from db.local import get_conn

logger = logging.getLogger(__name__)


def kirim_notif_task_baru(task_id: int, judul: str, assignee_ids: list):
    """Kirim notif ke assignee kalau ada task baru."""
    if not assignee_ids:
        return
    with get_conn() as conn:
        for uid in assignee_ids:
            row = conn.execute(
                "SELECT telegram_user_id, nama FROM users_dashboard WHERE id = ?",
                (int(uid),)
            ).fetchone()
            if row and row["telegram_user_id"]:
                try:
                    asyncio.run(_send(
                        row["telegram_user_id"],
                        f"📋 <b>Task baru untukmu!</b>\n\n"
                        f"• <b>{judul}</b>\n"
                        f"Detail: /task_{task_id}"
                    ))
                except Exception as e:
                    logger.error(f"Gagal kirim notif ke {row['nama']}: {e}")

def kirim_live_chat_reply(telegram_user_id: int, text: str):
    """Kirim balasan dari dashboard ke user telegram (buat fitur live chat)."""
    asyncio.run(_send(telegram_user_id, text))

async def _send(chat_id: int, text: str):
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")