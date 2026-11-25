---
name: martian-bank-booth-verify
description: Verify the Martian Bank login fix after the InfraOps PR shipped. Three fixed ClickHouse queries plus the firing-alert check, and a fixed VERIFIED / NOT VERIFIED verdict.
---

# Verify the customer-auth capacity fix

Run these queries with `observability_query` (datasource uid `clickhouse`, database `otel`), in order and
unchanged. No other tools except `list_firing_alerts`.

**V1: login p95 (s), last minute**
```sql
SELECT round(quantile(0.95)(Duration) / 1e9, 2) AS login_p95_s
FROM otel.otel_traces
WHERE ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server'
  AND Timestamp > now() - INTERVAL 1 MINUTE
```

**V2: customer-auth throttling %, last minute**
```sql
SELECT round(100 * sumIf(d, m = 'container_cpu_cfs_throttled_periods_total')
                       / nullIf(sumIf(d, m = 'container_cpu_cfs_periods_total'), 0), 1) AS throttled_pct
FROM (SELECT MetricName AS m, Attributes['id'] AS id, max(Value) - min(Value) AS d
      FROM otel.otel_metrics_sum
      WHERE MetricName IN ('container_cpu_cfs_throttled_periods_total', 'container_cpu_cfs_periods_total')
        AND Attributes['container'] = 'customer-auth' AND TimeUnix > now() - INTERVAL 1 MINUTE
      GROUP BY m, id)
```

**V3: customer-auth CPU limit (cores) and memory limit (MiB)**
```sql
SELECT maxIf(v, resource = 'cpu') AS cpu_limit_cores,
       maxIf(v, resource = 'memory') / 1048576 AS memory_limit_mib
FROM (SELECT Attributes['resource'] AS resource, argMax(Value, TimeUnix) AS v
      FROM otel.otel_metrics_gauge
      WHERE MetricName = 'kube_pod_container_resource_limits' AND Attributes['container'] = 'customer-auth'
        AND TimeUnix > now() - INTERVAL 1 MINUTE
      GROUP BY resource)
```

**V4: is the alert still firing?** Use `list_firing_alerts` and look for "Martian Bank: customer logins slow".

## Verdict rules

VERIFIED only if all of these hold: V1 < 1.5 s, V2 < 25 %, the CPU limit is ≥ 0.25 core AND the memory limit is
above 0 (capacity now comes from Git), and the alert isn't firing. Otherwise NOT VERIFIED, saying which check failed.
If V1 has no data yet, say "wait 60 s and re-run".

## Report: exactly this shape

```
VERDICT: VERIFIED | NOT VERIFIED
- Login p95: <V1> s (was above 4 s during the incident)
- Throttling: <V2> %
- customer-auth capacity: CPU limit <V3 cpu> core, memory limit <V3 memory> MiB (declared in Git, owned by Argo CD)
- Alert: <resolved | still firing>
NEXT: <"Resolve the incident; postmortem: out-of-band CPU limit invisible to GitOps → now declared in Git and enforced by the capacity policy gate." | what to wait for>
```
