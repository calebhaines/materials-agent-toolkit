"""Independent physical-unit references and evidence eligibility checks.

The reference tuples below express the same known quantity in different units.
Their SI values are fixed examples, not values calculated with the tool's unit
table. Approximate assertions cover binary64 representation only; screening
decisions themselves must use exact inclusive comparisons without tolerance.
"""

import copy
import hashlib
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

TOOL = "screening.evaluate"

# quantity, SI symbol, independently specified SI value, equivalent input pairs.
UNIT_REFERENCES = [
    ("density", "kg/m3", 2000.0, [("kg/m3", 2000.0), ("g/cm3", 2.0), ("g/mL", 2.0)]),
    (
        "elastic_modulus",
        "Pa",
        3_000_000_000.0,
        [("Pa", 3_000_000_000.0), ("kPa", 3_000_000.0), ("MPa", 3000.0), ("GPa", 3.0)],
    ),
    ("thermal_conductivity", "W/(m*K)", 100.0, [("W/(m*K)", 100.0), ("W/(cm*K)", 1.0)]),
    (
        "linear_expansion_coefficient",
        "1/K",
        -0.000012,
        [("1/K", -0.000012), ("1/degC", -0.000012), ("microstrain/K", -12.0)],
    ),
    (
        "specific_capacity",
        "C/kg",
        720_000.0,
        [("C/kg", 720_000.0), ("Ah/kg", 200.0), ("mAh/g", 200.0)],
    ),
    ("mass_fraction", "1", 0.25, [("1", 0.25), ("%", 25.0)]),
    ("length", "m", 0.002, [("m", 0.002), ("cm", 0.2), ("mm", 2.0), ("um", 2000.0)]),
    ("area", "m2", 0.0002, [("m2", 0.0002), ("cm2", 2.0), ("mm2", 200.0)]),
    (
        "volume",
        "m3",
        0.002,
        [("m3", 0.002), ("L", 2.0), ("mL", 2000.0), ("cm3", 2000.0)],
    ),
    ("mass", "kg", 0.002, [("kg", 0.002), ("g", 2.0), ("mg", 2000.0)]),
    ("time", "s", 7200.0, [("s", 7200.0), ("min", 120.0), ("h", 2.0)]),
    ("temperature", "K", 273.15, [("K", 273.15), ("degC", 0.0)]),
    ("diffusivity", "m2/s", 0.0002, [("m2/s", 0.0002), ("cm2/s", 2.0)]),
    ("dimensionless", "1", -3.5, [("1", -3.5)]),
]

UNIT_MAP = {
    "density": ("kg/m3", {"kg/m3": (1.0, 0.0), "g/cm3": (1000.0, 0.0), "g/mL": (1000.0, 0.0)}),
    "elastic_modulus": (
        "Pa",
        {"Pa": (1.0, 0.0), "kPa": (1000.0, 0.0), "MPa": (1e6, 0.0), "GPa": (1e9, 0.0)},
    ),
    "thermal_conductivity": ("W/(m*K)", {"W/(m*K)": (1.0, 0.0), "W/(cm*K)": (100.0, 0.0)}),
    "linear_expansion_coefficient": (
        "1/K",
        {"1/K": (1.0, 0.0), "1/degC": (1.0, 0.0), "microstrain/K": (1e-6, 0.0)},
    ),
    "specific_capacity": (
        "C/kg",
        {"C/kg": (1.0, 0.0), "Ah/kg": (3600.0, 0.0), "mAh/g": (3600.0, 0.0)},
    ),
    "mass_fraction": ("1", {"1": (1.0, 0.0), "%": (0.01, 0.0)}),
    "length": ("m", {"m": (1.0, 0.0), "cm": (0.01, 0.0), "mm": (0.001, 0.0), "um": (1e-6, 0.0)}),
    "area": ("m2", {"m2": (1.0, 0.0), "cm2": (1e-4, 0.0), "mm2": (1e-6, 0.0)}),
    "volume": ("m3", {"m3": (1.0, 0.0), "L": (0.001, 0.0), "mL": (1e-6, 0.0), "cm3": (1e-6, 0.0)}),
    "mass": ("kg", {"kg": (1.0, 0.0), "g": (0.001, 0.0), "mg": (1e-6, 0.0)}),
    "time": ("s", {"s": (1.0, 0.0), "min": (60.0, 0.0), "h": (3600.0, 0.0)}),
    "temperature": ("K", {"K": (1.0, 0.0), "degC": (1.0, 273.15)}),
    "diffusivity": ("m2/s", {"m2/s": (1.0, 0.0), "cm2/s": (1e-4, 0.0)}),
    "dimensionless": ("1", {"1": (1.0, 0.0)}),
}


