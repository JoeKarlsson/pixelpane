// Shared by the control page and the settings page: API calls, toasts and small DOM helpers.
const $ = s => document.querySelector(s);
// An error shown next to what failed (role="alert", so it's announced), not only in a toast.
function showError(target, msg) {
  const box = typeof target === 'string' ? $(target) : target;
  box.textContent = msg || '';
  if (msg) toast(msg, true);
}
async function send(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || await r.text());
  return r;
}
const api = (path, method = 'GET', body) => send(path, {method, headers: body ? {'Content-Type': 'application/json'} : {},
  body: body ? JSON.stringify(body) : undefined}).then(r => r.json());
let toastTimer = null;
const calmMotion = matchMedia('(prefers-reduced-motion: reduce)');
// app.css's motion curves, read once, so JS animations use the same ones
const EASE_ENTER = getComputedStyle(document.documentElement).getPropertyValue('--ease-enter').trim();
// failed: true for errors, which are announced at once (assertive) instead of politely
const toast = (t, failed = false) => {
  const e = $('#toast'), again = e.classList.contains('show');
  e.ariaLive = failed ? 'assertive' : 'polite';
  e.textContent = t; e.classList.add('show');
  if (again && !calmMotion.matches) e.animate([{scale: .97}, {scale: 1}], {duration: 180, easing: EASE_ENTER});
  clearTimeout(toastTimer); toastTimer = setTimeout(() => e.classList.remove('show'), t.length > 60 ? 4000 : 1800);
};

