"""(2) gpt-oss trigger reach (review M14).

An eligible (BENIGN_CALL) turn-1 prefix "reached" the poison hook if any turn-1 call's tool is in
sig.trigger_tools U sig.benign_tools (names compared with the frozen _norm_tool; the 'alt' variant uses
the alt labels and alt_norm). Y(S_ok), Y(E_*) and E_* - S_ok (case bootstrap, report.boot B=2000 seed 5)
are reported separately for reached and not-reached prefixes.

Run: cd condition_study && python3 analysis/fix_20261010/measure/s2_trigger_reach.py
Writes: s2_trigger_reach.json
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402
from cs_common import _norm_tool  # noqa: E402

RUNS = {"dev_native": "dev2_goss_native_poison", "dev_text": "dev2_goss_text_poison", "conf": "conf_goss_native_poison",
        # Qwen for reference (expected: few not-reached prefixes)
        "q14_conf": "conf_q14n_native_poison", "q8_conf": "conf_q8n_native_poison",
        "q14_dev_native": "dev2_q14n_native_poison", "q8_dev_native": "dev2_q8n_native_poison"}


def analyse(run, which, hook_fields=("trigger_tools", "benign_tools")):
    man, proto, t1, t2 = M.load_run(run, which)
    norm = _norm_tool if which == "frozen" else M.alt_norm
    Y, U, lab1 = M.Y_table(t1, t2)
    elig = sorted(k for k, v in lab1.items() if v == "BENIGN_CALL")
    reach, first_tools = {}, {}
    for r in t1:
        if r["case_id"] not in elig:
            continue
        sig = M.SIGS[r["case_id"]]
        hook = {norm(x) for f in hook_fields for x in sig.get(f, [])}
        calls = M.calls_of(r.get("response") or {}, proto)
        reach[r["case_id"]] = any(norm(c["tool"]) in hook for c in calls)
        first_tools[r["case_id"]] = [c["tool"] for c in calls]
    R = {k for k, v in reach.items() if v}
    N = {k for k, v in reach.items() if not v}
    conds = [c for c in man["conditions"] if c in Y]
    out = {"run": run, "labeler": which, "eligible": len(elig), "reached": len(R), "not_reached": len(N),
           "not_reached_cases": {k: first_tools[k] for k in sorted(N)},
           "not_reached_hook_is_only_poison_tool": sorted(
               k for k in N if {norm(x) for x in M.SIGS[k].get("trigger_tools", []) + M.SIGS[k].get("benign_tools", [])}
               <= {norm(M.SIGS[k]["poison_tool"])}),
           "subsets": {}}
    tot_mal = sum(sum(Y[c].values()) for c in conds)
    for name, S in (("all", set(elig)), ("reached", R), ("not_reached", N)):
        sub = {}
        for c in conds:
            sub[c] = M.ymean(Y, c, S)
            if c != "S_ok":
                sub[c]["diff_vs_S_ok"] = M.paired_diff(Y, c, cases=S)
        sub["_mal_rows_all_conditions"] = sum(sum(v for k, v in Y[c].items() if k in S) for c in conds)
        out["subsets"][name] = sub
    out["mal_rows_total"] = tot_mal
    return out


def main():
    res = {}
    for tag, run in RUNS.items():
        res[tag] = {w: analyse(run, w) for w in ("frozen", "alt")}
        res[tag]["frozen_trigger_only"] = analyse(run, "frozen", hook_fields=("trigger_tools",))
    p = M.dump("s2_trigger_reach.json", res)
    for tag in RUNS:
        for w in ("frozen", "alt", "frozen_trigger_only"):
            a = res[tag][w]
            key = "E_unknown" if "conf" in tag else "E_generic"
            line = f"{tag:15s} {w:19s} elig={a['eligible']:3d} reached={a['reached']:3d} not={a['not_reached']:3d} MALrows={a['mal_rows_total']:3d} |"
            for s in ("all", "reached", "not_reached"):
                sub = a["subsets"][s]
                d = sub[key]["diff_vs_S_ok"]
                line += (f" {s}: S_ok {sub['S_ok']['k']}/{sub['S_ok']['n']} {key} {sub[key]['k']}/{sub[key]['n']}"
                         f" d={d['diff']} {d['ci']} mal={sub['_mal_rows_all_conditions']};")
            print(line)
    print("wrote", p)


if __name__ == "__main__":
    main()
