// PixelPane GIFs page: make GIFs from a prompt and manage the library.
// $, api, send, toast, el, btn, ago and showStatus come from common.js.
let S = {}, gifFilter = 'everything', gifPage = 0;
let gifList = [], gifShown = [], selecting = false, lastPick = null;
const picked = new Set();

async function refresh() {
  S = await api('/api/state');
  showStatus(S);
}

async function init() {
  await refresh();
  $('#gtheme').replaceChildren(new Option('all year', 'all'), ...Object.entries(S.theme_names).map(([k, v]) => new Option(v, k)));
  const gen = S.plugins.find(p => p.name === 'generator');
  const ready = gen && gen.enabled && gen.settings.base_url && gen.settings.model;
  ['#gprompt', '#ggo', '#gsurprise'].forEach(s => $(s).disabled = !ready || generating);
  $('#gsetup').hidden = !!ready;
  loadDrafts();
  loadGifs();
}

async function loadGifs() {
  const list = gifList = await api('/api/gifs');
  const match = f => g => f === 'everything' ? true : f === 'all' ? g.theme === 'all' : f === 'mine' ? g.upload
    : f === 'hidden' ? g.hidden : f.startsWith('cat:') ? g.theme === 'all' && g.category === f.slice(4) : g.theme === f;
  const count = f => list.filter(match(f)).length;
  // Every option shows how many GIFs it holds, so nothing looks missing.
  const opts = [['everything', 'Everything'], ['mine', 'Mine (uploaded and made here)'], ['hidden', 'Hidden'],
    ['all', 'All year (every day)'],
    ...S.categories.map(c => ['cat:' + c, `  All year: ${c}`]),
    ...Object.entries(S.theme_names).map(([k, v]) => [k, v])];
  $('#gfilter').replaceChildren(...opts.map(([v, label]) => new Option(`${label} (${count(v)})`, v)));
  $('#gfilter').value = gifFilter;
  $('#grename').hidden = !gifFilter.startsWith('cat:');
  $('#gcats').replaceChildren(...[...new Set(list.map(g => g.category))].sort().map(c => new Option(c)));
  for (const id of [...picked]) if (!list.some(g => g.id === id)) picked.delete(id);
  drawPicked();
  const words = $('#gsearch').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const found = g => words.every(w => (g.name + ' ' + g.category + ' ' + g.theme).toLowerCase().replace(/[-_]/g, ' ').includes(w));
  const all = sortGifs(list.filter(match(gifFilter)).filter(found), $('#gsort').value);
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
    r.append(btn('▶', () => api('/api/play', 'POST', {scene:'gif', params:{id:g.id}}).then(() => toast('Up next')), '', '', 'Play next'),
      btn(g.hidden ? 'show' : 'hide', () => api('/api/gifs/hide', 'POST', {id:g.id, hidden:!g.hidden}).then(loadGifs)),
      btn('✎', () => openClassify([g]), '', 'classify', 'Move to a category or theme'));
    if (g.upload) r.append(btn('🗑', e => confirmDelete(g, e.currentTarget), '', 'delete', 'Delete'));
    d.append(img, cap, el('span', {className: 'cat' + (g.moved ? ' moved' : ''),
      textContent: g.category + (g.plays ? ` · ▶${g.plays}` : ''),
      title: g.moved ? `moved here from ${g.default_category}, ${g.default_theme.replace('_', ' ')}` : 'category'}));
    if (g.theme !== 'all') {
      const tag = document.createElement('span'); tag.className = 'pill theme'; tag.textContent = g.theme.replace('_', ' ');
      d.append(tag);
    }
    d.append(r); return d;
  }));
}

