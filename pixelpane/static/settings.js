// PixelPane settings page: schedule, timings, holidays, appearance, display hardware,
// access, backup, system.
// $, api, send, toast, el, btn and clockTime come from common.js.
let S = {}, C = {}, rules = [];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const ALL = [0, 1, 2, 3, 4, 5, 6];
const PRESETS = {
  quiet: {label: 'Quiet hours', days: ALL, from: '23:00', to: '07:00', action: 'off'},
  dim: {label: 'Evening', days: ALL, from: '20:00', to: '23:00', action: 'dim', brightness: 20},
  weekend: {label: 'Weekend lie-in', days: [5, 6], from: '07:00', to: '09:00', action: 'off'},
  playlist: {label: 'Mornings', days: [0, 1, 2, 3, 4], from: '06:30', to: '09:00', action: 'playlist',
    rotation: ['clock', 'weather', 'calendar']},
  blank: {label: '', days: ALL, from: '09:00', to: '17:00', action: 'off'},
};

async function load() {
  [S, C] = await Promise.all([api('/api/state'), api('/api/config')]);
  rules = (C.schedule || []).map(r => ({...r}));
  drawStatus(); drawRules(); drawPlayback(); drawHolidays(); drawAppearance(); drawHardware(); drawAccess(); drawSystem();
}

function drawStatus() {
  showStatus(S);
  const sch = S.schedule || {};
  $('#schednow').textContent = !(sch.rules || []).length ? 'No rule is on right now.'
    : `On now: ${sch.rules.join(', ')}.` + (sch.off ? ` The board is off until ${clockTime(sch.until)}.` : '')
      + (sch.overridden ? ` Turned on anyway until ${clockTime(sch.until)}.` : '')
      + (sch.brightness != null ? ` Brightness is capped at ${sch.brightness}.` : '')
      + (sch.playlist ? ' A scheduled playlist is playing.' : '');
}

// --- schedule ------------------------------------------------------------------

function scenesList() {
  const cats = (S.categories || []).map(c => 'gif:' + c);
  return [...(S.scenes.widget || []), 'gif', ...cats, 'seasonal', 'generative', 'ambient', ...(S.scenes.generative || [])];
}

function drawRules() {
  const live = new Set((S.schedule || {}).rules || []);
  $('#rules').replaceChildren(...(rules.length ? rules.map((r, i) => ruleRow(r, i, live)) :
    [el('div', {className: 'stat', textContent: 'No rules yet: the board plays all day. Add one below.'})]));
}

