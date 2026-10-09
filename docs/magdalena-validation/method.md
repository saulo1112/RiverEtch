# Magdalena validation: pre-registered method

**Status: written on 2026-10-08, before any new number of this validation was computed. It is not a
blind pre-registration:** this reach's real series was already computed and seen in the Urrá
validation, where it was the quiet reference. [What was already seen](#what-was-already-seen) lists
it.

Every value lives in `pipeline/magdalena-validation.yaml`. The thresholds the site screening already
fixed (pixel guards, sub-reach geometry, the point rain rule) are read unchanged from
`pipeline/screening.yaml`. The code is the Urrá validation's (`pipeline/src/climate_pipeline/validation/`),
driven by this reach's settings file, plus three modules written for this validation:
`quietness.py`, `injection.py` and `insitu.py`. Each run records this file's git blob hash and the
commit. Any later change is listed under [Deviations](#deviations), with its date and reason.

> NDTI is a relative index: comparable only within one sub-reach, never between sites, never NTU.
> An anomaly is a departure from the sub-reach's own baseline. It is a flag to investigate, never
> evidence that any actor caused anything.

## Questions

Decision D14 made `magdalena-puerto-wilches` the demo reach, with a clearly labelled synthetic test
event. Before the demo relies on it, this validation answers four questions:

1. **Quietness and specificity.** Is the real series clean and stable enough to be an honest
   baseline? How often does the detector flag it (false-alarm share, with intervals)?
2. **Ground truth.** Does NDTI track any real in-situ measurement on this reach?
3. **Regulation and public data.** Which authority and instrument cover the dredging here, what
   do they say about turbidity or suspended solids, and what is monitored in public?
4. **Detection power.** What size of NDTI step does the unchanged detector find on this series?

Nothing here is tuned toward an anomaly or a story. A "not quiet" reach, an NDTI that does not track
in-situ data, or poor detection power are results to report first, not reasons to change a value.

## What was already seen

This is disclosed in full because the criteria below were set after it was seen.

1. **Site screening (2022-2025).** All outputs, both variants. This reach had 0 anomalous of 61
   scored scenes. Its channel is 30.6 px wide (10 m pixels) at the frozen geometry, with a 600 m
   corridor (the screening's default).
2. **The Urrá validation's reference rows** (`docs/urra-validation/results/`). Same code, same
   imagery, same frozen geometry, 2018-12-01 to 2025-12-31:
   - 119 observable scenes, 112 scored under D0;
   - D0: 1 anomalous scene of 112 (0.9 %; Wilson 95 % [0.2 %, 4.9 %]). It was **2020-08-26**,
     on the downstream − upstream difference (z = −4.51), with a glint share of 0.625 and
     point-rule rain. It was flagged in 9 of the 10 variants; G2 removes it for glint;
   - other variants: B3 6 of 112 (5.4 %), Z2.5 3 of 112, G1 1 of 110, G2 0 of 106, all others
     1 of 112;
   - hold-out (2018-12 to 2021-12): 1 of 51; screening period: 0 of 61;
   - the per-scene table and the series figure;
   - rain flags from the point rule only: the catchment rule ran only at Urrá.
3. **The control** (`meta-orocue`, the same rows): D0 3 of 51 (5.9 %; Wilson 95 % [2.0 %, 15.9 %]).
4. **In-situ metadata, no values.** While designing question 2, the open-data endpoints were queried
   for station names, coordinates, variables, units, sample counts and date ranges only:
   - water quality (IDEAM, `datos.gov.co` resource `62gv-3857`): turbidity (NTU) and total
     suspended solids (mg/L), each sampled 7 times from 2021-07 to 2023-06 at Puerto Wilches
     [23187010], San Pablo [23207040] and Sitio Nuevo R-11 [23187280], and 9-10 times from
     2020-03 to 2023-06 at Barrancabermeja [23157030];
   - river levels (IDEAM, resource `bdmn-sqnh`): Puerto Wilches [0023187010] from 2024-10-29 to
     2026-07-24; San Pablo [0023207040] from 2016-10-07 to 2020-03-13.
5. **The screening's site research** for this reach: Cormagdalena's contracted maintenance dredging
   of the Barrancabermeja-Pinillos sector, 2024-01-01 to 2026-07-31 (contract level only), and a
   Cormagdalena dredge at Sitio Nuevo (Puerto Wilches) reported withdrawn in May 2023.

**Not seen:** the corridor alternatives; the catchment rain rule at this reach; any in-situ value
or level; any injection result; any candidate date for the demo event.

Consequence: **question 1 is not a test that could surprise on the frozen geometry.** With the
criterion below, the numbers above already pass it. What can still change the reading is the
corridor sensitivity (report-only, but reported next to the criterion), and the reproduction check:
the same code must give the same numbers.

## Data

- **Reaches.** Target: `magdalena-puerto-wilches`. Control: `meta-orocue` (the Urrá validation's
  control). No reference.
- **Imagery, geometry, seasons, rain points, events:** as in the Urrá validation
  ([method](../urra-validation/method.md#data)):
  - Sentinel-2 L2A from Earth Search v1, read as in the screening, 2018-12-01 to 2025-12-31;
  - masks, centerline and sub-reaches built only from the 2022-2025 acquisitions (frozen
    geometry, the screening's post-hoc mask rule), with the whole-period geometry as a check;
  - rainy months frozen to the screening's: target April, May, June, August, October and
    November; control April to August and November;
  - the screening's event catalog, frozen by its hash (`eef55429…`). For this reach it holds two
    entries: the 2024-01-01 to 2026-07-31 contract period (precision `range`) and the May 2023
    Sitio Nuevo report (precision `month`).

## Signals, anomalies and variants

Unchanged from the Urrá validation
([signals](../urra-validation/method.md#signals-and-anomalies),
[variants](../urra-validation/method.md#assumption-variants)):

- the three signals (upstream, downstream, downstream − upstream);
- the leave-one-out robust z, with σ = max(1.4826 · MAD, 0.01);
- anomalous means |z| ≥ 3 on any signal under D0;
- the ten variants D0, B1-B5, Z2.5, Z3.5, G1 and G2;
- persistence and 30-day episodes (report-only here).

**Every variant is reported; none is picked.**

## Question 1: quietness and specificity

- **False-alarm share** of a reach under a variant = anomalous scored scenes ÷ scored scenes, over
  the whole period. It is a false-alarm share only if the reach has no real event. The reach is
  being judged as a baseline, so every flag counts against it.
- **Interval:** Wilson score interval, 95 % (z = 1.96), for every variant, at the target and the
  control.
- **Criterion: the target is "quiet"** when both hold:
  1. the upper end of the D0 interval is at most **0.10**;
  2. no variant's point share exceeds **0.10**.
- **Why 0.10.**
  - The demo shows one flagged scene as unusual. With about 16 scored scenes a year here, 10 %
    is 1.6 flags a year: one demo flag would then be roughly as common as the reach's own noise.
    Above that, it would not stand out honestly.
  - Under a normal model, |z| ≥ 3 on three correlated signals flags under 1 % of scenes. Real
    series have heavier tails: the controls of the screening and the Urrá validation showed 2-6 %.
  - The bound was chosen after the seen 0.9 % (upper 4.9 %) and 5.4 % (B3). A stricter bound
    (for example 0.05) would sit just above the seen numbers and look tuned; 0.10 is the ceiling
    for a usable demo.
- **Comparison with the control,** from the D0 intervals: "lower than the control" when the
  target's upper end is below the control's lower end, "higher" in the opposite case, otherwise
  "not distinguishable from the control". On the seen numbers it is "not distinguishable": the
  control has 51 scored scenes and a wide interval.
- **Corridor sensitivity (report-only).** Every variant's share and interval is also computed with
  the corridor narrowed from the frozen 600 m half-width to 300 m and to 150 m around the same
  centerline. 150 m is the closest this code gets to "main channel only". The reach is braided, and
  side arms enter the wide corridor.
  - Each corridor reruns stage 1 and stage 2 on the same scenes, centerline and sub-reach windows.
  - It does not enter the criterion. If any corridor would change the reading, the report says so
    next to the result.
- **The single anomalous scene** (and any other D0 anomaly of the run) is examined:
  - date, signals, z and glint share;
  - point and catchment rain;
  - river level percentile, where a level exists;
  - the same signal within ±15 days of its day of year in other years (the seasonality table).

## Question 2: in-situ comparison

- **Sources.** IDEAM data published on `datos.gov.co`, through the Socrata API (SODA). Each
  response is cached and its SHA-256 recorded in the run manifest. A failed request is reported,
  never fatal.
- **Water quality** (resource `62gv-3857`): variables `TURBIDEZ` (NTU) and
  `SOLIDOS SUSPENDIDOS TOTALES` (mg/L), samples inside the period.
  - Primary stations: Puerto Wilches [23187010] and San Pablo [23207040], both at the reach ends.
  - Secondary stations: Barrancabermeja [23157030], upstream, and Sitio Nuevo R-11 [23187280],
    downstream, both about 40 km away.
  - A value reported below a detection limit ("<x") is used as x and flagged as censored.
  - Distances are straight lines to the centerline midpoint, not along the river.
- **Matching.** Each sample pairs with the usable target scene nearest in time, using the sample's
  local date (America/Bogota):
  - primary set: primary stations, within **±1 day**;
  - wider set: all four stations, within **±3 days**.

  The NDTI of a pair is the reach value: the mean of the two sub-reach medians at the D0 glint
  limit. Per-sub-reach values are kept in the pairs table. Two samples may pair with the same scene;
  this dependence is disclosed, not corrected.

- **Statistic.** Spearman's rank correlation (average ranks for ties), with a 95 % percentile
  bootstrap interval: 2000 resamples of the pairs, seed 20261008.
- **Reading, per variable and set:**
  - fewer than **10 pairs** → "not enough data";
  - ρ ≥ **0.4** and the interval's lower end > 0 → "tracks";
  - the interval's upper end < 0.4 → "does not track";
  - otherwise "inconclusive".
- **Expectation, stated now:** 7 samples per primary station make "not enough data" likely for
  the primary set.
- **River levels** (resource `bdmn-sqnh`, instantaneous level in m), flow context:
  - Puerto Wilches [0023187010] and San Pablo [0023207040];
  - the level of a scene is the mean of the observations within **±12 hours** of the
    acquisition, with at least **3 observations**. Times are read as local time (America/Bogota);
  - per station, NDTI (reach value) against level, with the same statistic and reading;
  - pooled, NDTI against the level's percentile within its station;
  - each scene's percentile goes into the per-scene table and the case file.

  A level is not a discharge: no rating curve is used. The two stations together cover only
  2018-12 to 2020-03 and 2024-10 to 2025-12.

- **Saturation check.** Per sub-reach, the usable scenes are split at the median of the median red
  reflectance of their water pixels. The check reports Spearman (NDTI, red) in each half and over
  all scenes:
  - "responds across the range" when the upper half's ρ ≥ **0.3**;
  - "flattens at high red reflectance" when only the lower half's ρ ≥ 0.3;
  - otherwise "weak relation in both halves".

  The red and NDTI ranges are reported. Scatter plots show NDTI against red reflectance and
  against the in-situ values.

## Question 3: regulation and public data

Answered in [regulatory.md](regulatory.md). The rules are the Urrá regulatory file's:

- primary sources first;
- quotes verbatim, with URL, page and date accessed;
- Spanish verbatim, with an English translation labelled as such;
- anything unreadable marked UNVERIFIED;
- no condition inferred and no value invented.

**Verdicts, defined now:**

- **(a)** a real condition sets a limit the observation can be compared with;
- **(b)** the authority and the instrument are verified, but no condition is a comparable limit:
  the demo permit is simulated;
- **(c)** the authority or the instrument cannot be verified: the same labels, and no entity names
  in the interface.

The file presents evidence and a recommendation; a person decides.

**Post-hoc events.** Dated events found during this verification are written to
`docs/magdalena-validation/post-hoc-events.csv` before the full run. They are post-hoc: described,
never counted as validation. They have one use: the demo date keeps away from them.

## Question 4: detection power (injection-recovery)

- **On a copy only.** The real series is never edited. Each injection adds a step to one scene's
  downstream NDTI in a copy of the series, and the difference signal moves with it. The unchanged
  D0 detector then scores that scene.
- **Detected** means the D0 rule on the injected location: |z| ≥ 3 on the downstream signal or on
  the difference. Both are also reported separately.
  - |z| counts both directions, so a small positive step can cancel a real negative anomaly.
  - The **zero step** (the uninjected copy) is always included. Its share is the false-positive
    rate of the same rule on this series.
- **Steps:**
  - raw NDTI: 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25 and
    0.30;
  - multiples of the downstream signal's robust σ (pooled over the eligible scenes): 1, 2, 3, 4,
    5, 6, 8 and 10.
- **Dates and repetitions: exhaustive, no sampling.**
  - Every eligible scene receives every step once, one at a time. Eligible means usable, scored
    under D0, with both sub-reaches measured.
  - There is no random draw, so no seed is needed; the run is deterministic.
  - The baseline leaves the scored scene out, so z moves linearly with the step. Each scene is
    therefore scored at steps 0 and 1 and the grid follows exactly. A test checks this against
    scoring every step on its own copy.
- **Reported:**
  - detection share against step, overall, by season (rainy and dry months) and by glint class
    (largest sub-reach glint share: low ≤ 0.1 < mid ≤ 0.3 < high);
  - the false-positive rate (zero step);
  - the **minimum step detected with at least 80 % probability**: the smallest grid step reaching
    80 %, and a linear interpolation between the grid steps around it. Both are given in NDTI and
    in σ.
- **Meaning.** This is a property of the detector on this series. It measures no real event, and
  converts nothing to NTU or mg/L.

### Demo event, fixed now

The demo's synthetic event follows this rule. Its date is drawn without looking at where it would
land, and its outcome is scored once.

1. **Magnitude:** 2.0 × the interpolated 80 % step in NDTI, rounded up to 0.01.
2. **Candidate scenes:** real observed scenes of the whole period (2018-12-01 to 2025-12-31), none
   interpolated, that meet all of these:
   - clear under the screening's clear rule;
   - usable, with both sub-reaches measured;
   - not D0-anomalous;
   - largest sub-reach glint share at most 0.2;
   - at least **30 days** from every catalogued and every post-hoc event of this reach. That
     includes ranges, such as contract periods: a month-precision event covers its whole month,
     and a range covers all of it.
3. **Date:** one seeded random draw among the candidates (Python's `random.Random(20261008)`).
4. **Location:** the step is added to the downstream sub-reach of that scene, in a copy.
5. If there is no 80 % step or no candidate, there is no demo event, and a person decides.

The event is written only to the case file's separate `synthetic_overlay` layer. Every record
carries `synthetic: true`, the magnitude and the label "SYNTHETIC test event (injected into a copy,
not observed)". The real series in the case file never includes it.

## Report-only analyses (Urrá's, unchanged)

None of these changes a reading:

- per-variant tables and signal split;
- seasonality (±15 days);
- January-February table;
- placebo (1000 within-season shuffles, seed 20261008);
- event test (the two catalogued events: one range, one month; neither has day or week
  precision, so none is scored);
- hold-out view (2018-12 to 2021-12, already seen);
- processing chain;
- the whole period's rainy months and geometry;
- CHIRPS probe.

**Rain.** The point rule (> 20 mm in 72 h) and the catchment rule are as in the Urrá validation,
with two changes of grid for a catchment this large:

- the grid is built from HydroBASINS level 12 at the coarsest of 2.0, 1.5, 1.0, 0.75 and 0.5°
  giving 6 to 12 points;
- it is committed as `docs/magdalena-validation/rain-grid.csv` before the full run.

The catchment upstream of Puerto Wilches is very large, and its flow is regulated upstream: dams
on the upper Magdalena and on the Sogamoso. Local or catchment rain is therefore a **weak** proxy
for flow here, and "not rain-coincident" means much less than at a small basin. River levels,
where they exist, are the better flow context.

## Reproduction checks

1. **The screening (2022-2025),** as in the Urrá validation:
   - item-id hashes (target `8bff3e8c…`, control `16548143…`);
   - geometry fields;
   - per-scene NDTI to 4 decimals.
2. **The Urrá validation's rows.** The target's and control's per-scene NDTI, D0 status and D0
   flags must equal the Urrá validation's `scenes.csv` for both reaches: same code, same imagery,
   same geometry. This is checked by hand in the report.

A failed check is reported and explained. It changes no reading.

## Outputs

- **Committed:**
  - `docs/magdalena-validation/results/`, written by the run and kept out of Prettier: every
    table above as CSV, `results.md`, figures under 300 KB and `run_manifest.json`;
  - `docs/magdalena-validation/rain-grid.csv`;
  - `docs/magdalena-validation/post-hoc-events.csv`;
  - `docs/magdalena-validation/sources/`.
- **Case file:** `pipeline/out/case/magdalena.json`, copied to
  `docs/magdalena-validation/magdalena.sample.json` only if it is under 300 KB. It holds:
  - the centerline and sub-reaches as GeoJSON;
  - per scene: date, STAC item ids, NDTI per sub-reach, z under every variant, rain flags, river
    level percentile, quality flags and exclusion reasons;
  - the separate `synthetic_overlay`;
  - a manifest: commit, config hash, method blob and item-id hashes.

  Anonymization, checked by the run:

  - interface fields say "simulated permit holder" and "illustrative limit, not the real
    licence";
  - real names of contracts, entities or authorities appear only in `context.sources`, marked
    "public-source context, not an accusation";
  - the settings file lists the names the interface must never show.

  The context sources are chosen from `regulatory.md` after the verification. They change no
  number.

- **Never committed:** rasters, caches, HydroBASINS files.

## Runs

The runs are local, on the developer's machine. This differs from D12's GitHub Actions pattern
for a logistics reason only: HydroBASINS refused the Actions runner during the Urrá validation.
The commands are the same:

1. `climate-pipeline catchment-grid --config pipeline/magdalena-validation.yaml` (commits
   `rain-grid.csv`);
2. `climate-pipeline validation --config pipeline/magdalena-validation.yaml --stage1-only` (smoke
   run: reproduction hashes, counts, Open-Meteo cells, CHIRPS probe);
3. `climate-pipeline validation --config pipeline/magdalena-validation.yaml` (full run).

## What will not be done

- No threshold, window, variant, step grid, matching window, minimum n or reading rule is changed
  after the full run's numbers are seen.
- No matching or flow window is widened to reach a minimum n.
- No demo date is chosen, moved or redrawn after seeing where the rule puts it, and no magnitude
  is chosen by hand.
- No variant, corridor or station is selected as "the" result: all are reported.
- No post-hoc event is counted as validation.
- NDTI is never converted to NTU or mg/L, and no licence value is applied to it unless the licence
  text says so.
- No actor is said to have caused anything.

## Deviation protocol

- **A technical failure** (network, timeout) is rerun, unchanged.
- **A bug found after results were seen** is fixed. Both results are reported, and the change is
  listed under Deviations.
- **A missing in-situ source** gives "not enough data". It is never replaced by a different station
  or variable chosen after seeing values.

## Deviations

None yet.
