import os

from caddy_manager import create_app
from caddy_manager.server_monitor import start_server_monitor

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Off by default -- Werkzeug's debug mode exposes an interactive, unauthenticated
    # code-execution console on any unhandled error. Set FLASK_DEBUG=1 for local dev.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    # debug=True forks a reloader child that sets WERKZEUG_RUN_MAIN; only
    # start the monitor there, so the parent watcher doesn't run a second copy.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_server_monitor()
    app.run(host="0.0.0.0", port=port, debug=debug)
