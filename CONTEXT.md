Project: ITOMS (IT Operations Management System)
Repo: github.com/Azmiifauzan/itoms
Stack: Python, Flask, SQLite, PostgreSQL, Docker, Gunicorn

Fitur selesai:
- Telegram bot (daftar POS, restart Adempiere SSH, share broadcast, whitelist management)
- Web dashboard (manager, kepala support, support, programmer)
- Task management + log progress
- Rekap komplain + ranking responder
- Docker Compose (bot + dashboard)
- GitHub repo (private)

Running di:
- Docker Desktop Windows
- WSL Ubuntu 22.04
- Port 8001 (dashboard)
- Port forwarding via Task Scheduler

Next:
- CI/CD (GitHub Actions)
- Fitur tiket (phase 2)
- Deploy ke VPS (kalau mau cloud)
- Switch repo ke public (setelah bersihkan credentials)

Notes:
- Bot token ada di .env (jangan di-commit)
- portforward.ps1 jalan via Task Scheduler saat startup
- restart: always di docker-compose.yml