def property_record(quantity="density", value=2.0, unit="g/cm3", **updates):
    return {
        "quantity": quantity,
        "value": value,
        "unit": unit,
        "evidence_kind": "measurement",
        "source": {"citation": "Synthetic supplied data; no material was measured."},
        **updates,
    }


def constraint(property_id="density", quantity="density", unit="kg/m3", **updates):
    return {
        "constraint_id": "density_limit",
        "property_id": property_id,
        "quantity": quantity,
        "unit": unit,
        "minimum": 1000.0,
        "maximum": 3000.0,
        **updates,
    }


def request(record=None, criterion=None):
    return {
        "candidates": [
            {"candidate_id": "synthetic", "properties": {"density": record or property_record()}}
        ],
        "constraints": [criterion or constraint()],
    }


def success(inputs):
    response = run_tool(TOOL, inputs)
    assert response.status == "ok", response.error
    assert response.error is None
    assert response.result is not None
    json.dumps(response.model_dump(mode="json"), allow_nan=False)
    return response


def rejected(inputs, codes=("INVALID_INPUT", "DOMAIN_ERROR")):
    response = run_tool(TOOL, inputs)
    assert response.status == "error"
    assert response.result is None
    assert response.error is not None
    assert response.error.code in codes
    envelope = response.model_dump(mode="json")
    json.dumps(envelope, allow_nan=False)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(envelope)
    return response


@pytest.mark.parametrize("quantity,si_unit,expected,pairs", UNIT_REFERENCES)
def test_every_compatible_unit_pair_has_independent_si_reference(
    quantity, si_unit, expected, pairs
):
    # Each criterion is expressed in every accepted unit; every candidate must
    # pass all of them. A zero-width threshold would conflate binary64 rounding
    # of different decimal input spellings with unit equivalence.
    inputs = {
        "candidates": [
            {
                "candidate_id": f"c{i}",
                "properties": {"value": property_record(quantity, value, unit)},
            }
            for i, (unit, value) in enumerate(pairs)
        ],
        "constraints": [
            constraint(
                "value",
                quantity,
                unit,
                constraint_id=f"bound{i}",
                minimum=min(value * 0.5, value * 1.5) if value else -1.0,
                maximum=max(value * 0.5, value * 1.5) if value else 1.0,
            )
            for i, (unit, value) in enumerate(pairs)
        ],
    }
    result = success(inputs).result
    assert result["summary"] == {
        "total": len(pairs),
        "passed": len(pairs),
        "failed": 0,
        "unknown": 0,
    }
    for i, candidate in enumerate(result["candidates"]):
        assert candidate["candidate_id"] == f"c{i}"
        record = candidate["properties"]["value"]
        assert record["normalized_value"] == pytest.approx(expected, rel=1e-14, abs=0)
        assert record["si_unit"] == si_unit
        assert record["unit"] == pairs[i][0]
        assert record["value"] == pairs[i][1]
        assert [check["constraint_id"] for check in candidate["checks"]] == [
            f"bound{j}" for j in range(len(pairs))
        ]
        assert all(check["status"] == "pass" for check in candidate["checks"])
    assert all(item["si_unit"] == si_unit for item in result["normalized_constraints"])


def test_temperature_is_affine_and_interval_bounds_convert_to_absolute_temperature():
    record = property_record(
        "temperature",
        25.0,
        "degC",
        interval={"lower": 20.0, "upper": 30.0, "basis": "Supplied possibility range"},
    )
    result = success(
        request(
            record, constraint(quantity="temperature", unit="K", minimum=293.15, maximum=303.15)
        )
    ).result
    normalized = result["candidates"][0]["properties"]["density"]
    assert normalized["normalized_value"] == 298.15
    assert normalized["normalized_interval"] == {
        "lower": 293.15,
        "upper": 303.15,
        "basis": "Supplied possibility range",
    }
    assert result["candidates"][0]["status"] == "pass"


