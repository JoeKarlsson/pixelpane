// Draw and Animate pages (one page, two modes, picked by the path). You draw pixels on
// a canvas the size of the board's drawings; while "Live on the board" is on, every
// change goes to PUT /api/sketch and the board shows it at once. $, api, send, toast,
// el and btn come from common.js.
const ANIM = location.pathname.startsWith('/animate');
const STORE = ANIM ? 'pixelpane-animate' : 'pixelpane-draw';
// PICO-8's sixteen, which read well on LEDs, plus white-ish and a hot pink
const PALETTE = ['#000000', '#1d2b53', '#7e2553', '#008751', '#ab5236', '#5f574f', '#c2c3c7', '#fff1e8',
  '#ff004d', '#ffa300', '#ffec27', '#00e436', '#29adff', '#83769c', '#ff77a8', '#ffccaa'];

let W = 32, H = 32;
let frames = [], cur = 0, ms = 125;
let tool = 'pen', color = [255, 0, 77];
const undoStack = [], redoStack = [];
const cv = $('#canvas'), g = cv.getContext('2d');

const blank = () => new Uint8ClampedArray(W * H * 3);
const hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
const unhex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));

function b64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
const unb64 = s => Uint8ClampedArray.from(atob(s), ch => ch.charCodeAt(0));

// --- drawing ---------------------------------------------------------------------

