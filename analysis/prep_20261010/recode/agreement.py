#!/usr/bin/env python3
"""Inter-annotator agreement for the attack signatures (recode-v1 sample, 150 cases).

Run (offline, no model calls, no network):
    python3 -B analysis/prep_20261010/recode/agreement.py

Reads data/, runs/, recode/annotator_{A,B}.jsonl. Writes only recode/agreement.{json,txt,calls.jsonl}.
src/ is imported read-only (bytecode writing disabled).

Coders
  F = frozen signatures (data/signatures.jsonl v1.1, written with the risk descriptions)
  A, B = blind re-codings (recode/annotator_A.jsonl, annotator_B.jsonl)

Evaluation call set = every tool call observed for the 150 sampled cases
  - MCPTox recorded responses (cases.jsonl mcptox_ref, every model key, non-empty response; text protocol)
  - our runs: runs/conf_*_native_poison, runs/dev2_*_native_poison (turn1 + turn2, native),
              runs/dev2_goss_text_poison (turn1 + turn2, text)
  Conventions (report.relabel): native rows -> run_native.calls_of(response)[0] (parser-miss text calls are
  NOT merged); text rows and MCPTox -> classify(visible_text(response), sig)["calls"]. Transport errors have no calls.
Per-call label = cs_common.call_is_malicious(call, sig_X), X in {F, A, B}.

Statistics: observed agreement, Cohen's kappa, PABAK, positives per coder; kappa CI by case-cluster bootstrap.
H1 re-run: confirm_analysis estimator (pooled, B=5000, seed 20261010) with labels recomputed under F / A / B
for conf_q14n / conf_q8n, restricted to the sampled cases in those runs; plus a supplementary "hybrid" full-run
re-analysis (frozen signatures everywhere except the sampled cases, which take A or B).
"""
import sys

sys.dont_write_bytecode = True

import collections  # noqa: E402
import glob  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cs_common import (call_is_malicious, classify, load_jsonl, load_signatures, normalize_call,  # noqa: E402
                       sha256_file, visible_text)
import run_native  # noqa: E402
import confirm_analysis as ca  # noqa: E402  (registered estimator, imported read-only)
import report  # noqa: E402

OUT_JSON = HERE / "agreement.json"
OUT_TXT = HERE / "agreement.txt"
OUT_CALLS = HERE / "agreement.calls.jsonl"
SEED = 20261010
B_KAPPA = 2000
CODERS = ("F", "A", "B")
PAIRS = (("F", "A"), ("F", "B"), ("A", "B"))
PARADIGMS = ("Template-1", "Template-2", "Template-3")
OK_CONDS = {"S_ok", "S_empty"}  # every other turn-2 condition is an error condition (E_*, X_exception)

# ------------------------------------------------------------------------------------------- inputs
CASES = {c["case_id"]: c for c in load_jsonl(ROOT / "data" / "cases.jsonl")}
FROZEN_ALL = load_signatures()
SAMPLE_META = json.load(open(HERE / "annotator_B_sample.json"))
SAMPLE = [x["case_id"] for x in SAMPLE_META["sample"]]
SPLIT = {x["case_id"]: x["split"] for x in SAMPLE_META["sample"]}
ANN = {"A": {r["case_id"]: r for r in load_jsonl(HERE / "annotator_A.jsonl")},
       "B": {r["case_id"]: r for r in load_jsonl(HERE / "annotator_B.jsonl")}}
assert len(SAMPLE) == 150 and len(set(SAMPLE)) == 150
for k in ("A", "B"):
    assert set(ANN[k]) == set(SAMPLE), k
SIGS = {"F": {c: FROZEN_ALL[c] for c in SAMPLE}, "A": ANN["A"], "B": ANN["B"]}
# sanity: sample rule reproduces
_chk = sorted(CASES, key=lambda c: hashlib.sha256(("recode-v1|" + c).encode()).hexdigest())
_per = collections.defaultdict(list)
for c in _chk:
    if len(_per[CASES[c]["paradigm"]]) < 50:
        _per[CASES[c]["paradigm"]].append(c)
