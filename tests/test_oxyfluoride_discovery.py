"""Independent charge, capacity and provenance checks for cathode screening.

These references concern formal Mn redox bookkeeping, not voltage, phase
stability or measured battery performance. The mass references are separately
tabulated natural-element weights; no isotope composition is inferred.
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
from fractions import Fraction
from pathlib import Path

import pytest

from materials_agent_toolkit.registry import ToolResponse, validate_input

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "manganese_oxyfluorides"

# Natural-element reference weights used by the locked periodictable dataset,
# in g/mol. Li 6.94 is the conventional natural-element value, not Li-7 mass.
REFERENCE_WEIGHTS = {
    "Li": 6.94,
    "Mn": 54.938043,
    "Ti": 47.867,
    "Nb": 92.90637,
    "O": 15.999,
    "F": 18.998403162,
}
ELEMENTARY_CHARGE_C = 1.602176634e-19
AVOGADRO_PER_MOL = 6.02214076e23
FARADAY_C_PER_MOL = ELEMENTARY_CHARGE_C * AVOGADRO_PER_MOL


@pytest.fixture(scope="module")
def screen_module():
    path = EXPERIMENT / "screen.py"
    name = "_tested_manganese_oxyfluoride_screen"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs():
    return json.loads((EXPERIMENT / "inputs.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def full_study(screen_module):
    inputs = json.loads((EXPERIMENT / "inputs.json").read_text(encoding="utf-8"))
    return screen_module.build_study(inputs)


def _chemistry_reference(denominator, titanium, niobium):
    """Exact rational charge conservation followed by independent SI conversion."""
    t = Fraction(titanium, denominator)
    n = Fraction(niobium, denominator)
    atom_counts = {
        "Li": Fraction(2),
        "Mn": 1 - t - n,
        "Ti": t,
        "Nb": n,
        "O": Fraction(2),
        "F": Fraction(1),
    }
    manganese_valence = (3 - 4 * t - 5 * n) / atom_counts["Mn"]
    electrons = atom_counts["Mn"] * (4 - manganese_valence)
    mass = math.fsum(
        float(count) * REFERENCE_WEIGHTS[element] for element, count in atom_counts.items()
    )
    return {
        "counts": atom_counts,
        "valence": manganese_valence,
        "electrons": electrons,
        "mass": mass,
        "capacity": float(electrons) * FARADAY_C_PER_MOL / (3.6 * mass),
        "nb_mass_fraction": float(n) * REFERENCE_WEIGHTS["Nb"] / mass,
    }


def _without_runtime(value):
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_runtime(item)
            for key, item in value.items()
            if key not in {"created_at", "python_version", "software_versions", "toolkit_version"}
        }
    return value


@pytest.mark.parametrize("denominator", [1, 2, 3, 6, 12, 60])
def test_grid_is_complete_unique_and_charge_admissible(screen_module, denominator):
    # Full Cartesian enumeration provides an independent grid oracle; it does
    # not use the screen's variable-width loop or floating-point inequalities.
    expected = {
        (i, j)
        for i in range(denominator + 1)
        for j in range(denominator + 1)
        if Fraction(i, denominator) + Fraction(j, denominator) * Fraction(3, 2) <= Fraction(1, 2)
    }
    actual = screen_module.enumerate_grid(denominator)
    assert set(actual) == expected
    assert len(actual) == len(set(actual))
    if denominator == 60:
        assert len(actual) == 331
    for i, j in actual:
        oracle = _chemistry_reference(denominator, i, j)
        counts = screen_module.candidate_counts(denominator, i, j)
        assert counts == {
            symbol: count * denominator for symbol, count in oracle["counts"].items() if count
        }
        assert sum(counts.values()) == 6 * denominator
        charge = (
            counts["Li"]
            + counts["Mn"] * oracle["valence"]
            + 4 * counts.get("Ti", 0)
            + 5 * counts.get("Nb", 0)
            - 2 * counts["O"]
            - counts["F"]
        )
        assert charge == 0
        assert 2 <= oracle["valence"] <= 3
        assert oracle["electrons"] == 1 + Fraction(j, denominator)
        assert 1 <= oracle["electrons"] <= Fraction(4, 3)
        assert oracle["electrons"] < oracle["counts"]["Li"]


@pytest.mark.parametrize(
    ("titanium", "niobium", "capacity"),
    [(0, 0, 223.691566450), (30, 0, 230.493025484), (0, 20, 269.760386752)],
)
def test_tabulated_endmember_capacity_references(full_study, titanium, niobium, capacity):
    # Faraday's exact SI charge and a six-atom formula unit are essential: using
    # the mean atomic mass directly would produce a sixfold capacity error.
    oracle = _chemistry_reference(60, titanium, niobium)
    assert oracle["capacity"] == pytest.approx(capacity, abs=5e-10)
    assert FARADAY_C_PER_MOL == pytest.approx(96485.33212331001, abs=1e-10)
    control = next(
        row
        for row in full_study.summary["controls"]
        if (row["ti_grid_count"], row["nb_grid_count"]) == (titanium, niobium)
    )
    assert control["ideal_capacity_mAh_g"] == pytest.approx(capacity, abs=5e-10)


def test_exact_nominee_stoichiometry_and_reference_capacity():
    oracle = _chemistry_reference(60, 10, 10)
    assert oracle["counts"] == {
        "Li": 2,
        "Mn": Fraction(2, 3),
        "Ti": Fraction(1, 6),
        "Nb": Fraction(1, 6),
        "O": 2,
        "F": 1,
    }
    assert oracle["valence"] == Fraction(9, 4)
    assert oracle["electrons"] == Fraction(7, 6)
    assert oracle["mass"] == pytest.approx(124.96399349533334, abs=1e-11)
    assert oracle["capacity"] == pytest.approx(250.219233517, abs=5e-10)
    assert oracle["nb_mass_fraction"] == pytest.approx(0.12391085277, abs=5e-12)


def test_every_candidate_agrees_with_independent_chemical_and_si_oracles(full_study):
    assert len(full_study.rows) == 331
    identities = set()
    for row in full_study.rows:
        d = row["grid_denominator"]
        i, j = row["ti_grid_count"], row["nb_grid_count"]
        identities.add((i, j))
        oracle = _chemistry_reference(d, i, j)
        formula_units = math.lcm(*(count.denominator for count in oracle["counts"].values()))
        assert row["formula_units_per_integer_formula"] == formula_units
        assert row["mn_grid_count"] == d - i - j
        assert row["ti_fraction"] == pytest.approx(float(oracle["counts"]["Ti"]))
        assert row["nb_fraction"] == pytest.approx(float(oracle["counts"]["Nb"]))
        assert row["mn_fraction"] == pytest.approx(float(oracle["counts"]["Mn"]))
        assert row["manganese_initial_mean_valence"] == pytest.approx(
            float(oracle["valence"]), abs=2e-15
        )
        assert row["manganese_final_assumed_valence"] == 4
        assert row["electrons_per_formula"] == pytest.approx(float(oracle["electrons"]), abs=1e-15)
        assert row["residual_lithium_per_formula"] == pytest.approx(
            float(2 - oracle["electrons"]), abs=1e-15
        )
        assert row["normalized_molar_mass_g_mol"] == pytest.approx(oracle["mass"], rel=2e-14)
        assert row["mean_atomic_mass_g_mol"] == pytest.approx(oracle["mass"] / 6, rel=2e-14)
        assert row["molar_mass_crosscheck_relative_error"] <= 5e-15
        assert row["ideal_capacity_mAh_g"] == pytest.approx(oracle["capacity"], rel=2e-14)
        mass_fractions = {
            element: float(count) * REFERENCE_WEIGHTS[element] / oracle["mass"]
            for element, count in oracle["counts"].items()
        }
        assert {element: row[f"mass_fraction_{element}"] for element in REFERENCE_WEIGHTS} == (
            pytest.approx(mass_fractions, rel=2e-14, abs=1e-16)
        )
        assert math.fsum(row[f"mass_fraction_{element}"] for element in REFERENCE_WEIGHTS) == (
            pytest.approx(1, abs=5e-16)
        )
        # No lattice, electronic or energetic model is available in this study.
        assert not any(
            prohibited in key.lower()
            for key in row
            for prohibited in ("voltage", "energy_density", "density_kg", "formation_energy")
        )
    assert len(identities) == 331


def test_formal_redox_helpers_conserve_charge_and_lithium(screen_module):
    for d, i, j in ((1, 0, 0), (2, 1, 0), (3, 0, 1), (60, 10, 10), (60, 1, 19)):
        budget = screen_module.oxidation_budget(d, i, j)
        oracle = _chemistry_reference(d, i, j)
        assert budget["initial_mean_valence"] == pytest.approx(float(oracle["valence"]), abs=2e-15)
        assert budget["final_assumed_valence"] == 4
        assert budget["electrons_per_formula"] == pytest.approx(
            float(oracle["electrons"]), abs=1e-15
        )
        assert (
            Fraction(budget["electron_numerator"], budget["electron_denominator"])
            == (oracle["electrons"])
        )
        assert budget["electrons_per_formula"] + budget["residual_lithium_per_formula"] == (
            pytest.approx(2, abs=2e-15)
        )


def test_gates_and_minimum_niobium_mass_nomination(full_study):
    feasible = []
    for row in full_study.rows:
        capacity_passes = row["ideal_capacity_mAh_g"] >= 250
        niobium_passes = row["mass_fraction_Nb"] <= 0.15
        assert row["passes_capacity"] is capacity_passes
        assert row["passes_nb_mass_fraction"] is niobium_passes
        assert row["feasible"] is (capacity_passes and niobium_passes)
        oracle = _chemistry_reference(60, row["ti_grid_count"], row["nb_grid_count"])
        expected_margin = min(
            (oracle["capacity"] - 250) / 250,
            (0.15 - oracle["nb_mass_fraction"]) / 0.15,
        )
        assert row["minimum_normalized_gate_margin"] == pytest.approx(expected_margin, abs=2e-15)
        if row["feasible"]:
            feasible.append(row)
    assert len(feasible) == 33
    nominee = min(
        feasible,
        key=lambda row: (
            row["mass_fraction_Nb"],
            -row["ideal_capacity_mAh_g"],
            row["ti_grid_count"],
            row["nb_grid_count"],
        ),
    )
    assert (nominee["ti_grid_count"], nominee["nb_grid_count"]) == (10, 10)
    assert nominee["normalized_molar_mass_g_mol"] == pytest.approx(124.96399349533334, abs=1e-11)
    assert nominee["ideal_capacity_mAh_g"] == pytest.approx(250.219233517, abs=5e-10)
    assert nominee["mass_fraction_Nb"] == pytest.approx(0.12391085277, abs=5e-12)
    assert full_study.summary["nominated_candidate"]["candidate_id"] == nominee["candidate_id"]
    assert full_study.summary["nominated_candidate"]["nominal"] == nominee
    assert full_study.summary["nominal_feasible_count"] == 33
    assert full_study.summary["evaluation_count"] == 331 * 4
    assert full_study.summary["feasible_counts_by_scenario"] == {
        "nominal": 33,
        "utilization_90pct": 0,
        "utilization_80pct": 0,
        "utilization_70pct": 0,
    }
    most_margin = max(feasible, key=lambda row: row["minimum_normalized_gate_margin"])
    assert (most_margin["ti_grid_count"], most_margin["nb_grid_count"]) == (10, 12)
    assert most_margin["minimum_normalized_gate_margin"] == pytest.approx(
        0.01865207774841412, abs=2e-15
    )
    assert full_study.summary["highest_nominal_margin_candidate"] == most_margin


def test_capacity_is_limited_by_mass_charge_and_hypothetical_utilization(full_study):
    # The Nb-only, Mn(II) boundary maximizes this rational capacity function.
    # Even that maximum cannot reach 250 mAh/g at 90% utilization.
    maximum = max(full_study.rows, key=lambda row: row["ideal_capacity_mAh_g"])
    assert (maximum["ti_grid_count"], maximum["nb_grid_count"]) == (0, 20)
    assert maximum["ideal_capacity_mAh_g"] == pytest.approx(269.760386752, abs=5e-10)
    assert full_study.summary["maximum_formal_capacity_candidate"] == maximum
    assert 0.9 * maximum["ideal_capacity_mAh_g"] < 250
    niobium_limited = max(
        (row for row in full_study.rows if row["mass_fraction_Nb"] <= 0.15),
        key=lambda row: row["ideal_capacity_mAh_g"],
    )
    assert (niobium_limited["ti_grid_count"], niobium_limited["nb_grid_count"]) == (12, 12)
    assert niobium_limited["ideal_capacity_mAh_g"] == pytest.approx(255.26455342951576, abs=1e-10)
    assert full_study.summary["maximum_formal_capacity_within_nb_gate_candidate"] == niobium_limited
    assert 250 / niobium_limited["ideal_capacity_mAh_g"] > 0.979
    for row in full_study.rows:
        assert row["ideal_capacity_mAh_g"] > 0
        assert row["ideal_capacity_mAh_g"] <= maximum["ideal_capacity_mAh_g"]
        assert row["nominal_capacity_mAh_g"] == row["ideal_capacity_mAh_g"]
        assert row["nominal_feasible"] is row["feasible"]
        for identifier, fraction in (
            ("utilization_90pct", 0.9),
            ("utilization_80pct", 0.8),
            ("utilization_70pct", 0.7),
        ):
            assert row[f"{identifier}_capacity_mAh_g"] == pytest.approx(
                fraction * row["ideal_capacity_mAh_g"], rel=2e-15
            )
            assert row[f"{identifier}_feasible"] is False


def test_gates_include_exact_boundary_values(screen_module):
    gates = {"ideal_capacity_min_mAh_g": 250.0, "nb_mass_fraction_max": 0.15}
    boundary = screen_module.evaluate_gates(250.0, 0.15, gates)
    assert boundary["passes_capacity"] is True
    assert boundary["passes_nb_mass_fraction"] is True
    assert boundary["feasible"] is True
    assert boundary["minimum_normalized_gate_margin"] == 0
    below = screen_module.evaluate_gates(math.nextafter(250, 0), 0.15, gates)
    above = screen_module.evaluate_gates(250.0, math.nextafter(0.15, math.inf), gates)
    assert below["passes_capacity"] is False
    assert below["passes_nb_mass_fraction"] is True
    assert above["passes_capacity"] is True
    assert above["passes_nb_mass_fraction"] is False
    assert below["feasible"] is above["feasible"] is False


def test_zero_niobium_gate_has_finite_margin_and_rejects_any_niobium(screen_module):
    gates = {"ideal_capacity_min_mAh_g": 200.0, "nb_mass_fraction_max": 0.0}
    no_niobium = screen_module.evaluate_gates(223.691566450, 0.0, gates)
    with_niobium = screen_module.evaluate_gates(269.760386752, 0.2337786684907288, gates)
    assert no_niobium["feasible"] is True
    assert no_niobium["minimum_normalized_gate_margin"] == 0
    assert with_niobium["passes_capacity"] is True
    assert with_niobium["passes_nb_mass_fraction"] is False
    assert with_niobium["feasible"] is False
    assert math.isfinite(with_niobium["minimum_normalized_gate_margin"])


def test_scenario_changes_are_isolated_and_inputs_are_preserved(screen_module, inputs):
    inputs["grid_denominator"] = 6
    original = copy.deepcopy(inputs)
    first = screen_module.build_study(inputs)
    assert inputs == original
    changed = copy.deepcopy(inputs)
    scenario = next(item for item in changed["scenarios"] if item["id"] == "utilization_90pct")
    scenario["utilization_denominator"] = 20
    second = screen_module.build_study(changed)
    assert changed["scenarios"][1]["utilization_denominator"] == 20
    assert len(first.rows) == len(second.rows) == 7
    first_rows = {row["candidate_id"]: row for row in first.rows}
    second_rows = {row["candidate_id"]: row for row in second.rows}
    for identifier, row in first_rows.items():
        modified = second_rows[identifier]
        assert modified["utilization_90pct_capacity_mAh_g"] == pytest.approx(
            0.5 * row["utilization_90pct_capacity_mAh_g"], rel=2e-15
        )
        assert {
            key: value for key, value in row.items() if not key.startswith("utilization_90pct_")
        } == {
            key: value
            for key, value in modified.items()
            if not key.startswith("utilization_90pct_")
        }
    reordered = copy.deepcopy(inputs)
    reordered["scenarios"].reverse()
    third = screen_module.build_study(reordered)
    assert {row["candidate_id"]: row for row in third.rows} == first_rows
    assert _without_runtime(first.records["entries"]) == _without_runtime(second.records["entries"])


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("root", "grid_denominator", True),
        ("root", "grid_denominator", 0),
        ("root", "grid_denominator", 121),
        ("root", "family", "Li2Mn[55]O2F"),
        ("screen", "ideal_capacity_min_mAh_g", True),
        ("screen", "ideal_capacity_min_mAh_g", 0),
        ("screen", "ideal_capacity_min_mAh_g", float("nan")),
        ("screen", "nb_mass_fraction_max", float("inf")),
        ("screen", "nb_mass_fraction_max", -0.1),
        ("screen", "nb_mass_fraction_max", 1.1),
        ("model", "manganese_final_assumed_valence", 5),
        ("model", "lithium_atoms_per_formula", True),
        ("scenario", "utilization_numerator", False),
        ("scenario", "utilization_numerator", 11),
        ("scenario", "utilization_denominator", 0),
        ("scenario", "utilization_denominator", 1.5),
    ],
)
def test_invalid_study_inputs_fail_before_any_tool_call(
    screen_module, inputs, monkeypatch, section, key, value
):
    target = (
        inputs
        if section == "root"
        else inputs["scenarios"][1]
        if section == "scenario"
        else inputs[section]
    )
    target[key] = value

    def no_scientific_work(*args, **kwargs):
        pytest.fail("Invalid study inputs reached a scientific calculation")

    monkeypatch.setattr(screen_module, "run_batch", no_scientific_work)
    with pytest.raises(ValueError):
        screen_module.build_study(inputs)


@pytest.mark.parametrize(
    "mutation", ["unknown_field", "duplicate_scenario", "wrong_nominal", "changed_charge"]
)
def test_schema_ambiguities_and_incompatible_charge_models_are_rejected(
    screen_module, inputs, mutation
):
    if mutation == "unknown_field":
        inputs["voltage_prediction"] = 4.0
    elif mutation == "duplicate_scenario":
        inputs["scenarios"].append(copy.deepcopy(inputs["scenarios"][1]))
    elif mutation == "wrong_nominal":
        inputs["scenarios"][0]["utilization_denominator"] = 2
    else:
        inputs["model"]["spectator_oxidation_states"]["Ti"] = 3
    with pytest.raises(ValueError):
        screen_module.validate_inputs(inputs)


def test_all_actual_tool_responses_have_complete_provenance_and_correct_science(full_study):
    rows = {row["candidate_id"]: row for row in full_study.rows}
    assert len(full_study.records["entries"]) == 331
    seen = set()
    response_count = 0
    for entry in full_study.records["entries"]:
        row = rows[entry["candidate_id"]]
        seen.add(entry["candidate_id"])
        oracle = _chemistry_reference(
            row["grid_denominator"], row["ti_grid_count"], row["nb_grid_count"]
        )
        assert len(entry["requests"]) == len(entry["responses"]) == 2
        tools = set()
        for request, response in zip(entry["requests"], entry["responses"], strict=True):
            ToolResponse.model_validate(response)
            response_count += 1
            assert response["status"] == "ok"
            assert response["tool"] == request["tool"]
            assert response["tool_version"] == request["tool_version"] == "1"
            tools.add(response["tool"])
            provenance = response["provenance"]
            assert datetime.fromisoformat(provenance["created_at"]).tzinfo is not None
            validated = validate_input(request["tool"], request["input"])
            expected_hash = hashlib.sha256(
                json.dumps(
                    validated, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
            assert provenance["input_sha256"] == expected_hash
            assert provenance["software_versions"]
            assert provenance["references"]
            assert "periodictable" in provenance["software_versions"]
            result = response["result"]
            if response["tool"] == "composition.analyze":
                assert result["molar_mass_g_mol"] / row[
                    "formula_units_per_integer_formula"
                ] == pytest.approx(oracle["mass"], rel=2e-14)
                assert result["atomic_counts"] == {
                    symbol: int(count * row["formula_units_per_integer_formula"])
                    for symbol, count in oracle["counts"].items()
                    if count
                }
            else:
                assert result["mean_atomic_mass_g_mol"] * 6 == pytest.approx(
                    oracle["mass"], rel=2e-14
                )
            assert result["atomic_fractions"] == pytest.approx(
                {symbol: float(count / 6) for symbol, count in oracle["counts"].items() if count},
                rel=2e-14,
            )
        assert tools == {"composition.analyze", "composition.from_fractions"}
    assert seen == set(rows)
    assert response_count == 662


@pytest.mark.parametrize(
    "invalid_json",
    [
        '{"experiment_version":"1","experiment_version":"1"}',
        '{"experiment_version":"1","value":NaN}',
        '{"experiment_version":"1","value":Infinity}',
        '{"experiment_version":"1","value":-Infinity}',
    ],
)
def test_load_inputs_rejects_nonfinite_or_ambiguous_json(screen_module, tmp_path, invalid_json):
    path = tmp_path / "inputs.json"
    path.write_text(invalid_json, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate|Nonfinite"):
        screen_module.load_inputs(path)


@pytest.mark.parametrize("denominator", [True, False, 0, -1, 121, 1.5, float("nan")])
def test_public_grid_helpers_reject_invalid_denominators(screen_module, denominator):
    for operation in (
        lambda: screen_module.enumerate_grid(denominator),
        lambda: screen_module.candidate_counts(denominator, 0, 0),
        lambda: screen_module.oxidation_budget(denominator, 0, 0),
    ):
        with pytest.raises(ValueError):
            operation()


@pytest.mark.parametrize(
    ("titanium", "niobium"),
    [(True, 0), (0, False), (-1, 0), (0, -1), (1.5, 0), (0, 1.5), (31, 0), (0, 21), (30, 1)],
)
def test_public_chemistry_helpers_reject_inadmissible_sites(screen_module, titanium, niobium):
    for operation in (
        lambda: screen_module.candidate_counts(60, titanium, niobium),
        lambda: screen_module.oxidation_budget(60, titanium, niobium),
    ):
        with pytest.raises(ValueError):
            operation()


@pytest.fixture
def generated_results(screen_module, inputs, tmp_path):
    inputs["grid_denominator"] = 6
    inputs_path = tmp_path / "inputs.json"
    input_bytes = (json.dumps(inputs, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    inputs_path.write_bytes(input_bytes)
    output_dir = tmp_path / "results"
    summary = screen_module.emit_artifacts(inputs_path, output_dir)
    return inputs_path, input_bytes, output_dir, summary


def test_artifacts_cover_grid_and_preserve_exact_input_bytes(screen_module, generated_results):
    inputs_path, input_bytes, output_dir, summary = generated_results
    assert summary["inputs_sha256"] == hashlib.sha256(input_bytes).hexdigest()
    assert summary["input_hash_basis"] == "exact input file bytes"
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == summary
    with (output_dir / "candidates.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 7
    assert {(int(row["ti_grid_count"]), int(row["nb_grid_count"])) for row in rows} == {
        (0, 0),
        (1, 0),
        (2, 0),
        (3, 0),
        (0, 1),
        (1, 1),
        (0, 2),
    }
    records = json.loads((output_dir / "tool-records.json").read_text(encoding="utf-8"))
    assert records["inputs_sha256"] == summary["inputs_sha256"]
    assert len(records["entries"]) == 7
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    screen_module.emit_artifacts(inputs_path, output_dir)
    after = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert {key: value for key, value in before.items() if key != "tool-records.json"} == {
        key: value for key, value in after.items() if key != "tool-records.json"
    }
    assert _without_runtime(json.loads(before["tool-records.json"])) == _without_runtime(
        json.loads(after["tool-records.json"])
    )
    assert screen_module.emit_artifacts(inputs_path, output_dir, check=True) == summary
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == after


@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "modified_csv",
        "modified_science",
        "modified_science_type",
        "missing_timestamp",
        "invalid_timestamp",
        "bad_hash",
    ],
)
def test_readonly_check_rejects_drift_without_writing(screen_module, generated_results, corruption):
    inputs_path, _, output_dir, _ = generated_results
    if corruption == "missing":
        (output_dir / "summary.json").unlink()
    elif corruption == "modified_csv":
        with (output_dir / "candidates.csv").open("a", encoding="utf-8") as stream:
            stream.write("unexpected row\n")
    else:
        path = output_dir / "tool-records.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        response = records["entries"][0]["responses"][0]
        if corruption == "missing_timestamp":
            del response["provenance"]["created_at"]
        elif corruption == "invalid_timestamp":
            response["provenance"]["created_at"] = "not an execution timestamp"
        elif corruption == "bad_hash":
            response["provenance"]["input_sha256"] = "0" * 64
        elif corruption == "modified_science_type":
            # Python dictionary equality equates True with the correct F count
            # 1. A scientific JSON snapshot must preserve their distinct types.
            response["result"]["atomic_counts"]["F"] = True
        else:
            response["result"]["molar_mass_g_mol"] += 1.0
        path.write_text(json.dumps(records), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    with pytest.raises(ValueError, match="Missing or stale experiment artifacts"):
        screen_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before


def test_readonly_check_preserves_recorded_runtime(screen_module, generated_results):
    inputs_path, _, output_dir, _ = generated_results
    path = output_dir / "tool-records.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    provenance = records["entries"][0]["responses"][0]["provenance"]
    provenance["python_version"] = "different recorded runtime"
    provenance["software_versions"] = {
        package: "different recorded version" for package in provenance["software_versions"]
    }
    path.write_text(json.dumps(records), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    screen_module.emit_artifacts(inputs_path, output_dir, check=True)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before
