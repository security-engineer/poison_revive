"""Freeze the dev / held-out split before any model output exists.

Stratified by (server, paradigm): within each stratum cases are ordered by
sha256(SALT + case_id) and the first round(0.3 * n) go to dev (at least 1 when n >= 2).
FileSystem::12 (the case that motivated the study) is forced into dev and
flagged, because it was selected on its outcome.
"""
import collections, hashlib, json, sys
sys.path.insert(0, 'src')
from cs_common import load_cases, DATA, sha256_file
SALT = "condition-study-split-v1-20261009"
cases = load_cases()
strata = collections.defaultdict(list)
for cid, c in cases.items():
    strata[(c['server'], c['paradigm'])].append(cid)
split = {}
for k, ids in strata.items():
    ids.sort(key=lambda x: hashlib.sha256((SALT + x).encode()).hexdigest())
    n_dev = round(0.3 * len(ids))
    if len(ids) >= 2:
        n_dev = max(1, n_dev)
    for i, cid in enumerate(ids):
        split[cid] = 'dev' if i < n_dev else 'heldout'
split['FileSystem::12'] = 'dev'
out = {"salt": SALT, "rule": __doc__.strip(), "cases_sha256": sha256_file(DATA / 'cases.jsonl'),
       "motivating_case_in_dev": "FileSystem::12", "split": split}
json.dump(out, open(DATA / 'split.json', 'w'), indent=0)
cnt = collections.Counter((v, cases[k]['paradigm']) for k, v in split.items())
print(sorted(cnt.items()), collections.Counter(split.values()), sha256_file(DATA / 'split.json'))
