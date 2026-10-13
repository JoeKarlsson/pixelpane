// Shared by the control page and the settings page: API calls (with the optional
// token), toasts and small DOM helpers.
const $ = s => document.querySelector(s);
// The board may require a token for writes (config "api_token"). We remember it in
// this browser and ask for it the first time the board says 401.
const tokenKey = 'pixelpane-token';
function authHeaders() {
  let t = null; try { t = localStorage.getItem(tokenKey); } catch (e) {}
  return t ? {'X-PixelPane-Token': t} : {};
}
function rememberToken(t) {
  try { t ? localStorage.setItem(tokenKey, t) : localStorage.removeItem(tokenKey); } catch (e) {}
}
function askToken() {
  return new Promise(resolve => {
    const dlg = document.getElementById('tokdlg'), inp = document.getElementById('tokinput');
    inp.value = ''; dlg.showModal();
    document.getElementById('toksave').onclick = () => { rememberToken(inp.value.trim()); dlg.close(); resolve(true); };
    document.getElementById('tokcancel').onclick = () => { dlg.close(); resolve(false); };
  });
}
async function send(path, opts, retry = true) {
  const r = await fetch(path, {...opts, headers: {...(opts.headers || {}), ...authHeaders()}});
  if (r.status === 401 && retry && await askToken()) return send(path, opts, false);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || await r.text());
  return r;
}
const api = (path, method = 'GET', body) => send(path, {method, headers: body ? {'Content-Type': 'application/json'} : {},
  body: body ? JSON.stringify(body) : undefined}).then(r => r.json());
let toastTimer = null;
const toast = t => {
  const e = $('#toast'); e.textContent = t; e.style.opacity = 1;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => e.style.opacity = 0, t.length > 60 ? 4000 : 1800);
};

function el(tag, props = {}, ...kids) {
  const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e;
}
// label: what the button shows; name: what it's called for screen readers and on
// hover, for buttons that show only a symbol (↑, ✕, 🗑).
function btn(label, fn, cls, testid, name) {
  const b = document.createElement('button'); b.textContent = label; b.onclick = fn;
  if (cls) b.className = cls; if (testid) b.dataset.testid = testid;
  if (name) { b.setAttribute('aria-label', name); b.title = name; }
  return b;
}
// A click whose API call fails says why instead of failing silently.
window.addEventListener('unhandledrejection', e => toast(e.reason?.message || 'Something went wrong'));
const ago = s => s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
// "until" from the API is local wall time, "2026-10-16T07:00": show it as 7:00 AM
const clockTime = iso => iso ? new Date(iso).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) : '';
// The header's status pill and the footer's version, from /api/state or /api/health.
function showStatus(S) {
  $('#stat').textContent = [S.temp_c ? S.temp_c.toFixed(0) + '°C' : null, S.throttled ? `throttled ${S.throttled}` : null,
    `up ${Math.round(S.uptime_s / 3600)}h`, S.version].filter(Boolean).join(' · ');
  const v = document.getElementById('footver');
  if (v) v.textContent = S.version ? `version ${S.version}` : '';
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
    const d = el('input', {type: 'number', id: id + '-day', min: 1, max: 31, placeholder: 'Day', value: v.day || ''});
    const n = el('input', {id: id + '-name', placeholder: 'Name', value: v.name || ''});
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

// Live preview: the board streams every frame as it shows it (see /api/frames) and we
// draw them on a canvas, so the preview runs at the panel's own speed.
let stream = null;
let previewSel = null;
async function streamPreview() {
  if (stream || document.hidden || !previewSel) return;
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
  if (!document.hidden) setTimeout(streamPreview, 2000);   // the board restarted or the stream timed out
}
function drawFrame(cv, g, cols, rows, rgb) {
  if (cv.width !== cols || cv.height !== rows) { cv.width = cols; cv.height = rows; }
  const img = g.createImageData(cols, rows);
  for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
    img.data[j] = rgb[i]; img.data[j + 1] = rgb[i + 1]; img.data[j + 2] = rgb[i + 2]; img.data[j + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}

// Start the live preview on a canvas; it pauses while the tab is in the background.
function startPreview(sel) {
  previewSel = sel;
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stream?.abort(); stream = null; } else streamPreview();
  });
  streamPreview();
}

// A Play now button's little animated preview of its scene (see /api/scenes/<name>/thumb.gif).
// Scenes with nothing to show, GIFs and categories get none.
function sceneThumb(scene) {
  if (scene?.startsWith('gif:')) scene = 'gif';   // GIF categories share the GIF icon
  if (!scene || scene.includes(':')) return [];
  const img = el('img', {className: 'thumb', src: `/api/scenes/${encodeURIComponent(scene)}/thumb.gif`, alt: '', loading: 'lazy',
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
