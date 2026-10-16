# 사전 등록 부록 v8·v9 수정 1: gpt-oss-120b 서버 이미지를 NVIDIA 공식 vLLM으로 바꿈

- 작성: 2026-10-12 16:39 UTC. v8·v9의 실험 출력은 없다(첫 적재는 모델 출력 전에 멈췄다).
- 해시는 `prereg/HASHES_v8.txt` 끝의 수정 1 블록에 적는다.

## 무슨 일이 있었나

- 등록한 이미지 `soslab-vllm:latest`로 gpt-oss-120b를 띄우자, 가중치를 다 읽은 직후 MXFP4 가중치 재배열 단계에서 Worker의 남은 메모리가 4.9GB까지 떨어졌고 메모리 감시가 컨테이너를 멈췄다(DEVIATIONS §2.24). 이 이미지로는 메모리 규칙 안에서 이 모델을 띄울 수 없다.
- Worker에 있는 NVIDIA 공식 이미지 `nvcr.io/nvidia/vllm:26.07-py3`(vLLM 0.24.0 dev)로 실험 사례 없이 적재만 시험했다. 같은 Marlin 방식이지만 가장 낮을 때도 남은 메모리가 32GB였고, 서버가 떴다(KV 캐시 13.1GiB). 실험과 무관한 날씨 질문 하나로 도구 호출이 제대로 해석되는 것을 확인했다.

## 바꾸는 것

- v8과 v9의 gpt-oss-120b 서버만 이미지를 `nvcr.io/nvidia/vllm:26.07-py3`로 바꾸고, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`를 더한다. 나머지 서버 인자(메모리 66%, `--max-model-len 16384`, `--max-num-seqs 8`, openai 파서, openai_gptoss 추론 파서, 모델의 chat template, seed, enforce-eager)와 디코딩은 등록 그대로다.
- 시험 적재로 띄운 서버(`cs-worker-goss120nv`)를 내리지 않고 그대로 쓴다. v8 실행(`v8_goss120`)을 먼저 하고, 이어서 v9의 gpt-oss-120b 실행(`e2e3_gs_goss120`, `e2e9_fs_goss120`)을 같은 서버로 한다. 그 뒤 Gemma와 Qwen3-30B는 등록대로 `soslab-vllm:latest`로 띄운다(`runs/chain_v8_v9_amend1.sh`).
- 분석 코드와 검정은 바뀌지 않는다.

## 해석에 미치는 영향

- gpt-oss-20b(v5)와 gpt-oss-120b(v8)는 서버 vLLM 판이 다르다. 두 크기를 비교할 때 이 차이를 함께 적는다. 프롬프트는 모델의 chat template로 만들어지므로 같지만, 도구 호출 해석기 판이 다를 수 있다. 해석 실패는 타당성 기준(parser 누락 5%)으로 따로 본다.
