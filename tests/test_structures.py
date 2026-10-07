"""Analytical crystallography references and bounded CIF-domain checks.

The fixtures are authored CC0 ideal/synthetic cells; they do not copy a dataset.
ASE-dependent execution checks skip individually in base-only installations.
"""

import builtins
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit.registry import (
    ToolResponse,
    describe_tool,
    run_tool,
    validate_input,
)

TOOL = "structure.analyze_cif"
FIXTURES = Path(__file__).parent / "fixtures" / "structures"
GEOMETRY_REL_TOL = 1e-12
DENSITY_REL_TOL = 1e-10


@pytest.fixture
def structures_extra():
    pytest.importorskip("ase", reason="CIF calculations require the structures extra")


def cif_fixture(name):
    return (FIXTURES / f"{name}.cif").read_text(encoding="utf-8")


def calculate(cif_text, **kwargs):
    return run_tool(TOOL, {"cif_text": cif_text}, **kwargs)


def require_success(response):
    assert response.status == "ok", response.error
    assert response.error is None
    assert response.result is not None
    return response.result


def require_error(response, code="DOMAIN_ERROR"):
    assert response.status == "error", response.result
    assert response.result is None
    assert response.error is not None
    assert response.error.code == code, response.error
    return response.error


def p1_cif(rows="Al1 Al 0.1 0.2 0.3 1", *, lengths=(3, 4, 5), angles=(90, 90, 90)):
    """Produce authored minimal CIF text, keeping malformed variants local to a test."""
    return (
        "data_synthetic\n"
        f"_cell_length_a {lengths[0]}\n"
        f"_cell_length_b {lengths[1]}\n"
        f"_cell_length_c {lengths[2]}\n"
        f"_cell_angle_alpha {angles[0]}\n"
        f"_cell_angle_beta {angles[1]}\n"
        f"_cell_angle_gamma {angles[2]}\n"
        "_space_group_IT_number 1\n"
        "loop_\n"
        "_atom_site_label\n"
        "_atom_site_type_symbol\n"
        "_atom_site_fract_x\n"
        "_atom_site_fract_y\n"
        "_atom_site_fract_z\n"
        "_atom_site_occupancy\n"
        f"{rows}\n"
    )


def periodic_sites(result):
    return {
        (symbol, *(round(float(value), 10) for value in position))
        for symbol, position in zip(result["symbols"], result["fractional_positions"], strict=True)
    }


@pytest.mark.parametrize(
    "fixture,counts,volume,density",
    [
        ("al_fcc", {"Al": 4}, 66.430125, 2697.806069499423),
        ("nacl_rocksalt", {"Na": 4, "Cl": 4}, 179.406144, 2163.616424776758),
        ("triclinic_water", {"H": 2, "O": 1}, 24.0, 1246.442137297369),
    ],
)
def test_reference_cells_expand_symmetry_and_preserve_stoichiometry(
    structures_extra, fixture, counts, volume, density
):
    result = require_success(calculate(cif_fixture(fixture)))
    assert result["atomic_counts"] == counts
    assert result["atom_count"] == sum(counts.values())
    assert Counter(result["symbols"]) == counts
    assert result["cell_volume_angstrom3"] == pytest.approx(volume, rel=GEOMETRY_REL_TOL)
    assert result["density_kg_m3"] == pytest.approx(density, rel=DENSITY_REL_TOL)
    assert result["source_block"] == fixture
    assert "periodictable" in result["atomic_weights_source"]


def test_fcc_al_has_four_analytical_conventional_cell_sites(structures_extra):
    result = require_success(calculate(cif_fixture("al_fcc")))
    assert periodic_sites(result) == {
        ("Al", 0.0, 0.0, 0.0),
        ("Al", 0.0, 0.5, 0.5),
        ("Al", 0.5, 0.0, 0.5),
        ("Al", 0.5, 0.5, 0.0),
    }


def test_rocksalt_sites_have_correct_sublattices(structures_extra):
    result = require_success(calculate(cif_fixture("nacl_rocksalt")))
    assert periodic_sites(result) == {
        ("Na", 0.0, 0.0, 0.0),
        ("Na", 0.0, 0.5, 0.5),
        ("Na", 0.5, 0.0, 0.5),
        ("Na", 0.5, 0.5, 0.0),
        ("Cl", 0.5, 0.5, 0.5),
        ("Cl", 0.5, 0.0, 0.0),
        ("Cl", 0.0, 0.5, 0.0),
        ("Cl", 0.0, 0.0, 0.5),
    }


