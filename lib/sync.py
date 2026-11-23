"""Watched folders: scan for new footage and assets, then process only those.

  adstudio watch add <brand> <folder>     add a folder to a brand (saved in its brand.json)
  adstudio sync [brand]                   ingest, transcribe and analyze what is new
  adstudio sync [brand] --dry-run         only say what is new
Sync runs only when asked; nothing scans in the background.

"New" is decided from path, size and modified time, which costs nothing even
on a cloud drive. A file that was merely renamed or moved is recognised by
its content when it is ingested, so it is not analyzed twice.
"""

import os
import time

from . import analyze, media, transcribe
from .util import (IMAGE_EXT, MEDIA, VIDEO_EXT, WORK, Fail, Timer, load_json, out,
                   read_key, save_json)

SEEN = os.path.join(MEDIA, "seen.json")
LEGACY = os.path.join(WORK, "sources.json")


def _brand_file(brand):
    from .util import BRANDS
    return os.path.join(BRANDS, brand, "brand.json")


def _brands():
    from .util import BRANDS
    if not os.path.isdir(BRANDS):
        return []
    return sorted(b for b in os.listdir(BRANDS) if os.path.exists(_brand_file(b)))


def _migrate():
    """Folders used to live in one workspace file; they belong to each brand."""
    rows = load_json(LEGACY)
    if not rows:
        return
    for r in rows:
        j = load_json(_brand_file(r["brand"]))
        if j is not None and r["path"] not in j.setdefault("folders", []):
            j["folders"].append(r["path"])
            save_json(_brand_file(r["brand"]), j)
    os.unlink(LEGACY)


def sources(brand=None):
    """Each brand keeps its own list of footage and asset folders in its
    brand.json, so a project's sources travel with the project."""
    _migrate()
    rows = []
    for b in _brands():
        if brand and b != brand:
            continue
        for p in (load_json(_brand_file(b)) or {}).get("folders", []):
            rows.append({"brand": b, "path": os.path.expanduser(p)})
    return rows


def add(brand, folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        raise Fail("not a folder: %s" % folder)
    j = load_json(_brand_file(brand))
    if j is None:
        raise Fail("unknown brand '%s' (adstudio brand list)" % brand)
    if folder in j.setdefault("folders", []):
        raise Fail("%s already has %s" % (brand, folder))
    j["folders"].append(folder)
    save_json(_brand_file(brand), j)
    out("%s now includes %s" % (brand, folder))
    out("nothing is scanned until you ask: adstudio sync %s" % brand)


def remove(brand, folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    j = load_json(_brand_file(brand)) or {}
    if folder not in j.get("folders", []):
        raise Fail("%s does not have %s" % (brand, folder))
    j["folders"].remove(folder)
    save_json(_brand_file(brand), j)
    out("removed %s from %s (its clips stay in the catalog)" % (folder, brand))


def listing(brand=None):
    rows = sources(brand)
    for r in rows:
        ok = "" if os.path.isdir(r["path"]) else "   (folder not found)"
        out("%-14s %s%s" % (r["brand"], r["path"], ok))
    out("%d folders" % len(rows))


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


def scan(brand=None):
    """Returns {brand: [(path, sig)]} of files not processed before."""
    seen = load_json(SEEN, {}) or {}
    new, missing = {}, []
    for r in sources(brand):
        if not os.path.isdir(r["path"]):
            missing.append(r["path"])
            continue
        for p, sig in _walk(r["path"]):
            if (seen.get(p) or [])[:2] != sig:
                new.setdefault(r["brand"], []).append((p, sig))
    return new, missing


def sync(brand=None, dry_run=False, do_analyze=True):
    """Runs only when asked. Nothing watches folders in the background."""
    if brand and brand not in _brands():
        raise Fail("unknown brand '%s' (adstudio brand list)" % brand)
    if not sources(brand):
        raise Fail("no folders yet. Add one: adstudio watch add <brand> <folder>")
    with Timer("scan", quiet=True) as t:
        new, missing = scan(brand)
    for m in missing:
        out("  skipped, folder not found: %s" % m)
    total = sum(len(v) for v in new.values())
    out("%d new files in %d folders (scan %.2fs)" % (total, len(sources(brand)), t.secs))
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
        _backlog(do_analyze, brand)
        _pages(brand)
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
    _backlog(do_analyze, brand)
    _pages(brand)


def _pages(brand):
    from . import brandpage
    for b in ([brand] if brand else _brands()):
        brandpage.write(b)


def _backlog(do_analyze, brand=None):
    """Anything in the catalog still without a shot log, including files a
    previous sync could not analyze (for example when a daily limit was hit)."""
    if not do_analyze:
        return
    todo = [m for m in media.all_clips(brand) if not os.path.exists(
        os.path.join(media.clip_dir(m["id"]), "shots.json"))]
    if todo:
        out("%d files in the catalog have no shot log yet" % len(todo))
        if not read_key("gemini"):
            # The key is optional: transcripts and search on speech still work.
            out("  no Gemini key, so shots are not tagged (optional: adstudio key gemini)")
            return
        analyze.run_for(todo)
