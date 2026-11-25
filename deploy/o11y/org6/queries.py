"""SQL for org 6 (Martian Bank ClickHouse, db otel). Shared by dashboards, alerts, Aiden skills and booth checks.

Conventions:
  * spans: otel_traces (Duration in ns, SpanKind 'Server'/'Client', StatusCode 'Error'/'Unset'/'Ok')
  * scraped counters: otel_metrics_sum (cumulative; per-series increase = max(Value) - min(Value) in a window,
    series identity = Attributes['id'] for cAdvisor, Attributes['pod']+container for kube-state-metrics)
  * gauges: otel_metrics_gauge (latest value per series = argMax(Value, TimeUnix))
  * logs: otel_logs (pod logs: ServiceName = container; k8s events: ScopeName k8seventsreceiver)
  * $__timeFilter / $__timeInterval are Grafana macros (dashboards); alerts/skills use fixed windows.
"""

# ----------------------------------------------------------------------------------------------- the booth story
LOGIN_P95_1M = """SELECT round(quantile(0.95)(Duration) / 1e9, 2) AS login_p95_s
FROM otel.otel_traces
WHERE ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server'
  AND Timestamp > now() - INTERVAL 1 MINUTE"""

SERVICE_P95_2M = """SELECT ServiceName AS service, round(quantile(0.95)(Duration) / 1e9, 3) AS p95_s, count() AS requests
FROM otel.otel_traces
WHERE SpanKind = 'Server' AND Timestamp > now() - INTERVAL 2 MINUTE
  AND ServiceName IN ('dashboard', 'accounts', 'transactions', 'loan', 'atm-locator')
GROUP BY service ORDER BY p95_s DESC"""

THROTTLE_PCT_2M = """SELECT round(100 * sumIf(d, m = 'container_cpu_cfs_throttled_periods_total')
                       / nullIf(sumIf(d, m = 'container_cpu_cfs_periods_total'), 0), 1) AS throttled_pct
FROM (SELECT MetricName AS m, Attributes['id'] AS id, max(Value) - min(Value) AS d
      FROM otel.otel_metrics_sum
      WHERE MetricName IN ('container_cpu_cfs_throttled_periods_total', 'container_cpu_cfs_periods_total')
        AND Attributes['container'] = 'customer-auth' AND TimeUnix > now() - INTERVAL 2 MINUTE
      GROUP BY m, id)"""

# Live limits per container (newest pod per container); memory in MiB. A Git-declared container has both.
LIVE_LIMITS = """SELECT container,
       maxIf(v, resource = 'cpu') AS cpu_limit_cores,
       maxIf(v, resource = 'memory') / 1048576 AS memory_limit_mib
FROM (SELECT Attributes['container'] AS container, Attributes['resource'] AS resource,
             argMax(Value, TimeUnix) AS v, argMax(Attributes['pod'], TimeUnix) AS pod
      FROM otel.otel_metrics_gauge
      WHERE MetricName = 'kube_pod_container_resource_limits' AND TimeUnix > now() - INTERVAL 2 MINUTE
        AND Attributes['container'] IN ('customer-auth', 'dashboard', 'accounts', 'transactions', 'loan', 'atm-locator',
                                        'nginx', 'ui', 'mongodb', 'locust')
      GROUP BY container, resource, Attributes['pod'])
GROUP BY container ORDER BY container"""

CUSTOMER_AUTH_LIMITS = """SELECT maxIf(v, resource = 'cpu') AS cpu_limit_cores,
       maxIf(v, resource = 'memory') / 1048576 AS memory_limit_mib
FROM (SELECT Attributes['resource'] AS resource, argMax(Value, TimeUnix) AS v
      FROM otel.otel_metrics_gauge
      WHERE MetricName = 'kube_pod_container_resource_limits' AND Attributes['container'] = 'customer-auth'
        AND TimeUnix > now() - INTERVAL 1 MINUTE
      GROUP BY resource)"""

# ----------------------------------------------------------------------------------------------- dashboards
TS_LOGIN_P95 = """SELECT $__timeInterval(Timestamp) AS time, quantile(0.95)(Duration) / 1e9 AS "login p95"
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server'
GROUP BY time ORDER BY time"""

TS_THROTTLE = """SELECT time, container, 100 * sumIf(d, m = 'container_cpu_cfs_throttled_periods_total')
       / nullIf(sumIf(d, m = 'container_cpu_cfs_periods_total'), 0) AS throttled
FROM (SELECT $__timeInterval(TimeUnix) AS time, Attributes['container'] AS container, MetricName AS m,
             Attributes['id'] AS id, max(Value) - min(Value) AS d
      FROM otel.otel_metrics_sum
      WHERE $__timeFilter(TimeUnix) AND MetricName IN ('container_cpu_cfs_throttled_periods_total', 'container_cpu_cfs_periods_total')
      GROUP BY time, container, m, id)
GROUP BY time, container ORDER BY time"""

TS_RPS = """SELECT $__timeInterval(Timestamp) AS time, ServiceName AS service, count() / $__interval_s AS rps
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND SpanKind = 'Server'
GROUP BY time, service ORDER BY time"""

TS_ERR_PCT = """SELECT $__timeInterval(Timestamp) AS time, ServiceName AS service,
       100 * countIf(StatusCode = 'Error' OR toUInt16OrZero(SpanAttributes['http.response.status_code']) >= 500) / count() AS error_pct
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND SpanKind = 'Server'
GROUP BY time, service ORDER BY time"""

