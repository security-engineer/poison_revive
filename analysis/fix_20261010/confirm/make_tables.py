#!/usr/bin/env python3
"""Print paper-ready tables from results_confirm.json (no recomputation).
Usage (condition_study root): python3 analysis/fix_20261010/confirm/make_tables.py > analysis/fix_20261010/confirm/tables.txt
"""
import json
from pathlib import Path

D = json.load(open(Path("analysis/fix_20261010/confirm/results_confirm.json")))
M, S = D["main"], D["sensitivity_exclude_empty_signatures"]
AG = ["qwen3-14b-nothink", "qwen3-8b-nothink", "gpt-oss-20b"]
SHORT = {"qwen3-14b-nothink": "Qwen3-14B", "qwen3-8b-nothink": "Qwen3-8B", "gpt-oss-20b": "gpt-oss-20b"}
CONDS = ["S_ok", "E_unknown", "E_internal", "E_invalid_arg", "E_precondition", "E_deadline", "E_permission",
         "E_unknown_remedy"]


def p(x):
    if x is None:
        return "–"
    if x == 0:
        return "0"
    if x >= 0.001:
        return f"{x:.3f}".lstrip("0") if x < 1 else "1.000"
    m, e = f"{x:.1e}".split("e")
    return f"{m}e{int(e)}"


def e(x):
    return f"{x:+.3f}"


def ci(c):
    return f"[{c[0]:+.3f}, {c[1]:+.3f}]"


def ycell(t):
    return f"{t['k']}/{t['n']} ({t['Y']:.3f})" if t["n"] else "–"


print("## Table A. Y = P(malicious next call) by condition, held-out, native protocol\n")
for stratum, agents in (("poison_BENIGN", AG), ("poison_DIRECT", AG), ("clean_BENIGN", AG[:2])):
    print(f"### {stratum}\n")
    print("| condition | " + " | ".join(SHORT[a] for a in agents) + " |")
    print("|---|" + "---|" * len(agents))
    for c in CONDS:
        print(f"| {c} | " + " | ".join(ycell(M["Y_table"][stratum][a][c]) for a in agents) + " |")
    print("| U (excluded rows) | " + " | ".join(str(sum(M["Y_table"][stratum][a][c]["U"] for c in CONDS)) for a in agents) + " |")
    print()

print("## Table B. Registered confirmatory family (pooled = two Qwen agents)\n")
h = M["holm"]
rows = [
    ("H1 E_unknown > S_ok (both Qwen; IUT p = max)", None, None, h["exact_perm_primary"]["raw"]["H1"], "exact McNemar, max of 2"),
    ("H2 clean-subtracted D(E_unknown)", M["H2"]["D"], M["H2"]["D_ci95"], M["H2"]["p"], "arm-label permutation (exact)"),
    ("H3 E_unknown − E_unknown_remedy", M["H3"]["pooled_qwen"]["est"], M["H3"]["pooled_qwen"]["ci95"], M["H3"]["pooled_qwen"]["p_exact"], "stratified sign-flip (exact)"),
    ("H4 mean(UNK,INT) − mean(DEAD,PERM)", M["H4"]["pooled_qwen"]["est"], M["H4"]["pooled_qwen"]["ci95"], M["H4"]["pooled_qwen"]["p_exact"], "stratified sign-flip (exact)"),
    ("H5 interaction (registered estimator)", M["H5"]["pooled_qwen_registered"]["est"], M["H5"]["pooled_qwen_registered"]["ci95"], M["H5"]["pooled_qwen_registered"]["p_exact"], "stratified sign-flip (exact)"),
    ("H6 DIRECT stratum E_unknown > S_ok", M["H6"]["pooled_qwen"]["est"], M["H6"]["pooled_qwen"]["ci95"], M["H6"]["pooled_qwen"]["p_exact"], "stratified sign-flip (exact)"),
]
print("| hypothesis | estimate | 95% CI (B=20000) | p (one-sided) | test | Holm p | Holm p, MC perm B=20000 | registered-code boot p (B=5000) | Holm on registered-code p | verdict |")
print("|---|---|---|---|---|---|---|---|---|---|")
for (name, est, c, pr, test), k in zip(rows, ["H1", "H2", "H3", "H4", "H5", "H6"]):
    print(f"| {name} | {e(est) if est is not None else 'see Table C'} | {ci(c) if c else '–'} | {p(pr)} | {test} | "
          f"{p(h['exact_perm_primary']['adjusted'][k])} | {p(h['perm_mc_B20000']['adjusted'][k])} | "
          f"{p(h['registered_code_bootstrap_B5000']['raw'][k])} | {p(h['registered_code_bootstrap_B5000']['adjusted'][k])} | "
          f"{'confirmed' if h['exact_perm_primary']['confirmed'][k] else 'not confirmed'} |")