function render(i = cur, onion = ANIM && $('#onion').checked) {
  const img = g.createImageData(W, H), f = frames[i];
  const under = onion && i > 0 ? frames[i - 1] : null;
  for (let i = 0, j = 0; i < f.length; i += 3, j += 4) {
    const lit = f[i] || f[i + 1] || f[i + 2];
    const src = lit ? f : under, k = lit ? 1 : .3;   // the frame before shows faintly through black
    img.data[j] = src ? src[i] * k : 0; img.data[j + 1] = src ? src[i + 1] * k : 0;
    img.data[j + 2] = src ? src[i + 2] * k : 0; img.data[j + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}

function setPx(x, y, c) {
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  const i = (y * W + x) * 3, f = frames[cur];
  f[i] = c[0]; f[i + 1] = c[1]; f[i + 2] = c[2];
}

function dab(x, y) {
  const s = +$('#size').value, o = Math.floor((s - 1) / 2), c = tool === 'eraser' ? [0, 0, 0] : color;
  for (let dy = 0; dy < s; dy++) for (let dx = 0; dx < s; dx++) {
    setPx(x - o + dx, y - o + dy, c);
    if ($('#mirror').checked) setPx(W - 1 - (x - o + dx), y - o + dy, c);
  }
}

function line(x0, y0, x1, y1) {   // Bresenham, so a fast stroke has no gaps
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    dab(x0, y0);
    if (x0 === x1 && y0 === y1) return;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

function fill(x, y) {
  const f = frames[cur], at = (x, y) => (y * W + x) * 3, i0 = at(x, y);
  const want = [f[i0], f[i0 + 1], f[i0 + 2]];
  if (want.every((v, k) => v === color[k])) return;
  const stack = [[x, y]];
  while (stack.length) {
    const [px, py] = stack.pop();
    if (px < 0 || py < 0 || px >= W || py >= H) continue;
    const i = at(px, py);
    if (f[i] !== want[0] || f[i + 1] !== want[1] || f[i + 2] !== want[2]) continue;
    setPx(px, py, color);
    stack.push([px + 1, py], [px - 1, py], [px, py + 1], [px, py - 1]);
  }
}

function pick(x, y) {
  const i = (y * W + x) * 3, f = frames[cur];
  setColor([f[i], f[i + 1], f[i + 2]]);
  setTool('pen');
}

function cell(e) {
  const r = cv.getBoundingClientRect();
  return [Math.min(W - 1, Math.max(0, Math.floor((e.clientX - r.left) / r.width * W))),
          Math.min(H - 1, Math.max(0, Math.floor((e.clientY - r.top) / r.height * H)))];
}

let last = null;
cv.addEventListener('pointerdown', e => {
  e.preventDefault();
  stopPlaying();
  const [x, y] = cell(e);
  if (tool === 'picker') return pick(x, y);
  snapshot();
  if (tool === 'fill') { fill(x, y); return changed(); }
  cv.setPointerCapture(e.pointerId);
  last = [x, y]; dab(x, y); changed();
});
cv.addEventListener('pointermove', e => {
  if (!last) return;
  const [x, y] = cell(e);
  if (x === last[0] && y === last[1]) return;
  line(last[0], last[1], x, y); last = [x, y]; changed();
});
const endStroke = () => { last = null; };
cv.addEventListener('pointerup', endStroke);
cv.addEventListener('pointercancel', endStroke);

// --- undo -------------------------------------------------------------------------

const copy = () => ({frames: frames.map(f => f.slice()), cur});
function snapshot() {
  undoStack.push(copy()); redoStack.length = 0;
  if (undoStack.length > 40) undoStack.shift();
}
function restore(from, to) {
  if (!from.length) return;
  to.push(copy());
  ({frames, cur} = from.pop());
  changed(true);
}
$('#undo').onclick = () => restore(undoStack, redoStack);
$('#redo').onclick = () => restore(redoStack, undoStack);
$('#clear').onclick = () => { snapshot(); frames[cur] = blank(); changed(); };

// --- tools and colors ------------------------------------------------------------

function setTool(t) {
  tool = t;
  document.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t));
  cv.dataset.tool = t;
}
document.querySelectorAll('[data-tool]').forEach(b => b.onclick = () => setTool(b.dataset.tool));

function setColor(c) {
  color = c; $('#color').value = hex(c);
  document.querySelectorAll('.swatch').forEach(s => s.classList.toggle('on', s.dataset.color === hex(c)));
  if (tool === 'eraser') setTool('pen');
}
$('#color').oninput = e => setColor(unhex(e.target.value));
$('#palette').replaceChildren(...PALETTE.map(h => {
  const s = btn('', () => setColor(unhex(h)), 'swatch', '', h);
  s.dataset.color = h; s.style.setProperty('--sw', h);
  return s;
}));
$('#grid').onchange = () => $('#wrap').classList.toggle('grid', $('#grid').checked);

document.addEventListener('keydown', e => {
  if (e.target.matches('input:not([type=checkbox]):not([type=range]), select, textarea')) return;
  const k = e.key.toLowerCase();
  if ((e.metaKey || e.ctrlKey) && k === 'z') { e.preventDefault(); return (e.shiftKey ? $('#redo') : $('#undo')).click(); }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const keys = {b: () => setTool('pen'), e: () => setTool('eraser'), f: () => setTool('fill'), i: () => setTool('picker')};
  if (ANIM) Object.assign(keys, {n: () => $('#fadd').click(), d: () => $('#fdup').click(),
    ',': () => select(cur - 1), '.': () => select(cur + 1), ' ': () => $('#play').click()});
  if (keys[k]) { e.preventDefault(); keys[k](); }
});

// --- frames (Animate) -------------------------------------------------------------

function thumb(i) {
  const c = el('canvas', {width: W, height: H, className: 'fthumb'});
  const img = c.getContext('2d').createImageData(W, H), f = frames[i];
  for (let a = 0, b = 0; a < f.length; a += 3, b += 4) {
    img.data[b] = f[a]; img.data[b + 1] = f[a + 1]; img.data[b + 2] = f[a + 2]; img.data[b + 3] = 255;
  }
  c.getContext('2d').putImageData(img, 0, 0);
  return c;
}
function drawStrip() {
  if (!ANIM) return;
  $('#strip').replaceChildren(...frames.map((_, i) => {
    const b = btn('', () => select(i), i === cur ? 'frame on' : 'frame', 'frame-' + i, `Frame ${i + 1}`);
    b.append(thumb(i), el('span', {textContent: i + 1}));
    return b;
  }));
  $('#fdel').disabled = frames.length < 2;
}
function select(i) {
  if (i < 0 || i >= frames.length) return;
  stopPlaying(); cur = i; render(); drawStrip();
}
function structural(fn) { stopPlaying(); snapshot(); fn(); changed(true); }
$('#fadd').onclick = () => frames.length < 64 ? structural(() => frames.splice(++cur, 0, blank())) : toast('64 frames at most');
$('#fdup').onclick = () => frames.length < 64 ? structural(() => frames.splice(cur + 1, 0, frames[cur++].slice())) : toast('64 frames at most');
$('#fdel').onclick = () => frames.length > 1 && structural(() => { frames.splice(cur, 1); cur = Math.min(cur, frames.length - 1); });
const swap = d => cur + d >= 0 && cur + d < frames.length && structural(() => {
  [frames[cur], frames[cur + d]] = [frames[cur + d], frames[cur]]; cur += d;
});
$('#fleft').onclick = () => swap(-1);
$('#fright').onclick = () => swap(1);
$('#onion').onchange = render;
const showFps = () => { $('#fpsv').textContent = $('#fps').value + ' fps'; ms = Math.round(1000 / +$('#fps').value); };
$('#fps').oninput = () => { showFps(); changed(true); };

let player = null;
function stopPlaying() {
  if (!player) return;
  clearInterval(player.timer); player = null;
  $('#play').textContent = '▶ Play'; render();
}
$('#play').onclick = () => {
  if (player) return stopPlaying();
  player = {i: cur, timer: setInterval(() => {
    player.i = (player.i + 1) % frames.length;
    render(player.i, false);
  }, ms)};
  $('#play').textContent = '■ Stop';
};

// --- the board ---------------------------------------------------------------------

// Sends at most one drawing at a time: changes made while one is on its way go in the next.
let dirty = false, inflight = false, saveTimer = null;
function changed(full) {
  render();
  if (full) drawStrip();
  else if (ANIM) $('#strip').children[cur]?.querySelector('canvas').replaceWith(thumb(cur));
  dirty = true; pump();
  clearTimeout(saveTimer); saveTimer = setTimeout(keep, 500);
}
const payload = () => ({width: W, height: H, ms, frames: (ANIM ? frames : [frames[cur]]).map(f => b64(Uint8Array.from(f)))});
async function pump() {
  if (!$('#live').checked || inflight || !dirty) return;
  dirty = false; inflight = true;
  try {
    await send('/api/sketch', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload())});
    showing(true);
  } catch (e) {
    $('#live').checked = false; status(`Not sent: ${e.message}`);
  } finally {
    inflight = false; setTimeout(pump, 40);
  }
}
$('#live').onchange = () => { if ($('#live').checked) { dirty = true; pump(); } else status(''); };
$('#stop').onclick = async () => {
  $('#live').checked = false;
  const sk = await api('/api/sketch');
  if (sk.showing) await api('/api/pin', 'DELETE');
  showing(false); toast('Back to the playlist');
};
function status(t) { $('#livestat').textContent = t; }
function showing(on) {
  status(on ? '● Showing on the board' : $('#live').checked ? 'Draw something to show it on the board' : 'Not on the board');
  $('#livestat').classList.toggle('live', on);
}