// Library order. Seasons and themes follow the calendar, all-year GIFs first.
function sortGifs(list, how) {
  const cal = ['new_year', 'winter', 'valentines', 'st_patricks', 'spring', 'birthday', 'summer', 'july4',
    'autumn', 'halloween', 'thanksgiving', 'christmas'];
  const name = g => g.name.toLowerCase();
  const themeOrder = ['all', ...cal, ...Object.keys(S.theme_names).filter(t => !cal.includes(t))];
  const by = {
    newest: (a, b) => b.added - a.added || name(a).localeCompare(name(b)),
    oldest: (a, b) => a.added - b.added || name(a).localeCompare(name(b)),
    name: (a, b) => name(a).localeCompare(name(b)),
    namedesc: (a, b) => name(b).localeCompare(name(a)),
    category: (a, b) => a.category.localeCompare(b.category) || name(a).localeCompare(name(b)),
    theme: (a, b) => themeOrder.indexOf(a.theme) - themeOrder.indexOf(b.theme) || name(a).localeCompare(name(b)),
    most: (a, b) => b.plays - a.plays || name(a).localeCompare(name(b)),
    least: (a, b) => a.plays - b.plays || name(a).localeCompare(name(b)),
    recent: (a, b) => b.last_played - a.last_played || name(a).localeCompare(name(b)),
  }[how] || (() => 0);
  return [...list].sort(by);
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

// Make a GIF: the board asks the model for a draft; you look at it and then save it,
// refine it, try again or throw it out. Drafts stay on the board for reference.
let generating = false, draft = null;
const genInputs = ['#gprompt', '#ggo', '#gsurprise', '#sdagain', '#sdrefine', '#sdchange'];
const STEPS = {drafting: 'Designing', reviewing: 'Checking its work', starting: 'Starting'};

async function runJob(body) {
  if (generating) return;
  generating = true; genInputs.forEach(s => $(s).disabled = true);
  const stat = $('#ggenstat'), began = Date.now();
  let step = 'starting';
  const tick = setInterval(() => {
    stat.textContent = `${STEPS[step] || step}… ${Math.round((Date.now() - began) / 1000)}s`;
  }, 400);
  try {
    const {job} = await api('/api/gifs/generate', 'POST', body);
    let j;
    do {
      await new Promise(r => setTimeout(r, 1000));
      j = await api('/api/gifs/generate/' + job); step = j.step || step;
    } while (j.state === 'working');
    if (j.state !== 'done') throw new Error(j.error || 'failed');
    stat.textContent = '';
    showDraft(j.draft);
    loadDrafts();
  } catch (e) {
    stat.textContent = 'Could not make it: ' + e.message;
  } finally {
    clearInterval(tick); generating = false;
    genInputs.forEach(s => $(s).disabled = false);
  }
}

function showDraft(d) {
  draft = d;
  $('#sdraft').hidden = !d;
  if (!d) return;
  $('#sdimg').src = `/draft/${d.id}.gif`;
  $('#sdtitle').textContent = d.title;
  const asked = d.prompt ? `"${d.prompt}"` : 'its own idea';
  $('#sdmeta').textContent = `${asked}${d.change ? `, changed: ${d.change}` : ''} · ${d.frames} frames, ${d.seconds}s loop · `
    + `${d.model}${d.checked ? ', self-checked' : ''} · ${new Date(d.created * 1000).toLocaleString()}`;
  $('#sdname').value = d.title.toLowerCase();
  $('#sdcat').value = d.category;
  $('#sdtheme').replaceChildren(new Option('all year', 'all'), ...Object.entries(S.theme_names).map(([k, v]) => new Option(v, k)));
  $('#sdchange').value = '';
  $('#sdsaved').textContent = d.saved ? `In the library as ${d.saved.split('/').pop()}` : '';
  $('#sdsave').textContent = d.saved ? 'Save another copy' : 'Save to library';
  document.querySelectorAll('#sdrafts .draft-thumb').forEach(t => t.classList.toggle('current', t.dataset.id === d.id));
}

async function loadDrafts() {
  const list = await api('/api/drafts');
  $('#srecenthead').hidden = !list.length;
  $('#sdrafts').replaceChildren(...list.map(d => {
    const t = el('button', {className: 'draft-thumb' + (d.saved ? ' saved' : '') + (draft && draft.id === d.id ? ' current' : ''),
      title: `${d.title}${d.prompt ? ` · "${d.prompt}"` : ''}${d.saved ? ' · saved' : ''}`},
      el('img', {src: `/draft/${d.id}.gif`, alt: d.title, loading: 'lazy'}));
    t.dataset.id = d.id; t.dataset.testid = 'draft-thumb';
    t.onclick = () => showDraft(d);
    return t;
  }));
}

$('#ggo').onclick = () => {
  const p = $('#gprompt').value.trim();
  if (!p) return toast('Type an idea, or press Surprise me');
  runJob({prompt: p});
};
$('#gprompt').onkeydown = e => { if (e.key === 'Enter') $('#ggo').click(); };
$('#gsurprise').onclick = () => runJob({prompt: ''});
$('#gsetup').onclick = () => { location.href = '/#plugin=generator'; };   // its settings are on the control page
$('#sdagain').onclick = () => draft && runJob({prompt: draft.prompt || ''});
$('#sdrefine').onclick = () => {
  const c = $('#sdchange').value.trim();
  if (!c) return toast('Say what to change');
  runJob({from: draft.id, change: c});
};
$('#sdchange').onkeydown = e => { if (e.key === 'Enter') $('#sdrefine').click(); };
$('#sdplay').onclick = () => api('/api/play', 'POST', {scene: 'gif', params: {id: `draft/${draft.id}.gif`}})
  .then(() => toast('Up next on the panel'));
$('#sdsave').onclick = async () => {
  let r;
  try {
    r = await api(`/api/drafts/${draft.id}/save`, 'POST',
      {name: $('#sdname').value, category: $('#sdcat').value, theme: $('#sdtheme').value});
  } catch (e) { return toast(e.message); }
  toast('Saved to the library as ' + r.name);
  draft.saved = r.id; showDraft(draft); loadDrafts(); loadGifs();
};
$('#sddiscard').onclick = async () => {
  await api('/api/drafts/' + draft.id, 'DELETE');
  toast('Discarded'); showDraft(null); loadDrafts();
};

// Deleting can't be undone, so the first click arms the button and a second one deletes.
function confirmDelete(g, b) {
  if (!b.classList.contains('armed')) {
    b.classList.add('armed'); b.textContent = 'Delete?'; b.setAttribute('aria-label', 'Confirm delete');
    setTimeout(() => { b.classList.remove('armed'); b.textContent = '🗑'; b.setAttribute('aria-label', 'Delete'); }, 3000);
    return;
  }
  api('/api/gifs/' + encodeURI(g.id), 'DELETE').then(() => { toast('Deleted ' + g.name); loadGifs(); });
}

$('#gfilter').onchange = e => { gifFilter = e.target.value; gifPage = 0; loadGifs(); };
$('#gsize').onchange = () => { gifPage = 0; loadGifs(); };
try {
  $('#gsort').value = localStorage.getItem('pixelpane-sort') || 'newest';
  $('#gthumb').value = localStorage.getItem('pixelpane-thumb') || '64';
} catch (e) { /* private window */ }
const thumbSize = () => document.documentElement.style.setProperty('--thumb', $('#gthumb').value + 'px');
thumbSize();
$('#gthumb').onchange = () => { try { localStorage.setItem('pixelpane-thumb', $('#gthumb').value); } catch (e) { /* private */ } thumbSize(); };
let searchTimer;
$('#gsearch').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { gifPage = 0; loadGifs(); }, 200); };
$('#gsort').onchange = () => {
  try { localStorage.setItem('pixelpane-sort', $('#gsort').value); } catch (e) { /* private window */ }
  gifPage = 0; loadGifs();
};
$('#gprev').onclick = () => { gifPage = Math.max(0, gifPage - 1); loadGifs(); };
$('#gnext').onclick = () => { gifPage += 1; loadGifs(); };
$('#gup').onclick = async () => {
  const files = $('#gfile').files; if (!files.length) return toast('Pick a file first');
  const fd = new FormData(); for (const f of files) fd.append('file', f);
  fd.append('theme', $('#gtheme').value); if ($('#gsmooth').checked) fd.append('smooth', '1');
  try { await send('/api/gifs', {method: 'POST', body: fd}); } catch (e) { return toast(e.message); }
  toast('Uploaded'); $('#gfile').value = ''; loadGifs();
};

setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 10000);
init().catch(e => $('#stat').textContent = 'error: ' + e.message);
