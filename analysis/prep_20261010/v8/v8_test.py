"""Registered analysis for prereg/PREREG_addendum_v8_scale_KO.md (written before any v8 output exists).
Run v8_goss120 (gpt-oss-120b, held-out hash ranks 451-937, conditions_v5_continuation.json), BENIGN stratum.
H7  : E_unknown > mean(N_empty, N_more, N_pending), per-case contrast, one-sided sign-flip (h7_test.h7_vals).
H1r : E_unknown > S_ok, one-sided exact McNemar (model_h.paired).
Holm over the 2 tests, alpha .05; an unrun test or one failing the validity gate (U > 5% or parser miss > 5%) counts
as p = 1. Auxiliary (outside Holm): everything else run_v5 reports (continuation counts, paraphrased errors vs S_ok,
P-CB), and the same numbers for v5_goss (gpt-oss-20b) side by side."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
from h7_test import run_v5

RUN = 'v8_goss120'
REF = 'v5_goss'

def holm(ps):
    it = sorted(ps.items(), key=lambda x: x[1]); m = len(it); run = 0; adj = {}
    for i, (k, p) in enumerate(it):
        run = max(run, min(1.0, (m - i) * p)); adj[k] = run
    return adj

def one(run):
    try:
        r = run_v5(run)
    except FileNotFoundError:
        return {"run": run, "ran": False}, 1.0, 1.0
    v = r["validity"]
    ok = v['U_share'] <= 0.05 and v['parser_miss_share'] <= 0.05
    p7 = r["H7"]["p"] if (ok and r["H7"]["p"] is not None) else 1.0
    p1 = r["H1r"]["p_exact"] if ok else 1.0
    r["ran"], r["valid"] = True, ok
    return r, p7, p1

def main():
    r, p7, p1 = one(RUN)
    ps = {"H7 gpt-oss-120b": p7, "H1r gpt-oss-120b": p1}
    adj = holm(ps)
    ref, _, _ = one(REF)
    out = {"v8": r, "holm": {k: {"p": ps[k], "p_holm": adj[k], "confirmed": adj[k] < 0.05} for k in ps},
           "reference_v5_goss_20b": ref}
    print(json.dumps(out, indent=1, default=str, ensure_ascii=False))

if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        h = holm({'a': 0.01, 'b': 0.04}); assert abs(h['a'] - 0.02) < 1e-12 and abs(h['b'] - 0.04) < 1e-12
        print("selftest ok")
    else:
        main()
