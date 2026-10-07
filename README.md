# Materials Agent Toolkit

A Python library and JSON CLI for materials science and engineering calculations that AI agents can discover, validate and invoke automatically.

This is the first working foundation for a broader toolkit. It supplies seven bounded calculations; advanced simulation, structure analysis, MCP integration and trained models are tracked in [ROADMAP.md](ROADMAP.md). Every tool declares its assumptions and exposes input/output JSON schemas. Results carry input hashes, software versions and scientific references. Invalid inputs produce structured errors.

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

`list` includes the full tool descriptors; `describe` returns one descriptor. `validate` checks schemas and normalizes inputs without executing a calculation. `run` returns a JSON response and exits with code 0 on success or 2 on error. Stdout contains JSON; CLI usage text goes to stderr. Schema validation and scientific domain validation are separate: a request can pass `validate` and still fail a tool's physical domain checks during `run`.

```python
from materials_agent_toolkit.registry import list_tools, run_tool

tools = list_tools()
response = run_tool("composition.analyze", {"formula": "Al2O3"})
assert response.status == "ok", response.error
print(response.result)
```

## Initial tool catalog

| Tool | Purpose |
| --- | --- |
| `composition.analyze` | Element counts, atomic/mass fractions and formula molar mass |
| `crystal.density` | Density from formula, formula units and unit-cell volume |
| `mechanics.isotropic_moduli` | Convert Young's modulus and Poisson ratio into isotropic moduli |
| `mechanics.elastic_vrh` | Stability validation and Voigt/Reuss/Hill aggregate elastic properties |
| `mixtures.scalar_bounds` | Scalar arithmetic/harmonic mixture estimates using volume fractions |
| `thermal.linear_expansion` | Constant-coefficient, small-strain linear thermal expansion |
| `kinetics.arrhenius_diffusivity` | Diffusivity from an Arrhenius prefactor and activation energy |

Discover the installed schemas instead of guessing argument names. Tool versions are independent of the package version. Requests may set `tool_version` to reject an incompatible implementation. Formula syntax is deliberately bounded; descriptors list the accepted syntax. Elastic stiffness uses the engineering Voigt ordering `xx, yy, zz, yz, xz, xy` with doubled shear strains. Calculation units are explicit in inputs and outputs.

Input hashes identify canonical validated inputs, including defaults. Record the tool name/version and software versions alongside the hash for reproducibility. Timestamps identify execution time; they are not part of the input hash. Scientific references explain the model, while numerical tolerances and assumptions are declared in descriptors or source documentation.

No tool downloads data or launches external jobs. Predictions and expensive simulation adapters will have separate contracts when implemented. Model assumptions and warnings must be considered before applying outputs to an engineering decision.

## Contributing and hourly development

[AGENTS.md](AGENTS.md) specifies the completion criteria for AI contributors. [BACKLOG.md](BACKLOG.md) is the persistent queue, and [RUN_LOG.md](RUN_LOG.md) records verified work. [The hourly task specification](docs/HOURLY_TASK.md) contains a schedule and prompt ready for a ChatGPT automation with GitHub and execution access. The specification is a setup artifact; it does not itself schedule any job.

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The exact development dependency resolution is committed in `uv.lock`. CI checks supported Python versions. Add scientific reference cases and explicit domain limits alongside each calculation.
