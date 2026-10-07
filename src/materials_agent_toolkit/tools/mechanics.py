"""Linear elastic calculations with explicit stress units and tensor conventions."""

from typing import Annotated, Literal

import numpy as np
from pydantic import Field, FiniteFloat

from ..contracts import CalculationResult, StrictModel, ToolSpec

StressUnit = Literal["Pa", "MPa", "GPa"]
PositiveFloat = Annotated[float, Field(gt=0)]
StiffnessRow = Annotated[list[FiniteFloat], Field(min_length=6, max_length=6)]
StiffnessMatrix = Annotated[list[StiffnessRow], Field(min_length=6, max_length=6)]


class IsotropicModuliInput(StrictModel):
    young_modulus: PositiveFloat
    poisson_ratio: Annotated[float, Field(gt=-1, lt=0.5)]
    stress_unit: StressUnit = "GPa"


class IsotropicModuliOutput(StrictModel):
    young_modulus: PositiveFloat
    poisson_ratio: Annotated[float, Field(gt=-1, lt=0.5)]
    shear_modulus: PositiveFloat
    bulk_modulus: PositiveFloat
    lame_first_parameter: float
    stress_unit: StressUnit


class ElasticVRHInput(StrictModel):
    stiffness_matrix: StiffnessMatrix = Field(
        description=(
            "Symmetric 6x6 stiffness matrix in engineering Voigt order "
            "xx, yy, zz, yz, xz, xy. Shear strains are 2*epsilon_yz, "
            "2*epsilon_xz, 2*epsilon_xy. Relative symmetry tolerance: 1e-10 "
            "of the largest matrix entry. The Kelvin matrix must be "
            "positive definite with condition number below 1e12."
        )
    )
    stress_unit: StressUnit = "GPa"


class ElasticVRHOutput(StrictModel):
    bulk_modulus_voigt: PositiveFloat
    bulk_modulus_reuss: PositiveFloat
    bulk_modulus_hill: PositiveFloat
    shear_modulus_voigt: PositiveFloat
    shear_modulus_reuss: PositiveFloat
    shear_modulus_hill: PositiveFloat
    young_modulus_hill: PositiveFloat
    poisson_ratio_hill: Annotated[float, Field(gt=-1, lt=0.5)]
    universal_anisotropy_index: Annotated[float, Field(ge=0)]
    stress_unit: StressUnit
    aggregate_assumption: Literal["isotropic polycrystalline aggregate"] = (
        "isotropic polycrystalline aggregate"
    )


def _require_finite(values: np.ndarray) -> None:
    if not np.all(np.isfinite(values)):
        raise ValueError("Calculated moduli exceed the supported finite numeric range.")


def calculate_isotropic_moduli(inputs: IsotropicModuliInput) -> CalculationResult:
    """Convert E and nu using the small-strain isotropic elastic relations."""
    young = inputs.young_modulus
    poisson = inputs.poisson_ratio
    shear = young / (2.0 * (1.0 + poisson))
    bulk = young / (3.0 * (1.0 - 2.0 * poisson))
    # Form a dimensionless coefficient first to avoid avoidable intermediate
    # overflow (for example, a very large modulus with nu == 0).
    lame = young * (poisson / ((1.0 + poisson) * (1.0 - 2.0 * poisson)))
    _require_finite(np.array([young, shear, bulk, lame]))
    if shear <= 0 or bulk <= 0:
        raise ValueError("Calculated moduli underflow the supported positive numeric range.")
    warnings = []
    if min(1.0 + poisson, 1.0 - 2.0 * poisson) < 1e-8:
        warnings.append(
            "Poisson ratio is close to a stability boundary; moduli are highly "
            "sensitive to its precision."
        )
    return CalculationResult(
        IsotropicModuliOutput(
            young_modulus=young,
            poisson_ratio=poisson,
            shear_modulus=shear,
            bulk_modulus=bulk,
            lame_first_parameter=lame,
            stress_unit=inputs.stress_unit,
        ),
        warnings=warnings,
    )


