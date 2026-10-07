"""Analytical elastic benchmarks and rejection of invalid tensor inputs."""

import math

import numpy as np
import pytest
from pydantic import ValidationError

from materials_agent_toolkit.tools.mechanics import (
    ElasticVRHInput,
    IsotropicModuliInput,
    calculate_elastic_vrh,
    calculate_isotropic_moduli,
)


def cubic_stiffness(c11: float, c12: float, c44: float) -> list[list[float]]:
    matrix = np.zeros((6, 6))
    matrix[:3, :3] = c12
    np.fill_diagonal(matrix[:3, :3], c11)
    matrix[3:, 3:] = np.eye(3) * c44
    return matrix.tolist()


def test_isotropic_moduli_steel_reference():
    result = calculate_isotropic_moduli(
        IsotropicModuliInput(young_modulus=210.0, poisson_ratio=0.3)
    ).result
    assert result.young_modulus == 210.0
    assert result.shear_modulus == pytest.approx(80.76923076923077)
    assert result.bulk_modulus == pytest.approx(175.0)
    assert result.lame_first_parameter == pytest.approx(121.15384615384616)
    assert result.stress_unit == "GPa"


def test_auxetic_material_has_negative_lame_parameter_and_positive_moduli():
    result = calculate_isotropic_moduli(
        IsotropicModuliInput(young_modulus=12.0, poisson_ratio=-0.5, stress_unit="MPa")
    ).result
    assert result.shear_modulus == pytest.approx(12.0)
    assert result.bulk_modulus == pytest.approx(2.0)
    assert result.lame_first_parameter == pytest.approx(-6.0)
    assert result.stress_unit == "MPa"


@pytest.mark.parametrize(
    "young,poisson",
    [(0.0, 0.3), (-1.0, 0.3), (1.0, -1.0), (1.0, 0.5), (math.inf, 0.3), (1.0, math.nan)],
)
def test_invalid_isotropic_inputs(young, poisson):
    with pytest.raises(ValidationError):
        IsotropicModuliInput(young_modulus=young, poisson_ratio=poisson)


def test_large_finite_isotropic_modulus_avoids_intermediate_overflow():
    result = calculate_isotropic_moduli(
        IsotropicModuliInput(young_modulus=1.7e308, poisson_ratio=0.0, stress_unit="Pa")
    ).result
    assert result.lame_first_parameter == 0.0
    assert result.shear_modulus == 8.5e307


def test_unrepresentable_isotropic_output_is_rejected():
    with pytest.raises(ValueError, match="finite numeric range"):
        calculate_isotropic_moduli(IsotropicModuliInput(young_modulus=1e308, poisson_ratio=0.49))


def test_vrh_isotropic_tensor_matches_steel_reference():
    result = calculate_elastic_vrh(
        ElasticVRHInput(
            stiffness_matrix=cubic_stiffness(
                282.6923076923077, 121.15384615384616, 80.76923076923077
            )
        )
    ).result
    for field in ("bulk_modulus_voigt", "bulk_modulus_reuss", "bulk_modulus_hill"):
        assert getattr(result, field) == pytest.approx(175.0)
    for field in ("shear_modulus_voigt", "shear_modulus_reuss", "shear_modulus_hill"):
        assert getattr(result, field) == pytest.approx(80.76923076923077)
    assert result.young_modulus_hill == pytest.approx(210.0)
    assert result.poisson_ratio_hill == pytest.approx(0.3)
    assert result.universal_anisotropy_index == pytest.approx(0.0, abs=1e-12)
    assert result.aggregate_assumption == "isotropic polycrystalline aggregate"


def test_cubic_copper_anisotropy_matches_closed_form():
    # Cubic crystals have K = (C11 + 2*C12)/3 for both bounds, and
    # G_V = (C11-C12+3*C44)/5, G_R = 5*(C11-C12)*C44/(4*C44+3*(C11-C12)).
    result = calculate_elastic_vrh(
        ElasticVRHInput(stiffness_matrix=cubic_stiffness(168.4, 121.4, 75.4))
    ).result
    expected_bulk = 137.06666666666666
    expected_reuss_shear = 17719.0 / 442.6
    expected_hill_shear = (54.64 + expected_reuss_shear) / 2.0
    assert result.bulk_modulus_voigt == pytest.approx(expected_bulk)
    assert result.bulk_modulus_reuss == pytest.approx(expected_bulk)
    assert result.shear_modulus_voigt == pytest.approx(54.64)
    assert result.shear_modulus_reuss == pytest.approx(expected_reuss_shear)
    assert result.shear_modulus_hill == pytest.approx(expected_hill_shear)
    assert result.universal_anisotropy_index == pytest.approx(
        5.0 * 54.64 / expected_reuss_shear - 5.0
    )
    assert result.shear_modulus_reuss < result.shear_modulus_hill < result.shear_modulus_voigt