function el(tag, props = {}, ...kids) {
  const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e;
}
// Icons for buttons that show only a symbol: drawn here, so they don't depend on which
// fonts the phone has (arrows and emoji fell back to faint hooks or color emoji).
const ICONS = {
  up: 'M8 13V3M4 7l4-4 4 4', down: 'M8 3v10M4 9l4 4 4-4', x: 'M4 4l8 8M12 4l-8 8',
  edit: 'M3 13l1-3.5 7-7 2.5 2.5-7 7z', trash: 'M2.5 4h11M6 4V2h4v2M4 4l1 10h6l1-10',
  undo: 'M4 7h6a3 3 0 010 6H7M6.5 4L3.5 7l3 3', redo: 'M12 7H6a3 3 0 000 6h3M9.5 4l3 3-3 3',
  play: 'F M5 3l8 5-8 5z', prev: 'F M11 3L5 8l6 5z', next: 'F M5 3l6 5-6 5z',
  grip: 'F ' + [3, 8, 13].map(y => `M5 ${y}a1.25 1.25 0 1 0 2.5 0a1.25 1.25 0 1 0-2.5 0M8.5 ${y}a1.25 1.25 0 1 0 2.5 0a1.25 1.25 0 1 0-2.5 0`).join(''),
};
function icon(name) {
  const ns = 'http://www.w3.org/2000/svg', d = ICONS[name], filled = d.startsWith('F ');
  const svg = document.createElementNS(ns, 'svg'), path = document.createElementNS(ns, 'path');
  svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('width', '16'); svg.setAttribute('height', '16');
  svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', 'icon'); svg.dataset.icon = name;
  path.setAttribute('d', filled ? d.slice(2) : d);
  path.setAttribute('fill', filled ? 'currentColor' : 'none');
  if (!filled) { path.setAttribute('stroke', 'currentColor'); path.setAttribute('stroke-width', '1.75'); path.setAttribute('stroke-linejoin', 'round'); }
  svg.append(path);
  return svg;
}
// What people call a playlist entry: "gif:film" is "GIFs: film", "now_playing" is "now playing".
const sceneLabel = s => s === 'gif' ? 'GIFs' : s.startsWith('gif:') ? 'GIFs: ' + s.slice(4).replace(/_/g, ' ') : s.replace(/_/g, ' ');
// label: what the button shows; name: what it's called for screen readers and on
// hover, for buttons that show only a symbol (↑, ✕, 🗑).
function btn(label, fn, cls, testid, name) {
  const b = document.createElement('button'); b.append(label); b.onclick = busy(fn);
  if (cls) b.className = cls; if (testid) b.dataset.testid = testid;
  if (name) { b.setAttribute('aria-label', name); b.title = name; }
  return b;
}
// A toggle's state for screen readers and its look: aria-pressed plus the .on fill.
function setPressed(b, on) { b.setAttribute('aria-pressed', on); b.classList.toggle('on', on); }
// A button whose label changes (Play/Stop, Select/Done) crossfades between two labels
// stacked in one grid cell, so the button keeps its width and doesn't jump. The hidden
// one is aria-hidden, so the button's accessible name is only the shown label.
// The label is text or an icon().
function setLabel(b, label) {
  let [a, z] = b.querySelectorAll(':scope > .swap > span');
  if (!a) {
    a = el('span', {}, ...b.childNodes); z = el('span'); z.setAttribute('aria-hidden', 'true');
    b.append(el('span', {className: 'swap'}, a, z));
    getComputedStyle(z).opacity;   // style the new cell before flipping it, so the first swap fades too
  }
  const shown = a.hasAttribute('aria-hidden') ? z : a, other = shown === a ? z : a;
  const same = typeof label === 'string' ? shown.textContent === label && !shown.querySelector('svg')
    : shown.firstElementChild?.dataset.icon === label.dataset.icon;
  if (same) return;
  other.replaceChildren(label);
  other.removeAttribute('aria-hidden'); shown.setAttribute('aria-hidden', 'true');
}
// Wraps a click handler: while the promise it returns runs, its button ignores clicks, so a
// double tap can't send the request twice (two skips). aria-disabled, not disabled, so focus
// stays on the button.
function busy(fn) {
  return function (e) {
    const b = e?.currentTarget;
    if (b?.ariaBusy === 'true') return;
    const r = fn.call(this, e);
    if (b && r && typeof r.finally === 'function') {
      b.ariaDisabled = b.ariaBusy = 'true';
      r.finally(() => { b.ariaDisabled = b.ariaBusy = null; });
    }
    return r;
  };
}
// A click whose API call fails says why instead of failing silently.
window.addEventListener('unhandledrejection', e => toast(e.reason?.message || 'Something went wrong', true));
// How long the board has been up: "42m" under an hour, then "5h 12m".
const upFor = s => s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
const ago = s => s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
// "until" from the API is local wall time, "2026-10-16T07:00": show it as 7:00 AM
const clockTime = iso => iso ? new Date(iso).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) : '';
// The page's one color is whatever the board is showing (live_color, sampled on the board);
// CSS crossfades --live, so a new scene re-tints the page.
function applyLive(color) { if (color) document.documentElement.style.setProperty('--live', color); }
// The header's status, the footer's version and the page color, from /api/state or /api/health.
function showStatus(S) {
  applyLive(S.live_color);
  $('#stat').textContent = [S.temp_c ? S.temp_c.toFixed(0) + '°C' : null, S.throttled && S.throttled !== '0x0' ? `throttled ${S.throttled}` : null,
    `up ${upFor(S.uptime_s)}`].filter(Boolean).join(', ');   // the version is in the footer
  const v = document.getElementById('footver');
  if (v) v.textContent = S.version || '';
}

// --- plugin settings forms (control page dialogs and the Settings page) ---------

