"""RU10 disposable subprocess supervisor with fail-closed resource controls."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .permissions import sanitized_environment, validate_run_spec
from .specs import CapabilityProfile, ToolRunResult, ToolRunSpec


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _safe_copy(source: Path, worker: Path) -> None:
    shutil.copytree(source, worker, symlinks=False)


def _persist(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


class ToolSupervisor:
    """Execute exact argv in a disposable source copy; never with shell=True."""

    def __init__(self, profile: CapabilityProfile | None = None):
        self.profile = profile or CapabilityProfile()

    def run(self, spec: ToolRunSpec) -> ToolRunResult:
        try:
            source, evidence = validate_run_spec(spec, self.profile)
        except ValidationError as exc:
            return ToolRunResult(
                run_id=spec.run_id,
                spec_digest=spec.digest,
                capability_profile_digest=self.profile.digest,
                supervisor_status="BLOCKED",
                target_exit_code=None,
                timed_out=False,
                output_limit_exceeded=False,
                cleanup_status="NOT_STARTED",
                stdout_sha256=None,
                stderr_sha256=None,
                stdout_bytes=0,
                stderr_bytes=0,
                limitations=(exc.code,),
                detail=exc.detail,
            )

        evidence.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="bdb-tool-run-"))
        worker = temp_root / "workspace"
        stdout_temp = temp_root / "stdout.bin"
        stderr_temp = temp_root / "stderr.bin"
        status = "EXECUTION_ERROR"
        exit_code: int | None = None
        timed_out = False
        output_exceeded = False
        detail: str | None = None
        limitations: list[str] = []
        stdout_digest: str | None = None
        stderr_digest: str | None = None
        stdout_size = stderr_size = 0
        process: subprocess.Popen[bytes] | None = None

        if self.profile.network_isolation != "ENFORCED":
            limitations.append("NETWORK_EGRESS_NOT_ENFORCED")

        try:
            _safe_copy(source, worker)
            cwd = (worker / spec.working_subdir).resolve()
            try:
                cwd.relative_to(worker.resolve())
            except ValueError as exc:
                raise ValidationError("TOOL_RUN_WORKDIR_ESCAPE") from exc
            if not cwd.is_dir():
                raise ValidationError("TOOL_RUN_WORKDIR_NOT_FOUND", str(cwd))

            env = sanitized_environment(spec.environment)
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            start_new_session = os.name != "nt"
            with stdout_temp.open("wb") as out_handle, stderr_temp.open("wb") as err_handle:
                process = subprocess.Popen(
                    list(spec.argv),
                    cwd=str(cwd),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=out_handle,
                    stderr=err_handle,
                    shell=False,
                    creationflags=creationflags,
                    start_new_session=start_new_session,
                )
                started = time.monotonic()
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    output_bytes = stdout_temp.stat().st_size + stderr_temp.stat().st_size
                    if output_bytes > spec.max_output_bytes:
                        output_exceeded = True
                        status = "OUTPUT_LIMIT"
                        _terminate_tree(process)
                        break
                    if elapsed > spec.timeout_seconds:
                        timed_out = True
                        status = "TIMEOUT"
                        _terminate_tree(process)
                        break
                    time.sleep(0.02)
                if process.poll() is None:
                    _terminate_tree(process)
                exit_code = process.returncode
                if not timed_out and not output_exceeded:
                    status = "SUCCESS" if exit_code == 0 else "TARGET_NONZERO"

            stdout_digest, stdout_size = _sha256_file(stdout_temp)
            stderr_digest, stderr_size = _sha256_file(stderr_temp)
            _persist(evidence / "stdout.bin", stdout_temp.read_bytes())
            _persist(evidence / "stderr.bin", stderr_temp.read_bytes())
            manifest = {
                "run_id": spec.run_id,
                "spec_digest": spec.digest,
                "capability_profile": self.profile.as_dict(),
                "argv": list(spec.argv),
                "working_subdir": spec.working_subdir,
                "supervisor_status": status,
                "target_exit_code": exit_code,
                "stdout_sha256": stdout_digest,
                "stderr_sha256": stderr_digest,
                "limitations": limitations,
            }
            _persist(evidence / "RUN_MANIFEST.json", canonical_bytes(manifest) + b"\n")
        except (OSError, ValidationError, subprocess.SubprocessError) as exc:
            if process is not None:
                _terminate_tree(process)
            status = "EXECUTION_ERROR"
            detail = str(exc)
        finally:
            try:
                shutil.rmtree(temp_root)
                cleanup_status = "CLEAN"
            except OSError as exc:
                cleanup_status = "FAILED"
                status = "CLEANUP_FAILED"
                detail = f"cleanup failed: {exc}"

        files = tuple(
            str(path)
            for path in (evidence / "RUN_MANIFEST.json", evidence / "stdout.bin", evidence / "stderr.bin")
            if path.is_file()
        )
        result = ToolRunResult(
            run_id=spec.run_id,
            spec_digest=spec.digest,
            capability_profile_digest=self.profile.digest,
            supervisor_status=status,
            target_exit_code=exit_code,
            timed_out=timed_out,
            output_limit_exceeded=output_exceeded,
            cleanup_status=cleanup_status,
            stdout_sha256=stdout_digest,
            stderr_sha256=stderr_digest,
            stdout_bytes=stdout_size,
            stderr_bytes=stderr_size,
            evidence_files=files,
            limitations=tuple(sorted(set(limitations))),
            detail=detail,
        )
        if files:
            receipt_body = result.as_dict()
            receipt_body["receipt_digest"] = result.receipt_digest
            _persist(evidence / "RUN_RECEIPT.json", canonical_bytes(receipt_body) + b"\n")
        return result


__all__ = ["ToolSupervisor"]
