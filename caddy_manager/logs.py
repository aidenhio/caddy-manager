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

from .configstore import get_log_dir, get_log_tail_lines

ROTATED_SUFFIX_RE = re.compile(
    r"^(?P<prefix>.+)-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}-[A-Za-z0-9_]+"
    r"(?P<ext>\.[A-Za-z0-9]+)(?:\.gz|\.zst)?$"
)

# Guard against reading an absurd number of lines regardless of what's
# configured in Settings (or hand-edited into config.json) -- the tail
# read below still has to walk the file backwards in chunks, and there's
# no reason for a "recent activity" modal to ever need more than this.
MAX_TAIL_LINES = 2000
TAIL_CHUNK_SIZE = 8192


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


def _safe_log_dir_path(filename):
    """Resolve filename inside the configured logs directory, preventing
    path traversal. Returns None if no logs directory is configured, or
    if filename would resolve outside it."""
    log_dir = get_log_dir()
    if not log_dir:
        return None
    base = os.path.abspath(log_dir)
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _tail_lines(path, n):
    """The last `n` lines of a (potentially large) text file, read
    backwards in chunks rather than loading the whole file into memory
    -- an access log can grow to many MB, and this runs fresh on every
    "More" click rather than once at page load."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        remaining = f.tell()
        data = b""
        while remaining > 0 and data.count(b"\n") <= n:
            read_size = min(TAIL_CHUNK_SIZE, remaining)
            remaining -= read_size
            f.seek(remaining)
            data = f.read(read_size) + data
        lines = data.splitlines()
        if remaining > 0 and lines:
            # The read window started mid-file, so its first entry is
            # very likely a partial line (we cut in after some earlier,
            # unread line's content) -- drop it rather than show a
            # truncated line as if it were whole.
            lines = lines[1:]
    tail = lines[-n:] if len(lines) > n else lines
    return [line.decode("utf-8", errors="replace") for line in tail]


def read_log_tail(filename):
    """(lines, error) for the live log file matching a Logs page row's
    `filename` (i.e. logical_log_name() -- the un-rotated path Caddy is
    actively appending to, since that's what "the latest log file"
    means for a group that may also include rotated backups). `lines`
    is [] and `error` a user-facing message whenever the file can't be
    read; the number of lines returned is capped by Settings' configured
    tail length (default 50), itself capped at MAX_TAIL_LINES."""
    if not get_log_dir():
        return [], "No logs directory is configured."
    path = _safe_log_dir_path(filename)
    if not path:
        return [], "Invalid log filename."
    if not os.path.isfile(path):
        return [], f"No active log file found for {filename}."
    n = min(get_log_tail_lines(), MAX_TAIL_LINES)
    try:
        return _tail_lines(path, n), None
    except OSError as e:
        return [], f"Could not read the log file: {e}"
