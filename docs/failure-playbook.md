# Martian Bank Failure Playbook

Runtime knobs for demo failure scenarios. **None of these require a deploy** —
they are live flips on the cluster (Argo CD self-heal will not fight them:
they patch fields Argo CD doesn't own, or state Argo CD doesn't manage).
Restore commands are listed with every knob.

Context: https://bank.stackgen.run · virtual users: 3 via Locust
(https://locust.stackgen.run, **Google SSO via the shared oauth2-proxy** —
sign-in lives at otel-demo.stackgen.run, session cookie covers *.stackgen.run)
· cluster: fe-stackgen-run (Civo k3s), namespace `martian-bank` ·
kubectl: use `/opt/homebrew/bin/kubectl` (the plain `kubectl` on the Mac is
broken).

Quick shorthand for all commands:

```sh
K="kubectl --context fe-stackgen-run -n martian-bank"
```

> **SSO note:** the locust host is gated by the shared oauth2-proxy. In a
> browser just click through Google sign-in. For raw `curl` use ONE of:
> (a) a port-forward bypassing the gate:
> `kubectl --context fe-stackgen-run port-forward -n martian-bank svc/locust 8098:8098`
> and hit `http://localhost:8098` instead of the public host, or (b) copy the
> `_oauth2_proxy` cookie from your browser's devtools and pass
> `-H "Cookie: _oauth2_proxy=<value>"`.

---

## Knob 1 — The customer dial (Locust)

**Blast radius:** request volume everywhere · **Signals:** spanmetrics
request/latency growth, OBI service-graph edges warm up, no errors by itself.

- **Browser**: open https://locust.stackgen.run → set users + spawn rate → Start.
- **API** (same thing the button does; see SSO note above for cookie/forward):

  ```sh
  curl -s -X POST http://localhost:8098/swarm -H 'Content-Type: application/json' -d '{"user_count": 30, "spawn_rate": 2}'
  ```

- **Stop the storm**: `curl -s -X POST http://localhost:8098/stop`
- **Peek at RPS/errors**: `curl -s http://localhost:8098/stats/requests | python3 -m json.tool | head -40`

Black Friday arc: 3 → 10 (rumbling) → 30 (the run) → 30 + Knob 2/3 (the crash).

---

## Knob 2 — Edge latency injection ("everything is spinning") — CERTIFIED

Latency = a tiny `bank-delayer` sleep service reached via the `bank-latency`
forwardAuth middleware. **Verified end-to-end 2026-11-16:** base 0.42s →
2.44s at `DELAY_MS=2000` → back to 0.42s at 0.

```sh
# attach (adds the delay dial to every bank request)
$K patch ingress martian-bank --type merge \
  -p '{"metadata":{"annotations":{"traefik.ingress.kubernetes.io/router.middlewares":"martian-bank-bank-latency@kubernetescrd"}}}'
# dial the pain live (each patch rolls ONE pod; wait ~30s to settle)
$K patch deploy bank-delayer -p '{"spec":{"template":{"spec":{"containers":[{"name":"delayer","env":[{"name":"DELAY_MS","value":"2000"}]}]}}}}'
# restore
$K patch deploy bank-delayer -p '{"spec":{"template":{"spec":{"containers":[{"name":"delayer","env":[{"name":"DELAY_MS","value":"0"}]}]}}}}'
$K patch ingress martian-bank --type merge \
  -p '{"metadata":{"annotations":{"traefik.ingress.kubernetes.io/router.middlewares":null}}}'
```

Operational truths baked in:

