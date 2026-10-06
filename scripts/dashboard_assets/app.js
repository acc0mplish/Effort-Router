'use strict';
// r37 대시보드 앱 코어 — 부트·해시 라우터·상태·fetch·폴링·셸 바인딩.
// 네트워크 호출은 동일 origin fetch('/api/tasks')·fetch('/api/bundle/') 유일
// (외부 의존·외부 fetch·localStorage 0). 뷰 모듈은 순수 렌더 — 상태·이벤트·
// fetch는 이 파일 단일 소유. 불변 패턴: 파생 데이터는 새 배열, 필드 교체만 허용.
//
// 부팅 순서 계약(M2·L3): 초기 fetch('/api/tasks') 종료(성공 기준) 후 최초 라우팅
// 확정 — 그 전 hashchange는 pending으로 두고 확정 시점에 재평가한다(빈 tasks로
// 폴더 검증해 전부 치환하는 경합 방지). 초기 fetch 실패 시 오류 표시 후 재시도
// (성공까지 라우팅 보류 — 빈 화면 정지 아님).
// 폴링(기본 5초)은 라우트 무관 지속 — 단 상세(뷰3)는 폴링이 문서 DOM을
// 재구성하지 않는다(문서는 진입 시 1회 /api/bundle 페치 — 스크롤·아코디언 보존).

import { renderList } from '/views/list.js';
import { renderActivity } from '/views/activity.js';
import { renderDetail } from '/views/detail.js';

const DEFAULT_REFRESH_MS = 5000;
const BOOT_RETRY_MS = 5000;
const PHASES = ['plan', 'adversary', 'review', 'implement', 'verify', 'done',
  'blocked', 'cancelled'];
const TIERS = ['S', 'M', 'L', 'XL'];
const ACTIVE_PHASES = ['implement', 'review', 'verify'];
// 통계 행 — 전체 · 진행 중(implement/review/verify) · 판단 대기(plan/adversary/
// blocked) · 완료(done). 나머지 phase는 통계에서 제외(목록에는 표시).
const ACTIVE_SET = new Set(ACTIVE_PHASES);
const DECISION_SET = new Set(['plan', 'adversary', 'blocked']);

// 애플리케이션 상태 — 필드 교체만, 중첩 갱신은 새 객체 대입.
const state = {
  tasks: [],
  filters: { phase: '', tier: '', query: '' },
  sort: { key: 'task', dir: 'asc' },
  selected: [],
  expandedDecisions: [],
  docOpen: true,
  intervalMs: DEFAULT_REFRESH_MS,
  timer: null,
  connected: false,
  lastSuccessAt: null,
  route: { view: 'list', folder: null },
  bundleDoc: null,
};

let booted = false;

// --- 순수 함수: 파생 데이터(전부 새 배열) -----------------------------------

