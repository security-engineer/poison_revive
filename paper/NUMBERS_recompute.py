#!/usr/bin/env python3
"""Recompute the key numbers in paper/NUMBERS_KO.md from raw run files (offline).

Usage (from condition_study/; about 40 s):
    python3 -B paper/NUMBERS_recompute.py > /tmp/numbers_recomputed.json

- No model endpoint, no network, no process or container control.
- Writes nothing inside the project. The real-server E2E recount (analysis/prep_20261010/e2e2/recount_e2e_args.py,
  five runs) writes its two helper files into a fresh temporary directory outside the project; only the summary is printed.
- Monte Carlo values from model_h.py (H4m bootstrap/sign-flip, H5m permutation) can differ in the last digits between
  runs because that code iterates over Python sets (see NUMBERS_KO.md, 불일치 6). Exact McNemar values do not change.
- Labels are always recomputed from raw responses with the frozen classifier
  (confirm_analysis.load_Y -> report.relabel). Stored 'label' fields are never used.
"""
import sys
sys.dont_write_bytecode = True
import collections, contextlib, hashlib, importlib.util, io, json, os, tempfile, time
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # condition_study/
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'analysis/prep_20261010/models'))
import confirm_analysis as ca  # noqa: E402
import report  # noqa: E402
import model_h  # noqa: E402
import client_h  # noqa: E402
import placebo_h  # noqa: E402
import persist  # noqa: E402

OUT = {"meta": {"script": "paper/NUMBERS_recompute.py", "root": str(ROOT), "started_utc": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "labels": "confirm_analysis.load_Y -> report.relabel (frozen classifier)"}}


def sha(p):
    return hashlib.sha256(open(ROOT / p, 'rb').read()).hexdigest()


def mcn1(b, c):
    """exact one-sided McNemar (b = discordant in the hypothesised direction)"""
    n = b + c
    return 1.0 if n == 0 else sum(comb(n, k) for k in range(b, n + 1)) / 2 ** n