function ruleRow(r, i, live) {
  const row = el('div', {className: 'rule' + (r.enabled === false ? ' off' : '')
    + (live.has(r.label || `rule ${i + 1}`) ? ' live' : '')});
  row.dataset.testid = 'rule';
  const label = el('input', {className: 'label', value: r.label || '', placeholder: 'Name (optional)', maxLength: 40});
  label.oninput = () => r.label = label.value;
  const on = el('label', {}, el('input', {type: 'checkbox', checked: r.enabled !== false}), ' on');
  on.firstChild.onchange = () => { r.enabled = on.firstChild.checked; row.classList.toggle('off', !r.enabled); };
  const del = btn('✕', () => { rules.splice(i, 1); drawRules(); }, '', 'delete-rule');
  del.title = 'Delete this rule';

  const days = el('div', {className: 'days'}, ...DAYS.map((d, n) => {
    const b = btn(d, () => {
      const set = new Set(r.days || ALL);
      set.has(n) ? set.delete(n) : set.add(n);
      if (!set.size) return toast('A rule needs at least one day');
      r.days = [...set].sort(); b.className = set.has(n) ? 'on' : '';
      b.setAttribute('aria-label', `${d} ${set.has(n) ? 'on' : 'off'}`);
    }, (r.days || ALL).includes(n) ? 'on' : '');
    b.setAttribute('aria-label', `${d} ${(r.days || ALL).includes(n) ? 'on' : 'off'}`);
    return b;
  }));

  const from = el('input', {type: 'time', value: r.from, required: true}), to = el('input', {type: 'time', value: r.to, required: true});
  from.onchange = () => r.from = from.value; to.onchange = () => r.to = to.value;
  from.setAttribute('aria-label', 'From'); to.setAttribute('aria-label', 'To');
  const action = el('select', {}, new Option('Turn off', 'off'), new Option('Dim to', 'dim'), new Option('Play a playlist', 'playlist'));
  action.value = r.action; action.setAttribute('aria-label', 'What it does');
  const extra = el('span', {className: 'row extra'});
  const drawExtra = () => {
    if (r.action === 'dim') {
      r.brightness = r.brightness || 20;
      const level = el('input', {type: 'number', min: 1, max: 100, value: r.brightness, style: 'width:70px'});
      level.onchange = () => r.brightness = +level.value;
      level.setAttribute('aria-label', 'Brightness');
      extra.replaceChildren(level, el('span', {className: 'stat', textContent: 'of 100'}));
    } else if (r.action === 'playlist') {
      r.rotation = r.rotation || ['clock'];
      const list = el('input', {className: 'scenes', value: r.rotation.join(', '), placeholder: 'clock, weather, gif:retro'});
      list.setAttribute('list', 'scenelist'); list.setAttribute('aria-label', 'Scenes in order');
      list.onchange = () => r.rotation = list.value.split(',').map(x => x.trim()).filter(Boolean);
      extra.replaceChildren(list);
    } else extra.replaceChildren();
  };
  action.onchange = () => { r.action = action.value; delete r.brightness; delete r.rotation; drawExtra(); };
  drawExtra();
  row.append(el('div', {className: 'row'}, label, on, del), days,
    el('div', {className: 'row'}, el('label', {textContent: 'from'}), from, el('label', {textContent: 'to'}), to, action, extra));
  return row;
}

$('#addrule').onclick = () => { rules.push(structuredClone(PRESETS[$('#preset').value])); drawRules(); };
$('#saverules').onclick = async () => {
  const clean = rules.map(r => {
    const out = {label: r.label || '', days: r.days || ALL, from: r.from, to: r.to, action: r.action, enabled: r.enabled !== false};
    if (r.action === 'dim') out.brightness = r.brightness;
    if (r.action === 'playlist') out.rotation = r.rotation;
    return out;
  });
  try { C = await api('/api/config', 'PUT', {schedule: clean}); } catch (e) { return toast(e.message); }
  toast('Schedule saved'); load();
};

// --- playback --------------------------------------------------------------------

function numberGrid(target, entries, onSave) {
  $(target).replaceChildren(...entries.map(([k, v, placeholder]) => {
    const inp = el('input', {type: 'number', min: 1, value: v ?? '', placeholder: placeholder ?? ''});
    inp.onchange = () => onSave(k, inp.value === '' ? null : +inp.value);
    inp.dataset.testid = `${target.slice(1)}-${k}`;
    return el('label', {}, k.replace(/_/g, ' ') + ' ', inp);
  }));
}

function drawPlayback() {
  numberGrid('#dwell', Object.entries(C.dwell), (k, v) => v && api('/api/config', 'PUT', {dwell: {[k]: v}})
    .then(c => { C = c; toast('Saved'); }, e => toast(e.message)));
  const ttl = S.plugins.flatMap(p => Object.entries(p.data).map(([k, mins]) => [k, (C.data_ttl_minutes || {})[k], mins]));
  numberGrid('#ttl', ttl, (k, v) => {
    const all = {...(C.data_ttl_minutes || {})};
    if (v == null) delete all[k]; else all[k] = v;
    api('/api/config', 'PUT', {data_ttl_minutes: all}).then(c => { C = c; toast('Saved'); }, e => toast(e.message));
  });
}

// --- display hardware ---------------------------------------------------------------

