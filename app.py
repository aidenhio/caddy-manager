import os

from caddy_manager import create_app
from caddy_manager.server_monitor import start_server_monitor

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = True
    # Flask's reloader (implied by debug=True) re-executes this whole
    # module in a child worker process it spawns to actually serve
    # requests, after first running it once in a parent process that
    # only watches for file changes and never serves anything --
    # WERKZEUG_RUN_MAIN is set only in that child. Gating the ping
    # monitor's startup on it (or starting unconditionally whenever the
    # reloader isn't in play at all, i.e. debug is off) avoids running a
    # second, orphaned copy of the background thread in the parent
    # watcher process.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_server_monitor()
    app.run(host="0.0.0.0", port=port, debug=debug)
