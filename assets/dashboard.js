// ---------- config ----------
const OUTPUT_URL = './data/comparison_output.json';
const META_URL = './data/meta.json';
const INFO_URL = './data/dash_info.json';
const RUN_API = 'http://127.0.0.1:8321/api/run';
const STOP_API = 'http://127.0.0.1:8321/api/stop';
const FLEX_API = 'http://127.0.0.1:8321/api/flexible-run';
const FLEX_LOCAL_PATH = './data/flexible_config.json';
const REFRESH_MS = 5000;
const MOCK_APIS = false; // set to true to mock API calls for testing

// ---------- state ----------
let lastControllers = {};
let currentQuery = '';
let runningName = null;
let IMU_IDS = [];
let MOTOR_TYPES = new Map();
let FLEX_MODAL_OPEN = false;

// ---------- helpers ----------
const bust = (url) => `${url}?t=${Date.now()}`;
const statusClass = (s) => (s === 1 ? 'ready' : s === 0 ? 'blocked' : 'unknown');
function updateText(el, text) { if (el && el.textContent !== text) el.textContent = text; }
async function fetchJSON(url) {
  const res = await fetch(bust(url), { cache: 'no-store' });
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.json();
}
function showToast(kind, text, opts = {}) {
  const root = document.getElementById('toast-root');
  if (!root) return;
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `
    <span class="dot" aria-hidden="true"></span>
    <div class="msg">${text}</div>
    <button class="x" aria-label="Dismiss">×</button>
  `;
  root.appendChild(el);
  const remove = () => { el.style.animation = 'toast-out .15s ease forwards'; setTimeout(() => el.remove(), 160); };
  el.querySelector('.x').onclick = remove;
  const ttl = opts.ttl ?? 6000;
  if (ttl > 0) setTimeout(remove, ttl);
}

// ---------- search/filter ----------
(function wireSearch() {
  const input = document.getElementById('ctrl-search');
  if (!input) return;
  input.addEventListener('input', (e) => {
    currentQuery = e.target.value.trim();
    applyFilter();
  });
})();
function matchesQuery(name, data, q) {
  if (!q) return true;
  const norm = (s) => s.replace(/\.py$/i, '').toLowerCase();
  if (q.startsWith('@')) {
    const needle = norm(q.slice(1));
    const miss = Array.isArray(data.missing) ? data.missing.join(' ').toLowerCase() : '';
    return norm(name).includes(needle) || miss.includes(needle);
  }
  return norm(name).includes(norm(q));
}
function applyFilter() {
  const grid = document.getElementById('grid');
  if (!grid) return;
  grid.querySelectorAll('.card[data-name]').forEach(card => {
    const name = card.dataset.name;
    const data = lastControllers[name];
    card.classList.toggle('is-hidden', !matchesQuery(name, data, currentQuery));
  });
}

// ---------- run/stop button visuals ----------
function setRunning(name) {
  runningName = name;
  document.querySelectorAll('.card[data-name]').forEach(card => {
    const btn = card.querySelector('button');
    if (!btn) return;
    const n = card.dataset.name;
    if (n === name) {
      btn.disabled = false; btn.textContent = 'Stop'; btn.className = 'btn btn-run'; btn.style.pointerEvents = '';
    } else {
      btn.disabled = true; btn.textContent = 'Running…'; btn.className = 'btn btn-disabled'; btn.style.pointerEvents = 'none';
    }
  });
}
function clearRunning() {
  runningName = null;
  document.querySelectorAll('.card[data-name] button').forEach(btn => {
    btn.disabled = false; btn.textContent = 'Run'; btn.className = 'btn btn-run'; btn.style.pointerEvents = '';
  });
}

// ---------- confirm modal ----------
async function confirmActionModal(controllerName, action = 'run') {
  return new Promise((resolve) => {
    const wrap = document.getElementById('confirm');
    const title = document.getElementById('confirm-title');
    const msg = document.getElementById('confirm-msg');
    const ok = document.getElementById('confirm-ok');
    const cancel = document.getElementById('confirm-cancel');
    const isRun = action === 'run';

    title.textContent = isRun ? 'Run Controller' : 'Stop Controller';
    msg.textContent = isRun ? `Run "${controllerName}" on the Jetson now?` : `Stop "${controllerName}" currently running on the Jetson?`;
    ok.textContent = isRun ? 'Run' : 'Stop';
    ok.className = isRun ? 'btn btn-primary' : 'btn btn-stop';
    wrap.hidden = false;

    const done = (val) => { wrap.hidden = true; ok.onclick = cancel.onclick = null; window.removeEventListener('keydown', onKey); resolve(val); };
    const onKey = (e) => { if (e.key === 'Escape') done(false); if (e.key === 'Enter') done(true); };
    ok.onclick = () => done(true);
    cancel.onclick = () => done(false);
    window.addEventListener('keydown', onKey);
  });
}

