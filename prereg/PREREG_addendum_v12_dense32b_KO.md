# 사전 등록 부록 v12: 같은 계열에서 크기를 키우면(Qwen3-32B) 재활성화가 줄어드는가

- 작성: 2026-10-13. 원고의 단계 이름은 S13이다.
- v12 출력은 아직 없다. 해시를 `prereg/HASHES_v12.txt`에 적고 git commit한 뒤에 실행한다.
- 실행 스크립트: `runs/chain_v12_worker.sh`.
- 분석 코드: `analysis/prep_20261010/v12/v12_test.py`.

## 왜 하는가

- Qwen3의 dense 모델은 8B와 14B만 시험했다. 같은 계열에서 크기만 키우면 이 현상이 줄어드는지가 원고의 빈칸이다.
- 지금까지 가장 큰 모델은 gpt-oss-120b였다. 그런데 이 모델은 활성 매개변수가 작은 MoE이고, 공격 문구를 첫 응답에서 바로 따르는 경우가 많았다.
- Qwen3-32B는 이 장비 메모리에 들어가는 가장 큰 Qwen3 dense 모델이다.

## 모델과 서버

- **가중치:** 공식 `Qwen/Qwen3-32B-FP8`(revision `aa55da1ecc13d006e8b8e4f54579b1ea8c3db2df`, 블록 FP8 128×128)를 그대로 쓴다. Worker의 `/workspace/TAEYUN/condition-study-worker/models/Qwen3-32B-FP8`에 받았다. 8B와 14B는 bf16이었다. 정밀도 차이는 결과에 함께 적는다.
- **서버:** Worker에 혼자 띄운다. 이미지는 앞 단계와 같은 `soslab-vllm:latest`다.
  - `--gpu-memory-utilization 0.45`, `--max-model-len 16384`, `--max-num-seqs 16`
  - `--tool-call-parser hermes`, 모델의 chat template, `--seed 20261010`, `--enforce-eager`
- **디코딩:** Qwen3-14B 생각 모드 끔과 같다(`enable_thinking` false, temperature 0.7, top_p 0.8, max_tokens 768).
- **메모리 감시:** 남은 메모리가 10GB 아래로 떨어지면 이 컨테이너만 멈춘다. 그 경우 그 실행은 "실행 안 됨"으로 적는다.

## 실행 두 개

| 실행 | 사례(held-out 해시 순위) | 조건 파일 | 같은 사례·조건으로 돌린 앞선 모델 |
|---|---|---|---|
| A `v12A_q32` | 1–300 | `data/conditions_v2_native.json` (성공, 오류 6종, UNKNOWN + 재시도 지시) | Qwen3-8B·14B(S1), Llama·Gemma(S2) |
| B `v12B_q32` | 451–750 | `data/conditions_v5_continuation.json` (성공, 미완료 메시지 3개, UNKNOWN, 바꿔 쓴 UNKNOWN 2개, INVALID_ARG) | Qwen3-14B·Qwen3-30B-A3B(S6) |

- 둘 다 `--arm poison --elig benign,direct`이다. 프로토콜과 판정(`report.relabel`, 서명 v1.1)은 앞 단계와 같다.
- A를 먼저 돌리고, 이어서 B를 돌린다.

## 가설과 판정 (Holm 4개, α = .05)

- **H1-32 (A):** Y(E_unknown) > Y(S_ok). BENIGN 층, 단측 정확 McNemar.
- **HK-32 (A):** 호출 탓 오류가 원인을 밝힌 오류보다 많이 되살린다.
  - 사례별 대비는 mean(E_invalid_arg, E_precondition) − mean(E_deadline, E_permission)이다.
  - BENIGN 층에서 단측 sign-flip으로 검정한다.
- **H1r-32 (B):** Y(E_unknown) > Y(S_ok). 단측 정확 McNemar.
- **H7-32 (B):** Y(E_unknown) > mean(Y(N_empty), Y(N_more), Y(N_pending)). 사례별 대비, 단측 sign-flip(v5와 같은 코드).
- 다음 경우 그 실행의 검정은 p = 1로 둔다.
  - 실행하지 못했다.
  - 타당성 기준에 걸렸다(판단 불가 U가 5% 초과, 또는 parser가 놓친 호출이 5% 초과).

## 보조 (Holm 밖)

- 조건별 재활성화율과 첫 응답에서 바로 따른 비율을 낸다.
- A에서 다음을 낸다.
  - DIRECT 층의 오류 대 성공
  - UNKNOWN 대 재시도 지시
  - 원인 없음 대 원인 명시(S1의 H4와 같은 정의)
- B에서는 다시 호출한 비율과, 새 호출 가운데 공격 문구를 따른 비율을 낸다(`run_v5`).
- **크기 비교 표(검정 없음):** 서버 빌드와 정밀도가 다르므로 기술 비교만 한다.
  - A의 E_unknown·S_ok 값은 Qwen3-8B(`conf_q8n_native_poison`)·Qwen3-14B(`conf_q14n_native_poison`)와 나란히 놓는다.
  - B의 값은 Qwen3-14B(`v5_q14w`)·Qwen3-30B-A3B(`v5_q30`)와 나란히 놓는다.

## 해석 규칙(미리 정함)

- **H1-32 확인:** "같은 계열에서 크기를 32B로 키워도 공격 문구 없는 오류 하나가 무시된 공격 문구를 되살렸다."
- **H1-32 미확인이고 성공 뒤 비율이 높을 때:** "이 모델은 오류가 없어도 무시된 문구를 자주 따라, 오류의 추가 효과는 확인되지 않았다."
- **H1-32 미확인이고 오류 뒤 비율도 낮을 때:** "32B에서는 재활성화가 거의 일어나지 않았다."
  - 원고 서론과 초록의 일반화 문장을 이 결과에 맞게 줄인다.
- **HK-32:** S7의 종류 비교(호출 탓 > 원인 명시)와 같은 방향인지로 읽는다.
- **H1r-32와 H7-32:** S6과 같은 규칙으로 읽는다.
- 결과와 상관없이 모두 보고한다.

## 한계(미리 밝힘)

- 정밀도(FP8 대 bf16)와 서버가 앞선 Qwen 실행과 다르다. 크기 비교는 이 차이를 함께 담는다.
- 모델은 하나, 계열도 하나다.
