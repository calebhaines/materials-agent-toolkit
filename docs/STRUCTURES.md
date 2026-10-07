# Ordered CIF crystal analysis

`structure.analyze_cif`, tool version `1`, parses one ordered crystal from supplied CIF 1.x text using ASE. It validates the cell and sites, expands the supplied crystallographic symmetry, and calculates the ideal full-occupancy cell density. Python, CLI and MCP use the same registry implementation.

## Installation and invocation

```sh
uv sync --locked --extra structures
uv run --no-sync matkit describe structure.analyze_cif
uv run --no-sync matkit run < examples/structures/al-fcc.json
```

For an MCP installation, select both `--extra mcp --extra structures`. With pip, use `materials-agent-toolkit[structures]` or `-e '.[structures]'` from a checkout. ASE is optional; installing the base package still exposes all schemas and catalog descriptors. A call without ASE returns `MISSING_DEPENDENCY` with installation guidance. Input schema validation takes place before dependency loading.

```python
from pathlib import Path
from materials_agent_toolkit.registry import run_tool

response = run_tool(
    "structure.analyze_cif",
    {"cif_text": Path("tests/fixtures/structures/al_fcc.cif").read_text()},
)
assert response.status == "ok", response.error
assert response.result["atomic_counts"] == {"Al": 4}
```

The input has exactly one field, `cif_text`, a strict string of 1–100000 characters. The tool accepts text contents rather than a path or URL. It parses in memory, does not fetch data or run external jobs, and uses ASE's installed crystallographic data. ASE 3.29.0 is locked under the LGPL-2.1-or-later license; the `structures` extra records its transitive dependencies in `uv.lock`.

## Results and coordinate conventions

| Field | Meaning and units |
| --- | --- |
| `atom_count` | Number of atoms after symmetry expansion in the supplied cell |
| `atomic_counts` | Canonical element symbols mapped to full-cell counts |
| `symbols` | One canonical element symbol per expanded atom, in ASE expansion order |
| `cell_vectors_angstrom` | Three lattice vectors as rows `a`, `b`, `c`, in Å, in ASE's orientation |
| `fractional_positions` | Dimensionless coordinates in symbol order, wrapped to `[0,1)` |
| `cartesian_positions_angstrom` | Wrapped Cartesian coordinates in Å; each row equals fractional row multiplied by the cell matrix |
| `cell_volume_angstrom3` | Positive supplied-cell volume in Å³ |
| `density_kg_m3` | Ideal crystallographic density in kg/m³ |
| `atomic_weights_source` | Installed `periodictable` atomic-weight table version |
| `source_block` | Parsed block name without the `data_` prefix |

Density uses the expanded elemental counts: `rho = sum_i(n_i M_i) / (N_A V)`, with atomic weights converted from g/mol to kg/mol and volume converted using `1 Å³ = 1e-30 m³`. The exact SI Avogadro constant is `6.02214076e23 mol^-1`. This mass convention matches `crystal.density`; ASE's default mass array is not substituted. Conventional terrestrial isotope abundances are assumed where available, and library representative isotope masses are retained for other elements.

The supplied cell is preserved. No primitive-cell conversion, new symmetry inference, phase identification, bonding analysis or porosity correction is performed. CIF numeric uncertainty notation is interpreted by ASE as its central value; the output does not assign measurement or prediction uncertainty. Atomic-weight notices and retained ASE parser warnings appear in the common response's `warnings` array. Malformed parser input that would drop atom rows or overwrite duplicate tags is rejected.

## Accepted domain and bounds

- Exactly one block containing atom-site data is required. Additional nonstructural metadata blocks are allowed. CIF 2.0 syntax and incomplete structural blocks are rejected.
- Natural-element symbols must be canonical. Explicit type symbols cannot include charges, isotopes, dummy species or aliases such as `D` and `T`. If type symbols are absent, labels may append numeric or underscore identifiers to canonical symbols.
- Missing occupancy means one. Explicit occupancy must be known and within absolute tolerance `1e-8` of one; accepted near-unity values are normalized to full occupancy with a warning. Partial, mixed or disordered sites are unsupported.
- At most 256 asymmetric input sites and 2048 expanded atoms are allowed. Input-site count multiplied by symmetry-operation count must also be at most 2048 before expansion. This conservative upper bound includes redundant operations and may reject a structure with many special-position sites even when its actual expanded count would be smaller.
- All six cell parameters are required. Lengths must lie in `[1e-6, 1e6]` Å; angles are in degrees and strictly between 0 and 180. The geometry must be positive definite and the cell singular-value condition number must be at most `1e8`.
- Three complete finite fractional or Cartesian coordinate columns are required. If both are supplied, their periodic coordinates must agree. Coordinates are converted to the supplied cell and wrapped periodically.
- Supplied symmetry operations must form a closed group, include identity, have unimodular rotations and preserve the cell metric within absolute tolerance `1e-8` times its largest entry. Fractional translations are compared periodically with tolerance `1e-8`. Exact duplicate operations are deduplicated for group validation; distinct translations with the same rotation at periodic component distance at most `1e-8` are rejected as ambiguous.
- Declared number/name aliases must agree. Explicit operations paired with a declared space group must match ASE's standard operation set for its setting and origin; alternate-origin sets are rejected. Accepted operation rounding is normalized to the declared canonical operations for expansion, with a notice, so small rounding errors cannot split special-position sites. Complete explicit operation sets may also be supplied without group metadata, retaining their supplied origin. Absent symmetry means identity P1.
- Symmetry-equivalent repeated input sites are rejected using ASE's dimensionless componentwise site tolerance `1e-8`.

Schema violations return `INVALID_INPUT`; malformed CIF and unsupported scientific domains return `DOMAIN_ERROR`. A broken installed dependency is an internal failure rather than an instruction to install ASE. A failed call does not prevent subsequent registry, batch or MCP calls.

## Provenance and reference evidence

The response records the tool and package versions, Python version, ASE/SciPy/NumPy/periodictable versions, scientific references and SHA-256 of the validated input object. SciPy provides periodic nearest-neighbor queries for the bounded symmetry checks. The hash includes the exact CIF text, including comments and whitespace; physically equivalent differently formatted files have different hashes. Preserve software versions alongside the hash because parser behavior can change between library releases.

The authored [reference fixtures](../tests/fixtures/structures) carry CC0-1.0 notices and sources for their crystal prototypes or coordinate convention. FCC Al at rounded `a = 4.05 Å` expands to four atoms, `66.430125 Å³` and approximately `2697.8060695 kg/m³`. Rocksalt NaCl at rounded `a = 5.64 Å` expands to eight atoms and approximately `2163.6164248 kg/m³`. A synthetic triclinic H2O-stoichiometry cell has independently stated row vectors and volume exactly `24 Å³`; it is not an equilibrium ice reference.

Reference tests use relative tolerance `1e-12` for geometry and `1e-10` for densities, reflecting floating arithmetic and the stated atomic weights. Tests also cover lattice scaling, periodic translation, Cartesian/fractional consistency, independent `crystal.density` agreement, domain limits and Python/CLI/MCP parity. Additional structure formats, round trips, neighbors and broader symmetry analysis remain roadmap items.
