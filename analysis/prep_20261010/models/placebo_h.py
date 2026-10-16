"""PREREG_addendum_v2 A: benign-rule placebo. Labels use the placebo signatures (not the malicious ones)."""
import json, sys, collections
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import run_native
from model_h import mcnemar_one_sided, boot
PL = json.load(open('data/placebo_rules_v1.json'))['cases']
def load(run, strata=('BENIGN_CALL',)):
    d = f'runs/{run}'
    lab1 = {}
    for l in open(f'{d}/turn1.jsonl'):
        r = json.loads(l); calls, _ = run_native.calls_of(r['response']) if r['response'].get('ok', True) else ([], [])
        lab1[r['case_id']] = run_native.label(calls, PL[r['case_id']]['signature']) if r['response'].get('ok', True) else 'ERR'
    Y = collections.defaultdict(dict)
    for l in open(f'{d}/turn2.jsonl'):
        r = json.loads(l)
        if lab1.get(r['case_id']) not in strata or not r['response'].get('ok', True): continue
        calls, _ = run_native.calls_of(r['response'])
        Y[r['condition']][r['case_id']] = int(run_native.label(calls, PL[r['case_id']]['signature']) == 'MALICIOUS')
    return Y, collections.Counter(lab1.values())
def contrast(Y, a='E_unknown', b='S_ok', sub=None):
    cs = sorted(c for c in set(Y[a]) & set(Y[b]) if sub is None or PL[c]['mechanism'] == sub)
    d = [Y[a][c] - Y[b][c] for c in cs]
    bb = sum(1 for c in cs if Y[a][c] and not Y[b][c]); cc = sum(1 for c in cs if not Y[a][c] and Y[b][c])
    return {"n": len(cs), "a": sum(Y[a][c] for c in cs), "b": sum(Y[b][c] for c in cs), "diff": round(sum(d)/len(d),4) if d else None, "ci": boot(d), "disc": (bb, cc), "p": mcnemar_one_sided(bb, cc)}
if __name__ == '__main__':
    for run in sys.argv[1:]:
        Y, t1 = load(run)
        print(run, 't1', dict(t1))
        print('  Y', {k: f"{sum(v.values())}/{len(v)}" for k, v in sorted(Y.items())})
        for sub in [None, 'param_tamper', 'precondition_hijack']:
            if 'E_unknown' in Y: print('  E_unknown-S_ok', sub or 'all', contrast(Y, sub=sub))
            if 'E_invalid_arg' in Y: print('  E_invalid_arg-S_ok', sub or 'all', contrast(Y, 'E_invalid_arg', 'S_ok', sub))
