"""k=5 repeats per (case, condition): per-case revival probability, between/within variance, single-draw stability."""
import json, sys, collections, statistics as st
sys.path.insert(0, 'src')
import report
d = report.ROOT / 'runs' / sys.argv[1]
t1 = {json.loads(l)['case_id']: json.loads(l) for l in open(d / 'turn1.jsonl')}
elig = {c for c, r in t1.items() if report.relabel(r, 'native') == 'BENIGN_CALL'}
Y = collections.defaultdict(lambda: collections.defaultdict(list))
for l in open(d / 'turn2.jsonl'):
    r = json.loads(l)
    if r['case_id'] not in elig: continue
    lab = report.relabel(r, 'native')
    if lab in ('ERROR_TRANSPORT', 'TRUNCATED'): continue
    Y[r['condition']][r['case_id']].append(int(lab == 'MALICIOUS'))
for cond in ['S_ok', 'E_unknown', 'E_invalid_arg']:
    ps = {c: sum(v) / len(v) for c, v in Y[cond].items() if len(v) >= 3}
    vals = list(ps.values()); n = len(vals)
    within = st.mean([(sum(v) / len(v)) * (1 - sum(v) / len(v)) for v in Y[cond].values() if len(v) >= 3])
    between = st.pvariance(vals) if n > 1 else 0
    dist = collections.Counter(round(p, 1) for p in vals)
    first = [Y[cond][c][0] for c in ps]; rest = [sum(Y[cond][c][1:]) / (len(Y[cond][c]) - 1) for c in ps]
    agree = sum(1 for f, r_ in zip(first, rest) if (f == 1) == (r_ >= 0.5)) / n
    print(f"{cond:14s} cases={n} mean_p={st.mean(vals):.3f} between_var={between:.4f} within_var={within:.4f} "
          f"cases_p>0={sum(1 for p in vals if p > 0)} cases_p=1={sum(1 for p in vals if p == 1)} first_vs_rest_agree={agree:.3f} dist={dict(sorted(dist.items()))}")
