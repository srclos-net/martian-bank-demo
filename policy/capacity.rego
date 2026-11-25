# Martian Bank capacity policy — evaluated by conftest in CI (rendered Git
# state, the PR gate) and by the in-cluster InfraOps scan (live state).
#
#   CAP-001  every container declares CPU + memory requests
#   CAP-002  every container declares CPU + memory limits
#   CAP-003  CPU limit >= 250m (a lower cap throttles a tier-1 service
#            under normal customer load)
package main

import rego.v1

workload_kinds := {"Deployment", "StatefulSet", "DaemonSet"}

containers contains [name, c] if {
	workload_kinds[input.kind]
	name := input.metadata.name
	c := input.spec.template.spec.containers[_]
}

deny contains msg if {
	some [name, c] in containers
	some r in ["cpu", "memory"]
	not c.resources.requests[r]
	msg := sprintf("CAP-001 %s/%s: no %s request declared", [name, c.name, r])
}

deny contains msg if {
	some [name, c] in containers
	some r in ["cpu", "memory"]
	not c.resources.limits[r]
	msg := sprintf("CAP-002 %s/%s: no %s limit declared", [name, c.name, r])
}

deny contains msg if {
	some [name, c] in containers
	lim := c.resources.limits.cpu
	units.parse(sprintf("%v", [lim])) < 0.25
	msg := sprintf("CAP-003 %s/%s: CPU limit %v is below the 250m floor", [name, c.name, lim])
}
