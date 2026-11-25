<!-- Aiden for SRE verify, under the same Black Friday load after the fix shipped, 2026-11-25, 36 s. -->
VERDICT: VERIFIED
- Login p95: 0.195 s (was above 4 s during the incident)
- Throttling: 0.583 %
- customer-auth capacity: CPU limit 1 core, memory limit 384 MiB (declared in Git, owned by Argo CD)
- Alert: resolved
NEXT: Resolve the incident; postmortem: out-of-band CPU limit invisible to GitOps → now declared in Git and enforced by the capacity policy gate.
