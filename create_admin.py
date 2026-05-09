import hashlib
import sys
sys.path.insert(0, '.')
from db.local import get_conn

def h(p): 
    return hashlib.sha256(p.encode()).hexdigest()

with get_conn() as conn:
    conn.execute(
        "INSERT INTO users_dashboard (username, password_hash, nama, role, telegram_user_id) VALUES (?,?,?,?,?)",
        ('admin', h('admin123'), 'Manager', 'manager', None)
    )
    conn.commit()
    print('User admin berhasil dibuat!')