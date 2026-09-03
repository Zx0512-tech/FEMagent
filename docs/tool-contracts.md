# Engineering Tool Contracts

FEMagent engineering tools use a versioned process boundary between the Pi/TypeScript runtime and the deterministic Python FEM core.

## Bridge protocol

Protocol identifier: `femagent.bridge/v1`.

Request:

```json
{
  "protocol": "femagent.bridge/v1",
  "requestId": "uuid",
  "command": "model.inspect",
  "payload": {"path": "bridge.cdb"}
}
```

Success response:

```json
{
  "protocol": "femagent.bridge/v1",
  "requestId": "uuid",
  "ok": true,
  "result": {},
  "meta": {"coreVersion": "0.1.0", "command": "model.inspect"}
}
```

Domain failure:

```json
{
  "protocol": "femagent.bridge/v1",
  "requestId": "uuid",
  "ok": false,
  "error": {"code": "FILE_NOT_FOUND", "message": "...", "details": {}},
  "meta": {"coreVersion": "0.1.0", "command": "model.inspect"}
}
```

The Python process returns structured domain failures instead of relying on stderr parsing. Process-launch, malformed-protocol, output-limit, abort, and timeout failures are represented by TypeScript `FemBridgeError` values.

## Workspace boundary

Engineering file tools may read only files whose resolved path remains inside the active workspace. Symlink/path traversal that resolves outside the workspace is rejected with `PATH_OUTSIDE_WORKSPACE`.

## PR2 tools

### `fem_health`

Checks the Python core bridge only. Solver fields remain `not_checked` until solver adapters validate them.

### `fem_model_inspect`

SAFE, read-only static inspection for ANSYS APDL/CDB-style text. It reports explicit commands and syntax signals; it does **not** claim total node/element counts for parameterized or block models and never runs ANSYS.

### `fem_load_inspect`

SAFE, read-only tabular inspection for CSV/TXT/DAT. It profiles rows/columns and time-name candidates. It does not infer physical units, directions, target nodes, or load kind.

## Design rule

Tool contracts are intentionally small and composable. Task methodology belongs in Skills; deterministic actions and engineering facts belong in Tools.
