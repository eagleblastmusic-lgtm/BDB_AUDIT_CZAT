"""Unit tests for platform integration adapters (clipboard, explorer, file dialog)."""
from __future__ import annotations

from pathlib import Path
import pytest

from bdb_audit.workflow.platform import (
    MockPlatformAdapter,
    GenericPlatformAdapter,
    WindowsPlatformAdapter,
)


def test_mock_platform_adapter_records_clipboard_and_explorer(tmp_path: Path):
    mock = MockPlatformAdapter()
    sample_file = tmp_path / "sample_package.zip"
    sample_file.write_text("dummy", encoding="utf-8")

    # Clipboard copy
    res_clip = mock.copy_to_clipboard("Prompt text content")
    assert res_clip is True
    assert len(mock.copied_texts) == 1
    assert mock.copied_texts[0] == "Prompt text content"

    # Explorer selection
    res_exp = mock.open_and_select(sample_file)
    assert res_exp is True
    assert len(mock.selected_files) == 1
    assert mock.selected_files[0] == sample_file


def test_mock_platform_adapter_queued_multi_select(tmp_path: Path):
    zip1 = tmp_path / "E1-A.zip"
    zip2 = tmp_path / "E1-B.zip"
    mock = MockPlatformAdapter(queued_selections=[[zip1, zip2], [zip1]])

    selected_batch1 = mock.select_multiple_zips()
    assert selected_batch1 == [zip1, zip2]

    selected_batch2 = mock.select_multiple_zips()
    assert selected_batch2 == [zip1]

    # Queue exhausted returns empty list
    assert mock.select_multiple_zips() == []


def test_generic_platform_adapter_fallbacks(tmp_path: Path):
    adapter = GenericPlatformAdapter()
    dummy = tmp_path / "pkg.zip"
    dummy.write_text("data", encoding="utf-8")

    # In test environment, dialog returns empty list gracefully
    zips = adapter.select_multiple_zips()
    assert zips == []


def test_windows_platform_adapter_handles_missing_file_gracefully(tmp_path: Path):
    adapter = WindowsPlatformAdapter()
    non_existent = tmp_path / "does_not_exist.zip"

    # Non-existent file selection should not raise an unhandled exception
    res = adapter.open_and_select(non_existent)
    # Returns True or False depending on explorer process launch, but must not crash
    assert isinstance(res, bool)
