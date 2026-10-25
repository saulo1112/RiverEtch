# Water quality from Sentinel-2: turbidity where a gauge measures it

This report gives the result the product publishes (the water-quality validation v5, decision D18),
how the reaches behave in operation, and the limits of the method. The rules are in the
[preregistration](preregistration.md); every number below is recomputed from committed snapshots by
`climate-pipeline quality run` ([results](results/results.md), [summary](results/summary.json)) and
checked in CI by `quality verify`: byte for byte, or to the last printed digit where another
machine rounds floating point differently (deviation 14).

> Every published error is out of sample: a locked test evaluated once, or leave-one-year-out. An
> in-sample fit is never shown as an error. A choice made after seeing results is labelled
> exploratory. No output states that any actor caused anything.

## The headline: turbidity where a gauge measures it

Ten gauged rivers met fixed data criteria (continuous, approved turbidity since 2017 or earlier; a
main channel ≥ 300 m; not at a dam), written before any of their values was read. Each was
validated with the same protocol: models trained on the hydrological years 2019–2023 (and, for the
pretrained ones, on other rivers only), selected inside those years, then scored **once** on a lock
box, 2023-12..2026-09, that nothing had seen.

| River (USGS gauge)                         | Lock-box MdSA | Pairs | Median (null) | 90 % coverage | Interval ×/÷ | Level             |
| ------------------------------------------ | ------------- | ----- | ------------- | ------------- | ------------ | ----------------- |
| **Mississippi at Belle Chasse (07374525)** | **17.8 %**    | 57    | 113.7 %       | 94.7 %        | 1.48         | validated         |
| **Platte at Louisville (06805500)**        | **20.3 %**    | 54    | 66.9 %        | 92.5 %        | 1.66         | validated         |
| Atchafalaya at Morgan City (07381600)      | 23.4 %        | 43    | 75.2 %        | 88.3 %        | 1.72         | validated         |
| Ohio at Ironton (03216070)                 | 28.2 %        | 122   | 149.4 %       | 88.5 %        | 2.58         | estimated         |
| Mississippi at Cape Girardeau (07020850)   | 33.1 %        | 74    | 71.4 %        | 89.1 %        | 2.69         | estimated         |
| San Joaquin at Jersey Point (11337190)     | 40.6 %        | 53    | 46.2 %        | 94.3 %        | 2.21         | estimated         |
| Connecticut at Middle Haddam (01193050)    | 38.0 %        | 56    | 31.8 %        | 92.8 %        | 2.23         | none              |
| Willamette at Portland (14211720)          | 52.2 %        | 136   | 64.9 %        | 77.2 %        | 2.50         | indicative        |
| Columbia at Vancouver (14144700)           | 53.6 %        | 48    | 47.4 %        | 89.5 %        | 2.17         | none              |
| Columbia at Port Westward (14246900)       | —             | 1     | —             | —             | —            | insufficient data |

- **The two demo reaches follow the preregistered rule** (the highest level, then the lowest
  error): the Mississippi at Belle Chasse and the Platte at Louisville. Their records show
  turbidity in FNU with a 90 % interval.
- **They are the best two of ten,** so as a pair they flatter the method. The honest summary is the
  median over the nine rivers evaluated: **33.1 %**. Rivers carrying sediment (the lower
  Mississippi, the Platte, the Atchafalaya) do best; clear, tidal rivers (the Columbia, the
  Connecticut) do worst, where the median of past values is already close.
