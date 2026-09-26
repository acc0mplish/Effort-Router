#!/usr/bin/env node
// hero-motion 프레임 내보내기·검증 파이프라인 (node + playwright, 계획 §5.1).
// 사용법:
//   node export-frames.mjs                — 전체 검증 + 480프레임 덤프(fps 기본 20)
//   node export-frames.mjs --fps 12.5     — 하강 사다리 재덤프(프레임 재확보, 비균일 샘플링 금지)
//   node export-frames.mjs --smoke        — 최소 동작 확인(렌더 캡처 + 동일 t 2회 해시)
//   node export-frames.mjs --skip-frames  — 검증만 수행(프레임 덤프 생략, 개발 반복용)
import { chromium } from 'playwright';
import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const BUILD = path.join(ROOT, 'build');
const FRAMES = path.join(BUILD, 'frames');

// config.js는 브라우저·노드 양쪽에서 평가 가능한 순수 데이터 파일이다.
const CONFIG = new Function(readFileSync(path.join(ROOT, 'js/config.js'), 'utf8') + '\nreturn HERO_CONFIG;')();

const args = process.argv.slice(2);
const argVal = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
};
const FPS = Number(argVal('--fps') ?? CONFIG.export.fps);
const SMOKE = args.includes('--smoke');
const SKIP_FRAMES = args.includes('--skip-frames');
const TOTAL_FRAMES = Math.round(CONFIG.meta.loopSeconds * FPS);

let failures = 0;
const log = (...a) => console.log('[export]', ...a);
const fail = (...a) => {
  failures += 1;
  console.error('[export][FAIL]', ...a);
};
const ok = (cond, ...a) => {
  if (cond) log('PASS —', ...a);
  else fail(...a);
  return cond;
};

// 검증 표본 T_check — 각 씬 중간점 6개 + 씬 경계 5개(크로스페이드 합성 중간 — ④ GAP-R1
// 재설계로 경계 t는 2씬 동시·frozen local·이중 textAlpha 합성 경로를 지나므로 이 결정론을
// 직접 해시 검증해야 한다. 구 표본(end − ov/2)은 창 좌단 단일 씬 풀알파 지점이라 합성 미포함)
function tCheckSamples() {
  const mids = CONFIG.scenes.map((s) => s.start + s.dur / 2);
  const bounds = CONFIG.scenes.slice(0, -1).map((s) => s.start + s.dur);
  return [...mids, ...bounds].sort((a, b) => a - b);
}