const HW = [
  {key: 'display', label: 'Driver', type: 'select', options: [['auto', 'Pick for this Pi'], ['hzeller', 'rpi-rgb-led-matrix (Pi 2-4)'],
    ['piomatter', 'PioMatter (Pi 5)'], ['fake', 'None (no panel)']]},
  {key: 'adafruit_board', label: 'Adafruit board', type: 'select', options: [['hat', 'Matrix HAT'], ['bonnet', 'Matrix Bonnet']]},
  {key: 'panel.cols', label: 'Panel width (LEDs)', type: 'select', options: [16, 32, 64, 128].map(n => [n, n])},
  {key: 'panel.rows', label: 'Panel height (LEDs)', type: 'select', options: [16, 32, 64, 128].map(n => [n, n])},
  {key: 'hardware_mapping', label: 'Hardware mapping', type: 'text', help: 'rpi-rgb-led-matrix --led-gpio-mapping, e.g. adafruit-hat or adafruit-hat-pwm'},
  {key: 'gpio_slowdown', label: 'GPIO slowdown', type: 'number', min: 0, max: 5, help: 'Raise it (1-4) if a Pi 4 flickers. Empty: the driver picks.'},
  {key: 'refresh_hz', label: 'Refresh limit (Hz)', type: 'number', min: 30, max: 2000, help: 'Empty: as fast as it goes.'},
  {key: 'panel_bgr', label: 'Panel swaps red and blue', type: 'checkbox'},
];
const hwRead = {};
const getPath = (o, k) => k.split('.').reduce((x, p) => x?.[p], o);

function drawHardware() {
  $('#hw').replaceChildren(...HW.map(f => {
    const id = 'hw-' + f.key.replace('.', '-'), v = getPath(C, f.key);
    let inp;
    if (f.type === 'select') {
      inp = el('select', {id}, ...f.options.map(([val, lbl]) => new Option(lbl, val)));
      inp.value = v ?? f.options[0][0];
      hwRead[f.key] = () => typeof f.options[0][0] === 'number' ? +inp.value : inp.value;
    } else if (f.type === 'checkbox') {
      inp = el('input', {id, type: 'checkbox', checked: !!v});
      hwRead[f.key] = () => inp.checked;
    } else if (f.type === 'number') {
      inp = el('input', {id, type: 'number', min: f.min, max: f.max, value: v ?? ''});
      hwRead[f.key] = () => inp.value === '' ? null : +inp.value;
    } else {
      inp = el('input', {id, value: v ?? ''});
      hwRead[f.key] = () => inp.value.trim();
    }
    return el('div', {className: 'field'}, el('label', {htmlFor: id, textContent: f.label}), inp,
      ...(f.help ? [el('small', {textContent: f.help})] : []));
  }));
}

async function saveHardware() {
  const out = {panel: {}};
  for (const [k, read] of Object.entries(hwRead)) {
    if (k.startsWith('panel.')) out.panel[k.slice(6)] = read(); else out[k] = read();
  }
  C = await api('/api/config', 'PUT', out);
}
$('#savehw').onclick = () => saveHardware().then(() => toast('Saved: restart to apply'), e => toast(e.message));
$('#restart2').onclick = () => saveHardware().then(restart, e => toast(e.message));

// --- access -----------------------------------------------------------------------------

function drawAccess() {
  $('#tokstate').textContent = S.auth ? 'A token is set: every change needs it.'
    : 'No token: anyone on your network can change the board.';
  $('#cleartoken').disabled = !S.auth;
  $('#hosts').value = (C.allowed_hosts || []).join('\n');
  const names = S.host_names || [], me = names.find(n => !n.includes('.') && n !== 'localhost');
  $('#ownnames').textContent = me ? `${me}, ${me}.local and the like, localhost` : names.join(', ');
}
$('#settoken').onclick = async () => {
  const t = $('#token').value.trim();
  if (t.length < 8) return toast('Use at least 8 characters');
  try { await api('/api/config', 'PUT', {api_token: t}); } catch (e) { return toast(e.message); }
  rememberToken(t); $('#token').value = ''; toast('Token set, and remembered in this browser'); load();
};
$('#cleartoken').onclick = async () => {
  try { await api('/api/config', 'PUT', {api_token: null}); } catch (e) { return toast(e.message); }
  rememberToken(null); toast('Token turned off'); load();
};
$('#savehosts').onclick = () => api('/api/config', 'PUT', {allowed_hosts: $('#hosts').value.split('\n').map(x => x.trim()).filter(Boolean)})
  .then(c => { C = c; toast('Saved'); drawAccess(); }, e => toast(e.message));

