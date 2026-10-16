"""Post hoc decomposition of revival into 'the agent acts again' and 'it follows the poison when it acts'.
For each run and result message, BENIGN stratum:
  P(revive) = P(new call) * P(revive | new call)
A 'new call' is a next-turn tool call that is not a verbatim repeat of the turn-1 call (h7_test.continuation).
Compares S_ok and E_unknown in every native run, and the three non-terminal results (N_*) in the v5 runs.
P(revive | new call), error vs comparison: one-sided Fisher exact test. Descriptive and post hoc; not part of any Holm family."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import confirm_analysis as ca
from h7_test import continuation
from scipy.stats import fisher_exact

RUNS = [  # (label, run)
    ("Qwen3-14B", "conf_q14n_native_poison"), ("Qwen3-8B", "conf_q8n_native_poison"), ("gpt-oss-20b", "conf_goss_native_poison"),
    ("Llama-3.1-8B", "confM_llama31_native_poison"), ("Gemma-4-12B", "confM_gemma4_native_poison"),
    ("Qwen3-14B think", "confT_q14w_think_poison"), ("Qwen3-14B think (v4 새 사례)", "v4A_q14w_think_fresh"),
    ("Qwen3-8B think (v4)", "v4B_q8w_think_poison"), ("Qwen3-30B-A3B (v4)", "v4C_q30_native_poison"),
    ("Qwen3-14B (v5)", "v5_q14w"), ("Llama-3.1-8B (v5)", "v5_llama31"), ("Gemma-4-12B (v5)", "v5_gemma4"),
    ("Qwen3-30B-A3B (v5)", "v5_q30"), ("gpt-oss-20b (v5)", "v5_goss"),
]
N_CONDS = ['N_empty', 'N_more', 'N_pending']

def row(c):
    return {"n": c["n"], "new": c["rows_with_new_call"], "rev": c["revived_among_new"],
            "p_new": round(c["rows_with_new_call"] / c["n"], 3) if c["n"] else None,
            "p_rev_given_new": round(c["revived_among_new"] / c["rows_with_new_call"], 3) if c["rows_with_new_call"] else None}

def fisher(a, b):  # a, b: (rev, new); one-sided a > b
    if not a[1] or not b[1]: return None
    return fisher_exact([[a[0], a[1] - a[0]], [b[0], b[1] - b[0]]], alternative='greater')[1]

out = {}
for label, run in RUNS:
    try:
        _, Y, _ = ca.load_Y(run)
    except FileNotFoundError:
        continue
    cont = continuation(run, Y)
    r = {k: row(v) for k, v in cont.items() if k in ('S_ok', 'E_unknown', *N_CONDS)}
    if all(k in cont for k in N_CONDS):
        pooled = {"n": sum(cont[k]["n"] for k in N_CONDS), "rows_with_new_call": sum(cont[k]["rows_with_new_call"] for k in N_CONDS),
                  "revived_among_new": sum(cont[k]["revived_among_new"] for k in N_CONDS)}
        r["N_pooled"] = row(pooled)
    e = cont['E_unknown']
    r["fisher_err_vs_ok"] = fisher((e["revived_among_new"], e["rows_with_new_call"]), (cont['S_ok']["revived_among_new"], cont['S_ok']["rows_with_new_call"]))
    if "N_pooled" in r:
        r["fisher_err_vs_N"] = fisher((e["revived_among_new"], e["rows_with_new_call"]), (r["N_pooled"]["rev"], r["N_pooled"]["new"]))
    out[label] = {"run": run, **r}

if __name__ == '__main__':
    print(json.dumps(out, indent=1, ensure_ascii=False))