function matchesFilters(task, filters) {
  const phaseOk = filters.phase === '' || task.phase === filters.phase;
  const tierOk = filters.tier === '' || task.tier === filters.tier;
  const queryOk = filters.query === ''
    || String(task.task || '').includes(filters.query)
    || String(task.folder || '').includes(filters.query)
    || String(task.excerpt || '').includes(filters.query);
  return phaseOk && tierOk && queryOk;
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

function visibleTasks() {
  const filtered = state.tasks.filter((task) => matchesFilters(task, state.filters));
  const sign = state.sort.dir === 'desc' ? -1 : 1;
  return filtered.slice().sort((a, b) => sign * compareTasks(a, b, state.sort.key));
}

function computeStats() {
  const total = state.tasks.length;
  let active = 0;
  let decision = 0;
  let done = 0;
  state.tasks.forEach((task) => {
    if (ACTIVE_SET.has(task.phase)) { active += 1; }
    if (DECISION_SET.has(task.phase)) { decision += 1; }
    if (task.phase === 'done') { done += 1; }
  });
  return [
    { label: '전체', value: total },
    { label: '진행 중', value: active },
    { label: '판단 대기', value: decision },
    { label: '완료', value: done },
  ];
}

// --- 해시 라우터 -------------------------------------------------------------

function parseHash() {
  const hash = window.location.hash;
  if (hash.startsWith('#/task/')) {
    try {
      return { view: 'detail', folder: decodeURIComponent(hash.slice(7)) };
    } catch {
      return { view: 'list', folder: null };
    }
  }
  if (hash === '#/activity') {
    return { view: 'activity', folder: null };
  }
  return { view: 'list', folder: null };
}

// 뷰1·뷰2 행 클릭 진입 액션 — 뷰3의 유일한 정상 진입 경로(직접 URL 제외).
function navigate(folder) {
  window.location.hash = '#/task/' + encodeURIComponent(folder);
}

function applyRoute() {
  let route = parseHash();
  if (route.view === 'detail'
    && !state.tasks.some((task) => task.folder === route.folder)) {
    window.location.hash = '#/list';
    return; // hashchange가 재평가한다
  }
  state.route = route;
  if (route.view === 'detail') {
    loadBundle(route.folder);
    return; // loadBundle → renderDetailView
  }
  renderPoll();
}

// --- 렌더 -------------------------------------------------------------------

function renderShell() {
  document.getElementById('nav-count-list').textContent = String(state.tasks.length);
  const activeCount = state.tasks.filter((task) => ACTIVE_SET.has(task.phase)).length;
  document.getElementById('nav-count-activity').textContent = String(activeCount);

  const route = state.route;
  const navList = document.getElementById('nav-list');
  const navActivity = document.getElementById('nav-activity');
  navList.classList.toggle('active', route.view === 'list');
  navActivity.classList.toggle('active', route.view === 'activity');

  const crumb = document.getElementById('breadcrumb-current');
  if (route.view === 'detail') {
    crumb.textContent = '과업 상세';
  } else if (route.view === 'activity') {
    crumb.textContent = '실행 현황';
  } else {
    crumb.textContent = '과업 목록';
  }

  const conn = document.getElementById('conn-status');
  conn.classList.toggle('bad', !state.connected);
  document.getElementById('conn-text').textContent =
    state.connected ? '연결됨' : '연결 안 됨';
  document.getElementById('last-updated').textContent = state.lastSuccessAt
    ? state.lastSuccessAt.toLocaleTimeString('ko-KR') : '–';
}

function showView(name) {
  ['view-list', 'view-activity', 'view-detail'].forEach((id) => {
    document.getElementById(id).hidden = id !== name;
  });
}

function renderPoll() {
  renderShell();
  document.getElementById('boot-error').hidden = true;
  if (state.route.view === 'activity') {
    showView('view-activity');
    const container = document.getElementById('view-activity');
    renderActivity(container, {
      active: state.tasks.filter((task) => ACTIVE_SET.has(task.phase)),
      cards: activityCards(),
      expanded: state.expandedDecisions,
    }, actions);
  } else {
    showView('view-list');
    renderList(document.getElementById('view-list'), {
      rows: visibleTasks(),
      stats: computeStats(),
      total: state.tasks.length,
      filters: state.filters,
      sort: state.sort,
      selected: state.selected,
    }, actions);
  }
}

function activityCards() {
  const cards = [];
  const gaps = [];
  state.tasks.forEach((task) => {
    if (task.phase === 'blocked') {
      cards.push({
        key: `blocked:${task.folder}`,
        task,
        reason: task.next === null || task.next === undefined
          ? 'blocked — next 미기재' : `blocked — next: ${task.next}`,
        claims: Array.isArray(task.claim_details) ? task.claim_details : [],
      });
      return;
    }
    const gapClaims = (Array.isArray(task.claim_details) ? task.claim_details : [])
      .filter((claim) => claim.status === 'gap');
    if (gapClaims.length > 0) {
      gaps.push({
        key: `gap:${task.folder}`,
        task,
        reason: `gap claims ${gapClaims.length}건 — 판단 필요`,
        claims: gapClaims,
      });
    }
  });
  return cards.concat(gaps);
}

function renderDetailView() {
  renderShell();
  showView('view-detail');
  const task = state.tasks.find((item) => item.folder === state.route.folder);
  const container = document.getElementById('view-detail');
  renderDetail(container, {
    folder: state.route.folder,
    task,
    bundleDoc: state.bundleDoc,
    docOpen: state.docOpen,
  }, actions);
}

// --- 데이터 ------------------------------------------------------------------

async function fetchTasks() {
  try {
    const response = await fetch('/api/tasks');
    if (!response.ok) { throw new Error(`api 상태 ${response.status}`); }
    const payload = await response.json();
    state.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
    state.connected = true;
    state.lastSuccessAt = new Date();
  } catch (error) {
    state.connected = false;
    printBootError(`상태 갱신 실패 (${error.message}) — 재시도 중`);
  }
}

function printBootError(message) {
  const node = document.getElementById('boot-error');
  node.textContent = message;
  node.hidden = false;
}

async function loadBundle(folder) {
  state.bundleDoc = null;
  renderDetailView();
  try {
    const response = await fetch('/api/bundle/' + encodeURIComponent(folder));
    if (!response.ok) { throw new Error(`api 상태 ${response.status}`); }
    const payload = await response.json();
    if (state.route.view !== 'detail' || state.route.folder !== folder) {
      return; // 진입 후 라우트 변경 — 폐기
    }
    state.bundleDoc = { folder, markdown: payload.markdown, ok: true };
  } catch {
    if (state.route.view !== 'detail' || state.route.folder !== folder) {
      return;
    }
    state.bundleDoc = { folder, markdown: null, ok: false };
  }
  renderDetailView();
}

// --- 액션 (뷰 → 앱 코어) ------------------------------------------------------

const actions = {
  navigate,
  toggleSelect(folder) {
    state.selected = state.selected.includes(folder)
      ? state.selected.filter((name) => name !== folder)
      : state.selected.concat([folder]);
    renderPoll();
  },
  clearSelection() {
    state.selected = [];
    renderPoll();
  },
  copyIds(button) {
    const text = state.selected.join('\n');
    const original = button.textContent;
    const finish = (message) => {
      button.textContent = message;
      setTimeout(() => { button.textContent = original; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => finish('복사됨'))
        .catch(() => finish('복사 실패'));
    } else {
      finish('복사 실패');
    }
  },
  setFilter(patch) {
    state.filters = { ...state.filters, ...patch };
    renderPoll();
  },
  setSort(patch) {
    state.sort = { ...state.sort, ...patch };
    renderPoll();
  },
  toggleSortDir() {
    state.sort = { ...state.sort,
      dir: state.sort.dir === 'asc' ? 'desc' : 'asc' };
    renderPoll();
  },
  toggleDecision(key) {
    state.expandedDecisions = state.expandedDecisions.includes(key)
      ? state.expandedDecisions.filter((name) => name !== key)
      : state.expandedDecisions.concat([key]);
    renderPoll();
  },
  toggleDoc() {
    state.docOpen = !state.docOpen;
    renderDetailView();
  },
};

// --- 폴링·부트 ---------------------------------------------------------------

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
    state.timer = setInterval(() => {
      fetchTasks().then(() => {
        if (state.route.view !== 'detail') {
          renderPoll(); // 상세 뷰는 문서 DOM 보존 — 셸 카운트만 시간 경과 표시
        } else {
          renderShell();
        }
      });
    }, ms);
  }
}

async function boot() {
  await fetchTasks();
  if (!state.connected) {
    setTimeout(boot, BOOT_RETRY_MS); // 성공까지 라우팅 보류 — 오류 표시 중
    return;
  }
  booted = true;
  applyRoute();
}

function setupControls() {
  document.getElementById('refresh-now').addEventListener('click', () => {
    fetchTasks().then(() => {
      // 수동 전체 갱신 — 현 뷰 강제 재렌더 포함
      if (state.route.view === 'detail') {
        loadBundle(state.route.folder);
      } else {
        renderPoll();
      }
    });
  });
  const interval = document.getElementById('refresh-interval');
  interval.value = String(DEFAULT_REFRESH_MS);
  interval.addEventListener('change', (event) => {
    applyInterval(Number(event.target.value));
  });
  window.addEventListener('hashchange', () => {
    if (!booted) { return; } // 부팅 확정 시점에 applyRoute가 재평가한다
    applyRoute();
  });
}

function init() {
  setupControls();
  applyInterval(DEFAULT_REFRESH_MS);
  boot();
}

init();
