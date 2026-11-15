"""A web page per brand: its rules, its kit, and every asset with its id.

Written to brands/<brand>/index.html in the workspace and served by
`adstudio serve`. The ids and variable names shown are the exact keys used
in timelines, so the page doubles as a reference while editing.
"""

import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import media
from .util import ADS, BRANDS, WORK, Fail, Timer, config, load_json, out, run

CSS = """
:root{--bg:#f4f1ec;--card:#fff;--ink:#16181b;--mute:#6b7076;--line:#e2ddd5;--accent:#c8501e}
@media (prefers-color-scheme:dark){:root{--bg:#131517;--card:#1c1f22;--ink:#e8e6e1;--mute:#8e949a;--line:#2b2f33;--accent:#f0794a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.55 ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
.wrap{max-width:1180px;margin:0 auto;padding:22px 24px 80px}
h1{font-size:18px;margin:0;font-weight:650}
.sub{color:var(--mute);font-size:13px;margin-top:2px}
nav{margin:14px 0 6px;display:flex;gap:14px;flex-wrap:wrap;font-size:13px}
nav a{color:var(--mute)}
h2{font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--mute);margin:34px 0 10px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.kv{display:grid;grid-template-columns:130px 1fr;gap:6px 14px}
.kv dt{color:var(--mute)}.kv dd{margin:0;overflow-wrap:anywhere}
ul{margin:0;padding-left:18px}li{margin:4px 0}
code,.key{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace}
.key{cursor:pointer;border-radius:5px;padding:1px 5px;background:color-mix(in srgb,var(--ink) 8%,transparent)}
.key:hover{background:color-mix(in srgb,var(--accent) 22%,transparent)}
.sw{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.sw div{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card)}
.sw i{display:block;height:64px}
.sw p{margin:0;padding:8px 10px;font-size:13px}
.fonts{display:grid;gap:12px}
.fonts .f{font-size:38px;line-height:1.1}
.logos{display:flex;gap:16px;flex-wrap:wrap}
.logos figure{margin:0;padding:16px;border:1px solid var(--line);border-radius:12px;background:#fff}
.logos figure.dark{background:#16181b}
.logos img{height:70px;display:block}
.logos figcaption{font-size:12px;color:#888;margin-top:8px}
.styles{display:flex;gap:14px;flex-wrap:wrap;align-items:center;background:#5b6166;padding:22px;border-radius:14px}
.styles .ov{position:static;display:block;left:auto;right:auto}
.styles .t{font-size:calc(var(--fs) * .42)!important}.styles .style-caption .t{-webkit-text-stroke-width:5px}
.styles small{display:block;color:#ddd;font:12px ui-monospace,monospace;margin-top:6px;text-align:center}
.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input[type=search]{font:inherit;padding:8px 12px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:inherit;min-width:260px}
.chip{font-size:12.5px;padding:4px 11px;border-radius:99px;border:1px solid var(--line);background:none;color:var(--mute);cursor:pointer}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}
.a{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.a .th{aspect-ratio:1/1;background:#000 center/contain no-repeat;position:relative}
.a video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
.a .dur{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.7);color:#fff;font-size:11.5px;padding:1px 6px;border-radius:5px}
.a .b{padding:9px 11px 11px;font-size:13px;display:flex;flex-direction:column;gap:5px}
.a .s{color:var(--mute);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.a .m{color:var(--mute);font-size:12px}
.tags{display:flex;gap:4px;flex-wrap:wrap}
.tags span{font-size:11px;padding:1px 7px;border-radius:99px;background:color-mix(in srgb,var(--ink) 7%,transparent)}
.none{color:var(--mute)}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:8px 16px;border-radius:99px;font-size:13px;opacity:0;transition:opacity .2s;pointer-events:none}
"""