def test_triclinic_cell_row_basis_and_cartesian_positions(structures_extra):
    result = require_success(calculate(cif_fixture("triclinic_water")))
    cell = np.asarray(result["cell_vectors_angstrom"])
    expected_basis = np.array([[2.0, 0.0, 0.0], [1.0, 3.0, 0.0], [1.0, 2.0, 4.0]])
    np.testing.assert_allclose(cell, expected_basis, rtol=GEOMETRY_REL_TOL, atol=1e-13)
    np.testing.assert_allclose(
        result["cartesian_positions_angstrom"],
        [[0.7, 1.2, 1.2], [0.9, 1.2, 1.2], [0.8, 1.5, 1.2]],
        rtol=GEOMETRY_REL_TOL,
        atol=1e-13,
    )
    assert np.linalg.det(cell) == pytest.approx(24.0, rel=GEOMETRY_REL_TOL)


def test_cartesian_cif_coordinates_match_fractional_coordinates_in_triclinic_cell(
    structures_extra,
):
    fractional_text = cif_fixture("triclinic_water")
    cartesian_text = fractional_text.replace("_atom_site_fract_", "_atom_site_Cartn_")
    for before, after in (
        ("O1 O 0.1 0.2 0.3 1", "O1 O 0.7 1.2 1.2 1"),
        ("H1 H 0.2 0.2 0.3 1", "H1 H 0.9 1.2 1.2 1"),
        ("H2 H 0.1 0.3 0.3 1", "H2 H 0.8 1.5 1.2 1"),
    ):
        cartesian_text = cartesian_text.replace(before, after)
    first = require_success(calculate(fractional_text))
    second = require_success(calculate(cartesian_text))
    assert second["atomic_counts"] == first["atomic_counts"]
    assert second["density_kg_m3"] == first["density_kg_m3"]
    for field in ("fractional_positions", "cartesian_positions_angstrom"):
        np.testing.assert_allclose(second[field], first[field], rtol=1e-12, atol=1e-13)


@pytest.mark.parametrize(
    "cartesian_values",
    ["0.3 0.8 1.5", "3.3 -3.2 11.5"],
)
def test_consistent_dual_coordinate_columns_preserve_periodic_sites(
    structures_extra, cartesian_values
):
    text = p1_cif().replace(
        "_atom_site_occupancy\n",
        "_atom_site_occupancy\n_atom_site_Cartn_x\n_atom_site_Cartn_y\n_atom_site_Cartn_z\n",
    )
    text = text.replace("Al1 Al 0.1 0.2 0.3 1", f"Al1 Al 0.1 0.2 0.3 1 {cartesian_values}")
    result = require_success(calculate(text))
    assert periodic_sites(result) == {("Al", 0.1, 0.2, 0.3)}


def test_inconsistent_dual_coordinate_columns_are_rejected(structures_extra):
    text = p1_cif().replace(
        "_atom_site_occupancy\n",
        "_atom_site_occupancy\n_atom_site_Cartn_x\n_atom_site_Cartn_y\n_atom_site_Cartn_z\n",
    )
    text = text.replace("Al1 Al 0.1 0.2 0.3 1", "Al1 Al 0.1 0.2 0.3 1 0.6 0.8 1.5")
    require_error(calculate(text))


@pytest.mark.parametrize("fixture", ["al_fcc", "nacl_rocksalt", "triclinic_water"])
def test_coordinates_are_consistent_and_wrapped_in_periodic_cell(structures_extra, fixture):
    result = require_success(calculate(cif_fixture(fixture)))
    fractions = np.asarray(result["fractional_positions"])
    cartesian = np.asarray(result["cartesian_positions_angstrom"])
    cell = np.asarray(result["cell_vectors_angstrom"])
    assert fractions.shape == cartesian.shape == (result["atom_count"], 3)
    assert np.all((fractions >= 0.0) & (fractions < 1.0))
    np.testing.assert_allclose(cartesian, fractions @ cell, rtol=1e-12, atol=1e-13)
    assert abs(np.linalg.det(cell)) == pytest.approx(
        result["cell_volume_angstrom3"], rel=GEOMETRY_REL_TOL
    )
    assert np.all(np.isfinite(fractions))
    assert np.all(np.isfinite(cartesian))
    assert np.all(np.isfinite(cell))


