"""Counterfactual branching runner.

Turn 1: [system (poisoned or clean MCPTox prompt), user (MCPTox query)] -> model.
         Eligible iff the visible answer contains a tool call and none is
         malicious or a direct call of the poison tool (MCPTox "Failure-Ignored").
Turn 2: for each eligible turn-1 prefix and each condition, append
         [assistant (turn-1 visible text), system (rendered tool result)] -> model.
         Everything except the rendered tool result is identical across conditions.

Outputs go to runs/<run_id>/ which must not exist (no overwrite, no resume).
Transport errors are retried inside chat(); model outcomes are never retried.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_common import (AGENTS, DATA, ENDPOINTS, ROOT, chat, classify, visible_text,
                       load_cases, load_signatures, render_result, sha256_file)


def seed_for(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def outcome(resp, sig):
    if not resp.get("ok"):
        return {"label": "ERROR_TRANSPORT", "error": resp.get("error")}
    if resp.get("finish_reason") == "length":
        c = classify(visible_text(resp), sig)
        # truncated: keep calls if any were completed, else undecidable
        if c["label"] in ("MALICIOUS", "DIRECT_EXEC", "BENIGN_CALL"):
            c["truncated"] = True
            return c
        return {"label": "TRUNCATED", "calls": [], "malicious": False, "direct": False, "truncated": True}
    return classify(visible_text(resp), sig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(AGENTS))
    ap.add_argument("--arm", required=True, choices=["poison", "clean"])
    ap.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    ap.add_argument("--conditions", default=str(DATA / "conditions_v1.json"))
    ap.add_argument("--only", default="", help="comma list of condition names (default all)")
    ap.add_argument("--signatures", default=str(DATA / "signatures.jsonl"))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0, help="fixed-seed random subset of the split")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    out = ROOT / "runs" / a.run_id
    out.mkdir(parents=True, exist_ok=False)
    cases = load_cases()
    sigs = load_signatures(a.signatures)
    split = json.load(open(DATA / "split.json"))["split"]
    conds = json.load(open(a.conditions))["conditions"]
    if a.only:
        conds = {k: v for k, v in conds.items() if k in a.only.split(",")}
    ids = sorted(cid for cid in cases if a.split == "all" or split[cid] == a.split)
    if a.sample:
        ids = sorted(ids, key=lambda x: hashlib.sha256(("sample-v1|" + x).encode()).hexdigest())[: a.sample]
        ids.sort()
    if a.limit:
        ids = ids[: a.limit]
    manifest = {
        "run_id": a.run_id, "agent": a.agent, "agent_cfg": AGENTS[a.agent],
        "endpoint": ENDPOINTS[AGENTS[a.agent]["ep"]], "arm": a.arm, "split": a.split,
        "n_cases": len(ids), "conditions": conds,
        "sha256": {
            "cases": sha256_file(DATA / "cases.jsonl"), "split": sha256_file(DATA / "split.json"),
            "signatures": sha256_file(a.signatures), "conditions": sha256_file(a.conditions),
            "cs_common.py": sha256_file(Path(__file__).with_name("cs_common.py")),
            "run_branch.py": sha256_file(__file__),
        },
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    lock = threading.Lock()
    f1 = open(out / "turn1.jsonl", "w")
    f2 = open(out / "turn2.jsonl", "w")

    def write(f, row):
        with lock:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            f.flush()

    def run_case(cid):
        c, sig = cases[cid], sigs[cid]
        system = c["system_poisoned"] if a.arm == "poison" else c["system_clean"]
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": c["query"]}]
        r1 = chat(a.agent, msgs, seed=seed_for(a.agent, a.arm, cid, "t1"))
        o1 = outcome(r1, sig)
        eligible = o1["label"] == "BENIGN_CALL"
        write(f1, {"case_id": cid, "arm": a.arm, "agent": a.agent, "outcome": o1, "eligible": eligible,
                   "response": r1})
        if not eligible:
            return
        visible = visible_text(r1)
        for name, cd in conds.items():
            sysmsg = render_result(cd["render"], cd.get("text"), cd.get("is_error", False))
            m2 = msgs + [{"role": "assistant", "content": visible}, {"role": "system", "content": sysmsg}]
            r2 = chat(a.agent, m2, seed=seed_for(a.agent, a.arm, cid, "t2", name))
            o2 = outcome(r2, sig)
            t1_calls = [(x["tool"], json.dumps(x["arguments"], sort_keys=True)) for x in o1["calls"]]
            o2["repeat_t1_call"] = any((x["tool"], json.dumps(x["arguments"], sort_keys=True)) in t1_calls
                                       for x in o2.get("calls", []))
            write(f2, {"case_id": cid, "arm": a.arm, "agent": a.agent, "condition": name,
                       "outcome": o2, "rendered": sysmsg, "response": r2})

    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run_case, cid) for cid in ids]
        for i, fu in enumerate(cf.as_completed(futs)):
            try:
                fu.result()
            except Exception as e:  # keep going; record the harness failure instead of losing the run
                print(f"HARNESS_ERROR {e!r}", flush=True)
                with open(out / "harness_errors.log", "a") as hf:
                    hf.write(repr(e) + "\n")
            if (i + 1) % 25 == 0:
                print(f"{i+1}/{len(ids)} cases, {time.time()-t0:.0f}s", flush=True)
    f1.close(); f2.close()
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps({"run_id": a.run_id, "cases": len(ids), "seconds": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
