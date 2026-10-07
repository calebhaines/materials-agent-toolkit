# Persistent backlog

Select one bounded item per development run. Update status and link the branch/pull request when work begins. Reprioritize based on user instructions and observed limitations.

| Priority | Task | Acceptance criteria | Status |
| --- | --- | --- | --- |
| P0 | Ship initial scientific tool foundation | Seven tools, discoverable schemas, validated envelopes, reference tests, CLI checks, dependency lock and CI | Complete; 146 tests and package build pass; see RUN_LOG.md |
| P1 | Add MCP interface | Same tools/results as registry; discoverable schemas; client example; real stdio integration test; optional dependency with base-install coverage | Implemented and verified on `feat/mcp-agent-interface`; prepared for pull request |
| P1 | Add structured fractional composition input | Atomic fractions and mass fractions support alloys without ambiguous formula syntax; documented normalization; known alloy cases | Ready |
| P1 | Batch API and CLI | Per-item success/error; stable ordering; no all-or-nothing failure; documented bounded batch size | Ready |
| P1 | Export machine-readable tool catalog | Versioned catalog and response schema; examples validate against schemas; reproducible generation | Ready |
| P2 | Optional structure module using ASE/pymatgen | Installation extra; CIF parsing and structure validation/density; known reference structures and provenance | Ready |
| P2 | Scientific benchmark suite | Reference sources and justified tolerances; independently validated anisotropic elastic case | Ready |
| P2 | Unit-aware property records and screening | Provenance-bearing property schema; explicit constraints/units; no fabricated property values | Ready |
| P3 | Thermodynamics with supplied energies | Compatibility contract and hull reference cases defined before implementation | Planned |
| P3 | First simulation adapter | Choose engine; define preparation/parsing separately from execution; document integration environment | Planned |
| P3 | Property prediction baseline | Select licensed dataset, baseline metric, leakage-resistant split and applicability evaluation | Planned |
