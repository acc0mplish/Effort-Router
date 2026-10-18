# platforms/ — 타 하니스 어댑터 인덱스

effort-router 본문(SKILL.md)은 Codex와 ChatGPT를 1급 대상으로 하며, 본 디렉터리는 환경별 설치·운용 단편을 모은다.

> 본 문서는 effort-router SKILL.md(§1 티어·§3 제약·§6 매핑)의 파생 축약 이식본이다 — 규칙 충돌 시 본문이 우선한다. 본문 갱신 시 본 파일도 파생 갱신한다.

## 단일 소스 원칙

- 어댑터는 본문 규칙의 **축약 이식**이다 — 재해석·신규 서술 없음. 규칙 변경 시 SKILL.md 본문이 우선하고 어댑터는 파생 갱신한다 — 현재 활성 어댑터는 케이스 1~4(claude·glm·codex·chat-app·zcode)다. qwen·gemini·grok은 사용하지 않아 2026-10-12 삭제했다.
- 설정 파일 병합은 사용자가 해당 하니스의 설치·업데이트를 요청한 범위에서만 수행한다. 그 외에는 삽입 단편만 제시하고 전역 파일을 임의 수정하지 않는다.

## Guide file 실패 원장

| 하니스 | 주요 guide file |
|---|---|
| Codex | `AGENTS.md` |
| Claude Code | `CLAUDE.md` |
| Cursor | `.cursorrules` |

관측·재현된 에이전트 실패 1건을 실행 가능하고 검증 가능한 예방 규칙 1줄로 바꿔 누적한다. 전역 파일에는 모든 저장소에 적용되는 규칙만 두며, 프로젝트 고유 실패는 가장 가까운 프로젝트 guide file에 둔다. 같은 실패의 규칙은 중복 추가하지 않고 기존 줄을 정밀화한다.

| 날짜 | 실패 | 재발 방지 (guide file · 강제 수단) |
|---|---|---|
| 2026-10-18 | GLM 세션의 역할 서브에이전트가 `model: opus\|sonnet\|haiku` 별칭 때문에 Claude로 스폰돼 Claude 사용량 소모 | `platforms/CLAUDE.md` 두뇌 프로토콜 규칙 · `scripts/glm_slot_gate.py`(스폰 전 exit 0 확인) · `scripts/test_glm_slot_gate.py`(매핑 블록·역할 별칭 강제) |

## 설치·붙여넣기 절차 표

| 파일 | 대상 | 삽입처(사용자 실행) | 형태 |
|------|------|--------------------|------|
| codex.md + codex-agents/ | Codex CLI·IDE·ChatGPT 앱 Codex | Skill + `~/.codex/config.toml` + `~/.codex/agents/*.toml` + `~/.codex/AGENTS.md` | 전역 설치·실행 어댑터 |
| glm.md | GLM Coding Plan | 설치 불필요 — Claude Code 백엔드 교체 시 참조 | 안내 문서 |
| claude.md | Claude Code(기준 하니스·GLM 백엔드 포함) | Skill(`~/.claude/skills/effort-router/`) + `~/.claude/agents/*.md` + `~/.claude/CLAUDE.md` 병합 | 10세션 토폴로지 어댑터 |
| zcode.md | ZCode (GLM Coding Plan 백엔드) | Skill(`~/.zcode/skills/` 또는 `~/.agents/skills/`) + `~/.zcode/AGENTS.md` 병합 | 어댑터 문서 |
| chat-app.md | ChatGPT Work·ChatGPT Classic(구 일반 Chat) | Skill + 앱 model/reasoning control | 앱 어댑터 |

## 참고

- `chat-app.md`는 현재 ChatGPT 앱 전용이다. GLM 웹앱·다른 웹 서비스용 범용 paste 카드로 재사용하지 않는다.
- 어댑터의 '미확인' 표기 항목은 공식 문서에서 확인하지 못한 것 — 현장 확인 후 갱신한다.
