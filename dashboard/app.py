"""
dashboard/app.py
Flask app untuk dashboard IT.
Jalankan: python dashboard/app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask
from dashboard.auth import auth_bp
from dashboard.routes.manager import manager_bp
from dashboard.routes.support import support_bp
from dashboard.routes.programmer import programmer_bp
from dashboard.routes.jadwal import jadwal_bp
from dashboard.routes.superadmin import superadmin_bp

app = Flask(__name__, template_folder="templates")
app.jinja_env.globals.update(enumerate=enumerate)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ganti-ini-dengan-random-string")

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(manager_bp)
app.register_blueprint(support_bp)
app.register_blueprint(programmer_bp)
app.register_blueprint(jadwal_bp)
app.register_blueprint(superadmin_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7770, debug=False)