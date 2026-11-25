#!/usr/bin/env bash
# Upsert the booth's Aiden pieces into the stage.dev workspace reinvent-booth.
#   AIDEN_KEY_FILE (default ~/.config/aiden/reinvent-booth.key) — API key scoped to the workspace
# Idempotent: POST, and on "already exists" PUT by name.
set -euo pipefail
cd "$(dirname "$0")"
URL="${AIDEN_URL:-https://stage.dev.stackgen.com}/guild/api/v1"
WS="${AIDEN_WORKSPACE_ID:-f2a4ba74-c584-4ef4-ba3d-63e602572781}"
KEY="$(tr -d '\n' < "${AIDEN_KEY_FILE:-$HOME/.config/aiden/reinvent-booth.key}")"
H=(-H "Authorization: Bearer $KEY" -H "X-Appcd-Org: $WS" -H 'Content-Type: application/json')

upsert() { # upsert <collection> <name> <json-file>
  local out code
  out=$(curl -s -m 30 -w '\n%{http_code}' "${H[@]}" -X POST "$URL/$1?orgId=$WS" -d @"$3"); code=${out##*$'\n'}
  if [[ "$code" =~ ^20 ]]; then echo "created $1/$2"; return; fi
  if [[ "$code" == 409 || "$out" == *xist* || "$out" == *uplicate* || ( "$1" = skills && "$out" == *"invalid skill ID"* ) ]]; then
    local ref="$2"
    if [ "$1" = skills ]; then   # skills are updated by ID, not name
      ref=$(curl -s -m 30 "${H[@]}" "$URL/skills?orgId=$WS" | python3 -c 'import sys,json;n=sys.argv[1];print(next(i["id"] for i in json.load(sys.stdin)["items"] if i["name"]==n))' "$2")
    fi
    python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));(sys.argv[2]=="agents") and d.pop("name",None);print(json.dumps(d))' "$3" "$1" > "$tmp/put.json"
    out=$(curl -s -m 30 -w '\n%{http_code}' "${H[@]}" -X PUT "$URL/$1/$ref?orgId=$WS" -d @"$tmp/put.json"); code=${out##*$'\n'}
    [[ "$code" =~ ^20 ]] && { echo "updated $1/$2"; return; }
  fi
  echo "FAILED $1/$2 [$code]: ${out%$'\n'*}" | cut -c1-400 >&2; exit 1
}

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for d in skills/*/; do
  n=$(basename "$d")
  python3 -c 'import json,sys;print(json.dumps({"skill_md":open(sys.argv[2]).read()}))' "$n" "$d/SKILL.md" > "$tmp/$n.json"
  upsert skills "$n" "$tmp/$n.json"
done
upsert agents martian-bank-sre agent.json
upsert agents martian-bank-devops agent-devops.json
upsert workflows martian-bank-verify workflow-verify.json
