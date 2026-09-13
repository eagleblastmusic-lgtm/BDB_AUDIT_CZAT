"""RU11 source-backed feature proposal discovery for Python CLI/API targets."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import tomllib
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..runner.environments import source_manifest
from .models import FeatureRevision


def _feature_id(interface: str, name: str, anchor: dict[str, Any]) -> str:
    seed = {"interface": interface, "name": name, "source_anchor": anchor}
    return "feature_" + hashlib.sha256(canonical_bytes(seed)).hexdigest()[:24]


def _load_pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError("FEATURE_PYPROJECT_PARSE_FAILED", str(path)) from exc


def _module_candidates(root: Path, module: str) -> tuple[Path, ...]:
    rel = Path(*module.split("."))
    return (
        root / "src" / rel.with_suffix(".py"),
        root / "src" / rel / "__init__.py",
        root / rel.with_suffix(".py"),
        root / rel / "__init__.py",
    )


def discover_cli_features(root: str | Path) -> tuple[FeatureRevision, ...]:
    source = Path(root).resolve()
    manifest = source_manifest(source)
    pyproject = _load_pyproject(source)
    scripts = pyproject.get("project", {}).get("scripts", {}) if isinstance(pyproject, dict) else {}
    if not isinstance(scripts, dict):
        raise ValidationError("FEATURE_SCRIPT_TABLE_INVALID")
    result: list[FeatureRevision] = []
    for script_name, target in sorted(scripts.items()):
        if not isinstance(script_name, str) or not isinstance(target, str):
            raise ValidationError("FEATURE_SCRIPT_ENTRY_INVALID")
        module, _, callable_name = target.partition(":")
        resolved = next((path for path in _module_candidates(source, module) if path.is_file()), None)
        anchor = {
            "path": resolved.relative_to(source).as_posix() if resolved is not None else "pyproject.toml",
            "symbol": target,
            "declaration": f"project.scripts.{script_name}",
        }
        result.append(FeatureRevision(
            feature_id=_feature_id("CLI", script_name, anchor),
            name=script_name,
            interface="CLI",
            source_anchor=anchor,
            source_manifest_digest=manifest["manifest_digest"],
            criticality="HIGH",
            environment_classes=("LOCAL_PYTHON",),
            reconciliation_status="RECONCILED" if resolved is not None and callable_name else "PROVISIONAL",
        ))
    return tuple(result)


def _api_features_from_file(root: Path, path: Path, source_digest: str) -> list[FeatureRevision]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return []
    rel = path.relative_to(root).as_posix()
    module = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel.replace("/", ".")
    if module.startswith("src."):
        module = module[4:]
    output: list[FeatureRevision] = []
    for node in tree.body:
        symbols: list[tuple[str, int]] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            symbols.append((node.name, node.lineno))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append((node.name, node.lineno))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    symbols.append((f"{node.name}.{child.name}", child.lineno))
        for symbol, line in symbols:
            name = f"{module}:{symbol}"
            anchor = {"path": rel, "symbol": name, "line": line}
            output.append(FeatureRevision(
                feature_id=_feature_id("API", name, anchor),
                name=name,
                interface="API",
                source_anchor=anchor,
                source_manifest_digest=source_digest,
                environment_classes=("LOCAL_PYTHON",),
                reconciliation_status="RECONCILED",
            ))
    return output


def discover_api_features(root: str | Path) -> tuple[FeatureRevision, ...]:
    source = Path(root).resolve()
    manifest = source_manifest(source)
    roots = [item for item in (source / "src", source) if item.is_dir()]
    chosen = roots[0] if (source / "src").is_dir() else source
    features: list[FeatureRevision] = []
    for path in sorted(chosen.rglob("*.py")):
        if any(part in {"tests", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        features.extend(_api_features_from_file(source, path, manifest["manifest_digest"]))
    unique = {item.feature_id: item for item in features}
    return tuple(unique[key] for key in sorted(unique))


def discover_features(root: str | Path) -> dict[str, Any]:
    source = Path(root).resolve()
    manifest = source_manifest(source)
    features = tuple(sorted((*discover_cli_features(source), *discover_api_features(source)), key=lambda item: item.feature_id))
    return {
        "schema_version": "BDB-DERIVED-FEATURE-INVENTORY-1",
        "authority": "DERIVED_NOT_ACCEPTED_HISTORY",
        "source_manifest_digest": manifest["manifest_digest"],
        "feature_count": len(features),
        "features": [item.as_dict() | {"feature_digest": item.digest} for item in features],
    }


__all__ = ["discover_cli_features", "discover_api_features", "discover_features"]
