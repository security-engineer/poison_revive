"""POST HOC sensitivity for the v11 census (not registered). Rule changes come from the 40-template check
(check40.json) and from error texts seen in our real-server runs; the registered result stays the primary one.

Changes to the registered rules:
  1. 'expected' must start a word, so 'Unexpected error' is no longer call-blaming.
  2. 'Tool {x} not found' / 'Tool not found' / 'Unknown prompt|resource|reference' / 'No arguments' count as
     call-blaming (a wrong call), checked before the explained lexicon.
  3. SQL wording that blames the query ('syntax error', 'incomplete input', 'datatype mismatch', 'only select',
     'only create table') counts as call-blaming.
  4. 'environment variable' counts as explained (server configuration, not the call).
A second post hoc check drops the 13 templates that come from prompt/resource handlers, start-up configuration checks
or a session assertion rather than from a tool call (NON_TOOL below), with the registered rules.
"""
import collections, json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import error_census as ec  # noqa: E402

CALL_FIRST = [r"\btool\b.{0,40}\bnot found", r"unknown (prompt|resource|reference)", r"no arguments"]
CALL_EXTRA = ["syntax error", "incomplete input", "datatype mismatch", "only select", "only create table"]
EXPL_EXTRA = ["environment variable"]
NON_TOOL = re.compile(r"unknown (prompt|resource|reference)|uri scheme|argument: topic|environment variables|smtp_port|"
                      r"imap_port|request_context", re.I)


def classify_ph(t):
    words = re.sub(r"\{x\}", " ", t).lower()
    letters = re.sub(r"\b(error|err|failed|failure)\b|[^a-z]", "", words)
    if len(letters) < 3:
        return "passthrough"
    if any(re.search(p, words) for p in CALL_FIRST):
        return "call-blaming"
    if any(k in words for k in ec.EXPLAINED + EXPL_EXTRA):
        return "explained"
    call = [k for k in ec.CALL if k != "expected"] + CALL_EXTRA
    if any(k in words for k in call) or re.search(r"\bexpected", words):
        return "call-blaming"
    return "unexplained"


def shares(rows, key):
    classes = ["explained", "call-blaming", "unexplained", "passthrough"]
    pooled = collections.Counter(r[key] for r in rows)
    per = collections.defaultdict(collections.Counter)
    for r in rows:
        per[r["server"]][r[key]] += 1
    mean = {k: round(sum(c[k] / sum(c.values()) for c in per.values()) / len(per), 4) for k in classes}
    return {"pooled": {k: round(pooled[k] / len(rows), 4) for k in classes}, "server_mean": mean,
            "pooled_counts": {k: pooled[k] for k in classes}}


def main():
    rows = [json.loads(l) for l in open(HERE / "templates.jsonl")]
    for r in rows:
        r["class_ph"] = classify_ph(r["template"])
    changed = [(r["server"], r["template"], r["class"], r["class_ph"]) for r in rows if r["class"] != r["class_ph"]]
    obs = json.load(open(HERE / "observed_errors.json"))
    obs_rows = [{"server": s.split(" | ")[0], "template": s.split(" | ", 2)[2]} for s in obs["templates"]]
    for r in obs_rows:
        r["class"] = ec.classify(r["template"]) if r["template"] else "passthrough"
        r["class_ph"] = classify_ph(r["template"]) if r["template"] else "passthrough"
    out = {"note": "POST HOC sensitivity; registered rules remain primary",
           "census_registered": shares(rows, "class"), "census_posthoc": shares(rows, "class_ph"),
           "census_changed": changed,
           "observed_distinct_registered": dict(collections.Counter(r["class"] for r in obs_rows)),
           "observed_distinct_posthoc": dict(collections.Counter(r["class_ph"] for r in obs_rows)),
           "observed_changed": [(r["server"], r["template"], r["class"], r["class_ph"]) for r in obs_rows
                                if r["class"] != r["class_ph"]]}
    tool_rows = [r for r in rows if not NON_TOOL.search(r["template"])]
    out["census_registered_tool_calls_only"] = dict(shares(tool_rows, "class"), n_templates=len(tool_rows),
                                                    n_dropped=len(rows) - len(tool_rows))
    chk = json.load(open(HERE / "check40.json"))                     # idx = row index in templates.jsonl
    ph = [rows[i]["class_ph"] for i in chk["idx"]]
    out["check40_agree_registered"] = f'{chk["agree"]}/{chk["n"]}'
    out["check40_agree_posthoc"] = f'{sum(a == b for a, b in zip(ph, chk["researcher_ai"]))}/{chk["n"]}'
    json.dump(out, open(HERE / "sensitivity_posthoc.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: out[k] for k in out if k not in ("census_changed", "observed_changed")}, indent=1,
                     ensure_ascii=False))
    for c in changed + out["observed_changed"]:
        print(c)


if __name__ == "__main__":
    main()
