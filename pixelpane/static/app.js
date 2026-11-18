// PixelPane control page. Talks to the board's HTTP API (see README).
// $, api, send, toast, el, btn, ago and showStatus come from common.js. The GIF maker
// and library are on /library (library.js).
let S = {}, C = {}, rotation = [], rotIds = [], nextRotId = 0;   // ids: follow each entry as it moves (flipRot)

// The timer and Power only need /api/health (under 1 KB); the full state (36 KB) loads in init.
async function refresh() {
  S = {...S, ...await api('/api/health')};
  const sch = S.schedule || {};
  setLabel($('#power'), !S.power ? 'Power: OFF' : sch.off ? 'Power: OFF (schedule)' : 'Power: ON');   // keeps its width
  setPressed($('#power'), S.on);   // a switch: lit outline when on
  $('#power').title = sch.off ? 'Quiet hours: press to turn on anyway until they end' : '';
  $('#sched').hidden = !(sch.rules || []).length;
  $('#sched').textContent = sch.off ? `Scheduled off until ${clockTime(sch.until)}`
    : sch.overridden ? `On anyway, quiet hours end ${clockTime(sch.until)}`
    : [sch.brightness != null ? `Dimmed to ${sch.brightness}` : null, sch.playlist ? 'Scheduled playlist' : null]
        .filter(Boolean).join(', ') || `Schedule: ${sch.rules?.join(', ')}`;
  if (document.activeElement !== $('#bright')) $('#bright').value = S.brightness;
  $('#bv').textContent = S.brightness;
  // only for a pin: the Now line below already names the scene, and updates faster
  $('#scene').hidden = !S.pinned;
  $('#scene').textContent = S.pinned ? `pinned: ${S.pinned.scene}` : '';
  const onAir = S.pinned?.scene === 'on_air', airBtn = document.querySelector('[data-pin=on_air]');
  airBtn.classList.toggle('on', onAir); airBtn.setAttribute('aria-pressed', onAir);
  if (S.panel) $('.panel').style.setProperty('--led', `calc(100% / ${S.panel[0]})`);   // one round lamp per panel pixel
  showStatus(S);
  $('#themes').replaceChildren(...S.themes.map(t => { const s = document.createElement('span'); s.className = 'pill'; s.textContent = S.theme_names?.[t] || t; return s; }));
}

async function init() {
  S = await api('/api/state');
  await refresh();
  C = await api('/api/config');
  rotation = [...C.rotation]; rotIds = rotation.map((_, i) => i); nextRotId = rotation.length;
  const cats = S.categories.map(c => 'gif:' + c);
  drawPlayNow(cats);
  $('#nicon').replaceChildren(...S.icons.map(i => new Option(i, i)));
  $('#addsel').replaceChildren(...[...(S.scenes.widget||[]), 'gif', ...cats, 'seasonal', 'generative', 'ambient'].map(s => new Option(sceneLabel(s), s)));
  drawRot(); drawPlugins(); pollNow(); pluginFromHash();
}

// Old links (/#plugin=generator) go to that plugin's settings, which live on the Settings page now
function pluginFromHash() {
  const want = new URLSearchParams(location.hash.slice(1)).get('plugin');
  if (want) location.replace('/settings#plugin-' + encodeURIComponent(want));
}
window.addEventListener('hashchange', pluginFromHash);

