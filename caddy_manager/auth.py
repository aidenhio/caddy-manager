"""Authentication: first-run setup, login/logout, and the login_required
decorator used by every other route in the app."""
import os
import secrets
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from .configstore import load_config, save_config, is_configured, default_paths_for_root
from .blocks import refresh_all_metadata

bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_configured():
            return redirect(url_for("auth.setup"))
        if not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if is_configured():
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        root_dir = request.form.get("root_dir", "").strip()
        defaults = default_paths_for_root(root_dir)
        conf_dir = request.form.get("conf_dir", "").strip() or defaults["conf_dir"]
        certificate_dir = request.form.get("certificate_dir", "").strip() or defaults["certificate_dir"]
        log_dir = request.form.get("log_dir", "").strip() or defaults["log_dir"]
        caddyfile_path = request.form.get("caddyfile_path", "").strip() or defaults["caddyfile_path"]

        if not username or not password:
            error = "Username and password are required."
        elif password != password2:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif not root_dir:
            error = "Caddy root directory is required."
        else:
            try:
                os.makedirs(root_dir, exist_ok=True)
                os.makedirs(conf_dir, exist_ok=True)
            except OSError as e:
                error = f"Could not create/access that directory: {e}"

        if not error:
            cfg = {
                "secret_key": secrets.token_hex(32),
                "username": username,
                "password_hash": generate_password_hash(password),
                "root_dir": root_dir,
                "conf_dir": conf_dir,
                "certificate_dir": certificate_dir,
                "log_dir": log_dir,
                "caddyfile_path": caddyfile_path,
            }
            save_config(cfg)
            # Switch to the real secret key immediately so the flash message
            # set below actually survives the redirect to /login.
            current_app.secret_key = cfg["secret_key"]
            flash("Setup complete. Please log in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("setup.html", error=error)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not is_configured():
        return redirect(url_for("auth.setup"))
    error = None
    if request.method == "POST":
        cfg = load_config()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == cfg["username"] and check_password_hash(cfg["password_hash"], password):
            session["logged_in"] = True
            session["username"] = username
            # Catch up on anything changed outside the app since the last
            # visit before the user reaches the site blocks list or a
            # preview page, rather than relying on each file self-healing
            # only when it happens to be read.
            refresh_all_metadata()
            return redirect(url_for("main.dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
