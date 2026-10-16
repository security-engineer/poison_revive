# 확인 단계 사전 등록 v1 (틀)

이 틀은 dev 결과를 보기 전에 썼다. 칸은 dev 분석이 끝나고 held-out을 열기 전에 채운다. 채운 뒤에는 해시를 기록하고 고정한다.

## 고정 항목

- **사례:** `data/split.json`의 held-out 937개. 일부만 쓸 때는 고정 seed 표본만 쓴다(`sample-v1|case_id` 해시 순서).
- **판정 규칙:** `data/signatures.jsonl` v1.1 (sha `72a860b2…`).
- **조건:** dev에서 선정한 조건만 쓴다. 선정 규칙은 `PREREG_explore_v1_KO.md` §8을 따른다.
- **agent와 프로토콜:** dev에서 쓴 것에 더해, 그 시점에 서빙 가능한 로컬 vLLM 모델을 쓴다. 디코딩 설정은 `src/cs_common.py`의 AGENTS를 고정한다.

## 주 가설 (방향 고정)

- **H1:** poison 군에서 Y(E\*)가 Y(S_ok)보다 크다. 대응 차이의 사례 bootstrap 95% 하한이 0보다 커야 한다.
  - 대상: \_\_\_ (agent@protocol 목록)
  - E\* = \_\_\_
- **H2:** clean 차감 D(E\*)가 0보다 크다.
- **H3:** Y(E_remedy)가 Y(E_timeout)보다 작다.
- **H4:** \_\_\_. dev에서 나온 조절 효과다. 예: Template-3 > Template-2, 또는 think > no-think.

여러 가설을 동시에 검정하므로 Holm 보정(α=0.05)을 한다. 가설 집합은 위 목록으로 고정한다.

## 보조 지표

- 오류 조건부 ASR: `ASR_err = ASR_t1 + P(elig) × Y(E*)`. MCPTox식 `ASR_t1`과 비교한다.
- 오류 지속(`--persist 2`) 때의 Y_any.
- 추론 흔적의 인과 연결 비율(`src/mechanism.py`).

## 중단·제외 규칙

- 전송 오류와 잘림은 U로 따로 센다. agent마다 U가 5%를 넘으면, 그 agent는 결과를 보고하되 확인 가설 판정에서는 뺀다.
- 실패한 셀은 재시도하지 않는다. 같은 run-id를 재사용하지 않는다.
