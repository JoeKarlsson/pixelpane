// PixelPane control page. Talks to the board's HTTP API (see README).
const $ = s => document.querySelector(s);
// The board may require a token for writes (config "api_token"). We remember it in
// this browser and ask for it the first time the board says 401.
const tokenKey = 'pixelpane-token';
function authHeaders() {
  let t = null; try { t = localStorage.getItem(tokenKey); } catch (e) {}
  return t ? {'X-PixelPane-Token': t} : {};
}
function askToken() {
  return new Promise(resolve => {
    const dlg = document.getElementById('tokdlg'), inp = document.getElementById('tokinput');
    inp.value = ''; dlg.showModal();
    document.getElementById('toksave').onclick = () => {
      try { localStorage.setItem(tokenKey, inp.value.trim()); } catch (e) {}
      dlg.close(); resolve(true);
    };
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
const toast = t => { const el = $('#toast'); el.textContent = t; el.style.opacity = 1; setTimeout(() => el.style.opacity = 0, 1800); };
let S = {}, C = {}, rotation = [], gifFilter = 'everything', gifPage = 0;
let gifList = [], gifShown = [], selecting = false, lastPick = null;
const picked = new Set();

function btn(label, fn, cls, testid) {
  const b = document.createElement('button'); b.textContent = label; b.onclick = fn;
  if (cls) b.className = cls; if (testid) b.dataset.testid = testid; return b;
}

async function refresh() {
  S = await api('/api/state');
  $('#power').textContent = S.power ? 'Power: ON' : 'Power: OFF';
  $('#power').className = S.power ? 'on' : '';
  if (document.activeElement !== $('#bright')) $('#bright').value = S.brightness;
  $('#bv').textContent = S.brightness;
  $('#scene').textContent = S.pinned ? `pinned: ${S.pinned.scene}` : S.scene;
  if (S.panel) {   // preview takes the panel's shape; the LED grid matches its pixels
    const [cols, rows] = S.panel, w = cols >= rows ? 256 : Math.round(256 * cols / rows);
    $('#preview').style.width = w + 'px';
    $('.panel').style.setProperty('--led', (w / cols) + 'px');
  }
  $('#footver').textContent = S.version ? `version ${S.version}` : '';
  $('#stat').textContent = [S.temp_c ? S.temp_c.toFixed(0) + '°C' : null, S.throttled ? `throttled ${S.throttled}` : null,
    `up ${Math.round(S.uptime_s/3600)}h`, S.version].filter(Boolean).join(' · ');
  $('#themes').replaceChildren(...S.themes.map(t => { const s = document.createElement('span'); s.className = 'pill'; s.textContent = S.theme_names[t] || t; return s; }));
}

async function init() {
  await refresh();
  C = await api('/api/config');
  rotation = [...C.rotation];
  const cats = S.categories.map(c => 'gif:' + c);
  const scenes = [...(S.scenes.widget||[]), 'gif', ...cats, 'seasonal', 'generative'];
  $('#playnow').replaceChildren(...[...(S.scenes.widget||[]), 'gif', ...cats, 'seasonal','generative',
    ...Object.keys(S.theme_names), ...(S.scenes.generative||[])].map(s => btn(s.replace('_',' ').replace('gif:', 'gif: '),
      () => api('/api/play','POST',{scene:s}).then(() => toast('Up next: '+s)), '', 'play-' + s)));
  $('#nicon').replaceChildren(...S.icons.map(i => new Option(i, i)));
  $('#addsel').replaceChildren(...scenes.map(s => new Option(s, s)));
  $('#gtheme').replaceChildren(new Option('all year', 'all'), ...Object.entries(S.theme_names).map(([k, v]) => new Option(v, k)));
  drawRot(); drawDwell(); drawPlugins(); loadGifs(); pollNow();
}

function el(tag, props = {}, ...kids) {
  const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e;
}
const ago = s => s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;

function fieldInput(f, value) {
  const id = 'pf-' + f.key;
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
  const inp = el('input', {id, value: value ?? '', placeholder: f.placeholder || ''});
  return [inp, () => inp.value];
}

function openPlugin(name) {
  const p = S.plugins.find(x => x.name === name), dlg = $('#pdlg');
  const readers = {};
  const kids = [el('h3', {textContent: p.name.replace('_', ' ')}), el('div', {className: 'stat', textContent: p.description}),
    el('p', {className: 'about', textContent: p.about || ''})];
  const dwellKeys = [...new Set([...p.scenes.filter(sc => sc in C.dwell), ...(p.name in C.dwell ? [p.name] : [])])];
  if (p.scenes.length) {
    kids.push(el('div', {className: 'block'}, el('h2', {textContent: 'Scenes'}),
      el('div', {className: 'row'}, ...p.scenes.map(sc => btn('▶ ' + sc.replace('_', ' '),
        () => api('/api/play', 'POST', {scene: sc}).then(() => toast('Up next: ' + sc)), '', 'dlg-play-' + sc)))));
  }
  if (dwellKeys.length) {
    kids.push(el('div', {className: 'block'}, el('h2', {textContent: 'Seconds on screen'}), el('div', {className: 'dwell'},
      ...dwellKeys.map(k => { const inp = el('input', {type: 'number', min: 3, value: C.dwell[k], id: 'pd-' + k});
        readers['dwell:' + k] = () => +inp.value; return el('label', {}, k.replace('_', ' ') + ' ', inp); }))));
  }
  const keys = Object.keys(p.data || {});
  if (keys.length) {
    kids.push(el('div', {className: 'block'}, el('h2', {textContent: 'Data it takes'}),
      ...keys.map(k => el('div', {className: 'stat', textContent:
        `POST /api/data/${k} · ` + (k in S.data ? `last received ${ago(S.data[k])}` : 'nothing received yet') + ` · fresh for ${p.data[k]} min`}))));
  }
  if (p.fields.length) {
    const form = el('div', {className: 'block'}, el('h2', {textContent: 'Settings'}));
    for (const f of p.fields) {
      const [input, read] = fieldInput(f, p.settings[f.key]);
      readers[f.key] = read;
      form.append(el('div', {className: 'field'}, el('label', {htmlFor: 'pf-' + f.key, textContent: f.label}), input,
        ...(f.help ? [el('small', {textContent: f.help})] : [])));
    }
    kids.push(form);
  }
  const save = btn('Save', async () => {
    const settings = {}, dwell = {};
    for (const [k, read] of Object.entries(readers)) (k.startsWith('dwell:') ? (dwell[k.slice(6)] = read()) : (settings[k] = read()));
    C = await api('/api/config', 'PUT', {plugins: {[p.name]: settings}, ...(Object.keys(dwell).length ? {dwell} : {})});
    toast(`${p.name} saved`); dlg.close(); init();
  }, 'on', 'dlg-save');
  const toggle = btn(p.enabled ? 'Turn off' : 'Turn on', () =>
    api('/api/config', 'PUT', {plugins: {[p.name]: {enabled: !p.enabled}}}).then(() => { dlg.close(); init(); }), '', 'dlg-toggle');
  kids.push(el('div', {className: 'foot'}, toggle, btn('Close', () => dlg.close(), '', 'dlg-close'),
    ...(p.fields.length || dwellKeys.length ? [save] : [])));
  dlg.replaceChildren(...kids);
  dlg.showModal();
}

function drawPlugins() {
  $('#plugins').replaceChildren(...S.plugins.map(p => {
    const row = document.createElement('div'); row.className = 'plugin'; row.dataset.testid = 'plugin-' + p.name;
    row.title = 'Details and settings'; row.onclick = e => { if (!e.target.closest('button')) openPlugin(p.name); };
    const info = document.createElement('div');
    const name = document.createElement('strong'); name.textContent = p.name;
    const desc = document.createElement('small'); desc.textContent = p.description;
    info.append(name, desc);
    row.append(info, btn(p.enabled ? 'On' : 'Off', () =>
      api('/api/config', 'PUT', {plugins: {[p.name]: {enabled: !p.enabled}}})
        .then(() => init()).then(() => toast(`${p.name} ${p.enabled ? 'off' : 'on'}`)), p.enabled ? 'on' : ''));
    return row;
  }));
}

function drawRot() {
  $('#rot').replaceChildren(...rotation.map((s, i) => {
    const li = document.createElement('li'); li.dataset.index = i;
    const span = document.createElement('span'); span.textContent = `${i+1}. ${s}`; span.style.flex = 1;
    li.append(span, btn('↑', () => { if (i) { [rotation[i-1], rotation[i]] = [rotation[i], rotation[i-1]]; drawRot(); } }),
      btn('↓', () => { if (i < rotation.length-1) { [rotation[i+1], rotation[i]] = [rotation[i], rotation[i+1]]; drawRot(); } }),
      btn('✕', () => { rotation.splice(i, 1); drawRot(); }));
    return li;
  }));
}

function drawDwell() {
  $('#dwell').replaceChildren(...Object.entries(C.dwell).map(([k, v]) => {
    const l = document.createElement('label'); l.textContent = k + ' ';
    const inp = document.createElement('input'); inp.type = 'number'; inp.min = 3; inp.value = v;
    inp.onchange = () => api('/api/config', 'PUT', {dwell: {[k]: +inp.value}}).then(c => { C = c; toast('Saved'); });
    l.append(inp); return l;
  }));
}

async function loadGifs() {
  const list = gifList = await api('/api/gifs');
  const match = f => g => f === 'everything' ? true : f === 'all' ? g.theme === 'all'
    : f.startsWith('cat:') ? g.theme === 'all' && g.category === f.slice(4) : g.theme === f;
  const count = f => list.filter(match(f)).length;
  // Every option shows how many GIFs it holds, so nothing looks missing.
  const opts = [['everything', 'Everything'], ['all', 'All year (every day)'],
    ...S.categories.map(c => ['cat:' + c, `  All year: ${c}`]),
    ...Object.entries(S.theme_names).map(([k, v]) => [k, v])];
  $('#gfilter').replaceChildren(...opts.map(([v, label]) => new Option(`${label} (${count(v)})`, v)));
  $('#gfilter').value = gifFilter;
  $('#grename').hidden = !gifFilter.startsWith('cat:');
  $('#gcats').replaceChildren(...[...new Set(list.map(g => g.category))].sort().map(c => new Option(c)));
  for (const id of [...picked]) if (!list.some(g => g.id === id)) picked.delete(id);
  drawPicked();
  const all = list.filter(match(gifFilter));
  const size = +$('#gsize').value, pages = Math.max(1, Math.ceil(all.length / size));
  gifPage = Math.min(gifPage, pages - 1);
  const shown = gifShown = all.slice(gifPage * size, (gifPage + 1) * size);
  $('#gcount').textContent = `${all.length} match · ${list.length} in the library`;
  $('#gpage').textContent = `Page ${gifPage + 1} of ${pages}` + (all.length ? ` · ${gifPage * size + 1}-${gifPage * size + shown.length}` : '');
  $('#gprev').disabled = gifPage === 0; $('#gnext').disabled = gifPage >= pages - 1;
  $('#gifs').replaceChildren(...shown.map(g => {
    const d = document.createElement('div'); d.dataset.testid = 'gif-card'; d.dataset.id = g.id;
    d.className = 'gif' + (g.hidden ? ' hidden' : '') + (selecting ? ' selecting' : '') + (picked.has(g.id) ? ' picked' : '');
    if (selecting) {   // the whole card is the checkbox; shift-click picks a range
      d.tabIndex = 0; d.setAttribute('role', 'checkbox'); d.setAttribute('aria-checked', picked.has(g.id));
      d.setAttribute('aria-label', g.name);
      d.onclick = e => togglePick(g, e.shiftKey);
      d.onkeydown = e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); togglePick(g, e.shiftKey); } };
    }
    const cap = document.createElement('div'); cap.className = 'stat'; cap.style.fontSize = '11px';
    cap.style.overflowWrap = 'anywhere'; cap.textContent = g.name.replace(/\.gif$/i, '');
    const img = document.createElement('img'); img.loading = 'lazy'; img.src = '/gif/' + encodeURI(g.id); img.title = g.name;
    const r = document.createElement('div'); r.className = 'row';
    r.append(btn('▶', () => api('/api/play', 'POST', {scene:'gif', params:{id:g.id}}).then(() => toast('Up next'))),
      btn(g.hidden ? 'show' : 'hide', () => api('/api/gifs/hide', 'POST', {id:g.id, hidden:!g.hidden}).then(loadGifs)),
      btn('✎', () => openClassify([g]), '', 'classify'));
    if (g.upload) r.append(btn('🗑', () => confirmDelete(g)));
    d.append(img, cap, el('span', {className: 'cat' + (g.moved ? ' moved' : ''), textContent: g.category,
      title: g.moved ? `moved here from ${g.default_category}, ${g.default_theme.replace('_', ' ')}` : 'category'}));
    if (g.theme !== 'all') {
      const tag = document.createElement('span'); tag.className = 'pill theme'; tag.textContent = g.theme.replace('_', ' ');
      d.append(tag);
    }
    d.append(r); return d;
  }));
}

