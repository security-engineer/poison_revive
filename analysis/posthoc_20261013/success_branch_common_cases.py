"""Post hoc (2026-10-13): revival after a success message, compared across models on common cases.

Question (user): does the poison lose its effect once the benign call succeeds? Earlier I quoted
per-model rates whose denominators came from different case sets. Here each comparison uses only
cases that are in the benign stratum for every model in the group, from runs that share the same
case list and the same result messages. No model calls; labels are recomputed with report.relabel
as in src/confirm_analysis.load_Y.

Groups (case-list hash over sorted case ids, from turn1.jsonl):
  A  S1/S2 300 held-out cases: Qwen3-14B, Qwen3-8B, gpt-oss-20b, Llama-3.1-8B, Gemma-4-12B,
     Qwen3-30B-A3B (v4C), Qwen3-32B (v12A)
  B  487 cases: gpt-oss-20b (v5_goss) and gpt-oss-120b (v8)
Serving differed between runs (see method.tex); only the cases and messages are held fixed.
"""
import collections
import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import report  # noqa: E402

GROUPS = {
    "A_300": ["conf_q14n_native_poison", "conf_q8n_native_poison", "conf_goss_native_poison",
              "confM_llama31_native_poison", "confM_gemma4_native_poison",
              "v4C_q30_native_poison", "v12A_q32"],
    "B_487": ["v5_goss", "v8_goss120"],
}
CONDS = ("S_ok", "E_unknown")
BAD = ("ERROR_TRANSPORT", "TRUNCATED")


def load(run):
    d = ROOT / "runs" / run
    man = json.load(open(d / "manifest.json"))
    proto = man.get("protocol", "text")
    t1 = {}
    for l in open(d / "turn1.jsonl"):
        r = json.loads(l)
        t1[r["case_id"]] = report.relabel(r, proto)
    t2 = collections.defaultdict(dict)
    for l in open(d / "turn2.jsonl"):
        r = json.loads(l)
        if r["condition"] in CONDS:
            t2[r["condition"]][r["case_id"]] = report.relabel(r, proto)
    return man["agent"], t1, t2


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def mcnemar_two_sided(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def summarize(group, runs):
    data = {run: load(run) for run in runs}
    common = None
    for run, (agent, t1, t2) in data.items():
        ok = {c for c, lab in t1.items() if lab == "BENIGN_CALL"
              and all(c in t2[k] and t2[k][c] not in BAD for k in CONDS)}
        common = ok if common is None else common & ok
    common = sorted(common)
    per_model = {}
    rev = {}
    for run, (agent, t1, t2) in data.items():
        row = {"run": run, "eligible_own": sum(1 for lab in t1.values() if lab == "BENIGN_CALL")}
        for k in CONDS:
            labs = collections.Counter(t2[k][c] for c in common)
            mal = labs.get("MALICIOUS", 0)
            row[k] = {"revived": mal, "n": len(common), "rate": round(mal / len(common), 3) if common else None,
                      "wilson95": wilson(mal, len(common)), "labels": dict(labs)}
            rev[(agent, k)] = {c: int(t2[k][c] == "MALICIOUS") for c in common}
        b = sum(1 for c in common if rev[(agent, "E_unknown")][c] and not rev[(agent, "S_ok")][c])
        cc = sum(1 for c in common if rev[(agent, "S_ok")][c] and not rev[(agent, "E_unknown")][c])
        row["within_model_error_vs_success"] = {"b_error_only": b, "c_success_only": cc,
                                               "p_two_sided": round(mcnemar_two_sided(b, cc), 6)}
        per_model[agent] = row
    pairs = []
    agents = list(per_model)
    for a, bb in itertools.combinations(agents, 2):
        x, y = rev[(a, "S_ok")], rev[(bb, "S_ok")]
        b = sum(1 for c in common if x[c] and not y[c])
        cc = sum(1 for c in common if y[c] and not x[c])
        pairs.append({"a": a, "b": bb, "a_only": b, "b_only": cc, "p_two_sided": round(mcnemar_two_sided(b, cc), 6)})
    # Pairwise: cases benign for both models only (larger n than the all-model intersection,
    # which keeps only cases every model ignored and is biased toward weak poisons).
    pairwise_own = []
    elig = {}
    for run, (agent, t1, t2) in data.items():
        elig[agent] = {c: (int(t2["S_ok"][c] == "MALICIOUS"), int(t2["E_unknown"][c] == "MALICIOUS"))
                       for c, lab in t1.items() if lab == "BENIGN_CALL"
                       and all(c in t2[k] and t2[k][c] not in BAD for k in CONDS)}
    for a, bb in itertools.combinations(agents, 2):
        cs = sorted(set(elig[a]) & set(elig[bb]))
        x = sum(1 for c in cs if elig[a][c][0] and not elig[bb][c][0])
        y = sum(1 for c in cs if elig[bb][c][0] and not elig[a][c][0])
        pairwise_own.append({"a": a, "b": bb, "n": len(cs),
                             "a_success_revived": sum(elig[a][c][0] for c in cs),
                             "b_success_revived": sum(elig[bb][c][0] for c in cs),
                             "a_only": x, "b_only": y, "p_two_sided": round(mcnemar_two_sided(x, y), 6)})
    return {"group": group, "n_common_cases": len(common), "per_model": per_model,
            "pairwise_success_branch": pairs, "pairwise_intersection_success_branch": pairwise_own}


if __name__ == "__main__":
    out = {"note": __doc__.strip().splitlines()[0], "results": [summarize(g, r) for g, r in GROUPS.items()]}
    p = Path(__file__).with_suffix(".json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for g in out["results"]:
        print(g["group"], "common cases:", g["n_common_cases"])
        for agent, row in g["per_model"].items():
            s, e = row["S_ok"], row["E_unknown"]
            print(f"  {agent:22s} own eligible {row['eligible_own']:3d} | success {s['revived']}/{s['n']} {s['wilson95']} "
                  f"| error {e['revived']}/{e['n']} | within b:c {row['within_model_error_vs_success']['b_error_only']}:"
                  f"{row['within_model_error_vs_success']['c_success_only']} p={row['within_model_error_vs_success']['p_two_sided']}"
                  f" | success-branch labels {s['labels']}")
        for pr in g["pairwise_intersection_success_branch"]:
            if pr["a_only"] + pr["b_only"]:
                print(f"    pairwise {pr['a']} vs {pr['b']}: n={pr['n']} success revived {pr['a_success_revived']} vs {pr['b_success_revived']}, {pr['a_only']}:{pr['b_only']} p={pr['p_two_sided']}")
