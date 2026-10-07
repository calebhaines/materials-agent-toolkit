"""Bounded batch contracts preserve scientific results and isolate item failures.

H2O and equiatomic NiTi reference masses use conventional CIAAW atomic weights
(H 1.008, O 15.999, Ni 58.6934, Ti 47.867 g/mol). Elastic references use the
analytical isotropic relations G = E/[2(1+nu)] and K = E/[3(1-2nu)]. These
checks verify that batching does not change the calculations' conventions.
"""

import hashlib
import json
import math
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit import registry
from materials_agent_toolkit.registry import (
    BATCH_VERSION,
    MAX_BATCH_SIZE,
    BatchRequest,
    BatchResponse,
    ToolRequest,
    ToolResponse,
    describe_batch,
    run_batch,
    validate_input,
)

WATER = {"tool": "composition.analyze", "input": {"formula": "H2O"}}
NITI = {
    "tool": "composition.from_fractions",
    "input": {"fractions": {"Ni": 0.5, "Ti": 0.5}, "basis": "atomic"},
}
MODULI = {
    "tool": "mechanics.isotropic_moduli",
    "input": {"young_modulus": 210.0, "poisson_ratio": 0.3},
}


def require_serializable_contract(response):
    """Require strict finite JSON, then validate its advertised response schema."""
    envelope = response.model_dump(mode="json")
    serialized = json.dumps(envelope, allow_nan=False)
    assert json.loads(response.model_dump_json()) == envelope
    Draft202012Validator(describe_batch()["response_schema"]).validate(envelope)
    for item in envelope["responses"]:
        Draft202012Validator(ToolResponse.model_json_schema()).validate(item)
    assert response.provenance.input_sha256 is None
    assert response.provenance.created_at
    assert response.provenance.software_versions["pydantic"] != "not-installed"
    return serialized


def test_heterogeneous_batch_preserves_independent_scientific_references_and_hashes():
    requests = [WATER, NITI, MODULI]
    response = run_batch({"requests": requests})
    assert response.batch_version == "1"
    assert response.status == "ok"
    assert response.error is None
    assert response.summary.model_dump() == {"total": 3, "succeeded": 3, "failed": 0}
    assert [item.tool for item in response.responses] == [item["tool"] for item in requests]
    water, niti, moduli = [item.result for item in response.responses]
    assert water["molar_mass_g_mol"] == pytest.approx(18.015, rel=1e-12)
    assert water["atomic_fractions"] == pytest.approx({"H": 2 / 3, "O": 1 / 3})
    assert niti["mean_atomic_mass_g_mol"] == pytest.approx(53.2802, rel=1e-12)
    assert niti["mass_fractions"] == pytest.approx(
        {"Ni": 0.5507993588612655, "Ti": 0.4492006411387345}, rel=1e-12
    )
    assert moduli["shear_modulus"] == pytest.approx(80.76923076923077, rel=1e-12)
    assert moduli["bulk_modulus"] == pytest.approx(175.0, rel=1e-12)
    assert moduli["stress_unit"] == "GPa"
    for request, item in zip(requests, response.responses):
        normalized = validate_input(request["tool"], request["input"])
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert item.provenance.input_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
        assert item.provenance.references
        assert "not-installed" not in item.provenance.software_versions.values()
    require_serializable_contract(response)


def test_batch_discovery_distinguishes_outer_and_item_schemas():
    descriptor = describe_batch()
    assert BATCH_VERSION == descriptor["batch_version"] == "1"
    assert MAX_BATCH_SIZE == descriptor["max_batch_size"] == 100
    assert descriptor["execution"] == "sequential"
    for key in ("request_schema", "response_schema", "item_request_schema"):
        Draft202012Validator.check_schema(descriptor[key])
    assert descriptor["request_schema"] == BatchRequest.model_json_schema()
    assert descriptor["response_schema"] == BatchResponse.model_json_schema()
    assert descriptor["item_request_schema"] == ToolRequest.model_json_schema()
    request_schema = descriptor["request_schema"]
    assert request_schema["additionalProperties"] is False
    assert request_schema["properties"]["requests"]["minItems"] == 1
    assert request_schema["properties"]["requests"]["maxItems"] == 100
    # Malformed individual calls are allowed through the envelope for isolation.
    payload = {"requests": [WATER, None, {}, MODULI]}
    Draft202012Validator(request_schema).validate(payload)
    assert not Draft202012Validator(descriptor["item_request_schema"]).is_valid(None)
    assert not Draft202012Validator(descriptor["item_request_schema"]).is_valid({})
    Draft202012Validator(descriptor["item_request_schema"]).validate(WATER)


