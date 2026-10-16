#!/usr/bin/env python3
"""Print readable tables from metrics.json plus sample-identity sanity checks.

Run from the condition_study root, after metrics.py:
    python3 analysis/fix_20261010/metrics/print_tables.py > analysis/fix_20261010/metrics/tables.txt
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
d = json.load(open(HERE / "metrics.json"))


def ids(run):
    return {json.loads(l)["case_id"] for l in open(ROOT / "runs" / run / "turn1.jsonl")}


print("# sanity checks")
dev = [ids(r) for r in ["dev2_q14n_native_poison", "dev2_q8n_native_poison", "dev2_goss_text_poison",
                        "dev2_goss_native_poison"]]
cl = [ids(r) for r in ["dev2_q14n_native_clean", "dev2_q8n_native_clean", "dev2_goss_text_clean",
                       "dev2_goss_native_clean", "dev2_q8n_text_poison"]]
conf = [ids(r) for r in ["conf_q14n_native_poison", "conf_q8n_native_poison", "conf_goss_native_poison"]]
cc = [ids(r) for r in ["conf_q14n_native_clean", "conf_q8n_native_clean"]]
print("dev-200 identical across dev poison runs:", all(x == dev[0] for x in dev), len(dev[0]))
print("dev-100 identical and subset of dev-200:", all(x == cl[0] for x in cl), cl[0] <= dev[0], len(cl[0]))
print("held-out-300 identical:", all(x == conf[0] for x in conf), len(conf[0]),
      "| clean-150 identical and subset:", cc[0] == cc[1], cc[0] <= conf[0], len(cc[0]))
st = json.load(open(ROOT / "analysis" / "confirm_v1_poison_only.json"))["Y_by_condition"]
for a, ys in st.items():
    mine = {r["condition"]: r["Y"] for r in d["6_ordering"]["conf"][a]}
    print("conf Y matches analysis/confirm_v1_poison_only.json for", a, all(abs(mine[c] - v) < 1e-4 for c, v in ys.items()))
print("tolerant normalizer check:", d["tolerant_normalizer_check"])
print("meta:", d["_meta"])

print("\n# (1) ASR metrics, transport rows excluded from n_t1 (frozen classifier)")
print("set  agent@proto            E          n_t1 mal elig  ASR_t1 P(elig) Y(E)      Y(S_ok)    ASR_err ASR_ok "
      "err/t1 [CI]            err/ok [CI]            P*(Y(E)-Y(S_ok)) [CI]")
for r in d["1_asr"]:
    p = r["primary_transport_excluded"]
    c, pt, ci = p["counts"], p["point"], p["ci95_case_bootstrap"]
    print(f"{r['set']:<4} {r['agent'] + '@' + r['protocol']:<24} {r['E']:<10} {c['n_t1']:>4} {c['mal_t1']:>3} {c['elig']:>4}  "
          f"{pt['ASR_t1']:.3f}  {pt['P_elig']:.3f}  {c['kE']:>2}/{c['nE']:<3}={pt['Y_E']:.3f} {c['kS']:>2}/{c['nS']:<3}={pt['Y_S_ok']:.3f} "
          f"{pt['ASR_err']:.3f}  {pt['ASR_ok']:.3f}  {pt['ratio_err_t1']:.2f} {ci['ratio_err_t1']}  "
          f"{pt['ratio_err_ok']:.2f} {ci['ratio_err_ok']}  {pt['inc_abs']:+.4f} {ci['inc_abs']}")
print("\n  paper-style (transport rows in n_t1) and tolerant-tool-name sensitivity")
for r in d["1_asr"]:
    pp, t = r["paper_style_transport_in_denominator"], r["sensitivity_tolerant_tool_names"]
    print(f"  {r['set']:<4} {r['agent'] + '@' + r['protocol']:<24} paper: n={pp['n_t1']} ASR_t1={pp['asr_t1']} "
          f"ASR_err={pp['asr_err']} ratio={pp['ratio']} | tolerant: n={t['counts']['n_t1']} mal={t['counts']['mal_t1']} "
          f"elig={t['counts']['elig']} ASR_t1={t['point']['ASR_t1']} Y(E)={t['counts']['kE']}/{t['counts']['nE']} "
          f"Y(S_ok)={t['counts']['kS']}/{t['counts']['nS']} ASR_err={t['point']['ASR_err']} "
          f"err/t1={t['point']['ratio_err_t1']} err/ok={t['point']['ratio_err_ok']} inc={t['point']['inc_abs']} "
          f"{t['ci95_case_bootstrap']['inc_abs']}")

print("\n# (2) remedy")
for key in ("dev_timeout_plus_remedy_vs_timeout", "conf_unknown_plus_remedy_vs_unknown"):
    print(" ", key)
    for r in d["2_remedy"][key]:
        print(f"  {r['agent']}@{r['protocol']} ({r['run']})")
        print("    rates:", {c: f"{v['k']}/{v['n']}" for c, v in r["rates"].items()})
        for k, v in r.items():
            if "minus" in k:
                print(f"    {k}: {v['diff']:+.4f} {v['ci95']} pairs={v['n_pairs']} McNemar b/c={v['mcnemar']['b']}/{v['mcnemar']['c']}"
                      f" p2={v['mcnemar']['p_two_sided']}")
        for c, v in r["retry"].items():
            print(f"    retry {c:<17} n={v['n']:<3} BENIGN {v['benign_call']:>3} ({v['share_benign']})  exact same-call retry "
                  f"{v['benign_exact_same_call_retry']:>3} ({v['share_exact_retry']})  same-tool {v['benign_same_tool_only']:>3}"
                  f" ({v['share_same_tool']})  labels={v['labels']}")

print("\n# (3) silent revivals (MALICIOUS turn-2 rows, BENIGN stratum, empty visible content)")
for r in d["3_silent"]:
    h = [k for k in r if k.startswith("headline_")][0]
    f = lambda x: f"{x['silent']}/{x['mal']}"
    print(f"  {r['run']:<26} all {f(r['all']):<8} error {f(r['error_conditions']):<8} success {f(r['success_conditions']):<6} "
          f"{h} {f(r[h]):<6} main_analysis={r['in_main_analysis']}")

print("\n# (4) dev clean arms: D = paired poison diff - marginal clean diff")
for r in d["4_dev_clean_D"]:
    x = r["D_E_generic"]
    print(f"  {r['agent']:<26} poison {x['poison_paired']['k_E']}/{x['poison_paired']['n_pairs']} vs "
          f"{x['poison_paired']['k_S_ok']}/{x['poison_paired']['n_pairs']} (paired {x['poison_paired']['diff']:+.4f}) | clean "
          f"{x['clean_marginal']['k_E']}/{x['clean_marginal']['n_E']} vs {x['clean_marginal']['k_S_ok']}/{x['clean_marginal']['n_S_ok']}"
          f" ({x['clean_marginal']['diff']:+.4f}) | D={x['D']:+.4f} {x['D_ci95']} | both-marginal "
          f"{x['alt_D_both_marginal(main.tex formula)']:+.4f} both-paired {x['alt_D_both_paired']:+.4f}")
    print("     clean t1:", r["clean_t1_labels"], "clean Y:", {c: f"{v['k']}/{v['n']}" for c, v in r["clean_Y_by_condition"].items()})

print("\n# (5) MCPTox")
m = d["5_mcptox"]
print(" ", {k: v for k, v in m["mcptox_configurations"].items() if not k.endswith("names")})
print(" ", m["mcptox_source"])
w = m["wrong_data2"]
print(" ", {k: v for k, v in w.items() if k not in ("samples", "case_ids")})
for k, v in w["samples"].items():
    print(f"   {k:<26} n={v['n_cases']:<4} wrong_data2={len(v['wrong_data2'])} {v['wrong_data2']} eligible "
          f"{v['wrong_data2_eligible']}/{v['n_eligible']}")

print("\n# (6) conditions ordered by Y (BENIGN stratum)")
for part in ("conf", "dev"):
    for agent, rows in d["6_ordering"][part].items():
        print(f"  {part} {agent}")
        for r in rows:
            ref = [k for k in r if k.startswith("paired_vs_") and k != "paired_vs_S_ok"][0]
            pv, ps = r[ref], r["paired_vs_S_ok"]
            a = (f"{pv['diff']:+.3f} {pv['ci95']} McNemar {pv['mcnemar']['b']}/{pv['mcnemar']['c']} p2={pv['mcnemar']['p_two_sided']}"
                 if pv else "(reference)")
            b = f"{ps['diff']:+.3f} {ps['ci95']} McNemar {ps['mcnemar']['b']}/{ps['mcnemar']['c']} p2={ps['mcnemar']['p_two_sided']}" if ps else "-"
            print(f"    {r['rank']}. {r['condition']:<17} {r['k']:>3}/{r['n']:<3} Y={r['Y']:.3f} Wilson{r['wilson95']} | {ref}: {a} | vs S_ok: {b}")

print("\n# m11: report.summarize paired diffs vs S_ok (report.boot B=2000 seed=5, as in the paper)")
for run, v in d["m11_report_py_diffs"].items():
    print(" ", run)
    for c, x in v.items():
        print(f"    {c:<14} n={x['n']:<4} Y={x['Y']} diff={x['diff_vs_S_ok']} CI={x['diff_ci95']} contains0={x['ci_contains_0']}")
sys.stdout.flush()
