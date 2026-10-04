# effort-router — Codex adapter (Astra local policy)

Codex CLI·IDE·앱은 로컬 Skill과 config.toml·역할 설정을 사용한다. [LOCAL-INSTALL.md](../LOCAL-INSTALL.md)와 [local-policy.json](../local-policy.json)이 설치 원본의 모델 예제보다 우선한다.

일반 작업은 `gpt-6-astra / medium`, 고난도 작업은 `gpt-6-astra / max`다. 계획·리뷰라는 단계만으로 max를 선택하지 않는다.

## Global defaults

기존 config.toml을 보존하고 첫 TOML table 위의 root 키만 병합한다.

```toml
model = "gpt-6-astra"
model_reasoning_effort = "medium"

[agents]
enabled = true
```

이미 존재하는 table을 중복 생성하지 않는다. fast·balanced·planning·unsloth_api는 Astra/medium, deep은 Astra/max다. unsloth_api는 기존 이름을 유지하는 Astra 프로필이며 별도 model_provider override를 사용하지 않는다. provider 정의·인증·서비스 등급·MCP·plugins·권한·컨텍스트 값은 보존한다.

## Role map

역할 이름은 호환성을 위해 유지한다. high/xhigh 접미사는 실제 effort를 의미하지 않는다.

| Role | Model | Effort |
|---|---|---|
| `coder-medium` | `gpt-6-astra` | `medium` |
| `implement-med` | `gpt-6-astra` | `medium` |
| `implement-xhigh` | `gpt-6-astra` | `max` |
| `core-xhigh` | `gpt-6-astra` | `max` |
| `plan-high` | `gpt-6-astra` | `medium` |
| `plan-xhigh` | `gpt-6-astra` | `max` |
| `plan-adversary-xhigh` | `gpt-6-astra` | `max` |
| `review-pr-high` | `gpt-6-astra` | `medium` |
| `review-pr-xhigh` | `gpt-6-astra` | `max` |
| `security-audit` | `gpt-6-astra` | `max` |

## Safe update and verification

```bash
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py --apply
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

갱신기는 local-policy.json을 읽고 역할 root model·effort만 변경한다. 변경 전 검증·스캔 트리 밖 백업·원자적 쓰기를 유지한다. 검증 성공은 `PASS global effort-router installation`이다. 기존 광범위 deploy_global.py는 로컬 정책 설치에서 차단된다.

일반 보조 작업도 Astra/medium, 고난도는 Astra/max다. native spawn/fan-out은 금지하며 승인된 독립 작업은 별도 codex exec에 모델·effort·-C·sandbox·결과 경로를 명시한다. 최대 동시 작업자는 4개다. 메인이 결과와 검증을 통합한다.

~/.codex와 ~/.agents의 effort-router 설치본을 동기화한다. 앱 재시작 또는 새 세션에서 전역 설정을 로드한다. 진행 중인 세션의 모델을 자동 변경했다고 주장하지 않는다.
