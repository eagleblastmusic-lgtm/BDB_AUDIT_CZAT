"""Missing declared runtime inputs must not produce a partial standalone."""
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

import build.build_single_file as builder


def distribution(monkeypatch, root, names):
    installed = SimpleNamespace(
        version="1", files=[PurePosixPath(name) for name in names],
        locate_file=lambda path: root / str(path),
    )
    monkeypatch.setattr(builder.importlib.metadata, "distribution", lambda name: installed)


@pytest.mark.parametrize("missing_kind", ["absent", "directory"])
def test_declared_runtime_input_cannot_disappear(monkeypatch, tmp_path, missing_kind):
    (tmp_path / "present.py").write_bytes(b"present runtime input\n")
    if missing_kind == "directory":
        (tmp_path / "required.py").mkdir()
    distribution(monkeypatch, tmp_path, ["present.py", "required.py"])
    with pytest.raises(RuntimeError, match="Declared runtime input missing or not a file"):
        builder.collect_runtime_files({"pinned-runtime": "1"})


def test_declared_runtime_files_retained_and_transport_exclusions_preserved(monkeypatch, tmp_path):
    raw = b"exact runtime input\r\n"
    (tmp_path / "present.py").write_bytes(raw)
    distribution(monkeypatch, tmp_path, ["present.py", "../../../Scripts/entry.exe", "__pycache__/unused.pyc"])
    assert builder.collect_runtime_files({"pinned-runtime": "1"}) == [("present.py", raw)]
