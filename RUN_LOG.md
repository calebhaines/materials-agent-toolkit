# Verified development log

Each entry records implemented behavior, verification evidence, unresolved limitations and the next useful task.

## 2026-10-07 — Initial scientific foundation

Prepared an agent-callable Python package, seven initial scientific operations, contributor instructions, roadmap and backlog.

Validation in Python 3.12.14 with the locked dependencies:

- `.venv/bin/python -m pytest -q`: **146 passed**. Covers analytical composition and density, isotropic and cubic anisotropic elasticity, scalar mixture limits, thermal expansion, Arrhenius diffusion, numeric edge cases, JSON schema conformance, provenance and CLI invocation.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: 19 files already formatted.
- `uv build`: source distribution and wheel built successfully.

Independent interface review found and resolved incorrect dependency provenance, an oversized-integer hashing failure and output-validation errors misclassified as caller domain errors. Regression coverage verifies the fixes.

CI is configured for Python 3.11, 3.12 and 3.13; the first GitHub run will verify those environments. The next priority is an MCP interface using the same tool registry and contracts.

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

## 2026-10-07 — Fractional alloy compositions, package 0.3.0

Implemented the next P1 scientific item on branch `feat/fractional-compositions`: `composition.from_fractions`, tool version 1. Agents supply an explicit elemental map and atomic or mass basis, then receive both fraction bases, mean atomic mass in g/mol of atoms, the original input total and atomic-weight provenance. Existing seven tool contracts remain version 1. Registry discovery makes the new operation available through Python, the JSON CLI and the optional MCP server without separate calculation adapters.

Default normalization requires a total within absolute tolerance `1e-8` of one; explicit `normalize` accepts weights or percentages with a positive finite total. Zero components are omitted. Invalid symbols, all-zero maps, non-finite or negative values, unknown fields and unrepresentable totals/components produce structured errors. No integer stoichiometry, formula-unit mass, alloy property or prediction uncertainty is inferred. Added NiTi and brass examples, full composition conventions and updated discovery documentation. Package version and lockfile metadata are now 0.3.0; dependency versions are unchanged.

Verification completed on Python 3.12.14:

- `uv sync --locked --extra dev --extra mcp`: passed.
- `uv run --no-sync pytest -q`: **245 passed**. Includes **71** fractional-composition cases: independently tabulated NiTi/brass references, formula-composition equivalence, per-atom mass convention, conservation/round trips, explicit normalization, strict schema failures, provenance, representable subnormal traces and numerical rejection cases. CLI and real stdio MCP results/schemas match the Python registry.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 28 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for version 0.3.0 built successfully.
- Independent scientific and interface review found a near-pure Li/Be conversion that rounded a dominant fraction above one. Added a regression for both bases, enforced positive fractions at most one and documented endpoint corrections bounded to four binary64 ulps. Larger excursions and loss of a positive trace remain domain errors. Review found no unresolved correctness issues after the fix.

CI exercises Python 3.11–3.13 and the base installation. The next P1 agent-interface item is a bounded batch API and CLI with stable ordering and per-item errors.

## 2026-10-07 — Bounded batch API and CLI, package 0.4.0

Implemented the next P1 agent-interface item on `feat/bounded-batch-calls`. `run_batch` accepts batch format version 1 with 1–100 raw request items, validates the strict outer envelope before execution, then dispatches each item sequentially through the existing registry. Results preserve input order and each item's scientific result, warnings, error taxonomy, validated input hash and software/reference provenance. Repeated requests execute independently without deduplication. Mixed outcomes return `partial`; all-item failures remain distinguishable from a structural `INVALID_BATCH` error. Unexpected item exceptions are redacted and isolated, while process interrupts propagate.

Added `matkit batch` with stdin/argument input, consistent JSON envelopes and exit code 0 only for all-success batches. `matkit batch-schema` and `describe_batch` expose the format version, bound, execution mode, envelope schemas and single-item request schema. Machine-readable field descriptions explain how malformed items are handled independently. A mixed NiTi/unknown-tool/water example and docs/BATCH.md document statuses, summary counts, limits and provenance. The eight scientific tool contracts and the MCP interface are unchanged; dependency versions are unchanged and package/lock metadata is 0.4.0.

