# Bot Telegram POS + Adempiere

Bot untuk membuat user POS dari data HRIS dan me-restart service Adempiere via Windows.

## Struktur Project

```
telegram_bot/
├── bot.py                  # Entry point
├── config.py               # Load konfigurasi dari .env
├── requirements.txt
├── .env                    # Konfigurasi (buat dari .env.example)
├── .env.example
├── db/
│   ├── connections.py      # 3 koneksi database
│   ├── hris.py             # Query HRIS
│   └── pos.py              # Insert user POS (⚠ sesuaikan schema dulu)
└── handlers/
    └── commands.py         # Semua command bot
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Buat file .env
```bash
copy .env.example .env
# Isi semua value di .env
```

### 3. Cari Telegram User ID kamu
Jalankan bot dulu, lalu kirim `/myid` ke bot.
Salin User ID-nya, isi ke `ALLOWED_USER_IDS` di `.env`.

### 4. Sesuaikan schema POS
Sebelum `/daftar` bisa jalan, perlu tahu struktur tabel user di DB webserv:
1. Jalankan bot
2. Kirim `/cek_schema` ke bot
3. Lihat output-nya, catat nama tabel dan kolom
4. Edit `db/pos.py` bagian ini:

```python
POS_USER_TABLE  = "public.ad_user"   # ganti nama tabel
COL_USERNAME    = "username"          # kolom username
COL_NAME        = "name"              # kolom nama
COL_PASSWORD    = "password"          # kolom password
DEFAULT_PASSWORD = "Password123!"     # password default
```

5. Sesuaikan juga fungsi `hash_password()` kalau POS pakai MD5 atau bcrypt.

### 5. Jalankan bot
```bash
python bot.py
```

## Command

| Command | Akses | Fungsi |
|---|---|---|
| `/start` | Semua | Lihat daftar command |
| `/myid` | Semua | Cek Telegram User ID sendiri |
| `/daftar <noabsen>` | Whitelist | Buat user POS dari HRIS |
| `/restart` | Whitelist | Restart service Adempiere |
| `/status` | Whitelist | Cek koneksi semua database |
| `/cek_schema` | Whitelist | Lihat struktur tabel POS (sementara) |

## Restart Adempiere di Windows

Bot menggunakan perintah `sc stop` dan `sc start` untuk restart service Windows.
Pastikan:
- Nama service Adempiere sudah benar (cek di `services.msc`)
- Isi `ADEMPIERE_SERVICE_NAME` di `.env`
- Bot dijalankan dengan akun yang punya hak akses ke service tersebut

Kalau perlu akses admin, jalankan terminal sebagai Administrator.

## Jalankan sebagai Background Service (Windows)

Gunakan NSSM (Non-Sucking Service Manager):
```bash
nssm install TelegramBot "C:\Python\python.exe" "C:\path\to\telegram_bot\bot.py"
nssm set TelegramBot AppDirectory "C:\path\to\telegram_bot"
nssm start TelegramBot
```
