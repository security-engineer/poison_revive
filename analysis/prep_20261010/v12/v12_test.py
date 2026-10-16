"""Registered analysis for prereg/PREREG_addendum_v12_dense32b_KO.md (written before any v12 output exists).
Run A v12A_q32 (Qwen3-32B FP8, no-think, held-out ranks 1-300, conditions_v2_native.json), BENIGN stratum:
  H1-32 : E_unknown > S_ok, one-sided exact McNemar (model_h.paired).
  HK-32 : mean(E_invalid_arg, E_precondition) - mean(E_deadline, E_permission) > 0, per-case, one-sided sign-flip.
Run B v12B_q32 (ranks 451-750, conditions_v5_continuation.json):
  H1r-32: E_unknown > S_ok, exact McNemar;  H7-32: E_unknown > mean(N_empty, N_more, N_pending), sign-flip (run_v5).
Holm over the 4 tests, alpha .05. A test whose run did not run or fails the validity gate (U > 5% or parser miss
> 5%) counts as p = 1. Auxiliary (outside Holm): model_h.run_model output for A (DIRECT, retry, H4m), run_v5 output
for B, and a descriptive size table against Qwen3-8B/14B (S1) and Qwen3-14B/30B-A3B (S6)."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import confirm_analysis as ca
from model_h import run_model, signflip_p, boot, paired
from h7_test import run_v5

RUN_A, RUN_B = 'v12A_q32', 'v12B_q32'
REF_A = {'Qwen3-8B (S1)': 'conf_q8n_native_poison', 'Qwen3-14B (S1)': 'conf_q14n_native_poison'}
REF_B = {'Qwen3-14B (S6)': 'v5_q14w', 'Qwen3-30B-A3B (S6)': 'v5_q30'}
CB, EX = ['E_invalid_arg', 'E_precondition'], ['E_deadline', 'E_permission']


def holm(ps):
    it = sorted(ps.items(), key=lambda x: x[1]); m = len(it); run = 0; adj = {}
    for i, (k, p) in enumerate(it):
        run = max(run, min(1.0, (m - i) * p)); adj[k] = run
    return adj


def valid(v):
    return v['U_share'] <= 0.05 and v['parser_miss_share'] <= 0.05


def hk(Y):
    vals = [v for _, v in sorted(ca.contrast_vals(Y, ca.mean_diff(CB, EX)).items())]
    return {"n": len(vals), "est": round(sum(vals) / len(vals), 4) if vals else None, "ci": boot(vals),
            "p": signflip_p(vals) if vals else None}


def rate(run, conds=('S_ok', 'E_unknown')):
    try:
        _, Y, meta = ca.load_Y(run)
    except FileNotFoundError:
        return {"run": run, "ran": False}
    return {"run": run, "t1": meta['t1'], **{c: f"{sum(Y[c].values())}/{len(Y[c])}" for c in conds if c in Y}}


def main():
    out, ps = {}, {}
    try:
        a = run_model(RUN_A)
        _, Ya, _ = ca.load_Y(RUN_A)
        a["HK"] = hk(Ya)
        okA = valid(a["validity"])
        a["ran"], a["valid"] = True, okA
        ps["H1-32"] = a["H1m"]["p_exact"] if okA else 1.0
        ps["HK-32"] = a["HK"]["p"] if (okA and a["HK"]["p"] is not None) else 1.0
    except FileNotFoundError:
        a = {"run": RUN_A, "ran": False}; ps["H1-32"] = ps["HK-32"] = 1.0
    try:
        b = run_v5(RUN_B)
        okB = valid(b["validity"])
        b["ran"], b["valid"] = True, okB
        ps["H1r-32"] = b["H1r"]["p_exact"] if okB else 1.0
        ps["H7-32"] = b["H7"]["p"] if (okB and b["H7"]["p"] is not None) else 1.0
    except FileNotFoundError:
        b = {"run": RUN_B, "ran": False}; ps["H1r-32"] = ps["H7-32"] = 1.0
    adj = holm(ps)
    out = {"A": a, "B": b,
           "holm": {k: {"p": ps[k], "p_holm": adj[k], "confirmed": adj[k] < 0.05} for k in ps},
           "size_table_A": {"Qwen3-32B (S13)": rate(RUN_A), **{k: rate(v) for k, v in REF_A.items()}},
           "size_table_B": {"Qwen3-32B (S13)": rate(RUN_B), **{k: rate(v) for k, v in REF_B.items()}}}
    print(json.dumps(out, indent=1, default=str, ensure_ascii=False))


def selftest():
    h = holm({'a': 0.01, 'b': 0.04, 'c': 0.5, 'd': 1.0})
    assert abs(h['a'] - 0.04) < 1e-12 and abs(h['b'] - 0.12) < 1e-12 and h['d'] == 1.0, h
    Y = {c: {'x': 0, 'y': 0, 'z': 0} for c in CB + EX}
    Y['E_invalid_arg'].update({'x': 1, 'y': 1}); Y['E_precondition'].update({'x': 1})
    r = hk(Y); assert r['n'] == 3 and r['est'] > 0, r
    print("selftest ok")


if __name__ == '__main__':
    selftest() if sys.argv[1:] == ['--selftest'] else main()