// ---------- flexible modal ----------
async function openFlexibleModal() {
  const wrap = document.getElementById('flex-modal');
  if (!wrap) { console.error('flex-modal not found'); return { ok: false }; }
  wrap.hidden = false; FLEX_MODAL_OPEN = true;

  const f_ok = document.getElementById('flex-ok');
  const f_cancel = document.getElementById('flex-cancel');
  const xsens = wrap.querySelector('#flex-xsensors');

  const leftId = wrap.querySelector('#flex-motor-left-id');
  const leftTy = wrap.querySelector('#flex-motor-left-type');
  const rightId = wrap.querySelector('#flex-motor-right-id');
  const rightTy = wrap.querySelector('#flex-motor-right-type');

  // 1) Convert the 5 IMU <input> to <select> the first time
  const imuGrid = wrap.querySelector('.flex-imu-grid');
  const imuMap = [
    { id: 'flex-imu-pelvis', key: 'pelvis' },
    { id: 'flex-imu-right-thigh', key: 'right.thigh' },
    { id: 'flex-imu-right-shank', key: 'right.shank' },
    { id: 'flex-imu-left-thigh', key: 'left.thigh' },
    { id: 'flex-imu-left-shank', key: 'left.shank' }
  ];

  if (imuGrid && !imuGrid.dataset.upgraded) {
    imuMap.forEach(({ id }) => {
      const input = imuGrid.querySelector(`#${id}`);
      if (!input) return;
      const sel = document.createElement('select');
      sel.id = input.id;
      sel.style.cssText = 'width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:8px;font-size:14px;';
      // keep label structure: replace only the input inside the label
      input.replaceWith(sel);
    });
    imuGrid.dataset.upgraded = 'true';
  }

  // After upgrade, get the 5 <select>s
  const imuSelects = imuMap.map(({ id }) => wrap.querySelector(`#${id}`));

  // 2) Populate IMU selects and keep values unique
  function populateImuSelects() {
    const chosen = new Set(imuSelects.map(s => s?.value).filter(Boolean));
    imuSelects.forEach(sel => {
      if (!sel) return;
      const keep = sel.value || null;
      sel.innerHTML = '';

      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = 'Select IMU';
      placeholder.disabled = true;
      if (!sel.value) placeholder.selected = true;
      sel.appendChild(placeholder);

      IMU_IDS.forEach(id => {
        if (!chosen.has(String(id)) || String(id) === String(keep)) {
          const opt = document.createElement('option');
          opt.value = String(id);
          opt.textContent = String(id);
          sel.appendChild(opt);
        }
      });
      if (keep && [...sel.options].some(o => o.value === String(keep))) sel.value = String(keep);
      else if (sel.options[0]) sel.value = sel.options[0].value;
    });
  }
  imuSelects.forEach(s => s && s.addEventListener('change', populateImuSelects));
  populateImuSelects();

  let showHints = false;            // only paint red when true
  const touched = new WeakSet();    // track user interaction per select

  function validateIMUs(paint = showHints) {
    const vals = imuSelects.map(s => s.value).filter(v => v !== '');
    const allChosen = vals.length === imuSelects.length;
    const unique = new Set(vals).size === vals.length;

    // clear any previous paint
    if (paint) imuSelects.forEach(s => s.classList.remove('is-invalid'));

    if (paint) {
      // mark empty only if the user touched it or we're in submit mode
      imuSelects.forEach(s => {
        if (s.value === '' && (showHints || touched.has(s))) s.classList.add('is-invalid');
      });
      // mark duplicates (both ends)
      if (vals.length) {
        const seen = new Map();
        imuSelects.forEach(s => {
          const v = s.value;
          if (!v) return;
          if (seen.has(v)) {
            s.classList.add('is-invalid');
            seen.get(v).classList.add('is-invalid');
          } else {
            seen.set(v, s);
          }
        });
      }
    }

    f_ok.disabled = !(allChosen && unique);
    return allChosen && unique;
  }

  // listeners: don’t paint red on first open; mark field as touched after focus/change
  imuSelects.forEach(s => {
    s.addEventListener('focus', () => touched.add(s));
    s.addEventListener('change', () => {
      touched.add(s);
      // keep options mutually exclusive and revalidate without painting
      populateImuSelects();
      validateIMUs(false);
    });
  });

  // initial neutral validation (no red)
  validateIMUs(false);

  // 3) Motors: dropdown IDs only; type is read-only below
  function syncType(sel, out) { out.textContent = MOTOR_TYPES.get(Number(sel.value)) || '—'; }
  function populateMotorSelect(selectEl, { excludeId = null, keepValue = null } = {}) {
    const prev = keepValue ?? selectEl.value ?? null;
    selectEl.innerHTML = '';
    const frag = document.createDocumentFragment();

    // default placeholder
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select Motor';
    placeholder.disabled = true;
    if (!prev) placeholder.selected = true;
    frag.appendChild(placeholder);

    // real options
    for (const [id] of MOTOR_TYPES.entries()) {
      if (excludeId != null && String(id) === String(excludeId) && String(id) !== String(prev)) continue;
      const opt = document.createElement('option');
      opt.value = String(id);
      opt.textContent = String(id);
      frag.appendChild(opt);
    }
    selectEl.appendChild(frag);
    const keep = [...selectEl.options].find(o => o.value === String(prev));
    selectEl.value = keep ? String(prev) : (selectEl.options[0]?.value ?? '');
  }
  function refreshMotorSelects() {
    populateMotorSelect(leftId, { excludeId: rightId.value, keepValue: leftId.value });
    populateMotorSelect(rightId, { excludeId: leftId.value, keepValue: rightId.value });
    syncType(leftId, leftTy);
    syncType(rightId, rightTy);
  }
  leftId.addEventListener('change', refreshMotorSelects);
  rightId.addEventListener('change', refreshMotorSelects);
  refreshMotorSelects();

  xsens.checked = true;
  
  // Reset IMUs 
  const btnResetIMU = wrap.querySelector('#flex-reset-imu');
  if (btnResetIMU) {
    btnResetIMU.onclick = (e) => {
      e.preventDefault();

      imuSelects.forEach(sel => {
        sel.innerHTML = '';

        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select IMU';
        placeholder.selected = true;
        placeholder.disabled = false;
        sel.appendChild(placeholder);

        IMU_IDS.forEach(id => {
          const opt = document.createElement('option');
          opt.value = String(id);
          opt.textContent = String(id);
          sel.appendChild(opt);
        });
      });

      validateIMUs(false);
    };
  }

  // Reset Motors
  const btnResetMotors = wrap.querySelector('#flex-reset-motors');
  if (btnResetMotors) {
    btnResetMotors.onclick = (e) => {
      e.preventDefault();

      [leftId, rightId].forEach(sel => {
        sel.innerHTML = '';

        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select Motor';
        placeholder.selected = true;
        placeholder.disabled = false;
        sel.appendChild(placeholder);

        for (const [id] of MOTOR_TYPES.entries()) {
          const opt = document.createElement('option');
          opt.value = String(id);
          opt.textContent = String(id);
          sel.appendChild(opt);
        }
      });

      leftTy.textContent = '—';
      rightTy.textContent = '—';
      validateIMUs(false);
    };
  }
  // 4) Promise for modal
  return new Promise((resolve) => {
    const close = () => { wrap.hidden = true; FLEX_MODAL_OPEN = false; };
    const clean = () => { if (f_ok) f_ok.onclick = null; if (f_cancel) f_cancel.onclick = null; };

    if (f_cancel) f_cancel.onclick = () => { clean(); close(); resolve({ ok: false }); };
    if (f_ok) f_ok.onclick = () => {
      if (!validateIMUs()) return;

      const imu = {};
      imuMap.forEach(({ id, key }) => {
        const sel = wrap.querySelector(`#${id}`);
        imu[key] = Number(sel.value);
      });

      const lId = Number(leftId.value);
      const rId = Number(rightId.value);
      if (!Number.isFinite(lId) || lId <= 0) return;
      if (!Number.isFinite(rId) || rId <= 0) return;
      if (lId === rId) return;

      const config = {
        IMUs: imu,
        Xsensors: !!xsens.checked,
        Motors: {
          'right.hip': { motor_id: rId, motor_type: MOTOR_TYPES.get(rId) || '', is_inverted: false },
          'left.hip': { motor_id: lId, motor_type: MOTOR_TYPES.get(lId) || '', is_inverted: true }
        }
      };
      clean(); close(); resolve({ ok: true, config });
    };
  });
}

