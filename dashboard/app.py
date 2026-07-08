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
from dashboard.routes.manager import manager_bp
from dashboard.routes.support import support_bp
from dashboard.routes.programmer import programmer_bp
from dashboard.routes.jadwal import jadwal_bp
from dashboard.routes.superadmin import superadmin_bp
from dashboard.routes.storage import storage_bp

app = Flask(__name__, template_folder="templates")
app.jinja_env.globals.update(enumerate=enumerate)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ganti-ini-dengan-random-string")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024


app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True


SESSION_TIMEOUT_MENIT = 30
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SESSION_TIMEOUT_MENIT)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True


@app.before_request
def _extend_session_lifetime():
    if session:
        session.permanent = True


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(manager_bp)
app.register_blueprint(support_bp)
app.register_blueprint(programmer_bp)
app.register_blueprint(jadwal_bp)
app.register_blueprint(superadmin_bp)
app.register_blueprint(storage_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7770, debug=False)
