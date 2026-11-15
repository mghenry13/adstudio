"""The per-ad page: version history with feedback and a Redo button.

Written as a static file on every render or snapshot. The small script in it
posts feedback to `adstudio serve` and reloads when a new version lands.
"""

import html
import json
import os
import time

from . import versions

CSS = """
:root{--bg:#f4f1ec;--card:#fff;--ink:#16181b;--mute:#6b7076;--line:#e2ddd5;--accent:#c8501e;--ok:#2f7d4f;--warn:#9a6a00}
@media (prefers-color-scheme:dark){:root{--bg:#131517;--card:#1c1f22;--ink:#e8e6e1;--mute:#8e949a;--line:#2b2f33;--accent:#f0794a;--ok:#5fbf86;--warn:#e0b050}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:22px 24px 6px;max-width:1100px;margin:0 auto}
h1{font-size:20px;margin:0 0 2px;font-weight:650}
.sub{color:var(--mute);font-size:13px}
main{max-width:1100px;margin:0 auto;padding:12px 24px 60px;display:flex;flex-direction:column;gap:18px}
.v{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:22px}
.v.old{opacity:.92}
@media (max-width:720px){.v{grid-template-columns:1fr}header,main{padding-left:16px;padding-right:16px}}
video{width:100%;border-radius:10px;background:#000;display:block;max-height:70vh}
.tabs{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.tabs button{font:inherit;font-size:12px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);background:none;color:var(--mute);cursor:pointer}
.tabs button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
h2{font-size:17px;margin:0;font-weight:650;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
h2 small{font-size:12.5px;color:var(--mute);font-weight:400}
h3{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:16px 0 6px;font-weight:600}
ul{margin:0;padding-left:18px}li{margin:3px 0}
.answers{border-left:3px solid var(--accent);padding:2px 0 2px 12px;margin-top:12px;color:var(--mute);white-space:pre-wrap}
.fb{border:1px solid var(--line);border-radius:10px;padding:9px 12px;margin:6px 0;white-space:pre-wrap}
.fb .st{display:block;font-size:12px;margin-top:4px;color:var(--mute)}
.fb .st.requested{color:var(--warn)}.fb .st.done{color:var(--ok)}
textarea{width:100%;min-height:92px;font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;resize:vertical}
textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.row{display:flex;gap:12px;align-items:center;margin-top:10px;flex-wrap:wrap}
button.go{font:inherit;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--accent);color:#fff;cursor:pointer}
button.go:disabled{opacity:.5;cursor:default}
.msg{font-size:13px;color:var(--mute)}
.msg.warn{color:var(--warn)}.msg.ok{color:var(--ok)}
.note{color:var(--mute);margin-top:6px}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:14px;padding:22px;color:var(--mute)}
.finals{font-size:13px;color:var(--mute)}.finals a{color:inherit}
"""

JS = """
const AD = %(ad)s, STAMP = %(stamp)d;
const $ = (s, r=document) => r.querySelector(s);
document.querySelectorAll('.tabs').forEach(t => t.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const v = t.parentElement.querySelector('video'), at = v.currentTime, playing = !v.paused;
  v.src = b.dataset.src; v.currentTime = at; if (playing) v.play();
  t.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
}));
const box = $('#fb'), go = $('#go'), msg = $('#msg');
const KEY = 'adstudio-draft-' + AD;
if (box) {
  try { box.value = localStorage.getItem(KEY) || ''; } catch (e) {}
  box.addEventListener('input', () => { try { localStorage.setItem(KEY, box.value); } catch (e) {} });
  box.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') go.click(); });
  go.addEventListener('click', async () => {
    const text = box.value.trim();
    if (!text) { say('Write what to change first.', 'warn'); return; }
    go.disabled = true; say('Sending...');
    try {
      const r = await fetch('/api/feedback', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ad: AD, version: +go.dataset.v, text, redo: true})});
      if (!r.ok) throw new Error((await r.json()).error || r.status);
      try { localStorage.removeItem(KEY); } catch (e) {}
      location.reload();
    } catch (e) {
      go.disabled = false;
      say('Could not send. Is the preview server running? (adstudio serve) ' + e.message, 'warn');
    }
  });
}
function say(t, cls) { if (msg) { msg.textContent = t; msg.className = 'msg ' + (cls || ''); } }
async function poll() {
  try {
    const s = await (await fetch('/api/state?ad=' + encodeURIComponent(AD), {cache: 'no-store'})).json();
    if (s.stamp && s.stamp > STAMP + 5 && !(box && box.value.trim() && document.activeElement === box)) { location.reload(); return; }
    const w = $('#working');
    if (w) w.textContent = s.pending.length
      ? (s.listening ? 'Claude has this and is working on the next version. This page updates by itself.'
                     : 'Saved. No chat is watching this ad right now: say "redo" in the adstudio chat.')
      : '';
    if (w) w.className = 'msg ' + (s.pending.length ? (s.listening ? 'ok' : 'warn') : '');
  } catch (e) {}
  setTimeout(poll, 1500);
}
poll();
"""


