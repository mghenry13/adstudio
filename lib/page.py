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
:root{--bg:#fafaf9;--panel:#fff;--ink:#18181b;--mute:#71717a;--faint:#a1a1aa;--line:#e7e5e4;--hover:#f4f4f5;--accent:#e4572e;--ok:#15803d;--warn:#b45309;--cta:#16a34a;--cta-ink:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#0f0f10;--panel:#17171a;--ink:#f4f4f5;--mute:#a1a1aa;--faint:#63636b;--line:#26262b;--hover:#1f1f23;--accent:#ff7a50;--ok:#4ade80;--warn:#fbbf24;--cta:#22c55e;--cta-ink:#052e16}}
*{box-sizing:border-box}
html{-webkit-font-smoothing:antialiased}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.55 ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
header{max-width:1120px;margin:0 auto;padding:26px 28px 18px;display:flex;justify-content:space-between;align-items:baseline;gap:20px;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600;letter-spacing:0}
.sub{color:var(--mute);font-size:13px;margin-left:10px;font-weight:400}
.finals{font-size:13px;color:var(--mute);display:flex;gap:14px}
.finals a{color:var(--mute);text-decoration:none;border-bottom:1px solid var(--line)}
.finals a:hover{color:var(--ink)}
main{max-width:1120px;margin:0 auto;padding:0 28px 80px}
.v{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:36px;align-items:start}
.v.latest{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px}
@media (max-width:760px){.v{grid-template-columns:1fr;gap:20px}header,main{padding-left:16px;padding-right:16px}}
video{width:100%;border-radius:12px;background:#000;display:block;max-height:76vh}
.tabs{display:flex;gap:4px;margin-top:10px}
.tabs button{font:inherit;font-size:12px;padding:3px 10px;border-radius:7px;border:0;background:none;color:var(--mute);cursor:pointer}
.tabs button:hover{background:var(--hover)}
.tabs button.on{background:var(--hover);color:var(--ink);font-weight:500}
h2{font-size:14px;margin:0;font-weight:600;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;letter-spacing:0}
h2 small,summary small{font-size:13px;color:var(--mute);font-weight:400}
.note{color:var(--mute);margin-top:4px}
.compose{display:flex;gap:10px;align-items:center;margin-top:18px;padding:6px 6px 6px 10px;border:1px solid var(--line);border-radius:12px;background:var(--bg)}
.compose:focus-within{border-color:var(--faint)}
textarea{flex:1;min-width:0;height:34px;min-height:34px;max-height:160px;font:inherit;color:inherit;background:none;border:0;padding:6px 0;resize:none;outline:none}
textarea::placeholder{color:var(--faint)}
button.go{font:inherit;font-size:13.5px;font-weight:600;padding:7px 14px;border-radius:9px;border:0;background:var(--cta);color:var(--cta-ink);cursor:pointer;white-space:nowrap}
button.go:hover{filter:brightness(1.06)}button.go:disabled{opacity:.5;cursor:default}
.msg{font-size:12.5px;color:var(--mute);margin-top:8px;min-height:1em}
.msg.warn{color:var(--warn)}.msg.ok{color:var(--ok)}.msg:empty{display:none}
.tc{font:500 12px ui-monospace,SFMono-Regular,Menlo,monospace;padding:3px 7px;border-radius:6px;border:0;background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);cursor:pointer;white-space:nowrap}
.tc:hover{background:color-mix(in srgb,var(--accent) 24%,transparent)}
.tc.off,.tc.gen{background:var(--hover);color:var(--mute)}
.tc.gen{cursor:default}
.head{display:flex;justify-content:space-between;align-items:center;gap:12px}
.compose.two{margin-top:8px}
#tc{cursor:default}
#clist,.clist{margin-top:14px}
.fb{display:flex;gap:12px;align-items:baseline;padding:10px 0;border-top:1px solid var(--line);white-space:pre-wrap}
.fb .x{flex:1;min-width:0}
.fb .st{display:block;font-size:12px;margin-top:2px;color:var(--faint)}
.fb .st.requested{color:var(--warn)}.fb .st.done{color:var(--ok)}
.del{border:0;background:none;color:var(--faint);cursor:pointer;font-size:16px;line-height:1;padding:2px 4px;border-radius:5px;opacity:0}
.fb:hover .del{opacity:1}.del:hover{color:var(--ink);background:var(--hover)}
.marks{position:relative;height:12px;margin:8px 16px 0}
.marks:empty{display:none}
.marks i{position:absolute;top:1px;width:9px;height:9px;margin-left:-4.5px;border-radius:50%;background:var(--accent);cursor:pointer}
.marks i.done{background:var(--ok)}
.sec{margin-top:20px;font-size:13.5px}
.sec h3{font-size:12px;color:var(--mute);margin:0 0 6px;font-weight:500}
ul{margin:0;padding-left:17px;color:var(--ink)}li{margin:2px 0}
.answers{color:var(--mute);white-space:pre-wrap;border-left:2px solid var(--line);padding-left:12px}
details.chg{border:0;margin-top:20px;font-size:12.5px}
details.chg summary{padding:6px 0;font-weight:400;color:var(--mute)}
details.chg summary:hover{background:none;color:var(--ink)}
details.chg ul{margin-top:4px}
.older{margin-top:34px}
.older>h3{font-size:12px;color:var(--mute);font-weight:500;margin:0 0 4px}
details{border-top:1px solid var(--line)}
details:last-child{border-bottom:1px solid var(--line)}
summary{list-style:none;cursor:pointer;padding:13px 4px;display:flex;gap:12px;align-items:baseline;font-weight:500}
summary::-webkit-details-marker{display:none}
summary:hover{background:var(--hover)}
summary::before{content:"\\203A";color:var(--faint);display:inline-block;width:10px;transition:transform .15s}
details[open] summary::before{transform:rotate(90deg)}
details .v{padding:8px 4px 26px}
.newv{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:5;font:inherit;font-size:13.5px;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--ink);color:var(--bg);cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.25)}
.newv[hidden]{display:none}
.empty{background:var(--panel);border:1px dashed var(--line);border-radius:16px;padding:24px;color:var(--mute)}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace}
"""

JS = """
const AD = %(ad)s; let STAMP = %(stamp)d;
const $ = (s, r=document) => r.querySelector(s);
const KEY = 'adstudio-draft-' + AD;
const fmt = t => Math.floor(t / 60) + ':' + (t %% 60 < 10 ? '0' : '') + (t %% 60).toFixed(1);
const vidOf = el => el.closest('.v').querySelector('video');
let box, boxw, go, msg, chip, at = 0, fresh = null;

