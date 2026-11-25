# re:Invent 2026 · booth 1738 · Martian Bank outer loop

**One live problem → found, fixed, shipped, back in policy, and verified.** All three StackGen products appear, and every
hand-off is visible as a record.

- [PRESENTER-SCRIPT.md](PRESENTER-SCRIPT.md): the one-page script (full 7–9 min run, 2-min loop, detours, stall plays)
- [RUNBOOK.md](RUNBOOK.md): what's where, credentials, pre-flight, commands, reset, fallbacks, troubleshooting
- [golden/](golden/): reference outputs (Aiden RCA, InfraOps report, Aiden verify) for comparison and fallback

## The story
Someone `kubectl patch`ed a 200m CPU limit onto `customer-auth`. Git never declared customer-auth's resources, so **Argo CD
still shows Synced** and self-heal never reverts it: the GitOps blind spot. Black Friday load throttles logins to ~15 s.

```
ObserveNow alert ──▶ Incidents (incident) ──ack──▶ Aiden for SRE: root cause (pinned 5-query skill, ~45 s)
        ──▶ Aiden for DevOps: work order (pinned) ──▶ PERSON approves ──▶ InfraOps: drift + policy + PR
        ──▶ DevOps: policy gate + merge ──▶ Argo CD sync ──▶ Aiden for SRE: verify ──▶ work order verified ──▶ incident resolved
```

## Same outcome every run
Every input is pinned: the failure (exactly `limits.cpu=200m`), the load (30 Locust users plus a 3-worker login rush), the
alert threshold (p95 > 4 s), Aiden's evidence queries and report shape, the work-order wording
(`deploy/aiden/workorder.json`, with the pinned copy filed if the agent ever deviates), the policy, and the PR diff. Verify records
its check only on a VERIFIED verdict. `booth reset` restores the exact start state and `booth status` asserts it.
Rehearsal numbers (2026-11-25): alert +2.5 min, RCA 42–46 s identical ×3, work-order draft identical ×3, p95 15 s →
0.2 s with the same load.