Verification completed on Python 3.12.14:

- `uv sync --locked --extra dev --extra mcp`: passed.
- `uv run --no-sync pytest -q`: **307 passed**. Includes **40** batch API cases and **22** batch CLI cases. Analytical water/NiTi/isotropic references and schemas confirm unchanged scientific results; bounds, invalid-envelope no-execution, malformed middle items, stable ordering, repeated calls, hash preservation, unexpected failure redaction, interrupts, finite JSON serialization and Python/CLI parity are covered.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 31 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for 0.4.0 built successfully.
- Independent review of API, CLI, scientific/isolation tests, documentation and the example found no unresolved production correctness issues.

Batch calls are bounded sequential local execution; cross-item dependency graphs and simulation-job scheduling are separate future contracts. The next P1 item is standalone, reproducible machine-readable catalog export.

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

All current P1 backlog items are implemented. The next P2 scientific capability is optional structure parsing and validation using an established ASE/pymatgen adapter, with reference structures and density/provenance verification.


## 2026-10-07 — Optional ordered CIF structures, package 0.6.0

Implemented the next P2 item on `feat/ase-cif-structures`: `structure.analyze_cif`, tool version 1, using optional ASE and SciPy dependencies. All nine scientific operations are discoverable in the base package, JSON CLI, catalog and MCP. CIF execution returns the symmetry-expanded supplied cell, canonical elemental counts, wrapped fractional/Cartesian coordinates, volume in Å³ and ideal crystallographic density in kg/m³. Natural-element masses and the exact SI Avogadro constant match the existing `crystal.density` convention; responses record ASE/SciPy/NumPy/periodictable versions, references and the validated-input hash including exact CIF text.

The accepted domain is one ordered, fully occupied CIF 1.x structure with a complete stable three-dimensional cell. Input is bounded to 100000 characters, 256 asymmetric sites and 2048 expanded atoms, with a conservative pre-expansion site-count × operation-count bound of 2048. Cell lengths, angles, conditioning, finite coordinates, occupancies, canonical symbols and periodic dual-coordinate consistency are validated. Partial/disordered sites, isotope/charged type symbols, multiple or incomplete structures, conflicting metadata, nonclosed symmetry groups, duplicate tags, malformed uncertainty notation and parser warnings indicating dropped atom rows are rejected. Explicit operations paired with declared space-group metadata must match ASE's standard setting/origin; accepted rounding is normalized before expansion to preserve special positions. Complete explicit-only groups retain their supplied origin.

Added the optional `structures` extra, lazy dependency loading and a common `MISSING_DEPENDENCY` error with installation guidance. Schema/catalog discovery and input validation work without ASE, and broken transitive or operational imports remain redacted internal failures. Added an executable FCC Al example, full structure conventions/limits, CC0 analytical Al/NaCl/triclinic fixtures and updated locked dependencies, catalog, developer instructions and CI. ASE 3.29.0 is LGPL-2.1-or-later; no third-party coordinate dataset is copied.

Verification completed locally:

- `uv sync --locked --extra dev --extra mcp --extra structures`: passed on Python 3.12.14.
- `uv run --no-sync pytest -q`: **500 passed**. Includes **135** structure cases and **9** optional-dependency cases, plus CLI/MCP/catalog parity. Analytical geometry and density tolerances are stated in fixtures; physical scaling, periodic translation, independent density agreement and domain/resource limits are covered.
- Base-only Python 3.11.16 environment, `uv sync --locked --extra dev` and `uv run --no-sync pytest -q`: **348 passed, 127 expected skips** (including two absent-MCP modules). Catalog byte checks passed; independent smoke checks confirmed nine-tool discovery, absent ASE/SciPy/MCP, actionable CIF errors and clean missing-MCP startup.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed. Catalog SHA-256: `4bf06ddffafb9eadf3cfcf6a4708831ca8d7bf7e08d84d4243d6762de3f60272`.
- `uv run --no-sync ruff check .`: passed. `uv run --no-sync ruff format --check .`: 40 files already formatted. `git diff --check`: passed.
- `uv build`: source distribution and wheel for version 0.6.0 built successfully.
- Independent scientific/parser review resolved silent ASE site merging, incomplete or conflicting operation sets, discarded malformed rows/tags and a tolerance-boundary special-position density error. Final parser and interface reviews found no unresolved material issues. A 2048-operation/2048-atom explicit-only stress case completed in approximately 2.74 seconds including initial ASE import; symmetry checks use bounded query chunks rather than a full pairwise-position allocation.

