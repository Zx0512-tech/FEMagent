from __future__ import annotations

from pathlib import Path

from ansys.mapdl import reader as pymapdl_reader
from ansys.mapdl.reader import examples

from fem_core.ansys_result_reader import describe_ansys_binary_result, query_ansys_nodal_result


def test_ansys_reader_describes_real_packaged_rst_example() -> None:
    report = describe_ansys_binary_result(Path(examples.rstfile))

    assert report["kind"] == "ansys_binary_result"
    assert report["format"] == "MAPDL_BINARY_RESULT"
    assert report["suffix"] == ".rst"
    assert report["resultSetCount"] >= 1
    assert report["nodeCount"] > 0
    assert report["dofLabels"]
    assert report["abscissa"]["sampleCount"] == report["resultSetCount"]
    assert report["abscissa"]["unit"] is None


def test_ansys_reader_queries_real_nodal_displacement_without_inventing_units() -> None:
    raw = pymapdl_reader.read_binary(examples.rstfile, parse_vtk=False)
    nnum, _ = raw.nodal_solution(0)
    node_id = int(nnum[0])
    dof_label = str(raw.result_dof(0)[0])

    result = query_ansys_nodal_result(
        Path(examples.rstfile),
        quantity="DISPLACEMENT",
        node_id=node_id,
        component=dof_label,
    )

    assert result["quantity"] == "DISPLACEMENT"
    assert result["target"] == {"type": "NODE", "id": node_id}
    assert result["unit"] is None
    assert result["referenceFrame"] == "SOLVER_NATIVE"
    assert len(result["abscissaValues"]) == len(result["values"])
    assert len(result["values"]) >= 1
