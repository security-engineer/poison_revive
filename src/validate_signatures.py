"""Validate frozen signatures against MCPTox's own labeled turn-1 responses.

MCPTox labels (LLM-judge + human check in the original paper):
  Success -> our MALICIOUS
  Failure-Ignored -> our BENIGN_CALL
  Failure-Direct Execution -> our DIRECT_EXEC
This is measurement validation only; MCPTox turn-1 responses are not our outcomes.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_common import classify, load_cases, load_signatures, DATA

MAP = {"Success": "MALICIOUS", "Failure-Ignored": "BENIGN_CALL", "Failure-Direct Execution": "DIRECT_EXEC"}


def main():
    sig_path = sys.argv[1] if len(sys.argv) > 1 else DATA / "signatures.jsonl"
    cases, sigs = load_cases(), load_signatures(sig_path)
    conf = collections.Counter()
    per_case = collections.defaultdict(collections.Counter)
    per_par = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    for cid, c in cases.items():
        s = sigs.get(cid)
        if s is None:
            continue
        for m, v in c["mcptox_ref"].items():
            lab, resp = v.get("label"), v.get("response")
            if lab not in MAP or not resp:
                continue
            ours = classify(resp, s)["label"]
            conf[(MAP[lab], ours)] += 1
            per_par[c["paradigm"]][(MAP[lab] == "MALICIOUS", ours == "MALICIOUS")] += 1
            agree = (MAP[lab] == "MALICIOUS") == (ours == "MALICIOUS")
            per_case[cid]["agree" if agree else "disagree"] += 1
            if not agree and len(examples[(MAP[lab], ours)]) < 400:
                examples[(MAP[lab], ours)].append({"case_id": cid, "model": m, "mcptox": lab, "ours": ours,
                                                    "resp": resp[:400]})
    tp = sum(v for (a, b), v in conf.items() if a == "MALICIOUS" and b == "MALICIOUS")
    fn = sum(v for (a, b), v in conf.items() if a == "MALICIOUS" and b != "MALICIOUS")
    fp = sum(v for (a, b), v in conf.items() if a != "MALICIOUS" and b == "MALICIOUS")
    tn = sum(v for (a, b), v in conf.items() if a != "MALICIOUS" and b != "MALICIOUS")
    n = tp + fn + fp + tn
    po = (tp + tn) / n
    pe = ((tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)) / n / n
    kappa = (po - pe) / (1 - pe)
    print(json.dumps({"n": n, "tp": tp, "fn": fn, "fp": fp, "tn": tn, "agreement": round(po, 4),
                      "kappa": round(kappa, 4)}))
    for k in sorted(conf):
        print(k, conf[k])
    for p, cc in sorted(per_par.items()):
        print(p, dict(cc))
    bad = sorted(((v["disagree"] / (v["agree"] + v["disagree"]), cid, dict(v)) for cid, v in per_case.items()
                  if v["disagree"]), reverse=True)
    print("cases with >=50% disagreement:", sum(1 for r, _, _ in bad if r >= 0.5), "of", len(per_case))
    out = Path(sig_path).with_suffix(".validation.json")
    out.write_text(json.dumps({"confusion": {f"{a}|{b}": v for (a, b), v in conf.items()},
                               "kappa": kappa, "agreement": po,
                               "worst_cases": bad[:150],
                               "disagree_examples": {f"{a}|{b}": v for (a, b), v in examples.items()}},
                              ensure_ascii=False, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