// Play now, grouped: everyday scenes and generative art as buttons; the longer lists
// (holidays and seasons, GIF categories) fold away until you open them.
function drawPlayNow(cats) {
  const play = s => playButton(s, 'play-' + s);
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

function drawPlugins() {
  const errs = S.plugin_errors || [];
  $('#pluginerrs').hidden = !errs.length;
  $('#pluginerrs').replaceChildren(...errs.map(e => el('div', {textContent: `⚠ ${e.source} didn't load: ${e.error}`})));
  $('#plugins').replaceChildren(...S.plugins.map(p => {
    const row = document.createElement('div'); row.className = 'plugin'; row.dataset.testid = 'plugin-' + p.name;
    const nice = p.name.replace(/_/g, ' ');
    const link = el('a', {className: 'plugin-link', href: '/settings#plugin-' + p.name, title: 'Settings and details'},
      el('strong', {textContent: nice}));
    const info = el('div', {}, link, el('small', {textContent: p.description}));
    const crashed = (p.tasks || []).filter(t => t.crashes);
    if (p.source !== 'built-in' || p.version) info.append(el('small', {textContent: [p.source, p.version && 'v' + p.version].filter(Boolean).join(' ')}));
    if (crashed.length) info.append(el('small', {className: 'warn', textContent: `⚠ task crashed: ${crashed[0].last_error}`}));
    const toggle = btn(p.enabled ? 'On' : 'Off', () =>
      api('/api/config', 'PUT', {plugins: {[p.name]: {enabled: !p.enabled}}})
        .then(() => init()).then(() => toast(`${nice} ${p.enabled ? 'off' : 'on'}`)));
    setPressed(toggle, p.enabled); toggle.setAttribute('aria-label', nice);   // "weather, toggle button, pressed"
    row.append(info, toggle);
    return row;
  }));
}

// Move playlist entry `from` to position `to` (drag and drop, or the arrows).
function moveRot(from, to) {
  if (from === to || to < 0 || to >= rotation.length) return;
  rotation.splice(to, 0, ...rotation.splice(from, 1)); rotIds.splice(to, 0, ...rotIds.splice(from, 1));
  const label = document.activeElement?.getAttribute('aria-label')?.split(':')[0];   // redraw replaces the button you pressed
  flipRot(() => { drawRot(); if (label) $(`#rot li[data-index="${to}"] [aria-label^="${label}:"]`)?.focus(); });
}

// Rows glide from where they were to where they are now (FLIP). Unlike a view transition
// the rows stay clickable while they move, so a quick second press isn't lost, and it
// starts from wherever the row is on screen. New rows fade in.
function flipRot(change) {
  const top = li => li.getBoundingClientRect().top;
  const was = new Map([...$('#rot').children].map(li => [li.dataset.rotId, top(li)]));
  change();
  if (calmMotion.matches) return;
  for (const li of $('#rot').children) {
    const from = was.get(li.dataset.rotId);
    if (from == null) li.animate([{opacity: .001}, {opacity: 1}], {duration: 200, easing: 'cubic-bezier(.22, 1, .36, 1)'});
    else if (from !== top(li)) li.animate([{translate: `0 ${from - top(li)}px`}, {translate: '0 0'}], {duration: 220, easing: 'cubic-bezier(.65, 0, .35, 1)'});
  }
}

function drawRot() {
  $('#rot').replaceChildren(...rotation.map((s, i) => {
    const li = document.createElement('li'); li.dataset.index = i; li.dataset.rotId = rotIds[i]; li.draggable = true;
    li.ondragstart = e => { e.dataTransfer.setData('text/plain', String(i)); e.dataTransfer.effectAllowed = 'move'; li.classList.add('dragging'); };
    li.ondragend = () => li.classList.remove('dragging');
    li.ondragover = e => { e.preventDefault(); li.classList.add('over'); };
    li.ondragleave = () => li.classList.remove('over');
    li.ondrop = e => { e.preventDefault(); moveRot(+e.dataTransfer.getData('text/plain'), i); };
    const grip = el('span', {className: 'grip', textContent: '⠿', ariaHidden: 'true'});
    const nice = sceneLabel(s), span = el('span', {className: 'name', textContent: `${i+1}. ${nice}`});
    li.append(grip, span, btn(icon('up'), () => moveRot(i, i - 1), '', '', `Move up: ${nice}`),
      btn(icon('down'), () => moveRot(i, i + 1), '', '', `Move down: ${nice}`),
      btn(icon('x'), () => flipRot(() => { rotation.splice(i, 1); rotIds.splice(i, 1); drawRot(); }), '', '', `Remove ${nice}`));
    return li;
  }));
  // Edits stay in the page until Save playlist, so say when there are some.
  const dirty = JSON.stringify(rotation) !== JSON.stringify(C.rotation);
  setLabel($('#saverot'), dirty ? 'Save playlist •' : 'Save playlist');
  $('#rotdirty').hidden = !dirty;
}

// Toggles what the panel actually shows: during quiet hours this turns it on anyway.
$('#power').onclick = busy(() => api('/api/state', 'POST', {power: !S.on}).then(refresh).then(() => toast(S.on ? 'Power on' : 'Power off')));
$('#bright').oninput = e => $('#bv').textContent = e.target.value;
$('#bright').onchange = e => api('/api/state', 'POST', {brightness: +e.target.value}).then(refresh);
document.querySelectorAll('[data-pin]').forEach(b => b.onclick = busy(() =>
  api('/api/pin', 'POST', {scene: b.dataset.pin, minutes: +$('#mins').value || null}).then(refresh)
    .then(() => toast(`${b.textContent} on`))));
$('#pinmsg').onclick = busy(() => api('/api/pin', 'POST', {scene:'message', params:{text: $('#msg').value || 'HELLO'}, minutes: +$('#mins').value || null})
  .then(refresh).then(() => toast('Showing your message')));
$('#unpin').onclick = busy(() => api('/api/pin', 'DELETE').then(refresh).then(() => toast('Cleared')));
$('#nsend').onclick = busy(() => api('/api/notify', 'POST', {text: $('#ntext').value, icon: $('#nicon').value,
  color: $('#ncolor').value, flash: $('#nflash').checked, style: $('#nstyle').value}).then(() => toast('Sent')));
$('#skip').onclick = busy(() => api('/api/skip', 'POST').then(() => toast('Skipped')));
$('#add').onclick = () => flipRot(() => { rotation.push($('#addsel').value); rotIds.push(nextRotId++); drawRot(); });
$('#saverot').onclick = busy(() => api('/api/config', 'PUT', {rotation}).then(c => { C = c; drawRot(); toast('Playlist saved'); }));
window.addEventListener('beforeunload', e => {
  if (C.rotation && JSON.stringify(rotation) !== JSON.stringify(C.rotation)) e.preventDefault();
});

const SOURCE = {playlist: n => `Playlist ${n.index + 1}/${n.length}`, requested: () => 'Requested',
  notification: () => 'Notification', pinned: () => 'Pinned', birthday: () => 'Birthday bonus', boosted: () => 'Happening now',
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
  const name = n.source === 'notification' ? `Notification · ${n.text || ''}` : prettyScene(h.scene, n.entry);
  const shown = $('#nowscene').textContent;
  applyLive(h.live_color);
  if (shown !== name) {   // a new scene fades in (opacity only: fine under reduced motion), not the first fill on load
    const parts = name.split(' · ');   // the name itself in the board's dots; what kind of scene it is underneath
    $('#nowscene').textContent = name;
    drawLed($('#nowdots'), parts.at(-1));
    $('#nowkind').textContent = parts.slice(0, -1).join(', ');
    if (shown !== '…') $('#nowdots').animate([{opacity: .001}, {opacity: 1}], {duration: 180, easing: 'cubic-bezier(.22, 1, .36, 1)'});
  }
  const pct = n.seconds ? Math.min(100, 100 * (n.elapsed || 0) / n.seconds) : (n.source === 'pinned' ? 100 : 0);
  setBar(n, pct);
  $('#nownext').textContent = n.next ? `Up next in the playlist: ${sceneLabel(n.next)}` : '';
  document.querySelectorAll('#rot li').forEach(li =>
    li.classList.toggle('current', n.source === 'playlist' && +li.dataset.index === n.index));
}

// A title drawn the way the panel draws text: the board's own 5x7 font (led5x7.js) as
// round lamps, lit in --live. Words wrap onto a second line; past that it's cut with "...".
// The dots grow to fill the width but stop at 10px, so a short name doesn't turn huge.
function drawLed(svg, text, perLine = 14) {
  const lines = [];
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const last = lines.at(-1);
    if (last != null && (last + ' ' + word).length <= perLine) lines[lines.length - 1] = last + ' ' + word;
    else lines.push(word.length > perLine ? word.slice(0, perLine - 1) + '.' : word);
  }
  if (lines.length > 2) { lines.length = 2; lines[1] = lines[1].slice(0, perLine - 3) + '...'; }
  if (!lines.length) lines.push(' ');
  const cell = 8, cols = Math.max(...lines.map(l => l.length)) * 5, rows = lines.length * 8 - 1;
  const ns = 'http://www.w3.org/2000/svg', dots = [];
  lines.forEach((line, li) => [...line].forEach((ch, ci) => {
    const g = LED_FONT[ch] || LED_FONT['?'];
    for (let i = 0; i < 35; i++) {
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', (ci * 5 + i % 5) * cell + cell / 2); c.setAttribute('cy', (li * 8 + Math.floor(i / 5)) * cell + cell / 2);
      c.setAttribute('r', cell * .4);
      if (g[i] === '1') c.setAttribute('class', 'lit');
      dots.push(c);
    }
  }));
  svg.setAttribute('viewBox', `0 0 ${cols * cell} ${rows * cell}`);
  svg.style.width = `min(100%, ${cols * 10}px)`;
  svg.replaceChildren(...dots);
}

