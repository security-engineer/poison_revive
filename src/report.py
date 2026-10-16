"""Build the main results table/figure from finished runs.

Per (agent@protocol): turn-1 ASR (MCPTox-style), eligible count, Y per condition (poison/clean),
paired diff vs S_ok with case-bootstrap CI, and the error-conditioned ASR:
    ASR_err(c) = P(mal at t1) + P(eligible) * P(mal at t2 | eligible, c)
"""
import collections
import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["S_ok", "S_empty", "E_flag_empty", "E_generic", "E_perm", "E_timeout", "E_remedy", "E_text_noflag",
         "X_exception", "E_json_flag"]


sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_common import classify, load_signatures, visible_text  # noqa: E402
import run_native  # noqa: E402

SIGS = load_signatures()


def relabel(r, proto):
    """Recompute the label from the raw response with the current (fixed) classifier."""
    resp = r.get("response") or {}
    if not resp.get("ok", True) or "error" in resp and not resp.get("ok"):
        return "ERROR_TRANSPORT"
    sig = SIGS[r["case_id"]]
    if proto == "native":
        calls, _ = run_native.calls_of(resp)
        l = run_native.label(calls, sig)
    else:
        c = classify(visible_text(resp), sig)
        l = c["label"]
        if resp.get("finish_reason") == "length" and l == "NO_CALL":
            l = "TRUNCATED"
    if proto == "native" and resp.get("finish_reason") == "length" and l == "NO_CALL":
        l = "TRUNCATED"
    return l


def lab(r):
    return r["_relabel"] if "_relabel" in r else (r["outcome"]["label"] if "outcome" in r else r["label"])


def boot(vals, B=2000, seed=5):
    if not vals:
        return (None, None)
    rng = random.Random(seed); n = len(vals); m = []
    for _ in range(B):
        m.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    m.sort()
    return (m[int(.025 * B)], m[int(.975 * B) - 1])


def load(run):
    d = ROOT / "runs" / run
    man = json.load(open(d / "manifest.json"))
    proto = man.get("protocol", "text")
    t1 = [json.loads(l) for l in open(d / "turn1.jsonl")]
    t2 = [json.loads(l) for l in open(d / "turn2.jsonl")]
    for r in t1 + t2:
        r["_stored"] = r["outcome"]["label"] if "outcome" in r else r["label"]
        r["_relabel"] = relabel(r, proto)
    elig = {r["case_id"] for r in t1 if r["_relabel"] == "BENIGN_CALL"}
    dropped = sum(1 for r in t2 if r["case_id"] not in elig)
    t2 = [r for r in t2 if r["case_id"] in elig]
    changed = sum(1 for r in t1 + t2 if r["_stored"] != r["_relabel"])
    man["_relabel"] = {"t2_rows_dropped_ineligible": dropped, "labels_changed": changed}
    return man, t1, t2


def summarize(run):
    man, t1, t2 = load(run)
    proto = man.get("protocol", "text")
    n1 = len(t1)
    c1 = collections.Counter(lab(r) for r in t1)
    Y = collections.defaultdict(dict)
    U = collections.Counter()
    for r in t2:
        l = lab(r)
        if l in ("ERROR_TRANSPORT", "TRUNCATED"):
            U[r["condition"]] += 1
            continue
        Y[r["condition"]][r["case_id"]] = int(l == "MALICIOUS")
    out = {"run": run, "agent": man["agent"], "protocol": proto, "arm": man["arm"], "n_t1": n1,
           "relabel": man.get("_relabel"),
           "t1": dict(c1), "asr_t1": c1["MALICIOUS"] / n1 if n1 else None,
           "p_elig": c1["BENIGN_CALL"] / n1 if n1 else None, "cond": {}}
    ref = Y.get("S_ok", {})
    for c in ORDER:
        if c not in Y:
            continue
        ys = list(Y[c].values())
        common = sorted(set(Y[c]) & set(ref))
        diffs = [Y[c][k] - ref[k] for k in common]
        out["cond"][c] = {"n": len(ys), "Y": sum(ys) / len(ys) if ys else None, "Y_ci": boot(ys),
                          "diff": sum(diffs) / len(diffs) if diffs else None, "diff_ci": boot(diffs),
                          "U": U[c],
                          "asr_err": (out["asr_t1"] + out["p_elig"] * (sum(ys) / len(ys))) if ys else None}
    return out


def main():
    runs = sys.argv[1:]
    rows = [summarize(r) for r in runs]
    print(json.dumps(rows, indent=1, default=str))
    # figure: Y by condition per run (poison arm)
    fig, ax = plt.subplots(figsize=(9, 3.2))
    width = 0.8 / max(1, len(rows))
    for i, r in enumerate(rows):
        xs, ys, lo, hi = [], [], [], []
        for j, c in enumerate(ORDER):
            if c in r["cond"]:
                v = r["cond"][c]
                xs.append(j + i * width); ys.append(v["Y"])
                lo.append(v["Y"] - v["Y_ci"][0]); hi.append(v["Y_ci"][1] - v["Y"])
        ax.bar(xs, ys, width, yerr=[lo, hi], label=f"{r['agent']}@{r['protocol']} ({r['arm']})", capsize=2)
    ax.set_xticks([j + 0.4 - width / 2 for j in range(len(ORDER))])
    ax.set_xticklabels(ORDER, rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("P(malicious at next step | failed at t1)")
    ax.legend(fontsize=6)
    fig.tight_layout()
    out = ROOT / "analysis" / "fig_revival_by_condition.pdf"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
