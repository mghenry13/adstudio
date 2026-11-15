"""The two index pages above an ad:

  /ads/index.html            every project (brand)
  /ads/<brand>/index.html    one project: its ads, with the latest frame,
                             version count and how many comments are waiting

Together with the ad page and the brand-kit page they give one path:
Projects > Project > Ad. Rewritten whenever an ad page is rewritten.
"""

import html
import os
import time

from . import media, versions
from .util import ADS, BRANDS, Fail, load_json, run

CSS = """
:root{--bg:#fafaf9;--panel:#fff;--ink:#18181b;--mute:#71717a;--faint:#a1a1aa;--line:#e7e5e4;--hover:#f4f4f5;--accent:#e4572e;--cta:#16a34a}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e10;--panel:#161618;--ink:#f4f4f5;--mute:#a1a1aa;--faint:#63636b;--line:#27272b;--hover:#1e1e22;--accent:#ff7a50;--cta:#22c55e}}
*{box-sizing:border-box}
html{-webkit-font-smoothing:antialiased}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.6 ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
a{color:inherit;text-decoration:none}
.wrap{max-width:1180px;margin:0 auto;padding:22px 28px 90px}
@media (max-width:780px){.wrap{padding-left:16px;padding-right:16px}}
.crumbs{font-size:12.5px;color:var(--mute);display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.crumbs a{border-bottom:1px solid var(--line)}.crumbs a:hover{color:var(--ink)}
.crumbs b{color:var(--ink);font-weight:600}
.crumbs i{font-style:normal;color:var(--faint)}
h1{font-size:18px;margin:18px 0 2px;font-weight:600}
.sub{color:var(--mute);font-size:12.5px}
.tools{display:flex;gap:16px;margin-top:10px;font-size:12.5px;color:var(--mute);flex-wrap:wrap}
.tools a{border-bottom:1px solid var(--line)}.tools a:hover{color:var(--ink)}
h2{font-size:12.5px;color:var(--mute);font-weight:400;margin:30px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}
.card{display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;transition:border-color .12s,transform .12s}
.card:hover{border-color:var(--mute);transform:translateY(-1px)}
.th{aspect-ratio:4/5;background:#000 center/cover no-repeat;position:relative}
.th.none{display:flex;align-items:center;justify-content:center;color:var(--faint);background:var(--hover)}
.pill{position:absolute;top:8px;left:8px;font-size:11.5px;padding:2px 8px;border-radius:99px;background:var(--accent);color:#fff}
.pill.v{left:auto;right:8px;background:rgba(0,0,0,.65)}
.b{padding:11px 13px 13px;display:flex;flex-direction:column;gap:3px}
.b b{font-weight:600}
.b .n{color:var(--mute);font-size:12.5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.b .m{color:var(--faint);font-size:12px}
.proj .th{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;background-size:cover}
.proj .th img{max-width:46%;max-height:60%}
.proj .th.plain{background:var(--hover)}
.empty{border:1px dashed var(--line);border-radius:14px;padding:22px;color:var(--mute)}
code{font:inherit;color:var(--ink)}
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def crumbs(*parts):
    """parts: (label, href or None). The last one is the current page."""
    out = []
    for i, (label, href) in enumerate(parts):
        last = i == len(parts) - 1
        out.append("<b>%s</b>" % _e(label) if last or not href
                   else "<a href='%s'>%s</a>" % (href, _e(label)))
    return "<nav class='crumbs'>%s</nav>" % "<i>/</i>".join(out)


def brands():
    if not os.path.isdir(BRANDS):
        return []
    return sorted(b for b in os.listdir(BRANDS)
                  if os.path.exists(os.path.join(BRANDS, b, "brand.json")))


def brand_name(brand):
    return (load_json(os.path.join(BRANDS, brand, "brand.json")) or {}).get("name") or brand


def ads(brand):
    d = os.path.join(ADS, brand)
    if not os.path.isdir(d):
        return []
    return sorted((a for a in os.listdir(d)
                   if os.path.exists(os.path.join(d, a, "timeline.json"))),
                  key=lambda a: -os.path.getmtime(os.path.join(d, a, "timeline.json")))


def _ad_info(brand, ad):
    d = os.path.join(ADS, brand, ad)
    h = versions.history(d)["versions"]
    last = h[-1] if h else None
    info = {"ad": ad, "n": len(h), "waiting": len(versions.waiting_comments(d)) if h else 0,
            "note": (last or {}).get("note", ""), "at": (last or {}).get("at"),
            "secs": (last or {}).get("seconds"), "thumb": None,
            "aspects": list((last or {}).get("files", {}))}
    if last and last.get("files"):
        src = os.path.join(d, "versions", list(last["files"].values())[0])
        dst = os.path.join(d, "thumb.jpg")
        if os.path.exists(src):
            if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
                try:
                    run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % min(1.0, (last.get("seconds") or 2) / 2),
                         "-i", src, "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", dst])
                except Fail:
                    pass
            if os.path.exists(dst):
                info["thumb"] = "%s/thumb.jpg?t=%d" % (ad, int(os.path.getmtime(dst)))
    return info


def _page(title, body):
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>%s</style></head><body><div class='wrap'>%s</div></body></html>"
            % (_e(title), CSS, body))


def write_project(brand):
    name = brand_name(brand)
    b = load_json(os.path.join(BRANDS, brand, "brand.json")) or {}
    infos = [_ad_info(brand, a) for a in ads(brand)]
    cards = []
    for i in infos:
        when = time.strftime("%b %d, %H:%M", time.localtime(i["at"])) if i["at"] else "no versions yet"
        th = ("<div class='th' style='background-image:url(%s)'>" % i["thumb"] if i["thumb"]
              else "<div class='th none'>draft")
        cards.append(
            "<a class='card' href='%s/preview.html'>%s%s%s</div><div class='b'><b>%s</b>"
            "<span class='n'>%s</span><span class='m'>%s%s</span></div></a>" % (
                _e(i["ad"]), th,
                "<span class='pill'>%d waiting</span>" % i["waiting"] if i["waiting"] else "",
                "<span class='pill v'>v%d</span>" % i["n"] if i["n"] else "",
                _e(i["ad"]), _e(i["note"] or ("Not snapshotted yet" if not i["n"] else "")),
                _e(when), " &middot; %.0fs &middot; %s" % (i["secs"], " ".join(i["aspects"]))
                if i["secs"] else ""))
    n_clips = len(media.all_clips(brand))
    body = (crumbs(("Projects", "/ads/index.html"), (name, None))
            + "<h1>%s</h1><div class='sub'>%s</div>" % (_e(name), _e(b.get("url", "")))
            + "<div class='tools'><a href='/brands/%s/index.html'>Brand kit, rules and footage (%d clips)</a></div>"
            % (_e(brand), n_clips)
            + "<h2>Ads (%d)</h2>" % len(infos)
            + ("<div class='grid'>%s</div>" % "".join(cards) if cards else
               "<div class='empty'>No ads yet for this project. In a Claude chat: "
               "&ldquo;make a %s ad about ...&rdquo;</div>" % _e(name)))
    d = os.path.join(ADS, brand)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write(_page("%s · adstudio project" % name, body))
    return infos


def write_home():
    cards = []
    for brand in brands():
        b = load_json(os.path.join(BRANDS, brand, "brand.json")) or {}
        infos = [_ad_info(brand, a) for a in ads(brand)]
        waiting = sum(i["waiting"] for i in infos)
        logo = b.get("logo") and os.path.exists(os.path.join(BRANDS, brand, b["logo"]))
        cover = next((i for i in infos if i["thumb"]), None)
        if cover:
            th = "<div class='th' style='background-image:url(%s/%s)'>" % (_e(brand), cover["thumb"])
        elif logo:
            th = "<div class='th plain'><img src='/brands/%s/%s' alt=''>" % (_e(brand), _e(b["logo"]))
        else:
            th = "<div class='th plain'>"
        cards.append(
            "<a class='card proj' href='%s/index.html'>%s%s</div><div class='b'><b>%s</b>"
            "<span class='n'>%s</span><span class='m'>%d ad%s &middot; %d clips</span></div></a>" % (
                _e(brand), th,
                "<span class='pill'>%d waiting</span>" % waiting if waiting else "",
                _e(b.get("name") or brand), _e(b.get("url", "")), len(infos),
                "" if len(infos) == 1 else "s", len(media.all_clips(brand))))
    body = (crumbs(("Projects", None)) + "<h1>Projects</h1>"
            "<div class='sub'>Each project has its own brand kit, footage and ads.</div>"
            + ("<h2>%d project%s</h2><div class='grid'>%s</div>" % (
                len(cards), "" if len(cards) == 1 else "s", "".join(cards)) if cards else
               "<div class='empty' style='margin-top:24px'>No projects yet. Create one with "
               "<code>adstudio brand new &lt;name&gt;</code>.</div>"))
    os.makedirs(ADS, exist_ok=True)
    with open(os.path.join(ADS, "index.html"), "w") as f:
        f.write(_page("Projects · adstudio", body))


def write_all():
    for b in brands():
        write_project(b)
    write_home()
