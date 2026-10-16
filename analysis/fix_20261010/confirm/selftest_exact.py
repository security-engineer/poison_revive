#!/usr/bin/env python3
"""Checks for reanalyze_confirm.py (offline; run from the condition_study root):
  1. exact sign-flip enumeration == brute force over all 2^n sign vectors (random small pooled problems, half units)
  2. exact arm-label permutation == brute force over all splits (small problems)
  3. the generalized python-random resampler == confirm_analysis.pooled on the real H1/H3 inputs (same draws)
  4. eligible-overlap counts between poison and clean arms (review M2 quotes 95 / 83)
Usage: python3 analysis/fix_20261010/confirm/selftest_exact.py
"""
import itertools
import random
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, str(Path("analysis/fix_20261010/confirm").resolve()))
import confirm_analysis as ca  # noqa: E402
import reanalyze_confirm as rc  # noqa: E402

rng = random.Random(1)

# 1. sign-flip
for trial in range(40):
    specs = []
    for a in range(rng.choice([1, 2])):
        terms = []
        for s in ([1] if rng.random() < .5 else [1, -1]):
            n = rng.randint(1, 6)
            terms.append((s, {f"c{a}{s}{i}": Fraction(rng.choice([-2, -1, 0, 0, 1, 2]), 2) for i in range(n)}))
        specs.append(terms)
    units = rc.units_of(specs)
    obs = sum(w * x for w, x in units)
    tot = 0
    for eps in itertools.product([-1, 1], repeat=len(units)):
        if sum(e * w * x for e, (w, x) in zip(eps, units)) >= obs:
            tot += 1
    brute = tot / 2 ** len(units)
    ex = rc.signflip_exact(specs)["p_exact"]
    assert abs(brute - ex) < 1e-12, (trial, brute, ex)
print("1 sign-flip exact == brute force: OK (40 problems)")

# 2. arm-label permutation
for trial in range(30):
    P, C = [], []
    for a in range(rng.choice([1, 2])):
        P.append({f"p{a}{i}": rng.choice([-1, 0, 0, 1]) for i in range(rng.randint(1, 5))})
        C.append({f"q{a}{i}": rng.choice([-1, 0, 0, 1]) for i in range(rng.randint(1, 4))})
    A = len(P)
    obs = sum(Fraction(sum(p.values()), len(p)) - Fraction(sum(c.values()), len(c)) for p, c in zip(P, C)) / A
    per = []
    for p, c in zip(P, C):
        allv = list(p.values()) + list(c.values())
        n = len(allv)
        per.append([(Fraction(sum(allv[i] for i in S), len(p)) - Fraction(sum(allv) - sum(allv[i] for i in S), len(c))) / A
                    for S in itertools.combinations(range(n), len(p))])
    cnt = tot = 0
    for combo in itertools.product(*per):
        tot += 1
        cnt += sum(combo) >= obs
    ex = rc.arm_perm_exact(P, C)["p_exact"]
    assert abs(cnt / tot - ex) < 1e-12, (trial, cnt / tot, ex)
print("2 arm-label exact == brute force: OK (30 problems)")

# 3. resampler equivalence on real data
P = {a: rc.load_rows(rc.POISON[a], rc.BEN) for a in rc.QWEN}
for name, (x, y) in {"H1": ("E_unknown", "S_ok"), "H3": ("E_unknown", "E_unknown_remedy")}.items():
    mine = rc.registered_style_boot([rc.spec_simple(rc.diff_vals(P[a]["Y"], x, y)) for a in rc.QWEN])
    reg = ca.pooled([ca.contrast_vals(P[a]["Y"], ca.diff(x, y)) for a in rc.QWEN])
    assert round(mine["est"], 4) == reg["est"] and [round(v, 4) for v in mine["ci95"]] == list(reg["ci95"]) \
        and round(mine["p_one_sided"], 4) == reg["p_one_sided"], (name, mine, reg)
    print(f"3 {name}: generalized resampler == confirm_analysis.pooled:", reg)

# 4. eligible overlap
C = {a: rc.load_rows(rc.CLEAN[a], rc.BEN) for a in rc.QWEN}
for a in rc.QWEN:
    pe = {c for c, l in P[a]["lab1"].items() if l == "BENIGN_CALL"}
    ce = {c for c, l in C[a]["lab1"].items() if l == "BENIGN_CALL"}
    print(f"4 {a}: poison elig {len(pe)}, clean elig {len(ce)}, overlap {len(pe & ce)}, "
          f"poison elig within clean sample {len(pe & set(C[a]['sample']))}")
