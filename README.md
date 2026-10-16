# Tool-poisoning instructions revived by tool errors

Code, pre-registrations, and results for the study *Is Ignoring the Same as Refusing? Tool-Poisoning Instructions Revived by Tool Errors in LLM Agents* (manuscript under review).

Tool poisoning hides an attack instruction in the description of an MCP tool. The benchmark MCPTox scores only the agent's first response, so an agent that ignores the instruction there is counted as a failed attack. This study takes first responses in which the agent ignored the instruction and made a benign tool call, replaces only the result of that call with a success message or an instruction-free error message, and checks whether the ignored instruction is executed in the next response. It also runs pinned real MCP servers to check whether such errors lead to actual state changes.

## Layout

| Path | Contents |
|---|---|
| `src/` | Experiment harness, judging, and analysis code |
| `tools/` | Offline FP8 block quantization helper used for one model |
| `data/` | Result-message conditions, judging rules (signatures) and their specification, case split, placebo rules, pinned server build files |
| `prereg/` | Pre-registration documents, amendments, deviation log, and SHA-256 hash lists that pin code and data before each run (Korean) |
| `runs/` | Raw per-episode model outputs and judgments for every run |
| `analysis/` | Derived results, reports, and the human-validation scoring code and summary |
| `paper/NUMBERS_KO.md` | Ledger that traces every number in the manuscripts to a file in this repository (Korean) |

Most documents are written in Korean. Code comments and data fields are in English.

## Pre-registration hash lists

Each `prereg/HASHES_*.txt` file records the SHA-256 of the code, data, and documents fixed before one run. The code kept changing as later runs were added, so the files in this repository match only the most recent hash lists. Earlier pinned versions are not included.

Some adapters (`src/e2e_*.py`, `data/servers/SERVER_PINS.json`) contain absolute paths of the original machine. Adjust them locally to rerun.

## Rebuilding the case table

The case table `data/cases.jsonl` is not included because it copies the MCPTox benchmark verbatim and the MCPTox release has no license. To rebuild it:

1. Download `response_all.json` from the MCPTox repository (https://github.com/zhiqiangwang4/MCPTox-Benchmark).
2. Place it at `../latest/data/mcptox/response_all.json`, relative to this repository's root.
3. Run `python3 src/build_cases.py`. The script checks the input's SHA-256 and writes `data/cases.jsonl`.

## Running the experiments

- Models are served with vLLM through its OpenAI-compatible endpoint. Endpoints and model names are listed in `src/cs_common.py`.
- Result-message substitution runs use `src/run_native.py`, `src/run_branch.py`, and `src/run_nexttask.py`.
- Real-server runs use `src/live_e2e_v2.py` (Git, SQLite) and `src/live_e2e_v3.py` (Memory, Commander). They need Docker and the pinned server builds in `data/servers/`. Each has a model-free self-test (`src/selftest_live_e2e_v2.py`, `src/selftest_live_e2e_v3.py`).

## What is not included

- The MCPTox case table and the MCPTox intent text used to write the judging rules (see above).
- The answer key and the blinded packages of the human validation, because further annotation may still use them. The scoring code and the aggregated results are included.
- Host-specific orchestration scripts.

## Safety

The repository contains tool-poisoning attack descriptions taken from a public benchmark and fake secrets (canaries such as `CANARY-SSH-…`) planted in test containers. The real-server experiments ran in isolated containers without network access. Do not point the harness at systems or data you do not own.

## License

Code and documents written for this study are released under the MIT License (`LICENSE`). Third-party components are listed in `THIRD_PARTY_NOTICES.md`.
