"""Offline discovery contracts remain complete, portable and usable by agents."""

import copy
import json
import platform
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from materials_agent_toolkit import registry
from materials_agent_toolkit.catalog import (
    CATALOG_VERSION,
    ToolCatalog,
    ToolDescriptor,
    catalog_json,
    catalog_schema,
    catalog_schema_json,
    get_catalog,
)

ROOT = Path(__file__).parents[1]
TOOL_NAMES = {
    "composition.analyze",
    "composition.from_fractions",
    "crystal.density",
    "kinetics.arrhenius_diffusivity",
    "mechanics.elastic_vrh",
    "mechanics.isotropic_moduli",
    "mixtures.scalar_bounds",
    "structure.analyze_cif",
    "thermal.linear_expansion",
}


def test_v1_catalog_preserves_existing_descriptors_and_response_contract():
    payload = get_catalog()
    assert CATALOG_VERSION == payload["catalog_version"] == "1"
    assert set(payload) == {"catalog_version", "tools", "response_schema"}
    assert payload["tools"] == registry.list_tools()
    assert payload["response_schema"] == registry.ToolResponse.model_json_schema()
    names = [tool["name"] for tool in payload["tools"]]
    assert names == sorted(TOOL_NAMES)
    assert len(names) == len(set(names))
    for descriptor in payload["tools"]:
        assert descriptor == registry.describe_tool(descriptor["name"])
        assert descriptor["references"]
        assert descriptor["assumptions"]
        assert descriptor["side_effects"] == []
        assert descriptor["network_access"] is False


def test_catalog_and_every_embedded_schema_are_valid_draft_2020_12():
    schema = catalog_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)
    payload = get_catalog()
    Draft202012Validator(schema).validate(payload)
    Draft202012Validator.check_schema(payload["response_schema"])
    Draft202012Validator.check_schema(registry.ToolRequest.model_json_schema())
    for descriptor in payload["tools"]:
        Draft202012Validator.check_schema(descriptor["input_schema"])
        Draft202012Validator.check_schema(descriptor["output_schema"])


@pytest.mark.parametrize(
    "change",
    [
        lambda payload: payload.pop("catalog_version"),
        lambda payload: payload.update(catalog_version="2"),
        lambda payload: payload.update(catalog_version=1),
        lambda payload: payload.update(unknown="unpublished field"),
        lambda payload: payload["tools"][0].update(unknown="unpublished field"),
        lambda payload: payload["tools"][0].update(name=""),
        lambda payload: payload["tools"][0].update(network_access=1),
        lambda payload: payload["tools"][0].update(references=[1]),
    ],
    ids=[
        "missing-version",
        "unsupported-version",
        "numeric-version",
        "outer-extra",
        "descriptor-extra",
        "empty-name",
        "nonboolean-network",
        "nonstring-reference",
    ],
)
def test_published_catalog_schema_and_strict_model_reject_malformed_metadata(change):
    payload = get_catalog()
    change(payload)
    assert not Draft202012Validator(catalog_schema()).is_valid(payload)
    with pytest.raises(ValidationError):
        ToolCatalog.model_validate(payload)


def test_descriptor_strictness_preserves_open_json_schema_documents():
    descriptor = get_catalog()["tools"][0]
    descriptor["input_schema"]["$comment"] = "An optional JSON Schema annotation."
    parsed = ToolDescriptor.model_validate(descriptor)
    assert parsed.model_dump(mode="json") == descriptor
    Draft202012Validator.check_schema(parsed.input_schema)