- **Argo self-heal ignores this knob by design** (`ignoreDifferences` in
  `deploy/argocd.yaml` covers the ingress middleware annotation and the
  delayer's env). Runtime patches survive; both dial mechanisms stay live
  until you set them back.
- traefik 2.9.4 has **no delay middleware** (binary, not CRD): the
  forwardAuth-delayer pattern is the substitute. If traefik is ever
  upgraded ≥2.10, a native `delay` middleware could replace this.
- The forwardAuth address is a **pinned ClusterIP** (10.43.124.255) because
  traefik's hostNetwork pods resolve in-cluster service DNS unreliably —
  same reason `kube-civo-auth` pins one. If the Service is recreated,
  re-read `kubectl get svc bank-delayer -o jsonpath='{.spec.clusterIP}'`
  and update the middleware (via git: `deploy/manifests/bank-latency.yaml`).
- Mid-dial measurements race pod rolls (old pods terminating keep serving
  briefly) — wait ~30s after `DELAY_MS` patches before judging numbers.

---

## Knob 3 — Edge rate limiting ("429 storm")

**Blast radius:** >5 req/s average (bursts of 10) get 429 at the edge; upstream
never sees the excess. **Signals:** 429 rate spike at edge spans; Locust
failure counts jump; RUM sees failed navigation/API calls.

```sh
# attach
$K patch ingress martian-bank --type merge \
  -p '{"metadata":{"annotations":{"traefik.ingress.kubernetes.io/router.middlewares":"martian-bank-bank-ratelimit@kubernetescrd"}}}'
# detach (restore)
$K patch ingress martian-bank --type merge \
  -p '{"metadata":{"annotations":{"traefik.ingress.kubernetes.io/router.middlewares":null}}}'
```

Dial: `kubectl edit middleware bank-ratelimit` — `average`/`burst`. Both this
and Knob 2 can be attached together:
`"martian-bank-bank-ratelimit@kubernetescrd, martian-bank-bank-delay@kubernetescrd"`.

---

## Knob 4 — The shared bottleneck falls over (MongoDB)

**Blast radius:** everything dies — the Node services (customer-auth,
atm-locator) **exit at boot if mongo is unreachable**, so they go into
boot-loop reconnect storms; Flask services log errors on their existing
requests. This is the cascade. **Signals:** mass error spans, service-graph
edges erroring, restart counts, spanmetrics error-rate alert (if wired),
customer pain everywhere (Faro).

```sh
# the event (mongo auto-restarts in ~10-30s; the cascade ends by itself)
$K delete pod -l app=mongodb
```

This knob self-restores. To *stretch* it: watch how long customer-auth stays
down (its restarts re-storm mongo on boot).

---

## Knob 5 — Login flood ("auth is the first domino")

**Blast radius:** customer-auth + mongo connection/CPU spike; legitimate
logins slow/fail. **Signals:** auth spans pile up, mongo connections climb,
5xx on /api/users.

```sh
for i in $(seq 1 200); do
  curl -s -o /dev/null -X POST https://bank.stackgen.run/api/users/auth \
    -H 'Content-Type: application/json' \
    -d '{"email":"storm@example.com","password":"bad'$i'"}' &
done; wait
```

No restore needed (it's just traffic). Combine with Knob 1 for the
"everyone on the site at once" feeling.

---

## Knob 6 — A service dies (single-point failure demo)

**Blast radius:** what nginx can't reach → 502s. Kill anything:

```sh
$K delete pod -l app=dashboard        # transfers/loans dead, auth still works
$K delete pod -l app=nginx            # whole front door down (ui keeps running)
```

Auto-restores when the replacement pod is Ready (~10-30s).

---

## Knob 7 — Load shedding at the edge (circuit breaker)

Passive: `bank-circuitbreaker` trips by itself under the storms of Knobs 1-3
once 30% of edge connections error or the 50th percentile latency exceeds
1.5s. Attach late in a demo for the satisfying "the bank protected itself"
narrative:

```sh
$K patch ingress martian-bank --type merge \
  -p '{"metadata":{"annotations":{"traefik.ingress.kubernetes.io/router.middlewares":"martian-bank-bank-circuitbreaker@kubernetescrd"}}}'
```

---

## The Black Friday arc (putting it together)

| T+ | Action | Where signals land |
|----|--------|--------------------|
| 0 min | baseline: 3 virtual users | normal spanmetrics + RUM |
| +1 min | Knob 1 → users 30 | requests/latency graphs lift off |
| +3 min | Knob 2 attach (2s delay) | Faro LCP degrade, user-side errors |
| +5 min | Knob 4 (`delete pod -l app=mongodb`) | cascade: boot-loops, mass errors |
| +7 min | (optional) Knob 5 storm | auth/connection storm deepens |
| +8 min | declare in incidents.stackgen.run (or let the alert do it) | escalation chain → page → Aiden investigates |
| +9 min | Knob 1 back to 3, detach Knob 2, mongo self-heals | recovery; Aiden drafts postmortem |

## Expected end-to-end telemetry paths (already live)

- **Backend:** OBI eBPF spans → devopsnow otel-collector (spanmetrics) →
  vmagent/zipkin → stephgen-medussa (ObserveNow).
- **Frontend:** Faro SDK in the ui → faro.stackgen.run → relay → ObserveNow
  (traces + logs; web vitals as measurements).
- **Alerts → pages:** ObserveNow contact point "fe-stackgen-run -> Aiden" →
  StackGen Incidents integration "fe-stackgen-run (ObserveNow)" → chain
  "fe-stackgen-run default" (notify Stephanie → wait 15 → repeat).

## Notes

- These knobs patch Ingress annotations, the locust swarm API, or pods.
  Argo CD self-heal watches **spec** of chart-managed resources; the
  middleware annotation is NOT in the managed spec (safe to flip), but
  avoid `kubectl edit deploy/*` — that would be reverted on the next sync.
- Locust UI: the 3 user baseline restarts on a pod restart (the run resets).
  After a pod churn, re-swarm or note the UI shows 0 users.
