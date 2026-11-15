"""Command dispatch. Each command is one short function."""

import argparse
import json
import os
import shutil
import sys
import time

from . import media
from .util import (ADS, BRANDS, CONFIG_DIR, MEDIA, ROOT, Fail, Timer, config,
                   load_json, out, read_key, rel, run, save_json)

HELP = """adstudio commands

  Footage
    watch add <brand> <folder>    remember a footage or assets folder (watch list, watch remove)
    sync [--dry-run]              find new files in watched folders; ingest, transcribe, analyze
    ingest <brand> <path...>      register footage, build proxies, transcribe
    clips [brand]                 list clips
    clip <id>                     one clip: details, shot log, transcript
    sheet <id> [--from s --to s]  contact sheet PNG to look at a clip
    frame <id> <t> [-o file]      full-quality still at time t
    transcribe [id...|--all]      Parakeet transcripts (local)
    analyze [id...|--all]         Gemini shot logs
    shots <id> <file.json>        import a hand-written shot log
    search <words...> [--brand b] find moments by shot log and speech

  Ads
    new <brand> <ad>              start an ad (timeline.json)
    preview <brand>/<ad>          fast draft render  [--aspect 9:16]
    render <brand>/<ad>           final MP4s         [--aspect all]
    xml <brand>/<ad>              Premiere Pro XML   [--aspect 9:16]
    static <brand>/<ad>           static ads from statics.json
    gfx <brand>/<ad> <name>       render a HyperFrames animation (alpha MOV)
    voice <brand>/<ad> [--force]  scratch VO for the timeline's "vo" lines (Runware,
                                  Fish Audio) and word timings for VO captions

  References (ads and images to model new work on)
    ref add <brand> <file|url> [--note "what I like"]   measure cuts, break it down
    ref list [brand]              all references
    ref show <id>                 the breakdown, cut times, contact sheet

  Versions and feedback
    serve [port]                  preview server (pages, feedback box, Redo button)
    snapshot <brand>/<ad> [--note ..]  keep the current draft as the next version
    history <brand>/<ad>          versions, what changed, feedback
    feedback <brand>/<ad> <n> "text"   add feedback from chat instead of the page
    wait <brand>/<ad>             block until the page sends feedback with Redo
    restore <brand>/<ad> <n>      make an old version the working edit again

  Library
    lib list [sfx|music]          what's in the sound library
    lib add <sfx|music> <file|url> --name n [--tags a,b] [--license text]

  Housekeeping
    setup [workspace-folder]      first run: workspace, skill, helpers
    where                         where the tool, your workspace and settings are
    brand new <name> | brand list brand kits
    key [gemini|runware] [--paste]  store your own API key (kept outside the repo)
    config [name value]           show or change your personal settings
    doctor                        check dependencies and keys
    timings [n]                   recent step timings
    prune                         clear the render cache
"""


def _ad_dir(ref):
    ref = ref.strip("/")
    if ref.startswith("ads/"):
        ref = ref[4:]
    d = os.path.join(ADS, ref)
    if not os.path.exists(os.path.join(d, "timeline.json")):
        raise Fail("no timeline at %s (run: adstudio new <brand> <ad>)" % rel(d))
    return d


def cmd_ingest(a):
    p = argparse.ArgumentParser(prog="adstudio ingest")
    p.add_argument("brand")
    p.add_argument("paths", nargs="+")
    p.add_argument("--no-transcribe", action="store_true")
    o = p.parse_args(a)
    if not os.path.isdir(os.path.join(BRANDS, o.brand)):
        raise Fail("unknown brand '%s'. See: adstudio brand list, or make one: "
                   "adstudio brand new %s" % (o.brand, o.brand))
    metas = media.ingest(o.paths, o.brand)
    if not o.no_transcribe:
        from . import transcribe
        transcribe.run_for([m for m in metas if m.get("has_audio")])