def test_generation_never_executes_science_collects_provenance_or_connects_to_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Catalog export attempted execution or network access")

    specs = {name: replace(spec, execute=forbidden) for name, spec in registry._tools().items()}
    monkeypatch.setattr(registry, "_tools", lambda: specs)
    monkeypatch.setattr(registry, "run_tool", forbidden)
    monkeypatch.setattr(registry, "run_request", forbidden)
    monkeypatch.setattr(registry, "_provenance", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    assert len(get_catalog()["tools"]) == len(TOOL_NAMES)
    assert json.loads(catalog_json()) == get_catalog()
    assert json.loads(catalog_schema_json()) == catalog_schema()


def test_returned_catalog_and_schema_have_deep_mutation_isolation():
    original = get_catalog()
    mutated = get_catalog()
    mutated["tools"][0]["input_schema"]["properties"]["formula"]["type"] = "integer"
    mutated["tools"][0]["references"].append("Untrusted local edit")
    mutated["response_schema"]["$defs"]["Provenance"]["properties"]["python_version"]["default"] = (
        "host-specific edit"
    )
    mutated["tools"].clear()
    assert get_catalog() == original
    assert registry.list_tools() == original["tools"]
    schema = catalog_schema()
    schema_baseline = copy.deepcopy(schema)
    schema["$defs"]["ToolDescriptor"]["properties"]["version"]["type"] = "integer"
    schema["properties"]["tools"]["items"]["$ref"] = "#/$defs/Unknown"
    assert catalog_schema() == schema_baseline


@pytest.mark.parametrize(
    "factory,render", [(get_catalog, catalog_json), (catalog_schema, catalog_schema_json)]
)
def test_canonical_json_has_sorted_keys_two_space_indent_and_one_final_newline(factory, render):
    expected = (
        json.dumps(factory(), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    output = render()
    assert output == expected == render()
    assert output.endswith("\n") and not output.endswith("\n\n")
    assert "\r" not in output
    assert output.encode("utf-8").decode("utf-8") == output


def test_canonical_json_preserves_unicode_without_ascii_escapes(monkeypatch):
    descriptors = registry.list_tools()
    descriptors[0]["description"] += "; α and Δ remain UTF-8"
    monkeypatch.setattr(registry, "list_tools", lambda: descriptors)
    output = catalog_json()
    assert "α and Δ" in output
    assert "\\u03b1" not in output
    assert json.loads(output)["tools"][0]["description"] == descriptors[0]["description"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("export", [get_catalog, catalog_json])
def test_catalog_exports_reject_nonfinite_values_in_embedded_schema_metadata(
    value, export, monkeypatch
):
    descriptors = registry.list_tools()
    descriptors[0]["input_schema"]["x-invalid-extension"] = value
    monkeypatch.setattr(registry, "list_tools", lambda: descriptors)
    with pytest.raises(ValueError):
        export()


def test_runtime_python_version_is_preserved_without_a_host_specific_schema_default():
    python_property = get_catalog()["response_schema"]["$defs"]["Provenance"]["properties"][
        "python_version"
    ]
    assert python_property["type"] == "string"
    assert "default" not in python_property
    response = registry.run_tool("composition.analyze", {"formula": "H2O"})
    assert response.status == "ok"
    assert response.provenance.python_version == platform.python_version()
    Draft202012Validator(get_catalog()["response_schema"]).validate(
        response.model_dump(mode="json")
    )


def test_host_independent_export_and_execution_time_provenance_in_fresh_process():
    script = """
import json
import platform

runtime = ["98.76.54"]
platform.python_version = lambda: runtime[0]
from materials_agent_toolkit.catalog import catalog_json, catalog_schema_json
from materials_agent_toolkit.registry import run_tool

exported = catalog_json()
schema = catalog_schema_json()
first = run_tool("composition.analyze", {"formula": "H2O"}).provenance.python_version
runtime[0] = "87.65.43"
second = run_tool("composition.analyze", {"formula": "H2O"}).provenance.python_version
print(json.dumps({"catalog": exported, "schema": schema, "versions": [first, second]}))
"""
    process = subprocess.run(
        [sys.executable, "-c", script], text=True, capture_output=True, check=False
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert process.stderr == ""
    observed = json.loads(process.stdout)
    assert observed["catalog"] == catalog_json()
    assert observed["schema"] == catalog_schema_json()
    assert observed["versions"] == ["98.76.54", "87.65.43"]


@pytest.mark.parametrize(
    "example",
    sorted(
        [
            *(ROOT / "examples").glob("*.json"),
            *(ROOT / "examples" / "structures").glob("*.json"),
        ]
    ),
    ids=lambda p: p.name,
)
def test_single_request_examples_validate_the_wrapper_and_exported_raw_input_schema(example):
    request = json.loads(example.read_text(encoding="utf-8"))
    Draft202012Validator(registry.ToolRequest.model_json_schema()).validate(request)
    descriptors = {item["name"]: item for item in get_catalog()["tools"]}
    descriptor = descriptors[request["tool"]]
    assert request.get("tool_version", descriptor["version"]) == descriptor["version"]
    # Validate the original example, including explicitly normalized 70/30 brass weights.
    Draft202012Validator(descriptor["input_schema"]).validate(request["input"])


@pytest.mark.parametrize(
    "example", sorted((ROOT / "examples" / "batch").glob("*.json")), ids=lambda p: p.name
)
def test_batch_examples_validate_envelope_and_items_with_documented_unknown_tools(example):
    payload = json.loads(example.read_text(encoding="utf-8"))
    batch = registry.describe_batch()
    Draft202012Validator.check_schema(batch["request_schema"])
    Draft202012Validator.check_schema(batch["item_request_schema"])
    Draft202012Validator(batch["request_schema"]).validate(payload)
    descriptors = {item["name"]: item for item in get_catalog()["tools"]}
    unknown = []
    for request in payload["requests"]:
        Draft202012Validator(batch["item_request_schema"]).validate(request)
        if request["tool"] not in descriptors:
            unknown.append(request["tool"])
            continue
        descriptor = descriptors[request["tool"]]
        assert request.get("tool_version", descriptor["version"]) == descriptor["version"]
        Draft202012Validator(descriptor["input_schema"]).validate(request["input"])
    # The mixed example demonstrates isolated UNKNOWN_TOOL errors intentionally.
    expected_unknown = {"mixed.json": ["missing.tool"]}
    assert unknown == expected_unknown.get(example.name, [])
