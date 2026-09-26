// hero-motion 설정 — 문구·색·시간·수치의 단일 출처.
// 렌더·씬·컨트롤·내보내기 코드는 이 파일의 상수만 읽는다(문구 변경은 여기 한 곳).
// 브라우저(classic script 전역)와 node 도구(new Function 평가) 양쪽에서 평가 가능해야 하므로
// window·document 참조를 넣지 않는다.
const HERO_CONFIG = Object.freeze({
  meta: {
    title: 'Effort Router',
    tagline: '작업 규모에 맞는 모델과 에포트를 배정한다',
    pageTitle: 'Effort Router — 히어로 모션',
    canvasLabel:
      'Effort Router 제품 소개 모션 — 한 장의 과업 카드가 티어 판정과 단계별 역할을 거쳐 증거와 함께 완결되는 장면',
    loopSeconds: 24.0,
  },

  // 절제 4색 계약 — 이 외 색은 사용하지 않고, 변형은 알파 합성으로만 만든다.
  palette: {
    paper: '#FAF7F0',
    ink: '#26241F',
    accent: '#D96C47',
    accent2: '#3E6B4F',
  },

  type: {
    fontFamily: "'Gaegu', 'Nanum Gothic Coding', sans-serif",
    codeFamily: "'Nanum Gothic Coding', 'Gaegu', monospace",
    titlePx: 150,    // 제품명(효과 S0·S5) 전용
    headlinePx: 88,  // 장면 헤드라인
    bodyPx: 52,      // 장면 본문·라벨
    minBodyPx: 48,   // 본문 최소 계약(1920 기준)
    lineHeight: 1.4,
  },

  layout: {
    width: 1920,
    height: 1080,
    marginX: 120,
    titleY: 228,     // 제품명 베이스라인
    headlineY: 152,  // 장면 헤드라인 베이스라인
    bodyY: 272,      // 장면 본문 베이스라인
    titleSubY: 336,  // S0·S5 부제 베이스라인
    floorY: 830,     // S1 바닥선
  },

  // §2.2 장면표 — start/dur 합계는 loopSeconds와 정확히 일치해야 한다.
  // headline·body는 문구 원문이며, 화면 배치(큰 글씨/작은 글씨)는 slot 값으로만 나눈다.
  // params의 시간 값은 모두 "장면 시작부터의 초"(local seconds)다.
  scenes: [
    {
      id: 'S0', visual: 'title', start: 0.0, dur: 2.6, minReadableSec: 2.0,
      headline: 'Effort Router',
      body: '작업 규모에 맞는 모델과 에포트를 배정한다',
      params: { slot: 'title' },
    },
    {
      id: 'S1', visual: 'hammers', start: 2.6, dur: 3.6, minReadableSec: 2.0,
      headline: '하나의 에포트로 전부 처리하면 —',
      body: '단순한 일엔 과투자, 큰 일엔 과소검증',
      params: {
        floorY: 830,
        cards: [
          { x: 400, w: 220, h: 150, label: '오타 수정' },
          { x: 950, w: 310, h: 215, label: '작은 버그' },
          { x: 1490, w: 450, h: 310, label: '대형 리팩터링 XL', hero: true },
        ],
        labelY: 960,
        hammer: {
          size: 210,          // 세 망치는 전부 같은 크기(같은 에포트의 은유)
          pivotY: 470,
          restAngle: -0.62,
          hitAngle: 0.62,
          times: [0.5, 1.08, 1.66],  // 카드별 타격 시작(장면 내 초)
          swingDur: 0.3,
        },
        heroMove: { start: 2.3, end: 3.1, toX: 960 },   // 주인공 카드가 중앙으로
        othersFall: { start: 1.87, dur: 0.94 },         // 나머지 두 장은 아래로 떨어짐
        trail: { start: 3.1, to: { x: -140, y: 760 } }, // S2 게이트(왼쪽)로 이어지는 점선
      },
    },
    {
      id: 'S2', visual: 'gate', start: 6.2, dur: 3.6, minReadableSec: 2.0,
      headline: '규모·위험도를 보고',
      body: 'S / M / L / XL 로 판정한다',
      params: {
        gate: { cx: 360, halfW: 265, floorY: 830, topY: 305 },
        badge: { x: 980, y: 880, label: 'jev', w: 150, h: 78 },
        badgeAt: 1.96,
        card: { w: 450, h: 310, from: { x: 960, y: 675 }, slot: { x: 360, y: 675 }, enterEnd: 1.08 },
        stamp: { label: 'XL', dropAt: 1.66, dropDur: 0.3, px: 120 },
        exit: { start: 2.66, dur: 0.79, to: { x: -320, y: 820 } },
        trail: { start: 2.59, to: { x: -140, y: 760 } },
      },
    },
    {
      id: 'S3', visual: 'rail', start: 9.8, dur: 5.6, minReadableSec: 2.0,
      headline: '단계마다 다른 모델과 역할 —',
      body: '계획 → 적대 검토 → 구현 → 리뷰',
      params: {
        rail: { y: 730, x1: 130, x2: 1790 },
        stations: [
          { x: 250, label: '계획', pen: 'accent2' },
          { x: 760, label: '적대 검토', pen: 'ink' },
          { x: 1270, label: '구현', pen: 'accent' },
          { x: 1730, label: '리뷰', pen: 'accent2' },
        ],
        labelY: 922,
        card: { w: 450, h: 310, enterEnd: 0.55 },
        cardCy: 575,   // 카드 바닥이 레일에 닿는 위치의 중심 y
        dwell: 0.3,    // 정거장 도착 후 머무는 시간(초)
        arrivals: [0.9, 1.95, 3.0, 4.05],  // 정거장 도착 시점(장면 내 초)
        checkOffsets: [[-112, -88], [112, -88], [-112, 52], [112, 52]],
        exit: { start: 4.55, tilt: 0.1, toX: 2080 },
      },
    },
    {
      id: 'S4', visual: 'folder', start: 15.4, dur: 4.2, minReadableSec: 2.0,
      headline: '단계 사이는',
      body: 'state.json과 증거번들로 인계된다',
      params: {
        folder: { cx: 520, cy: 670, w: 540, h: 400, label: 'state.json' },
        settle: { dur: 0.4 },
        slips: {
          cx: 1420, w: 660, h: 158, gapY: 190, y0: 470, popDur: 0.45,
          times: [0.55, 1.35, 2.15],
          rows: ['티어 판정 - XL', '계획·검토 - 합의 완료', '구현·리뷰 - 증거 13건'],
        },
        centerMove: { start: 2.9, end: 3.8, dx: 90 },  // 그룹이 중앙으로 미끄러짐
      },
    },
    {
      id: 'S5', visual: 'complete', start: 19.6, dur: 4.4, minReadableSec: 2.0,
      headline: 'Effort Router',
      // S3 정거장 어휘와 통일한 여정 요약(GAP-2 — 구 화구의 "검증·실행·학습"은 S2~S4 어휘와 불일치)
      body: '티어 판정 → 계획 → 검토 → 구현 → 리뷰 — 다음 과업으로',
      params: {
        slot: 'title',   // S0과 동일 구도(타이틀 중심·부제 슬롯) — 루프 이음새 계약
        folder: { cx: 960, cy: 664, w: 480, h: 340, label: 'state.json' },
        flow: { y: 900, x1: 330, x2: 1590, nodes: 5, drawEnd: 1.2 },  // 1.2초에 완성
        settle: { dur: 0.36 },  // 폴더가 제자리에 앉는 미세 이동
        // 루프 이음새 계약(GAP-1): 요약줄 온전 가독(local 0.2→3.0 = 2.8s ≥ minReadableSec 2.0)
        // 후 마지막 구간에 S5 전용 요소를 페이드아웃하고 부제를 S0 태그라인으로 교체 —
        // 프레임 479(local 4.35) = 타이틀+밑줄+태그라인 = 프레임 0과 실질 동일 구도.
        // fadeDur·taglineFadeDur는 프레임 479 이전(local 4.3)에 완료되어 잔상 없이 수렴한다.
        hold: { dur: 3.0, fadeDur: 1.3, summaryFadeDur: 0.7, taglineFadeDur: 0.6, taglineSwapAt: 3.7 },
      },
    },
  ],

  motion: {
    overlap: 0.4,      // 인접 씬 사이 5개 경계에만 존재하는 크로스페이드
    jitterAmpPx: 1.5,  // 손그림 선 지터 진폭
    strokeSegPx: 26,   // 손그림 선분 분할 길이
    lineWidth: 5,      // 기본 선 굵기
    seed: 20260926,
    easings: { enter: 'easeOutCubic', move: 'easeInOutCubic', stamp: 'easeOutBack' },
  },

  export: {
    fps: 20,       // GIF 10ms 양자 정합(50ms). 하강 사다리: 12.5 → 10
    width: 1920,
    height: 1080,
    gifWidth: 960,
  },
});