function togglePick(g, range) {
  const on = !picked.has(g.id), ids = gifShown.map(x => x.id);
  const from = range && lastPick ? ids.indexOf(lastPick) : -1, to = ids.indexOf(g.id);
  const span = from < 0 ? [g.id] : ids.slice(Math.min(from, to), Math.max(from, to) + 1);
  span.forEach(id => on ? picked.add(id) : picked.delete(id));
  lastPick = g.id;
  document.querySelectorAll('#gifs .gif').forEach(card => {
    const p = picked.has(card.dataset.id);
    card.classList.toggle('picked', p); card.setAttribute('aria-checked', p);
  });
  drawPicked();
}

function drawPicked() {
  $('#gbulk').hidden = !selecting;
  const here = gifShown.filter(g => picked.has(g.id)).length;
  $('#gselcount').textContent = picked.size
    ? `${picked.size} selected` + (here < picked.size ? ` (${here} on this page)` : '') : 'Click GIFs to pick them';
  const whole = gifShown.length && here === gifShown.length;
  $('#gselall').textContent = whole ? 'Unselect page' : 'Select page';
  $('#gmove').disabled = $('#gclear').disabled = !picked.size;
}

function themeOptions(keep) {
  return [...(keep ? [new Option("Keep each GIF's", '')] : []), new Option('All year', 'all'),
    ...Object.entries(S.theme_names).map(([k, v]) => new Option(v, k))];
}

