# Materials Agent Toolkit

A Python library and JSON CLI for materials science and engineering calculations that AI agents can discover, validate and invoke automatically.

The toolkit supplies nine bounded scientific operations through a Python library, JSON CLI and optional MCP server. Additional structure analysis, simulation and trained models are tracked in [ROADMAP.md](ROADMAP.md). Every tool declares its assumptions and exposes input/output JSON schemas. Results carry input hashes, software versions and scientific references. Invalid inputs produce structured errors.

## Install and run

Requires Python 3.11 or later. With [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked --extra dev
uv run matkit list
uv run matkit describe mechanics.isotropic_moduli
uv run matkit run --request '{"tool":"mechanics.isotropic_moduli","input":{"young_modulus":210,"poisson_ratio":0.3,"stress_unit":"GPa"}}'
```

Without uv:

```sh
python -m pip install -e '.[dev]'
matkit list
```

Requests can also come from standard input:

```sh
matkit run < examples/water-composition.json
matkit validate < examples/water-composition.json
```

`list` includes the full tool descriptors; `describe` returns one descriptor. `validate` checks schemas and normalizes inputs without executing a calculation. `run` returns a JSON response and exits with code 0 on success or 2 on error. Calculation stdout contains JSON; usage errors go to stderr. Schema validation and scientific domain validation are separate: a request can pass `validate` and still fail a tool's physical domain checks during `run`.

```python
from materials_agent_toolkit.registry import list_tools, run_tool

tools = list_tools()
response = run_tool("composition.analyze", {"formula": "Al2O3"})
assert response.status == "ok", response.error
print(response.result)
```

## Batch calls

Run 1–100 independent requests in one invocation:

```sh
uv run matkit batch < examples/batch/mixed.json
uv run matkit batch-schema
```

```python
from materials_agent_toolkit.registry import run_batch

batch = run_batch(
    {
        "requests": [
            {"tool": "composition.analyze", "input": {"formula": "H2O"}},
            {
                "tool": "mechanics.isotropic_moduli",
                "input": {"young_modulus": 210, "poisson_ratio": 0.3},
            },
        ]
    }
)
assert batch.status == "ok", batch.responses
```

Responses retain input order, per-item errors and provenance. Requests run sequentially; an item failure does not stop the remaining calculations. An invalid batch envelope is rejected before execution. The CLI exits with code 2 for mixed or failed batches while still printing their complete JSON responses. The mixed example intentionally includes an unknown tool. See [batch contracts, limits and error handling](docs/BATCH.md).

## Initial tool catalog

| Tool | Purpose |
| --- | --- |
| `composition.analyze` | Element counts, atomic/mass fractions and formula molar mass |
| `composition.from_fractions` | Explicit atomic/mass composition, fraction conversion and mean atomic mass |
| `crystal.density` | Density from formula, formula units and unit-cell volume |
| `mechanics.isotropic_moduli` | Convert Young's modulus and Poisson ratio into isotropic moduli |
| `mechanics.elastic_vrh` | Stability validation and Voigt/Reuss/Hill aggregate elastic properties |
| `mixtures.scalar_bounds` | Scalar arithmetic/harmonic mixture estimates using volume fractions |
| `thermal.linear_expansion` | Constant-coefficient, small-strain linear thermal expansion |
| `kinetics.arrhenius_diffusivity` | Diffusivity from an Arrhenius prefactor and activation energy |
| `structure.analyze_cif` | Validate an ordered CIF crystal, expand symmetry and calculate cell density (requires `structures` extra) |

Discover the installed schemas instead of guessing argument names. Tool versions are independent of the package version. Requests may set `tool_version` to reject an incompatible implementation. Formula syntax is deliberately bounded; descriptors list the accepted syntax. Elastic stiffness uses the engineering Voigt ordering `xx, yy, zz, yz, xz, xy` with doubled shear strains. Calculation units are explicit in inputs and outputs.

Alloys can use an explicit elemental fraction map and basis instead of a formula. For example, `{"tool":"composition.from_fractions","input":{"fractions":{"Ni":0.5,"Ti":0.5},"basis":"atomic"}}` describes equiatomic NiTi. Fractions must sum to one within the documented tolerance by default; `"normalization":"normalize"` explicitly accepts relative weights or percentages. See [fractional composition conventions and examples](docs/COMPOSITION.md).

For ordered crystal structures, install the optional ASE adapter and provide CIF contents:

```sh
uv sync --locked --extra structures
uv run --no-sync matkit run < examples/structures/al-fcc.json
```

With pip, install `materials-agent-toolkit[structures]` (or `-e '.[structures]'` from this checkout). `structure.analyze_cif` returns the symmetry-expanded supplied cell, atomic coordinates, volume and density. Its descriptor remains available without ASE; execution then returns `MISSING_DEPENDENCY`. See [CIF conventions, resource bounds and reference fixtures](docs/STRUCTURES.md).

Input hashes identify canonical validated inputs, including defaults. Record the tool name/version and software versions alongside the hash for reproducibility. Timestamps identify execution time; they are not part of the input hash. Scientific references explain the model, while numerical tolerances and assumptions are declared in descriptors or source documentation.

No tool downloads data or launches external jobs. Predictions and expensive simulation adapters will have separate contracts when implemented. Model assumptions and warnings must be considered before applying outputs to an engineering decision.

## Export the catalog

Save the versioned tool descriptors and complete response schema for offline bot discovery:

```sh
uv run matkit catalog > tool-catalog.json
uv run matkit catalog-schema > tool-catalog.schema.json
```

The [committed catalog](catalog/tool-catalog.json) and [catalog schema](catalog/tool-catalog.schema.json) are generated from the same registry used by Python, CLI and MCP. Exports use deterministic UTF-8 JSON and retain catalog format version `1`. Run `uv run --no-sync python scripts/export_catalog.py --check` to verify that artifacts match the installed source and locked dependencies. See [catalog format, validation and regeneration](docs/CATALOG.md).

## Connect an MCP client

Install the optional official MCP SDK and launch the stdio server:

```sh
uv sync --locked --extra mcp
uv run --no-sync matkit-mcp
```

Compatible AI clients can discover the nine tools by their names and call them using the input fields shown in their schemas. The server returns the same result/error envelope as the Python and CLI interfaces, with `structuredContent` for machine consumption and equivalent JSON text for other clients. It also exposes the complete catalog and response schema as MCP resources. See [MCP setup and protocol details](docs/MCP.md) for a client configuration and a runnable example.

## Discovery experiments

The [aluminum–ceramic heat-spreader experiment](experiments/lightweight_composites/REPORT.md) uses sourced constituent data and the existing tools to screen 8,401 recipes, compare controls and test sensitivity. It produces unvalidated candidate hypotheses with explicit prior-art and model limitations. The scripts, inputs, numerical outputs and plot are committed for reproducibility; these results are separate from the scientific tool catalog.

## Contributing and hourly development

[AGENTS.md](AGENTS.md) specifies the completion criteria for AI contributors. [BACKLOG.md](BACKLOG.md) is the persistent queue, and [RUN_LOG.md](RUN_LOG.md) records verified work. [The hourly task specification](docs/HOURLY_TASK.md) contains a schedule and prompt ready for a ChatGPT automation with GitHub and execution access. The specification is a setup artifact; it does not itself schedule any job.

```sh
uv sync --locked --extra dev --extra mcp --extra structures
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

The exact dependency resolution is committed in `uv.lock`. CI checks Python 3.11–3.13 with MCP and structures enabled and separately checks the base installation without either extra. Optional scientific and MCP tests skip when their extras are absent; discovery and structured missing-dependency errors remain covered. Add scientific reference cases and explicit domain limits alongside each calculation.
