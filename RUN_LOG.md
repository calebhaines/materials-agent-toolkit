# Verified development log

Each entry records implemented behavior, actual verification evidence, unresolved limitations and the next useful task. Files describing plans are not evidence that an automation is active or a GitHub change has been published.

## 2026-10-07 — Initial local preparation

Prepared an agent-callable Python package, seven initial scientific operations, persistent contributor instructions, roadmap, backlog and hourly task specification. GitHub authentication succeeded for calebhaines. No existing materials repository was present, so the initial repository uses the name materials-agent-toolkit and private visibility. Future development defaults to pull requests. These defaults can be changed by the owner.

Validation in Python 3.12.14 with the locked dependencies:

- `.venv/bin/python -m pytest -q`: **146 passed**. Covers analytical composition and density, isotropic and cubic anisotropic elasticity, scalar mixture limits, thermal expansion, Arrhenius diffusion, numeric edge cases, JSON schema conformance, provenance and CLI invocation.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: 19 files already formatted.
- `uv build`: source distribution and wheel built successfully.

Independent interface review found and resolved incorrect dependency provenance, an oversized-integer hashing failure and output-validation errors misclassified as caller domain errors. Regression coverage verifies the fixes.

CI is configured for Python 3.11, 3.12 and 3.13; the first GitHub run will verify those environments. The next priority is an MCP interface using the same tool registry and contracts.

No ChatGPT automation has been created: the current session has no callable automation tool. The hourly task specification is prepared for activation with execution and GitHub access.

## 2026-10-07 — Optional MCP integration, package 0.2.0

Implemented the next P1 item on branch `feat/mcp-agent-interface`: an optional stdio MCP server backed by the same scientific registry. All seven tools publish their strict raw input schemas, full result-envelope output schemas, versions, assumptions, references and read-only annotations. Calls preserve structured errors, scientific results and provenance, with equivalent machine-readable and text content. JSON resources expose the catalog and response schema.

Added a runnable official-SDK client example, client configuration and protocol documentation. The MCP extra is separate from the base dependencies. The base package and CLI remain usable without it; server startup then returns exit code 2 with installation guidance on stderr and no traceback or stdout. Updated the lockfile and configured CI to exercise both MCP-enabled and base-only installations. Scientific tool contracts remain version 1.

Verification completed locally:

- Complete MCP-enabled suite on Python 3.11.16, 3.12.14 and 3.13.5: **169 passed on each interpreter**, including 14 adapter tests and nine real stdio integration tests.
- Base-only environment on Python 3.12.14: **146 passed, two MCP test modules skipped**. Independently verified all tool discovery and missing-extra module/console startup behavior.
- `ruff check .`: passed. `ruff format --check .`: 24 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for version 0.2.0 built successfully.
- Client example successfully returned the structured H2O calculation with 18.015 g/mol molar mass.
- Independent review found no correctness defects and verified real JSON-RPC calls, structured failures followed by successful calls, unsupported resource rejection and clean shutdown without protocol stdout contamination.

Initial GitHub publication was blocked: credentials returned API 404 for the private repository, and Git fetch returned HTTP 403. The local branch, source archive and patch preserved the completed work. The owner subsequently made the repository public, restoring read access and allowing Git fetch. Write access initially remained blocked: Git push returned HTTP 403, and the GitHub branch-creation API returned "Resource not accessible by integration" (HTTP 403). The next scientific priority is structured fractional compositions for alloy inputs; the next agent-interface priority is bounded batch execution.

