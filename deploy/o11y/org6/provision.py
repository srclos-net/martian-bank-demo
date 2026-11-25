#!/usr/bin/env python3
"""Provision ObserveNow org 6 ("AWS re:Invent") for the Martian Bank booth: dashboards, alert rules, contact point and
notification policy, all on the Martian Bank ClickHouse (datasource uid `clickhouse`). Idempotent.

  provision.py all | dashboards | alerts | routing
Admin key: ~/.config/aiden/reinvent-onow-admin.key. The Incidents webhook URL is read at run time from Incidents
(integration "fe-stackgen-run (ObserveNow)") with the booth-aiden token, so no token lives in this repo.
"""
import base64, importlib.util, json, os, subprocess, sys, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("q", os.path.join(HERE, "queries.py")); Q = importlib.util.module_from_spec(spec); spec.loader.exec_module(Q)
G = "https://stephgen-medussa.observe.devopsnow.cloud"
KEY = open(os.path.expanduser("~/.config/aiden/reinvent-onow-admin.key")).read().strip()
DS = {"type": "grafana-clickhouse-datasource", "uid": "clickhouse"}
FOLDER = "martian-bank-booth"
R = "https://github.com/srclos-net/martian-bank-demo"


def api(method, path, body=None, extra=None):
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", **(extra or {})}
    req = urllib.request.Request(G + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read(); return e.code, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode()[:300])


# ------------------------------------------------------------------------------------------------ dashboards
def tgt(sql, fmt="table", ref="A"):
    f = {"timeseries": 0, "table": 1, "logs": 2}[fmt]
    return {"refId": ref, "datasource": DS, "editorType": "sql", "format": f, "queryType": fmt, "rawSql": sql}