function say(t, cls) { if (msg) { msg.textContent = t; msg.className = 'msg ' + (cls || ''); } }
async function post(body) {
  const r = await fetch('/api/feedback', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({ad: AD, version: +go.dataset.v}, body))});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  STAMP = d.stamp;
  return d;
}
function label() {
  const n = document.querySelectorAll('#clist .st.open').length;
  go.textContent = 'Redo' + (n ? ' with ' + n + ' comment' + (n === 1 ? '' : 's') : '');
}
function addRow(text, t, id) {
  const row = document.createElement('div'); row.className = 'fb'; row.dataset.t = t === null ? 1e9 : t;
  const tc = document.createElement(t === null ? 'span' : 'button');
  tc.className = 'tc' + (t === null ? ' gen' : ''); tc.textContent = t === null ? 'Whole video' : fmt(t);
  if (t !== null) tc.dataset.seek = t;
  const x = document.createElement('div'); x.className = 'x'; x.textContent = text;
  const st = document.createElement('span'); st.className = 'st open'; st.textContent = 'Not sent yet';
  x.appendChild(st);
  const del = document.createElement('button'); del.className = 'del'; del.dataset.at = id; del.title = 'Delete'; del.textContent = '\u00d7';
  row.append(tc, x, del);
  const list = $('#clist'), after = [...list.children].find(c => +c.dataset.t > +row.dataset.t);
  list.insertBefore(row, after || null);
  if (t !== null) { const v = vidOf(box), m = document.createElement('i');
    m.style.left = (t / (v.duration || 1) * 100) + '%%'; m.dataset.seek = t; m.dataset.at = id; m.title = text;
    box.closest('.v').querySelector('.marks').appendChild(m); }
  label();
}
// Adds whatever is typed in either box; with redo, then sends every comment.
async function send(redo) {
  const items = [];
  if (box.value.trim()) items.push([box, box.value.trim(), Math.round(at * 100) / 100, KEY]);
  if (boxw.value.trim()) items.push([boxw, boxw.value.trim(), null, KEY + '-whole']);
  if (!items.length && !redo) return;
  go.disabled = true;
  try {
    for (const [el, text, t, key] of items) {
      const d = await post({text, t, redo: false});
      addRow(text, t, d.added);
      el.value = ''; try { localStorage.removeItem(key); } catch (e) {}
    }
    if (redo) { await post({text: '', redo: true});
      document.querySelectorAll('#clist .st.open').forEach(s => { s.className = 'st requested'; s.textContent = 'Sent to Claude'; });
      document.querySelectorAll('#clist .del').forEach(d => d.remove()); label(); }
    say('');
    at = vidOf(box).currentTime; chip.textContent = fmt(at);
  } catch (e) {
    say(e.message === 'add a comment first' ? 'Add a comment first.'
        : 'Could not send. Is the preview server running? (adstudio serve) ' + e.message, 'warn');
  }
  go.disabled = false;
}

