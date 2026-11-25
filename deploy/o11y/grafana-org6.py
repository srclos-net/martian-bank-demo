#!/usr/bin/env python3
"""Org 6 ("AWS re:Invent") datasource wiring for the Martian Bank ClickHouse (mb-o11y).

  grafana-org6.py datasource     create/update the ClickHouse datasource (uid `clickhouse`); password read from
                                 Secret mb-o11y/mb-clickhouse-users (key grafana), never printed
  grafana-org6.py health         datasource health + a test query
  grafana-org6.py query "SQL"    run a SQL query through Grafana (as Aiden would)
Admin key: ~/.config/aiden/reinvent-onow-admin.key (org 6 only).
"""
import base64, json, os, subprocess, sys, urllib.request, urllib.error

G = "https://stephgen-medussa.observe.devopsnow.cloud"
HOST = "mb-clickhouse.39aaccad-291b-488b-9e67-526a5514adf2.k8s.civo.com"
KEY = open(os.path.expanduser("~/.config/aiden/reinvent-onow-admin.key")).read().strip()


def api(method, path, body=None):
    req = urllib.request.Request(G + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def ch_password():
    out = subprocess.run(["/opt/homebrew/bin/kubectl", "--context", "fe-stackgen-run", "-n", "mb-o11y", "get", "secret",
                          "mb-clickhouse-users", "-o", "jsonpath={.data.grafana}"], capture_output=True, text=True, check=True)
    return base64.b64decode(out.stdout).decode()


DS = {
    "uid": "clickhouse", "name": "Martian Bank (ClickHouse)", "type": "grafana-clickhouse-datasource", "access": "proxy",
    "isDefault": True,
    "jsonData": {
        "host": HOST, "port": 443, "protocol": "http", "secure": True, "path": "", "username": "grafana",
        "defaultDatabase": "otel", "dialTimeout": "10", "queryTimeout": "60",
        "logs": {"defaultDatabase": "otel", "defaultTable": "otel_logs", "otelEnabled": True, "otelVersion": "latest"},
        "traces": {"defaultDatabase": "otel", "defaultTable": "otel_traces", "otelEnabled": True, "otelVersion": "latest"},
    },
}


def query(sql):
    st, r = api("POST", "/api/ds/query", {"queries": [{"refId": "A", "datasource": {"uid": "clickhouse", "type": "grafana-clickhouse-datasource"},
                                                     "rawSql": sql, "format": 1, "queryType": "table"}], "from": "now-15m", "to": "now"})
    if st != 200:
        return st, r
    res = r["results"]["A"]
    if res.get("error"):
        return 400, res["error"]
    f = res.get("frames") or []
    if not f:
        return 200, []
    names = [x["name"] for x in f[0]["schema"]["fields"]]
    cols = f[0]["data"]["values"]
    return 200, [dict(zip(names, row)) for row in zip(*cols)] if cols else []


cmd = sys.argv[1] if len(sys.argv) > 1 else "health"
if cmd == "datasource":
    body = dict(DS, secureJsonData={"password": ch_password()})
    st, r = api("GET", "/api/datasources/uid/clickhouse")
    st, r = api("PUT", f"/api/datasources/uid/clickhouse", body) if st == 200 else api("POST", "/api/datasources", body)
    print(st, r.get("message"), (r.get("datasource") or {}).get("uid"))
elif cmd == "health":
    print(api("GET", "/api/datasources/uid/clickhouse/health"))
    print(query("SELECT count() AS spans FROM otel.otel_traces"))
elif cmd == "query":
    st, rows = query(sys.argv[2])
    print(st)
    for row in (rows if isinstance(rows, list) else [rows])[:40]:
        print(row)