def cmd_clips(a):
    brand = a[0] if a else None
    rows = media.all_clips(brand)
    for m in rows:
        d = media.clip_dir(m["id"])
        flags = "".join([
            "T" if os.path.exists(os.path.join(d, "transcript.json")) else "-",
            "S" if os.path.exists(os.path.join(d, "shots.json")) else "-",
            "H" if m.get("hdr") else "-"])
        out("%-38s %-10s %7.1fs %4dx%-4d %s  %s" % (
            m["id"], m.get("brand", ""), m.get("duration", 0), m["width"],
            m["height"], flags, m["name"]))
    out("%d clips   (T transcript, S shot log, H HDR source)" % len(rows))


def cmd_clip(a):
    m = media.find(a[0])
    d = media.clip_dir(m["id"])
    out(json.dumps({k: m[k] for k in ("id", "brand", "src", "duration", "width",
                                      "height", "fps", "hdr", "has_audio")}, indent=1))
    shots = load_json(os.path.join(d, "shots.json"))
    if shots:
        out("\nSummary: %s" % shots.get("summary", ""))
        for s in shots.get("shots", []):
            out("  %7.2f-%7.2f  q%s  %s  [%s]" % (
                s["start"], s["end"], s.get("quality", "?"),
                s.get("description", ""), ", ".join(s.get("tags", []))))
    tr = load_json(os.path.join(d, "transcript.json"))
    if tr:
        out("\nTranscript (%d words):" % len(tr.get("words", [])))
        for seg in tr.get("sentences", []):
            out("  %7.2f-%7.2f  %s" % (seg["start"], seg["end"], seg["text"]))


def cmd_sheet(a):
    p = argparse.ArgumentParser(prog="adstudio sheet")
    p.add_argument("id")
    p.add_argument("--from", dest="start", type=float, default=0.0)
    p.add_argument("--to", dest="end", type=float)
    p.add_argument("--cols", type=int, default=5)
    p.add_argument("--rows", type=int, default=4)
    o = p.parse_args(a)
    m = media.find(o.id)
    dst = os.path.join(media.clip_dir(m["id"]), "sheet-%d-%d.png" % (
        o.start, o.end or m["duration"]))
    with Timer("sheet"):
        dst, times, step = media.sheet(m, dst, o.start, o.end, o.cols, o.rows)
    out(dst)
    out("tiles left to right, top to bottom, every %.2fs:" % step)
    for r in range(o.rows):
        out("  " + "  ".join("%7.2f" % t for t in times[r * o.cols:(r + 1) * o.cols]))


def cmd_frame(a):
    p = argparse.ArgumentParser(prog="adstudio frame")
    p.add_argument("id")
    p.add_argument("t", type=float)
    p.add_argument("-o", "--out")
    o = p.parse_args(a)
    m = media.find(o.id)
    dst = o.out or os.path.join(media.clip_dir(m["id"]), "frame-%.2f.png" % o.t)
    with Timer("frame"):
        media.frame(m, o.t, dst)
    out(dst)


def _ids_or_all(a, need):
    if "--all" in a or not a:
        kinds = ("video", "image") if need == "shots.json" else ("video",)
        return [m for m in media.all_clips() if m["kind"] in kinds
                and not os.path.exists(os.path.join(media.clip_dir(m["id"]), need))]
    return [media.find(x) for x in a if not x.startswith("--")]


def cmd_transcribe(a):
    from . import transcribe
    force = "--force" in a
    ms = _ids_or_all([x for x in a if x != "--force"], "transcript.json")
    transcribe.run_for([m for m in ms if m.get("has_audio")], force=force)


def cmd_analyze(a):
    from . import analyze
    p = argparse.ArgumentParser(prog="adstudio analyze")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--backend", choices=["auto", "gemini", "runware"])
    p.add_argument("--note", default="", help="context for the model")
    o = p.parse_args(a)
    ms = _ids_or_all(o.ids if o.ids else ["--all"], "shots.json")
    if o.force and o.ids:
        ms = [media.find(x) for x in o.ids]
    analyze.run_for(ms, backend=o.backend, note=o.note, force=o.force)


def cmd_shots(a):
    from . import analyze
    m = media.find(a[0])
    data = load_json(a[1])
    if not data:
        raise Fail("could not read JSON from %s" % a[1])
    analyze.save_shots(m, data, source="manual")
    out("saved shot log for %s (%d shots)" % (m["id"], len(data.get("shots", []))))


