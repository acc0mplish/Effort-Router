// 장면 드로잉 — S0(타이틀)·S1(망치)·S2(판정 게이트).
// 모든 좌표·수치는 js/config.js의 상수만 읽고, 그리기는 HeroEngine 헬퍼만 사용한다.
// 텍스트는 항상 시각 요소보다 나중에 그려 최상단에 놓인다.
const HeroScenes = {};

// 장면 공통 문구 슬롯 — title 슬롯(S0·S5)과 headline 슬롯(S1~S4)만 있다.
// opts.bodyAlpha는 S5의 루프 이음새 스왑(요약줄 페이드아웃)에서만 1 미만이 된다.
function heroSceneText(ctx, scene, opts = {}) {
  const E = HeroEngine;
  const L = HERO_CONFIG.layout;
  const T = HERO_CONFIG.type;
  const isTitle = scene.params.slot === 'title';
  const title = E.text(ctx, {
    text: scene.headline,
    x: L.width / 2,
    y: isTitle ? L.titleY : L.headlineY,
    px: isTitle ? T.titlePx : T.headlinePx,
    weight: 700,
  });
  const body = E.text(ctx, {
    text: scene.body,
    x: L.width / 2,
    y: isTitle ? L.titleSubY : L.bodyY,
    px: T.bodyPx,
    alpha: opts.bodyAlpha,
  });
  return { title, body };
}

// 주인공 카드 — 같은 카드가 S1~S3에서 살아남으며 이동한다(장면 간 연속성 매개체).
function heroCard(ctx, cx, cy, w, h, opts = {}) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const x0 = cx - w / 2;
  const y0 = cy - h / 2;
  E.rect(ctx, x0, y0, w, h, {
    key: opts.key || 'card',
    width: opts.width || 5,
    color: opts.color || P.ink,
    fill: P.paper,
    fillAlpha: opts.alpha,
    alpha: opts.alpha,
  });
  const k = opts.key || 'card';
  E.line(ctx, x0 + w - 56, y0, x0 + w, y0 + 56, { key: `${k}:fold`, width: 3.5, color: E.withAlpha(P.ink, 0.6), alpha: opts.alpha });
  E.line(ctx, x0 + w - 56, y0, x0 + w - 56, y0 + 56, { key: `${k}:fold2`, width: 3.5, color: E.withAlpha(P.ink, 0.4), alpha: opts.alpha });
}

// ---- S0 타이틀 -----------------------------------------------------------

HeroScenes.title = function drawTitleScene(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const boxes = heroSceneText(ctx, scene);
  // 크로스페이드 텍스트 스왑 중에는 문구가 안 보일 수 있다(textAlpha 0) — 그때 장식도 생략.
  const u = boxes.title;
  if (u) {
    const uy = u.y + u.h + 18;
    E.line(ctx, u.x + 6, uy, u.x + u.w - 6, uy, {
      key: `${scene.id}-underline`,
      width: 18,
      color: E.withAlpha(P.accent, 0.3),
    });
    // 연필이 제목 스트로크를 살짝 다시 그리는 미세 모션 — S0에서만 진행
    if (scene.id === 'S0') {
      const prog = E.ease('easeInOutCubic', local.p);
      E.line(ctx, u.x + 6, uy + 3, u.x + 6 + (u.w - 12) * prog, uy + 3, {
        key: `${scene.id}-pencil`,
        width: 3.5,
        color: E.withAlpha(P.ink, 0.5),
      });
    }
  }
};

// ---- S1 망치 -------------------------------------------------------------

