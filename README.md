# effort-router

작업의 규모·위험도를 티어(S/M/L/XL)로 판정하고, 단계별(계획/검토/구현/리뷰/검증) 모델·에포트를 정해진 서브에이전트에 배정하는 Claude Code 스킬. 판정을 Output Contract로 출력한 뒤 작업을 수행한다.

```text
Decision(티어 판정) → Requirement → Acceptance → Task → Evidence → Learning
```

## 왜 필요한가

- 단일 모델·단일 에포트로 모든 과업을 처리하면 단순 수정에 과투자, 대형 변경에 과소검증이 된다
- 자기 산출물 검토는 검토가 아니다 — 검토는 역할과 산출물이 분리된 별도 에이전트가 해야 한다
- 서브에이전트 호출은 무상태다 — 단계 사이를 잇는 상태 계약(state.json·증거번들)이 없으면 인계가 산문 재구성에 의존해 무너진다

## 구조

| 경로 | 내용 |
|------|------|
| `SKILL.md` | 스킬 본체 — 티어 판정(§1)·라우팅 테이블(§2)·실행 제약(§3)·merge 권한(§4)·상태·인계 계약(§5)·타 하니스 매핑(§6)·Output Contract |
| `agents/` | 화이트리스트 서브에이전트 정의 10종(plan·implement·review·security 계열) |
| `platforms/` | 타 하니스 어댓터 — codex·qwen·gemini·glm·chat-app(ChatGPT/GLM 앱 paste 카드)·grok(Grok Bot)·README |
| `TESTS.md` | 검증 프로토콜·측정 결과·라운드별 개정 이력·재현 절차 |

## 설치 (Claude Code)

```bash
# 스킬 설치
cp -r SKILL.md TESTS.md agents platforms ~/.claude/skills/effort-router/

# 에이전트 등록본
cp agents/*.md ~/.claude/agents/
```

`~/.claude/CLAUDE.md`에 발동 규칙 추가:

```markdown
코딩 작업 착수 전 `effort-router` 스킬을 먼저 호출한다 — 티어 판정(S/M/L/XL) →
Output Contract 출력 → 화이트리스트 서브에이전트 라우팅·state.json 상태 계약 준수.
단순 질문·대화·조회는 제외.
```

스킬 갱신 시 사본 2곳(`~/.claude/skills/effort-router/`·등록본 `~/.claude/agents/`)에 재반영 후 `diff -r` 빈 출력으로 동기화 확인한다(진행 중 과업 디렉터리는 `-x` 제외).

## 다른 하니스에서 쓰기

라우팅(§2 화이트리스트·스폰)은 Claude Code 서브에이전트 시스템에 의존한다. 다른 환경에서는 티어 판정(§1)·실행 제약(§3)·Output Contract가 그대로 유효하고 라우팅은 §6 매핑을 따른다.

| 환경 | 어댓터 | 형태 |
|------|--------|------|
| Codex CLI | `platforms/codex.md` | AGENTS.md 병합 단편 + 커스텀 에이전트 TOML(`~/.codex/agents/`) role↔effort 매핑표 |
| Qwen Code | `platforms/qwen.md` | QWEN.md 병합 단편 |
| Gemini CLI | `platforms/gemini.md` | GEMINI.md 병합 단편 |
| GLM Coding Plan | `platforms/glm.md` | 백엔드 교체 매핑(Claude Code 하니스 유지) |
| ChatGPT 앱·GLM 앱 | `platforms/chat-app.md` | 붙여넣기 프롬프트 카드 |
| Grok Bot (Cursor) | `platforms/grok.md` | 스킬 저장 + Task/CloudAgent 매핑. xAI grok.com은 chat-app.md |

설치·붙여넣기 절차는 `platforms/README.md`. 어댓터는 본문의 파생 축약 이식본이다 — 규칙 충돌 시 SKILL.md가 우선한다.

