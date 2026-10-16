"""v5 draft analysis (prereg/PREREG_addendum_v5_continuation_DRAFT_KO.md). Not registered until that draft is committed.
H7: E_unknown > mean(N_empty, N_more, N_pending), BENIGN stratum, per-case contrast, one-sided sign-flip (as H4m in model_h.py).
H1r: E_unknown > S_ok, exact one-sided McNemar.
Auxiliary: per condition, share of rows with any next-turn tool call and revival per new (non-verbatim-repeat) call;
E_unknown_p1 / E_unknown_p2 vs S_ok; P-CB re-check E_invalid_arg > E_unknown."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import confirm_analysis as ca
from model_h import boot, signflip_p, paired, validity

N_CONDS = ['N_empty', 'N_more', 'N_pending']

def h7_vals(Y):
    return [x for _, x in sorted(ca.contrast_vals(Y, ca.mean_diff(['E_unknown'], N_CONDS)).items())]

def continuation(run, Y):
    """Any next-turn call, and signature-matched share among new calls (a call identical to the turn-1 call is a re-send)."""
    d = ca.ROOT / 'runs' / run
    t1 = {r['case_id']: r for r in map(json.loads, open(d / 'turn1.jsonl'))}
    raw = {(r['case_id'], r['condition']): r for r in map(json.loads, open(d / 'turn2.jsonl'))}
    out = {}
    for cond, ys in Y.items():
        anyc = new = mal_new = 0
        for c, y in ys.items():
            r = raw.get((c, cond))
            calls = (r or {}).get('calls') or []
            if calls: anyc += 1
            first = (t1.get(c) or {}).get('calls') or []
            fresh = [x for x in calls if x not in first]
            if fresh:
                new += 1; mal_new += int(y)
        out[cond] = {"n": len(ys), "any_call": anyc, "rows_with_new_call": new, "revived_among_new": mal_new}
    return out

def run_v5(run):
    _, Y, meta = ca.load_Y(run)
    v = h7_vals(Y)
    return {"run": run, "t1": meta['t1'], "validity": validity(run),
            "Y": {k: f"{sum(x.values())}/{len(x)}" for k, x in Y.items()},
            "H7": {"n": len(v), "est": round(sum(v) / len(v), 4) if v else None, "ci": boot(v), "p": signflip_p(v) if v else None},
            "H1r": paired(Y, 'E_unknown', 'S_ok'),
            "aux_p1": paired(Y, 'E_unknown_p1', 'S_ok'), "aux_p2": paired(Y, 'E_unknown_p2', 'S_ok'),
            "aux_pcb": paired(Y, 'E_invalid_arg', 'E_unknown'),
            "continuation": continuation(run, Y)}

def _selftest():
    Y = {'E_unknown': {'a': 1, 'b': 1, 'c': 0}, 'N_empty': {'a': 0, 'b': 0, 'c': 0}, 'N_more': {'a': 1, 'b': 0, 'c': 0},
         'N_pending': {'a': 0, 'b': 0, 'c': 1}, 'S_ok': {'a': 0, 'b': 0, 'c': 0}}
    v = h7_vals(Y)
    assert [round(x, 4) for x in v] == [round(1 - 1 / 3, 4), 1.0, round(-1 / 3, 4)], v
    assert paired(Y, 'E_unknown', 'S_ok')['discordant'] == (2, 0)
    print("selftest ok")

if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        _selftest()
    else:
        for run in sys.argv[1:]:
            print(json.dumps(run_v5(run), default=str))
