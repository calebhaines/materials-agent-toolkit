"""Versioned discovery contracts and reproducible JSON catalog exports.

Catalog generation describes the installed tools without executing calculations,
fetching data or importing the optional MCP SDK. Canonical exports are UTF-8 JSON
with sorted object keys, two-space indentation and exactly one trailing newline.
"""

import json
from typing import Annotated, Any, Literal

from pydantic import Field

from materials_agent_toolkit import registry
from materials_agent_toolkit.contracts import StrictModel

CATALOG_VERSION = "1"
_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_NonEmptyString = Annotated[str, Field(min_length=1)]


class ToolDescriptor(StrictModel):
    """Discoverable scientific contract, independent of a tool's implementation."""

    name: _NonEmptyString
    version: _NonEmptyString
    description: _NonEmptyString
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    assumptions: list[_NonEmptyString]
    references: list[_NonEmptyString]
    dependencies: list[_NonEmptyString]
    side_effects: list[_NonEmptyString]
    network_access: bool
    cost: _NonEmptyString


class ToolCatalog(StrictModel):
    """Version 1 catalog matching the existing MCP catalog resource."""

    catalog_version: Literal["1"] = Field(description="Catalog discovery contract version.")
    tools: list[ToolDescriptor]
    response_schema: dict[str, Any]


def get_catalog() -> dict[str, Any]:
    """Return a fresh validated catalog with tools sorted by their unique names."""
    catalog = ToolCatalog(
        catalog_version=CATALOG_VERSION,
        tools=registry.list_tools(),
        response_schema=registry.ToolResponse.model_json_schema(),
    )
    # Preserve open-schema values until JSON validation: Pydantic's JSON mode
    # silently maps non-finite floats in ``Any`` metadata to null.
    payload = catalog.model_dump(mode="python")
    json.dumps(payload, allow_nan=False)
    return payload


def catalog_schema() -> dict[str, Any]:
    """Return the strict catalog JSON Schema, including its Draft 2020-12 dialect."""
    return {"$schema": _JSON_SCHEMA_DIALECT, **ToolCatalog.model_json_schema()}


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def catalog_json() -> str:
    """Render the live catalog as canonical JSON without host-specific metadata."""
    return _canonical_json(get_catalog())


def catalog_schema_json() -> str:
    """Render the catalog contract schema using the same canonical JSON encoding."""
    return _canonical_json(catalog_schema())
