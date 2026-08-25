import os
import secrets

from flask import Flask

from .configstore import BASE_DIR, load_config
from .colors import type_color


def create_app():
    # templates/ and static/ live at the project root (one level up from
    # this package), unchanged from before this app was split into modules.
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )

    app.context_processor(lambda: dict(type_color=type_color))

    # A random placeholder so the session/flash machinery always has a
    # usable key -- even on the very first request Flask ever handles,
    # before `load_secret_key` below gets a chance to run. Overwritten by
    # the real, persisted secret_key as soon as setup has completed.
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
