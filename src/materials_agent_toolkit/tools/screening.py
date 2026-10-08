"""Evaluate supplied, traceable property evidence against explicit constraints.

This module performs bounded comparisons and SI normalization, not property
prediction or source verification. Possibility intervals have no probabilistic
interpretation. All arithmetic and comparisons use binary64 with no tolerance.
"""

import math
from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from ..contracts import CalculationResult, StrictModel, ToolSpec

Quantity = Literal[
    "density",
    "elastic_modulus",
    "thermal_conductivity",
    "linear_expansion_coefficient",
    "specific_capacity",
    "mass_fraction",
    "length",
    "area",
    "volume",
    "mass",
    "time",
    "temperature",
    "diffusivity",
    "dimensionless",
]
Unit = Literal[
    "kg/m3",
    "g/cm3",
    "g/mL",
    "Pa",
    "kPa",
    "MPa",
    "GPa",
    "W/(m*K)",
    "W/(cm*K)",
    "1/K",
    "1/degC",
    "microstrain/K",
    "C/kg",
    "Ah/kg",
    "mAh/g",
    "1",
    "%",
    "m",
    "cm",
    "mm",
    "um",
    "m2",
    "cm2",
    "mm2",
    "m3",
    "L",
    "mL",
    "cm3",
    "kg",
    "g",
    "mg",
    "s",
    "min",
    "h",
    "K",
    "degC",
    "m2/s",
    "cm2/s",
]
SIUnit = Literal[
    "kg/m3",
    "Pa",
    "W/(m*K)",
    "1/K",
    "C/kg",
    "1",
    "m",
    "m2",
    "m3",
    "kg",
    "s",
    "K",
    "m2/s",
]
EvidenceKind = Literal["measurement", "manufacturer", "calculation", "assumption"]
ScreeningStatus = Literal["pass", "fail", "unknown"]
CheckReason = Literal[
    "within_bounds",
    "outside_bounds",
    "interval_overlaps_bound",
    "missing_property",
    "evidence_not_allowed",
    "condition_mismatch",
]
Identifier = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"),
]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must contain non-whitespace characters")
    # Preserve the supplied source and context text, including its spacing.
    return value


NonblankText = Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_nonblank)]
Conditions = Annotated[dict[Identifier, NonblankText], Field(max_length=16)]

# Every conversion is value_SI = value * factor + offset. Unit symbols are
# deliberately closed; semantic equivalence between property IDs is not inferred.
_UNIT_DEFINITIONS: dict[str, tuple[str, str, dict[str, tuple[float, float]]]] = {
    "density": (
        "kg/m3",
        "strictly_positive",
        {"kg/m3": (1.0, 0.0), "g/cm3": (1000.0, 0.0), "g/mL": (1000.0, 0.0)},
    ),
    "elastic_modulus": (
        "Pa",
        "strictly_positive",
        {
            "Pa": (1.0, 0.0),
            "kPa": (1000.0, 0.0),
            "MPa": (1e6, 0.0),
            "GPa": (1e9, 0.0),
        },
    ),
    "thermal_conductivity": (
        "W/(m*K)",
        "strictly_positive",
        {"W/(m*K)": (1.0, 0.0), "W/(cm*K)": (100.0, 0.0)},
    ),
    "linear_expansion_coefficient": (
        "1/K",
        "signed",
        {"1/K": (1.0, 0.0), "1/degC": (1.0, 0.0), "microstrain/K": (1e-6, 0.0)},
    ),
    "specific_capacity": (
        "C/kg",
        "nonnegative",
        {"C/kg": (1.0, 0.0), "Ah/kg": (3600.0, 0.0), "mAh/g": (3600.0, 0.0)},
    ),
    "mass_fraction": ("1", "zero_to_one", {"1": (1.0, 0.0), "%": (0.01, 0.0)}),
    "length": (
        "m",
        "nonnegative",
        {"m": (1.0, 0.0), "cm": (0.01, 0.0), "mm": (0.001, 0.0), "um": (1e-6, 0.0)},
    ),
    "area": (
        "m2",
        "nonnegative",
        {"m2": (1.0, 0.0), "cm2": (1e-4, 0.0), "mm2": (1e-6, 0.0)},
    ),
    "volume": (
        "m3",
        "nonnegative",
        {"m3": (1.0, 0.0), "L": (0.001, 0.0), "mL": (1e-6, 0.0), "cm3": (1e-6, 0.0)},
    ),
    "mass": (
        "kg",
        "nonnegative",
        {"kg": (1.0, 0.0), "g": (0.001, 0.0), "mg": (1e-6, 0.0)},
    ),
    "time": ("s", "nonnegative", {"s": (1.0, 0.0), "min": (60.0, 0.0), "h": (3600.0, 0.0)}),
    "temperature": ("K", "nonnegative", {"K": (1.0, 0.0), "degC": (1.0, 273.15)}),
    "diffusivity": ("m2/s", "nonnegative", {"m2/s": (1.0, 0.0), "cm2/s": (1e-4, 0.0)}),
    "dimensionless": ("1", "signed", {"1": (1.0, 0.0)}),
}
QUANTITY_UNIT_MAP = {
    quantity: {
        "si_unit": si_unit,
        "record_domain": domain,
        "units": {
            unit: {"factor": factor, "offset": offset} for unit, (factor, offset) in units.items()
        },
    }
    for quantity, (si_unit, domain, units) in _UNIT_DEFINITIONS.items()
}


