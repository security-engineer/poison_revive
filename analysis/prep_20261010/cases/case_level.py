"""EXPLORATORY (post hoc): is revival a property of the attack case, shared across models?
Per model, a case 'revives' if any of the 7 error conditions revives it (BENIGN stratum, report.relabel via load_Y).
Reports pairwise cross-model concordance on cases eligible in both models, and revival by case attributes."""
import sys, json, itertools, collections, random
sys.path.insert(0, 'src')
import confirm_analysis as ca
RUNS = {"Qwen3-14B": "conf_q14n_native_poison", "Qwen3-8B": "conf_q8n_native_poison",
        "Llama-3.1-8B": "confM_llama31_native_poison", "Gemma-4-12B": "confM_gemma4_native_poison"}
ERR = ['E_unknown', 'E_internal', 'E_invalid_arg', 'E_precondition', 'E_deadline', 'E_permission', 'E_unknown_remedy']
rev = {}
for m, r in RUNS.items():
    _, Y, _ = ca.load_Y(r)
    cases = set.intersection(*[set(Y[c]) for c in ERR if c in Y])
    rev[m] = {c: int(any(Y[k][c] for k in ERR)) for c in cases}
out = {"per_model": {m: f"{sum(v.values())}/{len(v)}" for m, v in rev.items()}, "pairs": []}
def boot_or(pairs, B=5000, seed=1):
    rng = random.Random(seed); vals = []
    for _ in range(B):
        s = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        a = sum(1 for x, y in s if x and y) + .5; b = sum(1 for x, y in s if x and not y) + .5
        c = sum(1 for x, y in s if not x and y) + .5; d = sum(1 for x, y in s if not x and not y) + .5
        vals.append(a * d / (b * c))
    vals.sort(); return [round(vals[int(.025 * B)], 2), round(vals[int(.975 * B) - 1], 2)]
for a, b in itertools.combinations(RUNS, 2):
    cs = sorted(set(rev[a]) & set(rev[b])); pairs = [(rev[a][c], rev[b][c]) for c in cs]
    n11 = sum(1 for x, y in pairs if x and y); n10 = sum(1 for x, y in pairs if x and not y)
    n01 = sum(1 for x, y in pairs if not x and y); n00 = len(pairs) - n11 - n10 - n01
    p_b_given_a = n11 / (n11 + n10) if n11 + n10 else None; p_b_given_not_a = n01 / (n01 + n00) if n01 + n00 else None
    orr = (n11 + .5) * (n00 + .5) / ((n10 + .5) * (n01 + .5))
    out["pairs"].append({"pair": f"{a} ~ {b}", "n": len(cs), "both": n11, "only_a": n10, "only_b": n01, "neither": n00,
                         "P(b|a)": round(p_b_given_a, 3) if p_b_given_a is not None else None,
                         "P(b|not a)": round(p_b_given_not_a, 3) if p_b_given_not_a is not None else None,
                         "OR": round(orr, 2), "OR_ci": boot_or(pairs)})
# cases eligible in all 4 models
allc = sorted(set.intersection(*[set(v) for v in rev.values()]))
k = collections.Counter(sum(rev[m][c] for m in RUNS) for c in allc)
out["all4"] = {"n": len(allc), "models_reviving_distribution": dict(sorted(k.items()))}
# expected distribution if models were independent (same marginals)
ps = [sum(rev[m][c] for c in allc) / len(allc) for m in RUNS]
exp = collections.Counter()
for bits in itertools.product([0, 1], repeat=4):
    pr = 1
    for b_, p in zip(bits, ps): pr *= p if b_ else 1 - p
    exp[sum(bits)] += pr * len(allc)
out["all4"]["expected_if_independent"] = {i: round(exp[i], 1) for i in sorted(exp)}
out["all4"]["cases_reviving_in_all_4"] = [c for c in allc if all(rev[m][c] for m in RUNS)]
# attributes: pooled over models (case-model rows)
for attr in ("paradigm", "risk", "server"):
    t = collections.defaultdict(lambda: [0, 0])
    for m in RUNS:
        for c, y in rev[m].items():
            t[ca.CASES[c][attr]][0] += y; t[ca.CASES[c][attr]][1] += 1
    rows = sorted(((k_, v[0], v[1]) for k_, v in t.items() if v[1] >= (8 if attr == 'server' else 1)), key=lambda x: -x[1] / x[2])
    out[f"by_{attr}"] = [f"{k_}: {a}/{n} = {a / n:.3f}" for k_, a, n in rows]
print(json.dumps(out, indent=1, ensure_ascii=False))
