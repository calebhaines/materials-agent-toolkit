"""Generate or verify the committed catalog artifacts without executing calculations."""

import argparse
import sys
from pathlib import Path

from materials_agent_toolkit.catalog import catalog_json, catalog_schema_json


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Reject missing or stale artifacts")
    args = parser.parse_args(argv)
    repository = root if root is not None else Path(__file__).resolve().parents[1]
    artifacts = (
        (repository / "catalog" / "tool-catalog.json", catalog_json().encode("utf-8")),
        (
            repository / "catalog" / "tool-catalog.schema.json",
            catalog_schema_json().encode("utf-8"),
        ),
    )
    failures = []
    for path, expected in artifacts:
        if args.check:
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                failures.append(f"Missing catalog artifact: {path}")
            except OSError as exc:
                failures.append(f"Cannot read catalog artifact {path}: {exc}")
            else:
                if actual != expected:
                    failures.append(f"Stale catalog artifact: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(
            "Regenerate from the repository root: "
            "uv run --no-sync python scripts/export_catalog.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
