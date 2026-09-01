import os
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from .auth import login_required
from .configstore import load_config, save_config, get_conf_dir, get_log_dir
from .caddyfile import slugify, extract_body, site_addresses_from_textarea
from .blocks import (
    safe_path, meta_path_for, read_metadata, write_metadata, delete_metadata, list_blocks,
    unique_filename, rename_block_if_first_site_address_changed, build_block_from_form,
    delete_log_file, rename_log_file, log_path_for, set_block_disabled,
)

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    conf_dir = get_conf_dir()
    dir_exists = os.path.isdir(conf_dir)
    blocks = list_blocks() if dir_exists else []
    stats = {
        "total": len(blocks),
        "enabled": sum(1 for b in blocks if not b["disabled"]),
        "disabled": sum(1 for b in blocks if b["disabled"]),
    }
    return render_template(
        "home.html", stats=stats, conf_dir=conf_dir, dir_exists=dir_exists
    )


@bp.route("/site-blocks")
@login_required
def site_blocks():
    conf_dir = get_conf_dir()
    dir_exists = os.path.isdir(conf_dir)
    blocks = list_blocks() if dir_exists else []
    return render_template(
        "site_blocks.html", blocks=blocks, conf_dir=conf_dir, dir_exists=dir_exists
    )


@bp.route("/new/<block_type>", methods=["GET", "POST"])
@login_required
def new_block(block_type):
    if block_type not in ("reverse_proxy", "redirect", "load_balancer", "static_site", "custom"):
        abort(404)
    error = None
    meta = {}

    if request.method == "POST":
        # The eventual filename (and hence the log file's path, embedded in
        # the rendered content if logging is enabled) isn't known until the
        # site addresses have been parsed/normalized -- which is exactly
        # what build_block_from_form does internally. Rather than duplicate
        # that validation here, redo the same cheap parse just to get a
        # filename hint to pass in; build_block_from_form will parse the
        # identical form data the same way, so the two never disagree.
        create_disabled = request.form.get("disabled") == "1"
        site_addresses_hint = site_addresses_from_textarea(request.form.get("site_addresses", ""))
        filename_hint = None
        if site_addresses_hint:
            filename_hint = unique_filename(slugify(site_addresses_hint[0]))
            if create_disabled:
                filename_hint += ".disabled"

        content, meta, error = build_block_from_form(block_type, request.form, log_filename_hint=filename_hint)
        if not error:
            filename = filename_hint
            os.makedirs(get_conf_dir(), exist_ok=True)
            if meta.get("log_enabled"):
                log_dir = get_log_dir()
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
            path = safe_path(filename)
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, meta)
            flash(f"Created {filename}" + (" (disabled)" if create_disabled else ""), "success")
            return redirect(url_for("main.site_blocks"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    site_addresses_text = "\n".join(meta.get("site_addresses") or [])
    raw_body_text = request.form.get("raw_content", "") if request.method == "POST" and block_type == "custom" else ""
    disabled_toggle_checked = request.form.get("disabled") == "1" if request.method == "POST" else False
    return render_template(
        "block_form.html", mode="new", block_type=block_type,
        meta=meta, upstreams_text=upstreams_text, site_addresses_text=site_addresses_text,
        raw_body_text=raw_body_text, error=error, conf_dir=get_conf_dir(), log_dir=get_log_dir(), log_dir_display=(get_log_dir() or "<logs dir>").rstrip("/"),
        disabled_toggle_checked=disabled_toggle_checked,
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
    previous_log_enabled = meta.get("log_enabled", False)
    error = None
    raw_body_text = ""
    if block_type == "custom" and request.method == "GET":
        with open(path) as f:
            raw_body_text = extract_body(f.read())

    if request.method == "POST":
        original_filename = filename
        disabled_requested = request.form.get("disabled") == "1"
        # The log block's `output file` path (if enabled) is derived from
        # the block's current on-disk filename -- if the primary site
        # address changes below, both the content and the physical log
        # file are brought in line with the new filename afterwards.
        content, meta, error = build_block_from_form(block_type, request.form, log_filename_hint=filename)
        if block_type == "custom":
            raw_body_text = request.form.get("raw_content", "").strip()

        if not error:
            if meta.get("log_enabled"):
                log_dir = get_log_dir()
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            write_metadata(filename, path, meta)

            if previous_log_enabled and not meta.get("log_enabled"):
                delete_log_file(original_filename)

            # Rename the .conf/.metadata pair if the primary (first-after-
            # sorting) site address changed, so the filename keeps tracking it.
            filename, path = rename_block_if_first_site_address_changed(
                filename, path, old_site_addresses, meta["site_addresses"]
            )

            if filename != original_filename and meta.get("log_enabled"):
                # The log file (if any) and the log path baked into the
                # content we just wrote both still reference the old
                # filename -- move the file and re-render the content
                # against the new one.
                rename_log_file(original_filename, filename)
                fixed_content, _fixed_meta, fixed_error = build_block_from_form(
                    block_type, request.form, log_filename_hint=filename
                )
                if not fixed_error:
                    with open(path, "w") as f:
                        f.write(fixed_content)

            # Apply the form's own disable/enable toggle last -- it doesn't
            # touch the log file (whose name never includes the .disabled
            # suffix) or the rendered content, just the .conf/.metadata
            # filenames, so it's independent of everything above.
            filename, path = set_block_disabled(filename, path, disabled_requested)

            flash(f"Saved {filename}" + (" (disabled)" if disabled_requested else ""), "success")
            return redirect(url_for("main.site_blocks"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    site_addresses_text = "\n".join(meta.get("site_addresses") or [])
    path = safe_path(filename)
    disabled_toggle_checked = request.form.get("disabled") == "1" if request.method == "POST" \
        else filename.endswith(".disabled")

    return render_template(
        "block_form.html", mode="edit", block_type=block_type, filename=filename,
        meta=meta, upstreams_text=upstreams_text, site_addresses=meta.get("site_addresses", []),
        site_addresses_text=site_addresses_text, conf_path=path, raw_body_text=raw_body_text,
        error=error, conf_dir=get_conf_dir(), log_dir=get_log_dir(), log_dir_display=(get_log_dir() or "<logs dir>").rstrip("/"),
        disabled_toggle_checked=disabled_toggle_checked,
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
        log_path=log_path_for(filename) if meta.get("log_enabled") else None,
    )


@bp.route("/toggle/<path:filename>", methods=["POST"])
@login_required
def toggle_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    new_name, _new_path = set_block_disabled(filename, path, not filename.endswith(".disabled"))
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
        delete_log_file(filename)
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
            root_dir = request.form.get("root_dir", "").strip()
            conf_dir = request.form.get("conf_dir", "").strip()
            certificate_dir = request.form.get("certificate_dir", "").strip()
            log_dir = request.form.get("log_dir", "").strip()
            caddyfile_path = request.form.get("caddyfile_path", "").strip()
            if not conf_dir:
                error = "Conf directory path is required."
            else:
                try:
                    os.makedirs(conf_dir, exist_ok=True)
                except OSError as e:
                    error = f"Could not create/access that directory: {e}"
                if not error:
                    cfg.update(
                        root_dir=root_dir, conf_dir=conf_dir, certificate_dir=certificate_dir,
                        log_dir=log_dir, caddyfile_path=caddyfile_path,
                    )
                    save_config(cfg)
                    flash("Directories updated.", "success")
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