def _to_si(quantity: Quantity, unit: Unit, value: float) -> float:
    """Convert a validated scalar, rejecting nonfinite values and lost magnitude."""
    _, _, units = _UNIT_DEFINITIONS[quantity]
    if unit not in units:
        raise ValueError(f"Unit {unit!r} is incompatible with quantity {quantity!r}")
    factor, offset = units[unit]
    scaled = value * factor
    if not math.isfinite(scaled):
        raise ValueError("Unit conversion exceeds the finite binary64 range")
    if value != 0.0 and scaled == 0.0:
        raise ValueError("Unit conversion underflows a nonzero value to zero")
    converted = scaled + offset
    if not math.isfinite(converted):
        raise ValueError("Unit conversion exceeds the finite binary64 range")
    # Celsius at -273.15 maps to zero kelvin by subtraction, not underflow.
    return converted


def _check_record_domain(quantity: Quantity, value: float) -> None:
    domain = _UNIT_DEFINITIONS[quantity][1]
    if domain == "strictly_positive" and value <= 0:
        raise ValueError(f"{quantity} records and interval endpoints must be strictly positive")
    if domain == "nonnegative" and value < 0:
        raise ValueError(f"{quantity} records and interval endpoints must be nonnegative in SI")
    if domain == "zero_to_one" and not 0 <= value <= 1:
        raise ValueError("mass_fraction records and interval endpoints must lie in [0, 1] in SI")


class EvidenceSource(StrictModel):
    citation: NonblankText = Field(
        description="Required supplied citation; authenticity is not checked."
    )
    locator: NonblankText | None = Field(
        default=None,
        description="Optional supplied page, table, URL fragment, or other precise source locator.",
    )


class PropertyInterval(StrictModel):
    lower: FiniteFloat = Field(
        description="Inclusive lower possibility endpoint, in the record unit."
    )
    upper: FiniteFloat = Field(
        description="Inclusive upper possibility endpoint, in the record unit."
    )
    basis: NonblankText = Field(
        description="Supplied explanation of this range; it is not assigned confidence or probability."
    )

    @model_validator(mode="after")
    def validate_order(self) -> "PropertyInterval":
        if self.lower > self.upper:
            raise ValueError("Interval lower endpoint must not exceed upper endpoint")
        return self


class PropertyRecord(StrictModel):
    quantity: Quantity = Field(
        description="Named physical quantity, not a signed change in that quantity."
    )
    value: FiniteFloat = Field(
        description="Supplied point value in unit; missing evidence must be omitted."
    )
    unit: Unit = Field(
        description="Explicit closed unit symbol compatible with quantity; see x-quantity-unit-map."
    )
    evidence_kind: EvidenceKind = Field(
        description="Caller-declared evidence type; no authenticity check is performed."
    )
    source: EvidenceSource = Field(
        description="Required source citation and optional locator, retained verbatim."
    )
    conditions: Conditions = Field(
        default_factory=dict,
        description="Up to 16 explicit context tags; values match required tags exactly, with no inference.",
    )
    interval: PropertyInterval | None = Field(
        default=None,
        description="Optional supplied possibility range containing value; absent means the point [value, value].",
    )

    @model_validator(mode="after")
    def validate_quantity_domain(self) -> "PropertyRecord":
        normalized = _to_si(self.quantity, self.unit, self.value)
        _check_record_domain(self.quantity, normalized)
        if self.interval is not None:
            if not self.interval.lower <= self.value <= self.interval.upper:
                raise ValueError("Property value must lie inside its supplied interval")
            lower = _to_si(self.quantity, self.unit, self.interval.lower)
            upper = _to_si(self.quantity, self.unit, self.interval.upper)
            _check_record_domain(self.quantity, lower)
            _check_record_domain(self.quantity, upper)
            if not lower <= normalized <= upper:
                raise ValueError("Normalized interval must contain the normalized property value")
        return self