function fieldInput(f, value, id = 'pf-' + f.key) {
  if (f.type === 'items') return itemsInput(f, value, id);
  if (f.type === 'range') {
    const out = el('span', {className: 'stat', textContent: value ?? ''});
    const inp = el('input', {type: 'range', id, min: f.min ?? 0, max: f.max ?? 1, step: f.step ?? .05, value: value ?? f.min ?? 0});
    inp.oninput = () => out.textContent = inp.value;
    return [el('div', {className: 'row'}, inp, out), () => +inp.value];
  }
  if (f.type === 'number') {
    const inp = el('input', {type: 'number', id, step: f.step ?? 'any', value: value ?? ''});
    return [inp, () => inp.value === '' ? null : +inp.value];
  }
  if (f.type === 'list') {
    const ta = el('textarea', {id, placeholder: f.placeholder || '', value: (value || []).join('\n')});
    return [ta, () => ta.value.split('\n').map(x => x.trim()).filter(Boolean)];
  }
  if (f.type === 'choices') {
    const boxes = f.options.map(o => el('label', {}, el('input', {type: 'checkbox', value: o, checked: (value || []).includes(o)}), o.replace('_', ' ')));
    return [el('div', {className: 'checks', id}, ...boxes), () => boxes.map(b => b.firstChild).filter(c => c.checked).map(c => c.value)];
  }
  if (f.type === 'monthday') {
    const v = value || {};
    const m = el('select', {id: id + '-month'}, new Option('Month', ''), ...['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map((n, i) => new Option(n, i + 1)));
    m.value = v.month || '';
    const d = el('input', {type: 'number', id: id + '-day', min: 1, max: 31, placeholder: 'Day', value: v.day || '', ariaLabel: 'Day'});
    const n = el('input', {id: id + '-name', placeholder: 'Name', value: v.name || '', ariaLabel: 'Name'});
    m.ariaLabel = 'Month';
    return [el('div', {className: 'md'}, m, d, n), () => m.value && d.value ? {month: +m.value, day: +d.value, name: n.value.trim()} : null];
  }
  if (f.type === 'secret') {
    const inp = el('input', {type: 'password', id, value: value ?? '', placeholder: f.placeholder || '', autocomplete: 'off'});
    return [inp, () => inp.value];
  }
  if (f.type === 'select') {
    const sel = el('select', {id}, ...f.options.map(o => new Option(o.label, o.value)));
    sel.value = value ?? f.options[0].value;
    return [sel, () => sel.value];
  }
  if (f.type === 'color') {
    const inp = el('input', {type: 'color', id, value: value || '#ffffff'});
    return [inp, () => inp.value];
  }
  if (f.type === 'toggle') {
    const box = el('input', {type: 'checkbox', id, checked: value !== false});
    return [el('label', {className: 'toggle'}, box, f.text || 'On'), () => box.checked];
  }
  const inp = el('input', {id, value: value ?? '', placeholder: f.placeholder || '', ...(f.maxlength ? {maxLength: f.maxlength} : {})});
  return [inp, () => inp.value];
}

// One labelled form row for a field (or a sub-field of an items field).
function fieldRow(f, value, id) {
  const [input, read] = fieldInput(f, value, id);
  const row = el('div', {className: 'field' + (f.type === 'items' ? ' wide' : '')},
    el('label', {htmlFor: id, textContent: f.label}), input, ...(f.help ? [el('small', {textContent: f.help})] : []));
  return [row, read];
}

// "items": a list of small records (overlays, reminders...), each a card of sub-fields.
// A sub-field with show_when: {key: [values]} only shows while that sub-field has one of them.
function itemsInput(f, value, id) {
  const list = el('div', {className: 'items', id}), rows = [];
  const add = item => {
    const readers = {}, wraps = {};
    const card = el('div', {className: 'item'});
    const n = rows.length + Math.random().toString(36).slice(2, 6);
    for (const sf of f.fields) {
      const [row, read] = fieldRow(sf, item[sf.key] ?? sf.default, `${id}-${n}-${sf.key}`);
      readers[sf.key] = read; wraps[sf.key] = row; card.append(row);
    }
    const sync = () => {
      for (const sf of f.fields) {
        const when = sf.show_when; if (!when) continue;
        wraps[sf.key].hidden = !Object.entries(when).every(([k, vals]) => vals.includes(readers[k]()));
      }
    };
    card.addEventListener('change', sync); sync();
    const entry = {card, read: () => Object.fromEntries(f.fields.map(sf => [sf.key, readers[sf.key]()]))};
    card.append(el('div', {className: 'itemfoot'}, btn('Remove', () => { card.remove(); rows.splice(rows.indexOf(entry), 1); },
      '', `${id}-remove`, `Remove this ${(f.item_label || 'item').toLowerCase()}`)));
    rows.push(entry); list.append(card);
  };
  (value || []).forEach(add);
  const addBtn = btn('+ ' + (f.add_label || 'Add'), () => {
    if (rows.length >= (f.max || 20)) return toast(`At most ${f.max || 20}`);
    add(Object.fromEntries(f.fields.map(sf => [sf.key, sf.default])));
  }, '', `${id}-add`);
  return [el('div', {}, list, addBtn), () => rows.map(r => r.read())];
}

// A plugin's whole settings form: [node, {key: reader}].
function pluginForm(p, prefix = 'pf-') {
  const form = el('div', {className: 'pform'}), readers = {};
  for (const f of p.fields) {
    const [row, read] = fieldRow(f, p.settings[f.key], prefix + f.key);
    readers[f.key] = read; form.append(row);
  }
  return [form, readers];
}

// Safari has no closedby yet: there, a press outside a dialog[closedby=any] closes it too.
// (A press on the backdrop lands on the dialog itself, at a point outside its box. Not
// click: a text selection dragged out of a field ends as a click on the dialog.)
if (!('closedBy' in HTMLDialogElement.prototype)) {
  document.addEventListener('pointerdown', e => {
    const d = e.target;
    if (!(d instanceof HTMLDialogElement) || !d.open || d.getAttribute('closedby') !== 'any') return;
    const r = d.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close();
  });
}

// Live preview: the board streams every frame as it shows it (see /api/frames) and we
// draw them on a canvas, so the preview runs at the panel's own speed.
let stream = null;
let previewSel = null, previewWanted = () => true;
async function streamPreview() {
  if (stream || document.hidden || !previewSel || !previewWanted()) return;
  const ctl = stream = new AbortController(), cv = $(previewSel), g = cv.getContext('2d');
  try {
    const r = await fetch('/api/frames', {signal: ctl.signal, cache: 'no-store'});
    if (!r.ok || !r.body) throw new Error('no stream');
    const reader = r.body.getReader();
    let buf = new Uint8Array(0);
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      const joined = new Uint8Array(buf.length + value.length); joined.set(buf); joined.set(value, buf.length); buf = joined;
      let latest = null;   // a slow tab skips straight to the newest whole frame
      while (buf.length >= 4) {
        const cols = buf[0] << 8 | buf[1], rows = buf[2] << 8 | buf[3], end = 4 + cols * rows * 3;
        if (buf.length < end) break;
        latest = [cols, rows, buf.subarray(4, end)]; buf = buf.slice(end);
      }
      if (latest) drawFrame(cv, g, ...latest);
    }
  } catch (e) { if (ctl.signal.aborted) return; }
  if (stream === ctl) stream = null;
  if (!document.hidden && previewWanted()) setTimeout(streamPreview, 2000);   // the board restarted or the stream timed out
}
function drawFrame(cv, g, cols, rows, rgb) {
  if (cv.width !== cols || cv.height !== rows) { cv.width = cols; cv.height = rows; }
  const img = g.createImageData(cols, rows);
  for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
    img.data[j] = rgb[i]; img.data[j + 1] = rgb[i + 1]; img.data[j + 2] = rgb[i + 2]; img.data[j + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}

// Start the live preview on a canvas; it pauses while the tab is in the background, and
// while wanted() says nobody can see it (each stream costs the Pi CPU).
function stopPreview() { stream?.abort(); stream = null; }
function startPreview(sel, wanted = () => true) {
  previewSel = sel; previewWanted = wanted;
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopPreview(); else streamPreview(); });
  streamPreview();
}

