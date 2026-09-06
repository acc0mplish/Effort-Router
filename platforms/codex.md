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

`~/.codex/AGENTS.md`에는 아래 「AGENTS.md 삽입 단편」을 기존 내용과 병합한다. 라우팅 규칙과 실패 원장 규칙이 모두 있어야 한다. 설치 후 Codex CLI·IDE·ChatGPT 앱을 재시작한다.

## 설치 완료 검증

```bash
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

성공 기준은 `PASS global effort-router installation`이다. 이 검사는 Skill·UI metadata·전역 기본 모델/effort·subagent 활성화·전역 AGENTS 규칙·10개 custom-agent TOML을 함께 확인한다. 실제 역할 호출 검증은 `TESTS.md`의 Codex runtime protocol을 따른다.

## 요금제 자동 감지와 적용

이 프로젝트의 사용자 지정 정책: Plus는 검토·문제 판정·보안 감사도 `gpt-6-astra / medium`, Pro는 `gpt-6-astra / high`를 사용한다. 계획은 항상 Astra/medium, 모든 실무 실행은 Luna/max다. 이는 요금제의 공식 모델 제한을 주장하는 규칙이 아니다. 아래 표와 기본 TOML은 Pro 기준이며 Plus 적용 시 검토 4개 role의 effort를 medium으로 바꾼다.

```bash
# 조회·변경 예정 role 확인 (파일 변경 없음)
python3 scripts/configure_codex_plan.py
# 감지 결과 적용 (기존 파일 백업 후 모델·effort 키만 변경)
python3 scripts/configure_codex_plan.py --apply
# 오프라인 또는 자동 감지 불가 환경에서 명시적으로 선택
python3 scripts/configure_codex_plan.py --plan plus --apply
# 감지된 요금제를 기준으로 설치 검증
python3 scripts/verify_global_install.py
```

설치된 Skill에서는 위 `scripts/`를 `~/.codex/skills/effort-router/scripts/`로 바꾼다. 기본 대상은 `$CODEX_HOME/agents` 또는 `~/.codex/agents`; `--agents-dir PATH`로 별도 설치 디렉터리를 지정할 수 있다. 없는 role은 동봉 템플릿으로 생성한다. 기존 role은 기타 설정과 지시문을 보존하므로 구 정책의 지시문이 남은 설치는 먼저 현재 Skill·role 템플릿으로 병합 업데이트한다.

감지는 `codex app-server`의 `initialize` → `initialized` → `account/read` (`refreshToken: false`) 순서다. 현재 로그인 정보의 `planType`만 사용하고 토큰·이메일·계정 원문은 출력하지 않는다. 강제 토큰 갱신은 하지 않는다. 로그아웃·API 키 로그인·Plus/Pro 외 요금제·오류·15초 타임아웃에는 파일을 변경하지 않고 exit 1로 중단한다. 이 경우 사용자가 `--plan plus|pro`를 명시할 수 있다. [공식 OpenAI account/read 문서](https://learn.chatgpt.com/docs/app-server).

계정·요금제 변경 후 적용 명령을 다시 실행한다. `restart_required: true`이면 Codex CLI를 재시작한 뒤 역할을 호출한다. 실행 중인 메인 모델이나 이미 로드된 custom agent를 자동 전환했다고 간주하지 않는다. 변경 파일 원본은 대상 디렉터리의 `.effort-router-backups/` 아래에 보관한다. 동일 설정 재적용은 새 백업이나 변경을 만들지 않는다. 전역 `config.toml`·`AGENTS.md` 병합은 기존 설치 절차를 따른다.

## OpenAI 모델 정책

| 역할 | 모델 | effort | 선택 근거 |
|---|---|---|---|
| `coder-medium` | `gpt-5.6-luna` | `max` | 명확한 S 구현·테스트 |
| `implement-med` | `gpt-5.6-luna` | `max` | 확정 계획의 일반 구현 |
| `plan-high` | `gpt-6-astra` | `medium` | M/L 명세·계획 작성 |
| `plan-xhigh` | `gpt-6-astra` | `medium` | XL 아키텍처·명세 작성 |
| `plan-adversary-xhigh` | `gpt-6-astra` | `high` | 스펙·계획 적대 검토 |
| `review-pr-high` | `gpt-6-astra` | `high` | S/M 문제 판정·PR 리뷰 |
| `review-pr-xhigh` | `gpt-6-astra` | `high` | L/XL 심층 판정 |
| `implement-xhigh` | `gpt-5.6-luna` | `max` | 확정 계획의 XL 구현; 설계 변경은 계획·검토로 분리 |
| `core-xhigh` | `gpt-5.6-luna` | `max` | XL 직렬 임계경로 |
| `security-audit` | `gpt-6-astra` | `high` | 보안·출시 판정 |

`gpt-5.6-terra`는 기본 라우팅에서 제외한다. 모든 실무 실행은 Luna/max, 계획·명세 작성은 Astra/medium, 검토·문제 판정·보안 감사는 Astra/high가 담당한다. role 이름은 호환용 식별자이며 실제 effort는 표와 TOML을 따른다.

## 승격 규칙

- 동일 접근 2회 실패, 재현 불안정, 반복 테스트 실패: 현재 구현을 중단하고 `gpt-6-astra / high`로 원인 분석·해결안을 검토한다. 재계획은 Astra/medium, 확정된 수정·테스트 실행은 Luna/max로 복귀한다.
- `max`는 단일 에이전트의 reasoning depth다. 이것만으로 subagent를 늘리지 않는다.
- `ultra`는 서로 독립적인 하위 작업을 병렬화할 때만 선택한다.

## 실행 계약

- 작업 시작 전에 SKILL.md Output Contract를 출력한다.
- custom agent를 쓸 때 실제 role·model·effort는 위 표와 일치해야 한다. 호출 시 다른 모델로 override하지 않는다.
- 멀티에이전트는 사용자나 상위 지침이 허용하고, 독립성·병렬 이득이 모두 있을 때만 사용한다.
- 완료 보고는 실행 명령 원문과 exit code를 포함한다. 메인 세션이 핵심 검증을 1회 재실행한다.
- 스폰 워치독(§3): 장기 스폰을 10분 간격으로 점검한다 — Codex 스폰 정지 수단이 확인되지 않으면 스폰 프롬프트에 종료 시한을 사전 명시하는 폴백을 쓴다.

## AGENTS.md 삽입 단편

```markdown
코딩 작업 착수 전 설치된 `effort-router`를 사용한다. Output Contract로 티어·단계·모델·effort를 먼저 밝힌다. 모든 실무 실행은 GPT-5.6-Luna max, 계획·명세 작성은 GPT-6-Astra medium, 검토·문제 판정·보안 감사는 Plus에서 GPT-6-Astra medium, Pro에서 GPT-6-Astra high를 사용한다. 역할 호출 전 configure_codex_plan.py로 요금제를 확인하고 불일치 시 --apply 적용 및 Codex 재시작 후 진행한다. 동일 접근 2회 실패 시 요금제별 Astra effort로 검토하고, 재계획은 Astra medium, 확정된 실행은 Luna max로 복귀한다. max를 이유로 멀티에이전트를 자동 사용하지 않는다.

## 실패 기반 영구 예방 규칙

- 주요 agent guide file은 Codex의 `AGENTS.md`, Claude Code의 `CLAUDE.md`, Cursor의 `.cursorrules`다.
- 관측되거나 재현된 과거 실패 1건을 영구 예방 규칙 1줄로 변환한다.
- 규칙은 실패 트리거와 필수/금지 행동을 포함하고, 다음 작업에서 준수 여부를 판정할 수 있어야 한다.
- 같은 실패의 기존 규칙이 있으면 새 줄을 만들지 말고 기존 규칙을 더 정확하게 고친다.
- 모든 저장소에 적용되는 규칙만 전역 파일에 두고, 프로젝트 고유 규칙은 가장 가까운 프로젝트 guide file에 둔다.
```
