# Inspect FEM Results

Use this Skill when answering questions about numerical response from a completed FEMagent solver run.

## Method

1. Start with `fem_result_inspect` for the recorded run.
2. Read `integrity.status` and warnings before using any numerical result.
3. Treat artifact SHA verification and solver-native reader output as the result-fact boundary.
4. Read `queryCapabilities` before choosing a quantity/component.
5. Use `fem_result_query` for the requested recorded nodal fact. Do not recompute a response with the LLM and do not rerun a solver merely to answer an existing-result query.
6. If inspection is `LIMITED`, explain which standardized result evidence is unavailable. `LIMITED` never means zero displacement, zero force, or a successful engineering check.
7. For the controlled OpenSees response contract, reported `m`, `m/s`, `m/s2`, and `s` are deterministic because the recorder schema defines them.
8. For ANSYS MAPDL binary results, preserve `unit: null` and solver-native abscissa semantics unless separate deterministic project/model evidence establishes units. Never infer SI from value magnitude, common practice, or solver defaults.
9. Node/component facts are not engineering-role facts. A result at node 36 does not by itself prove that node 36 is a tower base, bearing, girder end, or damper location. Resolve engineering role to node IDs through model/project evidence first.
10. When a requested channel is absent, report it as unavailable rather than substituting another node, component, quantity, log value, or LLM estimate.

## Evidence ladder

```text
run_manifest.json
    -> referenced result artifacts
    -> path + SHA integrity verification
    -> solver-specific deterministic reader
    -> ResultManifest
    -> ResultQuery
    -> engineering explanation
```

The explanation may interpret verified facts, but it must not change their source semantics.

## Solver boundaries

### OpenSees controlled response

`response.csv` is the numerical source. Result Intelligence can expose relative displacement, velocity, and acceleration for the recorded response node/DOF.

Arbitrary OpenSees Python bundles do not automatically receive a FEMagent recorder. If no standard response series was recorded, inspection is `LIMITED` and response queries must fail closed.

### ANSYS MAPDL

Only a recorded MAPDL binary result (`.rst`, `.rth`, `.rfl`, or `.rmg`) is used for PR9 numerical result queries. Console/output logs are not numerical response truth.

Supported V1 nodal quantities are displacement, velocity, acceleration, and reaction force when present in the binary result. Physical units remain unknown unless declared elsewhere by deterministic evidence.

## Boundary

This Skill guides result reasoning only. It does not:

- execute or rerun ANSYS/OpenSees;
- resolve engineering semantic roles to arbitrary node IDs;
- decide which solver is more correct;
- create Artifact/Evidence validity states;
- perform cross-solver alignment;
- invent unavailable result channels.
