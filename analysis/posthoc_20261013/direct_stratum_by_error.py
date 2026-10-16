"""Post hoc (2026-10-13): revival in the DIRECT stratum (first call went to the attacker's own poisoned tool),
by result message, for the held-out S1/S2/S13 runs (ranks 1-300). Rows with transport errors or truncation are
dropped. 'Revived' = turn-2 label MALICIOUS (frozen signatures v1.1). Exploratory: informs a possible
attacker-triggered-error study; not a registered test.
Run: cd condition_study && python3 analysis/posthoc_20261013/direct_stratum_by_error.py
"""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = {"Qwen3-14B": "conf_q14n_native_poison", "Qwen3-8B": "conf_q8n_native_poison",
        "gpt-oss-20b": "conf_goss_native_poison", "Llama-3.1-8B": "confM_llama31_native_poison",
        "Gemma-4-12B": "confM_gemma4_native_poison", "Qwen3-32B": "v12A_q32"}
BAD = {"ERROR_TRANSPORT", "TRUNCATED"}
tpl = {c["case_id"]: c["paradigm"] for c in map(json.loads, open(ROOT / "data/cases.jsonl"))}
out = {}
for name, run in RUNS.items():
    d = collections.defaultdict(lambda: [0, 0])
    tp = collections.Counter()
    for r in map(json.loads, open(ROOT / "runs" / run / "turn2.jsonl")):
        if r.get("t1_label") != "DIRECT_EXEC" or r.get("repeat", 0) != 0 or r["label"] in BAD:
            continue
        d[r["condition"]][0] += r["label"] == "MALICIOUS"
        d[r["condition"]][1] += 1
        if r["condition"] == "S_ok":
            tp[tpl[r["case_id"]]] += 1
    out[name] = {"run": run, "by_condition": {k: {"revived": v[0], "n": v[1]} for k, v in d.items()},
                 "templates_in_stratum": dict(tp)}
    print(name, {k: f"{v[0]}/{v[1]}" for k, v in sorted(d.items())}, dict(tp))
json.dump(out, open(Path(__file__).with_suffix(".json"), "w"), indent=1)
