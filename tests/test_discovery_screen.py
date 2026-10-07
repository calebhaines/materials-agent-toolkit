"""Independent physical and reproducibility checks for the bounded discovery study.

Only small composition grids are evaluated here. Elastic references are formed
from engineering-Voigt stiffness/compliance matrices rather than the study's
scalar bulk/shear implementation.
"""

from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import importlib.util
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import periodictable
import pytest

from materials_agent_toolkit.registry import ToolResponse

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "lightweight_composites"


@pytest.fixture(scope="module")
def screen_module():
    path = EXPERIMENT / "screen.py"
    name = "_tested_lightweight_composite_screen"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def small_inputs():
    inputs = json.loads((EXPERIMENT / "inputs.json").read_text(encoding="utf-8"))
    inputs["screen"].update(
        grid_step_vol_percent=10,
        min_ceramic_vol_percent=10,
        max_ceramic_vol_percent=10,
    )
    return inputs


def _phase_properties(inputs, scenario):
    """Construct a scenario independently, without modifying input phases."""
    properties = copy.deepcopy(inputs["constituents"])
    for phase in properties:
        for key, scale in scenario["property_scales"].items():
            phase[key] *= scale
        phase.update(scenario["property_overrides"].get(phase["id"], {}))
    return properties


def _elastic_tensors(young, poisson):
    compliance = np.zeros((6, 6), dtype=float)
    compliance[:3, :3] = -poisson / young
    np.fill_diagonal(compliance[:3, :3], 1.0 / young)
    compliance[3:, 3:] = np.eye(3) * 2.0 * (1.0 + poisson) / young
    return np.linalg.inv(compliance), compliance


def _tensor_properties(stiffness):
    compliance = np.linalg.inv(stiffness)
    return {
        "young": 1.0 / compliance[0, 0],
        "bulk": stiffness[:3, :3].sum() / 9.0,
        "shear": stiffness[3, 3],
    }


def _physical_oracle(properties, fractions):
    tensors = [
        _elastic_tensors(phase["young_modulus_GPa"], phase["poisson_ratio"]) for phase in properties
    ]
    stiffness_v = sum(f * pair[0] for f, pair in zip(fractions, tensors, strict=True))
    compliance_r = sum(f * pair[1] for f, pair in zip(fractions, tensors, strict=True))
    stiffness_r = np.linalg.inv(compliance_r)
    density = sum(
        f * phase["density_kg_m3"] for f, phase in zip(fractions, properties, strict=True)
    )
    bulk = np.array([_tensor_properties(pair[0])["bulk"] for pair in tensors])
    alpha = np.array([phase["cte_per_K"] for phase in properties])
    conductivity = np.array([phase["conductivity_W_m_K"] for phase in properties])
    fractions = np.asarray(fractions)
    return {
        "density": density,
        "voigt": _tensor_properties(stiffness_v),
        "reuss": _tensor_properties(stiffness_r),
        "conductivity_harmonic": 1.0 / np.sum(fractions / conductivity),
        "conductivity_arithmetic": np.sum(fractions * conductivity),
        "cte_volume": np.sum(fractions * alpha),
        "cte_turner": np.sum(fractions * bulk * alpha) / np.sum(fractions * bulk),
    }


def _loosen_gates(inputs):
    inputs["screen"].update(
        density_max_kg_m3=1.0e6,
        specific_modulus_min_GPa_per_g_cm3=1.0e-6,
        conductivity_min_W_m_K=1.0e-6,
        cte_proxy_max_per_K=1.0,
    )


def _fractions(row, inputs):
    return [row[f"{phase['id']}_vol_percent"] / 100.0 for phase in inputs["constituents"]]


def _row_map(rows):
    return {(row["candidate_id"], row["scenario_id"]): row for row in rows}


