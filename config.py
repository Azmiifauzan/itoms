"""
config.py
Load semua konfigurasi dari file .env
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Admin: boleh pakai /adduser /removeuser /listuser
    # Isi dengan Telegram user ID kamu (yang paling dipercaya)
    ADMIN_USER_IDS: list[int] = [
        int(uid.strip())
        for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
        if uid.strip().isdigit()
    ]
    # Grup tujuan /share
    GROUP_IDS: list[int] = [
        int(gid.strip())
        for gid in os.getenv("GROUP_IDS", "").split(",")
            if gid.strip().lstrip("-").isdigit()
]

    # HRIS
    HRIS_HOST: str     = os.getenv("HRIS_HOST", "localhost")
    HRIS_PORT: int     = int(os.getenv("HRIS_PORT", 5432))
    HRIS_DATABASE: str = os.getenv("HRIS_DATABASE", "")
    HRIS_USER: str     = os.getenv("HRIS_USER", "")
    HRIS_PASSWORD: str = os.getenv("HRIS_PASSWORD", "")

    # Webserv / POS
    WEBSERV_HOST: str     = os.getenv("WEBSERV_HOST", "localhost")
    WEBSERV_PORT: int     = int(os.getenv("WEBSERV_PORT", 5432))
    WEBSERV_DATABASE: str = os.getenv("WEBSERV_DATABASE", "webserv_sci")
    WEBSERV_USER: str     = os.getenv("WEBSERV_USER", "")
    WEBSERV_PASSWORD: str = os.getenv("WEBSERV_PASSWORD", "")

    # SSH Adempiere Servers
    SSH_SERVERS: dict = {
        "127": {
            "label": "Adempiere 127",
            "hostname": os.getenv("SSH_ADEMPIERE_127_HOST", ""),
            "username": os.getenv("SSH_ADEMPIERE_127_USER", "root"),
            "password": os.getenv("SSH_ADEMPIERE_127_PASS", ""),
        },
        "148": {
            "label": "Adempiere 148",
            "hostname": os.getenv("SSH_ADEMPIERE_148_HOST", ""),
            "username": os.getenv("SSH_ADEMPIERE_148_USER", "root"),
            "password": os.getenv("SSH_ADEMPIERE_148_PASS", ""),
        },
        "158": {
            "label": "Adempiere 158 (5555 Luar)",
            "hostname": os.getenv("SSH_ADEMPIERE_158_HOST", ""),
            "username": os.getenv("SSH_ADEMPIERE_158_USER", "root"),
            "password": os.getenv("SSH_ADEMPIERE_158_PASS", ""),
        },
        "118": {
            "label": "Adempiere Curry",
            "hostname": os.getenv("SSH_ADEMPIERE_118_HOST", ""),
            "username": os.getenv("SSH_ADEMPIERE_118_USER", "root"),
            "password": os.getenv("SSH_ADEMPIERE_118_PASS",""),
        },
    }