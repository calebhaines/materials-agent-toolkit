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

Initial GitHub publication was blocked: credentials returned API 404 for the private repository, and Git fetch returned HTTP 403. The local branch, source archive and patch preserved the completed work. The owner subsequently made the repository public, restoring read access and allowing Git fetch. Write access remains blocked: Git push returns HTTP 403, and the GitHub branch-creation API returns "Resource not accessible by integration" (HTTP 403). No feature branch or pull request has been published. The prepared branch will be delivered through the agreed pull-request workflow once the connection has repository write access. The next scientific priority is structured fractional compositions for alloy inputs; the next agent-interface priority is bounded batch execution.

Connection diagnosis was corrected after checking the [official GitHub connection guide](https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt): the standard GitHub app in ChatGPT is read-only and cannot push code or open pull requests. Additional repository selection or repeated authentication does not change that product limitation. Publication requires a write-enabled Codex environment or another authorized development connection. [GITHUB_SETUP.md](docs/GITHUB_SETUP.md) records the supported setup and how to preserve the prepared work.