// GIF previews show their first frame only when the device asks for less motion or
// "Still previews" is on (a checkbox on the GIFs page, remembered in this browser).
function stillPreviews() {
  try { return localStorage.getItem('pixelpane-still') === '1'; } catch (e) { return false; }   // storage blocked: nothing was saved
}
const stillGifs = () => calmMotion.matches || stillPreviews() ? '?still=1' : '';
// A Play now button's little animated preview of its scene (see /api/scenes/<name>/thumb.gif).
// Scenes with nothing to show yet get an icon (GIF categories share the GIF one).
function sceneThumb(scene) {
  if (scene?.startsWith('gif:')) scene = 'gif';   // GIF categories share the GIF icon
  if (!scene || scene.includes(':')) return [];
  const img = el('img', {className: 'thumb', src: `/api/scenes/${encodeURIComponent(scene)}/thumb.gif${stillGifs()}`, alt: '', loading: 'lazy',
    width: 32, height: 32});
  img.onerror = () => img.remove();
  return [img];
}
// A button that plays a scene next, with its preview.
function playButton(scene, testid, label) {
  const b = btn('', () => api('/api/play', 'POST', {scene}).then(() => toast('Up next: ' + scene.replace(/_/g, ' '))), 'scenebtn', testid);
  b.append(...sceneThumb(scene), el('span', {textContent: label ?? scene.replace(/_/g, ' ').replace('gif:', '')}));
  return b;
}
