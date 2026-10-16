#!/bin/sh
# Reproduce every number in this folder (offline; reads runs/ and data/ only; no model calls).
# Run from condition_study/:  sh analysis/fix_20261010/measure/run_all.sh
set -e
D=analysis/fix_20261010/measure
python3 $D/s1_normalization.py      # (1) tool-name normalization sensitivity  -> s1_normalization.json
python3 $D/s2_trigger_reach.py      # (2) gpt-oss trigger reach                -> s2_trigger_reach.json
python3 $D/s3_audit_sample.py       # (3) audit items (deterministic sample)    -> audit_*_items.json, audit_dump_*.txt
python3 $D/s3_audit_stats.py        # (3) precision/recall from manual judgments -> s3_audit_stats.json
python3 $D/s4_mcptox_agreement.py   # (4) agreement with MCPTox labels         -> s4_mcptox_agreement.json
python3 $D/s5_direct_exec.py        # (5) turn-2 DIRECT_EXEC                   -> s5_direct_exec.json
python3 $D/s6_declared.py           # (6) declared-but-not-emitted             -> s6_declared.json, s6_manual_check_items.json
python3 $D/s7_common_pool.py        # (7) common-pool comparison               -> s7_common_pool.json
