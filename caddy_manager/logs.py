"""Logs page: scans the logs directory and groups Caddy's rotated backups
(`<prefix>-<timestamp>-<reason><ext>`) back under their live log file."""
import json
import os
import re
from datetime import datetime

from .configstore import get_log_dir, get_log_tail_lines

ROTATED_SUFFIX_RE = re.compile(
    r"^(?P<prefix>.+)-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}-[A-Za-z0-9_]+"
    r"(?P<ext>\.[A-Za-z0-9]+)(?:\.gz|\.zst)?$"
)

# Hard cap regardless of what Settings (or a hand-edited config.json) requests.
MAX_TAIL_LINES = 2000
TAIL_CHUNK_SIZE = 8192

# Format sniffing only looks at the end of the file, so a big log costs one small read.
FORMAT_SAMPLE_BYTES = 32768
FORMAT_SAMPLE_LINES = 10


def logical_log_name(filename):
    """The live log filename a file belongs to -- itself, unless it
    matches Caddy's rotated-backup pattern (then prefix + extension)."""
    match = ROTATED_SUFFIX_RE.match(filename)
    if not match:
        return filename
    return match.group("prefix") + match.group("ext")


def detect_log_format(path):
    """"json" if each of the last few non-blank lines is a JSON object, else "console".
    None if the file is missing, unreadable or has no complete lines yet."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            start = max(0, f.tell() - FORMAT_SAMPLE_BYTES)
            f.seek(start)
            data = f.read()
    except OSError:
        return None
    lines = data.splitlines()
    if start > 0 and lines:
        # The window began mid-file, so the first entry is likely a partial line -- drop it.
        lines = lines[1:]
    lines = [line.strip() for line in lines if line.strip()][-FORMAT_SAMPLE_LINES:]
    if not lines:
        return None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            return "console"
        if not isinstance(entry, dict):
            return "console"
    return "json"


def list_log_files():
    """Every file in the logs directory, grouped by logical_log_name() into one row per
    stream (file count, latest mtime, format of the live file). [] if unconfigured."""
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
        # Rotated backups may be compressed, so only the live file is sniffed.
        log["format"] = detect_log_format(os.path.join(log_dir, log["filename"]))
    logs.sort(key=lambda entry: entry["filename"].lower())
    return logs


def _safe_log_dir_path(filename):
    """Resolve filename inside the logs directory, preventing traversal.
    None if unconfigured or filename resolves outside it."""
    log_dir = get_log_dir()
    if not log_dir:
        return None
    base = os.path.abspath(log_dir)
    target = os.path.abspath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _tail_lines(path, n):
    """The last `n` lines, read backwards in chunks rather than loading
    the whole file -- logs can grow large and this runs on every "More" click."""
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
            # The window started mid-file, so the first entry is likely a partial line -- drop it.
            lines = lines[1:]
    tail = lines[-n:] if len(lines) > n else lines
    return [line.decode("utf-8", errors="replace") for line in tail]


def read_log_tail(filename):
    """(lines, error) for the live log file behind a Logs page row's
    `filename`. Line count is capped by Settings' tail length, itself capped at MAX_TAIL_LINES."""
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
