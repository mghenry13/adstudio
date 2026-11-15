"""The per-ad page: version history with timecoded comments.

Written as a static file on every render or snapshot. The small script in it
saves comments through `adstudio serve` and reloads when a new version lands.
"""

import html
import json
import os
import re
import time

from . import hub, versions

CSS = """
:root{--bg:#fafaf9;--panel:#fff;--ink:#18181b;--mute:#71717a;--faint:#a1a1aa;--line:#e7e5e4;--hover:#f4f4f5;--accent:#e4572e;--ok:#15803d;--warn:#b45309;--cta:#16a34a}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e10;--panel:#161618;--ink:#f4f4f5;--mute:#a1a1aa;--faint:#63636b;--line:#27272b;--hover:#1e1e22;--accent:#ff7a50;--ok:#4ade80;--warn:#fbbf24;--cta:#22c55e}}
*{box-sizing:border-box}
html{-webkit-font-smoothing:antialiased}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.6 ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace}
a{color:inherit}
header{max-width:1180px;margin:0 auto;padding:22px 28px 16px;display:flex;justify-content:space-between;align-items:baseline;gap:20px;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:600}
.crumbs{font-size:13px;color:var(--mute);display:flex;gap:8px;flex-wrap:wrap;align-items:baseline}
.crumbs a{text-decoration:none;border-bottom:1px solid var(--line)}.crumbs a:hover{color:var(--ink)}
.crumbs b{color:var(--ink);font-weight:600}.crumbs i{font-style:normal;color:var(--faint)}
.sub{color:var(--mute);font-size:12.5px;margin-left:12px;font-weight:400}
.sub a{text-decoration:none;border-bottom:1px solid var(--line)}.sub a:hover{color:var(--ink)}
.finals{font-size:12.5px;color:var(--mute);display:flex;gap:14px}
.finals a{text-decoration:none;border-bottom:1px solid var(--line)}.finals a:hover{color:var(--ink)}
main{max-width:1180px;margin:0 auto;padding:0 28px 90px}
.v{display:grid;grid-template-columns:minmax(0,360px) minmax(0,1fr);gap:40px;align-items:start}
.v.latest{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px}
.v.latest .stage{position:sticky;top:20px}
@media (max-width:780px){.v{grid-template-columns:1fr;gap:20px}.v.latest .stage{position:static}header,main{padding-left:16px;padding-right:16px}}
video{width:100%;border-radius:12px;background:#000;display:block;max-height:calc(100vh - 120px)}
.marks{position:relative;height:14px;margin:8px 16px 0}
.marks:empty{display:none}
.marks i{position:absolute;top:2px;width:9px;height:9px;margin-left:-4.5px;border-radius:50%;background:var(--accent);cursor:pointer;transition:transform .12s}
.marks i:hover{transform:scale(1.5)}
.marks i.done{background:var(--faint)}
.marks i.chg{background:none;border:2px solid var(--cta);border-radius:2px;transform:rotate(45deg);width:8px;height:8px;margin-left:-4px;top:3px}
.marks i.chg:hover{transform:rotate(45deg) scale(1.4)}
.tabs{display:flex;gap:4px;margin-top:8px}
.tabs button{font:inherit;font-size:12px;padding:3px 10px;border-radius:7px;border:0;background:none;color:var(--mute);cursor:pointer}
.tabs button:hover{background:var(--hover)}
.tabs button.on{background:var(--hover);color:var(--ink)}
h2{font-size:14px;margin:0;font-weight:600;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
h2 small{font-size:12.5px;color:var(--mute);font-weight:400}
.lead{margin:8px 0 0;color:var(--ink);font-size:13.5px;line-height:1.6;max-width:70ch}
.tc{font:500 12px ui-monospace,SFMono-Regular,Menlo,monospace;padding:3px 7px;border-radius:6px;border:0;background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);cursor:pointer;white-space:nowrap;flex:none}
button.tc:hover{background:color-mix(in srgb,var(--accent) 26%,transparent)}
.tc.gen{background:var(--hover);color:var(--mute);cursor:default}
#tc{cursor:default}
.tc.chgt{background:color-mix(in srgb,var(--cta) 15%,transparent);color:var(--cta)}
button.tc.chgt:hover{background:color-mix(in srgb,var(--cta) 28%,transparent)}
details.chg{margin-top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
details.chg+details.chg{margin-top:8px}
details.chg summary{list-style:none;cursor:pointer;padding:9px 12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;color:var(--mute);font-size:12.5px}
details.chg summary::-webkit-details-marker{display:none}
details.chg summary>span:first-child::before{content:"+";display:inline-block;width:14px;color:var(--faint)}
details.chg[open] summary>span:first-child::before{content:"\\2212"}
details.chg summary:hover{background:var(--hover)}
.jumps{display:flex;gap:5px;flex-wrap:wrap}
details.chg ul{list-style:none;margin:0;padding:4px 12px 10px;border-top:1px solid var(--line)}
details.chg li{display:flex;gap:10px;align-items:baseline;padding:5px 0;font-size:12.5px}
details.chg li>span:last-child{min-width:0;overflow-wrap:anywhere}
details.ans .fb{padding:8px 12px}
details.ans .fb:first-of-type{border-top:1px solid var(--line)}
.compose{display:flex;gap:10px;align-items:flex-start;margin-top:22px;padding:8px 10px;border:1px solid var(--line);border-radius:12px;background:var(--bg);transition:border-color .12s}
.compose.two{margin-top:8px}
.compose:focus-within{border-color:var(--mute)}
.compose .tc{margin-top:3px}
textarea{flex:1;min-width:0;height:26px;min-height:26px;max-height:180px;font:inherit;color:inherit;background:none;border:0;padding:3px 0;resize:none;outline:none;overflow:hidden}
textarea::placeholder{color:var(--faint)}
.msg{font-size:12.5px;color:var(--mute);margin-top:8px}.msg.warn{color:var(--warn)}.msg:empty{display:none}
#clist,.clist{margin-top:10px}
.fb{display:flex;gap:12px;align-items:baseline;padding:10px 8px;margin:0 -8px;border-radius:8px;white-space:pre-wrap}
.fb+.fb{border-top:1px solid var(--line);border-top-left-radius:0;border-top-right-radius:0}
.fb[data-t]{cursor:pointer}
.fb:hover{background:var(--hover)}
.fb.now{background:color-mix(in srgb,var(--accent) 9%,transparent)}
.fb .x{flex:1;min-width:0;overflow-wrap:anywhere}
.fb .st{display:block;font-size:11.5px;margin-top:1px;color:var(--faint)}
.fb .st.done{color:var(--ok)}
.fb.done .x{color:var(--mute)}
.del{border:0;background:none;color:var(--faint);cursor:pointer;font-size:15px;line-height:1;padding:2px 5px;border-radius:5px;opacity:0}
.fb:hover .del{opacity:1}.del:hover{color:var(--ink);background:var(--line)}
.hint{font-size:12.5px;color:var(--mute);margin-top:12px;padding:10px 12px;border-radius:10px;background:var(--hover)}
.hint:empty{display:none}
.hint b{color:var(--ink);font-weight:600}
.keys{margin-top:16px;font-size:11.5px;color:var(--faint);display:flex;gap:4px;flex-wrap:wrap;align-items:center}
kbd{font:inherit;padding:1px 5px;border:1px solid var(--line);border-radius:5px;color:var(--mute);margin-left:8px}
kbd:first-child{margin-left:0}kbd+kbd{margin-left:2px}
.older{margin-top:36px}
.older>h3{font-size:12px;color:var(--mute);font-weight:400;margin:0 0 6px}
details.ver{border-top:1px solid var(--line)}
details.ver:last-child{border-bottom:1px solid var(--line)}
details.ver>summary{list-style:none;cursor:pointer;padding:11px 6px;display:grid;grid-template-columns:96px minmax(0,1fr) auto;gap:14px;align-items:baseline}
details.ver>summary::-webkit-details-marker{display:none}
details.ver>summary:hover{background:var(--hover)}
details.ver>summary b{font-weight:600}
details.ver>summary .sn{color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
details.ver[open]>summary .sn{white-space:normal}
details.ver>summary small{color:var(--faint);font-size:12px;white-space:nowrap}
details.ver .v{padding:10px 6px 28px}
.newv{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:5;font:inherit;font-size:13px;font-weight:600;padding:9px 18px;border-radius:99px;border:0;background:var(--cta);color:#04130a;cursor:pointer;box-shadow:0 8px 28px rgba(0,0,0,.3)}
.newv[hidden]{display:none}
.empty{background:var(--panel);border:1px dashed var(--line);border-radius:16px;padding:24px;color:var(--mute)}
code{font:inherit}
:focus-visible{outline:2px solid var(--mute);outline-offset:2px;border-radius:6px}
textarea:focus-visible{outline:none}
"""

