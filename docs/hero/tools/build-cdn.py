#!/usr/bin/env python3
"""CDN 폰트판 단일 HTML 생성기 — css·js는 내장, Gaegu 폰트만 Google Fonts CDN에서 로드한다.

사용법:
  python3 tools/build-cdn.py
산출: docs/hero/hero-motion-cdn.html (생성 산출물 — 원본 수정 후 재생성)

standalone(woff2 base64 내장, 오프라인 자립 ~3MB)과의 차이:
  - 파일 크기 = HTML+CSS+JS 본문만(수십~수백 KB)
  - 대신 열람 시 네트워크 필수(fonts.googleapis.com·fonts.gstatic.com)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # docs/hero

CSS2_URL = "https://fonts.googleapis.com/css2?family=Gaegu:wght@400;700&display=swap"


def main() -> None:
    if len(sys.argv) != 1:
        sys.exit("usage: build-cdn.py")

    html = (ROOT / "hero-motion.html").read_text(encoding="utf-8")
    style = (ROOT / "css" / "style.css").read_text(encoding="utf-8")

    # TTF @font-face 블록(번들 경로) 제거 — 폰트는 head의 css2 링크가 담당한다.
    cdn_style, n_ttf = re.subn(r"@font-face \{[^}]*format\('truetype'\)[^}]*\}\n?", "", style)
    if n_ttf == 0:
        # 잔존 TTF 블록은 깨진 상대참조가 되고 "네트워크만 필요" 계약을 무음 위반한다(리뷰 #3).
        sys.exit("style.css에서 TTF @font-face 블록을 찾지 못했다 — 치환 패턴을 확인하라")

    font_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
        f'<link rel="stylesheet" href="{CSS2_URL}" />'
    )
    style_anchor = '<link rel="stylesheet" href="css/style.css" />'
    if style_anchor not in html:
        sys.exit("hero-motion.html에서 style 링크 앵커를 찾지 못했다 — 마크업 드리프트 확인")
    html = html.replace(
        style_anchor,
        font_links + "\n<style>\n" + cdn_style + "\n</style>",
    )

    for name in ("config", "engine", "scenes", "scenes-b", "controls"):
        js_anchor = f'<script src="js/{name}.js"></script>'
        js = (ROOT / "js" / f"{name}.js").read_text(encoding="utf-8")
        if js_anchor not in html:
            sys.exit(f"hero-motion.html에서 js/{name}.js 앵커를 찾지 못했다 — 마크업 드리프트 확인")
        html = html.replace(
            js_anchor,
            f"<script>\n{js}\n</script>",
        )
    if 'src="js/' in html:
        sys.exit("치환 후에도 js/ 상대참조가 잔존한다 — 앵커 불일치")

    banner = (
        "<!-- CDN 폰트판 생성 산출물(단일 파일) — 직접 편집 금지. 열람 시 네트워크 필요.\n"
        "     원본·편집: hero-motion.html + css/ + js/ (CONFIG 분리 구조)\n"
        "     재생성: python3 tools/build-cdn.py (repro.md 참고) -->\n"
    )
    html = html.replace("<!doctype html>", "<!doctype html>\n" + banner, 1)

    out = ROOT / "hero-motion-cdn.html"
    out.write_text(html, encoding="utf-8")
    print(f"written {out} ({out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
