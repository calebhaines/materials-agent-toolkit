"""Small, deterministic engineering calculations with explicit model assumptions.

All quantities use SI units except for scalar mixture properties, whose common
unit is supplied by the caller. Fractions are phase *volume* fractions.
"""

import math
import sys
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from materials_agent_toolkit.contracts import CalculationResult, StrictModel, ToolSpec

FRACTION_SUM_TOLERANCE = 1e-12
# The SI defining constants give R = k_B * N_A exactly; represented in binary64.
GAS_CONSTANT_J_MOL_K = 8.31446261815324

PositiveFloat = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
NonnegativeFloat = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class ScalarBoundsInput(StrictModel):
    values: list[PositiveFloat] = Field(
        min_length=1, description="Positive scalar constituent properties, all in property_unit."
    )
    fractions: list[NonnegativeFloat] = Field(
        min_length=1,
        description="Phase volume fractions, one per value; sum must be within 1e-12 of 1.",
    )
    property_unit: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("property_unit")
    @classmethod
    def validate_property_unit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("property_unit must contain non-whitespace characters")
        return value

    @model_validator(mode="after")
    def validate_fractions(self) -> "ScalarBoundsInput":
        if len(self.values) != len(self.fractions):
            raise ValueError("values and fractions must have the same length")
        try:
            total = math.fsum(self.fractions)
        except OverflowError as exc:
            raise ValueError("fractions must sum to 1 within absolute tolerance 1e-12") from exc
        if abs(total - 1.0) > FRACTION_SUM_TOLERANCE:
            raise ValueError("fractions must sum to 1 within absolute tolerance 1e-12")
        return self


class ScalarBoundsOutput(StrictModel):
    voigt_bound: PositiveFloat = Field(
        description="Arithmetic mean under the uniform-field assumption."
    )
    reuss_bound: PositiveFloat = Field(
        description="Harmonic mean under the uniform-flux assumption."
    )
    property_unit: str


def _log_domain_mean(active: list[tuple[float, float]], *, harmonic: bool) -> float:
    """Retain meaningful terms if scaling puts an entire sum in subnormal range."""
    sign = -1.0 if harmonic else 1.0
    terms = [math.log(fraction) + sign * math.log(value) for value, fraction in active]
    largest = max(terms)
    logarithm = largest + math.log(math.fsum(math.exp(term - largest) for term in terms))
    if harmonic:
        logarithm = -logarithm
    minimum = min(value for value, _ in active)
    maximum = max(value for value, _ in active)
    if logarithm <= math.log(minimum):
        return minimum
    if logarithm >= math.log(maximum):
        return maximum
    return math.exp(logarithm)


def scalar_bounds(inputs: ScalarBoundsInput) -> CalculationResult:
    """Compute the arithmetic and harmonic scalar mixture bounds stably."""
    total = math.fsum(inputs.fractions)
    warnings = []
    if total != 1.0:
        warnings.append(
            f"Volume fractions summed to {total:.17g}; normalized within the absolute "
            f"tolerance {FRACTION_SUM_TOLERANCE:g}."
        )
    active = [
        (value, fraction / total)
        for value, fraction in zip(inputs.values, inputs.fractions)
        if fraction > 0
    ]
    minimum = min(value for value, _ in active)
    maximum = max(value for value, _ in active)
    # Scaling avoids reciprocals of tiny values and sums of huge values.
    arithmetic_factor = math.fsum(fraction * (value / maximum) for value, fraction in active)
    reciprocal_factor = math.fsum(fraction * (minimum / value) for value, fraction in active)
    arithmetic = (
        maximum * min(arithmetic_factor, 1.0)
        if arithmetic_factor >= sys.float_info.min
        else _log_domain_mean(active, harmonic=False)
    )
    harmonic = (
        minimum / min(reciprocal_factor, 1.0)
        if reciprocal_factor >= sys.float_info.min
        else _log_domain_mean(active, harmonic=True)
    )
    # Clamp only roundoff at the mathematical endpoints/order of positive means.
    arithmetic = min(maximum, max(minimum, arithmetic))
    harmonic = min(arithmetic, max(minimum, harmonic))
    if not math.isfinite(arithmetic) or not math.isfinite(harmonic):
        raise ValueError("Mixture bounds exceed the finite floating-point range")
    return CalculationResult(
        ScalarBoundsOutput(
            voigt_bound=arithmetic, reuss_bound=harmonic, property_unit=inputs.property_unit
        ),
        warnings,
    )


class LinearExpansionInput(StrictModel):
    initial_length_m: PositiveFloat
    expansion_coefficient_per_K: FiniteFloat = Field(
        description="Constant linear thermal expansion coefficient; may be negative."
    )
    delta_temperature_K: FiniteFloat


class LinearExpansionOutput(StrictModel):
    delta_length_m: FiniteFloat
    final_length_m: PositiveFloat


def _finite_product(*factors: float) -> float:
    """Multiply with exponent scaling, avoiding unnecessary intermediate overflow."""
    if any(factor == 0 for factor in factors):
        return 0.0
    mantissa = 1.0
    exponent = 0
    for factor in factors:
        fraction, power = math.frexp(factor)
        mantissa *= fraction
        exponent += power
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError("Thermal expansion exceeds the finite floating-point range") from exc
    if not math.isfinite(result):
        raise ValueError("Thermal expansion exceeds the finite floating-point range")
    return result


