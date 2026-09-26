// 단일 파일 두 변형(standalone·cdn)의 로드·렌더 스모크 (node + playwright).
// 사용법: node tools/smoke-variants.mjs [standalone|cdn|둘 다 생략]
// - standalone: 오프라인 컨텍스트(외부 요청 전면 차단)에서 폰트 내장 증명
// - cdn: 온라인 컨텍스트에서 Google Fonts 로드 증명(네트워크 필요)
import { chromium } from 'playwright';
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
// config.js는 classic script(전역 HERO_CONFIG)라 ESM import 불가 — export-frames.mjs와 동일 평가 방식.
const CONFIG = new Function(readFileSync(path.join(ROOT, 'js/config.js'), 'utf8') + '\nreturn HERO_CONFIG;')();
let failures = 0;
const fail = (...a) => { failures++; console.error('FAIL:', ...a); };
const ok = (cond, msg) => console.log((cond ? 'ok  ' : 'FAIL') + ' — ' + msg) || (!cond && fail(msg));

// 잉크 = paper색으로부터의 RGB 편차 합이 90 초과인 픽셀 비율(export-frames.mjs 방식과 동일 기준).
// alpha>0 개수는 배경 paper가 전 캔버스를 채우므로 공허해진다(리뷰 #1).
const inkProbe = (paperHex) => {
  const c = document.getElementById('hero-canvas');
  const ctx = c.getContext('2d');
  HeroEngine.render(ctx, 0);
  const pr = parseInt(paperHex.slice(1, 3), 16), pg = parseInt(paperHex.slice(3, 5), 16), pb = parseInt(paperHex.slice(5, 7), 16);
  const img = ctx.getImageData(0, 0, c.width, c.height).data;
  let ink = 0;
  for (let i = 0; i < img.length; i += 4) {
    if (Math.abs(img[i] - pr) + Math.abs(img[i + 1] - pg) + Math.abs(img[i + 2] - pb) > 90) ink++;
  }
  return ink / (c.width * c.height);
};

async function smokeVariant(browser, file, offline) {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1200 } });
  if (offline) {
    await context.route(/^https?:\/\//, (route) => route.abort());
    await context.setOffline(true);
  }
  const page = await context.newPage();
  page.on('pageerror', (e) => fail(`${file} 페이지 예외:`, e.message));
  page.on('console', (m) => { if (m.type() === 'error') fail(`${file} 콘솔 에러:`, m.text()); });

  await page.goto('file://' + path.join(ROOT, file));
  await page.waitForFunction('window.HERO_READY === true', null, { timeout: 20000 });
  // 기본 체크는 400·라틴 서브셋만 증명한다 — 한국어 글리프('가')와 700을 별도 증명(리뷰 #4).
  const fontChecks = await page.evaluate(() => ({
    w400ko: document.fonts.check('48px Gaegu', '가'),
    w700ko: document.fonts.check('700 48px Gaegu', '가'),
  }));
  ok(fontChecks.w400ko === true, `${file} fonts.check 400 '가' === ${fontChecks.w400ko} (${offline ? '오프라인' : '온라인'})`);
  ok(fontChecks.w700ko === true, `${file} fonts.check 700 '가' === ${fontChecks.w700ko}`);

  const ink = await page.evaluate(inkProbe, CONFIG.palette.paper);
  ok(ink >= 0.01, `${file} t=0 잉크(전 캔버스, paper편차) ${(ink * 100).toFixed(2)}% ≥ 1%`);
  await context.close();
}

const which = process.argv[2] ?? 'both';
const browser = await chromium.launch({ headless: true });
try {
  if (which === 'standalone' || which === 'both') await smokeVariant(browser, 'hero-motion-standalone.html', true);
  if (which === 'cdn' || which === 'both') await smokeVariant(browser, 'hero-motion-cdn.html', false);
} finally {
  await browser.close();
}
console.log(failures ? `\n${failures} failures` : '\nall ok');
process.exit(failures ? 1 : 0);