def mcn2(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def holm(ps):
    order = sorted(ps, key=lambda k: ps[k]); m = len(order); res = {}; prev = 0
    for i, k in enumerate(order):
        adj = min(1.0, max(prev, (m - i) * ps[k])); prev = adj; res[k] = adj
    return res


def kn(d):
    return f"{sum(d.values())}/{len(d)}"


def paired(Y, a, b):
    cs = sorted(set(Y.get(a, {})) & set(Y.get(b, {})))
    up = sum(1 for c in cs if Y[a][c] == 1 and Y[b][c] == 0)
    dn = sum(1 for c in cs if Y[a][c] == 0 and Y[b][c] == 1)
    return {"n_pairs": len(cs), "k_a": sum(Y[a][c] for c in cs), "k_b": sum(Y[b][c] for c in cs),
            "diff": round((sum(Y[a][c] for c in cs) - sum(Y[b][c] for c in cs)) / len(cs), 4) if cs else None,
            "discordant": [up, dn], "p_exact_one_sided": mcn1(up, dn), "p_exact_two_sided": mcn2(up, dn)}


# ------------------------------------------------------------------ 1. data and design
cases = [json.loads(l) for l in open(ROOT / 'data/cases.jsonl')]
split = json.load(open(ROOT / 'data/split.json'))
spl = dict(collections.Counter(split['split'].values()))
OUT["data"] = {
    "n_cases": len(cases),
    "n_servers": len({c['case_id'].split('::')[0] for c in cases}),
    "paradigm": dict(collections.Counter(c['paradigm'] for c in cases)),
    "wrong_data": dict(collections.Counter(str(c.get('wrong_data')) for c in cases)),
    "split_sizes": spl,
    "sha256": {p: sha(p) for p in ['data/cases.jsonl', 'data/split.json', 'data/signatures.jsonl',
                                   'data/conditions_v1.json', 'data/conditions_v2_native.json',
                                   'data/conditions_v3_clients.json', 'data/placebo_rules_v1.json',
                                   'src/confirm_analysis.py', 'src/report.py', 'src/cs_common.py', 'src/run_native.py']},
    "n_signatures": sum(1 for _ in open(ROOT / 'data/signatures.jsonl')),
}


def cond_texts(path):
    d = json.load(open(ROOT / path))
    c = d.get('conditions', d)
    if isinstance(c, dict):
        return {k: (v.get('text') if isinstance(v, dict) else v) for k, v in c.items()}
    return {x.get('name'): x for x in c}


OUT["conditions"] = {
    "v1_text_protocol": cond_texts('data/conditions_v1.json'),
    "native_dev": json.load(open(ROOT / 'runs/dev2_q14n_native_poison/manifest.json'))['conditions'],
    "v2_native_heldout": cond_texts('data/conditions_v2_native.json'),
    "v3_clients": cond_texts('data/conditions_v3_clients.json'),
}

# ------------------------------------------------------------------ 2. runs: manifests, turn-1, Y by condition
RUNS = ['dev2_q14n_native_poison', 'dev2_q8n_native_poison', 'dev2_goss_native_poison', 'dev2_goss_text_poison',
        'dev2_q8n_text_poison', 'dev2_q14n_text_poison', 'dev2_q14n_native_clean', 'dev2_q8n_native_clean',
        'dev2_goss_native_clean', 'dev2_goss_text_clean',
        'conf_q14n_native_poison', 'conf_q8n_native_poison', 'conf_goss_native_poison',
        'conf_q14n_native_clean', 'conf_q8n_native_clean',
        'confM_llama31_native_poison', 'confM_llama31_native_clean', 'confM_gemma4_native_poison',
        'confM_gemma4_native_clean', 'confM_mistral7_native_poison', 'confT_q14w_think_poison',
        'cliQ_q14w', 'cliM_llama31', 'cliM_gemma4', 'persQ_q14w', 'persM_llama31', 'persM_gemma4', 'rep5_q14w']
R = {}
YB = {}
for run in RUNS:
    man = json.load(open(ROOT / 'runs' / run / 'manifest.json'))
    ag, Y, meta = ca.load_Y(run)
    _, Yd, _ = ca.load_Y(run, strata=('DIRECT_EXEC',))
    YB[run] = Y
    R[run] = {"agent": ag, "protocol": man.get('protocol', 'text'), "arm": man.get('arm'), "split": man.get('split'),
              "n_cases": man.get('n_cases'), "agent_cfg": man.get('agent_cfg'), "started_utc": man.get('started_utc'),
              "conds_file": man.get('conds_file'), "persist": man.get('persist'), "repeats": man.get('repeats'),
              "reuse_t1": man.get('reuse_t1'), "run_native_sha8": man.get('sha256', {}).get('run_native.py', '')[:8],
              "t1": meta['t1'], "U_benign": meta['U'],
              "Y_benign": {k: kn(v) for k, v in Y.items()}, "Y_direct": {k: kn(v) for k, v in Yd.items()}}
    if man.get('protocol') == 'native':
        R[run]["validity"] = model_h.validity(run)
OUT["runs"] = R

# ------------------------------------------------------------------ 3. key paired contrasts (exact McNemar)
C = {}
for run, a, b in [('dev2_q14n_native_poison', 'E_generic', 'S_ok'), ('dev2_q8n_native_poison', 'E_generic', 'S_ok'),
                  ('dev2_goss_native_poison', 'E_generic', 'S_ok'), ('dev2_goss_text_poison', 'E_generic', 'S_ok'),
                  ('dev2_q14n_native_poison', 'E_json_flag', 'S_ok'), ('dev2_q8n_native_poison', 'E_json_flag', 'S_ok'),
                  ('dev2_q14n_native_poison', 'E_timeout', 'E_remedy'), ('dev2_q8n_native_poison', 'E_timeout', 'E_remedy'),
                  ('dev2_goss_text_poison', 'E_flag_empty', 'S_empty'), ('dev2_goss_text_poison', 'E_text_noflag', 'S_ok'),
                  ('dev2_goss_text_poison', 'X_exception', 'S_ok'),
                  ('dev2_q8n_text_poison', 'X_exception', 'S_ok'), ('dev2_q14n_text_poison', 'X_exception', 'S_ok'),
                  ('dev2_q8n_text_poison', 'E_generic', 'S_ok'), ('dev2_q14n_text_poison', 'E_generic', 'S_ok'),
                  ('conf_q14n_native_poison', 'E_unknown', 'S_ok'), ('conf_q8n_native_poison', 'E_unknown', 'S_ok'),
                  ('conf_goss_native_poison', 'E_unknown', 'S_ok'),
                  ('conf_q14n_native_poison', 'E_unknown', 'E_unknown_remedy'), ('conf_q8n_native_poison', 'E_unknown', 'E_unknown_remedy'),
                  ('conf_goss_native_poison', 'E_unknown', 'E_unknown_remedy'),
                  ('confM_llama31_native_poison', 'E_unknown', 'S_ok'), ('confM_gemma4_native_poison', 'E_unknown', 'S_ok'),
                  ('confM_llama31_native_clean', 'E_unknown', 'S_ok'), ('confM_gemma4_native_clean', 'E_unknown', 'S_ok'),
                  ('confT_q14w_think_poison', 'E_unknown', 'S_ok'),
                  ('cliQ_q14w', 'CL_plain', 'S_ok'), ('cliM_llama31', 'CL_plain', 'S_ok'), ('cliM_gemma4', 'CL_plain', 'S_ok')]:
    C[f"{run}|{a}-{b}"] = paired(YB[run], a, b)
OUT["contrasts"] = C

# ------------------------------------------------------------------ 4. Holm families
p_l = C['confM_llama31_native_poison|E_unknown-S_ok']['p_exact_one_sided']
p_g = C['confM_gemma4_native_poison|E_unknown-S_ok']['p_exact_one_sided']
p_t = C['confT_q14w_think_poison|E_unknown-S_ok']['p_exact_one_sided']
OUT["holm"] = {
    "H1m_registered_3_models(Mistral p=1)": holm({"Llama": p_l, "Gemma": p_g, "Mistral": 1.0}),
    "H1m_valid_models_only": holm({"Llama": p_l, "Gemma": p_g}),
    "H1m_plus_H1t_4": holm({"Llama": p_l, "Gemma": p_g, "Mistral": 1.0, "H1t": p_t}),
    "confirm_with_goss_H1_as_7th": "see analysis/fix_20261010/confirm/tables.txt (exact/perm p)",
}
cli = {r: client_h.run(r) for r in ['cliQ_q14w', 'cliM_llama31', 'cliM_gemma4']}
OUT["clients"] = cli
pc = {"Q14_PC1": cli['cliQ_q14w']['P-C1']['p'], "Llama_PC1": cli['cliM_llama31']['P-C1']['p'],
      "Gemma_PC1": cli['cliM_gemma4']['P-C1']['p'], "Q14_PC2": cli['cliQ_q14w']['P-C2']['p'],
      "Llama_PC2": cli['cliM_llama31']['P-C2']['p'], "Gemma_PC2": cli['cliM_gemma4']['P-C2']['p']}
OUT["holm"]["clients_registered_8(Mistral p=1 x2)"] = holm({**pc, "Mistral_PC1": 1.0, "Mistral_PC2": 1.0})
OUT["holm"]["clients_sensitivity_6"] = holm(pc)

# ------------------------------------------------------------------ 5. model-level registered tests (model_h)
OUT["model_h"] = {r: model_h.run_model(r) for r in ['confM_llama31_native_poison', 'confM_gemma4_native_poison',
                                                     'confT_q14w_think_poison']}

# ------------------------------------------------------------------ 6. placebo, turn-1 compliance, specificity
plc = {}
for run in ['plc_q14w_poison', 'plc_q14w_clean']:
    Y, t1 = placebo_h.load(run)
    plc[run] = {"t1": dict(t1), "Y": {k: kn(v) for k, v in sorted(Y.items())},
                "E_unknown-S_ok": placebo_h.contrast(Y),
                "E_unknown-S_ok|param_tamper": placebo_h.contrast(Y, sub='param_tamper'),
                "E_unknown-S_ok|precondition_hijack": placebo_h.contrast(Y, sub='precondition_hijack')}
PL = json.load(open(ROOT / 'data/placebo_rules_v1.json'))['cases']
plc["n_placebo_cases"] = len(PL)
plc["mechanism_counts"] = dict(collections.Counter(v['mechanism'] for v in PL.values()))
# malicious poison on the same 226 cases, same own Qwen3-14B server (no-think)
for run in ['persQ_q14w', 'cliQ_q14w']:
    t1 = {json.loads(l)['case_id']: report.relabel(json.loads(l), 'native') for l in open(ROOT / 'runs' / run / 'turn1.jsonl')}
    on = collections.Counter(t1[c] for c in PL if c in t1)
    plc[f"turn1_on_226|{run}"] = dict(on)
Yp = YB['persQ_q14w']
plc["malicious_persQ_first_step_on_226"] = {c: kn({k: v for k, v in Yp[c].items() if k in PL}) for c in ['S_ok', 'E_unknown']}
Yc = YB['cliQ_q14w']
plc["malicious_cliQ_on_226"] = {c: kn({k: v for k, v in Yc[c].items() if k in PL}) for c in ['S_ok', 'CL_plain']}
Ybr, _ = placebo_h.load('plc_q14w_poison')
both = sorted(set(Ybr['E_unknown']) & {k for k in Yp['E_unknown'] if k in PL})
plc["overlap_both_turn1_benign"] = {"n": len(both), "malicious_E_unknown(persQ)": sum(Yp['E_unknown'][c] for c in both),
                                    "benign_rule_E_unknown": sum(Ybr['E_unknown'][c] for c in both)}
OUT["placebo"] = plc

# ------------------------------------------------------------------ 7. persistence and repeats
OUT["persistence"] = {r: persist.load(r) for r in ['persQ_q14w', 'persM_llama31', 'persM_gemma4']}
import statistics as st  # noqa: E402
d = ROOT / 'runs/rep5_q14w'
t1 = {json.loads(l)['case_id']: json.loads(l) for l in open(d / 'turn1.jsonl')}
elig = {c for c, r in t1.items() if report.relabel(r, 'native') == 'BENIGN_CALL'}
Yr = collections.defaultdict(lambda: collections.defaultdict(list))
for l in open(d / 'turn2.jsonl'):
    r = json.loads(l)
    if r['case_id'] not in elig:
        continue
    lab = report.relabel(r, 'native')
    if lab in ('ERROR_TRANSPORT', 'TRUNCATED'):
        continue
    Yr[r['condition']][r['case_id']].append(int(lab == 'MALICIOUS'))
rep = {"t1": dict(collections.Counter(report.relabel(r, 'native') for r in t1.values())), "eligible": len(elig)}
for cond in ['S_ok', 'E_unknown', 'E_invalid_arg']:
    ps = {c: sum(v) / len(v) for c, v in Yr[cond].items() if len(v) >= 3}
    vals = list(ps.values())
    within = st.mean([(sum(v) / len(v)) * (1 - sum(v) / len(v)) for v in Yr[cond].values() if len(v) >= 3])
    between = st.pvariance(vals) if len(vals) > 1 else 0
    first = [Yr[cond][c][0] for c in ps]; rest = [sum(Yr[cond][c][1:]) / (len(Yr[cond][c]) - 1) for c in ps]
    rep[cond] = {"cases": len(vals), "draws": sum(len(Yr[cond][c]) for c in ps), "mean_p": round(st.mean(vals), 4),
                 "between_var": round(between, 4), "within_var": round(within, 4),
                 "between_share": round(between / (between + within), 4) if between + within else None,
                 "cases_p_gt0": sum(1 for p in vals if p > 0), "cases_p_eq1": sum(1 for p in vals if p == 1),
                 "first_vs_rest_agree": round(sum(1 for f, r_ in zip(first, rest) if (f == 1) == (r_ >= .5)) / len(vals), 4),
                 "dist": dict(sorted(collections.Counter(round(p, 1) for p in vals).items()))}
OUT["repeats"] = rep

# ------------------------------------------------------------------ 8. think mode extras
import think_trace  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    think_trace.main()
OUT["think_trace_registered_rule_stdout"] = buf.getvalue().strip().splitlines()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    import think_trace_explore  # noqa: E402,F401  (runs at import; prints its table)
OUT["think_trace_exploratory_stdout"] = buf.getvalue().strip().splitlines()
# no-think turn-1 MALICIOUS on the same 150 held-out cases, same own server (cliQ / persQ fresh turn 1)
tt = {json.loads(l)['case_id'] for l in open(ROOT / 'runs/confT_q14w_think_poison/turn1.jsonl')}
cmp = {}
for run in ['cliQ_q14w', 'persQ_q14w', 'conf_q14n_native_poison']:
    lab = {json.loads(l)['case_id']: report.relabel(json.loads(l), 'native') for l in open(ROOT / 'runs' / run / 'turn1.jsonl')}
    cmp[run] = dict(collections.Counter(lab[c] for c in tt if c in lab))
cmp['confT_q14w_think_poison'] = R['confT_q14w_think_poison']['t1']
OUT["think_vs_nothink_turn1_same150"] = cmp

# ------------------------------------------------------------------ 9. MCPTox rescoring (A0) and measurement
mc = json.load(open(ROOT / 'analysis/mcptox_firstturn_by_signature.json'))
OUT["mcptox_firstturn_file_keys"] = list(mc.keys())[:10] if isinstance(mc, dict) else len(mc)

# ------------------------------------------------------------------ 10. real-server E2E recount (all five runs; Gemma has no stored file)
spec = importlib.util.spec_from_file_location('recount_e2e_args', ROOT / 'analysis/prep_20261010/e2e2/recount_e2e_args.py')
argv0 = sys.argv
sys.argv = ['recount_e2e_args.py']
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
sys.argv = argv0
E2E_RUNS = ['e2e_fs_q14n_v1', 'e2e_fs_goss_v1', 'e2e2_fs_q14w', 'e2e2_fs_llama31', 'e2e2_fs_gemma4']
tmp = tempfile.mkdtemp(prefix='numbers_e2e_')   # outside the project
rc.OUT = Path(tmp)
rc.RUNS = E2E_RUNS
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc.main()
ER = json.load(open(Path(tmp) / 'recount_e2e.json'))['runs']
E2E = {}
for run in E2E_RUNS:
    g = ER[run]
    E2E[run] = {"agent": g['agent'], "step0_identical": f"{g['step0_identity']['identical']}/{g['step0_identity']['n']}",
                "step0_labels_alias": g['step0_labels']['alias'], "step0_malicious_alias": g['step0_malicious']['alias'],
                "strict": {c: f"{g['marginal']['strict'][c]['union']}/{g['marginal']['strict'][c]['eligible']}" for c in ('inj_error', 'natural')},
                "current": {c: f"{g['marginal']['current'][c]['union']}/{g['marginal']['current'][c]['eligible']}" for c in ('inj_error', 'natural')},
                "strict_effect_cases": {c: g['marginal']['strict'][c]['effect_cases_union'] for c in ('inj_error', 'natural')},
                "paired_strict_identical_step0": g['paired']['strict']['identical_step0_and_eligible_both']['union'] | {"n_pairs": g['paired']['strict']['identical_step0_and_eligible_both']['n_pairs']},
                "natural_first_result_strict": {k: v['n'] for k, v in g['natural_first_result']['strict'].items() if isinstance(v, dict) and 'n' in v},
                "checks": g['checks']}
OUT["e2e_recount"] = E2E
OUT["meta"]["finished_utc"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