$('#save').onclick = async () => {
  stopPlaying();
  if (frames.every(f => !f.some(v => v))) return toast('Draw something first');
  const r = await api('/api/sketch/save', 'POST', {...payload(), name: $('#gname').value, category: $('#gcat').value || 'drawn'});
  toast(`Saved to the library as ${r.name}`);
};

// This browser keeps your work, so a reload doesn't lose it.
function keep() {
  try { localStorage.setItem(STORE, JSON.stringify({width: W, height: H, ms, cur, frames: frames.map(f => b64(Uint8Array.from(f)))})); } catch (e) {}
}
function loadSaved(d) {
  if (!d || d.width !== W || d.height !== H || !d.frames?.length) return false;
  frames = d.frames.map(unb64); ms = d.ms || ms; cur = Math.min(d.cur || 0, frames.length - 1);
  return true;
}

async function init() {
  if (ANIM) {
    document.title = 'PixelPane Animate';
    $('#brandword').textContent = 'animate';
    $('#drawtitle').textContent = 'pixelpane@board: animate';
    $('#framebox').hidden = false;
    $('#hint').textContent = 'Each frame is one step of the loop; the faint picture is the frame before. ' +
      'N adds a frame, D copies this one, , and . step through them, space plays. With Live on, the board plays your loop as you edit it.';
  } else {
    $('#hint').textContent = 'With Live on, the board shows your drawing while you draw it, and stays on it until you press Stop showing. ' +
      'B pen, E eraser, F fill, I picks a color, Ctrl+Z undoes.';
  }
  document.querySelector(`[data-testid=${ANIM ? 'animate' : 'draw'}-link]`).setAttribute('aria-current', 'page');
  const sk = await api('/api/sketch');
  [W, H] = sk.size;
  cv.width = W; cv.height = H;
  $('#wrap').style.setProperty('--cells', W);
  $('#preview').style.width = '160px';
  $('.panel').style.setProperty('--led', (160 / W) + 'px');
  let local = null; try { local = JSON.parse(localStorage.getItem(STORE)); } catch (e) {}
  const board = sk.width === W && sk.height === H ? sk : null;
  // Draw picks up what's on the board (it may have been drawn on another phone); Animate
  // keeps your own loop, else starts from the board's if that's an animation.
  const ok = ANIM ? loadSaved(local) || (board?.frames.length > 1 && loadSaved(board))
    : (board?.frames.length === 1 && loadSaved(board)) || loadSaved(local);
  if (!ok) frames = [blank()];
  if (!ANIM) { frames = [frames[cur]]; cur = 0; }
  $('#fps').value = Math.max(1, Math.min(24, Math.round(1000 / ms))); showFps();
  setColor(color); setTool('pen');
  render(); drawStrip(); showing(sk.showing);
  showStatus(await api('/api/health'));
}

startPreview('#preview');
init().catch(e => $('#stat').textContent = 'error: ' + e.message);
