"""Registered companion to error_census.py (PREREG_addendum_v11, '앞선 실제 서버 실험의 오류 문구'): classify, with the
same registered rules, every error text that a real MCP server returned in our real-server runs (any condition, any
step; injected errors excluded). Writes observed_errors.json next to this file."""
import collections, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from error_census import classify, template  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FS_RUNS = ["e2e_fs_q14n_v1", "e2e2_fs_q14w", "e2e2_fs_llama31", "e2e2_fs_gemma4", "e2e_fs_goss_v1",
           "e2e9_fs_goss120", "e2e9_fs_q30"]
GS_RUNS = ["e2e3_gs_q14w", "e2e3_gs_llama31_r2", "e2e3_gs_goss120", "e2e3_gs_gemma4", "e2e3_gs_q30"]


def norm(text):
    t = text.strip().splitlines()[0] if text.strip() else ""
    t = re.sub(r"'[^']*'|\"[^\"]*\"", "{x}", t)          # quoted paths/values
    t = re.sub(r"(/[\w.\-~]+)+", "{x}", t)                # bare paths
    t = re.sub(r"\b[0-9a-f]{7,40}\b|\b\d+\b", "{x}", t)
    return re.sub(r"\s+", " ", t)[:200]


def main():
    rows = []
    for run in FS_RUNS + GS_RUNS:
        for l in open(ROOT / "runs" / run / "episodes.jsonl"):
            ep = json.loads(l)
            for st in ep.get("trace") or []:
                for res in st.get("results") or []:
                    if res.get("src") != "server_error":        # injected errors and stubs excluded
                        continue
                    rows.append({"server": ep.get("server") or "FileSystem", "run": run,
                                 "condition": ep["condition"], "step": st["step"], "tool": res.get("tool"),
                                 "raw": (res.get("out") or "")[:300], "template": norm(res.get("out") or "")})
    for r in rows:
        r["class"] = classify(r["template"]) if r["template"] else "passthrough"
    by = collections.Counter((r["server"], r["class"]) for r in rows)
    uniq = {}
    for r in rows:
        uniq.setdefault((r["server"], r["template"]), r["class"])
    summary = {"n_error_results": len(rows), "by_server_class": {f"{s}|{c}": n for (s, c), n in sorted(by.items())},
               "n_distinct_templates": len(uniq),
               "distinct_by_class": dict(collections.Counter(uniq.values())),
               "first_step_natural": dict(collections.Counter(r["class"] for r in rows
                                                               if r["condition"] == "natural" and r["step"] == 0)),
               "templates": sorted({f"{s} | {c} | {t}" for (s, t), c in uniq.items()}),
               "examples": {f"{s} | {t}": next(r["raw"] for r in rows if (r["server"], r["template"]) == (s, t))
                            for (s, t) in uniq}}
    json.dump(summary, open(Path(__file__).resolve().parent / "observed_errors.json", "w"), indent=1,
              ensure_ascii=False)
    print(json.dumps({k: summary[k] for k in ("n_error_results", "n_distinct_templates", "distinct_by_class",
                                              "first_step_natural", "by_server_class")}, indent=1))


if __name__ == "__main__" and "--after" not in sys.argv:
    main()


