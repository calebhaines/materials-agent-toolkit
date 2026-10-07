"""Alloy reference data, conservation laws and fractional-composition contracts.

Reference masses are conventional terrestrial values: Ni 58.6934, Ti 47.867,
Cu 63.546, Zn 65.38, H 1.008 and O 15.999 g/mol (CIAAW atomic-weight table,
https://ciaaw.org/atomic-weights.htm). Reference fractions below were evaluated
independently using 40-digit decimal arithmetic. A 1e-12 relative tolerance
covers binary64 conversion of those tabulated values, not experimental error.
"""

import json
import math
import sys

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit.registry import (
    ToolResponse,
    describe_tool,
    run_tool,
    validate_input,
)

TOOL = "composition.from_fractions"
REFERENCE_REL_TOL = 1e-12


def calculate(fractions, basis="atomic", **options):
    return run_tool(TOOL, {"fractions": fractions, "basis": basis, **options})


def require_success(response):
    assert response.status == "ok", response.error
    assert response.error is None
    result = response.result
    assert result is not None
    # Serialize with strict JSON so a successful envelope cannot hide NaN/Infinity.
    json.dumps(response.model_dump(mode="json"), allow_nan=False)
    for field in ("atomic_fractions", "mass_fractions"):
        assert all(0 < value <= 1 for value in result[field].values())
        assert math.fsum(result[field].values()) == pytest.approx(1, abs=1e-15)
    assert math.isfinite(result["mean_atomic_mass_g_mol"])
    assert result["mean_atomic_mass_g_mol"] > 0
    return result


def require_error(response, codes):
    assert response.status == "error"
    assert response.result is None
    assert response.error is not None
    assert response.error.code in codes
    envelope = response.model_dump(mode="json")
    json.dumps(envelope, allow_nan=False)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(envelope)


def test_equiatomic_niti_reference_and_mass_conservation():
    result = require_success(calculate({"Ni": 0.5, "Ti": 0.5}))
    assert result["atomic_fractions"] == {"Ni": 0.5, "Ti": 0.5}
    assert result["mass_fractions"] == pytest.approx(
        {"Ni": 0.5507993588612655, "Ti": 0.4492006411387345}, rel=REFERENCE_REL_TOL
    )
    assert result["mean_atomic_mass_g_mol"] == pytest.approx(53.2802, rel=REFERENCE_REL_TOL)
    assert 47.867 < result["mean_atomic_mass_g_mol"] < 58.6934
    assert result["input_total"] == 1.0


def test_seventy_thirty_weight_percent_brass_reference():
    result = require_success(
        calculate({"Cu": 70.0, "Zn": 30.0}, basis="mass", normalization="normalize")
    )
    assert result["mass_fractions"] == pytest.approx({"Cu": 0.7, "Zn": 0.3})
    assert result["atomic_fractions"] == pytest.approx(
        {"Cu": 0.7059407864901635, "Zn": 0.2940592135098365}, rel=REFERENCE_REL_TOL
    )
    assert result["mean_atomic_mass_g_mol"] == pytest.approx(
        64.08530459757704, rel=REFERENCE_REL_TOL
    )
    assert result["input_total"] == 100.0


def test_mass_to_atomic_to_mass_round_trip():
    supplied_mass = {"Fe": 0.63, "Ni": 0.21, "Cr": 0.15, "C": 0.01}
    first = require_success(calculate(supplied_mass, basis="mass"))
    second = require_success(calculate(first["atomic_fractions"], basis="atomic"))
    assert second["mass_fractions"] == pytest.approx(supplied_mass, rel=REFERENCE_REL_TOL)
    assert second["mean_atomic_mass_g_mol"] == pytest.approx(
        first["mean_atomic_mass_g_mol"], rel=REFERENCE_REL_TOL
    )


@pytest.mark.parametrize("basis", ["atomic", "mass"])
def test_pure_element_has_unit_fractions_and_elemental_atomic_mass(basis):
    result = require_success(calculate({"Al": 1.0}, basis=basis))
    assert result["atomic_fractions"] == {"Al": 1.0}
    assert result["mass_fractions"] == {"Al": 1.0}
    assert result["mean_atomic_mass_g_mol"] == pytest.approx(26.9815384, rel=REFERENCE_REL_TOL)


