(() => {
  'use strict';
  const BOOT = window.OKO_BOOT || {};
  const LIVE = BOOT.backend === true;
  const LIMITS = Object.assign({ deadline_sec: 240, max_upload_mb: 500 }, BOOT.limits || {});
  const REDUCED = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  const I18N = window.OKO_I18N;
  const RULES_I18N = window.OKO_RULES_I18N || {};
  const NC_I18N = window.OKO_NOT_CLAIMED_I18N || {};
  const FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 9 7' shape-rendering='crispEdges'%3E%3Cpath fill='%23f3eeff' d='M2 0h5v1H2zM1 1h1v1H1zM7 1h1v1H7zM0 2h1v3H0zM8 2h1v3H8zM1 5h1v1H1zM7 5h1v1H7zM2 6h5v1H2z'/%3E%3Cpath fill='%239b6ae6' d='M3 2h3v3H3z'/%3E%3Cpath fill='%230f0a1c' d='M4 3h1v1H4z'/%3E%3C/svg%3E";
  let CATALOG = BOOT.catalog || null;

  /* ── утилиты ─────────────────────────────────────────────────────────── */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const svgIcon = id => { const tpl = $(`#icon-sprites .ic-${id}`); return tpl ? tpl.cloneNode(true) : null; };
  const imgSrc = b64 => (b64.startsWith('data:') ? b64 : `data:image/jpeg;base64,${b64}`);
  const fmtClock = s => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const fmtTc = s => { s = Math.round(Math.max(0, s || 0) * 10) / 10; const m = Math.floor(s / 60); return `${m}:${(s - m * 60).toFixed(1).padStart(4, '0').replace('.', ',')}`; };
  const fmtSec = s => `${(Math.round((s || 0) * 10) / 10).toString().replace('.', LANG === 'en' ? '.' : ',')} ${LANG === 'en' ? 's' : 'с'}`;
  const fmtSize = b => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} ${LANG === 'en' ? 'MB' : 'МБ'}` : `${Math.max(1, Math.round(b / 1024))} ${LANG === 'en' ? 'KB' : 'КБ'}`);
  const pct = x => `${Math.round(x * 100)}%`;
  const localISO = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const todayISO = () => localISO(new Date());
  const addDays = (iso, n) => localISO(new Date(new Date(`${iso}T12:00:00`).getTime() + n * 86400000));
  const dateOf = r => r.shot_date || (r.created_at ? localISO(new Date(r.created_at)) : '');
  /* Свои названия месяцев: в некоторых браузерах нет данных для казахской локали. */
  const MONTHS = {
    ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
    kk: ['қаң', 'ақп', 'нау', 'сәу', 'мам', 'мау', 'шіл', 'там', 'қыр', 'қаз', 'қар', 'жел'],
    en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  };
  function fmtDate(iso, withYear) {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-').map(Number);
    if (!y || !m || !d) return iso;
    return `${d} ${MONTHS[LANG][m - 1]}${withYear ? ` ${y}` : ''}`;
  }
  function fmtDateTime(isoTs) {
    if (!isoTs) return '—';
    const dt = new Date(isoTs);
    if (Number.isNaN(dt.getTime())) return isoTs;
    return `${fmtDate(localISO(dt))}, ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
  }
  function debounce(fn, ms) { let tm; return (...a) => { clearTimeout(tm); tm = setTimeout(() => fn(...a), ms); }; }
  const isTyping = el => !!el && (el.closest('input,textarea,select,[contenteditable="true"]') != null);

  /* ── языки ───────────────────────────────────────────────────────────── */
  /* По умолчанию — русский (язык норм и ответа API); выбранный вручную язык запоминается. */
  let LANG = (() => {
    try { const s = localStorage.getItem('oko-lang'); if (s && I18N[s]) return s; } catch (e) { /* хранилище недоступно */ }
    return 'ru';
  })();
  function t(key, vars) {
    let s = I18N[LANG] && I18N[LANG][key];
    if (s == null) s = I18N.ru[key];
    if (s == null) return key;
    if (typeof s !== 'string') return s;
    return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? vars[k] : m)) : s;
  }
  function pl(key, n) {
    const f = t(key);
    if (!Array.isArray(f)) return f;
    if (LANG === 'ru') { const a = Math.abs(n) % 100, b = a % 10; return f[a > 10 && a < 20 ? 2 : b > 1 && b < 5 ? 1 : b === 1 ? 0 : 2]; }
    if (LANG === 'en') return n === 1 ? f[0] : (f[1] || f[0]);
    return f[0];
  }
  const ruleById = id => (CATALOG && CATALOG.rules.find(r => r.id === id)) || null;
  function ruleText(rule) {
    const tr = RULES_I18N[LANG] && RULES_I18N[LANG][rule.id];
    return { title: tr ? tr[0] : rule.title, hint: tr ? tr[1] : rule.hint };
  }
  const groupName = g => ((t('groups') || {})[g] || g);
  const describe = (rule, observed) => `${observed.replace(/\.$/, '')}. Почему это может быть нарушением: ${rule.why}${rule.citation ? ` Источник: ${rule.citation}.` : ''}`;

  function applyStatic() {
    document.documentElement.lang = LANG;
    $$('[data-i18n]').forEach(el => { const v = t(el.dataset.i18n); if (typeof v === 'string') el.textContent = v; });
    $$('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
    $('#lang-cur').textContent = { kk: 'ҚАЗ', ru: 'РУС', en: 'ENG' }[LANG];
    $$('#lang-menu button').forEach(b => b.setAttribute('aria-checked', String(b.dataset.lang === LANG)));
    $('#drop-hint').textContent = t('up.hint', { mb: LIMITS.max_upload_mb });
    $('#keys-line').textContent = t('keys.line');
    $('#keys-body').replaceChildren(...t('keys.list').map(([k, d]) => h('p', null, h('span', { class: 'keys' }, h('kbd', null, k)), ' ', d)));
    renderApiTables();
  }
  function setLang(l) {
    if (!I18N[l]) return;
    LANG = l;
    try { localStorage.setItem('oko-lang', l); } catch (e) { /* ок */ }
    applyStatic();
    renderAll();
  }
  const langBtn = $('#lang-btn'), langMenu = $('#lang-menu');
  langBtn.addEventListener('click', () => { const open = langMenu.hidden; langMenu.hidden = !open; langBtn.setAttribute('aria-expanded', String(open)); });
  langMenu.addEventListener('click', e => { const b = e.target.closest('[data-lang]'); if (!b) return; langMenu.hidden = true; langBtn.setAttribute('aria-expanded', 'false'); setLang(b.dataset.lang); });
  document.addEventListener('click', e => { if (!e.target.closest('.lang')) { langMenu.hidden = true; langBtn.setAttribute('aria-expanded', 'false'); } });

  /* ── API: сервер или демо ─────────────────────────────────────────────── */
  async function getJSON(url, opts) {
    const r = await fetch(url, Object.assign({ cache: 'no-store' }, opts || {}));
    if (!r.ok) { const e = new Error(`HTTP ${r.status}`); e.status = r.status; try { e.detail = (await r.json()).detail; } catch (x) { /* нет тела */ } throw e; }
    return r.json();
  }
  const LiveApi = {
    demo: false,
    analyze(file, meta, onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/ui/v1/analyze');
        xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
        xhr.onload = () => {
          let body = null;
          try { body = JSON.parse(xhr.responseText); } catch (e) { /* не JSON */ }
          if (xhr.status >= 200 && xhr.status < 300 && body && body.job_id) resolve(body.job_id);
          else reject(new Error(body && body.detail ? String(body.detail) : `HTTP ${xhr.status}`));
        };
        xhr.onerror = () => reject(new Error(t('err.network')));
        const fd = new FormData();
        fd.append('file', file, file.name);
        for (const [k, v] of Object.entries(meta)) fd.append(k, v || '');
        xhr.send(fd);
      });
    },
    async statuses(ids) { return (await getJSON(`/ui/v1/jobs/status?ids=${encodeURIComponent(ids.join(','))}`)).items; },
    job: id => getJSON(`/ui/v1/jobs/${encodeURIComponent(id)}`),
    apiJson: id => getJSON(`/ui/v1/jobs/${encodeURIComponent(id)}/api`),
    async history() { return (await getJSON('/ui/v1/history')).items; },
    seen: id => getJSON(`/ui/v1/jobs/${encodeURIComponent(id)}/seen`, { method: 'POST' }),
    review: (id, key, decision, comment) => getJSON(`/ui/v1/jobs/${encodeURIComponent(id)}/review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key, decision, comment }),
    }),
    async clip(id, key) { try { return await getJSON(`/ui/v1/jobs/${encodeURIComponent(id)}/clip/${encodeURIComponent(key)}`); } catch (e) { return null; } },
    status: () => getJSON('/ui/v1/status'),
  };
  const api = LIVE ? LiveApi : window.OKO_makeDemoApi({ ruleById, describe, fmtTc, t: (k, v) => t(k, v) });

  /* ── состояние ───────────────────────────────────────────────────────── */
  const state = {
    view: 'check', id: null,
    pending: [], batch: [], local: new Map(),
    history: [], historyLoaded: false,
    report: null, active: 0, loop: null, clips: new Map(), playerOk: false,
    apiCache: new Map(), statusInfo: null, notifiedBatches: new Set(),
  };

  /* ── маршруты ────────────────────────────────────────────────────────── */
  const VIEWS = ['check', 'report', 'history', 'summary', 'norms', 'api'];
  function parseRoute() {
    const hash = (location.hash || '').slice(1);
    let m;
    if ((m = hash.match(/^report-([A-Za-z0-9]+)$/))) return { view: 'report', id: m[1] };
    if ((m = hash.match(/^print-([A-Za-z0-9]+)$/))) return { view: 'print', id: m[1] };
    if (VIEWS.includes(hash) && hash !== 'report') return { view: hash };
    const p = location.pathname.match(/\/report\/([A-Za-z0-9]+)\/?$/);
    if (p && !hash) return { view: 'print', id: p[1] };
    return { view: 'check' };
  }
  function go(hash) {
    if (location.hash === `#${hash}`) route();
    else location.hash = hash;
  }
  async function route() {
    const r = parseRoute();
    const prevView = state.view;
    state.view = r.view; state.id = r.id || null;
    if (r.view !== 'report') stopLoop();
    const printing = r.view === 'print';
    $('#app').hidden = printing;
    $('#print-view').hidden = !printing;
    if (printing) { await renderPrint(r.id); return; }
    for (const v of VIEWS) $(`#v-${v}`).hidden = v !== r.view;
    $$('#nav a').forEach(a => { if (a.dataset.view === r.view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    if (prevView !== r.view || r.view === 'report') window.scrollTo(0, 0);
    if (r.view === 'report') await openReport(r.id);
    else if (r.view === 'history') { renderHistory(); await refreshHistory(); }
    else if (r.view === 'summary') { renderSummary(); await refreshHistory(); }
    else if (r.view === 'check') { renderRecent(); refreshHistory(); }
    else if (r.view === 'api') refreshStatus();
  }
  window.addEventListener('hashchange', route);

  function renderAll() {
    updateRunBtn(); renderPicked(); renderBatch(); renderRecent(); renderStatusChip(); renderCatalog();
    if (state.view === 'history') renderHistory();
    if (state.view === 'summary') renderSummary();
    if (state.view === 'report' && state.report) renderReport(state.report);
    if (state.view === 'print' && state.id) renderPrint(state.id);
    if (state.view === 'api') renderStats();
  }

  /* ── история: загрузка и счётчик новых ────────────────────────────────── */
  let historyBusy = null;
  async function refreshHistory() {
    if (historyBusy) return historyBusy;
    historyBusy = (async () => {
      try {
        state.history = await api.history();
        state.historyLoaded = true;
      } catch (e) { /* оставляем прошлые данные */ }
      historyBusy = null;
      updateUnseen();
      fillSuggestions();
      if (state.view === 'history') renderHistory();
      if (state.view === 'summary') renderSummary();
      if (state.view === 'check') renderRecent();
    })();
    return historyBusy;
  }
  function updateUnseen() {
    const n = state.history.filter(r => r.status === 'done' && !r.seen).length;
    const b = $('#unseen-badge');
    b.textContent = String(n);
    b.hidden = n === 0;
    document.title = n ? `(${n}) OKO` : 'OKO';
  }
  function markSeenLocal(id) {
    const r = state.history.find(x => x.job_id === id);
    if (r) r.seen = true;
    updateUnseen();
  }

  /* ── статус сервиса ──────────────────────────────────────────────────── */
  async function refreshStatus() {
    try { state.statusInfo = await api.status(); state.statusErr = false; } catch (e) { state.statusErr = true; }
    renderStatusChip();
    if (state.view === 'api') renderStats();
  }
  function devLabel(d) {
    if (!d) return 'CPU';
    if (d.device === 'cuda') return `GPU${d.name && d.name !== 'GPU' ? ` ${d.name.replace(/^NVIDIA\s+/i, '').replace(/GeForce\s+/i, '')}` : ''}`;
    if (d.device === 'demo') return t('status.demo');
    return 'CPU';
  }
  function renderStatusChip() {
    const chip = $('#status-chip');
    chip.classList.toggle('is-demo', !LIVE);
    chip.classList.toggle('is-off', !!state.statusErr);
    const s = state.statusInfo;
    $('#status-text').textContent = state.statusErr ? t('status.offline')
      : s ? t('status.queue', { dev: devLabel(s.device), n: (s.queued || 0) + (s.processing || 0) }) : '…';
  }
  function renderStats() {
    const s = state.statusInfo;
    const box = $('#stats');
    if (!s) { box.replaceChildren(); return; }
    const p = s.processing_sec || {};
    const fmt = v => (v == null ? '—' : fmtSec(v));
    const cell = (label, value) => h('div', null, h('span', { class: 'label' }, label), h('b', null, value));
    box.replaceChildren(
      cell(t('a.device'), `${devLabel(s.device)}${s.device && s.device.memory ? ` · ${s.device.memory}` : ''}`),
      cell(t('a.workers'), String(s.workers)),
      cell(t('a.queued'), String(s.queued)),
      cell(t('a.processing'), String(s.processing)),
      cell(t('a.time'), `${fmt(p.avg)} / ${fmt(p.p95)} / ${fmt(p.max)}`),
    );
  }
  function renderApiTables() {
    const fields = t('a.fields'), errs = t('a.errs');
    $('#t-fields').replaceChildren(
      h('thead', null, h('tr', null, h('th', null, t('a.f.field')), h('th', null, t('a.f.what')))),
      h('tbody', null, fields.map(([f, d]) => h('tr', null, h('td', null, h('code', null, f)), h('td', null, d)))));
    $('#t-errors').replaceChildren(
      h('thead', null, h('tr', null, h('th', null, t('a.e.code')), h('th', null, t('a.e.when')))),
      h('tbody', null, errs.map(([c, d]) => h('tr', null, h('td', null, h('code', null, c)), h('td', null, d.replace('{mb}', LIMITS.max_upload_mb))))));
  }

  /* ── загрузка: выбор файлов и поля ───────────────────────────────────── */
  const input = $('#file-input'), drop = $('#drop');
  const fBranch = $('#f-branch'), fDesk = $('#f-desk'), fDate = $('#f-date');
  fDate.value = todayISO();
  try {
    const saved = JSON.parse(localStorage.getItem('oko-meta') || 'null');
    if (saved) { fBranch.value = saved.branch || ''; fDesk.value = saved.desk || ''; }
  } catch (e) { /* ок */ }
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('is-over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('is-over'); }));
  drop.addEventListener('drop', e => addFiles(Array.from((e.dataTransfer && e.dataTransfer.files) || [])));
  input.addEventListener('change', () => { addFiles(Array.from(input.files || [])); input.value = ''; });
  $('#clear-btn').addEventListener('click', () => { state.pending = []; showUploadError(''); renderPicked(); updateRunBtn(); });

  function showUploadError(msg) { const el = $('#upload-error'); el.textContent = msg; el.hidden = !msg; }
  function addFiles(files) {
    const errors = [];
    for (const f of files) {
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      if (!['mov', 'qt', 'mp4', 'm4v', 'avi', 'mkv', 'webm'].includes(ext) && !(f.type || '').startsWith('video/')) { errors.push(t('err.notvideo', { name: f.name })); continue; }
      if (f.size > LIMITS.max_upload_mb * 1048576) { errors.push(t('err.toobig', { name: f.name, mb: LIMITS.max_upload_mb })); continue; }
      if (!state.pending.some(p => p.name === f.name && p.size === f.size)) state.pending.push(f);
    }
    showUploadError(errors.join(' '));
    renderPicked();
    updateRunBtn();
  }
  function renderPicked() {
    const ul = $('#picked');
    ul.hidden = !state.pending.length;
    $('#clear-btn').hidden = !state.pending.length;
    ul.replaceChildren(...state.pending.map((f, i) => h('li', null,
      h('span', { class: 'name', title: f.name }, f.name),
      h('span', { class: 'faint num' }, fmtSize(f.size)),
      h('button', { type: 'button', 'aria-label': t('up.remove', { name: f.name }), onclick: () => { state.pending.splice(i, 1); renderPicked(); updateRunBtn(); } }, '×'))));
  }
  function updateRunBtn() {
    const n = state.pending.length;
    const b = $('#run-btn');
    b.disabled = n === 0;
    b.textContent = n ? t('up.run', { n }) : t('up.run0');
  }
  function fillSuggestions() {
    const uniq = key => [...new Set(state.history.map(r => r[key]).filter(Boolean))].sort();
    $('#dl-branches').replaceChildren(...uniq('branch').map(v => h('option', { value: v })));
    $('#dl-desks').replaceChildren(...uniq('desk').map(v => h('option', { value: v })));
  }

  $('#upload-form').addEventListener('submit', e => {
    e.preventDefault();
    if (!state.pending.length) return;
    askNotifyPermission();
    const meta = { branch: fBranch.value.trim(), desk: fDesk.value.trim(), shot_date: fDate.value };
    try { localStorage.setItem('oko-meta', JSON.stringify({ branch: meta.branch, desk: meta.desk })); } catch (x) { /* ок */ }
    startBatch(state.pending.splice(0), meta);
    renderPicked();
    updateRunBtn();
  });

  /* ── пакет: загрузка, опрос, уведомления ──────────────────────────────── */
  function startBatch(files, meta) {
    const batchId = `b${Date.now().toString(36)}`;
    for (const f of files) state.batch.push({ batchId, file: f, meta, jobId: null, phase: 'waiting', upload: 0, progress: 0, stage: '', queuePos: 0, verdict: null, n: 0, error: null, notified: false });
    renderBatch();
    $('#batch').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    pumpUploads();
    ensurePolling();
  }
  let uploading = 0;
  function pumpUploads() {
    while (uploading < 2) {
      const item = state.batch.find(x => x.phase === 'waiting');
      if (!item) return;
      uploading++;
      item.phase = 'uploading';
      renderBatch();
      api.analyze(item.file, Object.assign({}, item.meta, { batch_id: item.batchId }), p => { item.upload = p; renderBatchItem(item); })
        .then(jobId => {
          item.jobId = jobId; item.phase = 'queued';
          state.local.set(jobId, URL.createObjectURL(item.file));
        })
        .catch(err => { item.phase = 'failed'; item.error = err.message || t('err.network'); onItemFinished(item); })
        .finally(() => { uploading--; renderBatch(); pumpUploads(); ensurePolling(); });
    }
  }
  let pollTimer = null, pollMisses = 0;
  function ensurePolling() {
    if (pollTimer) return;
    pollTimer = setTimeout(pollOnce, 900);
  }
  async function pollOnce() {
    pollTimer = null;
    const active = state.batch.filter(x => x.jobId && (x.phase === 'queued' || x.phase === 'processing'));
    if (active.length) {
      try {
        const items = await api.statuses(active.map(x => x.jobId));
        pollMisses = 0;
        for (const s of items) {
          const item = state.batch.find(x => x.jobId === s.job_id);
          if (!item) continue;
          item.stage = s.stage; item.progress = s.progress || 0; item.queuePos = s.queue_position || 0;
          if (s.status === 'done') { item.phase = 'done'; item.verdict = s.verdict; item.n = s.n_violations || 0; onItemFinished(item); }
          else if (s.status === 'failed' || s.status === 'missing') { item.phase = 'failed'; item.error = s.error || t('st.failed'); onItemFinished(item); }
          else item.phase = s.status === 'queued' ? 'queued' : 'processing';
        }
      } catch (e) { pollMisses++; }
      renderBatch();
    }
    const stillBusy = state.batch.some(x => ['waiting', 'uploading', 'queued', 'processing'].includes(x.phase));
    if (stillBusy) pollTimer = setTimeout(pollOnce, pollMisses ? 3000 : 1500);
  }
  function onItemFinished(item) {
    if (item.notified) return;
    item.notified = true;
    const group = state.batch.filter(x => x.batchId === item.batchId);
    const place = [item.meta.branch, item.meta.desk].filter(Boolean).join(' · ');
    const body = [item.file.name, place].filter(Boolean).join(' · ');
    if (group.length <= 3) {
      const title = item.phase === 'failed' ? t('notif.failed') : item.verdict === 'violation' ? t('notif.found', { n: item.n }) : t('notif.clean');
      notify(title, body, item.phase === 'done' ? item.jobId : null, item.phase === 'failed' ? 'bad' : item.verdict === 'violation' ? 'bad' : 'ok');
    } else if (group.every(x => x.phase === 'done' || x.phase === 'failed') && !state.notifiedBatches.has(item.batchId)) {
      state.notifiedBatches.add(item.batchId);
      const bad = group.filter(x => x.verdict === 'violation').length;
      notify(t('notif.batch', { total: group.length, bad }), place, null, bad ? 'bad' : 'ok');
    }
    refreshHistory();
  }

  function canNotify() { return typeof window.Notification === 'function'; }
  function askNotifyPermission() {
    if (!canNotify() || Notification.permission !== 'default') { updateNotifBtn(); return; }
    try {
      const p = Notification.requestPermission(updateNotifBtn);
      if (p && p.then) p.then(updateNotifBtn, updateNotifBtn);
    } catch (e) { updateNotifBtn(); }
  }
  function updateNotifBtn() {
    const b = $('#notif-btn');
    if (!canNotify()) { b.hidden = true; return; }
    const perm = Notification.permission;
    b.hidden = perm === 'granted';
    b.disabled = perm === 'denied';
    b.querySelector('span').textContent = perm === 'denied' ? t('notif.blocked') : t('notif.enable');
  }
  $('#notif-btn').addEventListener('click', askNotifyPermission);
  function notify(title, body, jobId, tone) {
    toast(title, body, jobId, tone);
    if (document.hidden && canNotify() && Notification.permission === 'granted') {
      try {
        const n = new Notification(title, { body, tag: `oko-${jobId || 'batch'}`, icon: FAVICON });
        n.onclick = () => { window.focus(); go(jobId ? `report-${jobId}` : 'history'); n.close(); };
      } catch (e) { /* некоторые браузеры разрешают уведомления только из service worker */ }
    }
  }
  function toast(title, body, jobId, tone) {
    const box = $('#toasts');
    const el = h('div', { class: `toast${tone ? ` is-${tone}` : ''}`, role: 'status' },
      h('b', null, title),
      body ? h('span', { class: 'muted' }, body) : null,
      h('div', { class: 'toast__row' },
        jobId ? h('button', { class: 'link-btn', type: 'button', onclick: () => { el.remove(); go(`report-${jobId}`); } }, t('toast.open')) : h('span'),
        h('button', { class: 'link-btn', type: 'button', 'aria-label': t('pr.close'), onclick: () => el.remove() }, '×')));
    box.prepend(el);
    while (box.children.length > 4) box.lastElementChild.remove();
    setTimeout(() => el.remove(), 12000);
  }

  function phaseText(item) {
    switch (item.phase) {
      case 'waiting': return t('st.waiting');
      case 'uploading': return t('st.uploading', { p: Math.round(item.upload * 100) });
      case 'queued': return item.queuePos ? t('st.queuedPos', { n: item.queuePos }) : t('st.queued');
      case 'processing': return t({ decode: 'st.decode', evidence: 'st.evidence' }[item.stage] || 'st.detect');
      case 'done': return item.verdict === 'violation' ? t('v.bad.short', { n: item.n }) : t('v.ok.short');
      default: return `${t('st.failed')}: ${item.error || ''}`;
    }
  }
  function itemFrac(item) {
    if (item.phase === 'uploading') return item.upload * 0.15;
    if (item.phase === 'queued') return 0.16;
    if (item.phase === 'processing') return 0.16 + 0.84 * item.progress;
    if (item.phase === 'done' || item.phase === 'failed') return 1;
    return 0;
  }
  function slotEl(item, asButton) {
    const done = item.phase === 'done', failed = item.phase === 'failed';
    const bad = done && item.verdict === 'violation';
    const cls = `slot${done ? (bad ? ' is-bad' : ' is-ok') : ''}${failed ? ' is-failed' : ''}`;
    const el = h(asButton ? 'button' : 'span', { class: cls, type: asButton ? 'button' : null, title: item.file.name, 'aria-label': `${item.file.name}: ${phaseText(item)}` });
    if (!done && !failed) el.append(h('span', { class: 'slot__fill', style: `height:${Math.round(itemFrac(item) * 34)}px` }));
    const ic = svgIcon(done ? (bad ? 'bang' : 'ok') : failed ? 'x' : 'up');
    if (ic) el.append(ic);
    if (bad && item.n > 1) el.append(h('span', { class: 'slot__n' }, String(item.n)));
    return el;
  }
  function xpBar(frac, n) {
    const on = Math.round(frac * n);
    return h('span', { class: 'xp', 'aria-hidden': 'true' }, Array.from({ length: n }, (_, i) => h('i', { class: i < on ? 'on' : null })));
  }
  function renderBatchItem(item) {
    const li = $(`#batch-list [data-key="${item.batchId}-${state.batch.indexOf(item)}"]`);
    if (!li) { renderBatch(); return; }
    li.replaceWith(batchRow(item));
    renderHotbar();
  }
  function batchRow(item) {
    const done = item.phase === 'done';
    const place = [item.meta.branch, item.meta.desk, item.meta.shot_date ? fmtDate(item.meta.shot_date) : ''].filter(Boolean).join(' · ');
    return h('li', { class: `bitem${done ? (item.verdict === 'violation' ? ' is-bad' : ' is-ok') : ''}${item.phase === 'failed' ? ' is-failed' : ''}`, 'data-key': `${item.batchId}-${state.batch.indexOf(item)}` },
      slotEl(item, false),
      h('div', { style: 'min-width:0' }, h('p', { class: 'bitem__name', title: item.file.name }, item.file.name), h('p', { class: 'bitem__meta' }, place || fmtSize(item.file.size))),
      h('div', { class: 'bitem__state' }, xpBar(itemFrac(item), 16), h('span', { role: 'status' }, phaseText(item))),
      h('div', { class: 'bitem__act' }, done ? h('button', { class: 'btn btn--small', type: 'button', onclick: () => go(`report-${item.jobId}`) }, t('batch.open')) : null));
  }
  function renderBatch() {
    const sec = $('#batch');
    sec.hidden = !state.batch.length;
    if (!state.batch.length) { renderHotbar(); return; }
    const done = state.batch.filter(x => x.phase === 'done' || x.phase === 'failed').length;
    $('#batch-title').textContent = t('batch.title', { done, total: state.batch.length });
    $('#batch-list').replaceChildren(...state.batch.slice().reverse().map(batchRow));
    updateNotifBtn();
    renderHotbar();
  }
  function renderHotbar() {
    const bar = $('#hotbar');
    bar.hidden = !state.batch.length || state.view === 'print';
    if (bar.hidden) return;
    const items = state.batch.slice(-9);
    const done = state.batch.filter(x => x.phase === 'done' || x.phase === 'failed').length;
    $('#hotbar-label').replaceChildren(t('hotbar.label', { done, total: state.batch.length }));
    $('#hotbar-slots').replaceChildren(...items.map(item => {
      const b = slotEl(item, true);
      b.addEventListener('click', () => { if (item.phase === 'done') go(`report-${item.jobId}`); else { go('check'); setTimeout(() => $('#batch').scrollIntoView({ block: 'start' }), 50); } });
      return b;
    }));
  }

  /* ── строки истории (главная и вкладка «История») ─────────────────────── */
  function verdictPill(r) {
    if (r.status === 'queued' || r.status === 'processing') return h('span', { class: 'pill pill--muted' }, t('h.processing'));
    if (r.status === 'failed') return h('span', { class: 'pill pill--muted' }, t('h.failed'));
    const n = r.items.filter(i => i.status === 'reported').length;
    return r.verdict === 'violation' ? h('span', { class: 'pill pill--bad' }, t('v.bad.short', { n })) : h('span', { class: 'pill pill--ok' }, t('v.ok.short'));
  }
  function reviewPill(r) {
    const rep = r.items.filter(i => i.status === 'reported');
    if (!rep.length || r.status !== 'done') return h('span');
    const d = rep.filter(i => r.reviews && r.reviews[i.key] && r.reviews[i.key].decision).length;
    return h('span', { class: `pill ${d === rep.length ? 'pill--ok' : 'pill--warn'}` }, t('h.review', { d, t: rep.length }));
  }
  function historyRow(r) {
    const isNew = r.status === 'done' && !r.seen;
    const place = [r.branch, r.desk].filter(Boolean).join(' · ') || t('h.noPlace');
    return h('li', null, h('button', { class: `hrow${isNew ? ' is-new' : ''}`, type: 'button', onclick: () => go(`report-${r.job_id}`) },
      h('span', { class: 'hrow__date' }, fmtDate(dateOf(r)), h('br'), h('span', { class: 'faint' }, fmtDateTime(r.created_at))),
      h('span', { style: 'min-width:0' }, h('span', { class: 'hrow__file', style: 'display:block' }, r.filename), isNew ? h('span', { class: 'pill pill--new' }, t('h.new')) : null),
      h('span', { class: 'hrow__sub hrow__place' }, place),
      verdictPill(r),
      reviewPill(r)));
  }
  function renderRecent() {
    const items = state.history.slice(0, 5);
    $('#recent').hidden = !items.length;
    $('#recent-list').replaceChildren(...items.map(historyRow));
  }

  const hf = { q: $('#hf-q'), branch: $('#hf-branch'), desk: $('#hf-desk'), verdict: $('#hf-verdict'), status: $('#hf-status'), from: $('#hf-from'), to: $('#hf-to') };
  function fillSelect(sel, options, keep) {
    const cur = keep ? sel.value : '';
    sel.replaceChildren(...options.map(([v, label]) => h('option', { value: v }, label)));
    if (options.some(([v]) => v === cur)) sel.value = cur;
  }
  function renderHistory() {
    const uniq = key => [...new Set(state.history.map(r => r[key]).filter(Boolean))].sort();
    fillSelect(hf.branch, [['', t('f.allBranches')], ...uniq('branch').map(v => [v, v])], true);
    fillSelect(hf.desk, [['', t('f.allDesks')], ...uniq('desk').map(v => [v, v])], true);
    fillSelect(hf.verdict, [['', t('f.allVerdicts')], ['violation', t('f.withViol')], ['no_violation', t('f.clean')]], true);
    fillSelect(hf.status, [['', t('f.allStatus')], ['new', t('f.new')], ['unreviewed', t('f.unreviewed')], ['reviewed', t('f.reviewed')]], true);
    const q = hf.q.value.trim().toLowerCase();
    const list = state.history.filter(r => {
      const d = dateOf(r);
      const rep = r.items.filter(i => i.status === 'reported');
      const reviewed = rep.filter(i => r.reviews && r.reviews[i.key] && r.reviews[i.key].decision).length;
      if (q && !r.filename.toLowerCase().includes(q)) return false;
      if (hf.branch.value && r.branch !== hf.branch.value) return false;
      if (hf.desk.value && r.desk !== hf.desk.value) return false;
      if (hf.verdict.value && r.verdict !== hf.verdict.value) return false;
      if (hf.from.value && d < hf.from.value) return false;
      if (hf.to.value && d > hf.to.value) return false;
      if (hf.status.value === 'new' && !(r.status === 'done' && !r.seen)) return false;
      if (hf.status.value === 'unreviewed' && !(rep.length && reviewed < rep.length)) return false;
      if (hf.status.value === 'reviewed' && !(rep.length && reviewed === rep.length)) return false;
      return true;
    });
    $('#h-count').textContent = state.historyLoaded ? t('h.count', { n: list.length }) : '…';
    const ul = $('#h-list');
    if (!state.history.length) ul.replaceChildren(h('li', { class: 'empty' }, state.historyLoaded ? t('h.empty') : '…'));
    else if (!list.length) ul.replaceChildren(h('li', { class: 'empty' }, t('h.nomatch')));
    else ul.replaceChildren(...list.map(historyRow));
  }
  Object.values(hf).forEach(el => el.addEventListener(el.tagName === 'INPUT' && el.type === 'search' ? 'input' : 'change', renderHistory));
  $('#hf-reset').addEventListener('click', () => { Object.values(hf).forEach(el => { el.value = ''; }); renderHistory(); });

  /* ── сводка ──────────────────────────────────────────────────────────── */
  const sf = { period: $('#sf-period'), branch: $('#sf-branch') };
  sf.period.addEventListener('change', renderSummary);
  sf.branch.addEventListener('change', renderSummary);
  function summarize() {
    const period = sf.period.value || '7';
    const today = todayISO();
    const from = period === 'all' ? null : addDays(today, -(Number(period) - 1));
    const recs = state.history.filter(r => r.status === 'done' && (!from || dateOf(r) >= from) && (!sf.branch.value || r.branch === sf.branch.value));
    const tot = { checks: 0, withViol: 0, v: 0, c: 0, f: 0, p: 0 };
    const byType = new Map(), byDay = new Map(), byBranch = new Map();
    for (const r of recs) {
      const rep = r.items.filter(i => i.status === 'reported');
      const day = dateOf(r);
      const br = r.branch || '—';
      tot.checks++;
      if (rep.length) tot.withViol++;
      const dd = byDay.get(day) || { checks: 0, v: 0 }; dd.checks++; dd.v += rep.length; byDay.set(day, dd);
      const bb = byBranch.get(br) || { checks: 0, withViol: 0, v: 0, c: 0, f: 0 }; bb.checks++; if (rep.length) bb.withViol++;
      for (const it of rep) {
        const dec = r.reviews && r.reviews[it.key] ? r.reviews[it.key].decision : null;
        const k = dec === 'confirmed' ? 'c' : dec === 'false_positive' ? 'f' : 'p';
        tot.v++; tot[k]++; bb.v++; if (k !== 'p') bb[k]++;
        const tt = byType.get(it.rule_id) || { id: it.rule_id, count: 0, c: 0, f: 0, p: 0 }; tt.count++; tt[k]++; byType.set(it.rule_id, tt);
      }
      byBranch.set(br, bb);
    }
    let days = [];
    const keys = [...byDay.keys()].sort();
    if (keys.length) {
      let start = from || keys[0];
      const end = from ? today : keys[keys.length - 1];
      if (!from && keys.length) { const span = Math.round((new Date(`${end}T12:00:00`) - new Date(`${start}T12:00:00`)) / 86400000); if (span > 30) start = addDays(end, -30); }
      for (let d = start; d <= end; d = addDays(d, 1)) days.push([d, byDay.get(d) || { checks: 0, v: 0 }]);
    }
    return { tot, byType: [...byType.values()].sort((a, b) => b.count - a.count), days, byBranch: [...byBranch.entries()].sort((a, b) => b[1].v - a[1].v) };
  }
  const tip = $('#tip');
  function showTip(el, title, line) {
    tip.replaceChildren(h('b', null, title), line ? h('span', null, line) : null);
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    tip.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2))}px`;
    tip.style.top = `${r.top - hh - 8 < 8 ? r.bottom + 8 : r.top - hh - 8}px`;
  }
  const hideTip = () => { tip.hidden = true; };
  function bindTip(el, title, line) {
    el.addEventListener('pointerenter', () => showTip(el, title, line));
    el.addEventListener('pointerleave', hideTip);
    el.addEventListener('focus', () => showTip(el, title, line));
    el.addEventListener('blur', hideTip);
  }
  function meterCells(frac, n) {
    const on = Math.round(frac * n);
    return h('span', { class: 'meter__cells', 'aria-hidden': 'true' }, Array.from({ length: n }, (_, i) => h('i', { class: i < on ? 'on' : null })));
  }
  function renderSummary() {
    fillSelect(sf.period, [['7', t('s.p7')], ['30', t('s.p30')], ['all', t('s.pAll')]], true);
    if (!sf.period.value) sf.period.value = '7';
    const branches = [...new Set(state.history.map(r => r.branch).filter(Boolean))].sort();
    fillSelect(sf.branch, [['', t('f.allBranches')], ...branches.map(v => [v, v])], true);
    const s = summarize();
    const empty = !s.tot.checks;
    $('#s-empty').hidden = !empty || !state.historyLoaded;
    $('#s-body').hidden = empty;
    if (empty) return;
    const { tot } = s;
    const reviewed = tot.c + tot.f;
    const fp = reviewed ? tot.f / reviewed : null;
    const kpi = (label, value, sub, extra) => h('div', { class: 'kpi' }, h('span', { class: 'label' }, label), h('b', null, value), extra || null, sub ? h('small', null, sub) : null);
    $('#kpis').replaceChildren(
      kpi(t('s.k.checks'), String(tot.checks)),
      kpi(t('s.k.withViol'), String(tot.withViol), t('s.k.share', { p: Math.round(tot.withViol / tot.checks * 100) })),
      kpi(t('s.k.viol'), String(tot.v)),
      kpi(t('s.k.confirmed'), String(tot.c)),
      kpi(t('s.k.false'), String(tot.f)),
      kpi(t('s.k.fpRate'), fp == null ? '—' : pct(fp), fp == null ? t('s.k.noReviews') : `${t('s.k.ofReviewed', { n: reviewed })} · ${t('s.k.pending', { n: tot.p })}`, fp == null ? null : h('span', { class: 'meter' }, meterCells(fp, 10))));

    const typeBox = $('#c-type');
    if (!s.byType.length) typeBox.replaceChildren(h('p', { class: 'muted' }, t('s.noViol')));
    else {
      const max = Math.max(...s.byType.map(x => x.count));
      typeBox.replaceChildren(...s.byType.map(x => {
        const rule = ruleById(x.id) || { id: x.id, title: x.id };
        const title = ruleText(rule).title;
        const row = h('div', { class: 'hbar', tabindex: '0', 'aria-label': `${x.id} ${title}: ${x.count}. ${t('s.tt.type', x)}` },
          h('span', { class: 'hbar__label', title }, h('b', null, x.id), title),
          h('span', { class: 'hbar__track' }, h('span', { class: 'hbar__bar', style: `width:${Math.max(2, x.count / max * 88)}%` }), h('span', { class: 'hbar__val' }, String(x.count))));
        bindTip(row, `${x.count} · ${x.id}`, `${title}. ${t('s.tt.type', x)}`);
        return row;
      }));
    }

    const cols = $('#c-day'), axis = $('#c-day-axis');
    const maxV = Math.max(1, ...s.days.map(([, d]) => d.v));
    const maxIdx = s.days.findIndex(([, d]) => d.v === maxV);
    const every = Math.max(1, Math.ceil(s.days.length / 7));
    cols.replaceChildren(...s.days.map(([day, d], i) => {
      const col = h('div', { class: 'col', tabindex: '0', 'aria-label': `${fmtDate(day)}: ${t('s.tt.day', { c: d.checks, v: d.v })}` },
        (i === maxIdx || i === s.days.length - 1) && d.v ? h('span', { class: 'col__cap' }, String(d.v)) : null,
        h('span', { class: 'col__bar', style: `height:${d.v ? Math.max(3, d.v / maxV * 150) : 0}px` }));
      bindTip(col, `${d.v} · ${fmtDate(day)}`, t('s.tt.day', { c: d.checks, v: d.v }));
      return col;
    }));
    axis.replaceChildren(...s.days.map(([day], i) => h('span', null, i % every === 0 || i === s.days.length - 1 ? fmtDate(day) : '')));

    const tr = (...cells) => h('tr', null, cells);
    $('#t-branch').replaceChildren(
      h('thead', null, tr(h('th', null, t('s.col.branch')), h('th', { class: 'n' }, t('s.col.checks')), h('th', { class: 'n' }, t('s.col.withViol')), h('th', { class: 'n' }, t('s.col.episodes')), h('th', { class: 'n' }, t('s.col.confirmed')), h('th', { class: 'n' }, t('s.col.false')), h('th', { class: 'n' }, t('s.col.fp')))),
      h('tbody', null, s.byBranch.map(([br, b]) => tr(h('td', null, br), h('td', { class: 'n' }, b.checks), h('td', { class: 'n' }, b.withViol), h('td', { class: 'n' }, b.v), h('td', { class: 'n' }, b.c), h('td', { class: 'n' }, b.f), h('td', { class: 'n' }, b.c + b.f ? pct(b.f / (b.c + b.f)) : '—')))));
    $('#t-type').replaceChildren(
      h('thead', null, tr(h('th', null, t('s.col.type')), h('th', { class: 'n' }, t('s.col.total')), h('th', { class: 'n' }, t('s.col.confirmed')), h('th', { class: 'n' }, t('s.col.false')), h('th', { class: 'n' }, t('s.col.pending')))),
      h('tbody', null, s.byType.map(x => tr(h('td', null, `${x.id} · ${ruleText(ruleById(x.id) || { id: x.id, title: x.id }).title}`), h('td', { class: 'n' }, x.count), h('td', { class: 'n' }, x.c), h('td', { class: 'n' }, x.f), h('td', { class: 'n' }, x.p)))));
    $('#t-day').replaceChildren(
      h('thead', null, tr(h('th', null, t('s.col.day')), h('th', { class: 'n' }, t('s.col.checks')), h('th', { class: 'n' }, t('s.col.episodes')))),
      h('tbody', null, s.days.map(([day, d]) => tr(h('td', null, fmtDate(day, true)), h('td', { class: 'n' }, d.checks), h('td', { class: 'n' }, d.v)))));
  }

  /* ── отчёт ───────────────────────────────────────────────────────────── */
  const player = $('#player'), viewer = $('#viewer');
  let reportPoll = null;
  async function openReport(id) {
    clearTimeout(reportPoll);
    const stateEl = $('#report-state'), body = $('#report-body');
    if (!state.report || state.report.job_id !== id) { body.hidden = true; stateEl.hidden = false; stateEl.textContent = t('rep.loading'); }
    let data;
    try { data = await api.job(id); } catch (e) {
      body.hidden = true; stateEl.hidden = false; stateEl.textContent = t('rep.notfound'); state.report = null; return;
    }
    if (state.view !== 'report' || state.id !== id) return;
    if (data.status !== 'done' || !data.result) {
      body.hidden = true; stateEl.hidden = false;
      stateEl.textContent = data.status === 'failed' ? t('rep.failed', { error: data.error || '' }) : t('rep.processing', { stage: data.stage_label || t('st.detect') });
      if (data.status !== 'failed') reportPoll = setTimeout(() => { if (state.view === 'report' && state.id === id) openReport(id); }, 1500);
      return;
    }
    stateEl.hidden = true; body.hidden = false;
    const fresh = !state.report || state.report.job_id !== id;
    state.report = data;
    if (fresh) { state.active = 0; stopLoop(); $('#json-fold').open = false; }
    renderReport(data);
    if (data.meta && !data.meta.seen) { try { await api.seen(id); } catch (e) { /* не критично */ } markSeenLocal(id); }
  }
  $('#back-btn').addEventListener('click', () => { if (history.length > 1) history.back(); else go('history'); });
  $('#print-btn').addEventListener('click', () => { if (state.report) go(`print-${state.report.job_id}`); });
  $('#keys-btn').addEventListener('click', () => openDialog($('#keys-dialog')));
  $('#keys-close').addEventListener('click', () => closeDialog($('#keys-dialog')));

  function allItems(r) { return [...r.violations, ...(r.review || [])]; }
  function renderReport(data) {
    const r = data.result, meta = data.meta || {};
    const bad = r.verdict === 'violation';
    const n = r.violations.length;
    $('#verdict').classList.toggle('is-bad', bad);
    $('#verdict-title').textContent = bad ? t('verdict.violation') : t('verdict.clean');
    $('#verdict-sub').textContent = bad ? t('rep.sub.bad', { n, ep: pl('ep', n) }) : t('rep.sub.clean');
    const mg = $('#meta-grid');
    const cell = (k, v) => (v ? h('div', null, h('dt', null, k), h('dd', null, v)) : null);
    mg.replaceChildren(...[
      cell(t('meta.file'), data.filename || meta.filename),
      cell(t('meta.branch'), meta.branch), cell(t('meta.desk'), meta.desk),
      cell(t('meta.date'), meta.shot_date ? fmtDate(meta.shot_date, true) : ''),
      cell(t('meta.duration'), r.video ? fmtClock(r.video.duration_sec) : ''),
      cell(t('meta.analysis'), r.timings ? fmtSec(r.timings.total_sec) : ''),
      cell(t('meta.job'), data.job_id),
    ].filter(Boolean));
    const notes = (r.notes || []).join(' ');
    $('#report-notes').textContent = notes;
    $('#report-notes').hidden = !notes;
    setupMedia(data);
    buildTimeline(r);
    $('#findings-title').textContent = n ? t('f.titleN', { n }) : t('f.title');
    const cards = $('#cards');
    cards.replaceChildren(...(n ? r.violations.map((v, i) => card(v, i, false, data)) : [h('p', { class: 'empty' }, t('f.empty'))]));
    const rv = r.review || [];
    $('#review-fold').hidden = !rv.length;
    $('#review-title').textContent = t('review.title', { n: rv.length });
    $('#review-list').replaceChildren(...rv.map((v, i) => card(v, i, true, data)));
    setActive(Math.min(state.active, Math.max(0, allItems(r).length - 1)), false);
  }

  function reviewOf(data, key) { return (data.meta && data.meta.reviews && data.meta.reviews[key]) || { decision: null, comment: '' }; }
  function card(v, i, isReview, data) {
    const rule = v.rule;
    const rt = ruleText(rule);
    const frames = v.frames || [];
    const media = h('div', { class: `frames frames--${Math.min(frames.length, 3) || 1}` },
      frames.map((f, k) => h('button', { class: 'frame', type: 'button', 'aria-label': t('card.openFrame', { t: fmtTc(f.timestamp_sec) }), onclick: () => openLightbox(f, v) },
        h('img', { src: imgSrc(f.image_base64), alt: `${fmtTc(f.timestamp_sec)} · ${rt.title}`, loading: 'lazy' }),
        h('span', { class: 'frame__t' }, `${k === 0 ? `${t('card.main')} · ` : ''}${fmtTc(f.timestamp_sec)}`))));
    const refs = (rule.refs || []).filter(x => x.verified);
    const rv = reviewOf(data, v.key);
    const watchBtn = h('button', { class: 'btn btn--small js-watch', type: 'button', 'data-key': v.key, onclick: () => toggleWatch(v, data) }, isWatching(v.key) ? t('card.stop') : t('card.watch'));
    const okBtn = h('button', { class: 'btn btn--ghost btn--small btn--ok', type: 'button', 'aria-pressed': String(rv.decision === 'confirmed'), onclick: () => decide(data, v, 'confirmed') }, t('rv.confirm'));
    const noBtn = h('button', { class: 'btn btn--ghost btn--small btn--bad', type: 'button', 'aria-pressed': String(rv.decision === 'false_positive'), onclick: () => decide(data, v, 'false_positive') }, t('rv.false'));
    const stateTxt = h('span', { class: 'review-box__state', role: 'status' }, t(rv.decision ? `rv.${rv.decision}` : 'rv.none'));
    const area = h('textarea', { class: 'textarea', rows: '2', 'aria-label': t('rv.comment'), placeholder: t('rv.comment.ph') });
    area.value = rv.comment || '';
    const saveComment = debounce(() => saveReview(data, v, reviewOf(data, v.key).decision, area.value, stateTxt), 700);
    area.addEventListener('input', () => { stateTxt.textContent = t('rv.saving'); saveComment(); });
    const body = h('div', { class: 'vcard__body' },
      h('div', { class: 'vcard__head' },
        h('span', { class: 'vnum' }, String(i + 1)),
        h('div', null, h('p', { class: 'label', style: 'margin-bottom:4px' }, `${rule.id} · ${groupName(rule.group)}`), h('h3', { class: 'vcard__title' }, rt.title)),
        h('button', { class: 'tc', type: 'button', onclick: () => { setActive(allItems(state.report.result).indexOf(v), false); seek(v.timecode, true); } }, h('span', null, t('card.timecode')), h('b', null, fmtTc(v.timecode)))),
      isReview && v.review_reason ? h('p', { class: 'reason' }, v.review_reason) : null,
      h('dl', { class: 'dl' },
        h('dt', null, t('card.seen')), h('dd', { class: 'read' }, v.observed),
        h('dt', null, t('card.why')), h('dd', { class: 'read' }, rule.why),
        h('dt', null, t('card.rule')),
        h('dd', null,
          rule.citation ? h('p', { class: 'cite read' }, rule.citation) : h('p', { class: 'muted' }, t('card.noRef')),
          refs.length ? h('ul', { class: 'refs' }, refs.map(ref => h('li', null,
            h('a', { href: ref.url, target: '_blank', rel: 'noopener' }, `${ref.source}, ${ref.point} — ${t('card.adilet')}`),
            ref.quote ? h('q', null, ref.quote) : null))) : null,
          t('card.ruleRu') ? h('p', { class: 'ru-note' }, t('card.ruleRu')) : null)),
      h('div', { class: 'review-box' },
        h('div', { class: 'review-box__btns' }, watchBtn, okBtn, noBtn, stateTxt),
        h('label', { class: 'field' }, h('span', null, t('rv.comment')), area)),
      h('div', { class: 'vcard__foot' },
        h('span', { class: 'meter' }, meterCells(v.confidence, 10), t('card.conf', { p: Math.round(v.confidence * 100) })),
        v.t_end != null && v.t_end - v.timecode >= 0.5 ? h('span', null, t('card.segment', { a: fmtTc(v.timecode), b: fmtTc(v.t_end) })) : null,
        v.source ? h('span', null, t('card.detector', { d: v.source })) : null));
    const el = h('article', { class: `vcard${isReview ? ' is-review' : ''}`, 'data-key': v.key }, media, body);
    el.addEventListener('click', e => { if (!e.target.closest('button,a,textarea')) setActive(allItems(state.report.result).indexOf(v), false); });
    return el;
  }
  async function decide(data, v, decision) {
    const cur = reviewOf(data, v.key);
    const next = cur.decision === decision ? null : decision;
    const el = $(`.vcard[data-key="${v.key}"]`);
    const comment = el ? el.querySelector('textarea').value : cur.comment;
    await saveReview(data, v, next, comment, el && el.querySelector('.review-box__state'));
  }
  async function saveReview(data, v, decision, comment, stateEl) {
    try {
      const res = await api.review(data.job_id, v.key, decision, comment);
      data.meta = data.meta || {};
      data.meta.reviews = res.reviews;
      const rec = state.history.find(r => r.job_id === data.job_id);
      if (rec) rec.reviews = res.reviews;
      const el = $(`.vcard[data-key="${v.key}"]`);
      if (el) {
        const rv = reviewOf(data, v.key);
        el.querySelector('.btn--ok').setAttribute('aria-pressed', String(rv.decision === 'confirmed'));
        el.querySelector('.btn--bad').setAttribute('aria-pressed', String(rv.decision === 'false_positive'));
        const st = el.querySelector('.review-box__state');
        st.textContent = `${t(rv.decision ? `rv.${rv.decision}` : 'rv.none')} · ${t('rv.saved')}`;
      }
    } catch (e) {
      if (stateEl) stateEl.textContent = t('rv.error');
    }
  }

  /* активный эпизод и горячие клавиши */
  function setActive(idx, scroll) {
    const r = state.report && state.report.result;
    if (!r) return;
    const items = allItems(r);
    if (!items.length || idx < 0) return;
    state.active = Math.max(0, Math.min(items.length - 1, idx));
    const v = items[state.active];
    $$('.vcard').forEach(el => el.classList.toggle('is-active', el.dataset.key === v.key));
    if (scroll) {
      if (v.status === 'review') $('#review-fold').open = true;
      const el = $(`.vcard[data-key="${v.key}"]`);
      if (el) el.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'center' });
      seek(v.timecode, false);
    }
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { langMenu.hidden = true; }
    if (state.view !== 'report' || !state.report || e.altKey || e.ctrlKey || e.metaKey || isTyping(e.target)) return;
    if ($('#lightbox').open || $('#keys-dialog').open) return;
    const items = allItems(state.report.result);
    const v = items[state.active];
    const k = e.key.toLowerCase();
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' && e.shiftKey) { e.preventDefault(); setActive(state.active + 1, true); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setActive(state.active - 1, true); }
    else if ((k === 'y' || k === 'н') && v) { e.preventDefault(); decide(state.report, v, 'confirmed'); }
    else if ((k === 'n' || k === 'т') && v) { e.preventDefault(); decide(state.report, v, 'false_positive'); }
    else if ((k === 'w' || k === 'ц') && v) { e.preventDefault(); toggleWatch(v, state.report); }
    else if ((k === 'c' || k === 'с') && v) { const el = $(`.vcard[data-key="${v.key}"] textarea`); if (el) { e.preventDefault(); el.focus(); } }
    else if (k === 'p' || k === 'з') { e.preventDefault(); go(`print-${state.report.job_id}`); }
  });

  /* видео, кадры и «Смотреть» */
  function setupMedia(data) {
    const r = data.result;
    state.thumbs = r.thumbs || [];
    const url = state.local.get(data.job_id);
    player.onerror = null;
    if (url) {
      viewer.hidden = true;
      player.hidden = false;
      state.playerOk = false;
      if (player.getAttribute('src') !== url) player.src = url;
      player.onloadeddata = () => { state.playerOk = true; };
      player.onerror = () => { state.playerOk = false; player.hidden = true; showFrame(firstMark(r)); $('#screen-cap').textContent = t('screen.cantplay'); };
      $('#screen-cap').textContent = '';
    } else {
      player.hidden = true;
      player.removeAttribute('src');
      state.playerOk = false;
      showFrame(firstMark(r));
      $('#screen-cap').textContent = data.meta && data.meta.origin === 'ui' ? t('screen.nofile') : t('screen.frame', { t: fmtClock(firstMark(r)) });
    }
  }
  function firstMark(r) { const v = r.violations[0] || (r.review || [])[0]; return v ? Math.floor(v.timecode) : 0; }
  function showFrame(sec) {
    viewer.hidden = false;
    const b64 = state.thumbs[Math.min(sec, state.thumbs.length - 1)];
    viewer.src = b64 ? imgSrc(b64) : '';
    viewer.alt = fmtClock(sec);
    viewer.classList.toggle('is-pixel', !LIVE);
    markNow(sec);
  }
  function seek(sec, scroll) {
    stopLoop();
    if (!player.hidden && player.getAttribute('src')) { try { player.currentTime = sec; player.pause(); } catch (e) { /* ещё грузится */ } }
    else { showFrame(Math.floor(sec)); $('#screen-cap').textContent = t('screen.frame', { t: fmtClock(sec) }); }
    markNow(Math.floor(sec));
    if (scroll) $('#screen').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'center' });
  }
  player.addEventListener('timeupdate', () => {
    const L = state.loop;
    if (L && L.mode === 'video' && (player.currentTime >= L.b || player.currentTime < L.a - 0.5)) { player.currentTime = L.a; if (player.paused) player.play().catch(() => {}); }
    markNow(Math.floor(player.currentTime));
  });
  const isWatching = key => !!(state.loop && state.loop.key === key);
  function stopLoop() {
    if (!state.loop) return;
    clearInterval(state.loop.timer);
    if (state.loop.mode === 'video') { try { player.pause(); } catch (e) { /* ок */ } }
    const key = state.loop.key;
    state.loop = null;
    $('#loopbar').hidden = true;
    const b = $(`.js-watch[data-key="${key}"]`);
    if (b) b.textContent = t('card.watch');
  }
  $('#loop-stop').addEventListener('click', stopLoop);
  async function toggleWatch(v, data) {
    if (isWatching(v.key)) { stopLoop(); return; }
    stopLoop();
    const dur = data.result.video ? data.result.video.duration_sec : v.timecode + 3;
    const a = Math.max(0, v.timecode - 3), b = Math.min(dur, v.timecode + 3);
    setActive(allItems(data.result).indexOf(v), false);
    const btn = $(`.js-watch[data-key="${v.key}"]`);
    if (btn) btn.textContent = t('card.stop');
    const bar = $('#loopbar');
    if (!player.hidden && player.getAttribute('src') && player.readyState >= 1 && !player.error) {
      state.loop = { mode: 'video', key: v.key, a, b };
      player.currentTime = a;
      player.play().catch(() => {});
      $('#loop-text').textContent = t('loop.label', { a: fmtTc(a), b: fmtTc(b) });
    } else {
      const ck = `${data.job_id}:${v.key}`;
      let clip = state.clips.get(ck);
      if (clip === undefined) { clip = await api.clip(data.job_id, v.key); state.clips.set(ck, clip); }
      if (!state.loop && btn && btn.textContent !== t('card.stop')) return;
      const frames = clip && clip.frames && clip.frames.length ? clip.frames.map(f => ({ t: f.t, b64: f.b64 }))
        : (v.frames || []).map(f => ({ t: f.timestamp_sec, b64: f.image_base64 }));
      const fps = clip && clip.frames && clip.frames.length ? clip.fps : 1;
      player.hidden = true;
      viewer.hidden = false;
      viewer.classList.toggle('is-pixel', !LIVE);
      let i = 0;
      const step = () => { const f = frames[i % frames.length]; viewer.src = imgSrc(f.b64); markNow(Math.floor(f.t)); i++; };
      step();
      state.loop = { mode: 'flip', key: v.key, a, b, timer: setInterval(step, 1000 / fps) };
      $('#loop-text').textContent = clip ? `${t('loop.label', { a: fmtTc(clip.t0), b: fmtTc(clip.t1) })} ${t('loop.flip', { fps: clip.fps })}` : t('loop.none');
    }
    bar.hidden = false;
    $('#screen').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'center' });
  }

  /* таймлайн */
  let tlStep = 1, lastNow = -1;
  function markNow(sec) {
    const idx = Math.floor(sec / tlStep);
    if (idx === lastNow) return;
    const prev = $('#tl .is-now');
    if (prev) prev.classList.remove('is-now');
    const el = $(`#tl [data-i="${idx}"]`);
    if (el) el.classList.add('is-now');
    lastNow = idx;
  }
  function fitTimeline() {
    const tl = $('#tl');
    const n = tl.children.length;
    if (!n || !tl.clientWidth) return;
    const cols = Math.max(1, Math.min(n, Math.floor((tl.clientWidth - 12 + 3) / 17)));
    tl.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  }
  if (window.ResizeObserver) new ResizeObserver(fitTimeline).observe($('#tl'));
  function buildTimeline(r) {
    const tl = $('#tl');
    lastNow = -1;
    const dur = (r.video && r.video.duration_sec) || (r.activity || []).length || 1;
    const secs = Math.max(1, Math.ceil(dur));
    tlStep = Math.max(1, Math.ceil(secs / 240));
    $('#tl-title').textContent = t('tl.title', { step: tlStep === 1 ? t('tl.sec1') : t('tl.secN', { n: tlStep }) });
    $('#tl-end').textContent = fmtClock(dur);
    const slots = Math.ceil(secs / tlStep);
    const bad = new Map(), rev = new Map();
    const mark = (map, v) => {
      const a = Math.floor(v.timecode / tlStep), b = Math.floor((v.t_end != null ? v.t_end : v.timecode) / tlStep);
      for (let i = a; i <= Math.min(b, slots - 1); i++) if (!map.has(i)) map.set(i, v);
    };
    r.violations.forEach(v => mark(bad, v));
    (r.review || []).forEach(v => mark(rev, v));
    const act = r.activity || [];
    const nodes = [];
    for (let i = 0; i < slots; i++) {
      let a = 0;
      for (let s = i * tlStep; s < (i + 1) * tlStep; s++) a = Math.max(a, act[s] || 0);
      const sec = i * tlStep;
      const v = bad.get(i) || rev.get(i);
      const el = h('button', {
        class: ['tl-slot', bad.has(i) ? 'is-bad' : rev.has(i) ? 'is-review' : '', sec > 0 && sec % 10 === 0 ? 'is-ten' : ''].join(' ').trim(),
        type: 'button', 'data-i': i, 'data-l': a > 0.66 ? 3 : a > 0.33 ? 2 : a > 0.12 ? 1 : 0,
        'aria-label': `${fmtClock(sec)}${v ? ` — ${v.rule.id} ${ruleText(v.rule).title}` : ''}`,
      });
      el.addEventListener('click', () => { seek(sec, false); if (v) setActive(allItems(r).indexOf(v), false); });
      el.addEventListener('pointerenter', () => showSlotTip(el, sec, v, bad.has(i)));
      el.addEventListener('focus', () => showSlotTip(el, sec, v, bad.has(i)));
      el.addEventListener('pointerleave', hideTip);
      el.addEventListener('blur', hideTip);
      nodes.push(el);
    }
    tl.replaceChildren(...nodes);
    fitTimeline();
  }
  function showSlotTip(el, sec, v, isBad) {
    const b64 = state.thumbs && state.thumbs[Math.min(sec, state.thumbs.length - 1)];
    tip.replaceChildren(
      b64 ? h('img', { src: imgSrc(b64), alt: '', style: `display:block;width:160px;aspect-ratio:16/9;object-fit:cover;margin-bottom:6px;${LIVE ? '' : 'image-rendering:pixelated'}` }) : null,
      h('b', null, fmtClock(sec)),
      v ? h('span', null, `${v.rule.id} · ${isBad ? t('legend.bad') : t('legend.review')}`) : null);
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    tip.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2))}px`;
    tip.style.top = `${r.top - hh - 8 < 8 ? r.bottom + 8 : r.top - hh - 8}px`;
  }

  /* лайтбокс, диалоги, JSON */
  function openDialog(d) { if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', ''); }
  function closeDialog(d) { if (typeof d.close === 'function') d.close(); else d.removeAttribute('open'); }
  function openLightbox(f, v) {
    $('#lb-img').src = imgSrc(f.image_base64);
    $('#lb-img').alt = `${fmtTc(f.timestamp_sec)} · ${ruleText(v.rule).title}`;
    $('#lb-cap').textContent = `${v.rule.id} · ${fmtTc(f.timestamp_sec)} · ${ruleText(v.rule).title}`;
    openDialog($('#lightbox'));
  }
  $('#lb-close').addEventListener('click', () => closeDialog($('#lightbox')));
  $('#lightbox').addEventListener('click', e => { if (e.target === e.currentTarget) closeDialog(e.currentTarget); });
  $('#keys-dialog').addEventListener('click', e => { if (e.target === e.currentTarget) closeDialog(e.currentTarget); });
  let jsonFull = '';
  $('#json-fold').addEventListener('toggle', async e => {
    if (!e.currentTarget.open || !state.report) return;
    const id = state.report.job_id;
    const pre = $('#json-pre');
    pre.textContent = '…';
    let data = state.apiCache.get(id);
    if (!data) { try { data = await api.apiJson(id); state.apiCache.set(id, data); } catch (x) { data = null; } }
    jsonFull = data ? JSON.stringify(data, null, 2) : '';
    pre.textContent = data ? JSON.stringify(data, (k, val) => (k === 'image_base64' && typeof val === 'string' && val.length > 60 ? `${val.slice(0, 24)}… (${Math.round(val.length * 0.75 / 1024)} KB JPEG)` : val), 2) : '—';
  });
  async function copyText(text, btn, fallbackEl) {
    const label = btn.textContent;
    try { await navigator.clipboard.writeText(text); btn.textContent = t('copy.done'); } catch (e) {
      if (fallbackEl) { const sel = getSelection(); const range = document.createRange(); range.selectNodeContents(fallbackEl); sel.removeAllRanges(); sel.addRange(range); }
      btn.textContent = t('copy.select');
    }
    setTimeout(() => { btn.textContent = label; }, 1800);
  }
  $('#copy-json').addEventListener('click', e => copyText(jsonFull, e.currentTarget, $('#json-pre')));
  $$('.js-copy').forEach(b => b.addEventListener('click', e => { const el = $(`#${b.dataset.copy}`); copyText(el.textContent, e.currentTarget, el); }));
  $$('.js-origin').forEach(el => { el.textContent = LIVE ? location.origin : 'https://oko.example.kz'; });
  if (BOOT.version) $('#version').textContent = BOOT.version;

  /* ── печатная форма ──────────────────────────────────────────────────── */
  async function renderPrint(id) {
    const root = $('#print-view');
    stopLoop();
    root.replaceChildren(h('div', { class: 'pdoc' }, h('p', null, t('rep.loading'))));
    let data;
    try { data = await api.job(id); } catch (e) { data = null; }
    if (!data || !data.result) { root.replaceChildren(h('div', { class: 'pdoc' }, h('p', null, data ? t('rep.processing', { stage: data.stage_label || '' }) : t('rep.notfound')))); return; }
    const r = data.result, meta = data.meta || {};
    const bad = r.verdict === 'violation';
    const decisionText = key => { const rv = reviewOf(data, key); return t(rv.decision ? `rv.${rv.decision}` : 'rv.none'); };
    const counts = { c: 0, f: 0, p: 0 };
    r.violations.forEach(v => { const d = reviewOf(data, v.key).decision; counts[d === 'confirmed' ? 'c' : d === 'false_positive' ? 'f' : 'p']++; });
    const row = (k, v) => (v ? h('tr', null, h('th', null, k), h('td', null, v)) : null);
    const episode = (v, i, isReview) => {
      const rv = reviewOf(data, v.key);
      const refs = (v.rule.refs || []).filter(x => x.verified && x.quote);
      return h('section', { class: 'pep' },
        h('h3', null, `${t('pr.episode', { i: i + 1 })} · ${v.rule.id} · ${fmtTc(v.timecode)} — ${ruleText(v.rule).title}`),
        h('div', { class: 'pframes' }, (v.frames || []).slice(0, 3).map(f => h('img', { src: imgSrc(f.image_base64), alt: fmtTc(f.timestamp_sec) }))),
        h('dl', null,
          h('dt', null, t('card.timecode')), h('dd', null, v.t_end != null && v.t_end - v.timecode >= 0.5 ? `${fmtTc(v.timecode)} – ${fmtTc(v.t_end)}` : fmtTc(v.timecode)),
          h('dt', null, t('card.seen')), h('dd', null, v.observed),
          h('dt', null, t('card.why')), h('dd', null, v.rule.why),
          h('dt', null, t('card.rule')), h('dd', null, v.rule.citation || t('card.noRef'), refs.map(x => h('div', { style: 'margin-top:4px;color:var(--paper-muted)' }, `${x.source}, ${x.point}: «${x.quote}»`))),
          h('dt', null, t('pr.confidence')), h('dd', null, `${Math.round(v.confidence * 100)}%`),
          isReview ? null : h('dt', null, t('pr.decision')), isReview ? null : h('dd', null, h('b', null, decisionText(v.key))),
          rv.comment ? h('dt', null, t('pr.comment')) : null, rv.comment ? h('dd', null, rv.comment) : null));
    };
    const back = () => go(`report-${id}`);
    root.replaceChildren(
      h('div', { class: 'ptools' },
        h('span', null, t('pr.hint')),
        h('span', { style: 'display:flex;gap:18px;flex-wrap:wrap' },
          h('button', { class: 'btn btn--small', type: 'button', onclick: () => { try { window.print(); } catch (e) { /* печать недоступна */ } } }, t('pr.print')),
          h('button', { class: 'btn btn--ghost btn--small', type: 'button', onclick: back }, t('pr.close')))),
      h('article', { class: 'pdoc' },
        h('p', { class: 'pbrand' }, 'OKO · VIDEO REVIEW'),
        h('h1', null, t('pr.title')),
        h('p', { style: 'color:var(--paper-muted)' }, `${t('pr.generated')}: ${fmtDateTime(new Date().toISOString())}`),
        h('table', { class: 'ptable' }, h('tbody', null,
          row(t('meta.branch'), meta.branch), row(t('meta.desk'), meta.desk),
          row(t('meta.date'), meta.shot_date ? fmtDate(meta.shot_date, true) : ''),
          row(t('meta.file'), data.filename || meta.filename),
          row(t('meta.duration'), r.video ? fmtClock(r.video.duration_sec) : ''),
          row(t('meta.created'), fmtDateTime(meta.created_at)),
          row(t('meta.job'), data.job_id))),
        h('p', { class: `pverdict${bad ? ' is-bad' : ''}` }, bad ? `${t('verdict.violation')}: ${r.violations.length}` : t('verdict.clean')),
        bad ? h('p', { style: 'margin-top:8px' }, t('pr.summary', counts)) : null,
        h('h2', null, t('f.title')),
        r.violations.length ? r.violations.map((v, i) => episode(v, i, false)) : h('p', null, t('pr.none')),
        (r.review || []).length ? [h('h2', null, t('pr.reviewItems')), r.review.map((v, i) => episode(v, i, true))] : null,
        h('div', { class: 'psign' }, h('div', null, t('pr.reviewer')), h('div', null, t('pr.date'))),
        h('p', { class: 'pnote' }, t('pr.disclaimer'))));
    window.scrollTo(0, 0);
  }

  /* ── каталог норм ────────────────────────────────────────────────────── */
  function renderCatalog() {
    if (!CATALOG) return;
    const wrap = $('#catalog');
    const groups = CATALOG.groups.concat(['Прочее']);
    wrap.replaceChildren(...groups.map(g => {
      const rules = CATALOG.rules.filter(r => r.group === g);
      if (!rules.length) return null;
      return h('section', { class: 'card' },
        h('h2', { style: 'font-size:18px;margin-bottom:6px' }, groupName(g)),
        h('ul', { class: 'cat-list' }, rules.map(r => {
          const rt = ruleText(r);
          return h('li', { class: 'cat-item' },
            h('span', { class: 'code-chip' }, r.id),
            h('div', null, h('h3', null, rt.title), h('p', { class: 'muted read' }, rt.hint),
              h('p', { class: 'cat-refs' }, r.refs.length ? r.refs.map(ref => h('a', {
                href: ref.url, target: '_blank', rel: 'noopener', class: ref.verified ? null : 'is-unverified',
                title: ref.verified ? t('n.verified') : t('n.unverifiedTitle'),
              }, `${ref.source} ${ref.point}${ref.verified ? '' : ` · ${t('n.verifying')}`}`)) : h('span', { class: 'faint' }, t('n.noRef')))),
            h('span', { class: `lvl lvl--${r.level}`, title: t(`n.lv${r.level}`) }, r.level));
        })));
    }).filter(Boolean));
    $('#sources').replaceChildren(...CATALOG.sources.map(s => h('li', null, h('b', null, s.code), ' — ', h('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.title), h('br'), h('span', { class: 'faint' }, s.act))));
    const nc = NC_I18N[LANG] || CATALOG.not_claimed;
    $('#not-claimed').replaceChildren(...nc.map(x => h('li', null, x)));
  }

  /* ── старт ───────────────────────────────────────────────────────────── */
  async function start() {
    if (!CATALOG && LIVE) { try { CATALOG = await getJSON('/ui/v1/catalog'); } catch (e) { /* без каталога */ } }
    $('#demo-banner').hidden = LIVE;
    applyStatic();
    renderCatalog();
    updateRunBtn();
    updateNotifBtn();
    await route();
    refreshHistory();
    refreshStatus();
    setInterval(refreshStatus, 10000);
    if (LIVE) setInterval(() => { if (!document.hidden) refreshHistory(); }, 30000);
  }
  start();
})();