CI adds structures to the Python 3.11–3.13 matrix and preserves a base-only job. Other structure formats, writing, neighbors, alternate-origin metadata reconciliation and broader symmetry analysis remain planned. The next bounded backlog item is the scientific benchmark suite, beginning with an independently validated anisotropic elastic reference.


## 2026-10-07 — Aluminum–ceramic discovery experiment

A bounded discovery experiment explores lightweight aluminum–ceramic heat-spreader recipes. The existing toolkit has composition, elastic conversion, scalar mixing and thermal-expansion calculations; the study therefore uses source-traceable constituent proxies rather than inventing alloy stability, strength or model predictions. No scientific tool contracts, dependencies, catalog or package version were changed; the experiment runs with the base package and plotting is optional.

The frozen dataset uses pure Al, CeramaSil-C SiC, PCAN1000S AlN and CeramAlox99.7% alumina. Independently retrieved supplier/handbook-backed sources confirm all selected values and both recorded PDF hashes. Baseline SiC E 350 GPa uses its listed lower endpoint; the source-high case uses 400 GPa. AlN PDF E 320 GPa differs from same-grade HTML 350 GPa, explicitly retained as a source comparison. Consolidated-grade/powder transfer, typical-value uncertainty and thermal-temperature mismatches are documented. Small factual subsets are attributed; supplier PDFs/full tables are not redistributed.

Actual library execution screened **8401 recipes** on a 1 volume-percent grid with 5–35% ceramic loading under seven scenarios (**58807 evaluations**). The experiment performs **58814 scalar tool calls**, with caches and explicitly documented homogeneous-scaling reuse, then saves selected actual replays. Existing composition/isotropic-modulus/mixture/thermal tools supply calculations through the common registry and batch envelopes. Separate K/G tensor Voigt/Reuss endpoints are converted to E, density uses phase-volume mixing, and conductivity uses ideal Fourier endpoints. Volume-average/Turner CTE are proxies, not rigorous bounds. Complete stored ToolResponse envelopes preserve timestamps, input hashes, software versions and references; no specimen properties are asserted as measured.

Results: **113 nominally feasible** recipes. Ranking by minimum loading then conductivity nominates **70% Al / 6% SiC / 24% AlN by volume**: density 2868 kg/m3, Reuss E 91.80259 GPa, harmonic conductivity 202.01422 W/(m K). Its specific-stiffness margin is only **0.029%**. The first feasible Al/AlN binary needs 31% AlN, making the hybrid's benefit small. The largest minimum nominal gate margin occurs at66% Al / 7% SiC / 27% AlN, but **no recipe passes every scenario**; both CTE-high and joint stress have 0 feasible. The report treats these as candidates for testing within an established family, with no established novelty or synthesis result. Literature review confirms Al/AlN and Al-alloy/SiC/AlN prior art, and documents interface/process limitations.

Artifacts in experiments/lightweight_composites include input/source records, bounded screen.py, 8401-row nominal CSV, deterministic gzip of all 58807 rows, summary, 71 complete response snapshots, independent method/prior-art/report documents and exported PNG/SVG tradeoff figures. Source-generation and read-only --check behavior are documented; --check validates snapshot schemas before comparing scientific projections and never overwrites outputs.

Verification completed:

- `uv run --no-sync python experiments/lightweight_composites/screen.py`: actual full study completed, selected Al070_SiC006_AlN024_Al2O3000.
- `uv run --no-sync python experiments/lightweight_composites/screen.py --check`: full artifacts passed read-only verification.
- `uv run --no-sync python experiments/lightweight_composites/plot.py`: exported PNG/SVG; visual inspection confirmed readable scientific labels, explicit ideal-model status, thin nominee margin and zero all-scenario survivors.
- `uv run --no-sync pytest -q`: **531 passed** on Python 3.12.14. Includes **31** independent experiment tests covering complete stiffness/compliance tensor oracles, homogeneous-phase limits, mass conservation, Fourier/CTE equations, gates, scenario isolation, bounded finite inputs, complete provenance and artifact drift/read-only behavior.
- Base-only Python 3.11.16, `uv run --no-sync pytest -q`: **379 passed, 127 expected skips**. Experiment tests require no ASE/MCP/matplotlib.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed; existing catalog unchanged.
- `uv run --no-sync ruff check .` and `ruff format --check .`: passed; 46 files formatted. `git diff --check`: passed.
- Independent scientific review directly recalculated all 58807 rows,823298derived numeric cells and gate outcomes; all agree with the actual artifact within binary64 rounding. Independent prior-art review found no evidence/novelty overclaim. Actual stored envelopes and request hashes were audited.

