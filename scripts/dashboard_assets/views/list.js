'use strict';
// r37 뷰1 — 과업 리스트(기본 뷰). 데이터 매핑(번들 §뷰1 데이터 매핑):
//   트랙/목표 = task명 + excerpt(null이면 폴백 문구) · 우선순위 = tier 색 ·
//   현재 상태 = phase 배지(글리프) · 선택 판단 = claims 칩 · 최근 갱신 = mtime.
// 행→상세 진입(H1): 트랙/목표 셀 클릭 = navigate — 체크박스는 이벤트 분리.
// 컨트롤(검색·필터·정렬)은 1회 구축 후 값만 동기화 — 폴링 재렌더에 포커스 보존.

const EXCERPT_FALLBACK = '원 요구 발췌 없음 — 상세 참조';
const PHASES = ['plan', 'adversary', 'review', 'implement', 'verify', 'done',
  'blocked', 'cancelled'];
const TIERS = ['S', 'M', 'L', 'XL'];
// r36 승계 4키(task·tier·phase·spawns) + mtime(최근 갱신 열 대응 — ③ 재량).
const SORT_KEYS = [
  ['task', 'task'], ['tier', 'tier'], ['phase', 'phase'],
  ['spawns', 'spawns'], ['mtime', '최근 갱신'],
];

// phase → 배지(색·글리프) — 번들 §시각 매핑 확정표.
function phaseBadge(phase) {
  const value = phase === null || phase === undefined || phase === ''
    ? null : String(phase);
  if (value === 'done') {
    return { kind: 'badge-green', glyph: '✓', label: value };
  }
  if (value === 'implement' || value === 'verify') {
    return { kind: 'badge-blue', glyph: '●', label: value };
  }
  if (value === 'plan' || value === 'adversary' || value === 'review'
    || value === 'blocked') {
    return { kind: 'badge-cream', glyph: '◇', label: value };
  }
  const label = value === null ? 'null' : value;
  return { kind: 'badge-gray', glyph: '✕', label };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) { node.className = className; }
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  return node;
}

function priorityCell(tier) {
  const cell = el('td', 'cell-priority');
  const value = tier === null || tier === undefined ? null : String(tier);
  const tone = value === 'L' || value === 'XL' ? 'priority-high'
    : value === 'M' ? 'priority-mid' : 'priority-low';
  cell.appendChild(el('span', `priority ${tone}`, value === null ? '–' : value));
  return cell;
}

function stateCell(phase) {
  const cell = el('td', 'cell-state');
  const badge = phaseBadge(phase);
  const span = el('span', `badge ${badge.kind}`);
  span.appendChild(el('span', 'badge-glyph', badge.glyph));
  span.appendChild(document.createTextNode(badge.label));
  cell.appendChild(span);
  return cell;
}

function claimsCell(task) {
  const cell = el('td', 'cell-claims');
  const buckets = [
    ['verified', task.claims.verified],
    ['pending', task.claims.pending],
    ['gap', task.claims.gap],
  ];
  buckets.forEach(([name, count]) => {
    cell.appendChild(el('span',
      `claim-chip claim-${name}`, `${name} ${count}`));
  });
  if (task.claims.other > 0) {
    cell.appendChild(el('span', 'claim-chip', `other ${task.claims.other}`));
  }
  return cell;
}

function excerptText(task) {
  return task.excerpt === null || task.excerpt === undefined
    ? EXCERPT_FALLBACK : String(task.excerpt);
}

const SHORT_TIME = new Intl.DateTimeFormat('ko-KR', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h12',
});

function formatTime(mtime) {
  if (!mtime) { return '–'; }
  const parsed = new Date(mtime);
  return Number.isNaN(parsed.getTime()) ? '–' : SHORT_TIME.format(parsed);
}

