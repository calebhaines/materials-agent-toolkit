# Instructions for automated contributors

Build reliable materials science and engineering operations that agents can discover and use without guessing conventions. Read README.md, ROADMAP.md, BACKLOG.md and RUN_LOG.md before selecting work.

## Work loop

1. Inspect the repository, open pull requests and unfinished work. Continue the existing bounded improvement when useful; avoid duplicate branches and pull requests.
2. Select one highest-priority feasible item in BACKLOG.md. State measurable acceptance criteria before implementation. Keep each change reviewable.
3. Implement the change with schemas, domain checks, documentation and scientifically meaningful verification. Use established scientific packages for complex algorithms.
4. Run checks relevant to the change, then the existing suite and lint/format checks when code changes. Record actual commands, results and limitations in RUN_LOG.md. Run `uv sync --locked --extra dev --extra mcp` for the complete development suite. Check the base installation separately when changing optional dependency behavior.
5. Update the backlog and roadmap to reflect completed behavior. For publication, follow the owner-authorized delivery mode; default to a pull request when the owner has not chosen direct commits. Summarize what changed, validation and the next useful task.

## Tool completion criteria

- Publish a unique tool name, independent tool version, strict input/output JSON schemas, units, assumptions, scientific references, dependencies and side effects through ToolSpec.
- Reject unknown fields, non-finite numbers, incompatible units and physically invalid inputs. Make numerical limits explicit. Never silently return unstable inversions, NaNs or misleading infinities.
- Return the common response envelope through the registry. Preserve validated input hashes and software/data provenance. Do not invent prediction uncertainty for deterministic calculations.
- State tensor notation, index order, coordinate conventions, sign conventions and validity ranges when relevant. Use SI units internally unless the tool explicitly declares another consistent convention.
- Test analytical cases, physical invariants or independently validated reference data with justified tolerances. Include important domain failures. Avoid tests that merely reproduce the implementation.
- Update discovery documentation and examples. Preserve existing tool contracts or introduce a versioned migration for breaking changes.
- Keep network/data fetching, local calculations and external simulation execution as separate operations. Future job adapters must expose resource estimates, lifecycle state, cancellation and output provenance.

## Scientific and dependency policy

Use established libraries such as pymatgen and ASE for structure algorithms when the relevant optional module is implemented. Add heavy engines and model frameworks as extras. Track licenses and provenance for data and model artifacts. Update uv.lock with dependency changes and verify installation. Unverified research ideas belong in the roadmap, not in the shipped tool catalog.

Never place credentials in source, logs, fixtures or outputs. This repository does not grant access to other repositories or authorize paid computational resources. Follow the owner's explicit session instructions when they change delivery or scope.

The standard GitHub app in ChatGPT is read-only, but a separately authorized GitHub CLI login can publish changes in an execution environment. Where the owner has already authenticated that login, use it without repeating authorization. Environment variables `GH_TOKEN` and `GITHUB_TOKEN` override saved CLI credentials; remove those overrides for a command when intentionally using the saved CLI login. See docs/GITHUB_SETUP.md.
