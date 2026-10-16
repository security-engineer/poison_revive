"""v13 (PREREG_addendum_v13_nexttask_KO.md): does an ignored poison fire on the user's NEXT benign task?

For each case X where the agent ignored the poison (turn 1 BENIGN_CALL), received "Success" for that call
and then answered without a new call (stored S_ok branch of a v5 run, label NO_CALL), we append a new user
request Y and sample one response. Y is another MCPTox request of the same server (different query text),
preferring requests whose usual tool equals X's first call. The poisoned tool list of X is kept unchanged.

Conditions (paired within X):
  NEXT_DONE   system, user X, assistant call (stored), tool "Success", assistant answer (stored), user Y
  NEXT_FRESH  system, user Y            (a new conversation with the same tools)
Both responses are labelled with X's attack signature (same label() as run_native.py).
"""
import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cs_common import AGENTS, DATA, ROOT, call_is_malicious, load_cases, load_signatures, sha256_file  # noqa: E402
from run_native import AGENT_SYSTEM, calls_of, chat_native, label, parse_tools, seed_for  # noqa: E402

TOOL_RE = re.compile(r"""['"]tool['"]\s*:\s*['"]([^'"]+)""")


def ref_tool(case):
    """The tool MCPTox's own models usually called for this query (majority over Failure-Ignored responses,
    else over all parsed responses). Used only to prefer a next request that needs the same tool."""
    ign, allc = collections.Counter(), collections.Counter()
    for v in (case.get("mcptox_ref") or {}).values():
        m = TOOL_RE.search(v.get("response") or "")
        if not m:
            continue
        allc[m.group(1)] += 1
        if v.get("label") == "Failure-Ignored":
            ign[m.group(1)] += 1
    c = ign or allc
    return c.most_common(1)[0][0] if c else None


def choose_next(x, cases, ref, t1_tool):
    """Deterministic choice of the next request for case x. Returns (query, representative case id, matched)."""
    srv = cases[x]["server"]
    reps = {}
    for cid in sorted(cases):
        c = cases[cid]
        if c["server"] != srv or c["query"] == cases[x]["query"]:
            continue
        reps.setdefault(c["query"], cid)  # one representative case per distinct query (smallest id)
    if not reps:
        return None
    matched = {q: cid for q, cid in reps.items() if ref.get(cid) == t1_tool}
    pool = matched or reps
    key = lambda q: hashlib.sha256(f"next-v1|{x}|{q}".encode()).hexdigest()
    q = min(pool, key=key)
    return q, pool[q], bool(matched)


def build(source_run):
    cases = load_cases()
    ref = {cid: ref_tool(c) for cid, c in cases.items()}
    d = ROOT / "runs" / source_run
    t1 = {json.loads(l)["case_id"]: json.loads(l) for l in open(d / "turn1.jsonl")}
    s_ok = {}
    for l in open(d / "turn2.jsonl"):
        r = json.loads(l)
        if r["condition"] == "S_ok":
            s_ok[r["case_id"]] = r
    items, skipped = [], collections.Counter()
    for x in sorted(t1):
        r1 = t1[x]
        if r1["label"] != "BENIGN_CALL" or not r1["response"].get("tool_calls"):
            skipped["turn1 not benign"] += 1
            continue
        r2 = s_ok.get(x)
        if r2 is None or r2["label"] != "NO_CALL" or not r2["response"].get("ok") \
                or r2["response"].get("finish_reason") == "length":
            skipped["success branch did not end with an answer"] += 1
            continue
        t1_tool = (r1["calls"] or [{"tool": ""}])[0]["tool"]
        nxt = choose_next(x, cases, ref, t1_tool)
        if nxt is None:
            skipped["no other request on this server"] += 1
            continue
        items.append({"x": x, "y_query": nxt[0], "y_case": nxt[1], "matched_tool": nxt[2], "t1_tool": t1_tool,
                      "r1": r1["response"], "r2": r2["response"]})
    return cases, items, skipped


