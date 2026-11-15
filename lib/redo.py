"""Redo without a chat open: start Claude Code in the background.

When the page sends Redo and no chat is waiting on that ad, the server runs
`adstudio run-redo <ad>`, which hands the pending comments to the Claude
command-line tool. Claude edits the timeline and snapshots a new version;
the page then offers it. Each ad keeps its own conversation, so later
rounds remember earlier ones.

What the background run may do is deliberately narrow: read and edit files,
and run the adstudio command. Nothing else.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time

from . import versions
from .util import ADS, MEDIA, ROOT, WORK, Fail, config, load_json, out, save_json

APP_CLI = os.path.expanduser("~/Library/Application Support/Claude/claude-code/*/*/"
                             "claude.app/Contents/MacOS/claude")
LAUNCHER = os.path.expanduser("~/.config/adstudio/adstudio")


def claude_bin():
    c = config().get("claude_command") or shutil.which("claude")
    if c:
        return c
    hits = sorted(glob.glob(APP_CLI), key=os.path.getmtime)
    return hits[-1] if hits else ""


def _name(ad_dir):
    return os.path.relpath(ad_dir, ADS).replace("/", "--")


def status_path(ad_dir):
    return os.path.join(MEDIA, "redo-%s.json" % _name(ad_dir))


def status(ad_dir):
    s = load_json(status_path(ad_dir), {}) or {}
    if s.get("state") == "running":
        try:
            os.kill(int(s.get("pid", 0)), 0)
        except (OSError, ValueError):
            s = {"state": "failed", "message": "The background run stopped unexpectedly."}
    return s


def _set(ad_dir, **kw):
    os.makedirs(MEDIA, exist_ok=True)
    save_json(status_path(ad_dir), dict(kw, at=int(time.time())))


def start(ad_dir):
    """Called by the server. Returns immediately."""
    if not config().get("auto_redo", True):
        return
    if status(ad_dir).get("state") == "running":
        return
    log = open(os.path.join(MEDIA, "redo-%s.log" % _name(ad_dir)), "a")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "adstudio"), "run-redo",
                          os.path.relpath(ad_dir, ADS)],
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         start_new_session=True, cwd=WORK)
    _set(ad_dir, state="running", pid=p.pid)


def prompt(ad_dir, pending):
    ref = os.path.relpath(ad_dir, ADS)
    lines = []
    for fb in pending:
        if fb.get("t") is None:
            lines.append("- (whole video) %s" % fb["text"])
        else:
            lines.append("- at %s [%s]: %s" % (
                versions.tc(fb["t"]), versions.where(ad_dir, fb["version"], fb["t"]), fb["text"]))
    return (
        "Use the adstudio skill. The user reviewed the ad `%s` on its version page and pressed "
        "Redo. Nobody is watching this run, so do not ask questions.\n\n"
        "Their comments on version %d:\n%s\n\n"
        "Do this:\n"
        "1. Read %s/timeline.json and docs/LESSONS.md in the workspace.\n"
        "2. Apply every comment by editing timeline.json. Change only what was asked.\n"
        "3. Run: %s snapshot %s --note \"<one line on what you did>\"\n"
        "If a comment cannot be done or is unclear, do the rest and say so plainly in the note. "
        "Do not run sync, ingest, render or any command other than adstudio."
        % (ref, pending[0]["version"], "\n".join(lines), os.path.relpath(ad_dir, WORK),
           LAUNCHER, ref))


def run(ad_dir):
    """The background job itself."""
    pending = versions.pending(ad_dir)
    if not pending:
        _set(ad_dir, state="idle")
        return
    cli = claude_bin()
    if not cli:
        _set(ad_dir, state="failed", message="Claude Code is not installed on this Mac.")
        return
    _set(ad_dir, state="running", pid=os.getpid())
    sess_p = os.path.join(ad_dir, ".claude-session")
    sess = open(sess_p).read().strip() if os.path.exists(sess_p) else ""
    cmd = [cli, "-p", prompt(ad_dir, pending), "--output-format", "json",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read,Edit,Write,Glob,Grep,Skill,Bash(%s:*)" % LAUNCHER,
           "--add-dir", ROOT]
    if sess:
        cmd += ["--resume", sess]
    env = dict(os.environ)
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)
    try:
        r = subprocess.run(cmd, cwd=WORK, env=env, capture_output=True, text=True,
                           timeout=float(config().get("redo_timeout", 900)))
    except subprocess.TimeoutExpired:
        _set(ad_dir, state="failed", message="Claude took too long and was stopped.")
        return
    text = (r.stdout or "") + (r.stderr or "")
    out(text[-4000:])
    try:
        sid = json.loads(r.stdout).get("session_id")
        if sid:
            with open(sess_p, "w") as f:
                f.write(sid)
    except (ValueError, AttributeError):
        pass
    if "Not logged in" in text or "/login" in text[:400]:
        _set(ad_dir, state="failed", login=True,
             message="Claude Code is not signed in on this Mac. Open Terminal, run the "
                     "command below, type /login, then press Redo again.",
             command='"%s"' % cli)
    elif versions.pending(ad_dir):
        _set(ad_dir, state="failed",
             message="Claude ran but did not save a new version. Say \"redo\" in a chat instead.")
    else:
        _set(ad_dir, state="idle")
