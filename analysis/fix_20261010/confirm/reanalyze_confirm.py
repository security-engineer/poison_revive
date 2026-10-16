#!/usr/bin/env python3
"""Offline re-analysis of the held-out confirmation runs (review items M1, M2, M3, M5, m5, m6).

Run from the condition_study root (no network, no model calls):
    python3 analysis/fix_20261010/confirm/reanalyze_confirm.py > analysis/fix_20261010/confirm/run.log

Writes only analysis/fix_20261010/confirm/results_confirm.json. src/, runs/, data/, prereg/ are read only.

Method
- Labels: recomputed from raw responses with report.relabel through a loader that mirrors the registered
  confirm_analysis.load_Y line by line; the script asserts that it returns exactly what load_Y returns.
- Estimators: the registered ones (confirm_analysis): per-agent mean of case-level paired differences; pooled =
  mean over agents of the agent means. H5 additionally with the REGISTERED interaction estimator
  mean_agents[ mean_T3(d) - mean_T2(d) ], d = Y(E_invalid_arg) - Y(E_precondition).
- CIs: case-cluster percentile bootstrap, B=20000, the case union is resampled jointly across agents (as in
  confirm_analysis.pooled); an agent whose term has no case in a resample is skipped (review m16). Percentile
  indices follow confirm_analysis (bs[int(.025B)], bs[int(.975B)-1]).
- p-values, one-sided in the registered direction unless labelled two-sided:
    per agent, binary paired contrast -> exact McNemar (binomial on discordant pairs);
    per agent, non-binary contrast (H4, H5) -> exact sign-flip (full enumeration);
    pooled -> sign-flip stratified by agent (independent flips per agent x case unit, registered pooled
              statistic), exact by enumeration AND Monte Carlo with B=20000;
    H2 -> arm-label permutation within agent (poison vs clean case-level contrasts), exact by enumeration AND
          Monte Carlo B=20000; sign-flip of both arms also reported;
    H5 (extra) -> template-label permutation, case level, joint across agents, Monte Carlo B=20000.
- Registered-code comparison: confirm_analysis.pooled / holm are imported and called unchanged (B=5000).
"""
import collections
import json
import math
import random
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path.cwd()
assert (ROOT / "src" / "confirm_analysis.py").exists(), "run from the condition_study root"
sys.path.insert(0, "src")
import numpy as np  # noqa: E402

import confirm_analysis as ca  # noqa: E402  (registered code, imported read-only)
import report  # noqa: E402

OUT = ROOT / "analysis" / "fix_20261010" / "confirm"
B = 20000
SEED = 20261010
CONDS = ["S_ok", "E_unknown", "E_internal", "E_invalid_arg", "E_precondition", "E_deadline", "E_permission",
         "E_unknown_remedy"]
POISON = {"q14": "conf_q14n_native_poison", "q8": "conf_q8n_native_poison", "goss": "conf_goss_native_poison"}
CLEAN = {"q14": "conf_q14n_native_clean", "q8": "conf_q8n_native_clean"}
QWEN = ["q14", "q8"]
ALL3 = ["q14", "q8", "goss"]
CASES = ca.CASES
SIGS = report.SIGS
EMPTY_SIG = sorted(c for c, s in SIGS.items() if s.get("malicious") == [])
BEN, DIR = ("BENIGN_CALL",), ("DIRECT_EXEC",)


# ----------------------------------------------------------------------------------------------- loading
def load_rows(run, strata):
    """Mirror of confirm_analysis.load_Y that also keeps U per case (for exclusion-aware counts)."""
    d = ROOT / "runs" / run
    man = json.load(open(d / "manifest.json"))
    proto = man.get("protocol", "text")
    t1 = [json.loads(l) for l in open(d / "turn1.jsonl")]
    lab1 = {r["case_id"]: report.relabel(r, proto) for r in t1}
    Y = collections.defaultdict(dict)
    U = collections.defaultdict(set)
    rows = collections.Counter()
    for l in open(d / "turn2.jsonl"):
        r = json.loads(l)
        if lab1.get(r["case_id"]) not in strata:
            continue
        lab = report.relabel(r, proto)
        rows[r["condition"]] += 1
        if lab in ("ERROR_TRANSPORT", "TRUNCATED"):
            U[r["condition"]].add(r["case_id"])
            continue
        Y[r["condition"]][r["case_id"]] = int(lab == "MALICIOUS")
    # equality with the registered loader
    agent, Yreg, meta = ca.load_Y(run, strata=strata)
    assert agent == man["agent"]
    assert {k: dict(v) for k, v in Yreg.items()} == {k: dict(v) for k, v in Y.items()}, run
    assert meta["N"] == dict(rows) and meta["U"] == {k: len(v) for k, v in U.items() if v}, run
    return {"run": run, "agent": man["agent"], "Y": {k: dict(v) for k, v in Y.items()},
            "U": {k: set(v) for k, v in U.items()}, "lab1": lab1, "sample": [r["case_id"] for r in t1]}