def test_temperature_thresholds_convert_as_absolute_values_not_temperature_changes():
    result = success(
        request(
            property_record("temperature", 300.0, "K"),
            constraint(quantity="temperature", unit="degC", minimum=20.0, maximum=30.0),
        )
    ).result
    normalized = result["normalized_constraints"][0]
    assert normalized["minimum"] == 20.0
    assert normalized["maximum"] == 30.0
    assert normalized["normalized_minimum"] == 293.15
    assert normalized["normalized_maximum"] == 303.15
    assert result["candidates"][0]["status"] == "pass"


@pytest.mark.parametrize(
    "value,interval,minimum,maximum,status,reason",
    [
        (2.0, None, 2.0, 3.0, "pass", "within_bounds"),
        (3.0, None, 2.0, 3.0, "pass", "within_bounds"),
        (2.0, None, 2.0, 2.0, "pass", "within_bounds"),
        (1.0, None, 2.0, 3.0, "fail", "outside_bounds"),
        (4.0, None, 2.0, 3.0, "fail", "outside_bounds"),
        (2.5, (2.0, 3.0), 2.0, 3.0, "pass", "within_bounds"),
        (2.0, (2.0, 2.0), 2.0, 2.0, "pass", "within_bounds"),
        (1.5, (1.0, 2.0), 2.0, 3.0, "unknown", "interval_overlaps_bound"),
        (3.5, (3.0, 4.0), 2.0, 3.0, "unknown", "interval_overlaps_bound"),
        (2.0, (1.0, 4.0), 2.0, 3.0, "unknown", "interval_overlaps_bound"),
        (1.5, (1.0, 1.9), 2.0, 3.0, "fail", "outside_bounds"),
        (3.5, (3.1, 4.0), 2.0, 3.0, "fail", "outside_bounds"),
        (2.0, (1.0, 3.0), 2.0, None, "unknown", "interval_overlaps_bound"),
        (2.0, (1.0, 3.0), None, 2.0, "unknown", "interval_overlaps_bound"),
        (2.0, (2.0, 4.0), 2.0, None, "pass", "within_bounds"),
        (2.0, (0.0, 2.0), None, 2.0, "pass", "within_bounds"),
    ],
)
def test_exact_inclusive_point_and_possibility_range_semantics(
    value, interval, minimum, maximum, status, reason
):
    record = property_record("dimensionless", value, "1")
    if interval:
        record["interval"] = {
            "lower": interval[0],
            "upper": interval[1],
            "basis": "Supplied range, not a confidence interval",
        }
    result = success(
        request(
            record, constraint(quantity="dimensionless", unit="1", minimum=minimum, maximum=maximum)
        )
    ).result
    candidate = result["candidates"][0]
    assert candidate["status"] == status
    assert candidate["checks"] == [
        {
            "constraint_id": "density_limit",
            "property_id": "density",
            "status": status,
            "reason": reason,
        }
    ]


@pytest.mark.parametrize("direction", [-math.inf, math.inf])
def test_one_ulp_outside_equal_bounds_is_a_failure(direction):
    result = success(
        request(
            property_record("dimensionless", math.nextafter(2.0, direction), "1"),
            constraint(quantity="dimensionless", unit="1", minimum=2.0, maximum=2.0),
        )
    ).result
    assert result["candidates"][0]["status"] == "fail"


def test_missing_distinct_property_does_not_infer_dimensional_or_semantic_equivalence():
    inputs = {
        "candidates": [
            {
                "candidate_id": "missing",
                "properties": {
                    "theoretical_capacity": property_record("specific_capacity", 200.0, "mAh/g")
                },
            }
        ],
        "constraints": [
            constraint(
                "reversible_capacity", "specific_capacity", "mAh/g", minimum=100.0, maximum=None
            )
        ],
    }
    result = success(inputs).result
    assert result["candidates"][0]["checks"][0]["reason"] == "missing_property"
    assert result["summary"] == {"total": 1, "passed": 0, "failed": 0, "unknown": 1}
    assert set(result["candidates"][0]["properties"]) == {"theoretical_capacity"}


