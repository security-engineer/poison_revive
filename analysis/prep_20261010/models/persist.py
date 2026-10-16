"""Persistence analysis: Y_first (next step) vs Y_any (up to 1+persist steps; same error keeps returning)."""
import json, sys, collections
sys.path.insert(0, 'src')
import report, run_native
def load(run):
    d = report.ROOT / 'runs' / run
    t1 = {json.loads(l)['case_id']: json.loads(l) for l in open(d / 'turn1.jsonl')}
    elig = {c for c, r in t1.items() if report.relabel(r, 'native') == 'BENIGN_CALL'}
    agg = collections.defaultdict(lambda: collections.Counter())
    for l in open(d / 'turn2.jsonl'):
        r = json.loads(l)
        if r['case_id'] not in elig: continue
        sig = report.SIGS[r['case_id']]
        first = report.relabel(r, 'native')
        later = [run_native.label(st['calls'], sig) for st in r.get('later_steps', [])]
        any_mal = first == 'MALICIOUS' or 'MALICIOUS' in later
        k = r['condition']; agg[k]['n'] += 1; agg[k]['first'] += first == 'MALICIOUS'; agg[k]['any'] += any_mal
        agg[k]['steps>1'] += len(later) > 0
    return {k: dict(v) for k, v in agg.items()}
if __name__ == '__main__':
    for run in sys.argv[1:]:
        print(run)
        for k, v in sorted(load(run).items()):
            print(f"  {k:18s} n={v['n']:3d}  Y_first={v['first']:3d} ({v['first']/v['n']:.3f})  Y_any={v['any']:3d} ({v['any']/v['n']:.3f})  continued={v['steps>1']}")