// The bar glides to the end on the board's own clock and only resyncs on a new scene or
// drift, so it neither lurches between 2 s polls nor animates backwards at a scene change.
let barKey = null;
function setBar(n, pct) {
  const bar = $('#nowbar'), left = n.seconds ? Math.max(0, n.seconds - (n.elapsed || 0)) : 0;
  const shown = 100 * (parseFloat(getComputedStyle(bar).scale) || 0);
  if (!calmMotion.matches && n.started === barKey && Math.abs(shown - pct) < 3) return;
  barKey = n.started;
  bar.dataset.pct = Math.round(pct);
  bar.style.transition = 'none'; bar.style.scale = `${pct / 100} 1`;   // a new scene starts where it is, no rewind
  if (left && !calmMotion.matches) { bar.offsetWidth; bar.style.transition = `scale ${left}s linear`; bar.style.scale = '1 1'; }
}

// Everything else updates on a timer, paused while the tab is in the background.
const live = fn => () => { if (!document.hidden) fn(); };
setInterval(live(() => pollNow().catch(() => {})), 2000);
setInterval(live(refresh), 10000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) { refresh(); pollNow().catch(() => {}); }
});
startPreview('#preview');
init().catch(e => $('#stat').textContent = 'error: ' + e.message)
  .finally(() => $('main').removeAttribute('aria-busy'));   // reveal once Play now is drawn: no jump
