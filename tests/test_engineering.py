"""Analytical and domain-boundary checks for the engineering models."""

import math
import sys

import pytest
from pydantic import ValidationError

from materials_agent_toolkit.tools.engineering import (
    GAS_CONSTANT_J_MOL_K,
    ArrheniusDiffusivityInput,
    LinearExpansionInput,
    ScalarBoundsInput,
    arrhenius_diffusivity,
    linear_expansion,
    scalar_bounds,
)


def bounds(values, fractions):
    return scalar_bounds(ScalarBoundsInput(values=values, fractions=fractions, property_unit="GPa"))


@pytest.mark.parametrize("fractions,expected", [([1.0, 0.0], 10.0), ([0.0, 1.0], 40.0)])
def test_mixture_endpoints(fractions, expected):
    result = bounds([10.0, 40.0], fractions).result
    assert result.voigt_bound == expected
    assert result.reuss_bound == expected


def test_equal_mixture_arithmetic_and_harmonic():
    result = bounds([10.0, 40.0], [0.5, 0.5]).result
    assert result.voigt_bound == pytest.approx(25.0)
    assert result.reuss_bound == pytest.approx(16.0)
    assert result.property_unit == "GPa"


@pytest.mark.parametrize(
    "values,fractions",
    [
        ([1.0, 2.0, 100.0], [0.1, 0.2, 0.7]),
        ([3.0, 3.0], [0.25, 0.75]),
        ([5e-324, sys.float_info.max], [0.5, 0.5]),
        ([sys.float_info.max, sys.float_info.max], [0.5, 0.5]),
    ],
)
def test_positive_means_stay_ordered_and_finite(values, fractions):
    result = bounds(values, fractions).result
    assert min(values) <= result.reuss_bound <= result.voigt_bound <= max(values)
    assert math.isfinite(result.voigt_bound)
    assert math.isfinite(result.reuss_bound)


def test_negligible_fraction_rounding_is_explicitly_normalized():
    result = bounds([4.0, 4.0], [0.5, 0.5 + 2e-13])
    assert result.result.voigt_bound == 4.0
    assert result.result.reuss_bound == 4.0
    assert any("normalized" in warning for warning in result.warnings)


def test_harmonic_mean_retains_subnormal_scaled_contributions():
    smallest = math.ulp(0.0)
    result = bounds([smallest, 2.0], [smallest, 1.0]).result
    # f1/x1 = 1 and f2/x2 = 1/2, even though x1/x2 rounds to zero.
    assert result.reuss_bound == pytest.approx(2.0 / 3.0, rel=1e-12)


@pytest.mark.parametrize(
    "updates",
    [
        {"values": []},
        {"values": [0.0, 2.0]},
        {"values": [-1.0, 2.0]},
        {"values": [float("inf"), 2.0]},
        {"values": [float("nan"), 2.0]},
        {"values": ["1", 2.0]},
        {"values": [True, 2.0]},
        {"fractions": [0.4, 0.5]},
        {"fractions": [-0.1, 1.1]},
        {"fractions": [0.5]},
        {"fractions": [float("inf"), 0.5]},
        {"fractions": [float("nan"), 0.5]},
        {"fractions": [0.5, 0.50000001]},
        {"property_unit": "  "},
        {"property_unit": "a" * 129},
        {"unknown": 1},
    ],
)
def test_invalid_mixture_inputs_are_rejected(updates):
    data = {"values": [1.0, 2.0], "fractions": [0.5, 0.5], "property_unit": "Pa"}
    data.update(updates)
    with pytest.raises(ValidationError):
        ScalarBoundsInput(**data)


def test_linear_expansion_example():
    calculation = linear_expansion(
        LinearExpansionInput(
            initial_length_m=2.0, expansion_coefficient_per_K=12e-6, delta_temperature_K=100.0
        )
    )
    assert calculation.result.delta_length_m == pytest.approx(0.0024)
    assert calculation.result.final_length_m == pytest.approx(2.0024)
    assert any(
        "small-strain" in warning and "phase changes" in warning for warning in calculation.warnings
    )


def test_negative_expansion_coefficient():
    result = linear_expansion(
        LinearExpansionInput(
            initial_length_m=1.0, expansion_coefficient_per_K=-1e-5, delta_temperature_K=100.0
        )
    ).result
    assert result.delta_length_m == pytest.approx(-0.001)
    assert result.final_length_m == pytest.approx(0.999)