- **Suspended solids:** no river had 20 locked-test pairs. Discrete SSC samples give 4–6 a site in
  2023-12..2026-09, and the USGS surrogate SSC (estimated from turbidity) has no approved value in
  that period. No SSC value is published (v6 below tries again, with each gauge's own rating).

## More variables (v6)

v6 added the variables that are both observable from orbit and measured by the demo gauges, each
validated under the same rules (a lock box scored once, written before any value was read).

| Variable, reach                           | Model chosen                | Lock box                                  | Baseline        | Level         |
| ----------------------------------------- | --------------------------- | ----------------------------------------- | --------------- | ------------- |
| **Water temperature, the Platte**         | W1: Landsat 8/9 ST as it is | **MAE 1.28 °C**, bias +1.11 °C, 24 passes | 2.51 °C (W0)    | **estimated** |
| Suspended sediment, Belle Chasse (link 2) | R1: ln SSC on ln turbidity  | MdSA 15.9 %, 16 samples                   | 76.9 % (median) | indicative    |
| Suspended sediment, the Platte (link 2)   | R2: with ln discharge       | MdSA 50.7 %, bias +45 %, 23 samples       | 92.4 % (median) | indicative    |
| Suspended-sediment flux, both             | SSC × the gauge's discharge | follows SSC                               | —               | indicative    |

- **Water temperature at the Platte is published in °C** with a 90 % interval of ±2.8 °C (covered
  23 of 24 lock-box passes). It missed _validated_ on its bias (+1.11 °C against 0.75 °C). The
  linear adjustment W2 would have reached _validated_ (MAE 0.87 °C, bias −0.09 °C), but in the
  training years it was within 0.3 °C of W1, so the rule kept the simpler one; W2 stays a
  report-only row. In 2026, against the gauge, the records erred by 1.41 °C on 13 passes (8 of them
  provisional, so new to the model), 11 inside their interval.
- **Suspended sediment at Belle Chasse missed _estimated_ on its sample count alone:** the gauge's
  rating erred by 15.9 % on the lock box (the median, 76.9 %), but the lock box holds 16 approved
  samples and the rule asks 20. Satellite to sediment end to end, report-only: 26.1 % on 6 samples.
  At the Platte the rating itself erred by 50.7 %. Neither reach shows SSC in mg/L, and the flux
  follows SSC. (An indicative SSC class would only repeat the turbidity class: the rating is
  monotonic.)
- **The gauge's own readings** (discharge and gage height at both reaches; water temperature,
  dissolved oxygen, specific conductance and nitrate at the Platte) are shown beside each pass as
  context, labelled as measurements, never as satellite estimates.
- **Data note:** two Landsat files were unreadable at the source after two attempts (2022, in the
  training years); one pass was lost and one kept from its other tile.
- **Attempts:** 2 ratings at each gauge and 3 temperature candidates; each lock box scored once.

## Four more variables (v7 and v7.1)

v7 tried discharge from the river's water surface. v7.1 tried specific conductance and dissolved
oxygen at the Platte, and water temperature at Belle Chasse. Each was preregistered before any value
was read, then scored once on hydrological years 2024–2025.

| Variable, reach                     | Model chosen                         | Lock box                                     | Baseline (no satellite) | Level                       |
| ----------------------------------- | ------------------------------------ | -------------------------------------------- | ----------------------- | --------------------------- |
| **Water temperature, Belle Chasse** | W2 at Baton Rouge: a + b · ST        | **MAE 0.86 °C**, bias −0.33 °C, 37 passes    | 1.41 °C (W0)            | **estimated** (capped)      |
| Specific conductance, the Platte    | C1: power law of the water fraction  | MdSA 22.1 %, bias −11 %, 37 passes; ρ = 0.03 | 25.4 % (day-of-year)    | estimated, **not shown**    |
| Dissolved oxygen, the Platte        | O2: a + b · saturation at Landsat T  | MAE 1.02 mg/L, bias −0.65 mg/L, 16 passes    | 1.34 mg/L (day-of-year) | none (12 of 16 in interval) |
| Discharge, the Platte               | Q1: power law of the SCL water share | MdSA 110.6 %, bias +103 %, 47 passes         | 65.5 % (day-of-year)    | none                        |

- **Water temperature at Belle Chasse:**
  - The Belle Chasse gauge does not measure temperature, so the model was validated at Baton Rouge,
    the only main-stem gauge that does (about 245 km upstream).
  - It met every threshold of _validated_, but Baton Rouge's temperatures are provisional since
    2024, so the preregistered cap keeps it at _estimated_. Its 90 % interval is ±1.8 °C and covered
    33 of 37 passes.
  - Report-only: Belle Chasse's estimates against Baton Rouge's gauge on the same passes erred by
    0.90 °C (96 passes). Belle Chasse runs about 0.35 °C warmer.
  - **A warning:** on the 9 provisional passes after the lock box (2025-12 onwards) the model erred
    by 2.5 °C and ran 2.2 °C cold. As with the Platte's turbidity, this does not change the level of
    record, but it is watched.
- **Specific conductance earned _estimated_ by the rule, and is not shown:**
  - Its fit is nearly flat. The exponent is +0.14, the opposite sign of dilution, and the estimates
    stay within 690–740 µS/cm.
  - Its correlation with the gauge is 0.03. It beats the seasonal average by giving the river's
    usual value, not by following its changes.
  - Presenting that as a satellite measurement would mislead, so the product does not show it. This
    is a product choice made after seeing the result, and it only withholds; the level of record
    stands. The gauge's own conductance stays visible as context.
- **Dissolved oxygen missed _estimated_ on its interval alone:**
  - Its error (1.02 mg/L) and bias were within the thresholds and below the seasonal average's
    1.34 mg/L, but its 90 % interval covered 12 of 16 passes and the rule asks 80 % (13).
  - Pure saturation (O1, report-only) erred by 2.4 mg/L: at midday this river holds more oxygen than
    saturation (photosynthesis), which no satellite sees.
