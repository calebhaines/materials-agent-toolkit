# Manganese oxyfluoride battery-cathode screening

This offline discovery experiment explores lithium-ion cathode compositions in `Li2Mn_(1-t-n)Ti_tNb_nO2F`. It uses the toolkit to calculate elemental compositions and masses, then performs explicitly declared charge bookkeeping. It nominates composition hypotheses in an established research family; no new material, phase, property predictor or experimentally improved battery is claimed.

## Reproduce the experiment

From the repository root, with the base package installed:

```sh
uv run --no-sync python experiments/manganese_oxyfluorides/screen.py
uv run --no-sync python experiments/manganese_oxyfluorides/screen.py --check
```

The screen runs offline and requires neither ASE, MCP nor matplotlib. The frozen [inputs](inputs.json) specify the family, oxidation-state assumptions, grid, screening gates and scenarios. Source retrieval is separate from calculation: [sources.json](sources.json) records evidence levels and document hashes, while [PRIOR_ART.md](PRIOR_ART.md) explains known controls, related compositions and the limits of the literature search.

The script writes a 331-row candidate CSV, a numerical summary and complete actual response snapshots for both toolkit calls at every composition. CSV and summary bytes are deterministic under the locked scientific dependencies. The 662 stored responses retain actual execution timestamps, validated input hashes, software versions and scientific references. `--check` validates snapshot completeness, timezone-aware timestamps and request hashes before comparing scientific content without runtime timestamps or host version fields. It reruns the calculations and never overwrites artifacts. Run this experiment's check separately from the tool catalog check.

Optional plotting uses matplotlib, included with the locked `structures` extra:

```sh
uv run --no-sync python experiments/manganese_oxyfluorides/plot.py
```

Standalone PNG/SVG figures and the findings are committed in [REPORT.md](REPORT.md). No package version, dependency, production tool or catalog contract changes are part of this experiment.

## Model and scientific acceptance criteria

Let `t = i/60` and `n = j/60` be the Ti and Nb coefficients on the one-metal-per-formula composition basis. These are not mass fractions, volume fractions or fractions of all cations. The assumed species are Li(+1), Ti(+4), Nb(+5), O(-2), F(-1), and initial average Mn between +2 and +3. Charge neutrality gives:

```text
v_Mn = (3 - 4t - 5n) / (1 - t - n)
2 <= v_Mn <= 3  =>  2i + 3j <= 60
```

The exact integer constraint produces 331 recipes, including the pure-Mn comparator and both published Ti/Nb controls. Formula parsing uses positive integer counts, reduced by their greatest common divisor. An integer formula represents nominal composition only; it is neither a crystal structure nor an asserted supercell.

Assuming all Mn can be oxidized to +4 while Ti and Nb remain spectators, the formal manganese electron reservoir is:

```text
electrons per normalized formula = (4 - v_Mn)(1 - t - n) = 1 + n
Q_Mn [mAh/g] = F(1 + n) / (3.6 M)
```

Here `M` is grams per mole of pristine normalized `Li2Mn_(1-t-n)Ti_tNb_nO2F`, and `F = e N_A = 96485.33212331001 C/mol` using exact SI defining constants. The factor 3.6 converts coulombs to mAh. Each normalized formula contains six atoms. Natural-abundance atomic masses come from the toolkit's locked periodictable table; this convention is not an isotopically enriched calculation.

For every recipe, an actual `composition.analyze` call supplies the integer-formula mass and elemental fractions. An actual `composition.from_fractions` call independently converts the unreduced integer atom weights with explicit atomic basis and normalization. Dividing the formula mass by its formula scale must match six times the mean atomic mass; both elemental mass-fraction maps must agree. The maximum observed relative mass difference is 2.4e-16. Charge balance, the electron reservoir and remaining formal Li inventory are calculated with exact rational composition arithmetic before conversion to floating point.

Preset gates are **ideal Mn-only capacity at least 250 mAh/g** and **Nb at most 15% by mass**. These are design choices for this experiment, not experimentally qualified requirements or a cost model. Rank passing recipes by least Nb mass fraction, then greatest ideal capacity, then deterministic Ti/Nb grid counts. A separate minimum-relative-gate-margin comparison exposes the consequences of this ranking. Verification must cover independent charge/capacity oracles, endpoint controls, grid completeness, atom/mass conservation, exact gate boundaries, provenance and read-only artifact drift checks.

## Interpretation and next evidence

Formal capacity is the assumed Mn redox reservoir per gram of pristine active material. It is not delivered reversible capacity, electrode/cell capacity, energy density or power. Oxygen redox can add charge beyond the Mn-only reservoir; this calculation does not model its reversibility. Literature also reports Ti(+3) in some related compositions, so fixed Ti(+4) is an assumption rather than a measured assignment for every grid point.

The additional scenarios access 90%, 80% or 70% of the same formal Mn electron reservoir. They are hypothetical deterministic scalings without probabilities, calibrated uncertainty or predictions of actual utilization. Failing a scenario does not establish physical material failure. The model contains no voltage, phase stability, defect chemistry, diffusion, structural disorder, synthesis, safety or cycle-life prediction. Because no atomic configuration or lattice is established, structure/density tools are not used to manufacture an apparent crystal prediction.

Follow-up needs phase and local-valence characterization, competing-phase/disorder calculations and lithium-migration evidence. Candidate/control electrochemical comparisons must share synthesis and electrode conditions. Broader exact-formula and patent searches are required before making a novelty claim.
