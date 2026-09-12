"""RU07 regression proof for deterministic runtime RECORD metadata."""
from __future__ import annotations

from build.normalize_runtime_metadata import normalize_record_bytes


def test_ru07_record_policy_removes_only_payload_ineligible_rows_deterministically():
    prefix = (
        "jsonschema/__init__.py,sha256=stable,100\r\n"
        "jsonschema-4.25.1.dist-info/INSTALLER,sha256=stable-installer,4\r\n"
        "jsonschema-4.25.1.dist-info/RECORD,,\r\n"
        "jsonschema/__pycache__/__init__.cpython-314.pyc,,\r\n"
    )
    record_a = (
        "../../Scripts/jsonschema.exe,sha256=launcher-A,108352\r\n" + prefix
    ).encode("utf-8")
    record_b = (
        "../../Scripts/jsonschema.exe,sha256=launcher-B,108352\r\n" + prefix
    ).encode("utf-8")

    normalized_a = normalize_record_bytes(record_a)
    normalized_b = normalize_record_bytes(record_b)

    assert normalized_a == normalized_b
    text = normalized_a.decode("utf-8")
    assert "../../Scripts/jsonschema.exe" not in text
    assert "__pycache__" not in text
    assert "jsonschema/__init__.py,sha256=stable,100\n" in text
    assert "jsonschema-4.25.1.dist-info/INSTALLER,sha256=stable-installer,4\n" in text
    assert "jsonschema-4.25.1.dist-info/RECORD,,\n" in text