function buildRow(task, selected, actions) {
  const row = el('tr', 'task-row');
  row.dataset.folder = task.folder;
  const checkCell = el('td', 'cell-check');
  const checkbox = el('input', 'row-check');
  checkbox.type = 'checkbox';
  checkbox.checked = selected.includes(task.folder);
  checkbox.setAttribute('aria-label', `${task.task} 선택`);
  checkbox.addEventListener('change', () => actions.toggleSelect(task.folder));
  checkCell.appendChild(checkbox);
  row.appendChild(checkCell);

  // 트랙/목표 셀 — 클릭 = 뷰3 진입(행 클릭이 유일한 정상 진입 경로, H1)
  const trackCell = el('td', 'cell-track');
  const title = el('p', 'track-title');
  title.appendChild(el('span', 'track-name', task.task));
  // 폴더명이 과업명과 같으면 중복 라벨이 되므로 다를 때만 ID 표기(원본 "제목 · ID" 패턴)
  if (task.folder !== task.task) {
    title.appendChild(el('span', 'track-id mono-id', task.folder));
  }
  trackCell.appendChild(title);
  trackCell.appendChild(el('p', 'track-sub', excerptText(task)));
  trackCell.addEventListener('click', () => actions.navigate(task.folder));
  row.appendChild(trackCell);

  row.appendChild(priorityCell(task.tier));
  row.appendChild(stateCell(task.phase));
  row.appendChild(claimsCell(task));
  row.appendChild(el('td', 'cell-mtime muted tnum', formatTime(task.mtime)));
  return row;
}

