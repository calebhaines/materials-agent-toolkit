# Evidence-aware property screening

`screening.evaluate` compares supplied material-property records with explicit constraints. It is an offline tool available through Python, the JSON CLI and optional MCP server; its independent version is `1`.

The discovery studies repeatedly needed the same distinction: a composition calculation, a literature value under particular conditions, and a missing measurement cannot answer the same engineering question. This tool makes that distinction explicit, converts supported units, retains source and condition records, and returns `pass`, `fail` or `unknown` for every check. It does not obtain property data, verify citations, predict missing properties or rank candidates.

## Run the examples

Both examples contain **synthetic supplied data**, not measurements or predictions of actual materials. Their evidence labels exercise the interface; a `measurement` label in a fixture does not establish that an experiment occurred.

```sh
uv run matkit describe screening.evaluate
uv run matkit run < examples/screening/measured-only.json
uv run matkit run < examples/screening/calculation-allowed.json
```

```python
import json
from pathlib import Path

from materials_agent_toolkit.registry import run_tool

request = json.loads(
    Path("examples/screening/calculation-allowed.json").read_text(encoding="utf-8")
)
response = run_tool(request["tool"], request["input"], tool_version=request["tool_version"])
assert response.status == "ok", response.error
print(response.result["summary"])
for candidate in response.result["candidates"]:
    print(candidate["candidate_id"], candidate["status"], candidate["checks"])
```

For MCP, call `screening.evaluate` with the request's `input` object as arguments. Batch requests use the same request envelope; see [batch usage](BATCH.md).

The measured-only example produces two `unknown` candidates. One lacks thermal-conductivity data and has a manufacturer record that the default evidence policy excludes. The other has a synthetic declared measurement range that crosses the conductivity threshold. The calculation-allowed example produces one `pass`, one `fail` and one `unknown` under an explicitly permitted theoretical-capacity calculation. Its pass is a match to the supplied calculation and criteria, with no conclusion about experimental battery performance.

## Property records and constraints

An input contains 1–100 `candidates` and 1–20 `constraints`. Each candidate has a unique `candidate_id` and a `properties` map containing at most 32 records. Omit an unavailable property; a missing measurement is not a zero. One record per property key avoids silently combining different sources, specimens or methods.

Each property record specifies:

| Field | Meaning |
| --- | --- |
| `quantity`, `value`, `unit` | Supported physical quantity, finite supplied number, and literal unit symbol |
| `evidence_kind` | `measurement`, `manufacturer`, `calculation` or `assumption` |
| `source` | Required `citation` and optional `locator`, such as a table, specimen or model version |
| `conditions` | Optional map of explicit context tags, for example `temperature: "20 degC"` or `method: "declared_model_v1"` |
| `interval` | Optional `{lower, upper, basis}` containing the supplied value |

The `interval` is a caller-supplied possibility range. Its `basis` should explain its origin, such as stated measurement bounds or a declared model scenario. The tool assigns no probability or confidence level and does not construct an interval from a point value. A point without an interval is checked as the degenerate range `[value, value]`.

Each constraint identifies a unique `constraint_id`, a `property_id`, the `quantity`, a compatible `unit`, and at least one of `minimum` or `maximum`. Bounds are inclusive. It may also specify `required_conditions` and `allowed_evidence`. The default evidence policy is **`["measurement"]`**. Calculations, manufacturer information and assumptions must be allowed explicitly when they are intended to answer that criterion.

Property identifiers carry meaning separately from units. For example, `theoretical_capacity` and `reversible_capacity` can both have quantity `specific_capacity`, but a record for one cannot satisfy a constraint for the other. Use distinct identifiers for different material states or property definitions. Sharing dimensions does not establish interchangeability. All uses of one property identifier across the request must specify the same quantity; conflicting quantities or incompatible units reject the request rather than becoming missing evidence.

Condition matching checks that every required key/value pair occurs exactly in the supplied record. Additional record tags are retained. The tool does not interpret temperatures, translate synonymous method names, validate specimen equivalence or decide whether extra tags make a record applicable. For example, the condition strings `"20 degC"` and `"293.15 K"` do not match even though the separately supported numeric temperature conversion relates those values. Declare the conditions that matter and use consistent tags.

## Decision rules

Checks follow this order:

| Situation | Status | Reason |
| --- | --- | --- |
| Property absent | `unknown` | `missing_property` |
| Evidence kind not allowed | `unknown` | `evidence_not_allowed` |
| A required condition tag is absent or differs | `unknown` | `condition_mismatch` |
| Entire point/range is inside the inclusive limits | `pass` | `within_bounds` |
| Entire point/range is below the minimum or above the maximum | `fail` | `outside_bounds` |
| Range crosses a limit | `unknown` | `interval_overlaps_bound` |

A candidate is `fail` if any check fails, otherwise `unknown` if any check is unknown, otherwise `pass`. All checks are preserved, including unknown checks on a failed candidate. Input ordering is retained for candidates, constraints and checks. The summary counts total, passed, failed and unknown candidates; there is no winner or ranking.

