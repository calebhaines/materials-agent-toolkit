"""Reproducible, explicitly unvalidated aluminium composite screening study.

The curated input file is an experimental dataset, not a public tool contract.
Its phase properties are passed through the toolkit's validated scientific tools.
Derived composite estimates are ideal-mixture screening proxies; they neither
establish a new material nor predict a manufactured specimen's performance.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

from materials_agent_toolkit import __version__
from materials_agent_toolkit.registry import ToolResponse, run_batch, run_tool

HERE = Path(__file__).resolve().parent
PROPERTY_FIELDS = (
    "density_kg_m3",
    "young_modulus_GPa",
    "poisson_ratio",
    "cte_per_K",
    "conductivity_W_m_K",
)
MAX_GRID_CANDIDATES = 20_000
MAX_EVALUATIONS = 100_000
LIMITATION = (
    "Screening hypothesis only: ideal dense, isotropic, perfectly bonded mixtures. "
    "No phase stability, interfacial chemistry, porosity, microstructure, manufacturing, "
    "temperature dependence, experimental performance, or literature novelty is established. "
    "The two CTE estimates are model proxies, not rigorous bounds."
)


def _canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{label} must be {'positive and ' if positive else ''}finite")
    return number


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def validate_inputs(inputs: dict[str, Any]) -> None:
    """Validate the bounded study configuration, leaving source metadata intact."""
    if not isinstance(inputs, dict) or inputs.get("experiment_version") != "1":
        raise ValueError("experiment_version must be '1'")
    screen = inputs.get("screen")
    if not isinstance(screen, dict):
        raise ValueError("screen must be an object")
    step = _integer(screen.get("grid_step_vol_percent"), "grid_step_vol_percent", 1, 100)
    if 100 % step:
        raise ValueError("grid_step_vol_percent must divide 100")
    low = _integer(screen.get("min_ceramic_vol_percent"), "min_ceramic_vol_percent", 0, 100)
    high = _integer(screen.get("max_ceramic_vol_percent"), "max_ceramic_vol_percent", low, 100)
    if low % step or high % step:
        raise ValueError("Ceramic loading limits must be multiples of grid_step_vol_percent")
    for field in (
        "density_max_kg_m3",
        "specific_modulus_min_GPa_per_g_cm3",
        "conductivity_min_W_m_K",
        "cte_proxy_max_per_K",
    ):
        _finite(screen.get(field), field, positive=True)
    phases = inputs.get("constituents")
    if not isinstance(phases, list) or len(phases) != 4:
        raise ValueError("Exactly four constituents are required: one matrix and three ceramics")
    ids = []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError("Each constituent must be an object")
        phase_id = phase.get("id")
        if (
            not isinstance(phase_id, str)
            or not phase_id
            or not phase_id.isascii()
            or not all(character.isalnum() or character == "_" for character in phase_id)
        ):
            raise ValueError(
                "Constituent IDs must be nonempty ASCII letters, digits or underscores"
            )
        ids.append(phase_id)
        if phase.get("role") != ("matrix" if index == 0 else "reinforcement"):
            raise ValueError(
                "The first constituent must be the matrix; the other three reinforcements"
            )
        if not isinstance(phase.get("formula"), str) or not phase["formula"].strip():
            raise ValueError(f"{phase_id}.formula must be a nonempty chemical formula")
        _validate_phase_properties(phase, phase_id)
    if len(set(ids)) != len(ids):
        raise ValueError("Constituent IDs must be unique")
    scenarios = inputs.get("scenarios")
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 20:
        raise ValueError("One to twenty scenarios are required")
    scenario_ids = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("Each scenario must be an object")
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("Each scenario needs a nonempty string ID")
        scenario_ids.append(scenario_id)
        scales = scenario.get("property_scales", {})
        overrides = scenario.get("property_overrides", {})
        if not isinstance(scales, dict) or not isinstance(overrides, dict):
            raise ValueError("Scenario scales and overrides must be objects")
        for field, scale in scales.items():
            if field not in PROPERTY_FIELDS:
                raise ValueError(f"Unknown scaled property: {field}")
            _finite(scale, f"{scenario_id}.{field} scale", positive=True)
        for phase_id, properties in overrides.items():
            if phase_id not in ids or not isinstance(properties, dict):
                raise ValueError("Scenario overrides must map known phase IDs to property objects")
            for field, value in properties.items():
                if field not in PROPERTY_FIELDS:
                    raise ValueError(f"Unknown overridden property: {field}")
                _finite(value, f"{scenario_id}.{phase_id}.{field}")
        for phase in phases:
            _validate_phase_properties(
                _scenario_phase(phase, scenario), f"{scenario_id}.{phase['id']}"
            )
        if scenario_id == "nominal" and (
            overrides or any(float(value) != 1.0 for value in scales.values())
        ):
            raise ValueError("The nominal scenario must preserve the curated input properties")
    if len(set(scenario_ids)) != len(scenario_ids) or "nominal" not in scenario_ids:
        raise ValueError("Scenario IDs must be unique and include 'nominal'")
    count = sum(math.comb(loading // step + 2, 2) for loading in range(low, high + 1, step))
    if count > MAX_GRID_CANDIDATES or count * len(scenarios) > MAX_EVALUATIONS:
        raise ValueError("Study exceeds the bounded grid/evaluation limit; increase the grid step")
    # Catch nonfinite numbers in optional metadata as well as scientific fields.
    _canonical(inputs)


def _validate_phase_properties(phase: dict[str, Any], label: str) -> None:
    for field in ("density_kg_m3", "young_modulus_GPa", "conductivity_W_m_K"):
        _finite(phase.get(field), f"{label}.{field}", positive=True)
    poisson = _finite(phase.get("poisson_ratio"), f"{label}.poisson_ratio")
    if not -1.0 < poisson < 0.5:
        raise ValueError(f"{label}.poisson_ratio must lie strictly between -1 and 0.5")
    _finite(phase.get("cte_per_K"), f"{label}.cte_per_K")


def _scenario_phase(phase: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    adjusted = dict(phase)
    for field, factor in scenario.get("property_scales", {}).items():
        adjusted[field] = float(adjusted[field]) * float(factor)
    adjusted.update(scenario.get("property_overrides", {}).get(phase["id"], {}))
    return adjusted


def load_inputs(path: str | Path) -> dict[str, Any]:
    """Read finite JSON, rejecting ambiguous duplicate keys before screening."""

    def invalid_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON constant: {value}")

    inputs = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicates,
        parse_constant=invalid_constant,
    )
    validate_inputs(inputs)
    return inputs


def _request(tool: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "tool_version": "1", "input": inputs}


def _execute(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses = []
    for start in range(0, len(requests), 100):
        batch = run_batch({"batch_version": "1", "requests": requests[start : start + 100]})
        if batch.status != "ok":
            failures = [
                response.model_dump(mode="json")
                for response in batch.responses
                if response.status != "ok"
            ]
            raise ValueError(
                f"Scientific toolkit rejected a study calculation: {_canonical(failures)}"
            )
        responses.extend(response.model_dump(mode="json") for response in batch.responses)
    return responses


def _record_responses(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Preserve complete, schema-valid execution snapshots. Reproducibility checks
    # separately project away timestamps and host versions without altering them.
    return responses


def _bounds_request(values: tuple[float, ...], fractions: list[float], unit: str) -> dict[str, Any]:
    return _request(
        "mixtures.scalar_bounds",
        {"values": list(values), "fractions": fractions, "property_unit": unit},
    )


class _BoundsCache:
    """Store small result pairs rather than thousands of response envelopes."""

    def __init__(self) -> None:
        self.results: dict[tuple[Any, ...], tuple[float, float]] = {}
        self.calls = 0
        self.hits = 0
        self.homogeneous_reuses = 0

    def get(
        self, values: tuple[float, ...], fractions: list[float], unit: str
    ) -> tuple[float, float]:
        key = (values, tuple(fractions), unit)
        if key in self.results:
            self.hits += 1
            return self.results[key]
        response = run_tool(
            "mixtures.scalar_bounds", _bounds_request(values, fractions, unit)["input"]
        )
        if response.status != "ok" or response.result is None:
            raise ValueError(f"Scalar mixture calculation failed: {response.error}")
        result = (response.result["reuss_bound"], response.result["voigt_bound"])
        self.results[key] = result
        self.calls += 1
        return result


def _uniform_scale(values: tuple[float, ...], nominal: tuple[float, ...]) -> float | None:
    factor = values[0] / nominal[0]
    # Homogeneity is exact for a common multiplicative scenario perturbation;
    # allow only binary64 arithmetic roundoff when recognising that relation.
    for value, original in zip(values, nominal):
        expected = original * factor
        if abs(value - expected) > 8.0 * max(math.ulp(value), math.ulp(expected)):
            return None
    return factor


def _candidate_id(ids: list[str], percentages: tuple[int, ...]) -> str:
    return "_".join(f"{phase_id}{percentage:03d}" for phase_id, percentage in zip(ids, percentages))


def _evaluate_row(
    ids: list[str],
    percentages: tuple[int, ...],
    scenario_id: str,
    phases: list[dict[str, Any]],
    bounds: dict[str, tuple[float, float]],
    gates: dict[str, Any],
) -> dict[str, Any]:
    fractions = [percentage / 100.0 for percentage in percentages]
    density = math.fsum(
        fraction * phase["density_kg_m3"] for fraction, phase in zip(fractions, phases)
    )
    bulk_r, bulk_v = bounds["bulk"]
    shear_r, shear_v = bounds["shear"]
    young_r = 9.0 * bulk_r * shear_r / (3.0 * bulk_r + shear_r)
    young_v = 9.0 * bulk_v * shear_v / (3.0 * bulk_v + shear_v)
    conductivity_r, conductivity_v = bounds["conductivity"]
    cte_volume = math.fsum(
        fraction * phase["cte_per_K"] for fraction, phase in zip(fractions, phases)
    )
    cte_turner = math.fsum(
        fraction * phase["bulk_modulus_GPa"] * phase["cte_per_K"]
        for fraction, phase in zip(fractions, phases)
    ) / math.fsum(
        fraction * phase["bulk_modulus_GPa"] for fraction, phase in zip(fractions, phases)
    )
    cte_proxy = max(cte_volume, cte_turner)
    specific = young_r / (density / 1000.0)
    margins = (
        (gates["density_max_kg_m3"] - density) / gates["density_max_kg_m3"],
        (specific - gates["specific_modulus_min_GPa_per_g_cm3"])
        / gates["specific_modulus_min_GPa_per_g_cm3"],
        (conductivity_r - gates["conductivity_min_W_m_K"]) / gates["conductivity_min_W_m_K"],
        (gates["cte_proxy_max_per_K"] - cte_proxy) / gates["cte_proxy_max_per_K"],
    )
    row = {
        "candidate_id": _candidate_id(ids, percentages),
        "scenario_id": scenario_id,
        **{f"{phase_id}_vol_percent": percentage for phase_id, percentage in zip(ids, percentages)},
        "ceramic_vol_percent": sum(percentages[1:]),
        "density_kg_m3": density,
        "bulk_modulus_reuss_GPa": bulk_r,
        "bulk_modulus_voigt_GPa": bulk_v,
        "shear_modulus_reuss_GPa": shear_r,
        "shear_modulus_voigt_GPa": shear_v,
        "young_modulus_reuss_GPa": young_r,
        "young_modulus_voigt_GPa": young_v,
        "specific_modulus_reuss_GPa_per_g_cm3": specific,
        "conductivity_reuss_W_m_K": conductivity_r,
        "conductivity_voigt_W_m_K": conductivity_v,
        "cte_volume_average_per_K": cte_volume,
        "cte_turner_per_K": cte_turner,
        "cte_max_proxy_per_K": cte_proxy,
        "passes_density": margins[0] >= 0.0,
        "passes_specific_modulus": margins[1] >= 0.0,
        "passes_conductivity": margins[2] >= 0.0,
        "passes_cte_proxy": margins[3] >= 0.0,
        "feasible": all(margin >= 0.0 for margin in margins),
        "minimum_normalized_gate_margin": min(margins),
    }
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Derived screening property is nonfinite: {key}")
    return row


def _ranking(row: dict[str, Any], ids: list[str]) -> tuple[Any, ...]:
    return (
        row["ceramic_vol_percent"],
        -row["conductivity_reuss_W_m_K"],
        -row["specific_modulus_reuss_GPa_per_g_cm3"],
        *(row[f"{phase_id}_vol_percent"] for phase_id in ids),
    )


def screen_candidates(
    inputs: dict[str, Any], input_sha256: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Evaluate the complete bounded grid and retain reproducible selected replays.

    The optional digest is the SHA-256 of exact input file bytes. Without it the
    digest describes canonical JSON bytes, as recorded by input_hash_basis.
    """
    validate_inputs(inputs)
    phases = inputs["constituents"]
    ids = [phase["id"] for phase in phases]
    scenarios = inputs["scenarios"]
    gates = inputs["screen"]
    setup_requests = [
        _request("composition.analyze", {"formula": phase["formula"]}) for phase in phases
    ]
    composition_responses = _execute(setup_requests)
    composition_results = [response["result"] for response in composition_responses]
    scenario_phases: dict[str, list[dict[str, Any]]] = {}
    setup_records = [
        {
            "label": "constituent_compositions",
            "requests": setup_requests,
            "responses": _record_responses(composition_responses),
        }
    ]
    for scenario in scenarios:
        adjusted = [_scenario_phase(phase, scenario) for phase in phases]
        requests = [
            _request(
                "mechanics.isotropic_moduli",
                {
                    "young_modulus": float(phase["young_modulus_GPa"]),
                    "poisson_ratio": float(phase["poisson_ratio"]),
                    "stress_unit": "GPa",
                },
            )
            for phase in adjusted
        ]
        responses = _execute(requests)
        for phase, response in zip(adjusted, responses):
            phase["bulk_modulus_GPa"] = response["result"]["bulk_modulus"]
            phase["shear_modulus_GPa"] = response["result"]["shear_modulus"]
        scenario_phases[scenario["id"]] = adjusted
        setup_records.append(
            {
                "label": f"constituent_elastic_moduli:{scenario['id']}",
                "requests": requests,
                "responses": _record_responses(responses),
            }
        )
    vectors = {
        scenario_id: {
            "bulk": tuple(phase["bulk_modulus_GPa"] for phase in adjusted),
            "shear": tuple(phase["shear_modulus_GPa"] for phase in adjusted),
            "conductivity": tuple(float(phase["conductivity_W_m_K"]) for phase in adjusted),
        }
        for scenario_id, adjusted in scenario_phases.items()
    }
    scales = {
        scenario_id: {
            property_name: _uniform_scale(values, vectors["nominal"][property_name])
            for property_name, values in properties.items()
        }
        for scenario_id, properties in vectors.items()
    }
    cache = _BoundsCache()

    def evaluate(percentages: tuple[int, ...]) -> list[dict[str, Any]]:
        fractions = [percentage / 100.0 for percentage in percentages]
        nominal_bounds = {
            property_name: cache.get(
                values, fractions, "W/(m K)" if property_name == "conductivity" else "GPa"
            )
            for property_name, values in vectors["nominal"].items()
        }
        evaluated = []
        for scenario in scenarios:
            scenario_id = scenario["id"]
            bounds = {}
            for property_name, values in vectors[scenario_id].items():
                factor = scales[scenario_id][property_name]
                if factor is not None:
                    bounds[property_name] = tuple(
                        value * factor for value in nominal_bounds[property_name]
                    )
                    if scenario_id != "nominal":
                        cache.homogeneous_reuses += 1
                else:
                    bounds[property_name] = cache.get(
                        values, fractions, "W/(m K)" if property_name == "conductivity" else "GPa"
                    )
            evaluated.append(
                _evaluate_row(
                    ids, percentages, scenario_id, scenario_phases[scenario_id], bounds, gates
                )
            )
        return evaluated

    rows = []
    step = gates["grid_step_vol_percent"]
    for loading in range(
        gates["min_ceramic_vol_percent"], gates["max_ceramic_vol_percent"] + 1, step
    ):
        for first in range(0, loading + 1, step):
            for second in range(0, loading - first + 1, step):
                third = loading - first - second
                rows.extend(evaluate((100 - loading, first, second, third)))
    nominal = [row for row in rows if row["scenario_id"] == "nominal"]
    feasible = [row for row in nominal if row["feasible"]]
    selected = min(feasible, key=lambda row: _ranking(row, ids)) if feasible else None
    strongest = (
        max(
            feasible,
            key=lambda row: (
                row["minimum_normalized_gate_margin"],
                *(
                    -value if isinstance(value, (int, float)) else value
                    for value in _ranking(row, ids)
                ),
            ),
        )
        if feasible
        else None
    )
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    controls = []
    controls.extend(evaluate((100, 0, 0, 0)))
    if selected is not None:
        loading = selected["ceramic_vol_percent"]
        for ceramic_index in range(1, 4):
            percentages = [100 - loading, 0, 0, 0]
            percentages[ceramic_index] = loading
            controls.extend(evaluate(tuple(percentages)))
    replay_rows = [row for row in controls if row["scenario_id"] == "nominal"]
    if selected is not None:
        replay_rows.extend(by_candidate[selected["candidate_id"]])
    if strongest is not None and (
        selected is None or strongest["candidate_id"] != selected["candidate_id"]
    ):
        replay_rows.append(strongest)
    replay_records = []
    for row in replay_rows:
        fractions = [row[f"{phase_id}_vol_percent"] / 100.0 for phase_id in ids]
        requests = [
            _bounds_request(
                values, fractions, "W/(m K)" if property_name == "conductivity" else "GPa"
            )
            for property_name, values in vectors[row["scenario_id"]].items()
        ]
        replay_records.append(
            {
                "candidate_id": row["candidate_id"],
                "scenario_id": row["scenario_id"],
                "properties": list(vectors[row["scenario_id"]]),
                "requests": requests,
                "responses": _record_responses(_execute(requests)),
            }
        )
    nomination = None
    recipe_record = None
    thermal_record = None
    if selected is not None:
        fractions = [selected[f"{phase_id}_vol_percent"] / 100.0 for phase_id in ids]
        phase_masses = [
            fraction * phase["density_kg_m3"] for fraction, phase in zip(fractions, phases)
        ]
        total_mass = math.fsum(phase_masses)
        phase_mass_fractions = {
            phase_id: mass / total_mass for phase_id, mass in zip(ids, phase_masses) if mass > 0
        }
        elements: dict[str, float] = {}
        for phase_mass, composition in zip(phase_masses, composition_results):
            for symbol, elemental_fraction in composition["mass_fractions"].items():
                elements[symbol] = (
                    elements.get(symbol, 0.0) + phase_mass / total_mass * elemental_fraction
                )
        elements = {symbol: value for symbol, value in elements.items() if value > 0}
        request = _request(
            "composition.from_fractions",
            {"fractions": elements, "basis": "mass", "normalization": "require_unity"},
        )
        response = _execute([request])[0]
        recipe_record = {
            "label": "ideal_elemental_recipe",
            "requests": [request],
            "responses": _record_responses([response]),
        }
        thermal_requests = [
            _request(
                "thermal.linear_expansion",
                {
                    "initial_length_m": 0.1,
                    "expansion_coefficient_per_K": selected[field],
                    "delta_temperature_K": 25.0,
                },
            )
            for field in ("cte_volume_average_per_K", "cte_turner_per_K")
        ]
        thermal_record = {
            "label": "illustrative_constant_CTE_proxy_expansion",
            "proxy_fields": ["cte_volume_average_per_K", "cte_turner_per_K"],
            "assumption": "Illustration for a 0.1 m part and a 25 K temperature increase using each constant CTE proxy; not validated composite expansion.",
            "requests": thermal_requests,
            "responses": _record_responses(_execute(thermal_requests)),
        }
        nomination = {
            "candidate_id": selected["candidate_id"],
            "phase_volume_percent": {
                phase_id: selected[f"{phase_id}_vol_percent"] for phase_id in ids
            },
            "ideal_phase_mass_fractions": phase_mass_fractions,
            "ideal_elemental_composition": response["result"],
            "recipe_assumption": "Pure stoichiometric phase formulas; grade additives, binders, impurities and interfacial reactions are omitted.",
            "nominal": selected,
            "scenarios": by_candidate[selected["candidate_id"]],
            "all_scenarios_feasible": all(
                row["feasible"] for row in by_candidate[selected["candidate_id"]]
            ),
        }
    digest = input_sha256 or hashlib.sha256(_canonical(inputs).encode("utf-8")).hexdigest()
    summary = {
        "status": "screening_hypothesis",
        "experiment_version": "1",
        "toolkit_version": __version__,
        "inputs_sha256": digest,
        "input_hash_basis": "exact input file bytes"
        if input_sha256 is not None
        else "canonical JSON bytes",
        "limitations": LIMITATION,
        "screen": gates,
        "curated_inputs": inputs,
        "candidate_count": len(nominal),
        "evaluation_count": len(rows),
        "nominal_feasible_count": len(feasible),
        "feasible_counts_by_scenario": {
            scenario["id"]: sum(
                row["feasible"] for row in rows if row["scenario_id"] == scenario["id"]
            )
            for scenario in scenarios
        },
        "all_scenarios_feasible_count": sum(
            all(row["feasible"] for row in candidate_rows)
            for candidate_rows in by_candidate.values()
        ),
        "nomination_rule": "Nominal feasible candidates ranked by least ceramic volume loading, then highest harmonic conductivity, then highest Reuss specific modulus, then ordered volume percentages.",
        "nominated_candidate": nomination,
        "highest_nominal_margin_candidate": strongest,
        "controls": controls,
        "computation": {
            "scalar_tool_calls": cache.calls,
            "identical_input_cache_hits": cache.hits,
            "homogeneous_scalar_bound_reuses": cache.homogeneous_reuses,
            "homogeneity_assumption": "Arithmetic/harmonic means are homogeneous under a common positive scalar factor; recognised with at most eight binary64 ulps per constituent. Selected scenarios are replayed through actual tool calls.",
            "tool_response_scope": "All phase composition/modulus responses, selected candidate scenarios, nominal pure-matrix/single-ceramic controls and the highest nominal margin candidate; grid envelopes are not retained.",
        },
    }
    records = {
        "status": "screening_hypothesis",
        "inputs_sha256": digest,
        "provenance_policy": "Complete schema-valid toolkit execution response snapshots, including actual timestamps, input hashes, references and runtime versions. --check compares scientific records independently of execution timestamps and runtime version fields; data tables and summary are byte deterministic.",
        "setup": setup_records,
        "selected_and_control_replays": replay_records,
        "ideal_recipe": recipe_record,
        "illustrative_thermal_expansion": thermal_record,
    }
    return rows, summary, records


