"""Canonical CLI discovery and isolated, reproducible catalog artifact generation."""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from materials_agent_toolkit import cli
from materials_agent_toolkit.catalog import (
    catalog_json,
    catalog_schema,
    catalog_schema_json,
    get_catalog,
)

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "export_catalog.py"
ARTIFACTS = ("tool-catalog.json", "tool-catalog.schema.json")


def invoke(command: str, *, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "materials_agent_toolkit", command],
        capture_output=True,
        check=False,
        env=env,
    )


@pytest.mark.parametrize(
    "command,source,serialized",
    [
        ("catalog", get_catalog, catalog_json),
        ("catalog-schema", catalog_schema, catalog_schema_json),
    ],
)
def test_catalog_cli_matches_python_canonical_bytes(command, source, serialized):
    process = invoke(command)
    assert process.returncode == 0, process.stderr.decode()
    assert process.stderr == b""
    expected = serialized()
    assert process.stdout == expected.encode("utf-8")
    assert json.loads(process.stdout) == source()
    assert (
        expected
        == json.dumps(source(), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
    )
    assert process.stdout.endswith(b"\n")
    assert not process.stdout.endswith(b"\n\n")
    assert b"\r" not in process.stdout


@pytest.mark.parametrize("command", ["catalog", "catalog-schema"])
def test_catalog_cli_is_stable_across_fresh_processes(command):
    first = invoke(command)
    second = invoke(command)
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout


@pytest.mark.parametrize(
    "command,serialized", [("catalog", catalog_json), ("catalog-schema", catalog_schema_json)]
)
def test_catalog_cli_uses_utf8_bytes_under_legacy_stdout_encoding(command, serialized):
    process = invoke(command, env={**os.environ, "PYTHONIOENCODING": "ascii"})
    assert process.returncode == 0, process.stderr.decode("ascii")
    assert process.stderr == b""
    assert process.stdout == serialized().encode("utf-8")


@pytest.mark.parametrize(
    "command,serialized", [("catalog", catalog_json), ("catalog-schema", catalog_schema_json)]
)
def test_catalog_cli_supports_text_streams_without_a_buffer(command, serialized, monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["matkit", command])
    monkeypatch.setattr(sys, "stdout", output)
    assert cli.main() == 0
    assert output.getvalue() == serialized()


@pytest.fixture
def generator():
    spec = importlib.util.spec_from_file_location("catalog_export_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact_bytes(root):
    return {name: (root / "catalog" / name).read_bytes() for name in ARTIFACTS}


def test_generator_writes_portable_canonical_utf8_and_check_accepts(generator, tmp_path, capsys):
    assert generator.main([], root=tmp_path) == 0
    expected = {
        ARTIFACTS[0]: catalog_json().encode("utf-8"),
        ARTIFACTS[1]: catalog_schema_json().encode("utf-8"),
    }
    assert artifact_bytes(tmp_path) == expected
    for content in expected.values():
        assert content.endswith(b"\n") and not content.endswith(b"\n\n")
        assert b"\r" not in content
        json.loads(content.decode("utf-8"))
    assert generator.main(["--check"], root=tmp_path) == 0
    assert artifact_bytes(tmp_path) == expected
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_missing_check_reports_both_paths_and_creates_nothing(generator, tmp_path, capsys):
    assert generator.main(["--check"], root=tmp_path) == 1
    assert not (tmp_path / "catalog").exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    for name in ARTIFACTS:
        assert f"Missing catalog artifact: {tmp_path / 'catalog' / name}" in captured.err
    assert "uv run --no-sync python scripts/export_catalog.py" in captured.err
    assert '"catalog_version"' not in captured.err


@pytest.mark.parametrize("name", ARTIFACTS)
def test_stale_check_rejects_exact_byte_changes_without_writing(generator, tmp_path, capsys, name):
    assert generator.main([], root=tmp_path) == 0
    target = tmp_path / "catalog" / name
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    before = artifact_bytes(tmp_path)
    assert generator.main(["--check"], root=tmp_path) == 1
    assert artifact_bytes(tmp_path) == before
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"Stale catalog artifact: {target}" in captured.err
    assert "uv run --no-sync python scripts/export_catalog.py" in captured.err
    assert '"catalog_version"' not in captured.err


def test_check_missing_one_artifact_does_not_rewrite_the_other(generator, tmp_path, capsys):
    assert generator.main([], root=tmp_path) == 0
    (tmp_path / "catalog" / ARTIFACTS[0]).unlink()
    remaining = tmp_path / "catalog" / ARTIFACTS[1]
    before = remaining.read_bytes()
    assert generator.main(["--check"], root=tmp_path) == 1
    assert not (tmp_path / "catalog" / ARTIFACTS[0]).exists()
    assert remaining.read_bytes() == before
    assert "Missing catalog artifact:" in capsys.readouterr().err


def test_script_resolves_repository_from_its_own_path_in_different_cwd(tmp_path):
    copied_script = tmp_path / "temporary-repo" / "scripts" / "export_catalog.py"
    copied_script.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, copied_script)
    outside = tmp_path / "unrelated-working-directory"
    outside.mkdir()
    for args in ([], ["--check"]):
        process = subprocess.run(
            [sys.executable, str(copied_script), *args],
            cwd=outside,
            capture_output=True,
            check=False,
        )
        assert process.returncode == 0, process.stderr.decode()
        assert process.stdout == process.stderr == b""
    assert not (outside / "catalog").exists()
    assert artifact_bytes(copied_script.parents[1]) == {
        ARTIFACTS[0]: catalog_json().encode("utf-8"),
        ARTIFACTS[1]: catalog_schema_json().encode("utf-8"),
    }