class ScreeningCandidate(StrictModel):
    candidate_id: Identifier = Field(
        description="Unique stable candidate identifier; input order is retained."
    )
    properties: dict[Identifier, PropertyRecord] = Field(
        max_length=32,
        description="Zero to 32 semantic property IDs and their evidence; omitted properties remain unknown.",
    )


class ScreeningConstraint(StrictModel):
    constraint_id: Identifier = Field(
        description="Unique stable constraint identifier; input order is retained."
    )
    property_id: Identifier = Field(
        description="Exact semantic property key; dimensional similarity does not imply equivalence."
    )
    quantity: Quantity = Field(
        description="Quantity required for this property ID throughout the entire request."
    )
    unit: Unit = Field(
        description="Compatible unit for the original bounds; SI conversion table is in the input schema."
    )
    minimum: FiniteFloat | None = Field(
        default=None, description="Optional inclusive lower bound; at least one bound is required."
    )
    maximum: FiniteFloat | None = Field(
        default=None, description="Optional inclusive upper bound; at least one bound is required."
    )
    required_conditions: Conditions = Field(
        default_factory=dict,
        description="Required subset of exact context tags; extra record tags are retained without applicability checks.",
    )
    allowed_evidence: list[EvidenceKind] = Field(
        default_factory=lambda: ["measurement"],
        min_length=1,
        max_length=4,
        json_schema_extra={"uniqueItems": True},
        description="Unique eligible evidence types; default permits measurement only.",
    )

    @model_validator(mode="after")
    def validate_bounds(self) -> "ScreeningConstraint":
        if self.minimum is None and self.maximum is None:
            raise ValueError("A constraint requires at least one bound")
        if len(self.allowed_evidence) != len(set(self.allowed_evidence)):
            raise ValueError("allowed_evidence must contain unique evidence kinds")
        minimum = (
            _to_si(self.quantity, self.unit, self.minimum) if self.minimum is not None else None
        )
        maximum = (
            _to_si(self.quantity, self.unit, self.maximum) if self.maximum is not None else None
        )
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("Constraint minimum must not exceed maximum")
            if minimum > maximum:
                raise ValueError("Normalized constraint minimum must not exceed maximum")
        # Thresholds deliberately have no physical-domain restriction: a
        # supplied criterion may be impossible to satisfy.
        return self


class ScreeningInput(StrictModel):
    model_config = ConfigDict(json_schema_extra={"x-quantity-unit-map": QUANTITY_UNIT_MAP})

    candidates: list[ScreeningCandidate] = Field(
        min_length=1,
        max_length=100,
        description="One to 100 candidates with unique IDs; each has at most 32 supplied property records.",
    )
    constraints: list[ScreeningConstraint] = Field(
        min_length=1,
        max_length=20,
        description="One to 20 constraints with unique IDs; each candidate is checked against every constraint.",
    )

    @model_validator(mode="after")
    def validate_identifiers_and_quantities(self) -> "ScreeningInput":
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Candidate IDs must be unique")
        constraint_ids = [constraint.constraint_id for constraint in self.constraints]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("Constraint IDs must be unique")
        quantities: dict[str, Quantity] = {}
        for candidate in self.candidates:
            for property_id, record in candidate.properties.items():
                _check_property_quantity(quantities, property_id, record.quantity)
        for constraint in self.constraints:
            _check_property_quantity(quantities, constraint.property_id, constraint.quantity)
        return self


