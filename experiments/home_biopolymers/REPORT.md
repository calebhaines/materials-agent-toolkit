# Finding a home-processable, water-resistant biodegradable plastic

**Plain purchased polycaprolactone (PCL) is the best-supported first prototype for cool-water containment and simple home forming.** The scoped literature review supports water insolubility, low-temperature forming and biodegradation under particular test conditions. It does not establish that a home-molded article is leak-free or rapidly home-compostable. No specimens have been made or tested here, and no novel material meeting all requirements has been confirmed.

The study turns that evidence into a reproducible **13-formulation experimental plan**, using **20 actual toolkit calls** for feed bookkeeping and **39 blank trial records**. It supplies a [practical prototype and test protocol](HOME_PROTOCOL.md), [process review](PROCESS_REVIEW.md), [prior-art assessment](PRIOR_ART.md) and [source manifest](sources.json). Every material-performance result remains unmeasured.

## Material choice and tradeoffs

| Route | Evidence supporting a trial | Unresolved requirements |
| --- | --- | --- |
| Plain purchased PCL | Manufacturer identifies PCL, reports water insolubility and gives a hot-water forming route at approximately 66°C. An existing thermoplastic can be reshaped without home polymer synthesis. | Actual containment, molding defects, repeated wet use and the disposal behavior of the particular grade and geometry. Hot-service and food-contact suitability are not established. |
| PCL with 5% or 10% native starch | A bounded comparison against plain PCL; starch/polyester blends are established prior art. | Hand incorporation at the supplier's forming temperature is unvalidated. Starch moisture, agglomerates and weak interfaces may worsen leakage or integrity. No improvement in complete-polymer biodegradation is predicted. |
| Calcium-treated alginate/glycerol with beeswax coating | Aqueous polysaccharide-film preparation and wax barrier approaches have relevant literature. An untreated alginate control and uncoated treated variants help distinguish treatment effects. | Alginate can swell despite calcium treatment. Coating defects, edges, bending and leaching can undermine liquid-water resistance. The proposed cold-cast, bath-treated, surface-coated recipe is not a reproduced literature method. |

PCL is a purchased polymer rather than a pantry-ingredient plastic synthesized at home. That distinction matters: it offers a supported fabrication route, while an ingredient-made alginate film remains a less-supported candidate for continuous water exposure. None of these established material families is a newly discovered polymer.

The initial target is a **non-food-contact prototype at 20–25°C, under a 5 cm water head for 24 hours**. This is a test definition, not an observed achievement or a universal waterproof standard. A splash-only application would require a different acceptance test. Food packaging or drinking-water use requires separate material and regulatory evidence.

## Reproducible formulation plan

The frozen [inputs](inputs.json) contain three PCL feeds, nine treated alginate plans and one untreated alginate control. Amounts describe **nominal initial feeds**, not final retained material or measured dry article mass.

| PCL formulation | PCL feed | Nominal dry starch feed | Role |
| --- | ---: | ---: | --- |
| PCL_S00 | 50 g | 0 g | First prototype and matched-process control |
| PCL_S05 | 47.5 g | 2.5 g | Exploratory 5 wt% filler |
| PCL_S10 | 45 g | 5 g | Exploratory 10 wt% filler |

Household starch has unknown moisture unless measured. Adding native starch to softened PCL does not turn it into thermoplastic starch. Published TPS/PCL specimens use plasticized starch, high-shear mixing at 120°C and pressing at 130°C; they do not validate hand kneading at 66°C.

Each of the nine treated alginate plans has **2 g sodium alginate and 100 g casting water**, with the following full factorial design:

| Glycerol/polymer mass ratio | Glycerol feed | Beeswax coating-feed variants |
| --- | ---: | --- |
| 0.10 | 0.2 g | 0 / 0.2 / 0.4 g |
| 0.20 | 0.4 g | 0 / 0.2 / 0.4 g |
| 0.30 | 0.6 g | 0 / 0.2 / 0.4 g |

The coating plan covers a nominal 100 cm² sheet, sharing feed between both faces and edges. The area used in the bookkeeping is the sheet's projected area, not the combined surface area. Coating transfer and retained wax must be measured. Each treated formulation uses a separate fresh bath containing **2 g calcium lactate pentahydrate and 98 g water**. `ALG_UNTREATED` has 2 g alginate, 0.4 g glycerol and 100 g casting water, with no calcium bath or wax. Three trial rows per formulation are planned; independent preparation is needed before calling them independent replicates.

The whole alginate batch initially occupies roughly a 1 cm wet layer over 100 cm², requiring a retaining mold and potentially slow ambient drying. This is another process-feasibility question, not evidence of easy manufacture. Aliquot casting or a larger mold must be recorded with actual transferred feed and area; the nominal whole-batch budgets cannot be assigned unchanged to a smaller coupon.