function buildShell(actions) {
  const head = el('div', 'view-head');
  const headLeft = el('div');
  headLeft.appendChild(el('h1', 'view-title', '과업 목록'));
  head.appendChild(headLeft);
  head.appendChild(el('p', 'view-aside', 'state.json 기준 · 읽기 전용'));

  const stats = el('div', 'stats-row');

  const controls = el('div', 'controls-row');
  const searchBox = el('div', 'search-box');
  searchBox.appendChild(el('span', 'search-icon', '⌕'));
  const search = el('input');
  search.type = 'search';
  search.placeholder = '과업 검색';
  search.setAttribute('aria-label', '과업 검색');
  search.addEventListener('input', (event) => {
    actions.setFilter({ query: event.target.value.trim() });
  });
  searchBox.appendChild(search);
  searchBox.appendChild(el('kbd', null, '/'));
  controls.appendChild(searchBox);

  // '/' 키다운 = 검색창 포커스(번들 L6 — 로컬 동작). 입력 필드에서의 '/'는
  // 검색어로 통과시킨다.
  document.addEventListener('keydown', (event) => {
    if (event.key !== '/' || event.defaultPrevented) { return; }
    const target = event.target;
    if (target instanceof HTMLElement
      && (target.tagName === 'INPUT' || target.tagName === 'SELECT'
        || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
      return;
    }
    event.preventDefault();
    search.focus();
  });

  const phaseSelect = el('select');
  phaseSelect.setAttribute('aria-label', 'phase 필터');
  const phaseAll = el('option', null, 'phase: 전체');
  phaseAll.value = '';
  phaseSelect.appendChild(phaseAll);
  PHASES.forEach((phase) => {
    const option = el('option', null, `phase: ${phase}`);
    option.value = phase;
    phaseSelect.appendChild(option);
  });
  phaseSelect.addEventListener('change', (event) => {
    actions.setFilter({ phase: event.target.value });
  });
  controls.appendChild(phaseSelect);

  const tierSelect = el('select');
  tierSelect.setAttribute('aria-label', 'tier 필터');
  const tierAll = el('option', null, 'tier: 전체');
  tierAll.value = '';
  tierSelect.appendChild(tierAll);
  TIERS.forEach((tier) => {
    const option = el('option', null, `tier: ${tier}`);
    option.value = tier;
    tierSelect.appendChild(option);
  });
  tierSelect.addEventListener('change', (event) => {
    actions.setFilter({ tier: event.target.value });
  });
  controls.appendChild(tierSelect);

  const sortSelect = el('select');
  sortSelect.setAttribute('aria-label', '정렬 기준');
  SORT_KEYS.forEach(([key, label]) => {
    const option = el('option', null, `정렬: ${label}`);
    option.value = key;
    sortSelect.appendChild(option);
  });
  sortSelect.addEventListener('change', (event) => {
    actions.setSort({ key: event.target.value });
  });
  controls.appendChild(sortSelect);

  const sortDir = el('button', 'sort-dir', '▲');
  sortDir.type = 'button';
  sortDir.title = '정렬 방향 전환';
  sortDir.addEventListener('click', () => actions.toggleSortDir());
  controls.appendChild(sortDir);

  const section = el('div', 'section-label');
  section.appendChild(el('strong', null, '활성 과업'));
  section.appendChild(el('span', 'section-total'));

  const table = el('table', 'task-table');
  const thead = el('thead');
  const headRow = el('tr');
  ['체크', '트랙 / 목표', '우선순위', '현재 상태', '선택 판단', '최근 갱신']
    .forEach((label) => {
      headRow.appendChild(el('th', null, label));
    });
  thead.appendChild(headRow);
  table.appendChild(thead);
  table.appendChild(el('tbody', 'task-rows'));

  const empty = el('p', 'empty-state', '표시할 과업이 없다');
  empty.hidden = true;

  const actionBar = el('div', 'action-bar');
  actionBar.hidden = true;
  const count = el('span', 'action-bar-count');
  const clear = el('button', 'action-clear', '선택 해제');
  clear.type = 'button';
  clear.addEventListener('click', () => actions.clearSelection());
  const copy = el('button', 'action-copy', '과업 ID 클립보드 복사');
  copy.type = 'button';
  copy.addEventListener('click', () => actions.copyIds(copy));
  actionBar.appendChild(count);
  actionBar.appendChild(clear);
  actionBar.appendChild(copy);

  return { head, stats, controls, section, table, empty, actionBar,
    search, phaseSelect, tierSelect, sortSelect, sortDir };
}

// 컨트롤 값 동기화 — 사용자 입력과 다를 때만 대입(포커스·조합 중 보존).
function syncControls(shell, vm) {
  if (shell.search.value !== vm.filters.query) {
    shell.search.value = vm.filters.query;
  }
  if (shell.phaseSelect.value !== vm.filters.phase) {
    shell.phaseSelect.value = vm.filters.phase;
  }
  if (shell.tierSelect.value !== vm.filters.tier) {
    shell.tierSelect.value = vm.filters.tier;
  }
  if (shell.sortSelect.value !== vm.sort.key) {
    shell.sortSelect.value = vm.sort.key;
  }
  shell.sortDir.textContent = vm.sort.dir === 'asc' ? '▲' : '▼';
}

export function renderList(container, vm, actions) {
  let shell = container.__listShell;
  if (!shell) {
    shell = buildShell(actions);
    container.replaceChildren(shell.head, shell.stats, shell.controls,
      shell.section, shell.table, shell.empty, shell.actionBar);
    container.__listShell = shell;
  }
  syncControls(shell, vm);

  shell.stats.replaceChildren(...vm.stats.map((stat) => {
    const item = el('div', 'stat');
    item.appendChild(el('span', 'stat-label', stat.label));
    item.appendChild(el('span', 'stat-value', String(stat.value)));
    return item;
  }));

  const rows = document.createDocumentFragment();
  vm.rows.forEach((task) => {
    rows.appendChild(buildRow(task, vm.selected, actions));
  });
  shell.table.querySelector('tbody').replaceChildren(rows);
  shell.empty.hidden = vm.rows.length > 0;
  shell.section.querySelector('.section-total').textContent = `전체 ${vm.total}`;

  shell.actionBar.hidden = vm.selected.length === 0;
  if (vm.selected.length > 0) {
    shell.actionBar.querySelector('.action-bar-count').textContent =
      `${vm.selected.length}개 과업 선택`;
  }
}
