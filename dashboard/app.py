"""
dashboard/app.py
Flask app untuk dashboard IT.
Jalankan: python dashboard/app.py
"""

import sys
import os
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, session
from dashboard.auth import auth_bp
from dashboard.routes.dashboard import dashboard_bp
from dashboard.routes.jadwal import jadwal_bp
from dashboard.routes.superadmin import superadmin_bp
from dashboard.routes.storage import storage_bp
from dashboard.routes.check_retur import check_retur_bp
from dashboard.routes.berita_acara import berita_acara_bp
from dashboard.routes.bot import bot_bp

app = Flask(__name__, template_folder="templates")
app.jinja_env.globals.update(enumerate=enumerate)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY"
    )
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024

app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

SESSION_TIMEOUT_MENIT = 30
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SESSION_TIMEOUT_MENIT)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True


@app.before_request
def _extend_session_lifetime():
    # Kalau user lagi login (session ada isinya), tandai permanent supaya
    # Flask ngirim ulang cookie dengan waktu expired yang baru tiap request.
    if session:
        session.permanent = True


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(jadwal_bp)
app.register_blueprint(superadmin_bp)
app.register_blueprint(storage_bp)
app.register_blueprint(check_retur_bp)
app.register_blueprint(berita_acara_bp)
app.register_blueprint(bot_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7770, debug=False)
