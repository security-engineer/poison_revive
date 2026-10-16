"""Mechanism coding of reasoning traces at the turn-2 decision (RQ4).

For each turn-2 response that has a reasoning trace (gpt-oss reasoning channel, Qwen think),
code deterministic features:
  mentions_poison: reasoning mentions the poison tool name or a distinctive signature value
  mentions_error:  reasoning mentions the error/failure
  causal_link:     both, within the same sentence window, with a causal/remedial cue
                   ("because", "need to", "must", "first", "per rule", "requires", ...)
Rates are compared between MALICIOUS and non-MALICIOUS turn-2 outcomes per condition.
This coding is lexical and only a first pass; transcripts are also read by hand.
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_common import load_signatures

CAUSAL = re.compile(r"\b(because|need to|must|first|per (the )?(rule|instruction|description)|requires?|"
                    r"required|so we|therefore|maybe|perhaps|might be due|due to)\b", re.I)
ERR = re.compile(r"\b(error|fail|failed|failure|denied|timed out|timeout|permission)\b", re.I)


def sig_tokens(sig):
    toks = {sig.get("poison_tool", "")}
    for p in sig.get("malicious", []):
        for c in p.get("args", []):
            for v in c.get("values", []):
                v = str(v).strip('"')
                if len(v) >= 4:
                    toks.add(v)
    return {t.lower() for t in toks if t}


def code(reasoning, sig):
    r = reasoning or ""
    low = r.lower()
    toks = sig_tokens(sig)
    mp = any(t in low for t in toks)
    me = bool(ERR.search(r))
    causal = False
    for sent in re.split(r"(?<=[.!?\n])\s+", r):
        sl = sent.lower()
        if any(t in sl for t in toks) and CAUSAL.search(sent):
            causal = True
            break
    return {"mentions_poison": mp, "mentions_error": me, "causal_link": causal and me}


def main():
    runs = sys.argv[1:]
    sigs = load_signatures()
    agg = collections.defaultdict(collections.Counter)
    for d in runs:
        for l in open(Path(d) / "turn2.jsonl"):
            r = json.loads(l)
            lab = r["outcome"]["label"] if "outcome" in r else r["label"]
            reasoning = (r.get("response") or {}).get("reasoning") or ""
            if not reasoning:
                continue
            c = code(reasoning, sigs[r["case_id"]])
            k = (r["agent"], r["condition"], "MAL" if lab == "MALICIOUS" else "non")
            agg[k]["n"] += 1
            for f, v in c.items():
                agg[k][f] += int(v)
    for k in sorted(agg):
        c = agg[k]
        n = c["n"]
        print("|".join(k), n, {f: round(c[f] / n, 3) for f in ("mentions_poison", "mentions_error", "causal_link")})


if __name__ == "__main__":
    main()