@pytest.mark.parametrize("kind", ["manufacturer", "calculation", "assumption"])
def test_default_eligibility_requires_measurement_even_if_numerical_value_passes(kind):
    result = success(request(property_record(evidence_kind=kind))).result
    assert result["candidates"][0]["checks"][0]["reason"] == "evidence_not_allowed"
    assert result["candidates"][0]["status"] == "unknown"


def test_eligibility_order_and_fail_precedence_preserve_every_check():
    inputs = {
        "candidates": [
            {
                "candidate_id": "mixed",
                "properties": {
                    "ineligible": property_record(
                        value=20.0, evidence_kind="calculation", conditions={"temperature": "25 C"}
                    ),
                    "wrong_context": property_record(
                        value=20.0, conditions={"temperature": "25 C"}
                    ),
                    "fail": property_record(value=20.0),
                    "pass": property_record(),
                },
            }
        ],
        "constraints": [
            constraint("missing", constraint_id="absent"),
            constraint(
                "ineligible", constraint_id="evidence", required_conditions={"temperature": "30 C"}
            ),
            constraint(
                "wrong_context",
                constraint_id="context",
                required_conditions={"temperature": "30 C"},
            ),
            constraint("fail", constraint_id="failure"),
            constraint("pass", constraint_id="success"),
        ],
    }
    result = success(inputs).result
    candidate = result["candidates"][0]
    assert candidate["status"] == "fail"
    assert [(check["status"], check["reason"]) for check in candidate["checks"]] == [
        ("unknown", "missing_property"),
        ("unknown", "evidence_not_allowed"),
        ("unknown", "condition_mismatch"),
        ("fail", "outside_bounds"),
        ("pass", "within_bounds"),
    ]
    assert result["summary"] == {"total": 1, "passed": 0, "failed": 1, "unknown": 0}


def test_multiple_candidate_summary_and_input_order_are_preserved():
    inputs = {
        "candidates": [
            {"candidate_id": "z_failed", "properties": {"density": property_record(value=4.0)}},
            {"candidate_id": "a_missing", "properties": {}},
            {"candidate_id": "m_passed", "properties": {"density": property_record()}},
        ],
        "constraints": [
            constraint(constraint_id="z_bound"),
            constraint(constraint_id="a_bound", minimum=1500.0),
        ],
    }
    result = success(inputs).result
    assert result["summary"] == {"total": 3, "passed": 1, "failed": 1, "unknown": 1}
    assert [(item["candidate_id"], item["status"]) for item in result["candidates"]] == [
        ("z_failed", "fail"),
        ("a_missing", "unknown"),
        ("m_passed", "pass"),
    ]
    assert [item["constraint_id"] for item in result["normalized_constraints"]] == [
        "z_bound",
        "a_bound",
    ]
    assert all(
        [check["constraint_id"] for check in item["checks"]] == ["z_bound", "a_bound"]
        for item in result["candidates"]
    )


@pytest.mark.parametrize(
    "conditions", [{}, {"temperature": "25C"}, {"temperature": "25 C", "humidity": "50%"}]
)
def test_required_context_tags_are_matched_exactly_without_unit_or_text_inference(conditions):
    result = success(
        request(
            property_record(conditions=conditions),
            constraint(required_conditions={"temperature": "25 C", "humidity": "dry"}),
        )
    ).result
    assert result["candidates"][0]["checks"][0]["reason"] == "condition_mismatch"


