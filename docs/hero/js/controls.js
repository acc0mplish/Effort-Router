// 재생 제어 — 재생·일시정지·반복·스크러버. 렌더는 항상 t의 순수 함수라 결정론이 깨지지 않는다.
// 색·폭 등 UI 수치도 CONFIG에서 CSS 사용자 정의 속성으로 주입한다(하드코딩 금지).
(() => {
  'use strict';
  const CONFIG = HERO_CONFIG;
  const canvas = document.getElementById('hero-canvas');
  const btn = document.getElementById('btn-play');
  const loopChk = document.getElementById('chk-loop');
  const scrub = document.getElementById('scrub');
  const stateEl = document.getElementById('playback-state');
  const timeEl = document.getElementById('time-label');
  const ctx = canvas.getContext('2d');

  canvas.width = CONFIG.layout.width;
  canvas.height = CONFIG.layout.height;
  scrub.max = String(CONFIG.meta.loopSeconds);
  scrub.step = String(1 / CONFIG.export.fps);

  const rootStyle = document.documentElement.style;
  rootStyle.setProperty('--paper', CONFIG.palette.paper);
  rootStyle.setProperty('--ink', CONFIG.palette.ink);
  rootStyle.setProperty('--accent', CONFIG.palette.accent);
  rootStyle.setProperty('--font-body', CONFIG.type.fontFamily);
  // 제품명·접근성 설명은 CONFIG 단일 출처에서 주입한다 — HTML의 정적 title·라벨은
  // JS 주입 전 폴백이며 장면 문구는 아니다(④ GAP-R3: 주석 정확화).
  document.title = CONFIG.meta.pageTitle;
  canvas.setAttribute('aria-label', CONFIG.meta.canvasLabel);

  const PLAYING_TEXT = '재생 중';
  const PAUSED_TEXT = '일시정지';
  const st = { playing: false, t: 0, last: 0, raf: 0 };

  function syncScrub() {
    scrub.value = String(st.t);
  }

  function syncLabels() {
    stateEl.textContent = st.playing ? PLAYING_TEXT : PAUSED_TEXT;
    btn.textContent = st.playing ? '❚❚ 일시정지' : '▶ 재생';
    btn.setAttribute('aria-pressed', String(st.playing));
    timeEl.textContent = `${st.t.toFixed(2)}초 · 프레임 ${HeroEngine.frameOf(st.t)}`;
  }

  function renderAt(t) {
    st.t = t;
    HeroEngine.render(ctx, t);
    syncScrub();
    syncLabels();
  }

  function tick(now) {
    if (!st.playing) return;
    const dt = Math.min((now - st.last) / 1000, 0.25); // 탭 복귀 등 비정상 점프 방지
    st.last = now;
    let t = st.t + dt;
    const total = CONFIG.meta.loopSeconds;
    if (t >= total) {
      if (loopChk.checked) {
        t -= total;
      } else {
        renderAt(total - 1 / CONFIG.export.fps);
        setPlaying(false);
        return;
      }
    }
    renderAt(t);
    if (st.playing) st.raf = requestAnimationFrame(tick);
  }

  function setPlaying(p) {
    if (p === st.playing) {
      syncLabels();
      return;
    }
    st.playing = p;
    if (p) {
      st.last = performance.now();
      st.raf = requestAnimationFrame(tick);
    } else {
      cancelAnimationFrame(st.raf);
    }
    syncLabels();
  }

  btn.addEventListener('click', () => setPlaying(!st.playing));

  // 스크러버 — input 이벤트에서 render(t)를 동기 호출한다(자동화 검증 계약 §3.3-b).
  scrub.addEventListener('input', () => {
    renderAt(parseFloat(scrub.value));
    if (st.playing) st.last = performance.now();
  });

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) setPlaying(false);

  HeroEngine.whenReady().then(() => {
    renderAt(0);
    window.HERO_READY = true;
  });

  // 자동화 검증이 읽는 읽기 전용 스냅샷
  window.HeroControls = Object.freeze({
    getState: () => Object.freeze({ t: st.t, playing: st.playing, loop: loopChk.checked }),
  });
})();