assert set(SAMPLE) == {c for v in _per.values() for c in v}, "sample rule mismatch"

RUNS_NATIVE = sorted({Path(p).name for p in glob.glob(str(ROOT / "runs" / "conf_*_native_poison"))}
                     | {Path(p).name for p in glob.glob(str(ROOT / "runs" / "dev2_*_native_poison"))})
RUNS_TEXT = ["dev2_goss_text_poison"]


def rows_of(run):
    d = ROOT / "runs" / run
    man = json.load(open(d / "manifest.json"))
    proto = man.get("protocol", "text")
    out = []
    for turn in (1, 2):
        for i, l in enumerate(open(d / f"turn{turn}.jsonl")):
            r = json.loads(l)
            out.append((turn, i, r))
    return man, proto, out


def transport_error(resp):
    # same test as report.relabel
    return (not resp.get("ok", True)) or ("error" in resp and not resp.get("ok"))


def calls_for(resp, proto, cid):
    if transport_error(resp):
        return []
    if proto == "native":
        calls, _ = run_native.calls_of(resp)
    else:
        calls = classify(visible_text(resp), FROZEN_ALL[cid])["calls"]
    return [normalize_call(c) for c in calls]


def canon(call):
    return json.dumps([call["tool"], call["arguments"]], sort_keys=True, ensure_ascii=False, default=str)


# ------------------------------------------------------------------------------------------- call set
def build_call_set():
    recs = []
    S = set(SAMPLE)
    meta = {"runs_native": RUNS_NATIVE, "runs_text": RUNS_TEXT, "rows": collections.Counter(),
            "rows_transport_error": collections.Counter(), "native_parser_miss_text_calls_excluded": 0}

    def add(cid, call, **kw):
        lab = {x: bool(call_is_malicious(call, SIGS[x][cid])) for x in CODERS}
        recs.append({"case_id": cid, "paradigm": CASES[cid]["paradigm"], "split": SPLIT[cid], **kw,
                     "tool": call["tool"], "arguments": call["arguments"], "key": canon(call), **lab})

    # MCPTox recorded responses (text protocol)
    for cid in SAMPLE:
        for model, v in CASES[cid]["mcptox_ref"].items():
            resp = v.get("response")
            if not resp:
                continue
            meta["rows"]["mcptox"] += 1
            for k, call in enumerate(calls_for({"content": resp}, "text", cid)):
                add(cid, call, source="mcptox", run="mcptox", agent=model, protocol="text", turn=1,
                    condition=None, error_cond=False, row=model, k=k, mcptox_label=v.get("label"))
    for run in RUNS_NATIVE + RUNS_TEXT:
        man, proto, rows = rows_of(run)
        for turn, i, r in rows:
            cid = r["case_id"]
            if cid not in S:
                continue
            resp = r.get("response") or {}
            meta["rows"][run] += 1
            if transport_error(resp):
                meta["rows_transport_error"][run] += 1
            if proto == "native" and not transport_error(resp):
                meta["native_parser_miss_text_calls_excluded"] += len(run_native.calls_of(resp)[1])
            cond = r.get("condition") if turn == 2 else None
            for k, call in enumerate(calls_for(resp, proto, cid)):
                add(cid, call, source="ours", run=run, agent=man["agent"], protocol=proto, turn=turn,
                    condition=cond, error_cond=(turn == 2 and cond not in OK_CONDS), row=i, k=k, mcptox_label=None)
    meta["rows"] = dict(meta["rows"])
    meta["rows_transport_error"] = dict(meta["rows_transport_error"])
    return recs, meta


# ------------------------------------------------------------------------------------------- statistics
def conf_counts(recs, x, y):
    n11 = sum(1 for r in recs if r[x] and r[y])
    n10 = sum(1 for r in recs if r[x] and not r[y])
    n01 = sum(1 for r in recs if not r[x] and r[y])
    n00 = len(recs) - n11 - n10 - n01
    return n11, n10, n01, n00


def kappa_of(n11, n10, n01, n00):
    n = n11 + n10 + n01 + n00
    if not n:
        return None, None
    po = (n11 + n00) / n
    p1, p2 = (n11 + n10) / n, (n11 + n01) / n
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return po, (None if pe >= 1 - 1e-12 else (po - pe) / (1 - pe))


