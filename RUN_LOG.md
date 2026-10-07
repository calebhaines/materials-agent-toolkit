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
