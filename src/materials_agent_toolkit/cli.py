"""JSON-only stdout for predictable invocation by agents."""

import argparse
import json
import sys

from materials_agent_toolkit.registry import (
    ToolRequest,
    describe_tool,
    error_response,
    list_tools,
    run_request,
    validate_input,
)


def _decode_request(text: str) -> dict:
    def reject_constant(value: str):
        raise ValueError(f"Nonstandard JSON constant: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent-callable materials calculations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Discover tools and their JSON schemas")
    describe = commands.add_parser("describe", help="Describe a single tool")
    describe.add_argument("tool")
    for command in ("run", "validate"):
        child = commands.add_parser(command)
        child.add_argument("--request", help="JSON request; default: read from stdin")
    args = parser.parse_args()
    try:
        if args.command == "list":
            payload = {"tools": list_tools()}
        elif args.command == "describe":
            payload = describe_tool(args.tool)
        else:
            raw = args.request if args.request is not None else sys.stdin.read()
            request = _decode_request(raw)
            if args.command == "run":
                response = run_request(request)
                print(response.model_dump_json())
                return 0 if response.status == "ok" else 2
            validated = ToolRequest.model_validate(request)
            descriptor = describe_tool(validated.tool)
            if validated.tool_version not in (None, descriptor["version"]):
                raise ValueError(f"Supported version is {descriptor['version']}")
            payload = {
                "status": "ok",
                "tool": validated.tool,
                "tool_version": descriptor["version"],
                "input": validate_input(validated.tool, validated.input),
            }
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
        return 0
    except (ValueError, TypeError, RecursionError) as exc:
        print(error_response("INVALID_REQUEST", str(exc)).model_dump_json())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
