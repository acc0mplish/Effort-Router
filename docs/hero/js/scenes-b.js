// 장면 드로잉 후반 — S3(레일)·S4(서류철)·S5(완결·루프).
// scenes.js에서 650줄 경고 도달에 대비해 S3~S5를 이 파일로 분리한다(계획 §3.5).

// ---- S3 레일 -------------------------------------------------------------

// 카드 x 좌표: 진입 → 정거장별 정지·이동 → 퇴장(오른쪽 미끄러짐)
function railCardX(pr, t, dur) {
  const E = HeroEngine;
  const st = pr.stations;
  const a = pr.arrivals;
  if (t < pr.card.enterEnd) return E.lerp(-320, st[0].x, E.ease('easeInOutCubic', t / pr.card.enterEnd));
  for (let i = 0; i < st.length - 1; i++) {
    const leaveT = a[i] + pr.dwell;
    if (t < leaveT) return st[i].x;
    if (t < a[i + 1]) return E.lerp(st[i].x, st[i + 1].x, E.ease('easeInOutCubic', (t - leaveT) / (a[i + 1] - leaveT)));
  }
  if (t < pr.exit.start) return st[st.length - 1].x;
  return E.lerp(st[st.length - 1].x, pr.exit.toX, E.ease('easeInOutCubic', (t - pr.exit.start) / (dur - pr.exit.start)));
}

// 정거장마다 색이 다른 펜·스탬프가 내려와 체크 도장을 찍는다
function stampGarnish(ctx, pr, st, i, t) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const a = pr.arrivals[i];
  const dropT = a - 0.16;
  if (t < dropT || t > a + 0.5) return;
  const drop = E.easeAt('easeOutCubic', t, dropT, 0.16);
  const lift = E.easeAt('easeInOutCubic', t, a + 0.08, 0.4);
  const sy = E.lerp(pr.rail.y - 420, pr.cardCy - pr.card.h / 2 + 6, drop) - lift * 46;
  E.withTransform(ctx, st.x, sy, 1, 0, () => {
    E.line(ctx, 0, -70, 0, -18, { key: `s3-stamp-handle-${i}`, width: 7, color: P.ink });
    E.rect(ctx, -52, -18, 104, 38, { key: `s3-stamp-head-${i}`, width: 5, color: P.ink, fill: P.paper });
  });
}

HeroScenes.rail = function drawRail(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const pr = scene.params;
  const T = HERO_CONFIG.type;
  E.line(ctx, pr.rail.x1, pr.rail.y, pr.rail.x2, pr.rail.y, { key: 's3-rail', color: E.withAlpha(P.ink, 0.75), width: 6 });
  pr.stations.forEach((st, i) => {
    stampGarnish(ctx, pr, st, i, local.t);
    E.circle(ctx, st.x, pr.rail.y, 16, { key: `s3-st-${i}`, width: 5, color: P.ink, fill: P.paper });
    E.text(ctx, { text: st.label, x: st.x, y: pr.labelY, px: T.minBodyPx + 6 });
  });

  const cx = railCardX(pr, local.t, scene.dur);
  const exitP = E.easeAt('easeInOutCubic', local.t, pr.exit.start, scene.dur - pr.exit.start);
  E.withTransform(ctx, cx, pr.cardCy, 1, exitP * pr.exit.tilt, () => {
    heroCard(ctx, 0, 0, pr.card.w, pr.card.h, { key: 's3-card', color: P.accent, width: 6 });
  });

  // 도장 누적 — 정거장마다 그 펜 색의 체크가 카드에 남는다
  pr.stations.forEach((st, i) => {
    const pop = E.easeAt('easeOutBack', local.t, pr.arrivals[i] + 0.08, 0.3);
    if (pop <= 0) return;
    const [ox, oy] = pr.checkOffsets[i];
    E.withTransform(ctx, cx + ox, pr.cardCy + oy, 0.6 + 0.4 * pop, 0, () => {
      E.check(ctx, 0, 0, 64, { key: `s3-chk-${i}`, width: 7, color: P[st.pen] });
    });
  });

  // 카드가 지나간 만큼 길어지는 점선 궤적(레일 아래 평행선)
  const tp = E.clamp01((cx - pr.rail.x1) / (pr.rail.x2 - pr.rail.x1));
  if (tp > 0) {
    E.dashTrail(ctx, [{ x: pr.rail.x1, y: pr.rail.y + 30 }, { x: pr.rail.x2, y: pr.rail.y + 30 }], tp, {
      key: 's3-trail',
      color: P.accent,
      width: 3.5,
      on: 13,
      off: 11,
    });
  }
  heroSceneText(ctx, scene);
};