- **Discharge failed:**
  - Both water detections overestimated in the lock box. The MNDWI share (report-only) tracked the
    flow (ρ = 0.81) but read about twice the discharge, so the relation between the water surface
    and the flow drifted between the training years and 2024–2025.
  - By tercile of the gauge's discharge (report-only), low flows (≤ 142 m³/s) erred by 258 % and
    high flows (> 201 m³/s) by 38 %. The clear rule skipped 42 %, 30 % and 49 % of the passes in the
    three terciles, so it does not favour one flow.
  - No discharge is published; the gauge's own discharge stays visible as context.
- **Data note:** two Landsat files of path 22, row 39 (2022, in the training years) were unreadable
  at the source in both runs. Their passes are missing.
- **Network:** 4.4 GB estimated for the water surface (deviation 13 corrected the meter) and 0.5 GB
  for Landsat.
- **Attempts:** 2 candidates and a null for discharge, conductance and oxygen; 3 temperature
  candidates. Each lock box scored once.

## Missouri at Hermann (v4)

The first gauged reach, validated under the same locked-test protocol before v5:

- **A good error, one interval rule short of a level.** The selected model (H3: a ridge on the
  feature set F trained on eight other US rivers, then a site adjustment) erred by **34.9 %** on 70
  held-out overpasses in three years, against 87.7 % for the median. Its 90 % interval covered 68 of
  70 values (97.1 %); v4's rule wants [80 %, 97 %], so intervals too wide by one value cap it at
  _indicative_. The rule is not changed after the fact; under v5's rule it would still be
  _indicative_ (its interval is ×/÷ 3.65).
- **The physics transfers.** A4 (gradient-boosted trees) trained only on the other rivers, with no
  Hermann data at all, erred by 30.4 % on the same locked test. Where turbidity is measured
  continuously at the overpass, Sentinel-2 L2A carries the signal.

## How the validation works

- **Temporal, as the product runs.** A reach's estimate station is fixed and records are made for
  new scenes, so the test holds out whole time blocks: training on 2018-12..2023-11, a locked test
  on 2023-12..2026-09. The locked-test error speaks directly to how a reach's records behave.
- **Selection pays for itself.** Candidates (the median; a local log-log fit; three models
  pretrained on the other rivers plus a site adjustment) are chosen by leaving out one hydrological
  year at a time inside the training years; within 5 points, the simpler one wins.
- **Matched at the overpass.** A pair is the gauge's median within ±30 minutes of the Sentinel-2
  overpass, approved values only, read in a core window at least 60 m from the banks.
- **Levels need more than a low error.** _Validated_ and _estimated_ also ask for a small bias, a
  clear margin over the median of past values, enough pairs in at least two years, and a 90 %
  interval that covers at least 80 % without being too wide.

## What the product publishes, and why

- **The demo reaches** (`mississippi-belle-chasse`, `platte-louisville`): NDTI and NIR/red per
  sub-reach with their D0 z-scores and the verdict, plus **turbidity in FNU with its 90 % interval**
  at the gauge's window, from the locked-test card (`preregistered_lockbox_site`, _validated_). A
  scene whose features leave the card's training range, or whose window fails the guards, abstains
  and says why.
- **Water temperature at both demo reaches**, from Landsat 8/9:
  - each pass is its own sealed record, in its own ledger, with its 90 % interval;
  - the Platte's card was validated at its gauge;
  - Belle Chasse's was validated at Baton Rouge (`preregistered_lockbox_upstream_site`), so its
    values are labelled that way and checked against Baton Rouge's gauge.
