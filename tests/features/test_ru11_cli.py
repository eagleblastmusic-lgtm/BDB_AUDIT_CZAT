from __future__ import annotations

import json
from pathlib import Path
import sys

from bdb_audit.cli import run_cli


def _target(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "src" / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='1'\n[project.scripts]\ndemo='demo.cli:main'\n",
        encoding="utf-8",
    )
    (root / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "demo" / "cli.py").write_text(
        "import json\n"
        "def main(): print(json.dumps({'status':'ok'})); return 0\n"
        "if __name__ == '__main__': raise SystemExit(main())\n",
        encoding="utf-8",
    )
    return root


def test_ru11_features_cli_end_to_end_real_public_boundary(tmp_path: Path, capsys) -> None:
    root = _target(tmp_path)
    inventory = tmp_path / "inventory.json"
    assert run_cli(["features", "discover", "--source", str(root), "--output", str(inventory), "--json"]) == 0
    discover_response = json.loads(capsys.readouterr().out)
    assert discover_response["feature_count"] >= 1
    inventory_body = json.loads(inventory.read_text(encoding="utf-8"))
    feature = next(item for item in inventory_body["features"] if item["interface"] == "CLI" and item["name"] == "demo")

    request = tmp_path / "plan-input.json"
    request.write_text(json.dumps({
        "feature_id": feature["feature_id"],
        "cases": [{
            "case_id": "cli-ok",
            "behavior_kind": "POSITIVE",
            "argv": [sys.executable, "-m", "demo.cli"],
            "expected_exit_code": 0,
            "expected_json_subset": {"status": "ok"},
        }],
        "oracles": [{
            "case_id": "cli-ok",
            "requirement_refs": ["REQ-DEMO-CLI"],
            "independence": "INDEPENDENT",
        }],
    }), encoding="utf-8")

    plan = tmp_path / "plan.json"
    assert run_cli(["features", "plan", "--source", str(root), "--input", str(request), "--output", str(plan), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["case_count"] == 1

    run = tmp_path / "run.json"
    evidence = tmp_path / "evidence"
    assert run_cli(["features", "verify", "--source", str(root), "--plan", str(plan), "--evidence", str(evidence), "--output", str(run), "--json"]) == 0
    verify_response = json.loads(capsys.readouterr().out)
    assert verify_response["case_statuses"] == {"cli-ok": "PASS"}

    matrix = tmp_path / "FEATURE_STATUS_MATRIX.json"
    assert run_cli(["features", "matrix", "--source", str(root), "--inventory", str(inventory), "--assessments", str(run), "--output", str(matrix), "--json"]) == 0
    matrix_response = json.loads(capsys.readouterr().out)
    assert matrix_response["statuses"][feature["feature_id"]] == "PASS"
    matrix_body = json.loads(matrix.read_text(encoding="utf-8"))
    entry = next(item for item in matrix_body["entries"] if item["feature_id"] == feature["feature_id"])
    assert entry["freshness"] == "ACTIVE"
    assert entry["run_receipt_digests"]
