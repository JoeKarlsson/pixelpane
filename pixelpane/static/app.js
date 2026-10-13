// PixelPane control page. Talks to the board's HTTP API (see README).
// $, api, send, toast, el, btn, ago and showStatus come from common.js. The GIF maker
// and library are on /library (library.js).
let S = {}, C = {}, rotation = [];

async function refresh() {
  S = await api('/api/state');
  const sch = S.schedule || {};
  $('#power').textContent = !S.power ? 'Power: OFF' : sch.off ? 'Power: OFF (schedule)' : 'Power: ON';
  $('#power').className = S.on ? 'on' : '';
  $('#power').title = sch.off ? 'Quiet hours: press to turn on anyway until they end' : '';
  $('#sched').hidden = !(sch.rules || []).length;
  $('#sched').textContent = sch.off ? `Scheduled off until ${clockTime(sch.until)}`
    : sch.overridden ? `On anyway, quiet hours end ${clockTime(sch.until)}`
    : [sch.brightness != null ? `Dimmed to ${sch.brightness}` : null, sch.playlist ? 'Scheduled playlist' : null]
        .filter(Boolean).join(' · ') || `Schedule: ${sch.rules?.join(', ')}`;
  if (document.activeElement !== $('#bright')) $('#bright').value = S.brightness;
  $('#bv').textContent = S.brightness;
  $('#scene').textContent = S.pinned ? `pinned: ${S.pinned.scene}` : S.scene;
  if (S.panel) {   // preview takes the panel's shape; the LED grid matches its pixels
    const [cols, rows] = S.panel, w = cols >= rows ? 256 : Math.round(256 * cols / rows);
    $('#preview').style.width = w + 'px';
    $('.panel').style.setProperty('--led', (w / cols) + 'px');
  }
  showStatus(S);
  $('#themes').replaceChildren(...S.themes.map(t => { const s = document.createElement('span'); s.className = 'pill'; s.textContent = S.theme_names[t] || t; return s; }));
}

async function init() {
  await refresh();
  C = await api('/api/config');
  rotation = [...C.rotation];
  const cats = S.categories.map(c => 'gif:' + c);
  drawPlayNow(cats);
  $('#nicon').replaceChildren(...S.icons.map(i => new Option(i, i)));
  $('#addsel').replaceChildren(...[...(S.scenes.widget||[]), 'gif', ...cats, 'seasonal', 'generative', 'ambient'].map(s => new Option(s, s)));
  drawRot(); drawPlugins(); pollNow(); pluginFromHash();
}

// /#plugin=generator (the GIFs page links here) opens that plugin's settings
function pluginFromHash() {
  const want = new URLSearchParams(location.hash.slice(1)).get('plugin');
  if (want && S.plugins?.some(p => p.name === want) && !$('#pdlg').open) openPlugin(want);
}
window.addEventListener('hashchange', pluginFromHash);

