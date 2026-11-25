#!/usr/bin/env python3
"""Generate the booth's Aiden SKILL.md files from deploy/o11y/org6/queries.py (single source of SQL truth).
Run after editing queries.py, then ./apply.sh."""
import importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("q", os.path.join(HERE, "..", "o11y", "org6", "queries.py"))
Q = importlib.util.module_from_spec(spec); spec.loader.exec_module(Q)
fence = lambda sql: "```sql\n" + sql.strip() + "\n```"
VERIFY_THROTTLE = Q.THROTTLE_PCT_2M.replace("INTERVAL 2 MINUTE", "INTERVAL 1 MINUTE")

RCA = f"""---
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
{fence(Q.LOGIN_P95_1M)}

**Q2: is it only customer-auth?** Server p95 per service, last 2 min
{fence(Q.SERVICE_P95_2M)}

**Q3: saturation.** customer-auth CPU throttling, as a % of CFS periods
{fence(Q.THROTTLE_PCT_2M)}

**Q4: the live limits.** CPU limit (cores) and memory limit (MiB) per container; 0 means "not set"
{fence(Q.LIVE_LIMITS)}

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
"""

VERIFY = f"""---
name: martian-bank-booth-verify
description: Verify the Martian Bank login fix after the InfraOps PR shipped. Three fixed ClickHouse queries plus the firing-alert check, and a fixed VERIFIED / NOT VERIFIED verdict.
---

# Verify the customer-auth capacity fix

Run these queries with `observability_query` (datasource uid `clickhouse`, database `otel`), in order and
unchanged. No other tools except `list_firing_alerts`.

**V1: login p95 (s), last minute**
{fence(Q.LOGIN_P95_1M)}

**V2: customer-auth throttling %, last minute**
{fence(VERIFY_THROTTLE)}

**V3: customer-auth CPU limit (cores) and memory limit (MiB)**
{fence(Q.CUSTOMER_AUTH_LIMITS)}

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
"""

open(os.path.join(HERE, "skills", "martian-bank-booth-rca", "SKILL.md"), "w").write(RCA)
open(os.path.join(HERE, "skills", "martian-bank-booth-verify", "SKILL.md"), "w").write(VERIFY)
print("wrote rca + verify skills from queries.py")
