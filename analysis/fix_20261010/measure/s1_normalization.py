"""(1) Tool-name normalization sensitivity (review M13).

Run: cd condition_study && python3 analysis/fix_20261010/measure/s1_normalization.py
Writes: s1_normalization.json
"""
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402
import confirm_analysis as CA  # noqa: E402  (imported read-only for its pooled() bootstrap)

GOSS = ["dev2_goss_text_poison", "dev2_goss_native_poison", "conf_goss_native_poison"]
GOSS_OTHER = ["dev2_goss_text_clean", "dev2_goss_native_clean", "def_goss_err_note"]
QWEN = ["dev2_q14n_native_poison", "dev2_q8n_native_poison", "dev2_q8n_text_poison",
        "dev2_q14n_native_clean", "dev2_q8n_native_clean",
        "conf_q14n_native_poison", "conf_q8n_native_poison", "conf_q14n_native_clean", "conf_q8n_native_clean"]
KEY = {"dev": "E_generic", "conf": "E_unknown"}


def summarize(run, which, extra=()):
    man, proto, t1, t2 = M.load_run(run, which, extra)
    n1 = len(t1)
    c1 = collections.Counter(r["_lab"] for r in t1)
    Y, U, lab1 = M.Y_table(t1, t2)
    asr = c1["MALICIOUS"] / n1
    pel = c1["BENIGN_CALL"] / n1
    conds = {}
    for c in sorted(Y, key=lambda x: list(man["conditions"]).index(x)):
        ym = M.ymean(Y, c)
        conds[c] = dict(ym, U=U[c], asr_err=round(asr + pel * ym["Y"], 4) if ym["n"] else None,
                        diff_vs_S_ok=M.paired_diff(Y, c) if c != "S_ok" else None)
    # eligible prefixes with no turn-2 rows (should be 0: alt eligibility is a subset of frozen)
    t2cases = {r["case_id"] for r in t2}
    missing = sorted(k for k, v in lab1.items() if v == "BENIGN_CALL" and k not in t2cases)
    out = {"run": run, "labeler": which, "protocol": proto, "agent": man["agent"], "arm": man["arm"],
           "n_t1": n1, "t1": dict(c1), "asr_t1": round(asr, 4), "eligible": c1["BENIGN_CALL"],
           "eligible_missing_turn2": missing, "cond": conds}
    if run.startswith("conf_") and man["arm"] == "poison":
        # registered-style statistic (confirm_analysis.pooled: B=5000, seed 20261010)
        out["H1_pooled_style"] = CA.pooled([CA.contrast_vals(Y, CA.diff("E_unknown", "S_ok"))])
        Yd, Ud, _ = M.Y_table(t1, t2, strata=("DIRECT_EXEC",))
        out["direct_stratum"] = {c: M.ymean(Yd, c) for c in Yd}
        out["H6_pooled_style_this_agent"] = CA.pooled([CA.contrast_vals(Yd, CA.diff("E_unknown", "S_ok"))])
    return out


def transitions(run, extra=()):
    _, proto, t1f, t2f = M.load_run(run, "frozen")
    _, _, t1a, t2a = M.load_run(run, "alt", extra)
    tr = {"turn1": collections.Counter(), "turn2": collections.Counter()}
    rows = []
    for name, F, A in (("turn1", t1f, t1a), ("turn2", t2f, t2a)):
        for rf, ra in zip(F, A):
            assert rf["case_id"] == ra["case_id"] and rf.get("condition") == ra.get("condition")
            if rf["_lab"] != ra["_lab"]:
                tr[name][f"{rf['_lab']}->{ra['_lab']}"] += 1
                calls = M.calls_of(rf.get("response") or {}, proto)
                rows.append({"turn": name, "case_id": rf["case_id"], "condition": rf.get("condition"),
                             "frozen": rf["_lab"], "alt": ra["_lab"],
                             "calls": [{"tool": c["tool"], "args": json.dumps(c["arguments"], ensure_ascii=False)[:160]}
                                       for c in calls]})
    return {k: dict(v) for k, v in tr.items()}, rows


def main():
    res = {"goss": {}, "goss_other": {}, "qwen": {}, "transitions": {}, "changed_rows": {}}
    for run in GOSS + GOSS_OTHER + QWEN:
        tr, rows = transitions(run)
        res["transitions"][run] = tr
        res["changed_rows"][run] = rows
    for run in GOSS:
        res["goss"][run] = {w: summarize(run, w) for w in ("frozen", "alt")}
        # extension: also strip 'tool/' (observed once in dev text; not in the review's list)
        res["goss"][run]["alt_plus_tool_slash"] = summarize(run, "alt", extra=("tool/",))
    for run in GOSS_OTHER:
        res["goss_other"][run] = {w: summarize(run, w) for w in ("frozen", "alt")}
    for run in QWEN:
        f, a = summarize(run, "frozen"), summarize(run, "alt")
        same = json.dumps(f["cond"], sort_keys=True) == json.dumps(a["cond"], sort_keys=True) and f["t1"] == a["t1"]
        res["qwen"][run] = {"identical_summary": same, "frozen_t1": f["t1"], "alt_t1": a["t1"],
                            "frozen_key": {c: f["cond"][c]["Y"] for c in f["cond"]},
                            "alt_key": {c: a["cond"][c]["Y"] for c in a["cond"]}}
    p = M.dump("s1_normalization.json", res)
    # compact console table
    for run in GOSS:
        for w in ("frozen", "alt", "alt_plus_tool_slash"):
            s = res["goss"][run][w]
            key = KEY["conf" if run.startswith("conf") else "dev"]
            d = s["cond"][key]["diff_vs_S_ok"]
            print(f"{run:26s} {w:20s} ASR_t1={s['asr_t1']:.3f} elig={s['eligible']:3d} "
                  f"Y(S_ok)={s['cond']['S_ok']['k']}/{s['cond']['S_ok']['n']} "
                  f"Y({key})={s['cond'][key]['k']}/{s['cond'][key]['n']} diff={d['diff']:+.3f} {d['ci']}"
                  + (f"  pooledH1={s['H1_pooled_style']}" if 'H1_pooled_style' in s else ""))
    for run in QWEN:
        print(run, "identical" if res["qwen"][run]["identical_summary"] else "CHANGED", res["transitions"][run])
    print("wrote", p)


if __name__ == "__main__":
    main()
