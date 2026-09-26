#!/usr/bin/env python3
"""단일 파일 standalone HTML 생성기 — hero-motion.html·css·js 5종·Gaegu woff2를 하나로 묶는다.

사용법:
  python3 tools/build-standalone.py <woff2-css> <woff2-dir>   # docs/hero 기준 상대 경로
산출: docs/hero/hero-motion-standalone.html (편집 원본이 아니라 생성 산출물 — 원본 수정 후 재생성)

폰트 출처: Google Fonts css2 응답(Gaegu 400·700)의 woff2 서브셋 전체를 base64 data URI로 내장한다.
TTF 번들 대신 서브셋을 쓰는 이유: 단일 파일 크기(약 2MB vs 8MB+). unicode-range 블록 전체를
포함하므로 CONFIG 문구를 편집해도 글리프가 빠지지 않는다(오프라인 완전 자립).
"""
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # docs/hero


def font_face_blocks(css_path: Path, woff_dir: Path) -> str:
    """css2 응답의 woff2 URL을 base64 data URI로 치환해 @font-face 블록 전체를 반환한다."""
    css = css_path.read_text(encoding="utf-8")

    def to_data_uri(match: re.Match[str]) -> str:
        url = match.group(1)
        data = (woff_dir / url.rsplit("/", 1)[-1]).read_bytes()
        return f"url(data:font/woff2;base64,{base64.b64encode(data).decode()}) format('woff2')"

    return re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\) format\('woff2'\)", to_data_uri, css)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: build-standalone.py <woff2-css> <woff2-dir>")
    css_path, woff_dir = Path(sys.argv[1]), Path(sys.argv[2])

    html = (ROOT / "hero-motion.html").read_text(encoding="utf-8")
    style = (ROOT / "css" / "style.css").read_text(encoding="utf-8")

    # TTF @font-face 2블록(번들 경로)을 woff2 내장 블록으로 교체 — 외부 참조 0개가 목적.
    # css2 응답은 400·700 전체 서브셋을 담으므로 치환값은 1회만 삽입한다(2번째 매치는 빈 문자열).
    # 이전 구현은 매치 수만큼 전체 세트를 반복 삽입해 @font-face 356블록(178×2 중복)을 만들었다.
    embedded = font_face_blocks(css_path, woff_dir)
    seen: list[bool] = []

    def replace_first(_match: re.Match[str]) -> str:
        seen.append(True)
        return embedded if len(seen) == 1 else ""

    standalone_style, n_ttf = re.subn(
        r"@font-face \{[^}]*format\('truetype'\)[^}]*\}",
        replace_first,
        style,
        count=0,
    )
    if n_ttf == 0:
        # TTF 블록 포맷이 바뀌면 내장 폰트가 통째로 탈락한 채 성공하는 무음 결함이 된다(리뷰 #2).
        sys.exit("style.css에서 TTF @font-face 블록을 찾지 못했다 — 치환 패턴을 확인하라")
    style_anchor = '<link rel="stylesheet" href="css/style.css" />'
    if style_anchor not in html:
        sys.exit("hero-motion.html에서 style 링크 앵커를 찾지 못했다 — 마크업 드리프트 확인")
    html = html.replace(
        style_anchor,
        "<style>\n" + standalone_style + "\n</style>",
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
        "<!-- 자립 실행용 생성 산출물(단일 파일) — 직접 편집 금지.\n"
        "     원본·편집: hero-motion.html + css/ + js/ (CONFIG 분리 구조)\n"
        "     재생성: python3 tools/build-standalone.py <woff2-css> <woff2-dir> (repro.md 참조) -->\n"
    )
    html = html.replace("<!doctype html>", "<!doctype html>\n" + banner, 1)

    out = ROOT / "hero-motion-standalone.html"
    out.write_text(html, encoding="utf-8")
    print(f"written {out} ({out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
