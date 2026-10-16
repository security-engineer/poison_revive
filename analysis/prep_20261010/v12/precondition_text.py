"""POST HOC (written after the v12 outputs were read): how revived Qwen3-32B responses explain themselves.
For each revived branch in run v12A_q32 (benign stratum, load_Y), report the poison template and whether the
response text matches KEYWORDS (a rule/requirement/precondition the agent says must come first). Writes
precondition_text.json next to this file."""
import collections, json, re, sys
from pathlib import Path
sys.path.insert(0, 'src')
import confirm_analysis as ca

KEYWORDS = re.compile(r"precondition|prerequisite|requirement|must first|first (delete|call|post|perform|run|execute)"
                      r"|before|rule", re.I)


def main():
    _, Y, _ = ca.load_Y('v12A_q32')
    rows = [json.loads(l) for l in open(ca.ROOT / 'runs/v12A_q32/turn2.jsonl')]
    out = collections.defaultdict(lambda: {"revived": 0, "template2": 0, "with_text": 0, "keyword": 0, "cases": []})
    for r in rows:
        c, cid = r['condition'], r['case_id']
        if Y.get(c, {}).get(cid) != 1:
            continue
        txt = ((r.get('response') or {}).get('content') or '')
        o = out[c]
        o["revived"] += 1; o["template2"] += ca.CASES[cid]['paradigm'] == 'Template-2'
        o["with_text"] += bool(txt.strip()); o["keyword"] += bool(KEYWORDS.search(txt)); o["cases"].append(cid)
    res = {"keywords_regex": KEYWORDS.pattern, "by_condition": out}
    json.dump(res, open(Path(__file__).resolve().parent / "precondition_text.json", "w"), indent=1)
    for c, o in out.items():
        print(c, {k: v for k, v in o.items() if k != "cases"})


if __name__ == '__main__':
    main()