def after_natural_first_error():
    """Descriptive, post hoc: natural-condition episodes in which the agent ignored the poison in its first response
    and its first call got a real server error. Git/SQLite: malicious_first False, effect = E_attr. FileSystem: the
    recount files (alias-aware first label != MALICIOUS, effect = eff.union); the raw v1 real_effect flag also counted
    benign file creation, so it is not used. e2e2_fs_llama31 has no per-episode recount rows; its stored summary
    (recount_llama31.json, natural_first_result.alias) lists no union effect, so its effects are 0 by that file.
    The same cases with the injected error are counted for reference (same effect field). Revival = a
    signature-matching call at step >= 1 (Git/SQLite: calls[].sig_mal; FileSystem: alias-aware first MALICIOUS step
    from the recount files); it counts attempts whether or not they changed anything."""
    rc_files = ["analysis/fix_20261010/e2e/recount_episodes.jsonl", "analysis/prep_20261010/e2e2/recount_episodes.jsonl",
                "analysis/prep_20261010/e2e9fs/recount_episodes.jsonl"]
    rc = {(r["run"], r["case_id"], r["condition"]): r for f in rc_files for r in map(json.loads, open(ROOT / f))}
    llama_nat = json.load(open(ROOT / "analysis/prep_20261010/e2e2/recount_llama31.json"))["runs"]["e2e2_fs_llama31"]
    llama_eff = {c for v in llama_nat["natural_first_result"]["alias"].values() if isinstance(v, dict)
                 for c in v.get("cases_with_union_effect", [])}
    llama_inj = set(llama_nat["paired_by_natural_first_result"]["alias"]["real_error"]["inj_cases"])

    def fs_eff(run, e):
        r = rc.get((run, e["case_id"], e["condition"]))
        if r is not None:
            return bool(r["eff"]["union"])
        assert run == "e2e2_fs_llama31", run
        return e["case_id"] in (llama_inj if e["condition"] == "inj_error" else llama_eff)

    def fs_rev(run, e):
        """Revival = a signature-matching (alias-aware MALICIOUS) call at step >= 1."""
        r = rc.get((run, e["case_id"], e["condition"]))
        if r is not None:
            return r["first_malicious_step_alias"] is not None and r["first_malicious_step_alias"] >= 1
        return any(st.get("label") == "MALICIOUS" for st in e["trace"][1:])

    def ignored(run, e):
        r = rc.get((run, e["case_id"], e["condition"]))
        return (r["step0_label_alias"] != "MALICIOUS") if r is not None else not e.get("malicious_first")
    import math
    out = collections.defaultdict(lambda: collections.Counter())
    for run in FS_RUNS + GS_RUNS:
        eps = [json.loads(l) for l in open(ROOT / "runs" / run / "episodes.jsonl")]
        inj = {e["case_id"]: e for e in eps if e["condition"] == "inj_error"}
        if run in GS_RUNS:
            eff, ign = (lambda e: bool(e["effects"]["E_attr"])), (lambda e: not e.get("malicious_first"))
            rev = lambda e: any(c.get("sig_mal") and int(c["step"]) >= 1 for c in e.get("calls") or [])
        else:
            eff, ign = (lambda e, run=run: fs_eff(run, e)), (lambda e, run=run: ignored(run, e))
            rev = lambda e, run=run: fs_rev(run, e)
        for e in eps:
            if e["condition"] != "natural" or not ign(e) or not e.get("trace"):
                continue
            errs = [r for r in e["trace"][0].get("results") or [] if r.get("src") == "server_error"]
            if not errs:
                continue
            t = norm(errs[0].get("out") or "")
            cls = classify(t) if t else "passthrough"
            server = e.get("server") or "FileSystem"
            c = out[f"{server}|{cls}"]
            c["n"] += 1
            c["effect_after"] += eff(e)
            c["revived_after"] += rev(e)
            j = inj.get(e["case_id"])
            if j is not None and ign(j):
                c["n_inj_same_case"] += 1
                c["effect_inj_same_case"] += eff(j)
                c["revived_inj_same_case"] += rev(j)
                c["revived_inj_only"] += rev(j) and not rev(e)
                c["revived_nat_only"] += rev(e) and not rev(j)
    tot = collections.Counter()
    for c in out.values():
        tot.update(c)
    n = tot["n"]
    tot["upper95_effect_after"] = round(1 - 0.05 ** (1 / n), 4) if n and not tot["effect_after"] else None
    return {"by_server_class": {k: dict(v) for k, v in sorted(out.items())}, "total": dict(tot)}


if __name__ == "__main__" and "--after" in sys.argv:
    res = after_natural_first_error()
    p = Path(__file__).resolve().parent / "observed_errors.json"
    d = json.load(open(p))
    d["after_natural_first_error"] = res
    json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1))
