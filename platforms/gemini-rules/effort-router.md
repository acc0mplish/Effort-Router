---
trigger: always_on
---

# Effort-Router Global Policy (Gemini / Antigravity)

## 1. 확정 모델·에포트 정책 (2026-11-18 사용자 확정 — 임의 변경 금지)

허용 모델·에포트 조합은 아래 3개뿐이다(테이블 밖 모델 자의 배정 금지):

| 구분 | 확정 모델 슬러그 (표시명) | 배정 대상 | `agents/*.md` 티어 |
|---|---|---|---|
| **일반 구현 (상시 기본값)** | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | 메인 기본 세션 · `coder-medium` · `implement-med` · `implement-xhigh` · `core-xhigh` · `ops-supervisor` | `inherit` (메인 상속) |
| **계획·적대검토·심층 리뷰·보안감사** | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `plan-high` · `plan-xhigh` · `plan-adversary-xhigh` · `review-pr-xhigh` · `security-audit` | `pro` |
| **S/M 간이 리뷰** | `gemini-4-carbon-low` (`Gemini 4 Carbon (Low)`) | `review-pr-high` | `flash` |

- 전역 CLI 기본값은 `~/.gemini/antigravity-cli/settings.json`의 `"model": "gemini-4-carbon-high"`다.
- 현재 활성 세션 모델이 권장 조합과 다를 경우 설정 파일 수정만으로 전환됐다고 주장하지 말고 UI 모델 선택기 또는 `/model` 전환을 안내한다.
- 동일 접근 2회 실패 시 `gemini-4-hydrogen-xhigh`로 원인을 진단하고, 해결 방향이 확정된 일반 구현은 `gemini-4-carbon-high`로 진행한다(3회 반복 실패 시 `neverstuck_gate.py` 적용).

## 2. 작업 착수 발동 및 서브에이전트 호출 규칙 (필수)

모든 신규 코딩·계획·설계·리뷰·디버깅·보안감사 과업 착수 전(`"ㄱㄱ"`, `"go"`, `"진행해"` 등 짧은 신호 포함) 반드시 아래 순서를 지킨다:

1. 대상 저장소의 `docs/task-id/`에서 진행 중인 과업(`state.json`, `phase`, `next`, `claims`) 유무를 먼저 확인한다.
2. `effort-router` 스킬(`~/.gemini/config/skills/effort-router/SKILL.md`)을 로드하고 `python3 ~/.gemini/config/skills/effort-router/scripts/intake_gate.py "<발화 원문>"`으로 인테이크를 점검한다.
3. 실질 작업·스폰 전에 `[Effort Router]` **Output Contract**를 먼저 출력한다.
4. 보조 작업 위임은 `~/.gemini/config/agents/*.md`에 등록된 화이트리스트 에이전트(역할 10종 + 온디맨드 `ops-supervisor`)만 `invoke_subagent(TypeName="<역할명>")`로 호출한다(`Model` 인자는 생략하거나 에이전트 정의와 일치시킨다).
   - 구현·계획·운영(`coder-medium`, `implement-*`, `core-xhigh`, `plan-*`, `ops-supervisor`)만 쓰기 도구를 가지며, 검토·리뷰·감사(`plan-adversary-xhigh`, `review-pr-*`, `security-audit`)는 `edit_file`·`write_file`이 제거된 읽기 전용 에이전트로 분리 스폰한다(자기 산출물 셀프 리뷰 금지).
   - **정확한 슬러그 핀 고정 보완**: Antigravity `agents/*.md` 로더는 `inherit|pro|flash|flash_lite` 4종만 허용하므로, 고위험 L/XL 계획·적대검토·심층 리뷰·보안감사 또는 2회 실패 진단에서 `gemini-4-hydrogen-xhigh` / `gemini-4-carbon-low` 정확한 슬러그 고정이 필수일 때는 `agy -p --model <슬러그>` 또는 `swarm(action="add", model="<슬러그>")`로 핀 고정 실행할 수 있다.

## 3. 과업 상태 및 실패 기반 영구 예방 규칙

- M티어 이상 과업 상태는 저장소 내 `docs/task-id/<task-id>/state.json`에 메인 세션 단일 writer로 기록하며(gitignore, 커밋 금지), S티어는 완료 시 최소 기록 1회만 남긴다. 완료 보고는 실행 명령 원문 + exit code로 한다.
- 주요 guide file(`GEMINI.md`, `~/.gemini/config/rules/*.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`)에는 관측·재현된 과거 실패 1건을 실패 트리거와 필수·금지 행동이 포함된 검증 가능한 규칙 1줄로 변환해 기록한다(중복 추가 금지, 프로젝트 고유 실패는 프로젝트 guide file에 배치).
- Antigravity 커스텀 에이전트(`~/.gemini/config/agents/*.md`) 작성·갱신 시 `model:` 필드에 모델 슬러그를 직접 기입하면 로더가 에이전트를 스킵하므로 반드시 `inherit|pro|flash|flash_lite`만 기입하고 `agy plugin validate`로 스키마 통과를 검증하며, 역할별 모델·에포트 정책은 사용자 확정 없이 임의 추정하지 않는다.
