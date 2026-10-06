'use strict';
// r37 미니 마크다운 렌더러 — 순수 함수 모듈(외부 의존 0).
// 범위(번들 §마크다운 렌더러 범위 — 번들 실측 구성요소 기반):
//   헤딩 #~###### · 가로선 --- · 인용 >(1레벨) · 불릿/번호목록(2레벨) ·
//   표(|---| 구분 행) · 코드펜스(언어 태그 표시만) · 인라인 볼드/코드/링크.
// 보안(M1 — 일원화): 모든 텍스트는 createElement·textContent로만 주입한다.
// 마크업 문자열 일괄 주입 API는 사용 금지, 사전 이스케이프도 금지(이스케이프는
// 브라우저 담당).
// 링크 href는 http:/https: 스킴만 허용 — 그 외 스킴은 텍스트로 강등.

// 표 셀 분할용 이스케이프 파이프 placeholder(H3):
// 행에서 \를 placeholder로 치환 → | 로 분할 → 셀 텍스트에서 복원.
const PIPE_PLACEHOLDER = '\u0001';
const ESCAPED_PIPE = '\\|';
const FENCE_TOKEN = '```';
// 링크 스킴 화이트리스트 — 문자열에 '//'를 두지 않는다(C11 외부 스킴 0 계약).
const SAFE_SCHEMES = ['http:', 'https:'];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) { node.className = className; }
  if (text !== undefined && text !== null) { node.textContent = String(text); }
  return node;
}

function restorePipes(text) {
  return String(text).split(PIPE_PLACEHOLDER).join('|');
}

function isSafeHref(href) {
  return SAFE_SCHEMES.some((scheme) => href.startsWith(scheme));
}

// 인라인: **볼드** · `코드` · [텍스트](url) — 텍스트 노드는 전부 textContent.
function appendInline(target, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]*\))/g;
  const parts = String(text).split(pattern);
  parts.forEach((part) => {
    if (part === '') { return; }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      target.appendChild(el('strong', null, restorePipes(part.slice(2, -2))));
    } else if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      target.appendChild(el('code', null, restorePipes(part.slice(1, -1))));
    } else if (part.startsWith('[') && part.includes('](') && part.endsWith(')')) {
      appendLink(target, part);
    } else {
      target.appendChild(document.createTextNode(restorePipes(part)));
    }
  });
}

function appendLink(target, token) {
  const closeBracket = token.indexOf('](');
  const label = token.slice(1, closeBracket);
  const href = token.slice(closeBracket + 2, -1);
  if (isSafeHref(href)) {
    const anchor = el('a', null, restorePipes(label));
    anchor.href = href;
    anchor.rel = 'noopener noreferrer';
    target.appendChild(anchor);
    return;
  }
  // 비허용 스킴 — 링크를 만들지 않고 텍스트로 강등한다.
  target.appendChild(document.createTextNode(restorePipes(label)));
}

// 표 — 셀 분할 순서 계약(H3): \ 치환(전수) → | 분할 → 복원.
function splitRow(line) {
  const guarded = line.trim().split(ESCAPED_PIPE).join(PIPE_PLACEHOLDER);
  let cells = guarded.split('|');
  if (cells.length > 0 && cells[0].trim() === '') { cells = cells.slice(1); }
  if (cells.length > 0 && cells[cells.length - 1].trim() === '') {
    cells = cells.slice(0, -1);
  }
  return cells;
}

function isDivider(line) {
  return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
}

