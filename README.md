# ITOMS — IT Operations Management System

A comprehensive IT operations management system built for retail/franchise businesses. Combines a **Telegram Bot** for real-time support operations with a **Web Dashboard** for task management, complaint tracking, and team performance monitoring.

---

## Features

### Telegram Bot
- **User Registration** — Create POS system users directly from HRIS database with a single command
- **Multi-server Management** — Start, stop, and restart Adempiere ERP services via SSH across multiple servers
- **Broadcast Messaging** — Send announcements to all branch group chats simultaneously
- **Complaint Tracking** — Automatically detects and logs support complaints from group chats
- **Response Monitoring** — Tracks which IT staff respond to complaints and logs their activity
- **Whitelist Access Control** — Role-based access management via Telegram User ID
- **User Management** — Add/remove authorized users directly from Telegram

### Web Dashboard
- **Multi-role Access** — Manager, Head of Support, IT Support, and Programmer roles
- **Task Management** — Create, assign, track, and update tasks with progress percentage
- **Team Performance** — Leaderboard ranking of support staff based on complaint response activity
- **Complaint Analytics** — Daily complaint count and response tracking
- **User Management** — Full CRUD for dashboard users with role assignment
- **Telegram Integration** — Notification system linked to Telegram User IDs

---

## Tech Stack

| Component | Technology |
|---|---|
| Bot Framework | Python, python-telegram-bot |
| Web Framework | Python, Flask |
| Databases | PostgreSQL (HRIS, POS/Webserv), SQLite (local) |
| SSH Management | Paramiko |
| Containerization | Docker, Docker Compose |
| Frontend | HTML, Bootstrap 5 |
| Version Control | Git, GitHub |

---

## System Architecture

```
Telegram Groups
      │
      ▼
Telegram Bot (Python)
      │
      ├── HRIS Database (PostgreSQL) ──► Read employee data
      ├── POS Database (PostgreSQL)  ──► Create POS users
      ├── Adempiere Servers (SSH)    ──► Manage ERP services
      └── Local Database (SQLite)   ──► Whitelist, tasks, complaints
                                              │
                                              ▼
                                    Web Dashboard (Flask)
                                              │
                                    ┌─────────┴──────────┐
                                 Manager           IT Support
                               (full access)    (own tasks only)
```

---

## Installation

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL access (HRIS & POS databases)

### 1. Clone the repository
```bash
git clone https://github.com/Azmiifauzan/itoms.git
cd itoms
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your credentials in .env
```

### 3. Run with Docker
```bash
docker compose up -d
```

### 4. Run without Docker
```bash
pip install -r requirements.txt
python bot.py           # Run Telegram bot
python dashboard/app.py # Run web dashboard
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the following:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_USER_IDS=your_telegram_user_id

HRIS_HOST=your_hris_db_host
HRIS_DATABASE=your_hris_db_name
HRIS_USER=your_hris_db_user
HRIS_PASSWORD=your_hris_db_password

WEBSERV_HOST=your_pos_db_host
WEBSERV_DATABASE=your_pos_db_name
WEBSERV_USER=your_pos_db_user
WEBSERV_PASSWORD=your_pos_db_password
```

---

## Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | All | Show available commands |
| `/myid` | All | Get your Telegram User ID |
| `/daftar <employee_no>` | Whitelist | Register employee as POS user |
| `/restart_adempiere` | Whitelist | Restart Adempiere service |
| `/stop_adempiere` | Whitelist | Stop Adempiere service |
| `/start_adempiere` | Whitelist | Start Adempiere service |
| `/share <message>` | Whitelist | Broadcast message to all groups |
| `/status` | Whitelist | Check all database connections |
| `/adduser <id> <name>` | Admin | Add user to whitelist |
| `/removeuser <id>` | Admin | Remove user from whitelist |
| `/listuser` | Admin | List all whitelisted users |
| `/cekid` | Admin | Reply a message to get user ID |

---

## Dashboard Roles

| Role | Permissions |
|---|---|
| **Manager** | Full access — view all tasks, manage users, view all analytics |
| **Head of Support** | View & manage all support tasks, assign to team members |
| **IT Support** | View & update own tasks only, log progress |
| **Programmer** | View & update own tasks only, log progress |

---

## Project Structure

```
itoms/
├── bot.py                    # Telegram bot entry point
├── config.py                 # Configuration loader
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── db/
│   ├── connections.py        # Database connections (HRIS, POS, Adempiere)
│   ├── hris.py               # HRIS queries
│   ├── pos.py                # POS user operations
│   └── local.py              # SQLite operations (whitelist, tasks, complaints)
├── handlers/
│   ├── commands.py           # Telegram command handlers
│   └── adempiere.py          # Adempiere SSH management
└── dashboard/
    ├── app.py                # Flask application
    ├── auth.py               # Authentication
    ├── notif.py              # Telegram notifications
    ├── routes/
    │   ├── manager.py
    │   ├── support.py
    │   └── programmer.py
    └── templates/
        ├── base.html
        ├── login.html
        ├── dashboard.html
        ├── task.html
        ├── users.html
        └── profile.html
```

---

## License

MIT License — feel free to use and modify for your own projects.

---

## Author

**Azmii Fauzan** — IT Support turned Developer  
GitHub: [@Azmiifauzan](https://github.com/Azmiifauzan)
