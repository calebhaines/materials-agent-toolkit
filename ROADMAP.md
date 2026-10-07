# Roadmap

The aim is a broad, agent-callable materials science and engineering platform. Capability grows through completed, validated tools. The toolkit implements formula and fractional composition, density, selected engineering calculations and an optional MCP stdio interface. Later capabilities remain planned; publication status is recorded in RUN_LOG.md.

| Stage | Deliverables | Evidence required |
| --- | --- | --- |
| 0 — Contracts and calculations | Strict schemas, discovery, JSON CLI, provenance, seven initial calculations, reproducible dependencies, CI | Analytical cases, domain failures, JSON schema conformance and CLI integration |
| 1 — Agent integration | MCP server wrapping the same registry; batch calls with per-item errors; error taxonomy; versioned machine-readable catalog | Client integration, matching library/CLI/MCP results, predictable concurrency |
| 2 — Composition and structures | Structured fractional compositions; CIF/POSCAR/XYZ reading and writing; cell validation; symmetry, neighbors and structure density through optional pymatgen/ASE adapters | Reference structures, format round trips, consistent units, cross-library cases |
| 3 — Engineering design | Anisotropic stress/strain transformations; orientation dependence; constrained material screening; unit-aware property records; physical model applicability metadata | Tensor transformation invariants, benchmark cases, source-traceable property data |
| 4 — Thermodynamics | Phase diagrams and energy-above-hull with compatible supplied reference energies; explicit reference states and energy corrections | Known hulls, composition conservation, incompatible-dataset rejection |
| 5 — Simulation workflows | Reproducible inputs and parsers for selected engines; job lifecycle API; local/remote execution adapters with budgets and cancellation | Round-trip fixtures, engine availability checks, integration cases, complete job provenance |
| 6 — Property models | Curated datasets and baseline property prediction; split strategy, uncertainty, applicability limits and model cards | Leakage-resistant evaluations, uncertainty calibration, baseline comparisons |
| 7 — Discovery loops | Candidate generation, workflow planning, caching and adaptive experiment/simulation selection | End-to-end reproducibility, quantitative scientific benchmarks and bounded compute |

Stage 1 progress: package 0.2.0 introduced the optional MCP stdio server, native tool discovery, structured errors, catalog/schema resources and runnable client example. Package 0.4.0 adds versioned Python/CLI batches with 1–100 sequential calls, stable ordering, independent item errors and schema discovery. Package 0.5.0 adds deterministic standalone catalog/schema exports, tracked artifacts, example schema validation and CI drift checks on supported Python versions.

Stage 2 progress in package 0.3.0: `composition.from_fractions` supports explicit atomic or mass fractions, optional normalization of relative weights, conversion between bases and mean atomic mass. Formula-unit counts are not inferred. Structure parsing and analysis remain in the backlog.

Scope and ordering can be adjusted by the owner. Open tasks, acceptance criteria and dependencies belong in BACKLOG.md; completed work belongs in RUN_LOG.md.
