# platforms/ — 타 하니스 어댑터 인덱스

effort-router 본문(SKILL.md)은 Claude Code 실행 계약이고, 본 디렉터리는 타 하니스용 파생 단편을 모은다.

> 본 문서는 effort-router SKILL.md(§1 티어·§3 제약·§6 매핑)의 파생 축약 이식본이다 — 규칙 충돌 시 본문이 우선한다. 본문 갱신 시 본 파일도 파생 갱신한다.

## 단일 소스 원칙

- 어댑터는 본문 규칙의 **축약 이식**이다 — 재해석·신규 서술 없음. 규칙 변경 시 SKILL.md 본문이 우선하고 어댑터는 파생 갱신한다.
- 모든 설치·붙여넣기는 **사용자 실행**이다 — 본 스킬은 타 하니스 설정 파일(`~/.codex/AGENTS.md` 등)에 삽입하지 않는다.

## 설치·붙여넣기 절차 표

| 파일 | 대상 | 삽입처(사용자 실행) | 형태 |
|------|------|--------------------|------|
| codex.md | Codex CLI | `~/.codex/AGENTS.md`(글로벌) 또는 리포 루트 `AGENTS.md` | 병합용 단편 |
| qwen.md | Qwen Code | `~/.qwen/QWEN.md` 또는 프로젝트 루트 `QWEN.md`(`AGENTS.md` 병행 가능) | 병합용 단편 |
| gemini.md | Gemini CLI | `~/.gemini/GEMINI.md` 또는 워크스페이스 `GEMINI.md` | 병합용 단편 |
| glm.md | GLM Coding Plan | 설치 불필요 — Claude Code 백엔드 교체 시 참조 | 안내 문서 |
| chat-app.md | ChatGPT 앱·GLM 앱 | 앱 지침 계층(ChatGPT) 또는 첫 턴 붙여넣기 | paste 카드 |

## 참고

- Gemini 메모리 파일명은 `context.fileName` 설정으로 변경 가능 — 변경 시 삽입처도 따라간다.
- **glm.md와 chat-app.md는 다른 대상이다** — Claude Code 백엔드를 GLM으로 바꾸면 glm.md, GLM 웹앱(chat.z.ai)이면 chat-app.md.
- 어댑터의 '미확인' 표기 항목은 공식 문서에서 확인하지 못한 것 — 현장 확인 후 갱신한다.
