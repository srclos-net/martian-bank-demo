# re:Invent 2026 booth 1738 — "The fix GitOps couldn't see" (DRAFT v2, in-cluster, no AWS)

One live problem in Martian Bank → fixed, shipped, and back in policy, with each StackGen product's hand-off visible.
Everything runs in the `martian-bank` namespace on fe-stackgen-run, so there's no cloud account that could fail at the booth.

## The premise (verified on the live cluster 2026-11-25)

The Martian Bank Helm chart never declares CPU/memory resources. During a past "noisy neighbor" scare, someone
**hot-patched a 200m CPU limit onto `customer-auth` with kubectl**. Because Git never declared that field, **Argo CD still
shows Synced / Healthy**. This was tested live: a patched limit doesn't flip the app OutOfSync, and self-heal never
reverts it. The undeclared change is the **outage** (login CPU-throttled under load), the **drift** (live ≠ Git), and
the **policy violation** (tier-1 services must declare requests/limits in Git) all at once.

Why it's reliable: every step is deterministic. A CPU throttle plus a known Locust load gives the same latency curve
every run. No AWS, no edge DNS, no third-party state.

## Determinism contract: same outcome every run, flexible story

The outcome is fixed. Pacing and narration belong to the presenter.

| Beat | Pinned input | Identical every run |
|------|--------------|---------------------|
| Failure | `booth arm`: exactly `limits.cpu=200m` on customer-auth, nothing else | the root cause, the live object, and a `kubectl-patch` managedFields entry |
| Load | `booth blackfriday`: Locust 30 users, spawn rate 5, the same 5 flow files | the same latency curve (thresholds tuned in rehearsal so the alert always fires within ~60 s) |
| Alert | one alert rule on customer-auth p95 + CPU throttling, fixed threshold and `for:` | fires on every run, never at 3 users |
| SRE (Aiden) | workflow with fixed steps: named PromQL queries, a fixed Git file to compare, a structured output template (cause / evidence / hand-off) | the same root cause, the same 3 evidence lines, the same hand-off |
| InfraOps | `policy/capacity.rego` + `deploy/infraops/capacity-profile.json` | the same drift row, the same 4 CAP findings, and a **byte-identical PR diff** (only the branch timestamp differs) |
| DevOps | conftest v0.56.0, helm v3.16.3, deploy-only guard (no image rebuild) | the same green gate, and only customer-auth rolls |
| Close | Argo syncs the declared 100m/1 CPU | p95 back to baseline, drift 0, policy 0 |
| Reset | `booth reset` → restores the baseline Git block, syncs, re-arms, and `booth status` **asserts** the start state (fails loudly if not exact) | the same start state |

**Live LLM variance:** Aiden's run is constrained (fixed tools and queries, output template, low temperature
where the workspace allows it). `booth check-rca` compares Aiden's answer against the golden one (root cause =
customer-auth CPU limit 200m, not in Git). A **recorded golden run** (screenshots + transcript) is the fallback: if
the live run is slow or off-script, the presenter switches tabs without changing the story.

**Presenter flexibility (doesn't change the outcome):** a short (2 min) or full (5–8 min) cut; optional detours
(open the trace waterfall, show Argo "Synced" while it's broken, show the gate going red on a bad PR variant, ask
Aiden a follow-up question); and talk tracks per audience (SRE lead / platform engineer / exec). All of these are
read-only side trips that never mutate state.

## 5–8 minute script

| # | Time | Product | On screen | Presenter does / says |
|---|------|---------|-----------|------------------------|
| 1 | 0:00–0:45 | — | Booth dashboard (green) + Argo CD showing **Synced / Healthy** + the bank in a browser | "A real bank: 11 microservices, fully GitOps. Argo says everything matches Git. It's Black Friday on Mars." |
| 2 | 0:45–1:30 | — | `booth blackfriday`: Locust 3 → 30 users; login p95 climbs from 0.2 s to seconds; logging in spins in the browser | "Customers are piling in, and logins are crawling. Argo is still green." |
| 3 | 1:30–3:00 | **SRE (Aiden)** | Alert → incident → Aiden investigation | Aiden finds that only customer-auth is slow (spanmetrics); its downstream mongo is fine; the pod is CPU-throttled (cAdvisor throttling metric); and the deployment's managedFields show a `kubectl-patch` manager, not argocd-controller, setting `limits.cpu=200m`. **Root cause: an out-of-band change Git never knew about.** Hand-off → InfraOps. |
| 4 | 3:00–4:15 | **InfraOps** | Drift report (live vs rendered Git) + policy findings | Drift: customer-auth has resources Git doesn't declare. Policy: "tier-1 workloads must declare requests/limits in Git" fails for **all 11 services** (the real chart gap), and "CPU limit ≥ 250m for tier-1" fails live. InfraOps opens the PR "Declare martian-bank capacity in Git": the chart renders `resources` and the values set sane requests/limits. Hand-off → DevOps. |
| 5 | 4:15–5:45 | **DevOps** | PR checks: helm render, **policy gate (Rego/conftest) green** (the same gate is red on `main`), Shipyard preview env, merge → Argo syncs within seconds | "The fix goes through the same pipeline as code, and the policy is checked before it ships. No one touches kubectl." |
| 6 | 5:45–6:45 | **SRE (Aiden)** | Login p95 back to baseline (annotations mark each hand-off), drift = 0, policy compliant; Aiden resolves the incident with a postmortem timeline | "Aiden checks the fix actually worked and writes the postmortem." |
| 7 | 6:45–7:30 | — | Loop slide: Detect → Diagnose → Change → Govern | "Three products, one incident: found, fixed, shipped, and back in policy." |

## 2-minute loop

The same story from a completed run. Dashboard annotations at each hand-off link to the incident + RCA, the drift and
policy report, the PR and pipeline, and the resolved incident. The presenter clicks through 4 tabs, ~30 s each. This also
covers the time while the live run resets.

## Reset (target < 2 min, one command: `booth reset`)

1. Locust back to 3 users.
2. Restore the baseline Git state: a `[booth-reset] [skip ci]` commit returns `deploy/booth/` values to the pre-fix
   state. This is unavoidable: once the fix is in Git, Argo would self-heal away the next hot-patch.
3. Force an Argo refresh, then re-arm: kubectl-patch the 200m limit back onto customer-auth.
4. Resolve/close the demo incident.

## Build list

- `deploy/booth/`: chart `resources` support (a real upstream fix), baseline/fixed values, `booth` script
  (`arm|blackfriday|status|reset`)
- Policy: `policy/*.rego` + conftest job in `ci.yml` (the PR gate); `ci.yml` paths-ignore so deploy-only PRs don't
  rebuild 8 images
- Drift + policy check: a CronJob or Aiden skill that compares live against `helm template` output (namespace-scoped RBAC)
- Aiden: agent `martian-bank-sre`, skills (throttling triage, GitOps-blind-spot drift, postmortem), workflow
  `martian-bank-outer-loop`
- Alert rule (customer-auth p95 / login latency) → incident → Aiden; booth dashboard with hand-off annotations
- `docs/reinvent/PRESENTER-SCRIPT.md` (one page) + `RUNBOOK.md` (pre-flight, reset, fallbacks if Aiden is slow)