print("\nRegistered-code bootstrap H5 row uses the code estimator (+%.3f); H2 registered-code p is the poison-arm bootstrap p "
      "(the code computes no H2 p). (k+1)/(B+1) version of the registered-code Holm: %s\n" % (
          M["registered_code"]["H5"]["est"],
          {k: p(v) for k, v in h["registered_code_bootstrap_B5000_plus1"]["adjusted"].items()}))
print("Holm, registered family + gpt-oss H1 (7 members, exact/perm p): %s\n" % {
    k: p(v) for k, v in h["exact_perm_plus_gptoss_H1"]["adjusted"].items()})
print("Registered code's own Holm family (H1 counted twice, H2 absent): %s\n" % M["registered_code"]["holm_code_family_as_registered_code_computes"])

print("## Table C. Per-agent contrasts (BENIGN stratum unless noted); p one-sided in registered direction "
      "(two-sided in parentheses)\n")
print("| contrast | " + " | ".join(SHORT[a] for a in AG) + " | pooled Qwen |")
print("|---|---|---|---|---|")


def cell(r, counts=None):
    s = f"{e(r['est'])} {ci(r['ci95'])}, p={p(r['p_exact'])} ({p(r['p_exact_two_sided'])})"
    return s + (f"; {counts}" if counts else "")


def pc(r, a, b):
    return f"{r['k_' + a]} vs {r['k_' + b]} of {r['n_pairs']}, b/c={r['mcnemar_b']}/{r['mcnemar_c']}"


def pool(r):
    return f"{e(r['est'])} {ci(r['ci95'])}, p={p(r['p_exact'])}"


print("| H1 E_unknown − S_ok | " + " | ".join(cell(M["H1"][a], pc(M["H1"][a], "E_unknown", "S_ok")) for a in AG)
      + f" | {pool(M['H2']['poison_contrast'])} (descriptive) |")
print("| H3 E_unknown − E_unknown_remedy | " + " | ".join(
    cell(M["H3"]["per_agent"][a], pc(M["H3"]["per_agent"][a], "E_unknown", "E_unknown_remedy")) for a in AG)
      + f" | {pool(M['H3']['pooled_qwen'])} |")
print("| H4 mean(UNK,INT) − mean(DEAD,PERM) | " + " | ".join(cell(M["H4"]["per_agent"][a]) for a in AG)
      + f" | {pool(M['H4']['pooled_qwen'])} |")
for part, lab in (("minus_deadline", "H4a mean(UNK,INT) − DEADLINE"), ("minus_permission", "H4b mean(UNK,INT) − PERMISSION")):
    r = M["H4_decomposition"][part]
    print(f"| {lab} | " + " | ".join(cell(r["per_agent"][a]) for a in AG) + f" | {pool(r['pooled_qwen'])} |")
print("| H5 m3 − m2 (registered) | " + " | ".join(cell(M["H5"]["per_agent"][a]["registered"]) for a in AG)
      + f" | {pool(M['H5']['pooled_qwen_registered'])} |")
print("| H6 E_unknown − S_ok, DIRECT stratum | " + " | ".join(
    cell(M["H6"]["per_agent"][a], pc(M["H6"]["per_agent"][a], "E_unknown", "S_ok")) for a in AG)
      + f" | {pool(M['H6']['pooled_qwen'])} |")
print()

print("## Table D. H5 decomposition, d = Y(E_invalid_arg) − Y(E_precondition)\n")
print("| agent | T3 side m3 (counts) | T2 side m2 (counts) | registered m3 − m2 | code estimator | template-label perm p |")
print("|---|---|---|---|---|---|")
for a in AG:
    r = M["H5"]["per_agent"][a]
    t3, t2 = r["T3_side"], r["T2_side"]
    print(f"| {SHORT[a]} | {e(t3['est'])} {ci(t3['ci95'])} ({t3['k_E_invalid_arg']} vs {t3['k_E_precondition']} of {t3['n_pairs']}) | "
          f"{e(t2['est'])} {ci(t2['ci95'])} ({t2['k_E_invalid_arg']} vs {t2['k_E_precondition']} of {t2['n_pairs']}) | "
          f"{e(r['registered']['est'])} {ci(r['registered']['ci95'])}, p={p(r['registered']['p_exact'])} | "
          f"{e(r['code_estimator']['est'])} | {p(r['template_perm']['p_mc'])} |")
