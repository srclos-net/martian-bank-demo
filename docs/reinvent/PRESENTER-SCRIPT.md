# Booth 1738: "The fix GitOps couldn't see" (presenter script, one page)

**Before each run:** `deploy/booth/booth status` prints `READY: exact start state` (if not, run `booth reset`, ~2 min).
**Tabs, left to right:** ① [Booth dashboard (org 6)](https://stephgen-medussa.observe.devopsnow.cloud/d/martian-bank-booth?orgId=6) · ② [Martian Bank](https://bank.stackgen.run) · ③ [Argo CD](https://argocd.stackgen.run/applications/argocd/martian-bank) · ④ [Incidents](https://incidents.stackgen.run) · ⑤ [GitHub PRs](https://github.com/srclos-net/martian-bank-demo/pulls) · ⑥ terminal in `~/src/martian-bank-demo`

## Full run: 7–9 min (what's on screen · what you do · what you say)

| ⏱ | Product | Screen · action | Say (paraphrase freely, the outcome doesn't change) |
|---|---|---|---|
| 0:00 | — | ⑥ `booth blackfriday`, then ② log in (booth-visitor@martian.bank / reinvent-1738) | "Martian Bank: 11 microservices on Kubernetes, all GitOps. It's Black Friday on Mars and everyone's logging in." |
| 0:30 | — | ③ Argo CD: **Synced / Healthy** | "Git and the cluster agree, or so Argo says. Remember this green." |
| 1:00 | — | ① login p95 climbs past the red 4 s line; ② login spins ~15 s | "Customers are waiting 15 seconds to log in. Argo is still green." |
| ~2:30 | **SRE** | ④ alert group *"customer logins slow"* appears → **Declare incident** (SEV2) → **Acknowledge** (or ⑥ `booth declare`) | "The alert pages. Acknowledging hands the incident to Aiden for SRE." |
| ~3:15 | **SRE** | ④ Investigation panel fills in (~45 s): ROOT CAUSE · 4 EVIDENCE lines · HAND-OFF → InfraOps | "Only customer-auth is slow; it's 95 % CPU-throttled by a 200 m limit, and that limit has no memory limit next to it. Git never declared it: someone ran kubectl. That's why Argo can't see it." |
| ~4:00 | **DevOps** | ⑥ `booth handoff` → ④ **WO-n** appears: *"Declare customer-auth capacity in Git"*, risk normal, 4 steps, proposed by **Aiden for DevOps** | "Aiden for DevOps turns the diagnosis into a work order: look, act, act, check. Proposed, not done, because a service can't approve its own change." |
| ~4:30 | **Governance** | ④ you click **Approve** on WO-n | "A person approves. That's the control." |
| ~4:45 | **InfraOps** | ⑥ `booth infraops` (~40 s) → ④ steps 1–2 ✓ (formatted drift + policy report, PR link) → ⑤ PR *"InfraOps: declare customer-auth capacity in Git"* (1-line diff) | "InfraOps compares every live field against Git, not just the ones Git declares. One drift, four policy violations. It opens the PR that puts the capacity in Git, and it wouldn't do that before the approval." |
| ~5:45 | **DevOps** | ⑤ policy gate (capacity CAP-001/2/3) green → **Squash and merge** → ⑥ `booth sync` → ④ step 3 ✓ | "The fix ships like code: policy-checked, merged, applied by Argo. Nobody touched the cluster." |
| ~6:30 | — | ② log in again: **< 1 s**; ① p95 drops under the line | "Same Black Friday load, logins back under a second." |
| ~7:30 | **SRE** | ⑥ `booth verify` (waits for clean numbers, ~1–2 min, then ~35 s) → ④ step 4 ✓ **VERIFIED** → WO verified → incident **monitoring → resolved** when the alert clears | "Aiden checks its own fix before anyone closes anything. Detect, diagnose, change, govern, verify: the outer loop, three products, one incident." |
| after | — | ⑥ `booth reset` (~2 min, while you talk to the visitor) | — |

## Short loop: 2 min (no live changes)
Leave a completed run on screen (don't reset). Click through: ① the dashboard's spike and recovery → ④ the incident: the Aiden RCA,
then the work order with all 4 steps ✓ and its links → ⑤ the merged PR (1 line) → ③ Argo Synced. ~30 s each.
"Alert → Aiden root cause → work order → human approval → InfraOps PR → policy gate → Argo → Aiden verifies."

## Optional detours (read-only, any time, outcome unchanged)
- ③ Argo shows Synced while broken: **the GitOps blind spot** (best for platform engineers).
- ④ "Ask Aiden" a follow-up: *"Why didn't Argo CD revert this?"*
- ⑤ The policy file `policy/capacity.rego`: three rules, the same gate in CI and on the live cluster.
- ① The throttling panel: 95 % → ~0 % after the fix.

## If something stalls (keep talking, use the fallback, never improvise a cluster change)
- The alert is slow (> 3 min): ⑥ `booth declare` works as soon as the alert group exists; talk over the dashboard meanwhile.
- The Aiden RCA is slow (> 2 min) or off-script: switch to the recorded run (RUNBOOK § Fallbacks); the outcome is the same.
- The policy gate doesn't show (Actions off): merge anyway and say "the gate runs on every PR". Show `policy/capacity.rego`.
- `booth verify` says "waiting for the fixed pod's numbers": that's expected for 1–2 min. Show ② logging in fast meanwhile.