def exclude(D, excl):
    return {**D, "Y": {k: {c: y for c, y in v.items() if c not in excl} for k, v in D["Y"].items()},
            "U": {k: {c for c in v if c not in excl} for k, v in D["U"].items()},
            "lab1": {c: l for c, l in D["lab1"].items() if c not in excl},
            "sample": [c for c in D["sample"] if c not in excl]}


# ----------------------------------------------------------------------------------------------- contrasts
def diff_vals(Y, a, b):
    ya, yb = Y.get(a, {}), Y.get(b, {})
    return {c: ya[c] - yb[c] for c in set(ya) & set(yb)}


def meandiff_vals(Y, A, Bs):
    cs = set.intersection(*[set(Y.get(x, {})) for x in A + Bs])
    return {c: Fraction(sum(Y[x][c] for x in A), len(A)) - Fraction(sum(Y[x][c] for x in Bs), len(Bs)) for c in cs}


def tmpl(vals, t):
    return {c: v for c, v in vals.items() if CASES[c]["paradigm"] == t}


def spec_simple(vals):
    return [(1, vals)]


def spec_h5_registered(d):
    return [(1, tmpl(d, "Template-3")), (-1, tmpl(d, "Template-2"))]


def spec_h5_code(d):
    v = {c: x for c, x in tmpl(d, "Template-3").items()}
    v.update({c: -x for c, x in tmpl(d, "Template-2").items()})
    return [(1, v)]


def point(specs):
    vals = [sum(s * Fraction(sum(t.values())) / len(t) for s, t in terms)
            for terms in specs if all(len(t) for _, t in terms)]
    return sum(vals) / len(vals) if vals else None


# ----------------------------------------------------------------------------------------------- bootstrap
def boot_stats(specs, seed=SEED, nb=B):
    allc = sorted(set().union(*[set(t) for terms in specs for _, t in terms]))
    n = len(allc)
    idx = {c: i for i, c in enumerate(allc)}
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(n, np.full(n, 1.0 / n), size=nb).astype(np.float64)
    S, V = [], []
    for terms in specs:
        st = np.zeros(nb)
        ok = np.ones(nb, bool)
        for s, t in terms:
            v = np.zeros(n)
            m = np.zeros(n)
            for c, x in t.items():
                v[idx[c]] = float(x)
                m[idx[c]] = 1.0
            num, den = counts @ v, counts @ m
            ok &= den > 0
            st += s * np.divide(num, den, out=np.zeros(nb), where=den > 0)
        S.append(st)
        V.append(ok)
    S, V = np.array(S), np.array(V)
    k = V.sum(0)
    stat = np.where(k > 0, (S * V).sum(0) / np.maximum(k, 1), np.nan)
    return stat, {"n_cases": n, "resamples_with_skipped_agent": int((k < len(specs)).sum()),
                  "resamples_all_skipped": int((k == 0).sum())}


def summarize_boot(stat):
    bs = np.sort(stat[~np.isnan(stat)])
    nb = len(bs)
    le0 = int((bs <= 0).sum())
    return {"ci95": [float(bs[int(.025 * nb)]), float(bs[int(.975 * nb) - 1])],
            "p_boot_le0": le0 / nb, "p_boot_plus1": (le0 + 1) / (nb + 1), "B_eff": nb}


def bootstrap(specs, seed=SEED):
    stat, info = boot_stats(specs, seed)
    return {**summarize_boot(stat), **info}


def registered_style_boot(specs, nb=5000, seed=SEED):
    """confirm_analysis.pooled resampling scheme (python random, same draws) for a generalized statistic."""
    allc = sorted(set().union(*[set(t) for terms in specs for _, t in terms]))
    rng = random.Random(seed)

    def stat(cs):
        cnt = collections.Counter(cs)
        vals = []
        for terms in specs:
            tot = 0.0
            ok = True
            for s, t in terms:
                den = sum(cnt[c] for c in t)
                if not den:
                    ok = False
                    break
                tot += s * sum(cnt[c] * float(t[c]) for c in t) / den
            if ok:
                vals.append(tot)
        return sum(vals) / len(vals)

    bs = sorted(stat([allc[rng.randrange(len(allc))] for _ in allc]) for _ in range(nb))
    return {"est": float(stat(allc)), "ci95": [bs[int(.025 * nb)], bs[int(.975 * nb) - 1]],
            "p_one_sided": sum(1 for x in bs if x <= 0) / nb, "B": nb}


