// config 
const OUTPUT_URL = './data/comparison_output.json';
const META_URL = './data/meta.json';
const INFO_URL = './data/dash_info.json';
const RUN_API = 'http://127.0.0.1:8321/api/run';
const REFRESH_MS = 5000;

// utils
const bust = (url) => `${url}?t=${Date.now()}`;
const statusClass = (s) => (s === 1 ? 'ready' : s === 0 ? 'blocked' : 'unknown');

// last snapshot for filtering
let lastControllers = {};
let currentQuery = "";

// search / filter
function matchesQuery(name, data, q) {
  if (!q) return true;
  const norm = (s) => s.replace(/\.py$/i, '').toLowerCase();
  if (q.startsWith('@')) {
    const needle = norm(q.slice(1));
    return norm(name).includes(needle) ||
      (Array.isArray(data.missing) && data.missing.join(' ').toLowerCase().includes(needle));
  }
  return norm(name).includes(norm(q));
}

function applyFilter() {
  const grid = document.getElementById('grid');
  const cards = grid.querySelectorAll('.card[data-name]');
  cards.forEach((card) => {
    const name = card.dataset.name;
    const data = lastControllers[name];
    const show = matchesQuery(name, data, currentQuery);
    card.classList.toggle('is-hidden', !show);
  });
}

(function wireSearch() {
  const searchInput = document.getElementById('ctrl-search');
  if (!searchInput) return;
  searchInput.addEventListener('input', (e) => {
    currentQuery = e.target.value.trim();
    applyFilter();
  });
})();

// toast
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

  const ttl = opts.ttl ?? 3000;
  if (ttl > 0) setTimeout(remove, ttl);
}

// run API
async function requestRun(controllerName) {
  try {
    const res = await fetch(RUN_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: controllerName })
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(text || `HTTP ${res.status}`);
    }
    const data = await res.json().catch(() => ({}));
    if (data.ok) {
      showToast('success', `Started: ${controllerName}`);
    } else {
      showToast('error', `Failed: ${data.message || 'Unknown error'}`);
    }
  } catch (e) {
    showToast('error', `Failed to start: ${e.message || e}`);
  }
}

// UI builders
function buildCard(name, data) {
  const card = document.createElement('div');
  card.dataset.name = name;
  card.className = `card ${statusClass(data.status)}`;

  const missingText = (Array.isArray(data.missing) && data.missing.length)
    ? data.missing.map((m) => '• ' + m).join('\n')
    : '';
  if (missingText) {
    card.setAttribute('data-missing', missingText);
  }

  const title = document.createElement('div');
  title.className = 'name';
  title.textContent = name;
  card.appendChild(title);

  const btn = document.createElement('button');
  btn.textContent = 'Run';
  if (data.status === 1) {
    btn.className = 'btn btn-run';
    btn.onclick = async () => {
      if (btn.disabled) return;
      const oldText = btn.textContent;
      btn.textContent = 'Running…';
      btn.disabled = true;
      try {
        await requestRun(name);
      } finally {
        btn.textContent = oldText;
        btn.disabled = false;
      }
    };
  } else {
    btn.className = 'btn btn-disabled';
    btn.disabled = true;
  }
  card.appendChild(btn);
  return card;
}

function updateCard(card, data) {
  const newClass = statusClass(data.status);
  if (!card.classList.contains(newClass)) {
    card.className = `card ${newClass}`;
  }

  const missingText = (Array.isArray(data.missing) && data.missing.length)
    ? data.missing.map((m) => '• ' + m).join('\n')
    : '';
  if (missingText) {
    if (card.getAttribute('data-missing') !== missingText) {
      card.setAttribute('data-missing', missingText);
    }
  } else if (card.hasAttribute('data-missing')) {
    card.removeAttribute('data-missing');
  }

  const btn = card.querySelector('button');
  const isReady = data.status === 1;
  if (isReady && btn.disabled) {
    btn.className = 'btn btn-run';
    btn.disabled = false;
    const ctrlName = card.dataset.name;
    btn.onclick = () => requestRun(ctrlName);
  } else if (!isReady && !btn.disabled) {
    btn.className = 'btn btn-disabled';
    btn.disabled = true;
    btn.onclick = null;
  }
}

function updateGrid(controllers) {
  const grid = document.getElementById('grid');
  const existing = new Map();
  grid.querySelectorAll('.card[data-name]').forEach((card) => {
    existing.set(card.dataset.name, card);
  });

  for (const [name, data] of Object.entries(controllers)) {
    const card = existing.get(name);
    if (card) {
      updateCard(card, data);
      existing.delete(name);
    } else {
      grid.appendChild(buildCard(name, data));
    }
  }

  existing.forEach((card) => card.remove());
  lastControllers = controllers;
  applyFilter();
}

function updateTable(tbody, items, buildRowHtml, idKey) {
  const existingRows = new Map();
  tbody.querySelectorAll('tr[data-id]').forEach((row) => {
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

  existingRows.forEach((row, id) => {
    if (!newIds.has(id)) row.remove();
  });
}

function updateText(el, text) {
  if (el && el.textContent !== text) el.textContent = text;
}

// trim ".py" live
(function trimPyLive() {
  const trimPy = (s) => s.replace(/\.py$/i, '');
  function applyTrim(root = document) {
    root.querySelectorAll('.card .name').forEach((el) => {
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

// data fetch
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

    updateGrid(cmp.controllers);

    const sBody = document.querySelector('#sensor-table tbody');
    const imus = (meta.IMUs || []).map((id) => ({ id, type: 'IMU' }));
    const sensorRow = (item, id) =>
      `<tr data-id="${id}">
        <td>${item.id}</td>
        <td>${item.type}</td>
        <td><span class="pill">connected</span></td>
      </tr>`;
    updateTable(sBody, imus, sensorRow, 'id');

    const mBody = document.querySelector('#motor-table tbody');
    const motors = Array.isArray(meta.Motors)
      ? meta.Motors.map((m) => ({ id: m.id, type: m.type || '—' }))
      : [];
    const motorRow = (item, id) =>
      `<tr data-id="${id}">
        <td>${item.id}</td>
        <td>${item.type}</td>
      </tr>`;
    updateTable(mBody, motors, motorRow, 'id');

    updateText(document.getElementById('sum-ts'), info.LastUpdated || '—');
    updateText(document.getElementById('sum-host'), info.JetsonHost || '—');
    updateText(document.getElementById('sum-wifi'), info.WiFi || '—');
    updateText(document.getElementById('sum-xsens'), meta.Xsensors ? 'ON' : 'OFF');
  } catch (e) {
    console.error('Dashboard update failed:', e);
    showToast('error', 'Sync error — check connection', { ttl: 2500 });
  }
}

loadAll();
setInterval(loadAll, REFRESH_MS);