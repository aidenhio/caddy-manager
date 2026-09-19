import os
import shutil
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

from .auth import login_required
from .configstore import (
    load_config, save_config, get_conf_dir, get_log_dir, get_cert_expiring_soon_days, get_log_tail_lines,
    QUICK_ADD_BLOCK_TYPES, get_quick_add_type_dashboard, get_quick_add_type_site_blocks,
    get_show_metadata_card, get_caddy_log_output_dir, get_caddyfile_path, get_caddyfile_backup_path,
    DASHBOARD_WIDGETS, get_dashboard_widget_visibility, default_paths_for_root,
    MAX_CADDY_SERVERS, MIN_CADDY_SERVER_PING_INTERVAL_SECONDS,
    get_caddy_server_ping_interval_seconds, get_caddy_server_warning_after_misses,
    get_caddy_server_danger_after_misses,
)
from .caddy_api import upstream_stats
from .server_monitor import get_server_statuses, notify_config_changed
from .caddyfile import slugify, extract_body, site_addresses_from_textarea
from .blocks import (
    safe_path, meta_path_for, read_metadata, write_metadata, delete_metadata, list_blocks,
    unique_filename, rename_block_if_first_site_address_changed, build_block_from_form,
    delete_log_file, rename_log_file, log_path_for, set_block_disabled,
)
from .logs import list_log_files, read_log_tail
from .certs import certificates_root, list_certificates, certificate_stats

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    conf_dir = get_conf_dir()
    dir_exists = os.path.isdir(conf_dir)
    blocks = list_blocks() if dir_exists else []
    certs_root = certificates_root()
    certs = list_certificates() if certs_root and os.path.isdir(certs_root) else []
    caddy_stats = upstream_stats()
    by_type = {t: 0 for t in QUICK_ADD_BLOCK_TYPES}
    for b in blocks:
        by_type[b["type"]] = by_type.get(b["type"], 0) + 1
    stats = {
        "total": len(blocks),
        "enabled": sum(1 for b in blocks if not b["disabled"]),
        "disabled": sum(1 for b in blocks if b["disabled"]),
        "by_type": by_type,
        **certificate_stats(certs),
        "current_requests": caddy_stats["current_requests"] if caddy_stats else None,
        "upstreams_total": caddy_stats["upstreams_total"] if caddy_stats else None,
        "failed_requests": caddy_stats["failed_requests"] if caddy_stats else None,
        "unique_requested_sites": caddy_stats["unique_requested_sites"] if caddy_stats else None,
    }
    # created_ts, not updated_ts, so an unrelated edit doesn't bump a block back to the top.
    recent_blocks = sorted(blocks, key=lambda b: b["created_ts"], reverse=True)[:5]
    return render_template(
        "home.html", stats=stats, conf_dir=conf_dir, dir_exists=dir_exists,
        recent_blocks=recent_blocks, quick_add_type=get_quick_add_type_dashboard(),
        dashboard_widgets=get_dashboard_widget_visibility(),
    )


@bp.route("/dashboard/caddy-stats")
@login_required
def dashboard_caddy_stats():
    """JSON refresh for the Dashboard's Current Requests/Upstream Health
    cards, sourced live from Caddy's admin API (see dashboard-stats.js)."""
    caddy_stats = upstream_stats()
    return jsonify(
        current_requests=caddy_stats["current_requests"] if caddy_stats else None,
        upstreams_total=caddy_stats["upstreams_total"] if caddy_stats else None,
        failed_requests=caddy_stats["failed_requests"] if caddy_stats else None,
        unique_requested_sites=caddy_stats["unique_requested_sites"] if caddy_stats else None,
    )


@bp.route("/nav/server-status")
@login_required
def nav_server_status():
    """JSON refresh for the navbar's status tags (see nav-status.js). Reads
    the ping monitor's in-memory state rather than pinging live per request."""
    return jsonify(servers=get_server_statuses())


