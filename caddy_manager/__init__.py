import os
import secrets

from flask import Flask

from .configstore import BASE_DIR, load_config
from .colors import type_color
from .server_monitor import get_server_statuses


def create_app():
    # templates/ and static/ live at the project root, one level up from this package.
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )

    # Re-evaluated per render, so every page's navbar status tags reflect
    # the ping monitor's current state with no per-view wiring needed.
    app.context_processor(lambda: dict(type_color=type_color, nav_caddy_servers=get_server_statuses()))

    # Placeholder so sessions/flash work before setup saves a real secret_key.
    app.secret_key = secrets.token_hex(32)

    @app.before_request
    def load_secret_key():
        cfg = load_config()
        if cfg and cfg.get("secret_key"):
            app.secret_key = cfg["secret_key"]

    from .auth import bp as auth_bp
    from .views import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    return app