@pytest.mark.parametrize("scale", [0.01, 2.0, 100.0])
def test_uniform_length_scaling_changes_volume_cubically_and_density_inversely(
    structures_extra, scale
):
    first = require_success(calculate(p1_cif()))
    scaled = require_success(
        calculate(p1_cif(lengths=tuple(length * scale for length in (3, 4, 5))))
    )
    assert scaled["atomic_counts"] == first["atomic_counts"]
    np.testing.assert_allclose(
        scaled["fractional_positions"], first["fractional_positions"], rtol=1e-12, atol=1e-14
    )
    assert scaled["cell_volume_angstrom3"] == pytest.approx(
        first["cell_volume_angstrom3"] * scale**3, rel=GEOMETRY_REL_TOL
    )
    assert scaled["density_kg_m3"] == pytest.approx(
        first["density_kg_m3"] / scale**3, rel=DENSITY_REL_TOL
    )
    np.testing.assert_allclose(
        scaled["cartesian_positions_angstrom"],
        np.asarray(first["cartesian_positions_angstrom"]) * scale,
        rtol=1e-12,
        atol=1e-13,
    )


def test_periodic_integer_translation_preserves_structure_and_density(structures_extra):
    first = require_success(calculate(p1_cif("Al1 Al 0.125 0.25 0.375 1")))
    shifted = require_success(calculate(p1_cif("Al1 Al -1.875 3.25 1.375 1")))
    assert shifted["atomic_counts"] == first["atomic_counts"]
    assert shifted["density_kg_m3"] == first["density_kg_m3"]
    assert periodic_sites(shifted) == periodic_sites(first)
    np.testing.assert_allclose(
        shifted["cartesian_positions_angstrom"], first["cartesian_positions_angstrom"]
    )


def test_structure_and_formula_density_use_same_natural_element_masses(structures_extra):
    result = require_success(calculate(cif_fixture("nacl_rocksalt")))
    reference = require_success(
        run_tool(
            "crystal.density",
            {
                "formula": "NaCl",
                "formula_units": 4,
                "cell_volume_angstrom3": result["cell_volume_angstrom3"],
            },
        )
    )
    assert result["density_kg_m3"] == pytest.approx(reference["density_kg_m3"], rel=DENSITY_REL_TOL)


@pytest.mark.parametrize("value", [None, True, 123, 1.5, [], {}, b"data_example"])
def test_cif_text_requires_strict_string_input(value):
    require_error(calculate(value), "INVALID_INPUT")


@pytest.mark.parametrize("inputs", [{}, {"cif_text": "data_test", "path": "test.cif"}])
def test_unknown_input_fields_and_missing_text_are_rejected(inputs):
    require_error(run_tool(TOOL, inputs), "INVALID_INPUT")


def test_oversized_cif_is_rejected_by_input_schema_before_parsing():
    require_error(calculate("#" * 100001), "INVALID_INPUT")


@pytest.mark.parametrize("cif_text", ["", " ", "# comment only\n", "not a CIF", "data_empty\n"])
def test_empty_or_malformed_cif_returns_structured_error(structures_extra, cif_text):
    response = calculate(cif_text)
    assert response.status == "error"
    assert response.error.code in {"INVALID_INPUT", "DOMAIN_ERROR"}
    assert response.result is None


@pytest.mark.parametrize("bad_length", [0, -1, "nan", "inf", "?", ".", 1e-7, 1e7])
def test_cell_lengths_are_finite_positive_and_bounded(structures_extra, bad_length):
    require_error(calculate(p1_cif(lengths=(bad_length, 4, 5))))


@pytest.mark.parametrize("bad_angle", [0, 180, 181, -1, "nan", "inf", "?", "."])
def test_cell_angles_are_finite_and_strictly_between_zero_and_180(structures_extra, bad_angle):
    require_error(calculate(p1_cif(angles=(bad_angle, 90, 90))))


def test_inconsistent_angles_do_not_produce_a_fictitious_volume(structures_extra):
    require_error(calculate(p1_cif(angles=(10, 10, 170))))


def test_nearly_degenerate_cell_exceeding_condition_bound_is_rejected(structures_extra):
    require_error(calculate(p1_cif(angles=(90, 90, 1e-7))))