def _e(s):
    return html.escape(str(s or ""))


def _when(t):
    return time.strftime("%b %d, %H:%M", time.localtime(t))


def _video(files, base):
    keys = list(files)
    if not keys:
        return ""
    src = lambda k: "%s/%s#t=0.1" % (base, files[k])
    tabs = ""
    if len(keys) > 1:
        tabs = "<div class='tabs'>%s</div>" % "".join(
            "<button class='%s' data-src='%s'>%s</button>" % ("on" if i == 0 else "", src(k), k)
            for i, k in enumerate(keys))
    return "<div><video src='%s' controls loop playsinline preload='metadata'></video>%s</div>" % (
        src(keys[0]), tabs)


def write(ad_dir, tl):
    name = tl.get("name", os.path.basename(ad_dir))
    ad_ref = "%s/%s" % (tl.get("brand", ""), os.path.basename(ad_dir))
    h = versions.history(ad_dir)["versions"]
    cards = []
    for i, v in enumerate(reversed(h)):
        newest = i == 0
        stamp = "?t=%d" % v["at"]
        files = dict((k, f + stamp) for k, f in v["files"].items())
        body = ["<h2>Version %d <small>%s &middot; %.1fs%s</small></h2>" % (
            v["n"], _when(v["at"]), v["seconds"], " &middot; latest" if newest else "")]
        if v.get("note"):
            body.append("<div class='note'>%s</div>" % _e(v["note"]))
        if v.get("answers"):
            body.append("<h3>Your feedback on version %d</h3><div class='answers'>%s</div>"
                        % (v["n"] - 1, _e(v["answers"])))
        body.append("<h3>What changed</h3><ul>%s</ul>" % "".join(
            "<li>%s</li>" % _e(c) for c in v["changes"]))
        fbs = v.get("feedback", [])
        if fbs:
            label = {"requested": "Redo requested", "note": "Note"}
            body.append("<h3>Feedback</h3>" + "".join(
                "<div class='fb'>%s<span class='st %s'>%s &middot; %s</span></div>" % (
                    _e(f["text"]), f["status"],
                    "Done in version %d" % f["done_in"] if f["status"] == "done"
                    else label.get(f["status"], f["status"]), _when(f["at"])) for f in fbs))
        if newest:
            body.append(
                "<h3>What should change?</h3>"
                "<textarea id='fb' placeholder='Say it like you would in chat. "
                "Example: hook text bigger, cut the first clip half a second earlier, "
                "lose the end card.'></textarea>"
                "<div class='row'><button class='go' id='go' data-v='%d'>Redo</button>"
                "<span class='msg' id='msg'>Cmd+Enter also sends.</span></div>"
                "<div class='msg' id='working' style='margin-top:8px'></div>" % v["n"])
        cards.append("<section class='v%s'>%s<div>%s</div></section>" % (
            "" if newest else " old", _video(files, "versions"), "".join(body)))
    if not cards:
        drafts = []
        d = os.path.join(ad_dir, "previews")
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.endswith(".mp4") and ".tmp" not in n:
                    drafts.append("<video src='previews/%s?t=%d' controls loop playsinline "
                                  "style='max-width:300px'></video>"
                                  % (n, int(os.path.getmtime(os.path.join(d, n)))))
        cards.append("<div class='empty'>No saved versions yet. A version is saved with "
                     "<code>adstudio snapshot %s</code>, and then feedback and Redo appear here."
                     "<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:14px'>%s</div></div>"
                     % (_e(ad_ref), "".join(drafts)))
    finals = ""
    d = os.path.join(ad_dir, "exports")
    if os.path.isdir(d):
        fl = [n for n in sorted(os.listdir(d)) if n.endswith((".mp4", ".xml"))]
        if fl:
            finals = "<div class='finals'>Finals: %s</div>" % " &middot; ".join(
                "<a href='exports/%s'>%s</a>" % (n, n) for n in fl)
    hist = os.path.join(ad_dir, "versions", "history.json")
    page = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s &middot; adstudio versions</title><style>%s</style></head><body>"
            "<header><h1>%s</h1><div class='sub'>%s &middot; %d version%s</div>%s</header>"
            "<main>%s</main><script>%s</script></body></html>") % (
        _e(name), CSS, _e(name), _e(tl.get("brand", "")), len(h),
        "" if len(h) == 1 else "s", finals, "".join(cards),
        JS % {"ad": json.dumps(ad_ref), "stamp": 0})
    dst = os.path.join(ad_dir, "preview.html")
    with open(dst, "w") as f:
        f.write(page)
    # The page carries the stamp the server will report for it, so it only
    # reloads when something newer than itself exists.
    stamp = int(max(os.path.getmtime(dst),
                    os.path.getmtime(hist) if os.path.exists(hist) else 0) * 1000)
    with open(dst, "w") as f:
        f.write(page.replace("STAMP = 0;", "STAMP = %d;" % stamp))
    os.utime(dst, (stamp / 1000.0, stamp / 1000.0))
