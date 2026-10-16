"""Registered mechanism test (PREREG_addendum_v4_mechanism_scale_KO.md, frozen before the v4 runs).
Unit: BENIGN-stratum turn-2 rows under the 7 error conditions of conditions_v2_native.json.
  R = revived (report.relabel via confirm_analysis.load_Y)
  X_mention = the think trace names the poison carrier tool (from 'Tool: <name>' in poisoned_tool), case-insensitive
  X_reread  = the think trace says it checks/reviews/re-reads the tools/functions (REREAD regex)
Test: within-case permutation of R across that case's error rows (conditional association, case confounds removed),
one-sided (revived rows carry X more often), statistic T = sum(R*X), B = 20000, seed 20261011.
Effect: pooled P(X|R=1) - P(X|R=0) with case-cluster bootstrap 95% CI (B = 20000)."""
import json, re, random, sys
sys.path.insert(0, 'src')
import confirm_analysis as ca
ERR_CONDS = ['E_unknown', 'E_internal', 'E_invalid_arg', 'E_precondition', 'E_deadline', 'E_permission', 'E_unknown_remedy']
THINK = re.compile(r"<think>(.*?)(</think>|$)", re.S)
REREAD = re.compile(r"(check|look at|review|re-?read|re-?examine)\w*\s+(the\s+)?(available\s+)?(tools|functions)(\s+again)?", re.I)

def think_text(resp):
    m = THINK.search(resp.get('content') or '')
    return ((resp.get('reasoning') or '') + ' ' + (m.group(1) if m else '')).strip()

def carrier(case_id):
    m = re.match(r"Tool:\s*(\S+)", ca.CASES[case_id]['poisoned_tool'])
    return m.group(1) if m else None

def rows_of(run):
    _, Y, _ = ca.load_Y(run)
    raw = {(r['case_id'], r['condition']): r for r in map(json.loads, open(ca.ROOT / 'runs' / run / 'turn2.jsonl'))}
    out = {}
    for cond in ERR_CONDS:
        for c, y in Y.get(cond, {}).items():
            r = raw.get((c, cond))
            if r is None: continue
            tt = think_text(r['response']); car = carrier(c)
            out.setdefault(c, []).append({"R": int(y), "mention": int(bool(car) and car.lower() in tt.lower()),
                                          "reread": int(bool(REREAD.search(tt)))})
    return out

def test(rows, key, B=20000, seed=20261011):
    cases = sorted(rows)
    T = sum(r['R'] * r[key] for c in cases for r in rows[c])
    rng = random.Random(seed); k = 0
    for _ in range(B):
        t = 0
        for c in cases:
            Rs = [r['R'] for r in rows[c]]; rng.shuffle(Rs)
            t += sum(a * r[key] for a, r in zip(Rs, rows[c]))
        if t >= T: k += 1
    def diff(cs):
        a = [r[key] for c in cs for r in rows[c] if r['R']]; b = [r[key] for c in cs for r in rows[c] if not r['R']]
        return (sum(a) / len(a) - sum(b) / len(b)) if a and b else None
    rngb = random.Random(seed + 1); bs = []
    for _ in range(B):
        d = diff([cases[rngb.randrange(len(cases))] for _ in cases])
        if d is not None: bs.append(d)
    bs.sort()
    n1 = sum(r['R'] for c in cases for r in rows[c]); n0 = sum(1 - r['R'] for c in cases for r in rows[c])
    x1 = sum(r[key] for c in cases for r in rows[c] if r['R']); x0 = sum(r[key] for c in cases for r in rows[c] if not r['R'])
    return {"key": key, "cases": len(cases), "revived": f"{x1}/{n1}", "not_revived": f"{x0}/{n0}",
            "diff": round(diff(cases), 4) if diff(cases) is not None else None,
            "ci": [round(bs[int(.025 * len(bs))], 4), round(bs[int(.975 * len(bs)) - 1], 4)] if bs else None,
            "T": T, "p_perm_within_case": (k + 1) / (B + 1)}

if __name__ == '__main__':
    for run in sys.argv[1:]:
        rows = rows_of(run)
        print(json.dumps({"run": run, "M1_mention": test(rows, 'mention'), "M2_reread": test(rows, 'reread')}, default=str))
