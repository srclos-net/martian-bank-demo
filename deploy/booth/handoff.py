#!/usr/bin/env python3
"""Booth glue between StackGen Incidents and the Aiden agents (docs/reinvent/).

  handoff.py declare            firing "logins slow" alert group -> incident (SEV2) -> Aiden for SRE investigates
  handoff.py rca [INC]          wait for Aiden for SRE's root cause on the incident and print it
  handoff.py handoff [INC]      Aiden for DevOps drafts the work order; filed in Incidents as a service
                                ("Aiden for DevOps") for a PERSON to approve
  handoff.py wo                 print the open booth work order ref (or nothing)
  handoff.py step N "did" [--result R] [--ok true|false]   record a step on the open booth work order
  handoff.py verify             Aiden for SRE verifies; records the check step (passed / failed)
  handoff.py cleanup            reset: cancel the booth work order if still only proposed, resolve booth incidents
  handoff.py status             one line per open booth incident / work order

Credentials: the Incidents service token "booth-aiden" is read from Secret martian-bank/incidents-booth via
kubectl (never printed); the Aiden key from ~/.config/aiden/reinvent-booth.key.
Determinism: the work order Aiden drafts is compared with deploy/aiden/workorder.json; if the draft ever
deviates, the pinned copy is filed instead (and the script says so).
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = os.environ.get("BOOTH_CONTEXT", "fe-stackgen-run")
KUBECTL = os.environ.get("KUBECTL", "/opt/homebrew/bin/kubectl")
INC_URL = os.environ.get("INCIDENTS_URL", "https://incidents.stackgen.run")
AIDEN = os.environ.get("AIDEN_URL", "https://stage.dev.stackgen.com") + "/guild/api/v1"
WS = os.environ.get("AIDEN_WORKSPACE_ID", "f2a4ba74-c584-4ef4-ba3d-63e602572781")
ALERT = "Martian Bank: customer logins slow"
PINNED = json.load(open(os.path.join(HERE, "..", "aiden", "workorder.json")))


def die(msg):
    sys.exit(f"\033[1;31m✗ {msg}\033[0m")


def say(msg):
    print(f"\033[1;36m▸ {msg}\033[0m", flush=True)


def inc_token():
    out = subprocess.run([KUBECTL, "--context", CTX, "-n", "martian-bank", "get", "secret", "incidents-booth",
                          "-o", "jsonpath={.data.token}"], capture_output=True, text=True)
    if out.returncode or not out.stdout:
        die("Secret martian-bank/incidents-booth not readable")
    return base64.b64decode(out.stdout).decode()


TOKEN = None


def inc(method, path, body=None, actor=None):
    global TOKEN
    TOKEN = TOKEN or inc_token()
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    if actor:
        h["X-Actor"] = actor
    req = urllib.request.Request(INC_URL + path, method=method, headers=h,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        die(f"Incidents {method} {path}: {e.code} {e.read().decode()[:300]}")


def aiden_chat(agent, message, session):
    key = open(os.path.expanduser(os.environ.get("AIDEN_KEY_FILE", "~/.config/aiden/reinvent-booth.key"))).read().strip()
    h = {"Authorization": f"Bearer {key}", "X-Appcd-Org": WS, "Content-Type": "application/json"}
    req = urllib.request.Request(f"{AIDEN}/agents/{agent}/chat/start?orgId={WS}", method="POST", headers=h,
                                 data=json.dumps({"message": message, "session_id": session}).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        trace = json.loads(r.read())["trace_id"]
    text = ""
    sub = urllib.request.Request(f"{AIDEN}/executions/{trace}/subscribe?orgId={WS}", headers={**h, "Accept": "text/event-stream"})
    with urllib.request.urlopen(sub, timeout=600) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            kind = str(ev.get("type", "")).replace("ai.genie.agui.", "") or (ev.get("data") or {}).get("Type", "")
            if kind == "TEXT_MESSAGE_CONTENT":
                text += (ev.get("data") or {}).get("Content", "")
            elif kind == "TURN_FINISHED":
                break
    return trace, text.strip()


def booth_incidents():
    return [i for i in inc("GET", "/api/incidents?status=open") if ALERT.lower() in (i.get("title") or "").lower()]


def current_incident(ref=None):
    if ref:
        return ref
    open_ = booth_incidents()
    if not open_:
        die("no open booth incident (run: booth declare)")
    return open_[0]["ref"]


def booth_wo(open_only=True):
    for inc_ in booth_incidents():
        for w in inc("GET", f"/api/work-orders?incident={inc_['ref']}"):
            if not open_only or w["status"] in ("proposed", "approved", "in_progress"):
                return w
    return None


cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "status"), sys.argv[2:]

if cmd == "declare":
    existing = booth_incidents()
    if existing:
        ref = existing[0]["ref"]
        say(f"booth incident already open: {ref}")
    else:
        groups = [g for g in inc("GET", "/api/alert-groups") if ALERT.lower() in (g.get("title") or "").lower()
                  and g.get("state") in ("firing", "acknowledged")]
        if not groups:
            die("the login alert isn't firing yet (Black Friday running? alert needs ~2 min)")
        r = inc("POST", f"/api/alert-groups/{groups[0]['id']}/declare_incident", {"severity": 2}, actor="Booth presenter")
        x = r.get("incident") if isinstance(r, dict) else None
        ref = (x.get("ref") if isinstance(x, dict) else x) or (r.get("ref") if isinstance(r, dict) else None) or booth_incidents()[0]["ref"]
        say(f"declared {ref} from alert group {groups[0]['id']}")
    inc("POST", f"/api/incidents/{ref}/investigate", {}, actor="Booth presenter")
    say(f"Aiden for SRE is investigating {ref}: {INC_URL}/incidents/{ref}")

elif cmd == "rca":
    ref = current_incident(args[0] if args else None)
    for _ in range(60):
        i = inc("GET", f"/api/incidents/{ref}")
        invs = i.get("investigations") or []
        done = [v for v in invs if v.get("status") in ("complete", "completed", "done", "failed", "blocked")]
        if done:
            v = done[-1]
            say(f"investigation {v.get('status')} on {ref}")
            print(v.get("note") or v.get("summary") or json.dumps(v)[:1500])
            break
        time.sleep(5)
    else:
        die("no investigation result within 5 min")

elif cmd == "handoff":
    ref = current_incident(args[0] if args else None)
    if booth_wo():
        die(f"work order already open: {booth_wo()['ref']}")
    i = inc("GET", f"/api/incidents/{ref}")
    brief = (f"Draft the fix for this incident — {ref}: {i.get('title')}. Severity SEV{i.get('severity')}. "
             f"Cause: customer-auth is CPU-throttled by a 200m CPU limit set outside Git (Aiden for SRE). Answer with JSON only.")
    say("Aiden for DevOps is drafting the work order…")
    trace, text = aiden_chat("martian-bank-devops", brief, f"booth-wo-{ref}-{int(time.time())}")
    try:
        draft = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        draft = None
    if draft != PINNED:
        say("Aiden's draft deviated from the pinned work order: filing the pinned copy (deploy/aiden/workorder.json)")
        draft = PINNED
    w = inc("POST", "/api/work-orders", {**draft, "incident": ref, "required": True}, actor="Aiden for DevOps")
    say(f"{w['ref']} proposed by Aiden for DevOps ({w['risk']}, {w['status']}): a person approves it in {INC_URL}/incidents/{ref}")
    print(w["ref"])

elif cmd == "wo":
    w = booth_wo()
    print(w["ref"] if w else "")

elif cmd == "step":
    w = booth_wo() or die("no open booth work order")
    n, did = int(args[0]), args[1]
    body = {"step": n, "did": did}
    if "--result" in args:
        body["result"] = args[args.index("--result") + 1]
    if "--ok" in args:
        body["ok"] = args[args.index("--ok") + 1] == "true"
    actor = {1: "StackGen InfraOps", 2: "StackGen InfraOps", 3: "StackGen DevOps pipeline", 4: "Aiden for SRE"}.get(n, "booth")
    r = inc("POST", f"/api/work-orders/{w['ref']}/steps", body, actor=actor)
    say(f"{w['ref']} step {n} recorded by {actor} → {r.get('status', '?')}")

elif cmd == "verify":
    w = booth_wo() or die("no open booth work order")
    if w["status"] not in ("approved", "in_progress"):
        die(f"{w['ref']} is {w['status']}: approve it first")
    # Pre-check the same numbers Aiden will judge (org 6 viewer key), so the recorded check never fails on timing:
    # spans and the 1-minute windows need ~1-2 min after the sync to show the fixed pod only.
    vk = open(os.path.expanduser("~/.config/aiden/reinvent-onow-viewer.key")).read().strip()
    def q(expr):
        body = {"queries": [{"refId": "A", "datasource": {"uid": "metrics"}, "expr": expr, "instant": True}], "from": "now-5m", "to": "now"}
        r = urllib.request.Request("https://stephgen-medussa.observe.devopsnow.cloud/api/ds/query", data=json.dumps(body).encode(),
                                   headers={"Authorization": f"Bearer {vk}", "Content-Type": "application/json"}, method="POST")
        f = json.load(urllib.request.urlopen(r, timeout=30))["results"]["A"].get("frames") or []
        return f[0]["data"]["values"][1][0] if f and f[0]["data"]["values"] else None
    P95 = 'histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{job="martian-bank/customer-auth", span_name="POST /api/users/auth", span_kind="SPAN_KIND_SERVER"}[1m]))) / 1000'
    THR = '100 * sum(rate(container_cpu_cfs_throttled_periods_total{namespace="martian-bank", container="customer-auth"}[1m])) / sum(rate(container_cpu_cfs_periods_total{namespace="martian-bank", container="customer-auth"}[1m]))'
    for i in range(24):
        p95, thr = q(P95), q(THR)
        if p95 is not None and p95 < 1.5 and (thr or 0) < 25:
            break
        say(f"waiting for the fixed pod's numbers: p95 {p95 if p95 is None else round(p95, 1)} s, throttling {thr if thr is None else round(thr)} % (15 s)")
        time.sleep(15)
    else:
        die("numbers didn't recover within 6 min; not recording a check (WO stays in progress)")
    say("Aiden for SRE is verifying…")
    trace, text = aiden_chat("martian-bank-sre", "Verify the Martian Bank login fix (customer-auth capacity PR shipped). Load skill martian-bank-booth-verify and follow it exactly.",
                             f"booth-verify-{w['ref']}-{int(time.time())}")
    print(text)
    ok = "VERDICT: VERIFIED" in text.upper().replace("**", "")
    if not ok:
        die("Aiden says NOT VERIFIED: check not recorded, so the work order stays in progress. Wait a minute and run booth verify again")
    r = inc("POST", f"/api/work-orders/{w['ref']}/steps", {"step": 4, "did": "Aiden for SRE verified the fix" if ok else "Aiden for SRE: not verified yet",
                                                           "result": text[:3900], "ok": ok}, actor="Aiden for SRE")
    say(f"{w['ref']} check {'PASSED' if ok else 'FAILED'} → work order {r.get('status', '?')}")
    if not ok:
        sys.exit(2)

elif cmd == "cleanup":
    for i in booth_incidents():
        for w in inc("GET", f"/api/work-orders?incident={i['ref']}"):
            if w["status"] == "proposed":
                inc("POST", f"/api/work-orders/{w['ref']}/cancel", {"note": "booth reset"}, actor="Aiden for DevOps")
                say(f"cancelled {w['ref']} (proposed)")
            elif w["status"] in ("approved", "in_progress"):
                die(f"{w['ref']} is {w['status']}: only a person can cancel it. Cancel it in {INC_URL}/incidents/{i['ref']}, then re-run reset")
        inc("PATCH", f"/api/incidents/{i['ref']}", {"status": "resolved", "cause": "Out-of-band 200m CPU limit on customer-auth (booth scenario)",
                                                     "resolution": "Capacity declared in Git via the InfraOps work order (booth reset)", "note": "booth reset"},
            actor="Booth reset")
        say(f"resolved {i['ref']}")

elif cmd == "status":
    for i in booth_incidents():
        ws = inc("GET", f"/api/work-orders?incident={i['ref']}")
        print(f"{i['ref']} {i['status']} SEV{i['severity']} · " + ", ".join(f"{w['ref']} {w['status']}" for w in ws))

else:
    print(__doc__)