# ----------------------------------------------------------------------------------------------- sign-flip
def units_of(specs):
    """(weight, value) per agent x case unit; weight = sign / (A_valid * n_term)."""
    valid = [terms for terms in specs if all(len(t) for _, t in terms)]
    A = len(valid)
    out = []
    for terms in valid:
        for s, t in terms:
            for c, x in sorted(t.items()):  # sorted: MC draws must not depend on hash order
                out.append((Fraction(s, A * len(t)), Fraction(x)))
    return out


def _dist_add(dist, k):
    nd = collections.defaultdict(float)
    for s, p in dist.items():
        nd[s + k] += p / 2
        nd[s - k] += p / 2
    return nd


def signflip_exact(specs):
    units = units_of(specs)
    obs = sum(w * x for w, x in units)
    groups = collections.defaultdict(list)
    for w, x in units:
        if x != 0:
            groups[w].append(int(abs(x) * 2))  # half units -> integers
    dists = []
    for w, ks in sorted(groups.items()):
        dist = {0: 1.0}
        for k in ks:
            dist = _dist_add(dist, k)
        dists.append([(w * s / 2, p) for s, p in dist.items()])

    def conv(ds):
        out = {Fraction(0): 1.0}
        for d in ds:
            nd = collections.defaultdict(float)
            for v, p in out.items():
                for v2, p2 in d:
                    nd[v + v2] += p * p2
            out = nd
        return out

    h = len(dists) // 2
    left, right = conv(dists[:h]), conv(dists[h:])
    rv = sorted(right.items())
    vals = [v for v, _ in rv]
    tail = np.cumsum([p for _, p in rv][::-1])[::-1]

    def p_ge(a):
        tot = 0.0
        for v, p in left.items():
            j = _bisect_left(vals, a - v)
            if j < len(vals):
                tot += p * tail[j]
        return float(min(1.0, tot))

    p1 = p_ge(obs)
    p2 = 1.0 if obs == 0 else min(1.0, 2 * p_ge(abs(obs)))
    return {"p_exact": p1, "p_exact_two_sided": p2, "obs": float(obs), "n_units": len(units),
            "n_nonzero_units": sum(len(k) for k in groups.values())}


def _bisect_left(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def signflip_mc(specs, seed=SEED + 1, nb=B):
    units = units_of(specs)
    obs = float(sum(w * x for w, x in units))
    wd = np.array([float(w * x) for w, x in units if x != 0])
    rng = np.random.default_rng(seed)
    cnt = 0
    for start in range(0, nb, 5000):
        b = min(5000, nb - start)
        eps = rng.integers(0, 2, size=(b, len(wd))) * 2 - 1
        cnt += int(((eps @ wd) >= obs - 1e-12).sum())
    return {"p_mc": (cnt + 1) / (nb + 1), "B": nb}


def mcnemar(vals):
    b = sum(1 for v in vals.values() if v == 1)
    c = sum(1 for v in vals.values() if v == -1)
    assert all(v in (-1, 0, 1) for v in vals.values())
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "p_exact": 1.0, "p_exact_two_sided": 1.0}
    up = Fraction(sum(math.comb(n, k) for k in range(b, n + 1)), 2 ** n)
    lo = Fraction(sum(math.comb(n, k) for k in range(0, b + 1)), 2 ** n)
    return {"b": b, "c": c, "p_exact": float(up), "p_exact_two_sided": float(min(1, 2 * min(up, lo)))}


# ----------------------------------------------------------------------------------------------- H2 arm permutation
def arm_perm_exact(P, C):
    """P, C: lists (per agent, same order) of {case: value in -1/0/1}. Statistic D = mean_a mean(P_a) - mean_a mean(C_a).
    Null: within each agent, poison and clean case-level contrasts are exchangeable. Exact enumeration."""
    A = len(P)
    obs = sum(Fraction(sum(p.values()), len(p)) - Fraction(sum(c.values()), len(c)) for p, c in zip(P, C)) / A
    dists = []
    for p, c in zip(P, C):
        allv = list(p.values()) + list(c.values())
        npos, nneg = allv.count(1), allv.count(-1)
        nzero = len(allv) - npos - nneg
        n_p, n_c, N = len(p), len(c), len(allv)
        tot = math.comb(N, n_p)
        dist = collections.defaultdict(float)
        for x in range(0, min(npos, n_p) + 1):
            for y in range(0, min(nneg, n_p - x) + 1):
                z = n_p - x - y
                if z > nzero:
                    continue
                w = math.comb(npos, x) * math.comb(nneg, y) * math.comb(nzero, z)
                val = (Fraction(x - y, n_p) - Fraction((npos - x) - (nneg - y), n_c)) / A
                dist[val] += w / tot
        dists.append(dist)
    out = {Fraction(0): 1.0}
    for d in dists:
        nd = collections.defaultdict(float)
        for v, pr in out.items():
            for v2, p2 in d.items():
                nd[v + v2] += pr * p2
        out = nd
    p1 = sum(pr for v, pr in out.items() if v >= obs)
    return {"D_obs": float(obs), "p_exact": min(1.0, p1)}