def test_cell_length_condition_limit_is_explicit_and_inclusive(structures_extra):
    accepted = require_success(calculate(p1_cif(lengths=(1e-6, 100, 100))))
    assert np.linalg.cond(accepted["cell_vectors_angstrom"]) == pytest.approx(1e8)
    require_error(calculate(p1_cif(lengths=(1e-6, 1000, 1000))))


@pytest.mark.parametrize("length", [1e-6, 1e6])
def test_uniform_cells_at_declared_length_endpoints_remain_finite(structures_extra, length):
    result = require_success(calculate(p1_cif(lengths=(length, length, length))))
    assert result["cell_volume_angstrom3"] == pytest.approx(length**3, rel=1e-12, abs=0)
    assert math.isfinite(result["density_kg_m3"])
    assert result["density_kg_m3"] > 0


@pytest.mark.parametrize("field", ["a", "b", "c"])
def test_missing_cell_dimensions_are_rejected(structures_extra, field):
    text = p1_cif()
    line = next(line for line in text.splitlines() if line.startswith(f"_cell_length_{field}"))
    require_error(calculate(text.replace(f"{line}\n", "")))


@pytest.mark.parametrize("field", ["alpha", "beta", "gamma"])
def test_missing_cell_angles_are_rejected(structures_extra, field):
    text = p1_cif()
    require_error(calculate(text.replace(f"_cell_angle_{field} 90\n", "")))


def test_nonperiodic_coordinates_without_unit_cell_are_rejected(structures_extra):
    text = "\n".join(line for line in p1_cif().splitlines() if not line.startswith("_cell_"))
    require_error(calculate(text))


@pytest.mark.parametrize("occupancy", [0, 0.5, 1.0001, "?", ".", "nan", "inf"])
def test_partial_or_unknown_site_occupancies_are_rejected(structures_extra, occupancy):
    require_error(calculate(p1_cif(f"Al1 Al 0.1 0.2 0.3 {occupancy}")))


@pytest.mark.parametrize("occupancy", [0.999999995, 1.000000005])
def test_near_unity_occupancy_is_interpreted_as_a_full_site(structures_extra, occupancy):
    ordinary = require_success(calculate(p1_cif()))
    response = calculate(p1_cif(f"Al1 Al 0.1 0.2 0.3 {occupancy}"))
    rounded = require_success(response)
    assert rounded["atomic_counts"] == {"Al": 1}
    assert rounded["density_kg_m3"] == ordinary["density_kg_m3"]
    assert any("normalized" in warning for warning in response.warnings)


def test_absent_occupancy_column_means_full_occupancy(structures_extra):
    text = (
        p1_cif()
        .replace("_atom_site_occupancy\n", "")
        .replace("Al1 Al 0.1 0.2 0.3 1", "Al1 Al 0.1 0.2 0.3")
    )
    result = require_success(calculate(text))
    assert result["atomic_counts"] == {"Al": 1}


@pytest.mark.parametrize("symbol", ["D", "T", "Xx", "Fe2+", "Al/Si", "Al0.5Si0.5"])
def test_unknown_isotopic_charged_or_mixed_symbols_are_rejected(structures_extra, symbol):
    require_error(calculate(p1_cif(f"X1 {symbol} 0.1 0.2 0.3 1")))


def test_standard_element_labels_work_without_type_symbol_column(structures_extra):
    text = (
        p1_cif()
        .replace("_atom_site_type_symbol\n", "")
        .replace("Al1 Al 0.1 0.2 0.3 1", "Al1 0.1 0.2 0.3 1")
    )
    result = require_success(calculate(text))
    assert result["atomic_counts"] == {"Al": 1}


@pytest.mark.parametrize("label", ["D1", "T1", "Xx1", "13C1", "Fe2+", "ni1"])
def test_missing_type_symbol_does_not_permit_isotope_or_charge_label_aliases(
    structures_extra, label
):
    text = (
        p1_cif()
        .replace("_atom_site_type_symbol\n", "")
        .replace("Al1 Al 0.1 0.2 0.3 1", f"{label} 0.1 0.2 0.3 1")
    )
    require_error(calculate(text))


def test_explicit_disorder_group_is_rejected_even_when_occupancy_is_unity(structures_extra):
    text = p1_cif().replace(
        "_atom_site_occupancy\n", "_atom_site_occupancy\n_atom_site_disorder_group\n"
    )
    text = text.replace("Al1 Al 0.1 0.2 0.3 1", "Al1 Al 0.1 0.2 0.3 1 1")
    require_error(calculate(text))


