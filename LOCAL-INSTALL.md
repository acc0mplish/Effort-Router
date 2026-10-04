# 로컬 설치 정책 — Astra

Upstream: https://github.com/acc0mplish/Effort-Router
Source commit: `89d5a4b5f7a38f98a465281611e32ea94ce2c934` (r35).

2026-10-05 최신 사용자 지시: 모든 작업 `gpt-6-astra`; 일반 `medium`, 고난도 `max`. 이전 max 금지·Terra/Sol/Luna 정책을 대체한다. 이 설치는 원본에 로컬 정책을 적용한 수정본이다.

`local-policy.json`은 기본값·고난도 기준·10개 역할의 단일 정책 원천이다. 갱신기와 검증기가 직접 읽는다. 역할 식별자의 high/xhigh는 실제 effort를 뜻하지 않는다. 일반 역할 4개는 medium, 고난도 역할 6개는 max다.

전역 기본값은 Astra/medium. fast·balanced·planning·unsloth_api 프로필은 Astra/medium, deep은 Astra/max다. unsloth_api 프로필 이름은 호환용으로 유지하며 기본 OpenAI 경로를 사용한다. 기존 provider 정의·인증·MCP·plugins·권한·컨텍스트 값은 보존한다. 정책 밖 역할은 자동 호출하지 않는다.

안전한 역할 갱신·검증:

```bash
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py
python3 ~/.codex/skills/effort-router/scripts/configure_codex_plan.py --apply
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

갱신기는 역할의 bare root model·effort 키만 변경하고 사전 검증·백업·원자적 쓰기를 유지한다. config.toml·AGENTS.md 변경은 필요한 키·라우팅 단편만 병합한다. `~/.codex/skills/effort-router`와 `~/.agents/skills/effort-router`의 로컬 정책·Codex 어댑터·역할 템플릿·갱신기·검증기를 함께 동기화한다.

기존 `deploy_global.py`는 전역 정규식 치환과 역할 전체 덮어쓰기가 있어 이 로컬 정책에서 실행을 차단했다. 재설치 시 upstream 배포기를 그대로 실행하지 않는다. 비Codex 어댑터와 과거 검증 기록은 현재 Codex 라우팅 원천으로 사용하지 않는다.

멀티에이전트는 독립된 `codex exec`에 -m gpt-6-astra, 명시적 medium/max, -C, sandbox, 결과 경로를 지정한다. native spawn/fan-out은 금지한다. Astra 백엔드가 확인되지 않은 선택적 외부 LLM은 호출하지 않는다.

백업은 `~/.effort-router-backups/`에 저장하고 `~/.codex/agents/` 내부에 만들지 않는다. 변경한 전역 기본값·역할을 새 세션에 로드하려면 앱을 재시작한다. 기존 세션은 모델·effort 선택기로 직접 전환하며 자동 전환했다고 보고하지 않는다.