def calculate_elastic_vrh(inputs: ElasticVRHInput) -> CalculationResult:
    """Estimate isotropic aggregate moduli and the universal anisotropy index."""
    stiffness = np.asarray(inputs.stiffness_matrix, dtype=float)
    scale = float(np.max(np.abs(stiffness)))
    if scale == 0:
        raise ValueError("Stiffness matrix must be positive definite.")

    # Scale before subtraction, averaging, eigensolving, and conversion to Kelvin
    # notation, so large or small stress units do not impair the calculation.
    normalized = stiffness / scale
    asymmetry = float(np.max(np.abs(normalized - normalized.T)))
    if asymmetry > 1e-10:
        raise ValueError("Stiffness matrix must be symmetric within 1e-10 of its largest entry.")
    normalized = (normalized + normalized.T) / 2.0
    kelvin_factors = np.array([1.0, 1.0, 1.0, np.sqrt(2.0), np.sqrt(2.0), np.sqrt(2.0)])
    kelvin = normalized * kelvin_factors[:, None] * kelvin_factors[None, :]
    eigenvalues = np.linalg.eigvalsh(kelvin)
    if eigenvalues[0] <= 0:
        raise ValueError("Stiffness matrix must be positive definite (elastically stable).")
    condition_number = float(eigenvalues[-1] / eigenvalues[0])
    if condition_number >= 1e12:
        raise ValueError(
            "Stiffness matrix is too ill-conditioned: its Kelvin condition number "
            "must be below 1e12."
        )

    # Orthonormal volumetric and deviatoric Kelvin tensor bases. Quadratic forms
    # in these bases reproduce the engineering-Voigt VRH formulae while avoiding
    # cancellation in compliance sums and avoiding an explicit matrix inverse.
    volumetric = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0]) / np.sqrt(3.0)
    deviatoric = np.array(
        [
            [1.0 / np.sqrt(2.0), -1.0 / np.sqrt(2.0), 0.0, 0.0, 0.0, 0.0],
            [1.0 / np.sqrt(6.0), 1.0 / np.sqrt(6.0), -2.0 / np.sqrt(6.0), 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ]
    ).T
    cholesky = np.linalg.cholesky(kelvin)
    volumetric_compliance = np.linalg.solve(cholesky, volumetric)
    deviatoric_compliance = np.linalg.solve(cholesky, deviatoric)
    bulk_voigt = float(volumetric @ kelvin @ volumetric / 3.0)
    shear_voigt = float(np.trace(deviatoric.T @ kelvin @ deviatoric) / 10.0)
    bulk_reuss = float(1.0 / (3.0 * np.sum(volumetric_compliance**2)))
    shear_reuss = float(5.0 / (2.0 * np.sum(deviatoric_compliance**2)))
    bulk_hill = (bulk_voigt + bulk_reuss) / 2.0
    shear_hill = (shear_voigt + shear_reuss) / 2.0
    denominator = 3.0 * bulk_hill + shear_hill
    young_hill = 9.0 * bulk_hill * (shear_hill / denominator)
    poisson_hill = (3.0 * bulk_hill - 2.0 * shear_hill) / (2.0 * denominator)
    anisotropy = 5.0 * shear_voigt / shear_reuss + bulk_voigt / bulk_reuss - 6.0
    # AU is nonnegative by construction; small negative values arise at isotropy
    # from floating-point rounding of the Voigt/Reuss ratios.
    if anisotropy < -1e-10:
        raise ValueError("Numerical precision is insufficient for the anisotropy calculation.")
    anisotropy = max(0.0, anisotropy)
    with np.errstate(over="ignore", under="ignore"):
        moduli = (
            np.array(
                [
                    bulk_voigt,
                    bulk_reuss,
                    bulk_hill,
                    shear_voigt,
                    shear_reuss,
                    shear_hill,
                    young_hill,
                ]
            )
            * scale
        )
    _require_finite(moduli)
    if np.any(moduli <= 0):
        raise ValueError("Calculated moduli underflow the supported positive numeric range.")

    warnings = []
    if asymmetry > 0:
        warnings.append("Small stiffness asymmetry within tolerance was symmetrized.")
    if condition_number > 1e8:
        warnings.append(
            "Stiffness is poorly conditioned; aggregate moduli may be sensitive "
            "to numerical precision and input uncertainty."
        )
    return CalculationResult(
        ElasticVRHOutput(
            bulk_modulus_voigt=float(moduli[0]),
            bulk_modulus_reuss=float(moduli[1]),
            bulk_modulus_hill=float(moduli[2]),
            shear_modulus_voigt=float(moduli[3]),
            shear_modulus_reuss=float(moduli[4]),
            shear_modulus_hill=float(moduli[5]),
            young_modulus_hill=float(moduli[6]),
            poisson_ratio_hill=poisson_hill,
            universal_anisotropy_index=anisotropy,
            stress_unit=inputs.stress_unit,
        ),
        warnings=warnings,
    )


TOOLS = [
    ToolSpec(
        name="mechanics.isotropic_moduli",
        description="Convert isotropic Young's modulus and Poisson ratio to elastic moduli.",
        input_model=IsotropicModuliInput,
        output_model=IsotropicModuliOutput,
        execute=calculate_isotropic_moduli,
        assumptions=(
            "Homogeneous isotropic, small-strain linear elasticity.",
            "Young's modulus is positive and -1 < Poisson ratio < 0.5.",
            "All output moduli have the same explicit stress unit as Young's modulus.",
        ),
        references=("https://en.wikipedia.org/wiki/Lam%C3%A9_parameters",),
        dependencies=("numpy",),
    ),
    ToolSpec(
        name="mechanics.elastic_vrh",
        description=(
            "Compute Voigt, Reuss, and Hill isotropic aggregate elastic moduli and "
            "universal anisotropy from a stable 6x6 stiffness matrix."
        ),
        input_model=ElasticVRHInput,
        output_model=ElasticVRHOutput,
        execute=calculate_elastic_vrh,
        assumptions=(
            "Engineering Voigt order is xx, yy, zz, yz, xz, xy; shear strains are twice tensor shear strains.",
            "The stiffness matrix represents positive-definite small-strain elasticity.",
            "Hill moduli describe an isotropic polycrystalline aggregate with random orientations.",
            "Symmetry tolerance is 1e-10 of the largest entry; Kelvin condition number must be below 1e12.",
            "All output moduli retain the input stiffness stress unit; Poisson ratio and anisotropy are dimensionless.",
        ),
        references=(
            "https://doi.org/10.1088/0370-1298/65/5/307",
            "https://doi.org/10.1103/PhysRevLett.101.055504",
        ),
        dependencies=("numpy",),
    ),
]