// ---------- API calls ----------
async function requestRun(name) {
  if (MOCK_APIS) { await new Promise(r => setTimeout(r, 200)); showToast('success', `Started: ${name}`); return { ok: true }; }
  try {
    const res = await fetch(RUN_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    showToast('success', `Started: ${name}`); return { ok: true };
  } catch (e) { showToast('error', `Failed: ${e.message || e}`); return { ok: false, error: e }; }
}
async function requestFlexibleRun(scriptName, config) {
  if (MOCK_APIS) { await new Promise(r => setTimeout(r, 200)); showToast('success', `Config saved to ${FLEX_LOCAL_PATH}`); await new Promise(r => setTimeout(r, 200)); showToast('success', `Started: ${scriptName}`); return { ok: true }; }
  try {
    const res = await fetch(FLEX_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: scriptName, config: config}) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    showToast('success', `Started: ${scriptName}`); return { ok: true };
  } catch (e) { showToast('error', `Failed: ${e.message || e}`); return { ok: false, error: e }; }
}
async function requestStop(name) {
  if (MOCK_APIS) { await new Promise(r => setTimeout(r, 200)); showToast('success', `Stopped: ${name}`); return { ok: true }; }
  try {
    const res = await fetch(STOP_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    showToast('success', `Stopped: ${name}`); return { ok: true };
  } catch (e) { showToast('error', `Failed: ${e.message || e}`); return { ok: false, error: e }; }
}

// ---------- grid ----------
function buildCard(name, data) {
  const card = document.createElement('div');
  card.dataset.name = name;
  card.className = `card ${statusClass(data.status)}`;

  const missingText = (Array.isArray(data.missing) && data.missing.length) ? data.missing.map(m => '• ' + m).join('\n') : '';
  if (missingText) card.setAttribute('data-missing', missingText);

  const title = document.createElement('div');
  title.className = 'name';
  title.textContent = name;
  card.appendChild(title);

  const btn = document.createElement('button');
  card.appendChild(btn);

  updateCard(card, data);
  return card;
}
function updateCard(card, data) {
  const newClass = statusClass(data.status);
  if (!card.classList.contains(newClass)) card.className = `card ${newClass}`;

  const missingText = (Array.isArray(data.missing) && data.missing.length) ? data.missing.map(m => '• ' + m).join('\n') : '';
  if (missingText) {
    if (card.getAttribute('data-missing') !== missingText) card.setAttribute('data-missing', missingText);
  } else if (card.hasAttribute('data-missing')) {
    card.removeAttribute('data-missing');
  }

  const btn = card.querySelector('button');
  const ctrlName = card.dataset.name;
  const isReady = data.status === 1;

  if (runningName) {
    if (runningName === ctrlName) {
      btn.className = 'btn btn-run'; btn.disabled = false; btn.textContent = 'Stop'; btn.style.pointerEvents = '';
      btn.onclick = async () => {
        if (btn.disabled) return;
        if (!(await confirmActionModal(ctrlName, 'stop'))) return;
        btn.disabled = true; btn.textContent = 'Stopping…'; btn.style.pointerEvents = 'none';
        const r = await requestStop(ctrlName);
        if (r.ok) clearRunning();
      };
    } else {
      btn.className = 'btn btn-disabled'; btn.disabled = true; btn.textContent = 'Running…'; btn.style.pointerEvents = 'none'; btn.onclick = null;
    }
    return;
  }

  if (isReady) {
    btn.className = 'btn btn-run'; btn.disabled = false; btn.textContent = 'Run'; btn.style.pointerEvents = '';
    const isFlexible = /flex/i.test(ctrlName); // open flexible modal for any controller name containing "flex"
    if (isFlexible) {
      btn.onclick = async () => {
        const res = await openFlexibleModal();
        if (!res.ok) return;
        const proceed = await confirmActionModal(ctrlName, 'run');
        if (!proceed) return;

        btn.disabled = true; btn.textContent = 'Running…'; btn.style.pointerEvents = 'none';
        const r = await requestFlexibleRun(ctrlName, res.config);
        if (r.ok) {
          setRunning(ctrlName);
          const active = document.querySelector(`.card[data-name="${ctrlName}"] button`);
          if (active) {
            active.disabled = true; active.textContent = 'Starting…'; active.style.pointerEvents = 'none';
            setTimeout(() => {
              if (runningName === ctrlName) { active.disabled = false; active.textContent = 'Stop'; active.style.pointerEvents = ''; }
            }, 5000);
          }
        }
      };
    } else {
      btn.onclick = async () => {
        if (!(await confirmActionModal(ctrlName, 'run'))) return;
        btn.disabled = true; btn.textContent = 'Running…'; btn.style.pointerEvents = 'none';
        const r = await requestRun(ctrlName);
        if (r.ok) {
          setRunning(ctrlName);
          const active = document.querySelector(`.card[data-name="${ctrlName}"] button`);
          if (active) {
            active.disabled = true; active.textContent = 'Starting…'; active.style.pointerEvents = 'none';
            setTimeout(() => {
              if (runningName === ctrlName) { active.disabled = false; active.textContent = 'Stop'; active.style.pointerEvents = ''; }
            }, 5000);
          }
        }
      };
    }
  } else {
    btn.className = 'btn btn-disabled'; btn.disabled = true; btn.textContent = 'Run'; btn.style.pointerEvents = 'none'; btn.onclick = null;
  }
}

// ---------- table diff ----------
function updateTable(tbody, items, buildRowHtml, idKey) {
  const existingRows = new Map();
  tbody.querySelectorAll('tr[data-id]').forEach(row => existingRows.set(row.dataset.id, row));
  const newIds = new Set();
  for (const item of items) {
    const id = String(item[idKey]);
    newIds.add(id);
    if (!existingRows.has(id)) tbody.insertAdjacentHTML('beforeend', buildRowHtml(item, id));
  }
  existingRows.forEach((row, id) => { if (!newIds.has(id)) row.remove(); });
}

// ---------- trim ".py" live ----------
(function trimPyLive() {
  const trimPy = (s) => s.replace(/\.py$/i, '');
  function applyTrim(root = document) {
    root.querySelectorAll('.card .name').forEach(el => {
      const raw = el.textContent || '';
      const trimmed = trimPy(raw);
      if (trimmed !== raw) el.textContent = trimmed;
    });
  }
  applyTrim();
  const grid = document.getElementById('grid');
  if (!grid) return;
  const observer = new MutationObserver(() => applyTrim(grid));
  observer.observe(grid, { childList: true, subtree: true, characterData: true });
})();

// ---------- fetch + render ----------
async function loadAll() {
  try {
    const [cmp, meta, info] = await Promise.all([fetchJSON(OUTPUT_URL), fetchJSON(META_URL), fetchJSON(INFO_URL)]);

    // sensors -> IMU_IDS + table
    const sBody = document.querySelector('#sensor-table tbody');
    const imus = (meta.IMUs || []).map(id => ({ id, type: 'IMU' }));
    IMU_IDS = [...new Set((meta.IMUs || []).map(Number).filter(n => Number.isFinite(n) && n > 0))];
    const sensorRow = (item, id) => `<tr data-id="${id}"><td>${item.id}</td><td>${item.type}</td><td><span class="pill">connected</span></td></tr>`;
    if (sBody) updateTable(sBody, imus, sensorRow, 'id');

    // motors -> MOTOR_TYPES + table
    const mBody = document.querySelector('#motor-table tbody');
    const motors = Array.isArray(meta.Motors) ? meta.Motors.map(m => ({ id: m.id, type: m.type || '—' })) : [];
    MOTOR_TYPES.clear();
    for (const m of motors) if (m && typeof m.id !== 'undefined') MOTOR_TYPES.set(Number(m.id), String(m.type || ''));
    const motorRow = (item, id) => `<tr data-id="${id}"><td>${item.id}</td><td>${item.type}</td></tr>`;
    if (mBody) updateTable(mBody, motors, motorRow, 'id');

    // controllers grid
    const grid = document.getElementById('grid');
    const existing = new Map();
    grid.querySelectorAll('.card[data-name]').forEach(card => existing.set(card.dataset.name, card));
    for (const [name, data] of Object.entries(cmp.controllers)) {
      const card = existing.get(name);
      if (card) { updateCard(card, data); existing.delete(name); }
      else { grid.appendChild(buildCard(name, data)); }
    }
    existing.forEach(card => card.remove());
    lastControllers = cmp.controllers;
    applyFilter();

    // summary
    updateText(document.getElementById('sum-ts'), info.LastUpdated || '—');
    updateText(document.getElementById('sum-host'), info.JetsonHost || '—');
    updateText(document.getElementById('sum-wifi'), info.WiFi || '—');
    updateText(document.getElementById('sum-xsens'), meta.Xsensors ? 'ON' : 'OFF');

  } catch (e) {
    console.error('Dashboard update failed:', e);
    showToast('error', 'Sync error — check connection', { ttl: 2500 });
  }
}

// ---------- boot ----------
loadAll();
setInterval(loadAll, REFRESH_MS);