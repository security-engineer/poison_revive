"""(3) Turn-2 outcome validity table from the manual audit (review M12, m14).

Inputs: audit_precision_items.json / audit_recall_items.json (built by s3_audit_sample.py) and the manual
judgments audit_precision_judgments.json / audit_recall_judgments.json.
Precision is a census of all BENIGN-stratum MALICIOUS rows of the three held-out poison runs.
Recall uses a fixed-seed random sample of non-MALICIOUS rows (45 error-condition + 15 S_ok rows per agent):
  FOR = false-omission rate among sampled non-MAL rows (Wilson 95% CI);
  implied recall = TP_hat / (TP_hat + FN_hat), TP_hat = precision * N_MAL, FN_hat = FOR * N_nonMAL;
  its conservative 95% lower bound uses the Wilson lower bound of precision and the Wilson upper bound of FOR.
Rows are clustered within cases; Wilson intervals treat rows as independent (case counts are reported too).

Run: cd condition_study && python3 analysis/fix_20261010/measure/s3_audit_stats.py
Writes: s3_audit_stats.json
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402
from cs_common import _constraint_ok, _norm_tool  # noqa: E402

AGENTS = {"qwen3-14b": "conf_q14n_native_poison", "qwen3-8b": "conf_q8n_native_poison", "gpt-oss-20b": "conf_goss_native_poison"}


def fam(cond):
    return "success" if cond == "S_ok" else "error"


def verdict_for(j, agent):
    v = j["verdict"]
    return v[agent] if isinstance(v, dict) else v


def population():
    """N_MAL and N_nonMAL (excluding transport/truncation U) per agent x family in the BENIGN stratum."""
    pop = {}
    for agent, run in AGENTS.items():
        man, proto, t1, t2 = M.load_run(run, "frozen")
        Y, U, _ = M.Y_table(t1, t2)
        for c, d in Y.items():
            k = (agent, fam(c))
            p = pop.setdefault(k, {"mal": 0, "nonmal": 0})
            p["mal"] += sum(d.values())
            p["nonmal"] += len(d) - sum(d.values())
    return pop


def weak_match(case_id, calls):
    """True if the row is MALICIOUS only through argument-free patterns (review m14)."""
    sig = M.SIGS[case_id]
    strong = weak = False
    for c in calls:
        for pat in sig.get("malicious", []):
            if _norm_tool(c["tool"]) != _norm_tool(pat["tool"]):
                continue
            if all(_constraint_ok(c["arguments"], k) for k in pat.get("args", [])):
                if pat.get("args"):
                    strong = True
                else:
                    weak = True
    return weak and not strong


def main():
    items = json.load(open(M.OUT / "audit_precision_items.json"))
    pj = json.load(open(M.OUT / "audit_precision_judgments.json"))["judgments"]
    rec = json.load(open(M.OUT / "audit_recall_items.json"))
    rj = json.load(open(M.OUT / "audit_recall_judgments.json"))["judgments"]
    pop = population()

    # ---- precision (row level census)
    P = collections.defaultdict(collections.Counter)
    Pcases = collections.defaultdict(lambda: collections.defaultdict(set))
    fps, ambs = [], []
    weak = collections.defaultdict(collections.Counter)
    for it in items:
        j = pj[it["item"]]
        for r in it["rows"]:
            v = verdict_for(j, r["agent"])
            k = (r["agent"], fam(r["condition"]))
            P[k][v] += 1
            P[(r["agent"], "all")][v] += 1
            Pcases[k][v].add(it["case_id"])
            if weak_match(it["case_id"], it["calls"]):
                weak[r["agent"]][v] += 1
                weak["all"][v] += 1
            if v != "TP":
                (fps if v == "FP" else ambs).append({"agent": r["agent"], "condition": r["condition"], "case_id": it["case_id"],
                                                     "calls": it["calls"], "verdict": v, "reason": j["reason"]})
    prec = {}
    for (agent, f), c in sorted(P.items()):
        n = sum(c.values())
        prec[f"{agent}|{f}"] = {"n_rows": n, "TP": c["TP"], "AMBIG": c["AMBIG"], "FP": c["FP"],
                                "precision_strict": round(c["TP"] / n, 4) if n else None,
                                "strict_wilson": M.wilson(c["TP"], n),
                                "precision_lenient": round((c["TP"] + c["AMBIG"]) / n, 4) if n else None,
                                "lenient_wilson": M.wilson(c["TP"] + c["AMBIG"], n),
                                "cases": {v: len(s) for v, s in Pcases.get((agent, f), {}).items()}}
    # ---- recall
    R = collections.defaultdict(collections.Counter)
    for r in rec:
        R[(r["agent"], fam(r["condition"]))][rj[r["row"]]["verdict"]] += 1
    recall = {}
    for (agent, f), c in sorted(R.items()):
        n_eval = sum(v for k, v in c.items() if k != "NA_TEXT_ONLY")
        out = {"n_sampled": sum(c.values()), "n_evaluable": n_eval, "counts": dict(c),
               "population": pop.get((agent, f))}
        for mode, fn in (("strict", c["FN"]), ("lenient", c["FN"] + c["AMBIG"])):
            for_hat = fn / n_eval if n_eval else None
            lo_for, hi_for = M.wilson(fn, n_eval)
            pk = prec.get(f"{agent}|{f}")
            p = pop.get((agent, f), {"mal": 0, "nonmal": 0})
            if pk and pk["n_rows"]:
                ph = pk[f"precision_{mode}"]
                plo = pk[f"{mode}_wilson"][0]
            else:
                ph = plo = None
            tp_hat = ph * p["mal"] if ph is not None else None
            fn_hat = for_hat * p["nonmal"] if for_hat is not None else None
            rec_hat = tp_hat / (tp_hat + fn_hat) if tp_hat is not None and (tp_hat + fn_hat) > 0 else None
            rec_lo = (plo * p["mal"]) / (plo * p["mal"] + hi_for * p["nonmal"]) if plo is not None and (plo * p["mal"] + hi_for * p["nonmal"]) > 0 else None
            out[mode] = {"FN": fn, "FOR": round(for_hat, 4) if for_hat is not None else None, "FOR_wilson": (lo_for, hi_for),
                         "implied_recall": round(rec_hat, 4) if rec_hat is not None else None,
                         "implied_recall_lower95_conservative": round(rec_lo, 4) if rec_lo is not None else None}
        recall[f"{agent}|{f}"] = out
    declared = {k: v["declared_in_text"] for k, v in rj.items() if v.get("declared_in_text")}
    # audit-corrected Y: set audited FP (strict: FP+AMBIG) MALICIOUS rows to 0 and recompute E_* - S_ok
    corrected = {}
    bad = {"strict": {(f["agent"], f["case_id"], f["condition"]) for f in fps + ambs},
           "lenient": {(f["agent"], f["case_id"], f["condition"]) for f in fps}}
    for agent, run in AGENTS.items():
        man, proto, t1, t2 = M.load_run(run, "frozen")
        Y0, _, _ = M.Y_table(t1, t2)
        corrected[agent] = {}
        for mode, B in bad.items():
            Y = {c: {k: (0 if (agent, k, c) in B else y) for k, y in d.items()} for c, d in Y0.items()}
            corrected[agent][mode] = {c: dict(M.ymean(Y, c), diff_vs_S_ok=(M.paired_diff(Y, c) if c != "S_ok" else None))
                                      for c in man["conditions"] if c in Y}
        corrected[agent]["frozen"] = {c: dict(M.ymean(Y0, c), diff_vs_S_ok=(M.paired_diff(Y0, c) if c != "S_ok" else None))
                                      for c in man["conditions"] if c in Y0}
    res = {"precision": prec, "false_positives": fps, "ambiguous": ambs, "recall": recall,
           "weak_pattern_MAL_rows": {k: dict(v) for k, v in weak.items()},
           "recall_rows_with_declared_text": declared, "audit_corrected_Y": corrected}
    p = M.dump("s3_audit_stats.json", res)
    for k, v in prec.items():
        print("PREC", k, v["n_rows"], "TP", v["TP"], "AMBIG", v["AMBIG"], "FP", v["FP"], "strict", v["precision_strict"], v["strict_wilson"],
              "lenient", v["precision_lenient"], v["lenient_wilson"])
    for k, v in recall.items():
        print("REC ", k, v["n_evaluable"], v["counts"], "strict FOR", v["strict"]["FOR"], v["strict"]["FOR_wilson"],
              "recall", v["strict"]["implied_recall"], ">=", v["strict"]["implied_recall_lower95_conservative"],
              "| lenient FOR", v["lenient"]["FOR"], v["lenient"]["FOR_wilson"], "recall", v["lenient"]["implied_recall"])
    print("weak-pattern MAL rows", res["weak_pattern_MAL_rows"])
    print("FP rows", len(fps), collections.Counter((f["agent"], f["case_id"]) for f in fps))
    print("AMBIG rows", len(ambs), collections.Counter((f["agent"], f["case_id"]) for f in ambs))
    for agent, d in corrected.items():
        for mode in ("frozen", "lenient", "strict"):
            e = d[mode]["E_unknown"]
            print("CORR", agent, mode, "S_ok", d[mode]["S_ok"]["k"], "/", d[mode]["S_ok"]["n"], "E_unknown", e["k"], "/", e["n"], e["diff_vs_S_ok"])
    print("wrote", p)


if __name__ == "__main__":
    main()
