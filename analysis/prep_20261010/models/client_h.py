"""PREREG_addendum_v3_clients: P-C1 CL_plain > S_ok (exact McNemar); P-C2 mean(fix-type) - CL_plain > 0 (sign-flip)."""
import json, random, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import confirm_analysis as ca
from model_h import mcnemar_one_sided, boot, signflip_p
FIX = ['CL_pydantic', 'CL_langgraph', 'CL_continue']
ORDER = ['S_ok', 'CL_plain', 'CL_sdk_server', 'CL_roo', 'CL_codex', 'CL_cline4_json', 'CL_gemini_cli', 'CL_pydantic', 'CL_langgraph', 'CL_continue', 'CL_agents_exc', 'CL_copilot_exc']
def run(r):
    ag, Y, meta = ca.load_Y(r)
    out = {"agent": ag, "t1": meta['t1'], "Y": {c: f"{sum(Y[c].values())}/{len(Y[c])}" for c in ORDER if c in Y}}
    cs = sorted(set(Y['CL_plain']) & set(Y['S_ok']))
    b = sum(1 for c in cs if Y['CL_plain'][c] and not Y['S_ok'][c]); cc = sum(1 for c in cs if not Y['CL_plain'][c] and Y['S_ok'][c])
    d = [Y['CL_plain'][c] - Y['S_ok'][c] for c in cs]
    out["P-C1"] = {"n": len(cs), "diff": round(sum(d) / len(d), 4), "ci": boot(d), "discordant": (b, cc), "p": mcnemar_one_sided(b, cc)}
    cs2 = sorted(set.intersection(*[set(Y[k]) for k in FIX + ['CL_plain']]))
    d2 = [sum(Y[k][c] for k in FIX) / 3 - Y['CL_plain'][c] for c in cs2]
    out["P-C2"] = {"n": len(cs2), "est": round(sum(d2) / len(d2), 4), "ci": boot(d2), "p": signflip_p(d2)}
    return out
if __name__ == '__main__':
    print(json.dumps({r: run(r) for r in sys.argv[1:]}, indent=1, default=str))
