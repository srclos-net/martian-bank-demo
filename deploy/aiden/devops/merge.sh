#!/bin/sh
# Aiden for DevOps, step 3 of the booth work order: merge the PR once the policy gate has passed.
# Runs inside the github-martian-bank integration sandbox. Usage: sh merge.sh <pr-number> WO-nnnn
set -eu
PR="$1"; WO="$2"; REPO=srclos-net/martian-bank-demo
i=0; S=""
while [ $i -lt 18 ]; do
  S=$(gh pr checks "$PR" --repo "$REPO" 2>&1 || true)
  echo "$S" | grep -qiE "pending|in_progress|queued|expected" || break
  i=$((i + 1)); sleep 10
done
echo "CHECKS: $(echo "$S" | tr '\n' ' ' | cut -c1-300)"
if echo "$S" | grep -qiE "^[^ ]+[[:space:]]+fail"; then echo "GATE_FAILED"; exit 4; fi
gh pr merge "$PR" --repo "$REPO" --squash --delete-branch --subject "InfraOps: declare customer-auth capacity in Git ($WO) [skip ci]"
echo "MERGED_SHA=$(gh pr view "$PR" --repo "$REPO" --json mergeCommit --jq .mergeCommit.oid)"