def arm_perm_mc(P, C, seed=SEED + 2, nb=B):
    A = len(P)
    obs = sum(sum(p.values()) / len(p) - sum(c.values()) / len(c) for p, c in zip(P, C)) / A
    rng = np.random.default_rng(seed)
    stat = np.zeros(nb)
    for p, c in zip(P, C):
        allv = np.array([v for _, v in sorted(p.items())] + [v for _, v in sorted(c.items())], float)
        n_p, n_c, tot = len(p), len(c), allv.sum()
        sp = np.array([allv[rng.permutation(len(allv))[:n_p]].sum() for _ in range(nb)])
        stat += (sp / n_p - (tot - sp) / n_c) / A
    return {"p_mc": (int((stat >= obs - 1e-12).sum()) + 1) / (nb + 1), "B": nb}


# ----------------------------------------------------------------------------------------------- H5 template permutation
def template_perm_mc(dlist, seed=SEED + 3, nb=B):
    """dlist: per agent {case: d} restricted to T2/T3 cases. Labels permuted once per draw over the case union
    (joint across agents). Statistic: registered H5 estimator."""
    union = sorted(set().union(*[set(d) for d in dlist]))
    lab = np.array([CASES[c]["paradigm"] == "Template-3" for c in union])
    idx = {c: i for i, c in enumerate(union)}
    n = len(union)
    rng = np.random.default_rng(seed)
    L = np.array([lab[rng.permutation(n)] for _ in range(nb)]).astype(float)  # nb x n, 1 = T3
    obsL = lab.astype(float)[None, :]
    def stat(Lm):
        S, V = [], []
        for d in dlist:
            v = np.zeros(n); m = np.zeros(n)
            for c, x in d.items():
                v[idx[c]] = float(x); m[idx[c]] = 1
            n3, d3 = Lm @ (v * m), Lm @ m
            n2, d2 = (1 - Lm) @ (v * m), (1 - Lm) @ m
            ok = (d3 > 0) & (d2 > 0)
            S.append(np.divide(n3, d3, out=np.zeros(len(Lm)), where=d3 > 0)
                     - np.divide(n2, d2, out=np.zeros(len(Lm)), where=d2 > 0))
            V.append(ok)
        S, V = np.array(S), np.array(V)
        return (S * V).sum(0) / np.maximum(V.sum(0), 1)
    obs = float(stat(obsL)[0])
    st = stat(L)
    return {"obs": obs, "p_mc": (int((st >= obs - 1e-12).sum()) + 1) / (nb + 1), "B": nb}


# ----------------------------------------------------------------------------------------------- reporting helpers
def holm(ps):
    order = sorted(ps, key=lambda k: ps[k])
    m, res, prev = len(order), {}, 0.0
    for i, k in enumerate(order):
        adj = min(1.0, max(prev, (m - i) * ps[k]))
        prev = adj
        res[k] = adj
    return res


def pair_counts(Y, a, b):
    cs = set(Y.get(a, {})) & set(Y.get(b, {}))
    return {"n_pairs": len(cs), "k_" + a: sum(Y[a][c] for c in cs), "k_" + b: sum(Y[b][c] for c in cs)}


def agent_result(terms, binary_vals=None, seed=SEED):
    """terms: one agent's statistic terms (e.g. spec_simple(v))."""
    specs = [terms]
    r = {"est": float(point(specs)) if point(specs) is not None else None}
    r.update(bootstrap(specs, seed))
    if binary_vals is not None:
        mc = mcnemar(binary_vals)
        r.update({"mcnemar_b": mc["b"], "mcnemar_c": mc["c"], "p_exact": mc["p_exact"],
                  "p_exact_two_sided": mc["p_exact_two_sided"], "p_method": "exact McNemar (one-sided)"})
        se = signflip_exact(specs)
        assert abs(se["p_exact"] - mc["p_exact"]) < 1e-9, (se, mc)  # sign-flip == McNemar for binary d
    else:
        se = signflip_exact(specs)
        r.update({"p_exact": se["p_exact"], "p_exact_two_sided": se["p_exact_two_sided"],
                  "p_method": "exact sign-flip (one-sided)"})
    return r


