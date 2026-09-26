// 렌더 엔진 — render(ctx, t) 순수 함수.
// 모든 무작위성은 "요소 키 + 정수 프레임 인덱스"에서 파생된 시드(mulberry32)로 만들고
// 호출 순서에 의존하지 않는다. 무작위 전역 함수·시계 함수는 렌더 경로에서 일절 사용하지 않는다.
const HeroEngine = (() => {
  'use strict';
  const CONFIG = HERO_CONFIG;

  // ---- 결정론 도구 -------------------------------------------------------

  function fnv1a(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function next() {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  let curFrame = 0;
  let curTextAlpha = 1;
  let curBoxes = [];

  // 요소 키 → 시드. 프레임 인덱스가 섞여 프레임마다 미세하게 다른 필압이 된다.
  function prng(key) {
    return mulberry32((fnv1a(key) ^ CONFIG.motion.seed) + curFrame);
  }

  function frameOf(t) {
    return Math.floor(t * CONFIG.export.fps);
  }

  const easeFns = {
    linear: (p) => p,
    easeOutCubic: (p) => 1 - Math.pow(1 - p, 3),
    easeInOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    easeOutBack: (p) => {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
    },
  };

  function ease(name, p) {
    const fn = easeFns[name] || easeFns.linear;
    return fn(clamp01(p));
  }

  function clamp01(v) {
    return Math.min(1, Math.max(0, v));
  }

  function lerp(a, b, s) {
    return a + (b - a) * s;
  }

  function easeAt(name, t, start, dur) {
    return ease(name, (t - start) / dur);
  }

  function withAlpha(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }

  // ---- 타임라인 ----------------------------------------------------------

  // 오버랩(0.4s)은 인접 씬 사이 5개 경계 중심의 크로스페이드 창(경계 ±0.2s)으로 동작한다.
  // 나가는 씬은 경계까지 1→0.5, 들어오는 씬은 경계에서 0.5로 등장해 합성 alpha가 창 전체에서
  // 항상 1 — 배경 비침·경계 빈 프레임이 없다(④ GAP-R1: 경계 t에서도 두 씬이 0.5+0.5로 렌더).
  // 표시 연장 구간의 local은 씬 경계에서 고정된다(들어오는 씬은 첫 모습, 나가는 씬은 완료 모습).
  // 텍스트는 경계를 기준으로 교차 스왑된다: 나가는 문구는 창 전반부에 사라지고 들어오는
  // 문구는 창 후반부에 나타나 같은 슬롯 문구가 한 프레임에도 공존하지 않는다(bbox 계약).
  function visibleScenes(t) {
    const scenes = CONFIG.scenes;
    const half = CONFIG.motion.overlap / 2;
    const out = [];
    scenes.forEach((scene, i) => {
      const start = scene.start;
      const end = scene.start + scene.dur;
      if (t < start - half - 1e-9 || t > end + half + 1e-9) return;
      let alpha = 1;
      let textAlpha = 1;
      const fadingIn = i > 0 && t < start + half;
      const fadingOut = i < scenes.length - 1 && t > end - half;
      if (fadingIn) {
        const p = (t - (start - half)) / (half * 2);
        alpha = Math.min(alpha, clamp01(p));
        textAlpha = Math.min(textAlpha, clamp01(p * 2 - 1));
      }
      if (fadingOut) {
        const p = (end + half - t) / (half * 2);
        alpha = Math.min(alpha, clamp01(p));
        textAlpha = Math.min(textAlpha, clamp01(p * 2 - 1));
      }
      if (alpha <= 0.002) return;
      let localT = t;
      if (t < start) localT = start;
      if (t > end) localT = end;
      out.push({ scene, index: i, localT: localT - start, p: (localT - start) / scene.dur, alpha, textAlpha });
    });
    return out;
  }

  // 정지시간 계약(§3.2 경계 인식 차감): dur − (앞 오버랩) − (뒤 오버랩) ≥ minReadableSec
  function minReadableReport() {
    const scenes = CONFIG.scenes;
    const ov = CONFIG.motion.overlap;
    return scenes.map((scene, i) => {
      let readable = scene.dur;
      if (i > 0) readable -= ov;
      if (i < scenes.length - 1) readable -= ov;
      return {
        id: scene.id,
        dur: scene.dur,
        readable: Math.round(readable * 100) / 100,
        required: scene.minReadableSec,
        pass: readable >= scene.minReadableSec - 1e-9,
      };
    });
  }

  // ---- 손그림 헬퍼 -------------------------------------------------------

  function strokeStyle(ctx, opts) {
    ctx.strokeStyle = opts.color || CONFIG.palette.ink;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    if (opts.alpha != null) ctx.globalAlpha *= opts.alpha;
  }

  // 직선을 짧은 선분으로 쪼개 각 점에 시드 고정 지터를 준다. 선굵기는 경로 따라 ±15%.
  function jitterPts(x1, y1, x2, y2, key) {
    const M = CONFIG.motion;
    const len = Math.hypot(x2 - x1, y2 - y1);
    const n = Math.max(2, Math.round(len / M.strokeSegPx));
    const r = prng('ln:' + key);
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const s = i / n;
      const edge = i === 0 || i === n ? 0.35 : 1;
      pts.push({
        x: x1 + (x2 - x1) * s + (r() - 0.5) * 2 * M.jitterAmpPx * edge,
        y: y1 + (y2 - y1) * s + (r() - 0.5) * 2 * M.jitterAmpPx * edge,
        w: 1 + 0.3 * (r() - 0.5),
      });
    }
    return pts;
  }

  function strokePts(ctx, pts, opts) {
    ctx.save();
    strokeStyle(ctx, opts);
    for (let i = 1; i < pts.length; i++) {
      ctx.beginPath();
      ctx.lineWidth = (opts.width ?? CONFIG.motion.lineWidth) * pts[i].w;
      ctx.moveTo(pts[i - 1].x, pts[i - 1].y);
      ctx.lineTo(pts[i].x, pts[i].y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function line(ctx, x1, y1, x2, y2, opts = {}) {
    const key = opts.key ?? `L${Math.round(x1)},${Math.round(y1)},${Math.round(x2)},${Math.round(y2)}`;
    strokePts(ctx, jitterPts(x1, y1, x2, y2, key), opts);
  }

  function poly(ctx, pts, opts = {}) {
    for (let i = 1; i < pts.length; i++) {
      line(ctx, pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y, { ...opts, key: `${opts.key ?? 'P'}:${i}` });
    }
  }

  // 채색은 반투명 단색 1회(마커 느낌) — GIF 팔레트 안정화를 위해 직사각 그대로 둔다.
  function rect(ctx, x, y, w, h, opts = {}) {
    if (opts.fill) {
      ctx.save();
      ctx.globalAlpha *= opts.fillAlpha ?? 1;
      ctx.fillStyle = opts.fill;
      ctx.fillRect(x, y, w, h);
      ctx.restore();
    }
    const k = opts.key ?? `R${Math.round(x)},${Math.round(y)},${Math.round(w)},${Math.round(h)}`;
    line(ctx, x, y, x + w, y, { ...opts, key: `${k}:t` });
    line(ctx, x + w, y, x + w, y + h, { ...opts, key: `${k}:r` });
    line(ctx, x + w, y + h, x, y + h, { ...opts, key: `${k}:b` });
    line(ctx, x, y + h, x, y, { ...opts, key: `${k}:l` });
  }

  function circle(ctx, cx, cy, r, opts = {}) {
    const M = CONFIG.motion;
    const n = 22;
    const r2 = prng('c:' + (opts.key ?? `c${Math.round(cx)},${Math.round(cy)},${Math.round(r)}`));
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      const rr = r + (r2() - 0.5) * 2 * M.jitterAmpPx;
      pts.push({ x: cx + Math.cos(a) * rr, y: cy + Math.sin(a) * rr, w: 1 });
    }
    strokePts(ctx, pts, opts);
  }

  function check(ctx, cx, cy, size, opts = {}) {
    const k = opts.key ?? `k${Math.round(cx)},${Math.round(cy)}`;
    line(ctx, cx - size * 0.45, cy + size * 0.05, cx - size * 0.1, cy + size * 0.38, { ...opts, key: `${k}:a` });
    line(ctx, cx - size * 0.1, cy + size * 0.38, cx + size * 0.5, cy - size * 0.35, { ...opts, key: `${k}:b` });
  }

  function arrowHead(ctx, x, y, angle, size, opts = {}) {
    const k = opts.key ?? `h${Math.round(x)},${Math.round(y)}`;
    const a1 = angle + Math.PI - 0.45;
    const a2 = angle + Math.PI + 0.45;
    line(ctx, x, y, x + Math.cos(a1) * size, y + Math.sin(a1) * size, { ...opts, key: `${k}:1` });
    line(ctx, x, y, x + Math.cos(a2) * size, y + Math.sin(a2) * size, { ...opts, key: `${k}:2` });
  }

  function pathLength(pts) {
    let total = 0;
    for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    return total;
  }

  // 경로를 steppx 간격으로 보간 — {x, y, d(누적 거리)} 목록
  function resamplePath(pts, step) {
    const out = [{ x: pts[0].x, y: pts[0].y, d: 0 }];
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1];
      const b = pts[i];
      const segLen = Math.hypot(b.x - a.x, b.y - a.y);
      const n = Math.max(1, Math.round(segLen / step));
      for (let j = 1; j <= n; j++) {
        out.push({ x: lerp(a.x, b.x, j / n), y: lerp(a.y, b.y, j / n), d: out[out.length - 1].d + segLen / n });
      }
    }
    return out;
  }

  // 길이가 자라는 점선 궤적 — progress가 경로 길이의 앞부분까지만 점선을 그린다.
  // 대시 위상은 요소 키에서 파생(시간과 무관)되어 그려진 부분은 고정된다.
  function dashTrail(ctx, pathPts, progress, opts = {}) {
    const on = opts.on ?? 16;
    const off = opts.off ?? 13;
    const fine = resamplePath(pathPts, 4);
    const target = pathLength(pathPts) * clamp01(progress);
    const period = on + off;
    const phase = prng('d:' + (opts.key ?? 'trail'))() * period;
    ctx.save();
    strokeStyle(ctx, opts);
    ctx.lineWidth = opts.width ?? 4;
    ctx.beginPath();
    let pen = false;
    for (const p of fine) {
      if (p.d > target) break;
      const inOn = (p.d + phase) % period < on;
      if (inOn && !pen) {
        ctx.moveTo(p.x, p.y);
        pen = true;
      } else if (inOn && pen) {
        ctx.lineTo(p.x, p.y);
      } else {
        pen = false;
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  // ---- 텍스트 ------------------------------------------------------------

  function textBoxOf(spec, m) {
    const w = m.actualBoundingBoxRight != null ? m.actualBoundingBoxLeft + m.actualBoundingBoxRight : m.width;
    const asc = m.actualBoundingBoxAscent || spec.px * 0.78;
    const desc = m.actualBoundingBoxDescent || spec.px * 0.22;
    const x0 = spec.align === 'left' ? spec.x : spec.align === 'right' ? spec.x - w : spec.x - w / 2;
    const y0 = spec.y - asc;
    if (!spec.rotate) return { text: spec.text, x: x0, y: y0, w, h: asc + desc };
    const cos = Math.cos(spec.rotate);
    const sin = Math.sin(spec.rotate);
    const cx = spec.x;
    const cy = spec.y;
    const corners = [
      [x0, y0], [x0 + w, y0], [x0, y0 + asc + desc], [x0 + w, y0 + asc + desc],
    ].map(([px, py]) => {
      const dx = px - cx;
      const dy = py - cy;
      return [cx + dx * cos - dy * sin, cy + dx * sin + dy * cos];
    });
    const xs = corners.map((c) => c[0]);
    const ys = corners.map((c) => c[1]);
    const bx = Math.min(...xs);
    const by = Math.min(...ys);
    return { text: spec.text, x: bx, y: by, w: Math.max(...xs) - bx, h: Math.max(...ys) - by };
  }

  // 텍스트 그리기 + bbox 반환·기록(내보내기 품질 검사용). 보이지 않는 텍스트는 기록하지 않는다.
  function text(ctx, spec) {
    if (curTextAlpha * (spec.alpha ?? 1) <= 0.001) return null;
    const T = CONFIG.type;
    ctx.save();
    ctx.font = `${spec.weight || 400} ${spec.px}px ${spec.code ? T.codeFamily : T.fontFamily}`;
    ctx.fillStyle = spec.color || CONFIG.palette.ink;
    ctx.textAlign = spec.align || 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.globalAlpha *= spec.alpha ?? 1;
    const m = ctx.measureText(spec.text);
    const box = textBoxOf(spec, m);
    if (spec.rotate) {
      ctx.translate(spec.x, spec.y);
      ctx.rotate(spec.rotate);
      ctx.fillText(spec.text, 0, 0);
    } else {
      ctx.fillText(spec.text, spec.x, spec.y);
    }
    ctx.restore();
    curBoxes.push(box);
    return box;
  }

  // 스케일·회전 변형 안에서 스트로크를 그리기 위한 래퍼(텍스트는 넣지 않는다 — bbox 왜곡 방지)
  function withTransform(ctx, x, y, scale, rotate, drawFn) {
    ctx.save();
    ctx.translate(x, y);
    if (rotate) ctx.rotate(rotate);
    if (scale != null && scale !== 1) ctx.scale(scale, scale);
    drawFn();
    ctx.restore();
  }

  // ---- 렌더 ---------------------------------------------------------------

  function render(ctx, t) {
    const L = CONFIG.layout;
    curFrame = frameOf(t);
    curBoxes = [];
    ctx.save();
    ctx.fillStyle = CONFIG.palette.paper;
    ctx.fillRect(0, 0, L.width, L.height);
    ctx.restore();
    for (const v of visibleScenes(t)) {
      const fn = HeroScenes[v.scene.visual];
      if (!fn) throw new Error('알 수 없는 비주얼: ' + v.scene.visual);
      ctx.save();
      ctx.globalAlpha = v.alpha;
      curTextAlpha = v.textAlpha;
      fn(ctx, v.scene, { t: v.localT, p: v.p });
      ctx.restore();
    }
    curTextAlpha = 1;
  }

  function getTextBoxes() {
    return curBoxes;
  }

  async function whenReady() {
    await document.fonts.load("400 48px Gaegu");
    await document.fonts.load("700 48px Gaegu");
    await document.fonts.ready;
  }

  return Object.freeze({
    render,
    getTextBoxes,
    whenReady,
    visibleScenes,
    minReadableReport,
    frameOf,
    ease,
    lerp,
    clamp01,
    easeAt,
    withAlpha,
    line,
    poly,
    rect,
    circle,
    check,
    arrowHead,
    dashTrail,
    text,
    withTransform,
    prng,
  });
})();
