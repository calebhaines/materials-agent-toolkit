"""Batch CLI contracts, scientific parity and strict JSON transport failures."""

import io
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit import cli, registry


def invoke(command, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "materials_agent_toolkit", *command],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_json_response(process, exit_code):
    assert process.returncode == exit_code, process.stderr
    assert process.stderr == ""
    response = json.loads(process.stdout)
    assert process.stdout.count("\n") == 1
    Draft202012Validator(registry.describe_batch()["response_schema"]).validate(response)
    return response


def without_timestamps(response):
    response = deepcopy(response)
    response["provenance"].pop("created_at")
    for item in response["responses"]:
        item["provenance"].pop("created_at")
    return response


def composition(formula):
    return {"tool": "composition.analyze", "input": {"formula": formula}}


@pytest.mark.parametrize("source", ["stdin", "argument"])
def test_screening_batch_preserves_unknown_outcomes_and_cli_python_parity(source):
    screening = {
        "tool": "screening.evaluate",
        "input": {
            "candidates": [
                {
                    "candidate_id": "supplied_measurement",
                    "properties": {
                        "thickness": {
                            "quantity": "length",
                            "value": 2,
                            "unit": "mm",
                            "evidence_kind": "measurement",
                            "source": {
                                "citation": "Synthetic supplied data; not measured material."
                            },
                            "conditions": {"temperature": "25 degC"},
                        }
                    },
                },
                {"candidate_id": "missing_data", "properties": {}},
            ],
            "constraints": [
                {
                    "constraint_id": "thin_sheet",
                    "property_id": "thickness",
                    "quantity": "length",
                    "unit": "cm",
                    "maximum": 0.3,
                    "required_conditions": {"temperature": "25 degC"},
                }
            ],
        },
    }
    request = {"requests": [screening, composition("H2O")]}
    encoded = json.dumps(request)
    process = (
        invoke(["batch"], encoded)
        if source == "stdin"
        else invoke(["batch", "--request", encoded], "invalid unused stdin")
    )
    response = assert_json_response(process, 0)
    assert response["status"] == "ok"
    assert response["summary"] == {"total": 2, "succeeded": 2, "failed": 0}
    assert [item["tool"] for item in response["responses"]] == [
        "screening.evaluate",
        "composition.analyze",
    ]
    result = response["responses"][0]["result"]
    assert result["summary"] == {"total": 2, "passed": 1, "failed": 0, "unknown": 1}
    assert [candidate["status"] for candidate in result["candidates"]] == ["pass", "unknown"]
    measured, missing = result["candidates"]
    assert measured["properties"]["thickness"]["normalized_value"] == pytest.approx(0.002)
    assert measured["properties"]["thickness"]["si_unit"] == "m"
    assert result["normalized_constraints"][0]["normalized_maximum"] == pytest.approx(0.003)
    assert missing["checks"][0]["reason"] == "missing_property"
    assert missing["properties"] == {}
    assert without_timestamps(response) == without_timestamps(
        registry.run_batch(request).model_dump(mode="json")
    )


@pytest.mark.parametrize("source", ["stdin", "argument"])
def test_mixed_batch_preserves_order_and_cli_python_parity(source):
    request = {
        "batch_version": "1",
        "requests": [
            {
                "tool": "composition.from_fractions",
                "input": {"fractions": {"Ni": 0.5, "Ti": 0.5}, "basis": "atomic"},
            },
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": -210, "poisson_ratio": 0.3},
            },
            "malformed item",
            {"tool": "missing", "input": {}},
            composition("H2O"),
        ],
    }
    encoded = json.dumps(request)
    process = (
        invoke(["batch"], encoded)
        if source == "stdin"
        else invoke(["batch", "--request", encoded], "invalid unused stdin")
    )
    response = assert_json_response(process, 2)
    assert response["status"] == "partial"
    assert response["error"] is None
    assert response["summary"] == {"total": 5, "succeeded": 2, "failed": 3}
    assert [item["status"] for item in response["responses"]] == [
        "ok",
        "error",
        "error",
        "error",
        "ok",
    ]
    assert [item["error"]["code"] for item in response["responses"][1:4]] == [
        "INVALID_INPUT",
        "INVALID_REQUEST",
        "UNKNOWN_TOOL",
    ]
    assert response["responses"][0]["result"]["atomic_fractions"] == {"Ni": 0.5, "Ti": 0.5}
    assert response["responses"][-1]["result"]["atomic_counts"] == {"H": 2, "O": 1}
    assert without_timestamps(response) == without_timestamps(
        registry.run_batch(request).model_dump(mode="json")
    )


@pytest.mark.parametrize(
    "requests,status,exit_code,successes",
    [
        ([composition("H2O"), composition("CO2")], "ok", 0, 2),
        ([{}, {"tool": "missing", "input": {}}], "error", 2, 0),
    ],
)
def test_batch_exit_code_tracks_complete_success(requests, status, exit_code, successes):
    response = assert_json_response(
        invoke(["batch"], json.dumps({"requests": requests})), exit_code
    )
    assert response["status"] == status
    assert response["batch_version"] == "1"
    assert response["error"] is None
    assert response["summary"] == {
        "total": len(requests),
        "succeeded": successes,
        "failed": len(requests) - successes,
    }
    assert len(response["responses"]) == len(requests)


