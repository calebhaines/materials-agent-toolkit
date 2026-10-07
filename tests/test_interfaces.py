"""Agent-facing contracts, scientific schema conformance and CLI integration."""

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit.contracts import CalculationResult, StrictModel
from materials_agent_toolkit.registry import (
    ToolResponse,
    describe_tool,
    list_tools,
    run_request,
    run_tool,
    validate_input,
)

STIFFNESS = [
    [168.4, 121.4, 121.4, 0, 0, 0],
    [121.4, 168.4, 121.4, 0, 0, 0],
    [121.4, 121.4, 168.4, 0, 0, 0],
    [0, 0, 0, 75.4, 0, 0],
    [0, 0, 0, 0, 75.4, 0],
    [0, 0, 0, 0, 0, 75.4],
]
CASES = [
    ("composition.analyze", {"formula": "H2O"}),
    ("crystal.density", {"formula": "Al", "formula_units": 4, "cell_volume_angstrom3": 4.05**3}),
    ("mechanics.isotropic_moduli", {"young_modulus": 210, "poisson_ratio": 0.3}),
    ("mechanics.elastic_vrh", {"stiffness_matrix": STIFFNESS}),
    (
        "mixtures.scalar_bounds",
        {"values": [10, 20], "fractions": [0.5, 0.5], "property_unit": "GPa"},
    ),
    (
        "thermal.linear_expansion",
        {"initial_length_m": 1, "expansion_coefficient_per_K": 12e-6, "delta_temperature_K": 100},
    ),
    (
        "kinetics.arrhenius_diffusivity",
        {"pre_exponential_m2_s": 1e-5, "activation_energy_J_mol": 50000, "temperature_K": 1000},
    ),
]


@pytest.mark.parametrize("name,inputs", CASES)
def test_each_tool_conforms_to_discovered_schemas_and_has_provenance(name, inputs):
    descriptor = describe_tool(name)
    normalized = validate_input(name, inputs)
    Draft202012Validator.check_schema(descriptor["input_schema"])
    Draft202012Validator.check_schema(descriptor["output_schema"])
    Draft202012Validator(descriptor["input_schema"]).validate(normalized)
    response = run_tool(name, inputs, tool_version=descriptor["version"])
    assert response.status == "ok", response.error
    Draft202012Validator(descriptor["output_schema"]).validate(response.result)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(
        json.loads(response.model_dump_json())
    )
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert response.provenance.input_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
    assert response.provenance.references
    assert response.provenance.software_versions["pydantic"] == version("pydantic")
    assert "not-installed" not in response.provenance.software_versions.values()


def test_discovery_is_unique_and_deterministic():
    tools = list_tools()
    assert len(tools) == len(CASES)
    names = [tool["name"] for tool in tools]
    assert names == sorted(set(names))
    assert all(tool["side_effects"] == [] and not tool["network_access"] for tool in tools)


def test_hash_is_stable_across_default_and_explicit_unit():
    first = run_tool("mechanics.isotropic_moduli", {"young_modulus": 210, "poisson_ratio": 0.3})
    second = run_tool(
        "mechanics.isotropic_moduli",
        {
            "stress_unit": "GPa",
            "poisson_ratio": 0.3,
            "young_modulus": 210.0,
        },
    )
    assert first.result == second.result
    assert first.provenance.input_sha256 == second.provenance.input_sha256


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"tool": "missing", "input": {}}, "UNKNOWN_TOOL"),
        (
            {"tool": "composition.analyze", "input": {"formula": "H2O"}, "tool_version": "2"},
            "UNSUPPORTED_VERSION",
        ),
        (
            {"tool": "composition.analyze", "input": {"formula": "H2O", "unknown": 1}},
            "INVALID_INPUT",
        ),
        (
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": True, "poisson_ratio": 0.3},
            },
            "INVALID_INPUT",
        ),
        (
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": float("nan"), "poisson_ratio": 0.3},
            },
            "INVALID_INPUT",
        ),
        (
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": "210", "poisson_ratio": 0.3},
            },
            "INVALID_INPUT",
        ),
        ({"tool": "composition.analyze", "input": {"formula": "DoesNotExist"}}, "DOMAIN_ERROR"),
        (
            {
                "tool": "crystal.density",
                "input": {"formula": "Al", "formula_units": 10**5000, "cell_volume_angstrom3": 1},
            },
            "INVALID_INPUT",
        ),
        ({"tool": "composition.analyze"}, "INVALID_REQUEST"),
        ({"tool": "composition.analyze", "input": {}, "unrecognized": 1}, "INVALID_REQUEST"),
        ([], "INVALID_REQUEST"),
    ],
)
def test_errors_are_structured_and_serializable(payload, code):
    response = run_request(payload)
    assert response.status == "error"
    assert response.result is None
    assert response.error.code == code
    json.loads(response.model_dump_json())


def invoke(command, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "materials_agent_toolkit", *command],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_and_python_return_same_scientific_result():
    name, inputs = CASES[0]
    process = invoke(["run"], json.dumps({"tool": name, "input": inputs}))
    assert process.returncode == 0
    assert process.stderr == ""
    assert json.loads(process.stdout)["result"] == run_tool(name, inputs).result


def test_examples_are_executable_and_validate():
    directory = Path(__file__).parents[1] / "examples"
    for example in directory.glob("*.json"):
        text = example.read_text()
        for command in ("run", "validate"):
            process = invoke([command], text)
            assert process.returncode == 0, process.stdout + process.stderr
            assert json.loads(process.stdout)["status"] == "ok"


@pytest.mark.parametrize(
    "stdin",
    [
        "not json",
        '{"tool":"composition.analyze","input":{"formula":"H2O","formula":"CO2"}}',
        '{"tool":"mechanics.isotropic_moduli","input":{"young_modulus":NaN,"poisson_ratio":0.3}}',
        "null",
        "[]",
        "",
    ],
)
def test_cli_rejects_invalid_json_and_requests_with_machine_readable_errors(stdin):
    process = invoke(["run"], stdin)
    assert process.returncode == 2
    assert process.stderr == ""
    response = json.loads(process.stdout)
    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_cli_discovery_and_unknown_tool():
    process = invoke(["list"])
    assert process.returncode == 0
    assert len(json.loads(process.stdout)["tools"]) == len(CASES)
    process = invoke(["describe", "missing"])
    assert process.returncode == 2
    assert json.loads(process.stdout)["status"] == "error"


def test_output_contract_failure_is_an_internal_error(monkeypatch):
    from materials_agent_toolkit import registry

    specs = registry._tools()
    specs["composition.analyze"] = replace(
        specs["composition.analyze"],
        execute=lambda inputs: CalculationResult(StrictModel()),
    )
    monkeypatch.setattr(registry, "_tools", lambda: specs)
    response = run_tool("composition.analyze", {"formula": "H2O"})
    assert response.error.code == "INTERNAL_ERROR"
    assert response.result is None