// ---- 서류철(S4·S5 공용) ---------------------------------------------------

// 폴더 본체 스트로크 + 완료 체크. 라벨 텍스트는 bbox 정합을 위해 변형 밖 folderLabel로 그린다.
function heroFolder(ctx, E, P, f, opts = {}) {
  const x0 = f.cx - f.w / 2;
  const y0 = f.cy - f.h / 2 + (opts.settleDy || 0);
  const alpha = opts.alpha;
  // 탭(위쪽 귀퉁이)
  E.rect(ctx, x0 + 36, y0 - 40, 190, 44, { key: `${opts.key}:tab`, width: 5, color: P.ink, fill: P.paper, fillAlpha: alpha, alpha });
  E.rect(ctx, x0, y0, f.w, f.h, { key: `${opts.key}:body`, width: 6, color: P.ink, fill: P.paper, fillAlpha: alpha, alpha });
  E.line(ctx, x0 + 14, y0 + 74, x0 + f.w - 14, y0 + 74, { key: `${opts.key}:fold`, width: 3.5, color: E.withAlpha(P.ink, 0.45), alpha });
  if (opts.checked) {
    E.check(ctx, f.cx + 130, f.cy + 74, 56, { key: `${opts.key}:chk`, width: 7, color: P.accent2, alpha });
  }
}

// state.json 라벨 — 항상 월드 좌표(변형 없는 컨텍스트)에서 그린다.
function folderLabel(ctx, E, f, opts = {}) {
  E.text(ctx, { text: f.label, x: f.cx, y: f.cy + 92 + (opts.settleDy || 0), px: HERO_CONFIG.type.minBodyPx, code: true, alpha: opts.alpha });
}

// ---- S4 서류철·영수증 -----------------------------------------------------

HeroScenes.folder = function drawFolder(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const pr = scene.params;
  const T = HERO_CONFIG.type;
  // 그룹이 화면 중앙으로 미끄러진다 — 텍스트 bbox 정합을 위해 ctx 이동 대신 x에 더한다
  const dx = E.lerp(pr.centerMove.dx, 0, E.easeAt('easeInOutCubic', local.t, pr.centerMove.start, pr.centerMove.end - pr.centerMove.start));
  const pop = E.easeAt('easeOutBack', local.t, 0, pr.settle.dur);
  E.withTransform(ctx, pr.folder.cx, pr.folder.cy, 0.94 + 0.06 * pop, 0, () => {
    heroFolder(ctx, E, P, { ...pr.folder, cx: 0, cy: 0 }, { key: 's4-folder' });
  });
  folderLabel(ctx, E, pr.folder, { alpha: E.clamp01(local.t / 0.3) });

  pr.slips.rows.forEach((row, i) => {
    const t0 = pr.slips.times[i];
    const popP = E.easeAt('easeOutBack', local.t, t0, pr.slips.popDur);
    if (popP <= 0) return;
    const sy = pr.slips.y0 + i * pr.slips.gapY;
    const sx = pr.slips.cx + dx;
    const tilt = (i % 2 === 0 ? -1 : 1) * 0.022;
    E.withTransform(ctx, sx, sy, 0.6 + 0.4 * popP, tilt, () => {
      E.rect(ctx, -pr.slips.w / 2, -pr.slips.h / 2, pr.slips.w, pr.slips.h, {
        key: `s4-slip-${i}`,
        width: 4,
        color: P.ink,
        fill: P.paper,
      });
    });
    E.text(ctx, { text: row, x: sx - pr.slips.w / 2 + 46, y: sy + 17, px: T.minBodyPx + 4, align: 'left', alpha: E.clamp01((local.t - t0) / 0.3) });
    E.check(ctx, sx + pr.slips.w / 2 - 64, sy, 46, { key: `s4-slip-chk-${i}`, width: 6, color: P.accent2, alpha: E.clamp01((local.t - t0 - 0.12) / 0.3) });
  });

  heroSceneText(ctx, scene);
};

