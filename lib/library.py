"""Sound library: SFX and music, each with a small index entry.

Every entry records where the sound came from and its licence note, so
nothing ends up in a paid ad without a known source.
"""

import os
import shutil
import time
import urllib.request

from . import probe
from .util import AUDIO_EXT, LIBRARY, Fail, load_json, out, rel, save_json, slug


def _index(kind):
    return os.path.join(LIBRARY, kind, "index.json")


def entries(kind):
    return load_json(_index(kind), []) or []


def add(kind, src, name, tags="", license_note="", prompt=""):
    d = os.path.join(LIBRARY, kind)
    os.makedirs(d, exist_ok=True)
    is_url = src.startswith(("http://", "https://"))
    ext = os.path.splitext(src.split("?")[0])[1].lower()
    if ext not in AUDIO_EXT:
        ext = ".mp3"
    dst = os.path.join(d, slug(name, 50) + ext)
    if os.path.exists(dst):
        raise Fail("%s already exists; pick another --name" % rel(dst))
    if is_url:
        req = urllib.request.Request(src, headers={"User-Agent": "adstudio"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
            shutil.copyfileobj(r, f)
    else:
        src = os.path.expanduser(src)
        if not os.path.exists(src):
            raise Fail("not found: %s" % src)
        shutil.copyfile(src, dst)
    try:
        dur = round(probe.audio_duration(dst), 2)
    except Fail:
        os.unlink(dst)
        raise Fail("that file is not readable audio")
    rows = entries(kind)
    rows.append({"name": slug(name, 50), "file": rel(dst), "seconds": dur,
                 "tags": [t.strip().lower() for t in tags.split(",") if t.strip()],
                 "license": license_note or "unknown: check before using in a paid ad",
                 "prompt": prompt, "source": src if is_url else "local file",
                 "added": time.strftime("%Y-%m-%d")})
    save_json(_index(kind), rows)
    out("added %s (%.2fs)" % (rel(dst), dur))
    return dst


def show(kind=None):
    for k in ([kind] if kind else ["sfx", "music"]):
        rows = entries(k)
        out("%s (%d)" % (k, len(rows)))
        for r in rows:
            out("  %-34s %6.2fs  [%s]  %s" % (r["file"], r["seconds"],
                                              ", ".join(r["tags"]), r["license"][:50]))
