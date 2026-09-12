# effort-router

작업의 규모·위험도를 티어(S/M/L/XL)로 판정하고 단계별 모델·에포트를 배정하는 Codex·ChatGPT Skill. Codex CLI 기준 모든 실무 실행은 GPT-5.6-Luna max, 계획은 GPT-6-Astra medium, 검토는 GPT-6-Astra high로 보낸다.

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
| `agents/` | Claude Code 역할 정의 10종 + ChatGPT 데스크톱 UI 메타데이터 `openai.yaml` |
| `platforms/` | Codex·ChatGPT 실행 어댑터와 기타 하니스 파생 문서 |
| `TESTS.md` | 검증 프로토콜·측정 결과·라운드별 개정 이력·재현 절차 |

## 설치 (Codex + ChatGPT 데스크톱 앱)

### 1. Skill·custom agents 설치

```bash
mkdir -p ~/.codex/skills/effort-router
cp -R SKILL.md TESTS.md README.md agents platforms scripts ~/.codex/skills/effort-router/

mkdir -p ~/.codex/agents
cp platforms/codex-agents/*.toml ~/.codex/agents/
python3 scripts/configure_codex_plan.py --apply
```

### 2. `~/.codex/config.toml` 전역 설정

기존 파일을 통째로 교체하지 말고 다음 값을 병합한다. `model`과 `model_reasoning_effort`는 첫 TOML table보다 위의 root 영역에 둔다.

```toml
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

[agents]
enabled = true
```

이미 `[agents]`가 있으면 table을 다시 만들지 말고 `enabled = true`만 추가·수정한다. 기존 설치가 `[features]`의 `multi_agent = true`를 쓰며 정상 작동한다면 그대로 유지해도 된다.

### 3. `~/.codex/AGENTS.md` 전역 발동 규칙

기존 내용을 보존하고 다음 단편을 추가한다.

```markdown
코딩 작업 착수 전 설치된 `effort-router`를 사용한다. 모든 실무 실행은 GPT-5.6-Luna max,
계획은 GPT-6-Astra medium, 검토·문제 판정·보안 감사는 Plus에서 GPT-6-Astra medium, Pro에서 high를 사용한다.
역할 호출 전 configure_codex_plan.py로 요금제를 확인하고, 변경 시 --apply 적용 및 Codex 재시작 후 진행한다.
동일 접근 2회 실패 시 요금제별 Astra effort로 검토하고, 재계획은 Astra medium, 확정된 실행은 Luna max로 복귀한다.

## 실패 기반 영구 예방 규칙

- 주요 agent guide file은 Codex의 `AGENTS.md`, Claude Code의 `CLAUDE.md`, Cursor의 `.cursorrules`다.
- 관측되거나 재현된 과거 실패 1건을 영구 예방 규칙 1줄로 변환한다.
- 규칙은 실패 트리거와 필수/금지 행동을 포함하고, 다음 작업에서 준수 여부를 판정할 수 있어야 한다.
- 같은 실패의 기존 규칙이 있으면 새 줄을 만들지 말고 기존 규칙을 더 정확하게 고친다.
- 모든 저장소에 적용되는 규칙만 전역 파일에 두고, 프로젝트 고유 규칙은 가장 가까운 프로젝트 guide file에 둔다.
```

### 4. 재로드·검증

ChatGPT 데스크톱 앱의 Codex 화면은 같은 로컬 Skill과 `~/.codex` 설정을 공유한다. ChatGPT Work는 Skill을 사용할 수 있지만 로컬 custom-agent TOML을 전제로 하지 않으므로 앱의 model/reasoning control에서 같은 매핑을 직접 선택한다. 자세한 구분은 `platforms/chat-app.md`.

설치 후 Codex CLI·IDE·ChatGPT 앱을 재시작하고 검사한다.

```bash
python3 ~/.codex/skills/effort-router/scripts/verify_global_install.py
```

`PASS global effort-router installation`이 나와야 로컬 Skill, 전역 모델·effort, subagent 활성화, 전역 발동 규칙, 10개 custom agent가 모두 설치된 상태다. 상세 병합법은 `platforms/codex.md` 참조.

## 모델 매핑

**Plus:** 계획·검토 모두 Astra/medium. **Pro:** 계획 Astra/medium, 검토 Astra/high. 실무는 모두 Luna/max. 아래 표는 Pro 기준이다.

