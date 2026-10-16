"""Per-model registered tests for the model-extension addendum (PREREG_addendum_models_v1_KO.md).
H1m: E_unknown > S_ok (exact one-sided McNemar, BENIGN); H3m remedy; H4m gap; H5m registered fit; H6m DIRECT.
Also measurement-validity gates: U share and parser-miss share."""
import json, random, sys, collections
from math import comb
sys.path.insert(0, 'src')
import confirm_analysis as ca
CASES = ca.CASES

def mcnemar_one_sided(b, c):
    n = b + c
    return 1.0 if n == 0 else sum(comb(n, k) for k in range(b, n + 1)) / 2 ** n

def boot(vals, B=20000, seed=20261010):
    if not vals: return (None, None)
    rng = random.Random(seed); n = len(vals); m = []
    for _ in range(B): m.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    m.sort(); return (round(m[int(.025 * B)], 4), round(m[int(.975 * B) - 1], 4))

def signflip_p(vals, B=20000, seed=7):
    obs = sum(vals); rng = random.Random(seed); k = 0
    for _ in range(B):
        if sum(v if rng.random() < .5 else -v for v in vals) >= obs - 1e-12: k += 1
    return (k + 1) / (B + 1)

def paired(Y, a, b):
    cs = sorted(set(Y.get(a, {})) & set(Y.get(b, {})))
    d = [Y[a][c] - Y[b][c] for c in cs]
    bb = sum(1 for c in cs if Y[a][c] == 1 and Y[b][c] == 0); cc = sum(1 for c in cs if Y[a][c] == 0 and Y[b][c] == 1)
    return {"n": len(cs), "a": sum(Y[a][c] for c in cs), "b": sum(Y[b][c] for c in cs), "diff": round(sum(d) / len(d), 4) if d else None,
            "ci": boot(d), "discordant": (bb, cc), "p_exact": mcnemar_one_sided(bb, cc)}

def validity(run):
    d = ca.ROOT / 'runs' / run
    rows = [json.loads(l) for f in ('turn1.jsonl', 'turn2.jsonl') for l in open(d / f)]
    n = len(rows); u = 0; miss = 0
    for r in rows:
        resp = r.get('response') or {}
        if not resp.get('ok', True) or (resp.get('finish_reason') == 'length' and not resp.get('tool_calls')): u += 1
        if r.get('text_calls') and not r.get('calls'): miss += 1
    return {"rows": n, "U_share": round(u / n, 4), "parser_miss_share": round(miss / n, 4)}

def run_model(run):
    ag, Y, meta = ca.load_Y(run)
    _, Yd, _ = ca.load_Y(run, strata=('DIRECT_EXEC',))
    res = {"agent": ag, "t1": meta['t1'], "validity": validity(run),
           "Y": {k: f"{sum(v.values())}/{len(v)}" for k, v in Y.items()},
           "Y_direct": {k: f"{sum(v.values())}/{len(v)}" for k, v in Yd.items()},
           "H1m": paired(Y, 'E_unknown', 'S_ok'), "H3m": paired(Y, 'E_unknown', 'E_unknown_remedy'),
           "H6m": paired(Yd, 'E_unknown', 'S_ok')}
    h4 = [v for _, v in sorted(ca.contrast_vals(Y, ca.mean_diff(['E_unknown', 'E_internal'], ['E_deadline', 'E_permission'])).items())]  # sorted: hash-seed independent
    res["H4m"] = {"n": len(h4), "est": round(sum(h4) / len(h4), 4) if h4 else None, "ci": boot(h4), "p": signflip_p(h4) if h4 else None}
    def side(par):
        v = [Y['E_invalid_arg'][c] - Y['E_precondition'][c] for c in sorted(set(Y.get('E_invalid_arg', {})) & set(Y.get('E_precondition', {}))) if CASES[c]['paradigm'] == par]
        return v
    t3, t2 = side('Template-3'), side('Template-2')
    m3 = sum(t3) / len(t3) if t3 else 0; m2 = sum(t2) / len(t2) if t2 else 0
    # permutation p over template labels for the registered estimator
    allv = [(d, 'T3') for d in t3] + [(d, 'T2') for d in t2]
    rng = random.Random(11); k = 0; B = 20000; obs = m3 - m2
    for _ in range(B):
        lab = [x[1] for x in allv]; rng.shuffle(lab)
        a = [x[0] for x, l in zip(allv, lab) if l == 'T3']; b = [x[0] for x, l in zip(allv, lab) if l == 'T2']
        if a and b and (sum(a) / len(a) - sum(b) / len(b)) >= obs - 1e-12: k += 1
    res["H5m"] = {"m3": round(m3, 4), "m2": round(m2, 4), "est": round(obs, 4), "n3": len(t3), "n2": len(t2), "p_perm": (k + 1) / (B + 1)}
    return res

if __name__ == '__main__':
    out = {r: run_model(r) for r in sys.argv[1:]}
    print(json.dumps(out, indent=1, default=str))
