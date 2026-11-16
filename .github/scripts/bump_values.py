#!/usr/bin/env python3
"""Pin the CI image tag in deploy/values-civo.yaml for Argo CD to sync."""
import re
import sys

sha = sys.argv[1]
path = "deploy/values-civo.yaml"
s = open(path).read()

if re.search(r"^  tag: ", s, flags=re.M):
    s = re.sub(r"^(  tag: )\S*$", rf"\1sha-{sha}", s, flags=re.M)
else:
    s = s.rstrip("\n") + (
        "\n\n# Pin the CI-built images (set by .github/workflows/ci.yml).\n"
        "image:\n"
        "  repository: ghcr.io/srclos-net/martian-bank-demo\n"
        f"  tag: sha-{sha}\n"
    )

open(path, "w").write(s)
print(f"pinned image tag to sha-{sha}")