def binom_two_sided(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def pair_stats(recs, x, y, boot=True, seed=SEED):
    n11, n10, n01, n00 = conf_counts(recs, x, y)
    n = n11 + n10 + n01 + n00
    po, k = kappa_of(n11, n10, n01, n00)
    out = {"n_calls": n, "n_cases": len({r["case_id"] for r in recs}),
           "both_mal": n11, f"{x}_only": n10, f"{y}_only": n01, "both_not": n00,
           "agreement": None if po is None else round(po, 4), "kappa": None if k is None else round(k, 4),
           "pabak": None if po is None else round(2 * po - 1, 4),
           f"pos_{x}": n11 + n10, f"pos_{y}": n11 + n01,
           "mcnemar_two_sided_p_calls": round(binom_two_sided(n10, n01), 4)}
    if boot and n:
        per = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in recs:
            j = (0 if r[y] else 1) if r[x] else (2 if r[y] else 3)
            per[r["case_id"]][j] += 1
        cs = sorted(per)
        rng = random.Random(seed)
        ks = []
        for _ in range(B_KAPPA):
            tot = [0, 0, 0, 0]
            for _c in cs:
                v = per[cs[rng.randrange(len(cs))]]
                for j in range(4):
                    tot[j] += v[j]
            kk = kappa_of(*tot)[1]
            if kk is not None:
                ks.append(kk)
        ks.sort()
        if len(ks) >= 100:
            out["kappa_ci95_case_boot"] = [round(ks[int(.025 * len(ks))], 4), round(ks[int(.975 * len(ks)) - 1], 4)]
            out["kappa_boot_defined"] = len(ks)
    return out


def dedup(recs):
    seen, out = set(), []
    for r in recs:
        key = (r["case_id"], r["key"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def all_pairs(recs, boot=True):
    return {f"{x}_vs_{y}": pair_stats(recs, x, y, boot=boot) for x, y in PAIRS}


def fleiss3(recs):
    """Fleiss' kappa for three coders on binary labels (supplementary)."""
    N = len(recs)
    if not N:
        return None
    P, pj = [], [0, 0]
    for r in recs:
        m = sum(r[x] for x in CODERS)
        cnt = [m, 3 - m]
        pj[0] += m
        pj[1] += 3 - m
        P.append((sum(c * c for c in cnt) - 3) / 6)
    Pbar = sum(P) / N
    pj = [v / (3 * N) for v in pj]
    Pe = sum(v * v for v in pj)
    return None if Pe >= 1 - 1e-12 else round((Pbar - Pe) / (1 - Pe), 4)


# ------------------------------------------------------------------------------------------- inclusiveness
def sig_shape(s):
    pats = s.get("malicious", [])
    return {"patterns": len(pats),
            "values": sum(len(c.get("values", [])) for p in pats for c in p.get("args", [])),
            "wildcard_constraints": sum(1 for p in pats for c in p.get("args", []) if c.get("key") in (None, "*")),
            "argless_patterns": sum(1 for p in pats if not p.get("args")),
            "equals_constraints": sum(1 for p in pats for c in p.get("args", []) if c.get("op") == "equals"),
            "tools": sorted({p["tool"] for p in pats})}


def inclusiveness(recs):
    out = {}
    by_case = collections.defaultdict(list)
    for r in recs:
        by_case[r["case_id"]].append(r)
    for x, y in PAIRS:
        kinds = collections.Counter()
        cases = {"x_superset": [], "y_superset": [], "crossing": []}
        for cid, rs in by_case.items():
            xo = sum(1 for r in rs if r[x] and not r[y])
            yo = sum(1 for r in rs if r[y] and not r[x])
            if xo and yo:
                kinds["crossing"] += 1
                cases["crossing"].append((cid, xo, yo))
            elif xo:
                kinds[f"{x}_more_inclusive"] += 1
                cases["x_superset"].append((cid, xo, yo))
            elif yo:
                kinds[f"{y}_more_inclusive"] += 1
                cases["y_superset"].append((cid, xo, yo))
            else:
                kinds["identical_on_observed_calls"] += 1
        # cases where the observed calls never hit either signature cannot discriminate inclusiveness
        out[f"{x}_vs_{y}"] = {"case_counts": dict(kinds),
                              "cases": {k: sorted(v, key=lambda t: -(t[1] + t[2])) for k, v in cases.items()}}
    shapes = {x: collections.Counter() for x in CODERS}
    for x in CODERS:
        for cid in SAMPLE:
            sh = sig_shape(SIGS[x][cid])
            for k in ("patterns", "values", "wildcard_constraints", "argless_patterns", "equals_constraints"):
                shapes[x][k] += sh[k]
            shapes[x]["empty_malicious"] += int(not SIGS[x][cid].get("malicious"))
            shapes[x]["unrealizable"] += int(bool(SIGS[x][cid].get("unrealizable")))
    out["signature_shape_totals"] = {x: dict(v) for x, v in shapes.items()}
    tool_disagree = {}
    for x, y in PAIRS:
        tool_disagree[f"{x}_vs_{y}"] = sum(1 for cid in SAMPLE
                                           if {t.lower() for t in sig_shape(SIGS[x][cid])["tools"]}
                                           != {t.lower() for t in sig_shape(SIGS[y][cid])["tools"]})
    out["cases_with_different_malicious_tool_sets"] = tool_disagree
    return out


def examples(recs, per_dir=6):
    """One example call per disagreeing case, most disagreements first, turn-2 error calls preferred."""
    ex = {}
    for x, y in PAIRS:
        for a, b in ((x, y), (y, x)):
            dis = [r for r in recs if r[a] and not r[b]]
            byc = collections.defaultdict(list)
            for r in dis:
                byc[r["case_id"]].append(r)
            items = []
            for cid, rs in sorted(byc.items(), key=lambda kv: -len(kv[1])):
                rs.sort(key=lambda r: (not r["error_cond"], r["source"] != "ours"))
                r = rs[0]
                items.append({"case_id": cid, "paradigm": r["paradigm"], "n_disagreeing_calls": len(rs),
                              "n_from_turn2_error": sum(1 for q in rs if q["error_cond"]),
                              "example_source": f'{r["run"]}/t{r["turn"]}/{r["condition"] or ""}/{r["agent"]}',
                              "call": {"tool": r["tool"],
                                       "arguments": json.dumps(r["arguments"], ensure_ascii=False, default=str)[:300]},
                              f"sig_{a}": SIGS[a][cid]["malicious"], f"sig_{b}": SIGS[b][cid]["malicious"],
                              f"note_{a}": SIGS[a][cid].get("note", ""), f"note_{b}": SIGS[b][cid].get("note", "")})
            ex[f"{a}+_{b}-"] = {"n_calls": len(dis), "n_cases": len(byc), "examples": items[:per_dir],
                                "all_cases": [(it["case_id"], it["n_disagreeing_calls"]) for it in items]}
    return ex


# ------------------------------------------------------------------------------------------- H1 re-run
def relabel_with(r, proto, sig):
    """report.relabel with an explicit signature (same branches)."""
    resp = r.get("response") or {}
    if not resp.get("ok", True) or "error" in resp and not resp.get("ok"):
        return "ERROR_TRANSPORT"
    if proto == "native":
        calls, _ = run_native.calls_of(resp)
        lab = run_native.label(calls, sig)
    else:
        lab = classify(visible_text(resp), sig)["label"]
        if resp.get("finish_reason") == "length" and lab == "NO_CALL":
            lab = "TRUNCATED"
    if proto == "native" and resp.get("finish_reason") == "length" and lab == "NO_CALL":
        lab = "TRUNCATED"
    return lab


def load_Y_with(run, sigmap, strata=("BENIGN_CALL",), keep=None):
    """Mirror of confirm_analysis.load_Y with a signature map and an optional case filter."""
    d = ROOT / "runs" / run
    man = json.load(open(d / "manifest.json"))
    proto = man.get("protocol", "text")
    t1 = [json.loads(l) for l in open(d / "turn1.jsonl")]
    if keep is not None:
        t1 = [r for r in t1 if r["case_id"] in keep]
    lab1 = {r["case_id"]: relabel_with(r, proto, sigmap[r["case_id"]]) for r in t1}
    Y = collections.defaultdict(dict)
    U = collections.Counter()
    N = collections.Counter()
    for l in open(d / "turn2.jsonl"):
        r = json.loads(l)
        if keep is not None and r["case_id"] not in keep:
            continue
        if lab1.get(r["case_id"]) not in strata:
            continue
        lab = relabel_with(r, proto, sigmap[r["case_id"]])
        N[r["condition"]] += 1
        if lab in ("ERROR_TRANSPORT", "TRUNCATED"):
            U[r["condition"]] += 1
            continue
        Y[r["condition"]][r["case_id"]] = int(lab == "MALICIOUS")
    return man["agent"], Y, {"U": dict(U), "N": dict(N), "t1": dict(collections.Counter(lab1.values()))}, lab1


def mcnemar_one_sided(Y, a="E_unknown", b="S_ok"):
    cs = set(Y.get(a, {})) & set(Y.get(b, {}))
    up = sum(1 for c in cs if Y[a][c] == 1 and Y[b][c] == 0)
    dn = sum(1 for c in cs if Y[a][c] == 0 and Y[b][c] == 1)
    n = up + dn
    p = sum(math.comb(n, i) for i in range(up, n + 1)) / 2 ** n if n else 1.0
    return {"n_pairs": len(cs), "Y_a": sum(Y[a][c] for c in cs), "Y_b": sum(Y[b][c] for c in cs),
            "discordant_up": up, "discordant_down": dn, "exact_p_one_sided": round(p, 6)}


def sigmap_for(coder):
    m = dict(FROZEN_ALL)
    if coder != "F":
        m.update(SIGS[coder])
    return m


QWEN_POISON = ["conf_q14n_native_poison", "conf_q8n_native_poison"]
QWEN_CLEAN = ["conf_q14n_native_clean", "conf_q8n_native_clean"]


def h1_rerun():
    out = {"subset": {}, "hybrid_full": {}, "loader_check": {}}
    # loader reproduces the registered loader on the full frozen run
    for run in QWEN_POISON:
        ag, Yreg, meta = ca.load_Y(run)
        ag2, Y2, meta2, _ = load_Y_with(run, FROZEN_ALL)
        same = {k: dict(v) for k, v in Yreg.items()} == {k: dict(v) for k, v in Y2.items()} and meta == meta2
        assert same, run
        out["loader_check"][run] = "identical to confirm_analysis.load_Y"
    S = set(SAMPLE)
    for run in QWEN_POISON:
        run_cases = {json.loads(l)["case_id"] for l in open(ROOT / "runs" / run / "turn1.jsonl")}
        keep = S & run_cases
        res = {"sampled_cases_in_run": len(keep)}
        lab1s, Ys = {}, {}
        for coder in CODERS:
            ag, Y, meta, lab1 = load_Y_with(run, sigmap_for(coder), keep=keep)
            lab1s[coder], Ys[coder] = lab1, Y
            h1 = ca.pooled([ca.contrast_vals(Y, ca.diff("E_unknown", "S_ok"))])
            res[coder] = {"H1": h1, "mcnemar": mcnemar_one_sided(Y), "t1": meta["t1"], "U": meta["U"],
                          "Y_by_condition": {k: f"{sum(v.values())}/{len(v)}" for k, v in sorted(Y.items())}}
        # what moved
        moves = {}
        for coder in ("A", "B"):
            st = [(c, lab1s["F"][c], lab1s[coder][c]) for c in sorted(keep) if lab1s["F"][c] != lab1s[coder][c]]
            yc = []
            for cond in sorted(set(Ys["F"]) | set(Ys[coder])):
                for c in sorted(set(Ys["F"].get(cond, {})) | set(Ys[coder].get(cond, {}))):
                    f, o = Ys["F"].get(cond, {}).get(c), Ys[coder].get(cond, {}).get(c)
                    if f != o:
                        yc.append((c, cond, f, o))
            moves[coder] = {"t1_stratum_changes": st, "Y_changes(case,cond,F,coder)": yc}
        res["changes_vs_frozen"] = moves
        out["subset"][run] = res
    # pooled over the two Qwen agents on the subset (registered pooled statistic)
    for coder in CODERS:
        per = []
        for run in QWEN_POISON:
            run_cases = {json.loads(l)["case_id"] for l in open(ROOT / "runs" / run / "turn1.jsonl")}
            _, Y, _, _ = load_Y_with(run, sigmap_for(coder), keep=S & run_cases)
            per.append(ca.contrast_vals(Y, ca.diff("E_unknown", "S_ok")))
        out["subset"].setdefault("pooled_qwen_H1", {})[coder] = ca.pooled(per)
    # supplementary: hybrid full-run re-analysis of the registered hypotheses (Qwen only, as registered)
    for coder in CODERS:
        sm = sigmap_for(coder)
        P = [load_Y_with(r, sm)[:3] for r in QWEN_POISON]
        C = [load_Y_with(r, sm)[:3] for r in QWEN_CLEAN]
        D = [load_Y_with(r, sm, strata=("DIRECT_EXEC",))[:3] for r in QWEN_POISON]
        h = {"H1": {p[0]: ca.pooled([ca.contrast_vals(p[1], ca.diff("E_unknown", "S_ok"))]) for p in P},
             "H1_mcnemar": {p[0]: mcnemar_one_sided(p[1]) for p in P}}
        pc = ca.pooled([ca.contrast_vals(p[1], ca.diff("E_unknown", "S_ok")) for p in P])
        cc = ca.pooled([ca.contrast_vals(c[1], ca.diff("E_unknown", "S_ok")) for c in C])
        h["H2"] = {"poison": pc, "clean": cc, "D": round(pc["est"] - cc["est"], 4)}
        h["H3"] = ca.pooled([ca.contrast_vals(p[1], ca.diff("E_unknown", "E_unknown_remedy")) for p in P])
        h["H4"] = ca.pooled([ca.contrast_vals(p[1], ca.mean_diff(["E_unknown", "E_internal"],
                                                                 ["E_deadline", "E_permission"])) for p in P])
        h["H5"] = ca.pooled([ca.contrast_vals(p[1], ca.fit_term) for p in P])
        h["H6"] = ca.pooled([ca.contrast_vals(d[1], ca.diff("E_unknown", "S_ok")) for d in D])
        ps = {"H1_" + k: v["p_one_sided"] for k, v in h["H1"].items()}
        for k in ("H3", "H4", "H5", "H6"):
            ps[k] = h[k]["p_one_sided"]
        h["holm_adjusted_p"] = ca.holm(ps)
        h["t1"] = {p[0]: p[2]["t1"] for p in P}
        out["hybrid_full"][coder] = h
    return out


# ------------------------------------------------------------------------------------------- main
def fmt_pair(s, x, y):
    ci = s.get("kappa_ci95_case_boot")
    k = "n/a" if s["kappa"] is None else f'{s["kappa"]:.3f}'
    cis = f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
    return (f'n={s["n_calls"]:>6} cases={s["n_cases"]:>3}  agree={s["agreement"]:.4f}  kappa={k}{cis}  '
            f'PABAK={s["pabak"]:.3f}  both+={s["both_mal"]} {x}only={s[f"{x}_only"]} {y}only={s[f"{y}_only"]}  '
            f'pos {x}/{y}={s[f"pos_{x}"]}/{s[f"pos_{y}"]}')


def main():
    recs, meta = build_call_set()
    with open(OUT_CALLS, "w") as f:
        for r in recs:
            f.write(json.dumps({k: v for k, v in r.items() if k != "key"}, ensure_ascii=False, default=str) + "\n")

    subsets = collections.OrderedDict()
    subsets["all"] = recs
    subsets["mcptox"] = [r for r in recs if r["source"] == "mcptox"]
    subsets["ours_all"] = [r for r in recs if r["source"] == "ours"]
    subsets["ours_turn1"] = [r for r in recs if r["source"] == "ours" and r["turn"] == 1]
    subsets["ours_turn2_all"] = [r for r in recs if r["source"] == "ours" and r["turn"] == 2]
    subsets["ours_turn2_error"] = [r for r in recs if r["error_cond"]]
    subsets["ours_turn2_ok"] = [r for r in recs if r["source"] == "ours" and r["turn"] == 2 and not r["error_cond"]]
    subsets["ours_turn2_error_native"] = [r for r in recs if r["error_cond"] and r["protocol"] == "native"]
    subsets["ours_turn2_error_text"] = [r for r in recs if r["error_cond"] and r["protocol"] == "text"]
    subsets["ours_turn2_error_conf_qwen"] = [r for r in recs if r["error_cond"] and r["run"] in QWEN_POISON]
    for p in PARADIGMS:
        subsets[f"all|{p}"] = [r for r in recs if r["paradigm"] == p]
        subsets[f"mcptox|{p}"] = [r for r in recs if r["source"] == "mcptox" and r["paradigm"] == p]
        subsets[f"ours_all|{p}"] = [r for r in recs if r["source"] == "ours" and r["paradigm"] == p]
        subsets[f"ours_turn2_error|{p}"] = [r for r in recs if r["error_cond"] and r["paradigm"] == p]
    subsets["all|unique_calls"] = dedup(recs)
    subsets["ours_turn2_error|unique_calls"] = dedup(subsets["ours_turn2_error"])
    for run in RUNS_NATIVE + RUNS_TEXT:
        subsets[f"ours_turn2_error|run={run}"] = [r for r in recs if r["error_cond"] and r["run"] == run]

    stats = {name: {**all_pairs(rs), "fleiss_kappa_3coders": fleiss3(rs)} for name, rs in subsets.items()}

    # row-level (response-level MALICIOUS) supplementary: ours turn-2 error rows
    rowmap = collections.defaultdict(lambda: {x: False for x in CODERS})
    for r in recs:
        if r["error_cond"]:
            key = (r["run"], r["row"])
            rowmap[key]["case_id"] = r["case_id"]
            for x in CODERS:
                rowmap[key][x] = rowmap[key][x] or r[x]
    rowrecs = list(rowmap.values())
    stats["ROW_LEVEL|ours_turn2_error_rows_with_calls"] = all_pairs(rowrecs)

    incl = inclusiveness(recs)
    incl_err = inclusiveness(subsets["ours_turn2_error"])
    ex = examples(recs)
    h1 = h1_rerun()

    result = {
        "inputs": {
            "annotator_A": sha256_file(HERE / "annotator_A.jsonl"),
            "annotator_B": sha256_file(HERE / "annotator_B.jsonl"),
            "signatures": sha256_file(ROOT / "data" / "signatures.jsonl"),
            "cases": sha256_file(ROOT / "data" / "cases.jsonl"),
            "cs_common.py": sha256_file(ROOT / "src" / "cs_common.py"),
            "run_native.py": sha256_file(ROOT / "src" / "run_native.py"),
            "confirm_analysis.py": sha256_file(ROOT / "src" / "confirm_analysis.py"),
            "report.py": sha256_file(ROOT / "src" / "report.py"),
        },
        "sample": {"n": len(SAMPLE), "paradigm": dict(collections.Counter(CASES[c]["paradigm"] for c in SAMPLE)),
                   "split": dict(collections.Counter(SPLIT.values()))},
        "call_set": {**meta, "n_calls": len(recs),
                     "by_source": dict(collections.Counter(f'{r["source"]}:t{r["turn"]}' for r in recs)),
                     "by_run": dict(collections.Counter(r["run"] for r in recs)),
                     "cases_with_any_call": len({r["case_id"] for r in recs})},
        "agreement": stats,
        "inclusiveness_all_calls": incl,
        "inclusiveness_turn2_error_calls": {k: v for k, v in incl_err.items() if k.endswith(("_vs_A", "_vs_B"))},
        "disagreement_examples": ex,
        "h1_rerun": h1,
    }
    OUT_JSON.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))

    # ---------------- text summary
    L = []
    L.append("Signature inter-annotator agreement (recode-v1, 150 cases; F=frozen v1.1, A/B=blind re-codes)")
    L.append(f"call set: {len(recs)} calls in {result['call_set']['cases_with_any_call']} cases; "
             f"{result['call_set']['by_source']}")
    L.append(f"runs: native {RUNS_NATIVE}; text {RUNS_TEXT}")
    L.append("")
    for name in subsets:
        L.append(f"[{name}]  Fleiss(3)={stats[name]['fleiss_kappa_3coders']}")
        for x, y in PAIRS:
            s = stats[name][f"{x}_vs_{y}"]
            if s["n_calls"]:
                L.append(f"  {x}-{y}: " + fmt_pair(s, x, y))
    L.append("[ROW_LEVEL|ours_turn2_error_rows_with_calls]")
    for x, y in PAIRS:
        L.append(f"  {x}-{y}: " + fmt_pair(stats["ROW_LEVEL|ours_turn2_error_rows_with_calls"][f"{x}_vs_{y}"], x, y))
    L.append("")
    L.append("Inclusiveness (case level, all calls): " +
             json.dumps({k: v["case_counts"] for k, v in incl.items() if "_vs_" in k}))
    L.append("Inclusiveness (case level, turn-2 error calls): " +
             json.dumps({k: v["case_counts"] for k, v in incl_err.items() if "_vs_" in k}))
    L.append("Signature shape totals over 150 cases: " + json.dumps(incl["signature_shape_totals"]))
    L.append("Cases whose malicious tool set differs: " + json.dumps(incl["cases_with_different_malicious_tool_sets"]))
    L.append("")
    for k, v in ex.items():
        L.append(f"Disagreement {k}: {v['n_calls']} calls in {v['n_cases']} cases: {v['all_cases']}")
        for it in v["examples"][:4]:
            L.append(f"   - {it['case_id']} ({it['paradigm']}, {it['n_disagreeing_calls']} calls, "
                     f"{it['n_from_turn2_error']} t2-error) e.g. {it['call']['tool']} {it['call']['arguments'][:160]}")
            sk = [kk for kk in it if kk.startswith("sig_")]
            for kk in sk:
                L.append(f"       {kk}: {json.dumps(it[kk], ensure_ascii=False)[:260]}")
    L.append("")
    L.append("H1 (E_unknown - S_ok), Qwen conf runs, restricted to sampled cases present in the run")
    for run in QWEN_POISON:
        r = h1["subset"][run]
        L.append(f"  {run}: sampled cases in run = {r['sampled_cases_in_run']}")
        for coder in CODERS:
            h, m = r[coder]["H1"], r[coder]["mcnemar"]
            L.append(f"    {coder}: est={h['est']} ci95={h['ci95']} p_boot={h['p_one_sided']} n={h['n_cases']}  "
                     f"Y(E_unknown)={m['Y_a']}/{m['n_pairs']} Y(S_ok)={m['Y_b']}/{m['n_pairs']} "
                     f"disc {m['discordant_up']}/{m['discordant_down']} exact p={m['exact_p_one_sided']}  t1={r[coder]['t1']}")
        for coder in ("A", "B"):
            mv = r["changes_vs_frozen"][coder]
            L.append(f"    changes F->{coder}: t1 strata {mv['t1_stratum_changes']}; Y {mv['Y_changes(case,cond,F,coder)']}")
    L.append("  pooled Qwen (subset): " + json.dumps(h1["subset"]["pooled_qwen_H1"]))
    L.append("")
    L.append("Supplementary hybrid full-run re-analysis (frozen outside the sample, coder inside):")
    for coder in CODERS:
        h = h1["hybrid_full"][coder]
        L.append(f"  {coder}: H1 " + json.dumps({k: (v['est'], v['ci95']) for k, v in h['H1'].items()}) +
                 f" H2 D={h['H2']['D']} H3={h['H3']['est']} {h['H3']['ci95']} H4={h['H4']['est']} {h['H4']['ci95']}"
                 f" H5={h['H5']['est']} {h['H5']['ci95']} H6={h['H6']['est']} {h['H6']['ci95']}"
                 f" holm={json.dumps(h['holm_adjusted_p'])}")
    OUT_TXT.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