def test_disordered_mixed_site_is_rejected_without_inventing_formula(structures_extra):
    require_error(calculate(p1_cif("Al1 Al 0.1 0.2 0.3 0.5\nSi1 Si 0.1 0.2 0.3 0.5")))


def test_fully_occupied_duplicate_site_is_rejected_instead_of_silently_merged(structures_extra):
    require_error(calculate(p1_cif("Al1 Al 0.1 0.2 0.3 1\nAl2 Al 0.1 0.2 0.3 1")))


@pytest.mark.parametrize("coordinate", ["?", ".", "nan", "inf", "-inf"])
def test_fractional_positions_cannot_be_unknown_or_nonfinite(structures_extra, coordinate):
    require_error(calculate(p1_cif(f"Al1 Al {coordinate} 0.2 0.3 1")))


@pytest.mark.parametrize("field", ["x", "y", "z"])
def test_incomplete_fractional_coordinate_triplet_is_rejected(structures_extra, field):
    text = p1_cif().replace(f"_atom_site_fract_{field}\n", "")
    values = {"x": "Al1 Al 0.2 0.3 1", "y": "Al1 Al 0.1 0.3 1", "z": "Al1 Al 0.1 0.2 1"}
    text = text.replace("Al1 Al 0.1 0.2 0.3 1", values[field])
    require_error(calculate(text))


def test_two_structural_blocks_are_rejected_as_ambiguous(structures_extra):
    require_error(calculate(cif_fixture("al_fcc") + "\n" + cif_fixture("nacl_rocksalt")))


def test_nonstructural_metadata_block_does_not_make_structure_ambiguous(structures_extra):
    text = "data_metadata\n_audit_creation_method 'Authored test fixture'\n\n" + cif_fixture(
        "al_fcc"
    )
    result = require_success(calculate(text))
    assert result["source_block"] == "al_fcc"
    assert result["atomic_counts"] == {"Al": 4}


def test_asymmetric_site_limit_accepts_256_sites_and_rejects_257(structures_extra):
    rows = [f"Al{i} Al {i / 1000:.6f} 0.2 0.3 1" for i in range(257)]
    result = require_success(calculate(p1_cif("\n".join(rows[:256]))))
    assert result["atom_count"] == 256
    require_error(calculate(p1_cif("\n".join(rows))))


def test_expanded_cell_at_2048_atom_limit_is_supported(structures_extra):
    # P m m m (47) has eight operations; all 256 sites are general positions.
    rows = [f"Al{i} Al {0.001 + i * 0.0008:.6f} 0.237 0.319 1" for i in range(256)]
    text = p1_cif("\n".join(rows)).replace(
        "_space_group_IT_number 1\n", "_space_group_IT_number 47\n"
    )
    result = require_success(calculate(text))
    assert result["atom_count"] == 2048
    assert result["atomic_counts"] == {"Al": 2048}
    assert len(periodic_sites(result)) == 2048


def test_cif_text_at_100000_character_limit_is_supported(structures_extra):
    text = p1_cif()
    padded = text + "#" + "a" * (100000 - len(text) - 2) + "\n"
    assert len(padded) == 100000
    result = require_success(calculate(padded))
    assert result["atomic_counts"] == {"Al": 1}


def test_conservative_symmetry_expansion_limit_is_enforced(structures_extra):
    # Space group 225 has 192 operations. Eleven general-position sites
    # exceed the declared 2048-site preflight bound before expansion.
    rows = [f"Al{i} Al {0.013 + i / 1000:.6f} 0.127 0.263 1" for i in range(11)]
    text = p1_cif("\n".join(rows)).replace(
        "_space_group_IT_number 1\n", "_space_group_IT_number 225\n"
    )
    require_error(calculate(text))


def test_declared_fcc_group_cannot_be_replaced_with_identity_only(structures_extra):
    text = cif_fixture("al_fcc").replace(
        "loop_\n_atom_site_label",
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\nloop_\n_atom_site_label",
    )
    require_error(calculate(text))


def test_inconsistent_declared_spacegroup_number_and_name_are_rejected(structures_extra):
    text = cif_fixture("al_fcc").replace("'F m -3 m'", "'P 1'")
    require_error(calculate(text))