def test_water_fractions_agree_with_formula_analysis_but_use_per_atom_molar_mass():
    result = require_success(calculate({"H": 2.0, "O": 1.0}, normalization="normalize"))
    formula = run_tool("composition.analyze", {"formula": "H2O"})
    assert formula.status == "ok", formula.error
    assert result["atomic_fractions"] == pytest.approx(formula.result["atomic_fractions"])
    assert result["mass_fractions"] == pytest.approx(formula.result["mass_fractions"])
    assert result["mean_atomic_mass_g_mol"] == pytest.approx(6.005, rel=REFERENCE_REL_TOL)
    assert 3 * result["mean_atomic_mass_g_mol"] == pytest.approx(18.015)
    assert result["mean_atomic_mass_g_mol"] == pytest.approx(
        formula.result["molar_mass_g_mol"] / 3, rel=REFERENCE_REL_TOL
    )


@pytest.mark.parametrize("basis", ["atomic", "mass"])
@pytest.mark.parametrize("scale", [1e-100, 100.0, 1e100])
def test_explicit_normalization_preserves_composition_under_scaling(basis, scale):
    first = require_success(
        calculate({"Cu": 0.7, "Zn": 0.3}, basis=basis, normalization="normalize")
    )
    scaled = require_success(
        calculate(
            {"Cu": 0.7 * scale, "Zn": 0.3 * scale},
            basis=basis,
            normalization="normalize",
        )
    )
    assert scaled["atomic_fractions"] == pytest.approx(first["atomic_fractions"])
    assert scaled["mass_fractions"] == pytest.approx(first["mass_fractions"])
    assert scaled["mean_atomic_mass_g_mol"] == pytest.approx(
        first["mean_atomic_mass_g_mol"], rel=REFERENCE_REL_TOL
    )
    assert scaled["input_total"] == pytest.approx(scale, rel=REFERENCE_REL_TOL)


@pytest.mark.parametrize("basis", ["atomic", "mass"])
def test_zero_components_are_omitted_without_changing_active_composition(basis):
    result = require_success(calculate({"Al": 1.0, "Ni": 0.0, "Ti": -0.0}, basis=basis))
    assert result["atomic_fractions"] == {"Al": 1.0}
    assert result["mass_fractions"] == {"Al": 1.0}


@pytest.mark.parametrize("delta", [-5e-9, 5e-9])
def test_require_unity_accepts_and_normalizes_within_absolute_tolerance(delta):
    result = require_success(calculate({"Al": 1.0 + delta}))
    assert result["atomic_fractions"] == {"Al": 1.0}
    assert result["mass_fractions"] == {"Al": 1.0}
    assert result["input_total"] == 1.0 + delta


@pytest.mark.parametrize("total", [0.0, 0.5, 100.0, 1.0 - 2e-8, 1.0 + 2e-8])
def test_default_normalization_rejects_nonunit_totals(total):
    require_error(calculate({"Al": total}), {"DOMAIN_ERROR"})


def test_explicit_normalization_rejects_all_zero_weights():
    require_error(
        calculate({"Ni": 0.0, "Ti": 0.0}, normalization="normalize"),
        {"DOMAIN_ERROR"},
    )


@pytest.mark.parametrize(
    "value",
    [
        -0.1,
        math.inf,
        -math.inf,
        math.nan,
        "0.5",
        True,
        None,
        pytest.param(10**5000, id="unrepresentable-integer"),
    ],
)
def test_fraction_values_are_finite_nonnegative_strict_numbers(value):
    require_error(calculate({"Ni": value, "Ti": 0.5}), {"INVALID_INPUT"})


