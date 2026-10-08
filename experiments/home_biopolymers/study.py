"""Offline feed budgeting and empirical trial plan for home-processable polymers.

Actual toolkit composition calls support ideal elemental feed inventories only.
No model predicts waterproofing, biodegradation, strength or manufacturing success.
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
from pathlib import Path
from typing import Any

from materials_agent_toolkit import __version__
from materials_agent_toolkit.registry import Provenance, ToolResponse, run_batch, validate_input

HERE = Path(__file__).resolve().parent
ELEMENTS = ("H", "C", "O", "Na")
FORMULAS = {
    "pcl_repeat": "C6H10O2",
    "starch_repeat": "C6H10O5",
    "sodium_alginate_repeat": "C6H7NaO6",
    "glycerol": "C3H8O3",
    "calcium_lactate_pentahydrate": "Ca(C3H5O3)2(H2O)5",
    "calcium_lactate_anhydrous_diagnostic": "Ca(C3H5O3)2",
    "water": "H2O",
}
DESIGN = {
    "pcl_nominal_dry_feed_g": 50.0,
    "starch_nominal_mass_fractions": [0.0, 0.05, 0.10],
    "sodium_alginate_feed_g": 2.0,
    "glycerol_per_alginate_mass_ratios": [0.10, 0.20, 0.30],
    "beeswax_topcoat_feed_g": [0.0, 0.2, 0.4],
    "wax_coating_area_cm2": 100.0,
    "casting_water_feed_g": 100.0,
    "fresh_bath_pentahydrate_feed_g": 2.0,
    "fresh_bath_water_feed_g": 98.0,
    "untreated_control_glycerol_per_alginate_mass_ratio": 0.20,
}
TEST_PLAN = {
    "replicates_per_formulation": 3,
    "water_head_cm": 5.0,
    "duration_h": 24.0,
    "temperature_min_C": 20.0,
    "temperature_max_C": 25.0,
    "thickness_measurement_count": 5,
}
LIMITATIONS = (
    "Unmeasured formulations in established material families. Composition tools calculate "
    "ideal pre-treatment feed inventories, not final film composition or material properties. "
    "Repeat-unit formulas omit chain ends, additives, moisture and commercial-grade variability; "
    "as-received starch is not necessarily dry. Wax is a mixture with unknown elemental "
    "composition. Bath ions, retained moisture, lost glycerol/polymer and wax transfer are "
    "unmeasured. Bath calcium availability and carboxylate site inventories do not measure "
    "uptake, crosslink density, reaction completion or film performance. No waterproof, "
    "biodegradation, food-contact, strength, novelty or home-manufacturing claim is established."
)


@dataclass(frozen=True)
class Study:
    """Finite feed budgets, actual response snapshots and blank measurement rows."""

    rows: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    records: dict[str, Any]
    template: tuple[dict[str, Any], ...]


def _canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"{label} must be a nonempty string of at most 4000 characters")
    return value


def _fixed(value: Any, expected: Any, label: str) -> None:
    """Validate a curated bounded model without numeric coercion or boolean aliases."""
    if isinstance(expected, dict):
        _object(value, set(expected), label)
        for key, target in expected.items():
            _fixed(value[key], target, f"{label}.{key}")
    elif isinstance(expected, list):
        if not isinstance(value, list) or len(value) != len(expected):
            raise ValueError(f"{label} must preserve the fixed study grid")
        for index, target in enumerate(expected):
            _fixed(value[index], target, f"{label}[{index}]")
    elif isinstance(expected, (float, int)):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"{label} must be a finite number, not a boolean")
        try:
            valid = math.isfinite(value) and value == expected
        except (OverflowError, TypeError):
            valid = False
        if isinstance(expected, int) and type(value) is not int:
            valid = False
        if not valid:
            raise ValueError(f"{label} must match the fixed study value {expected}")
    elif value != expected or type(value) is not type(expected):
        raise ValueError(f"{label} must match the fixed study value {expected}")


def validate_inputs(inputs: Any) -> None:
    """Require the finite fixed 13-formulation design and strict source bookkeeping."""
    _object(
        inputs,
        {"experiment_version", "purpose", "components", "design", "test_plan", "sources"},
        "inputs",
    )
    _fixed(inputs["experiment_version"], "1", "experiment_version")
    _string(inputs["purpose"], "purpose")
    components = _object(inputs["components"], set(FORMULAS), "components")
    for name, formula in FORMULAS.items():
        component = _object(components[name], {"formula", "scope"}, f"component {name}")
        _fixed(component["formula"], formula, f"component {name}.formula")
        _string(component["scope"], f"component {name}.scope")
    _fixed(inputs["design"], DESIGN, "design")
    _fixed(inputs["test_plan"], TEST_PLAN, "test_plan")
    sources = inputs["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise ValueError("sources must contain one to twenty evidence records")
    identifiers = []
    for source in sources:
        _object(source, {"id", "url", "scope"}, "source")
        identifiers.append(_string(source["id"], "source.id"))
        if not _string(source["url"], "source.url").startswith("https://"):
            raise ValueError("source.url must be an HTTPS URL")
        _string(source["scope"], "source.scope")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("source identifiers must be unique")
    _canonical(inputs)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON constant: {value}")


def load_inputs(path: str | Path) -> dict[str, Any]:
    inputs = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicates,
        parse_constant=_reject_constant,
    )
    validate_inputs(inputs)
    return inputs


def _request(tool: str, values: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "tool_version": "1", "input": values}


def _execute(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 1 <= len(requests) <= 100:
        raise ValueError("The study requires one to one hundred bounded toolkit requests")
    batch = run_batch({"batch_version": "1", "requests": requests})
    if batch.status != "ok":
        raise ValueError("The toolkit rejected a feed-composition calculation")
    return [response.model_dump(mode="json") for response in batch.responses]


def _formulations() -> tuple[dict[str, Any], ...]:
    rows = []
    for fraction in DESIGN["starch_nominal_mass_fractions"]:
        rows.append(
            {
                "formulation_id": f"PCL_S{round(fraction * 100):02d}",
                "family": "pcl_starch",
                "control_role": "plain_pcl_control" if fraction == 0 else "starch_blend_trial",
                "pcl_feed_g": DESIGN["pcl_nominal_dry_feed_g"] * (1 - fraction),
                "starch_feed_g": DESIGN["pcl_nominal_dry_feed_g"] * fraction,
                "sodium_alginate_feed_g": 0.0,
                "glycerol_feed_g": 0.0,
                "beeswax_topcoat_feed_g": 0.0,
                "bath_assigned": False,
            }
        )
    for ratio in DESIGN["glycerol_per_alginate_mass_ratios"]:
        for wax in DESIGN["beeswax_topcoat_feed_g"]:
            rows.append(
                {
                    "formulation_id": f"ALG_G{round(ratio * 100):02d}_W{round(wax * 10):02d}",
                    "family": "calcium_alginate_wax",
                    "control_role": "uncoated_bath_control" if wax == 0 else "wax_topcoat_trial",
                    "pcl_feed_g": 0.0,
                    "starch_feed_g": 0.0,
                    "sodium_alginate_feed_g": DESIGN["sodium_alginate_feed_g"],
                    "glycerol_feed_g": DESIGN["sodium_alginate_feed_g"] * ratio,
                    "beeswax_topcoat_feed_g": wax,
                    "bath_assigned": True,
                }
            )
    rows.append(
        {
            "formulation_id": "ALG_UNTREATED",
            "family": "sodium_alginate_control",
            "control_role": "untreated_uncoated_control",
            "pcl_feed_g": 0.0,
            "starch_feed_g": 0.0,
            "sodium_alginate_feed_g": DESIGN["sodium_alginate_feed_g"],
            "glycerol_feed_g": DESIGN["sodium_alginate_feed_g"]
            * DESIGN["untreated_control_glycerol_per_alginate_mass_ratio"],
            "beeswax_topcoat_feed_g": 0.0,
            "bath_assigned": False,
        }
    )
    if not 1 <= len(rows) <= 100:
        raise ValueError("The fixed design must remain bounded to at most 100 formulations")
    return tuple(rows)


def _measurement_template(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    observations = (
        "actual_pcl_feed_g",
        "actual_starch_feed_g",
        "actual_sodium_alginate_feed_g",
        "actual_glycerol_feed_g",
        "actual_beeswax_topcoat_feed_g",
        "actual_casting_water_feed_g",
        "actual_bath_salt_feed_g",
        "actual_bath_water_feed_g",
        "feed_moisture_known",
        "feed_moisture_notes",
        "actual_bath_salt_hydration_identity",
        "actual_bath_exposure_min",
        "actual_test_temperature_C",
        "actual_water_head_cm",
        "actual_duration_h",
        "specimen_area_cm2",
        "thickness_1_mm",
        "thickness_2_mm",
        "thickness_3_mm",
        "thickness_4_mm",
        "thickness_5_mm",
        "catch_collected_mass_g",
        "matched_blank_collected_mass_g",
        "initial_dry_specimen_mass_g",
        "blotted_wet_specimen_mass_g",
        "redried_specimen_mass_g",
        "initial_length_mm",
        "wet_length_mm",
        "dimensional_change_percent",
        "leak_observations",
        "edge_seal_failure_observations",
        "drying_method_and_endpoint",
        "handling_observations",
        "biodegradation_environment_and_duration",
        "biodegradation_evidence_notes",
        "overall_observations",
    )
    return tuple(
        {
            "formulation_id": row["formulation_id"],
            "replicate": replicate,
            "status": "not_tested",
            "planned_water_head_cm": TEST_PLAN["water_head_cm"],
            "planned_duration_h": TEST_PLAN["duration_h"],
            "planned_temperature_min_C": TEST_PLAN["temperature_min_C"],
            "planned_temperature_max_C": TEST_PLAN["temperature_max_C"],
            **dict.fromkeys(observations, ""),
        }
        for row in rows
        for replicate in range(1, TEST_PLAN["replicates_per_formulation"] + 1)
    )


def build_study(inputs: dict[str, Any], input_sha256: str | None = None) -> Study:
    """Run seven formula analyses and thirteen ideal-feed elemental conversions."""
    validate_inputs(inputs)
    if input_sha256 is not None and (
        not isinstance(input_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", input_sha256) is None
    ):
        raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
    requests = [
        _request("composition.analyze", {"formula": formula}) for formula in FORMULAS.values()
    ]
    responses = _execute(requests)
    analyses = {name: response["result"] for name, response in zip(FORMULAS, responses)}
    rows = list(_formulations())
    elemental_feeds = []
    component_feeds = {
        "pcl_repeat": "pcl_feed_g",
        "starch_repeat": "starch_feed_g",
        "sodium_alginate_repeat": "sodium_alginate_feed_g",
        "glycerol": "glycerol_feed_g",
    }
    for row in rows:
        elemental_mass = {
            symbol: math.fsum(
                row[field] * analyses[name]["mass_fractions"].get(symbol, 0.0)
                for name, field in component_feeds.items()
            )
            for symbol in ELEMENTS
        }
        elemental_feeds.append(elemental_mass)
    feed_requests = [
        _request(
            "composition.from_fractions",
            {"fractions": mass, "basis": "mass", "normalization": "normalize"},
        )
        for mass in elemental_feeds
    ]
    feed_responses = _execute(feed_requests)
    entries = [
        {"label": name, "request": request, "response": response}
        for name, request, response in zip(FORMULAS, requests, responses)
    ]
    for row, elemental_mass, request, response in zip(
        rows, elemental_feeds, feed_requests, feed_responses
    ):
        known_feed = math.fsum(row[field] for field in component_feeds.values())
        if not math.isclose(math.fsum(elemental_mass.values()), known_feed, rel_tol=2e-14):
            raise ValueError(
                "Ideal elemental feed masses do not conserve modeled component feed mass"
            )
        is_alginate = row["sodium_alginate_feed_g"] > 0
        has_bath = row.pop("bath_assigned")
        salt = DESIGN["fresh_bath_pentahydrate_feed_g"] if has_bath else 0.0
        bath_water = DESIGN["fresh_bath_water_feed_g"] if has_bath else 0.0
        calcium_mol = salt / analyses["calcium_lactate_pentahydrate"]["molar_mass_g_mol"]
        sites_mol = (
            row["sodium_alginate_feed_g"] / analyses["sodium_alginate_repeat"]["molar_mass_g_mol"]
        )
        total_nonwater = known_feed + row["beeswax_topcoat_feed_g"]
        row.update(
            {
                "known_formula_feed_g": known_feed,
                "nominal_total_nonwater_formulation_feed_g": total_nonwater,
                "known_formula_mass_coverage_fraction": known_feed / total_nonwater,
                "casting_water_feed_g": DESIGN["casting_water_feed_g"] if is_alginate else 0.0,
                "wax_coating_area_cm2": DESIGN["wax_coating_area_cm2"] if is_alginate else "",
                "nominal_wax_feed_g_cm2": row["beeswax_topcoat_feed_g"]
                / DESIGN["wax_coating_area_cm2"]
                if is_alginate
                else "",
                "bath_salt_identity": "calcium_lactate_pentahydrate" if has_bath else "none",
                "bath_pentahydrate_feed_g": salt,
                "bath_water_feed_g": bath_water,
                "bath_total_feed_g": salt + bath_water,
                "bath_salt_mass_fraction": salt / (salt + bath_water) if has_bath else "",
                "bath_available_calcium_mol": calcium_mol,
                "initial_alginate_carboxylate_site_mol": sites_mol,
                "bath_calcium_site_inventory_ratio": 2 * calcium_mol / sites_mol
                if is_alginate
                else "",
                "same_mass_anhydrous_diagnostic_calcium_mol": salt
                / analyses["calcium_lactate_anhydrous_diagnostic"]["molar_mass_g_mol"]
                if has_bath
                else "",
                **{f"feed_element_mass_g_{symbol}": elemental_mass[symbol] for symbol in ELEMENTS},
                **{
                    f"feed_element_mass_fraction_{symbol}": response["result"][
                        "mass_fractions"
                    ].get(symbol, 0.0)
                    for symbol in ELEMENTS
                },
                "waterproof_status": "unmeasured",
                "biodegradation_status": "unmeasured",
                "home_manufacturing_status": "unvalidated",
            }
        )
        entries.append({"label": row["formulation_id"], "request": request, "response": response})
    digest = input_sha256 or hashlib.sha256(_canonical(inputs).encode()).hexdigest()
    template = _measurement_template(rows)
    summary = {
        "status": "unmeasured_empirical_trial_plan",
        "experiment_version": "1",
        "toolkit_version": __version__,
        "inputs_sha256": digest,
        "input_hash_basis": "exact input file bytes" if input_sha256 else "canonical JSON bytes",
        "formulation_count": len(rows),
        "measurement_template_row_count": len(template),
        "actual_tool_call_count": len(entries),
        "stored_tool_response_count": len(entries),
        "verified_waterproof_formulation_count": 0,
        "verified_biodegradable_formulation_count": 0,
        "verified_all_requirements_formulation_count": 0,
        "ranking": None,
        "nominated_new_material": None,
        "curated_inputs": inputs,
        "limitations": LIMITATIONS,
        "formula_analyses": analyses,
        "elemental_feed_basis": "Only ideal PCL/starch/sodium-alginate repeat units and glycerol before treatment; excludes casting water, bath ingredients and unknown wax composition.",
        "bath_inventory_basis": "Each of nine treated alginate formulations receives a separate fresh bath. Available calcium and initial carboxylate sites are feed inventories, not uptake or a measured crosslink fraction.",
        "same_mass_hydration_diagnostic_ratio": analyses["calcium_lactate_pentahydrate"][
            "molar_mass_g_mol"
        ]
        / analyses["calcium_lactate_anhydrous_diagnostic"]["molar_mass_g_mol"],
        "formulations": rows,
    }
    records = {
        "status": summary["status"],
        "experiment_version": "1",
        "inputs_sha256": digest,
        "snapshot_policy": "Complete actual successful responses. --check validates schemas, timestamps and request hashes, then compares scientific content while retaining recorded runtime provenance.",
        "entries": entries,
    }
    return Study(tuple(rows), summary, records, template)


def _csv(rows: tuple[dict[str, Any], ...]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _scientific_projection(value: Any) -> Any:
    if isinstance(value, list):
        return [_scientific_projection(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _scientific_projection(item)
            for key, item in value.items()
            if key not in {"created_at", "python_version", "software_versions"}
        }
    return value


def _validate_record_responses(records: Any) -> None:
    if not isinstance(records, dict) or not isinstance(records.get("entries"), list):
        raise ValueError("Recorded entries must be a list")
    for entry in records["entries"]:
        _object(entry, {"label", "request", "response"}, "record entry")
        _string(entry["label"], "record label")
        request = _object(entry["request"], {"tool", "tool_version", "input"}, "recorded request")
        response = _object(
            entry["response"], set(ToolResponse.model_fields), "complete tool response"
        )
        provenance = _object(
            response["provenance"], set(Provenance.model_fields), "complete provenance"
        )
        validated = ToolResponse.model_validate(response)
        if validated.status != "ok" or validated.error is not None or validated.result is None:
            raise ValueError("Scientific snapshots must preserve successful calculations")
        if datetime.fromisoformat(provenance["created_at"]).utcoffset() is None:
            raise ValueError("Recorded timestamps must include a timezone")
        _string(provenance["python_version"], "recorded python_version")
        if set(provenance["software_versions"]) != {"pydantic", "periodictable"}:
            raise ValueError("Recorded composition calls must retain package versions")
        for version in provenance["software_versions"].values():
            _string(version, "recorded software version")
        normalized = validate_input(request["tool"], request["input"])
        expected = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        if (
            provenance["input_sha256"] != expected
            or response["tool"] != request["tool"]
            or response["tool_version"] != request["tool_version"]
        ):
            raise ValueError(
                "Recorded response tool/version or validated input hash disagrees with request"
            )


def emit_artifacts(
    inputs_path: str | Path, output_dir: str | Path, *, check: bool = False
) -> dict[str, Any]:
    """Generate data or verify existing files without altering any recording."""
    inputs_path = Path(inputs_path)
    study = build_study(
        load_inputs(inputs_path), hashlib.sha256(inputs_path.read_bytes()).hexdigest()
    )
    artifacts = {
        "formulations.csv": _csv(study.rows),
        "summary.json": _canonical(study.summary),
        "tool-records.json": _canonical(study.records),
        "measurements-template.csv": _csv(study.template),
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
            if name == "tool-records.json":
                try:
                    recorded = json.loads(
                        actual,
                        object_pairs_hook=_reject_duplicates,
                        parse_constant=_reject_constant,
                    )
                    _validate_record_responses(recorded)
                    matches = _canonical(_scientific_projection(recorded)) == _canonical(
                        _scientific_projection(study.records)
                    )
                except (ValueError, KeyError, TypeError):
                    matches = False
            else:
                matches = actual == expected.encode("utf-8")
            if not matches:
                stale.append(name)
        if stale:
            raise ValueError(f"Missing or stale experiment artifacts: {', '.join(stale)}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, value in artifacts.items():
            (output_dir / name).write_text(value, encoding="utf-8")
    return study.summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=HERE / "inputs.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "results")
    parser.add_argument("--check", action="store_true", help="Verify artifacts without writing")
    arguments = parser.parse_args(argv)
    try:
        summary = emit_artifacts(arguments.inputs, arguments.output_dir, check=arguments.check)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 1
    print(
        _canonical(
            {
                key: summary[key]
                for key in (
                    "status",
                    "formulation_count",
                    "measurement_template_row_count",
                    "actual_tool_call_count",
                    "verified_all_requirements_formulation_count",
                )
            }
            | {"checked": arguments.check}
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