def _without_execution_timestamps(value):
    if isinstance(value, list):
        return [_without_execution_timestamps(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_execution_timestamps(item)
            for key, item in value.items()
            if key != "created_at"
        }
    return value


def test_tensor_elastic_and_transport_oracles(screen_module, small_inputs):
    """Every scenario agrees with independent full 6×6 matrix averaging."""
    small_inputs["screen"]["grid_step_vol_percent"] = 5
    rows, _, _ = screen_module.screen_candidates(small_inputs)
    scenarios = {scenario["id"]: scenario for scenario in small_inputs["scenarios"]}
    for row in rows:
        properties = _phase_properties(small_inputs, scenarios[row["scenario_id"]])
        fractions = _fractions(row, small_inputs)
        oracle = _physical_oracle(properties, fractions)
        assert row["density_kg_m3"] == pytest.approx(oracle["density"], rel=2e-14)
        for name in ("voigt", "reuss"):
            for property_name in ("bulk", "shear", "young"):
                assert row[f"{property_name}_modulus_{name}_GPa"] == pytest.approx(
                    oracle[name][property_name], rel=2e-13
                )
        harmonic_young = 1.0 / sum(
            f / phase["young_modulus_GPa"] for f, phase in zip(fractions, properties, strict=True)
        )
        assert row["young_modulus_reuss_GPa"] == pytest.approx(harmonic_young, rel=2e-13)
        assert row["conductivity_reuss_W_m_K"] == pytest.approx(
            oracle["conductivity_harmonic"], rel=2e-13
        )
        assert row["conductivity_voigt_W_m_K"] == pytest.approx(
            oracle["conductivity_arithmetic"], rel=2e-13
        )
        assert row["cte_volume_average_per_K"] == pytest.approx(oracle["cte_volume"], rel=2e-13)
        assert row["cte_turner_per_K"] == pytest.approx(oracle["cte_turner"], rel=2e-13)
        assert row["cte_max_proxy_per_K"] == pytest.approx(
            max(oracle["cte_volume"], oracle["cte_turner"]), rel=2e-13
        )
        assert row["specific_modulus_reuss_GPa_per_g_cm3"] == pytest.approx(
            oracle["reuss"]["young"] / (oracle["density"] / 1000.0), rel=2e-13
        )


def test_complete_unique_grid_and_all_scenarios(screen_module, small_inputs):
    small_inputs["screen"].update(
        grid_step_vol_percent=5, min_ceramic_vol_percent=5, max_ceramic_vol_percent=10
    )
    rows, summary, _ = screen_module.screen_candidates(small_inputs)
    expected = {
        (100 - sum(parts), *parts)
        for parts in itertools.product((0, 5, 10), repeat=3)
        if 5 <= sum(parts) <= 10
    }
    nominal = [row for row in rows if row["scenario_id"] == "nominal"]
    actual = {
        tuple(row[f"{phase['id']}_vol_percent"] for phase in small_inputs["constituents"])
        for row in nominal
    }
    assert actual == expected
    assert len(expected) == 9
    assert len(nominal) == len(actual)
    assert len(rows) == len(_row_map(rows)) == 9 * 7
    assert summary["candidate_count"] == 9
    assert summary["evaluation_count"] == len(rows)
    assert all(sum(_fractions(row, small_inputs)) == pytest.approx(1.0) for row in rows)
    assert all(row["ceramic_vol_percent"] in (5, 10) for row in rows)


def test_homogeneous_phase_limits(screen_module, small_inputs):
    small_inputs["scenarios"] = small_inputs["scenarios"][:1]
    small_inputs["screen"].update(
        grid_step_vol_percent=100, min_ceramic_vol_percent=0, max_ceramic_vol_percent=100
    )
    _loosen_gates(small_inputs)
    rows, summary, _ = screen_module.screen_candidates(small_inputs)
    assert summary["candidate_count"] == 4
    for row in rows:
        phase = next(
            phase
            for phase in small_inputs["constituents"]
            if row[f"{phase['id']}_vol_percent"] == 100
        )
        assert row["density_kg_m3"] == phase["density_kg_m3"]
        for endpoint in ("voigt", "reuss"):
            assert row[f"young_modulus_{endpoint}_GPa"] == pytest.approx(
                phase["young_modulus_GPa"], rel=2e-13
            )
            assert row[f"conductivity_{endpoint}_W_m_K"] == pytest.approx(
                phase["conductivity_W_m_K"], rel=2e-13
            )
        assert row["cte_volume_average_per_K"] == pytest.approx(phase["cte_per_K"], rel=2e-13)
        assert row["cte_turner_per_K"] == pytest.approx(phase["cte_per_K"], rel=2e-13)


def test_feasibility_is_conjunction_of_declared_gates(screen_module, small_inputs):
    rows, summary, _ = screen_module.screen_candidates(small_inputs)
    limits = small_inputs["screen"]
    for row in rows:
        flags = {
            "passes_density": row["density_kg_m3"] <= limits["density_max_kg_m3"],
            "passes_specific_modulus": row["specific_modulus_reuss_GPa_per_g_cm3"]
            >= limits["specific_modulus_min_GPa_per_g_cm3"],
            "passes_conductivity": row["conductivity_reuss_W_m_K"]
            >= limits["conductivity_min_W_m_K"],
            "passes_cte_proxy": row["cte_max_proxy_per_K"] <= limits["cte_proxy_max_per_K"],
        }
        assert {name: row[name] for name in flags} == flags
        assert row["feasible"] is all(flags.values())
    assert summary["nominal_feasible_count"] == sum(
        row["feasible"] for row in rows if row["scenario_id"] == "nominal"
    )
    assert summary["all_scenarios_feasible_count"] == sum(
        all(row["feasible"] for row in rows if row["candidate_id"] == candidate)
        for candidate in {row["candidate_id"] for row in rows}
    )


def test_gate_thresholds_include_equal_values(screen_module, small_inputs):
    small_inputs["scenarios"] = small_inputs["scenarios"][:1]
    rows, _, _ = screen_module.screen_candidates(small_inputs)
    target = rows[0]
    small_inputs["screen"].update(
        density_max_kg_m3=target["density_kg_m3"],
        specific_modulus_min_GPa_per_g_cm3=target["specific_modulus_reuss_GPa_per_g_cm3"],
        conductivity_min_W_m_K=target["conductivity_reuss_W_m_K"],
        cte_proxy_max_per_K=target["cte_max_proxy_per_K"],
    )
    checked, _, _ = screen_module.screen_candidates(small_inputs)
    boundary = next(row for row in checked if row["candidate_id"] == target["candidate_id"])
    assert boundary["feasible"] is True
    assert all(value for name, value in boundary.items() if name.startswith("passes_"))
    assert boundary["minimum_normalized_gate_margin"] == 0.0


@pytest.mark.parametrize(
    ("threshold", "value", "flag"),
    [
        ("density_max_kg_m3", 1000.0, "passes_density"),
        ("specific_modulus_min_GPa_per_g_cm3", 1.0e6, "passes_specific_modulus"),
        ("conductivity_min_W_m_K", 1.0e6, "passes_conductivity"),
        ("cte_proxy_max_per_K", 1.0e-12, "passes_cte_proxy"),
    ],
)
def test_each_gate_can_independently_reject_candidates(
    screen_module, small_inputs, threshold, value, flag
):
    small_inputs["scenarios"] = small_inputs["scenarios"][:1]
    _loosen_gates(small_inputs)
    small_inputs["screen"][threshold] = value
    rows, summary, _ = screen_module.screen_candidates(small_inputs)
    for row in rows:
        assert row[flag] is False
        assert row["feasible"] is False
        assert all(row[key] for key in row if key.startswith("passes_") and key != flag)
    assert summary["nominal_feasible_count"] == 0
    assert summary["nominated_candidate"] is None


def test_nomination_mass_balance_and_matched_loading_controls(screen_module, small_inputs):
    _loosen_gates(small_inputs)
    rows, summary, _ = screen_module.screen_candidates(small_inputs)
    nomination = summary["nominated_candidate"]
    assert nomination is not None
    nominal = [row for row in rows if row["scenario_id"] == "nominal"]
    expected = min(
        nominal,
        key=lambda row: (
            row["ceramic_vol_percent"],
            -row["conductivity_reuss_W_m_K"],
            -row["specific_modulus_reuss_GPa_per_g_cm3"],
            *(row[f"{phase['id']}_vol_percent"] for phase in small_inputs["constituents"]),
        ),
    )
    assert nomination["candidate_id"] == expected["candidate_id"]
    assert nomination["phase_volume_percent"] == {"Al": 90, "SiC": 0, "AlN": 10, "Al2O3": 0}
    expected_mass = {"Al": 0.9 * 2700.0, "AlN": 0.1 * 3300.0}
    total_mass = sum(expected_mass.values())
    phase_mass_fractions = nomination["ideal_phase_mass_fractions"]
    assert phase_mass_fractions == pytest.approx(
        {name: mass / total_mass for name, mass in expected_mass.items()}, rel=2e-13
    )
    assert sum(phase_mass_fractions.values()) == pytest.approx(1.0, abs=2e-14)
    nitrogen_fraction = (
        phase_mass_fractions["AlN"]
        * periodictable.N.mass
        / (periodictable.Al.mass + periodictable.N.mass)
    )
    assert nomination["ideal_elemental_composition"]["mass_fractions"] == pytest.approx(
        {"Al": 1.0 - nitrogen_fraction, "N": nitrogen_fraction}, rel=2e-13
    )
    nominal_controls = [row for row in summary["controls"] if row["scenario_id"] == "nominal"]
    assert len(nominal_controls) == 4
    assert sorted(row["ceramic_vol_percent"] for row in nominal_controls) == [0, 10, 10, 10]
    assert all(
        sum(value > 0 for value in _fractions(row, small_inputs)[1:]) <= 1
        for row in nominal_controls
    )


def test_scenario_scaling_monotonicity_and_input_isolation(screen_module, small_inputs):
    original = copy.deepcopy(small_inputs)
    rows, _, _ = screen_module.screen_candidates(small_inputs)
    assert small_inputs == original
    lookup = _row_map(rows)
    for candidate_id in {row["candidate_id"] for row in rows}:
        nominal = lookup[candidate_id, "nominal"]
        high = lookup[candidate_id, "source_high_moduli"]
        softer = lookup[candidate_id, "matrix_5pct_softer"]
        conductivity = lookup[candidate_id, "conductivity_10pct_lower"]
        density = lookup[candidate_id, "density_2pct_higher"]
        cte = lookup[candidate_id, "cte_proxies_10pct_higher"]
        for endpoint in ("voigt", "reuss"):
            assert high[f"young_modulus_{endpoint}_GPa"] >= nominal[f"young_modulus_{endpoint}_GPa"]
            assert (
                softer[f"young_modulus_{endpoint}_GPa"] < nominal[f"young_modulus_{endpoint}_GPa"]
            )
            assert conductivity[f"conductivity_{endpoint}_W_m_K"] == pytest.approx(
                0.9 * nominal[f"conductivity_{endpoint}_W_m_K"], rel=2e-13
            )
        assert density["density_kg_m3"] == pytest.approx(1.02 * nominal["density_kg_m3"], rel=2e-13)
        assert density["specific_modulus_reuss_GPa_per_g_cm3"] == pytest.approx(
            nominal["specific_modulus_reuss_GPa_per_g_cm3"] / 1.02, rel=2e-13
        )
        for key in ("cte_volume_average_per_K", "cte_turner_per_K", "cte_max_proxy_per_K"):
            assert cte[key] == pytest.approx(1.1 * nominal[key], rel=2e-13)
    reordered = copy.deepcopy(small_inputs)
    reordered["scenarios"].reverse()
    reordered_rows, _, _ = screen_module.screen_candidates(reordered)
    assert _row_map(reordered_rows) == lookup


def test_reproducible_records_preserve_validated_inputs_and_hashes(screen_module, small_inputs):
    _loosen_gates(small_inputs)
    first = screen_module.screen_candidates(small_inputs, input_sha256="a" * 64)
    second = screen_module.screen_candidates(small_inputs, input_sha256="a" * 64)
    assert first[:2] == second[:2]
    assert _without_execution_timestamps(first[2]) == _without_execution_timestamps(second[2])
    _, summary, records = first
    assert summary["inputs_sha256"] == records["inputs_sha256"] == "a" * 64
    assert summary["input_hash_basis"] == "exact input file bytes"
    groups = [
        *records["setup"],
        *records["selected_and_control_replays"],
        records["ideal_recipe"],
        records["illustrative_thermal_expansion"],
    ]
    for group in groups:
        for request, response in zip(group["requests"], group["responses"], strict=True):
            ToolResponse.model_validate(response)
            assert response["status"] == "ok"
            assert response["tool"] == request["tool"]
            assert response["tool_version"] == request["tool_version"] == "1"
            provenance = response["provenance"]
            assert datetime.fromisoformat(provenance["created_at"]).tzinfo is not None
            expected_hash = hashlib.sha256(
                json.dumps(
                    request["input"], sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            ).hexdigest()
            assert provenance["input_sha256"] == expected_hash
            assert provenance["software_versions"]
            assert provenance["references"]
    thermal = records["illustrative_thermal_expansion"]
    nominated_row = summary["nominated_candidate"]["nominal"]
    oracle = _physical_oracle(small_inputs["constituents"], _fractions(nominated_row, small_inputs))
    for response, alpha in zip(
        thermal["responses"], (oracle["cte_volume"], oracle["cte_turner"]), strict=True
    ):
        assert response["result"]["delta_length_m"] == pytest.approx(0.1 * 25.0 * alpha, rel=2e-13)
        assert response["result"]["final_length_m"] == pytest.approx(
            0.1 * (1.0 + 25.0 * alpha), rel=2e-13
        )


@pytest.mark.parametrize(
    "invalid_json",
    [
        '{"experiment_version":"1","experiment_version":"1"}',
        '{"experiment_version":"1","value":NaN}',
        '{"experiment_version":"1","value":Infinity}',
        '{"experiment_version":"1","value":-Infinity}',
    ],
)
def test_load_inputs_rejects_ambiguous_or_nonfinite_json(screen_module, tmp_path, invalid_json):
    path = tmp_path / "inputs.json"
    path.write_text(invalid_json, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate|Nonfinite"):
        screen_module.load_inputs(path)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("screen", "grid_step_vol_percent", True),
        ("screen", "grid_step_vol_percent", 3),
        ("screen", "min_ceramic_vol_percent", 11),
        ("screen", "density_max_kg_m3", float("nan")),
        ("phase", "poisson_ratio", 0.5),
        ("phase", "density_kg_m3", 0),
        ("phase", "young_modulus_GPa", -1),
        ("phase", "conductivity_W_m_K", 0),
    ],
)
def test_invalid_physical_inputs_fail_before_screening(
    screen_module, small_inputs, monkeypatch, section, key, value
):
    target = small_inputs["screen"] if section == "screen" else small_inputs["constituents"][0]
    target[key] = value

    def no_scientific_work(*args, **kwargs):
        pytest.fail("Invalid study inputs reached a scientific calculation")

    monkeypatch.setattr(screen_module, "run_batch", no_scientific_work)
    monkeypatch.setattr(screen_module, "run_tool", no_scientific_work)
    with pytest.raises(ValueError):
        screen_module.screen_candidates(small_inputs)


def test_evaluation_budget_rejected_before_work(screen_module, small_inputs, monkeypatch):
    small_inputs["screen"].update(
        grid_step_vol_percent=1, min_ceramic_vol_percent=0, max_ceramic_vol_percent=100
    )

    def no_scientific_work(*args, **kwargs):
        pytest.fail("An oversized grid reached a scientific calculation")

    monkeypatch.setattr(screen_module, "run_batch", no_scientific_work)
    monkeypatch.setattr(screen_module, "run_tool", no_scientific_work)
    with pytest.raises(ValueError, match="bounded grid/evaluation limit"):
        screen_module.screen_candidates(small_inputs)


@pytest.fixture
def generated_results(screen_module, small_inputs, tmp_path):
    _loosen_gates(small_inputs)
    inputs_path = tmp_path / "inputs.json"
    input_bytes = (json.dumps(small_inputs, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    inputs_path.write_bytes(input_bytes)
    output_dir = tmp_path / "results"
    summary = screen_module.write_results(inputs_path, output_dir)
    return inputs_path, input_bytes, output_dir, summary


def test_artifacts_are_complete_and_byte_reproducible(screen_module, generated_results):
    inputs_path, input_bytes, output_dir, summary = generated_results
    assert summary["inputs_sha256"] == hashlib.sha256(input_bytes).hexdigest()
    assert summary["input_hash_basis"] == "exact input file bytes"
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == summary
    with (output_dir / "candidates.csv").open(newline="", encoding="utf-8") as stream:
        nominal_rows = list(csv.DictReader(stream))
    assert len(nominal_rows) == summary["candidate_count"] == 3
    assert {row["scenario_id"] for row in nominal_rows} == {"nominal"}
    scenario_artifacts = list(output_dir.glob("*.csv.gz"))
    assert len(scenario_artifacts) == 1
    with gzip.open(scenario_artifacts[0], mode="rt", newline="", encoding="utf-8") as stream:
        scenario_rows = list(csv.DictReader(stream))
    assert len(scenario_rows) == summary["evaluation_count"] == 21
    assert len({(row["candidate_id"], row["scenario_id"]) for row in scenario_rows}) == 21
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    screen_module.write_results(inputs_path, output_dir)
    after = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert {name: value for name, value in after.items() if name != "tool-records.json"} == {
        name: value for name, value in before.items() if name != "tool-records.json"
    }
    assert _without_execution_timestamps(json.loads(after["tool-records.json"])) == (
        _without_execution_timestamps(json.loads(before["tool-records.json"]))
    )
    assert screen_module.write_results(inputs_path, output_dir, check=True) == summary
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == after


@pytest.mark.parametrize(
    "corruption", ["missing", "modified_csv", "modified_science", "missing_timestamp"]
)
def test_readonly_check_rejects_artifact_drift(screen_module, generated_results, corruption):
    inputs_path, _, output_dir, _ = generated_results
    if corruption == "missing":
        (output_dir / "summary.json").unlink()
    elif corruption == "modified_csv":
        with (output_dir / "candidates.csv").open("a", encoding="utf-8") as stream:
            stream.write("unexpected row\n")
    else:
        path = output_dir / "tool-records.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        response = records["setup"][0]["responses"][0]
        if corruption == "missing_timestamp":
            del response["provenance"]["created_at"]
        else:
            response["result"]["molar_mass_g_mol"] += 1.0
        path.write_text(json.dumps(records), encoding="utf-8")
    corrupted = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    with pytest.raises(ValueError, match="Missing or stale experiment artifacts"):
        screen_module.write_results(inputs_path, output_dir, check=True)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == corrupted


def test_readonly_check_preserves_recorded_runtime_provenance(screen_module, generated_results):
    inputs_path, _, output_dir, _ = generated_results
    path = output_dir / "tool-records.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    provenance = records["setup"][0]["responses"][0]["provenance"]
    provenance["python_version"] = "different recorded runtime"
    provenance["software_versions"] = {"materials-agent-toolkit": "recorded version"}
    path.write_text(json.dumps(records), encoding="utf-8")
    before = {artifact.name: artifact.read_bytes() for artifact in output_dir.iterdir()}
    screen_module.write_results(inputs_path, output_dir, check=True)
    assert {artifact.name: artifact.read_bytes() for artifact in output_dir.iterdir()} == before
