# Urrá validation: pre-registered method

**Status: pre-registered on 2026-10-07, before any NDTI of this validation was computed.** Every
value lives in `pipeline/urra-validation.yaml`. The thresholds the site screening already fixed
(pixel guards, sub-reach geometry, the point rain rule) are read unchanged from
`pipeline/screening.yaml`. The code is written after this file, in
`pipeline/src/climate_pipeline/validation/`. Each run records this file's git blob hash and the
commit. Any later change is listed under [Deviations](#deviations), with its date and reason.

> NDTI is a relative index: comparable only within one sub-reach, never between sites, never NTU.
> An anomaly is a departure from the sub-reach's own baseline. It is a flag to investigate, never
> evidence that any actor caused anything.

## Question

The screening found 7 anomalous scenes among 26 usable scenes at the Río Sinú below Urrá I, against
1 in 41 at the control. Its baselines were short, and split by season. Decision D13 chose this reach
for the demo. This validation asks one question before the demo relies on the reach:

**Do anomalies that are not explained by rain persist across reasonable changes of the
assumptions, on a longer series, more often than at the control?**

A "yes" is a candidate signal worth showing as an observation. It is not evidence about what
produced it. A "no" sends the demo to its fallback, which a person decides (decision D13).

## What was already seen

This is disclosed in full because the criteria below were set after it was seen.

1. **All screening outputs for 2022-2025**, both variants, all eight reaches. At Urrá the anomalous
   scenes were 2022-12-07, 2023-12-02, 2024-01-16, 2024-02-10, 2024-02-25, 2025-11-06 and
   2025-12-16. All but 2025-11-06 were not rain-coincident.
   - Merged at 30 days, those six form **four episodes**: 2022-12-07; 2023-12-02; 2024-01-16 to
     2024-02-25; 2025-12-16.
   - **The episode count N = 4 was chosen knowing this.**
2. **Four of the seven anomalies fall in November or December.** The frozen rainy months (April to
   September) class these months as dry. Their NDTI was near 0, while most dry-group scenes
   (January to March) lay between about −0.15 and −0.27. Variants B2 and B3 below test whether
   the season split explains them.
3. The three January-February 2024 anomalies are on the downstream − upstream difference. One of
   them (2024-01-16) had 66-76 % of its water pixels above the B11 glint limit.
4. The control (`meta-orocue`) had 1 anomalous scene of 41 (2023-01-15); the reference
   (`magdalena-puerto-wilches`) had 0 of 61.
5. During planning, the STAC metadata of pre-2022 Earth Search items was surveyed: processing
   baselines and offset flags only. No pixel was read.
6. The regulatory verification ([regulatory.md](regulatory.md)) read documents only, no imagery.

**Not seen:** every pixel from 2018-12-01 to 2021-12-31 at all three reaches. That period is
reported separately as a hold-out view.

## Data

- **Reaches.**
  - Target: `sinu-urra`.
  - Control: `meta-orocue`.
  - Reference: `magdalena-puerto-wilches` (a quiet reach, report-only, never in the criteria).
- **Imagery.** Sentinel-2 L2A from Earth Search v1, read exactly as in the screening
  ([method](../site-screening/method.md), stage 1 steps 1-2 and stage 2 steps 1-5). This
  includes the per-item scaling, the `boa_offset_applied` handling and the B11 water checks.
  Scenes span **2018-12-01 to 2025-12-31**.
- **Geometry frozen to the screening's.**
  - The water-frequency passes (SCL, and MNDWI where SCL fails: the screening's post-hoc mask
    rule) use only the 2022-01-01 to 2025-12-31 acquisitions.
  - So the river masks, centerlines and sub-reaches are the screening's.
  - The geometry from the whole period is computed as a check: its sub-reach overlap with the
    frozen geometry is reported, never used.
- **Seasons frozen to the screening's rainy months** (Open-Meteo at the reach center, 2022-2025):
  - Urrá: April to September.
  - Control: April to August and November.
  - Reference: April, May, June, August, October and November.

  The months the same rule gives over the whole period are reported, never used.

- **Rain.** Open-Meteo archive, hourly, from 8 days before the period, at the site's rain points
  (point rule) and at the catchment grid points (catchment rule, below).
- **Events.** The screening's catalog, frozen by its hash
  (`eef554292bca112f858ff206a533d0334ac7fa7449646174be9780fa79fb5cf8`). No event is added or
  changed.

## Signals and anomalies

For every usable scene the signals are the median NDTI of each sub-reach (upstream, downstream) and
their difference (downstream − upstream), as in the screening.

Each signal is scored against a leave-one-out robust baseline: median, and
σ = max(1.4826 · MAD, 0.01). A scene is **anomalous** under a variant when any of its three signals
reaches the variant's |z| threshold. A scene that is excluded, has a missing signal, or has no
baseline ("insufficient") is not anomalous for that signal under that variant.

## Assumption variants

Ten variants. D0 is the screening rule; each other variant changes exactly one thing.

| Id   | Changes from D0                                                                                                                         | Truly differs |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| D0   | none: same-season group if it has ≥ 8 other scenes, else all others if ≥ 12; \|z\| ≥ 3; pixel B11 ≤ 0.05                                | -             |
| B1   | same-season group only (≥ 8); no fallback                                                                                               | no            |
| B2   | others whose calendar month is within ±1 month of the scene's (December, January and February are adjacent), any year, ≥ 8; no fallback | yes           |
| B3   | others within ±182 days of the scene's date (a centred 365-day window), ≥ 6; no fallback                                                | yes           |
| B4   | group minimums 5 (season) and 8 (all)                                                                                                   | no            |
| B5   | group minimums 12 (season) and 20 (all)                                                                                                 | no            |
| Z2.5 | \|z\| ≥ 2.5                                                                                                                             | no            |
| Z3.5 | \|z\| ≥ 3.5                                                                                                                             | yes           |
| G1   | pixel B11 ≤ 0.03; NDTI recomputed from the same reads; a sub-reach with fewer than 200 pixels is missing                                | yes           |
| G2   | scenes whose glint share (pixels above B11 0.05, at the D0 pixel rule) exceeds 0.5 in either sub-reach are removed                      | yes           |

- Each variant computes its baselines from its own usable scenes. Removed scenes count as
  excluded.
- A scene's **persistence** is the number of the ten variants in which it is anomalous.
- **Disclosed weakness:** for these reaches (no regime changes) B1 equals D0 whenever the season
  group has 8 scenes, and B4, B5 and Z2.5 mostly agree with D0. A D0 anomaly therefore starts with
  about six votes. To reach 8 it needs about two of the five variants that truly differ (B2, B3,
  Z3.5, G1, G2). The persistence over those five is reported next to the criterion. It is not
  used by it.

## Rain coincidence

- **Point rule (the screening's):** the wettest of the site's rain points had more than 20 mm in
  the 72 hours before the acquisition.
- **Catchment rule:**
  - Six statistics are computed per scene: the mean and the maximum over the grid points of the
    rain sums over 24, 72 and 168 hours ending at the acquisition hour.
  - Each statistic has a threshold: the 90th percentile of its daily values. A daily value is the
    statistic for the sums ending at 15:00 UTC on each day of the period, on days where every grid
    point is known.
  - A scene is catchment-coincident when any statistic reaches its threshold. A statistic is
    unknown when any grid point's sum is unknown (more than 10 % of its hours missing).
  - If the six statistics were independent, about 47 % of days would be flagged; they are not
    independent. The share of days and scenes actually flagged is reported.
- **Union, used by the criteria:** a scene is rain-coincident when the point rule or the catchment
  rule flags it, **or when either is unknown**.
- **Catchment grid** (target only, built once, committed as `docs/urra-validation/rain-grid.csv`
  before the full run):
  1. HydroBASINS v1c, South America, level 12
     (`https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_sa_lev12_v1c.zip`). The
     archive's SHA-256 is recorded.
  2. **Outlet:** of the basins whose polygon contains the site file's downstream anchor or one of
     the eight points 0.01° around it, the one with the largest upstream area.
  3. **Catchment:** the outlet and every basin upstream of it, following the downstream links
     (`NEXT_DOWN`).
  4. **Lattice:** points at whole multiples of a spacing (longitude = i·s, latitude = j·s) inside
     the catchment. The spacing is the coarsest of 0.30, 0.25, 0.20, 0.15, 0.125 and 0.10° that
     gives 6 to 12 points.
  5. **Open-Meteo cells:** points that Open-Meteo answers with the same grid cell (the coordinates
     it returns) are merged, keeping the first.
  6. **Fallback:** if no spacing gives 6 to 12 points, the grid is unbuildable. Only the point rule
     is then used, and the report says so.
- **CHIRPS** (report-only, never in the criteria):
  - CHIRPS 2.0 daily COGs are probed in the smoke run.
  - If reachable, the full run compares two quantities for each D0-anomalous target scene: the
    CHIRPS catchment-mean rain of the 3 days before the scene, and the Open-Meteo catchment mean
    over 72 hours.

## Criteria and verdict

**Candidate signal** if and only if both hold:

- **(a) Persistence away from rain.** Take the target's scenes that are flagged in at least 8 of
  the 10 variants and are not rain-coincident under the union rule. Merge them into episodes:
  scenes no more than 30 days after the previous one join its episode. There must be **at least
  N = 4 episodes**, counted over the whole period, 2018-12-01 to 2025-12-31.
- **(b) More than the control.** The target's D0 anomalous-scene share must be **at least 3 times**
  the control's, over the whole period. A share is anomalous scored scenes ÷ scored scenes, where a
  scored scene has at least one z-score. A control share of 0 counts as 0.5 ÷ n, with n the
  control's scored scenes.

**Otherwise "no robust signal".** The verdict is **"not computable"** when any of these holds:

- the target or the control has no scored scene under D0;
- the target's point-rule rain is unavailable for every scene.

An unbuildable grid is not "not computable": the point rule alone is used, and the report says so.

**Chance level (report-only).** At the control's D0 share p, with the target's n scored scenes, the
binomial tail P(X ≥ k) is reported for k = N and for k = the observed number of candidate scenes.
At p = 0.024, P(X ≥ 4) is 2.4 %, 5.6 % and 8.8 % for 46, 60 and 70 scenes, and P(X ≥ 3) is 9.8 %,
17.5 % and 23.7 %. Episodes never outnumber scenes, so counting episodes is never weaker. The
criterion's two filters (persistence and rain) make this tail an upper bound under independence.

## Report-only analyses

None of these changes the verdict.

1. **Per variant:** usable, scored and anomalous scenes; anomalies per signal; agreement with D0
   (scenes anomalous in both, in D0 only, in the variant only). Persistence over the five
   distinct variants.
2. **Seasonality (±15 days):** for each D0-anomalous target scene, the median and count of the same
   signal at scenes within ±15 days of its day of year in other years.
3. **January-February table:** every target scene of those months, all years, with its difference
   signal, z under D0, B2 and B3, and its glint shares.
4. **Placebo (1000 within-season shuffles, seed 20261007).**
   - The target's usable scene rows move between dates of the same season: all their
     measurements, glint shares included. Rain flags stay with the dates. Excluded scenes stay
     where they are.
   - **S1** is the number of D0 anomalies that are not rain-coincident. Within-season shuffles
     cannot change which values are D0 anomalies, because each value keeps its baseline group. So
     S1 tests only whether anomalies fall on dry dates more often than at random.
   - **S2** is the number of criterion-(a) episodes, with every variant recomputed, the
     date-dependent B2 and B3 included.
   - p = (1 + number of shuffles at or above the observed value) / 1001.
5. **Event test:**
   - every scored catalog event of the target (day or week precision);
   - window from 2 days before to 10 days after;
   - outcome under D0, and whether a persistent scene (flagged in ≥ 8 variants) falls in the
     window;
   - chance rate from 500 random windows of the same length (seed 20260101), away from catalog
     events, over the whole period.
6. **Control and reference:** anomalous-scene shares per variant.
7. **Hold-out view (2018-12 to 2021-12):** D0 anomalies, persistent scenes and episodes in that
   period, with baselines from the whole series.
8. **Processing chain:** scene counts by year, sensor, processing-baseline family and scaling
   status, and the median NDTI per family and sub-reach.
9. The rainy months the rule gives over the whole period.
10. The geometry check of the whole period.
11. The CHIRPS comparison.

## Reproduction checks (2022-2025)

1. The SHA-256 of each reach's 2022-2025 STAC item ids equals the screening's:
   - Urrá: `678e6ef8…`;
   - control: `16548143…`;
   - reference: `8bff3e8c…`.
2. The geometry fields equal the screening's post-hoc `stage1_summary.csv`: mask source,
   threshold, reach length, separation, anchor shifts, width and centerline midpoint.
3. For each 2022-2025 scene:
   - NDTI (upstream, downstream, difference) equals the screening's post-hoc `stage2_scenes.csv`
     to 4 decimals;
   - the same scenes are excluded.

A failed check is reported and explained in the report. It does not change the verdict rule.

## Outputs

- **Committed** (`docs/urra-validation/results/`, kept out of Prettier so they stay byte-identical
  to the run):
  - per-scene table with every variant's z and flags, and the rain flags;
  - variant summary, persistence and episodes;
  - seasonality and January-February tables;
  - placebo results; event test and chance rates;
  - control and reference shares; hold-out view;
  - stage-1 counts by year, sensor, processing family and scaling status;
  - read errors and B11 exclusions by year and cause;
  - baseline sizes against the screening's;
  - reproduction checks;
  - figures under 300 KB;
  - `results.md`, with the mechanical verdict;
  - `run_manifest.json`, with:
    - the git blob of this file and the commit;
    - the hashes of the screening config, this validation config, the site files, the event
      catalog and the rain grid;
    - the full-period and 2022-2025 item-id hashes;
    - library versions.
- **Case file.** `pipeline/out/case/urra.json`, copied to `docs/urra-validation/urra.sample.json`
  only if it is under 300 KB.
  - Its interface block names the river and the municipality, never the dam or the company.
  - Any permit in it is marked simulated: holder "simulated permit holder", limit
    "illustrative limit, not the real licence".
  - It never uses the classification `candidate_human_pressure`.
  - Real names appear only in a separate context block marked "public-source context, not an
    accusation".
- **Never committed:** rasters, caches, HydroBASINS files.

## Runs

The runs use the `Urrá validation` GitHub Actions workflow (decision D12's pattern):

1. a grid run, which commits `rain-grid.csv`;
2. a smoke run: stage 1 only, no NDTI; reproduction hashes, counts by year, Open-Meteo cell and
   CHIRPS status;
3. the full run, whose small outputs are committed back by the workflow.

## Deviation protocol

- **A technical failure** (network, timeout, runner) is rerun, unchanged.
- **A bug found after results were seen** is fixed. Both results are reported, and the change is
  listed under Deviations.
- **Never changed after this pre-registration:** N, the variants, the thresholds, the windows, the
  rainy months and the event catalog.
- **A missing target, control or target rain** gives the verdict "not computable". It is never
  replaced by a different reach or rule.

## Deviations

None yet.