def test_scaled_expansion_avoids_intermediate_overflow():
    result = linear_expansion(
        LinearExpansionInput(
            initial_length_m=1e100, expansion_coefficient_per_K=1e250, delta_temperature_K=1e-250
        )
    ).result
    assert result.delta_length_m == pytest.approx(1e100)
    assert result.final_length_m == pytest.approx(2e100)


@pytest.mark.parametrize("coefficient", [-1.0, -2.0])
def test_nonpositive_final_length_rejected(coefficient):
    with pytest.raises(ValueError, match="nonpositive"):
        linear_expansion(
            LinearExpansionInput(
                initial_length_m=1.0,
                expansion_coefficient_per_K=coefficient,
                delta_temperature_K=1.0,
            )
        )


@pytest.mark.parametrize(
    "length,coefficient,temperature",
    [
        (sys.float_info.max, 1.0, 1.0),
        (1.0, sys.float_info.max, 2.0),
    ],
)
def test_overflowing_expansion_rejected(length, coefficient, temperature):
    with pytest.raises(ValueError, match="finite"):
        linear_expansion(
            LinearExpansionInput(
                initial_length_m=length,
                expansion_coefficient_per_K=coefficient,
                delta_temperature_K=temperature,
            )
        )


def test_arrhenius_analytical_reference():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=1e-5, activation_energy_J_mol=100000.0, temperature_K=1000.0
        )
    ).result
    assert result.diffusivity_m2_s == pytest.approx(5.979129887968594e-11, rel=1e-12)


def test_arrhenius_zero_barrier_preserves_pre_exponential():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=sys.float_info.max,
            activation_energy_J_mol=0.0,
            temperature_K=300.0,
        )
    ).result
    assert result.diffusivity_m2_s == sys.float_info.max


def test_arrhenius_underflow_is_explicit():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=1e-5, activation_energy_J_mol=1e9, temperature_K=1.0
        )
    )
    assert result.result.diffusivity_m2_s == 0.0
    assert any("underflow" in warning for warning in result.warnings)


def test_arrhenius_subnormal_precision_is_explicit():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=1.0,
            activation_energy_J_mol=740.0 * GAS_CONSTANT_J_MOL_K,
            temperature_K=1.0,
        )
    )
    assert 0 < result.result.diffusivity_m2_s < sys.float_info.min
    assert any("subnormal" in warning for warning in result.warnings)


def test_arrhenius_log_domain_preserves_finite_diffusivity():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=1e300,
            activation_energy_J_mol=800.0 * GAS_CONSTANT_J_MOL_K,
            temperature_K=1.0,
        )
    ).result
    assert result.diffusivity_m2_s == pytest.approx(math.exp(math.log(1e300) - 800.0))
    assert result.diffusivity_m2_s > 0


def test_arrhenius_large_temperature_does_not_overflow_rt():
    result = arrhenius_diffusivity(
        ArrheniusDiffusivityInput(
            pre_exponential_m2_s=1.0, activation_energy_J_mol=1e308, temperature_K=1e308
        )
    ).result
    assert result.diffusivity_m2_s == pytest.approx(math.exp(-1.0 / GAS_CONSTANT_J_MOL_K))


@pytest.mark.parametrize(
    "model,data",
    [
        (
            LinearExpansionInput,
            {
                "initial_length_m": 0.0,
                "expansion_coefficient_per_K": 1e-5,
                "delta_temperature_K": 1.0,
            },
        ),
        (
            LinearExpansionInput,
            {
                "initial_length_m": 1.0,
                "expansion_coefficient_per_K": float("inf"),
                "delta_temperature_K": 1.0,
            },
        ),
        (
            LinearExpansionInput,
            {
                "initial_length_m": 1.0,
                "expansion_coefficient_per_K": 1e-5,
                "delta_temperature_K": float("nan"),
            },
        ),
        (
            ArrheniusDiffusivityInput,
            {"pre_exponential_m2_s": -1.0, "activation_energy_J_mol": 0.0, "temperature_K": 300.0},
        ),
        (
            ArrheniusDiffusivityInput,
            {"pre_exponential_m2_s": 1.0, "activation_energy_J_mol": -1.0, "temperature_K": 300.0},
        ),
        (
            ArrheniusDiffusivityInput,
            {"pre_exponential_m2_s": 1.0, "activation_energy_J_mol": 1.0, "temperature_K": 0.0},
        ),
        (
            ArrheniusDiffusivityInput,
            {"pre_exponential_m2_s": 1.0, "activation_energy_J_mol": 1.0, "temperature_K": "300"},
        ),
    ],
)
def test_invalid_thermal_and_kinetic_inputs(model, data):
    with pytest.raises(ValidationError):
        model(**data)