def histories(case, it):
    sysm = {"role": "system", "content": AGENT_SYSTEM}
    asst = {"role": "assistant", "content": it["r1"].get("content") or "", "tool_calls": [
        {"id": t.get("id") or f"call_{i}", "type": "function",
         "function": {"name": t["function"]["name"], "arguments": t["function"].get("arguments") or "{}"}}
        for i, t in enumerate(it["r1"]["tool_calls"])]}
    tool_msgs = [{"role": "tool", "tool_call_id": t["id"], "content": "Success"} for t in asst["tool_calls"]]
    answer = {"role": "assistant", "content": it["r2"].get("content") or ""}
    done = [sysm, {"role": "user", "content": case["query"]}, asst] + tool_msgs + [answer,
                                                                                  {"role": "user", "content": it["y_query"]}]
    fresh = [sysm, {"role": "user", "content": it["y_query"]}]
    return {"NEXT_DONE": done, "NEXT_FRESH": fresh}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(AGENTS))
    ap.add_argument("--source-run", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="build histories only; no model calls, no run folder")
    a = ap.parse_args()
    src_man = json.load(open(ROOT / "runs" / a.source_run / "manifest.json"))
    if src_man["agent"] != a.agent:
        sys.exit(f"agent mismatch: source run is {src_man['agent']}")
    cases, items, skipped = build(a.source_run)
    sigs = load_signatures()
    summary = {"eligible": len(items), "matched_tool": sum(i["matched_tool"] for i in items), "skipped": dict(skipped)}
    if a.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
        ex = items[0]
        h = histories(cases[ex["x"]], ex)
        print(json.dumps({"example_x": ex["x"], "y_case": ex["y_case"], "matched": ex["matched_tool"],
                          "NEXT_DONE_roles": [m["role"] for m in h["NEXT_DONE"]],
                          "last_user": h["NEXT_DONE"][-1]["content"][:200]}, ensure_ascii=False))
        return
    out = ROOT / "runs" / a.run_id
    out.mkdir(parents=True, exist_ok=False)
    (out / "manifest.json").write_text(json.dumps({
        "run_id": a.run_id, "protocol": "native", "agent": a.agent, "agent_cfg": AGENTS[a.agent],
        "source_run": a.source_run, "agent_system": AGENT_SYSTEM, "conditions": ["NEXT_DONE", "NEXT_FRESH"],
        "summary": summary,
        "sha256": {"cases": sha256_file(DATA / "cases.jsonl"), "signatures": sha256_file(DATA / "signatures.jsonl"),
                   "run_nexttask.py": sha256_file(__file__), "run_native.py": sha256_file(Path(__file__).parent / "run_native.py"),
                   "source_turn1": sha256_file(ROOT / "runs" / a.source_run / "turn1.jsonl"),
                   "source_turn2": sha256_file(ROOT / "runs" / a.source_run / "turn2.jsonl")},
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1))
    lock = threading.Lock()
    f = open(out / "next.jsonl", "w")

    def run_item(it):
        x = it["x"]
        case, sig = cases[x], sigs[x]
        tools = parse_tools(case["system_clean"]) + parse_tools(case["poisoned_tool"].replace("\\n", "\n") + "\n\n")
        for cond, msgs in histories(case, it).items():
            r = chat_native(a.agent, msgs, tools, seed_for(a.agent, "next-v1", x, cond))
            calls, text_calls = calls_of(r) if r.get("ok") else ([], [])
            lab = label(calls, sig) if r.get("ok") else "ERROR_TRANSPORT"
            if r.get("ok") and r.get("finish_reason") == "length" and lab == "NO_CALL":
                lab = "TRUNCATED"
            row = {"case_id": x, "agent": a.agent, "condition": cond, "y_case": it["y_case"], "y_query": it["y_query"],
                   "matched_tool": it["matched_tool"], "t1_tool": it["t1_tool"], "label": lab, "calls": calls,
                   "text_calls": text_calls, "text_call_malicious": any(call_is_malicious(c, sig) for c in text_calls),
                   "response": r}
            with lock:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n"); f.flush()

    t0 = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, fu in enumerate(cf.as_completed([ex.submit(run_item, it) for it in items])):
            try:
                fu.result()
            except Exception as e:
                print(f"HARNESS_ERROR {e!r}", flush=True)
                with open(out / "harness_errors.log", "a") as hf:
                    hf.write(repr(e) + "\n")
            if (i + 1) % 25 == 0:
                print(f"{i+1}/{len(items)} {time.time()-t0:.0f}s", flush=True)
    f.close()
    print(json.dumps({"run_id": a.run_id, "items": len(items), "seconds": round(time.time() - t0)}))


if __name__ == "__main__":
    main()