TS_P95_BY_SVC = """SELECT $__timeInterval(Timestamp) AS time, ServiceName AS service, quantile(0.95)(Duration) / 1e9 AS p95
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND SpanKind = 'Server'
GROUP BY time, service ORDER BY time"""

TBL_SLOW_ROUTES = """SELECT ServiceName AS service, SpanName AS route, count() AS calls,
       round(quantile(0.5)(Duration) / 1e6, 1) AS p50_ms, round(quantile(0.95)(Duration) / 1e6, 1) AS p95_ms,
       countIf(StatusCode = 'Error') AS errors
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND SpanKind = 'Server'
GROUP BY service, route ORDER BY p95_ms DESC LIMIT 25"""

TS_CPU = """SELECT time, container, sum(d) / $__interval_s AS cores
FROM (SELECT $__timeInterval(TimeUnix) AS time, Attributes['container'] AS container, Attributes['id'] AS id,
             max(Value) - min(Value) AS d
      FROM otel.otel_metrics_sum
      WHERE $__timeFilter(TimeUnix) AND MetricName = 'container_cpu_usage_seconds_total'
      GROUP BY time, container, id)
GROUP BY time, container ORDER BY time"""

TS_MEM = """SELECT $__timeInterval(TimeUnix) AS time, Attributes['container'] AS container, max(Value) / 1048576 AS mib
FROM otel.otel_metrics_gauge
WHERE $__timeFilter(TimeUnix) AND MetricName = 'container_memory_working_set_bytes'
GROUP BY time, container ORDER BY time"""

TBL_MEM_VS_LIMIT = """SELECT w.container AS container, round(w.mib) AS working_set_mib, round(l.mib) AS limit_mib,
       if(l.mib > 0, round(100 * w.mib / l.mib), NULL) AS pct_of_limit
FROM (SELECT Attributes['container'] AS container, argMax(Value, TimeUnix) / 1048576 AS mib
      FROM otel.otel_metrics_gauge WHERE MetricName = 'container_memory_working_set_bytes' AND TimeUnix > now() - INTERVAL 2 MINUTE
      GROUP BY container) AS w
LEFT JOIN (SELECT Attributes['container'] AS container, argMax(Value, TimeUnix) / 1048576 AS mib
           FROM otel.otel_metrics_gauge WHERE MetricName = 'kube_pod_container_resource_limits' AND Attributes['resource'] = 'memory'
             AND TimeUnix > now() - INTERVAL 2 MINUTE GROUP BY container) AS l USING container
ORDER BY pct_of_limit DESC"""

TBL_RESTARTS = """SELECT Attributes['container'] AS container, Attributes['pod'] AS pod, max(Value) AS restarts
FROM otel.otel_metrics_sum
WHERE $__timeFilter(TimeUnix) AND MetricName = 'kube_pod_container_status_restarts_total'
GROUP BY container, pod HAVING restarts > 0 ORDER BY restarts DESC"""

TS_DEPLOY_AVAIL = """SELECT $__timeInterval(TimeUnix) AS time, Attributes['deployment'] AS deployment, min(Value) AS available
FROM otel.otel_metrics_gauge
WHERE $__timeFilter(TimeUnix) AND MetricName = 'kube_deployment_status_replicas_available'
GROUP BY time, deployment ORDER BY time"""

TBL_EVENTS = """SELECT Timestamp AS time, SeverityText AS type, LogAttributes['k8s.event.reason'] AS reason,
       LogAttributes['k8s.object.name'] AS object, substring(Body, 1, 200) AS message
FROM otel.otel_logs
WHERE $__timeFilter(Timestamp) AND ScopeName LIKE '%k8sevents%'
ORDER BY Timestamp DESC LIMIT 50"""

TS_ERROR_LOGS = """SELECT $__timeInterval(Timestamp) AS time, ServiceName AS service, count() AS error_lines
FROM otel.otel_logs
WHERE $__timeFilter(Timestamp) AND ServiceName != ''
  AND (Body ILIKE '%error%' OR Body ILIKE '%exception%' OR Body ILIKE '%traceback%' OR SeverityText IN ('ERROR', 'error', 'FATAL'))
GROUP BY time, service ORDER BY time"""

TBL_RECENT_ERRORS = """SELECT Timestamp AS time, ServiceName AS service, substring(Body, 1, 240) AS line
FROM otel.otel_logs
WHERE $__timeFilter(Timestamp) AND ServiceName != ''
  AND (Body ILIKE '%error%' OR Body ILIKE '%exception%' OR Body ILIKE '%traceback%')
ORDER BY Timestamp DESC LIMIT 100"""

LOGS_EXPLORER = """SELECT Timestamp AS timestamp, Body AS body, ServiceName AS service, SeverityText AS level
FROM otel.otel_logs
WHERE $__timeFilter(Timestamp) AND ServiceName != ''
ORDER BY Timestamp DESC LIMIT 500"""

TS_RUM = """SELECT $__timeInterval(Timestamp) AS time, SpanName AS what, count() AS events
FROM otel.otel_traces
WHERE $__timeFilter(Timestamp) AND ServiceName = 'martian-bank-ui'
GROUP BY time, what ORDER BY time"""
