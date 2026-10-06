'use strict';
// r37 뷰2 — 실행 현황. 좌 Current work(phase ∈ implement/review/verify —
// visual-target 기본안) + 우 디시전 레일(~370px, 크림 아코디언 — blocked 과업 +
// gap claims 카드). 표시 전용 — textarea·제출 버튼 없음(상호작용 경계 8).
// 행 클릭 → 뷰3 진입(뷰1과 동일 계약 — navigate 배선).
// 폴링마다 전체 재렌더한다(입력 요소 없음 — 포커스 손실 없음).

const EXCERPT_FALLBACK = '원 요구 발췌 없음 — 상세 참조';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) { node.className = className; }
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  return node;
}

function excerptText(task) {
  return task.excerpt === null || task.excerpt === undefined
    ? EXCERPT_FALLBACK : String(task.excerpt);
}

function statePill(phase) {
  // 활성 phase만 들어오는 뷰 — 블루 ● 칩 단일 계약(원본 "Working" 상당).
  const pill = el('span', 'pill badge-blue');
  pill.appendChild(el('span', 'badge-glyph', '●'));
  pill.appendChild(document.createTextNode(String(phase)));
  return pill;
}

function workRow(task, actions) {
  const row = el('div', 'work-row');
  row.dataset.folder = task.folder;
  row.tabIndex = 0;
  row.setAttribute('role', 'link');

  const title = el('p', 'work-title');
  title.appendChild(el('span', 'work-name', task.task));
  title.appendChild(el('span', 'work-id mono-id', task.folder));
  row.appendChild(title);

  const stateLine = el('div', 'work-state');
  stateLine.appendChild(statePill(task.phase));
  const sublabel = task.next === null || task.next === undefined
    ? String(task.phase) : `${task.phase} · next: ${task.next}`;
  stateLine.appendChild(el('span', 'work-sublabel', sublabel));
  row.appendChild(stateLine);

  row.appendChild(el('p', 'work-desc', excerptText(task)));
  row.appendChild(el('p', 'work-meta tnum', `spawns · ${task.spawns}`));

  // 행 클릭·Enter = 뷰3 진입(뷰1과 동일 계약)
  row.addEventListener('click', () => actions.navigate(task.folder));
  row.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      actions.navigate(task.folder);
    }
  });
  return row;
}

// 디시전 카드 — 헤더 클릭 = 아코디언 토글(로컬). 본문은 next·claims 문면 표시
// 전용이다(쓰기 UI 미구현).
function decisionCard(card, expanded, actions) {
  const node = el('div', 'decision-card');
  const head = el('button', 'decision-head');
  head.type = 'button';
  head.appendChild(el('span', 'decision-chevron', expanded ? '▼' : '▶'));
  head.appendChild(el('span', 'badge-glyph', '◇'));
  const title = el('span', 'decision-title');
  title.appendChild(el('span', null, card.task.task));
  title.appendChild(el('span', 'mono-id', card.task.folder));
  head.appendChild(title);
  head.addEventListener('click', () => actions.toggleDecision(card.key));
  node.appendChild(head);

  if (!expanded) { return node; }

  const body = el('div', 'decision-body');
  if (card.reason) {
    body.appendChild(el('p', null, card.reason));
  }
  if (card.claims.length === 0) {
    body.appendChild(el('p', 'muted', 'claims 문면이 없다'));
  }
  card.claims.forEach((claim) => {
    const item = el('div', 'decision-claim');
    item.appendChild(el('span', `claim-chip claim-${claim.status}`,
      String(claim.status)));
    item.appendChild(el('span', 'claim-text', claim.claim));
    if (claim.evidence) {
      item.appendChild(el('span', 'claim-evidence', claim.evidence));
    }
    body.appendChild(item);
  });
  node.appendChild(body);
  return node;
}

// 카드 목록 파생은 app.js 단일 소유(activityCards) — 이 모듈은 렌더만 한다.
// 카드 구조: blocked 과업(next 사유·claims 전체) + gap>0 비-blocked 과업
// (gap claims 한정) — blocked 카드에 claims가 포함되므로 gap 카드 중복 제외.
export function renderActivity(container, vm, actions) {
  const grid = el('div', 'activity-grid');
  const left = el('div', 'work-pane');
  const leftHead = el('div', 'pane-head');
  leftHead.appendChild(el('strong', null, 'Current work'));
  leftHead.appendChild(el('span', 'tnum', `${vm.active.length}개 과업`));
  left.appendChild(leftHead);
  if (vm.active.length === 0) {
    left.appendChild(el('p', 'empty-state', '진행 중 과업이 없다'));
  }
  vm.active.forEach((task) => {
    left.appendChild(workRow(task, actions));
  });
  grid.appendChild(left);

  const right = el('div', 'decision-pane');
  const rightHead = el('div', 'pane-head');
  rightHead.appendChild(el('strong', null, '판단 대기'));
  rightHead.appendChild(el('span', 'tnum', String(vm.cards.length)));
  right.appendChild(rightHead);
  if (vm.cards.length === 0) {
    right.appendChild(el('p', 'empty-state', '판단 대기 항목이 없다'));
  }
  vm.cards.forEach((card) => {
    right.appendChild(decisionCard(card, vm.expanded.includes(card.key), actions));
  });
  grid.appendChild(right);

  container.replaceChildren(grid);
}