// Move one GIF, or every selected one, to another category and/or theme.
function openClassify(gs) {
  const dlg = $('#gdlg'), one = gs.length === 1 ? gs[0] : null;
  $('#gdlgtitle').textContent = one ? 'Move ' + one.name.replace(/\.gif$/i, '') : `Move ${gs.length} GIFs`;
  $('#gdlgabout').textContent = one
    ? `Now: ${one.category}, ${one.theme === 'all' ? 'all year' : S.theme_names[one.theme] || one.theme}.` +
      (one.moved ? ` Its file says ${one.default_category}, ${one.default_theme.replace('_', ' ')}.` : '')
    : 'Changes only what you fill in.';
  $('#gdlgcat').value = one ? one.category : '';
  $('#gdlgtheme').replaceChildren(...themeOptions(!one));
  $('#gdlgtheme').value = one ? one.theme : '';
  $('#gdlgreset').hidden = !gs.some(g => g.moved);
  const done = async (body, msg) => {
    try { await api('/api/gifs/classify', 'POST', {ids: gs.map(g => g.id), ...body}); }
    catch (e) { return toast(e.message); }
    toast(msg); dlg.close(); picked.clear(); init();
  };
  $('#gdlgsave').onclick = () => {
    const category = $('#gdlgcat').value.trim(), theme = $('#gdlgtheme').value;
    done({...(category ? {category} : {}), ...(theme ? {theme} : {})}, one ? 'Moved' : `Moved ${gs.length} GIFs`);
  };
  $('#gdlgreset').onclick = () => done({reset: true}, 'Back to where the file is');
  $('#gdlgcancel').onclick = () => dlg.close();
  dlg.showModal();
}