@bp.route("/site-blocks")
@login_required
def site_blocks():
    conf_dir = get_conf_dir()
    dir_exists = os.path.isdir(conf_dir)
    blocks = list_blocks() if dir_exists else []
    return render_template(
        "site_blocks.html", blocks=blocks, conf_dir=conf_dir, dir_exists=dir_exists,
        quick_add_type=get_quick_add_type_site_blocks(),
    )


@bp.route("/logs")
@login_required
def logs():
    log_dir = get_log_dir()
    dir_exists = bool(log_dir) and os.path.isdir(log_dir)
    logs = list_log_files() if dir_exists else []
    return render_template(
        "logs.html", logs=logs, log_dir=log_dir, dir_exists=dir_exists,
        tail_lines=get_log_tail_lines(),
    )


@bp.route("/logs/<path:filename>/tail")
@login_required
def log_tail(filename):
    lines, error = read_log_tail(filename)
    return jsonify(filename=filename, lines=lines, error=error, tail_lines=get_log_tail_lines())


@bp.route("/certificates")
@login_required
def certificates():
    certs_root = certificates_root()
    dir_exists = bool(certs_root) and os.path.isdir(certs_root)
    certs = list_certificates() if dir_exists else []
    return render_template(
        "certificates.html", certs=certs, certificate_dir=certs_root, dir_exists=dir_exists,
        expiring_soon_days=get_cert_expiring_soon_days(),
    )


@bp.route("/new/<block_type>", methods=["GET", "POST"])
@login_required
def new_block(block_type):
    if block_type not in QUICK_ADD_BLOCK_TYPES:
        abort(404)
    error = None
    meta = {}

    if request.method == "POST":
        # Redo the cheap site-address parse just for a filename hint;
        # build_block_from_form parses the same data identically, so they can't disagree.
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
        f"blocks/{block_type}.html", mode="new", block_type=block_type,
        meta=meta, upstreams_text=upstreams_text, site_addresses_text=site_addresses_text,
        raw_body_text=raw_body_text, error=error, conf_dir=get_conf_dir(), log_dir=get_log_dir(),
        log_dir_display=(get_caddy_log_output_dir() or "<logs dir>").rstrip("/"),
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
    if block_type not in QUICK_ADD_BLOCK_TYPES:
        block_type = "custom"
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
        # The log path is derived from the current filename; brought in line with a rename below.
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

            # Rename to track the primary (first-after-sorting) site address if it changed.
            filename, path = rename_block_if_first_site_address_changed(
                filename, path, old_site_addresses, meta["site_addresses"]
            )

            if filename != original_filename and meta.get("log_enabled"):
                # The log file and its path baked into the content both still reference the old name.
                rename_log_file(original_filename, filename)
                fixed_content, _fixed_meta, fixed_error = build_block_from_form(
                    block_type, request.form, log_filename_hint=filename
                )
                if not fixed_error:
                    with open(path, "w") as f:
                        f.write(fixed_content)

            # Applied last -- only renames .conf/.metadata, independent of everything above.
            filename, path = set_block_disabled(filename, path, disabled_requested)

            flash(f"Saved {filename}" + (" (disabled)" if disabled_requested else ""), "success")
            return redirect(url_for("main.site_blocks"))

    upstreams_text = "\n".join(meta.get("upstreams") or [])
    site_addresses_text = "\n".join(meta.get("site_addresses") or [])
    path = safe_path(filename)
    disabled_toggle_checked = request.form.get("disabled") == "1" if request.method == "POST" \
        else filename.endswith(".disabled")

    return render_template(
        f"blocks/{block_type}.html", mode="edit", block_type=block_type, filename=filename,
        meta=meta, upstreams_text=upstreams_text, site_addresses=meta.get("site_addresses", []),
        site_addresses_text=site_addresses_text, conf_path=path, raw_body_text=raw_body_text,
        error=error, conf_dir=get_conf_dir(), log_dir=get_log_dir(),
        log_dir_display=(get_caddy_log_output_dir() or "<logs dir>").rstrip("/"),
        disabled_toggle_checked=disabled_toggle_checked,
    )


