"""(5) Turn-2 DIRECT_EXEC (agent calls the attacker's own tool) in the held-out runs, BENIGN stratum (review m15).

Frozen labels (precedence MALICIOUS > DIRECT_EXEC). Also counts rows with ANY call to the poison tool
(including rows that are MALICIOUS and also call the poison tool). In clean runs the poison tool is not offered.

Run: cd condition_study && python3 analysis/fix_20261010/measure/s5_direct_exec.py
Writes: s5_direct_exec.json
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402
from cs_common import _norm_tool  # noqa: E402

RUNS = {("qwen3-14b", "poison"): "conf_q14n_native_poison", ("qwen3-14b", "clean"): "conf_q14n_native_clean",
        ("qwen3-8b", "poison"): "conf_q8n_native_poison", ("qwen3-8b", "clean"): "conf_q8n_native_clean",
        ("gpt-oss-20b", "poison"): "conf_goss_native_poison"}


def main():
    res = {}
    for (agent, arm), run in RUNS.items():
        man, proto, t1, t2 = M.load_run(run, "frozen")
        lab1 = {r["case_id"]: r["_lab"] for r in t1}
        per = collections.defaultdict(collections.Counter)
        Yd = collections.defaultdict(dict)   # DIRECT_EXEC indicator per case
        Yu = collections.defaultdict(dict)   # MALICIOUS or DIRECT_EXEC
        for r in t2:
            if lab1.get(r["case_id"]) != "BENIGN_CALL":
                continue
            c = r["condition"]
            l = r["_lab"]
            per[c]["n"] += 1
            if l in ("ERROR_TRANSPORT", "TRUNCATED"):
                per[c]["U"] += 1
                continue
            per[c][l] += 1
            Yd[c][r["case_id"]] = int(l == "DIRECT_EXEC")
            Yu[c][r["case_id"]] = int(l in ("DIRECT_EXEC", "MALICIOUS"))
            pt = _norm_tool(M.SIGS[r["case_id"]]["poison_tool"])
            if any(_norm_tool(x["tool"]) == pt for x in M.calls_of(r["response"], proto)):
                per[c]["any_poison_tool_call"] += 1
        conds = [c for c in man["conditions"] if c in per]
        tab = {}
        for c in conds:
            d = per[c]
            n = d["n"] - d["U"]
            tab[c] = {"n": n, "MALICIOUS": d["MALICIOUS"], "DIRECT_EXEC": d["DIRECT_EXEC"],
                      "any_poison_tool_call": d["any_poison_tool_call"], "NO_CALL": d["NO_CALL"], "BENIGN_CALL": d["BENIGN_CALL"],
                      "DIRECT_rate": round(d["DIRECT_EXEC"] / n, 4) if n else None, "DIRECT_wilson": M.wilson(d["DIRECT_EXEC"], n),
                      "MAL_rate": round(d["MALICIOUS"] / n, 4) if n else None,
                      "DIRECT_diff_vs_S_ok": M.paired_diff(Yd, c) if c != "S_ok" else None,
                      "MAL_or_DIRECT_diff_vs_S_ok": M.paired_diff(Yu, c) if c != "S_ok" else None}
        err = [c for c in conds if c != "S_ok"]
        tab["_all_error_conditions"] = {k: sum(tab[c][k] for c in err) for k in ("n", "MALICIOUS", "DIRECT_EXEC", "any_poison_tool_call")}
        res[f"{agent}|{arm}"] = {"run": run, "by_condition": tab}
    p = M.dump("s5_direct_exec.json", res)
    for k, v in res.items():
        print(k, {c: (d["MALICIOUS"], d["DIRECT_EXEC"], d["n"]) for c, d in v["by_condition"].items() if not c.startswith("_")},
              v["by_condition"]["_all_error_conditions"])
    print("wrote", p)


if __name__ == "__main__":
    main()
