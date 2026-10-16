# 재코딩 A와 B의 출처

- `annotator_A.jsonl`, `annotator_B.jsonl`, `annotator_B_sample.json`의 작성자는 사람이 아니다.
  - 2026-10-10 Claude Code 세션(session 6f2afeea-03c3-4432-8950-7c45b47e23b0)이 띄운 AI 에이전트다.
  - 두 에이전트는 고정 서명을 보지 않고, 서로의 결과도 보지 않은 채 서명을 다시 작성했다.
- 따라서 `agreement.txt`의 κ(.978/.974)는 **AI끼리, 그리고 AI와 고정 서명 사이의 일관성**이다. 사람 평가자 간 신뢰도가 아니다.
- 고정 서명 v1.1 자체도 LLM 에이전트 인스턴스가 작성했다(OUTLINE Corrections M11).
- 사람 검증은 `analysis/human_validation_v1/`에 준비해 두었다. 평가자는 사람이어야 한다(AI가 만든 규칙을 AI가 검증하면 순환이다).
- 세션 기록: `/root/.claude/projects/-workspace-TAEYUN-mcp-security-research/6f2afeea-03c3-4432-8950-7c45b47e23b0.jsonl`
