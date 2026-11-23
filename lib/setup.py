"""First-run setup and brand kits.

The tool (this repo) and a person's work (their workspace) are separate
folders. Setup creates the workspace, installs the skill for Claude Code,
and checks the machine. It is safe to run again.
"""

import os
import shutil
import subprocess

from .util import (BRANDS, CONFIG_DIR, ROOT, TEMPLATES, WORK, Fail, load_json,
                   out, run, save_json, slug)

SKILL_LINK = os.path.expanduser("~/.claude/skills/adstudio")
LAUNCHER = os.path.join(CONFIG_DIR, "adstudio")
WORK_IGNORE = """# derived files: all of this can be rebuilt from footage and timelines
media/
ads/*/*/previews/
ads/*/*/exports/
ads/*/*/versions/*.mp4
ads/*/*/preview.html
ads/*/*/render.json
ads/*/*/gfx/*/render-*.mov
ads/*/*/.claude-session
brands/*/index.html
ads/index.html
ads/*/index.html
ads/*/*/thumb.jpg
.DS_Store
"""
LESSONS = """# Lessons

How your ads should look, sound and be made. Claude adds a line here the
moment you state a preference, and changes the matching default so it sticks.
"""


def _link(target, link):
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.islink(link):
        os.unlink(link)
    elif os.path.exists(link):
        raise Fail("%s exists and is not a link; move it away and run setup again" % link)
    os.symlink(target, link)


def setup(workspace=None):
    cfg_p = os.path.join(CONFIG_DIR, "config.json")
    cfg = load_json(cfg_p, {}) or {}
    work = os.path.abspath(os.path.expanduser(workspace)) if workspace else WORK
    if workspace or "workspace" not in cfg:
        cfg["workspace"] = work
        save_json(cfg_p, cfg)
    for sub in ("brands", "ads", "library/sfx", "library/music", "docs"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)
    for name, text in ((".gitignore", WORK_IGNORE), ("docs/LESSONS.md", LESSONS)):
        p = os.path.join(work, name)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write(text)
    out("workspace: %s" % work)

    missing = [t for t in ("ffmpeg", "ffprobe", "node", "npm", "swift") if not shutil.which(t)]
    if missing:
        out("MISSING: %s" % ", ".join(missing))
        if "swift" in missing:
            out("  run: xcode-select --install   (wait for it to finish)")
        if set(missing) & set(("ffmpeg", "ffprobe", "node", "npm")):
            out("  run: brew install ffmpeg node   (no brew? see Install in README.md)")
        out("  then run ./adstudio setup again")
    if not os.path.exists("/Applications/Google Chrome.app"):
        out("MISSING: Google Chrome (https://www.google.com/chrome/), needed to draw text")
    if shutil.which("npm") and not os.path.isdir(os.path.join(ROOT, "node_modules", "playwright-core")):
        out("installing the page renderer (npm install)...")
        # npm ci installs exactly what package-lock.json says and never rewrites
        # it, so `git pull` keeps working for updates.
        r = subprocess.run(["npm", "ci", "--silent"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            out("  npm install failed: %s" % (r.stderr or r.stdout)[-300:])
    if shutil.which("swift"):
        from . import transcribe
        try:
            transcribe.build()
        except Fail as e:
            out("  could not build the transcription helper: %s" % str(e)[-300:])

    _link(os.path.join(ROOT, "skill"), SKILL_LINK)
    _link(os.path.join(ROOT, "adstudio"), LAUNCHER)
    out("skill installed for Claude Code: %s" % SKILL_LINK)
    out("command: %s" % LAUNCHER)
    out("")
    out("Next:")
    out("  1. open a new Claude Code chat and say: make an ad for <your-brand>")
    out("  2. optional, to tag shots by what is in them: copy a Gemini API key,")
    out("     then run: %s key gemini --paste" % LAUNCHER)


def brand_new(name):
    key = slug(name)
    d = os.path.join(BRANDS, key)
    if os.path.exists(d):
        raise Fail("brand '%s' already exists at %s" % (key, d))
    os.makedirs(os.path.join(d, "fonts"))
    for f in ("brand.json", "brand.css"):
        with open(os.path.join(TEMPLATES, "brand", f)) as src:
            text = src.read().replace("{{name}}", name)
        with open(os.path.join(d, f), "w") as dst:
            dst.write(text)
    out("created brand kit: %s" % d)
    out("  brand.css   colours and fonts")
    out("  brand.json  name, site, tagline, call to action, logo file")
    out("  fonts/      put font files here")
    return d


def brand_list():
    if not os.path.isdir(BRANDS):
        out("no brands yet (adstudio brand new <name>)")
        return
    for b in sorted(os.listdir(BRANDS)):
        j = load_json(os.path.join(BRANDS, b, "brand.json"))
        if j is not None:
            out("%-20s %-24s %s" % (b, j.get("name", ""), j.get("url", "")))