h5 = M["H5"]
print(f"| pooled Qwen | {pool(h5['pooled_qwen_T3_side'])} | {pool(h5['pooled_qwen_T2_side'])} | "
      f"{pool(h5['pooled_qwen_registered'])} | {e(h5['pooled_qwen_code_estimator_B20000']['est'])} "
      f"{ci(h5['pooled_qwen_code_estimator_B20000']['ci95'])} (registered code B=5000: {e(h5['registered_code_output']['est'])} "
      f"[{h5['registered_code_output']['ci95'][0]:+.3f}, {h5['registered_code_output']['ci95'][1]:+.3f}], p={p(h5['registered_code_output']['p_one_sided'])}) | "
      f"{p(h5['pooled_qwen_registered']['p_template_perm_mc'])} |")
rb = h5["registered_estimator_with_registered_bootstrap_B5000"]
print(f"\nRegistered estimator with the registered resampler (B=5000, seed 20261010): {e(rb['est'])} "
      f"[{rb['ci95'][0]:+.3f}, {rb['ci95'][1]:+.3f}], bootstrap p={p(rb['p_one_sided'])}\n")

print("## Table E. H2 detail\n")
h2 = M["H2"]
print(f"- pooled poison contrast {e(h2['poison_contrast']['est'])} {ci(h2['poison_contrast']['ci95'])}; pooled clean contrast "
      f"{e(h2['clean_contrast']['est'])} {ci(h2['clean_contrast']['ci95'])}; clean Y=0 in every condition: {h2['clean_all_conditions_zero']}")
print(f"- clean pairs: " + ", ".join(f"{SHORT[a]} {v['k_E_unknown']} vs {v['k_S_ok']} of {v['n_pairs']}" for a, v in h2["clean_per_agent"].items()))
print(f"- D = {e(h2['D'])} {ci(h2['D_ci95'])}; p arm-label exact {p(h2['p_arm_perm_exact'])}, MC {p(h2['p_arm_perm_mc'])}; "
      f"sign-flip both arms exact {p(h2['p_signflip_both_arms_exact'])}")
for k, v in h2["poison_restricted"].items():
    per = "; ".join(f"{SHORT[a]} {x['k_E_unknown']} vs {x['k_S_ok']} of {x['n_pairs']} = {e(x['est'])} {ci(x['ci95'])}, p={p(x['p_exact'])}"
                    for a, x in v["per_agent"].items())
    print(f"- poison contrast restricted to {k}: pooled {pool(v['pooled'])}; {per}; D_restricted {e(v['D_restricted'])}, "
          f"arm-perm p {p(v['p_arm_perm_exact'])}")
print()

print("## Table F. Sensitivity: cases with empty signatures excluded " + str(D["inputs"]["empty_signature_cases"]) + "\n")
print("| quantity | main | excluding empty-signature cases |")
print("|---|---|---|")
for a in AG:
    for R, tag in ((M, "m"), (S, "s")):
        pass
    mu, su = M["H1"][a], S["H1"][a]
    print(f"| H1 {SHORT[a]} | {mu['marginal']['E_unknown'][0]}/{mu['marginal']['E_unknown'][1]} vs {mu['marginal']['S_ok'][0]}/{mu['marginal']['S_ok'][1]}, "
          f"{e(mu['est'])} {ci(mu['ci95'])}, p={p(mu['p_exact'])} | {su['marginal']['E_unknown'][0]}/{su['marginal']['E_unknown'][1]} vs "
          f"{su['marginal']['S_ok'][0]}/{su['marginal']['S_ok'][1]}, {e(su['est'])} {ci(su['ci95'])}, p={p(su['p_exact'])} |")
print(f"| H2 D | {e(M['H2']['D'])} {ci(M['H2']['D_ci95'])}, p={p(M['H2']['p'])} | {e(S['H2']['D'])} {ci(S['H2']['D_ci95'])}, p={p(S['H2']['p'])} |")
for k, path in (("H3", ("H3", "pooled_qwen")), ("H4", ("H4", "pooled_qwen")), ("H5", ("H5", "pooled_qwen_registered")), ("H6", ("H6", "pooled_qwen"))):
    mr, sr = M[path[0]][path[1]], S[path[0]][path[1]]
    print(f"| {k} pooled Qwen | {pool(mr)} | {pool(sr)} |")
print("| Holm-adjusted (exact/perm) | " + ", ".join(f"{k} {p(v)}" for k, v in M["holm"]["exact_perm_primary"]["adjusted"].items())
      + " | " + ", ".join(f"{k} {p(v)}" for k, v in S["holm"]["exact_perm_primary"]["adjusted"].items()) + " |")
print(f"\nVerdict changes: {D['verdict_changes'] or 'none'}")
print(f"Excluded cases present: {S['excluded_present']}")
