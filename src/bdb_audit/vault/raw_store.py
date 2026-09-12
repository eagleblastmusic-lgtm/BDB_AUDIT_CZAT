"""Content-addressed raw artifact vault (RU03).

Raw bytes are retained before semantic parsing.  User-controlled file names never
participate in storage paths; identity is the RawDigest of exact bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import raw_digest


@dataclass(frozen=True)
class RawVaultReceipt:
    raw_digest: str
    byte_length: int
    media_type: str
    blob_path: Path
    metadata_path: Path
    already_present: bool = False

    def as_dict(self) -> dict:
        return {
            "raw_digest": self.raw_digest,
            "byte_length": self.byte_length,
            "media_type": self.media_type,
            "already_present": self.already_present,
        }


class RawArtifactVault:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.blob_root = self.root / "sha256"
        self.meta_root = self.root / "metadata"
        self.blob_root.mkdir(parents=True, exist_ok=True)
        self.meta_root.mkdir(parents=True, exist_ok=True)

    def _paths(self, digest: str) -> tuple[Path, Path]:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValidationError("INVALID_RAW_DIGEST")
        return (
            self.blob_root / digest[:2] / digest[2:],
            self.meta_root / f"{digest}.json",
        )

    @staticmethod
    def _sync_dir(path: Path) -> None:
        if os.name == "nt":
            return
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def put_bytes(self, raw: bytes, *, media_type: str = "application/octet-stream") -> RawVaultReceipt:
        if type(raw) is not bytes:
            raise ValidationError("RAW_BYTES_REQUIRED")
        if not isinstance(media_type, str) or not media_type.strip():
            raise ValidationError("INVALID_MEDIA_TYPE")
        digest = raw_digest(raw).value
        blob_path, metadata_path = self._paths(digest)
        blob_path.parent.mkdir(parents=True, exist_ok=True)

        if blob_path.exists():
            existing = blob_path.read_bytes()
            if raw_digest(existing).value != digest or existing != raw:
                raise ValidationError("RAW_VAULT_DIGEST_COLLISION")
            self._write_metadata(metadata_path, digest, len(raw), media_type)
            return RawVaultReceipt(digest, len(raw), media_type, blob_path, metadata_path, True)

        try:
            fd, temp_name = tempfile.mkstemp(prefix=".bdb-vault-", dir=str(blob_path.parent))
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "wb", closefd=True) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Never overwrite an already published digest path silently.
                try:
                    os.link(temp_path, blob_path)
                    temp_path.unlink()
                except FileExistsError:
                    temp_path.unlink(missing_ok=True)
                    existing = blob_path.read_bytes()
                    if existing != raw:
                        raise ValidationError("RAW_VAULT_DIGEST_COLLISION")
                except OSError:
                    # Windows/filesystems without hard-link support: os.replace is
                    # atomic within the directory. Re-read after publication.
                    os.replace(temp_path, blob_path)
                self._sync_dir(blob_path.parent)
            finally:
                temp_path.unlink(missing_ok=True)
        except ValidationError:
            raise
        except OSError as exc:
            raise ValidationError("RAW_VAULT_WRITE_FAILED", type(exc).__name__) from exc

        published = blob_path.read_bytes()
        if published != raw or raw_digest(published).value != digest:
            raise ValidationError("RAW_VAULT_READBACK_FAILED")
        self._write_metadata(metadata_path, digest, len(raw), media_type)
        return RawVaultReceipt(digest, len(raw), media_type, blob_path, metadata_path, False)

    def put_file(self, path: str | Path, *, media_type: str = "application/octet-stream") -> RawVaultReceipt:
        p = Path(path)
        if not p.is_file():
            raise ValidationError("RAW_ARTIFACT_NOT_FOUND")
        return self.put_bytes(p.read_bytes(), media_type=media_type)

    def _write_metadata(self, path: Path, digest: str, size: int, media_type: str) -> None:
        body = {
            "raw_digest": digest,
            "byte_length": size,
            "media_type": media_type,
            "digest_profile": "SHA-256",
        }
        raw = canonical_bytes(body)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValidationError("RAW_VAULT_METADATA_CONFLICT")
            return
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_bytes(raw)
            with tmp.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            raise ValidationError("RAW_VAULT_WRITE_FAILED", type(exc).__name__) from exc
        finally:
            tmp.unlink(missing_ok=True)

    def read_bytes(self, digest: str) -> bytes:
        blob_path, _ = self._paths(digest)
        if not blob_path.is_file():
            raise ValidationError("RAW_ARTIFACT_NOT_FOUND", digest)
        raw = blob_path.read_bytes()
        if raw_digest(raw).value != digest:
            raise ValidationError("RAW_VAULT_READBACK_FAILED")
        return raw


__all__ = ["RawArtifactVault", "RawVaultReceipt"]