def panel(pid, title, kind, sql, x, y, w, h, fmt=None, unit=None, extra=None):
    fmt = fmt or ("timeseries" if kind == "timeseries" else "logs" if kind == "logs" else "table")
    p = {"id": pid, "type": kind, "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [tgt(sql, fmt)], "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    if extra:
        for k, v in extra.items():
            if k == "defaults":
                p["fieldConfig"]["defaults"].update(v)
            else:
                p.setdefault("options", {}).update(v) if k == "options" else p.__setitem__(k, v)
    return p


def text(pid, md, y=0, h=3):
    return {"id": pid, "type": "text", "title": "", "gridPos": {"x": 0, "y": y, "w": 24, "h": h}, "options": {"mode": "markdown", "content": md}}


NAV = (f"[Booth](/d/martian-bank-booth?orgId=6) · [Services](/d/mb-services?orgId=6) · [Kubernetes](/d/mb-k8s?orgId=6) · "
       f"[Logs & errors](/d/mb-logs?orgId=6) · [Customers (RUM)](/d/mb-rum?orgId=6) · [Bank](https://bank.stackgen.run) · "
       f"[Argo CD](https://argocd.stackgen.run/applications/argocd/martian-bank) · [Incidents](https://incidents.stackgen.run) · [PRs]({R}/pulls)")
THRESH4 = {"defaults": {"min": 0, "custom": {"lineWidth": 2, "fillOpacity": 10, "thresholdsStyle": {"mode": "line+area"}},
                        "thresholds": {"mode": "absolute", "steps": [{"color": "transparent", "value": None}, {"color": "red", "value": 4}]}}}

LOGINS_PER_S = """SELECT count() / 60 AS logins_per_s FROM otel.otel_traces
WHERE ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server' AND Timestamp > now() - INTERVAL 1 MINUTE"""

DASHBOARDS = [
    {"uid": "martian-bank-booth", "title": "Martian Bank — Booth: the outer loop", "panels": [
        text(1, "### 🛰️ Martian Bank — Black Friday on Mars · **Detect** (Aiden for SRE) → **Work order** (Aiden for DevOps) → **Approve** (a person) → **Reconcile** (InfraOps) → **Ship** (DevOps) → **Verify** (Aiden)\n" + NAV),
        panel(2, "Customer login p95 (customer-auth POST /api/users/auth)", "timeseries", Q.TS_LOGIN_P95, 0, 3, 12, 9, unit="s", extra=THRESH4),
        panel(3, "CPU throttled (% of CFS periods) by container", "timeseries", Q.TS_THROTTLE, 12, 3, 12, 9, unit="percent", extra={"defaults": {"min": 0, "max": 100}}),
        panel(4, "customer-auth live CPU limit", "stat", Q.CUSTOMER_AUTH_LIMITS.replace("maxIf(v, resource = 'memory') / 1048576 AS memory_limit_mib", "1 AS _x"), 0, 12, 6, 5, unit="cores",
              extra={"defaults": {"decimals": 2, "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 0.25}]}},
                     "options": {"colorMode": "background", "graphMode": "none", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^cpu_limit_cores$/"}}}),
        panel(5, "Logins / s", "stat", LOGINS_PER_S, 6, 12, 6, 5, unit="reqps", extra={"options": {"reduceOptions": {"calcs": ["lastNotNull"]}}}),
        {"id": 6, "type": "alertlist", "title": "Martian Bank alerts", "gridPos": {"x": 12, "y": 12, "w": 12, "h": 10},
         "options": {"alertName": "", "dashboardAlerts": False, "groupMode": "default", "maxItems": 30, "sortOrder": 1,
                     "stateFilter": {"firing": True, "pending": True, "normal": False, "error": True, "noData": False}, "viewMode": "list",
                     "folder": {"uid": FOLDER}}},
        panel(7, "Server p95 by service", "timeseries", Q.TS_P95_BY_SVC, 0, 17, 12, 8, unit="s"),
    ]},
    {"uid": "mb-services", "title": "Martian Bank — Services (RED)", "panels": [
        text(1, "### Martian Bank services — rate, errors, duration (from OBI eBPF spans)\n" + NAV),
        panel(2, "Requests / s by service", "timeseries", Q.TS_RPS, 0, 3, 12, 8, unit="reqps"),
        panel(3, "Error % by service (span error or HTTP 5xx)", "timeseries", Q.TS_ERR_PCT, 12, 3, 12, 8, unit="percent"),
        panel(4, "p95 latency by service", "timeseries", Q.TS_P95_BY_SVC, 0, 11, 24, 8, unit="s"),
        panel(5, "Slowest routes", "table", Q.TBL_SLOW_ROUTES, 0, 19, 24, 10),
    ]},
    {"uid": "mb-k8s", "title": "Martian Bank — Kubernetes", "panels": [
        text(1, "### Martian Bank on Kubernetes (namespace martian-bank) — cAdvisor + kube-state-metrics\n" + NAV),
        panel(2, "CPU (cores) by container", "timeseries", Q.TS_CPU, 0, 3, 12, 8, unit="none"),
        panel(3, "Memory working set (MiB) by container", "timeseries", Q.TS_MEM, 12, 3, 12, 8, unit="decmbytes"),
        panel(4, "CPU throttled % by container", "timeseries", Q.TS_THROTTLE, 0, 11, 12, 8, unit="percent"),
        panel(5, "Replicas available by deployment", "timeseries", Q.TS_DEPLOY_AVAIL, 12, 11, 12, 8),
        panel(6, "Live limits (CPU cores, memory MiB) — Git-declared containers have both", "table", Q.LIVE_LIMITS, 0, 19, 12, 10),
        panel(7, "Memory vs limit", "table", Q.TBL_MEM_VS_LIMIT, 12, 19, 12, 10),
        panel(8, "Restarts", "table", Q.TBL_RESTARTS, 0, 29, 12, 8),
        panel(9, "Kubernetes events", "table", Q.TBL_EVENTS, 12, 29, 12, 8),
    ]},
    {"uid": "mb-logs", "title": "Martian Bank — Logs & errors", "panels": [
        text(1, "### Martian Bank pod logs (mb-otelcol-logs) — what developers alert on\n" + NAV),
        panel(2, "Error-looking log lines by service", "timeseries", Q.TS_ERROR_LOGS, 0, 3, 24, 8),
        panel(3, "Recent errors", "table", Q.TBL_RECENT_ERRORS, 0, 11, 24, 10),
        panel(4, "Logs", "logs", Q.LOGS_EXPLORER, 0, 21, 24, 14, extra={"options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"}}),
    ]},
    {"uid": "mb-rum", "title": "Martian Bank — Customers (RUM)", "panels": [
        text(1, "### Browser telemetry from https://bank.stackgen.run (Grafana Faro SDK → faro.stackgen.run → Martian Bank ClickHouse)\n" + NAV),
        panel(2, "Browser events by kind", "timeseries", Q.TS_RUM, 0, 3, 24, 9),
    ]},
]


def dashboards():
    for d in DASHBOARDS:
        body = {"dashboard": {**d, "tags": ["martian-bank", "reinvent"], "timezone": "browser", "refresh": "10s", "schemaVersion": 39,
                              "time": {"from": "now-30m", "to": "now"}, "templating": {"list": []},
                              "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True,
                                                        "hide": True, "name": "Annotations & Alerts", "type": "dashboard"}]}},
                "folderUid": FOLDER, "overwrite": True, "message": "provision.py"}
        st, r = api("POST", "/api/dashboards/db", body)
        print("dashboard", d["uid"], st, r.get("status") if isinstance(r, dict) else r)


# ------------------------------------------------------------------------------------------------ alerts
def rule(uid, title, sql, op, thr, labels, summary, description, for_="1m", nodata="OK"):
    return {"uid": uid, "title": title, "condition": "C", "folderUID": FOLDER, "orgID": 6, "for": for_, "noDataState": nodata,
            "execErrState": "OK", "isPaused": False,
            "labels": {"namespace": "martian-bank", "cluster": "fe-stackgen-run", "demo": "reinvent-booth", **labels},
            "annotations": {"summary": summary, "description": description, "runbook_url": f"{R}/blob/main/docs/reinvent/RUNBOOK.md"},
            "data": [{"refId": "A", "datasourceUid": "clickhouse", "relativeTimeRange": {"from": 600, "to": 0},
                      "model": {"refId": "A", **tgt(sql, "table")}},
                     {"refId": "B", "datasourceUid": "__expr__", "relativeTimeRange": {"from": 0, "to": 0},
                      "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": "last", "settings": {"mode": "dropNN"}}},
                     {"refId": "C", "datasourceUid": "__expr__", "relativeTimeRange": {"from": 0, "to": 0},
                      "model": {"refId": "C", "type": "threshold", "expression": "B", "conditions": [{"evaluator": {"type": op, "params": [thr]}}]}}]}