// --- backup -------------------------------------------------------------------------------

$('#download').onclick = async () => {
  let r;
  try { r = await send('/api/backup', {method: 'GET'}); } catch (e) { return toast(e.message); }
  const name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'pixelpane-settings.json';
  const a = el('a', {href: URL.createObjectURL(await r.blob()), download: name});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
};
$('#restore').onclick = async () => {
  const f = $('#restorefile').files[0];
  if (!f) return toast('Pick a settings file first');
  let doc;
  try { doc = JSON.parse(await f.text()); } catch (e) { return toast('That file is not JSON'); }
  try { await api('/api/restore', 'POST', doc); } catch (e) { return toast(e.message); }
  $('#restorefile').value = ''; toast('Settings restored'); load();
};

// --- system ---------------------------------------------------------------------------------

// vcgencmd get_throttled bits: now (0-3) and since boot (16-19)
const THROTTLE = [[0, 'under-voltage now'], [1, 'CPU capped now'], [2, 'throttled now'], [3, 'too hot now'],
  [16, 'under-voltage since boot'], [17, 'CPU capped since boot'], [18, 'throttled since boot'], [19, 'too hot since boot']];
function throttleText(v) {
  const n = parseInt(v, 16);
  if (!v || isNaN(n)) return ['unknown', false];
  const bits = THROTTLE.filter(([b]) => n & (1 << b)).map(([, t]) => t);
  return bits.length ? [bits.join(', ') + (bits.some(t => t.startsWith('under')) ? ': check the power supply' : ''), true] : ['all good', false];
}

function drawSystem() {
  const [thr, bad] = throttleText(S.throttled);
  const facts = [['Version', S.version], ['Up for', `${Math.floor(S.uptime_s / 3600)}h ${Math.round(S.uptime_s % 3600 / 60)}m`],
    ['Temperature', S.temp_c != null ? `${S.temp_c.toFixed(1)}°C` : 'unknown', S.temp_c > 75],
    ['Power and heat', thr, bad], ['Panel', (S.panel || []).join(' x ') + ' LEDs'],
    ['Plugins on', `${S.plugins.filter(p => p.enabled).length} of ${S.plugins.length}`]];
  $('#facts').replaceChildren(...facts.flatMap(([k, v, warn]) => [el('dt', {textContent: k}), el('dd', {textContent: v, className: warn ? 'bad' : ''})]));
  const problems = [...(S.plugin_errors || []).map(e => `${e.source} didn't load: ${e.error}`),
    ...S.plugins.flatMap(p => (p.tasks || []).filter(t => t.crashes).map(t =>
      `${p.name}: task ${t.name} crashed ${t.crashes}x (${t.last_error})${t.running ? ', running again' : ''}`))];
  $('#problems').hidden = !problems.length;
  $('#problems').replaceChildren(...problems.map(t => el('div', {textContent: '⚠ ' + t})));
}

async function restart() {
  try { await api('/api/system/restart', 'POST'); } catch (e) { return toast(e.message); }
  toast('Restarting…');
  const began = Date.now();
  await new Promise(r => setTimeout(r, 2500));
  for (;;) {
    try { await api('/api/health'); break; } catch (e) { /* still down */ }
    if (Date.now() - began > 120000) return toast('It hasn\'t come back yet: check the Pi');
    await new Promise(r => setTimeout(r, 1500));
  }
  toast('Back up'); load();
}
$('#restart').onclick = restart;

