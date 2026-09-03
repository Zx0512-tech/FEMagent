---
name: runtime-health
description: Checks the FEMagent runtime bootstrap and Python engineering-core bridge. Use when asked whether FEMagent itself is installed, connected, or healthy; do not use it to claim ANSYS or OpenSees readiness.
---

# Runtime Health

Use the `fem_health` tool once.

Report the returned Python/core versions and whether the bridge is healthy.

The solver fields `not_checked` mean exactly that: PR1 has not probed or validated ANSYS or OpenSees. Never upgrade them into an availability claim.
