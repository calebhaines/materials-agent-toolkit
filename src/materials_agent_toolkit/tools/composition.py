"""Neutral formula/fractional composition and ideal crystallographic density.

The supported formula language is deliberately a subset of periodictable's
parser: natural-abundance element symbols, positive integer counts, and nested
parentheses. Isotopes, charges, mixtures, hydrate dots, and decimal counts are
excluded because silently interpreting those can change the physical meaning.
Explicit elemental fractions separately support non-integer alloy compositions
without inferring a formula unit, integer atom counts, or isotope composition.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Literal

import periodictable
from periodictable.core import Element
from pydantic import Field, StringConstraints, field_validator
from pyparsing import ParseBaseException

from ..contracts import CalculationResult, StrictModel, ToolSpec

AVOGADRO_CONSTANT_PER_MOL = 6.02214076e23  # Exact SI defining constant.
MAX_EXACT_JSON_INTEGER = 2**53 - 1
FORMULA_DESCRIPTION = (
    "Neutral elemental formula using case-sensitive element symbols, positive "
    "integer counts, and parentheses, e.g. H2O or Ca(OH)2. Surrounding whitespace is allowed. "
    "No isotope labels, charges, mixtures, hydrate dots, or decimal counts."
    " Each resulting elemental atom count must be at most 2^53-1 for exact "
    "JSON/binary64 integer interoperability."
)
Formula = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
PositiveExactInteger = Annotated[int, Field(strict=True, gt=0, le=MAX_EXACT_JSON_INTEGER)]
ElementSymbol = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2, pattern=r"^[A-Z][a-z]?$")
]
NonnegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveUnitFraction = Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
FRACTION_UNITY_TOLERANCE = 1e-8
FRACTION_ROUNDOFF_ULPS = 4


class CompositionInput(StrictModel):
    formula: Formula = Field(description=FORMULA_DESCRIPTION)

    @field_validator("formula")
    @classmethod
    def strip_formula(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("formula must contain an elemental composition")
        return value


class CompositionOutput(StrictModel):
    atomic_counts: dict[str, PositiveExactInteger] = Field(
        description="Number of atoms of each element per formula unit."
    )
    atomic_fractions: dict[str, PositiveFiniteFloat] = Field(
        description="Dimensionless elemental atom fractions; sum is one."
    )
    mass_fractions: dict[str, PositiveFiniteFloat] = Field(
        description="Dimensionless elemental mass fractions; sum is one."
    )
    molar_mass_g_mol: PositiveFiniteFloat = Field(
        description="Formula-unit molar mass in grams per mole."
    )
    atomic_weights_source: str = Field(
        description="Atomic-weight library and installed version used."
    )


class FractionalCompositionInput(StrictModel):
    fractions: dict[ElementSymbol, NonnegativeFiniteFloat] = Field(
        min_length=1,
        max_length=118,
        description=(
            "One to 118 exact, case-sensitive elemental symbols mapped to finite "
            "nonnegative fractions or weights. Natural-element symbols only; "
            "isotope aliases such as D and T are unsupported. Zero components "
            "are allowed and omitted from outputs."
        ),
    )
    basis: Literal["atomic", "mass"] = Field(
        description=(
            "Whether the supplied values represent elemental atom fractions "
            "or elemental mass fractions."
        )
    )
    normalization: Literal["require_unity", "normalize"] = Field(
        default="require_unity",
        description=(
            "require_unity accepts a positive finite total within absolute "
            "tolerance 1e-8 of one, then divides by that total. normalize explicitly "
            "accepts any positive finite total, including weights or percentages, "
            "and divides by it. All-zero inputs and overflowing totals are rejected."
        ),
    )


class FractionalCompositionOutput(StrictModel):
    atomic_fractions: dict[ElementSymbol, PositiveUnitFraction] = Field(
        min_length=1,
        max_length=118,
        description=(
            "Positive dimensionless elemental atom fractions in increasing atomic "
            "number order; sum is one within floating-point rounding."
        ),
    )
    mass_fractions: dict[ElementSymbol, PositiveUnitFraction] = Field(
        min_length=1,
        max_length=118,
        description=(
            "Positive dimensionless elemental mass fractions in increasing atomic "
            "number order; sum is one within floating-point rounding."
        ),
    )
    mean_atomic_mass_g_mol: PositiveFiniteFloat = Field(
        description=(
            "Mean atomic mass in grams per mole of atoms: sum(x_i*M_i), where "
            "x_i are atom fractions. This is not formula-unit molar mass."
        )
    )
    input_total: PositiveFiniteFloat = Field(
        description="Dimensionless positive finite sum of the original supplied values."
    )
    atomic_weights_source: str = Field(
        description="Atomic-weight library and installed version used."
    )


class CrystalDensityInput(CompositionInput):
    formula_units: int = Field(
        strict=True,
        gt=0,
        le=MAX_EXACT_JSON_INTEGER,
        description=(
            "Positive integer Z: formula units in the supplied unit cell, at most "
            "2^53-1 for exact JSON/binary64 integer interoperability."
        ),
    )
    cell_volume_angstrom3: PositiveFiniteFloat = Field(
        description="Unit-cell volume in cubic angstroms (1 Å³ = 1e-30 m³)."
    )


class CrystalDensityOutput(StrictModel):
    density_kg_m3: PositiveFiniteFloat = Field(
        description="Ideal crystallographic mass density in kilograms per cubic metre."
    )
    molar_mass_g_mol: PositiveFiniteFloat = Field(
        description="Formula-unit molar mass in grams per mole."
    )
    atomic_weights_source: str


def _positive_finite(value: float, name: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def _parse_formula(formula: str) -> tuple[dict[str, int], dict[str, float], float]:
    # Reject unsupported notation before parsing: an ASCII '.' may mean either
    # a decimal stoichiometry or a hydrate separator, and is intentionally absent.
    if not re.fullmatch(r"[A-Za-z0-9()]+", formula, flags=re.ASCII):
        raise ValueError(FORMULA_DESCRIPTION)
    if re.search(r"(?:^|\()\d|\(\)", formula):
        raise ValueError("Leading coefficients and empty groups are not supported")
    if any(int(count) <= 0 for count in re.findall(r"\d+", formula)):
        raise ValueError("All atom counts and group multipliers must be positive")
    try:
        parsed = periodictable.formula(formula)
        atoms = parsed.atoms
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
        ParseBaseException,
    ) as exc:
        raise ValueError("Invalid or unrecognized elemental formula") from exc
    if not atoms:
        raise ValueError("formula must contain an elemental composition")

    counts: dict[str, int] = {}
    masses: dict[str, float] = {}
    try:
        for atom, count in sorted(atoms.items(), key=lambda pair: pair[0].number):
            if not isinstance(atom, Element) or atom.number <= 0:
                raise ValueError("Only neutral natural-abundance elements are supported")
            if not isinstance(count, int) or count <= 0:
                raise ValueError("Only positive integer atom counts are supported")
            if count > MAX_EXACT_JSON_INTEGER:
                raise ValueError("Elemental atom counts must be at most 2^53-1")
            mass = _positive_finite(float(atom.mass), f"Atomic mass for {atom.symbol}")
            counts[atom.symbol] = count
            masses[atom.symbol] = _positive_finite(
                count * mass, f"Mass contribution for {atom.symbol}"
            )
        molar_mass = _positive_finite(math.fsum(masses.values()), "Molar mass")
        _positive_finite(math.fsum(counts.values()), "Total atom count")
    except (TypeError, OverflowError) as exc:
        raise ValueError(
            "Formula produces a mass or atom count outside finite numeric range"
        ) from exc
    return counts, masses, molar_mass


def _atomic_weights_source() -> str:
    return f"periodictable {periodictable.__version__} atomic-weight table"


def _mass_warnings() -> list[str]:
    return [
        "Atomic weights use the periodictable table and conventional terrestrial "
        "isotope abundances where available; isotopically enriched material needs "
        "different masses. Elements without a standard atomic weight may use a "
        "representative isotope mass from the library."
    ]


def analyze_composition(inputs: CompositionInput) -> CalculationResult:
    counts, masses, molar_mass = _parse_formula(inputs.formula)
    total_count = sum(counts.values())
    return CalculationResult(
        result=CompositionOutput(
            atomic_counts=counts,
            atomic_fractions={symbol: count / total_count for symbol, count in counts.items()},
            mass_fractions={symbol: mass / molar_mass for symbol, mass in masses.items()},
            molar_mass_g_mol=molar_mass,
            atomic_weights_source=_atomic_weights_source(),
        ),
        warnings=_mass_warnings(),
    )


def _preserved_fraction(value: float, symbol: str, basis: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(
            f"{basis} fraction for {symbol} is outside positive finite binary64 "
            "range; normalization or conversion would lose a positive component"
        )
    if value > 1:
        if value - 1 <= FRACTION_ROUNDOFF_ULPS * math.ulp(1.0):
            return 1.0
        raise ValueError(f"{basis} fraction for {symbol} exceeds one beyond binary64 roundoff")
    return value


def _bounded_mean_atomic_mass(mean_mass: float, masses: dict[str, float]) -> float:
    minimum, maximum = min(masses.values()), max(masses.values())
    if mean_mass < minimum:
        if minimum - mean_mass <= FRACTION_ROUNDOFF_ULPS * math.ulp(minimum):
            return minimum
        raise ValueError("Mean atomic mass falls below elemental masses beyond binary64 roundoff")
    if mean_mass > maximum:
        if mean_mass - maximum <= FRACTION_ROUNDOFF_ULPS * math.ulp(maximum):
            return maximum
        raise ValueError("Mean atomic mass exceeds elemental masses beyond binary64 roundoff")
    return mean_mass


def composition_from_fractions(inputs: FractionalCompositionInput) -> CalculationResult:
    # Lookup by canonical symbol rather than periodictable's permissive aliases:
    # D/T isotopes and the neutron are not elemental fractional compositions.
    elements = {element.symbol: element for element in periodictable.elements if element.number > 0}
    unknown = sorted(set(inputs.fractions) - elements.keys())
    if unknown:
        raise ValueError(
            "Unsupported elemental symbols: "
            + ", ".join(unknown)
            + "; use exact natural-element symbols, without isotope aliases"
        )
    try:
        total = math.fsum(inputs.fractions.values())
    except OverflowError as exc:
        raise ValueError("Input fraction total exceeds finite binary64 range") from exc
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Input fraction total must be positive and finite")
    if inputs.normalization == "require_unity" and abs(total - 1.0) > FRACTION_UNITY_TOLERANCE:
        raise ValueError(
            "Input fraction total must equal one within absolute tolerance 1e-8; "
            "use normalization='normalize' for weights or percentages"
        )

    normalized: dict[str, float] = {}
    masses: dict[str, float] = {}
    for symbol in sorted(inputs.fractions, key=lambda item: elements[item].number):
        weight = inputs.fractions[symbol]
        if weight == 0:
            continue
        normalized[symbol] = _preserved_fraction(weight / total, symbol, inputs.basis)
        masses[symbol] = _positive_finite(float(elements[symbol].mass), f"Atomic mass for {symbol}")

    if inputs.basis == "atomic":
        atomic_fractions = normalized
        # xi <= 1 and table masses are small, positive finite values. Direct
        # products avoid overflowing unnormalized input weights or dividing a
        # subnormal fraction before its final conversion factor is known.
        mean_mass = _positive_finite(
            math.fsum(fraction * masses[symbol] for symbol, fraction in normalized.items()),
            "Mean atomic mass",
        )
        mean_mass = _bounded_mean_atomic_mass(mean_mass, masses)
        mass_fractions = {
            symbol: _preserved_fraction(fraction * (masses[symbol] / mean_mass), symbol, "Mass")
            for symbol, fraction in normalized.items()
        }
    else:
        mass_fractions = normalized
        # Mbar = 1/sum(wi/Mi). Scaling by the largest elemental mass makes
        # every factor >= 1, preserving positive subnormal terms without
        # overflow. Dividing wi by Mi first can underflow even when the final
        # atom fraction wi*Mbar/Mi remains representable.
        maximum_mass = max(masses.values())
        scaled_reciprocal_mean = math.fsum(
            fraction * (maximum_mass / masses[symbol]) for symbol, fraction in normalized.items()
        )
        mean_mass = _positive_finite(maximum_mass / scaled_reciprocal_mean, "Mean atomic mass")
        mean_mass = _bounded_mean_atomic_mass(mean_mass, masses)
        atomic_fractions = {
            symbol: _preserved_fraction(fraction * (mean_mass / masses[symbol]), symbol, "Atomic")
            for symbol, fraction in normalized.items()
        }

    return CalculationResult(
        result=FractionalCompositionOutput(
            atomic_fractions=atomic_fractions,
            mass_fractions=mass_fractions,
            mean_atomic_mass_g_mol=mean_mass,
            input_total=total,
            atomic_weights_source=_atomic_weights_source(),
        ),
        warnings=_mass_warnings(),
    )


def crystal_density(inputs: CrystalDensityInput) -> CalculationResult:
    _, _, molar_mass = _parse_formula(inputs.formula)
    # rho = (M_g/mol / 1000) * Z / (N_A * V_angstrom^3 * 1e-30).
    # Evaluate in log space to avoid intermediate overflow or underflow when
    # the final density is representable. N_A is the exact SI constant above.
    try:
        log_density = (
            math.log(molar_mass)
            + math.log(inputs.formula_units)
            + math.log(1e27 / AVOGADRO_CONSTANT_PER_MOL)
            - math.log(inputs.cell_volume_angstrom3)
        )
        density = _positive_finite(math.exp(log_density), "Derived density")
    except (ValueError, OverflowError) as exc:
        raise ValueError("Derived density is outside positive finite numeric range") from exc
    return CalculationResult(
        result=CrystalDensityOutput(
            density_kg_m3=density,
            molar_mass_g_mol=molar_mass,
            atomic_weights_source=_atomic_weights_source(),
        ),
        warnings=_mass_warnings()
        + [
            "Density assumes the supplied composition and formula units exactly "
            "occupy the supplied unit cell; it does not infer Z, partial occupancy, "
            "porosity, or thermal expansion."
        ],
    )


_MASS_ASSUMPTIONS = (
    FORMULA_DESCRIPTION,
    "Atomic weights come from the installed periodictable package; its version is returned.",
    "Conventional terrestrial isotope abundances are assumed where standard atomic weights exist.",
    "Elements without a standard atomic weight use the mass provided by periodictable.",
)
_MASS_REFERENCES = (
    "https://periodictable.readthedocs.io/en/latest/api/mass.html",
    "https://ciaaw.org/atomic-weights.htm",
)

TOOLS = (
    ToolSpec(
        name="composition.analyze",
        description="Parse a neutral elemental formula and calculate atom counts, atom/mass fractions, and molar mass.",
        input_model=CompositionInput,
        output_model=CompositionOutput,
        execute=analyze_composition,
        assumptions=_MASS_ASSUMPTIONS,
        references=_MASS_REFERENCES,
        dependencies=("periodictable",),
    ),
    ToolSpec(
        name="crystal.density",
        description="Calculate ideal crystallographic density from a formula, explicit formula units Z, and unit-cell volume.",
        input_model=CrystalDensityInput,
        output_model=CrystalDensityOutput,
        execute=crystal_density,
        assumptions=_MASS_ASSUMPTIONS
        + (
            "The input Z and cell volume refer to the same unit cell; full stated occupancy is assumed.",
            "N_A = 6.02214076e23 mol^-1 exactly; 1 Å³ = 1e-30 m³.",
            "Result is crystallographic density; porosity and thermal expansion are not modeled.",
        ),
        references=_MASS_REFERENCES + ("https://www.bipm.org/en/si-base-units/mole",),
        dependencies=("periodictable",),
    ),
    ToolSpec(
        name="composition.from_fractions",
        description=(
            "Convert explicit elemental atom or mass fractions/weights into both "
            "fraction bases and mean atomic mass per mole of atoms. Require unity "
            "within absolute tolerance 1e-8 by default, or explicitly normalize "
            "a positive finite weight/percentage total. No formula or atom counts are inferred."
        ),
        input_model=FractionalCompositionInput,
        output_model=FractionalCompositionOutput,
        execute=composition_from_fractions,
        assumptions=(
            "Keys are exact case-sensitive elemental symbols; isotope labels and D/T aliases are unsupported.",
            "Atomic weights come from the installed periodictable package; its version is returned.",
            "Conventional terrestrial isotope abundances are assumed where standard atomic weights exist.",
            "Elements without a standard atomic weight use the mass provided by periodictable.",
            "require_unity uses absolute tolerance 1e-8 with zero relative tolerance; accepted inputs are divided by their actual total.",
            "normalize accepts weights or percentages only when their sum is positive and finite, then divides every value by that sum.",
            "Zero components are omitted from results; keys are ordered by increasing atomic number.",
            "For atom fractions x_i, Mbar=sum(x_i*M_i) and mass fractions w_i=x_i*M_i/Mbar.",
            "For mass fractions w_i, Mbar=1/sum(w_i/M_i) and atom fractions x_i=w_i*Mbar/M_i.",
            "Mean atomic mass is in g/mol of atoms; formula-unit molar mass and integer stoichiometry are not inferred.",
            "Binary64 rounding applies. Overflowing input totals and normalization/conversion that loses a positive component to zero or nonfinite values are rejected.",
            "Fractions exceeding one by at most four binary64 ulps are rounded to one; mean atomic masses outside elemental mass extrema by at most four ulps are rounded to that endpoint. Larger excursions are rejected.",
            "Elemental fractions specify composition only; phases, site occupancy, charge, microstructure and uncertainty are not inferred.",
        ),
        references=_MASS_REFERENCES,
        dependencies=("periodictable",),
    ),
)