Every result retains the supplied property value/unit, `source`, `conditions` and interval, plus `normalized_value`, `si_unit` and any `normalized_interval`. Normalized constraints retain the supplied bounds/unit and include `normalized_minimum`, `normalized_maximum` and `si_unit`. Check `property_id` links back to the corresponding record. The standard response envelope also records the validated input hash, tool/software versions, references and warnings. A result-level pass only matches the declared supplied evidence and criteria; it is not verification of that evidence or a material's fitness for use.

## Units and numerical limits

Conversions use `SI value = factor × supplied value + offset`. Intervals and constraint bounds undergo the same conversion. Accepted symbols are exact and case-sensitive; aliases are not inferred. The input schema publishes the complete supported map as `x-quantity-unit-map` for automated discovery.

| Quantity | SI unit | Accepted input symbols and conversion factors |
| --- | --- | --- |
| `density` | `kg/m3` | `kg/m3`: 1; `g/cm3`, `g/mL`: 1000 |
| `elastic_modulus` | `Pa` | `Pa`: 1; `kPa`: 1000; `MPa`: 10⁶; `GPa`: 10⁹ |
| `thermal_conductivity` | `W/(m*K)` | `W/(m*K)`: 1; `W/(cm*K)`: 100 |
| `linear_expansion_coefficient` | `1/K` | `1/K`, `1/degC`: 1; `microstrain/K`: 10⁻⁶ |
| `specific_capacity` | `C/kg` | `C/kg`: 1; `Ah/kg`, `mAh/g`: 3600 |
| `mass_fraction` | `1` | `1`: 1; `%`: 0.01 |
| `length` | `m` | `m`: 1; `cm`: 0.01; `mm`: 0.001; `um`: 10⁻⁶ |
| `area` | `m2` | `m2`: 1; `cm2`: 10⁻⁴; `mm2`: 10⁻⁶ |
| `volume` | `m3` | `m3`: 1; `L`: 0.001; `mL`, `cm3`: 10⁻⁶ |
| `mass` | `kg` | `kg`: 1; `g`: 0.001; `mg`: 10⁻⁶ |
| `time` | `s` | `s`: 1; `min`: 60; `h`: 3600 |
| `temperature` | `K` | `K`: factor 1, offset 0; `degC`: factor 1, offset 273.15 |
| `diffusivity` | `m2/s` | `m2/s`: 1; `cm2/s`: 10⁻⁴ |
| `dimensionless` | `1` | `1`: 1 |

The [BIPM SI Brochure, ninth edition](https://www.bipm.org/en/publications/si-brochure) defines the SI quantities and Celsius relationship. Capacity conversion follows directly from charge and mass units: `1 mAh/g = (10⁻³ Ah)/(10⁻³ kg) = 1 Ah/kg = 3600 C/kg`. Thus `200 mAh/g = 720000 C/kg`. This conversion changes units, not theoretical capacity into reversible capacity or any other property definition.

Supplied density, elastic modulus and thermal conductivity values and interval endpoints must be strictly positive. Specific capacity, length, area, volume, mass, time and diffusivity are nonnegative. Absolute temperature must be nonnegative after conversion to kelvin. Mass fractions must fall within `[0, 1]` after conversion. Linear expansion coefficients and dimensionless values may be signed. These domains describe the named quantities, not signed changes of density or other positive quantities. Constraint thresholds may be any finite number; an intentionally impossible criterion remains meaningful.

Unknown fields, booleans as numbers, numeric strings and nonfinite values are rejected. Intervals require `lower <= value <= upper`; two-sided constraints require `minimum <= maximum`. Nonzero conversion underflow to zero, overflow and nonfinite converted results produce structured input/domain errors. Comparisons use binary64 arithmetic with no tolerance or display rounding; values extremely close to a boundary can be affected by representational rounding. To express a range of plausible values, supply an interval and its basis rather than rely on an unstated numerical margin.

Identifiers match `^[A-Za-z][A-Za-z0-9_.-]{0,63}$`. Conditions contain at most 16 tags. Citations, locators, condition values and interval bases must be nonblank and at most 2000 characters. Evidence policies contain 1–4 unique entries. Duplicate candidate or constraint identifiers are rejected.

## Using research results responsibly

Preserve each source's property definition, sample state, measurement conditions and limitations. Source citations and evidence labels remain caller assertions: the toolkit neither retrieves publications nor authenticates them. Manufacturer claims do not become measurements through unit conversion, a model calculation does not become an observation, and a failed evidence policy means `unknown`, not poor material performance.

For the existing research studies, use distinct identifiers for ideal redox-reservoir capacity and measured reversible capacity; distinguish constituent conductivity from a composite's measured conductivity; and leave unperformed water-containment or biodegradation measurements absent. A water uptake mass fraction cannot stand in for leakage, and specimen mass loss cannot establish polymer mineralization. Schema validation improves bookkeeping; selecting the correct evidence and engineering criterion remains essential.
