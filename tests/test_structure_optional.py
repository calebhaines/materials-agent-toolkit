"""Optional structure availability must preserve discovery and structured execution."""

import builtins
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from materials_agent_toolkit.catalog import catalog_json
from materials_agent_toolkit.registry import describe_tool, run_batch, run_tool, validate_input

FIXTURE = Path(__file__).parent / "fixtures" / "structures" / "al_fcc.cif"


@pytest.fixture
def missing_ase(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "ase" or name.startswith("ase."):
            raise ModuleNotFoundError("No module named 'ase'", name="ase")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_discovery_validation_and_catalog_do_not_require_ase(missing_ase):
    descriptor = describe_tool("structure.analyze_cif")
    assert descriptor["version"] == "1"
    assert descriptor["dependencies"] == ["ase", "numpy", "periodictable", "scipy"]
    inputs = {"cif_text": FIXTURE.read_text()}
    assert validate_input("structure.analyze_cif", inputs) == inputs
    catalog = json.loads(catalog_json())
    assert len(catalog["tools"]) == 10
    assert descriptor in catalog["tools"]


def test_missing_ase_returns_actionable_error_and_validated_input_hash(missing_ase):
    inputs = {"cif_text": FIXTURE.read_text()}
    response = run_tool("structure.analyze_cif", inputs)
    assert response.status == "error"
    assert response.result is None
    assert response.error.code == "MISSING_DEPENDENCY"
    assert "materials-agent-toolkit[structures]" in response.error.message
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert response.provenance.input_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
    assert {
        "ase",
        "scipy",
        "numpy",
        "periodictable",
    } <= response.provenance.software_versions.keys()
    assert response.provenance.references == describe_tool("structure.analyze_cif")["references"]
    json.dumps(response.model_dump(mode="json"), allow_nan=False)


def test_schema_error_precedes_optional_dependency_check(missing_ase):
    response = run_tool("structure.analyze_cif", {"cif_text": 7})
    assert response.error.code == "INVALID_INPUT"
    assert response.provenance.input_sha256 is None


def test_missing_structure_dependency_is_isolated_in_batch(missing_ase):
    response = run_batch(
        {
            "requests": [
                {"tool": "structure.analyze_cif", "input": {"cif_text": FIXTURE.read_text()}},
                {"tool": "composition.analyze", "input": {"formula": "H2O"}},
            ]
        }
    )
    assert response.status == "partial"
    assert response.summary.model_dump() == {"total": 2, "succeeded": 1, "failed": 1}
    assert response.responses[0].error.code == "MISSING_DEPENDENCY"
    assert response.responses[1].result["molar_mass_g_mol"] == pytest.approx(18.015)


@pytest.mark.parametrize("error_type", [ImportError, ModuleNotFoundError])
def test_broken_transitive_dependency_is_not_reported_as_missing_ase(monkeypatch, error_type):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "ase.io.cif":
            raise error_type("private installation detail", name="unexpected_transitive_package")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    response = run_tool("structure.analyze_cif", {"cif_text": FIXTURE.read_text()})
    assert response.status == "error"
    assert response.error.code == "INTERNAL_ERROR"
    assert "private installation detail" not in response.model_dump_json()


def test_broken_operational_scipy_import_is_an_internal_failure(monkeypatch):
    pytest.importorskip("ase", reason="Operational dependency test needs the structures extra")
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "scipy.spatial":
            raise ImportError("private operational detail", name="scipy.spatial")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    response = run_tool("structure.analyze_cif", {"cif_text": FIXTURE.read_text()})
    assert response.error.code == "INTERNAL_ERROR"
    assert "private operational detail" not in response.model_dump_json()


def test_fresh_process_discovery_does_not_import_optional_engines():
    script = """
import sys
from materials_agent_toolkit.catalog import catalog_json
from materials_agent_toolkit.registry import list_tools
assert len(list_tools()) == 10
assert 'structure.analyze_cif' in catalog_json()
for package in ('ase', 'scipy', 'matplotlib', 'mcp'):
    assert package not in sys.modules, package
"""
    process = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def test_cli_missing_extra_returns_json_without_traceback():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'ase' or name.startswith('ase.'):
        raise ModuleNotFoundError("No module named 'ase'", name='ase')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from materials_agent_toolkit.cli import main
raise SystemExit(main())
"""
    request = {"tool": "structure.analyze_cif", "input": {"cif_text": FIXTURE.read_text()}}
    process = subprocess.run(
        [sys.executable, "-c", script, "run", "--request", json.dumps(request)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2
    assert process.stderr == ""
    payload = json.loads(process.stdout)
    assert payload["error"]["code"] == "MISSING_DEPENDENCY"
    assert "[structures]" in payload["error"]["message"]