def cmd_search(a):
    from . import catalog
    p = argparse.ArgumentParser(prog="adstudio search")
    p.add_argument("words", nargs="+")
    p.add_argument("--brand")
    p.add_argument("-n", type=int, default=15)
    o = p.parse_args(a)
    catalog.search(o.words, o.brand, o.n)


def cmd_new(a):
    from . import timeline
    p = argparse.ArgumentParser(prog="adstudio new")
    p.add_argument("brand")
    p.add_argument("ad")
    o = p.parse_args(a)
    d = timeline.create(o.brand, o.ad)
    out("created %s" % rel(os.path.join(d, "timeline.json")))


def cmd_preview(a):
    from . import render
    p = argparse.ArgumentParser(prog="adstudio preview")
    p.add_argument("ad")
    p.add_argument("--aspect", default=None)
    o = p.parse_args(a)
    render.render_ad(_ad_dir(o.ad), mode="draft", aspects=o.aspect)


def cmd_render(a):
    from . import render
    p = argparse.ArgumentParser(prog="adstudio render")
    p.add_argument("ad")
    p.add_argument("--aspect", default="all")
    o = p.parse_args(a)
    render.render_ad(_ad_dir(o.ad), mode="final", aspects=o.aspect)


def cmd_watch(a):
    from . import sync
    if a and a[0] == "add" and len(a) == 3:
        sync.add(a[1], a[2])
    elif a and a[0] == "remove" and len(a) == 2:
        sync.remove(a[1])
    elif not a or a[0] == "list":
        sync.listing()
    else:
        raise Fail("usage: adstudio watch add <brand> <folder> | remove <folder> | list")


def cmd_sync(a):
    from . import sync
    sync.sync(dry_run="--dry-run" in a, do_analyze="--no-analyze" not in a)


def cmd_snapshot(a):
    from . import versions
    p = argparse.ArgumentParser(prog="adstudio snapshot")
    p.add_argument("ad")
    p.add_argument("--note", default="")
    o = p.parse_args(a)
    versions.snapshot(_ad_dir(o.ad), o.note)


def cmd_feedback(a):
    from . import versions
    if len(a) < 3:
        raise Fail('usage: adstudio feedback <brand>/<ad> <version> "text"')
    versions.add_feedback(_ad_dir(a[0]), int(a[1].lstrip("v")), " ".join(a[2:]),
                          redo="--note-only" not in a)
    out("feedback saved on v%s" % a[1].lstrip("v"))


def cmd_history(a):
    from . import versions
    d = _ad_dir(a[0])
    for v in versions.history(d)["versions"]:
        out("v%d  %s  %.1fs%s" % (v["n"], time.strftime("%b %d %H:%M", time.localtime(v["at"])),
                                   v["seconds"], "  " + v["note"] if v.get("note") else ""))
        if v.get("answers"):
            out("   answers: %s" % v["answers"])
        for c in v["changes"]:
            out("   - " + c)
        for fb in v.get("feedback", []):
            out("   feedback (%s): %s" % (fb["status"], fb["text"]))


def cmd_restore(a):
    from . import versions
    versions.restore(_ad_dir(a[0]), int(a[1].lstrip("v")))


def cmd_wait(a):
    from . import serve
    p = argparse.ArgumentParser(prog="adstudio wait")
    p.add_argument("ad")
    p.add_argument("--timeout", type=float)
    o = p.parse_args(a)
    serve.wait(_ad_dir(o.ad), o.timeout)


def cmd_serve(a):
    from . import serve
    serve.serve(a[0] if a else None)


def cmd_xml(a):
    from . import fcpxml
    p = argparse.ArgumentParser(prog="adstudio xml")
    p.add_argument("ad")
    p.add_argument("--aspect", default=None)
    o = p.parse_args(a)
    fcpxml.export(_ad_dir(o.ad), o.aspect)


def cmd_static(a):
    from . import static
    static.render(_ad_dir_static(a[0]))


def _ad_dir_static(ref):
    ref = ref.strip("/")
    if ref.startswith("ads/"):
        ref = ref[4:]
    d = os.path.join(ADS, ref)
    if not os.path.exists(os.path.join(d, "statics.json")):
        raise Fail("no statics.json in %s" % rel(d))
    return d