The [official GitHub connection guide](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt) confirms that the standard GitHub app in ChatGPT is read-only. That limitation does not apply to a separately authorized GitHub CLI login. A fresh CLI device login requesting `repo` and `workflow` scopes succeeded; subsequent `gh auth status` confirmed both scopes. With `GH_TOKEN` and `GITHUB_TOKEN` removed from the command environment, Git push succeeded and [PR #1](https://github.com/calebhaines/materials-agent-toolkit/pull/1) was opened. No merge has been performed. [GITHUB_SETUP.md](docs/GITHUB_SETUP.md) records both publishing routes. GitHub CI results are available on the pull request.

## 2026-10-07 — MCP acceptance and protected repository policy

The owner authorized the maintainer to accept the MCP PR and protect the repository against outside code changes and pull requests. Independent pre-merge review found no material correctness issues at head `1170863`; all four required CI jobs passed. [PR #1](https://github.com/calebhaines/materials-agent-toolkit/pull/1) was squash-merged as `1a40fa75b790160e91deeefa7bf5b19abdb641f2`. GitHub does not permit a PR author to formally approve their own PR; owner-authorized review and CI verification preceded the merge.

Applied and independently verified these server settings:

- Permanent `pull_request_creation_policy: collaborators_only` using the update-repository API version `2026-03-10`. The repository remains public. `calebhaines` is the only collaborator; no deploy keys or pending invitations exist.
- Protected `main`: pull requests required, branch must be current, administrator enforcement, resolved conversations and linear history required. GitHub Actions app `15368` must report success for `validate (3.11)`, `validate (3.12)`, `validate (3.13)` and `base-install`. Force pushes and branch deletion are blocked.
- Required approval count is zero to avoid an impossible self-approval requirement for the sole owner's changes; independent review and CI remain required by the maintenance policy.
- Actions tokens have default read permissions and cannot approve PR reviews. Workflows from all external contributors require approval.

The initial protection request contained both `contexts` and `checks`, which GitHub rejected as conflicting schema alternatives. A checks-only request succeeded, and GET verification confirmed all checks remain bound to the expected GitHub Actions app. No branch protection was bypassed for the merge. Public cloning/forking and issue/comment participation do not grant upstream code access or PR creation rights. The policy is recorded in docs/REPOSITORY_POLICY.md and a machine-readable snapshot in .github/repository-policy.json.

## 2026-10-07 — Fractional alloy compositions, package 0.3.0

Implemented the next P1 scientific item on branch `feat/fractional-compositions`: `composition.from_fractions`, tool version 1. Agents supply an explicit elemental map and atomic or mass basis, then receive both fraction bases, mean atomic mass in g/mol of atoms, the original input total and atomic-weight provenance. Existing seven tool contracts remain version 1. Registry discovery makes the new operation available through Python, the JSON CLI and the optional MCP server without separate calculation adapters.

Default normalization requires a total within absolute tolerance `1e-8` of one; explicit `normalize` accepts weights or percentages with a positive finite total. Zero components are omitted. Invalid symbols, all-zero maps, non-finite or negative values, unknown fields and unrepresentable totals/components produce structured errors. No integer stoichiometry, formula-unit mass, alloy property or prediction uncertainty is inferred. Added NiTi and brass examples, full composition conventions and updated discovery documentation. Package version and lockfile metadata are now 0.3.0; dependency versions are unchanged.

Verification completed on Python 3.12.14:

- `uv sync --locked --extra dev --extra mcp`: passed.
- `uv run --no-sync pytest -q`: **245 passed**. Includes **71** fractional-composition cases: independently tabulated NiTi/brass references, formula-composition equivalence, per-atom mass convention, conservation/round trips, explicit normalization, strict schema failures, provenance, representable subnormal traces and numerical rejection cases. CLI and real stdio MCP results/schemas match the Python registry.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 28 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for version 0.3.0 built successfully.
- Independent scientific and interface review found a near-pure Li/Be conversion that rounded a dominant fraction above one. Added a regression for both bases, enforced positive fractions at most one and documented endpoint corrections bounded to four binary64 ulps. Larger excursions and loss of a positive trace remain domain errors. Review found no unresolved correctness issues after the fix.

The owner permitted direct pushes, but protected `main` requires PR delivery and all four existing CI checks. This run preserves those controls and uses the maintainer-authorized merge workflow. CI exercises Python 3.11–3.13 and the base installation. The next P1 agent-interface item is a bounded batch API and CLI with stable ordering and per-item errors.

## 2026-10-07 — Bounded batch API and CLI, package 0.4.0

Implemented the next P1 agent-interface item on `feat/bounded-batch-calls`. `run_batch` accepts batch format version 1 with 1–100 raw request items, validates the strict outer envelope before execution, then dispatches each item sequentially through the existing registry. Results preserve input order and each item's scientific result, warnings, error taxonomy, validated input hash and software/reference provenance. Repeated requests execute independently without deduplication. Mixed outcomes return `partial`; all-item failures remain distinguishable from a structural `INVALID_BATCH` error. Unexpected item exceptions are redacted and isolated, while process interrupts propagate.

Added `matkit batch` with stdin/argument input, consistent JSON envelopes and exit code 0 only for all-success batches. `matkit batch-schema` and `describe_batch` expose the format version, bound, execution mode, envelope schemas and single-item request schema. Machine-readable field descriptions explain how malformed items are handled independently. A mixed NiTi/unknown-tool/water example and docs/BATCH.md document statuses, summary counts, limits and provenance. The eight scientific tool contracts and the MCP interface are unchanged; dependency versions are unchanged and package/lock metadata is 0.4.0.

Verification completed on Python 3.12.14:

- `uv sync --locked --extra dev --extra mcp`: passed.
- `uv run --no-sync pytest -q`: **307 passed**. Includes **40** batch API cases and **22** batch CLI cases. Analytical water/NiTi/isotropic references and schemas confirm unchanged scientific results; bounds, invalid-envelope no-execution, malformed middle items, stable ordering, repeated calls, hash preservation, unexpected failure redaction, interrupts, finite JSON serialization and Python/CLI parity are covered.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 31 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for 0.4.0 built successfully.
- Independent review of API, CLI, scientific/isolation tests, documentation and the example found no unresolved production correctness issues.

The protected PR workflow and repository access policy remain in force. Batch calls are bounded sequential local execution; cross-item dependency graphs and simulation-job scheduling are separate future contracts. The next P1 item is standalone, reproducible machine-readable catalog export.

## 2026-10-07 — Reproducible catalog export, package 0.5.0

Implemented the next P1 item on `feat/reproducible-catalog-export`: a shared version-1 catalog API, `matkit catalog` and `matkit catalog-schema`, and committed JSON artifacts. The catalog preserves the MCP resource's three-field object and all eight scientific descriptors. Strict catalog/descriptor models publish a Draft 2020-12 outer schema; embedded scientific input/output and common response schemas retain their own roots and local references. The MCP resource now uses the same canonical renderer as standalone export.

Canonical exports use sorted keys, two-space indentation, UTF-8 bytes and one final line feed. The CLI writes bytes directly to preserve encoding under legacy stdout settings. Generation rejects non-finite and non-serializable metadata without null replacement. A runtime factory for Python-version provenance removes host-specific schema defaults while preserving execution-time Python versions in actual responses. No science runs or network calls occur during export, and MCP remains optional. Package/lock metadata is 0.5.0; dependency versions and scientific tool versions are unchanged.

Added `scripts/export_catalog.py` and its read-only `--check` mode. Both artifacts are tracked in `catalog/`; missing or byte-stale files fail checks without overwriting them. CI checks generation on Python 3.11–3.13 with MCP and on the base installation. Contributor instructions and docs/CATALOG.md explain regeneration, strict validation, reproducibility limits and separate batch discovery.

Verification completed on Python 3.12.14:

- `uv sync --locked --extra dev --extra mcp`: passed.
- `uv run --no-sync pytest -q`: **350 passed**. Includes **29** catalog contract cases and **14** CLI/generator cases. All root and batch example inputs validate against published contracts; outer and 17 embedded schemas pass Draft 2020-12 checks. Actual MCP resource text matches Python canonical JSON and committed UTF-8 bytes.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed. Catalog SHA-256 is `c3c99498d18b1c845b05c5223738dbb8b907ae1841461ceae9c687c50fc3048f`; schema SHA-256 is `8c3aa03fbbc4a3b595251e38045704f64a21af5728212c9542a3b333263c24c1`.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 36 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for 0.5.0 built successfully; wheel contains the new catalog module.
- Contract testing exposed Pydantic JSON serialization converting open-schema NaN/infinity values to null. Export now preserves values for explicit finite JSON validation, and both API/rendering rejection cases pass. Independent compatibility, artifact, reference-resolution and interface review found no unresolved correctness issues after the fix.

The protected delivery workflow and repository access controls remain active. All current P1 backlog items are implemented. The next P2 scientific capability is optional structure parsing and validation using an established ASE/pymatgen adapter, with reference structures and density/provenance verification.


## 2026-10-07 — Optional ordered CIF structures, package 0.6.0

Implemented the next P2 item on `feat/ase-cif-structures`: `structure.analyze_cif`, tool version 1, using optional ASE and SciPy dependencies. All nine scientific operations are discoverable in the base package, JSON CLI, catalog and MCP. CIF execution returns the symmetry-expanded supplied cell, canonical elemental counts, wrapped fractional/Cartesian coordinates, volume in Å³ and ideal crystallographic density in kg/m³. Natural-element masses and the exact SI Avogadro constant match the existing `crystal.density` convention; responses record ASE/SciPy/NumPy/periodictable versions, references and the validated-input hash including exact CIF text.

The accepted domain is one ordered, fully occupied CIF 1.x structure with a complete stable three-dimensional cell. Input is bounded to 100000 characters, 256 asymmetric sites and 2048 expanded atoms, with a conservative pre-expansion site-count × operation-count bound of 2048. Cell lengths, angles, conditioning, finite coordinates, occupancies, canonical symbols and periodic dual-coordinate consistency are validated. Partial/disordered sites, isotope/charged type symbols, multiple or incomplete structures, conflicting metadata, nonclosed symmetry groups, duplicate tags, malformed uncertainty notation and parser warnings indicating dropped atom rows are rejected. Explicit operations paired with declared space-group metadata must match ASE's standard setting/origin; accepted rounding is normalized before expansion to preserve special positions. Complete explicit-only groups retain their supplied origin.

Added the optional `structures` extra, lazy dependency loading and a common `MISSING_DEPENDENCY` error with installation guidance. Schema/catalog discovery and input validation work without ASE, and broken transitive or operational imports remain redacted internal failures. Added an executable FCC Al example, full structure conventions/limits, CC0 analytical Al/NaCl/triclinic fixtures and updated locked dependencies, catalog, developer instructions and CI. ASE 3.29.0 is LGPL-2.1-or-later; no third-party coordinate dataset is copied.

Verification completed locally:

- `uv sync --locked --extra dev --extra mcp --extra structures`: passed on Python 3.12.14.
- `uv run --no-sync pytest -q`: **500 passed**. Includes **135** structure cases and **9** optional-dependency cases, plus CLI/MCP/catalog parity. Analytical geometry and density tolerances are stated in fixtures; physical scaling, periodic translation, independent density agreement and domain/resource limits are covered.
- Base-only Python 3.11.16 environment, `UV_PROJECT_ENVIRONMENT=/workspace/materials-agent-base-env uv sync --locked --extra dev` and `uv run --no-sync pytest -q`: **348 passed, 127 expected skips** (including two absent-MCP modules). Catalog byte checks passed; independent smoke checks confirmed nine-tool discovery, absent ASE/SciPy/MCP, actionable CIF errors and clean missing-MCP startup.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed. Catalog SHA-256: `4bf06ddffafb9eadf3cfcf6a4708831ca8d7bf7e08d84d4243d6762de3f60272`.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 40 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for version 0.6.0 built successfully.
- Independent scientific/parser review resolved silent ASE site merging, incomplete or conflicting operation sets, discarded malformed rows/tags and a tolerance-boundary special-position density error. Final parser and interface reviews found no unresolved material issues. A 2048-operation/2048-atom explicit-only stress case completed in approximately 2.74 seconds including initial ASE import; symmetry checks use bounded query chunks rather than a full pairwise-position allocation.

CI retains the same four protected check names, adding structures to the Python 3.11–3.13 matrix and preserving a base-only job. Repository API verification confirms collaborator-only PR creation, administrator-enforced branch protection, strict GitHub Actions checks, and blocked force pushes/deletion. Other structure formats, writing, neighbors, alternate-origin metadata reconciliation and broader symmetry analysis remain planned. The next bounded backlog item is the scientific benchmark suite, beginning with an independently validated anisotropic elastic reference.


## 2026-10-07 — User-directed material-discovery attempt

The owner asked to use the library for novel material discovery and allowed any material type. Reprioritized one bounded experiment: lightweight aluminum–ceramic heat-spreader recipes. The existing toolkit has composition, elastic conversion, scalar mixing and thermal-expansion calculations; the study therefore uses source-traceable constituent proxies rather than inventing alloy stability, strength or model predictions. No scientific tool contracts, dependencies, catalog or package version were changed; the experiment runs with the base package and plotting is optional.

The frozen dataset uses pure Al, CeramaSil-C SiC, PCAN1000S AlN and CeramAlox99.7% alumina. Independently retrieved supplier/handbook-backed sources confirm all selected values and both recorded PDF hashes. Baseline SiC E 350 GPa uses its listed lower endpoint; the source-high case uses 400 GPa. AlN PDF E 320 GPa differs from same-grade HTML 350 GPa, explicitly retained as a source comparison. Consolidated-grade/powder transfer, typical-value uncertainty and thermal-temperature mismatches are documented. Small factual subsets are attributed; supplier PDFs/full tables are not redistributed.

Actual library execution screened **8401 recipes** on a 1 volume-percent grid with 5–35% ceramic loading under seven scenarios (**58807 evaluations**). The experiment performs **58814 scalar tool calls**, with caches and explicitly documented homogeneous-scaling reuse, then saves selected actual replays. Existing composition/isotropic-modulus/mixture/thermal tools supply calculations through the common registry and batch envelopes. Separate K/G tensor Voigt/Reuss endpoints are converted to E, density uses phase-volume mixing, and conductivity uses ideal Fourier endpoints. Volume-average/Turner CTE are proxies, not rigorous bounds. Complete stored ToolResponse envelopes preserve timestamps, input hashes, software versions and references; no specimen properties are asserted as measured.

Results: **113 nominally feasible** recipes. Ranking by minimum loading then conductivity nominates **70% Al / 6% SiC / 24% AlN by volume**: density 2868 kg/m3, Reuss E 91.80259 GPa, harmonic conductivity 202.01422 W/(m K). Its specific-stiffness margin is only **0.029%**. The first feasible Al/AlN binary needs 31% AlN, making the hybrid's benefit small. The largest minimum nominal gate margin occurs at66% Al / 7% SiC / 27% AlN, but **no recipe passes every scenario**; both CTE-high and joint stress have 0 feasible. The report treats these as candidates for testing within an established family, with no established novelty or synthesis result. Literature review confirms Al/AlN and Al-alloy/SiC/AlN prior art, and documents interface/process limitations.

Artifacts in experiments/lightweight_composites include input/source records, bounded screen.py, 8401-row nominal CSV, deterministic gzip of all 58807 rows, summary, 71 complete response snapshots, independent method/prior-art/report documents and exported PNG/SVG tradeoff figures. Source-generation and read-only --check behavior are documented; --check validates snapshot schemas before comparing scientific projections and never overwrites outputs.

Verification completed:

- `uv run --no-sync python experiments/lightweight_composites/screen.py`: actual full study completed, selected Al070_SiC006_AlN024_Al2O3000.
- `uv run --no-sync python experiments/lightweight_composites/screen.py --check`: full artifacts passed read-only verification.
- `uv run --no-sync python experiments/lightweight_composites/plot.py`: exported PNG/SVG; visual inspection confirmed readable scientific labels, explicit ideal-model status, thin nominee margin and zero all-scenario survivors.
- `uv run --no-sync pytest -q`: **531 passed** on Python 3.12.14. Includes **31** independent experiment tests covering complete stiffness/compliance tensor oracles, homogeneous-phase limits, mass conservation, Fourier/CTE equations, gates, scenario isolation, bounded finite inputs, complete provenance and artifact drift/read-only behavior.
- Base-only Python 3.11.16, `UV_PROJECT_ENVIRONMENT=/workspace/materials-agent-base-env uv run --no-sync pytest -q`: **379 passed, 127 expected skips**. Experiment tests require no ASE/MCP/matplotlib.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed; existing catalog unchanged.
- `uv run --no-sync ruff check .` and `ruff format --check .`: passed; 46 files formatted. `git diff --check`: passed.
- Independent scientific review directly recalculated all 58807 rows,823298derived numeric cells and gate outcomes; all agree with the actual artifact within binary64 rounding. Independent prior-art review found no evidence/novelty overclaim. Actual stored envelopes and request hashes were audited.

Frozen-input SHA256: 772b736d09f78cc9df0ec6f971bbbe268df3871b60e8c62b27a5ade742860f3d. NominalCSV SHA256: f6d592d1ef872d76acd5b8b5fd0550552afcbd570d05aa923869a6d581b455e5. Fullscenario-gzip SHA256: fc321c9b6ef2eba45b0f95b1ca3334abed72d9db076b450f2dc973b3c864c9ba. Numerical tables/summary are deterministic; response snapshots retain the recording environment and actual execution timestamps.

The experiment identifies hypotheses and an assumption-sensitive bottleneck, not a verified novel material. Next useful discovery work requires measured constituent/interface/porosity evidence and a broader novelty search; the standing core backlog still includes scientific benchmarks and property-record contracts. Protected delivery and repository access controls remain in force.
