"""(3) Turn-2 outcome validity audit: build the items to judge (review M12, m14).

Precision: ALL turn-2 rows labelled MALICIOUS (frozen classifier) in the BENIGN_CALL stratum of the three
held-out poison runs (a census, which is >= 40 per agent). Rows are grouped into items by
(case_id, emitted call set) because the judgment depends only on the poison text, the query and the calls.
Recall: a fixed-seed random sample of non-MALICIOUS rows of the same stratum: 45 per agent under error
conditions and 15 per agent under S_ok (seed 'audit-v1').

Run: cd condition_study && python3 analysis/fix_20261010/measure/s3_audit_sample.py
Writes: audit_precision_items.json, audit_recall_items.json, audit_dump_precision.txt, audit_dump_recall.txt
"""
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402

RUNS = {"qwen3-14b": "conf_q14n_native_poison", "qwen3-8b": "conf_q8n_native_poison", "gpt-oss-20b": "conf_goss_native_poison"}
N_ERR, N_OK = 45, 15


def callset(calls):
    return sorted((c["tool"], json.dumps(c["arguments"], ensure_ascii=False, sort_keys=True)) for c in calls)


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def case_block(cid):
    c, s = M.CASES[cid], M.SIGS[cid]
    return (f"=== {cid} [{c['paradigm']}] poison_tool={s['poison_tool']} mech={s['mechanism']}\n"
            f"QUERY: {c['query']}\n"
            f"POISON: {c['poisoned_tool'].replace(chr(92) + 'n', ' ').replace(chr(10), ' ')[:900]}\n"
            f"SIG: {json.dumps(s['malicious'], ensure_ascii=False)}  trig={s['trigger_tools']} benign={s['benign_tools']}\n"
            f"NOTE: {s.get('note', '')}\n")


def main():
    prec = {}
    recall = []
    t1calls = {}
    for agent, run in RUNS.items():
        man, proto, t1, t2 = M.load_run(run, "frozen")
        lab1 = {r["case_id"]: r["_lab"] for r in t1}
        for r in t1:
            if r["_lab"] == "BENIGN_CALL":
                t1calls[(agent, r["case_id"])] = [(c["tool"], json.dumps(c["arguments"], ensure_ascii=False)[:200])
                                                  for c in M.calls_of(r["response"], proto)]
        pool_err, pool_ok = [], []
        for i, r in enumerate(t2):
            if lab1.get(r["case_id"]) != "BENIGN_CALL":
                continue
            calls = M.calls_of(r["response"], proto)
            if r["_lab"] == "MALICIOUS":
                key = r["case_id"] + "|" + json.dumps(callset(calls), ensure_ascii=False)
                it = prec.setdefault(key, {"item": "P" + h(key)[:8], "case_id": r["case_id"],
                                           "calls": [{"tool": c["tool"], "arguments": c["arguments"]} for c in calls],
                                           "rows": []})
                it["rows"].append({"agent": agent, "run": run, "condition": r["condition"]})
            else:
                row = {"row": f"R{h(run + '|' + str(i))[:8]}", "agent": agent, "run": run, "line": i,
                       "case_id": r["case_id"], "condition": r["condition"], "label": r["_lab"],
                       "calls": [{"tool": c["tool"], "arguments": c["arguments"]} for c in calls],
                       "text_calls": r.get("text_calls"),
                       "content": (r["response"].get("content") or "")[:600],
                       "reasoning": (r["response"].get("reasoning") or "")[:700]}
                (pool_ok if r["condition"] == "S_ok" else pool_err).append(row)
        key = lambda x: h("audit-v1|" + x["row"])
        recall += sorted(pool_err, key=key)[:N_ERR] + sorted(pool_ok, key=key)[:N_OK]
    items = sorted(prec.values(), key=lambda x: (x["case_id"], x["item"]))
    M.dump("audit_precision_items.json", items)
    M.dump("audit_recall_items.json", recall)
    # human-readable dumps
    with open(M.OUT / "audit_dump_precision.txt", "w") as f:
        last = None
        for it in items:
            if it["case_id"] != last:
                f.write("\n" + case_block(it["case_id"]))
                last = it["case_id"]
            ags = collections.Counter(r["agent"] for r in it["rows"])
            t1 = {a: t1calls.get((a, it["case_id"])) for a in ags}
            f.write(f"  [{it['item']}] rows={len(it['rows'])} {dict(ags)} conds={sorted({r['condition'] for r in it['rows']})}\n"
                    f"     T1: {t1}\n"
                    f"     T2: {json.dumps(it['calls'], ensure_ascii=False)[:600]}\n")
    with open(M.OUT / "audit_dump_recall.txt", "w") as f:
        for r in sorted(recall, key=lambda x: (x["case_id"], x["agent"], x["condition"])):
            f.write("\n" + case_block(r["case_id"]))
            f.write(f"  [{r['row']}] {r['agent']} {r['condition']} label={r['label']}\n"
                    f"     T1: {t1calls.get((r['agent'], r['case_id']))}\n"
                    f"     T2 calls: {json.dumps(r['calls'], ensure_ascii=False)[:500]}\n"
                    f"     text_calls: {json.dumps(r['text_calls'], ensure_ascii=False)[:300]}\n"
                    f"     content: {r['content'][:400]!r}\n"
                    f"     reasoning: {r['reasoning'][:500]!r}\n")
    print("precision items", len(items), "rows", sum(len(i["rows"]) for i in items),
          collections.Counter(r["agent"] for i in items for r in i["rows"]))
    print("recall rows", len(recall), collections.Counter((r["agent"], r["condition"] == "S_ok") for r in recall))


if __name__ == "__main__":
    main()