// 세 망치는 전부 같은 크기 — 단순한 일엔 크고, 큰 일엔 작게 보이는 것이 핵심 연출.
function drawHammer(ctx, pr, cx, cardTopY, i, t) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const hm = pr.hammer;
  const hitT = hm.times[i];
  let angle;
  if (t < hitT) {
    angle = hm.restAngle;
  } else if (t < hitT + hm.swingDur) {
    angle = E.lerp(hm.restAngle, hm.hitAngle, E.ease('easeOutCubic', (t - hitT) / hm.swingDur));
  } else {
    angle = E.lerp(hm.hitAngle, hm.restAngle, E.ease('easeInOutCubic', E.clamp01((t - hitT - hm.swingDur) / 0.55)));
  }
  E.withTransform(ctx, cx, hm.pivotY, 1, angle, () => {
    E.line(ctx, 0, 0, 0, hm.size, { key: `s1-hammer-handle-${i}`, width: 9, color: P.ink });
    E.rect(ctx, -86, hm.size, 172, 96, { key: `s1-hammer-head-${i}`, width: 6, color: P.ink, fill: P.paper });
  });
  // 타격 임팩트 별 — 맞은 자리에서 잠깐 퍼지는 짧은 선 3개
  const hitDone = hitT + hm.swingDur * 0.75;
  const starP = (t - hitDone) / 0.45;
  if (starP > 0 && starP < 1) {
    for (let k = 0; k < 3; k++) {
      const ang = -Math.PI / 2 + (k - 1) * 0.6;
      const reach = 26 + 34 * (1 - starP);
      E.line(ctx, cx + Math.cos(ang) * 26, cardTopY + Math.sin(ang) * 26, cx + Math.cos(ang) * reach, cardTopY + Math.sin(ang) * reach, {
        key: `s1-star-${i}-${k}`,
        width: 4,
        color: P.accent,
        alpha: 1 - starP,
      });
    }
  }
}

HeroScenes.hammers = function drawHammers(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const pr = scene.params;
  const L = HERO_CONFIG.layout;
  E.line(ctx, L.marginX + 40, pr.floorY, L.width - L.marginX - 40, pr.floorY, {
    key: 's1-floor',
    color: E.withAlpha(P.ink, 0.7),
    width: 5,
  });
  pr.cards.forEach((card, i) => {
    const isHero = !!card.hero;
    const fall = isHero ? 0 : E.easeAt('easeInOutCubic', local.t, pr.othersFall.start, pr.othersFall.dur);
    const move = isHero ? E.easeAt('easeInOutCubic', local.t, pr.heroMove.start, pr.heroMove.end - pr.heroMove.start) : 0;
    const cx = isHero ? E.lerp(card.x, pr.heroMove.toX, move) : card.x;
    const cy = pr.floorY - card.h / 2 + fall * 620;
    const alpha = 1 - fall;
    drawHammer(ctx, pr, card.x, cy - card.h / 2, i, local.t);
    heroCard(ctx, cx, cy, card.w, card.h, { key: `s1-card-${i}`, color: isHero ? P.accent : P.ink, width: isHero ? 6 : 5, alpha });
    // 라벨은 제자리에서 사라지고 카드 모양만 낙하한다(텍스트 잘림 계약)
    E.text(ctx, { text: card.label, x: cx, y: pr.labelY, px: HERO_CONFIG.type.minBodyPx + 4, alpha: 1 - E.clamp01(fall / 0.7) });
  });
  // 주인공 카드가 S2 게이트(왼쪽)로 향하는 길이가 자라는 점선
  const tp = E.clamp01((local.t - pr.trail.start) / (scene.dur - pr.trail.start));
  if (tp > 0) {
    E.dashTrail(ctx, [{ x: 960, y: 700 }, { x: 480, y: 735 }, pr.trail.to], tp, { key: 's1-trail', color: P.ink, width: 4 });
  }
  heroSceneText(ctx, scene);
};

// ---- S2 판정 게이트 -------------------------------------------------------