Frozen-input SHA256: 772b736d09f78cc9df0ec6f971bbbe268df3871b60e8c62b27a5ade742860f3d. NominalCSV SHA256: f6d592d1ef872d76acd5b8b5fd0550552afcbd570d05aa923869a6d581b455e5. Fullscenario-gzip SHA256: fc321c9b6ef2eba45b0f95b1ca3334abed72d9db076b450f2dc973b3c864c9ba. Numerical tables/summary are deterministic; response snapshots retain the recording environment and actual execution timestamps.

The experiment identifies hypotheses and an assumption-sensitive bottleneck, not a verified novel material. Next useful discovery work requires measured constituent/interface/porosity evidence and a broader novelty search; the standing core backlog still includes scientific benchmarks and property-record contracts.


## 2026-10-07 — Discovery in a different category: battery oxyfluorides

A bounded lithium-ion cathode composition experiment on `experiment/manganese-oxyfluoride-discovery` explores a different material category from the earlier aluminum composites. Acceptance criteria were a complete charge-admissible rational grid, actual composition-tool calls, source-verified endpoint controls, independently checked mass/electron budgets and gates, complete response provenance, deterministic replay and explicit phase/property/novelty limitations. No production source, scientific tool contract, catalog, dependency or package version changed.

The fixed family is Li2Mn_(1-t-n)Ti_tNb_nO2F with Li(+1), Ti(+4), Nb(+5), O(-2), F(-1), initial average Mn +2 to +3 and final assumed Mn(+4). Exact charge bookkeeping gives the grid constraint 2i_Ti+3j_Nb<=60 and conditional Mn-redox inventory 1+n electrons per normalized formula. Actual `composition.analyze` and `composition.from_fractions` calls supply formula masses/fractions, cross-checked using six atoms per normalized formula. Capacity is an experiment-level SI calculation F(1+n)/(3.6M), not a new prediction tool or a total-capacity ceiling when oxygen participates.

Actual execution covers **331 recipes**, **1324 candidate/scenario evaluations** and **662 successful toolkit calls**; every complete response snapshot is retained. Frozen gates are ideal Mn-only capacity >=250 mAh/g and Nb <=15 wt%, with ranking by least Nb mass fraction then greatest capacity. **33** nominal recipes pass. Nominee **Li2Mn2/3Ti1/6Nb1/6O2F** has mass 124.963993495 g/mol, formal Mn valence 2.25, ideal capacity 250.219233517 mAh/g and Nb 12.391085277 wt%. Its capacity margin is only 0.0877%, requiring 99.9124% of the assumed Mn redox to reach the target. It uses about 47% less Nb by mass and has about 7.2% lower formal capacity than the published Nb control.

The largest minimum normalized gate margin is a different recipe, Ti10/Nb12 (Li2Mn19/30Ti1/6Nb1/5O2F), with 254.787912301 mAh/g, 14.720218834 wt% Nb and 1.8652% minimum margin. Ti12/Nb12 maximizes capacity under the Nb gate, with 255.264553430 mAh/g. None pass hypothetical 90%, 80% or 70% utilization scenarios. Those are deterministic electron-budget scalings, not probabilities or predictions of experimental failure; the Nb-limited maximum is only 229.738 mAh/g at 90%. No voltage, phase stability, local valence, diffusion, oxygen-redox utilization, cycling, synthesis or safety performance is inferred.

