# Lightweight heat-spreader composite screening

This experiment uses the existing toolkit to propose aluminum–ceramic composite recipes for laboratory validation. It does not introduce a property predictor or add a scientific tool to the catalog. The selected family combines pure Al with SiC, AlN and/or alumina. Published examples of these families exist; chemical novelty, a viable processing route and actual performance are unverified.

The objective is to retain useful heat conduction while increasing stiffness per unit mass and reducing thermal-expansion proxies. The screen searches a 1 volume-percent grid with 5–35% total ceramic loading and at least 65% aluminum. All 8,401 compositions are evaluated against four declared gates: density at most 3,000 kg/m³; the ideal tensor-Reuss Young-modulus endpoint divided by density at least 32 GPa/(g/cm³); ideal harmonic thermal conductivity at least 190 W/(m·K); and the larger of two CTE proxies at most 18 × 10⁻⁶/K. These thresholds are engineering screening choices, not measured property requirements for a qualified product.

Run from the repository root with the base package installed:

```sh
uv run --no-sync python experiments/lightweight_composites/screen.py
```

The [inputs](inputs.json) contain the property subset, source URLs, grades, units, access dates, temperature notes, gates and sensitivity scenarios. No network access is needed to run the study. The script writes deterministic nominal candidate data, a compressed table for all scenarios and summary results, plus selected actual toolkit responses with scientific input hashes, execution timestamps and software/reference provenance. Response snapshots identify the environment used for generation. `--check` compares their scientific content while excluding runtime-specific timestamps/version fields, and verifies numerical artifacts without overwriting them. It checks this experiment's artifacts rather than replacing the toolkit's catalog check.

Historical package versions remain recorded in response provenance and summary metadata. Read-only replay accepts a different installed package version while still checking scientific content and tool contract versions; it does not rewrite earlier recordings.

## Constituent evidence

| Phase / source grade | Density kg/m³ | E GPa | ν | Conductivity W/(m·K) | CTE 10⁻⁶/K |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pure Al, handbook-backed secondary table | 2700 | 70.2 | 0.345 | 237 | 23.1 |
| SiC, CeramaSil-C | 3100 | 350 | 0.14 | 102.6 | 4.02 |
| AlN, PCAN1000S substrate | 3300 | 320 | 0.22 | 170 | 4.6 |
| Alumina, CeramAlox 99.7% | 3950 | 370 | 0.23 | 33 | 6.5 |

Al data are from [Matmake's handbook-backed table](https://matmake.com/materials-data/aluminum-properties.html). Its independently listed shear/bulk moduli are inconsistent with the selected E and ν, so the toolkit derives both from the latter pair. Ceramic data come from Precision Ceramics' [SiC page](https://precision-ceramics.com/materials/silicon-carbide/), [AlN datasheet](https://precision-ceramics.com/wp-content/uploads/Aluminum-Nitride-PCAN1000S-Technical-Data-Sheet.pdf) and [alumina datasheet](https://precision-ceramics.com/wp-content/uploads/Alumina-99.7-Technical-Data-Sheet.pdf). Only this small factual subset is reproduced with attribution; no open license for the complete supplier documents is asserted.

SiC E = 350 GPa is the lower endpoint of the supplier's 350–400 GPa range. AlN E = 320 GPa comes from its PDF, while the [same-grade web table](https://precision-ceramics.com/materials/aluminum-nitride/) gives 350 GPa. The source-high scenario uses SiC 400 GPa and AlN 350 GPa. The disagreement is not a certified measurement interval. Supplier values describe typical consolidated grades, including a substrate grade, and are not guaranteed reinforcement-powder values.

Al's CTE is instantaneous at 25°C, while all selected ceramic PDF CTEs are means over 25–400°C. The alumina web page instead labels its CTE interval 25–300°C. Al conductivity is at 27°C; ceramic web tables specify 25°C, although the AlN/alumina PDFs omit that temperature. Mechanical temperatures are unspecified for the ceramics and assumed ambient for screening. Those mismatches limit every thermal interpretation.

## Models and actual library calls

`composition.analyze` supplies constituent stoichiometry and `mechanics.isotropic_moduli` converts each sourced E/ν pair to bulk modulus K and shear modulus G. For each composition, `mixtures.scalar_bounds` computes separate arithmetic/harmonic K and G endpoints and Fourier-conduction endpoints using **phase volume fractions**. Effective isotropic Young-modulus endpoints follow `E = 9KG/(3K+G)`. This is the tensor Voigt/Reuss construction for isotropic phases. Directly averaging E arithmetically is not generally the tensor-Voigt result when Poisson ratios differ.

Density is `rho = sum_i(v_i rho_i)`. Phase mass fractions are `w_i = v_i rho_i / rho`; selected recipes are converted into ideal elemental mass/atomic fractions through the composition tools. This estimate ignores commercial-grade additives, impurities and processing reactions. The material remains a multiphase composite; a combined elemental fraction map does not identify an alloy phase.

The volume-average CTE proxy is `sum_i(v_i alpha_i)`. The Turner proxy is `sum_i(v_i K_i alpha_i) / sum_i(v_i K_i)`, a hydrostatic compatibility approximation from [Turner (1946), “Thermal-expansion stresses in reinforced plastics”](https://doi.org/10.6028/jres.037.015). Their maximum is a two-model screening rule, **not a rigorous CTE upper bound**. An illustrative `thermal.linear_expansion` call uses a 100 mm specimen and a 25 K temperature change; it only evaluates each assumed constant coefficient.

Elastic endpoints assume stable isotropic phases, perfect bonding, zero porosity and retained phase fractions. Conductivity endpoints assume linear Fourier transport and perfect thermal contact. Interface resistance, pore networks or reaction layers can invalidate applying their lower endpoints to fabricated specimens. No strength, toughness, fatigue, temperature-dependent constitutive law or process kinetics is inferred.

## Scenarios, controls and reproducibility

The source-high case is a comparison between sourced values. Additional stress cases soften the Al modulus by 5%, reduce all constituent conductivities by 10%, increase densities by 2%, increase CTE proxies by 10%, and apply those stresses jointly. These are hypothetical deterministic perturbations, with no assigned probabilities or calibrated confidence intervals. Scaling phase conductivities is not a model of interface resistance. The script records scenario counts and each nominated recipe's gate margins, including failures.

Nominal feasible recipes are ranked by minimum total ceramic loading, then maximum harmonic conductivity, then maximum specific Reuss modulus, with deterministic composition tie-breaking. The report compares the selected hybrid with pure Al and each single-ceramic control at exactly the same total reinforcement loading. This prevents changing loading from masquerading as a hybrid-composition benefit. Analytical checks independently average complete isotropic stiffness/compliance tensors, verify phase limits, mass conservation, Fourier means, grid completeness and read-only artifact checking.

The numerical results and tradeoff plot are in [REPORT.md](REPORT.md). The [prior-art review](PRIOR_ART.md) records what was actually checked and why this study cannot establish novelty. Candidate ranking is conditional on this deliberately small design space; it is not a global optimum over all materials or processes.

To regenerate the plot in an environment with matplotlib installed (included with the locked `structures` extra):

```sh
uv run --no-sync python experiments/lightweight_composites/plot.py
```

The plotting step is optional; the base package can run the scientific screen without ASE, MCP or matplotlib. PNG and SVG outputs are committed for reading and export.