- **Missouri reach** (`missouri-hermann`): the same indices, plus turbidity as a relative class (the
  tercile among the gauge window's own history), never a unit, from the locked-test card
  (`preregistered_lockbox_site`, _indicative_).
- **The 2026 check (retrospective):** beside the sealed records, `reach run` notes each gauged
  reach's raw estimate of every new scene, and `reach check` compares the scenes with the gauge's
  value at the overpass (provisional data, labelled). It is report-only. Its scenes were sealed
  after their gauge values were public, so it is a backtest. Prospective scoring follows rule v1
  ([prospective.md](prospective.md)): `reach score` scores only claims anchored before the gauge was
  read, after T0.
- Every record is sealed (SHA-256 of its canonical JSON) and chained in an append-only ledger ready
  for anchoring. Each record names one satellite pass (`sceneId`), so two passes on one day are two
  records.

## The reaches in operation (2026)

`reach run --since 2026-01-01` with the committed cards, one record per usable pass:

| Reach                    | Records | Turbidity in FNU                    | Abstained or without a value                                      | Anomalous verdicts |
| ------------------------ | ------- | ----------------------------------- | ----------------------------------------------------------------- | ------------------ |
| mississippi-belle-chasse | 33      | 29 (validated)                      | 4: window too cloudy (3), contamination above 0.2 (1)             | 6                  |
| platte-louisville        | 16      | 13 (12 validated, 1 estimated)      | 3 in the 100–300 FNU range, which earned no level in the lock box | 0                  |
| missouri-hermann         | 19      | none (indicative: 7 classed "high") | 12 estimated under 100 FNU, ranges without a level                | 1                  |

Clouds weigh on every reach: in 2026, 99 of 137 passes at Belle Chasse were not observable (72 %,
and 5 more excluded), 50 of 66 on the Platte (76 %) and 49 of 68 at Hermann (72 %).

**The 2026 check** (retrospective, report-only, `reach check --since 2026-01-01`): each record's
estimate against the gauge's value at the overpass.

| Reach                    | Pairs | Approved / provisional | MdSA       | Bias (SSPB) | Inside the 90 % interval |
| ------------------------ | ----- | ---------------------- | ---------- | ----------- | ------------------------ |
| mississippi-belle-chasse | 22    | 0 / 22                 | **18.0 %** | −13.9 %     | 17 of 22                 |
| platte-louisville        | 10    | 2 / 8                  | 44.9 %     | +24.4 %     | 9 of 10                  |

(The daily run's check of 2026-10-21, `checks/summary.json` of each reach. Each reach's last pair,
of 20 Oct 2026, was sealed and anchored before the station was read: it is also scored
prospectively, below.)

- **The provisional values are the first data the cards never saw:** the lock box took approved
  values only. The USGS can still revise them, so the check never changes a level (preregistration
  v4, A). The two approved Platte values (March and June) were already in the lock box.
- **Belle Chasse holds its error** on new data (18.0 %, against 17.8 % in the lock box), but its
  intervals covered 17 of 22 values: under the nominal 90 %, a 6.2 % chance if they truly covered
  90 % and the pairs were independent. Four of the five misses are from February and March 2026.
  That is a warning to watch.
- **The Platte overestimated all five provisional values of July–September 2026** by a factor of
  1.5–2.0; its two approved values (March and June) were within 17 %, and October's three read 12
  to 29 % low. Untested explanations: low summer flow
  in a shallow, braided channel (sandbars or the bed inside the window), a summer bloom, or
  revisions of the provisional values. The bias appears on Sentinel-2B and 2C alike. Until those
  values are approved and more seasons arrive, this is a warning, not a result: the card stays as
  its lock box rated it.
- **The first passes scored in advance** (rule v2, `reach score`; each reach's outcomes ledger):
  the 20 Oct 2026 pass at each demo reach, anchored on Sepolia at 17:01:36 UTC on 21 Oct (block 11963767) and read against the station at 17:04:50. Belle Chasse: 32.92 FNU (22.63–47.89), the
  station 31.35, inside. The Platte: 29.17 FNU (19.44–43.76), the station 33.2, inside. Both
  station values are provisional. Two passes say little; they are counted on the web app's Track
  record tab (counts, not percentages, until there are 20).

## Rivers the model never saw (transfer test, 2026-10-20)

RiverEtch is meant for rivers without a gauge, so the error that matters is the error on a river the
model was never trained on. The test was preregistered
([preregistration-transfer.md](preregistration-transfer.md)), frozen and anchored on Sepolia at
block 11952275 (2026-10-20 02:19:48 UTC) before it ran, and run **once** (02:38 UTC). Results:
[results/transfer/](results/transfer/transfer.md), with their own MANIFEST, recomputed by CI.

- **Design:** each of the nine river groups is held out in turn. A4 (LightGBM, v2's grid and seed,
  no site adjustment) is trained on the training years (2018-12 to 2023-11) of the other eight
  groups, and scored on the held-out group's lock box (2023-12 to 2026-09). No pair from any
  lock-box year trains any model.
- **Baselines:** (a) the held-out group's own median over its training years (a reference: an
  ungauged river has no such median); (b) the other groups' median, with no local data at all.
- **Disclosure:** v5 had scored these lock boxes with site models and, report-only, with models
  pretrained on the four pilot rivers; this design, which adds the five non-pilot rivers to the
  training, was chosen after seeing those results.

| River (USGS gauge)                       | Error on a river it never saw | Usual value (a) | No local data (b) | Bias     | Inside the 90 % range | Class matched | Level      |
| ---------------------------------------- | ----------------------------- | --------------- | ----------------- | -------- | --------------------- | ------------- | ---------- |
| Mississippi at Belle Chasse (07374525)   | 15.4 %                        | 112.7 %         | 618 %             | −6.8 %   | 56 of 57              | 53 of 57      | validated  |
| Willamette at Portland (14211720)        | 24.4 %                        | 64.9 %          | 337 %             | +9.8 %   | 131 of 136            | 135 of 136    | indicative |
| Columbia at Vancouver (14144700)         | 32.2 %                        | 47.4 %          | 191 %             | +26.5 %  | 40 of 48              | 48 of 48      | estimated  |
| San Joaquin at Jersey Point (11337190)   | 33.1 %                        | 46.2 %          | 86 %              | +26.1 %  | 52 of 53              | 53 of 53      | estimated  |
| Mississippi at Cape Girardeau (07020850) | 33.8 %                        | 72.3 %          | 600 %             | −1.0 %   | 71 of 74              | 49 of 74      | validated  |
| Atchafalaya at Morgan City (07381600)    | 40.5 %                        | 75.2 %          | 1004 %            | −40.5 %  | 40 of 43              | 32 of 43      | indicative |
| Missouri at Hermann (06934500)           | 41.2 %                        | 87.7 %          | 732 %             | −34.3 %  | 55 of 70              | 36 of 70      | indicative |
| Ohio at Ironton (03216070)               | 48.6 %                        | 149.4 %         | 110 %             | +45.9 %  | 116 of 122            | 114 of 122    | indicative |
| Connecticut at Middle Haddam (01193050)  | 88.4 %                        | 31.8 %          | 179 %             | +88.4 %  | 39 of 56              | 55 of 56      | none       |
| Platte at Louisville (06805500)          | 162.0 %                       | 66.9 %          | 729 %             | −162.0 % | 26 of 54              | 15 of 54      | none       |

- **Where it holds:** on 8 of the 10 sites the model that never saw the river erred less than
  guessing that river's usual value. Both Mississippi sites reach _validated_ under the v5 rules.
- **Where it fails:** the Platte (162 %: it reads far too low; no cause was tested) and the
  Connecticut (88 %: a clear river it reads too high). Both are listed, not dropped.
- **Biases stay large** on several rivers (−40 % at the Atchafalaya, +46 % at the Ohio), which is
  why an ungauged reach's value is shown only beside its class's range (since 2026-10-23; before
  that, as a class alone: [preregistration-values.md](preregistration-values.md)).
- **"Class matched" is easy on clear rivers:** nearly every value there is under 30 FNU, so the
  count says little; the pooled count below, on sediment-carrying rivers, is the one that matters.
- **The usual value (a) is the group's median,** as preregistered: for the Mississippi it pools both
  sites, so Belle Chasse reads 112.7 % here against 113.7 % in v5, which used the site's own median.

**Similar rivers, pooled (the ungauged reach's expected error).** The five sites whose training
median is at least 20 FNU (Atchafalaya, Mississippi at Cape Girardeau and Belle Chasse, Missouri,
Platte), each estimated by the model that never saw it: 298 pairs, **MdSA 36.9 %**, bias −22.9 %,
Spearman ρ 0.719 (95 % interval 0.647 to 0.781); 248 of 298 inside the 90 % range; the class (under
30, 30 to 100, 100 and over FNU) matched the gauge on **185 of 298**. The lower bound of ρ is above
0.3, so by the preregistered rule an ungauged reach shows the **class**, with this expected error.

**Report-only.** The ridge A3 errs far more on almost every river (for example 103 % at Belle
Chasse), so A4's gain is not a property of any model. Holding the Mississippi and the Atchafalaya
out together (the Atchafalaya takes part of the Mississippi's flow) leaves the Mississippi sites
near their scores (27.8 % and 24.7 %) but raises the Atchafalaya's to 78.7 %: part of its result
came from the Mississippi's data.

### The ungauged reach: the Mississippi above Natchez

Chosen by the owner on 2026-10-20, after the test, among three candidates: the lower Mississippi
from the USGS location near St. Joseph, Louisiana, down to river mile 378, about 25 km above
Natchez, Mississippi ([site file](../../pipeline/reaches/mississippi-st-joseph.yaml)). No USGS
turbidity series (63680) is on the river there; the only one in the reach's box is Fields Lake near
Church Hill, a lake, for four days in October 2012 (USGS Water Data API, 2026-10-20). The nearest
main-stem water-quality gauge, at Natchez (07290880), records nitrate but not turbidity.

- **Its model:** the test's `all` fold, A4 trained on the training years of all nine groups, with
  no site adjustment. Its card
  ([`ungauged/mississippi-st-joseph/turbidity.json`](ungauged/mississippi-st-joseph/turbidity.json))
  is frozen in the frozen-artifacts ledger and recomputed by CI (`quality transfer-verify`).
- **What a record shows:** a class, and since 2026-10-23 its value beside the class's range
  ([preregistration-values.md](preregistration-values.md)), at the level _unvalidated_, with the
  pooled error above in this report: under 30, 30 to 100, 100 FNU and over at first, and four classes (under 30, 30 to 50, 50 to
  100, 100 FNU and over) since the class test below passed. With no gauge it is never scored. It is a reach the
  model never saw, not a river: the model learned from two other Mississippi gauges, Cape
  Girardeau upstream and Belle Chasse downstream.
- **Its climate context** (the app's Climate tab, added 2026-10-21): the daily discharge measured
  at Vicksburg (USGS 07289000, 2008 to 2026), on the same river 59.0 km upstream of the reading
  spot in a straight line; Natchez and Tarbert Landing, downstream, publish no daily discharge.
  It is named as the station upstream, never read as the reach's own and never scored
  (`climate_station` in [`reach.yaml`](../../pipeline/reach.yaml)). No open station record of the
  Fırat was found: its Climate tab shows a flood model's flow instead (below).
- **Where the window sits, and why (decided on 2026-10-20, before any estimate on the reach):** the
  model abstains when the channel is wider than any river it was trained on (305 to 773 m). With
  the pipeline's selection rule (SCL water frequency, 2022 to 2025), the channel measures 848 m at
  the Natchez gauge and 1028 m at mile 378, so a window there would abstain on every pass. At the
  USGS location near St. Joseph it measures 522 m, so the window is there. The choice used the
  channel's geometry only: no estimate of the reach existed, and there is no gauge to compare with.

### Outside the tested region: the Fırat (Euphrates) at Birecik, Türkiye

Preregistered before any reading of it ([preregistration](preregistration-outside-us.md),
frozen-artifacts lines 15 to 17, Sepolia block 11957144), after measuring channel widths only: of
eleven points on Turkish rivers, the Fırat at the Birecik Bridge (322.5 m) lies inside the model's
training widths (305 to 773 m) by the largest margin. The reach runs from about 2 km below the
Birecik Dam to the bridge ([site file](../../pipeline/reaches/firat-birecik.yaml)).

- **What a record shows:** a class (and since 2026-10-23 its value beside the class's range, see
  [preregistration-values.md](preregistration-values.md)), with the label "Outside the tested region.
  No error estimate." Every river the model was trained and tested on is in the United States, so no error
  figure of any kind is shown.
- **Dams upstream** (the Birecik Dam 8 km above the town, the Atatürk Dam 60 km above that) may
  hold back much of the sediment; the water may be clearer than the training rivers, and the model
  may then abstain or read "under 30" on most passes. Either outcome is shown as it comes.
- **Its baseline stopped at the preregistered 6 GB network cap,** as Belle Chasse's and Hermann's
  did: 359 of 1069 acquisitions measured (2019-01 to 2021-06), 213 usable. Its scenes are larger
  than the Mississippi's, so the cap came sooner. Each pass's z-scores compare it with those 213.
- **What 2026 showed** (the 93 passes to 20 Oct 2026 in the committed examples): 74 read under 30
  FNU and 19 abstained (13 with the red-to-blue ratio log B04/B02 outside the training range, 2 for
  glint, 4 on other features); against its own 2019–2021 passes, 84 were usual.
- **Published measurements, looked up after seeing the result**
  ([file](published/firat-birecik.json)): the Euphrates at the Atatürk and Birecik dams' outlets,
  one point 0.8 km above the reading spot, read 5.0 NTU as median, minimum and maximum over eight
  months of 2002–2003, and the Birecik Dam Lake 7.5 NTU (5.0 to 20.0) (Alp, Koçer, Sen and Ozbay
  2010, _J. Anim. Vet. Adv._ 9(18): 2412–2421, Table 2). In 2013 a Secchi disk stayed visible 2.9
  to 4.35 m down in the reservoir (Kutlu et al. 2015, _Turk. J. Agric. Food Sci. Technol._ 3(7):
  623–628). Under 30 FNU is in line with them. Other years and another unit (NTU): a check of
  plausibility, not a test, and no record names them.
- **Its climate context** (the app's Climate tab, added 2026-10-21): no open daily flow record of
  the river was found, so the tab shows the daily river discharge the GloFAS v4 flood model
  computes (Copernicus Emergency Management Service, through the Open-Meteo flood API), labelled
  "modelled, not measured", never read as the reach's own and never scored (`climate_model` in
  [`reach.yaml`](../../pipeline/reach.yaml)). The cell, 37.025° N 37.925° E, is the one with the
  largest modelled flow within 5 km of the reading spot, about 4 km west of it. Its values run from
  1 January 1997 (the API documents 1984; earlier days came back empty) to 20 Oct 2026 in the
  committed [snapshot](reach/firat-birecik/climate/daily.csv): the model's reanalysis to July 2022,
  its forecasts after (Open-Meteo's documentation). Of 29 complete years, 2023 has the highest
  peak, 3,827.2 m³/s on 15 March. The 7-day low stays between 402.7 and 406.4 m³/s every year, so
  the years are not ranked by it (decided after seeing the record).

### The class tests (2026-10-20 and 21, each run once after its anchor)

All three read exactly the transfer test's 298 pooled pairs (the similar rivers, each estimated by
the model that never saw its river group), rebuilt from the committed models; the rebuild first
reproduces 185 of 298. All were **decided after seeing that result**. Results:
[`results/transfer-baseline/`](results/transfer-baseline/),
[`results/four-classes/`](results/four-classes/) and
[`results/five-classes/`](results/five-classes/), recomputed by CI (`quality class-verify`).

**A baseline for three classes**
([preregistration](preregistration-class-baseline.md), frozen-artifacts line 14, Sepolia block
11957144):

| Always guessing the most common class of…                    | Matched the gauge |
| ------------------------------------------------------------ | ----------------- |
| (the model, which never saw the river)                       | 185 of 298        |
| B1: the other similar rivers' training years                 | 160 of 298        |
| B2: every other river's training years (report-only)         | 79 of 298         |
| B3: the river's own training years (local data; report-only) | 160 of 298        |

On the pairs only one of the two got right, the model was right on 95 and B1 on 70. The model's
edge over always guessing is real but modest on three classes: the middle class, 30 to 100 FNU,
holds most of these rivers' values.

**Four classes** ([preregistration](preregistration-four-classes.md), frozen-artifacts line 18,
Sepolia block 11957929): 30 to 100 split at 50 FNU.

| Site                          | Model matched  | Guessing matched | Two or more classes away |
| ----------------------------- | -------------- | ---------------- | ------------------------ |
| Mississippi at Belle Chasse   | 49 of 57       | 20               | 0                        |
| Mississippi at Cape Girardeau | 40 of 74       | 11               | 1                        |
| Missouri at Hermann           | 35 of 70       | 16               | 13                       |
| Atchafalaya at Morgan City    | 23 of 43       | 7                | 3                        |
| Platte at Louisville          | 13 of 54       | 7                | 20                       |
| **Pooled**                    | **160 of 298** | **61**           | **37**                   |

- **It passes the preregistered rule.** On the pairs only one of the two got right, the model was
  right on 121 and the four-class guess on 22: an exact one-sided McNemar test gives
  p = 4.6 × 10⁻¹⁸ (the committed file rounds it to 0 at six decimals), below 0.05.
- **The Platte is the weak site:** 13 of 54, with 20 passes two or more classes away, where the
  transfer test also failed.
- **What changed:** each ungauged reach got a four-class card (the same model; frozen-artifacts
  lines 19 and 20). St. Joseph's passes sealed with three classes are read again with it, each new
  record naming the one it replaces (`supersedes`); the earlier records stay in the ledger. The
  Fırat at Birecik starts with four classes.

**Five classes** ([preregistration](preregistration-five-classes.md), frozen-artifacts line 21,
Sepolia block 11960616): under 30 split at 15 FNU. As the third test on the same pairs, its level
is a third of 0.05 (0.0167), and it passes only if the split itself also beats guessing, on the
pairs whose estimate and gauge value are both under 30 FNU.

| Site                          | Model matched  | Guessing matched | Two or more away | Split: model / guessing (pairs) |
| ----------------------------- | -------------- | ---------------- | ---------------- | ------------------------------- |
| Mississippi at Belle Chasse   | 45 of 57       | 20               | 0                | 22 / 10 (26)                    |
| Mississippi at Cape Girardeau | 37 of 74       | 11               | 4                | 11 / 8 (14)                     |
| Missouri at Hermann           | 31 of 70       | 16               | 16               | 6 / 10 (10)                     |
| Atchafalaya at Morgan City    | 20 of 43       | 24               | 3                | 4 / 6 (7)                       |
| Platte at Louisville          | 12 of 54       | 13               | 22               | 5 / 6 (6)                       |
| **Pooled**                    | **145 of 298** | **84**           | **45**           | **48 / 40 (63)**                |

- **It does not pass.** Five classes beat the five-class guess (b = 107, c = 46, p = 4.5 × 10⁻⁷),
  but the split on its own does not: on the 63 pairs under 30 FNU, b = 18 and c = 10, p = 0.092,
  above 0.0167. The pass of five classes came from the classes above 30.
- **Only Belle Chasse made the split** (22 of 26 against 10, p = 0.002). Cape Girardeau leaned the
  model's way without making it (11 of 14 against 8, p = 0.125); at the other three sites guessing
  did as well or better on it.
- **Each class's counts** (gauge values / estimates / both): under 15, 26 / 37 / 18; 15 to 30,
  53 / 99 / 30; 30 to 50, 76 / 73 / 27; 50 to 100, 84 / 56 / 38; 100 and over, 59 / 33 / 32
  ([`five_classes_bins.csv`](results/five-classes/five_classes_bins.csv)).
- **What changed:** nothing shown. The four classes stay everywhere, and no five-class card was
  written (the card builder refuses a test that did not pass).

## What would improve the estimates (research and proposals)

- **A continuous sensor at the estimate station beats a new model.** Every level above rests on
  hundreds of exact matchups with a continuous probe; point samples a few times a year never gave
  enough clear-scene matches to rate a model (annex).
- **Shallow water and blooms:** a visible bed or a bloom raises red and NIR as turbidity does. A
  low-flow flag (from the gauge's discharge) and a red-edge chlorophyll index (NDCI) would tell a
  user when to doubt a value, without changing it.
- **Clouds and shadows:** Sen2Cor's SCL is built for its atmospheric correction, not as a cloud
  product, and false clouds on bright targets were a known issue of its screening
  ([DLR, Sen2Cor status](https://elib.dlr.de/142245)). A cloud-probability mask such as
  OmniCloudMask (Sentinel-2, Landsat; trained on CloudSEN12 classes, including cloud shadow)
  ([docs](https://omnicloudmask.readthedocs.io/)) could replace or check SCL over the windows. It
  needs a deep-learning environment, kept apart like ACOLITE. Adding Landsat 8/9 would also shorten
  the gaps between clear scenes.
- **Glint and adjacency:** the pipeline already drops pixels with B11 > 0.05, checks the water B11
  median and uses a core window ≥ 60 m from land. ACOLITE's SWIR glint correction can leave hot
  spots in turbid water
  ([ACOLITE forum](https://odnature.naturalsciences.be/remsem/acolite-forum/viewtopic.php?p=2111)).
  The core window is the cheap, transparent defence and stays.
- **Physical models:** Dogliotti et al. (2015) switch from red to NIR as turbidity rises and were
  validated within 12–22 % in five coastal and estuarine sites
  ([RSE 156](https://biblio.naturalsciences.be/library-1/rbins-staff-publications/dogliotti_single_2015)).
  Generic algorithms were mostly built for 0–100 FNU, and the red band saturates above about 250 FNU
  in a turbid estuary
  ([Frontiers in Marine Science, 2023](https://www.frontiersin.org/articles/10.3389/fmars.2023.1186441/full));
  the NIR branch and the SWIR bands matter there.
- **Continuous-sensor validation elsewhere:** Sentinel-2 turbidity validated against continuous
  stations reached R² 0.63–0.75 over 965 matchups in the San Francisco Estuary
  ([UC Merced](https://escholarship.org/uc/item/4hz1q8jm)), and under 35 % mean error at the USGS
  Colorado River site ([USGS](https://pubs.usgs.gov/publication/70273951)), in line with the
  results above.
- **Rivers with open continuous turbidity outside the US** were searched (Rijkswaterstaat AQUALARM
  at Lobith, the Rhône sediment observatory, the Elbe, New South Wales and Queensland, ANA); none
  offers an approved, continuous, open series on a river ≥ 300 m wide that can be fetched now.

## Integrity

- Fourteen deviations are listed in the preregistration, each with what was seen when it was found.
- `quality run` recomputes every result in a few minutes, and CI checks them against the MANIFEST
  (deviation 14).

## Annex: earlier rounds on a Colombian reach

Before the gauged rivers, rounds v2–v4 tried to calibrate turbidity and suspended solids on the Río
Magdalena from IDEAM's point samples. None reached a publishable level: the samples met too few
clear scenes to rate any model. Those rounds, with every candidate and attempt counted, stay in the
[preregistration](preregistration.md), the [results](results/results.md) and the decision log
([D15–D18](../decisions.md)), and CI still recomputes them. The product no longer runs that reach.