// Play now, grouped: everyday scenes and generative art as buttons; the longer lists
// (holidays and seasons, GIF categories) fold away until you open them.
function drawPlayNow(cats) {
  const play = s => btn(s.replace(/_/g, ' ').replace('gif:', ''),
    () => api('/api/play', 'POST', {scene: s}).then(() => toast('Up next: ' + s)), '', 'play-' + s);
  const group = (title, list, fold) => {
    if (!list.length) return null;
    const row = el('div', {className: 'row'}, ...list.map(play));
    return fold ? el('details', {className: 'group'}, el('summary', {textContent: `${title} (${list.length})`}), row)
      : el('div', {className: 'group'}, el('div', {className: 'stat', textContent: title}), row);
  };
  $('#playnow').replaceChildren(...[
    group('Scenes', [...(S.scenes.widget || []), 'gif', 'seasonal', 'generative', 'ambient']),
    group('Art', S.scenes.generative || []),
    group('Holidays and seasons', S.scenes.seasonal || [], true),
    group('GIF categories', cats, true),
  ].filter(Boolean));
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
    const [form, read] = pluginForm(p);
    for (const [k, r] of Object.entries(read)) readers[k] = r;
    kids.push(el('div', {className: 'block'}, el('h2', {textContent: 'Settings'}), form));
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
  const errs = S.plugin_errors || [];
  $('#pluginerrs').hidden = !errs.length;
  $('#pluginerrs').replaceChildren(...errs.map(e => el('div', {textContent: `⚠ ${e.source} didn't load: ${e.error}`})));
  $('#plugins').replaceChildren(...S.plugins.map(p => {
    const row = document.createElement('div'); row.className = 'plugin'; row.dataset.testid = 'plugin-' + p.name;
    row.title = 'Details and settings'; row.onclick = e => { if (!e.target.closest('button')) openPlugin(p.name); };
    row.tabIndex = 0; row.setAttribute('role', 'button'); row.setAttribute('aria-label', `${p.name} details and settings`);
    row.onkeydown = e => { if (e.target === row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openPlugin(p.name); } };
    const info = document.createElement('div');
    const name = document.createElement('strong'); name.textContent = p.name;
    const desc = document.createElement('small'); desc.textContent = p.description;
    info.append(name, desc);
    const crashed = (p.tasks || []).filter(t => t.crashes);
    if (p.source !== 'built-in' || p.version) info.append(el('small', {textContent: [p.source, p.version && 'v' + p.version].filter(Boolean).join(' · ')}));
    if (crashed.length) info.append(el('small', {className: 'warn', textContent: `⚠ task crashed: ${crashed[0].last_error}`}));
    row.append(info, btn(p.enabled ? 'On' : 'Off', () =>
      api('/api/config', 'PUT', {plugins: {[p.name]: {enabled: !p.enabled}}})
        .then(() => init()).then(() => toast(`${p.name} ${p.enabled ? 'off' : 'on'}`)), p.enabled ? 'on' : ''));
    return row;
  }));
}

// Move playlist entry `from` to position `to` (drag and drop, or the arrows).
function moveRot(from, to) {
  if (from === to || to < 0 || to >= rotation.length) return;
  rotation.splice(to, 0, ...rotation.splice(from, 1));
  drawRot();
}

function drawRot() {
  $('#rot').replaceChildren(...rotation.map((s, i) => {
    const li = document.createElement('li'); li.dataset.index = i; li.draggable = true;
    li.ondragstart = e => { e.dataTransfer.setData('text/plain', String(i)); e.dataTransfer.effectAllowed = 'move'; li.classList.add('dragging'); };
    li.ondragend = () => li.classList.remove('dragging');
    li.ondragover = e => { e.preventDefault(); li.classList.add('over'); };
    li.ondragleave = () => li.classList.remove('over');
    li.ondrop = e => { e.preventDefault(); moveRot(+e.dataTransfer.getData('text/plain'), i); };
    const grip = el('span', {className: 'grip', textContent: '⠿', ariaHidden: 'true'});
    const span = el('span', {className: 'name', textContent: `${i+1}. ${s}`});
    li.append(grip, span, btn('↑', () => moveRot(i, i - 1), '', '', 'Move up'),
      btn('↓', () => moveRot(i, i + 1), '', '', 'Move down'),
      btn('✕', () => { rotation.splice(i, 1); drawRot(); }, '', '', 'Remove'));
    return li;
  }));
  // Edits stay in the page until Save playlist, so say when there are some.
  const dirty = JSON.stringify(rotation) !== JSON.stringify(C.rotation);
  $('#saverot').textContent = dirty ? 'Save playlist •' : 'Save playlist';
  $('#rotdirty').hidden = !dirty;
}

// Toggles what the panel actually shows: during quiet hours this turns it on anyway.
$('#power').onclick = () => api('/api/state', 'POST', {power: !S.on}).then(refresh);
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
$('#saverot').onclick = () => api('/api/config', 'PUT', {rotation}).then(c => { C = c; drawRot(); toast('Playlist saved'); });
window.addEventListener('beforeunload', e => {
  if (C.rotation && JSON.stringify(rotation) !== JSON.stringify(C.rotation)) e.preventDefault();
});

const SOURCE = {playlist: n => `Playlist ${n.index + 1}/${n.length}`, requested: () => 'Requested',
  notification: () => 'Notification', pinned: () => 'Pinned', birthday: () => 'Birthday bonus',
  off: () => 'Off', schedule: () => 'Quiet hours', starting: () => 'Starting'};

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
  if (entry === 'ambient') return `Ambient · ${nice}`;
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