$('#gselect').onclick = () => {
  selecting = !selecting; if (!selecting) { picked.clear(); lastPick = null; }
  $('#gselect').textContent = selecting ? 'Done' : 'Select';
  $('#gselect').setAttribute('aria-pressed', selecting); loadGifs();
};
$('#gselall').onclick = () => {
  const whole = gifShown.every(g => picked.has(g.id));
  gifShown.forEach(g => whole ? picked.delete(g.id) : picked.add(g.id)); loadGifs();
};
$('#gclear').onclick = () => { picked.clear(); lastPick = null; loadGifs(); };
$('#gmove').onclick = () => openClassify(gifList.filter(g => picked.has(g.id)));
$('#grename').onclick = () => {
  const old = gifFilter.slice(4), dlg = $('#rdlg');
  $('#rdlgabout').textContent = `Renames "${old}" on every GIF in it.`;
  $('#rdlgname').value = old;
  $('#rdlgcancel').onclick = () => dlg.close();
  $('#rdlgsave').onclick = async () => {
    let r;
    try { r = await api('/api/categories/rename', 'POST', {from: old, to: $('#rdlgname').value}); }
    catch (e) { return toast(e.message); }
    toast(`Renamed ${r.changed} GIFs`); dlg.close();
    gifFilter = 'cat:' + $('#rdlgname').value.trim().toLowerCase().replace(/[-\s]+/g, '_'); init();
  };
  dlg.showModal();
};

function confirmDelete(g) { api('/api/gifs/' + encodeURI(g.id), 'DELETE').then(() => { toast('Deleted ' + g.name); loadGifs(); }); }

