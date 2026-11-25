<!-- Aiden for SRE (martian-bank-sre), live on INC-0050, 2026-11-25T20:32Z, 46 s, $0.07. Every rehearsal so far matches this shape. -->
ROOT CAUSE
customer-auth is CPU-throttled by a 200m CPU limit that was set outside Git (no memory limit alongside it, so not from the chart). Argo CD still reports Synced.

EVIDENCE
1. Customer impact: login p95 14.9 s (SLO 4 s).
2. Blast radius: only customer-auth is slow; dashboard, accounts, transactions, loan and atm-locator are all under 0.2 s.
3. Saturation: customer-auth throttled 95 % of CPU periods.
4. Out-of-band config: customer-auth has CPU limit 200m but no memory limit; every other container has both, as declared in Git (Q4/Q5).

IMPACT
Customers wait 14.9 s to log in. Transfers, loans and accounts still work for already-signed-in customers.

HAND-OFF → InfraOps
Reconcile customer-auth capacity into Git: drift (live limit not in Git) + capacity policy CAP-001/002/003. Don't hand-edit the cluster again: the fix ships as a PR through the policy gate.
