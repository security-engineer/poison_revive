r"""Amendment 1 to the registered v4 mechanism test (prereg/PREREG_addendum_v4_amendment1_KO.md), written before any v4 turn-2 output was read.
The registered mech_test.py takes the carrier name with re.match(r"Tool:\s*(\S+)") on the raw MCPTox text, where line breaks are the
two characters '\\n'. For about half of the cases the capture then ends in a literal '\\nDescription:' and never matches a trace, so
X_mention is forced to 0 (77/150 cases in held-out ranks 1-150, 61/150 in ranks 301-450). Everything else in mech_test.py is kept;
only carrier() is replaced. The name now comes from run_native.parse_tools, the parser that built the tool list the model saw.
X_reread (M2) does not use carrier() and is unchanged."""
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, 'analysis/prep_20261010/mech')
import mech_test as mt
import confirm_analysis as ca
from run_native import parse_tools

def carrier(case_id):
    t = parse_tools(ca.CASES[case_id]['poisoned_tool'].replace("\\n", "\n"))
    return t[0]['function']['name'] if t else None

mt.carrier = carrier

if __name__ == '__main__':
    for run in sys.argv[1:]:
        rows = mt.rows_of(run)
        print(json.dumps({"run": run, "amendment": 1, "M1_mention": mt.test(rows, 'mention'), "M2_reread": mt.test(rows, 'reread')}, default=str))
