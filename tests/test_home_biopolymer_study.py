"""Independent feed bookkeeping and honest evidence checks for the home study.

Static natural-element weights and expanded grouped-formula atom inventories
provide chemical oracles. None of these checks treats feed bookkeeping as a
prediction of water resistance, retained crosslinks or biodegradation.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import pytest

from materials_agent_toolkit.registry import ToolResponse, validate_input

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "home_biopolymers"

# Independently tabulated conventional natural-element atomic weights, g/mol.
# These match the frozen periodictable dataset; polymer chain ends, water,
# commercial-grade impurities and retained treatment salts are not inferred.
REFERENCE_WEIGHTS = {
    "H": 1.008,
    "C": 12.011,
    "O": 15.999,
    "Na": 22.98976928,
    "Ca": 40.078,
}
FORMULA_COUNTS = {
    "C6H10O2": {"C": 6, "H": 10, "O": 2},
    "C6H10O5": {"C": 6, "H": 10, "O": 5},
    "C6H7NaO6": {"C": 6, "H": 7, "Na": 1, "O": 6},
    "C3H8O3": {"C": 3, "H": 8, "O": 3},
    "Ca(C3H5O3)2(H2O)5": {"Ca": 1, "C": 6, "H": 20, "O": 11},
    "Ca(C3H5O3)2": {"Ca": 1, "C": 6, "H": 10, "O": 6},
    "H2O": {"H": 2, "O": 1},
}


@pytest.fixture(scope="module")
def study_module():
    name = "_tested_home_biopolymer_study"
    spec = importlib.util.spec_from_file_location(name, EXPERIMENT / "study.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs():
    return json.loads((EXPERIMENT / "inputs.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def full_study(study_module):
    inputs = json.loads((EXPERIMENT / "inputs.json").read_text(encoding="utf-8"))
    return study_module.build_study(inputs)


def _formula_mass(formula):
    return math.fsum(
        count * REFERENCE_WEIGHTS[symbol] for symbol, count in FORMULA_COUNTS[formula].items()
    )


def _feed_mass_fractions(feed):
    """Conserve elemental grams from pure-formula feed, independently of tools."""
    total = math.fsum(feed.values())
    element_grams = {symbol: 0.0 for symbol in ("H", "C", "O", "Na")}
    for formula, grams in feed.items():
        for symbol, count in FORMULA_COUNTS[formula].items():
            element_grams[symbol] += (
                grams * count * REFERENCE_WEIGHTS[symbol] / _formula_mass(formula)
            )
    assert math.fsum(element_grams.values()) == pytest.approx(total, abs=2e-14)
    return {symbol: grams / total for symbol, grams in element_grams.items()}


def _without_runtime(value):
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_runtime(item)
            for key, item in value.items()
            if key not in {"created_at", "python_version", "software_versions"}
        }
    return value


def test_complete_trial_grid_preserves_both_matched_controls(full_study):
    rows = full_study.rows
    assert len(rows) == len({row["formulation_id"] for row in rows}) == 13
    pcl = [row for row in rows if row["family"] == "pcl_starch"]
    alginate = [row for row in rows if row["family"] == "calcium_alginate_wax"]
    untreated = [row for row in rows if row["family"] == "sodium_alginate_control"]
    assert {(row["pcl_feed_g"], row["starch_feed_g"]) for row in pcl} == {
        (50.0, 0.0),
        (47.5, 2.5),
        (45.0, 5.0),
    }
    assert {(row["glycerol_feed_g"], row["beeswax_topcoat_feed_g"]) for row in alginate} == {
        (glycerol, wax) for glycerol in (0.2, 0.4, 0.6) for wax in (0.0, 0.2, 0.4)
    }
    assert len(untreated) == 1
    assert untreated[0]["sodium_alginate_feed_g"] == 2.0
    assert untreated[0]["glycerol_feed_g"] == 0.4
    assert untreated[0]["beeswax_topcoat_feed_g"] == 0.0
    assert sum(row["control_role"] == "plain_pcl_control" for row in rows) == 1
    assert sum(row["control_role"] == "untreated_uncoated_control" for row in rows) == 1
    assert sum(row["control_role"] == "uncoated_bath_control" for row in rows) == 3


def test_elemental_feed_conservation_excludes_water_wax_and_treatment(full_study):
    responses = {
        entry["label"]: entry["response"]["result"]
        for entry in full_study.records["entries"]
        if entry["request"]["tool"] == "composition.from_fractions"
    }
    fractions_by_glycerol = {}
    for row in full_study.rows:
        feed = {
            "C6H10O2": row["pcl_feed_g"],
            "C6H10O5": row["starch_feed_g"],
            "C6H7NaO6": row["sodium_alginate_feed_g"],
            "C3H8O3": row["glycerol_feed_g"],
        }
        expected = _feed_mass_fractions(feed)
        known_feed = math.fsum(feed.values())
        assert row["known_formula_feed_g"] == pytest.approx(known_feed, abs=1e-14)
        assert row["nominal_total_nonwater_formulation_feed_g"] == pytest.approx(
            known_feed + row["beeswax_topcoat_feed_g"], abs=1e-14
        )
        assert row["known_formula_mass_coverage_fraction"] == pytest.approx(
            known_feed / (known_feed + row["beeswax_topcoat_feed_g"]), rel=2e-14
        )
        assert math.fsum(row[f"feed_element_mass_g_{s}"] for s in expected) == pytest.approx(
            known_feed, abs=2e-14
        )
        actual = {s: row[f"feed_element_mass_fraction_{s}"] for s in expected}
        assert actual == pytest.approx(expected, rel=2e-14, abs=1e-15)
        for symbol, fraction in expected.items():
            assert row[f"feed_element_mass_g_{symbol}"] == pytest.approx(
                fraction * known_feed, rel=2e-14, abs=1e-15
            )
        assert responses[row["formulation_id"]]["mass_fractions"] == pytest.approx(
            {symbol: fraction for symbol, fraction in expected.items() if fraction}, rel=2e-14
        )
        assert "Ca" not in responses[row["formulation_id"]]["mass_fractions"]
        if row["sodium_alginate_feed_g"]:
            assert row["casting_water_feed_g"] == 100.0
            glycerol = row["glycerol_feed_g"]
            if glycerol in fractions_by_glycerol:
                assert actual == fractions_by_glycerol[glycerol]
            fractions_by_glycerol[glycerol] = actual
        else:
            assert known_feed == 50.0
            assert row["casting_water_feed_g"] == 0.0
    basis = full_study.summary["elemental_feed_basis"].lower()
    assert all(word in basis for word in ("before treatment", "water", "bath", "unknown wax"))
    limitations = full_study.summary["limitations"].lower()
    assert all(word in limitations for word in ("chain ends", "moisture", "additives", "retained"))


def test_calcium_ratios_are_hydration_specific_bath_inventories(full_study):
    available = 2.0 / _formula_mass("Ca(C3H5O3)2(H2O)5")
    anhydrous_diagnostic = 2.0 / _formula_mass("Ca(C3H5O3)2")
    carboxylate_sites = 2.0 / _formula_mass("C6H7NaO6")
    treated = []
    for row in full_study.rows:
        assert row["initial_alginate_carboxylate_site_mol"] == pytest.approx(
            carboxylate_sites if row["sodium_alginate_feed_g"] else 0.0, rel=2e-14
        )
        if row["family"] == "calcium_alginate_wax":
            treated.append(row)
            assert row["bath_salt_identity"] == "calcium_lactate_pentahydrate"
            assert row["bath_pentahydrate_feed_g"] == 2.0
            assert row["bath_water_feed_g"] == 98.0
            assert row["bath_total_feed_g"] == 100.0
            assert row["bath_salt_mass_fraction"] == 0.02
            assert row["bath_available_calcium_mol"] == pytest.approx(available, rel=2e-14)
            assert row["bath_calcium_site_inventory_ratio"] == pytest.approx(
                2 * available / carboxylate_sites, rel=2e-14
            )
            assert row["same_mass_anhydrous_diagnostic_calcium_mol"] == pytest.approx(
                anhydrous_diagnostic, rel=2e-14
            )
            # A ratio above one represents excess supplied inventory, not
            # impossible >100% reaction conversion or a measured crosslink.
            assert row["bath_calcium_site_inventory_ratio"] > 1
        else:
            assert row["bath_salt_identity"] == "none"
            assert row["bath_total_feed_g"] == row["bath_available_calcium_mol"] == 0
            assert row["bath_calcium_site_inventory_ratio"] == (
                0.0 if row["sodium_alginate_feed_g"] else ""
            )
    assert len(treated) == 9
    assert math.fsum(row["bath_pentahydrate_feed_g"] for row in treated) == 18.0
    assert anhydrous_diagnostic / available == pytest.approx(
        full_study.summary["same_mass_hydration_diagnostic_ratio"], rel=2e-14
    )
    basis = full_study.summary["bath_inventory_basis"].lower()
    assert "separate fresh bath" in basis
    assert "not uptake" in basis


def test_no_waterproof_or_biodegradation_result_is_invented(full_study):
    summary = full_study.summary
    assert summary["status"] == "unmeasured_empirical_trial_plan"
    assert summary["ranking"] is summary["nominated_new_material"] is None
    assert summary["verified_waterproof_formulation_count"] == 0
    assert summary["verified_biodegradable_formulation_count"] == 0
    assert summary["verified_all_requirements_formulation_count"] == 0
    for row in full_study.rows:
        assert row["waterproof_status"] == row["biodegradation_status"] == "unmeasured"
        assert row["home_manufacturing_status"] == "unvalidated"
    templates = full_study.template
    identifiers = {row["formulation_id"] for row in full_study.rows}
    assert len(templates) == 39
    assert {(row["formulation_id"], row["replicate"]) for row in templates} == {
        (identifier, replicate) for identifier in identifiers for replicate in (1, 2, 3)
    }
    for row in templates:
        assert row["status"] == "not_tested"
        assert row["planned_water_head_cm"] == 5.0
        assert row["planned_duration_h"] == 24.0
        assert row["planned_temperature_min_C"] == 20.0
        assert row["planned_temperature_max_C"] == 25.0
        for key, value in row.items():
            if key not in {"formulation_id", "replicate", "status"} and not key.startswith(
                "planned_"
            ):
                assert value == "", f"Unperformed measurement {key} is populated"
        assert {
            "initial_dry_specimen_mass_g",
            "blotted_wet_specimen_mass_g",
            "redried_specimen_mass_g",
            "catch_collected_mass_g",
            "matched_blank_collected_mass_g",
            "biodegradation_evidence_notes",
        } <= set(row)


def test_actual_formula_calls_match_independent_atom_inventories(full_study):
    """Grouped pentahydrate and anhydrous salt must remain distinct feeds."""
    entries = [
        entry
        for entry in full_study.records["entries"]
        if entry["request"]["tool"] == "composition.analyze"
    ]
    assert len(entries) == len(FORMULA_COUNTS) == 7
    results = {}
    for entry in entries:
        formula = entry["request"]["input"]["formula"]
        result = entry["response"]["result"]
        assert formula not in results
        results[formula] = result
        assert result["atomic_counts"] == FORMULA_COUNTS[formula]
        assert result["molar_mass_g_mol"] == pytest.approx(_formula_mass(formula), rel=2e-14)
        assert result["mass_fractions"] == pytest.approx(
            {
                symbol: count * REFERENCE_WEIGHTS[symbol] / _formula_mass(formula)
                for symbol, count in FORMULA_COUNTS[formula].items()
            },
            rel=2e-14,
        )
    assert set(results) == set(FORMULA_COUNTS)
    assert (
        results["Ca(C3H5O3)2(H2O)5"]["molar_mass_g_mol"]
        - results["Ca(C3H5O3)2"]["molar_mass_g_mol"]
    ) == pytest.approx(5 * _formula_mass("H2O"), abs=6e-14)


def test_every_actual_response_preserves_complete_provenance(full_study):
    entries = full_study.records["entries"]
    assert len(entries) == 20
    assert len({entry["label"] for entry in entries}) == len(entries)
    assert sum(entry["request"]["tool"] == "composition.from_fractions" for entry in entries) == 13
    for entry in entries:
        request, response = entry["request"], entry["response"]
        ToolResponse.model_validate(response)
        assert response["status"] == "ok"
        assert response["tool"] == request["tool"]
        assert response["tool_version"] == request["tool_version"] == "1"
        provenance = response["provenance"]
        assert datetime.fromisoformat(provenance["created_at"]).tzinfo is not None
        validated = validate_input(request["tool"], request["input"])
        assert (
            provenance["input_sha256"]
            == hashlib.sha256(
                json.dumps(
                    validated, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
        )
        assert provenance["toolkit_version"]
        assert provenance["python_version"]
        assert provenance["references"]
        assert provenance["software_versions"]["periodictable"]


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("design", "pcl_nominal_dry_feed_g", True),
        ("design", "casting_water_feed_g", float("nan")),
        ("design", "fresh_bath_pentahydrate_feed_g", float("inf")),
        ("design", "sodium_alginate_feed_g", -2.0),
        ("design", "starch_nominal_mass_fractions", [0.0, 0.05, 0.10, 0.20]),
        ("test_plan", "replicates_per_formulation", 3.0),
    ],
)
def test_invalid_or_unbounded_plans_fail_before_tools(
    study_module, inputs, monkeypatch, section, key, value
):
    inputs[section][key] = value

    def no_scientific_work(*args, **kwargs):
        pytest.fail("Invalid study inputs reached a scientific calculation")

    monkeypatch.setattr(study_module, "run_batch", no_scientific_work)
    with pytest.raises(ValueError):
        study_module.build_study(inputs)


@pytest.mark.parametrize("mutation", ["unknown_field", "wrong_salt_hydration", "duplicate_source"])
def test_ambiguous_schema_or_chemical_basis_is_rejected(study_module, inputs, mutation):
    if mutation == "unknown_field":
        inputs["predicted_waterproof_pass"] = True
    elif mutation == "wrong_salt_hydration":
        inputs["components"]["calcium_lactate_pentahydrate"]["formula"] = "Ca(C3H5O3)2"
    else:
        inputs["sources"].append(copy.deepcopy(inputs["sources"][0]))
    with pytest.raises(ValueError):
        study_module.validate_inputs(inputs)


@pytest.mark.parametrize(
    "invalid_json",
    [
        '{"experiment_version":"1","experiment_version":"1"}',
        '{"experiment_version":"1","value":NaN}',
        '{"experiment_version":"1","value":Infinity}',
    ],
)
def test_ambiguous_or_nonfinite_json_is_rejected(study_module, tmp_path, invalid_json):
    path = tmp_path / "inputs.json"
    path.write_text(invalid_json, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate|Nonfinite"):
        study_module.load_inputs(path)


@pytest.fixture
def generated_results(study_module, inputs, tmp_path):
    inputs_path = tmp_path / "inputs.json"
    input_bytes = (json.dumps(inputs, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    inputs_path.write_bytes(input_bytes)
    output_dir = tmp_path / "results"
    summary = study_module.emit_artifacts(inputs_path, output_dir)
    return inputs_path, input_bytes, output_dir, summary


def test_exact_input_provenance_and_readonly_reproducibility(study_module, generated_results):
    inputs_path, input_bytes, output_dir, summary = generated_results
    assert summary["inputs_sha256"] == hashlib.sha256(input_bytes).hexdigest()
    assert summary["input_hash_basis"] == "exact input file bytes"
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == summary
    records = json.loads((output_dir / "tool-records.json").read_text(encoding="utf-8"))
    assert records["inputs_sha256"] == summary["inputs_sha256"]
    with (output_dir / "formulations.csv").open(newline="", encoding="utf-8") as stream:
        formulations = list(csv.DictReader(stream))
    with (output_dir / "measurements-template.csv").open(newline="", encoding="utf-8") as stream:
        templates = list(csv.DictReader(stream))
    assert len(formulations) == 13
    assert len(templates) == 39
    assert {row["formulation_id"] for row in formulations} == {
        row["formulation_id"] for row in templates
    }
    assert all(
        row["status"] == "not_tested"
        and row["blotted_wet_specimen_mass_g"] == ""
        and row["catch_collected_mass_g"] == ""
        and row["biodegradation_evidence_notes"] == ""
        for row in templates
    )
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    study_module.emit_artifacts(inputs_path, output_dir)
    after = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert {key: value for key, value in before.items() if key != "tool-records.json"} == {
        key: value for key, value in after.items() if key != "tool-records.json"
    }
    assert _without_runtime(json.loads(before["tool-records.json"])) == _without_runtime(
        json.loads(after["tool-records.json"])
    )
    assert study_module.emit_artifacts(inputs_path, output_dir, check=True) == summary
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == after


@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "modified_feed_csv",
        "fabricated_measurement",
        "modified_science",
        "modified_science_type",
        "missing_timestamp",
        "invalid_timestamp",
        "bad_hash",
    ],
)
def test_readonly_check_rejects_scientific_or_provenance_drift(
    study_module, generated_results, corruption
):
    inputs_path, _, output_dir, _ = generated_results
    if corruption == "missing":
        (output_dir / "summary.json").unlink()
    elif corruption == "modified_feed_csv":
        with (output_dir / "formulations.csv").open("a", encoding="utf-8") as stream:
            stream.write("unexpected formulation\n")
    elif corruption == "fabricated_measurement":
        path = output_dir / "measurements-template.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["catch_collected_mass_g"] = "0"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        path = output_dir / "tool-records.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        response = next(
            entry["response"]
            for entry in records["entries"]
            if entry["request"]["input"].get("formula") == "H2O"
        )
        if corruption == "missing_timestamp":
            del response["provenance"]["created_at"]
        elif corruption == "invalid_timestamp":
            response["provenance"]["created_at"] = "not an execution timestamp"
        elif corruption == "bad_hash":
            response["provenance"]["input_sha256"] = "0" * 64
        elif corruption == "modified_science_type":
            # True == 1 in Python; JSON science must distinguish their types.
            response["result"]["atomic_counts"]["O"] = True
        else:
            response["result"]["molar_mass_g_mol"] += 1.0
        path.write_text(json.dumps(records), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    with pytest.raises(ValueError, match="Missing or stale experiment artifacts"):
        study_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before


def test_readonly_check_preserves_valid_recorded_runtime(study_module, generated_results):
    inputs_path, _, output_dir, _ = generated_results
    path = output_dir / "tool-records.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    provenance = records["entries"][0]["response"]["provenance"]
    provenance["created_at"] = "2001-01-01T00:00:00+00:00"
    provenance["python_version"] = "different recorded runtime"
    provenance["software_versions"] = {
        package: "different recorded version" for package in provenance["software_versions"]
    }
    path.write_text(json.dumps(records), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    study_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before


def test_readonly_check_preserves_older_package_recording(study_module, generated_results):
    inputs_path, _, output_dir, current = generated_results
    summary_path = output_dir / "summary.json"
    summary = json.loads(summary_path.read_bytes())
    summary["toolkit_version"] = "0.0.1"
    summary_path.write_text(study_module._canonical(summary), encoding="utf-8")
    records_path = output_dir / "tool-records.json"
    records = json.loads(records_path.read_bytes())
    for entry in records["entries"]:
        entry["response"]["provenance"]["toolkit_version"] = "0.0.1"
    records_path.write_text(study_module._canonical(records), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert study_module.emit_artifacts(inputs_path, output_dir, check=True) == current
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before


@pytest.mark.parametrize("location", ["summary", "response"])
@pytest.mark.parametrize("version", [None, "", " \t", 6.0])
def test_readonly_check_rejects_invalid_recorded_package_version(
    study_module, generated_results, location, version
):
    inputs_path, _, output_dir, _ = generated_results
    path = output_dir / ("summary.json" if location == "summary" else "tool-records.json")
    recorded = json.loads(path.read_bytes())
    metadata = (
        recorded if location == "summary" else recorded["entries"][0]["response"]["provenance"]
    )
    if version is None:
        del metadata["toolkit_version"]
    else:
        metadata["toolkit_version"] = version
    path.write_text(study_module._canonical(recorded), encoding="utf-8")
    before = {item.name: item.read_bytes() for item in output_dir.iterdir()}
    with pytest.raises(ValueError, match="Missing or stale experiment artifacts"):
        study_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {item.name: item.read_bytes() for item in output_dir.iterdir()} == before


@pytest.mark.parametrize(
    "drift", ["summary_science", "summary_format", "tool_version", "extra_version"]
)
def test_release_compatibility_retains_scientific_and_schema_checks(
    study_module, generated_results, drift
):
    inputs_path, _, output_dir, _ = generated_results
    path = output_dir / ("summary.json" if drift.startswith("summary") else "tool-records.json")
    recorded = json.loads(path.read_bytes())
    if drift == "summary_science":
        recorded["verified_waterproof_formulation_count"] = True
    elif drift == "tool_version":
        recorded["entries"][0]["response"]["tool_version"] = "different tool contract"
    elif drift == "extra_version":
        recorded["entries"][0]["response"]["result"]["toolkit_version"] = "unrelated science"
    path.write_text(
        json.dumps(recorded) if drift == "summary_format" else study_module._canonical(recorded),
        encoding="utf-8",
    )
    before = {item.name: item.read_bytes() for item in output_dir.iterdir()}
    with pytest.raises(ValueError, match="Missing or stale experiment artifacts"):
        study_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {item.name: item.read_bytes() for item in output_dir.iterdir()} == before
