"""Auxiliary prediction P-CB (prereg/PREREG_addendum_v4_amendment1_KO.md), written before any v4 turn-2 output was read.
P-CB: errors that blame the call revive more than the other error strings, BENIGN stratum:
  mean(E_invalid_arg, E_precondition) - mean(E_unknown, E_internal, E_deadline, E_permission) > 0
Same machinery as H4m in model_h.py: per-case contrast, one-sided sign-flip p, case bootstrap CI. Not in the Holm family."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/models')
import confirm_analysis as ca
from model_h import boot, signflip_p

CALL = ['E_invalid_arg', 'E_precondition']
OTHER = ['E_unknown', 'E_internal', 'E_deadline', 'E_permission']

def pcb(run):
    _, Y, _ = ca.load_Y(run)
    v = [x for _, x in sorted(ca.contrast_vals(Y, ca.mean_diff(CALL, OTHER)).items())]
    return {"run": run, "n": len(v), "est": round(sum(v) / len(v), 4) if v else None, "ci": boot(v), "p": signflip_p(v) if v else None}

if __name__ == '__main__':
    for run in sys.argv[1:]:
        print(json.dumps(pcb(run), default=str))
