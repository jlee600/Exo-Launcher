// ---------- config ----------
const OUTPUT_URL = './data/comparison_output.json';
const META_URL   = './data/meta.json';
const INFO_URL   = './data/dash_info.json';
const RUN_API    = 'http://127.0.0.1:8321/api/run';
const STOP_API   = 'http://127.0.0.1:8321/api/stop';
const REFRESH_MS = 5000;

// toggle this to simulate APIs when offline
const MOCK_APIS = true;

// ---------- helpers ----------
const bust = (url) => `${url}?t=${Date.now()}`;
const statusClass = (s) => (s === 1 ? 'ready' : s === 0 ? 'blocked' : 'unknown');

// ---------- search/filter state ----------
let lastControllers = {};
let currentQuery = "";

// ---------- search / filter wiring ----------
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
  grid.querySelectorAll('.card[data-name]').forEach(card => {
    const name = card.dataset.name;
    const data = lastControllers[name];
    const show = matchesQuery(name, data, currentQuery);
    card.classList.toggle('is-hidden', !show);
  });
}

// ---------- toast ----------
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

  const remove = () => {
    el.style.animation = 'toast-out .15s ease forwards';
    setTimeout(() => el.remove(), 160);
  };
  el.querySelector('.x').onclick = remove;

  const ttl = opts.ttl ?? 6000;
  if (ttl > 0) setTimeout(remove, ttl);
}

// ---------- run/stop global state ----------
let runningName = null;

function setRunning(name) {
  runningName = name;
  document.querySelectorAll('.card[data-name]').forEach(card => {
    const btn = card.querySelector('button');
    if (!btn) return;
    const n = card.dataset.name;

    if (n === name) {
      btn.disabled = false;
      btn.textContent = 'Stop';
      btn.className = 'btn btn-run';
      btn.style.pointerEvents = '';
    } else {
      btn.disabled = true;
      btn.textContent = 'Running…';
      btn.className = 'btn btn-disabled';
      btn.style.pointerEvents = 'none';
    }
  });
}

function clearRunning() {
  runningName = null;
  document.querySelectorAll('.card[data-name] button').forEach(btn => {
    btn.disabled = false;
    btn.textContent = 'Run';
    btn.className = 'btn btn-run';
    btn.style.pointerEvents = '';
  });
}

// ---------- confirmation modal ----------
async function confirmActionModal(controllerName, action = 'run') {
  return new Promise((resolve) => {
    const wrap = document.getElementById('confirm');
    const title = document.getElementById('confirm-title');
    const msg = document.getElementById('confirm-msg');
    const ok = document.getElementById('confirm-ok');
    const cancel = document.getElementById('confirm-cancel');

    const isRun = action === 'run';
    title.textContent = isRun ? 'Run Controller' : 'Stop Controller';
    msg.textContent = isRun
      ? `Run "${controllerName}" on the Jetson now?`
      : `Stop "${controllerName}" currently running on the Jetson?`;

    ok.textContent = isRun ? 'Run'  : 'Stop';
    ok.className = isRun ? 'btn btn-primary' : 'btn btn-stop';

    wrap.hidden = false;

    const done = (val) => {
      wrap.hidden = true;
      ok.onclick = cancel.onclick = null;
      window.removeEventListener('keydown', onKey);
      resolve(val);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') done(false);
      if (e.key === 'Enter')  done(true);
    };

    ok.onclick = () => done(true);
    cancel.onclick = () => done(false);
    window.addEventListener('keydown', onKey);
  });
}