HeroScenes.gate = function drawGate(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const pr = scene.params;
  const g = pr.gate;
  // 아치형 게이트 — 기둥 2개와 상단 보, 바닥은 열려 있다
  E.line(ctx, g.cx - g.halfW, g.floorY, g.cx - g.halfW, g.topY, { key: 's2-gate-l', width: 7, color: P.ink });
  E.line(ctx, g.cx + g.halfW, g.floorY, g.cx + g.halfW, g.topY, { key: 's2-gate-r', width: 7, color: P.ink });
  E.line(ctx, g.cx - g.halfW, g.topY, g.cx + g.halfW, g.topY, { key: 's2-gate-top', width: 7, color: P.ink });
  E.line(ctx, g.cx - 34, g.topY - 62, g.cx, g.topY, { key: 's2-gate-hopper-l', width: 5, color: P.ink });
  E.line(ctx, g.cx + 34, g.topY - 62, g.cx, g.topY, { key: 's2-gate-hopper-r', width: 5, color: P.ink });

  // 카드 진입 → 슬롯 통과
  const enter = E.easeAt('easeInOutCubic', local.t, 0, pr.card.enterEnd);
  const exitP = E.easeAt('easeInOutCubic', local.t, pr.exit.start, pr.exit.dur);
  const cardX = E.lerp(E.lerp(pr.card.from.x, pr.card.slot.x, enter), pr.exit.to.x, exitP);
  const cardY = E.lerp(pr.card.slot.y, pr.exit.to.y, exitP);

  // 스탬프 헤드 — 카드 위에서 내려와 XL을 찍는다
  const drop = E.easeAt('easeOutCubic', local.t, pr.stamp.dropAt - 0.18, 0.18);
  const lift = E.easeAt('easeInOutCubic', local.t, pr.stamp.dropAt + pr.stamp.dropDur, 0.4);
  const stampY = E.lerp(g.topY - 40, cardY - pr.card.h / 2 + 10, drop) - lift * 40;
  if (local.t > pr.stamp.dropAt - 0.18 && local.t < pr.exit.start + 0.2) {
    E.withTransform(ctx, g.cx, stampY, 1, 0, () => {
      E.line(ctx, 0, -96, 0, -22, { key: 's2-stamp-handle', width: 8, color: P.ink });
      E.rect(ctx, -62, -22, 124, 46, { key: 's2-stamp-head', width: 6, color: P.ink, fill: P.paper });
    });
  }

  heroCard(ctx, cardX, cardY, pr.card.w, pr.card.h, { key: 's2-card', color: P.accent, width: 6 });

  // 찍힌 XL — 카드와 함께 움직이다가 퇴장 전반에 화면 안에서 사라진다(텍스트 잘림 계약)
  const xlP = E.clamp01((local.t - (pr.stamp.dropAt + pr.stamp.dropDur * 0.6)) / 0.18);
  const xlFade = 1 - E.clamp01((exitP - 0.3) / 0.12);
  if (xlP > 0 && xlFade > 0) {
    E.text(ctx, { text: pr.stamp.label, x: cardX, y: cardY + 44, px: pr.stamp.px, weight: 700, color: P.accent, rotate: -0.1, alpha: xlP * xlFade });
  }

  // 작은 배지 — CONFIG.scenes 배지 라벨, 1회 등장(확대 없음)
  const badgeP = E.clamp01((local.t - pr.badgeAt) / 0.25);
  if (badgeP > 0) {
    E.rect(ctx, pr.badge.x - pr.badge.w / 2, pr.badge.y - pr.badge.h / 2, pr.badge.w, pr.badge.h, {
      key: 's2-badge',
      width: 4,
      color: P.ink,
      fill: P.paper,
      alpha: badgeP,
    });
    E.text(ctx, { text: pr.badge.label, x: pr.badge.x, y: pr.badge.y + 17, px: HERO_CONFIG.type.minBodyPx, code: true, alpha: badgeP });
  }

  // S3 레일로 이어지는 점선 — 카드가 나가기 직전부터 자란다
  const tp = E.clamp01((local.t - pr.trail.start) / (scene.dur - pr.trail.start));
  if (tp > 0) {
    E.dashTrail(ctx, [{ x: pr.card.slot.x, y: 700 }, { x: 80, y: 745 }, pr.trail.to], tp, { key: 's2-trail', color: P.ink, width: 4 });
  }
  heroSceneText(ctx, scene);
};
