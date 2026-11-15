"""Watched folders: scan for new footage and assets, then process only those.

  adstudio watch add <brand> <folder>     remember a folder
  adstudio sync                           ingest, transcribe and analyze what is new
  adstudio sync --dry-run                 only say what is new

"New" is decided from path, size and modified time, which costs nothing even
on a cloud drive. A file that was merely renamed or moved is recognised by
its content when it is ingested, so it is not analyzed twice.
"""

import os
import time

from . import analyze, media, transcribe
from .util import (IMAGE_EXT, MEDIA, VIDEO_EXT, WORK, Fail, Timer, load_json, out,
                   save_json)

SOURCES = os.path.join(WORK, "sources.json")
SEEN = os.path.join(MEDIA, "seen.json")


def sources():
    return load_json(SOURCES, []) or []


def add(brand, folder):
    from .util import BRANDS
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        raise Fail("not a folder: %s" % folder)
    if not os.path.isdir(os.path.join(BRANDS, brand)):
        raise Fail("unknown brand '%s' (adstudio brand list)" % brand)
    rows = sources()
    if any(r["path"] == folder for r in rows):
        raise Fail("already watching %s" % folder)
    rows.append({"brand": brand, "path": folder, "added": time.strftime("%Y-%m-%d")})
    save_json(SOURCES, rows)
    out("watching %s for %s" % (folder, brand))


def remove(folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    rows = [r for r in sources() if r["path"] != folder]
    if len(rows) == len(sources()):
        raise Fail("not watching %s" % folder)
    save_json(SOURCES, rows)
    out("stopped watching %s (its clips stay in the catalog)" % folder)


def listing():
    rows = sources()
    for r in rows:
        ok = "" if os.path.isdir(r["path"]) else "   (folder not found)"
        out("%-14s %s%s" % (r["brand"], r["path"], ok))
    out("%d watched folders" % len(rows))


def _walk(folder):
    for base, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for n in sorted(names):
            if n.startswith(".") or not n.lower().endswith(VIDEO_EXT + IMAGE_EXT):
                continue
            p = os.path.join(base, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            yield p, [st.st_size, int(st.st_mtime)]


def scan():
    """Returns {brand: [(path, sig)]} of files not processed before."""
    seen = load_json(SEEN, {}) or {}
    new, missing = {}, []
    for r in sources():
        if not os.path.isdir(r["path"]):
            missing.append(r["path"])
            continue
        for p, sig in _walk(r["path"]):
            if (seen.get(p) or [])[:2] != sig:
                new.setdefault(r["brand"], []).append((p, sig))
    return new, missing


def sync(dry_run=False, do_analyze=True):
    if not sources():
        raise Fail("no watched folders yet. Add one: adstudio watch add <brand> <folder>")
    with Timer("scan", quiet=True) as t:
        new, missing = scan()
    for m in missing:
        out("  skipped, folder not found: %s" % m)
    total = sum(len(v) for v in new.values())
    out("%d new files in %d watched folders (scan %.2fs)" % (total, len(sources()), t.secs))
    for brand, files in sorted(new.items()):
        size = sum(s[0] for _, s in files) / 1e6
        vids = sum(1 for p, _ in files if p.lower().endswith(VIDEO_EXT))
        out("  %-14s %d videos, %d images, %.0f MB" % (brand, vids, len(files) - vids, size))
        if dry_run:
            for p, _ in files[:40]:
                out("    " + p)
            if len(files) > 40:
                out("    ... and %d more" % (len(files) - 40))
    if dry_run:
        return
    if not total:
        _backlog(do_analyze)
        return
    seen = load_json(SEEN, {}) or {}
    metas = []
    for brand, files in sorted(new.items()):
        ok = []
        for p, sig in files:            # one unreadable file must not stop the rest
            try:
                m = media.ingest([p], brand, quiet=True)[0]
                seen[p] = sig + [m["id"]]
                ok.append(m)
            except Fail as e:
                out("  FAIL %s: %s" % (os.path.basename(p), str(e).splitlines()[0]))
        save_json(SEEN, seen)
        out("  %s: %d ingested" % (brand, len(ok)))
        metas += ok
    transcribe.run_for([m for m in metas if m.get("has_audio")])
    _backlog(do_analyze)


def _backlog(do_analyze):
    """Anything in the catalog still without a shot log, including files a
    previous sync could not analyze (for example when a daily limit was hit)."""
    if not do_analyze:
        return
    todo = [m for m in media.all_clips() if not os.path.exists(
        os.path.join(media.clip_dir(m["id"]), "shots.json"))]
    if todo:
        out("%d files in the catalog have no shot log yet" % len(todo))
        analyze.run_for(todo)
