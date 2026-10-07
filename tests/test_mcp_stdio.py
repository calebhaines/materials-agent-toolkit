"""Exercise the real stdio server with the official MCP client, including shutdown."""

import json
import math
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit.registry import ToolResponse, list_tools, run_tool

mcp = pytest.importorskip("mcp", reason="Install the optional mcp extra for stdio tests")
anyio = pytest.importorskip("anyio")
stdio_client = pytest.importorskip("mcp.client.stdio").stdio_client

COPPER_STIFFNESS = [
    [168.4, 121.4, 121.4, 0, 0, 0],
    [121.4, 168.4, 121.4, 0, 0, 0],
    [121.4, 121.4, 168.4, 0, 0, 0],
    [0, 0, 0, 75.4, 0, 0],
    [0, 0, 0, 0, 75.4, 0],
    [0, 0, 0, 0, 0, 75.4],
]
CASES = [
    ("composition.analyze", {"formula": "H2O"}, {"molar_mass_g_mol": 18.015}),
    (
        "composition.from_fractions",
        {"fractions": {"Ni": 0.5, "Ti": 0.5}, "basis": "atomic"},
        {
            "atomic_fractions": {"Ni": 0.5, "Ti": 0.5},
            "mass_fractions": {
                "Ni": 58.6934 / (58.6934 + 47.867),
                "Ti": 47.867 / (58.6934 + 47.867),
            },
            "mean_atomic_mass_g_mol": 53.2802,
            "input_total": 1.0,
        },
    ),
    (
        "crystal.density",
        {"formula": "Al", "formula_units": 4, "cell_volume_angstrom3": 4.05**3},
        {"density_kg_m3": 2697.806069499},
    ),
    (
        "mechanics.isotropic_moduli",
        {"young_modulus": 210, "poisson_ratio": 0.3},
        {"bulk_modulus": 175.0, "shear_modulus": 80.76923076923077},
    ),
    (
        "mechanics.elastic_vrh",
        {"stiffness_matrix": COPPER_STIFFNESS},
        {"bulk_modulus_hill": 137.06666666666666, "shear_modulus_voigt": 54.64},
    ),
    (
        "mixtures.scalar_bounds",
        {"values": [10, 20], "fractions": [0.5, 0.5], "property_unit": "GPa"},
        {"voigt_bound": 15.0, "reuss_bound": 40.0 / 3.0},
    ),
    (
        "thermal.linear_expansion",
        {"initial_length_m": 1, "expansion_coefficient_per_K": 12e-6, "delta_temperature_K": 100},
        {"delta_length_m": 0.0012, "final_length_m": 1.0012},
    ),
    (
        "kinetics.arrhenius_diffusivity",
        {"pre_exponential_m2_s": 1e-5, "activation_energy_J_mol": 50000, "temperature_K": 1000},
        {"diffusivity_m2_s": 1e-5 * math.exp(-50000 / (8.31446261815324 * 1000))},
    ),
]


@asynccontextmanager
async def initialized_session():
    """Keep process launch, requests and orderly teardown inside one deadline."""
    parameters = mcp.StdioServerParameters(
        command=sys.executable, args=["-m", "materials_agent_toolkit.mcp_server"]
    )
    with anyio.fail_after(30):
        async with stdio_client(parameters) as (read, write):
            async with mcp.ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.capabilities.tools is not None
                assert initialized.capabilities.resources is not None
                yield session


def response_envelope(result, schema):
    """Require equal machine-readable and text content, valid against discovery."""
    assert result.structuredContent is not None
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    envelope = json.loads(result.content[0].text)
    assert envelope == result.structuredContent
    Draft202012Validator(schema).validate(envelope)
    assert result.isError == (envelope["status"] == "error")
    timestamp = datetime.fromisoformat(envelope["provenance"]["created_at"])
    assert timestamp.utcoffset() == timedelta(0)
    return envelope


