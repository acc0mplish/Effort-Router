#!/usr/bin/env python3
"""hero-motion GIF 조립 (python3 + Pillow, 계획 §5.2).

사용법:
  python3 build-gif.py                       — build/frames → build/hero.gif (20fps, 960폭)
  python3 build-gif.py --fps 12.5            — 하강 사다리 재덤프 후 조립(10ms 양자 정합 fps만 허용)

프레임은 export-frames.mjs가 해당 fps로 재덤프한 것을 사용한다(비균일 샘플링 금지).
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZE_TARGET_BYTES = 10 * 1024 * 1024
LADDER = "fps 20 → 12.5(80ms) → 10(100ms) → 폭 960→800 → 팔레트 256→128"


def loop_seconds_from_config():
    src = (ROOT / "js" / "config.js").read_text(encoding="utf-8")
    m = re.search(r"loopSeconds:\s*([0-9.]+)", src)
    if not m:
        sys.exit("config.js에서 loopSeconds를 읽지 못했다")
    return float(m.group(1))


def main():
    ap = argparse.ArgumentParser(description="hero-motion GIF 조립")
    ap.add_argument("--fps", type=float, default=20.0, help="덤프 fps(기본 20 — CONFIG.export.fps)")
    ap.add_argument("--gif-width", type=int, default=960, help="GIF 폭(기본 960, 16:9 유지)")
    ap.add_argument("--frames", default=str(ROOT / "build" / "frames"))
    ap.add_argument("--out", default=str(ROOT / "build" / "hero.gif"))
    args = ap.parse_args()

    duration_ms = round(1000 / args.fps)
    if duration_ms % 10 != 0:
        sys.exit(f"[gif][FAIL] 프레임 시간 {duration_ms}ms가 GIF 10ms 양자가 아니다 — 양자 정합 fps만 사용: {LADDER}")
    loop_seconds = loop_seconds_from_config()
    expected = round(loop_seconds * args.fps)

    files = sorted(Path(args.frames).glob("*.png"))
    if len(files) == 0:
        sys.exit(f"[gif][FAIL] 프레임이 없다: {args.frames} — 먼저 export-frames.mjs --fps {args.fps} 실행(재덤프 계약)")
    if len(files) != expected:
        sys.exit(f"[gif][FAIL] 프레임 수 불일치: {len(files)}장 (기대 {expected}장 = {loop_seconds}s × {args.fps}fps)")

    height = round(args.gif_width * 9 / 16)
    print(f"[gif] {len(files)}프레임 → {args.gif_width}×{height}, {duration_ms}ms/프레임")

    # 공용 256색 팔레트 — 전체 프레임 샘플에서 1개만 만들어 모든 프레임에 적용(프레임 간 색 떨림 방지)
    sample_files = files[:: max(1, len(files) // 24)]
    strips = [Image.open(f).resize((320, 180), Image.LANCZOS) for f in sample_files]
    sheet = Image.new("RGB", (320 * len(strips), 180))
    for i, s in enumerate(strips):
        sheet.paste(s, (320 * i, 0))
    palette_img = sheet.quantize(colors=256, method=Image.MEDIANCUT)

    out_frames = []
    for f in files:
        rgb = Image.open(f).convert("RGB").resize((args.gif_width, height), Image.LANCZOS)
        # 디더링 없음 — 프레임 간 색 노이즈(점멸) 방지, 평면 색 구성에 유리
        out_frames.append(rgb.quantize(palette=palette_img, dither=Image.Dither.NONE))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_frames[0].save(
        args.out,
        save_all=True,
        append_images=out_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )

    size = Path(args.out).stat().st_size
    total = len(out_frames) * duration_ms / 1000
    print("[gif] 실측 리포트 (claim 3)")
    print(f"[gif]   해상도      : {args.gif_width}×{height}")
    print(f"[gif]   총프레임    : {len(out_frames)}")
    print(f"[gif]   프레임당    : {duration_ms}ms (fps {args.fps})")
    print(f"[gif]   총 재생시간 : {total:.2f}초 (계약 {loop_seconds:.2f}초)")
    print(f"[gif]   파일 크기   : {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
    print(f"[gif]   판정        : {'PASS — 목표 ≤10MB' if size <= SIZE_TARGET_BYTES else '초과 — 하강 사다리 발동: ' + LADDER}")
    if shutil.which("ffmpeg") is None:
        print("[gif]   MP4         : 생략 — ffmpeg 미설치(claim 8). 설치 시에만 선택 생성")
    if total != loop_seconds:
        sys.exit(f"[gif][FAIL] 총 재생시간 {total}초가 계약 {loop_seconds}초와 어긋난다")
    sys.exit(0 if size <= SIZE_TARGET_BYTES else 2)


if __name__ == "__main__":
    main()