def test_sources_original_inputs_ranges_and_extra_context_are_retained():
    source = {
        "citation": "Synthetic example with an unverified citation",
        "locator": "table 2, row 4",
    }
    conditions = {
        "temperature": "25 C",
        "method": "method supplied by caller",
        "unrequired": "not checked",
    }
    interval = {"lower": 1.9, "upper": 2.1, "basis": "Caller-supplied possibility range"}
    criterion = constraint(
        unit="g/mL",
        minimum=1.8,
        maximum=2.2,
        allowed_evidence=["calculation", "measurement"],
        required_conditions={"temperature": "25 C"},
    )
    response = success(
        request(
            property_record(
                source=source, conditions=conditions, interval=interval, evidence_kind="calculation"
            ),
            criterion,
        )
    )
    result = response.result
    record = result["candidates"][0]["properties"]["density"]
    assert record["source"] == source
    assert record["conditions"] == conditions
    assert record["value"] == 2.0 and record["unit"] == "g/cm3"
    assert record["interval"] == interval
    assert record["normalized_interval"] == {
        "lower": 1900.0,
        "upper": 2100.0,
        "basis": interval["basis"],
    }
    normalized = result["normalized_constraints"][0]
    assert normalized["minimum"] == 1.8 and normalized["maximum"] == 2.2
    assert normalized["unit"] == "g/mL"
    assert normalized["normalized_minimum"] == 1800.0
    assert normalized["normalized_maximum"] == 2200.0
    assert normalized["allowed_evidence"] == ["calculation", "measurement"]
    assert normalized["required_conditions"] == {"temperature": "25 C"}
    assert result["candidates"][0]["status"] == "pass"
    assert response.warnings
    assert any(
        "required" in warning.lower() and "context" in warning.lower()
        for warning in response.warnings
    )
    assert "ranking" not in result and "winner" not in result


@pytest.mark.parametrize("location", ["other_candidate", "constraint", "other_constraint"])
def test_same_property_identifier_requires_one_quantity_across_the_entire_request(location):
    inputs = request()
    if location == "other_candidate":
        inputs["candidates"].append(
            {
                "candidate_id": "other",
                "properties": {"density": property_record("mass_fraction", 0.5, "1")},
            }
        )
    elif location == "constraint":
        inputs["constraints"][0].update(
            quantity="mass_fraction", unit="1", minimum=0.0, maximum=1.0
        )
    else:
        inputs["constraints"].append(
            constraint(
                quantity="mass_fraction", unit="1", minimum=0.0, maximum=1.0, constraint_id="other"
            )
        )
    rejected(inputs)


@pytest.mark.parametrize("location", ["record", "criterion"])
@pytest.mark.parametrize("unit", ["kg", "g/cc", "GPa", " K", "g/cm³", "kg/m^3"])
def test_dimension_conflicts_and_unpublished_aliases_are_rejected(location, unit):
    inputs = request()
    if location == "record":
        inputs["candidates"][0]["properties"]["density"]["unit"] = unit
    else:
        inputs["constraints"][0]["unit"] = unit
    rejected(inputs)


@pytest.mark.parametrize(
    "quantity,value,unit",
    [
        ("density", 0.0, "kg/m3"),
        ("density", -1.0, "g/mL"),
        ("elastic_modulus", 0.0, "Pa"),
        ("elastic_modulus", -1.0, "GPa"),
        ("thermal_conductivity", 0.0, "W/(m*K)"),
        ("specific_capacity", -1.0, "mAh/g"),
        ("mass_fraction", -0.1, "1"),
        ("mass_fraction", 1.01, "1"),
        ("mass_fraction", 101.0, "%"),
        ("length", -1.0, "mm"),
        ("area", -1.0, "cm2"),
        ("volume", -1.0, "mL"),
        ("mass", -1.0, "g"),
        ("time", -1.0, "min"),
        ("temperature", -1.0, "K"),
        ("temperature", -273.150001, "degC"),
        ("diffusivity", -1.0, "cm2/s"),
    ],
)
def test_named_physical_quantity_domains_are_enforced(quantity, value, unit):
    rejected(
        request(
            property_record(quantity, value, unit),
            constraint(quantity=quantity, unit=unit, minimum=0.0, maximum=None),
        )
    )


@pytest.mark.parametrize(
    "quantity,value,unit",
    [
        ("specific_capacity", 0.0, "mAh/g"),
        ("mass_fraction", 0.0, "%"),
        ("mass_fraction", 100.0, "%"),
        ("length", 0.0, "mm"),
        ("area", 0.0, "cm2"),
        ("volume", 0.0, "mL"),
        ("mass", 0.0, "g"),
        ("time", 0.0, "h"),
        ("temperature", 0.0, "K"),
        ("temperature", -273.15, "degC"),
        ("diffusivity", 0.0, "cm2/s"),
        ("linear_expansion_coefficient", -12.0, "microstrain/K"),
        ("dimensionless", -10.0, "1"),
    ],
)
def test_zero_and_signed_values_are_valid_in_their_declared_domains(quantity, value, unit):
    response = success(
        request(
            property_record(quantity, value, unit),
            constraint(quantity=quantity, unit=unit, minimum=value, maximum=value),
        )
    )
    assert response.result["candidates"][0]["status"] == "pass"


