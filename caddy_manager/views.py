import os
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from .auth import login_required
from .configstore import load_config, save_config, get_caddy_dir
from .caddyfile import slugify, extract_body
from .blocks import (
    safe_path, meta_path_for, read_metadata, write_metadata, delete_metadata, list_blocks,
    unique_filename, rename_block_if_first_site_address_changed, build_block_from_form,
)

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    stats = {
        "total": len(blocks),
        "enabled": sum(1 for b in blocks if not b["disabled"]),
        "disabled": sum(1 for b in blocks if b["disabled"]),
    }
    return render_template(
        "home.html", stats=stats, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@bp.route("/site-blocks")
@login_required
def site_blocks():
    caddy_dir = get_caddy_dir()
    dir_exists = os.path.isdir(caddy_dir)
    blocks = list_blocks() if dir_exists else []
    return render_template(
        "site_blocks.html", blocks=blocks, caddy_dir=caddy_dir, dir_exists=dir_exists
    )


@bp.route("/new/<block_type>", methods=["GET", "POST"])
@login_required
def new_block(block_type):
    if block_type not in ("reverse_proxy", "redirect", "load_balancer", "static_site", "custom"):
        abort(404)
    error = None
    meta = {}

    if request.method == "POST":
        content, meta, error = build_block_from_form(block_type, request.form)
        if not error:
            create_disabled = request.form.get("create_disabled") == "1"
            filename = unique_filename(slugify(meta["site_addresses"][0]))
            if create_disabled:
                filename += ".disabled"
            os.makedirs(get_caddy_dir(), exist_ok=True)
            path = safe_path(filename)
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, meta)
            flash(f"Created {filename}" + (" (disabled)" if create_disabled else ""), "success")
            return redirect(url_for("main.site_blocks"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    site_addresses_text = "\n".join(meta.get("site_addresses") or [])
    raw_body_text = request.form.get("raw_content", "") if request.method == "POST" and block_type == "custom" else ""
    return render_template(
        "block_form.html", mode="new", block_type=block_type,
        meta=meta, upstreams_text=upstreams_text, site_addresses_text=site_addresses_text,
        raw_body_text=raw_body_text, error=error, caddy_dir=get_caddy_dir()
    )


@bp.route("/edit/<path:filename>", methods=["GET", "POST"])
@login_required
def edit_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    meta = read_metadata(filename, path)
    block_type = meta.get("type", "custom")
    old_site_addresses = meta.get("site_addresses", [])
    error = None
    raw_body_text = ""
    if block_type == "custom" and request.method == "GET":
        with open(path) as f:
            raw_body_text = extract_body(f.read())

    if request.method == "POST":
        content, meta, error = build_block_from_form(block_type, request.form)
        if block_type == "custom":
            raw_body_text = request.form.get("raw_content", "").strip()

        if not error:
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, meta)
            # Rename the .conf/.metadata pair if the primary (first-after-
            # sorting) site address changed, so the filename keeps tracking it.
            filename, path = rename_block_if_first_site_address_changed(
                filename, path, old_site_addresses, meta["site_addresses"]
            )
            flash(f"Saved {filename}", "success")
            return redirect(url_for("main.site_blocks"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    site_addresses_text = "\n".join(meta.get("site_addresses") or [])
    path = safe_path(filename)

    return render_template(
        "block_form.html", mode="edit", block_type=block_type, filename=filename,
        meta=meta, upstreams_text=upstreams_text, site_addresses=meta.get("site_addresses", []),
        site_addresses_text=site_addresses_text, conf_path=path, raw_body_text=raw_body_text,
        error=error, caddy_dir=get_caddy_dir()
    )


@bp.route("/preview/<path:filename>")
@login_required
def preview_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    # read_metadata may self-heal (rewrite) a stale/missing sidecar, so call
    # it before reading the raw metadata file below -- the preview should
    # always show the same sidecar content the rest of the app is using.
    meta = read_metadata(filename, path)
    block_type = meta.get("type", "custom")

    with open(path) as f:
        conf_content = f.read()

    meta_file = meta_path_for(filename)
    if os.path.isfile(meta_file):
        with open(meta_file) as f:
            metadata_content = f.read()
    else:
        metadata_content = "(no metadata file found)"

    created_ts = meta.get("created_ts")
    return render_template(
        "preview.html",
        filename=filename,
        block_type=block_type,
        meta=meta,
        site_addresses=meta.get("site_addresses", []),
        disabled=filename.endswith(".disabled"),
        conf_path=path,
        conf_content=conf_content,
        metadata_content=metadata_content,
        created=datetime.fromtimestamp(created_ts).strftime("%d/%m/%Y %I:%M%p") if created_ts else "Unknown",
        updated=datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d/%m/%Y %I:%M%p"),
    )


@bp.route("/toggle/<path:filename>", methods=["POST"])
@login_required
def toggle_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    if filename.endswith(".disabled"):
        new_name = filename[: -len(".disabled")]
    else:
        new_name = filename + ".disabled"

    os.rename(path, safe_path(new_name))
    state = "Disabled" if new_name.endswith(".disabled") else "Enabled"
    flash(f"{state} {new_name}", "success")
    return redirect(url_for("main.site_blocks"))


@bp.route("/delete/<path:filename>", methods=["POST"])
@login_required
def delete_block(filename):
    path = safe_path(filename)
    if os.path.isfile(path):
        os.remove(path)
        delete_metadata(filename)
        flash(f"Deleted {filename}", "success")
    return redirect(url_for("main.site_blocks"))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    cfg = load_config()
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_dir":
            new_dir = request.form.get("caddy_dir", "").strip()
            if not new_dir:
                error = "Directory is required."
            else:
                try:
                    os.makedirs(new_dir, exist_ok=True)
                except OSError as e:
                    error = f"Could not create/access that directory: {e}"
                if not error:
                    cfg["caddy_dir"] = new_dir
                    save_config(cfg)
                    flash("Caddy directory updated.", "success")
                    return redirect(url_for("main.settings"))

        elif action == "change_password":
            current = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password2 = request.form.get("new_password2", "")
            if not check_password_hash(cfg["password_hash"], current):
                error = "Current password is incorrect."
            elif len(new_password) < 6:
                error = "New password must be at least 6 characters."
            elif new_password != new_password2:
                error = "New passwords do not match."
            else:
                cfg["password_hash"] = generate_password_hash(new_password)
                save_config(cfg)
                flash("Password updated.", "success")
                return redirect(url_for("main.settings"))

    return render_template("settings.html", cfg=cfg, error=error)
