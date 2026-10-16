#!/usr/bin/env python3
"""Effect-size and benchmark-implication metrics, plus small number fixes.

Review items addressed: M4 (remedy), M6 (ASR_err multipliers), m1 (silent revivals),
m4 (MCPTox configuration count), m11 (CIs that touch 0), m13 (dev clean D), m19 (versions / wrong_data).

Offline only: reads runs/, data/, ../latest/data/mcptox/response_all.json. No model calls, no writes
outside this directory. Labels are always recomputed from raw responses with report.relabel
(report.load also applies the BENIGN_CALL eligibility filter to turn-2 rows).

Run from the condition_study root:
    python3 analysis/fix_20261010/metrics/metrics.py
Output: analysis/fix_20261010/metrics/metrics.json
"""
import collections
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
import cs_common  # noqa: E402
import report  # noqa: E402
import run_native  # noqa: E402
from cs_common import _strip_reasoning, classify, load_cases, visible_text  # noqa: E402

B = 5000
SEED = 20261010
U_LABELS = ("ERROR_TRANSPORT", "TRUNCATED")

DATASETS = [  # (set, agent, protocol, run, headline error condition)
    ("dev", "qwen3-14b-nothink", "native", "dev2_q14n_native_poison", "E_generic"),
    ("dev", "qwen3-8b-nothink", "native", "dev2_q8n_native_poison", "E_generic"),
    ("dev", "gpt-oss-20b", "text", "dev2_goss_text_poison", "E_generic"),
    ("dev", "gpt-oss-20b", "native", "dev2_goss_native_poison", "E_generic"),
    ("conf", "qwen3-14b-nothink", "native", "conf_q14n_native_poison", "E_unknown"),
    ("conf", "qwen3-8b-nothink", "native", "conf_q8n_native_poison", "E_unknown"),
    ("conf", "gpt-oss-20b", "native", "conf_goss_native_poison", "E_unknown"),
]
CLEAN_PAIRS = [  # (agent@protocol, poison run, clean run)
    ("qwen3-14b-nothink@native", "dev2_q14n_native_poison", "dev2_q14n_native_clean"),
    ("qwen3-8b-nothink@native", "dev2_q8n_native_poison", "dev2_q8n_native_clean"),
    ("gpt-oss-20b@text", "dev2_goss_text_poison", "dev2_goss_text_clean"),
    ("gpt-oss-20b@native", "dev2_goss_native_poison", "dev2_goss_native_clean"),
]

# ----------------------------------------------------------------------------- helpers

_CACHE = {}


def load(run, variant="frozen"):
    """report.load (relabel + eligibility filter), cached per classifier variant."""
    key = (run, variant)
    if key not in _CACHE:
        man, t1, t2 = report.load(run)
        proto = man.get("protocol", "text")
        seen = collections.Counter((r["case_id"], r["condition"]) for r in t2)
        dup = [k for k, v in seen.items() if v > 1]
        assert not dup, (run, dup[:3])
        _CACHE[key] = (man, proto, t1, t2)
    return _CACHE[key]