def test_criterion_can_request_physically_unachievable_values_without_invalidating_input():
    result = success(
        request(
            property_record("mass_fraction", 0.5, "1"),
            constraint(quantity="mass_fraction", unit="%", minimum=110.0, maximum=120.0),
        )
    ).result
    assert result["candidates"][0]["status"] == "fail"


@pytest.mark.parametrize(
    "record",
    [
        property_record(
            interval={"lower": 0.0, "upper": 3.0, "basis": "Positive density required"}
        ),
        property_record(
            "mass_fraction",
            0.5,
            "1",
            interval={"lower": 0.0, "upper": 1.1, "basis": "Outside fractional domain"},
        ),
        property_record(
            "temperature",
            0.0,
            "degC",
            interval={"lower": -274.0, "upper": 1.0, "basis": "Below absolute zero"},
        ),
        property_record(interval={"lower": 2.1, "upper": 3.0, "basis": "Value below range"}),
        property_record(interval={"lower": 1.0, "upper": 1.9, "basis": "Value above range"}),
        property_record(interval={"lower": 3.0, "upper": 1.0, "basis": "Reversed range"}),
    ],
)
def test_possibility_interval_obeys_quantity_domain_and_contains_supplied_value(record):
    rejected(
        request(
            record,
            constraint(
                quantity=record["quantity"], unit=record["unit"], minimum=None, maximum=10.0
            ),
        )
    )


@pytest.mark.parametrize("location", ["value", "lower", "upper", "minimum", "maximum"])
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        "2.0",
        math.nan,
        math.inf,
        -math.inf,
        None,
        pytest.param(10**5000, id="huge-integer"),
    ],
)
def test_numeric_fields_are_strict_and_finite(location, value):
    inputs = request(
        property_record(interval={"lower": 1.0, "upper": 3.0, "basis": "Supplied range"})
    )
    if location == "value":
        inputs["candidates"][0]["properties"]["density"]["value"] = value
    elif location in {"lower", "upper"}:
        inputs["candidates"][0]["properties"]["density"]["interval"][location] = value
    else:
        inputs["constraints"][0][location] = value
        if value is None:
            inputs["constraints"][0]["minimum"] = None
            inputs["constraints"][0]["maximum"] = None
    rejected(inputs, ("INVALID_INPUT",))


@pytest.mark.parametrize("location", ["record", "interval", "criterion"])
@pytest.mark.parametrize("kind", ["overflow", "underflow"])
def test_conversion_overflow_and_nonzero_underflow_have_structured_errors(location, kind):
    if kind == "overflow":
        quantity, unit, value = "density", "g/cm3", sys.float_info.max
        record = property_record(quantity, 1.0, unit)
    else:
        quantity, unit, value = "length", "um", math.ulp(0.0)
        record = property_record(quantity, 1.0, unit)
    criterion = constraint(quantity=quantity, unit=unit, minimum=0.0, maximum=None)
    if location == "record":
        record["value"] = value
    elif location == "interval":
        record["interval"] = {
            "lower": 1.0 if kind == "overflow" else value,
            "upper": value if kind == "overflow" else 2.0,
            "basis": "Conversion extreme",
        }
    else:
        criterion["maximum"] = value
    rejected(request(record, criterion))


@pytest.mark.parametrize(
    "location", ["input", "candidate", "record", "source", "interval", "criterion"]
)
def test_unknown_fields_are_rejected_at_every_model_level(location):
    inputs = request(
        property_record(interval={"lower": 1.0, "upper": 3.0, "basis": "Supplied range"})
    )
    record = inputs["candidates"][0]["properties"]["density"]
    target = {
        "input": inputs,
        "candidate": inputs["candidates"][0],
        "record": record,
        "source": record["source"],
        "interval": record["interval"],
        "criterion": inputs["constraints"][0],
    }[location]
    target["unknown"] = 1
    rejected(inputs, ("INVALID_INPUT",))


