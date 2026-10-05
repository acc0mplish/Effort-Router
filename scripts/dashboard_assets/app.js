'use strict';
// r36 대시보드 프론트엔드 — vanilla JS. 외부 의존·외부 fetch·localStorage 0
// (오프라인 동작 계약). 네트워크 호출은 동일 origin fetch('/api/tasks') 유일.
// 불변 패턴: 파생 데이터(필터·정렬 결과)는 전부 새 배열 — 원본 payload를
// 변형하지 않는다. 상태 컨테이너의 필드 교체만 허용한다.

const DEFAULT_REFRESH_MS = 5000;
const PHASES = ['plan', 'adversary', 'review', 'implement', 'verify', 'done',
  'blocked', 'cancelled'];
const TIERS = ['S', 'M', 'L', 'XL'];
const SORT_KEYS = ['task', 'tier', 'phase', 'spawns'];

// 애플리케이션 상태 — 필드 교체만 하고 중첩 객체는 새로 만들어 대입한다
const state = {
  tasks: [],
  filters: { phase: '', tier: '', query: '' },
  sort: { key: 'task', dir: 'asc' },
  expanded: [],
  intervalMs: DEFAULT_REFRESH_MS,
  timer: null,
};

// --- 순수 함수: 파생 데이터 -------------------------------------------------

function matchesFilters(task, filters) {
  const phaseOk = filters.phase === '' || task.phase === filters.phase;
  const tierOk = filters.tier === '' || task.tier === filters.tier;
  const queryOk = filters.query === ''
    || String(task.task || '').includes(filters.query);
  return phaseOk && tierOk && queryOk;
}

function filterTasks(tasks, filters) {
  return tasks.filter((task) => matchesFilters(task, filters));
}

function compareTasks(a, b, key) {
  const va = a[key];
  const vb = b[key];
  if (va === vb) { return 0; }
  if (va === null || va === undefined) { return 1; }
  if (vb === null || vb === undefined) { return -1; }
  if (typeof va === 'number' && typeof vb === 'number') { return va - vb; }
  return String(va).localeCompare(String(vb), 'ko');
}

function sortTasks(tasks, sort) {
  const sign = sort.dir === 'desc' ? -1 : 1;
  return tasks.slice().sort((a, b) => sign * compareTasks(a, b, sort.key));
}

function visibleTasks() {
  return sortTasks(filterTasks(state.tasks, state.filters), state.sort);
}

function countByPhase(tasks) {
  const counts = {};
  PHASES.forEach((phase) => { counts[phase] = 0; });
  tasks.forEach((task) => {
    const phase = task.phase;
    if (Object.prototype.hasOwnProperty.call(counts, phase)) {
      counts[phase] += 1;
    } else {
      counts.other = (counts.other || 0) + 1;
    }
  });
  return counts;
}

function toggleExpanded(expanded, taskName) {
  if (expanded.includes(taskName)) {
    return expanded.filter((name) => name !== taskName);
  }
  return expanded.concat([taskName]);
}

// --- 렌더 ------------------------------------------------------------------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) { node.className = className; }
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  return node;
}

function badge(value, kind) {
  const safe = value === null || value === undefined || value === ''
    ? 'none' : String(value);
  return el('span', `badge badge-${kind}-${CSS.escape(safe) || 'none'}`, safe);
}

function renderSummary(tasks) {
  const host = document.getElementById('summary-chips');
  const counts = countByPhase(tasks);
  const total = el('span', 'chip chip-total');
  total.appendChild(el('strong', null, String(tasks.length)));
  total.appendChild(document.createTextNode(' 과업'));
  const chips = [total];
  PHASES.forEach((phase) => {
    const chip = el('span', `chip chip-${phase}`);
    chip.appendChild(el('span', `chip-phase phase-${phase}`, phase));
    chip.appendChild(el('span', 'chip-count', String(counts[phase])));
    chips.push(chip);
  });
  host.replaceChildren(...chips);
}

function claimSummaryCell(task) {
  const cell = el('td', 'claims-cell');
  const buckets = [
    ['verified', task.claims.verified],
    ['pending', task.claims.pending],
    ['gap', task.claims.gap],
    ['other', task.claims.other],
  ];
  buckets.forEach(([name, count]) => {
    cell.appendChild(el('span', `claim-count claim-${name}`,
      `${name} ${count}`));
  });
  cell.appendChild(el('span', 'muted', `/${task.claims_total}`));
  return cell;
}

function detailRow(task, colCount) {
  const row = el('tr', 'detail-row');
  const cell = el('td', null, null);
  cell.colSpan = colCount;
  const box = el('div', 'detail-box');
  if (Array.isArray(task.claim_details) && task.claim_details.length > 0) {
    const list = el('ul', 'claim-list');
    task.claim_details.forEach((detail) => {
      const item = el('li', 'claim-item');
      item.appendChild(el('span', 'claim-text', detail.claim));
      item.appendChild(badge(detail.status, 'claim'));
      item.appendChild(el('span', 'claim-evidence', detail.evidence || ''));
      list.appendChild(item);
    });
    box.appendChild(list);
  } else {
    box.appendChild(el('p', 'muted', 'claims 상세가 없다.'));
  }
  const bundleLine = el('p', 'bundle-path');
  bundleLine.appendChild(el('span', 'muted', 'bundle: '));
  bundleLine.appendChild(el('code', null,
    task.bundle ? String(task.bundle) : '(없음)'));
  if (task.parse_error) {
    const errLine = el('p', 'parse-error');
    errLine.textContent = `parse_error: ${task.parse_error}`;
    box.appendChild(errLine);
  }
  box.appendChild(bundleLine);
  cell.appendChild(box);
  row.appendChild(cell);
  return row;
}

