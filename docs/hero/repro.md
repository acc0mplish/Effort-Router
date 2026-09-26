# hero-motion 재현 절차 (repro)

외부 의존성 → 설치 → 실행 → 검증 로그 해석 → fps 하강(사다리) 순서다. 새 환경에서 그대로 따라 하면 GIF·포스터가 재현된다. 네트워크는 도구 설치 시에만 필요하며, 페이지 로드·렌더·내보내기는 전부 오프라인(로컬 번들)으로 동작한다.

## 1. 외부 의존성

| 항목 | 요구 | 실측(2026-09-26 개발 환경) |
|------|------|-----------------------------|
| node | v22 이상 | v22.21.0 |
| playwright | **1.63.0 고정** — `docs/hero/tools/package.json`의 정확 핀(`"playwright": "1.63.0"`) | npm 설치 성공 |
| 브라우저 | chromium(headless) | `~/.cache/ms-playwright` 캐시 사용. 없으면 `npx playwright install chromium` |
| python3 + Pillow | GIF 조립 | python3 + Pillow 12.1.0 |
| ffmpeg | 불필요 | **부재 — MP4는 생략된다**(claim 8). 설치되어 있어도 파이프라인은 MP4를 만들지 않으며, build-gif.py가 ffmpeg 존재 여부를 리포트에만 표기 |

주의: 이 환경의 npm은 `package-lock.json` 생성을 거부했다(3회 시도 `--package-lock-only` 포함 실패). 버전 고정은 `package.json`의 정확 핀이 유일한 수단이므로 핀을 변경하지 않는다.

## 2. 설치

```bash
cd docs/hero/tools
npm install          # playwright 1.63.0 격리 설치(저장소 루트 의존성 불변)
npx playwright install chromium   # 캐시에 chromium이 없을 때만 필요
```

## 3. 실행 시퀀스

저장소 루트 기준 기본 경로(`docs/hero/build/`)로 산출되며, 반드시 위 순서대로 실행한다(프레임 덤프 → GIF 조립).

```bash
cd docs/hero/tools
node export-frames.mjs            # 전체 검증 + 480프레임 덤프 + 포스터
python3 build-gif.py              # build/frames → build/hero.gif
```

옵션:

```bash
node export-frames.mjs --smoke         # 최소 동작 확인(렌더 캡처 + 동일 t 2회 해시)
node export-frames.mjs --skip-frames   # 검증만(프레임 덤프 생략 — 개발 반복용)
node export-frames.mjs --fps 12.5      # fps 지정 덤프(§5 사다리에서 사용)
python3 build-gif.py --fps 12.5        # 조립도 같은 fps로
```

## 4. export-frames.mjs 검증 로그 해석

실행 로그에 다음 항목이 순서대로 찍히며, 하나라도 `FAIL`이면 exit 1로 중단된다.

| 로그 항목 | 의미 |
|-----------|------|
| `document.fonts.check('48px Gaegu') === true` | 번들 폰트가 http(s) 차단+오프라인 컨텍스트에서 활성화됨(네트워크 불필요 증명) |
| `결정론 검증 — T_check 11표본` | 씬 중간점 6 + 씬 경계 5(크로스페이드 합성 중간 — 2씬 동시 렌더 경로)에서 동일 t 2회 렌더 `toDataURL` 해시 일치(claim 1) |
| `minReadableSec 경계 인식 검산` | 씬마다 `dur − 앞오버랩 − 뒤오버랩 ≥ minReadableSec` 6줄(claim 13) |
| 컨트롤 4쌍 (a)–(d) | 재생 토글 / 재생 실질 진행 / 일시정지 정지 / 스크러버 동기 렌더 일치(claim 11) |
| `텍스트 bbox 검사` | 캔버스 밖 잘림·텍스트 간 교차 0건(claim 13) |
| `잉크 커버리지` | t=0 제목 영역(상단 1/3) ≥ 3% — 실측 6.09%(claim 2) |
| `프레임 덤프` | 480장 → `build/frames/00000.png…00479.png` |
| `평균 해시 거리` | 프레임 479↔0 루프 유사도 — 현재 실측 **0/64**(상한 16, claim 10) |
| `타이틀 영역 16셀 전수 일치` | 루프 이음새 타이틀 구도 일치 |
| `경계 프레임 잉크 실측` | 씬 경계 5곳(t=2.60·6.20·9.80·15.40·19.60)이 크로스페이드 합성으로 잉크 >0%이며 이웃 프레임 평균과 편차 2pp 미만 — 빈 프레임·점프 없음(④ GAP-R1) |

## 5. build-gif.py 리포트와 크기 초과 시 사다리

리포트는 해상도·총프레임·프레임당 ms·총 재생시간·파일 크기를 찍고 ≤10MB를 판정한다(현재 실측 960×540·480프레임·50ms·24.00초·7,596,082B = 7.24MB PASS).