def test_screw_group_declaration_cannot_be_replaced_with_pure_twofold_rotation(
    structures_extra,
):
    # P 21 (4) requires a b/2 screw translation; P 2 operations are not equivalent.
    text = p1_cif().replace(
        "_space_group_IT_number 1\n",
        "_space_group_IT_number 4\nloop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'-x,y,-z'\n",
    )
    require_error(calculate(text))


@pytest.mark.parametrize("number", [0, 231, 1.5, "?", ".", "nan"])
def test_invalid_spacegroup_numbers_are_rejected(structures_extra, number):
    text = p1_cif().replace("_space_group_IT_number 1\n", f"_space_group_IT_number {number}\n")
    require_error(calculate(text))


def test_explicit_inversion_symmetry_expands_two_general_position_sites(structures_extra):
    text = p1_cif("Al1 Al 0.125 0.25 0.375 1").replace(
        "_space_group_IT_number 1\n",
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'-x,-y,-z'\n",
    )
    result = require_success(calculate(text))
    assert periodic_sites(result) == {
        ("Al", 0.125, 0.25, 0.375),
        ("Al", 0.875, 0.75, 0.625),
    }
    assert result["atomic_counts"] == {"Al": 2}


def test_complete_translation_group_expands_three_sites(structures_extra):
    text = p1_cif("Al1 Al 0.125 0.25 0.375 1").replace(
        "_space_group_IT_number 1\n",
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'x+1/3,y,z'\n'x+2/3,y,z'\n",
    )
    result = require_success(calculate(text))
    assert result["atom_count"] == 3
    assert result["atomic_counts"] == {"Al": 3}
    assert sorted(site[1] for site in periodic_sites(result)) == pytest.approx(
        [0.125, 0.125 + 1 / 3, 0.125 + 2 / 3], rel=1e-9, abs=1e-10
    )


def test_incomplete_translation_group_is_rejected(structures_extra):
    text = p1_cif().replace(
        "_space_group_IT_number 1\n",
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'x+1/3,y,z'\n",
    )
    require_error(calculate(text))


def test_declared_inversion_with_roundoff_uses_canonical_special_position(structures_extra):
    # The inversion displacement is at the matching tolerance. Canonical SG2
    # expansion preserves the special-position multiplicity instead of creating
    # an additional atom from serialization roundoff.
    text = p1_cif("Al1 Al 0 0 0 1").replace(
        "_space_group_IT_number 1\n",
        "_space_group_IT_number 2\n"
        "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'-x+0.00000001,-y,-z'\n",
    )
    response = calculate(text)
    result = require_success(response)
    assert result["atom_count"] == 1
    assert periodic_sites(result) == {("Al", 0.0, 0.0, 0.0)}
    assert any(
        "symmetry operations" in warning and "normalized" in warning
        for warning in response.warnings
    )


@pytest.mark.parametrize("declared_group", [False, True])
def test_near_identity_distinct_translations_are_rejected(structures_extra, declared_group):
    operations = "loop_\n_space_group_symop_operation_xyz\n'x,y,z'\n'x+0.00000001,y,z'\n"
    declaration = "_space_group_IT_number 1\n" if declared_group else ""
    text = p1_cif().replace("_space_group_IT_number 1\n", declaration + operations)
    require_error(calculate(text))


@pytest.mark.parametrize(
    "operations",
    [
        "'-x,-y,-z'",  # Missing identity.
        "'x,y,z'\n'x,x,z'",  # Singular rotation.
        "'x,y,z'\n'y,x,z'",  # Swapping unequal a and b violates the metric.
        "'x,y,z'\n'x+1/0,y,z'",  # Undefined translation.
        "'x,y,z'\n'x**2,y,z'",  # Not a linear coordinate expression.
    ],
)
def test_invalid_explicit_symmetry_is_rejected(structures_extra, operations):
    text = p1_cif().replace(
        "_space_group_IT_number 1\n",
        f"loop_\n_space_group_symop_operation_xyz\n{operations}\n",
    )
    require_error(calculate(text))


def test_cif_numeric_uncertainty_uses_central_value_with_same_geometry(structures_extra):
    ordinary = require_success(calculate(p1_cif()))
    text = p1_cif().replace("_cell_length_a 3\n", "_cell_length_a 3.0(2)\n")
    result = require_success(calculate(text))
    assert result["cell_volume_angstrom3"] == ordinary["cell_volume_angstrom3"]
    assert result["density_kg_m3"] == ordinary["density_kg_m3"]