def pooled_result(specs, seed=SEED):
    r = {"est": float(point(specs))}
    r.update(bootstrap(specs, seed))
    se = signflip_exact(specs)
    r.update({"p_exact": se["p_exact"], "p_exact_two_sided": se["p_exact_two_sided"],
              "p_method": "stratified sign-flip, exact enumeration (one-sided)"})
    r["p_signflip_mc"] = signflip_mc(specs)["p_mc"]
    return r


def ytable(D):
    out = {}
    for c in CONDS:
        y = D["Y"].get(c, {})
        out[c] = {"k": sum(y.values()), "n": len(y), "Y": (sum(y.values()) / len(y)) if y else None,
                  "U": len(D["U"].get(c, set()))}
    return out


# ----------------------------------------------------------------------------------------------- analysis
def analyze(excl):
    P = {a: exclude(load_rows(POISON[a], BEN), excl) for a in ALL3}
    PD = {a: exclude(load_rows(POISON[a], DIR), excl) for a in ALL3}
    C = {a: exclude(load_rows(CLEAN[a], BEN), excl) for a in QWEN}
    R = {"excluded_cases": sorted(excl),
         "excluded_present": {f"{arm}:{a}:{st}": sorted({c for v in D0["Y"].values() for c in v} & set(excl))
                              for arm, src, st in (("poison", POISON, BEN), ("poison", POISON, DIR), ("clean", CLEAN, BEN))
                              for a in src for D0 in [load_rows(src[a], st)]}}
    agent_name = {a: P[a]["agent"] for a in ALL3}
    R["agents"] = agent_name

    # ---- (10) Y tables + meta
    R["Y_table"] = {"poison_BENIGN": {agent_name[a]: ytable(P[a]) for a in ALL3},
                    "poison_DIRECT": {agent_name[a]: ytable(PD[a]) for a in ALL3},
                    "clean_BENIGN": {agent_name[a]: ytable(C[a]) for a in QWEN}}
    R["meta"] = {}
    for arm, src in (("poison", P), ("clean", C)):
        for a, D in src.items():
            t1 = collections.Counter(D["lab1"].values())
            rows = sum(len(v) for v in D["Y"].values()) + sum(len(v) for v in D["U"].values())
            u = sum(len(v) for v in D["U"].values())
            R["meta"][f"{arm}:{agent_name[a]}"] = {"n_t1": len(D["lab1"]), "t1": dict(t1),
                                                   "n_benign_eligible": t1["BENIGN_CALL"],
                                                   "turn2_rows_benign": rows, "U_benign": u,
                                                   "U_rate_benign": u / rows if rows else None}
    for a in ALL3:
        D = PD[a]
        rows = sum(len(v) for v in D["Y"].values()) + sum(len(v) for v in D["U"].values())
        u = sum(len(v) for v in D["U"].values())
        R["meta"][f"poison:{agent_name[a]}"].update({"turn2_rows_direct": rows, "U_direct": u})

    # ---- (1) H1 per agent
    R["H1"] = {}
    for a in ALL3:
        v = diff_vals(P[a]["Y"], "E_unknown", "S_ok")
        r = agent_result(spec_simple(v), v)
        r.update(pair_counts(P[a]["Y"], "E_unknown", "S_ok"))
        r["marginal"] = {c: [sum(P[a]["Y"][c].values()), len(P[a]["Y"][c])] for c in ("E_unknown", "S_ok")}
        R["H1"][agent_name[a]] = r
    q = [R["H1"][agent_name[a]] for a in QWEN]
    R["H1_registered_both_qwen"] = {"p_IUT_exact": max(x["p_exact"] for x in q),
                                    "ci_lower_gt0_both": all(x["ci95"][0] > 0 for x in q)}

    # ---- (2) H2
    Pv = [diff_vals(P[a]["Y"], "E_unknown", "S_ok") for a in QWEN]
    Cv = [diff_vals(C[a]["Y"], "E_unknown", "S_ok") for a in QWEN]
    ps, _ = boot_stats([spec_simple(v) for v in Pv], SEED)
    cs, _ = boot_stats([spec_simple(v) for v in Cv], SEED + 7)
    Dhat = point([spec_simple(v) for v in Pv]) - point([spec_simple(v) for v in Cv])
    h2 = {"poison_contrast": pooled_result([spec_simple(v) for v in Pv]),
          "clean_contrast": {"est": float(point([spec_simple(v) for v in Cv])), **bootstrap([spec_simple(v) for v in Cv], SEED + 7)},
          "clean_per_agent": {agent_name[a]: {**pair_counts(C[a]["Y"], "E_unknown", "S_ok"),
                                              "est": float(point([spec_simple(v)]))}
                              for a, v in zip(QWEN, Cv)},
          "clean_all_conditions_zero": all(sum(y.values()) == 0 for a in QWEN for y in C[a]["Y"].values()),
          "D": float(Dhat)}
    h2.update({"D_" + k: v for k, v in summarize_boot(ps - cs).items()})
    ap = arm_perm_exact(Pv, Cv)
    h2["p_arm_perm_exact"] = ap["p_exact"]
    h2["p_arm_perm_mc"] = arm_perm_mc(Pv, Cv)["p_mc"]
    # sign-flip of both arms: statistic = mean_a P_a - mean_a C_a, weights 1/(2 n)
    units_specs = [[(1, v)] for v in Pv] + [[(-1, v)] for v in Cv]
    se = signflip_exact(units_specs)  # A_valid = 4 -> statistic = D/2; p-value invariant to the positive scale
    h2["p_signflip_both_arms_exact"] = se["p_exact"]
    h2["p"] = h2["p_arm_perm_exact"]
    h2["p_method"] = "arm-label permutation within agent, exact enumeration (one-sided)"
    # restriction of the poison contrast to the clean sample (150) and to cases eligible in both arms
    restr = {}
    for name, sel in (("clean_sample_150", lambda a: set(C[a]["sample"])),
                      ("eligible_in_both_arms", lambda a: set(diff_vals(C[a]["Y"], "E_unknown", "S_ok")))):
        vs = [{c: x for c, x in diff_vals(P[a]["Y"], "E_unknown", "S_ok").items() if c in sel(a)} for a in QWEN]
        rr = {"pooled": pooled_result([spec_simple(v) for v in vs]), "per_agent": {}}
        for a, v in zip(QWEN, vs):
            rr["per_agent"][agent_name[a]] = {**agent_result(spec_simple(v), v),
                                              "n_pairs": len(v), "k_E_unknown": sum(P[a]["Y"]["E_unknown"][c] for c in v),
                                              "k_S_ok": sum(P[a]["Y"]["S_ok"][c] for c in v)}
        rr["D_restricted"] = float(point([spec_simple(v) for v in vs]) - point([spec_simple(v) for v in Cv]))
        rr["p_arm_perm_exact"] = arm_perm_exact(vs, Cv)["p_exact"]
        restr[name] = rr
    h2["poison_restricted"] = restr
    # registered-code view (point D only) and the bootstrap p it implies
    reg_pc = ca.pooled([ca.contrast_vals(P[a]["Y"], ca.diff("E_unknown", "S_ok")) for a in QWEN])
    reg_cc = ca.pooled([ca.contrast_vals(C[a]["Y"], ca.diff("E_unknown", "S_ok")) for a in QWEN])
    h2["registered_code"] = {"poison": reg_pc, "clean": reg_cc, "D": round(reg_pc["est"] - reg_cc["est"], 4)}
    R["H2"] = h2

    # ---- (3) H3, (4) H4 + decomposition, (6) H6
    def family(Ysrc, f, binary, agents_pooled=QWEN, agents=ALL3):
        out = {"per_agent": {}}
        for a in agents:
            v = f(Ysrc[a]["Y"])
            out["per_agent"][agent_name[a]] = agent_result(spec_simple(v), v if binary else None)
            out["per_agent"][agent_name[a]]["n_cases"] = len(v)
        if agents_pooled:
            out["pooled_qwen"] = pooled_result([spec_simple(f(Ysrc[a]["Y"])) for a in agents_pooled])
        return out

    R["H3"] = family(P, lambda Y: diff_vals(Y, "E_unknown", "E_unknown_remedy"), True)
    for a in ALL3:
        R["H3"]["per_agent"][agent_name[a]].update(pair_counts(P[a]["Y"], "E_unknown", "E_unknown_remedy"))
    R["H4"] = family(P, lambda Y: meandiff_vals(Y, ["E_unknown", "E_internal"], ["E_deadline", "E_permission"]), False)
    R["H4_decomposition"] = {
        "minus_deadline": family(P, lambda Y: meandiff_vals(Y, ["E_unknown", "E_internal"], ["E_deadline"]), False),
        "minus_permission": family(P, lambda Y: meandiff_vals(Y, ["E_unknown", "E_internal"], ["E_permission"]), False)}
    R["H6"] = family(PD, lambda Y: diff_vals(Y, "E_unknown", "S_ok"), True)
    for a in ALL3:
        R["H6"]["per_agent"][agent_name[a]].update(pair_counts(PD[a]["Y"], "E_unknown", "S_ok"))

    # ---- (5) H5
    dv = {a: diff_vals(P[a]["Y"], "E_invalid_arg", "E_precondition") for a in ALL3}
    h5 = {"per_agent": {}}
    for a in ALL3:
        d = dv[a]
        t3, t2 = tmpl(d, "Template-3"), tmpl(d, "Template-2")
        Y = P[a]["Y"]
        h5["per_agent"][agent_name[a]] = {
            "registered": agent_result(spec_h5_registered(d)),
            "code_estimator": {"est": float(point([spec_h5_code(d)]))},
            "T3_side": {**agent_result(spec_simple(t3), t3), "n_pairs": len(t3),
                        "k_E_invalid_arg": sum(Y["E_invalid_arg"][c] for c in t3),
                        "k_E_precondition": sum(Y["E_precondition"][c] for c in t3)},
            "T2_side": {**agent_result(spec_simple(t2), t2), "n_pairs": len(t2),
                        "k_E_invalid_arg": sum(Y["E_invalid_arg"][c] for c in t2),
                        "k_E_precondition": sum(Y["E_precondition"][c] for c in t2)},
            "template_perm": template_perm_mc([{c: x for c, x in d.items()
                                                 if CASES[c]["paradigm"] in ("Template-2", "Template-3")}])}
    h5["pooled_qwen_registered"] = pooled_result([spec_h5_registered(dv[a]) for a in QWEN])
    h5["pooled_qwen_registered"]["p_template_perm_mc"] = template_perm_mc(
        [{c: x for c, x in dv[a].items() if CASES[c]["paradigm"] in ("Template-2", "Template-3")} for a in QWEN])["p_mc"]
    h5["pooled_qwen_T3_side"] = pooled_result([spec_simple(tmpl(dv[a], "Template-3")) for a in QWEN])
    h5["pooled_qwen_T2_side"] = pooled_result([spec_simple(tmpl(dv[a], "Template-2")) for a in QWEN])
    h5["pooled_qwen_code_estimator_B20000"] = pooled_result([spec_h5_code(dv[a]) for a in QWEN])
    h5["registered_code_output"] = ca.pooled([ca.contrast_vals(P[a]["Y"], ca.fit_term) for a in QWEN])
    h5["registered_estimator_with_registered_bootstrap_B5000"] = registered_style_boot(
        [spec_h5_registered(dv[a]) for a in QWEN])
    R["H5"] = h5

    # ---- registered-code outputs (unchanged confirm_analysis functions, B=5000)
    regH1 = {agent_name[a]: ca.pooled([ca.contrast_vals(P[a]["Y"], ca.diff("E_unknown", "S_ok"))]) for a in ALL3}
    regH3 = ca.pooled([ca.contrast_vals(P[a]["Y"], ca.diff("E_unknown", "E_unknown_remedy")) for a in QWEN])
    regH4 = ca.pooled([ca.contrast_vals(P[a]["Y"], ca.mean_diff(["E_unknown", "E_internal"], ["E_deadline", "E_permission"]))
                       for a in QWEN])
    regH6 = ca.pooled([ca.contrast_vals(PD[a]["Y"], ca.diff("E_unknown", "S_ok")) for a in QWEN])
    reg = {"H1": regH1, "H3": regH3, "H4": regH4, "H5": h5["registered_code_output"], "H6": regH6, "H2": h2["registered_code"]}
    reg_ps_code_family = {"H1_" + agent_name[a]: regH1[agent_name[a]]["p_one_sided"] for a in QWEN}
    reg_ps_code_family.update({h: reg[h]["p_one_sided"] for h in ("H3", "H4", "H5", "H6")})
    reg["holm_code_family_as_registered_code_computes"] = ca.holm(reg_ps_code_family)
    R["registered_code"] = reg

    # ---- (8) Holm over the registered family
    fam_exact = {"H1": R["H1_registered_both_qwen"]["p_IUT_exact"], "H2": h2["p"],
                 "H3": R["H3"]["pooled_qwen"]["p_exact"], "H4": R["H4"]["pooled_qwen"]["p_exact"],
                 "H5": h5["pooled_qwen_registered"]["p_exact"], "H6": R["H6"]["pooled_qwen"]["p_exact"]}
    fam_mc = {"H1": max(mcnemar(diff_vals(P[a]["Y"], "E_unknown", "S_ok"))["p_exact"] for a in QWEN),
              "H2": h2["p_arm_perm_mc"],
              "H3": R["H3"]["pooled_qwen"]["p_signflip_mc"], "H4": R["H4"]["pooled_qwen"]["p_signflip_mc"],
              "H5": h5["pooled_qwen_registered"]["p_signflip_mc"], "H6": R["H6"]["pooled_qwen"]["p_signflip_mc"]}
    fam_boot = {"H1": max(regH1[agent_name[a]]["p_one_sided"] for a in QWEN), "H2": h2["registered_code"]["poison"]["p_one_sided"],
                "H3": regH3["p_one_sided"], "H4": regH4["p_one_sided"], "H5": reg["H5"]["p_one_sided"],
                "H6": regH6["p_one_sided"]}
    fam_boot_p1 = {k: (v * 5000 + 1) / 5001 for k, v in fam_boot.items()}
    R["holm"] = {}
    for name, fam in (("exact_perm_primary", fam_exact), ("perm_mc_B20000", fam_mc),
                      ("registered_code_bootstrap_B5000", fam_boot),
                      ("registered_code_bootstrap_B5000_plus1", fam_boot_p1)):
        adj = holm(fam)
        R["holm"][name] = {"raw": fam, "adjusted": adj, "confirmed": {k: adj[k] < 0.05 for k in fam}}
    fam7 = dict(fam_exact, H1_gptoss=R["H1"][agent_name["goss"]]["p_exact"])
    adj7 = holm(fam7)
    R["holm"]["exact_perm_plus_gptoss_H1"] = {"raw": fam7, "adjusted": adj7, "confirmed": {k: adj7[k] < 0.05 for k in fam7}}
    R["holm"]["note"] = ("registered_code_bootstrap uses H5 = code estimator (fit_term) and H2 p = poison-arm "
                         "bootstrap p as in DECISION_LOG; the code itself never computes an H2 p.")

    # ---- (7) gpt-oss auxiliary summary (already in per_agent blocks); collect
    g = agent_name["goss"]
    R["gptoss_auxiliary"] = {"H1": R["H1"][g], "H3": R["H3"]["per_agent"][g], "H4": R["H4"]["per_agent"][g],
                             "H4_minus_deadline": R["H4_decomposition"]["minus_deadline"]["per_agent"][g],
                             "H4_minus_permission": R["H4_decomposition"]["minus_permission"]["per_agent"][g],
                             "H5_registered": h5["per_agent"][g]["registered"], "H6": R["H6"]["per_agent"][g]}
    return R


