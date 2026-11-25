---
name: martian-bank-booth-workorder
description: Turn the Martian Bank login-latency root cause (an out-of-band CPU limit on customer-auth) into the fixed work-order draft for StackGen Incidents. Answer with JSON only.
---

# Work order for the customer-auth capacity drift

Use this whenever you're asked to draft or propose the fix for a Martian Bank incident about slow logins,
customer-auth CPU throttling, or an out-of-band CPU limit. Don't call any tools: the root cause is already
established by Aiden for SRE, and the change is always the same governed change below.

Answer with **exactly this JSON and nothing else** (no prose, no code fence). Keep the wording identical, because
the booth audience compares it run to run:

{"title": "Declare customer-auth capacity in Git (replace the out-of-band 200m CPU limit)", "description": "Aiden for SRE: customer-auth is CPU-throttled by a 200m CPU limit set with kubectl, outside Git; Argo CD still shows Synced because Git never declared customer-auth's resources. Fix it the governed way: InfraOps declares the capacity in Git (requests 100m CPU / 128Mi, limits 1 CPU / 384Mi), the capacity policy gate (CAP-001/002/003) checks the PR, and Argo CD applies it, replacing the out-of-band limit. No hand edits to the cluster. Rollback: revert the PR.", "risk": "normal", "steps": [{"kind": "look", "text": "InfraOps: read the drift and policy report for customer-auth (live CPU limit 200m set by kubectl-patch, not in Git; CAP-001/002/003)."}, {"kind": "act", "text": "InfraOps: open the reconcile PR declaring customer-auth capacity in Git (requests 100m/128Mi, limits 1 CPU/384Mi)."}, {"kind": "act", "text": "DevOps: merge the PR after the capacity policy gate passes; Argo CD syncs customer-auth from Git."}, {"kind": "check", "text": "Aiden for SRE: login p95 under 1.5 s, CPU throttling under 25 %, customer-auth capacity owned by Git, login alert resolved."}]}