// Clicks are handled once for the whole page, so they keep working after
// a new version is swapped in.
document.addEventListener('click', async e => {
  const tab = e.target.closest('.tabs button');
  if (tab) { const t = tab.parentElement, v = t.parentElement.querySelector('video'), pos = v.currentTime, playing = !v.paused;
    v.src = tab.dataset.src; v.currentTime = pos; if (playing) v.play();
    t.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === tab)); return; }
  const s = e.target.closest('[data-seek]');
  if (s) { const v = vidOf(s); v.currentTime = +s.dataset.seek; v.pause(); return; }
  if (e.target.closest('#go')) { send(true); return; }
  if (e.target.closest('#newv')) { swap(); return; }
  const d = e.target.closest('.del');
  if (d) { try { await post({text: '', redo: false, delete: +d.dataset.at});
      const m = document.querySelector('.marks i[data-at="' + d.dataset.at + '"]'); if (m) m.remove();
      d.closest('.fb').remove(); label();
    } catch (err) { say(err.message, 'warn'); } }
});

// Wires up the comment boxes of the latest version. Runs at load and again
// after each swap.
function init() {
  box = $('#fb'); boxw = $('#fbw'); go = $('#go'); msg = $('#msg'); chip = $('#tc');
  if (!box) return;
  const v = vidOf(box);
  at = 0;
  // The timecode follows the playhead until you start typing, then it holds.
  v.addEventListener('timeupdate', () => { if (!box.value.trim()) { at = v.currentTime; chip.textContent = fmt(at); } });
  // A half-typed timecode comment keeps its moment across a reload.
  try { const saved = parseFloat(localStorage.getItem(KEY + '-at'));
    if ((localStorage.getItem(KEY) || '').trim() && !isNaN(saved)) { at = saved;
      v.addEventListener('loadedmetadata', () => { v.currentTime = saved; }, {once: true});
      if (v.readyState >= 1) v.currentTime = saved; } } catch (e) {}
  [[box, KEY], [boxw, KEY + '-whole']].forEach(([el, key]) => {
    try { el.value = localStorage.getItem(key) || ''; } catch (e) {}
    el.addEventListener('input', () => {
      if (el === box) { if (el.value.trim()) v.pause(); try { localStorage.setItem(KEY + '-at', at); } catch (e) {} }
      try { localStorage.setItem(key, el.value); } catch (e) {} });
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(true); }
      else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(false); }
    });
  });
  chip.textContent = fmt(at); label();
}

