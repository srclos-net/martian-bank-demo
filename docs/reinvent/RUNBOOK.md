# re:Invent booth runbook: Martian Bank outer loop

The presenter script is [PRESENTER-SCRIPT.md](PRESENTER-SCRIPT.md). This page covers setup, pre-flight, how each piece
works, reset, fallbacks and troubleshooting. All commands run from the repo root with `deploy/booth/booth <cmd>`.

## What's where

| Piece | Lives in | Notes |
|---|---|---|
| Martian Bank | ns `martian-bank`, cluster `fe-stackgen-run` (Civo), Argo app `martian-bank` | auto-sync + self-heal from `main` |
| The failure | `booth arm`: `kubectl patch` sets `customer-auth` `limits.cpu=200m` | Git never declares customer-auth resources, so Argo stays **Synced** |
| Load | Locust (30 users) + `deploy/booth/login-rush.yaml` (3 real-login workers) | pinned: p95 ~15 s armed, ~0.2–0.5 s fixed |
| Alert | ObserveNow org 1 rule `martian-bank-login-slow` (p95 > 4 s, 20 s eval, 30 s pending) → contact point → Incidents integration 4 | as code: `deploy/observability/booth-alert-rule.yaml` |
| Dashboard | ObserveNow org 6 "AWS re:Invent", uid `martian-bank-booth` (copy in org 1) | `deploy/observability/booth-dashboard.json` |
| Incidents | https://incidents.stackgen.run, 0.24.26 | its Aiden connection → `martian-bank-sre`; work orders render markdown |
| Aiden | stage.dev workspace `reinvent-booth` (f2a4ba74…) | agents `martian-bank-sre`, `martian-bank-devops`; skills; workflow `martian-bank-verify`; `deploy/aiden/apply.sh` |
| InfraOps | `deploy/infraops/scan.py` → suspended CronJob `infraops-scan` (via Git: `deploy/manifests/infraops-scan.yaml`) | drift (all live fields vs rendered Git) + `policy/capacity.rego` + PR; waits for work-order approval |
| Policy gate | `.github/workflows/ci.yml` job "policy gate (capacity)" (conftest) | **Actions is currently off on the repo**: see Known gaps |
| Glue | `deploy/booth/booth` + `deploy/booth/handoff.py` | Incidents ↔ Aiden ↔ InfraOps |

## Credentials (booth laptop)
| File / Secret | What | Created by |
|---|---|---|
| `~/.kube/config` context `fe-stackgen-run` | cluster access | existing |
| `~/.config/aiden/reinvent-booth.key` | Aiden API key, workspace reinvent-booth | Stephanie |
| `~/.config/aiden/reinvent-onow-viewer.key` / `-admin.key` | ObserveNow org 6 service accounts | Stephanie |
| `~/.config/aiden/reinvent-github.key` → Secret `martian-bank/infraops-github` | fine-grained PAT, this repo only (contents + PRs), expires after re:Invent | Stephanie |
| Secret `martian-bank/incidents-booth` (url, token) | Incidents service token `booth-aiden` | created 2026-11-25 |
| `incidents-keys.AIDEN_TOKEN` | the booth Aiden key, for Incidents' direct connection | created 2026-11-25 |
All of these are logged in #community-devops (CISO rule). Revoke after the event: the PAT, `booth-aiden` (Incidents → Settings → API tokens), and the Aiden and ObserveNow keys.

## Pre-flight (start of each booth day, ~5 min)
1. `deploy/booth/booth status`: all ✓ and `READY: exact start state`. If not: `booth reset`.
2. Aiden is healthy: `python3 deploy/booth/handoff.py status` returns (Incidents reachable), and one dry RCA (below) answers within ~60 s.
3. Dashboard ① loads in org 6; login p95 is flat under 4 s; Argo ③ shows Synced/Healthy.
4. Sign in to Incidents ④ (Google, @stackgen.com) and GitHub ⑤ (an account that can merge to srclos-net/martian-bank-demo).
5. Optional dry RCA without an incident: `booth blackfriday`, wait 90 s, then in Aiden chat (stage.dev → reinvent-booth
   → martian-bank-sre) ask *"Investigate slow Martian Bank logins"*. Compare with `golden/rca.md`. Then `booth reset`.

