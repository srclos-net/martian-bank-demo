#!/usr/bin/env python3
"""Run every SQL in queries.py through Grafana org 6 (as dashboards/alerts would) and report rows or errors."""
import importlib.util, json, os, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("q", os.path.join(HERE, "queries.py")); q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
KEY = open(os.path.expanduser("~/.config/aiden/reinvent-onow-admin.key")).read().strip()
G = "https://stephgen-medussa.observe.devopsnow.cloud"


def run(sql, frm="now-15m"):
    body = {"queries": [{"refId": "A", "datasource": {"uid": "clickhouse", "type": "grafana-clickhouse-datasource"},
                         "rawSql": sql, "format": 1, "queryType": "table", "intervalMs": 30000, "maxDataPoints": 500}],
            "from": frm, "to": "now"}
    req = urllib.request.Request(G + "/api/ds/query", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))["results"]["A"]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:300]}"
    if r.get("error"):
        return "ERROR " + r["error"][:300]
    f = r.get("frames") or []
    if not f or not f[0]["data"]["values"]:
        return "0 rows"
    vals = f[0]["data"]["values"]; names = [x["name"] for x in f[0]["schema"]["fields"]]
    first = {n: v[0] for n, v in zip(names, vals)}
    return f"{len(vals[0])} rows, first={json.dumps(first, default=str)[:160]}"


names = [n for n in dir(q) if n.isupper()] if len(sys.argv) < 2 else sys.argv[1:]
bad = 0
for n in names:
    out = run(getattr(q, n))
    bad += out.startswith(("ERROR", "HTTP"))
    print(f"{n:20} {out}")
sys.exit(1 if bad else 0)
