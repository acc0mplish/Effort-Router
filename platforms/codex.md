# effort-router — Codex 어댑터

대상: Codex CLI, IDE extension, ChatGPT 데스크톱 앱의 Codex 화면. 세 클라이언트는 로컬 Codex Skill·`config.toml`·custom-agent TOML을 공유한다.

## 설치 위치

- Skill: `~/.codex/skills/effort-router/`
- custom agents: `platforms/codex-agents/*.toml`을 `~/.codex/agents/`로 설치
- 전역 기본값·subagent 활성화: `~/.codex/config.toml`
- 전역 발동 규칙: `~/.codex/AGENTS.md`
- 프로젝트 예외: 리포의 가까운 `AGENTS.md`가 전역 규칙보다 우선

## 전역 설정

`~/.codex/config.toml` 전체를 덮어쓰지 말고 다음 값을 병합한다. root key는 첫 `[table]`보다 위에 둔다.

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
```

- 기존 `[agents]` table이 있으면 중복 생성하지 말고 `enabled`만 추가·수정한다.
- 기존 profiles, MCP, sandbox, projects 설정은 보존한다.
- `[features]`의 `multi_agent = true`를 사용하는 기존 설치가 정상 작동하면 호환 설정으로 인정하며 억지로 중복 추가하지 않는다.
- custom agent의 `model`과 `model_reasoning_effort`는 각 `~/.codex/agents/*.toml`이 전역 기본값보다 우선한다.

`~/.codex/AGENTS.md`에는 아래 「AGENTS.md 삽입 단편」을 기존 내용과 병합한다. 설치 후 Codex CLI·IDE·ChatGPT 앱을 재시작한다.

## 설치 완료 검증

```bash
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

성공 기준은 `PASS global effort-router installation`이다. 이 검사는 Skill·UI metadata·전역 기본 모델/effort·subagent 활성화·전역 AGENTS 규칙·10개 custom-agent TOML을 함께 확인한다. 실제 역할 호출 검증은 `TESTS.md`의 Codex runtime protocol을 따른다.

## OpenAI 모델 정책

| 역할 | 모델 | effort | 선택 근거 |
|---|---|---|---|
| `coder-medium` | `gpt-5.6-luna` | `max` | 명확한 S 구현·테스트 |
| `implement-med` | `gpt-5.6-luna` | `max` | 확정 계획의 일반 구현 |
| `plan-high` | `gpt-5.6-sol` | `high` | M/L 명세·계획 작성 |
| `plan-xhigh` | `gpt-5.6-sol` | `xhigh` | XL 아키텍처·명세 작성 |
| `plan-adversary-xhigh` | `gpt-5.6-sol` | `xhigh` | 스펙·계획 적대 검토 |
| `review-pr-high` | `gpt-5.6-sol` | `high` | S/M 문제 판정·PR 리뷰 |
| `review-pr-xhigh` | `gpt-5.6-sol` | `xhigh` | L/XL 심층 판정 |
| `implement-xhigh` | `gpt-5.6-sol` | `xhigh` | 구현 중 설계 판단이 필요한 XL 작업 |
| `core-xhigh` | `gpt-5.6-sol` | `max` | XL 직렬 임계경로 |
| `security-audit` | `gpt-5.6-sol` | `max` | 보안·출시 판정 |

`gpt-5.6-terra`는 기본 라우팅에서 제외한다. 일반 실행량은 Luna/max가 담당하고, 명세·검토·문제 해결·문제 판정은 Sol이 담당한다.

## 승격 규칙

- 동일 접근 2회 실패, 재현 불안정, 반복 테스트 실패: 현재 구현을 중단하고 `gpt-5.6-sol / max`로 원인 분석·해결안 판정을 다시 한다.
- `max`는 단일 에이전트의 reasoning depth다. 이것만으로 subagent를 늘리지 않는다.
- `ultra`는 서로 독립적인 하위 작업을 병렬화할 때만 선택한다.

## 실행 계약

- 작업 시작 전에 SKILL.md Output Contract를 출력한다.
- custom agent를 쓸 때 실제 role·model·effort는 위 표와 일치해야 한다. 호출 시 다른 모델로 override하지 않는다.
- 멀티에이전트는 사용자나 상위 지침이 허용하고, 독립성·병렬 이득이 모두 있을 때만 사용한다.
- 완료 보고는 실행 명령 원문과 exit code를 포함한다. 메인 세션이 핵심 검증을 1회 재실행한다.

## AGENTS.md 삽입 단편

```markdown
코딩 작업 착수 전 설치된 `effort-router`를 사용한다. Output Contract로 티어·단계·모델·effort를 먼저 밝힌다. 명세 작성·스펙 검토·문제 분석·해결안 판단·PR 판정·고난도 작업은 GPT-5.6 Sol, 요구가 확정된 일반 구현은 GPT-5.6 Luna max를 사용한다. 동일 접근 2회 실패 시 Sol max로 승격한다. max를 이유로 멀티에이전트를 자동 사용하지 않는다.
```