@pytest.mark.parametrize("count", [1, 100])
def test_batch_accepts_size_boundaries_and_executes_every_item(count, monkeypatch):
    original = registry.run_request
    calls = []

    def record(request):
        calls.append(request)
        return original(request)

    monkeypatch.setattr(registry, "run_request", record)
    response = run_batch({"batch_version": "1", "requests": [WATER] * count})
    assert calls == [WATER] * count
    assert response.status == "ok"
    assert response.summary.model_dump() == {"total": count, "succeeded": count, "failed": 0}
    assert len(response.responses) == count
    assert all(
        item.result["molar_mass_g_mol"] == pytest.approx(18.015) for item in response.responses
    )
    require_serializable_contract(response)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"requests": None},
        {"requests": WATER},
        {"requests": ()},
        {"requests": []},
        {"requests": [WATER] * 101},
        {"requests": [WATER], "unknown": True},
        {"batch_version": "2", "requests": [WATER]},
        {"batch_version": 1, "requests": [WATER]},
        {"batch_version": True, "requests": [WATER]},
        {"batch_version": None, "requests": [WATER]},
    ],
)
def test_invalid_outer_envelope_executes_nothing(payload, monkeypatch):
    def forbidden(request):
        pytest.fail("A structurally invalid batch executed an item")

    monkeypatch.setattr(registry, "run_request", forbidden)
    response = run_batch(payload)
    assert response.status == "error"
    assert response.error.code == "INVALID_BATCH"
    assert response.responses == []
    assert response.summary.model_dump() == {"total": 0, "succeeded": 0, "failed": 0}
    require_serializable_contract(response)


@pytest.mark.parametrize(
    "malformed",
    [
        None,
        [],
        {},
        1,
        "composition.analyze",
        {"tool": "composition.analyze"},
        {"tool": 7, "input": {}},
        {"tool": "composition.analyze", "input": []},
        {"tool": "composition.analyze", "input": {}, "unknown": 1},
        {"tool": "composition.analyze", "input": {}, "tool_version": 1},
    ],
)
def test_malformed_middle_item_is_isolated_and_following_science_succeeds(malformed):
    response = run_batch({"requests": [WATER, malformed, NITI]})
    assert response.status == "partial"
    assert response.error is None
    assert response.summary.model_dump() == {"total": 3, "succeeded": 2, "failed": 1}
    first, failed, last = response.responses
    assert first.result["molar_mass_g_mol"] == pytest.approx(18.015)
    assert failed.status == "error"
    assert failed.error.code == "INVALID_REQUEST"
    assert failed.result is None
    assert last.result["mean_atomic_mass_g_mol"] == pytest.approx(53.2802)
    require_serializable_contract(response)


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"tool": "missing", "input": {}}, "UNKNOWN_TOOL"),
        ({**WATER, "tool_version": "2"}, "UNSUPPORTED_VERSION"),
        ({"tool": WATER["tool"], "input": {"formula": "H2O", "unknown": 1}}, "INVALID_INPUT"),
        ({"tool": WATER["tool"], "input": {"formula": "DoesNotExist"}}, "DOMAIN_ERROR"),
    ],
)
def test_existing_error_codes_are_preserved_without_stopping_later_items(payload, code):
    response = run_batch({"requests": [payload, MODULI]})
    assert response.status == "partial"
    assert response.error is None
    assert response.responses[0].error.code == code
    assert response.responses[0].result is None
    assert response.responses[1].result["bulk_modulus"] == pytest.approx(175)
    assert response.summary.model_dump() == {"total": 2, "succeeded": 1, "failed": 1}
    require_serializable_contract(response)