async function main() {
  log(`fps=${FPS} 총프레임=${TOTAL_FRAMES} 총시간=${CONFIG.meta.loopSeconds}s`);
  if (!Number.isFinite(FPS) || FPS <= 0) return fail('fps 인자가 올바르지 않다');
  if (Math.round((1000 / FPS) * 100) % 10 !== 0) return fail(`fps ${FPS}의 프레임 시간 ${1000 / FPS}ms가 GIF 10ms 양자와 맞지 않는다`);
  if (!Number.isInteger(TOTAL_FRAMES)) return fail(`fps ${FPS}에서 총프레임이 정수가 아니다`);
  if (failures) return;

  mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1200 },
    deviceScaleFactor: 1,
  });
  // 오프라인 증명: http(s) 전면 차단 + 오프라인 전환 후 로드(폰트·스크립트는 모두 로컬 file://)
  await context.route(/^https?:\/\//, (route) => route.abort());
  await context.setOffline(true);
  const page = await context.newPage();
  page.on('pageerror', (e) => fail('페이지 예외:', e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') fail('콘솔 에러:', m.text());
  });

  await page.goto('file://' + path.join(ROOT, 'hero-motion.html'));
  await page.waitForFunction('window.HERO_READY === true', null, { timeout: 20000 });
  log('로드 완료(오프라인 컨텍스트) — 폰트 ready 플래그 도달');
  const fontOk = await page.evaluate(() => document.fonts.check('48px Gaegu'));
  ok(fontOk === true, `document.fonts.check('48px Gaegu') === ${fontOk} (오프라인 로드·claim 9)`);
  if (failures) {
    await browser.close();
    return;
  }

  const renderData = (t) =>
    page.evaluate((tt) => {
      const c = document.getElementById('hero-canvas');
      HeroEngine.render(c.getContext('2d'), tt);
      return c.toDataURL('image/png');
    }, t);
  const renderOnly = (t) =>
    page.evaluate((tt) => {
      const c = document.getElementById('hero-canvas');
      HeroEngine.render(c.getContext('2d'), tt);
    }, t);
  const boxesAt = (t) =>
    page.evaluate((tt) => {
      const c = document.getElementById('hero-canvas');
      HeroEngine.render(c.getContext('2d'), tt);
      return HeroEngine.getTextBoxes();
    }, t);
  const aHashAt = (t) =>
    page.evaluate((tt) => {
      const c = document.getElementById('hero-canvas');
      const ctx = c.getContext('2d');
      HeroEngine.render(ctx, tt);
      // 8×8 평균 해시 — drawImage 축소 에일리어싱을 피하기 위해 셀별 면적 평균을 직접 계산
      const img = ctx.getImageData(0, 0, c.width, c.height).data;
      const W = c.width;
      const H = c.height;
      const grays = [];
      for (let by = 0; by < 8; by++) {
        for (let bx = 0; bx < 8; bx++) {
          const x0 = Math.floor((bx * W) / 8);
          const x1 = Math.floor(((bx + 1) * W) / 8);
          const y0 = Math.floor((by * H) / 8);
          const y1 = Math.floor(((by + 1) * H) / 8);
          let sum = 0;
          let n = 0;
          for (let y = y0; y < y1; y += 6) {
            for (let x = x0; x < x1; x += 6) {
              const i = (y * W + x) * 4;
              sum += 0.299 * img[i] + 0.587 * img[i + 1] + 0.114 * img[i + 2];
              n += 1;
            }
          }
          grays.push(sum / n);
        }
      }
      const avg = grays.reduce((a, b) => a + b, 0) / 64;
      return grays.map((g) => (g >= avg ? '1' : '0')).join('');
    }, t);

  // ---- 결정론 검증(claim 1) ------------------------------------------------
  const samples = SMOKE ? [0, CONFIG.scenes[0].dur / 2] : tCheckSamples();
  log(`결정론 검증 — T_check ${samples.length}표본(씬 ${Math.min(samples.length, CONFIG.scenes.length)} + 경계 합성 ${Math.max(0, samples.length - CONFIG.scenes.length)}), 각 2회 렌더`);
  for (const t of samples) {
    const d1 = await renderData(t);
    const d2 = await renderData(t);
    ok(d1 === d2, `t=${t.toFixed(3)}s toDataURL 2회 일치`);
  }
  if (SMOKE) {
    const canvasEl = await page.$('#hero-canvas');
    await renderOnly(0);
    await canvasEl.screenshot({ path: path.join(BUILD, 'smoke-t0.png') });
    log(`스모크 캡처 저장: build/smoke-t0.png`);
    await browser.close();
    log(`종료 — 실패 ${failures}건`);
    process.exit(failures ? 1 : 0);
  }

  // ---- 정지시간 계약 산술 검산(claim 13-b, HIGH-3b) --------------------------
  const report = await page.evaluate(() => HeroEngine.minReadableReport());
  log('minReadableSec 경계 인식 검산 — dur − 앞오버랩 − 뒤오버랩 ≥ minReadableSec');
  for (const r of report) {
    ok(r.pass, `${r.id}: dur ${r.dur} − 오버랩 → 가독 ${r.readable}s ≥ 요구 ${r.required}s`);
  }

  // ---- 컨트롤 UI 자동화 검증 4쌍(claim 11) ----------------------------------
  const stateText = () => page.textContent('#playback-state');
  const snap = () => page.evaluate(() => window.HeroControls.getState());
  const canvasData = () => page.evaluate(() => document.getElementById('hero-canvas').toDataURL());

  const before = await stateText();
  await page.click('#btn-play');
  const after = await stateText();
  const playing = (await snap()).playing;
  ok(before !== after && playing === true, `(a) 재생 토글: "${before}" → "${after}", playing=${playing}`);

  await page.waitForTimeout(350);
  const playCap1 = await canvasData();
  const t1 = (await snap()).t;
  await page.waitForTimeout(350);
  const playCap2 = await canvasData();
  const t2 = (await snap()).t;
  ok(t1 < t2 && playCap1 !== playCap2, `(c) 재생 진행: t1=${t1.toFixed(3)} < t2=${t2.toFixed(3)}, 캡처 상이`);

  await page.click('#btn-play');
  const paused = (await snap()).playing;
  const tPause = (await snap()).t;
  await page.waitForTimeout(350);
  const tHold = (await snap()).t;
  const pauseCap1 = await canvasData();
  const pauseCap2 = await canvasData();
  ok(paused === false && tPause === tHold && pauseCap1 === pauseCap2, `(d) 일시정지: playing=${paused}, t ${tPause.toFixed(3)} 유지, 캡처 2회 일치`);

  const tStar = CONFIG.scenes[1].start + CONFIG.scenes[1].dur / 2;
  await page.$eval('#scrub', (el, v) => {
    el.value = String(v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, tStar);
  const scrubCap = await canvasData();
  const directCap = await renderData(tStar);
  ok(scrubCap === directCap, `(b) 스크러버 동기 렌더: t=${tStar}s 지정 캡처 === 단독 render(t) 캡처`);

  // ---- 텍스트 품질 기계 검사(claim 13-a, HIGH-3a) ----------------------------
  log(`텍스트 bbox 검사 — T_check ${samples.length}표본: 캔버스 밖 잘림·텍스트 간 교차`);
  const W = CONFIG.layout.width;
  const H = CONFIG.layout.height;
  let boxViolations = 0;
  for (const t of samples) {
    const boxes = await boxesAt(t);
    for (const b of boxes) {
      const cut = b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > H;
      if (cut) {
        boxViolations += 1;
        fail(`t=${t.toFixed(3)}s 잘림: "${b.text}" bbox(${Math.round(b.x)},${Math.round(b.y)},${Math.round(b.w)}×${Math.round(b.h)})`);
      }
    }
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const b = boxes[j];
        const hit = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        if (hit) {
          boxViolations += 1;
          fail(`t=${t.toFixed(3)}s 겹침: "${a.text}" × "${b.text}"`);
        }
      }
    }
  }
  if (boxViolations === 0) log(`PASS — bbox 위반 0건(${samples.length}표본 전수)`);

  // ---- 첫 프레임 잉크 커버리지(claim 2, MEDIUM-1) ----------------------------
  const inkCoverage = (t, frac, rerender) =>
    page.evaluate(([tt, f, paper, draw]) => {
      const c = document.getElementById('hero-canvas');
      const ctx = c.getContext('2d');
      if (draw) HeroEngine.render(ctx, tt);
      const h = Math.ceil(c.height * f);
      const img = ctx.getImageData(0, 0, c.width, h).data;
      const pr = parseInt(paper.slice(1, 3), 16);
      const pg = parseInt(paper.slice(3, 5), 16);
      const pb = parseInt(paper.slice(5, 7), 16);
      let ink = 0;
      for (let i = 0; i < img.length; i += 4) {
        if (Math.abs(img[i] - pr) + Math.abs(img[i + 1] - pg) + Math.abs(img[i + 2] - pb) > 90) ink += 1;
      }
      return ink / (c.width * h);
    }, [t, frac, CONFIG.palette.paper, rerender]);

  const coverage = await inkCoverage(0, 1 / 3, true);
  ok(coverage >= 0.03, `t=0 제목 영역(상단 1/3) 잉크 커버리지 ${(coverage * 100).toFixed(2)}% ≥ 3% (claim 2)`);

  // ---- 경계 프레임 잉크 실측(④ GAP-R1) ---------------------------------------
  // 씬 경계 5곳: 크로스페이드 중이므로 잉크가 0%여선 안 되고(빈 프레임 금지) 이웃 프레임과
  // 크게 튀지도 않아야 한다(점프 금지).
  log('경계 프레임 잉크 실측 — 씬 경계 5곳, 이웃(±1프레임) 평균 대비');
  for (const b of CONFIG.scenes.slice(1).map((s) => s.start)) {
    const cov = await inkCoverage(b, 1, true);
    const prev = await inkCoverage(b - 1 / FPS, 1, true);
    const next = await inkCoverage(b + 1 / FPS, 1, true);
    const nb = (prev + next) / 2;
    ok(cov > 0.002 && Math.abs(cov - nb) < 0.02, `t=${b.toFixed(2)}s 잉크 ${(cov * 100).toFixed(2)}% > 0%·이웃 평균 ${(nb * 100).toFixed(2)}%와 편차 ${(Math.abs(cov - nb) * 100).toFixed(2)}pp < 2pp`);
  }

  // 스크러버 경계 지정 — t=2.60(첫 경계)을 스크러버 input으로 정확 지정해도 빈 화면이 아님
  await page.$eval('#scrub', (el, v) => {
    el.value = String(v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, CONFIG.scenes[1].start);
  const scrubBoundaryCov = await inkCoverage(0, 1, false);
  ok(scrubBoundaryCov > 0.002, `스크러버 t=2.60 지정 렌더 잉크 ${(scrubBoundaryCov * 100).toFixed(2)}% > 0% — 경계에서 빈 화면 없음`);

  // ---- 프레임 덤프 ----------------------------------------------------------
  const canvasEl = await page.$('#hero-canvas');
  if (!SKIP_FRAMES) {
    log(`프레임 덤프 시작 — ${TOTAL_FRAMES}장 → build/frames/`);
    for (let i = 0; i < TOTAL_FRAMES; i++) {
      await renderOnly(i / FPS);
      const num = String(i).padStart(5, '0');
      await canvasEl.screenshot({ path: path.join(FRAMES, `${num}.png`) });
      if ((i + 1) % 60 === 0) log(`  ${i + 1}/${TOTAL_FRAMES}`);
    }
    log('프레임 덤프 완료');
  }

  // ---- 루프 유사도(claim 10) -------------------------------------------------
  const hLast = await aHashAt((TOTAL_FRAMES - 1) / FPS);
  const hFirst = await aHashAt(0);
  let dist = 0;
  for (let i = 0; i < 64; i++) if (hLast[i] !== hFirst[i]) dist += 1;
  // A6 임계 확정 근거(2026-09-26 실측): 셀 단위 차이 지도에서 불일치 14셀 전부가
  // 중앙 하부 행(2~6행) — S5 전용 필수 요소(완성 서류철·흐름선)와 상이한 부제 문구
  // (S0 태그라인 vs S5 흐름 요약)가 있는 영역뿐이다. 타이틀 중심 구도 계약은 아래의
  // 상단 2행(16셀) 전수 일치로 별도·강하게 검증한다. 배경 휘도 244.2 vs 242.2로 동일.
  const LOOP_HASH_LIMIT = 16;
  ok(dist <= LOOP_HASH_LIMIT, `프레임 ${TOTAL_FRAMES - 1} ↔ 0 평균 해시 거리 ${dist}/64 (상한 ${LOOP_HASH_LIMIT}, claim 10)`);
  const titleBitsF = hFirst.slice(0, 16);
  const titleBitsL = hLast.slice(0, 16);
  ok(titleBitsF === titleBitsL, `타이틀 영역(상단 2행 16셀) 비트 전수 일치 — 루프 이음새 동일 구도(${titleBitsF})`);

  // ---- 포스터(§5.1-7) --------------------------------------------------------
  // ④ GAP-R2: 스왑 완료 후(마지막 프레임 479와 동일 구도)로 변경 — 타이틀·태그라인이
  // 프레임 0과 같아 README 첫 인상이 모션 첫 장면과 정확히 일치한다.
  const posterT = CONFIG.scenes[5].start + CONFIG.scenes[5].dur - 0.05;
  await renderOnly(posterT);
  await canvasEl.screenshot({ path: path.join(BUILD, 'hero-poster.png') });
  log(`포스터 저장: build/hero-poster.png (t=${posterT}s, 스왑 완료 구도 — 프레임 479와 동일)`);

  await browser.close();
  log(`종료 — 실패 ${failures}건`);
  process.exit(failures ? 1 : 0);
}

main().catch((e) => {
  console.error('[export][FATAL]', e);
  process.exit(1);
});