@pytest.mark.parametrize(
    "updates",
    [
        {"fractions": {}},
        {"fractions": []},
        {"fractions": {f"X{i}": 1.0 for i in range(119)}},
        {"basis": "weight"},
        {"basis": "Atomic"},
        {"basis": None},
        {"normalization": "automatic"},
        {"normalization": None},
        {"unknown": 1},
    ],
)
def test_structured_input_contract_rejects_invalid_fields_and_cardinality(updates):
    inputs = {"fractions": {"Ni": 0.5, "Ti": 0.5}, "basis": "atomic", **updates}
    require_error(run_tool(TOOL, inputs), {"INVALID_INPUT"})


def test_basis_is_required():
    require_error(run_tool(TOOL, {"fractions": {"Al": 1.0}}), {"INVALID_INPUT"})


@pytest.mark.parametrize("symbol", ["D", "T", "n", "Xx", "ni", "NI", " Ni", "Ni2", ""])
def test_only_exact_neutral_element_symbols_are_accepted(symbol):
    require_error(calculate({symbol: 1.0}), {"INVALID_INPUT", "DOMAIN_ERROR"})


def test_an_unknown_zero_component_cannot_evade_element_validation():
    require_error(calculate({"Al": 1.0, "D": 0.0}), {"INVALID_INPUT", "DOMAIN_ERROR"})


@pytest.mark.parametrize("basis", ["atomic", "mass"])
@pytest.mark.parametrize("weight", [math.ulp(0.0), sys.float_info.max])
def test_extreme_single_component_weights_normalize_to_pure_material(basis, weight):
    result = require_success(calculate({"Al": weight}, basis=basis, normalization="normalize"))
    assert result["atomic_fractions"] == {"Al": 1.0}
    assert result["mass_fractions"] == {"Al": 1.0}
    assert result["input_total"] == weight


@pytest.mark.parametrize("basis", ["atomic", "mass"])
def test_smallest_equal_weights_remain_a_finite_binary_composition(basis):
    smallest = math.ulp(0.0)
    result = require_success(
        calculate({"Ni": smallest, "Ti": smallest}, basis=basis, normalization="normalize")
    )
    assert result[f"{basis}_fractions"] == {"Ni": 0.5, "Ti": 0.5}
    assert result["input_total"] == 2 * smallest


@pytest.mark.parametrize("basis", ["atomic", "mass"])
def test_finite_trace_component_is_preserved(basis):
    result = require_success(calculate({"H": 1.0, "O": 1e-300}, basis=basis))
    assert result["atomic_fractions"]["O"] > 0
    assert result["mass_fractions"]["O"] > 0


def test_mass_conversion_preserves_recoverable_subnormal_trace_components():
    smallest = math.ulp(0.0)
    supplied = {"H": smallest, "Ni": 2 * smallest, "Og": 1.0}
    result = require_success(calculate(supplied, basis="mass"))
    assert result["mass_fractions"] == supplied
    # Og's representative mass is 294 g/mol. Therefore trace atom fractions
    # increase by factors 294/1.008 and 294/58.6934. Both final values survive
    # binary64 even though computing w_Ni/58.6934 first would round to zero.
    # One subnormal ulp is the appropriate absolute precision at this scale.
    assert result["atomic_fractions"]["H"] == pytest.approx(292 * smallest, rel=0, abs=smallest)
    assert result["atomic_fractions"]["Ni"] == pytest.approx(10 * smallest, rel=0, abs=smallest)


@pytest.mark.parametrize(
    "basis,expected_atomic_be,expected_mass_be",
    [
        ("mass", 7.700686862431812e-301, 1e-300),
        ("atomic", 1e-300, 1.2985854610951008e-300),
    ],
)
def test_near_pure_lithium_preserves_trace_without_fraction_roundoff_above_one(
    basis, expected_atomic_be, expected_mass_be
):
    result = require_success(calculate({"Li": 1.0, "Be": 1e-300}, basis=basis))
    # CIAAW conventional masses Li 6.94 and Be 9.0121831 g/mol. The trace
    # changes the true dominant fraction by far less than one binary64 ulp,
    # so that fraction must round to exactly one while Be remains positive.
    assert result["atomic_fractions"]["Li"] == 1.0
    assert result["mass_fractions"]["Li"] == 1.0
    assert result["atomic_fractions"]["Be"] == pytest.approx(
        expected_atomic_be, rel=REFERENCE_REL_TOL, abs=0
    )
    assert result["mass_fractions"]["Be"] == pytest.approx(
        expected_mass_be, rel=REFERENCE_REL_TOL, abs=0
    )
    assert 6.94 <= result["mean_atomic_mass_g_mol"] <= 9.0121831


