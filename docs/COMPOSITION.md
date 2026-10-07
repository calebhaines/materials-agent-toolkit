# Fractional compositions

`composition.from_fractions` describes an alloy or elemental mixture using an explicit fraction map. It is available through the Python registry, JSON CLI and optional MCP server. The independent tool version is `1`.

## Inputs and normalization

| Field | Meaning |
| --- | --- |
| `fractions` | Nonempty map of case-sensitive elemental symbols to finite, nonnegative numbers; at most 118 entries |
| `basis` | Required: `atomic` for relative numbers of atoms or `mass` for relative masses |
| `normalization` | `require_unity` by default; `normalize` explicitly accepts relative weights or percentages |

With `require_unity`, the original total must be within an absolute tolerance of `1e-8` of one. Accepted inputs are divided by their actual total before calculation. With `normalize`, any positive finite total is accepted and divided out. The result's `input_total` records the original total in either mode. Input values have no implied percentage convention: a total of 100 requires explicit normalization.

Zero entries are allowed and omitted from both output maps. At least one entry must be positive. Only canonical natural-element symbols are supported: no formulas, isotope labels, `D`/`T` aliases, charges, whitespace, or case correction. Boolean values, numeric strings, negative values, unknown fields and non-finite values are rejected. The original total and all nonzero converted fractions must remain representable as positive finite binary64 numbers; inputs causing overflow or loss of a positive component produce a structured domain error.

Binary64 arithmetic can slightly overshoot a physical endpoint. A derived fraction exceeding one by at most four floating-point ulps at one is clamped to one. Mean atomic mass is similarly clamped to a participating elemental mass endpoint only when an overshoot is within four ulps at that endpoint. Larger excursions are rejected. These rounding corrections do not remove positive trace components.

## Scientific convention

For atomic fractions `x_i` and atomic weights `M_i`, mass fractions are `w_i = x_i M_i / sum_j(x_j M_j)`. For mass fractions, atomic fractions are `x_i = (w_i / M_i) / sum_j(w_j / M_j)`.

`mean_atomic_mass_g_mol` is `sum_i(x_i M_i)`: grams per mole of atoms in the mixture. For mass fractions it is equivalently `1 / sum_i(w_i / M_i)`. This differs from formula-unit molar mass: water has a mean atomic mass near `18.015 / 3 = 6.005 g/mol of atoms`, while `composition.analyze` reports the water formula-unit molar mass near `18.015 g/mol`.

The tool does not infer integer atom counts, a formula, phases, density, or alloy properties. Atomic weights come from the installed `periodictable` table, and outputs identify its version. Conventional terrestrial isotope abundances are used where available; representative isotope masses may be used for elements without standard atomic weights. Isotopically enriched materials require another mass convention. The response carries these warnings, scientific references, dependency versions and a hash of the validated inputs including defaults. The hash preserves the supplied weights; equivalent compositions supplied at different scales have different input hashes.

## Examples

Equiatomic NiTi:

```json
{"tool":"composition.from_fractions","input":{"fractions":{"Ni":0.5,"Ti":0.5},"basis":"atomic"}}
```

This returns equal atomic fractions, different mass fractions and a mean atomic mass near `53.2802 g/mol of atoms`.

Brass with 70 wt% copper and 30 wt% zinc:

```json
{"tool":"composition.from_fractions","input":{"fractions":{"Cu":70,"Zn":30},"basis":"mass","normalization":"normalize"}}
```

The output mass fractions are `0.7` and `0.3`, and the atomic fractions account for the different copper and zinc atomic weights. `input_total` is `100`.

Run the bundled requests:

```sh
uv run matkit run < examples/niti-composition.json
uv run matkit run < examples/brass-composition.json
uv run matkit describe composition.from_fractions
```

For an MCP call, use `composition.from_fractions` as the tool name and pass the `input` object directly as arguments.

Reference mass conventions: [periodictable mass data](https://periodictable.readthedocs.io/en/latest/api/mass.html) and [CIAAW atomic weights](https://ciaaw.org/atomic-weights.htm). Numerical tests use independently stated elemental weights, formula-composition equivalence and conservation/round-trip checks with tolerances reflecting the precision of those values.