def logs_count(service, where, minutes=5):
    return (f"SELECT count() AS lines FROM otel.otel_logs WHERE ServiceName = '{service}' AND Timestamp > now() - INTERVAL {minutes} MINUTE AND ({where})")


def spans_count(where, minutes=5):
    return f"SELECT count() AS spans FROM otel.otel_traces WHERE Timestamp > now() - INTERVAL {minutes} MINUTE AND ({where})"


DEV = {"team": "dev", "severity": "warning"}
PLAT = {"team": "platform"}
GROUPS = {
    # The one that pages (Incidents): customer impact.
    "martian-bank-booth": (20, [
        rule("martian-bank-login-slow", "Martian Bank: customer logins slow (customer-auth p95 > 4s)", Q.LOGIN_P95_1M, "gt", 4,
             {"service": "customer-auth", "severity": "critical", "team": "sre"},
             "Martian Bank customers wait more than 4 s to log in (customer-auth p95 {{ $values.B.Value }}s)",
             "Login latency on customer-auth (POST /api/users/auth) is above the 4 s customer SLO. Check customer-auth CPU throttling and its live resources vs Git (deploy/values-civo.yaml). Argo CD only diffs fields Git declares.",
             for_="30s"),
    ]),
    # What developers write: one alert per thing they once got bitten by. Mostly noise; some fire all day.
    "martian-bank-dev": (60, [
        rule("mb-dev-auth-stacktraces", "customer-auth: error stack trace logged", logs_count("customer-auth", "Body ILIKE '%Error%' OR Body ILIKE '%    at %'"), "gt", 0,
             {**DEV, "service": "customer-auth"}, "customer-auth logged {{ $values.B.Value }} stack-trace lines in 5 min", "Someone wants to know whenever an Error stack trace shows up in customer-auth's logs."),
        rule("mb-dev-auth-notfound", "customer-auth: NotFound thrown by errorMiddleware", logs_count("customer-auth", "Body ILIKE '%notFound%'"), "gt", 0,
             {**DEV, "service": "customer-auth"}, "customer-auth threw NotFound {{ $values.B.Value }} times", "errorMiddleware.js notFound() fired. Usually a client calling a route that doesn't exist."),
        rule("mb-dev-auth-login-failures", "customer-auth: failed logins (4xx on /api/users/auth)",
             spans_count("ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server' AND toUInt16OrZero(SpanAttributes['http.response.status_code']) BETWEEN 400 AND 499"), "gt", 5,
             {**DEV, "service": "customer-auth"}, "{{ $values.B.Value }} failed logins in 5 min", "Bad passwords or unknown users. Could be a brute-force attempt, could be Locust."),
        rule("mb-dev-dashboard-traceback", "dashboard: Python exception (Traceback)", logs_count("dashboard", "Body ILIKE '%Traceback%' OR Body ILIKE '%Exception%'"), "gt", 0,
             {**DEV, "service": "dashboard"}, "dashboard raised {{ $values.B.Value }} exceptions", "A Flask handler raised. Check the traceback in Logs & errors."),
        rule("mb-dev-transactions-errors", "transactions: transfer error logged", logs_count("transactions", "Body ILIKE '%error%' OR Body ILIKE '%insufficient%'"), "gt", 0,
             {**DEV, "service": "transactions"}, "transactions logged {{ $values.B.Value }} transfer errors", "Zelle or internal transfer failed (insufficient funds or a bad account)."),
        rule("mb-dev-loan-slow", "loan: p95 above 50 ms", "SELECT round(quantile(0.95)(Duration) / 1e6, 1) AS p95_ms FROM otel.otel_traces WHERE ServiceName = 'loan' AND SpanKind = 'Server' AND Timestamp > now() - INTERVAL 5 MINUTE",
             "gt", 50, {**DEV, "service": "loan"}, "loan p95 {{ $values.B.Value }} ms", "The loan team's own latency target (tighter than the customer SLO)."),
        rule("mb-dev-atm-404", "atm-locator: 404 for an ATM id", spans_count("ServiceName = 'atm-locator' AND SpanKind = 'Server' AND SpanAttributes['http.response.status_code'] = '404'"), "gt", 0,
             {**DEV, "service": "atm-locator"}, "{{ $values.B.Value }} ATM lookups returned 404", "Somebody asked for an ATM that doesn't exist."),
        rule("mb-dev-accounts-mongo-slow", "accounts: Mongo find slower than 30 ms",
             "SELECT round(quantile(0.95)(Duration) / 1e6, 1) AS p95_ms FROM otel.otel_traces WHERE ServiceName = 'accounts' AND SpanKind = 'Client' AND Timestamp > now() - INTERVAL 5 MINUTE",
             "gt", 30, {**DEV, "service": "accounts"}, "accounts → mongo p95 {{ $values.B.Value }} ms", "Database calls from accounts are slower than the team likes."),
        rule("mb-dev-nginx-5xx", "nginx: upstream 5xx", spans_count("ServiceName = 'nginx' AND toUInt16OrZero(SpanAttributes['http.response.status_code']) >= 500"), "gt", 0,
             {**DEV, "service": "nginx"}, "{{ $values.B.Value }} 5xx at the front door", "nginx returned 5xx: an upstream failed or timed out."),
        rule("mb-dev-ui-js-errors", "ui: JavaScript errors in the browser", "SELECT count() AS errors FROM otel.otel_logs WHERE ServiceName = 'martian-bank-ui' AND Timestamp > now() - INTERVAL 5 MINUTE AND (SeverityText ILIKE 'error' OR Body ILIKE '%error%')",
             "gt", 0, {**DEV, "service": "ui"}, "{{ $values.B.Value }} browser errors", "Faro reported JavaScript errors from bank.stackgen.run."),
    ]),
    # What the platform team writes: resource and workload health.
    "martian-bank-platform": (60, [
        rule("mb-plat-cpu-throttled", "CPU throttling above 25%",
             Q.THROTTLE_PCT_2M.replace("AND Attributes['container'] = 'customer-auth' ", "").replace("SELECT round(", "SELECT container, round(").replace("FROM (SELECT MetricName AS m,", "FROM (SELECT Attributes['container'] AS container, MetricName AS m,").replace("GROUP BY m, id)", "GROUP BY container, m, id) GROUP BY container"),
             "gt", 25, {**PLAT, "severity": "warning"}, "{{ $labels.container }} is throttled {{ $values.B.Value }}% of CPU periods", "The container keeps hitting its CPU limit. Check the limit against Git and the load."),
        rule("mb-plat-mem-near-limit", "Memory above 80% of limit", "SELECT container, pct_of_limit FROM (" + Q.TBL_MEM_VS_LIMIT + ") WHERE pct_of_limit IS NOT NULL",
             "gt", 80, {**PLAT, "severity": "warning"}, "{{ $labels.container }} uses {{ $values.B.Value }}% of its memory limit", "Working set close to the limit: an OOM kill is next."),
        rule("mb-plat-no-mem-limit", "Container running without a memory limit",
             "SELECT container, toUInt8(cpu_limit_cores > 0 AND memory_limit_mib = 0) AS missing FROM (" + Q.LIVE_LIMITS + ")",
             "gt", 0, {**PLAT, "severity": "warning"}, "{{ $labels.container }} has a CPU limit but no memory limit", "Every Git-declared container has both. A CPU-only limit usually means someone set it by hand."),
        rule("mb-plat-restarts", "Pod restarted in the last 15 min",
             "SELECT Attributes['container'] AS container, max(Value) - min(Value) AS restarts FROM otel.otel_metrics_sum WHERE MetricName = 'kube_pod_container_status_restarts_total' AND TimeUnix > now() - INTERVAL 15 MINUTE GROUP BY container",
             "gt", 0, {**PLAT, "severity": "warning"}, "{{ $labels.container }} restarted {{ $values.B.Value }} times", "Crash or OOM. Check last_terminated_reason and the logs."),
        rule("mb-plat-oom", "Container OOM-killed",
             "SELECT Attributes['container'] AS container, max(Value) - min(Value) AS ooms FROM otel.otel_metrics_sum WHERE MetricName = 'container_oom_events_total' AND TimeUnix > now() - INTERVAL 15 MINUTE GROUP BY container",
             "gt", 0, {**PLAT, "severity": "critical"}, "{{ $labels.container }} was OOM-killed", "The kernel killed the container for exceeding its memory limit."),
        rule("mb-plat-replicas-unavailable", "Deployment has unavailable replicas",
             "SELECT Attributes['deployment'] AS deployment, argMax(Value, TimeUnix) AS unavailable FROM otel.otel_metrics_gauge WHERE MetricName = 'kube_deployment_status_replicas_unavailable' AND TimeUnix > now() - INTERVAL 2 MINUTE GROUP BY deployment",
             "gt", 0, {**PLAT, "severity": "warning"}, "{{ $labels.deployment }} has {{ $values.B.Value }} unavailable replicas", "A rollout is stuck or pods are crash-looping."),
        rule("mb-plat-last-terminated-error", "Container last terminated with Error",
             "SELECT Attributes['container'] AS container, argMax(Value, TimeUnix) AS errored FROM otel.otel_metrics_gauge WHERE MetricName = 'kube_pod_container_status_last_terminated_reason' AND Attributes['reason'] = 'Error' AND TimeUnix > now() - INTERVAL 2 MINUTE GROUP BY container",
             "gt", 0, {**PLAT, "severity": "info"}, "{{ $labels.container }} last terminated with Error", "Kubernetes still remembers the last crash of this container (it may be long ago)."),
        rule("mb-plat-warning-events", "Kubernetes warning events",
             "SELECT count() AS warnings FROM otel.otel_logs WHERE ScopeName LIKE '%k8sevents%' AND SeverityText = 'Warning' AND Timestamp > now() - INTERVAL 10 MINUTE",
             "gt", 3, {**PLAT, "severity": "info"}, "{{ $values.B.Value }} warning events in martian-bank in 10 min", "BackOff, Unhealthy, FailedScheduling and friends."),
        rule("mb-plat-scrape-down", "Metrics scrape target down",
             "SELECT Attributes['node'] AS node, argMax(Value, TimeUnix) AS up FROM otel.otel_metrics_gauge WHERE MetricName = 'up' AND TimeUnix > now() - INTERVAL 2 MINUTE GROUP BY node",
             "lt", 1, {**PLAT, "severity": "warning"}, "cAdvisor scrape on {{ $labels.node }} is down", "mb-otelcol can't scrape a node's cAdvisor: container metrics for pods on that node are missing."),
    ]),
}


