"""
db/connections.py
Mengelola 3 koneksi database: HRIS, Webserv (POS), Adempiere
"""

import psycopg2
import psycopg2.extras
from config import Config
import logging

logger = logging.getLogger(__name__)


def get_hris_connection():
    """Koneksi ke database HRIS."""
    return psycopg2.connect(
        host=Config.HRIS_HOST,
        port=Config.HRIS_PORT,
        database=Config.HRIS_DATABASE,
        user=Config.HRIS_USER,
        password=Config.HRIS_PASSWORD,
        connect_timeout=10,
    )


def get_webserv_connection():
    """Koneksi ke database Webserv / POS."""
    return psycopg2.connect(
        host=Config.WEBSERV_HOST,
        port=Config.WEBSERV_PORT,
        database=Config.WEBSERV_DATABASE,
        user=Config.WEBSERV_USER,
        password=Config.WEBSERV_PASSWORD,
        connect_timeout=10,
    )


def get_adempiere_connection():
    """Koneksi ke database Adempiere."""
    return psycopg2.connect(
        host=Config.ADEMPIERE_HOST,
        port=Config.ADEMPIERE_PORT,
        database=Config.ADEMPIERE_DATABASE,
        user=Config.ADEMPIERE_USER,
        password=Config.ADEMPIERE_PASSWORD,
        connect_timeout=10,
    )


def test_all_connections() -> dict:
    """Test semua koneksi, return dict status masing-masing."""
    results = {}
    for name, fn in [
        ("HRIS", get_hris_connection),
        ("Webserv/POS", get_webserv_connection),
        ("Adempiere", get_adempiere_connection),
    ]:
        try:
            conn = fn()
            conn.close()
            results[name] = "OK"
        except Exception as e:
            results[name] = f"GAGAL - {e}"
    return results
