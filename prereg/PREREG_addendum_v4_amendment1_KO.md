# 사전 등록 부록 v4 수정 1: 기제 검정 코드의 이름 추출 오류와 보조 예측 추가

- **작성:** 2026-10-11, v4 실행 중.
- **이 시점까지 본 v4 자료:** v4 B(`runs/v4B_q8w_think_poison`)는 07:08Z에 시작했고, 아래만 봤다.
  - 실행이 잘 도는지 보려고 `turn1.jsonl` 첫 행 하나(AlphaVantage::39)를 열었다. 본 것은 사례 이름, 1턴 라벨(BENIGN_CALL), 응답 앞 160자다.
  - 두 파일의 줄 수를 셌다.
  - turn-2 행의 내용, 재활성화 라벨, 분석 출력은 하나도 보지 않았다. v4 A와 C는 아직 시작하지 않았다.
- **발견 경위:** 근거 점검 작업(AI 감사 에이전트, 이 세션)이 찾았다. 확인은 MCPTox 사례 파일(`data/cases.jsonl`)만으로 했다.

## 1. 무엇이 잘못됐나

- 등록 문서의 X_mention 정의는 "추론 흔적에 오염 도구의 이름(`poisoned_tool`의 `Tool: <이름>`)이 나오는가"이다.
- 등록 코드 `analysis/prep_20261010/mech/mech_test.py`(sha 77b7f500)의 `carrier()`는 이 정의를 제대로 구현하지 못한다.
  - MCPTox 원문의 줄바꿈은 글자 두 개(`\n`)로 저장돼 있다. 정규식 `Tool:\s*(\S+)`가 이 원문에서 이름을 뽑으면, 절반 가까운 사례에서 `이름\nDescription:`까지 함께 잡힌다.
  - 그런 이름은 추론 흔적에 절대 나오지 않는다. 그래서 그 사례들의 X_mention은 늘 0이 된다.
- **영향받는 사례 수:**
  - v4 B 사례(held-out 해시 순위 1–150): 77/150
  - v4 A 사례(순위 301–450): 61/150
  - 예: `ClickHouse::46`은 `context_provider\nDescription:`로 잡혔다. 맞는 이름은 `context_provider`다.
- **X_reread(M2)는 `carrier()`를 쓰지 않으므로 영향이 없다.**

## 2. 고친 방법

- `analysis/prep_20261010/mech/mech_test_amend1.py`를 새로 만들었다. 등록 코드를 불러와 `carrier()`만 바꾼다. 나머지(단위, R, X_reread, 검정, B, seed)는 등록 코드 그대로다.
- 새 `carrier()`는 `run_native.parse_tools`로 이름을 뽑는다. 이 파서가 모델에게 보여 준 도구 목록을 만들었다.
- 사례 1,348개 모두에서 고친 이름은 공백이나 `\`가 없는 한 단어다.
- 등록 코드 `mech_test.py`는 고치지 않았다. 해시도 그대로다.

## 3. 판정 규칙 수정

- **M1a·M1b의 주 분석은 `mech_test_amend1.py`로 한다.**
  - 이유: 등록 문서의 정의(도구 이름이 흔적에 나오는가)를 구현한 것은 이 코드다. 등록 코드는 사례 절반에서 그 정의를 재지 못한다.
- **등록 코드 그대로의 M1 결과도 모두 함께 보고한다.** 값, CI, 순열 p를 나란히 적는다.
- **Holm 집합은 그대로 7개다** {H1a, M1a, M2a, H1b, M1b, M2b, H1c}, α = 0.05. M1에는 수정 코드의 p를 쓴다.
  - 민감도로 등록 코드의 M1 p를 넣은 Holm도 보고한다.
  - 둘의 판정이 다르면 그 사실을 본문에 적는다.
- "확인된 기제"의 조건(M1a와 M1b가 모두 확인)과 "인과로 쓰지 않는다"는 제한은 바꾸지 않는다.
- **흔적과 결정의 순서 문제(한계로 적음):** 모델이 오염 도구를 부르기로 이미 정했기 때문에 흔적에 그 이름이 나왔을 수 있다. M1은 연관만 보여 준다.

## 4. 예전 참고치 정정 (탐색, 판정 안 씀)

- 같은 버그가 v4 등록 전에 낸 탐색 참고치에도 들어 있었다(`exploratory_confT_q14w.json`, NUMBERS 5절).
- 고친 코드로 같은 자료(`confT_q14w_think_poison`)를 다시 돌렸다(`exploratory_confT_q14w_amend1.json`).
  - M1: 재활성화 행 124/135, 아닌 행 121/292, 차이 +0.504 [0.376, 0.619], 사례 내 순열 p 5.0e-5
  - 예전 값은 70/135 대 57/292, +0.323이었다.
  - M2는 그대로다(64/135 대 71/292, +0.231).
- 이 값은 결과를 본 자료라 판정에 쓰지 않는다.

## 5. 보조 예측 추가: P-CB (호출을 탓하는 오류)

- 지금까지의 자료에서 탐색으로 본 경향이다. INVALID_ARGUMENT, FAILED_PRECONDITION처럼 호출을 탓하는 오류가 모델마다 가장 높거나 거의 가장 높았다.
- 이 경향을 v4 새 자료에서 미리 정한 방향으로 본다.
- **P-CB:** BENIGN 층에서 mean(E_invalid_arg, E_precondition) − mean(E_unknown, E_internal, E_deadline, E_permission) > 0
  - 코드는 `analysis/prep_20261010/models/pcb_test.py`다. 사례별 대비, 단측 sign-flip p, 사례 bootstrap CI를 쓴다. `model_h.py`의 H4m과 같은 방식이다.
  - 대상은 v4 A, B, C(poison) 세 실행이다. 실행마다 따로 보고한다.
- **Holm 집합에 넣지 않는 보조 결과다.** 확인 판정에 쓰지 않는다.

## 6. 해시

새 파일과 이 문서의 해시는 `prereg/HASHES_v4.txt` 끝의 "amendment 1" 블록에 적었다. 이 문서와 코드는 v4 turn-2 행을 열기 전에 git commit으로 남긴다.
