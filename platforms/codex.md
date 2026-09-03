# effort-router — Codex CLI 어댑터

삽입처: `~/.codex/AGENTS.md`(글로벌) 또는 리포 루트 `AGENTS.md`. 설치(붙여넣기)는 사용자 실행 — 본 파일은 병합용 단편 콘텐츠만 제공한다.

> 본 문서는 effort-router SKILL.md(§1 티어·§3 제약·§6 매핑)의 파생 축약 이식본이다 — 규칙 충돌 시 본문이 우선한다. 본문 갱신 시 본 파일도 파생 갱신한다.

## 티어 판정 (본문 §1 축약)

- **S** 단일 파일·텍스트/스타일 · **M** 2~10파일·~1000줄 이하·위험 지표 음성 · **L** 10파일·1000줄 초과 또는 위험 지표 양성(규모 무관) · **XL** 코어 엔진·전면 리팩터링 · **보안감사** 별도 트랙
- **폴백**: 지표 충돌 시 상위 티어 — 하향 예외는 실질이 국소·기계적 변경임이 확인될 때 근거와 함께만.
- **은닉 변수**(해당 시 1티어 상향): 요청 경로 동작 변경 / 보안 통제 자체 변경 / 코드만으로 판별 불가 변수(확인 질문 1개 선행).

## 실행 계약 (본문 §3·Output Contract 축약)

- 작업 착수 전 티어 판정·실행 지침 요약을 먼저 출력한다.
- 타 하니스 표기: 적용 에이전트 라인 = 아래 대응물 또는 `없음(단일 세션)`, 팬아웃 라인 = `OFF`, 단계 상태 라인은 인계를 실제 운반할 때만 기입.
- **적용 제외: §2 화이트리스트·팬아웃·state.json(§5)** — Claude Code 전용 계약이다.

## Codex 대응 (본문 §6)

- 서브에이전트: 멀티에이전트 도구(`spawn_agent`·`send_input`·`resume_agent`·`wait_agent`·`close_agent` — stable, 기본 on). 커스텀 에이전트는 독립 TOML 파일 — `~/.codex/agents/`(개인)·`.codex/agents/`(프로젝트), 파일당 1 에이전트. 필수 `name`·`description`·`developer_instructions`, 선택 `model`·`model_reasoning_effort`·`sandbox_mode`·`mcp_servers`·`skills.config`. 빌트인 `default`·`worker`·`explorer`(동명 커스텀이 우선). 우선순위: 명시 스폰 > `config.toml` `[agents]` 기본(`default_subagent_model`·`default_subagent_reasoning_effort`) > 커스텀 파일 > 부모 상속.
- effort: `model_reasoning_effort` = minimal|low|medium|high|xhigh(xhigh는 모델 의존). 스폰 기본값 `agents.default_subagent_reasoning_effort`·`agents.default_subagent_model` — 스폰 시 명시가 우선. 서브에이전트 안내 페이지는 모델 의존 상위 단계 `max`·`ultra`도 언급한다.
- 컨텍스트 등재: AGENTS.md 계층 `~/.codex/AGENTS.md` → 리포 루트 → 하위 디렉터리. 프로필 전환은 `$CODEX_HOME/<name>.config.toml` + `--profile`(user-level).
- 역할 분리가 필요하면 본 스킬의 에이전트명(plan-high 등)을 지목하지 않고, 아래 표를 참조해 커스텀 에이전트 파일(`agents/<역할>.toml` — `~/.codex/` 또는 `.codex/` 기준)을 직접 정의한다.

## role↔설정 매핑표 (원본 `agents/*.md` frontmatter 증류)

| 본문 §2 역할 | 커스텀 에이전트 파일 | effort |
|--------------|------------------------|--------|
| ①계획(M/L) | `agents/plan-high.toml` | high |
| ①계획(XL) | `agents/plan-xhigh.toml` | xhigh |
| ②검토(적대 리뷰) | `agents/plan-adversary-xhigh.toml` | xhigh |
| ③구현(S 위임) | `agents/coder-medium.toml` | medium |
| ③구현(M) | `agents/implement-med.toml` | medium |
| ③구현(XL) | `agents/implement-xhigh.toml` | xhigh |
| ③구현(XL 임계경로) | `agents/core-xhigh.toml` | xhigh |
| ④리뷰(S/M) | `agents/review-pr-high.toml` | high |
| ④리뷰(L/XL) | `agents/review-pr-xhigh.toml` | xhigh |
| 보안감사 | `agents/security-audit.toml` | xhigh |

- 모델 열 없음 — 원본의 슬롯명(haiku/sonnet/opus)은 Claude Code 프록시 슬롯이라 Codex 모델명과 대응하지 않는다. 모델은 Codex 설정의 모델 지정을 따른다.
- 현장 주의(커뮤니티 실측 2026-09, Codex 0.144.5): multi_agent v2 세션에서 스폰 시 모델·effort 제어가 동작하지 않는 회귀 보고가 있다(openai/codex 이슈 트래킹 중). 공식 문서 기준이 우선이되 설치 후 커스텀 에이전트 1회 스폰 프루브를 권장한다.
