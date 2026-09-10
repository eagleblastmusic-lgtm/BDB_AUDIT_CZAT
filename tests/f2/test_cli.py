import os
from pathlib import Path
import subprocess
import sys


def test_help_has_no_domain_side_effect(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
               PYTHONDONTWRITEBYTECODE="1")
    run = subprocess.run([sys.executable, "-B", "-m", "bdb_audit", "--help"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0
    assert "usage: bdb_audit" in run.stdout
    assert list(tmp_path.iterdir()) == []