def alerts():
    for group, (interval, rules) in GROUPS.items():
        body = {"folderUid": FOLDER, "interval": interval, "title": group, "rules": [dict(r, ruleGroup=group) for r in rules]}
        st, r = api("PUT", f"/api/v1/provisioning/folder/{FOLDER}/rule-groups/{group}", body, {"X-Disable-Provenance": "true"})
        print("rule group", group, st, len(rules), "" if st == 200 else r)


# ------------------------------------------------------------------------------------------------ routing
def incidents_webhook():
    tok = base64.b64decode(subprocess.run(["/opt/homebrew/bin/kubectl", "--context", "fe-stackgen-run", "-n", "martian-bank", "get", "secret",
                                           "incidents-booth", "-o", "jsonpath={.data.token}"], capture_output=True, text=True, check=True).stdout).decode()
    req = urllib.request.Request("https://incidents.stackgen.run/api/integrations", headers={"Authorization": f"Bearer {tok}"})
    for i in json.load(urllib.request.urlopen(req, timeout=30)):
        if i["name"] == "fe-stackgen-run (ObserveNow)":
            return i["url"]
    sys.exit("Incidents integration 'fe-stackgen-run (ObserveNow)' not found")


def routing():
    cps = [{"uid": "mb-incidents", "name": "Martian Bank → Incidents (pages)", "type": "webhook",
            "settings": {"url": incidents_webhook(), "httpMethod": "POST"}, "disableResolveMessage": False},
           {"uid": "mb-triage-only", "name": "Martian Bank → triage only (Aiden for SRE pulls, nobody is paged)", "type": "email",
            "settings": {"addresses": "booth-triage-only@stackgen.invalid", "singleEmail": True}, "disableResolveMessage": True}]
    for cp in cps:
        st, _ = api("PUT", f"/api/v1/provisioning/contact-points/{cp['uid']}", cp, {"X-Disable-Provenance": "true"})
        if st == 404 or st >= 400:
            st, r = api("POST", "/api/v1/provisioning/contact-points", cp, {"X-Disable-Provenance": "true"})
        print("contact point", cp["uid"], st)
    policy = {"receiver": "Martian Bank → triage only (Aiden for SRE pulls, nobody is paged)", "group_by": ["grafana_folder", "alertname"],
              "routes": [{"receiver": "Martian Bank → Incidents (pages)", "object_matchers": [["severity", "=", "critical"], ["team", "=", "sre"]],
                          "group_by": ["alertname"], "group_wait": "10s", "group_interval": "1m", "repeat_interval": "1h"}]}
    st, r = api("PUT", "/api/v1/provisioning/policies", policy, {"X-Disable-Provenance": "true"})
    print("policy", st, "" if st == 202 or st == 200 else r)


what = sys.argv[1] if len(sys.argv) > 1 else "all"
if what in ("all", "dashboards"): dashboards()
if what in ("all", "routing"): routing()
if what in ("all", "alerts"): alerts()