Scoped prior-art retrieval verified six DOI records. Accessible 2018 Nature and 2020/2021 Nature Materials author manuscripts, independently re-fetched with matching PDF hashes, establish both endpoint controls and mixed Mn/Ti/Nb oxyfluoride prior art at different Li/O/F ratios. The Ti-series indexed abstract reports Ti(+3) in related compositions, limiting the fixed Ti(+4) assumption; oxygen-redox literature limits any total-capacity interpretation. Evidence levels, HTTP 403 access limits, hashes and small attributed metadata are preserved in sources.json without redistributing articles. Neither exact-recipe novelty nor a synthesized improved cathode is established.

Artifacts in experiments/manganese_oxyfluorides include frozen inputs, screen.py, the 331-row CSV, summary, all 662 complete response snapshots, source records, prior-art/method/report documents and exported PNG/SVG figures. Plotting remains optional and requires no new dependency. Read-only --check validates complete envelopes, timezone-aware timestamps and validated-input hashes, then compares scientific content while retaining recorded runtime provenance.

Verification completed on the final files:

- `uv sync --locked --extra dev --extra mcp --extra structures`: passed on Python 3.12.14.
- `uv run --no-sync python experiments/manganese_oxyfluorides/screen.py`: actual complete generation passed. Final `--check`: passed without overwriting artifacts.
- `uv run --no-sync python experiments/manganese_oxyfluorides/plot.py`: exported PNG/SVG; independent and maintainer visual inspection confirmed readable controls, gate margins and hypothetical status. SVG XML and whitespace checks passed.
- `uv run --no-sync pytest -q`: **598 passed** on Python 3.12.14. The **67** new cases use independent rational charge/conservation and static natural-mass/SI capacity oracles, all-row endpoint/gate/ranking/scenario checks, strict input bounds, complete response hashes/timestamps and read-only drift/type-corruption cases. An earlier 596-case run was followed by the final 598-case run after adding two timestamp/type-drift tests.
- Base-only Python 3.11.16, `uv run --no-sync pytest -q`: **446 passed, 127 expected skips**; all 67 new experiment tests pass without ASE/MCP/matplotlib.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed; catalog unchanged.
- `uv run --no-sync ruff check .` and `ruff format --check .`: passed; 52 files formatted. Whitespace checks passed.
- Independent scientific review directly recomputed all 331 rows / 8,606 numeric cells and all gates, replayed all 662actualresponses with schemas/input hashes, and verified all six DOI records and both manuscript PDF hashes. Largest physical relative error was 4.27e-16; all scientific documents and figure passed without overclaims. Independent review confirmed the strict experiment inputs, complete provenance and unchanged production contracts.

Frozen-input SHA256: 659e8555e770093f67910e1464b3e35b9f7062687f094b6a8f438cb632b37466. CSV SHA256: d29a2063869f85b97547c95d0e1b77bf72fdac510fb4e36e28229daa4cdd61cb. Summary SHA256: c9fefa75fcb3c22ec06406189656d3bf994aaabe84204a04384dd5c3e60f59d4. Recorded-response SHA256: e6e3828dae97af4f4c90cf257edb6ed1c81256becc95f243787dabf34ad72761. Runtime snapshots retain their actual recording timestamps and environment.

The result is a shortlist and a charge-accessibility bottleneck within a known family. Useful follow-up needs competing-phase/disorder and migration evidence, local-valence/fluorine characterization and matched electrochemical controls; further electron-count optimization cannot establish a better battery.

## 2026-10-08 — Documentation maintenance

Updated development guidance and project progress wording, and added ignore rules for local configuration. Scientific methods, results, response provenance, tool contracts and dependencies are unchanged.

Validation: all 46 relative Markdown links resolve; `git diff --check`, `uv run --no-sync python scripts/export_catalog.py --check`, `uv run --no-sync ruff check .` and `uv run --no-sync ruff format --check .` pass. Independent documentation review passed. This change contains no calculation or test-code changes.

## 2026-10-08 — Home-processable biopolymer investigation

Added a bounded formulation study on `experiment/home-biopolymer-discovery` for cool-water containment and simple home processing. Acceptance criteria were sourced process guidance, matched controls, strict and reproducible feed calculations, actual tool-response provenance, blank empirical records, and separate conclusions for water performance and environmental biodegradation. No production tool contract, catalog, dependency or package version changed.