## The run, command by command
| Step | Command / click | What it does | Typical time |
|---|---|---|---|
| Incident | `booth blackfriday` | Locust 3→30 users + login rush Job | alert fires ~2.5 min later |
| SRE | Incidents: Declare incident + Acknowledge, **or** `booth declare` | incident SEV2 from the alert group; starts `martian-bank-sre` | RCA ~45 s |
| DevOps | `booth handoff` | `martian-bank-devops` drafts the work order; filed as "Aiden for DevOps" (status proposed). If the draft ever deviates from `deploy/aiden/workorder.json`, the pinned copy is filed and the script says so | ~10 s |
| Governance | Incidents: **Approve** WO-n | a person approves (a service never can; the approver must not be the requester, and the requester here is the service) | — |
| InfraOps | `booth infraops` | scan + policy; refuses a PR while the WO is only proposed; then opens the PR and records steps 1 (report) and 2 (PR) | ~40 s |
| DevOps | GitHub: merge the PR, then `booth sync` | Argo refresh, wait for Synced at the merge commit, customer-auth rolls; records step 3 | ~30–60 s |
| Verify | `booth verify` | pre-checks p95 < 1.5 s and throttling < 25 % (1-minute windows), then `martian-bank-sre` verifies; records step 4 **only** on VERIFIED → WO verified → incident monitoring → resolved once the alert group clears | 1–2 min wait + ~35 s |
| Reset | `booth reset` | calm; cancel a still-proposed WO; resolve booth incidents; close infraops PRs and delete their branches; `[booth-reset] [skip ci]` commit restoring the baseline Git block; Argo sync; re-arm; assert | ~2 min |

`booth wo` shows the open booth incident and work order at any time. `booth login` times 3 real logins.

## Fallbacks (same outcome, no improvising)
- **Aiden is slow or off-script:** show `docs/reinvent/golden/rca.md`, the same report shape and numbers within ±1 s. Keep
  the flow: `booth handoff` doesn't depend on the RCA text (the work order is pinned).
- **Aiden is down entirely:** run the short loop on the last completed incident (keep one resolved booth incident and its
  WO as the "recorded run"; don't reset it away: resolved incidents stay browsable).
- **InfraOps job fails:** `kubectl -n martian-bank logs job/<latest infraops-…> -c scan`. The PR can be opened by hand
  from `golden/infraops-report.md` + the one-line diff (add the `customer-auth:` line between the booth markers in
  `deploy/values-civo.yaml`).
- **Verify never passes:** check that customer-auth actually rolled (`kubectl -n martian-bank get deploy customer-auth -o
  jsonpath='{..resources}'` shows 1 CPU / 384Mi). If it did, wait one more minute (span lag); `booth verify` re-runs safely.
- **A WO got approved but the run was abandoned:** only a person can cancel an approved WO. Cancel it in Incidents, then
  `booth reset`.

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| `booth status` ✗ CPU limit not 200m | Argo self-heal after a Git change, or reset didn't re-arm | `booth reset` |
| ✗ Git capacity block not 2 lines | the PR was merged and not reset | `booth reset` (pushes the baseline commit) |
| The arm or reset shows 502s for ~30 s | customer-auth boots slowly at 200m (no readiness probe) | the script waits for real logins; just wait |
| An infraops change doesn't take effect | `deploy/manifests` is an Argo source: direct applies get self-healed | change `deploy/infraops/*`, run `python3 deploy/infraops/gen-manifest.py`, commit, push |
| Incidents shows the WO steps as raw text | Incidents < 0.24.26 | deploy 0.24.26+ (stackgen-incidents repo, civo overlay) |
| `handoff.py`: "Secret … not readable" | kube context | `kubectl config use-context fe-stackgen-run` |

## Known gaps (as of 2026-11-25)
- **GitHub Actions is not running** on srclos-net/martian-bank-demo (no runs since 606cb85), so the policy gate doesn't
  show on PRs. Re-enable it in org/repo Settings → Actions. The gate itself was checked locally with conftest (red on
  baseline for customer-auth only, green on the fix).
- The stackgen-incidents `work-orders` branch (0.24.25/0.24.26 commits) is local only: appcd-dev access for srclosson
  returns 404.
- Org 6's datasource reads the whole stephgen-medussa VM tenant (no per-org filter). Fine for Aiden's read-only key; a
  separate VictoriaMetrics tenant is the post-event option.
- Remaining build items: `booth check-rca` (auto-compare against golden) and one clean end-to-end rehearsal with the
  final script.