$('#gfilter').onchange = e => { gifFilter = e.target.value; gifPage = 0; loadGifs(); };
$('#gsize').onchange = () => { gifPage = 0; loadGifs(); };
$('#gprev').onclick = () => { gifPage = Math.max(0, gifPage - 1); loadGifs(); };
$('#gnext').onclick = () => { gifPage += 1; loadGifs(); };
$('#gup').onclick = async () => {
  const files = $('#gfile').files; if (!files.length) return toast('Pick a file first');
  const fd = new FormData(); for (const f of files) fd.append('file', f);
  fd.append('theme', $('#gtheme').value); if ($('#gsmooth').checked) fd.append('smooth', '1');
  try { await send('/api/gifs', {method: 'POST', body: fd}); } catch (e) { return toast(e.message); }
  toast('Uploaded'); $('#gfile').value = ''; loadGifs();
};
$('#power').onclick = () => api('/api/state', 'POST', {power: !S.power}).then(refresh);
$('#bright').oninput = e => $('#bv').textContent = e.target.value;
$('#bright').onchange = e => api('/api/state', 'POST', {brightness: +e.target.value}).then(refresh);
document.querySelectorAll('[data-pin]').forEach(b => b.onclick = () =>
  api('/api/pin', 'POST', {scene: b.dataset.pin, minutes: +$('#mins').value || null}).then(refresh));
$('#pinmsg').onclick = () => api('/api/pin', 'POST', {scene:'message', params:{text: $('#msg').value || 'HELLO'}, minutes: +$('#mins').value || null}).then(refresh);
$('#unpin').onclick = () => api('/api/pin', 'DELETE').then(refresh);
$('#nsend').onclick = () => api('/api/notify', 'POST', {text: $('#ntext').value, icon: $('#nicon').value,
  color: $('#ncolor').value, flash: $('#nflash').checked}).then(() => toast('Sent'));
$('#skip').onclick = () => api('/api/skip', 'POST').then(() => toast('Skipped'));
$('#add').onclick = () => { rotation.push($('#addsel').value); drawRot(); };
$('#saverot').onclick = () => api('/api/config', 'PUT', {rotation}).then(c => { C = c; toast('Playlist saved'); });

const SOURCE = {playlist: n => `Playlist ${n.index + 1}/${n.length}`, requested: () => 'Requested',
  notification: () => 'Notification', pinned: () => 'Pinned', birthday: () => 'Birthday bonus',
  off: () => 'Off', starting: () => 'Starting'};

function prettyScene(label, entry) {
  if (!label) return '…';
  if (label.startsWith('gif: ')) {
    const name = label.slice(5).replace(/\.gif$/i, '');
    const [cat, ...rest] = name.split('-');
    return rest.length ? `GIF · ${cat} · ${rest.join(' ')}` : `GIF · ${name}`;
  }
  if (label.startsWith('empty: ')) return `${label.slice(7).replace('_', ' ')} (nothing to show)`;
  const nice = label.replace(/_/g, ' ');
  if (entry === 'seasonal') return `Seasonal · ${nice}`;
  if (entry === 'generative') return `Generative · ${nice}`;
  return nice.charAt(0).toUpperCase() + nice.slice(1);
}

async function pollNow() {
  const h = await api('/api/health');
  const n = h.now || {};
  $('#nowsrc').textContent = (SOURCE[n.source] || (() => n.source || '…'))(n);
  $('#nowscene').textContent = n.source === 'notification' ? `Notification · ${n.text || ''}` : prettyScene(h.scene, n.entry);
  const pct = n.seconds ? Math.min(100, 100 * (n.elapsed || 0) / n.seconds) : (n.source === 'pinned' ? 100 : 0);
  $('#nowbar').style.width = pct + '%';
  $('#nownext').textContent = n.next ? `Up next in the playlist: ${n.next.replace('_', ' ')}` : '';
  document.querySelectorAll('#rot li').forEach(li =>
    li.classList.toggle('current', n.source === 'playlist' && +li.dataset.index === n.index));
}

// Live preview: the board streams every frame as it shows it (see /api/frames) and we
// draw them on a canvas, so the preview runs at the panel's own speed.
let stream = null;
async function streamPreview() {
  if (stream || document.hidden) return;
  const ctl = stream = new AbortController(), cv = $('#preview'), g = cv.getContext('2d');
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

// Everything else updates on a timer, paused while the tab is in the background.
const live = fn => () => { if (!document.hidden) fn(); };
setInterval(live(() => pollNow().catch(() => {})), 2000);
setInterval(live(refresh), 10000);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { stream?.abort(); stream = null; }
  else { refresh(); pollNow().catch(() => {}); streamPreview(); }
});
streamPreview();
init().catch(e => $('#stat').textContent = 'error: ' + e.message);
