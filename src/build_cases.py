"""Build the fixed case table from MCPTox response_all.json.

Every case keeps MCPTox text verbatim: poisoned system prompt, clean system
prompt, user query, poisoned tool description. Nothing here is model output
except the MCPTox reference responses/labels, kept only for measurement
validation.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "latest" / "data" / "mcptox" / "response_all.json"
EXPECTED_SHA = "79a90049be931c59e71446d6180b1d7f0d196d123d08a59bc155d142b5041c03"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    got = sha256_file(SRC)
    if got != EXPECTED_SHA:
        sys.exit(f"source sha mismatch {got}")
    r = json.load(open(SRC))
    out = []
    for server, s in r["servers"].items():
        clean = s["clean_system_promot"]
        for idx, mi in enumerate(s["malicious_instance"]):
            assert len(mi["datas"]) == 1
            d = mi["datas"][0]
            online = d.get("online_result") or {}
            resp = (online.get("backend_model_responses") or [{}])[0]
            lab = (online.get("labeled_model_results") or [{}])[0]
            ref = {m: {"response": d["response"].get(m), "label": d["label"].get(m)} for m in d["label"]}
            for m in lab:
                ref["online:" + m] = {"response": resp.get(m), "label": lab.get(m)}
            out.append({
                "case_id": f"{server}::{idx}",
                "server": server,
                "server_tools": s["tool_names"],
                "paradigm": mi["metadata"]["paradigm"],
                "risk": mi["metadata"]["security risk"],
                "risk_desc_zh": mi["security_risk_description"],
                "wrong_data": mi.get("wrong_data"),
                "poisoned_tool": mi["poisoned_tool"],
                "query": d["query"],
                "system_poisoned": d["system"],
                "system_clean": clean,
                "mcptox_id": d["id"],
                "mcptox_ref": ref,
            })
    p = ROOT / "data" / "cases.jsonl"
    with open(p, "w") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    # sanity: how the poison is embedded
    emb = sum(1 for c in out if c["poisoned_tool"].strip()[:60] in c["system_poisoned"])
    same_prefix = sum(1 for c in out if c["system_poisoned"].startswith(c["system_clean"][:200]))
    print(json.dumps({"cases": len(out), "poison_embedded_verbatim": emb,
                      "system_shares_clean_prefix": same_prefix,
                      "sha256_cases": sha256_file(p)}))


if __name__ == "__main__":
    main()