def test_isotropic_negative_poisson_tensor_uses_engineering_shear_convention():
    # E=12, nu=-0.5 gives lambda=-6 and mu=12, hence C11=18, C12=-6.
    result = calculate_elastic_vrh(
        ElasticVRHInput(stiffness_matrix=cubic_stiffness(18.0, -6.0, 12.0))
    ).result
    assert result.bulk_modulus_hill == pytest.approx(2.0)
    assert result.shear_modulus_hill == pytest.approx(12.0)
    assert result.young_modulus_hill == pytest.approx(12.0)
    assert result.poisson_ratio_hill == pytest.approx(-0.5)


def test_units_scale_dimensional_outputs_only():
    gpa_matrix = np.array(cubic_stiffness(168.4, 121.4, 75.4))
    gpa = calculate_elastic_vrh(ElasticVRHInput(stiffness_matrix=gpa_matrix.tolist())).result
    pa = calculate_elastic_vrh(
        ElasticVRHInput(stiffness_matrix=(gpa_matrix * 1e9).tolist(), stress_unit="Pa")
    ).result
    assert pa.bulk_modulus_hill == pytest.approx(gpa.bulk_modulus_hill * 1e9)
    assert pa.shear_modulus_hill == pytest.approx(gpa.shear_modulus_hill * 1e9)
    assert pa.young_modulus_hill == pytest.approx(gpa.young_modulus_hill * 1e9)
    assert pa.poisson_ratio_hill == pytest.approx(gpa.poisson_ratio_hill)
    assert pa.universal_anisotropy_index == pytest.approx(gpa.universal_anisotropy_index)
    assert pa.stress_unit == "Pa"


@pytest.mark.parametrize("matrix", [[[1.0]], [[1.0] * 6] * 5, [[1.0] * 5] * 6])
def test_malformed_stiffness_shape_is_rejected(matrix):
    with pytest.raises(ValidationError):
        ElasticVRHInput(stiffness_matrix=matrix)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_stiffness_is_rejected(value):
    matrix = cubic_stiffness(18.0, -6.0, 12.0)
    matrix[0][0] = value
    with pytest.raises(ValidationError):
        ElasticVRHInput(stiffness_matrix=matrix)


def test_asymmetric_stiffness_is_rejected():
    matrix = cubic_stiffness(18.0, -6.0, 12.0)
    matrix[0][1] = -5.0
    with pytest.raises(ValueError, match="symmetric"):
        calculate_elastic_vrh(ElasticVRHInput(stiffness_matrix=matrix))


def test_roundoff_asymmetry_is_symmetrized_and_reported():
    matrix = cubic_stiffness(18.0, -6.0, 12.0)
    matrix[0][1] += 1e-12
    result = calculate_elastic_vrh(ElasticVRHInput(stiffness_matrix=matrix))
    assert result.result.bulk_modulus_hill == pytest.approx(2.0)
    assert any("symmetrized" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    "diagonal", [[0.0] * 6, [1.0, 1.0, 1.0, 1.0, 1.0, 0.0], [1.0, 1.0, 1.0, 1.0, 1.0, -1.0]]
)
def test_nonpositive_stiffness_is_rejected(diagonal):
    with pytest.raises(ValueError, match="positive definite"):
        calculate_elastic_vrh(ElasticVRHInput(stiffness_matrix=np.diag(diagonal).tolist()))


def test_near_singular_stiffness_is_rejected():
    matrix = np.diag([1.0, 1.0, 1.0, 1.0, 1.0, 1e-15]).tolist()
    with pytest.raises(ValueError, match="ill-conditioned"):
        calculate_elastic_vrh(ElasticVRHInput(stiffness_matrix=matrix))
