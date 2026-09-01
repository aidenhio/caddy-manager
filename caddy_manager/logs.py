"""Logs page: scanning the configured logs directory for log files,
grouping Caddy's rotated/rolled backups (created via the roll_size /
roll_keep / roll_keep_for options on the log directive -- see
blocks.py's render_log_block) back under the live log file they rolled
from.

Caddy's file writer (backed by the timberjack library) names a rotated
backup `<prefix>-<timestamp>-<reason><ext>`, e.g.
"app-2024-01-02T15-04-05.123-size.log" rolled from "app.log", gaining a
further .gz/.zst suffix if compressed. ROTATED_SUFFIX_RE recognizes
that shape well enough to fold a backup back under its logical
`<prefix><ext>` name. This module doesn't cross-reference blocks.py's
metadata at all -- it just reports whatever files actually exist in the
logs directory, whether or not they were written by a block this app
manages.
"""
import os
import re
from datetime import datetime

from .configstore import get_log_dir

ROTATED_SUFFIX_RE = re.compile(
    r"^(?P<prefix>.+)-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}-[A-Za-z0-9_]+"
    r"(?P<ext>\.[A-Za-z0-9]+)(?:\.gz|\.zst)?$"
)


def logical_log_name(filename):
    """The live log filename a given file belongs to -- itself, unless
    it matches Caddy's rotated-backup naming pattern, in which case
    it's the prefix + original extension that pattern rolled from."""
    match = ROTATED_SUFFIX_RE.match(filename)
    if not match:
        return filename
    return match.group("prefix") + match.group("ext")


def list_log_files():
    """Every file in the configured logs directory, grouped by
    logical_log_name() into one row per logical log stream -- each
    carrying how many physical files (the live file plus any rotated
    backups) belong to it, and the most recent mtime among them.
    Returns [] if no logs directory is configured or it doesn't exist
    yet. Dotfiles are skipped; everything else is treated as a log
    file, since this directory is expected to hold only those."""
    log_dir = get_log_dir()
    if not log_dir or not os.path.isdir(log_dir):
        return []

    groups = {}
    with os.scandir(log_dir) as entries:
        for entry in entries:
            if entry.name.startswith(".") or not entry.is_file():
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            name = logical_log_name(entry.name)
            group = groups.setdefault(name, {"filename": name, "count": 0, "updated_ts": 0.0})
            group["count"] += 1
            group["updated_ts"] = max(group["updated_ts"], mtime)

    logs = list(groups.values())
    for log in logs:
        log["updated"] = datetime.fromtimestamp(log["updated_ts"]).strftime("%d/%m/%Y %I:%M%p")
    logs.sort(key=lambda entry: entry["filename"].lower())
    return logs
