#!/bin/sh
# Aiden for DevOps, step 2 of the booth work order: ship InfraOps' proposed change as a PR.
# Runs inside the github-martian-bank integration sandbox. Usage: sh ship.sh WO-nnnn
set -eu
WO="$1"; REPO=srclos-net/martian-bank-demo; BR="aiden-devops/${WO}-customer-auth-capacity"
LINE='  customer-auth: {requests: {cpu: 100m, memory: 128Mi}, limits: {cpu: "1", memory: 384Mi}}'
DIR="/workspace/booth/${WO}-$(date +%s)"
gh auth setup-git >/dev/null 2>&1 || true
mkdir -p "$DIR"
gh repo clone "$REPO" "$DIR" -- --depth 1 -q
cd "$DIR"
if grep -q '^  customer-auth: ' deploy/values-civo.yaml; then echo "ALREADY_DECLARED"; exit 3; fi
git checkout -q -b "$BR"
sed -i "s|^  # >>> booth:customer-auth-capacity\$|&\n${LINE}|" deploy/values-civo.yaml
git diff --stat
git -c user.name='Aiden for DevOps' -c user.email='aiden-devops@users.noreply.github.com' commit -q -am "Declare customer-auth capacity in Git ($WO)"
git push -q -u origin "$BR"
gh pr create --repo "$REPO" --base main --head "$BR" \
  --title "InfraOps: declare customer-auth capacity in Git (drift + policy CAP-001/2/3)" \
  --body "Aiden for DevOps, executing $WO (approved in StackGen Incidents: https://incidents.stackgen.run). InfraOps found customer-auth running a 200m CPU limit set outside Git (Argo CD can't see it) and proposed declaring its capacity in Git. This PR is exactly that change; the capacity policy gate checks it; Argo CD applies it on merge."
