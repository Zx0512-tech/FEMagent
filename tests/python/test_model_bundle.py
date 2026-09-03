from hashlib import sha256
from pathlib import Path

from fem_core.model_bundle import bundle_fingerprint, discover_bundle


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_bundle_fingerprint_is_order_independent_and_content_sensitive(tmp_path: Path) -> None:
    main = tmp_path / "main.py"
    helper = tmp_path / "helper.py"
    main.write_text("print('main')\n", encoding="utf-8")
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    files = [
        {"path": "main.py", "sha256": _digest(main)},
        {"path": "helper.py", "sha256": _digest(helper)},
    ]

    first = bundle_fingerprint(files)
    second = bundle_fingerprint(list(reversed(files)))
    assert first == second

    helper.write_text("VALUE = 2\n", encoding="utf-8")
    changed = bundle_fingerprint(
        [
            {"path": "main.py", "sha256": _digest(main)},
            {"path": "helper.py", "sha256": _digest(helper)},
        ]
    )
    assert changed != first


def test_discover_bundle_blocks_dependency_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    main = workspace / "main.py"
    main.write_text("# model\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("# outside\n", encoding="utf-8")

    bundle = discover_bundle(
        workspace,
        main,
        [
            {
                "source": "main.py",
                "reference": "../outside.py",
                "target": "../outside.py",
                "type": "PYTHON_FILE_READ",
                "role": "ENGINEERING_DATA",
            }
        ],
    )

    dependency = bundle["dependencies"][0]
    assert dependency["status"] == "BLOCKED_OUTSIDE_WORKSPACE"
    assert bundle["integrity"] == "BLOCKED"