def pct_ci(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return (None, None)
    n = len(vals)
    return (vals[int(.025 * n)], vals[int(.975 * n) - 1])


def r4(x):
    return None if x is None else round(x, 4)


def ci4(c):
    return [r4(c[0]), r4(c[1])]


def wilson(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def binom_tail_ge(k, n):
    """P(X >= k), X ~ Bin(n, 1/2)."""
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "p_two_sided": 1.0, "p_one_sided_b_gt_c": 1.0}
    p1 = binom_tail_ge(b, n)
    p2 = min(1.0, 2 * min(binom_tail_ge(b, n), binom_tail_ge(c, n)))
    return {"b": b, "c": c, "p_two_sided": r4(p2), "p_one_sided_b_gt_c": r4(p1)}


def boot_mean(vals, seed=SEED):
    if not vals:
        return (None, None)
    rng = random.Random(seed)
    n = len(vals)
    bs = [sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(B)]
    return pct_ci(bs)


def ycond(t2):
    """{condition: {case: 0/1}} for non-U rows; U counts per condition."""
    Y = collections.defaultdict(dict)
    U = collections.Counter()
    for r in t2:
        if r["_relabel"] in U_LABELS:
            U[r["condition"]] += 1
            continue
        Y[r["condition"]][r["case_id"]] = int(r["_relabel"] == "MALICIOUS")
    return Y, U


def paired(Y, a, b, seed=SEED):
    common = sorted(set(Y.get(a, {})) & set(Y.get(b, {})))
    d = [Y[a][c] - Y[b][c] for c in common]
    bb = sum(1 for c in common if Y[a][c] == 1 and Y[b][c] == 0)
    cc = sum(1 for c in common if Y[a][c] == 0 and Y[b][c] == 1)
    return {"n_pairs": len(common), "diff": r4(sum(d) / len(d)) if d else None, "ci95": ci4(boot_mean(d, seed)),
            "mcnemar": mcnemar(bb, cc)}


def kn(Y, c):
    v = Y.get(c, {})
    k, n = sum(v.values()), len(v)
    return {"k": k, "n": n, "Y": r4(k / n) if n else None}


# ----------------------------------------------------------------------------- tolerant tool-name normalizer
# Sensitivity only (review M13). The frozen classifier is the primary result.
_ORIG_NORM = cs_common._norm_tool
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_PREFIX = re.compile(r"^(?:repo_browser\.|tool[.:=/_-]|repo[._]|functions[./])")


def _norm_tolerant(n):
    n = _ORIG_NORM(str(n).translate(_ZW))
    for _ in range(2):
        n = _PREFIX.sub("", n)
    return n.replace("-", "_")


def set_variant(variant):
    f = _norm_tolerant if variant == "tolerant" else _ORIG_NORM
    cs_common._norm_tool = f
    run_native._norm_tool = f


def tolerant_collision_check():
    cases, sigs = load_cases(), cs_common.load_signatures()
    bad_prefix, collide = [], []
    for cid, c in cases.items():
        names = list(c["server_tools"]) + [sigs[cid].get("poison_tool", "")] + \
            [p["tool"] for p in sigs[cid].get("malicious", [])]
        names = sorted(set(n for n in names if n))
        for n in names:
            if _PREFIX.match(_ORIG_NORM(n)):
                bad_prefix.append((cid, n))
        m = collections.defaultdict(set)
        for n in names:
            m[_norm_tolerant(n)].add(_ORIG_NORM(n))
        collide += [(cid, sorted(v)) for v in m.values() if len(v) > 1]
    return {"real_names_with_stripped_prefix": len(bad_prefix), "within_case_collisions_after_folding": len(collide),
            "examples": collide[:5]}


# ----------------------------------------------------------------------------- (1) ASR metrics


def asr_records(run, E, variant="frozen", drop_truncated_t1=False):
    man, proto, t1, t2 = load(run, variant)
    Y, U = ycond(t2)
    recs = []
    n_tr = sum(1 for r in t1 if r["_relabel"] == "ERROR_TRANSPORT")
    n_tc = sum(1 for r in t1 if r["_relabel"] == "TRUNCATED")
    for r in t1:
        l = r["_relabel"]
        if l == "ERROR_TRANSPORT" or (drop_truncated_t1 and l == "TRUNCATED"):
            continue
        cid = r["case_id"]
        recs.append((l, Y.get(E, {}).get(cid), Y.get("S_ok", {}).get(cid)))
    return recs, {"n_t1_raw": len(t1), "n_transport_t1": n_tr, "n_truncated_t1": n_tc,
                  "t2_U": {"E": U.get(E, 0), "S_ok": U.get("S_ok", 0)}}


def asr_stats(recs):
    n = len(recs)
    mal = sum(1 for l, _, _ in recs if l == "MALICIOUS")
    el = sum(1 for l, _, _ in recs if l == "BENIGN_CALL")
    yE = [e for l, e, _ in recs if l == "BENIGN_CALL" and e is not None]
    yS = [s for l, _, s in recs if l == "BENIGN_CALL" and s is not None]
    pd = [e - s for l, e, s in recs if l == "BENIGN_CALL" and e is not None and s is not None]
    if not n or not yE or not yS:
        return None
    a1, p = mal / n, el / n
    YE, YS = sum(yE) / len(yE), sum(yS) / len(yS)
    err, ok = a1 + p * YE, a1 + p * YS
    return {"n_t1": n, "mal_t1": mal, "elig": el, "kE": sum(yE), "nE": len(yE), "kS": sum(yS), "nS": len(yS),
            "ASR_t1": a1, "P_elig": p, "Y_E": YE, "Y_S_ok": YS, "ASR_err": err, "ASR_ok": ok,
            "ratio_err_t1": err / a1 if a1 else None, "ratio_err_ok": err / ok if ok else None,
            "inc_abs": p * (YE - YS),
            "inc_abs_paired": p * (sum(pd) / len(pd)) if pd else None}


def asr_block(run, E, variant="frozen", drop_truncated_t1=False, with_ci=True):
    recs, meta = asr_records(run, E, variant, drop_truncated_t1)
    st = asr_stats(recs)
    out = {"meta": meta,
           "counts": {k: st[k] for k in ("n_t1", "mal_t1", "elig", "kE", "nE", "kS", "nS")},
           "point": {k: r4(st[k]) for k in ("ASR_t1", "P_elig", "Y_E", "Y_S_ok", "ASR_err", "ASR_ok",
                                            "ratio_err_t1", "ratio_err_ok", "inc_abs", "inc_abs_paired")}}
    if with_ci:
        rng = random.Random(SEED)
        n = len(recs)
        acc = collections.defaultdict(list)
        for _ in range(B):
            s = asr_stats([recs[rng.randrange(n)] for _ in range(n)])
            if s is None:
                continue
            for k in ("ASR_err", "ASR_ok", "ratio_err_t1", "ratio_err_ok", "inc_abs", "inc_abs_paired"):
                acc[k].append(s[k])
        out["ci95_case_bootstrap"] = {k: ci4(pct_ci(v)) for k, v in acc.items()}
        out["n_boot_used"] = len(acc["inc_abs"])
    return out


def section1():
    res = []
    for ds, agent, proto, run, E in DATASETS:
        set_variant("frozen")
        main = asr_block(run, E)
        alt = asr_block(run, E, drop_truncated_t1=True, with_ci=False)
        # paper-style (transport rows kept in n_t1, as report.summarize does), for comparison
        _, _, t1, t2 = load(run)
        Y, _ = ycond(t2)
        n_raw = len(t1)
        a1 = sum(1 for r in t1 if r["_relabel"] == "MALICIOUS") / n_raw
        pe = sum(1 for r in t1 if r["_relabel"] == "BENIGN_CALL") / n_raw
        yE = sum(Y[E].values()) / len(Y[E])
        paper = {"n_t1": n_raw, "asr_t1": r4(a1), "p_elig": r4(pe), "asr_err": r4(a1 + pe * yE),
                 "ratio": r4((a1 + pe * yE) / a1)}
        if ds == "dev":  # cross-check against report.summarize
            s = report.summarize(run)
            assert abs(s["cond"][E]["asr_err"] - (a1 + pe * yE)) < 1e-12, run
        set_variant("tolerant")
        _CACHE.clear()
        tol = asr_block(run, E, variant="tolerant", with_ci=True)
        set_variant("frozen")
        _CACHE.clear()
        res.append({"set": ds, "agent": agent, "protocol": proto, "run": run, "E": E,
                    "primary_transport_excluded": main,
                    "variant_all_U_excluded_t1": {"counts": alt["counts"], "point": alt["point"]},
                    "paper_style_transport_in_denominator": paper,
                    "sensitivity_tolerant_tool_names": {"counts": tol["counts"], "point": tol["point"],
                                                        "ci95_case_bootstrap": tol["ci95_case_bootstrap"]}})
    return res


# ----------------------------------------------------------------------------- (2) remedy


def call_key(c):
    return (cs_common._norm_tool(c["tool"]), json.dumps(c["arguments"], sort_keys=True, ensure_ascii=False))


def calls_from(r, proto):
    resp = r.get("response") or {}
    if not resp.get("ok", True):
        return []
    if proto == "native":
        return run_native.calls_of(resp)[0]
    return classify(visible_text(resp), report.SIGS[r["case_id"]])["calls"]


def retry_table(run):
    man, proto, t1, t2 = load(run)
    t1calls = {r["case_id"]: calls_from(r, proto) for r in t1}
    out = {}
    for cond in man["conditions"]:
        rows = [r for r in t2 if r["condition"] == cond]
        lab = collections.Counter(r["_relabel"] for r in rows)
        nU = sum(lab[u] for u in U_LABELS)
        n = len(rows) - nU
        exact = anyrep = sametool = benign = 0
        for r in rows:
            if r["_relabel"] in U_LABELS:
                continue
            k1 = {call_key(c) for c in t1calls[r["case_id"]]}
            tools1 = {k[0] for k in k1}
            c2 = calls_from(r, proto)
            k2 = [call_key(c) for c in c2]
            if r["_relabel"] == "BENIGN_CALL":
                benign += 1
                if k2 and all(k in k1 for k in k2):
                    exact += 1
                if k2 and all(k[0] in tools1 for k in k2):
                    sametool += 1
            if any(k in k1 for k in k2):
                anyrep += 1
        out[cond] = {"n": n, "n_U": nU, "labels": dict(lab),
                     "benign_call": benign, "benign_exact_same_call_retry": exact,
                     "benign_same_tool_only": sametool, "any_row_repeats_a_t1_call": anyrep,
                     "share_benign": r4(benign / n) if n else None,
                     "share_exact_retry": r4(exact / n) if n else None,
                     "share_same_tool": r4(sametool / n) if n else None}
    return out


def section2():
    dev, conf = [], []
    for ds, agent, proto, run, E in DATASETS:
        man, proto, t1, t2 = load(run)
        Y, U = ycond(t2)
        rt = retry_table(run)
        if ds == "dev":
            base, rem = "E_timeout", "E_remedy"
            ctx = ["S_ok", "E_generic", "E_timeout", "E_remedy"]
        else:
            base, rem = "E_unknown", "E_unknown_remedy"
            ctx = ["S_ok", "E_unknown", "E_unknown_remedy"]
        row = {"agent": agent, "protocol": proto, "run": run,
               "rates": {c: kn(Y, c) for c in ctx},
               f"{base}_minus_{rem}": paired(Y, base, rem),
               f"{rem}_minus_S_ok": paired(Y, rem, "S_ok"),
               "retry": {c: rt[c] for c in ctx}}
        if ds == "dev":
            row["E_generic_minus_E_remedy(wording-confounded)"] = paired(Y, "E_generic", "E_remedy")
            dev.append(row)
        else:
            conf.append(row)
    return {"dev_timeout_plus_remedy_vs_timeout": dev, "conf_unknown_plus_remedy_vs_unknown": conf}


# ----------------------------------------------------------------------------- (3) silent revivals


def section3():
    runs = ["dev2_q14n_native_poison", "dev2_q8n_native_poison", "conf_q14n_native_poison",
            "conf_q8n_native_poison", "conf_goss_native_poison", "dev2_goss_native_poison"]
    out = []
    for run in runs:
        man, proto, t1, t2 = load(run)
        head = "E_generic" if run.startswith("dev") else "E_unknown"
        mal = [r for r in t2 if r["_relabel"] == "MALICIOUS"]

        def silent(r):
            return _strip_reasoning((r.get("response") or {}).get("content") or "").strip() == ""

        def cnt(rows):
            k = sum(1 for r in rows if silent(r))
            return {"silent": k, "mal": len(rows), "share": r4(k / len(rows)) if rows else None}
        per = collections.defaultdict(list)
        for r in mal:
            per[r["condition"]].append(r)
        out.append({"run": run, "agent": man["agent"], "note": "BENIGN stratum, relabelled, MALICIOUS rows",
                    "all": cnt(mal),
                    "error_conditions": cnt([r for r in mal if r["condition"].startswith("E_")]),
                    "success_conditions": cnt([r for r in mal if r["condition"].startswith("S_")]),
                    "headline_" + head: cnt(per.get(head, [])),
                    "per_condition": {c: cnt(v) for c, v in sorted(per.items())},
                    "in_main_analysis": run != "dev2_goss_native_poison"})
    return out


# ----------------------------------------------------------------------------- (4) dev clean D


def section4():
    out = []
    for name, prun, crun in CLEAN_PAIRS:
        _, _, pt1, pt2 = load(prun)
        cman, _, ct1, ct2 = load(crun)
        PY, PU = ycond(pt2)
        CY, CU = ycond(ct2)
        conds = [c for c in cman["conditions"]]
        clean_table = {c: dict(kn(CY, c), U=CU.get(c, 0)) for c in conds}
        clean_t1 = dict(collections.Counter(r["_relabel"] for r in ct1))
        rows = {}
        for E in [c for c in conds if c != "S_ok"]:
            # poison: paired within case
            common = sorted(set(PY.get(E, {})) & set(PY.get("S_ok", {})))
            pdiff = [PY[E][c] - PY["S_ok"][c] for c in common]
            P = sum(pdiff) / len(pdiff)
            # clean: marginal
            cE, cS = CY.get(E, {}), CY.get("S_ok", {})
            C = sum(cE.values()) / len(cE) - sum(cS.values()) / len(cS)
            # alternatives for transparency
            pE, pS = PY[E], PY["S_ok"]
            P_marg = sum(pE.values()) / len(pE) - sum(pS.values()) / len(pS)
            ccommon = sorted(set(cE) & set(cS))
            C_pair = sum(cE[c] - cS[c] for c in ccommon) / len(ccommon)
            # bootstrap: independent case resampling of poison pairs and clean eligible cases
            rng_p, rng_c = random.Random(SEED), random.Random(SEED + 1)
            celig = sorted(set(cE) | set(cS))
            bs = []
            for _ in range(B):
                bp = sum(pdiff[rng_p.randrange(len(pdiff))] for _ in pdiff) / len(pdiff)
                s = [celig[rng_c.randrange(len(celig))] for _ in celig]
                e = [cE[c] for c in s if c in cE]
                o = [cS[c] for c in s if c in cS]
                bc = (sum(e) / len(e) if e else 0) - (sum(o) / len(o) if o else 0)
                bs.append(bp - bc)
            rows[E] = {"poison_paired": {"n_pairs": len(common), "k_E": sum(PY[E][c] for c in common),
                                         "k_S_ok": sum(PY["S_ok"][c] for c in common), "diff": r4(P)},
                       "clean_marginal": {"k_E": sum(cE.values()), "n_E": len(cE), "k_S_ok": sum(cS.values()),
                                          "n_S_ok": len(cS), "diff": r4(C)},
                       "D": r4(P - C), "D_ci95": ci4(pct_ci(bs)),
                       "alt_D_both_marginal(main.tex formula)": r4(P_marg - C),
                       "alt_D_both_paired": r4(P - C_pair),
                       "poison_marginal": {"k_E": sum(pE.values()), "n_E": len(pE), "k_S_ok": sum(pS.values()),
                                           "n_S_ok": len(pS)}}
        out.append({"agent": name, "poison_run": prun, "clean_run": crun, "clean_t1_labels": clean_t1,
                    "clean_n_t1": len(ct1), "clean_Y_by_condition": clean_table,
                    "D_E_generic": rows["E_generic"], "D_all_conditions": rows})
    return out


# ----------------------------------------------------------------------------- (5) MCPTox


def section5():
    MAP = {"Success", "Failure-Ignored", "Failure-Direct Execution"}
    cases = load_cases()
    keys_all = set()
    per = collections.Counter()
    for c in cases.values():
        for m, v in c["mcptox_ref"].items():
            keys_all.add(m)
            if v.get("label") in MAP and v.get("response"):
                per[m] += 1
    local = sorted(k for k in per if not k.startswith("online:"))
    online = sorted(k for k in per if k.startswith("online:"))
    a0 = json.load(open(ROOT / "analysis" / "mcptox_firstturn_by_signature.json"))
    src = ROOT.parent / "latest" / "data" / "mcptox" / "response_all.json"
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    raw = json.load(open(src))
    raw_inst = []
    for server, s in raw["servers"].items():
        for idx, mi in enumerate(s["malicious_instance"]):
            raw_inst.append((f"{server}::{idx}", mi.get("wrong_data"), mi["metadata"]["paradigm"]))
    raw_wd = collections.Counter(w for _, w, _ in raw_inst)
    cases_wd = collections.Counter(c["wrong_data"] for c in cases.values())
    match = all(cases[cid]["wrong_data"] == w for cid, w, _ in raw_inst)
    flagged = sorted(cid for cid, c in cases.items() if c["wrong_data"] == 2)
    split = json.load(open(ROOT / "data" / "split.json"))["split"]

    def ids(run):
        return [json.loads(l)["case_id"] for l in open(ROOT / "runs" / run / "turn1.jsonl")]
    samples = {}
    for run in ["dev2_q14n_native_poison", "dev2_q8n_native_poison", "dev2_goss_text_poison",
                "dev2_goss_native_poison", "dev2_q8n_text_poison", "dev2_q14n_native_clean",
                "dev2_q8n_native_clean", "dev2_goss_text_clean", "dev2_goss_native_clean",
                "conf_q14n_native_poison", "conf_q8n_native_poison", "conf_goss_native_poison",
                "conf_q14n_native_clean", "conf_q8n_native_clean"]:
        s = ids(run)
        samples[run] = {"n_cases": len(set(s)), "wrong_data2": sorted(set(s) & set(flagged))}
        _, _, t1, _ = load(run)
        el = {r["case_id"] for r in t1 if r["_relabel"] == "BENIGN_CALL"}
        samples[run]["wrong_data2_eligible"] = len(el & set(flagged))
        samples[run]["n_eligible"] = len(el)
    val = json.load(open(ROOT / "data" / "signatures.validation.json"))
    worst30 = [w[1] for w in val["worst_cases"] if w[0] >= 0.30]
    return {
        "mcptox_configurations": {"distinct_ref_keys": len(keys_all), "with_labelled_nonempty_responses": len(per),
                                  "local": len(local), "online": len(online), "labelled_responses_total": sum(per.values()),
                                  "local_names": local, "online_names": online,
                                  "analysis_mcptox_firstturn_by_signature_entries": len(a0)},
        "mcptox_source": {"path": str(src.relative_to(ROOT.parent)), "sha256": sha,
                          "matches_build_cases_EXPECTED_SHA": sha == "79a90049be931c59e71446d6180b1d7f0d196d123d08a59bc155d142b5041c03",
                          "instances": len(raw_inst), "servers": len(raw["servers"]),
                          "wrong_data_values": {str(k): v for k, v in raw_wd.items()},
                          "cases_jsonl_wrong_data_values": {str(k): v for k, v in cases_wd.items()},
                          "cases_jsonl_matches_source": match,
                          "instances_minus_wrong_data2": len(raw_inst) - raw_wd.get(2, 0)},
        "wrong_data2": {"n": len(flagged),
                        "by_paradigm": dict(collections.Counter(cases[c]["paradigm"] for c in flagged)),
                        "dev_split": sum(1 for c in flagged if split[c] == "dev"),
                        "heldout_split": sum(1 for c in flagged if split[c] == "heldout"),
                        "split_sizes": dict(collections.Counter(split.values())),
                        "case_ids": flagged, "samples": samples,
                        "signature_disagreement_ge30pct": {"n_cases": len(worst30),
                                                           "flagged": sorted(set(worst30) & set(flagged))}},
    }


# ----------------------------------------------------------------------------- (6) ordering


def ordering(run, ref):
    man, proto, t1, t2 = load(run)
    Y, U = ycond(t2)
    rows = []
    for c in man["conditions"]:
        d = kn(Y, c)
        lo, hi = wilson(d["k"], d["n"])
        rows.append({"condition": c, "k": d["k"], "n": d["n"], "Y": d["Y"], "wilson95": ci4((lo, hi)), "U": U.get(c, 0),
                     f"paired_vs_{ref}": paired(Y, c, ref) if c != ref else None,
                     "paired_vs_S_ok": paired(Y, c, "S_ok") if c != "S_ok" else None})
    rows.sort(key=lambda x: (-x["Y"], x["condition"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def section6():
    conf = {agent: ordering(run, E) for ds, agent, proto, run, E in DATASETS if ds == "conf"}
    dev = {f"{agent}@{proto}": ordering(run, E) for ds, agent, proto, run, E in DATASETS if ds == "dev"}
    return {"conf": conf, "dev": dev}


# ----------------------------------------------------------------------------- m11: report.py diffs (paper's B=2000)


def section_m11():
    out = {}
    for run in ["dev2_q14n_native_poison", "dev2_q8n_native_poison", "dev2_goss_text_poison",
                "dev2_goss_native_poison", "dev2_q8n_text_poison"]:
        s = report.summarize(run)
        out[run] = {c: {"n": v["n"], "Y": r4(v["Y"]), "diff_vs_S_ok": r4(v["diff"]), "diff_ci95": ci4(v["diff_ci"]),
                        "ci_contains_0": (v["diff_ci"][0] is not None and v["diff_ci"][0] <= 0 <= v["diff_ci"][1])}
                    for c, v in s["cond"].items()}
    return out


def main():
    set_variant("frozen")
    res = {"_meta": {"script": "analysis/fix_20261010/metrics/metrics.py", "B": B, "seed": SEED,
                     "labels": "report.relabel on raw responses; report.load BENIGN_CALL eligibility filter",
                     "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()[:8]
                                for p in ["src/cs_common.py", "src/report.py", "src/run_native.py",
                                          "data/signatures.jsonl", "data/cases.jsonl"]}},
           "tolerant_normalizer_check": tolerant_collision_check()}
    res["1_asr"] = section1()
    set_variant("frozen"); _CACHE.clear()
    res["2_remedy"] = section2()
    res["3_silent"] = section3()
    res["4_dev_clean_D"] = section4()
    res["5_mcptox"] = section5()
    res["6_ordering"] = section6()
    res["m11_report_py_diffs"] = section_m11()
    (HERE / "metrics.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    print("wrote", HERE / "metrics.json")


if __name__ == "__main__":
    main()