def test_duplicate_scalar_tags_are_rejected_instead_of_overwritten(structures_extra):
    text = p1_cif().replace("_cell_length_a 3\n", "_cell_length_a 3\n_cell_length_a 4\n")
    require_error(calculate(text))


def test_duplicate_loop_tags_are_rejected_instead_of_overwritten(structures_extra):
    text = p1_cif().replace("_atom_site_fract_x\n", "_atom_site_fract_x\n_atom_site_fract_x\n")
    text = text.replace("Al1 Al 0.1 0.2 0.3 1", "Al1 Al 0.1 0.1 0.2 0.3 1")
    require_error(calculate(text))


@pytest.mark.parametrize("value", ["3.0(2", "3.0(abc)", "3.0(1)(2)"])
def test_malformed_numeric_uncertainty_is_rejected(structures_extra, value):
    text = p1_cif().replace("_cell_length_a 3\n", f"_cell_length_a {value}\n")
    require_error(calculate(text))


@pytest.mark.parametrize("row", ["Al1 Al 0.1 0.2 0.3", "Al1 Al 0.1 0.2 0.3 1 9"])
def test_malformed_atom_loop_row_is_rejected(structures_extra, row):
    require_error(calculate(p1_cif(row)))


def test_cif2_syntax_marker_is_rejected_explicitly(structures_extra):
    error = require_error(calculate("#\\#CIF_2.0\n" + p1_cif()))
    assert "CIF 2.0" in error.message


def test_descriptors_and_input_schema_work_without_optional_ase():
    descriptor = describe_tool(TOOL)
    assert descriptor["version"] == "1"
    assert descriptor["side_effects"] == []
    assert descriptor["network_access"] is False
    assert {"ase", "numpy", "periodictable"} <= set(descriptor["dependencies"])
    assert descriptor["assumptions"]
    assert descriptor["references"]
    for schema in (descriptor["input_schema"], descriptor["output_schema"]):
        Draft202012Validator.check_schema(schema)
    cif_schema = descriptor["input_schema"]["properties"]["cif_text"]
    assert cif_schema["maxLength"] == 100000
    text = cif_fixture("al_fcc")
    assert validate_input(TOOL, {"cif_text": text}) == {"cif_text": text}


def test_missing_structures_extra_has_actionable_error_and_preserves_other_tools(monkeypatch):
    original_import = builtins.__import__

    def without_ase(name, *args, **kwargs):
        if name == "ase" or name.startswith("ase."):
            raise ModuleNotFoundError("ASE unavailable", name=name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_ase)
    response = calculate(cif_fixture("al_fcc"))
    error = require_error(response, "MISSING_DEPENDENCY")
    assert "materials-agent-toolkit[structures]" in error.message
    assert response.provenance.input_sha256
    assert describe_tool(TOOL)["version"] == "1"
    assert validate_input(TOOL, {"cif_text": "data_test"}) == {"cif_text": "data_test"}
    assert require_success(run_tool("composition.analyze", {"formula": "H2O"}))[
        "atomic_counts"
    ] == {"H": 2.0, "O": 1.0}


def test_success_result_schema_and_provenance_record_parser_and_mass_sources(structures_extra):
    descriptor = describe_tool(TOOL)
    text = cif_fixture("al_fcc")
    response = calculate(text, tool_version="1")
    result = require_success(response)
    Draft202012Validator(descriptor["output_schema"]).validate(result)
    Draft202012Validator(ToolResponse.model_json_schema()).validate(
        response.model_dump(mode="json")
    )
    assert response.provenance.references == descriptor["references"]
    for dependency in ("ase", "numpy", "periodictable"):
        assert response.provenance.software_versions[dependency] != "not-installed"
    assert response.provenance.input_sha256
    assert response.warnings


def test_raw_cif_hash_is_reproducible_and_sensitive_to_source_text(structures_extra):
    text = cif_fixture("al_fcc")
    first = calculate(text)
    repeated = calculate(text)
    commented = calculate("# Additional provenance comment\n" + text)
    assert require_success(first) == require_success(repeated) == require_success(commented)
    assert first.provenance.input_sha256 == repeated.provenance.input_sha256
    assert first.provenance.input_sha256 != commented.provenance.input_sha256


def test_unsupported_tool_version_is_rejected_before_parser_execution():
    require_error(calculate(cif_fixture("al_fcc"), tool_version="2"), "UNSUPPORTED_VERSION")