@pytest.mark.parametrize(
    "identifier",
    ["", "bad id", "1starts_digit", "_starts_underscore", "a" * 65, "naïve", "x/y", "valid\n"],
)
@pytest.mark.parametrize(
    "location", ["candidate", "property", "constraint", "constraint_property", "condition"]
)
def test_identifiers_have_one_bounded_ascii_grammar(identifier, location):
    inputs = request()
    if location == "candidate":
        inputs["candidates"][0]["candidate_id"] = identifier
    elif location == "property":
        inputs["candidates"][0]["properties"] = {identifier: property_record()}
    elif location == "constraint":
        inputs["constraints"][0]["constraint_id"] = identifier
    elif location == "constraint_property":
        inputs["constraints"][0]["property_id"] = identifier
    else:
        inputs["candidates"][0]["properties"]["density"]["conditions"] = {identifier: "25 C"}
    rejected(inputs, ("INVALID_INPUT",))


@pytest.mark.parametrize("value", ["", " \t\n", "x" * 2001, 25, True])
@pytest.mark.parametrize(
    "location", ["citation", "locator", "basis", "condition", "required_condition"]
)
def test_source_basis_and_context_text_are_nonblank_strict_and_bounded(value, location):
    record = property_record(interval={"lower": 1.0, "upper": 3.0, "basis": "Supplied range"})
    criterion = constraint()
    if location in {"citation", "locator"}:
        record["source"][location] = value
    elif location == "basis":
        record["interval"]["basis"] = value
    elif location == "condition":
        record["conditions"] = {"temperature": value}
    else:
        criterion["required_conditions"] = {"temperature": value}
    rejected(request(record, criterion), ("INVALID_INPUT",))


@pytest.mark.parametrize("location", ["citation", "basis", "condition", "required_condition"])
def test_required_text_fields_do_not_accept_null(location):
    record = property_record(interval={"lower": 1.0, "upper": 3.0, "basis": "Supplied range"})
    criterion = constraint()
    if location == "citation":
        record["source"]["citation"] = None
    elif location == "basis":
        record["interval"]["basis"] = None
    elif location == "condition":
        record["conditions"] = {"temperature": None}
    else:
        criterion["required_conditions"] = {"temperature": None}
    rejected(request(record, criterion), ("INVALID_INPUT",))


def test_optional_locator_can_be_absent_or_explicit_null():
    absent = success(request())
    explicit = success(
        request(
            property_record(
                source={
                    "citation": "Synthetic supplied data; no material was measured.",
                    "locator": None,
                }
            )
        )
    )
    assert absent.result == explicit.result
    assert absent.provenance.input_sha256 == explicit.provenance.input_sha256


@pytest.mark.parametrize("location", ["candidates", "constraints"])
def test_duplicate_ids_are_rejected(location):
    inputs = request()
    inputs[location].append(copy.deepcopy(inputs[location][0]))
    rejected(inputs, ("INVALID_INPUT",))


@pytest.mark.parametrize("minimum,maximum", [(None, None), (3001.0, 3000.0)])
def test_constraints_need_an_ordered_bound(minimum, maximum):
    rejected(request(criterion=constraint(minimum=minimum, maximum=maximum)), ("INVALID_INPUT",))


@pytest.mark.parametrize(
    "allowed", [[], ["measurement", "measurement"], ["unknown"], ["measurement"] * 5, "measurement"]
)
def test_allowed_evidence_list_is_unique_nonempty_closed_and_bounded(allowed):
    rejected(request(criterion=constraint(allowed_evidence=allowed)), ("INVALID_INPUT",))


@pytest.mark.parametrize("count", [0, 101])
def test_candidate_resource_bounds(count):
    inputs = request()
    inputs["candidates"] = [{"candidate_id": f"c{i}", "properties": {}} for i in range(count)]
    rejected(inputs, ("INVALID_INPUT",))


@pytest.mark.parametrize("count", [0, 21])
def test_constraint_resource_bounds(count):
    inputs = request()
    inputs["constraints"] = [constraint(constraint_id=f"bound{i}") for i in range(count)]
    rejected(inputs, ("INVALID_INPUT",))


