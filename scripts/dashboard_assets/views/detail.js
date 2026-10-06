'use strict';
// r37 뷰3 — 과업 상세. 모노 ID 헤더 → H1(task명) → 서브 배지 행(tier·phase·
// round·spawns·next·bundle 존재·parse_error 배지) → claims 섹션(r36 행 확장
// 이관처 — M3) → "분석 및 계획" 행 + 문서 뷰어 토글.
// 문서는 app.js가 진입 시 1회 /api/bundle 페치해 bundleDoc으로 전달한다 —
// 이 모듈은 순수 렌더(폴링 재렌더 대상 아님). 번들 404·부재 시 안내 문구
// ("번들을 불러올 수 없다" — 빈 뷰어 아님).

import { renderMarkdown } from '/markdown.js';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) { node.className = className; }
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  return node;
}

function subBadge(label, value, kind) {
  const chip = el('span', `badge badge-${kind}`);
  chip.appendChild(document.createTextNode(`${label}: ${value}`));
  return chip;
}

function buildSubRow(task) {
  const sub = el('div', 'detail-sub');
  // tier 색 계약(번들 §시각 매핑): L/XL=벽돌레드 · M=블루그레이 · S/None=회색 —
  // 뷰1 priority 패턴과 동일 클래스를 재사용한다.
  const tier = task.tier === null || task.tier === undefined ? null : String(task.tier);
  sub.appendChild(el('span',
    `priority ${tier === 'L' || tier === 'XL' ? 'priority-high'
      : tier === 'M' ? 'priority-mid' : 'priority-low'}`,
    `tier: ${tier === null ? '–' : tier}`));
  const phase = task.phase === null || task.phase === undefined
    ? null : String(task.phase);
  if (phase === null) {
    sub.appendChild(subBadge('phase', 'null', 'gray'));
  } else if (phase === 'done') {
    sub.appendChild(subBadge('phase', phase, 'green'));
  } else if (phase === 'implement' || phase === 'verify') {
    sub.appendChild(subBadge('phase', phase, 'blue'));
  } else {
    sub.appendChild(subBadge('phase', phase, 'cream'));
  }
  sub.appendChild(el('span', null,
    `round ${task.round.adversary}/${task.round.review}`));
  sub.appendChild(el('span', null, `spawns · ${task.spawns}`));
  sub.appendChild(el('span', null,
    task.next === null || task.next === undefined
      ? 'next –' : `next: ${task.next}`));
  sub.appendChild(el('span', null,
    task.bundle_exists ? 'bundle 있음' : 'bundle 없음'));
  if (task.parse_error) {
    sub.appendChild(el('span', 'parse-error-badge',
      `파손 state.json — ${task.parse_error}`));
  }
  return sub;
}

function buildClaimsSection(task) {
  const section = el('section', 'claims-section');
  section.appendChild(el('h2', null, 'claims'));
  const details = Array.isArray(task.claim_details) ? task.claim_details : [];
  if (details.length === 0) {
    section.appendChild(el('p', 'muted', 'claims 상세가 없다'));
    return section;
  }
  details.forEach((claim) => {
    const item = el('div', 'claim-item');
    item.appendChild(el('span', 'claim-text', claim.claim));
    const status = claim.status === null || claim.status === undefined
      ? 'other' : String(claim.status);
    const kind = status === 'verified' ? 'green'
      : status === 'pending' ? 'blue'
        : status === 'gap' ? 'cream' : 'gray';
    item.appendChild(el('span', `badge badge-${kind}`, status));
    if (claim.evidence) {
      item.appendChild(el('span', 'claim-evidence', claim.evidence));
    }
    section.appendChild(item);
  });
  return section;
}

function buildDocSection(task, bundleDoc, docOpen, actions) {
  const header = el('div', 'doc-header');
  header.appendChild(el('h2', null, '분석 및 계획'));
  const toggle = el('button', 'doc-toggle',
    docOpen ? '문서 닫기 ↘' : '문서 열기 ↗');
  toggle.type = 'button';
  toggle.addEventListener('click', () => actions.toggleDoc());
  header.appendChild(toggle);

  const wrapper = el('div');
  wrapper.appendChild(header);
  if (!docOpen) {
    wrapper.appendChild(el('p', 'muted',
      task.bundle_exists ? '번들 문서가 접혀 있다' : '번들 파일이 없다'));
    return wrapper;
  }

  const viewer = el('div', 'doc-viewer');
  if (bundleDoc === null) {
    viewer.appendChild(el('p', 'doc-loading', '번들을 불러오는 중…'));
  } else if (!bundleDoc.ok) {
    viewer.appendChild(el('p', 'doc-missing', '번들을 불러올 수 없다'));
  } else {
    viewer.classList.add('doc-md');
    viewer.appendChild(renderMarkdown(bundleDoc.markdown));
  }
  wrapper.appendChild(viewer);
  return wrapper;
}

export function renderDetail(container, vm, actions) {
  const wrap = el('div');

  const back = el('a', 'back-link', '← 리스트');
  back.href = '#/list';
  wrap.appendChild(back);

  // 폴더 소실 가드(④리뷰 LOW) — 뷰3 체류 중 과업 폴더가 사라진 경우
  // vm.task가 undefined다(TypeError 대신) 안내 렌더로 분기한다.
  if (!vm.task) {
    wrap.appendChild(el('p', 'detail-id mono-id', vm.folder));
    wrap.appendChild(el('p', 'empty-state', '과업을 찾을 수 없다 — 폴더가 사라졌다'));
    container.replaceChildren(wrap);
    return;
  }

  wrap.appendChild(el('p', 'detail-id mono-id', vm.folder));
  wrap.appendChild(el('h1', 'detail-title', vm.task.task));
  wrap.appendChild(buildSubRow(vm.task));
  wrap.appendChild(buildClaimsSection(vm.task));
  wrap.appendChild(buildDocSection(vm.task, vm.bundleDoc, vm.docOpen, actions));

  container.replaceChildren(wrap);
}
