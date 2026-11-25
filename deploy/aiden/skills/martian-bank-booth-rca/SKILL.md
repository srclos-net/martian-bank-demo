---
name: martian-bank-booth-rca
description: Root-cause slow Martian Bank logins (customer-auth) with four fixed ClickHouse queries and a fixed report shape, then hand off to InfraOps. Use for any Martian Bank login-latency alert or incident.
---

# Martian Bank login latency: root cause in four queries

Martian Bank's telemetry lives in its own ClickHouse (ObserveNow org 6, datasource uid `clickhouse`, database
`otel`): spans in `otel_traces`, scraped Kubernetes metrics in `otel_metrics_gauge` / `otel_metrics_sum`, pod
logs in `otel_logs`. Run these four SQL queries with `observability_query` against datasource uid
`clickhouse`, in this order, exactly as written. Don't improvise other queries, don't list dashboards, and don't
run shell commands. Missing data is a finding: say so in the line instead of guessing.

**Q1: customer impact.** Login p95 in seconds (SLO: 4 s)
```sql
SELECT round(quantile(0.95)(Duration) / 1e9, 2) AS login_p95_s
FROM otel.otel_traces
WHERE ServiceName = 'customer-auth' AND SpanName = 'POST /api/users/auth' AND SpanKind = 'Server'
  AND Timestamp > now() - INTERVAL 1 MINUTE
```

**Q2: is it only customer-auth?** Server p95 per service, last 2 min
```sql
SELECT ServiceName AS service, round(quantile(0.95)(Duration) / 1e9, 3) AS p95_s, count() AS requests
FROM otel.otel_traces
WHERE SpanKind = 'Server' AND Timestamp > now() - INTERVAL 2 MINUTE
  AND ServiceName IN ('customer-auth', 'dashboard', 'accounts', 'transactions', 'loan', 'atm-locator')
GROUP BY service ORDER BY p95_s DESC
```

**Q3: saturation.** customer-auth CPU throttling, as a % of CFS periods
```sql
SELECT round(100 * sumIf(d, m = 'container_cpu_cfs_throttled_periods_total')
                       / nullIf(sumIf(d, m = 'container_cpu_cfs_periods_total'), 0), 1) AS throttled_pct
FROM (SELECT MetricName AS m, Attributes['id'] AS id, max(Value) - min(Value) AS d
      FROM otel.otel_metrics_sum
      WHERE MetricName IN ('container_cpu_cfs_throttled_periods_total', 'container_cpu_cfs_periods_total')
        AND Attributes['container'] = 'customer-auth' AND TimeUnix > now() - INTERVAL 2 MINUTE
      GROUP BY m, id)
```

**Q4: the live limits.** CPU limit (cores) and memory limit (MiB) per container; 0 means "not set"
```sql
SELECT container,
       maxIf(v, resource = 'cpu') AS cpu_limit_cores,
       maxIf(v, resource = 'memory') / 1048576 AS memory_limit_mib
FROM (SELECT Attributes['container'] AS container, Attributes['resource'] AS resource,
             argMax(Value, TimeUnix) AS v, argMax(Attributes['pod'], TimeUnix) AS pod
      FROM otel.otel_metrics_gauge
      WHERE MetricName = 'kube_pod_container_resource_limits' AND TimeUnix > now() - INTERVAL 2 MINUTE
      GROUP BY container, resource, Attributes['pod'])
GROUP BY container ORDER BY container
```

## How to read them (Martian Bank facts)

- The Martian Bank Helm chart declares capacity in Git (`deploy/values-civo.yaml`, key `capacity`), and Argo CD
  applies it. **Git-declared containers always have a CPU limit AND a memory limit.**
- A container with a CPU limit but **memory_limit_mib = 0** (no memory limit) didn't get its limit from Git.
  Someone set it out of band (`kubectl patch`/`edit`). Argo CD can't see this: it only compares the fields Git
  declares, so the app still shows **Synced / Healthy**.
- Login does a bcrypt password check, which is CPU-bound. A CPU limit below ~250m (0.25 cores) throttles it under
  normal load.
- Healthy reference values: login p95 under 1 s, throttling under 10 %, every other service's p95 under 0.2 s.
- Other Martian Bank alerts may be firing at the same time (stack traces in logs, CPU throttling, "container without a
  memory limit"). Those are symptoms of the same root cause or unrelated background noise; this report is about the
  customer-facing login latency.

## Report: use exactly this shape

```
ROOT CAUSE
customer-auth is CPU-throttled by a <Q4 cpu_limit_cores in m, e.g. 200m> CPU limit that was set outside Git (no memory limit alongside it, so not from the chart). Argo CD still reports Synced.

EVIDENCE
1. Customer impact: login p95 <Q1> s (SLO 4 s).
2. Blast radius: only customer-auth is slow; <name the other services from Q2 and say they are under 0.2 s>.
3. Saturation: customer-auth throttled <Q3> % of CPU periods.
4. Out-of-band config: customer-auth has CPU limit <Q4> but no memory limit; every other container has both, as declared in Git (Q4).

IMPACT
Customers wait <Q1> s to log in. Transfers, loans and accounts still work for already-signed-in customers.

HAND-OFF → InfraOps
Reconcile customer-auth capacity into Git: drift (live limit not in Git) + capacity policy CAP-001/002/003. Don't hand-edit the cluster again: the fix ships as a PR through the policy gate.
```

Round seconds to 1 decimal and percentages to whole numbers. Don't propose restarting, scaling or `kubectl`
changes. The product answer is the InfraOps hand-off.