def _check_property_quantity(
    quantities: dict[str, Quantity], property_id: str, quantity: Quantity
) -> None:
    if property_id in quantities and quantities[property_id] != quantity:
        raise ValueError(
            f"Property ID {property_id!r} has inconsistent quantities across the request"
        )
    quantities[property_id] = quantity


class NormalizedPropertyRecord(PropertyRecord):
    normalized_value: FiniteFloat = Field(
        description="Supplied value converted to si_unit using binary64 arithmetic."
    )
    si_unit: SIUnit = Field(description="Canonical SI unit for quantity.")
    normalized_interval: PropertyInterval | None = Field(
        default=None,
        description="Supplied interval converted to si_unit, retaining its basis; null when no interval was supplied.",
    )


class NormalizedConstraint(ScreeningConstraint):
    normalized_minimum: FiniteFloat | None = Field(
        default=None,
        description="Original minimum converted to si_unit; null for an unbounded lower side.",
    )
    normalized_maximum: FiniteFloat | None = Field(
        default=None,
        description="Original maximum converted to si_unit; null for an unbounded upper side.",
    )
    si_unit: SIUnit = Field(
        description="Canonical SI unit for quantity and both normalized bounds."
    )


class ScreeningCheck(StrictModel):
    constraint_id: Identifier = Field(description="Constraint producing this check.")
    property_id: Identifier = Field(
        description="Property key linking this check to its supplied source and context."
    )
    status: ScreeningStatus = Field(
        description="pass, fail, or unknown for this declared evidence and constraint."
    )
    reason: CheckReason = Field(
        description="Exact comparison or eligibility reason, without a ranking or prediction."
    )


class EvaluatedCandidate(StrictModel):
    candidate_id: Identifier = Field(description="Original candidate identifier.")
    status: ScreeningStatus = Field(
        description="fail if any check fails; otherwise unknown if any check is unknown; otherwise pass."
    )
    properties: dict[Identifier, NormalizedPropertyRecord] = Field(
        max_length=32,
        description="All supplied property records, with original evidence and normalized values retained.",
    )
    checks: list[ScreeningCheck] = Field(
        min_length=1,
        max_length=20,
        description="Every constraint result in stable constraint input order.",
    )


class ScreeningSummary(StrictModel):
    total: int = Field(ge=1, le=100, description="Number of evaluated candidates.")
    passed: int = Field(ge=0, le=100, description="Candidates whose every check passes.")
    failed: int = Field(
        ge=0,
        le=100,
        description="Candidates with at least one failed check, even if other checks are unknown.",
    )
    unknown: int = Field(
        ge=0, le=100, description="Candidates with no failed check and at least one unknown check."
    )


class ScreeningOutput(StrictModel):
    normalized_constraints: list[NormalizedConstraint] = Field(
        min_length=1,
        max_length=20,
        description="Original constraints and SI bounds in stable input order.",
    )
    candidates: list[EvaluatedCandidate] = Field(
        min_length=1,
        max_length=100,
        description="Evaluated candidates in stable input order; no winner or ranking is assigned.",
    )
    summary: ScreeningSummary = Field(
        description="Counts of candidate-level pass, fail, and unknown outcomes."
    )


def _normalize_property(record: PropertyRecord) -> NormalizedPropertyRecord:
    interval = record.interval
    normalized_interval = (
        PropertyInterval(
            lower=_to_si(record.quantity, record.unit, interval.lower),
            upper=_to_si(record.quantity, record.unit, interval.upper),
            basis=interval.basis,
        )
        if interval is not None
        else None
    )
    return NormalizedPropertyRecord(
        **record.model_dump(),
        normalized_value=_to_si(record.quantity, record.unit, record.value),
        si_unit=_UNIT_DEFINITIONS[record.quantity][0],
        normalized_interval=normalized_interval,
    )


def _normalize_constraint(constraint: ScreeningConstraint) -> NormalizedConstraint:
    return NormalizedConstraint(
        **constraint.model_dump(),
        normalized_minimum=(
            _to_si(constraint.quantity, constraint.unit, constraint.minimum)
            if constraint.minimum is not None
            else None
        ),
        normalized_maximum=(
            _to_si(constraint.quantity, constraint.unit, constraint.maximum)
            if constraint.maximum is not None
            else None
        ),
        si_unit=_UNIT_DEFINITIONS[constraint.quantity][0],
    )