def verdicts(R):
    v = {k: R["holm"]["exact_perm_primary"]["confirmed"][k] for k in ("H1", "H2", "H3", "H4", "H5", "H6")}
    v["H1_ci_lower_gt0_both_qwen"] = R["H1_registered_both_qwen"]["ci_lower_gt0_both"]
    for a, r in R["H1"].items():
        v[f"H1_{a}_exact_p_lt_05"] = r["p_exact"] < 0.05
        v[f"H1_{a}_ci_lower_gt0"] = r["ci95"][0] > 0
    return v


def main():
    main_R = analyze(set())
    # reproduce the stored registered output exactly
    stored = json.load(open(ROOT / "analysis" / "confirm_v1_full.json"))
    rc = main_R["registered_code"]
    for a in ("qwen3-14b-nothink", "qwen3-8b-nothink"):
        assert rc["H1"][a]["est"] == stored["H1"][a]["est"] and list(rc["H1"][a]["ci95"]) == stored["H1"][a]["ci95"]
    for h in ("H3", "H4", "H5", "H6"):
        assert rc[h]["est"] == stored[h]["est"] and list(rc[h]["ci95"]) == stored[h]["ci95"], h
    assert rc["holm_code_family_as_registered_code_computes"] == stored["holm_adjusted_p"]
    assert rc["H2"]["D"] == stored["H2"]["D"]
    sens_R = analyze(set(EMPTY_SIG))
    vm, vs = verdicts(main_R), verdicts(sens_R)
    out = {"inputs": {"poison": POISON, "clean": CLEAN, "B": B, "seed": SEED,
                      "registered_code_reproduced": "analysis/confirm_v1_full.json (H1,H2.D,H3,H4,H5,H6,holm) exact match",
                      "empty_signature_cases": EMPTY_SIG},
           "main": main_R, "sensitivity_exclude_empty_signatures": sens_R,
           "verdicts_main": vm, "verdicts_sensitivity": vs,
           "verdict_changes": {k: [vm[k], vs[k]] for k in vm if vm[k] != vs[k]}}
    (OUT / "results_confirm.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"verdicts_main": vm, "verdict_changes": out["verdict_changes"]}, indent=1))
    print("wrote", OUT / "results_confirm.json")


if __name__ == "__main__":
    main()