## 핵심 원칙

- **존재 ≠ 허가** — 호출 가능한 에이전트는 §2 화이트리스트뿐. 테이블 밖 파일은 무시한다
- **증거기반 보고** — 완료 보고는 서술이 아니라 실행 명령 원문 + exit code. 상위 세션은 핵심 검증 1회 재실행
- **state.json 단일 writer** — 서브에이전트는 쓰지 않고 메인 세션이 패치. 재개는 대화 히스토리 추측 없이 `next`·`bundle`부터
- **gap이 다음 라운드를 만든다** — claims 전부 verified + CRITICAL·HIGH 부재일 때만 done. 라운드 상한 2회, 초과 시 사용자 에스컬레이션
- **라우팅의 본질은 effort 수치가 아니라 역할·산출물 분리** — effort는 환경 의존(프록시에서 조용히 강등될 수 있음, §3 실측)

## 근거·참조논문

- **역할 3분(Project Planner/Developer/QA)·증거번들·계보** — [1]에서 증류
- **상태계약 원형**(state.json·최소정보·명시적 실행 상태) — [2]
- **반복의 효과 실측**: 반복 3회 원샷 대비 +17~22pt(GameCraft Overall), 10회까지 상승(FrontierSWE Dominance) — [1]의 평가에서 관측. 이득의 원천은 호출량이 아니라 호출 사이를 잇는 상태다
- **외부 하니스 상태의 구성(Belief·Progress·Experience)과 선택적 상태 접근** — [4]. state.json 최소정보·압축 재개 원침의 이론적 배경

### 참조논문

1. Haoyang Yan, Min-le Su, Hangfan Zhang, Zhanhao Li, Chen Zhang, Shao Zhang, Yang Chen, Lei Bai, Shuyue Hu. *Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement.* arXiv:2609.01481 [cs.AI], 2026. — https://arxiv.org/abs/2609.01481
2. Sanket Badhe, Priyanka Tiwari, Jonghyun Chung. *SKILL.state: Scalable Long-Horizon Agent Skills.* arXiv:2608.26263 [cs.AI], 2026. — https://arxiv.org/abs/2608.26263
3. Tongxu Luo 외. *GameCraft-Bench: Can Agents Build Playable Games End-to-End in a Real Game Engine?* arXiv:2606.17861, 2026. — https://arxiv.org/abs/2606.17861
4. Xuying Ning, Dongqi Fu, Tianxin Wei, Hanqing Zeng, Yuanchen Bei, Bingxuan Li, Zihao Li, Qifan Wang, Xiang Shen, Yifan Wu, Jiayi Liu, Hong Li, Yinglong Xia, Xiangjun Fan, Hanghang Tong, Jingrui He. *EvoHarness-RL: Learning Self-Evolving Runtime Harness for Long-Horizon LLM Agents.* arXiv:2608.05446 [cs.LG], 2026. — https://arxiv.org/abs/2608.05446

FrontierSWE·ProgramBench는 [1]의 평가 벤치마크다(개별 링크는 [1] 본문 참조). 측정·검증 기록과 개정 이력(r4 결함 수정 → r6 병렬성 완화 → harness-compat 타 하니스 지원)은 `TESTS.md` 참조.

### 한국어 번역본 (`books/`)

참조논문의 한국어 번역 서적을 함께 동봉한다(korean-ebook 스킬로 제작):

| 파일 | 대응 |
|------|------|
| `books/하니스의_하니스_harness-of-harness-ko.pdf` | [1] HoH |
| `books/에이전트는_대화로_일하지_않는다_skill-state-ko.pdf` | [2] SKILL.state |
| `books/에이전트는 하니스를 배운다.pdf` | [4] EvoHarness-RL |
| `books/많이_줄수록_여럿일수록_정말_더_잘할까_agent-papers-2026-ko.pdf` | 맬티 에이전트 논문집(번역 시리즈) |
