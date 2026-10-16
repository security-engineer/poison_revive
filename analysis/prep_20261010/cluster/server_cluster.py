"""Sensitivity (mock review priority 1): cases are nested in 45 MCP servers.
Server-cluster bootstrap CIs and leave-one-server-out for the held-out H1 contrasts (BENIGN stratum)."""
import json, random, sys, collections
sys.path.insert(0, 'src')
import confirm_analysis as ca
CASES = ca.CASES
out = {}
for run in ['conf_q14n_native_poison', 'conf_q8n_native_poison', 'conf_goss_native_poison']:
    ag, Y, _ = ca.load_Y(run)
    pairs = {c: Y['E_unknown'][c] - Y['S_ok'][c] for c in set(Y['E_unknown']) & set(Y['S_ok'])}
    by_srv = collections.defaultdict(list)
    for c, d in pairs.items():
        by_srv[CASES[c]['server']].append(d)
    srv = sorted(by_srv)
    est = sum(pairs.values()) / len(pairs)
    rng = random.Random(20261010); B = 20000; bs = []
    for _ in range(B):
        draw = [srv[rng.randrange(len(srv))] for _ in srv]
        vals = [d for s in draw for d in by_srv[s]]
        bs.append(sum(vals) / len(vals))
    bs.sort()
    loso = {}
    for s in srv:
        vals = [d for t in srv if t != s for d in by_srv[t]]
        loso[s] = sum(vals) / len(vals)
    lo = min(loso.values()); hi = max(loso.values())
    out[ag] = {"n_cases": len(pairs), "n_servers": len(srv), "est": round(est, 4),
               "server_cluster_ci95": (round(bs[int(.025 * B)], 4), round(bs[int(.975 * B) - 1], 4)),
               "p_le0_server_boot": round(sum(1 for x in bs if x <= 0) / B, 4),
               "loso_min": round(lo, 4), "loso_max": round(hi, 4),
               "loso_min_server": min(loso, key=loso.get), "top_servers_by_revivals":
                   sorted(((s, sum(1 for d in by_srv[s] if d > 0), len(by_srv[s])) for s in srv), key=lambda x: -x[1])[:6]}
json.dump(out, open('analysis/prep_20261010/cluster/server_cluster.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
