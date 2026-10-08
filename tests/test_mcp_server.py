"""MCP discovery and registry-adapter contracts without a live transport."""

import asyncio
import builtins
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from materials_agent_toolkit import mcp_server, registry
from materials_agent_toolkit.catalog import catalog_json, get_catalog

types = pytest.importorskip("mcp.types")
SCREENING_INPUT = {
    "candidates": [
        {
            "candidate_id": "supplied_measurement",
            "properties": {
                "thickness": {
                    "quantity": "length",
                    "value": 2,
                    "unit": "mm",
                    "evidence_kind": "measurement",
                    "source": {"citation": "Synthetic supplied data; not measured material."},
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
}


@pytest.fixture
def server():
    return mcp_server.build_server()


def invoke(server, request):
    return asyncio.run(server.request_handlers[type(request)](request)).root


def test_tools_preserve_raw_schemas_and_publish_complete_response_contract(server):
    result = invoke(server, types.ListToolsRequest())
    descriptors = registry.list_tools()
    assert [tool.name for tool in result.tools] == [item["name"] for item in descriptors]
    assert "structure.analyze_cif" in {tool.name for tool in result.tools}
    for tool, descriptor in zip(result.tools, descriptors, strict=True):
        assert tool.inputSchema == descriptor["input_schema"]
        assert tool.inputSchema["additionalProperties"] is False
        assert tool.outputSchema == registry.ToolResponse.model_json_schema()
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator.check_schema(tool.outputSchema)
        assert tool.description.startswith(descriptor["description"])
        assert f"Tool version: {descriptor['version']}" in tool.description
        assert all(value in tool.description for value in descriptor["assumptions"])
        assert all(value in tool.description for value in descriptor["references"])
        assert tool.meta["tool_version"] == descriptor["version"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False


@pytest.mark.parametrize(
    "name,arguments,error_code",
    [
        ("composition.analyze", {"formula": "Al2O3"}, None),
        ("composition.analyze", {"formula": "H2O", "unexpected": 1}, "INVALID_INPUT"),
        ("composition.analyze", {}, "INVALID_INPUT"),
        ("composition.analyze", {"formula": "DoesNotExist"}, "DOMAIN_ERROR"),
        (
            "mechanics.isotropic_moduli",
            {"young_modulus": "210", "poisson_ratio": 0.3},
            "INVALID_INPUT",
        ),
        ("structure.analyze_cif", {"cif_text": 123}, "INVALID_INPUT"),
        ("screening.evaluate", SCREENING_INPUT, None),
        ("screening.evaluate", {"candidates": [], "constraints": []}, "INVALID_INPUT"),
        ("unknown.tool", {}, "UNKNOWN_TOOL"),
    ],
)
def test_calls_delegate_to_registry_and_keep_errors_structured(
    server, monkeypatch, name, arguments, error_code
):
    response = registry.run_tool(name, arguments)
    calls = []

    def run_tool(actual_name, actual_arguments):
        calls.append((actual_name, actual_arguments))
        return response

    monkeypatch.setattr(registry, "run_tool", run_tool)
    result = invoke(
        server,
        types.CallToolRequest(params=types.CallToolRequestParams(name=name, arguments=arguments)),
    )
    assert calls == [(name, arguments)]
    assert result.structuredContent == response.model_dump(mode="json")
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert json.loads(result.content[0].text) == result.structuredContent
    assert result.isError is (error_code is not None)
    if error_code is not None:
        assert result.structuredContent["error"]["code"] == error_code
    else:
        assert result.structuredContent["provenance"]["input_sha256"]
    Draft202012Validator(registry.ToolResponse.model_json_schema()).validate(
        result.structuredContent
    )


def test_registry_internal_failures_use_the_same_envelope(server, monkeypatch):
    response = registry.error_response(
        "INTERNAL_ERROR", "Unexpected tool failure", tool="composition.analyze"
    )
    monkeypatch.setattr(registry, "run_tool", lambda name, arguments: response)
    result = invoke(
        server,
        types.CallToolRequest(
            params=types.CallToolRequestParams(
                name="composition.analyze", arguments={"formula": "H2O"}
            )
        ),
    )
    assert result.isError is True
    assert result.structuredContent == response.model_dump(mode="json")
    assert json.loads(result.content[0].text) == result.structuredContent


def test_cif_missing_extra_preserves_discovery_and_adapter_recovery(server, monkeypatch):
    original_import = builtins.__import__

    def without_ase(name, *args, **kwargs):
        if name == "ase" or name.startswith("ase."):
            raise ModuleNotFoundError("ASE unavailable", name=name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_ase)
    tools = invoke(server, types.ListToolsRequest()).tools
    descriptor = next(tool for tool in tools if tool.name == "structure.analyze_cif")
    cif_text = (Path(__file__).parent / "fixtures" / "structures" / "al_fcc.cif").read_text(
        encoding="utf-8"
    )
    result = invoke(
        server,
        types.CallToolRequest(
            params=types.CallToolRequestParams(
                name="structure.analyze_cif", arguments={"cif_text": cif_text}
            )
        ),
    )
    assert result.isError is True
    envelope = result.structuredContent
    assert envelope["error"]["code"] == "MISSING_DEPENDENCY"
    assert "materials-agent-toolkit[structures]" in envelope["error"]["message"]
    assert envelope["provenance"]["input_sha256"]
    assert envelope["result"] is None
    assert json.loads(result.content[0].text) == envelope
    Draft202012Validator(descriptor.outputSchema).validate(envelope)
    recovered = invoke(
        server,
        types.CallToolRequest(
            params=types.CallToolRequestParams(
                name="composition.analyze", arguments={"formula": "H2O"}
            )
        ),
    )
    assert recovered.isError is False
    assert recovered.structuredContent["status"] == "ok"


def test_resources_are_versioned_complete_json_catalog_and_response_schema(server):
    resources = invoke(server, types.ListResourcesRequest()).resources
    assert [str(resource.uri) for resource in resources] == [
        mcp_server.CATALOG_URI,
        mcp_server.RESPONSE_SCHEMA_URI,
    ]
    assert all(resource.mimeType == "application/json" for resource in resources)
    contents = []
    for resource in resources:
        result = invoke(
            server,
            types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri=resource.uri)),
        )
        assert len(result.contents) == 1
        assert result.contents[0].mimeType == "application/json"
        assert result.contents[0].uri == resource.uri
        if str(resource.uri) == mcp_server.CATALOG_URI:
            assert result.contents[0].text == catalog_json()
        contents.append(json.loads(result.contents[0].text))
    assert contents[0] == get_catalog()
    assert contents[0] == {
        "catalog_version": "1",
        "tools": registry.list_tools(),
        "response_schema": registry.ToolResponse.model_json_schema(),
    }
    assert contents[1] == contents[0]["response_schema"]


@pytest.mark.parametrize(
    "uri",
    [
        "materials://unknown",
        "materials://catalog?path=/etc/passwd",
        "file:///etc/passwd",
        "https://example.com/catalog",
    ],
)
def test_unsupported_resource_uris_are_rejected_without_content(server, uri):
    request = types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri=uri))
    with pytest.raises(ValueError, match="^Unsupported materials resource URI$"):
        invoke(server, request)


def test_missing_optional_sdk_gives_install_guidance_on_stderr_only(monkeypatch, capsys):
    original_import = builtins.__import__

    def without_mcp(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("MCP unavailable", name=name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_mcp)
    with pytest.raises(ImportError, match=r"materials-agent-toolkit\[mcp\]"):
        mcp_server.build_server()
    assert mcp_server.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "python -m pip install 'materials-agent-toolkit[mcp]'" in captured.err
    assert registry.run_tool("composition.analyze", {"formula": "H2O"}).status == "ok"