@pytest.mark.parametrize("name,inputs,reference", CASES, ids=[case[0] for case in CASES])
def test_mcp_scientific_results_schemas_and_provenance_match_python(name, inputs, reference):
    async def exercise():
        async with initialized_session() as session:
            discovered = {tool.name: tool for tool in (await session.list_tools()).tools}
            tool = discovered[name]
            assert tool.outputSchema == ToolResponse.model_json_schema()
            envelope = response_envelope(await session.call_tool(name, inputs), tool.outputSchema)
            assert envelope["status"] == "ok", envelope["error"]
            for field, expected in reference.items():
                assert envelope["result"][field] == pytest.approx(expected, rel=1e-8)
            expected = run_tool(name, inputs).model_dump(mode="json")
            # Executions have separate timestamps; all scientific content and
            # input hashes, references and dependency versions must agree.
            envelope["provenance"].pop("created_at")
            expected["provenance"].pop("created_at")
            assert envelope == expected

    anyio.run(exercise)


def test_mcp_discovery_and_resources_preserve_full_registry_contract():
    async def exercise():
        async with initialized_session() as session:
            expected = {tool["name"]: tool for tool in list_tools()}
            discovered = (await session.list_tools()).tools
            assert [tool.name for tool in discovered] == sorted(expected)
            for tool in discovered:
                assert tool.inputSchema == expected[tool.name]["input_schema"]
                Draft202012Validator.check_schema(tool.inputSchema)
                Draft202012Validator.check_schema(tool.outputSchema)
                assert tool.annotations.readOnlyHint is True
                assert tool.annotations.destructiveHint is False
                assert tool.annotations.openWorldHint is False

            resources = (await session.list_resources()).resources
            assert {str(resource.uri) for resource in resources} == {
                "materials://catalog",
                "materials://schemas/response",
            }
            catalog_result = await session.read_resource("materials://catalog")
            assert len(catalog_result.contents) == 1
            assert catalog_result.contents[0].mimeType == "application/json"
            catalog = json.loads(catalog_result.contents[0].text)
            assert "catalog_version" in catalog
            assert catalog["tools"] == list_tools()
            assert catalog["response_schema"] == ToolResponse.model_json_schema()
            schema_result = await session.read_resource("materials://schemas/response")
            assert len(schema_result.contents) == 1
            schema = json.loads(schema_result.contents[0].text)
            assert schema == ToolResponse.model_json_schema()

    anyio.run(exercise)


def test_mcp_error_envelopes_preserve_session_for_following_calls():
    cases = [
        ("composition.analyze", None, "INVALID_INPUT"),
        ("composition.analyze", {"formula": "H2O", "unknown": 1}, "INVALID_INPUT"),
        (
            "composition.from_fractions",
            {"fractions": {"Ni": True, "Ti": 0.5}, "basis": "atomic"},
            "INVALID_INPUT",
        ),
        ("composition.from_fractions", {"fractions": {"Ni": 1.0}}, "INVALID_INPUT"),
        (
            "mechanics.isotropic_moduli",
            {"young_modulus": True, "poisson_ratio": 0.3},
            "INVALID_INPUT",
        ),
        (
            "mechanics.isotropic_moduli",
            {"young_modulus": 210, "poisson_ratio": 0.5},
            "INVALID_INPUT",
        ),
        (
            "mechanics.isotropic_moduli",
            {"young_modulus": "210", "poisson_ratio": 0.3},
            "INVALID_INPUT",
        ),
        ("composition.analyze", {"formula": "NotAnElement"}, "DOMAIN_ERROR"),
        ("missing.tool", {}, "UNKNOWN_TOOL"),
    ]

    async def exercise():
        async with initialized_session() as session:
            discovered = {tool.name: tool for tool in (await session.list_tools()).tools}
            schema = discovered["composition.analyze"].outputSchema
            for name, inputs, code in cases:
                envelope = response_envelope(await session.call_tool(name, inputs), schema)
                assert envelope["status"] == "error"
                assert envelope["result"] is None
                assert envelope["tool"] == name
                assert envelope["error"]["code"] == code
                successful = response_envelope(
                    await session.call_tool("composition.analyze", {"formula": "H2O"}), schema
                )
                assert successful["status"] == "ok"
                assert successful["result"]["atomic_counts"] == {"H": 2, "O": 1}

    anyio.run(exercise)