@pytest.mark.parametrize("basis", ["atomic", "mass"])
@pytest.mark.parametrize(
    "fractions",
    [
        {"Ni": sys.float_info.max, "Ti": sys.float_info.max},
        {"Ni": sys.float_info.max, "Ti": math.ulp(0.0)},
    ],
)
def test_unrepresentable_totals_or_positive_components_fail_explicitly(basis, fractions):
    require_error(
        calculate(fractions, basis=basis, normalization="normalize"),
        {"DOMAIN_ERROR", "NUMERICAL_ERROR"},
    )


@pytest.mark.parametrize(
    "basis,fractions",
    [
        ("atomic", {"H": math.ulp(0.0), "Og": 1.0}),
        ("mass", {"H": 1.0, "Og": math.ulp(0.0)}),
    ],
)
def test_conversion_cannot_silently_drop_a_positive_component(basis, fractions):
    # The lightest/heaviest-element mass ratio pushes the trace below binary64.
    require_error(calculate(fractions, basis=basis), {"DOMAIN_ERROR"})


def test_hash_is_stable_across_element_order_and_explicit_default():
    implicit = calculate({"Ni": 0.5, "Ti": 0.5})
    explicit = calculate({"Ti": 0.5, "Ni": 0.5}, normalization="require_unity")
    require_success(implicit)
    require_success(explicit)
    assert implicit.result == explicit.result
    assert implicit.provenance.input_sha256 == explicit.provenance.input_sha256


def test_hash_records_raw_validated_weights_even_when_normalized_composition_is_same():
    first = calculate({"Ni": 0.5, "Ti": 0.5}, normalization="normalize")
    second = calculate({"Ni": 50.0, "Ti": 50.0}, normalization="normalize")
    first_result = require_success(first)
    second_result = require_success(second)
    assert first_result["atomic_fractions"] == second_result["atomic_fractions"]
    assert first_result["mass_fractions"] == second_result["mass_fractions"]
    assert first_result["input_total"] != second_result["input_total"]
    assert first.provenance.input_sha256 != second.provenance.input_sha256


def test_discovered_schemas_and_provenance_describe_fractional_calculation():
    descriptor = describe_tool(TOOL)
    inputs = {"fractions": {"Cu": 70.0, "Zn": 30.0}, "basis": "mass", "normalization": "normalize"}
    validated = validate_input(TOOL, inputs)
    response = run_tool(TOOL, inputs, tool_version=descriptor["version"])
    result = require_success(response)
    for schema in (descriptor["input_schema"], descriptor["output_schema"]):
        Draft202012Validator.check_schema(schema)
    fractions_schema = descriptor["input_schema"]["properties"]["fractions"]
    assert fractions_schema["minProperties"] == 1
    assert fractions_schema["maxProperties"] == 118
    Draft202012Validator(descriptor["input_schema"]).validate(validated)
    Draft202012Validator(descriptor["output_schema"]).validate(result)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(
        response.model_dump(mode="json")
    )
    assert descriptor["side_effects"] == []
    assert descriptor["network_access"] is False
    assert descriptor["assumptions"]
    assert descriptor["references"]
    assert "periodictable" in descriptor["dependencies"]
    assert "periodictable" in result["atomic_weights_source"]
    assert response.provenance.software_versions["periodictable"] != "not-installed"
    assert response.provenance.references == descriptor["references"]
    assert response.warnings


def test_new_tool_rejects_unsupported_versions():
    response = run_tool(TOOL, {"fractions": {"Al": 1.0}, "basis": "atomic"}, tool_version="2")
    require_error(response, {"UNSUPPORTED_VERSION"})