// ---------- API calls ----------
async function requestRun(name) {
  if (MOCK_APIS) {
    await new Promise(requestAnimationFrame);
    await new Promise(r => setTimeout(r, 250));
    showToast('success', `Started: ${name}`);
    return { ok: true };
  }

  try {
    const res = await fetch(RUN_API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    showToast('success', `Started: ${name}`);
    return { ok: true };
  } catch (e) {
    showToast('error', `Failed: ${e.message || e}`);
    return { ok: false, error: e };
  }
}

async function requestStop(name) {
  if (MOCK_APIS) {
    await new Promise(r => setTimeout(r, 250));
    showToast('success', `Stopped: ${name}`);
    return { ok: true };
  }

  try {
    const res = await fetch(STOP_API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.message || `HTTP ${res.status}`);
    showToast('success', `Stopped: ${name}`);
    return { ok: true };
  } catch (e) {
    showToast('error', `Failed: ${e.message || e}`);
    return { ok: false, error: e };
  }
}

// ---------- UI: cards ----------
function buildCard(name, data) {
  const card = document.createElement('div');
  card.dataset.name = name;
  card.className = `card ${statusClass(data.status)}`;

  const missingText = (Array.isArray(data.missing) && data.missing.length)
    ? data.missing.map(m => '• ' + m).join('\n') : '';
  if (missingText) card.setAttribute('data-missing', missingText);

  const title = document.createElement('div');
  title.className = 'name';
  title.textContent = name;
  card.appendChild(title);

  const btn = document.createElement('button');
  card.appendChild(btn);

  // initial wire via updateCard to keep logic in one place
  updateCard(card, data);
  return card;
}

function updateCard(card, data) {
  const newClass = statusClass(data.status);
  if (!card.classList.contains(newClass)) card.className = `card ${newClass}`;

  const missingText = (Array.isArray(data.missing) && data.missing.length)
    ? data.missing.map(m => '• ' + m).join('\n') : '';
  if (missingText) {
    if (card.getAttribute('data-missing') !== missingText) card.setAttribute('data-missing', missingText);
  } else if (card.hasAttribute('data-missing')) {
    card.removeAttribute('data-missing');
  }

  const btn = card.querySelector('button');
  const ctrlName = card.dataset.name;
  const isReady = data.status === 1;

  // running lock
  if (runningName) {
    if (runningName === ctrlName) {
      btn.className = 'btn btn-run';
      btn.disabled = false;
      btn.textContent = 'Stop';
      btn.style.pointerEvents = '';
      btn.onclick = async () => {
        if (btn.disabled) return;
        if (!(await confirmActionModal(ctrlName, 'stop'))) return;

        btn.disabled = true;
        btn.textContent = 'Stopping…';
        btn.style.pointerEvents = 'none';
        const r = await requestStop(ctrlName);
        if (r.ok) clearRunning();
      };
    } else {
      btn.className = 'btn btn-disabled';
      btn.disabled = true;
      btn.textContent = 'Running…';
      btn.style.pointerEvents = 'none';
      btn.onclick = null;
    }
    return;
  }

  // idle state
  if (isReady) {
    btn.className = 'btn btn-run';
    btn.disabled = false;
    btn.textContent = 'Run';
    btn.style.pointerEvents = '';
    btn.onclick = async () => {
      if (btn.disabled) return;
      if (!(await confirmActionModal(ctrlName, 'run'))) return;

      btn.disabled = true;
      btn.textContent = 'Running…';
      btn.style.pointerEvents = 'none';

      const r = await requestRun(ctrlName);
      if (r.ok) {
        setRunning(ctrlName);

        // disable Stop for 3 seconds after start
        const active = document.querySelector(`.card[data-name="${ctrlName}"] button`);
        if (active) {
          active.disabled = true;
          active.textContent = 'Starting…';
          active.style.pointerEvents = 'none';
          setTimeout(() => {
            if (runningName === ctrlName) {
              active.disabled = false;
              active.textContent = 'Stop';
              active.style.pointerEvents = '';
            }
          }, 3000); 
        }
      }
    };
  } else {
    btn.className = 'btn btn-disabled';
    btn.disabled = true;
    btn.textContent = 'Run';
    btn.style.pointerEvents = 'none';
    btn.onclick = null;
  }
}

// ---------- UI: tables ----------
function updateTable(tbody, items, buildRowHtml, idKey) {
  const existingRows = new Map();
  tbody.querySelectorAll('tr[data-id]').forEach(row => {
    existingRows.set(row.dataset.id, row);
  });

  const newIds = new Set();
  for (const item of items) {
    const id = String(item[idKey]);
    newIds.add(id);
    if (!existingRows.has(id)) {
      const html = buildRowHtml(item, id);
      tbody.insertAdjacentHTML('beforeend', html);
    }
  }

  existingRows.forEach((row, id) => { if (!newIds.has(id)) row.remove(); });
}

function updateText(el, text) {
  if (el && el.textContent !== text) el.textContent = text;
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

// ---------- data fetch ----------
async function fetchJSON(url) {
  const res = await fetch(bust(url), { cache: 'no-store' });
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.json();
}

async function loadAll() {
  try {
    const [cmp, meta, info] = await Promise.all([
      fetchJSON(OUTPUT_URL),
      fetchJSON(META_URL),
      fetchJSON(INFO_URL)
    ]);

    // controllers grid
    const grid = document.getElementById('grid');
    const existing = new Map();
    grid.querySelectorAll('.card[data-name]').forEach(card => {
      existing.set(card.dataset.name, card);
    });

    for (const [name, data] of Object.entries(cmp.controllers)) {
      const card = existing.get(name);
      if (card) {
        updateCard(card, data);
        existing.delete(name);
      } else {
        grid.appendChild(buildCard(name, data));
      }
    }
    existing.forEach(card => card.remove());
    lastControllers = cmp.controllers;
    applyFilter();

    // sensors
    const sBody = document.querySelector('#sensor-table tbody');
    const imus = (meta.IMUs || []).map(id => ({ id, type: 'IMU' }));
    const sensorRow = (item, id) =>
      `<tr data-id="${id}">
         <td>${item.id}</td>
         <td>${item.type}</td>
         <td><span class="pill">connected</span></td>
       </tr>`;
    updateTable(sBody, imus, sensorRow, 'id');

    // motors
    const mBody = document.querySelector('#motor-table tbody');
    const motors = Array.isArray(meta.Motors) ? meta.Motors.map(m => ({
      id: m.id, type: m.type || '—'
    })) : [];
    const motorRow = (item, id) =>
      `<tr data-id="${id}">
         <td>${item.id}</td>
         <td>${item.type}</td>
       </tr>`;
    updateTable(mBody, motors, motorRow, 'id');

    // summary
    updateText(document.getElementById('sum-ts'),   info.LastUpdated || '—');
    updateText(document.getElementById('sum-host'), info.JetsonHost  || '—');
    updateText(document.getElementById('sum-wifi'), info.WiFi        || '—');
    updateText(document.getElementById('sum-xsens'), meta.Xsensors ? 'ON' : 'OFF');

  } catch (e) {
    console.error('Dashboard update failed:', e);
    showToast('error', 'Sync error — check connection', { ttl: 2500 });
  }
}

// ---------- boot ----------
loadAll();
setInterval(loadAll, REFRESH_MS);