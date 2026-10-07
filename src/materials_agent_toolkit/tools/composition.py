"""Neutral formula analysis and ideal crystallographic mass density.

The supported formula language is deliberately a subset of periodictable's
parser: natural-abundance element symbols, positive integer counts, and nested
parentheses. Isotopes, charges, mixtures, hydrate dots, and decimal counts are
excluded because silently interpreting those can change the physical meaning.
"""

from __future__ import annotations

import math
import re
from typing import Annotated

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
)