// ---- S5 완결·루프 ----------------------------------------------------------

HeroScenes.complete = function drawComplete(ctx, scene, local) {
  const E = HeroEngine;
  const P = HERO_CONFIG.palette;
  const pr = scene.params;
  const L = HERO_CONFIG.layout;
  const T = HERO_CONFIG.type;
  // 루프 이음새 스왑(GAP-1): 요약줄은 온전히 읽힌 뒤(hold.dur) 사라지고,
  // 완전히 사라진 시점(taglineSwapAt)에 S0 태그라인이 같은 슬롯에 등장한다.
  const hold = pr.hold;
  const summaryFade = 1 - E.clamp01((local.t - hold.dur) / hold.summaryFadeDur);
  const boxes = heroSceneText(ctx, scene, { bodyAlpha: summaryFade });
  // S5 전용 시각 요소(흐름 레일·폴더)는 마지막 fadeDur에 걸쳐 소멸 — 프레임 479에는 없다.
  const visualFade = 1 - E.clamp01((local.t - hold.dur) / hold.fadeDur);

  // 흐름 다이어그램 한 줄 — drawEnd(초)까지 완성
  const fp = E.clamp01(local.t / pr.flow.drawEnd);
  const step = (pr.flow.x2 - pr.flow.x1) / (pr.flow.nodes - 1);
  if (fp > 0 && visualFade > 0) {
    E.line(ctx, pr.flow.x1, pr.flow.y, pr.flow.x1 + (pr.flow.x2 - pr.flow.x1) * fp, pr.flow.y, {
      key: 's5-flow',
      width: 5,
      color: E.withAlpha(P.accent2, 0.85),
      alpha: visualFade,
    });
    for (let i = 0; i < pr.flow.nodes; i++) {
      const nx = pr.flow.x1 + step * i;
      const nodeP = E.clamp01(fp * (pr.flow.nodes - 1) - i + 1);
      if (nodeP <= 0) continue;
      ctx.save();
      ctx.globalAlpha *= nodeP * visualFade;
      ctx.fillStyle = P.accent2;
      ctx.beginPath();
      ctx.arc(nx, pr.flow.y, 9, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      if (i < pr.flow.nodes - 1 && nodeP >= 1) {
        E.arrowHead(ctx, nx + step / 2 + step * 0.32, pr.flow.y, 0, 16, {
          key: `s5-arrow-${i}`,
          width: 4,
          color: P.accent2,
          alpha: visualFade,
        });
      }
    }
  }

  // 완성 서류철이 흐름선 위에 착지
  const settleP = E.easeAt('easeInOutCubic', local.t, 0, pr.settle.dur);
  const settleDy = (1 - settleP) * 20;
  heroFolder(ctx, E, P, { ...pr.folder, cy: pr.folder.cy + settleDy }, { key: 's5-folder', settleDy, checked: true, alpha: visualFade });
  folderLabel(ctx, E, { ...pr.folder, cy: pr.folder.cy + settleDy }, { alpha: visualFade });

  // S0과 동일한 마커 언더라인(정적) — 루프 이음새 구도 일치.
  // 페이드인 전반부는 문구가 아직 안 보이므로(textAlpha 0) 언더라인도 생략한다.
  const u = boxes.title;
  if (u) {
    E.line(ctx, u.x + 6, u.y + u.h + 18, u.x + u.w - 6, u.y + u.h + 18, {
      key: 's5-underline',
      width: 18,
      color: E.withAlpha(P.accent, 0.3),
    });
  }

  // S0 태그라인 스왑 — 요약줄이 완전히 사라진 뒤 같은 부제 슬롯에 등장해 프레임 0과 동일 구도로 수렴
  const tagP = E.clamp01((local.t - hold.taglineSwapAt) / hold.taglineFadeDur);
  if (tagP > 0) {
    E.text(ctx, { text: HERO_CONFIG.meta.tagline, x: L.width / 2, y: L.titleSubY, px: T.bodyPx, alpha: tagP });
  }
};