// A new version never interrupts: it waits behind a button. Clicking it
// swaps the page content in place, with no reload. Typed text is kept.
function swap() {
  if (!fresh) return;
  const open = [...document.querySelectorAll('.older details[open] > summary')].map(x => x.dataset.n);
  // Set as HTML rather than moving nodes: a <video> parsed in a detached
  // document never starts loading when it is moved into the page.
  $('main').innerHTML = fresh.doc.querySelector('main').innerHTML;
  $('header').innerHTML = fresh.doc.querySelector('header').innerHTML;
  document.querySelectorAll('main video').forEach(v => v.load());
  open.forEach(n => { const d = document.querySelector('summary[data-n="' + n + '"]'); if (d) d.parentElement.open = true; });
  STAMP = fresh.stamp; fresh = null;
  $('#newv').hidden = true;
  try { localStorage.removeItem(KEY + '-at'); } catch (e) {}
  init();
  window.scrollTo({top: 0, behavior: 'smooth'});
}
async function check() {
  const text = await (await fetch(location.pathname + '?_=' + Date.now(), {cache: 'no-store'})).text();
  const doc = new DOMParser().parseFromString(text, 'text/html');
  const stamp = +(text.match(/let STAMP = (\\d+)/) || [0, 0])[1];
  const theirs = doc.querySelector('#go'), mine = $('#go');
  if (theirs && mine && +theirs.dataset.v > +mine.dataset.v) {
    fresh = {doc, stamp};
    const b = $('#newv'); b.textContent = 'Version ' + theirs.dataset.v + ' is ready. Show it'; b.hidden = false;
  } else if (theirs && mine && !fresh) {
    // Same version, something else changed (for example a comment was
    // marked done): refresh the list quietly, leave the video alone.
    const a = doc.querySelector('#clist'), m = doc.querySelector('.v.latest .marks');
    if (a) $('#clist').innerHTML = a.innerHTML;
    if (m) document.querySelector('.v.latest .marks').innerHTML = m.innerHTML;
    STAMP = stamp; label();
  } else if (!mine) { location.reload(); }
}
async function poll() {
  try {
    const s = await (await fetch('/api/state?ad=' + encodeURIComponent(AD), {cache: 'no-store'})).json();
    if (s.stamp && s.stamp > STAMP + 5 && !(fresh && s.stamp <= fresh.stamp + 5)) await check();
    const w = $('#working'), r = s.runner || {};
    if (w) {
      let t = '', cls = '';
      if (s.pending.length) {
        if (s.listening || r.state === 'running') { t = 'Claude is working on the next version.'; cls = 'ok'; }
        else if (r.state === 'failed') { t = r.message + (r.command ? '\\n' + r.command : ''); cls = 'warn'; }
        else { t = 'Sent. Waiting for Claude to pick this up.'; cls = ''; }
      }
      w.textContent = t; w.className = 'msg ' + cls; w.style.whiteSpace = 'pre-wrap';
    }
  } catch (e) {}
  setTimeout(poll, 1500);
}
init();
poll();
"""


def _e(s):
    return html.escape(str(s or ""))


def _when(t):
    t = t / 1000.0 if t > 1e11 else t      # newer comments store milliseconds
    return time.strftime("%b %d, %H:%M", time.localtime(t))


def _video(files, base, feedback=None, seconds=1.0):
    keys = list(files)
    if not keys:
        return ""
    src = lambda k: "%s/%s#t=0.1" % (base, files[k])
    tabs = ""
    if len(keys) > 1:
        tabs = "<div class='tabs'>%s</div>" % "".join(
            "<button class='%s' data-src='%s'>%s</button>" % ("on" if i == 0 else "", src(k), k)
            for i, k in enumerate(keys))
    marks = "".join(
        "<i class='%s' style='left:%.2f%%' data-seek='%s' data-at='%s' title='%s'></i>" % (
            "done" if f.get("status") == "done" else "", 100.0 * f["t"] / max(seconds, 0.1),
            f["t"], f["at"], _e(f["text"]))
        for f in (feedback or []) if f.get("t") is not None)
    return ("<div><video src='%s' controls loop playsinline preload='metadata'></video>"
            "<div class='marks' title='Comments on the timeline'>%s</div>%s</div>") % (
        src(keys[0]), marks, tabs)


def write(ad_dir, tl):
    name = tl.get("name", os.path.basename(ad_dir))
    ad_ref = "%s/%s" % (tl.get("brand", ""), os.path.basename(ad_dir))
    h = versions.history(ad_dir)["versions"]
    cards = []
    older = []
    for i, v in enumerate(reversed(h)):
        newest = i == 0
        stamp = "?t=%d" % v["at"]
        files = dict((k, f + stamp) for k, f in v["files"].items())
        fbs = sorted(v.get("feedback", []),
                     key=lambda f: (f.get("t") is None, f.get("t") or 0, f["at"]))
        label = {"requested": "Sent to Claude", "note": "Note", "open": "Not sent yet"}
        rows = "".join(
            "<div class='fb' data-t='%s'>%s<div class='x'>%s<span class='st %s'>%s</span></div>%s</div>" % (
                f["t"] if f.get("t") is not None else 1e9,
                "<button class='tc' data-seek='%s'>%s</button>" % (f["t"], versions.tc(f["t"]))
                if f.get("t") is not None else "<span class='tc gen'>Whole video</span>",
                _e(f["text"]), f["status"],
("Done in version %d" % f["done_in"] if f["status"] == "done"
                 else label.get(f["status"], f["status"]))
                + (" &middot; written on version %d" % f["from"] if f.get("from") else ""),
                "<button class='del' data-at='%d' title='Delete'>&times;</button>" % f["at"]
                if f["status"] == "open" and newest else "") for f in fbs)
        body = []
        if newest:
            n_open = sum(1 for f in fbs if f["status"] == "open")
            body.append(
                "<div class='head'><h2>Version %d <small>%s &middot; %.1fs</small></h2>"
                "<button class='go' id='go' data-v='%d' title='Send all comments to Claude "
                "(Cmd+Enter)'>Redo%s</button></div>" % (
                    v["n"], _when(v["at"]), v["seconds"], v["n"],
                    " with %d comment%s" % (n_open, "" if n_open == 1 else "s") if n_open else ""))
            if v.get("note"):
                body.append("<div class='note'>%s</div>" % _e(v["note"]))
            body.append(
                "<div class='compose'><span class='tc' id='tc'>0:00.0</span>"
                "<textarea id='fb' rows='1' placeholder='Comment at this moment, then Enter'></textarea></div>"
                "<div class='compose two'><span class='tc gen'>Whole video</span>"
                "<textarea id='fbw' rows='1' placeholder='Comment on the whole video, then Enter'></textarea></div>"
                "<div class='msg' id='msg'></div><div class='msg' id='working'></div>"
                "<div id='clist'>%s</div>" % rows)
        elif v.get("note"):
            body.append("<div class='note'>%s</div>" % _e(v["note"]))
        if not newest and rows:
            body.append("<div class='clist'>%s</div>" % rows)
        if v.get("answers"):
            body.append("<div class='sec'><h3>Your notes on version %d</h3>"
                        "<div class='answers'>%s</div></div>" % (v["n"] - 1, _e(v["answers"])))
        nch = len(v["changes"])
        body.append("<details class='chg'><summary>What changed <small>%d change%s</small></summary>"
                    "<ul>%s</ul></details>" % (nch, "" if nch == 1 else "s", "".join(
                        "<li>%s</li>" % _e(c) for c in v["changes"])))
        card = "<section class='v%s'>%s<div>%s</div></section>" % (
            " latest" if newest else "",
            _video(files, "versions", v.get("feedback"), v.get("seconds", 1.0)), "".join(body))
        if newest:
            cards.append(card)
        else:
            nc, nf = len(v["changes"]), len(fbs)
            older.append("<details><summary data-n='%d'>Version %d <small>%s &middot; %d change%s%s</small>"
                         "</summary>%s</details>" % (
                             v["n"], v["n"], _when(v["at"]), nc, "" if nc == 1 else "s",
                             " &middot; %d comment%s" % (nf, "" if nf == 1 else "s") if nf else "",
                             card))
    if older:
        cards.append("<div class='older'><h3>Earlier versions</h3>%s</div>" % "".join(older))
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
            finals = "<div class='finals'>%s</div>" % "".join(
                "<a href='exports/%s' title='%s'>%s</a>" % (
                    n, n, "Premiere XML" if n.endswith(".xml") else "Final " + n.rsplit("-", 1)[-1][:-4])
                for n in fl)
    hist = os.path.join(ad_dir, "versions", "history.json")
    page = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s &middot; adstudio versions</title><style>%s</style></head><body>"
            "<header><h1>%s<span class='sub'>%s &middot; %d version%s</span></h1>%s</header>"
            "<main>%s</main><button id='newv' class='newv' hidden></button>"
            "<script>%s</script></body></html>") % (
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
        f.write(page.replace("let STAMP = 0;", "let STAMP = %d;" % stamp))
    os.utime(dst, (stamp / 1000.0, stamp / 1000.0))
