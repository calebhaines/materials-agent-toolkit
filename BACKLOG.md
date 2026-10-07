# Persistent backlog

Select one bounded item per development run. Update status and link the branch/pull request when work begins. Reprioritize based on user instructions and observed limitations.

| Priority | Task | Acceptance criteria | Status |
| --- | --- | --- | --- |
| P0 | Ship initial scientific tool foundation | Seven tools, discoverable schemas, validated envelopes, reference tests, CLI checks, dependency lock and CI | Complete; 146 tests and package build pass; see RUN_LOG.md |
| P1 | Add MCP interface | Same tools/results as registry; discoverable schemas; client example; real stdio integration test; optional dependency with base-install coverage | Complete; [PR #1](https://github.com/calebhaines/materials-agent-toolkit/pull/1) merged after independent review and passing CI |
| P1 | Add structured fractional composition input | Explicit atomic/mass basis; strict fractions and element validation; documented normalization and numeric limits; alloy references and Python/CLI/MCP parity | Complete in package 0.3.0 on `feat/fractional-compositions`; 245 tests pass; see RUN_LOG.md |
| P1 | Batch API and CLI | 1–100 items; independent success/errors in stable input order; sequential execution; invalid envelopes run nothing; versioned schema discovery and CLI/Python parity | Complete in package 0.4.0 on `feat/bounded-batch-calls`; 307 tests pass; see RUN_LOG.md |
| P1 | Export machine-readable tool catalog | Compatible v1 catalog/API/CLI/MCP; deterministic JSON and tracked schema artifacts; example schema validation; CI rejects stale generation across Python 3.11–3.13 | Complete in package 0.5.0 on `feat/reproducible-catalog-export`; 350 tests pass; see RUN_LOG.md |
| P2 | Optional structure module using ASE/pymatgen | Installation extra; single ordered CIF parsing, cell validation, bounded symmetry expansion and density; analytical references, provenance and Python/CLI/MCP parity; base-install missing-extra behavior | Complete in package 0.6.0 on `feat/ase-cif-structures`; 500 tests pass; see RUN_LOG.md |
| P2 | Scientific benchmark suite | Reference sources and justified tolerances; independently validated anisotropic elastic case | Ready |
| P2 | Unit-aware property records and screening | Provenance-bearing property schema; explicit constraints/units; no fabricated property values | Ready |
| P3 | Thermodynamics with supplied energies | Compatibility contract and hull reference cases defined before implementation | Planned |
| P3 | First simulation adapter | Choose engine; define preparation/parsing separately from execution; document integration environment | Planned |
| P3 | Property prediction baseline | Select licensed dataset, baseline metric, leakage-resistant split and applicability evaluation | Planned |