@bp.route("/preview/<path:filename>")
@login_required
def preview_block(filename):
    path = safe_path(filename)
    if not os.path.isfile(path):
        abort(404)

    # Call before reading the raw sidecar below, so it self-heals first and preview stays in sync.
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
        show_metadata_card=get_show_metadata_card(),
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


# Which tab-pane each form action belongs to, and the valid tab ids -- keeps a save on its own
# tab instead of bouncing to User; an unrecognized ?tab= falls back to DEFAULT_TAB.
TAB_IDS = ("user", "password", "general", "directory", "dashboard", "quick-add", "global", "api", "servers", "logs")
DEFAULT_TAB = "user"
ACTION_TAB = {
    "update_user": "user",
    "change_password": "password",
    "update_preview": "general",
    "update_logging": "general",
    "update_certificates": "general",
    "update_dir": "directory",
    "update_dashboard_widgets": "dashboard",
    "update_quick_add": "quick-add",
    "update_global_config": "global",
    "rollback_global_config": "global",
    "update_caddy_api": "api",
    "update_caddy_servers": "servers",
    "update_caddy_logging": "logs",
}


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    cfg = load_config()
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_dir":
            # Fully root-derived or fully custom, never a mix; root_dir stays None in custom
            # mode. Root mode always recomputes the four paths, ignoring the disabled fields.
            custom_dirs = request.form.get("custom_dirs") == "1"
            root_dir = conf_dir = certificate_dir = log_dir = caddyfile_path = None

            if custom_dirs:
                conf_dir = request.form.get("conf_dir", "").strip()
                certificate_dir = request.form.get("certificate_dir", "").strip()
                log_dir = request.form.get("log_dir", "").strip()
                caddyfile_path = request.form.get("caddyfile_path", "").strip()
                if not conf_dir:
                    error = "Conf directory path is required."
            else:
                root_dir = request.form.get("root_dir", "").strip()
                if not root_dir:
                    error = "Caddy root directory is required."
                else:
                    defaults = default_paths_for_root(root_dir)
                    conf_dir = defaults["conf_dir"]
                    certificate_dir = defaults["certificate_dir"]
                    log_dir = defaults["log_dir"]
                    caddyfile_path = defaults["caddyfile_path"]

            if not error:
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
                    return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_logging":
            log_tail_lines = request.form.get("log_tail_lines", "").strip()
            if not (log_tail_lines.isdigit() and int(log_tail_lines) > 0):
                error = "Log tail length must be a positive whole number of lines."
            else:
                cfg["log_tail_lines"] = int(log_tail_lines)
                save_config(cfg)
                flash("Logging settings updated.", "success")
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_global_config":
            caddyfile_path = get_caddyfile_path()
            if not caddyfile_path:
                error = "No Caddyfile path is configured. Set one in Directories first."
            else:
                content = request.form.get("caddyfile_content", "")
                # Normalize to exactly one trailing newline, like a normal editor would.
                if content and not content.endswith("\n"):
                    content += "\n"
                try:
                    os.makedirs(os.path.dirname(caddyfile_path), exist_ok=True)
                    # One backup slot, not a history -- each save replaces it with the prior version.
                    if os.path.isfile(caddyfile_path):
                        shutil.copyfile(caddyfile_path, get_caddyfile_backup_path())
                    with open(caddyfile_path, "w") as f:
                        f.write(content)
                except OSError as e:
                    error = f"Could not write the Caddyfile: {e}"
                else:
                    flash("Caddyfile saved.", "success")
                    return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "rollback_global_config":
            caddyfile_path = get_caddyfile_path()
            backup_path = get_caddyfile_backup_path()
            if not caddyfile_path:
                error = "No Caddyfile path is configured. Set one in Directories first."
            elif not backup_path or not os.path.isfile(backup_path):
                error = "No Caddyfile.bak backup was found to roll back to."
            else:
                try:
                    shutil.copyfile(backup_path, caddyfile_path)
                    # Consumed by the rollback it undoes, so a second rollback can't reapply a stale version.
                    os.remove(backup_path)
                except OSError as e:
                    error = f"Could not roll back the Caddyfile: {e}"
                else:
                    flash("Caddyfile rolled back to the last backup.", "success")
                    return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_caddy_logging":
            cfg["caddy_log_output_dir"] = request.form.get("caddy_log_output_dir", "").strip()
            save_config(cfg)
            flash("Caddy logging settings updated.", "success")
            return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_caddy_api":
            cfg["caddy_admin_api_url"] = request.form.get("caddy_admin_api_url", "").strip()
            save_config(cfg)
            flash("Caddy API settings updated.", "success")
            return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_caddy_servers":
            # Two fixed named slots, not a dynamic list. A slot is either fully filled
            # or fully blank; one field set and the other blank is rejected, not guessed at.
            servers = []
            for i in range(1, MAX_CADDY_SERVERS + 1):
                display_name = request.form.get(f"server{i}_display_name", "").strip()
                host = request.form.get(f"server{i}_host", "").strip()
                if display_name and host:
                    servers.append({"display_name": display_name, "host": host})
                elif display_name or host:
                    error = f"Server {i} needs both a display name and a host, or leave both blank."
                    break

            if not error and len(servers) == MAX_CADDY_SERVERS and servers[0]["host"] == servers[1]["host"]:
                error = "Server 1 and Server 2 must have different hosts."

            ping_interval_raw = request.form.get("ping_interval_seconds", "").strip()
            warning_raw = request.form.get("warning_after_misses", "").strip()
            danger_raw = request.form.get("danger_after_misses", "").strip()

            if not error:
                if not (ping_interval_raw.isdigit() and int(ping_interval_raw) >= MIN_CADDY_SERVER_PING_INTERVAL_SECONDS):
                    error = f"Ping interval must be a whole number of seconds, at least {MIN_CADDY_SERVER_PING_INTERVAL_SECONDS}."
                elif not (warning_raw.isdigit() and int(warning_raw) > 0):
                    error = "Warning threshold must be a positive whole number of missed pings."
                elif not (danger_raw.isdigit() and int(danger_raw) > 0):
                    error = "Offline threshold must be a positive whole number of missed pings."
                elif int(danger_raw) <= int(warning_raw):
                    error = "Offline threshold must be greater than the warning threshold."

            if not error:
                cfg["caddy_servers"] = servers
                cfg["caddy_server_ping_interval_seconds"] = int(ping_interval_raw)
                cfg["caddy_server_warning_after_misses"] = int(warning_raw)
                cfg["caddy_server_danger_after_misses"] = int(danger_raw)
                save_config(cfg)
                # Wakes the monitor for an immediate check, instead of "Checking" for up to a full interval.
                notify_config_changed()
                flash("Caddy Servers settings updated.", "success")
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_certificates":
            cert_expiring_soon_days = request.form.get("cert_expiring_soon_days", "").strip()
            if not (cert_expiring_soon_days.isdigit() and int(cert_expiring_soon_days) > 0):
                error = "Expiring soon threshold must be a positive whole number of days."
            else:
                cfg["cert_expiring_soon_days"] = int(cert_expiring_soon_days)
                save_config(cfg)
                flash("Certificate settings updated.", "success")
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_preview":
            cfg["show_metadata_card"] = request.form.get("show_metadata_card") == "on"
            save_config(cfg)
            flash("Preview page settings updated.", "success")
            return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_dashboard_widgets":
            cfg["dashboard_widgets"] = {
                key: request.form.get(key) == "on" for key, _label in DASHBOARD_WIDGETS
            }
            save_config(cfg)
            flash("Dashboard settings updated.", "success")
            return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_quick_add":
            quick_add_type_dashboard = request.form.get("quick_add_type_dashboard", "")
            quick_add_type_site_blocks = request.form.get("quick_add_type_site_blocks", "")
            valid_choices = ("",) + QUICK_ADD_BLOCK_TYPES
            if quick_add_type_dashboard not in valid_choices or quick_add_type_site_blocks not in valid_choices:
                error = "Invalid Quick Add block type selected."
            else:
                cfg["quick_add_type_dashboard"] = quick_add_type_dashboard
                cfg["quick_add_type_site_blocks"] = quick_add_type_site_blocks
                save_config(cfg)
                flash("Quick Add settings updated.", "success")
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

        elif action == "update_user":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            if not username:
                error = "Username is required."
            else:
                cfg["username"] = username
                cfg["email"] = email
                save_config(cfg)
                session["username"] = username
                flash("User settings updated.", "success")
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

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
                return redirect(url_for("main.settings", tab=ACTION_TAB[action]))

    # Shows what's on disk, or what was just submitted if validation failed, so a rejected save doesn't wipe the edit.
    if request.method == "POST" and request.form.get("action") == "update_global_config":
        caddyfile_content = request.form.get("caddyfile_content", "")
        caddyfile_read_error = None
    else:
        caddyfile_content = ""
        caddyfile_read_error = None
        caddyfile_path = get_caddyfile_path()
        if caddyfile_path and os.path.isfile(caddyfile_path):
            try:
                with open(caddyfile_path) as f:
                    caddyfile_content = f.read()
            except OSError as e:
                caddyfile_read_error = f"Could not read the Caddyfile: {e}"

    caddyfile_backup_path = get_caddyfile_backup_path()
    caddyfile_backup_updated = None
    if caddyfile_backup_path and os.path.isfile(caddyfile_backup_path):
        caddyfile_backup_updated = datetime.fromtimestamp(
            os.path.getmtime(caddyfile_backup_path)
        ).strftime("%d/%m/%Y %I:%M%p")

    # Same "don't wipe a rejected edit" treatment as Global Configuration above.
    # caddy_servers_padded always has exactly MAX_CADDY_SERVERS entries for the template to index into.
    if request.method == "POST" and request.form.get("action") == "update_caddy_servers":
        caddy_servers_padded = [
            {
                "display_name": request.form.get(f"server{i}_display_name", "").strip(),
                "host": request.form.get(f"server{i}_host", "").strip(),
            }
            for i in range(1, MAX_CADDY_SERVERS + 1)
        ]
        caddy_server_form = {
            "ping_interval": request.form.get("ping_interval_seconds", "").strip(),
            "warning_after": request.form.get("warning_after_misses", "").strip(),
            "danger_after": request.form.get("danger_after_misses", "").strip(),
        }
    else:
        raw_servers = (cfg.get("caddy_servers") or [])[:MAX_CADDY_SERVERS]
        caddy_servers_padded = [
            {
                "display_name": raw_servers[i].get("display_name", "") if i < len(raw_servers) and isinstance(raw_servers[i], dict) else "",
                "host": raw_servers[i].get("host", "") if i < len(raw_servers) and isinstance(raw_servers[i], dict) else "",
            }
            for i in range(MAX_CADDY_SERVERS)
        ]
        caddy_server_form = {
            "ping_interval": get_caddy_server_ping_interval_seconds(),
            "warning_after": get_caddy_server_warning_after_misses(),
            "danger_after": get_caddy_server_danger_after_misses(),
        }

    # A POST that failed validation re-shows its own tab; a GET reads ?tab= from the save redirect.
    if request.method == "POST":
        active_tab = ACTION_TAB.get(action, DEFAULT_TAB)
    else:
        requested_tab = request.args.get("tab", "")
        active_tab = requested_tab if requested_tab in TAB_IDS else DEFAULT_TAB

    return render_template(
        "settings.html", cfg=cfg, error=error,
        dashboard_widgets=get_dashboard_widget_visibility(),
        conf_dir=get_conf_dir(),
        caddyfile_content=caddyfile_content, caddyfile_read_error=caddyfile_read_error,
        caddyfile_backup_updated=caddyfile_backup_updated,
        caddy_servers_padded=caddy_servers_padded, caddy_server_form=caddy_server_form,
        active_tab=active_tab,
    )