def _check_constraint(
    properties: dict[str, NormalizedPropertyRecord], constraint: NormalizedConstraint
) -> ScreeningCheck:
    record = properties.get(constraint.property_id)
    if record is None:
        status, reason = "unknown", "missing_property"
    elif record.evidence_kind not in constraint.allowed_evidence:
        status, reason = "unknown", "evidence_not_allowed"
    elif any(
        record.conditions.get(key) != value for key, value in constraint.required_conditions.items()
    ):
        status, reason = "unknown", "condition_mismatch"
    else:
        interval = record.normalized_interval
        lower = interval.lower if interval is not None else record.normalized_value
        upper = interval.upper if interval is not None else record.normalized_value
        minimum, maximum = constraint.normalized_minimum, constraint.normalized_maximum
        if (minimum is None or lower >= minimum) and (maximum is None or upper <= maximum):
            status, reason = "pass", "within_bounds"
        elif (minimum is not None and upper < minimum) or (maximum is not None and lower > maximum):
            status, reason = "fail", "outside_bounds"
        else:
            status, reason = "unknown", "interval_overlaps_bound"
    return ScreeningCheck(
        constraint_id=constraint.constraint_id,
        property_id=constraint.property_id,
        status=status,
        reason=reason,
    )


def evaluate_screening(inputs: ScreeningInput) -> CalculationResult:
    """Normalize supplied evidence and retain every tri-state constraint result."""
    constraints = [_normalize_constraint(constraint) for constraint in inputs.constraints]
    candidates = []
    for candidate in inputs.candidates:
        properties = {
            property_id: _normalize_property(record)
            for property_id, record in candidate.properties.items()
        }
        checks = [_check_constraint(properties, constraint) for constraint in constraints]
        statuses = {check.status for check in checks}
        status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
        candidates.append(
            EvaluatedCandidate(
                candidate_id=candidate.candidate_id,
                status=status,
                properties=properties,
                checks=checks,
            )
        )
    return CalculationResult(
        ScreeningOutput(
            normalized_constraints=constraints,
            candidates=candidates,
            summary=ScreeningSummary(
                total=len(candidates),
                passed=sum(candidate.status == "pass" for candidate in candidates),
                failed=sum(candidate.status == "fail" for candidate in candidates),
                unknown=sum(candidate.status == "unknown" for candidate in candidates),
            ),
        ),
        warnings=[
            "Context is checked only for explicit required condition tags; extra supplied tags "
            "are not validated for applicability. A pass only matches the declared supplied "
            "evidence and criteria; it does not verify sources, predict properties, or qualify a material.",
            "Comparisons use normalized binary64 values with inclusive bounds and no tolerance; "
            "rounding near a boundary can affect a check. Supplied intervals are possibility "
            "ranges, not confidence intervals or probabilities.",
        ],
    )


TOOLS = (
    ToolSpec(
        name="screening.evaluate",
        description=(
            "Evaluate traceable supplied material-property records against explicit inclusive "
            "constraints, normalizing compatible units and returning pass, fail, or unknown."
        ),
        input_model=ScreeningInput,
        output_model=ScreeningOutput,
        execute=evaluate_screening,
        assumptions=(
            "Property IDs identify exact semantic properties; dimensional equivalence does not equate different IDs.",
            "Supplied sources and evidence types are retained but their authenticity is not verified.",
            "Context eligibility checks only exact required condition tags; additional tags are not validated for applicability.",
            "A supplied interval is a possibility range containing the point value, without assigned confidence or probability.",
            "Bounds are inclusive; the full interval must be inside to pass or fully outside a bound to fail, otherwise the check is unknown.",
            "Missing, disallowed, or context-mismatched evidence is unknown; any failed check takes candidate-level precedence.",
            "Conversions and comparisons use finite binary64 arithmetic with no tolerance; nonzero conversion underflow to zero and overflow are rejected.",
            "A pass only matches supplied evidence to declared criteria; it is not material qualification, a prediction, a ranking, or a discovery claim.",
        ),
        references=(
            "BIPM SI Brochure, 9th edition: https://www.bipm.org/en/publications/si-brochure",
            "Possibility-range screening semantics are defined by the screening.evaluate version 1 contract.",
        ),
    ),
)