JS = """
const toast = document.getElementById('toast');
document.addEventListener('click', e => {
  const k = e.target.closest('.key'); if (!k) return;
  navigator.clipboard.writeText(k.dataset.k || k.textContent).then(() => {
    toast.textContent = 'Copied ' + (k.dataset.k || k.textContent); toast.style.opacity = 1;
    setTimeout(() => toast.style.opacity = 0, 1200);
  });
});
const q = document.getElementById('q'), cards = [...document.querySelectorAll('.a')];
let kind = 'all';
function apply() {
  const words = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
  let n = 0;
  cards.forEach(c => {
    const ok = (kind === 'all' || c.dataset.kind === kind) && words.every(w => c.dataset.text.includes(w));
    c.style.display = ok ? '' : 'none'; if (ok) n++;
  });
  document.getElementById('count').textContent = n + ' shown';
}
if (q) { q.addEventListener('input', apply);
  document.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => {
    kind = b.dataset.kind; document.querySelectorAll('.chip').forEach(x => x.classList.toggle('on', x === b)); apply(); }));
  apply(); }
cards.forEach(c => { const th = c.querySelector('.th'); if (!c.dataset.video) return;
  th.addEventListener('mouseenter', () => { if (th.querySelector('video')) return;
    const v = document.createElement('video'); v.src = c.dataset.video; v.muted = true; v.loop = true; v.playsInline = true;
    th.prepend(v); v.play().catch(() => {}); });
  th.addEventListener('mouseleave', () => { const v = th.querySelector('video'); if (v) v.remove(); });
});
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _key(k, label=None):
    return "<span class='key' data-k='%s' title='Click to copy'>%s</span>" % (_e(k), _e(label or k))


def thumb(m):
    d = media.clip_dir(m["id"])
    dst = os.path.join(d, "thumb.jpg")
    if os.path.exists(dst):
        return dst
    try:
        if m["kind"] == "image":
            run(["ffmpeg", "-v", "error", "-y", "-i", m["src"], "-vf", "scale=420:-2",
                 "-frames:v", "1", "-q:v", "4", dst])
        else:
            run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % min(1.0, m["duration"] / 2),
                 "-i", os.path.join(d, "proxy.mp4"), "-vf", "scale=420:-2",
                 "-frames:v", "1", "-q:v", "4", dst])
    except Fail:
        return None
    return dst


def _colors(css):
    return re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;(?:\s*/\*\s*(.*?)\s*\*/)?", css)


def _fonts(css):
    return re.findall(r"--(font-[\w-]+)\s*:\s*([^;]+);", css)


def write(brand):
    bdir = os.path.join(BRANDS, brand)
    b = load_json(os.path.join(bdir, "brand.json"))
    if b is None:
        raise Fail("unknown brand '%s'" % brand)
    try:
        css = open(os.path.join(bdir, "brand.css")).read()
    except IOError:
        css = ""
    clips = media.all_clips(brand, refs=True)
    with Timer("thumbnails", quiet=True):
        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(thumb, clips))

    P = []
    P.append("<h2 id='rules'>Rules and notes</h2><div class='card'>")
    rules = b.get("rules") or []
    if rules:
        P.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _e(r) for r in rules))
    if b.get("notes"):
        P.append("<p class='none' style='margin:%s 0 0'>%s</p>" % ("10px" if rules else "0", _e(b["notes"])))
    if not rules and not b.get("notes"):
        P.append("<span class='none'>No rules yet. Tell Claude a rule for this brand and it is saved here.</span>")
    P.append("</div>")

    P.append("<h2 id='kit'>Brand kit</h2><div class='card'><dl class='kv'>")
    for k in ("name", "url", "tagline", "cta", "logo"):
        P.append("<dt>%s</dt><dd>%s</dd>" % (k, _e(b.get(k)) or "<span class='none'>not set</span>"))
    P.append("<dt>brand key</dt><dd>%s</dd></dl></div>" % _key(brand))

    cols = _colors(css)
    if cols:
        P.append("<h2>Colors</h2><div class='sw'>%s</div>" % "".join(
            "<div><i style='background:%s'></i><p>%s<br>%s%s</p></div>" % (
                hx, _key(name), _key(hx), "<br><span class='none'>%s</span>" % _e(note) if note else "")
            for name, hx, note in cols))
    fonts = _fonts(css)
    if fonts:
        P.append("<h2>Fonts</h2><div class='card fonts'>%s</div>" % "".join(
            "<div><div class='f' style='font-family:var(--%s)'>%s</div>"
            "<span class='none'>%s &middot; %s</span></div>" % (
                n, _e(b.get("tagline") or b.get("name") or "The quick brown fox"),
                _key("--" + n), _e(v.strip())) for n, v in fonts))
    logos = [f for f in sorted(os.listdir(bdir)) if f.lower().endswith((".svg", ".png", ".jpg", ".webp"))]
    if logos:
        P.append("<h2>Logos</h2><div class='logos'>%s</div>" % "".join(
            "<figure class='%s'><img src='%s' alt=''><figcaption>%s</figcaption></figure>" % (
                cls, _e(f), _key("brands/%s/%s" % (brand, f), f))
            for f in logos for cls in ("", "dark")))
    styles = ["hook", "caption", "title", "label", "cta", "hand"]
    P.append("<h2>Text styles</h2><div class='styles'>%s</div>" % "".join(
        "<div><div class='ov style-%s'><span class='t'>%s</span></div><small>%s</small></div>"
        % (s, "Sample <em>text</em>", s) for s in styles))

    folders = b.get("folders") or []
    P.append("<h2 id='folders'>Footage and asset folders</h2><div class='card'>")
    if folders:
        P.append("<ul>%s</ul><p class='none' style='margin:10px 0 0'>Scanned only when you ask "
                 "(<code>adstudio sync %s</code>).</p>" % (
                     "".join("<li>%s%s</li>" % (_e(f), "" if os.path.isdir(os.path.expanduser(f))
                                                else " <span class='none'>(not found)</span>")
                             for f in folders), _e(brand)))
    else:
        P.append("<span class='none'>None yet. <code>adstudio watch add %s &lt;folder&gt;</code></span>" % _e(brand))
    P.append("</div>")

    ads_dir = os.path.join(ADS, brand)
    ads = sorted(a for a in (os.listdir(ads_dir) if os.path.isdir(ads_dir) else [])
                 if os.path.exists(os.path.join(ads_dir, a, "timeline.json")))
    P.append("<h2 id='ads'>Ads</h2><div class='card'>%s</div>" % (
        "<ul>%s</ul>" % "".join(
            "<li><a href='/ads/%s/%s/preview.html'>%s</a> %s</li>" % (
                _e(brand), _e(a), _e(a), _key("%s/%s" % (brand, a))) for a in ads)
        if ads else "<span class='none'>No ads yet.</span>"))

    cards, counts = [], {"video": 0, "image": 0, "ref": 0}
    for m in sorted(clips, key=lambda x: x["id"]):
        d = media.clip_dir(m["id"])
        shots = load_json(os.path.join(d, "shots.json")) or {}
        tr = load_json(os.path.join(d, "transcript.json")) or {}
        kind = "ref" if m.get("ref") else m["kind"]
        counts[kind] += 1
        tags = []
        for s in shots.get("shots", []):
            for t in s.get("tags", []):
                if t not in tags:
                    tags.append(t)
        summary = shots.get("summary") or ""
        said = tr.get("text") or ""
        text = " ".join([m["id"], m["name"], summary, said, " ".join(tags)]).lower()
        has_thumb = os.path.exists(os.path.join(d, "thumb.jpg"))
        vid = "/media/clips/%s/proxy.mp4" % m["id"] if m["kind"] == "video" else ""
        meta = "%dx%d" % (m["width"], m["height"])
        if m["kind"] == "video":
            meta += " &middot; %.4gfps%s" % (m["fps"], " &middot; HDR source" if m.get("hdr") else "")
        if not shots:
            meta += " &middot; not analyzed"
        cards.append(
            "<div class='a' data-kind='%s' data-text='%s' data-video='%s'>"
            "<div class='th' style='%s'>%s</div><div class='b'>%s"
            "<div class='s'>%s</div>%s<div class='m'>%s</div>"
            "<div class='tags'>%s</div></div></div>" % (
                kind, _e(text), vid,
                "background-image:url(/media/clips/%s/thumb.jpg)" % m["id"] if has_thumb else "",
                "<span class='dur'>%.1fs</span>" % m["duration"] if m["kind"] == "video" else "",
                _key(m["id"]), _e(summary) or "<span class='none'>No description yet</span>",
                "<div class='s'>&ldquo;%s&rdquo;</div>" % _e(said) if said else "",
                meta, "".join("<span>%s</span>" % _e(t) for t in tags[:8])))
    P.append("<h2 id='assets'>Assets</h2>")
    if cards:
        P.append("<div class='tools'><input type='search' id='q' placeholder='Search ids, descriptions, speech, tags'>"
                 "<button class='chip on' data-kind='all'>All %d</button>"
                 "<button class='chip' data-kind='video'>Video %d</button>"
                 "<button class='chip' data-kind='image'>Images %d</button>"
                 "<button class='chip' data-kind='ref'>References %d</button>"
                 "<span class='none' id='count'></span></div><div class='grid'>%s</div>" % (
                     len(cards), counts["video"], counts["image"], counts["ref"], "".join(cards)))
    else:
        P.append("<div class='card none'>Nothing ingested yet. Add a folder, then run "
                 "<code>adstudio sync %s</code>.</div>" % _e(brand))

    others = [x for x in sorted(os.listdir(BRANDS))
              if x != brand and os.path.exists(os.path.join(BRANDS, x, "brand.json"))]
    page = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s &middot; adstudio brand</title>"
            "<link rel='stylesheet' href='brand.css'>"
            "<link rel='stylesheet' href='/tool/overlay.css'>"
            "<style>html,body{height:auto;overflow:auto}%s</style></head><body><div class='wrap'>"
            "<h1>%s</h1><div class='sub'>%s &middot; updated %s &middot; click any key to copy it</div>"
            "<nav><a href='#rules'>Rules</a><a href='#kit'>Kit</a><a href='#folders'>Folders</a>"
            "<a href='#ads'>Ads</a><a href='#assets'>Assets</a>%s</nav>%s</div>"
            "<div id='toast'></div><script>%s</script></body></html>") % (
        _e(b.get("name", brand)), CSS, _e(b.get("name", brand)), _e(b.get("url", "")),
        time.strftime("%b %d, %H:%M"),
        "".join("<a href='/brands/%s/index.html'>%s &rarr;</a>" % (_e(x), _e(x)) for x in others),
        "".join(P), JS)
    dst = os.path.join(bdir, "index.html")
    with open(dst, "w") as f:
        f.write(page)
    return "http://localhost:%s/brands/%s/index.html" % (config().get("preview_port", 8787), brand)
