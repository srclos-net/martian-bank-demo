#!/bin/sh
# Aiden for DevOps, step 2 of the booth work order: ship InfraOps' proposed change as a PR.
# Runs inside the github-martian-bank integration sandbox, GitHub API only (gh api; no git credentials, no
# `gh auth` subcommands: the integration forbids them). Usage: sh ship.sh WO-nnnn
set -eu
WO="$1"; REPO=srclos-net/martian-bank-demo; F=deploy/values-civo.yaml
BR="aiden-devops/${WO}-customer-auth-capacity-$(date +%s)"
LINE='  customer-auth: {requests: {cpu: 100m, memory: 128Mi}, limits: {cpu: "1", memory: 384Mi}}'
DIR="/workspace/booth/${WO}-$(date +%s)"; mkdir -p "$DIR"; cd "$DIR"
BASE=$(gh api "repos/$REPO/git/ref/heads/main" --jq .object.sha)
gh api -H "Accept: application/vnd.github.raw" "repos/$REPO/contents/$F?ref=$BASE" > values.yaml
if grep -q '^  customer-auth: ' values.yaml; then echo "ALREADY_DECLARED"; exit 3; fi
FSHA=$(gh api "repos/$REPO/contents/$F?ref=$BASE" --jq .sha)
sed -i "s|^  # >>> booth:customer-auth-capacity\$|&\n${LINE}|" values.yaml
grep -c '^  customer-auth: ' values.yaml >/dev/null || { echo "INSERT_FAILED"; exit 5; }
B64=$(base64 values.yaml | tr -d '\n')
gh api -X POST "repos/$REPO/git/refs" -f ref="refs/heads/$BR" -f sha="$BASE" --jq .ref
gh api -X PUT "repos/$REPO/contents/$F" -f message="Declare customer-auth capacity in Git ($WO)" -f branch="$BR" \
  -f sha="$FSHA" -f content="$B64" -f "committer[name]=Aiden for DevOps" \
  -f "committer[email]=aiden-devops@users.noreply.github.com" --jq .commit.sha
gh pr create --repo "$REPO" --base main --head "$BR" \
  --title "InfraOps: declare customer-auth capacity in Git (drift + policy CAP-001/2/3)" \
  --body "Aiden for DevOps, executing $WO (approved in StackGen Incidents: https://incidents.stackgen.run). InfraOps found customer-auth running a 200m CPU limit set outside Git (Argo CD can't see it) and proposed declaring its capacity in Git. This PR is exactly that change; the capacity policy gate checks it; Argo CD applies it on merge."