10MB 초과 시 아래 사다리를 한 단계씩 내려가며 각 단계 실측을 다시 기록한다:

1. **fps 20 → 12.5(80ms) → 10(100ms)** — 모두 GIF 10ms 양자 정수배라 총 재생시간 24.00초 계약이 유지된다.
   - **재덤프 계약(비균일 샘플링 금지)**: `node export-frames.mjs --fps 12.5` → `python3 build-gif.py --fps 12.5`. build-gif.py가 기존 480장 프레임에서 일부만 골라 쓰는 것은 금지이며, 프레임 수(24.0s × fps)가 맞지 않으면 실패시킨다.
2. 그래도 초과면 폭 960 → 800: `python3 build-gif.py --gif-width 800`(재덤프 불필요).
3. 그 다음은 팔레트 256 → 128(`build-gif.py` 내부 상수 수정 후 재조립).
4. 15MB를 넘으면 계획 변경으로 보고한다.

## 6. 폰트

- Gaegu Regular·Bold TTF를 `docs/hero/assets/fonts/`에 번들(@font-face 상대경로) — 렌더·내보내기에 네트워크가 불필요하다.
- 라이선스 OFL — `docs/hero/assets/fonts/OFL.txt` 동봉.
- 폴백 체인: Gaegu → Nanum Gothic Coding → sans-serif. 폰트 미탑재 환경에서도 레이아웃은 유지되지만 산출 품질을 위해 번들 폰트를 제거하지 않는다.

## 7. 산출물 위치

| 산출물 | 경로 | git |
|--------|------|-----|
| 편집 가능 원본 | `docs/hero/hero-motion.html`(+js/css) | 추적 |
| 단일 파일 standalone(**납품 본체**) | `docs/hero/hero-motion-standalone.html` | 추적 |
| CDN 폰트판(보조 — 네트워크 필요) | `docs/hero/hero-motion-cdn.html` | 추적 |
| 폰트 확보 자산 | `docs/hero/fonts.css`·`docs/hero/woff2/` | `.gitignore` 제외 |
| GIF | `docs/hero/build/hero.gif` | 추적 |
| 포스터 | `docs/hero/build/hero-poster.png` | 추적 |
| 중간 프레임 | `docs/hero/build/frames/` | `.gitignore` 제외 |
| 도구 의존성 | `docs/hero/tools/node_modules/` | `.gitignore` 제외 |

## 단일 파일 standalone (hero-motion-standalone.html)

- 생성 산출물이다 — 직접 편집 금지. 원본 수정(문구·색·타이밍) 후 아래로 재생성한다.
- 폰트 소스(1회 확보): Google Fonts css2(Gaegu 400·700)의 woff2 서브셋 전체를 base64로 내장한다(오프라인 완전 자립, 외부 참조 0).

```bash
# 1) woff2 확보 (fonts.css의 URL 전부 다운로드, 한 폴더에 — 178파일 검산까지)
curl -sf -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0" \
  "https://fonts.googleapis.com/css2?family=Gaegu:wght@400;700&display=swap" -o fonts.css
mkdir -p woff2 && grep -oE "https://fonts.gstatic.com/[^)]+\.woff2" fonts.css | sort -u |
  while read -r u; do curl -sf "$u" -o "woff2/$(basename "$u")"; done
[ "$(ls woff2 | wc -l)" -eq 178 ] || { echo "woff2 178파일 아님"; exit 1; }
# 2) 생성 (TTF 블록·앵커 미매치 시 빌더가 즉시 실패한다)
python3 tools/build-standalone.py fonts.css woff2
```

- 실측(2026-09-26 재생성): **2,917,938B**·내장 @font-face **178블록(400·700 각 89서브셋, 중복 0)**·외부 참조 0.
  오프라인 로드 검증(smoke-variants.mjs) — `fonts.check('48px Gaegu','가')`·`fonts.check('700 48px Gaegu','가')`
  모두 true·t=0 잉크(paper 편차) ≥1%. 컨트롤 상호작용 검증은 export-frames.mjs 소관.
  초기 빌드(5,789,710B·356블록)는 빌더가 css2 전체 세트를 TTF @font-face 매치마다 재삽입한 중복 버그였다(2026-09-26 수정).

## CDN 폰트판 (hero-motion-cdn.html)

- 동일 단일 파일이되 폰트만 Google Fonts css2 링크로 로드한다 — 파일 46,401B(45KB), 열람 시 네트워크 필수.
- 생성: `python3 tools/build-cdn.py` (인자 없음, fonts.css·woff2 불필요)

## 변형 스모크 (tools/smoke-variants.mjs)

```bash
cd docs/hero/tools && node smoke-variants.mjs both   # standalone=오프라인 차단, cdn=온라인
```

두 변형 모두 `HERO_READY`·`fonts.check('48px Gaegu','가')`·`fonts.check('700 48px Gaegu','가')`·t=0 잉크(paper 편차) ≥1%·콘솔 에러 0을 확인한다.
