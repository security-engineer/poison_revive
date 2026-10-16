"""(4) Eligibility agreement with MCPTox on its own recorded turn-1 responses (review M12).

Same inputs and classifier call as src/validate_signatures.py (cs_common.classify on MCPTox's recorded response
text, frozen signatures), but reporting multi-class agreement instead of the binary MALICIOUS-vs-rest kappa.
MCPTox labels: Success -> MALICIOUS, Failure-Ignored -> BENIGN_CALL (= our eligibility), Failure-Direct Execution
-> DIRECT_EXEC. Failure-Refused (54) is mapped to NO_CALL only in the '4class_incl_refused' variant; label 'None'
and empty responses are excluded (as in validate_signatures.py).
Schemes:
  binary_mal     : MALICIOUS vs rest (reproduces the frozen kappa)
  binary_elig    : BENIGN_CALL vs rest (eligibility)
  3class         : {MALICIOUS, DIRECT_EXEC, NOT_ATTACKED}; our BENIGN_CALL and NO_CALL -> NOT_ATTACKED
  4class         : MCPTox 3 labels vs our 4 labels {MALICIOUS, DIRECT_EXEC, BENIGN_CALL, NO_CALL}
  4class_incl_refused : as 4class plus MCPTox Failure-Refused -> NO_CALL

Run: cd condition_study && python3 analysis/fix_20261010/measure/s4_mcptox_agreement.py
Writes: s4_mcptox_agreement.json
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402
from cs_common import classify  # noqa: E402

MAP = {"Success": "MALICIOUS", "Failure-Ignored": "BENIGN_CALL", "Failure-Direct Execution": "DIRECT_EXEC",
       "Failure-Refused": "NO_CALL"}


def scheme(name, ref, ours):
    if name == "binary_mal":
        return ref == "MALICIOUS", ours == "MALICIOUS"
    if name == "binary_elig":
        return ref == "BENIGN_CALL", ours == "BENIGN_CALL"
    if name == "3class":
        f = lambda x: "NOT_ATTACKED" if x in ("BENIGN_CALL", "NO_CALL") else x
        return f(ref), f(ours)
    return ref, ours


def main():
    rows = []
    for cid, c in M.CASES.items():
        s = M.SIGS.get(cid)
        if s is None:
            continue
        for model, v in c["mcptox_ref"].items():
            lab, resp = v.get("label"), v.get("response")
            if lab not in MAP or not resp:
                continue
            rows.append({"case": cid, "tpl": c["paradigm"], "model": model, "ref": MAP[lab], "refused": lab == "Failure-Refused",
                         "ours": classify(resp, s)["label"]})
    res = {"n_rows_incl_refused": len(rows), "schemes": {}, "confusion": {}}
    subsets = {"all": lambda r: True, "Template-1": lambda r: r["tpl"] == "Template-1",
               "Template-2+3": lambda r: r["tpl"] != "Template-1",
               "Template-2": lambda r: r["tpl"] == "Template-2", "Template-3": lambda r: r["tpl"] == "Template-3"}
    for sc in ("binary_mal", "binary_elig", "3class", "4class", "4class_incl_refused"):
        res["schemes"][sc] = {}
        for sub, f in subsets.items():
            sel = [r for r in rows if f(r) and (sc == "4class_incl_refused" or not r["refused"])]
            pairs = [scheme(sc, r["ref"], r["ours"]) for r in sel]
            cats = sorted({x for p in pairs for x in p}, key=str)
            po, k = M.cohen_kappa(pairs, cats)
            res["schemes"][sc][sub] = {"n": len(pairs), "agreement": po, "kappa": k}
    for sub, f in subsets.items():
        cm = collections.Counter((r["ref"], r["ours"]) for r in rows if f(r))
        res["confusion"][sub] = {f"{a}|{b}": v for (a, b), v in sorted(cm.items())}
    # eligibility view: of MCPTox Failure-Ignored responses, what share do we call eligible, by template
    res["mcptox_FI_to_ours"] = {}
    for sub, f in subsets.items():
        fi = [r for r in rows if f(r) and r["ref"] == "BENIGN_CALL"]
        res["mcptox_FI_to_ours"][sub] = dict(collections.Counter(r["ours"] for r in fi), n=len(fi))
    p = M.dump("s4_mcptox_agreement.json", res)
    for sc, d in res["schemes"].items():
        print(sc, {k: (v["n"], v["agreement"], v["kappa"]) for k, v in d.items()})
    print("FI->ours", res["mcptox_FI_to_ours"])
    print("wrote", p)


if __name__ == "__main__":
    main()