def test_all_item_errors_remain_distinct_from_invalid_batch():
    response = run_batch({"requests": [None, {"tool": "missing", "input": {}}]})
    assert response.status == "error"
    assert response.error is None
    assert [item.error.code for item in response.responses] == ["INVALID_REQUEST", "UNKNOWN_TOOL"]
    assert response.summary.model_dump() == {"total": 2, "succeeded": 0, "failed": 2}
    require_serializable_contract(response)


def test_numeric_failure_retains_tool_provenance_and_does_not_abort_batch(monkeypatch):
    specs = registry._tools()

    def numerical_failure(inputs):
        raise OverflowError("deliberate numeric range failure")

    specs[MODULI["tool"]] = replace(specs[MODULI["tool"]], execute=numerical_failure)
    monkeypatch.setattr(registry, "_tools", lambda: specs)
    response = run_batch({"requests": [MODULI, WATER]})
    failed, successful = response.responses
    assert response.status == "partial"
    assert failed.error.code == "NUMERICAL_ERROR"
    assert failed.tool == MODULI["tool"]
    assert failed.tool_version == "1"
    assert failed.provenance.input_sha256 is not None
    assert failed.provenance.references
    assert successful.result["molar_mass_g_mol"] == pytest.approx(18.015)
    require_serializable_contract(response)


def test_repeated_requests_execute_sequentially_without_deduplication_or_response_rewriting(
    monkeypatch,
):
    original = registry.run_request
    trace = []
    completed = []

    def traced(request):
        trace.append(("start", request["tool"]))
        response = original(request)
        completed.append(response)
        trace.append(("end", request["tool"]))
        return response

    monkeypatch.setattr(registry, "run_request", traced)
    requests = [MODULI, NITI, MODULI, WATER]
    response = run_batch({"requests": requests})
    assert trace == [
        event
        for request in requests
        for event in (("start", request["tool"]), ("end", request["tool"]))
    ]
    assert len(completed) == len(requests)
    assert [item.model_dump() for item in response.responses] == [
        item.model_dump() for item in completed
    ]
    assert (
        response.responses[0].provenance.input_sha256
        == response.responses[2].provenance.input_sha256
    )
    assert response.responses[0].result == response.responses[2].result
    require_serializable_contract(response)


def test_unexpected_runner_exception_is_redacted_and_later_items_continue(monkeypatch):
    original = registry.run_request
    marker = "private-diagnostic-should-never-leak"
    calls = []

    def faulty(request):
        calls.append(request)
        if request is NITI:
            raise RuntimeError(marker)
        return original(request)

    monkeypatch.setattr(registry, "run_request", faulty)
    response = run_batch({"requests": [WATER, NITI, MODULI]})
    assert calls == [WATER, NITI, MODULI]
    assert response.status == "partial"
    assert response.responses[1].error.code == "INTERNAL_ERROR"
    assert response.responses[1].result is None
    assert response.responses[2].result["bulk_modulus"] == pytest.approx(175)
    assert marker not in require_serializable_contract(response)


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_process_cancellation_is_not_swallowed(exception, monkeypatch):
    original = registry.run_request
    calls = []

    def interrupted(request):
        calls.append(request)
        if request is NITI:
            raise exception("cancel batch")
        return original(request)

    monkeypatch.setattr(registry, "run_request", interrupted)
    with pytest.raises(exception, match="cancel batch"):
        run_batch({"requests": [WATER, NITI, MODULI]})
    assert calls == [WATER, NITI]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_bad_items_produce_finite_json_errors_and_preserve_good_item(value):
    malformed = {"tool": value, "input": {}}
    invalid_input = {
        "tool": MODULI["tool"],
        "input": {"young_modulus": value, "poisson_ratio": 0.3},
    }
    response = run_batch({"requests": [value, malformed, invalid_input, WATER]})
    assert response.status == "partial"
    assert response.summary.model_dump() == {"total": 4, "succeeded": 1, "failed": 3}
    assert [item.error.code for item in response.responses[:3]] == [
        "INVALID_REQUEST",
        "INVALID_REQUEST",
        "INVALID_INPUT",
    ]
    assert response.responses[-1].result["molar_mass_g_mol"] == pytest.approx(18.015)
    require_serializable_contract(response)
