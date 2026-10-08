# Home-processable biopolymer investigation

This investigation compares purchased polycaprolactone (PCL), exploratory PCL/native-starch feeds, and ingredient-made alginate/glycerol/wax films. It addresses cool-water containment and low-temperature home processing. **No specimens have been manufactured or tested in this study, and no new waterproof, home-compostable plastic has been established.**

The best-supported first prototype is plain purchased PCL formed in the manufacturer's hot-water process. It is an existing polyester, not a polymer synthesized at home. Its literature-supported biodegradation under specific conditions does not establish rapid decomposition or home-compostability of a particular article.

Read the [findings](REPORT.md), [practical protocol](HOME_PROTOCOL.md), [process review](PROCESS_REVIEW.md) and [prior art](PRIOR_ART.md). Source URLs, retrieval evidence and hashes are in [sources.json](sources.json). The methods and numerical data are separate from the production tool catalog.

## Reproduce the planning calculations

From the repository root with the base package installed:

```sh
uv run --no-sync python experiments/home_biopolymers/study.py
uv run --no-sync python experiments/home_biopolymers/study.py --check
```

The calculation is offline and uses only the base library. Frozen [inputs](inputs.json) define 13 nominal formulations and three planned replicates each. Actual `composition.analyze` calls provide seven formula inventories; actual `composition.from_fractions` calls check the elemental feed for each formulation. All **20 complete responses** retain tool versions, validated input hashes, timestamps, references and software provenance.

The generated artifacts are:

- [formulations.csv](results/formulations.csv): 13 ideal feed budgets, without material-property predictions.
- [summary.json](results/summary.json): formula masses, design assumptions and explicitly unmeasured status.
- [tool-records.json](results/tool-records.json): actual execution envelopes and their exact requests.
- [measurements-template.csv](results/measurements-template.csv): 39 planned trial records with actual observations left blank.

Copy the measurement template before recording results; regeneration writes the blank planning template. Never enter an inferred result as an observation. The three replicate rows represent independent trials only if preparation is independent; otherwise label them as shared-batch specimens in the notes.

`--check` never overwrites files. It checks deterministic numerical/template bytes, validates stored response completeness and request hashes, and compares scientific snapshots while retaining their original runtime timestamps and host versions. No network retrieval or physical testing occurs during either command.

## Scientific basis

PCL uses the ideal repeat formula `C6H10O2`, starch `C6H10O5`, and sodium alginate `C6H7NaO6`. They are repeat inventories, not full polymer molar masses or descriptions of molecular weight, crystallinity, chain ends, additives, moisture or structure. Glycerol is `C3H8O3`. Natural-element masses come from the locked periodictable table.

PCL trials use nominal 50 g dry-solids targets: 50/0, 47.5/2.5 and 45/5 g PCL/starch. Household starch has unknown residual moisture; actual weighed powder is not a verified dry-starch mass. Native starch is particulate filler here, not thermoplastic starch.

Nine alginate plans use 2 g sodium alginate, glycerol at 0.1/0.2/0.3 g per gram of polymer, and 0/0.2/0.4 g beeswax coating feed over a planned 100 cm² sheet. Each has a separate fresh bath of 2 g calcium lactate pentahydrate and 98 g water. An additional untreated, uncoated alginate control uses 2 g polymer and 0.4 g glycerol. Casting water is 100 g per alginate batch.

Elemental alginate budgets cover **only the initial sodium-alginate/glycerol feed**. Beeswax is a mixture of unknown elemental composition and is recorded separately; bath ingredients and casting water are excluded. The total non-water formulation feed is not final dry-film mass. Calcium uptake, sodium release, glycerol loss, moisture and retained wax are unknown.

For documented pentahydrate, `Ca(C3H5O3)2(H2O)5` has the same elemental inventory as the usual hydrate-dot notation, which the toolkit's bounded formula parser excludes. The available bath calcium is `m_salt/M_salt`; initial carboxylate sites are `m_alginate/M_repeat`. The inventory ratio `2 n_Ca/n_sites` is **available bath inventory**, not measured crosslink fraction, uptake or completed reaction. Confirm the salt's hydration state on its packaging; anhydrous salt is not equivalent gram-for-gram.

No water-vapor transport, liquid-water permeability, strength, crosslink-density, biodegradation or processing-success model is present. Composition arithmetic cannot supply those outputs. There is no numerical ranking or nominated new material; results remain unmeasured until an empirical test is recorded.
