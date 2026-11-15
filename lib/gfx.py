"""HyperFrames animations, used sparingly.

An animation is a small HyperFrames project in ads/<brand>/<ad>/gfx/<name>/.
It renders once to a ProRes 4444 MOV with transparency and is then just
another overlay. The render is skipped while the project is unchanged.
Authoring rules live in the HyperFrames skill, not here.
"""

import glob
import os

from .util import Fail, Timer, load_json, out, rel, run, save_json, sha

RUNTIMES = os.path.expanduser("~/Library/Application Support/HyperFrames/runtimes")
SKILL = os.path.expanduser("~/Library/Application Support/HyperFrames/guides/"
                           "studio-plugin/skills/hyperframes/SKILL.md")
PRESET = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}


def cli_path():
    hits = sorted(glob.glob(os.path.join(RUNTIMES, "cli-*", "node_modules",
                                         "hyperframes", "bin", "hyperframes.mjs")),
                  key=os.path.getmtime)
    return hits[-1] if hits else ""


def hf(args, cwd=None, check=True):
    cli = cli_path()
    if not cli:
        raise Fail("HyperFrames is not installed (expected under %s)" % RUNTIMES)
    import subprocess
    r = subprocess.run(["node", cli] + args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise Fail("hyperframes %s failed:\n%s" % (args[0], (r.stderr or r.stdout)[-1500:]))
    return r


def _tree_sig(d):
    sig = []
    for base, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ("renders", "node_modules", ".hyperframes")]
        for n in sorted(names):
            if n.startswith("render-") or n == ".adstudio.json":
                continue
            p = os.path.join(base, n)
            sig.append((os.path.relpath(p, d), os.path.getsize(p), int(os.path.getmtime(p))))
    return sha(sig)


def render(ad_dir, name, aspect="9:16", quality="looks"):
    if aspect not in PRESET:
        raise Fail("HyperFrames presets cover 9:16, 16:9 and 1:1, not %s" % aspect)
    d = os.path.join(ad_dir, "gfx", name)
    if not os.path.exists(os.path.join(d, "index.html")):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        with Timer("hyperframes init"):
            hf(["init", name, "--example", "blank", "--non-interactive",
                "--skip-skills", "--resolution", PRESET[aspect]], cwd=os.path.dirname(d))
        out("created %s" % rel(d))
        out("author index.html following %s, then run this command again" % SKILL)
        return None
    dst = os.path.join(d, "render-%s.mov" % aspect.replace(":", "x"))
    state_p = os.path.join(d, ".adstudio.json")
    state = load_json(state_p, {}) or {}
    sig = _tree_sig(d)
    if os.path.exists(dst) and state.get(aspect) == sig:
        out("gfx '%s' unchanged, using %s" % (name, rel(dst)))
        return dst
    with Timer("hyperframes render %s" % name):
        hf(["render", "--format", "mov", "--quality", quality,
            "--resolution", PRESET[aspect], "--output", dst], cwd=d)
    state[aspect] = _tree_sig(d)
    save_json(state_p, state)
    out(rel(dst))
    return dst