`python3 scripts/configure_codex_plan.py`는 현재 Codex 로그인 요금제를 자동 조회한다. `--apply`를 붙이면 백업 후 role TOML에 반영한다. 계정 전환 후 다시 실행하고 변경 시 Codex를 재시작한다. 감지 실패 시 임의 기본값을 쓰지 않으며 `--plan plus|pro`로 명시할 수 있다. [상세 절차](platforms/codex.md#요금제-자동-감지와-적용).

| 작업 | 모델·effort |
|---|---|
| 모든 실무 실행·구현·수정·테스트·검증 (XL 임계경로 포함) | `gpt-5.6-luna / max` |
| 명세 작성·계획·아키텍처 설계 | `gpt-6-astra / medium` |
| 스펙 검토·문제 분석·PR 판정·보안 감사 | `gpt-6-astra / high` |

`gpt-5.6-terra`는 기본 라우팅에서 제외한다. `max`는 단일 작업 깊이이며, `ultra`는 독립 병렬 작업이 있을 때만 쓴다.

## 다른 하니스에서 쓰기

Claude Code와 기타 환경에서는 티어 판정·증거 계약·Output Contract를 유지하고 각 하니스의 모델 체계로 치환한다.

| 환경 | 어댑터 | 형태 |
|------|--------|------|
| Codex CLI | `platforms/codex.md` | AGENTS.md 병합 단편 + 커스텀 에이전트 TOML(`~/.codex/agents/`) role↔effort 매핑표 |
| Qwen Code | `platforms/qwen.md` | QWEN.md 병합 단편 |
| Gemini CLI | `platforms/gemini.md` | GEMINI.md 병합 단편 |
| GLM Coding Plan | `platforms/glm.md` | 백엔드 교체 매핑(Claude Code 하니스 유지) |
| ZCode (GLM 백엔드) | `platforms/zcode.md` | 빌트인 스폰 + 역할 계약 주입 매핑. 백엔드 교체(Claude Code+GLM)는 glm.md |
| ChatGPT 앱 | `platforms/chat-app.md` | Codex 화면/Work/ChatGPT Classic 구분 |
| Grok Bot (Cursor) | `platforms/grok.md` | 스킬 저장 + Task/CloudAgent 매핑. xAI grok.com은 chat-app.md |

설치·붙여넣기 절차는 `platforms/README.md`. 어댑터는 본문의 파생 축약 이식본이다 — 규칙 충돌 시 SKILL.md가 우선한다.

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
- **기각 이력의 재주입(반려 근거 주입 계약)** — [5]. 기각된 후보를 다음 수정 호출에 되먹여 같은 실패 제안의 변형 반복을 막는 구조가 §2 반려 게이트의 반려 근거 주입 계약 원형이다
- **관측 기반 규칙의 외부 실측** — [5]. 결함 있는 손작업 전문가 그래프가 MultiChallenge 전체 성공률을 87.50 → 58.93로 깎았고(결함 있는 사전의 게이트 없는 1회 갱신은 53.57로 악화), 검증 게이트를 갖춘 반복 진화만 92.86로 회복시켰다 — '관측된 실패 1건 → 규칙 1줄' 실패 원장 원칙의 교차 근거
- **진단 조건부 재시도 > 무진단 재샘플링(난이도 클수록 격차 확대)·검증 통과 ≠ 요구 충실성(거짓 증명서 방지)** — [6]

### 참조논문

1. Haoyang Yan, Min-le Su, Hangfan Zhang, Zhanhao Li, Chen Zhang, Shao Zhang, Yang Chen, Lei Bai, Shuyue Hu. *Harness-of-Harness: Multi-Day Autonomous Software Development with Continual Improvement.* arXiv:2609.01481 [cs.AI], 2026. — https://arxiv.org/abs/2609.01481
2. Sanket Badhe, Priyanka Tiwari, Jonghyun Chung. *SKILL.state: Scalable Long-Horizon Agent Skills.* arXiv:2608.26263 [cs.AI], 2026. — https://arxiv.org/abs/2608.26263
3. Tongxu Luo 외. *GameCraft-Bench: Can Agents Build Playable Games End-to-End in a Real Game Engine?* arXiv:2606.17861, 2026. — https://arxiv.org/abs/2606.17861
4. Xuying Ning, Dongqi Fu, Tianxin Wei, Hanqing Zeng, Yuanchen Bei, Bingxuan Li, Zihao Li, Qifan Wang, Xiang Shen, Yifan Wu, Jiayi Liu, Hong Li, Yinglong Xia, Xiangjun Fan, Hanghang Tong, Jingrui He. *EvoHarness-RL: Learning Self-Evolving Runtime Harness for Long-Horizon LLM Agents.* arXiv:2608.05446 [cs.LG], 2026. — https://arxiv.org/abs/2608.05446
5. Yuxing Lu, Yicheng Chen, Shanchan Wu, Sercan Ö. Arık. *Procedural Graphs: Self-Evolving Execution Structures for LLM Agents.* arXiv:2609.09153 [cs.AI], 2026. — https://arxiv.org/abs/2609.09153
6. Joshua Ong Jun Leang, Haonan Li, Zheng Zhao, Xinyi Shang, Wenda Li, Zhengzhong Liu, Eric Xing, Shay B. Cohen, Eleonora Giunchiglia. *Magenta: Closing the Loop Between Mathematical Reasoning and Lean Verification.* arXiv:2609.11319 [cs.AI], 2026. — https://arxiv.org/abs/2609.11319

FrontierSWE·ProgramBench는 [1]의 평가 벤치마크다(개별 링크는 [1] 본문 참조). 측정·검증 기록과 개정 이력(r4 결함 수정 → r6 병렬성 완화 → r12 Procedural Graphs 증류 → harness-compat 타 하니스 지원)은 `TESTS.md` 참조.

### 한국어 번역본 (`books/`)

참조논문의 한국어 정독서를 함께 동봉한다(korean-ebook 스킬로 제작. 정독서 시리즈 전체는 [KLIC-BOOK](https://github.com/klic-co-kr/KLIC-BOOK)):

| 파일 | 대응 |
|------|------|
| `books/하니스의_하니스_harness-of-harness-ko.pdf` | [1] HoH |
| `books/에이전트는_대화로_일하지_않는다_skill-state-ko.pdf` | [2] SKILL.state |
| `books/에이전트는 하니스를 배운다.pdf` | [4] EvoHarness-RL |
| `books/절차_그래프의_이해_procedural-graphs-ko.pdf` | [5] Procedural Graphs — LLM 에이전트를 위한 자기진화 실행 구조 (2026-09) |
| `books/많이_줄수록_여럿일수록_정말_더_잘할까_agent-papers-2026-ko.pdf` | 멀티 에이전트 논문집(번역 시리즈) |
