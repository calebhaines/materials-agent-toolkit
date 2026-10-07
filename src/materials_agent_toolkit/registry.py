"""Discover, validate and execute tools through a common JSON contract."""

import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from pydantic import Field, ValidationError

from materials_agent_toolkit import __version__
from materials_agent_toolkit.contracts import StrictModel, ToolSpec


class ToolRequest(StrictModel):
    tool: str = Field(min_length=1, max_length=120)
    input: dict[str, Any]
    tool_version: str | None = None


class ToolError(StrictModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class Provenance(StrictModel):
    toolkit_version: str = __version__
    python_version: str = platform.python_version()
    created_at: str
    input_sha256: str | None = None
    software_versions: dict[str, str] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)


class ToolResponse(StrictModel):
    status: Literal["ok", "error"]
    tool: str | None
    tool_version: str | None
    result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance
    error: ToolError | None = None


def _tools() -> dict[str, ToolSpec]:
    from materials_agent_toolkit.tools import composition, engineering, mechanics

    specs = [*composition.TOOLS, *engineering.TOOLS, *mechanics.TOOLS]
    registry = {spec.name: spec for spec in specs}
    if len(registry) != len(specs):
        raise RuntimeError("Duplicate tool names in registry")
    return registry


def list_tools() -> list[dict[str, Any]]:
    return [spec.describe() for _, spec in sorted(_tools().items())]


def describe_tool(name: str) -> dict[str, Any]:
    if name not in _tools():
        raise ValueError(f"Unknown tool: {name}")
    return _tools()[name].describe()


def validate_input(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Return normalized inputs or raise ValueError/ValidationError."""
    spec = _tools().get(name)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")
    return spec.input_model.model_validate(inputs).model_dump(mode="json")


def _provenance(spec: ToolSpec | None = None, inputs: dict | None = None) -> Provenance:
    versions = {}
    for package in ("pydantic", *(spec.dependencies if spec else ())):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not-installed"
    digest = None
    if inputs is not None:
        canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
    return Provenance(
        created_at=datetime.now(timezone.utc).isoformat(),
        input_sha256=digest,
        software_versions=versions,
        references=list(spec.references) if spec else [],
    )


def error_response(
    code: str,
    message: str,
    *,
    tool: str | None = None,
    spec: ToolSpec | None = None,
    provenance: Provenance | None = None,
    details: list[dict[str, Any]] | None = None,
) -> ToolResponse:
    return ToolResponse(
        status="error",
        tool=tool,
        tool_version=spec.version if spec else None,
        provenance=provenance or _provenance(spec),
        error=ToolError(code=code, message=message, details=details or []),
    )


def run_request(request: dict[str, Any]) -> ToolResponse:
    try:
        validated_request = ToolRequest.model_validate(request)
    except ValidationError as exc:
        return error_response(
            "INVALID_REQUEST",
            "Invalid tool request",
            details=exc.errors(include_url=False, include_context=False, include_input=False),
        )
    name = validated_request.tool
    spec = _tools().get(name)
    if spec is None:
        return error_response("UNKNOWN_TOOL", f"Unknown tool: {name}", tool=name)
    if validated_request.tool_version not in (None, spec.version):
        return error_response(
            "UNSUPPORTED_VERSION", f"Supported version is {spec.version}", tool=name, spec=spec
        )
    try:
        inputs = spec.input_model.model_validate(validated_request.input)
    except ValidationError as exc:
        return error_response(
            "INVALID_INPUT",
            "Inputs failed validation",
            tool=name,
            spec=spec,
            details=exc.errors(include_url=False, include_context=False, include_input=False),
        )
    try:
        provenance = _provenance(spec, inputs.model_dump(mode="json"))
    except (ValueError, TypeError, OverflowError):
        return error_response(
            "INVALID_INPUT",
            "Inputs cannot be represented as canonical finite JSON",
            tool=name,
            spec=spec,
        )
    try:
        calculation = spec.execute(inputs)
        result = spec.output_model.model_validate(calculation.result)
        return ToolResponse(
            status="ok",
            tool=name,
            tool_version=spec.version,
            result=result.model_dump(mode="json"),
            warnings=calculation.warnings,
            provenance=provenance,
        )
    except ValidationError:
        return error_response(
            "INTERNAL_ERROR",
            "Tool output failed its declared schema",
            tool=name,
            spec=spec,
            provenance=provenance,
        )
    except ValueError as exc:
        return error_response("DOMAIN_ERROR", str(exc), tool=name, spec=spec, provenance=provenance)
    except (OverflowError, ZeroDivisionError, FloatingPointError):
        return error_response(
            "NUMERICAL_ERROR",
            "Calculation exceeds numerical limits",
            tool=name,
            spec=spec,
            provenance=provenance,
        )
    except Exception:
        return error_response(
            "INTERNAL_ERROR",
            "Unexpected tool failure",
            tool=name,
            spec=spec,
            provenance=provenance,
        )


def run_tool(name: str, inputs: dict[str, Any], *, tool_version: str | None = None) -> ToolResponse:
    return run_request({"tool": name, "input": inputs, "tool_version": tool_version})