Plain purchased PCL is the first supported forming benchmark, using the selected manufacturer's approximately 66°C water-bath instructions, tool-assisted removal and cooling. It is an existing polymer reshaped at home. Optional 5%/10% native-starch feeds are unvalidated hand-incorporation experiments, not thermoplastic starch. Nine calcium-treated alginate/glycerol/wax plans and one untreated alginate control provide an ingredients-based comparison. The whole-batch alginate casting geometry needs a retaining mold and may dry slowly; wax heating follows supplier guidance with an explicit proposed bath limit. Modified-process feasibility, water performance and environmental conversion remain unmeasured.

Actual execution covers **13 formulations**, **20 successful composition calls** and **39 blank trial rows**. Seven formula analyses and thirteen elemental-fraction conversions retain their complete response envelopes. Elemental budgets are ideal initial polymer/glycerol feed only: repeat formulas omit chain ends, grade additives and moisture; unknown beeswax composition, casting water and treatment baths are excluded. A 2 g calcium-lactate-pentahydrate bath feed provides approximately 6.4873 mmol available calcium against 10.0956 mmol initial alginate sites. The 1.28518 inventory ratio is not calcium uptake, crosslink fraction or reaction completion. Anhydrous salt is not interchangeable gram-for-gram.

Fourteen source records distinguish manufacturer information, accessible primary full texts, reviews and abstract-only evidence. The practical report treats PCL biodegradation as dependent on environment, grade and geometry, and distinguishes recovered mass loss from whole-polymer biological conversion. Manufacturer assets are fingerprinted without redistributing them. No verified waterproof material, novel polymer, food-contact approval, rapid home-compost timeline or numerical property prediction is claimed. Zero verified-result counts mean no empirical verification has occurred.

Artifacts in experiments/home_biopolymers include frozen inputs, study.py, formulation CSV, summary, all actual responses, a blank measurement template, source records and methods/prior-art/process/protocol/report documents. The water protocol specifies 20–25°C, 5 cm head and 24 hours, matched geometries, independent preparations, leakage/evaporation controls, wet and redried mass observations, and handling damage. Physical specimens have not been manufactured or tested.

Verification completed:

- `uv sync --locked --extra dev --extra mcp --extra structures`: passed on Python 3.12.14.
- `uv run --no-sync python experiments/home_biopolymers/study.py`: actual generation passed. Final `--check` passed without overwriting stored responses or observations; the base-only environment also reproduces it.
- `uv run --no-sync pytest -q`: **626 passed**. The **28** new cases use independent static elemental-mass/formula oracles, complete-grid controls, hydrate-specific inventory, mass closure, blank-record checks, strict finite input validation, complete provenance and read-only drift checks.
- Base-only Python 3.11.16, `python -m pytest -q`: **474 passed, 127 expected skips**. All new study tests require only the base package.
- `uv run --no-sync python scripts/export_catalog.py --check`: passed; catalog unchanged. `uv run --no-sync ruff check .` and `ruff format --check .`: passed; 56 files formatted. All **67** relative Markdown links resolve.
- Independent process review passed after clarifying alginate casting depth and wax handling limits; supported plain-PCL instructions remain separate from unvalidated blends and coatings.
- Independent numerical review recomputed all seven formula inventories, all thirteen rows and 334 numeric row cells with separately written atom counts and static elemental masses. Across 1002 comparisons, maximum relative error was 2.13e-16 and maximum mass-closure error 7.11e-15 g. All twenty response envelopes were validated and replayed, and all 1404 empirical observation cells in the 39-row template remain blank. Scientific and process documents passed without performance or novelty overclaims.

Frozen-input SHA256: f431e353cede3992e91355fc3c7d65c9c12f3c3d51f3a8bdc84012de0f418581. Formulation-CSV SHA256: 13b8037745a8af87efa9093647bd3b56b144884a8ea5ebac3df4fab935cf3115. Summary SHA256: e572fa5465afea8655265814594a321e20d9572c4eeed10e3a1c0fc97d80bfa7. Response-record SHA256: e30c096b03d4cf8c44c7ace3fe9b84605afdd70d124b2eea9ac8cf25dc6bba18.

The next decisive research step is measured matched-process specimens, followed separately by grade- and geometry-specific biodegradation evidence. Composition arithmetic alone cannot establish the requested combination of properties.
