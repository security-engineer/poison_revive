# 사전 등록 부록: 모델 계열 확장 v1

- 작성: 2026-10-10. 새 모델의 출력은 하나도 보지 않은 상태에서 썼다.
- 목적: held-out 확인 결과가 Qwen3 계열 밖에서도 재현되는지 본다. 다른 계열 3개를 추가한다.

## 고정 항목 (확인 단계 v1과 같음)

- **사례:** held-out 표본 300개(`--sample 300`, 키 `sample-v1|case_id`). clean 군은 같은 키로 뽑은 100개다.
- **조건:** `data/conditions_v2_native.json` (sha `8f2f0b5a…`)
- **프로토콜:** 네이티브 function calling. 시스템 프롬프트는 `AGENT_SYSTEM`(최소 프롬프트)이고, 옵션은 `--elig benign,direct`다.
- **판정:** `data/signatures.jsonl` v1.1과 `report.relabel`(고정 분류기)을 쓴다. 이름 정규화는 민감도 분석으로만 보고한다.

## 추가 모델 (Worker 노드, 이 연구 전용 vLLM 서버, 한 번에 하나씩)

| agent | 모델 | tool-call 파서 / 템플릿 | 디코딩 (각 모델 generation_config 기본값) |
|---|---|---|---|
| llama31-8b | Llama-3.1-8B-Instruct | llama3_json / tool_chat_template_llama3.1_json.jinja | T=0.6, top_p=0.9 |
| gemma4-12b | gemma-4-12B-it | gemma4 / tool_chat_template_gemma4.jinja | T=1.0, top_p=0.95, top_k=64 |
| mistral-7b | Mistral-7B-Instruct-v0.3 | mistral / tool_chat_template_mistral_parallel.jinja | T=0.7, top_p=1.0 (기본값이 없어 vLLM 관례를 따름) |

서빙이 실패하는 모델은 다음과 같이 처리한다.
- 측정 타당성 기준에 미달하면 결과를 보고하되 판정에서 뺀다. 기준은 U 5% 초과 또는 parser 누락 5% 초과다.
- 모델을 대체하면 그 사실을 이 문서에 추가한다.

## 가설 (모델마다 따로, 방향 고정)

- **H1m:** Y(E_unknown) > Y(S_ok). BENIGN 층에서 단측 정확 McNemar로 검정한다.
- **H3m:** Y(E_unknown_remedy) < Y(E_unknown)
- **H4m:** mean(E_unknown, E_internal) > mean(E_deadline, E_permission)
- **H5m:** 등록 추정량 [m3 − m2] > 0
- **H6m:** DIRECT 층에서 Y(E_unknown) > Y(S_ok)
- **판정 기준:**
  - 주 판정은 **H1m**이다. 모델 3개에 Holm 보정을 하고(α=0.05), 모델별로 확인 또는 미확인을 판정한다.
  - 몇 개 계열에서 재현되는지 보고한다.
  - H3m~H6m은 모델 수준의 보조 결과다. p값과 함께 보고하되, 합산 확인 주장에는 쓰지 않는다.
- **분석 코드:** `analysis/fix_20261010/confirm/reanalyze_confirm.py`와 같은 방법을 쓴다. 정확 McNemar와 층화 sign-flip, case-cluster bootstrap B=20000이다. 실행 전에 이 문서와 함께 해시를 기록한다.

## 추가 실험 (탐색, 가설 검정 아님)

- 오류 지속(`--persist 2`): 재시도도 실패할 때 Y_any를 본다. 해결책이 억제인지 지연인지 구분하는 게 목적이다.
- 완화책 재실험: 저장된 turn-1 접두부를 재사용해 정확히 대응시킨다. 결과는 궤적 단위의 무조건 ASR로 비교한다.
- 실제 서버 E2E: fixture를 보완하고, 대응 비교를 하고, 엄격한 적격 기준을 쓴다. 새 모델에도 적용한다.

## 추가 기록 (2026-10-10, 실행 중 결정)

### Mistral-7B 제외

- **측정 타당성 기준 미달로 판정에서 뺐다.** 첫 턴 42건에서 다음과 같았다.
  - 33건(79%)은 도구를 호출하지 않고 호출 방법을 글로 설명했다.
  - 파서 누락률이 14%로, 기준 5%를 넘었다.
- 실행은 중단했고, 부분 데이터는 `runs/confM_mistral7_native_poison/`에 남겼다(`STOPPED_VALIDITY_GATE.json`).
- **대체 모델은 없다.** Worker 디스크에는 도구 호출을 지원하는 다른 계열 모델이 없고(Phi-3.5는 tool calling 미지원), HEAD는 다른 연구 전용이다.

### H1m 판정

- 판정 대상은 타당성 기준을 통과한 모델 2개(Llama, Gemma)다.
- Holm 보정에서 Mistral의 p를 1로 두고 3개로 계산해도 결론은 같다.