async function loadLogs() {
  let lines;
  try { lines = await api('/api/logs'); } catch (e) { return toast(e.message); }
  if ($('#onlyproblems').checked) lines = lines.filter(l => l.level !== 'INFO' && l.level !== 'DEBUG');
  const pre = $('#logs');
  pre.hidden = false;
  pre.replaceChildren(...(lines.length ? lines.slice(-300).map(l => el('div', {className: l.level,
    textContent: `${new Date(l.t * 1000).toLocaleTimeString()} ${l.level.padEnd(7)} ${l.name}: ${l.msg}`}))
    : [el('div', {textContent: 'Nothing logged yet.'})]));
  pre.scrollTop = pre.scrollHeight;
}
$('#loadlogs').onclick = loadLogs;
$('#onlyproblems').onchange = () => { if (!$('#logs').hidden) loadLogs(); };

// --- holidays and seasons ----------------------------------------------------------

let customs = [];
const DEFAULT_ACCENT = '#fdae84';

function drawHolidays() {
  const t = C.themes || {};
  $('#hemi').value = t.hemisphere || 'north';
  const off = new Set(t.off || []);
  $('#builtins').replaceChildren(...S.holidays.map(h => el('label', {},
    el('input', {type: 'checkbox', value: h, checked: !off.has(h)}), ' ' + S.theme_names[h].split(' (')[0])));
  customs = (t.custom || []).map(c => ({...c}));
  drawCustoms();
}

// "11-08 to 11-12" lines <-> [["11-08", "11-12"]]
const rangesText = dates => dates.map(([a, b]) => a === b ? a : `${a} to ${b}`).join('\n');
const parseRanges = text => text.split('\n').map(l => l.trim()).filter(Boolean)
  .map(l => { const [a, b] = l.split(/\s+to\s+/); return [a.trim(), (b || a).trim()]; });

function drawCustoms() {
  $('#customs').replaceChildren(...(customs.length ? customs.map((c, i) => {
    const name = el('input', {value: c.name || '', placeholder: 'Name, like Diwali', maxLength: 40, className: 'label'});
    name.oninput = () => c.name = name.value;
    const dates = el('textarea', {rows: 2, value: rangesText(c.dates || []), placeholder: '11-08 to 11-12'});
    dates.oninput = () => c.text = dates.value;
    const row = el('div', {className: 'rule'}, el('div', {className: 'row'}, name,
      btn('✕', () => { customs.splice(i, 1); drawCustoms(); }, '', 'delete-holiday', 'Delete this holiday')), dates);
    row.dataset.testid = 'holiday';
    return row;
  }) : [el('div', {className: 'stat', textContent: 'None yet.'})]));
}

$('#addholiday').onclick = () => { customs.push({name: '', dates: []}); drawCustoms(); };
$('#saveholidays').onclick = async () => {
  const custom = customs.map(c => ({...(c.key ? {key: c.key} : {}), name: c.name.trim(),
    dates: c.text != null ? parseRanges(c.text) : c.dates}));
  const off = [...document.querySelectorAll('#builtins input')].filter(b => !b.checked).map(b => b.value);
  try { C = await api('/api/config', 'PUT', {themes: {hemisphere: $('#hemi').value, off, custom}}); }
  catch (e) { return toast(e.message); }
  S = await api('/api/state');
  drawHolidays(); toast('Holidays saved');
};

// --- appearance --------------------------------------------------------------------

function drawAppearance() {
  const ui = C.ui || {};
  $('#uitheme').value = ui.theme || 'dark';
  $('#uiaccent').value = ui.accent || DEFAULT_ACCENT;
}
$('#uidefault').onclick = () => { $('#uiaccent').value = DEFAULT_ACCENT; };
$('#saveui').onclick = async () => {
  try { await api('/api/config', 'PUT', {ui: {theme: $('#uitheme').value, accent: $('#uiaccent').value}}); }
  catch (e) { return toast(e.message); }
  location.hash = '#appearance';
  location.reload();   // the board paints the page in the new colors
};

load().then(() => {
  // scene names for the playlist rules
  document.body.append(el('datalist', {id: 'scenelist'}, ...scenesList().map(s => new Option(s))));
  if (location.hash) document.querySelector(location.hash)?.scrollIntoView();
}).catch(e => $('#stat').textContent = 'error: ' + e.message);
setInterval(() => { if (!document.hidden) api('/api/state').then(s => { S = s; drawStatus(); drawSystem(); }).catch(() => {}); }, 15000);
