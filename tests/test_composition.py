"""Scientific reference cases and input-boundary checks for composition tools."""

import math

import pytest
from pydantic import ValidationError

from materials_agent_toolkit.tools.composition import (
    AVOGADRO_CONSTANT_PER_MOL,
    CompositionInput,
    CrystalDensityInput,
    analyze_composition,
    crystal_density,
)


def test_water_reference_molar_mass_and_fractions():
    result = analyze_composition(CompositionInput(formula="H2O"))
    water = result.result
    assert water.atomic_counts == {"H": 2.0, "O": 1.0}
    assert water.molar_mass_g_mol == pytest.approx(18.015, abs=0.002)
    assert water.atomic_fractions == pytest.approx({"H": 2 / 3, "O": 1 / 3})
    assert water.mass_fractions["H"] == pytest.approx(0.1119067, abs=0.00005)
    assert water.mass_fractions["O"] == pytest.approx(0.8880933, abs=0.00005)
    assert sum(water.mass_fractions.values()) == pytest.approx(1)
    assert "periodictable" in water.atomic_weights_source
    assert result.warnings


def test_parentheses_and_nested_groups_preserve_element_counts():
    hydroxide = analyze_composition(CompositionInput(formula="Ca(OH)2")).result
    assert hydroxide.atomic_counts == {"Ca": 1.0, "O": 2.0, "H": 2.0}
    assert hydroxide.molar_mass_g_mol == pytest.approx(74.092, abs=0.003)
    sulfate = analyze_composition(CompositionInput(formula="Al2(SO4)3")).result
    assert sulfate.atomic_counts == {"Al": 2.0, "S": 3.0, "O": 12.0}


def test_aluminum_fcc_cell_reference_density_and_volume_scaling():
    # Room-temperature FCC Al: a near 4.05 Å, Z = 4, expected rho near 2.70 g/cm³.
    aluminum = crystal_density(
        CrystalDensityInput(formula="Al", formula_units=4, cell_volume_angstrom3=4.05**3)
    ).result
    assert aluminum.density_kg_m3 == pytest.approx(2697.9, abs=1)
    assert aluminum.molar_mass_g_mol == pytest.approx(26.9815384, abs=0.00001)
    larger = crystal_density(
        CrystalDensityInput(formula="Al", formula_units=4, cell_volume_angstrom3=2 * 4.05**3)
    ).result
    assert larger.density_kg_m3 == pytest.approx(aluminum.density_kg_m3 / 2)


def test_compound_density_uses_formula_units_not_atom_count():
    # Rock salt conventional cell has 4 NaCl units (8 atoms), a = 5.64 Å.
    result = crystal_density(
        CrystalDensityInput(formula="NaCl", formula_units=4, cell_volume_angstrom3=5.64**3)
    ).result
    assert result.density_kg_m3 == pytest.approx(2163.9, abs=2)


@pytest.mark.parametrize(
    "formula",
    [
        "Xx2",
        "water",
        "H0O",
        "(OH)0",
        "H-2O",
        "Na+",
        "H[2]2O",
        "D2O",
        "CuSO4·5H2O",
        "CuSO4.5H2O",
        "Fe0.5Ni0.5",
        "H2O@1",
        "Ca(OH2",
        "H2O)",
        "()",
        "H2()O",
        "2H2O",
        "CaCO3 6H2O",
        "n",
    ],
)
def test_malformed_unknown_or_unsupported_formulas_are_rejected(formula):
    with pytest.raises(ValueError):
        analyze_composition(CompositionInput(formula=formula))


@pytest.mark.parametrize("formula", ["", "   ", 123, True, "H" * 513])
def test_formula_input_is_bounded_strict_and_nonempty(formula):
    with pytest.raises(ValidationError):
        CompositionInput(formula=formula)


@pytest.mark.parametrize(
    "formula_units",
    [0, -1, 1.5, True, "4", 2**53, pytest.param(10**5000, id="oversized-integer")],
)
def test_formula_units_require_a_positive_integer(formula_units):
    with pytest.raises(ValidationError):
        CrystalDensityInput(formula="Al", formula_units=formula_units, cell_volume_angstrom3=66.4)


@pytest.mark.parametrize("volume", [0, -1, math.inf, -math.inf, math.nan, True, "66.4"])
def test_volume_requires_a_positive_finite_number(volume):
    with pytest.raises(ValidationError):
        CrystalDensityInput(formula="Al", formula_units=4, cell_volume_angstrom3=volume)


def test_density_overflow_has_an_explicit_failure():
    with pytest.raises(ValueError, match="finite numeric range"):
        crystal_density(
            CrystalDensityInput(formula="Al", formula_units=4, cell_volume_angstrom3=5e-324)
        )


def test_formula_counts_preserve_exact_json_integer_range():
    maximum_count = 2**53 - 1
    result = analyze_composition(CompositionInput(formula=f"H{maximum_count}")).result
    assert result.atomic_counts == {"H": maximum_count}
    assert isinstance(result.atomic_counts["H"], int)
    with pytest.raises(ValueError, match="at most 2\\^53-1"):
        analyze_composition(CompositionInput(formula=f"H{maximum_count + 1}"))
    with pytest.raises(ValueError, match="at most 2\\^53-1"):
        analyze_composition(CompositionInput(formula=f"(H{maximum_count})2"))


def test_avogadro_is_the_exact_si_defining_value():
    assert AVOGADRO_CONSTANT_PER_MOL == 6.02214076e23
