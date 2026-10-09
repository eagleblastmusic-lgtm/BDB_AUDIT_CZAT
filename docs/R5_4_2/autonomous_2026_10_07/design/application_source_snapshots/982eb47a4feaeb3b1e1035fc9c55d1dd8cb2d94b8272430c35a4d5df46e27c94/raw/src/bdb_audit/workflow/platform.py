"""Platform integration adapters for clipboard, Explorer file selection, and file dialogs.

Implements OS-native automation safely (no shell=True, safe arguments list) with
graceful fallbacks and an in-memory mock adapter for deterministic unit testing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import sys
from typing import Sequence


class PlatformAdapter(ABC):
    """Abstract interface for OS platform automation."""

    @abstractmethod
    def copy_to_clipboard(self, text: str) -> bool:
        """Copy given string to OS clipboard. Return True if successful."""
        raise NotImplementedError

    @abstractmethod
    def open_and_select(self, file_path: Path) -> bool:
        """Open file manager and highlight/select the given file."""
        raise NotImplementedError

    @abstractmethod
    def select_multiple_zips(self, initial_dir: Path | None = None) -> list[Path]:
        """Display a multi-select file dialog for ZIP files. Return selected paths."""
        raise NotImplementedError


class WindowsPlatformAdapter(PlatformAdapter):
    """Native Windows implementation using clip.exe, explorer.exe /select, and PowerShell OpenFileDialog."""

    def copy_to_clipboard(self, text: str) -> bool:
        try:
            # clip.exe expects UTF-16 on Windows console
            subprocess.run(
                ["clip.exe"],
                input=text.encode("utf-16"),
                check=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except Exception:
            return False

    def open_and_select(self, file_path: Path) -> bool:
        try:
            resolved = str(file_path.resolve())
            subprocess.Popen(
                ["explorer.exe", f"/select,{resolved}"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except Exception:
            return False

    def select_multiple_zips(self, initial_dir: Path | None = None) -> list[Path]:
        try:
            init_dir_clause = ""
            if initial_dir and initial_dir.exists():
                esc_dir = str(initial_dir.resolve()).replace("'", "''")
                init_dir_clause = f"$f.InitialDirectory = '{esc_dir}';"

            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                "$f.Multiselect = $true; "
                "$f.Filter = 'ZIP archives (*.zip)|*.zip|All files (*.*)|*.*'; "
                f"{init_dir_clause} "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                "  $f.FileNames | ForEach-Object { Write-Output $_ } "
                "}"
            )
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0 and proc.stdout:
                lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
                return [Path(line) for line in lines if Path(line).exists()]
            return []
        except Exception:
            return []


class GenericPlatformAdapter(PlatformAdapter):
    """Generic fallback platform adapter for Linux / macOS / headless environments."""

    def copy_to_clipboard(self, text: str) -> bool:
        # Try xclip / pbcopy if available
        for tool, args in [("pbcopy", []), ("xclip", ["-selection", "clipboard"])]:
            try:
                subprocess.run(
                    [tool] + args,
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=5,
                )
                return True
            except Exception:
                continue
        return False

    def open_and_select(self, file_path: Path) -> bool:
        # Fallback to xdg-open or open if available
        for tool in ["xdg-open", "open"]:
            try:
                subprocess.Popen([tool, str(file_path.parent)])
                return True
            except Exception:
                continue
        return False

    def select_multiple_zips(self, initial_dir: Path | None = None) -> list[Path]:
        return []


class MockPlatformAdapter(PlatformAdapter):
    """In-memory mock adapter for deterministic, side-effect-free testing."""

    def __init__(self, queued_selections: Sequence[Sequence[Path | str]] | None = None):
        self.copied_texts: list[str] = []
        self.selected_files: list[Path] = []
        self.queued_selections: list[list[Path]] = [
            [Path(p) for p in sel] for sel in (queued_selections or [])
        ]

    def copy_to_clipboard(self, text: str) -> bool:
        self.copied_texts.append(text)
        return True

    def open_and_select(self, file_path: Path) -> bool:
        self.selected_files.append(file_path)
        return True

    def select_multiple_zips(self, initial_dir: Path | None = None) -> list[Path]:
        if self.queued_selections:
            return self.queued_selections.pop(0)
        return []


def DefaultPlatformAdapter() -> PlatformAdapter:
    if sys.platform == "win32":
        return WindowsPlatformAdapter()
    return GenericPlatformAdapter()


__all__ = [
    "PlatformAdapter",
    "WindowsPlatformAdapter",
    "GenericPlatformAdapter",
    "MockPlatformAdapter",
    "DefaultPlatformAdapter",
]
