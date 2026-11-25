<!-- InfraOps scan (deploy/infraops/scan.py), armed state, 2026-11-25. -->
### InfraOps scan — namespace `martian-bank` vs `srclos-net/martian-bank-demo@main`

**Drift (live ≠ Git): 1**
- `customer-auth/customer-auth`: live **limits cpu=200m**, Git **(none)** — set by `kubectl-patch`

**Policy, live state: 4 violation(s)**
- CAP-001 customer-auth/customer-auth: no cpu request declared
- CAP-001 customer-auth/customer-auth: no memory request declared
- CAP-002 customer-auth/customer-auth: no memory limit declared
- CAP-003 customer-auth/customer-auth: CPU limit 200m is below the 250m floor

**Policy, Git state: 4 violation(s)**
- CAP-001 customer-auth/customer-auth: no cpu request declared
- CAP-001 customer-auth/customer-auth: no memory request declared
- CAP-002 customer-auth/customer-auth: no cpu limit declared
- CAP-002 customer-auth/customer-auth: no memory limit declared