def test_property_and_condition_resource_bounds():
    inputs = request()
    inputs["candidates"][0]["properties"] = {f"p{i}": property_record() for i in range(33)}
    rejected(inputs, ("INVALID_INPUT",))
    inputs = request(property_record(conditions={f"tag{i}": "value" for i in range(17)}))
    rejected(inputs, ("INVALID_INPUT",))
    inputs = request(
        criterion=constraint(required_conditions={f"tag{i}": "value" for i in range(17)})
    )
    rejected(inputs, ("INVALID_INPUT",))


def test_all_resource_maxima_and_empty_property_maps_are_usable():
    identifier = "A" + "z" * 63
    record = property_record(
        source={"citation": "x" * 2000, "locator": "y" * 2000},
        conditions={f"tag{i}": "z" * 2000 for i in range(16)},
        interval={"lower": 1.0, "upper": 3.0, "basis": "b" * 2000},
    )
    inputs = {
        "candidates": [
            {"candidate_id": identifier, "properties": {f"p{i}": record for i in range(32)}}
        ]
        + [{"candidate_id": f"c{i}", "properties": {}} for i in range(99)],
        "constraints": [
            constraint(
                f"p{i}",
                constraint_id=f"b{i}",
                required_conditions=record["conditions"],
                allowed_evidence=["measurement", "manufacturer", "calculation", "assumption"],
            )
            for i in range(20)
        ],
    }
    result = success(inputs).result
    assert result["summary"] == {"total": 100, "passed": 1, "failed": 0, "unknown": 99}
    assert len(result["candidates"][0]["properties"]) == 32
    assert len(result["normalized_constraints"]) == 20


def test_input_hash_is_canonical_and_records_unconverted_supplied_evidence():
    inputs = request(property_record(conditions={"temperature": "25 C", "method": "example"}))
    first = success(inputs)
    explicit = copy.deepcopy(inputs)
    explicit["candidates"][0]["properties"]["density"].update(interval=None)
    explicit["candidates"][0]["properties"]["density"]["conditions"] = {
        "method": "example",
        "temperature": "25 C",
    }
    explicit["constraints"][0].update(allowed_evidence=["measurement"], required_conditions={})
    second = success(explicit)
    assert first.provenance.input_sha256 == second.provenance.input_sha256
    canonical = json.dumps(
        validate_input(TOOL, inputs), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    assert first.provenance.input_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
    equivalent = copy.deepcopy(inputs)
    equivalent["candidates"][0]["properties"]["density"].update(value=2000.0, unit="kg/m3")
    third = success(equivalent)
    assert third.result["candidates"][0]["properties"]["density"]["normalized_value"] == 2000.0
    assert first.provenance.input_sha256 != third.provenance.input_sha256


def test_discovery_schema_exposes_the_complete_unit_map_and_base_only_operation():
    descriptor = describe_tool(TOOL)
    response = success(request())
    for schema in (descriptor["input_schema"], descriptor["output_schema"]):
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(descriptor["input_schema"]).validate(validate_input(TOOL, request()))
    Draft202012Validator(descriptor["output_schema"]).validate(response.result)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(
        response.model_dump(mode="json")
    )
    unit_map = descriptor["input_schema"]["x-quantity-unit-map"]
    assert set(unit_map) == set(UNIT_MAP)
    for quantity, (si_unit, conversions) in UNIT_MAP.items():
        assert unit_map[quantity]["si_unit"] == si_unit
        assert set(unit_map[quantity]["units"]) == set(conversions)
        for unit, (factor, offset) in conversions.items():
            assert unit_map[quantity]["units"][unit] == {"factor": factor, "offset": offset}
        assert unit_map[quantity]["record_domain"]
    assert descriptor["dependencies"] == []
    assert descriptor["side_effects"] == []
    assert descriptor["network_access"] is False
    assert descriptor["assumptions"]
    assert descriptor["references"]
    assert set(response.provenance.software_versions) == {"pydantic"}
    assert response.provenance.references == descriptor["references"]


def test_unsupported_tool_version_is_rejected():
    response = run_tool(TOOL, request(), tool_version="2")
    assert response.status == "error"
    assert response.error.code == "UNSUPPORTED_VERSION"
