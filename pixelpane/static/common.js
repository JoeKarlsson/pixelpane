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
