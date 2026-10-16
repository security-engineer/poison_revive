"""(7) Common-pool comparison (review m7).

Held-out: cases whose turn-1 is BENIGN_CALL (frozen) for all three agents; Y per condition and E_* - S_ok
(case bootstrap, report.boot B=2000 seed 5) per agent on that common set. Pairwise pools are reported too,
plus the dev gpt-oss text-vs-native pool and the dev native pool shared by all three agents.

Run: cd condition_study && python3 analysis/fix_20261010/measure/s7_common_pool.py
Writes: s7_common_pool.json
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_common as M  # noqa: E402

CONF = {"qwen3-14b": "conf_q14n_native_poison", "qwen3-8b": "conf_q8n_native_poison", "gpt-oss-20b": "conf_goss_native_poison"}
DEV_NATIVE = {"qwen3-14b": "dev2_q14n_native_poison", "qwen3-8b": "dev2_q8n_native_poison", "gpt-oss-20b": "dev2_goss_native_poison"}
DEV_GOSS = {"gpt-oss-20b@text": "dev2_goss_text_poison", "gpt-oss-20b@native": "dev2_goss_native_poison"}


def load(runs, which="frozen"):
    out = {}
    for a, run in runs.items():
        man, proto, t1, t2 = M.load_run(run, which)
        Y, U, lab1 = M.Y_table(t1, t2)
        out[a] = {"Y": Y, "elig": {k for k, v in lab1.items() if v == "BENIGN_CALL"}, "conds": [c for c in man["conditions"] if c in Y]}
    return out


def on_pool(D, pool, key):
    res = {}
    for a, d in D.items():
        r = {c: M.ymean(d["Y"], c, pool) for c in d["conds"]}
        for c in d["conds"]:
            if c != "S_ok":
                r[c]["diff_vs_S_ok"] = M.paired_diff(d["Y"], c, cases=pool)
        res[a] = r
    return {"n_pool": len(pool), "key_condition": key, "by_agent": res}


def main():
    out = {}
    for which in ("frozen", "alt"):
        C = load(CONF, which)
        allp = set.intersection(*[d["elig"] for d in C.values()])
        out[f"conf_{which}"] = {"eligible": {a: len(d["elig"]) for a, d in C.items()},
                                "all_three": on_pool(C, allp, "E_unknown"),
                                "pairwise": {f"{a}&{b}": on_pool({a: C[a], b: C[b]}, C[a]["elig"] & C[b]["elig"], "E_unknown")
                                             for a, b in itertools.combinations(C, 2)},
                                "own_pool_minus_common": {a: on_pool({a: d}, d["elig"] - allp, "E_unknown") for a, d in C.items()}}
    # where do Qwen revivals sit? gpt-oss turn-1 label on the cases where each Qwen agent revived under E_unknown
    import collections
    g1 = {}
    man, proto, t1, _ = M.load_run(CONF["gpt-oss-20b"], "frozen")
    g1 = {r["case_id"]: r["_lab"] for r in t1}
    C = load(CONF)
    out["qwen_revival_cases_by_goss_t1_label"] = {
        a: dict(collections.Counter(g1.get(k, "NOT_SAMPLED") for k, y in C[a]["Y"]["E_unknown"].items() if y))
        for a in ("qwen3-14b", "qwen3-8b")}
    allp = set.intersection(*[d["elig"] for d in C.values()])
    out["template_mix"] = {name: dict(sorted(collections.Counter(M.CASES[k]["paradigm"] for k in pool).items()))
                           for name, pool in (("common3", allp), ("q14_only_outside_common", C["qwen3-14b"]["elig"] - allp))}
    Dn = load(DEV_NATIVE)
    out["dev_native_all_three"] = on_pool(Dn, set.intersection(*[d["elig"] for d in Dn.values()]), "E_generic")
    Dg = load(DEV_GOSS)
    pool = Dg["gpt-oss-20b@text"]["elig"] & Dg["gpt-oss-20b@native"]["elig"]
    out["dev_goss_text_vs_native"] = {"eligible": {a: len(d["elig"]) for a, d in Dg.items()}, "common": on_pool(Dg, pool, "E_generic")}
    p = M.dump("s7_common_pool.json", out)
    for which in ("frozen", "alt"):
        o = out[f"conf_{which}"]
        print(which, "eligible", o["eligible"], "common3", o["all_three"]["n_pool"])
        for a, r in o["all_three"]["by_agent"].items():
            print("   ", a, "S_ok", r["S_ok"]["k"], "/", r["S_ok"]["n"], "E_unknown", r["E_unknown"]["k"], "/", r["E_unknown"]["n"],
                  "diff", r["E_unknown"]["diff_vs_S_ok"])
        for k, v in o["pairwise"].items():
            print("   pair", k, v["n_pool"], {a: (r["S_ok"]["k"], r["E_unknown"]["k"], r["E_unknown"]["n"]) for a, r in v["by_agent"].items()})
        for a, v in o["own_pool_minus_common"].items():
            r = v["by_agent"][a]
            print("   outside-common", a, v["n_pool"], "S_ok", r["S_ok"]["k"], "E_unknown", r["E_unknown"]["k"], "/", r["E_unknown"]["n"])
    print("dev native common3", out["dev_native_all_three"]["n_pool"],
          {a: (r["S_ok"]["k"], r["E_generic"]["k"], r["E_generic"]["n"], r["E_generic"]["diff_vs_S_ok"]) for a, r in out["dev_native_all_three"]["by_agent"].items()})
    g = out["dev_goss_text_vs_native"]
    print("dev goss text vs native", g["eligible"], g["common"]["n_pool"],
          {a: (r["S_ok"]["k"], r["E_generic"]["k"], r["E_generic"]["n"], r["E_generic"]["diff_vs_S_ok"]) for a, r in g["common"]["by_agent"].items()})
    print("qwen revival cases by gpt-oss t1 label", out["qwen_revival_cases_by_goss_t1_label"])
    print("template mix", out["template_mix"])
    print("wrote", p)


if __name__ == "__main__":
    main()
