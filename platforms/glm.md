# effort-router — GLM Coding Plan (백엔드 매핑)

대상: GLM Coding Plan(Z.ai)을 Claude Code 백엔드로 연결해 쓰는 환경. **GLM 앱(chat.z.ai)은 본 문서 대상이 아니다 — chat-app.md를 본다.**

> 본 문서는 effort-router SKILL.md(§1 티어·§3 제약·§6 매핑)의 파생 축약 이식본이다 — 규칙 충돌 시 본문이 우선한다. 본문 갱신 시 본 파일도 파생 갱신한다.

## 매핑의 본질 (본문 §6 GLM 불릿 축약)

- GLM Coding Plan은 하니스가 아니라 **백엔드 교체**다 — 공식 적용 대상에 Claude Code가 포함된다(docs.z.ai/devpack).
- 하니스 불변이므로 본문 전 계약 — §2 화이트리스트·§3 제약·§5 state.json — 이 **그대로 유효**하다. 치환·적용 제외 없음.
- 연결 설정(엔드포인트·키·env 값 등)은 Z.ai 공식 문서(docs.z.ai/devpack)를 따른다 — 본 문서는 구체 값을 단정하지 않는다.

## effort 강등 주의 (본문 §3 실측 인용)

- 카탈로그 미수록 모델(GLM 프록시)에서 xhigh는 high로 자동 강등이 실측됐다 — effort frontmatter는 설정값이며 실발효 값과 다를 수 있다.
- 강등되면 xhigh와 high 계획의 차이는 프롬프트 내용뿐이다. 라우팅의 본질은 effort 수치가 아니라 **역할·산출물 분리** — 강등 시에도 에이전트명(역할) 기준 라우팅을 유지한다.
- 슬롯 실체(sonnet/opus/haiku/fable의 실제 모델)는 프록시 매핑을 따른다 — 슬롯명과 실제 모델의 대응은 연결 설정 문서를 확인한다.
