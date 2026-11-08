from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .config import REGISTRY_PATH, SCHEMA_DIR


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Registry at {path} is not an object")
    return value


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text())


def validate_document(value: Any, schema_name: str) -> list[str]:
    validator = Draft202012Validator(load_schema(schema_name), format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    ]


def validate_registry(path: Path = REGISTRY_PATH) -> list[str]:
    registry = load_registry(path)
    errors = validate_document(registry, "source-registry.schema.json")
    sources = registry.get("sources", [])
    keys = [source.get("key") for source in sources if isinstance(source, dict)]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        errors.append(f"Duplicate source keys: {', '.join(duplicates)}")
    known = set(keys)
    for source in sources:
        if not isinstance(source, dict):
            continue
        missing = sorted(set(source.get("dependencies", [])) - known)
        if missing:
            errors.append(f"{source.get('key')}: unknown dependencies: {', '.join(missing)}")
    return errors


def source_config(source_key: str, path: Path = REGISTRY_PATH) -> dict[str, Any]:
    for source in load_registry(path)["sources"]:
        if source["key"] == source_key:
            return source
    raise KeyError(f"Unknown source: {source_key}")