## What the library actually calculated

Seven `composition.analyze` calls supply ideal formula inventories, and thirteen `composition.from_fractions` calls check elemental feed conversion. All [20 complete responses](results/tool-records.json) retain validated input hashes, tool versions, actual execution timestamps and software provenance. These are real calculations, not simulated experimental observations.

The ideal repeat formulas are PCL `C6H10O2`, starch `C6H10O5` and sodium alginate `C6H7NaO6`; glycerol is `C3H8O3`. Repeat inventories omit chain ends, molecular-weight distributions, crystallinity, additives and moisture. Alginate elemental budgets cover only initial alginate and glycerol: bath ions, casting water and the unknown elemental composition of beeswax are excluded and accounted for separately. The nominal non-water formulation total is therefore neither a final-film mass nor an elemental description of a treated coated article.

Using the locked natural-element masses:

- Calcium lactate pentahydrate, `Ca(C3H5O3)2(H2O)5`, has molar mass **308.293 g/mol**. A 2 g feed supplies approximately **6.4873 mmol available calcium**.
- The 2 g initial sodium-alginate feed contains approximately **10.0956 mmol nominal carboxylate sites**.
- The ratio `2 n_Ca / n_sites` is approximately **1.28518**. It is an available bath inventory ratio, not calcium uptake, crosslink fraction, reaction completion or film performance.
- Anhydrous calcium lactate has molar mass **218.218 g/mol**. The same mass would supply approximately **41.28% more calcium** than the pentahydrate, so unspecified hydrate labels cannot be treated as equivalent.

The [13-row table](results/formulations.csv) contains these ideal budgets. The [summary](results/summary.json) contains no performance ranking and no nominated new material. Its zero verified-result counts mean **no verification has occurred**, not that physical tests found every formulation to fail. The [39-row measurement template](results/measurements-template.csv) has blank observations and `not_tested` status.

## What must be measured

The [protocol](HOME_PROTOCOL.md) starts with plain PCL and the selected product's forming instructions: approximately 66°C water for the retrieved InstaMorph route, tool-assisted removal, drainage and cooling before handling. Hot water, hot plastic and trapped water pockets can burn. Filler and alginate trials remain optional process-feasibility experiments, with failures recorded rather than compensated for by unreviewed higher-temperature processing.

Measure thickness at five points and compare matched geometries. For containment, record catch-vessel leakage and an evaporation blank under the declared head, duration and temperature. Report raw masses, visible leaks and the scale's detection limit. Validate any film-clamping fixture against an impermeable reference; an edge-seal failure does not isolate material permeability. If no suitable fixture is available, immersion observations cannot substitute for containment evidence.

For immersion, record conditioned initial mass, blotted wet mass, dimensions, wet integrity and mass after redrying under the original recorded conditions. Water uptake and plasticizer/salt loss can occur together; mass changes alone cannot distinguish them. Document bending or geometry-appropriate handling damage and repeat water exposure. A successful observation would support only the tested conditions, thickness and specimen construction.

## Biodegradability needs a separate conclusion

Retrieved primary PCL evidence includes moist-soil film mass loss at 30°C, aqueous powder oxygen-demand tests at 25°C, controlled compost carbon-dioxide tests at 58°C and sediment-enriched seawater tests at 20°C. Those environments, geometries and grades are not interchangeable with a thick craft-PCL article in home compost.

For example, the soil study reports about **4% pure-PCL film mass loss after one month and 16% after two months**. This is evidence of recovered mass change under that experiment, not a mineralization rate or a promised disposal timeline. Vendor portfolio compost certifications cannot be transferred to an unspecified craft grade, a new starch-filled recipe or arbitrary thickness. This review found no verified home-compost mineralization assay for the specific planned craft grade or starch formulations.

Burial photographs, fragmentation, ingredient origin, a lost specimen and filler leaching do not prove complete microbial conversion of the article. Disposal claims require evidence tied to formulation, geometry and environment, such as an applicable product certificate or an appropriate controlled biological-conversion assessment. The prototype protocol therefore provides no guaranteed home-compost time and does not recommend environmental release.

## Outcome and next decision

The supported outcome is a **plain-PCL prototype route plus bounded comparison experiments**, with traceable sources and executable feed calculations. Waterproof performance, ease of manufacture for modified recipes and environmental conversion remain empirical questions. Start with the plain-PCL control: if it cannot be formed reproducibly and pass the stated cool-water test, there is no basis for claiming that a filler or coating has solved the problem. If it passes, compare modifications under the same conditions before making any improvement claim.

Further arithmetic cannot establish the requested combination of properties. The next decisive evidence is from real specimens and, separately, a grade- and geometry-specific biodegradation assessment.
