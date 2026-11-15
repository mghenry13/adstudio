"""Shared plumbing: paths, subprocess, hashing, JSON, timing.

Stdlib only. Every command reports how long it took, and the numbers are
appended to media/timings.jsonl so slow steps are visible.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the tool
CONFIG_DIR = os.path.expanduser("~/.config/adstudio")
TEMPLATES = os.path.join(ROOT, "templates")


def _workspace():
    """Where a person's own brands, ads, sounds and derived media live.

    Kept apart from the tool so the tool can be shared and updated without
    touching anyone's work. Order: ADSTUDIO_HOME, the user's config, default.
    """
    env = os.environ.get("ADSTUDIO_HOME", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    try:
        with open(os.path.join(CONFIG_DIR, "config.json")) as f:
            w = (json.load(f) or {}).get("workspace")
        if w:
            return os.path.abspath(os.path.expanduser(w))
    except (IOError, ValueError):
        pass
    return os.path.expanduser("~/adstudio-work")


WORK = _workspace()
MEDIA = os.path.join(WORK, "media")          # derived files, never in git
CLIPS = os.path.join(MEDIA, "clips")
RCACHE = os.path.join(MEDIA, "render-cache")
ADS = os.path.join(WORK, "ads")
BRANDS = os.path.join(WORK, "brands")
LIBRARY = os.path.join(WORK, "library")

VIDEO_EXT = (".mov", ".mp4", ".m4v", ".mxf", ".mkv", ".webm")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".heic")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aif", ".aiff")


class Fail(Exception):
    """A user-facing error. Printed without a traceback."""


def die(msg):
    raise Fail(msg)


def run(cmd, check=True, stdin=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=stdin)
    if check and r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-12:]
        raise Fail("%s failed:\n  %s" % (os.path.basename(cmd[0]), "\n  ".join(tail)))
    return r


def sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        if not isinstance(p, (bytes, bytearray)):
            p = json.dumps(p, sort_keys=True, default=str).encode()
        h.update(p)
        h.update(b"\x00")
    return h.hexdigest()


def fingerprint(path):
    """Identity of a file's content: size plus first and last megabyte.

    Survives renames and moves, and is instant on multi-gigabyte footage.
    """
    size = os.path.getsize(path)
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if size > (2 << 20):
            f.seek(size - (1 << 20))
            h.update(f.read(1 << 20))
    return h.hexdigest()


def file_sig(path):
    """Cheap change detector for small assets (path, size, mtime)."""
    st = os.stat(path)
    return "%s|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime))


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return obj


def slug(s, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].strip("-") or "x"


def rel(path):
    """Path relative to the workspace when inside it, for tidy output."""
    path = os.path.abspath(path)
    for base in (WORK, ROOT):
        if path.startswith(base + os.sep):
            return os.path.relpath(path, base)
    return path


def resolve(path, base=None):
    """Timeline paths are relative to the ad folder or to the workspace."""
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    for b in (base, WORK, ROOT):
        if b and os.path.exists(os.path.join(b, path)):
            return os.path.join(b, path)
    return os.path.join(WORK, path)


KEY_ENV = {"gemini": "GEMINI_API_KEY", "runware": "RUNWARE_API_KEY"}


def key_path(name):
    return os.path.join(CONFIG_DIR, name + ".key")


def read_key(name):
    """Per-user secrets. They live outside the repo so it can be shared:
    an environment variable wins, then ~/.config/adstudio/<name>.key."""
    env = os.environ.get(KEY_ENV.get(name, ""), "").strip()
    if env:
        return env
    try:
        with open(key_path(name)) as f:
            return f.read().strip()
    except IOError:
        return ""


def write_key(name, value):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    p = key_path(name)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value.strip() + "\n")
    os.chmod(p, 0o600)
    return p


def config():
    """Defaults, then the repo's config.json (shared), then the user's own
    ~/.config/adstudio/config.json (per person, never in git)."""
    cfg = {"gemini_model": "gemini-3.5-flash",
           "runware_gemini": "google:gemini@3.5-flash",
           "analysis_backend": "auto",
           "preview_port": 8787,
           "workers": 4}
    cfg.update(load_json(os.path.join(ROOT, "config.json"), {}) or {})
    cfg.update(load_json(os.path.join(CONFIG_DIR, "config.json"), {}) or {})
    return cfg


class Timer(object):
    """with Timer("preview"): ...  prints and logs elapsed seconds."""

    def __init__(self, label, quiet=False, **extra):
        self.label, self.quiet, self.extra = label, quiet, extra

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, et, ev, tb):
        self.secs = time.time() - self.t0
        if et is None:
            if not self.quiet:
                print("  %-28s %6.2fs" % (self.label, self.secs))
            try:
                os.makedirs(MEDIA, exist_ok=True)
                row = {"t": int(self.t0), "step": self.label,
                       "secs": round(self.secs, 3)}
                row.update(self.extra)
                with open(os.path.join(MEDIA, "timings.jsonl"), "a") as f:
                    f.write(json.dumps(row) + "\n")
            except IOError:
                pass
        return False


def out(msg=""):
    print(msg)
    sys.stdout.flush()