def linear_expansion(inputs: LinearExpansionInput) -> CalculationResult:
    delta = _finite_product(
        inputs.initial_length_m, inputs.expansion_coefficient_per_K, inputs.delta_temperature_K
    )
    try:
        final = math.fsum((inputs.initial_length_m, delta))
    except OverflowError as exc:
        raise ValueError("Final length exceeds the finite floating-point range") from exc
    if not math.isfinite(final):
        raise ValueError("Final length exceeds the finite floating-point range")
    if final <= 0:
        raise ValueError("The linear model gives a nonpositive final length")
    warnings = [
        "Uses a constant expansion coefficient and a linear small-strain model; "
        "phase changes are excluded."
    ]
    if abs(delta / inputs.initial_length_m) > 0.01:
        warnings.append(
            "Predicted absolute strain exceeds 1%; assess the small-strain approximation."
        )
    if delta == 0 and inputs.expansion_coefficient_per_K != 0 and inputs.delta_temperature_K != 0:
        warnings.append("Length change underflowed to zero in binary64 arithmetic.")
    return CalculationResult(
        LinearExpansionOutput(delta_length_m=delta, final_length_m=final), warnings
    )


class ArrheniusDiffusivityInput(StrictModel):
    pre_exponential_m2_s: PositiveFloat
    activation_energy_J_mol: NonnegativeFloat
    temperature_K: PositiveFloat = Field(description="Absolute temperature in kelvin.")


class ArrheniusDiffusivityOutput(StrictModel):
    diffusivity_m2_s: NonnegativeFloat


def arrhenius_diffusivity(inputs: ArrheniusDiffusivityInput) -> CalculationResult:
    # Divide by T before R so R*T cannot overflow at a large finite temperature.
    exponent = (inputs.activation_energy_J_mol / inputs.temperature_K) / GAS_CONSTANT_J_MOL_K
    if inputs.activation_energy_J_mol == 0:
        diffusivity = inputs.pre_exponential_m2_s
    elif exponent <= 700.0:
        # Use direct multiplication while the exponential has full precision.
        diffusivity = inputs.pre_exponential_m2_s * math.exp(-exponent)
    else:
        # A log-domain product preserves results when exp(-E/RT) alone underflows.
        diffusivity = math.exp(math.log(inputs.pre_exponential_m2_s) - exponent)
    if not math.isfinite(diffusivity):
        raise ValueError("Diffusivity exceeds the finite floating-point range")
    warnings = []
    if diffusivity == 0:
        warnings.append("Diffusivity underflowed to zero in binary64 arithmetic.")
    elif diffusivity < sys.float_info.min:
        warnings.append(
            "Diffusivity is subnormal in binary64 arithmetic; relative precision is limited."
        )
    return CalculationResult(ArrheniusDiffusivityOutput(diffusivity_m2_s=diffusivity), warnings)


TOOLS = (
    ToolSpec(
        name="mixtures.scalar_bounds",
        description="Calculate arithmetic (Voigt) and harmonic (Reuss) scalar mixture bounds.",
        input_model=ScalarBoundsInput,
        output_model=ScalarBoundsOutput,
        execute=scalar_bounds,
        assumptions=(
            "Fractions are phase volume fractions; all positive scalar constituent properties share a unit.",
            "Fractions must sum to 1 within absolute tolerance 1e-12; only rounding within that tolerance is normalized.",
            "Voigt assumes a uniform driving field; Reuss assumes a uniform conjugate flux.",
            "Applicability requires a compatible linear scalar constitutive model; these are not universal strength bounds.",
        ),
        references=(
            "Voigt, W. Lehrbuch der Kristallphysik (1910).",
            "Reuss, A. ZAMM 9 (1929), 49-58. https://doi.org/10.1002/zamm.19290090104",
        ),
    ),
    ToolSpec(
        name="thermal.linear_expansion",
        description="Predict length change using delta_L = L0 * alpha * delta_T in SI units.",
        input_model=LinearExpansionInput,
        output_model=LinearExpansionOutput,
        execute=linear_expansion,
        assumptions=(
            "Constant linear expansion coefficient over the temperature interval; negative coefficients are allowed.",
            "Small strain, unconstrained expansion, and no phase changes.",
            "Nonpositive final lengths and outputs outside the finite binary64 range are rejected.",
        ),
        references=("Linear thermal expansion relation: delta_L = L0 * alpha * delta_T.",),
    ),
    ToolSpec(
        name="kinetics.arrhenius_diffusivity",
        description="Calculate D = D0 * exp(-Ea / (R*T)) using molar activation energy and SI units.",
        input_model=ArrheniusDiffusivityInput,
        output_model=ArrheniusDiffusivityOutput,
        execute=arrhenius_diffusivity,
        assumptions=(
            "A single thermally activated mechanism with temperature-independent D0 and activation energy.",
            "Temperature is absolute kelvin and activation energy is J/mol.",
            "R = k_B * N_A = 8.31446261815324 J/(mol*K), from the exact SI defining constants.",
            "Binary64 underflow to zero or subnormal results are reported explicitly in warnings.",
        ),
        references=(
            "BIPM SI Brochure, 9th edition: https://www.bipm.org/en/publications/si-brochure",
        ),
    ),
)
