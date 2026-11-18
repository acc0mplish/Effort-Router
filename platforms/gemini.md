# effort-router — Gemini / Antigravity 어댑터

대상: Google Antigravity (`agy` CLI, Antigravity IDE, Antigravity 2.0). 전역 스킬 디렉터리, `settings.json`, 전역 상시 규칙(`rules/effort-router.md`), 커스텀 서브에이전트 정의(`agents/*.md` 11종)를 공유한다.

> 본 문서는 effort-router `SKILL.md`(§1 티어·§2 화이트리스트·§3 제약·§5 `state.json` 계약·§6 환경 매핑)의 파생 이식본이다 — 규칙 충돌 시 `SKILL.md` 본문이 우선한다.

## 설치 및 업데이트 경로

- **전역 스킬**: `~/.gemini/config/skills/effort-router/` (호환 미러: `~/.agents/skills/effort-router/`)
- **전역 커스텀 서브에이전트 (11종)**: `~/.gemini/config/agents/*.md` (역할 10종 + `ops-supervisor`)
- **전역 상시 규칙**: `~/.gemini/config/rules/effort-router.md` (`trigger: always_on`)
- **전역 CLI 기본 모델**: `~/.gemini/antigravity-cli/settings.json` (`"model": "gemini-4-carbon-high"`)

저장소 루트에서 업스트림 스킬 본문·스크립트·어댑터를 전역 스킬 디렉터리와 호환 미러에 복사한 뒤, 동봉된 커스텀 서브에이전트 11종과 전역 상시 규칙을 적용한다(무관한 기존 에이전트·규칙·설정은 보존한다):

```bash
mkdir -p ~/.gemini/config/skills/effort-router ~/.gemini/config/agents ~/.gemini/config/rules ~/.agents/skills/effort-router
cp -R SKILL.md README.md TESTS*.md agents platforms scripts ~/.gemini/config/skills/effort-router/
cp -R SKILL.md README.md TESTS*.md agents platforms scripts ~/.agents/skills/effort-router/
cp platforms/gemini-agents/*.md ~/.gemini/config/agents/
cp platforms/gemini-rules/effort-router.md ~/.gemini/config/rules/
```

## 전역 기본 모델 설정

`~/.gemini/antigravity-cli/settings.json`을 통째로 덮어쓰지 말고 기존 설정 키(인증·테마·MCP·권한 등)를 보존한 채 최상위 `"model"` 키만 병합한다:

```json
{
  "model": "gemini-4-carbon-high"
}
```

## 고정 모델·역할 매핑 (3조합)

| 역할 (`~/.gemini/config/agents/<role>.md`) | 확정 목표 모델 (슬러그) | `agent.md` `model:` 티어 | 도구 권한 |
|---|---|---|---|
| `coder-medium` | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | `inherit` | 전체 (읽기·편집·명령·웹) |
| `implement-med` | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | `inherit` | 전체 (읽기·편집·명령·웹) |
| `implement-xhigh` | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | `inherit` | 전체 (읽기·편집·명령·웹) |
| `core-xhigh` | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | `inherit` | 전체 (읽기·편집·명령·웹) |
| `ops-supervisor` | `gemini-4-carbon-high` (`Gemini 4 Carbon (High)`) | `inherit` | 전체 (감시·GitHub 운영·무결성 점검) |
| `plan-high` | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `pro` | 전체 (계획 번들 작성 허용, 제품 코드 금지) |
| `plan-xhigh` | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `pro` | 전체 (계획 번들 작성 허용, 제품 코드 금지) |
| `plan-adversary-xhigh` | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `pro` | 읽기 전용 (`edit_file`·`write_file` 제외) |
| `review-pr-high` | `gemini-4-carbon-low` (`Gemini 4 Carbon (Low)`) | `flash` | 읽기 전용 (`edit_file`·`write_file` 제외) |
| `review-pr-xhigh` | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `pro` | 읽기 전용 (`edit_file`·`write_file` 제외) |
| `security-audit` | `gemini-4-hydrogen-xhigh` (`Gemini 4 Hydrogen (XHigh)`) | `pro` | 읽기 전용 (`edit_file`·`write_file` 제외) |

일반 구현·감시 작업은 `gemini-4-carbon-high`(`inherit`)를 기본으로 사용하고, 계획·적대적 검토·심층 리뷰·보안감사는 `gemini-4-hydrogen-xhigh`(`pro`), S/M 간이 리뷰는 `gemini-4-carbon-low`(`flash`)를 사용한다. 커스텀 서브에이전트 파일의 존재 자체는 자동 스폰 권한을 뜻하지 않으며 `SKILL.md` §2·§3 게이트를 따른다.

## 전역 규칙 및 설치 검증

1. **전역 상시 규칙 (`~/.gemini/config/rules/effort-router.md`)**: `trigger: always_on`으로 작업 착수 전 `intake_gate.py` 점검, `[Effort Router]` Output Contract 선출력, 3조합 정책, 실패 기반 영구 예방 규칙을 강제한다.
2. **`invoke_subagent` 기본 호출**: `~/.gemini/config/agents/*.md`에 등록된 `TypeName`으로 스폰한다. 모든 서브에이전트는 `inheritCustomizations: false`로 설정되어 상위 `effort-router` 규칙을 중복 상속·재호출하지 않는다.
3. **정확한 슬러그 핀 고정 통로**: Antigravity의 `agents/*.md` 파서는 `model:` 값으로 `inherit | pro | flash | flash_lite` 4종만 허용한다(`agy plugin validate` 검증 기준). `inherit` 역할 5종은 메인 기본 세션(`gemini-4-carbon-high`)을 그대로 물려받으며, `gemini-4-hydrogen-xhigh` / `gemini-4-carbon-low` 슬러그 강제가 필요한 고위험 단계·2회 실패 진단은 `agy -p --model <슬러그>` 또는 `swarm(action="add", model="<슬러그>")`를 사용한다.
4. **세션 재시작 및 검증**: `~/.gemini/config/agents/*.md`, `rules/effort-router.md`, `settings.json` 변경 사항은 Antigravity IDE 또는 `agy` 세션을 재시작해야 다음 세션부터 반영된다. 재시작 후 아래 명령으로 전역 스킬, 기본 모델, 상시 규칙, 11종 서브에이전트 스키마를 검증한다:

```bash
python3 ~/.gemini/config/skills/effort-router/scripts/verify_gemini_install.py --require-agy
```

성공 시 `PASS global Gemini effort-router installation`과 `- custom subagents: 11/11 validated`를 출력한다(`agy` 바이너리가 없는 격리 CI·샌드박스에서는 `--require-agy`를 생략해 정적 계약만 점검할 수 있다).
