"""Offline composition/electron-inventory screen for manganese oxyfluoride cathodes.

This experiment uses actual toolkit composition calls. Its formal Mn-only
capacity is a charge-bookkeeping inventory, not a prediction of reversible
capacity, voltage, phase stability, synthesis, safety, or literature novelty.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from materials_agent_toolkit import __version__
from materials_agent_toolkit.registry import (
    Provenance,
    ToolResponse,
    run_batch,
    validate_input,
)

HERE = Path(__file__).resolve().parent
MAX_GRID_DENOMINATOR = 120
FAMILY = "Li2Mn_(1-t-n)Ti_tNb_nO2F"
ELEMENT_ORDER = ("Li", "Mn", "Ti", "Nb", "O", "F")
ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO_CONSTANT_PER_MOL = 6.02214076e23
FARADAY_CONSTANT_C_MOL = ELEMENTARY_CHARGE_C * AVOGADRO_CONSTANT_PER_MOL
MODEL = {
    "lithium_atoms_per_formula": 2,
    "oxygen_atoms_per_formula": 2,
    "fluorine_atoms_per_formula": 1,
    "metal_atoms_per_formula": 1,
    "spectator_oxidation_states": {"Li": 1, "Ti": 4, "Nb": 5, "O": -2, "F": -1},
    "manganese_initial_mean_valence_min": 2,
    "manganese_initial_mean_valence_max": 3,
    "manganese_final_assumed_valence": 4,
    "redox_scope": (
        "Mn-only formal electron inventory; no oxygen redox, Ti/Nb redox, "
        "kinetics or phase inference"
    ),
}
LIMITATIONS = (
    "Computational composition hypothesis in an established cathode family. "
    "Formal charge neutrality and Mn-only electron inventory assume Li+, O2-, F-, "
    "Ti4+, Nb5+, initial mean Mn between 2+ and 3+, and final Mn4+. They do not "
    "establish a single phase, site occupancy, reversible capacity, voltage, energy "
    "density, kinetics, cycle life, synthesis feasibility, safety, or novelty. "
    "Utilization scenarios are hypothetical electron-budget scalings, not "
    "probabilities, confidence intervals, or predicted experimental performance."
)


@dataclass(frozen=True)
class Study:
    """A complete bounded run, with separate scientific data and raw snapshots."""

    rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    records: dict[str, Any]


def _canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must contain exactly these fields: {', '.join(sorted(keys))}")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{label} must be {'positive and ' if positive else ''}finite")
    return number


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()) or len(value) > 4000:
        raise ValueError(
            f"{label} must be a {'possibly empty ' if allow_empty else 'nonempty '}string"
        )
    return value


def validate_inputs(inputs: dict[str, Any]) -> None:
    """Reject unknown fields, coercions and unbounded or inconsistent study inputs."""
    _object(
        inputs,
        {
            "experiment_version",
            "family",
            "grid_denominator",
            "model",
            "screen",
            "scenarios",
            "sources",
        },
        "inputs",
    )
    if inputs["experiment_version"] != "1" or inputs["family"] != FAMILY:
        raise ValueError(
            "The experiment version and fixed oxyfluoride family must match this model"
        )
    _integer(inputs["grid_denominator"], "grid_denominator", 1, MAX_GRID_DENOMINATOR)
    model = _object(inputs["model"], set(MODEL), "model")
    oxidation = _object(
        model["spectator_oxidation_states"], {"Li", "Ti", "Nb", "O", "F"}, "oxidation states"
    )
    for key, expected in MODEL.items():
        if key == "spectator_oxidation_states":
            for symbol, state in expected.items():
                if type(oxidation[symbol]) is not int or oxidation[symbol] != state:
                    raise ValueError(f"The fixed oxidation state of {symbol} must be {state}")
        elif isinstance(expected, int):
            if type(model[key]) is not int or model[key] != expected:
                raise ValueError(f"The fixed model parameter {key} must be {expected}")
        elif model[key] != expected:
            raise ValueError(f"The fixed model parameter {key} must match the stated redox scope")
    screen = _object(
        inputs["screen"], {"ideal_capacity_min_mAh_g", "nb_mass_fraction_max"}, "screen"
    )
    _finite(screen["ideal_capacity_min_mAh_g"], "ideal_capacity_min_mAh_g", positive=True)
    if not 0 <= _finite(screen["nb_mass_fraction_max"], "nb_mass_fraction_max") <= 1:
        raise ValueError("nb_mass_fraction_max must be between zero and one")
    scenarios = inputs["scenarios"]
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 20:
        raise ValueError("One to twenty hypothetical utilization scenarios are required")
    scenario_ids = []
    for scenario in scenarios:
        _object(
            scenario,
            {"id", "label", "utilization_numerator", "utilization_denominator"},
            "scenario",
        )
        scenario_id = _string(scenario["id"], "scenario.id")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", scenario_id, flags=re.ASCII) is None:
            raise ValueError("Scenario IDs must be ASCII identifiers of at most 64 characters")
        scenario_ids.append(scenario_id)
        _string(scenario["label"], "scenario.label")
        numerator = _integer(scenario["utilization_numerator"], "utilization_numerator", 1, 1000)
        denominator = _integer(
            scenario["utilization_denominator"], "utilization_denominator", 1, 1000
        )
        if numerator > denominator or math.gcd(numerator, denominator) != 1:
            raise ValueError("Utilization must be a reduced rational fraction between zero and one")
        if scenario_id == "nominal" and (numerator, denominator) != (1, 1):
            raise ValueError("The nominal scenario must use the full formal electron inventory")
    if len(set(scenario_ids)) != len(scenario_ids) or "nominal" not in scenario_ids:
        raise ValueError("Unique scenario IDs must include nominal")
    sources = inputs["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise ValueError("One to twenty scoped sources are required")
    source_ids = []
    for source in sources:
        _object(source, {"id", "url", "doi", "scope"}, "source")
        source_ids.append(_string(source["id"], "source.id"))
        if not _string(source["url"], "source.url").startswith("https://"):
            raise ValueError("Sources must supply HTTPS URLs")
        _string(source["doi"], "source.doi", allow_empty=True)
        _string(source["scope"], "source.scope")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Source IDs must be unique")
    _canonical(inputs)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_inputs(path: str | Path) -> dict[str, Any]:
    """Read finite, unambiguous JSON and validate its strict experiment schema."""

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON constant: {value}")

    inputs = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicates,
        parse_constant=invalid_constant,
    )
    validate_inputs(inputs)
    return inputs


def enumerate_grid(denominator: int) -> tuple[tuple[int, int], ...]:
    """Enumerate exact Ti/Nb coefficients with 2*i_Ti + 3*j_Nb <= d."""
    d = _integer(denominator, "denominator", 1, MAX_GRID_DENOMINATOR)
    return tuple((i, j) for i in range(d // 2 + 1) for j in range((d - 2 * i) // 3 + 1))


def _validate_candidate(d: int, i: int, j: int) -> None:
    _integer(d, "denominator", 1, MAX_GRID_DENOMINATOR)
    _integer(i, "Ti count", 0, d)
    _integer(j, "Nb count", 0, d)
    if 2 * i + 3 * j > d:
        raise ValueError("Candidate must satisfy 2*i_Ti + 3*j_Nb <= denominator")


def candidate_counts(d: int, i: int, j: int) -> dict[str, int]:
    """Return unreduced positive integer atom counts for d normalized formulas."""
    _validate_candidate(d, i, j)
    counts = {"Li": 2 * d, "Mn": d - i - j, "Ti": i, "Nb": j, "O": 2 * d, "F": d}
    return {symbol: count for symbol, count in counts.items() if count > 0}


def oxidation_budget(d: int, i: int, j: int) -> dict[str, Any]:
    """Derive charge neutrality and the exact rational Mn-to-Mn4+ electron budget."""
    _validate_candidate(d, i, j)
    manganese = d - i - j
    initial = Fraction(3 * d - 4 * i - 5 * j, manganese)
    electrons = Fraction(d + j, d)
    if not 2 <= initial <= 3 or not 0 < electrons <= 2:
        raise ValueError("Candidate violates the stated initial Mn valence or lithium inventory")
    return {
        "initial_mean_valence": float(initial),
        "final_assumed_valence": 4,
        "electron_numerator": electrons.numerator,
        "electron_denominator": electrons.denominator,
        "electrons_per_formula": float(electrons),
        "residual_lithium_per_formula": float(2 - electrons),
    }


def evaluate_gates(capacity: float, nb_mass: float, gates: dict[str, Any]) -> dict[str, Any]:
    """Apply inclusive formal-capacity and Nb mass-fraction gates without tolerance."""
    capacity = _finite(capacity, "capacity", positive=True)
    nb_mass = _finite(nb_mass, "Nb mass fraction")
    if not 0 <= nb_mass <= 1:
        raise ValueError("Nb mass fraction must be between zero and one")
    _object(gates, {"ideal_capacity_min_mAh_g", "nb_mass_fraction_max"}, "gates")
    minimum = _finite(gates["ideal_capacity_min_mAh_g"], "capacity gate", positive=True)
    maximum = _finite(gates["nb_mass_fraction_max"], "Nb gate")
    if not 0 <= maximum <= 1:
        raise ValueError("Nb gate must be between zero and one")
    passes_capacity = capacity >= minimum
    passes_nb = nb_mass <= maximum
    # A zero-Nb gate is supported, with its absolute fraction margin used because
    # division by its zero threshold has no normalized interpretation.
    nb_margin = (maximum - nb_mass) / maximum if maximum > 0 else -nb_mass
    return {
        "passes_capacity": passes_capacity,
        "passes_nb_mass_fraction": passes_nb,
        "feasible": passes_capacity and passes_nb,
        "minimum_normalized_gate_margin": min((capacity - minimum) / minimum, nb_margin),
    }


def ranking(row: dict[str, Any]) -> tuple[float, float, int, int]:
    """Rank nominally gated candidates by least Nb mass, then greatest formal capacity."""
    return (
        row["mass_fraction_Nb"],
        -row["ideal_capacity_mAh_g"],
        row["ti_grid_count"],
        row["nb_grid_count"],
    )


def _request(tool: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "tool_version": "1", "input": inputs}


def _execute(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses = []
    for start in range(0, len(requests), 100):
        batch = run_batch({"batch_version": "1", "requests": requests[start : start + 100]})
        if batch.status != "ok":
            raise ValueError(
                "The toolkit rejected a composition calculation: "
                + _canonical(
                    [
                        response.model_dump(mode="json")
                        for response in batch.responses
                        if response.status != "ok"
                    ]
                )
            )
        responses.extend(response.model_dump(mode="json") for response in batch.responses)
    return responses


def _formula(counts: dict[str, int]) -> str:
    return "".join(
        symbol + (str(counts[symbol]) if counts[symbol] != 1 else "")
        for symbol in ELEMENT_ORDER
        if symbol in counts
    )


def _normalized_formula(d: int, i: int, j: int) -> str:
    counts = candidate_counts(d, i, j)
    return " ".join(
        symbol + (str(Fraction(counts[symbol], d)) if counts[symbol] != d else "")
        for symbol in ELEMENT_ORDER
        if symbol in counts
    )


def _scenario_evaluations(row: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": scenario["id"],
            "label": scenario["label"],
            "utilization_numerator": scenario["utilization_numerator"],
            "utilization_denominator": scenario["utilization_denominator"],
            "formal_scaled_capacity_mAh_g": row[f"{scenario['id']}_capacity_mAh_g"],
            "feasible": row[f"{scenario['id']}_feasible"],
        }
        for scenario in inputs["scenarios"]
    ]


def build_study(inputs: dict[str, Any], input_sha256: str | None = None) -> Study:
    """Run two actual composition tools per grid point and retain every response."""
    validate_inputs(inputs)
    if input_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", input_sha256) is None:
        raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
    d = inputs["grid_denominator"]
    grid = enumerate_grid(d)
    requests = []
    specifications = []
    for i, j in grid:
        counts = candidate_counts(d, i, j)
        divisor = math.gcd(*counts.values())
        reduced = {symbol: count // divisor for symbol, count in counts.items()}
        formula = _formula(reduced)
        requests.extend(
            [
                _request("composition.analyze", {"formula": formula}),
                _request(
                    "composition.from_fractions",
                    {"fractions": counts, "basis": "atomic", "normalization": "normalize"},
                ),
            ]
        )
        specifications.append((i, j, formula, d // divisor))
    responses = _execute(requests)
    rows = []
    entries = []
    for index, (i, j, formula, scale) in enumerate(specifications):
        analysis = responses[2 * index]["result"]
        fractions = responses[2 * index + 1]["result"]
        normalized_mass = analysis["molar_mass_g_mol"] / scale
        independent_mass = fractions["mean_atomic_mass_g_mol"] * 6
        relative_error = abs(normalized_mass - independent_mass) / normalized_mass
        if relative_error > 2e-14:
            raise ValueError("Formula and atomic-fraction molar masses disagree")
        for symbol in candidate_counts(d, i, j):
            if not math.isclose(
                analysis["mass_fractions"][symbol],
                fractions["mass_fractions"][symbol],
                rel_tol=2e-14,
                abs_tol=0,
            ):
                raise ValueError(
                    "Independent composition tools disagree on elemental mass fraction"
                )
        budget = oxidation_budget(d, i, j)
        capacity = (
            FARADAY_CONSTANT_C_MOL * budget["electrons_per_formula"] / (3.6 * normalized_mass)
        )
        row = {
            "candidate_id": f"d{d:03d}_Ti{i:03d}_Nb{j:03d}",
            "grid_denominator": d,
            "ti_grid_count": i,
            "nb_grid_count": j,
            "mn_grid_count": d - i - j,
            "ti_fraction": i / d,
            "nb_fraction": j / d,
            "mn_fraction": (d - i - j) / d,
            "normalized_formula": _normalized_formula(d, i, j),
            "toolkit_integer_formula": formula,
            "formula_units_per_integer_formula": scale,
            "normalized_molar_mass_g_mol": normalized_mass,
            "mean_atomic_mass_g_mol": fractions["mean_atomic_mass_g_mol"],
            "molar_mass_crosscheck_relative_error": relative_error,
            "manganese_initial_mean_valence": budget["initial_mean_valence"],
            "manganese_final_assumed_valence": budget["final_assumed_valence"],
            "electrons_per_formula": budget["electrons_per_formula"],
            "residual_lithium_per_formula": budget["residual_lithium_per_formula"],
            **{
                f"mass_fraction_{symbol}": fractions["mass_fractions"].get(symbol, 0.0)
                for symbol in ELEMENT_ORDER
            },
            "ideal_capacity_mAh_g": capacity,
        }
        row.update(evaluate_gates(capacity, row["mass_fraction_Nb"], inputs["screen"]))
        for scenario in inputs["scenarios"]:
            scaled = capacity * float(
                Fraction(scenario["utilization_numerator"], scenario["utilization_denominator"])
            )
            row[f"{scenario['id']}_capacity_mAh_g"] = scaled
            row[f"{scenario['id']}_feasible"] = evaluate_gates(
                scaled, row["mass_fraction_Nb"], inputs["screen"]
            )["feasible"]
        if any(not math.isfinite(value) for value in row.values() if isinstance(value, float)):
            raise ValueError("A derived scientific value is nonfinite")
        rows.append(row)
        entries.append(
            {
                "candidate_id": row["candidate_id"],
                "requests": requests[2 * index : 2 * index + 2],
                "responses": responses[2 * index : 2 * index + 2],
            }
        )
    feasible = [row for row in rows if row["feasible"]]
    selected = min(feasible, key=ranking) if feasible else None
    strongest = (
        min(feasible, key=lambda row: (-row["minimum_normalized_gate_margin"], *ranking(row)))
        if feasible
        else None
    )
    nomination = None
    if selected is not None:
        nomination = {
            "candidate_id": selected["candidate_id"],
            "nominal": selected,
            "scenarios": _scenario_evaluations(selected, inputs),
            "all_scenarios_feasible": all(
                selected[f"{scenario['id']}_feasible"] for scenario in inputs["scenarios"]
            ),
            "required_electron_utilization_for_capacity_gate": inputs["screen"][
                "ideal_capacity_min_mAh_g"
            ]
            / selected["ideal_capacity_mAh_g"],
        }
    digest = input_sha256 or hashlib.sha256(_canonical(inputs).encode("utf-8")).hexdigest()
    # Published controls coincide with this rational grid only when d divides
    # their half/third coefficients exactly; missing controls are not rounded.
    control_indices = {(0, 0)}
    if d % 2 == 0:
        control_indices.add((d // 2, 0))
    if d % 3 == 0:
        control_indices.add((0, d // 3))
    summary = {
        "status": "screening_hypothesis",
        "experiment_version": "1",
        "toolkit_version": __version__,
        "inputs_sha256": digest,
        "input_hash_basis": "exact input file bytes"
        if input_sha256 is not None
        else "canonical JSON bytes",
        "limitations": LIMITATIONS,
        "curated_inputs": inputs,
        "screen": inputs["screen"],
        "scenarios": inputs["scenarios"],
        "candidate_count": len(rows),
        "evaluation_count": len(rows) * len(inputs["scenarios"]),
        "nominal_feasible_count": len(feasible),
        "feasible_counts_by_scenario": {
            scenario["id"]: sum(row[f"{scenario['id']}_feasible"] for row in rows)
            for scenario in inputs["scenarios"]
        },
        "all_scenarios_feasible_count": sum(
            all(row[f"{scenario['id']}_feasible"] for scenario in inputs["scenarios"])
            for row in rows
        ),
        "nomination_rule": "Nominal feasible candidates ranked by least Nb mass fraction, then greatest ideal Mn-only capacity, then Ti count and Nb count.",
        "nominated_candidate": nomination,
        "highest_nominal_margin_candidate": strongest,
        "controls": [
            row for row in rows if (row["ti_grid_count"], row["nb_grid_count"]) in control_indices
        ],
        "maximum_formal_capacity_candidate": max(rows, key=lambda row: row["ideal_capacity_mAh_g"]),
        "maximum_formal_capacity_within_nb_gate_candidate": max(
            (row for row in rows if row["passes_nb_mass_fraction"]),
            key=lambda row: row["ideal_capacity_mAh_g"],
        ),
        "constants": {
            "elementary_charge_C": ELEMENTARY_CHARGE_C,
            "avogadro_constant_per_mol": AVOGADRO_CONSTANT_PER_MOL,
            "faraday_constant_C_mol": FARADAY_CONSTANT_C_MOL,
            "charge_C_per_mAh": 3.6,
            "atoms_per_normalized_formula": 6,
        },
        "computation": {
            "actual_tool_calls": len(responses),
            "tool_calls_per_candidate": 2,
            "stored_tool_response_count": len(responses),
            "mass_crosscheck": "Integer-formula molar mass divided by normalized-formula scale independently compared with six times the atomic-fraction tool mean atomic mass.",
            "max_molar_mass_crosscheck_relative_error": max(
                row["molar_mass_crosscheck_relative_error"] for row in rows
            ),
        },
    }
    records = {
        "status": "screening_hypothesis",
        "experiment_version": "1",
        "inputs_sha256": digest,
        "snapshot_policy": "Complete actual execution snapshots for both tools at every grid point. --check validates required snapshot fields, response schema, timezone-aware timestamps and validated input hashes before comparing scientific records without execution timestamps or host runtime versions.",
        "entries": entries,
    }
    return Study(tuple(rows), summary, records)


def _csv(rows: tuple[dict[str, Any], ...]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _scientific_projection(value: Any, *, provenance: bool = False) -> Any:
    if isinstance(value, list):
        return [_scientific_projection(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _scientific_projection(item, provenance=key == "provenance")
            for key, item in value.items()
            if key not in {"created_at", "python_version", "software_versions"}
            and not (provenance and key == "toolkit_version")
        }
    return value


def _summary_matches(actual: bytes, current: dict[str, Any]) -> bool:
    """Allow a recorded package release while preserving all other summary bytes."""
    recorded = json.loads(actual, object_pairs_hook=_reject_duplicates)
    if not isinstance(recorded, dict):
        raise ValueError("Recorded summary must be an object")
    _string(recorded["toolkit_version"], "recorded toolkit_version")
    if actual != _canonical(recorded).encode("utf-8"):
        return False
    recorded["toolkit_version"] = current["toolkit_version"]
    return _canonical(recorded) == _canonical(current)


def _validate_record_responses(records: Any) -> None:
    """Validate complete snapshot envelopes and request-to-response input hashes."""
    if not isinstance(records, dict) or not isinstance(records.get("entries"), list):
        raise ValueError("Recorded entries must be a list")
    for entry in records["entries"]:
        _object(entry, {"candidate_id", "requests", "responses"}, "record entry")
        requests, responses = entry["requests"], entry["responses"]
        if (
            not isinstance(requests, list)
            or not isinstance(responses, list)
            or len(requests) != 2
            or len(responses) != 2
        ):
            raise ValueError("Each candidate must preserve two requests and responses")
        for request, response in zip(requests, responses):
            _object(response, set(ToolResponse.model_fields), "complete tool response")
            provenance = _object(
                response["provenance"], set(Provenance.model_fields), "complete provenance"
            )
            validated = ToolResponse.model_validate(response)
            if validated.status != "ok" or validated.error is not None or validated.result is None:
                raise ValueError("Scientific snapshots must preserve successful calculations")
            timestamp = datetime.fromisoformat(provenance["created_at"])
            if timestamp.utcoffset() is None:
                raise ValueError("Recorded timestamps must include a timezone")
            _string(provenance["toolkit_version"], "recorded toolkit_version")
            _string(provenance["python_version"], "recorded python_version")
            if set(provenance["software_versions"]) != {"pydantic", "periodictable"}:
                raise ValueError("Recorded composition calls must retain package versions")
            for version in provenance["software_versions"].values():
                _string(version, "recorded software version")
            _object(request, {"tool", "tool_version", "input"}, "recorded request")
            normalized = validate_input(request["tool"], request["input"])
            canonical = json.dumps(
                normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if (
                provenance["input_sha256"] != expected
                or response["tool"] != request["tool"]
                or response["tool_version"] != request["tool_version"]
            ):
                raise ValueError(
                    "Recorded response tool/version or validated input hash disagrees with its request"
                )


def emit_artifacts(
    inputs_path: str | Path, output_dir: str | Path, *, check: bool = False
) -> dict[str, Any]:
    """Generate artifacts, or verify existing artifacts without writing any files."""
    inputs_path = Path(inputs_path)
    inputs = load_inputs(inputs_path)
    study = build_study(inputs, input_sha256=hashlib.sha256(inputs_path.read_bytes()).hexdigest())
    artifacts = {
        "candidates.csv": _csv(study.rows).encode("utf-8"),
        "summary.json": _canonical(study.summary).encode("utf-8"),
        "tool-records.json": _canonical(study.records).encode("utf-8"),
    }
    output_dir = Path(output_dir)
    if check:
        stale = []
        for name, expected in artifacts.items():
            path = output_dir / name
            if not path.is_file():
                stale.append(name)
                continue
            actual = path.read_bytes()
            if name == "summary.json":
                try:
                    matches = _summary_matches(actual, study.summary)
                except (ValueError, KeyError, TypeError):
                    matches = False
            elif name == "tool-records.json":
                try:
                    recorded = json.loads(actual, object_pairs_hook=_reject_duplicates)
                    _validate_record_responses(recorded)
                    # Canonical JSON comparison preserves type distinctions:
                    # Python mapping equality otherwise considers True == 1.
                    matches = _canonical(_scientific_projection(recorded)) == _canonical(
                        _scientific_projection(study.records)
                    )
                except (ValueError, KeyError, TypeError):
                    matches = False
            else:
                matches = actual == expected
            if not matches:
                stale.append(name)
        if stale:
            raise ValueError(f"Missing or stale experiment artifacts: {', '.join(stale)}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, value in artifacts.items():
            (output_dir / name).write_bytes(value)
    return study.summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=HERE / "inputs.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "results")
    parser.add_argument(
        "--check", action="store_true", help="Verify recorded scientific artifacts without writing"
    )
    arguments = parser.parse_args(argv)
    try:
        summary = emit_artifacts(arguments.inputs, arguments.output_dir, check=arguments.check)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 1
    print(
        _canonical(
            {
                "status": summary["status"],
                "candidate_count": summary["candidate_count"],
                "evaluation_count": summary["evaluation_count"],
                "nominal_feasible_count": summary["nominal_feasible_count"],
                "feasible_counts_by_scenario": summary["feasible_counts_by_scenario"],
                "nominated_candidate": summary["nominated_candidate"]["candidate_id"]
                if summary["nominated_candidate"]
                else None,
                "checked": arguments.check,
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