@pytest.mark.parametrize(
    "encoded",
    [
        "not json",
        "",
        '{"requests":[],"requests":[]}',
        '{"requests":[{"tool":"composition.analyze","input":{"formula":"H2O","formula":"CO2"}}]}',
        '{"requests":[{"tool":"mechanics.isotropic_moduli","input":{"young_modulus":NaN,"poisson_ratio":0.3}}]}',
        '{"requests":[{"tool":"mechanics.isotropic_moduli","input":{"young_modulus":Infinity,"poisson_ratio":0.3}}]}',
        '{"requests":[{"tool":"mechanics.isotropic_moduli","input":{"young_modulus":-Infinity,"poisson_ratio":0.3}}]}',
    ],
)
def test_strict_json_failures_return_batch_errors_without_invoking_batch(
    encoded, monkeypatch, capsys
):
    def unexpected_batch(request):
        pytest.fail("Malformed JSON must not enter batch execution")

    monkeypatch.setattr(cli, "run_batch", unexpected_batch)
    monkeypatch.setattr(sys, "argv", ["matkit", "batch"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(encoded))
    assert cli.main() == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    response = json.loads(captured.out)
    Draft202012Validator(registry.describe_batch()["response_schema"]).validate(response)
    assert response["batch_version"] == "1"
    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_BATCH"
    assert response["responses"] == []
    assert response["summary"] == {"total": 0, "succeeded": 0, "failed": 0}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"requests": []},
        {"requests": "not a list"},
        {"requests": [composition("H2O")] * 101},
        {"requests": [composition("H2O")], "batch_version": "2"},
        {"requests": [composition("H2O")], "unrecognized": True},
    ],
)
def test_invalid_batch_envelopes_execute_no_items(payload, monkeypatch, capsys):
    executed = []

    def track_item(item):
        executed.append(item)
        pytest.fail("An invalid batch envelope must not execute any item")

    monkeypatch.setattr(registry, "run_request", track_item)
    monkeypatch.setattr(sys, "argv", ["matkit", "batch", "--request", json.dumps(payload)])
    assert cli.main() == 2
    assert executed == []
    captured = capsys.readouterr()
    assert captured.err == ""
    response = json.loads(captured.out)
    Draft202012Validator(registry.describe_batch()["response_schema"]).validate(response)
    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_BATCH"
    assert response["responses"] == []
    assert response["summary"] == {"total": 0, "succeeded": 0, "failed": 0}


def test_batch_schema_discovery_matches_python_and_describes_item_requests():
    process = invoke(["batch-schema"])
    assert process.returncode == 0
    assert process.stderr == ""
    descriptor = json.loads(process.stdout)
    assert descriptor == registry.describe_batch()
    assert descriptor["batch_version"] == "1"
    assert descriptor["max_batch_size"] == 100
    assert descriptor["execution"] == "sequential"
    for name in ("request_schema", "response_schema", "item_request_schema"):
        Draft202012Validator.check_schema(descriptor[name])
    validator = Draft202012Validator(descriptor["request_schema"])
    validator.validate({"requests": [composition("H2O"), "malformed item"]})
    assert not validator.is_valid({"requests": []})
    assert not validator.is_valid({"requests": [composition("H2O")] * 101})
    Draft202012Validator(descriptor["item_request_schema"]).validate(composition("H2O"))
    assert not Draft202012Validator(descriptor["item_request_schema"]).is_valid("malformed item")


def test_documented_mixed_batch_example_is_executable():
    example = Path(__file__).parents[1] / "examples" / "batch" / "mixed.json"
    response = assert_json_response(invoke(["batch"], example.read_text()), 2)
    assert response["status"] == "partial"
    assert response["error"] is None
    assert response["summary"] == {"total": 3, "succeeded": 2, "failed": 1}
    assert [item["tool"] for item in response["responses"]] == [
        "composition.from_fractions",
        "missing.tool",
        "composition.analyze",
    ]
    assert [item["status"] for item in response["responses"]] == ["ok", "error", "ok"]


def test_existing_single_request_cli_contract_is_preserved():
    request = json.dumps(composition("H2O"))
    for command in ("run", "validate"):
        process = invoke([command], request)
        assert process.returncode == 0
        assert process.stderr == ""
        response = json.loads(process.stdout)
        assert response["status"] == "ok"
        assert response["tool"] == "composition.analyze"
        assert "batch_version" not in response
        assert "responses" not in response
    process = invoke(["run"], "not json")
    assert process.returncode == 2
    assert process.stderr == ""
    response = json.loads(process.stdout)
    assert response["error"]["code"] == "INVALID_REQUEST"
    assert "batch_version" not in response
    process = invoke(["list"])
    assert process.returncode == 0
    assert process.stderr == ""
    assert len(json.loads(process.stdout)["tools"]) == 10
