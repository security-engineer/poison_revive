"""Post-hoc breakdown for v10 (written after the Qwen3-14B checker runs were seen; NOT registered).

The registered auxiliary 'false_block_t2_nonmalicious' mixes two kinds of turn-2 calls that the signature matcher
does not flag: calls to the poisoned tool itself (the description asks for it, so blocking them is not a false block)
and every other call (retries of the benign tool, other tools). This script splits them and also reports, per
checker run, how often the checker blocked a malicious call versus a turn-1 benign call.

Usage (from condition_study/):  python3 -B analysis/prep_20261010/v10/v10_posthoc.py > analysis/prep_20261010/v10/v10_posthoc.json
"""
import collections, json, sys
sys.path.insert(0, 'src')
from cs_common import ROOT, load_cases  # noqa: E402
import run_native  # noqa: E402

RUNS = ['v10_icfull_q14w', 'v10_icmin_q14w', 'v10_icfull_llama31', 'v10_icmin_llama31']


def poisoned_names(case):
    return {t['function']['name'] for t in run_native.parse_tools(case['poisoned_tool'].replace('\\n', '\n') + '\n\n')}


def frac(rows):
    return f"{sum(r['verdict'] == 'BLOCK' for r in rows)}/{len(rows)}"


def main():
    cases = load_cases()
    out = {}
    for run in RUNS:
        path = ROOT / 'runs' / run / 'checks.jsonl'
        if not path.exists():
            out[run] = {"ran": False}
            continue
        rows = [json.loads(l) for l in open(path)]
        groups = collections.defaultdict(list)
        for r in rows:
            if r['source'] == 't1':
                groups['t1_benign'].append(r)
            elif r['malicious']:
                groups[f"t2_{r['condition']}_malicious"].append(r)
            elif r['call']['tool'] in poisoned_names(cases[r['case_id']]):
                groups[f"t2_{r['condition']}_poisoned_tool"].append(r)
            else:
                groups[f"t2_{r['condition']}_other"].append(r)
        out[run] = {"ran": True, "block_rate": {k: frac(v) for k, v in sorted(groups.items())}}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