def cmd_gfx(a):
    from . import gfx
    if len(a) < 2:
        raise Fail("usage: adstudio gfx <brand>/<ad> <name>")
    ref = a[0].strip("/")
    gfx.render(os.path.join(ADS, ref[4:] if ref.startswith("ads/") else ref), a[1])


def cmd_ref(a):
    from . import refs
    if not a or a[0] == "list":
        refs.listing(a[1] if len(a) > 1 else None)
    elif a[0] == "show" and len(a) > 1:
        refs.show(a[1])
    elif a[0] == "add":
        p = argparse.ArgumentParser(prog="adstudio ref add")
        p.add_argument("brand")
        p.add_argument("src", help="video or image file, or a video URL")
        p.add_argument("--note", default="", help="what you like about it")
        o = p.parse_args(a[1:])
        refs.add(o.brand, o.src, o.note)
    else:
        raise Fail("usage: adstudio ref add <brand> <file|url> [--note ..] | list | show <id>")


def cmd_lib(a):
    from . import library
    if not a or a[0] == "list":
        library.show(a[1] if len(a) > 1 else None)
        return
    if a[0] == "add":
        p = argparse.ArgumentParser(prog="adstudio lib add")
        p.add_argument("kind", choices=["sfx", "music"])
        p.add_argument("src")
        p.add_argument("--name", required=True)
        p.add_argument("--tags", default="")
        p.add_argument("--license", default="")
        p.add_argument("--prompt", default="")
        o = p.parse_args(a[1:])
        library.add(o.kind, o.src, o.name, o.tags, o.license, o.prompt)
        return
    raise Fail("usage: adstudio lib list|add")


def cmd_voice(a):
    from . import voice
    p = argparse.ArgumentParser(prog="adstudio voice")
    p.add_argument("ad")
    p.add_argument("--force", action="store_true", help="remake every scratch line")
    o = p.parse_args(a)
    voice.build(_ad_dir(o.ad), force=o.force)


def cmd_doctor(a):
    from . import gfx, transcribe
    ok = True

    def row(name, good, note=""):
        out("  %-4s %-22s %s" % ("ok" if good else "MISS", name, note))
        return good

    for tool in ("ffmpeg", "ffprobe", "node", "swift"):
        ok &= row(tool, bool(shutil.which(tool)), shutil.which(tool) or "")
    r = run(["ffmpeg", "-hide_banner", "-filters"], check=False).stdout
    ok &= row("ffmpeg scale_vt", " scale_vt " in r, "hardware HDR to SDR")
    ok &= row("ffmpeg videotoolbox", "h264_videotoolbox" in
              run(["ffmpeg", "-hide_banner", "-encoders"], check=False).stdout)
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ok &= row("Google Chrome", os.path.exists(chrome), "text overlays, statics")
    ok &= row("playwright-core", os.path.isdir(os.path.join(ROOT, "node_modules", "playwright-core")))
    row("parakeet helper", os.path.exists(transcribe.BIN),
        "built" if os.path.exists(transcribe.BIN) else "builds on first transcribe")
    row("parakeet model", os.path.isdir(transcribe.MODEL_DIR),
        "present" if os.path.isdir(transcribe.MODEL_DIR) else "downloads on first transcribe")
    hf = gfx.cli_path()
    row("HyperFrames CLI", bool(hf), hf or "install the HyperFrames app")
    row("gemini key", bool(read_key("gemini")), "set with: adstudio key gemini")
    row("runware key", bool(read_key("runware")), "for scratch VO and Runware analysis: adstudio key runware")
    out("config: %s" % json.dumps(config()))
    return 0 if ok else 1


def cmd_setup(a):
    from . import setup
    setup.setup(a[0] if a else None)


def cmd_brand(a):
    from . import setup
    if a and a[0] == "new" and len(a) > 1:
        setup.brand_new(" ".join(a[1:]))
    else:
        setup.brand_list()


def cmd_where(a):
    from .util import WORK
    out("tool:      %s" % ROOT)
    out("workspace: %s   (brands, ads, library, media, docs/LESSONS.md)" % WORK)
    out("settings:  %s" % CONFIG_DIR)


