/* Демо-адаптер: те же методы, что у настоящего API (app.js → LiveApi), но всё в памяти браузера.
   Включается, только когда страница открыта без сервера OKO (например, как статическое превью).
   Кадры — пиксельная сцена «вид сверху»; для своего видео — кадры из него самого. */
window.OKO_makeDemoApi = function (env) {
  'use strict';
  const jobs = new Map();
  const W = 160, H = 90;

  /* ── сцена ─────────────────────────────────────────── */
  function scene(t, ev) {
    const on = k => ev[k] && t >= ev[k][0] && t < ev[k][1];
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const g = c.getContext('2d');
    for (let y = 0; y < H; y += 10) for (let x = 0; x < W; x += 10) {
      const odd = ((x + y) / 10) % 2;
      g.fillStyle = y < 34 ? (odd ? '#5d5a66' : '#66636f') : (odd ? '#7f858c' : '#899097');
      g.fillRect(x, y, 10, 10);
    }
    g.fillStyle = '#4a4655'; g.fillRect(0, 0, W, 3);
    g.fillStyle = '#8a5a32'; g.fillRect(8, 34, 144, 10);
    g.fillStyle = '#a8743f'; g.fillRect(8, 34, 144, 2);
    g.fillStyle = '#a9d4e4'; g.fillRect(8, 44, 144, 2);
    g.fillStyle = '#6b7076'; g.fillRect(71, 41, 18, 9);
    g.fillStyle = '#9aa0a6'; g.fillRect(72, 42, 16, 7);
    g.fillStyle = '#34383e'; g.fillRect(112, 35, 13, 8);
    g.fillStyle = '#57d16a'; g.fillRect(114, 37, 4, 1);
    const cash = (x, y) => { g.fillStyle = '#4f9a57'; g.fillRect(x, y, 15, 6); g.fillStyle = '#7fcf86'; for (let i = 0; i < 4; i++) g.fillRect(x + 1 + i * 4, y + 1, 2, 4); };
    if (!on('countAway') && !on('overGlass')) cash(46, 36);
    if (on('bag')) { g.fillStyle = '#2f5d3a'; g.fillRect(72, 41, 16, 9); g.fillStyle = '#d64545'; g.fillRect(79, 44, 3, 3); }
    const person = (x, y, coat, hair) => {
      g.fillStyle = coat; g.fillRect(x, y + 3, 20, 9);
      g.fillStyle = hair; g.fillRect(x + 6, y, 8, 8);
    };
    if (!on('away')) {
      if (on('countAway')) {
        person(30, 12, '#2f4f8f', '#3a2a1f');
        cash(30, 24);
        g.fillStyle = '#d9a77c'; g.fillRect(29, 25, 3, 3); g.fillRect(45, 25, 3, 3);
      } else {
        const dx = Math.round(Math.sin(t * 0.8) * 2);
        person(70 + dx, 16, '#2f4f8f', '#3a2a1f');
        g.fillStyle = '#25406f'; g.fillRect(70 + dx, 26, 20, 2);
        g.fillStyle = '#d9a77c'; g.fillRect(69 + dx, 29, 3, 3); g.fillRect(88 + dx, 29, 3, 3);
        if (on('phone')) { g.fillStyle = '#15171a'; g.fillRect(89 + dx, 25, 5, 8); g.fillStyle = '#6fd0ff'; g.fillRect(90 + dx, 26, 3, 6); }
        if (on('overGlass')) { cash(40, 41); g.fillStyle = '#d9a77c'; g.fillRect(55, 40, 10, 3); }
      }
    } else {
      g.fillStyle = '#48444f'; g.fillRect(74, 17, 12, 10);
      g.fillStyle = '#3b3842'; g.fillRect(74, 25, 12, 2);
    }
    if (on('clientIn')) {
      const dx = Math.round(Math.sin(t * 0.5) * 3);
      person(67 + dx, 60, '#8f3a46', '#4a3322');
      g.fillStyle = '#e0b48a'; g.fillRect(77 + dx, 55, 3, 4);
    }
    if (on('collector')) { person(26, 58, '#5f6b52', '#2b2b2b'); g.fillStyle = '#c9c9c9'; g.fillRect(31, 70, 10, 2); }
    if (on('dark')) {
      g.fillStyle = 'rgba(8,8,10,0.94)'; g.fillRect(0, 0, W, H);
      g.fillStyle = 'rgba(40,40,46,0.6)';
      for (let i = 0; i < 40; i++) g.fillRect((i * 37) % W, (i * 53) % H, 2, 2);
    }
    return c;
  }

  const toB64 = (canvas, q) => canvas.toDataURL('image/jpeg', q).split(',')[1];

  function stamp(src, t, ruleId, boxes, scale) {
    const big = document.createElement('canvas');
    big.width = src.width * scale; big.height = src.height * scale;
    const g = big.getContext('2d');
    g.imageSmoothingEnabled = false;
    g.drawImage(src, 0, 0, big.width, big.height);
    const k = big.width / 160;
    g.font = `bold ${Math.round(4 * k)}px system-ui, sans-serif`;
    g.textBaseline = 'top';
    for (const [x1, y1, x2, y2, label] of boxes || []) {
      g.strokeStyle = '#e03a3a'; g.lineWidth = Math.max(2, k * 0.8);
      g.strokeRect(x1 * k, y1 * k, (x2 - x1) * k, (y2 - y1) * k);
      const w = g.measureText(label).width + 2.4 * k;
      g.fillStyle = '#e03a3a'; g.fillRect(x1 * k, Math.max(0, y1 * k - 6 * k), w, 6 * k);
      g.fillStyle = '#ffffff'; g.fillText(label, x1 * k + 1.2 * k, Math.max(0, y1 * k - 6 * k) + 0.8 * k);
    }
    const tag = `OKO · ${ruleId} · ${env.fmtTc(t)}`;
    const w = g.measureText(tag).width + 2.4 * k;
    g.fillStyle = '#14111d'; g.fillRect(2 * k, 2 * k, w, 6.4 * k);
    g.fillStyle = '#ffffff'; g.fillText(tag, 3.2 * k, 2.9 * k);
    return toB64(big, 0.86);
  }

  const BOXES = {
    V01: [[86, 23, 98, 35, 'телефон в руке']],
    V03: [[64, 13, 96, 32, 'место кассира пусто'], [62, 53, 96, 75, 'клиент у окна']],
    V04: [[44, 34, 64, 43, 'наличные на столе']],
    V05: [[26, 10, 52, 31, 'пересчёт у задней стенки']],
    V12: [[36, 37, 66, 50, 'передача поверх стекла']],
    V14: [[70, 39, 92, 52, 'сумка без осмотра пломбы']],
  };

  /* ── примеры проверок ──────────────────────────────── */
  const SAMPLES = [
    { file: 'касса1_утро.mov', branch: 'Отделение №1', desk: 'Касса 1', days: 0, dur: 34, seen: false,
      ev: { phone: [5.8, 9.6], away: [19.2, 27.5], clientIn: [2.5, 31] },
      items: [
        { id: 'V01', tc: 6.2, end: 9.6, conf: 0.91, main: 6.8, obs: 'С 0:06 по 0:09 кассир держит в руке смартфон над рабочим столом, рядом лежат наличные' },
        { id: 'V03', tc: 19.4, end: 27.5, conf: 0.88, main: 20.6, obs: 'В 0:19 кассир встаёт и выходит из кабины; клиент остаётся у окна, наличные лежат на столе', review: ['confirmed', 'Кассир отошёл на 8 с, клиент ждал у окна'] },
      ],
      reviewItems: [{ id: 'V07', tc: 3.4, conf: 0.41, obs: 'В начале обслуживания в окне не видно документа клиента; он мог быть показан вне кадра' }] },
    { file: 'касса2_утро.mov', branch: 'Отделение №1', desk: 'Касса 2', days: 0, dur: 26, seen: false, ev: { clientIn: [3, 20] }, items: [] },
    { file: 'касса1_день.mov', branch: 'Отделение №2', desk: 'Касса 1', days: 1, dur: 41, seen: true, ev: { clientIn: [2, 38] },
      items: [{ id: 'V04', tc: 12.0, end: 18.5, conf: 0.74, main: 13.0, obs: 'С 0:12 по 0:18 принятые наличные лежат на столе открыто, кассир обслуживает следующего клиента', review: ['false_positive', 'Это деньги клиента в лотке, не кассовые'] }] },
    { file: 'инкассация_вечер.mov', branch: 'Отделение №2', desk: 'Касса 3', days: 2, dur: 52, seen: true, ev: { bag: [18, 30], collector: [15, 40] },
      items: [{ id: 'V14', tc: 21.6, end: 24.0, conf: 0.82, main: 22.0, obs: 'В 0:21 кассир принимает сумку инкассации и сразу убирает её, не осматривая пломбу и шов', review: ['confirmed', ''] }] },
    { file: 'касса2_день.mov', branch: 'Отделение №3', desk: 'Касса 2', days: 3, dur: 30, seen: true, ev: { dark: [8, 11], countAway: [17, 21], clientIn: [3, 27] },
      items: [
        { id: 'V13', tc: 8.0, end: 11.0, conf: 0.95, main: 9.0, obs: 'С 0:08 по 0:11 (3,0 с) изображение с камеры перекрыто: кадр тёмный, без деталей; рабочая зона кассира не просматривается', review: ['confirmed', ''] },
        { id: 'V05', tc: 17.2, end: 21.0, conf: 0.63, main: 18.0, obs: 'В 0:17 кассир уносит наличные к задней стенке кабины и пересчитывает их вне видимости клиента', review: ['false_positive', 'Пересчёт был виден клиенту через стекло'] },
      ] },
    { file: 'касса1_вечер.mov', branch: 'Отделение №1', desk: 'Касса 1', days: 4, dur: 22, seen: true, ev: { clientIn: [2, 18] }, items: [] },
    { file: 'касса3_утро.mov', branch: 'Отделение №3', desk: 'Касса 1', days: 5, dur: 38, seen: true, ev: { overGlass: [14, 17], away: [26, 33], clientIn: [3, 35] },
      items: [
        { id: 'V12', tc: 14.5, end: 17.0, conf: 0.71, main: 15.0, obs: 'В 0:14 кассир передаёт пачку наличных клиенту поверх перегородки, минуя лоток' },
        { id: 'V03', tc: 26.0, end: 33.0, conf: 0.86, main: 27.0, obs: 'В 0:26 кассир выходит из кабины, клиент остаётся у окна', review: ['confirmed', ''] },
      ] },
  ];

  const isoDaysAgo = days => {
    const d = new Date(Date.now() - days * 86400000);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  };
  let seq = 0;
  const newId = () => `demo${(++seq).toString(16).padStart(3, '0')}${Math.random().toString(16).slice(2, 6)}`;

  function activityFor(ev, dur) {
    const marks = [];
    for (const k of Object.keys(ev)) marks.push(ev[k][0], ev[k][1]);
    return Array.from({ length: Math.ceil(dur) }, (_, s) => {
      const near = marks.length ? Math.min(...marks.map(m => Math.abs(m - s))) : 9;
      return Math.round(Math.max(0.06, 0.95 - near * 0.3) * 100) / 100;
    });
  }

  function makeItem(it, key, status, frameAt, dur) {
    const rule = env.ruleById(it.id);
    if (!rule) return null;
    const main = it.main != null ? it.main : it.tc;
    const times = [main, Math.max(0, it.tc - 1.6), Math.min(dur - 0.2, (it.end != null ? it.end : it.tc) + 0.8)]
      .filter((v, i, a) => a.findIndex(x => Math.abs(x - v) < 0.3) === i).slice(0, status === 'review' ? 1 : 3);
    return {
      key, rule, timecode: it.tc, t_end: it.end != null ? it.end : null, confidence: it.conf,
      observed: it.obs, description: env.describe(rule, it.obs), source: it.source || env.t('demo.sample'), status,
      review_reason: status === 'review' ? (it.reason || 'Низкая уверенность — нужен взгляд человека.') : null,
      frames: times.map((tt, i) => ({ timestamp_sec: Math.round(tt * 100) / 100, image_base64: frameAt(tt, it.id, i === 0 ? (BOXES[it.id] || []) : []) })),
    };
  }

  function recItems(s) {
    return [
      ...s.items.map((it, i) => ({ key: `v${i}`, rule_id: it.id, title: (env.ruleById(it.id) || {}).title || it.id, timecode: it.tc, confidence: it.conf, status: 'reported' })),
      ...(s.reviewItems || []).map((it, i) => ({ key: `r${i}`, rule_id: it.id, title: (env.ruleById(it.id) || {}).title || it.id, timecode: it.tc, confidence: it.conf, status: 'review' })),
    ];
  }

  function seed() {
    SAMPLES.forEach((s, n) => {
      const id = newId();
      const date = isoDaysAgo(s.days);
      const created = new Date(Date.now() - s.days * 86400000 - (n + 1) * 2700000).toISOString();
      const reviews = {};
      s.items.forEach((it, i) => { if (it.review) reviews[`v${i}`] = { decision: it.review[0], comment: it.review[1], at: created }; });
      const rec = {
        job_id: id, created_at: created, filename: s.file, origin: 'ui', branch: s.branch, desk: s.desk, shot_date: date, batch_id: '',
        status: 'done', verdict: s.items.length ? 'violation' : 'no_violation', error: null, duration_sec: s.dur,
        processing_sec: Math.round((6 + s.dur * 0.35) * 10) / 10, items: recItems(s), reviews, seen: s.seen, seen_at: null, clips_ready: true,
      };
      jobs.set(id, { rec, sample: s, ui: null, created: Date.parse(created), clips: null });
    });
  }

  function buildSampleUi(job) {
    const s = job.sample;
    const frameAt = (tt, ruleId, boxes) => stamp(scene(tt, s.ev), tt, ruleId, boxes, 4);
    const violations = s.items.map((it, i) => makeItem(it, `v${i}`, 'reported', frameAt, s.dur)).filter(Boolean);
    const review = (s.reviewItems || []).map((it, i) => makeItem(it, `r${i}`, 'review', frameAt, s.dur)).filter(Boolean);
    return {
      job_id: job.rec.job_id, status: 'done', stage: 'done', progress: 1, filename: s.file, error: null,
      result: {
        verdict: violations.length ? 'violation' : 'no_violation', violations, review,
        video: { duration_sec: s.dur, fps: 30, width: 1920, height: 1080 },
        activity: activityFor(s.ev, s.dur),
        thumbs: Array.from({ length: Math.ceil(s.dur) }, (_, sec) => toB64(scene(sec + 0.5, s.ev), 0.8)),
        timings: { total_sec: job.rec.processing_sec }, coverage_sec: s.dur, degraded: false, notes: [], detectors: [env.t('demo.sample')], threshold: 0.5,
      },
    };
  }

  function sampleClip(job, key) {
    const it = key[0] === 'v' ? job.sample.items[Number(key.slice(1))] : (job.sample.reviewItems || [])[Number(key.slice(1))];
    if (!it) return null;
    const a = Math.max(0, it.tc - 3), b = Math.min(job.sample.dur - 0.1, it.tc + 3);
    const frames = [];
    for (let tt = a; tt <= b + 1e-6; tt += 0.25) {
      const big = document.createElement('canvas');
      big.width = 480; big.height = 270;
      const g = big.getContext('2d');
      g.imageSmoothingEnabled = false;
      g.drawImage(scene(tt, job.sample.ev), 0, 0, 480, 270);
      frames.push({ t: Math.round(tt * 100) / 100, b64: toB64(big, 0.7) });
    }
    return { fps: 4, tc: it.tc, t0: a, t1: b, frames };
  }

  /* ── своё видео: кадры прямо из файла ─────────────── */
  async function grab(url, times, width) {
    const v = document.createElement('video');
    v.muted = true; v.preload = 'auto'; v.playsInline = true; v.src = url;
    const ok = await new Promise(res => { v.onloadeddata = () => res(true); v.onerror = () => res(false); setTimeout(() => res(false), 6000); });
    if (!ok || !v.videoWidth) return null;
    const out = new Map();
    for (const tt of times) {
      await new Promise(res => { v.onseeked = res; v.currentTime = Math.min(tt, Math.max(0, v.duration - 0.05)); setTimeout(res, 1500); });
      const c = document.createElement('canvas');
      c.width = width; c.height = Math.round(width * v.videoHeight / v.videoWidth);
      c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
      out.set(tt, c);
    }
    return { duration: v.duration, frames: out };
  }

  async function buildUploadUi(job, url) {
    const probe = await new Promise(res => {
      const v = document.createElement('video');
      v.preload = 'metadata'; v.muted = true;
      v.onloadedmetadata = () => res(isFinite(v.duration) ? v.duration : null);
      v.onerror = () => res(null);
      setTimeout(() => res(null), 5000);
      v.src = url;
    });
    const d = probe && probe > 1 ? probe : null;
    if (d) {
      const tc = Math.round(d * 0.35 * 10) / 10;
      const n = Math.min(90, Math.ceil(d));
      const thumbTimes = Array.from({ length: n }, (_, i) => Math.min(d - 0.1, (i + 0.5) * d / n));
      const clipTimes = [];
      for (let tt = Math.max(0, tc - 3); tt <= Math.min(d - 0.1, tc + 3) + 1e-6; tt += 0.25) clipTimes.push(Math.round(tt * 100) / 100);
      const before = Math.max(0, Math.round((tc - 1.5) * 100) / 100);
      const got = await grab(url, [tc, before, ...thumbTimes, ...clipTimes], 640);
      if (got) {
        const it = { id: 'V03', tc, end: Math.min(d, tc + 4), conf: 0.9, main: tc, obs: env.t('demo.observed', { t: env.fmtTc(tc) }), source: 'демо' };
        const item = makeItem(it, 'v0', 'reported', (tt, ruleId) => stamp(got.frames.get(tt === tc ? tc : before) || got.frames.get(tc), tt, ruleId, [], 1), d);
        item.frames = item.frames.slice(0, 2);
        const thumbs = Array.from({ length: Math.ceil(d) }, (_, s) => {
          const c = got.frames.get(thumbTimes[Math.min(n - 1, Math.floor(s * n / Math.ceil(d)))]);
          const small = document.createElement('canvas');
          small.width = 160; small.height = Math.round(160 * c.height / c.width);
          small.getContext('2d').drawImage(c, 0, 0, small.width, small.height);
          return toB64(small, 0.7);
        });
        job.clips = {
          v0: { fps: 4, tc, t0: clipTimes[0], t1: clipTimes[clipTimes.length - 1],
            frames: clipTimes.map(tt => { const c = got.frames.get(tt); const s = document.createElement('canvas'); s.width = 480; s.height = Math.round(480 * c.height / c.width); s.getContext('2d').drawImage(c, 0, 0, s.width, s.height); return { t: tt, b64: toB64(s, 0.7) }; }) },
        };
        job.rec.items = [{ key: 'v0', rule_id: 'V03', title: item.rule.title, timecode: tc, confidence: 0.9, status: 'reported' }];
        job.rec.duration_sec = Math.round(d * 10) / 10;
        return {
          job_id: job.rec.job_id, status: 'done', stage: 'done', progress: 1, filename: job.rec.filename, error: null,
          result: {
            verdict: 'violation', violations: [item], review: [], video: { duration_sec: d, fps: 30, width: got.frames.get(tc).width, height: got.frames.get(tc).height },
            activity: Array.from({ length: Math.ceil(d) }, (_, s) => Math.round((0.15 + 0.7 * Math.exp(-Math.abs(s - tc) / 2)) * 100) / 100),
            thumbs, timings: { total_sec: 4.6 }, coverage_sec: d, degraded: false, notes: [env.t('demo.note')], detectors: ['демо'], threshold: 0.5,
          },
        };
      }
    }
    // браузер не прочитал файл — показываем пример
    const s = SAMPLES[0];
    job.sample = s;
    job.rec.items = recItems(s);
    job.rec.duration_sec = s.dur;
    const ui = buildSampleUi(job);
    ui.filename = job.rec.filename;
    ui.result.notes = [env.t('demo.noframes')];
    return ui;
  }

  /* ── API ───────────────────────────────────────────── */
  seed();
  const publicRec = r => JSON.parse(JSON.stringify(r));

  function stateOf(job) {
    if (job.rec.status === 'done' || job.rec.status === 'failed') return { status: job.rec.status, stage: job.rec.status, progress: job.rec.status === 'done' ? 1 : 0 };
    const el = Date.now() - job.created;
    if (el < 700) return { status: 'queued', stage: 'queued', progress: 0, queue_position: 1 };
    const p = Math.min(0.95, (el - 700) / 3800);
    if (el >= 4500 && job.ui) {
      job.rec.status = 'done';
      job.rec.verdict = job.ui.result.verdict;
      job.rec.processing_sec = Math.round(el / 100) / 10;
      return { status: 'done', stage: 'done', progress: 1 };
    }
    return { status: 'processing', stage: p < 0.15 ? 'decode' : p < 0.8 ? 'detect' : 'evidence', progress: p };
  }

  const STAGE_LABEL = { queued: 'st.queued', decode: 'st.decode', detect: 'st.detect', evidence: 'st.evidence', done: 'st.done', failed: 'st.failed' };

  return {
    demo: true,
    async analyze(file, meta, onProgress) {
      for (let p = 0; p <= 1.0001; p += 0.2) { onProgress(Math.min(1, p)); await new Promise(r => setTimeout(r, 120)); }
      const id = newId();
      const url = URL.createObjectURL(file);
      const rec = {
        job_id: id, created_at: new Date().toISOString(), filename: file.name, origin: 'ui',
        branch: meta.branch || '', desk: meta.desk || '', shot_date: meta.shot_date || '', batch_id: meta.batch_id || '',
        status: 'queued', verdict: null, error: null, duration_sec: null, processing_sec: null,
        items: [], reviews: {}, seen: false, seen_at: null, clips_ready: false,
      };
      const job = { rec, sample: null, ui: null, created: Date.now(), clips: null };
      jobs.set(id, job);
      buildUploadUi(job, url).then(ui => { job.ui = ui; job.rec.clips_ready = true; }).catch(() => { job.rec.status = 'failed'; job.rec.error = 'demo'; });
      return id;
    },
    async statuses(ids) {
      return ids.map(id => {
        const job = jobs.get(id);
        if (!job) return { job_id: id, status: 'missing' };
        const st = stateOf(job);
        return {
          job_id: id, status: st.status, filename: job.rec.filename, verdict: job.rec.verdict, error: job.rec.error,
          n_violations: job.rec.items.filter(i => i.status === 'reported').length, stage: st.stage,
          stage_label: env.t(STAGE_LABEL[st.stage] || 'st.detect'), progress: st.progress, queue_position: st.queue_position || 0,
        };
      });
    },
    async job(id) {
      const job = jobs.get(id);
      if (!job) { const e = new Error('404'); e.status = 404; throw e; }
      const st = stateOf(job);
      if (st.status !== 'done') return { job_id: id, status: st.status, stage: st.stage, stage_label: env.t(STAGE_LABEL[st.stage]), progress: st.progress, filename: job.rec.filename, error: job.rec.error, result: null, meta: publicRec(job.rec) };
      if (!job.ui) job.ui = buildSampleUi(job);
      return Object.assign({}, job.ui, { meta: publicRec(job.rec) });
    },
    async apiJson(id) {
      const data = await this.job(id);
      if (!data.result) return { job_id: id, status: 'processing', verdict: null, violations: [] };
      return {
        job_id: id, status: 'done', verdict: data.result.verdict,
        violations: data.result.violations.map(v => ({
          type: v.rule.title, timecode_sec: v.timecode, description: v.description,
          evidence_frames: v.frames.map(f => ({ timestamp_sec: f.timestamp_sec, image_base64: f.image_base64 })),
        })),
      };
    },
    async history() {
      for (const job of jobs.values()) stateOf(job);
      return [...jobs.values()].map(j => publicRec(j.rec)).sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    },
    async seen(id) { const j = jobs.get(id); if (j) { j.rec.seen = true; j.rec.seen_at = new Date().toISOString(); } return { ok: true }; },
    async review(id, key, decision, comment) {
      const j = jobs.get(id);
      if (!j) throw new Error('404');
      if (!decision && !comment) delete j.rec.reviews[key];
      else j.rec.reviews[key] = { decision: decision || null, comment: comment || '', at: new Date().toISOString() };
      return { reviews: JSON.parse(JSON.stringify(j.rec.reviews)) };
    },
    async clip(id, key) {
      const j = jobs.get(id);
      if (!j) return null;
      if (j.clips && j.clips[key]) return j.clips[key];
      if (j.sample) return sampleClip(j, key);
      return null;
    },
    async status() {
      let queued = 0, processing = 0;
      for (const j of jobs.values()) { const st = stateOf(j); if (st.status === 'queued') queued++; else if (st.status === 'processing') processing++; }
      return { queued, processing, workers: 2, deadline_sec: 240, device: { device: 'demo', name: 'Demo', memory: null }, processing_sec: { avg: 14.2, p95: 21.0, max: 24.6, n: jobs.size } };
    },
  };
};