JS = """
const AD = %(ad)s; let STAMP = %(stamp)d;
const $ = (s, r=document) => r.querySelector(s);
const KEY = 'adstudio-draft-' + AD;
const fmt = t => Math.floor(t / 60) + ':' + (t %% 60 < 10 ? '0' : '') + (t %% 60).toFixed(1);
const vidOf = el => el.closest('.v').querySelector('video');
let box, boxw, msg, chip, at = 0, fresh = null;
const ver = () => +$('#clist').dataset.v;

function say(t, cls) { if (msg) { msg.textContent = t; msg.className = 'msg ' + (cls || ''); } }
async function post(body) {
  const r = await fetch('/api/feedback', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(Object.assign({ad: AD, version: ver()}, body))});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  STAMP = d.stamp;
  return d;
}
// Comments are applied from the Claude chat, so the page says how.
function label() {
  const n = document.querySelectorAll('#clist .st.open').length, h = $('#hint');
  if (!h) return;
  h.innerHTML = n ? '<b>' + n + ' comment' + (n === 1 ? '' : 's') + ' waiting.</b> Say "redo" in your Claude chat for this ad to apply ' + (n === 1 ? 'it' : 'them') + '.' : '';
}
function addRow(text, t, id) {
  const row = document.createElement('div'); row.className = 'fb'; row.dataset.t = t === null ? 1e9 : t;
  const tc = document.createElement(t === null ? 'span' : 'button');
  tc.className = 'tc' + (t === null ? ' gen' : ''); tc.textContent = t === null ? 'Whole video' : fmt(t);
  if (t !== null) tc.dataset.seek = t;
  const x = document.createElement('div'); x.className = 'x'; x.textContent = text;
  const st = document.createElement('span'); st.className = 'st open'; st.textContent = 'Waiting';
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
// Saves whatever is typed in the given box.
async function send(el) {
  const text = el.value.trim();
  if (!text) return;
  const t = el === box ? Math.round(at * 100) / 100 : null;
  try {
    const d = await post({text, t});
    addRow(text, t, d.added);
    el.value = ''; grow(el); try { localStorage.removeItem(el === box ? KEY : KEY + '-whole'); } catch (e) {}
    say('');
    if (el === box) { at = vidOf(box).currentTime; chip.textContent = fmt(at); }
  } catch (e) {
    say('Could not save. Is the preview server running? (adstudio serve) ' + e.message, 'warn');
  }
}

// Earlier versions load their video only when first used.
function wake(v) { if (v && !v.getAttribute('src') && v.dataset.src) { v.src = v.dataset.src; v.load(); } }
document.addEventListener('toggle', e => {
  if (e.target.matches && e.target.matches('details.ver') && e.target.open) wake(e.target.querySelector('video'));
}, true);
// Keys, when not typing: space plays, arrows step a second, comma and
// period step a frame, C starts a comment at the current moment.
document.addEventListener('keydown', e => {
  if ((e.target.closest && e.target.closest('textarea, input')) || e.metaKey || e.ctrlKey || e.altKey) return;
  const v = document.querySelector('.v.latest video'); if (!v) return;
  const step = d => { v.pause(); v.currentTime = Math.max(0, Math.min(v.duration || 1e9, v.currentTime + d)); };
  if (e.key === ' ') { e.preventDefault(); v.paused ? v.play() : v.pause(); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  else if (e.key === ',') step(-1 / 30);
  else if (e.key === '.') step(1 / 30);
  else if (e.key === 'c' || e.key === 'C') { e.preventDefault(); v.pause(); if (box) box.focus(); }
});
const grow = el => { el.style.height = 'auto'; el.style.height = Math.min(180, el.scrollHeight) + 'px'; };

// Clicks are handled once for the whole page, so they keep working after
// a new version is swapped in.
document.addEventListener('click', async e => {
  const tab = e.target.closest('.tabs button');
  if (tab) { const t = tab.parentElement, v = t.parentElement.querySelector('video'), pos = v.currentTime, playing = !v.paused;
    v.src = tab.dataset.src; v.currentTime = pos; if (playing) v.play();
    t.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === tab)); return; }
  const s = e.target.closest('[data-seek]');
  if (s) { const v = vidOf(s); wake(v); v.currentTime = +s.dataset.seek; v.pause(); return; }
  if (e.target.closest('#newv')) { swap(); return; }
  const row = e.target.closest('.fb[data-t]');
  if (row && !e.target.closest('.del') && +row.dataset.t < 1e8) {
    const v = vidOf(row); wake(v); v.currentTime = +row.dataset.t; v.pause(); return; }
  const d = e.target.closest('.del');
  if (d) { try { await post({text: '', delete: +d.dataset.at});
      const m = document.querySelector('.marks i[data-at="' + d.dataset.at + '"]'); if (m) m.remove();
      d.closest('.fb').remove(); label();
    } catch (err) { say(err.message, 'warn'); } }
});

// Wires up the comment boxes of the latest version. Runs at load and again
// after each swap.
function init() {
  box = $('#fb'); boxw = $('#fbw'); msg = $('#msg'); chip = $('#tc');
  if (!box) return;
  const v = vidOf(box);
  at = 0;
  // The timecode follows the playhead until you start typing, then it holds.
  v.addEventListener('timeupdate', () => {
    if (!box.value.trim()) { at = v.currentTime; chip.textContent = fmt(at); }
    // Light up the comment that belongs to what is on screen.
    document.querySelectorAll('.v.latest .fb[data-t]').forEach(r => {
      const t = +r.dataset.t; r.classList.toggle('now', t < 1e8 && v.currentTime >= t - 0.15 && v.currentTime < t + 1.5); });
  });
  // A half-typed timecode comment keeps its moment across a reload.
  try { const saved = parseFloat(localStorage.getItem(KEY + '-at'));
    if ((localStorage.getItem(KEY) || '').trim() && !isNaN(saved)) { at = saved;
      v.addEventListener('loadedmetadata', () => { v.currentTime = saved; }, {once: true});
      if (v.readyState >= 1) v.currentTime = saved; } } catch (e) {}
  [[box, KEY], [boxw, KEY + '-whole']].forEach(([el, key]) => {
    try { el.value = localStorage.getItem(key) || ''; } catch (e) {}
    grow(el);
    el.addEventListener('input', () => {
      grow(el);
      if (el === box) { if (el.value.trim()) v.pause(); try { localStorage.setItem(KEY + '-at', at); } catch (e) {} }
      try { localStorage.setItem(key, el.value); } catch (e) {} });
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(el); }
    });
  });
  chip.textContent = fmt(at); label();
}

// A new version never interrupts: it waits behind a button. Clicking it
// swaps the page content in place, with no reload. Typed text is kept.
function swap() {
  if (!fresh) return;
  const open = [...document.querySelectorAll('details.ver[open] > summary')].map(x => x.dataset.n);
  // Set as HTML rather than moving nodes: a <video> parsed in a detached
  // document never starts loading when it is moved into the page.
  $('main').innerHTML = fresh.doc.querySelector('main').innerHTML;
  $('header').innerHTML = fresh.doc.querySelector('header').innerHTML;
  document.querySelectorAll('main video[src]').forEach(v => v.load());
  document.querySelectorAll('details.ver[open] video').forEach(wake);
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
  const theirs = doc.querySelector('#clist'), mine = $('#clist');
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


def _video(files, base, feedback=None, seconds=1.0, changes=None, lazy=False):
    keys = list(files)
    if not keys:
        return ""
    src = lambda k: "%s/%s#t=0.1" % (base, files[k])
    tabs = ""
    if len(keys) > 1:
        tabs = "<div class='tabs'>%s</div>" % "".join(
            "<button class='%s' data-src='%s'>%s</button>" % ("on" if i == 0 else "", src(k), k)
            for i, k in enumerate(keys))
    pct = lambda t: 100.0 * t / max(seconds, 0.1)
    marks = "".join(
        "<i class='chg' style='left:%.2f%%' data-seek='%s' title='Changed: %s'></i>" % (
            pct(t), t, _e(c)) for c, t in (changes or []) if t is not None)
    marks += "".join(
        "<i class='%s' style='left:%.2f%%' data-seek='%s' data-at='%s' title='%s'></i>" % (
            "done" if f.get("status") == "done" else "", pct(f["t"]), f["t"], f["at"], _e(f["text"]))
        for f in (feedback or []) if f.get("t") is not None)
    # Earlier versions stay unloaded until opened, so a long history is instant.
    vid = ("<video data-src='%s' controls loop playsinline preload='none'></video>" if lazy
           else "<video src='%s' controls loop playsinline preload='metadata'></video>") % src(keys[0])
    return "<div class='stage'>%s<div class='marks'>%s</div>%s</div>" % (vid, marks, tabs)


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
        waiting = ("open", "requested", "note")
        rows = "".join(
            "<div class='fb' data-t='%s'>%s<div class='x'>%s<span class='st %s'>%s</span></div>%s</div>" % (
                f["t"] if f.get("t") is not None else 1e9,
                "<button class='tc' data-seek='%s'>%s</button>" % (f["t"], versions.tc(f["t"]))
                if f.get("t") is not None else "<span class='tc gen'>Whole video</span>",
                _e(f["text"]), "done" if f["status"] == "done" else "open",
                "Done in version %d" % f["done_in"] if f["status"] == "done"
                else ("Still waiting, from version %d" % f["from"] if f.get("from") else "Waiting"),
                "<button class='del' data-at='%d' title='Delete'>&times;</button>" % f["at"]
                if f["status"] in waiting and newest else "") for f in fbs)
        nch = len(v["changes"])
        cts = list(v.get("change_times") or []) + [None] * nch
        pairs = list(zip(v["changes"], cts))
        body = ["<h2>Version %d <small>%s &middot; %.1fs</small></h2>" % (
            v["n"], _when(v["at"]), v["seconds"])]
        if v.get("note"):
            body.append("<p class='lead'>%s</p>" % _e(v["note"]))
        # 1. What is different, and where to look.
        seen, jumps = set(), []
        for c, t in sorted(pairs, key=lambda x: (x[1] is None, x[1] or 0)):
            if t is None or round(t, 1) in seen:
                continue
            seen.add(round(t, 1))
            here = [x for x, y in pairs if y is not None and round(y, 1) == round(t, 1)]
            jumps.append("<button class='tc chgt' data-seek='%s' title='%s'>%s</button>" % (
                t, _e("\n".join(here)), versions.tc(t)))
        first = v["changes"] == ["First version"]
        if not first:
            body.append(
                "<details class='chg'><summary><span>%d change%s</span>%s</summary><ul>%s</ul></details>" % (
                    nch, "" if nch == 1 else "s",
                    "<span class='jumps'>%s</span>" % "".join(jumps) if jumps else "",
                    "".join("<li>%s<span>%s</span></li>" % (
                        "<button class='tc chgt' data-seek='%s'>%s</button>" % (t, versions.tc(t))
                        if t is not None else "<span class='tc gen'>All</span>", _e(c))
                        for c, t in pairs)))
        # 2. Which of your comments this version answered.
        if v.get("answers"):
            done_rows = []
            for line in v["answers"].split("\n"):
                m = re.match(r"^(\d+):(\d+(?:\.\d+)?)\s{2}(.*)$", line)
                if m:
                    t = int(m.group(1)) * 60 + float(m.group(2))
                    done_rows.append("<div class='fb done' data-t='%s'><button class='tc' data-seek='%s'>%s"
                                     "</button><div class='x'>%s</div></div>" % (
                                         t, t, versions.tc(t), _e(m.group(3))))
                else:
                    done_rows.append("<div class='fb done'><span class='tc gen'>Whole video</span>"
                                     "<div class='x'>%s</div></div>" % _e(
                                         re.sub(r"^Whole video\s{2}", "", line)))
            body.append("<details class='chg ans'><summary><span>%d comment%s addressed</span></summary>"
                        "%s</details>" % (len(done_rows), "" if len(done_rows) == 1 else "s",
                                          "".join(done_rows)))
        # 3. Your turn.
        if newest:
            body.append(
                "<div class='compose'><span class='tc' id='tc'>0:00.0</span>"
                "<textarea id='fb' rows='1' placeholder='Comment at this moment, then Enter'></textarea></div>"
                "<div class='compose two'><span class='tc gen'>Whole video</span>"
                "<textarea id='fbw' rows='1' placeholder='Comment on the whole video, then Enter'></textarea></div>"
                "<div class='msg' id='msg'></div>"
                "<div id='clist' data-v='%d'>%s</div>"
                "<div class='hint' id='hint'></div>"
                "<div class='keys'><kbd>Space</kbd> play <kbd>&larr;</kbd><kbd>&rarr;</kbd> 1s "
                "<kbd>,</kbd><kbd>.</kbd> frame <kbd>C</kbd> comment</div>" % (v["n"], rows))
        elif rows:
            body.append("<div class='clist'>%s</div>" % rows)
        card = "<section class='v%s'>%s<div class='side'>%s</div></section>" % (
            " latest" if newest else "",
            _video(files, "versions", v.get("feedback"), v.get("seconds", 1.0),
                   changes=pairs, lazy=not newest), "".join(body))
        if newest:
            cards.append(card)
        else:
            nf = len(fbs)
            older.append("<details class='ver'><summary data-n='%d'><b>Version %d</b>"
                         "<span class='sn'>%s</span><small>%s%s</small></summary>%s</details>" % (
                             v["n"], v["n"], _e(v.get("note") or "%d change%s" % (
                                 nch, "" if nch == 1 else "s")),
                             _when(v["at"]),
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
                     "<code>adstudio snapshot %s</code>, and then the comment boxes appear here."
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
            "<header><div><nav class='crumbs'><a href='/ads/index.html'>Projects</a><i>/</i>"
            "<a href='/ads/%s/index.html'>%s</a><i>/</i><b>%s</b>"
            "<span class='sub'>%d version%s</span></nav></div>%s</header>"
            "<main>%s</main><button id='newv' class='newv' hidden></button>"
            "<script>%s</script></body></html>") % (
        _e(name), CSS, _e(tl.get("brand", "")), _e(hub.brand_name(tl.get("brand", ""))), _e(name), len(h),
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
    try:
        hub.write_project(tl.get("brand", ""))
        hub.write_home()
    except Exception:          # an index page must never block an ad page
        pass