def cmd_key(a):
    """Store an API key without it ever appearing in chat or shell history."""
    import getpass
    from .util import KEY_ENV, key_path, write_key
    names = sorted(KEY_ENV)
    if not a:
        for n in names:
            src = ("env %s" % KEY_ENV[n] if os.environ.get(KEY_ENV[n])
                   else key_path(n) if read_key(n) else "not set")
            out("  %-8s %s" % (n, src))
        out("set one with: adstudio key <%s> [--paste]" % "|".join(names))
        return
    name = a[0]
    if name not in KEY_ENV:
        raise Fail("unknown key '%s' (have: %s)" % (name, ", ".join(names)))
    if "--paste" in a:
        value = run(["pbpaste"]).stdout.strip()
        run(["pbcopy"], stdin="")            # clear the clipboard afterwards
    elif sys.stdin.isatty():
        value = getpass.getpass("Paste the %s API key (hidden), then Enter: " % name).strip()
    else:
        value = sys.stdin.read().strip()
    if not value or len(value) < 16 or " " in value or "\n" in value:
        raise Fail("that does not look like an API key; nothing saved")
    p = write_key(name, value)
    out("saved %s key to %s (owner-only, %d characters)" % (name, p, len(value)))
    if name == "gemini":
        from . import analyze
        out("  " + analyze.check_gemini())


def cmd_config(a):
    """Per-user settings in ~/.config/adstudio/config.json."""
    p = os.path.join(CONFIG_DIR, "config.json")
    if len(a) >= 2:
        user = load_json(p, {}) or {}
        v = a[1]
        try:
            v = json.loads(v)
        except ValueError:
            pass
        user[a[0]] = v
        save_json(p, user)
        out("set %s = %s in %s" % (a[0], json.dumps(v), p))
        return
    out(json.dumps(config(), indent=2))
    out("user settings file: %s" % p)


def cmd_timings(a):
    n = int(a[0]) if a else 25
    p = os.path.join(MEDIA, "timings.jsonl")
    if not os.path.exists(p):
        out("no timings yet")
        return
    with open(p) as f:
        rows = [json.loads(x) for x in f.readlines()[-n:]]
    for r in rows:
        out("%s  %-30s %7.2fs" % (time.strftime("%m-%d %H:%M", time.localtime(r["t"])),
                                  r["step"], r["secs"]))


def cmd_prune(a):
    from .util import RCACHE
    n = 0
    if os.path.isdir(RCACHE):
        for f in os.listdir(RCACHE):
            os.unlink(os.path.join(RCACHE, f))
            n += 1
    out("removed %d cached render files" % n)


COMMANDS = {"voice": cmd_voice, "ingest": cmd_ingest, "clips": cmd_clips, "clip": cmd_clip,
            "sheet": cmd_sheet, "frame": cmd_frame,
            "transcribe": cmd_transcribe, "analyze": cmd_analyze,
            "shots": cmd_shots, "search": cmd_search, "new": cmd_new,
            "preview": cmd_preview, "render": cmd_render, "xml": cmd_xml,
            "static": cmd_static, "gfx": cmd_gfx, "lib": cmd_lib, "ref": cmd_ref,
            "doctor": cmd_doctor, "timings": cmd_timings, "prune": cmd_prune,
            "key": cmd_key, "config": cmd_config, "snapshot": cmd_snapshot,
            "feedback": cmd_feedback, "history": cmd_history, "restore": cmd_restore,
            "wait": cmd_wait, "serve": cmd_serve, "setup": cmd_setup,
            "brand": cmd_brand, "where": cmd_where, "watch": cmd_watch, "sync": cmd_sync}


def main(argv):
    if not argv or argv[0] in ("help", "-h", "--help"):
        out(HELP)
        return 0
    fn = COMMANDS.get(argv[0])
    if not fn:
        out("unknown command '%s'\n" % argv[0])
        out(HELP)
        return 2
    t0 = time.time()
    try:
        code = fn(argv[1:]) or 0
    except Fail as e:
        sys.stderr.write("adstudio: %s\n" % e)
        return 1
    out("done in %.2fs" % (time.time() - t0))
    return code
