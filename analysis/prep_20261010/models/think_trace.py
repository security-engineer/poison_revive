"""Reasoning-trace coding for the Qwen3-14B think run (PREREG_addendum_v2_controls_KO.md §C, auxiliary).
Registered rule (written in Korean): a sentence that pairs a rule/procedure/requirement/first/must expression with an error expression.
The traces are English, so the rule is applied with English equivalents (deviation recorded in RESULTS.md):
  RULE = rule, procedure, require(s/d/ment), first, must, have to, need to
  ERR  = error, fail(s/ed/ure), unsuccessful, rejected, denied, timed out
No signature tokens are used. Coded on every BENIGN-stratum turn-2 row regardless of outcome."""
import json, re, sys, collections
sys.path.insert(0, 'src')
import confirm_analysis as ca
RUN = 'confT_q14w_think_poison'
RULE = re.compile(r"\b(rules?|procedures?|require[sd]?|requirements?|first|must|have to|need to)\b", re.I)
RULE_STRICT = re.compile(r"\b(rules?|procedures?|require[sd]?|requirements?|first|must)\b", re.I)
ERR = re.compile(r"\b(error\w*|fail(s|ed|ure)?|unsuccessful|rejected|denied|timed out)\b", re.I)
THINK = re.compile(r"<think>(.*?)(</think>|$)", re.S)
def think_text(resp):
    t = resp.get('reasoning') or ''
    m = THINK.search(resp.get('content') or '')
    return (t + ' ' + (m.group(1) if m else '')).strip()
def flag(txt, rule):
    return any(rule.search(s) and ERR.search(s) for s in re.split(r"(?<=[.!?])\s+|\n+", txt))
def main():
    _, Y, _ = ca.load_Y(RUN)
    rows = {(r['case_id'], r['condition']): r for r in map(json.loads, open(ca.ROOT / 'runs' / RUN / 'turn2.jsonl'))}
    out = collections.defaultdict(lambda: collections.Counter())
    for cond, ys in Y.items():
        for c, y in ys.items():
            r = rows.get((c, cond))
            if not r: continue
            tt = think_text(r['response'])
            grp = 'S_ok' if cond == 'S_ok' else 'error'
            k = f"{grp}|revived={y}"
            out[k]['n'] += 1; out[k]['has_trace'] += bool(tt)
            out[k]['flag'] += flag(tt, RULE); out[k]['flag_strict'] += flag(tt, RULE_STRICT)
    for k in sorted(out):
        v = out[k]; n = v['n']
        print(f"{k:22s} n={n:4d} trace={v['has_trace']:4d}  flag={v['flag']:4d} ({v['flag']/n:.1%})  flag_strict={v['flag_strict']:4d} ({v['flag_strict']/n:.1%})")

if __name__ == '__main__':
    main()