def _csv(rows: list[dict[str, Any]]) -> str:
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


def _recorded_toolkit_version(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Recorded toolkit_version must be a nonempty string")


def _summary_matches(actual: bytes, current: dict[str, Any]) -> bool:
    """Allow a recorded package release while preserving all other summary bytes."""
    recorded = json.loads(actual, object_pairs_hook=_reject_duplicates)
    if not isinstance(recorded, dict):
        raise ValueError("Recorded summary must be an object")
    _recorded_toolkit_version(recorded["toolkit_version"])
    if actual != _canonical(recorded).encode("utf-8"):
        return False
    recorded["toolkit_version"] = current["toolkit_version"]
    return _canonical(recorded) == _canonical(current)


def _validate_record_responses(value: Any) -> None:
    """Require complete valid snapshots before ignoring host fields for drift."""
    if isinstance(value, list):
        for item in value:
            _validate_record_responses(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "responses":
                if not isinstance(item, list):
                    raise ValueError("Recorded responses must be a list")
                for response in item:
                    _recorded_toolkit_version(response["provenance"]["toolkit_version"])
                    ToolResponse.model_validate(response)
            else:
                _validate_record_responses(item)


def _gzip(text: str) -> bytes:
    stream = io.BytesIO()
    # GzipFile keeps the header platform-independent, with no embedded filename
    # or wall-clock time. gzip.compress(mtime=0) differs across Python versions.
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
        compressed.write(text.encode("utf-8"))
    return stream.getvalue()


def write_results(
    inputs_path: str | Path, output_dir: str | Path, *, check: bool = False
) -> dict[str, Any]:
    """Generate results or verify committed outputs without changing any files."""
    inputs_path = Path(inputs_path)
    inputs = load_inputs(inputs_path)
    digest = hashlib.sha256(inputs_path.read_bytes()).hexdigest()
    rows, summary, records = screen_candidates(inputs, input_sha256=digest)
    artifacts = {
        "candidates.csv": _csv([row for row in rows if row["scenario_id"] == "nominal"]).encode(
            "utf-8"
        ),
        "candidates.csv.gz": _gzip(_csv(rows)),
        "summary.json": _canonical(summary).encode("utf-8"),
        "tool-records.json": _canonical(records).encode("utf-8"),
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
                    matches = _summary_matches(actual, summary)
                except (ValueError, KeyError, TypeError):
                    matches = False
            elif name == "tool-records.json":
                try:
                    recorded = json.loads(actual)
                    _validate_record_responses(recorded)
                    matches = _canonical(_scientific_projection(recorded)) == _canonical(
                        _scientific_projection(records)
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
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=HERE / "inputs.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "results")
    parser.add_argument(
        "--check", action="store_true", help="Verify generated scientific artifacts without writing"
    )
    arguments = parser.parse_args(argv)
    try:
        summary = write_results(arguments.inputs, arguments.output_dir, check=arguments.check)
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
