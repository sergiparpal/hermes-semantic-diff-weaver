"""Safe configuration loading, precedence, normalization, and validation."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import ErrorCode, WeaverError
from .models import AnalyzeRequest, WeaverConfig

MAX_CONFIG_BYTES = 256 * 1024


def _configuration_error(message: str) -> WeaverError:
    return WeaverError(
        ErrorCode.CONFIGURATION_ERROR,
        message,
        "Correct the YAML configuration or remove the invalid override and retry.",
    )


def _validate_relative_pattern(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _configuration_error(f"{label} must contain non-empty relative patterns.")
    normalized = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(normalized)
    if "\x00" in value or windows.is_absolute() or posix.is_absolute() or windows.drive:
        raise _configuration_error(f"{label} contains an absolute or invalid pattern.")
    if ".." in posix.parts or re.match(r"^[A-Za-z]:", value):
        raise _configuration_error(f"{label} may not contain parent traversal or a drive path.")
    return normalized


def _validate_config_paths(data: dict[str, Any]) -> None:
    paths = data.get("paths", {})
    if isinstance(paths, dict):
        for field in ("include", "exclude", "test_roots"):
            for value in paths.get(field, []) or []:
                _validate_relative_pattern(value, f"paths.{field}")
    for item in data.get("critical_paths", []) or []:
        if isinstance(item, dict) and "pattern" in item:
            _validate_relative_pattern(item["pattern"], "critical_paths.pattern")
    for item in data.get("mapping", []) or []:
        if not isinstance(item, dict):
            continue
        if "source" in item:
            _validate_relative_pattern(item["source"], "mapping.source")
        for value in item.get("tests", []) or []:
            _validate_relative_pattern(value, "mapping.tests")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _configuration_error(
            "The configuration file does not exist or is inaccessible."
        ) from exc
    if resolved.suffix.lower() not in {".yaml", ".yml"} or not resolved.is_file():
        raise _configuration_error("Configuration must be a regular .yaml or .yml file.")
    if resolved.stat().st_size > MAX_CONFIG_BYTES:
        raise _configuration_error("The configuration file exceeds the 262144-byte limit.")
    try:
        loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise _configuration_error("The configuration file is not valid safe UTF-8 YAML.") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise _configuration_error("The configuration root must be a mapping.")
    _validate_config_paths(loaded)
    return loaded


def _merge(lower: dict[str, Any], upper: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(lower)
    for key, value in upper.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_config(repo_root: Path, request: AnalyzeRequest) -> tuple[WeaverConfig, list[str]]:
    """Load built-ins, repository config, explicit profile, and request overrides."""
    warnings: list[str] = []
    data = WeaverConfig().model_dump(mode="python")
    hermes_path = repo_root / ".hermes" / "semantic-diff-weaver.yaml"
    local_path = repo_root / ".semantic-diff-weaver.yaml"
    if hermes_path.is_file():
        data = _merge(data, _read_yaml(hermes_path))
        if local_path.is_file():
            warnings.append(
                "Ignored .semantic-diff-weaver.yaml because the .hermes configuration has precedence."
            )
    elif local_path.is_file():
        data = _merge(data, _read_yaml(local_path))
    if request.risk_profile:
        data = _merge(data, _read_yaml(Path(request.risk_profile)))
    request_override: dict[str, Any] = {"paths": {}}
    if request.include is not None:
        request_override["paths"]["include"] = [
            _validate_relative_pattern(value, "include") for value in request.include
        ]
    if request.exclude is not None:
        request_override["paths"]["exclude"] = [
            _validate_relative_pattern(value, "exclude") for value in request.exclude
        ]
    if request_override["paths"]:
        data = _merge(data, request_override)
    if data.get("language", {}).get("primary") != "python":
        raise WeaverError(
            ErrorCode.UNSUPPORTED_LANGUAGE,
            "The configured primary language is not supported by this MVP.",
            "Set language.primary to python or remove the unsupported language override.",
        )
    try:
        return WeaverConfig.model_validate(data), warnings
    except ValidationError as exc:
        field = ".".join(str(part) for part in exc.errors()[0].get("loc", ())) or "configuration"
        raise _configuration_error(f"Invalid configuration value at {field}.") from exc
