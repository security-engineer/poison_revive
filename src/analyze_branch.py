"""Analyze counterfactual-branch runs.

Unit of inference = case. For each (agent, arm), eligible prefixes are branched
into every condition, so condition contrasts are paired within case.

Reports per agent x arm x condition:
  n, malicious rate (Y), direct-exec rate, repeat-call rate, no-call rate, truncated
and paired contrasts vs a reference condition with case-cluster bootstrap CIs,
plus the clean-subtracted contrast D = (poison_c - poison_ref) - (clean_c - clean_ref)
computed on case-level rates.
"""
import argparse
import collections
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _norm_row(r, proto):
    # native rows keep `label` at top level; text-protocol rows keep it under `outcome`
    if "outcome" not in r:
        r["outcome"] = {"label": r.get("label"), "repeat_t1_call": False}
    r["agent"] = f"{r['agent']}@{proto}"
    return r


def load_rows(run_dirs):
    t1, t2 = [], []
    for d in run_dirs:
        d = Path(d)
        proto = json.load(open(d / "manifest.json")).get("protocol", "text")
        t1 += [_norm_row(json.loads(l), proto) for l in open(d / "turn1.jsonl")]
        t2 += [_norm_row(json.loads(l), proto) for l in open(d / "turn2.jsonl")]
    return t1, t2


def boot_ci(values, B=4000, seed=7):
    if not values:
        return (None, None)
    rng = random.Random(seed)
    n = len(values)
    ms = []
    for _ in range(B):
        s = [values[rng.randrange(n)] for _ in range(n)]
        ms.append(sum(s) / n)
    ms.sort()
    return (round(ms[int(0.025 * B)], 4), round(ms[int(0.975 * B) - 1], 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--ref", default="S_ok")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    t1, t2 = load_rows(a.runs)
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(ROOT / "data" / "cases.jsonl")}
    report = {"turn1": {}, "turn2": {}, "contrasts": {}}

    # turn-1 summary (MCPTox-comparable ASR)
    g1 = collections.defaultdict(collections.Counter)
    for r in t1:
        g1[(r["agent"], r["arm"])][r["outcome"]["label"]] += 1
    for k, c in sorted(g1.items()):
        n = sum(c.values())
        report["turn1"]["|".join(k)] = {"n": n, **dict(c), "asr": round(c["MALICIOUS"] / n, 4) if n else None,
                                        "eligible": c["BENIGN_CALL"]}

    # turn-2: case-level indicators
    Y = collections.defaultdict(dict)  # (agent, arm, cond) -> {case: 0/1}
    g2 = collections.defaultdict(collections.Counter)
    for r in t2:
        k = (r["agent"], r["arm"], r["condition"])
        lab = r["outcome"]["label"]
        g2[k][lab] += 1
        if r["outcome"].get("repeat_t1_call"):
            g2[k]["repeat_t1_call"] += 1
        if lab in ("ERROR_TRANSPORT", "TRUNCATED"):
            continue
        Y[k][r["case_id"]] = 1 if lab == "MALICIOUS" else 0
    for k, c in sorted(g2.items()):
        n = sum(v for kk, v in c.items() if kk != "repeat_t1_call")
        ys = list(Y[k].values())
        report["turn2"]["|".join(k)] = {"n": n, **dict(c), "Y": round(sum(ys) / len(ys), 4) if ys else None,
                                        "Y_ci": boot_ci(ys)}

    # paired contrasts vs ref within (agent, arm), by paradigm too
    agents = sorted({(k[0], k[1]) for k in Y})
    conds = sorted({k[2] for k in Y})
    for ag, arm in agents:
        ref = Y.get((ag, arm, a.ref), {})
        for cnd in conds:
            if cnd == a.ref:
                continue
            cur = Y.get((ag, arm, cnd), {})
            common = sorted(set(ref) & set(cur))
            diffs = [cur[c] - ref[c] for c in common]
            flips_up = sum(1 for c in common if cur[c] == 1 and ref[c] == 0)
            flips_dn = sum(1 for c in common if cur[c] == 0 and ref[c] == 1)
            by_par = {}
            for par in ("Template-1", "Template-2", "Template-3"):
                dd = [cur[c] - ref[c] for c in common if cases[c]["paradigm"] == par]
                by_par[par] = {"n": len(dd), "diff": round(sum(dd) / len(dd), 4) if dd else None,
                               "ci": boot_ci(dd)}
            report["contrasts"][f"{ag}|{arm}|{cnd}-{a.ref}"] = {
                "n_pairs": len(common), "diff": round(sum(diffs) / len(diffs), 4) if diffs else None,
                "ci": boot_ci(diffs), "up": flips_up, "down": flips_dn, "by_paradigm": by_par}

    # clean-subtracted D (case sets differ between arms; use arm-level rates with independent bootstrap)
    for ag in sorted({k[0] for k in Y}):
        for cnd in conds:
            if cnd == a.ref:
                continue
            pk = [(ag, "poison", cnd), (ag, "poison", a.ref), (ag, "clean", cnd), (ag, "clean", a.ref)]
            if not all(k in Y for k in pk):
                continue
            pp = Y[pk[0]]; pr = Y[pk[1]]; cc = Y[pk[2]]; cr = Y[pk[3]]
            pc = sorted(set(pp) & set(pr)); ccs = sorted(set(cc) & set(cr))
            dp = [pp[c] - pr[c] for c in pc]; dc = [cc[c] - cr[c] for c in ccs]
            rng = random.Random(11); B = 4000; ds = []
            for _ in range(B):
                sp = [dp[rng.randrange(len(dp))] for _ in dp] if dp else [0]
                sc = [dc[rng.randrange(len(dc))] for _ in dc] if dc else [0]
                ds.append(sum(sp) / len(sp) - sum(sc) / len(sc))
            ds.sort()
            D = (sum(dp) / len(dp) if dp else 0) - (sum(dc) / len(dc) if dc else 0)
            report["contrasts"][f"{ag}|D|{cnd}-{a.ref}"] = {"D": round(D, 4),
                                                            "ci": (round(ds[100], 4), round(ds[3899], 4)),
                                                            "n_poison": len(dp), "n_clean": len(dc)}
    txt = json.dumps(report, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