function renderTable(headerLine, bodyLines) {
  const table = el('table');
  const thead = el('thead');
  const headRow = el('tr');
  splitRow(headerLine).forEach((cell) => {
    const th = el('th');
    appendInline(th, cell.trim());
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = el('tbody');
  bodyLines.forEach((line) => {
    const row = el('tr');
    splitRow(line).forEach((cell) => {
      const td = el('td');
      appendInline(td, cell.trim());
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  return table;
}

function renderFence(lang, codeLines) {
  const pre = el('pre');
  if (lang) {
    pre.appendChild(el('span', 'fence-lang', lang));
  }
  const code = el('code', null, codeLines.join('\n'));
  pre.appendChild(code);
  return pre;
}

function renderHeading(level, text) {
  // H4+는 H4 스타일로 근사한다(범위 계약).
  const tag = `h${Math.min(Math.max(level, 1), 4)}`;
  const node = el(tag);
  appendInline(node, text);
  return node;
}

function renderListBlock(items) {
  // items: [{ ordered, depth, text }] — 중첩 2레벨.
  const root = items[0].ordered ? el('ol') : el('ul');
  let currentList = root;
  let currentDepth = items[0].depth;
  let currentLi = null;
  items.forEach((item) => {
    if (item.depth > currentDepth) {
      const nested = item.ordered ? el('ol') : el('ul');
      if (currentLi) { currentLi.appendChild(nested); }
      currentList = nested;
      currentDepth = item.depth;
      currentLi = null;
    } else if (item.depth < currentDepth) {
      currentList = root;
      currentDepth = item.depth;
      currentLi = null;
    }
    currentLi = el('li');
    appendInline(currentLi, item.text);
    currentList.appendChild(currentLi);
  });
  return root;
}

function renderQuoteBlock(lines) {
  const quote = el('blockquote');
  lines.forEach((line) => {
    const p = el('p');
    appendInline(p, line);
    quote.appendChild(p);
  });
  return quote;
}

// 행 단위 상태 기계 — 블록 요소를 순서대로 fragment에 쌓는다.
export function renderMarkdown(text) {
  const fragment = document.createDocumentFragment();
  const lines = String(text).split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') { i += 1; continue; }
    if (line.startsWith(FENCE_TOKEN)) {
      const lang = line.slice(FENCE_TOKEN.length).trim();
      const codeLines = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith(FENCE_TOKEN)) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1; // 닫는 펜스 소비(부재 시 문서 끝)
      fragment.appendChild(renderFence(lang, codeLines));
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      fragment.appendChild(renderHeading(heading[1].length, heading[2]));
      i += 1;
      continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      fragment.appendChild(el('hr'));
      i += 1;
      continue;
    }
    if (line.includes('|') && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const bodyLines = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        bodyLines.push(lines[i]);
        i += 1;
      }
      fragment.appendChild(renderTable(line, bodyLines));
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ''));
        i += 1;
      }
      fragment.appendChild(renderQuoteBlock(quoteLines));
      continue;
    }
    const bullet = line.match(/^(\s*)[-*]\s+(.*)$/);
    const ordered = line.match(/^(\s*)\d+\.\s+(.*)$/);
    if (bullet || ordered) {
      const items = [];
      while (i < lines.length) {
        const b = lines[i].match(/^(\s*)[-*]\s+(.*)$/);
        const o = lines[i].match(/^(\s*)\d+\.\s+(.*)$/);
        if (!b && !o) { break; }
        const match = b || o;
        items.push({
          ordered: Boolean(o),
          depth: Math.floor(match[1].length / 2),
          text: match[2],
        });
        i += 1;
      }
      fragment.appendChild(renderListBlock(items));
      continue;
    }
    // 문단 — 연속 텍스트 행을 하나의 p로 모은다(행 사이 br).
    const paragraph = el('p');
    let first = true;
    while (i < lines.length && lines[i].trim() !== ''
      && !/^(#{1,6})\s/.test(lines[i])
      && !lines[i].startsWith(FENCE_TOKEN)
      && !/^\s*>\s?/.test(lines[i])
      && !/^(\s*)[-*]\s+/.test(lines[i])
      && !/^(\s*)\d+\.\s+/.test(lines[i])) {
      if (!first) { paragraph.appendChild(el('br')); }
      appendInline(paragraph, lines[i]);
      first = false;
      i += 1;
    }
    fragment.appendChild(paragraph);
  }
  return fragment;
}