function taskRow(task, colCount) {
  // 행 식별 키 = folder(④리뷰 LOW) — task 값은 state.json 기재값이라 폴더 간
  // 중복 가능. folder는 폴더별 유일이라 동명 task 엣지에서도 확장이 정확하다.
  const isOpen = state.expanded.includes(task.folder);
  const row = el('tr', `task-row phase-${task.phase || 'none'}`);
  row.dataset.folder = task.folder;
  row.tabIndex = 0;
  row.setAttribute('role', 'button');
  row.setAttribute('aria-expanded', String(isOpen));
  row.appendChild(el('td', 'cell-task', task.task));
  row.appendChild(el('td')).appendChild(badge(task.tier, 'tier'));
  row.appendChild(el('td')).appendChild(badge(task.phase, 'phase'));
  row.appendChild(el('td', 'cell-round',
    `${task.round.adversary}/${task.round.review}`));
  row.appendChild(el('td', 'cell-num', task.spawns));
  row.appendChild(claimSummaryCell(task));
  row.appendChild(el('td', 'cell-next', task.next === null ? '–' : task.next));
  const bundleCell = el('td', 'cell-bundle');
  bundleCell.appendChild(el('span',
    task.bundle_exists ? 'bundle-ok' : 'bundle-missing',
    task.bundle_exists ? '있음' : '없음'));
  row.appendChild(bundleCell);
  if (isOpen) {
    const fragment = document.createDocumentFragment();
    fragment.appendChild(row);
    fragment.appendChild(detailRow(task, colCount));
    return fragment;
  }
  return row;
}

function renderRows(tasks) {
  const body = document.getElementById('task-rows');
  const colCount = document.getElementById('task-table')
    .querySelector('thead tr').children.length;
  const fragment = document.createDocumentFragment();
  tasks.forEach((task) => { fragment.appendChild(taskRow(task, colCount)); });
  body.replaceChildren(fragment);
  document.getElementById('empty-message').hidden = tasks.length > 0;
}

function renderSortMarkers() {
  document.querySelectorAll('button.sort').forEach((button) => {
    const active = button.dataset.key === state.sort.key;
    button.classList.toggle('sort-active', active);
    button.textContent = active
      ? `${button.dataset.key}${state.sort.dir === 'asc' ? ' ▲' : ' ▼'}`
      : button.dataset.key;
  });
}

function render() {
  const tasks = visibleTasks();
  renderSummary(state.tasks);
  renderRows(tasks);
  renderSortMarkers();
  document.getElementById('last-updated').textContent =
    `마지막 갱신 ${new Date().toLocaleTimeString('ko-KR')}`;
}

// --- 데이터·갱신 ------------------------------------------------------------

async function fetchTasks() {
  try {
    const response = await fetch('/api/tasks');
    if (!response.ok) { throw new Error(`api 상태 ${response.status}`); }
    const payload = await response.json();
    state.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
    render();
  } catch (error) {
    document.getElementById('last-updated').textContent =
      `갱신 실패 (${error.message})`;
  }
}

function stopTimer() {
  if (state.timer !== null) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

function applyInterval(ms) {
  stopTimer();
  state.intervalMs = ms;
  if (ms > 0) {
    state.timer = setInterval(fetchTasks, ms);
  }
}

// --- 배선 ------------------------------------------------------------------

function fillSelect(select, values) {
  const options = values.map((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    return option;
  });
  select.replaceChildren(select.options[0], ...options);
}

function setupControls() {
  fillSelect(document.getElementById('filter-phase'), PHASES);
  fillSelect(document.getElementById('filter-tier'), TIERS);

  document.getElementById('filter-phase').addEventListener('change', (event) => {
    state.filters = { ...state.filters, phase: event.target.value };
    render();
  });
  document.getElementById('filter-tier').addEventListener('change', (event) => {
    state.filters = { ...state.filters, tier: event.target.value };
    render();
  });
  document.getElementById('filter-task').addEventListener('input', (event) => {
    state.filters = { ...state.filters, query: event.target.value.trim() };
    render();
  });

  document.querySelectorAll('button.sort').forEach((button) => {
    button.addEventListener('click', () => {
      const key = button.dataset.key;
      const dir = state.sort.key === key && state.sort.dir === 'asc'
        ? 'desc' : 'asc';
      state.sort = { key, dir };
      render();
    });
  });

  const rows = document.getElementById('task-rows');
  rows.addEventListener('click', (event) => {
    const target = event.target.closest('tr.task-row');
    if (!target) { return; }
    state.expanded = toggleExpanded(state.expanded, target.dataset.folder);
    render();
  });
  rows.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') { return; }
    const target = event.target.closest('tr.task-row');
    if (!target) { return; }
    event.preventDefault();
    state.expanded = toggleExpanded(state.expanded, target.dataset.folder);
    render();
  });

  document.getElementById('refresh-now').addEventListener('click', fetchTasks);
  document.getElementById('refresh-interval').addEventListener('change', (event) => {
    applyInterval(Number(event.target.value));
  });
}

function init() {
  setupControls();
  document.getElementById('refresh-interval').value = String(DEFAULT_REFRESH_MS);
  applyInterval(DEFAULT_REFRESH_MS);
  fetchTasks();
}

document.addEventListener('DOMContentLoaded', init);
