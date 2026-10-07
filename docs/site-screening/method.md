# Site screening: pre-registered method

**Status: pre-registered on 2026-10-07, before any run on real imagery.** The rules and numbers
below were fixed and committed before the first real run. Each run records this file's git blob
hash in `results/run_manifest.json`. Any later change is listed under [Deviations](#deviations),
with its date and reason. Every threshold lives in `pipeline/screening.yaml`, and every site in
`pipeline/sites/<id>.yaml`; the code is in `pipeline/src/climate_pipeline/screening/`.

## Purpose

The goal is to choose the study reach for detecting river turbidity anomalies with Sentinel-2.
The candidates are diversified by pressure type:

- **A**: reaches immediately downstream of dams.
- **B**: two mining benchmarks.
- **C**: one dredging or sand-extraction reach.
- **D**: one control reach without an identified major pressure.

The hypothesis under test is that reservoir operations give discrete, datable events that
Sentinel-2 can observe. This is a hypothesis, not a fact.

The turbidity proxy is the Normalized Difference Turbidity Index, NDTI = (red − green) /
(red + green). It is a **relative index**:

- Its level is comparable only within one sub-reach, never between sites.
- It is never converted to turbidity units (NTU).

An anomaly is an observation that NDTI departed from its own baseline. It is a flag to
investigate. It is never evidence that any actor caused anything.

## Data

| Input          | Source                                                                            | Notes                                                        |
| -------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Sentinel-2 L2A | STAC collection `sentinel-2-l2a`, Earth Search v1 (default) or Planetary Computer | COG assets `scl`, `red` (B04), `green` (B03), `swir16` (B11) |
| Period         | 2022-01-01 to 2025-12-31                                                          | inclusive                                                    |
| Rain           | Open-Meteo historical archive, hourly `precipitation`                             | reanalysis-based grid; context, not measurement              |
| Events         | `docs/site-screening/events.csv`                                                  | dates exactly as sources give them; see its notes            |

## Stage 1: observability, from SCL only

1. **Grid.** Each site has one grid: the UTM zone of its AOI center, 20 m for SCL and B11, and a
   nested 10 m grid for red and green. Every item is read onto that grid by nearest-neighbour
   warping, so tiles from different MGRS squares or UTM zones line up pixel for pixel.
2. **Acquisitions.** Items are grouped by platform, UTC day and relative orbit, keeping the
   highest processing baseline of each MGRS tile. Overlapping tiles fill each other's gaps (the
   first tile with data wins). Every count below counts acquisitions, not items.
3. **Water frequency.**
   - A pixel's clear observations are acquisitions where its SCL class is neither no data (0)
     nor invalid (1, 3, 8, 9, 10, 11).
   - Its water frequency is the share of those observations with class 6. It is only defined
     with at least 20 clear observations.
   - Classes 2 and 7 count as clear, and are reported separately.
4. **River mask.** The river is every pixel with water frequency ≥ 0.5, minus the site's
   `exclude_polygons`.
   - If the two anchors do not connect at 0.5, the run tries 0.35 and then 0.25. This fallback
     is for rivers SCL rarely calls water. The threshold used is reported for every site.
5. **Main channel and centerline.**
   - Both anchors from the site file are snapped to the nearest river pixel within 1.5 km, and
     the distances are reported.
   - The main channel is the 4-connected river region containing them. 4-connectivity keeps pits
     and floodplain lakes that touch the river only diagonally out.
   - For connectivity and the centerline only, mask gaps up to 2 pixels (40 m) wide, such as
     bridges or rapids, are bridged by a morphological closing; bridged pixels are never counted
     as water.
   - The centerline is the shortest path between the anchors inside that region. Diagonal steps
     must not cut a land corner. Chainage is the distance along the centerline from the upstream
     anchor.
   - The corridor is the main-channel pixels within the corridor half-width of the centerline:
     600 m by default, or the site's override.
6. **Sub-reaches.**
   - Two windows, each 2 km of chainage long.
   - The upstream one starts as close to 1 km below the upstream anchor as possible. The
     downstream one is 5–15 km further, center to center (target 10 km).
   - Placements are tried in 250 m steps, and the lowest cost wins, where cost =
     |separation − 10 km| plus twice the extra distance below the upstream anchor. Placements with
     a tributary confluence inside a window (± 1 km) are avoided whenever possible; if
     unavoidable, the site is flagged. A confluence between the windows is reported.
   - **Dams:** the anchors are chosen below the dam and outside the reservoir and its backwater,
     so both sub-reaches are downstream of it.
7. **Per acquisition and sub-reach**, counted in 10 m pixel equivalents (one 20 m SCL pixel = 4):
   - data coverage (share of the sub-reach with data);
   - water pixels (class 6);
   - valid pixels (data and not invalid, whatever class);
   - contamination (invalid / pixels with data);
   - shares of classes 2 and 7;
   - `suspect_turbid_as_cloud`: cloud classes (8, 9, 10) cover ≥ 50 % of the river while ≤ 10 % of
     the land ring is cloud. The land ring is the non-river pixels 100–400 m from the sub-reach.
8. **Scene rules** (both sub-reaches must pass):
   - **clear** (the brief's rule, used in the score): ≥ 200 water pixels, contamination < 20 %,
     data coverage ≥ 90 %;
   - **observable** (used by stage 2): the same, with valid pixels instead of water pixels. SCL
     often labels very turbid water as soil or unclassified. The clear rule would drop exactly
     those scenes, and stage 2 must not.
9. **Per site**:
   - scene counts per month;
   - % of the 48 months with ≥ 1 clear scene;
   - longest gap between clear scenes (period edges included);
   - clear share in the rainy versus dry months;
   - mean daily rain on clear days versus all days;
   - MGRS tiles and relative orbits, and the share of acquisitions needing more than one tile;
   - tile integrity: the share of acquisitions with data where both sub-reaches are ≥ 99 % covered;
   - per-platform counts;
   - scaling-metadata status counts.

   Rainy months are those whose mean daily rain at the site center, 2022–2025, is above the
   median of the twelve monthly means.

10. **Width proxy.** Each sub-reach is upsampled to 10 m and eroded by the site's bank erosion
    (default 1 pixel, 2 on canyon reaches). Width = area ÷ length, in 10 m pixels. The site
    width is that of the narrower sub-reach. Below 5 pixels, NDTI at 10 m is unreliable.

## Score (pre-registered)

Each term is in [0, 1] and anchored in absolute units. Terms are never rescaled across the
candidate sites.

| Term                                | Weight | Definition                                                                                                                   |
| ----------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Clear-scene coverage                | 0.30   | ½ · min(1, clear scenes per year ÷ 24) + ½ · (share of months with a clear scene)                                            |
| Width adequacy                      | 0.20   | clamp((width − 5) ÷ (15 − 5)) in 10 m pixels after erosion                                                                   |
| Tile integrity                      | 0.10   | share of acquisitions with data where both sub-reaches are ≥ 99 % covered                                                    |
| Sub-reach contrast feasibility      | 0.15   | min(1, median water pixels of the weaker sub-reach on clear scenes ÷ 400), halved when a confluence falls inside a sub-reach |
| Documented events in a clear window | 0.25   | min(1, n ÷ 3), where n counts scored events (below) with a clear scene in their window                                       |

**Hard gates.** A site is excluded whatever its score if:

- its mask failed (anchors not found or not connected, reach too short, empty sub-reach);
- its width is under 5 px;
- it has fewer than 24 clear scenes over the period.

**Stage-2 selection.** Stage 2 takes the three best eligible non-control sites by score, with at
most one mining benchmark (category B), and adds every eligible control.

**Sensitivity.** The ranking is recomputed with each term dropped (the remaining weights
renormalized), and once with coverage computed from the observable rule instead of the clear
rule. A ranking that changes under these checks is reported as fragile.

**Recommendation rule.**

- The recommended study reach is the highest-scoring eligible site in category A or C. The
  runner-up is the next one.
- Mining benchmarks are scored and reported, but are not recommended as the study reach (design
  decision of the brief).
- Stage-2 results and event validation describe the recommended sites. They do **not** re-rank
  them, which avoids choosing after seeing the anomalies.

## Stage 2: NDTI on the selected sites

1. **Scenes.** Every observable acquisition of the site, up to 400 per site (any excess is
   logged and reported).
2. **Reflectance.**
   - reflectance = DN · scale + offset, using each item's own `raster:bands` scale and offset.
     Nothing is hard-coded, and the conversion happens per item before tiles are merged.
   - The offset is cross-checked against the item's processing baseline: ≥ 04.00 implies −0.1,
     older implies 0.
   - A scene with a disagreeing or missing offset is listed and **not used**. A wrong +0.1 keeps
     water plausible but pulls NDTI toward zero.
   - _Amended after the first real runs:_ an item flagged `earthsearch:boa_offset_applied`
     already carries the offset in its pixels and gets offset 0 (see [Deviations](#deviations)).
3. **Empirical check.** In each sub-reach, the median red and green reflectance of all water
   pixels (before the darkness and glint guards of step 4) must lie in (0, 0.3]. Otherwise the
   scene is excluded and listed. _Amended after the first real runs:_ the median B11 of the same
   pixels must also lie in [−0.03, 0.08], because water absorbs SWIR (see
   [Deviations](#deviations)).
4. **Pixels.** A pixel is used if all of these hold:
   - it is inside the eroded sub-reach;
   - its SCL is not no-data and not invalid, whatever class SCL gives the water;
   - red + green > 0.01;
   - B11 ≤ 0.05 (higher means likely glint or a mixed pixel).

   With fewer than 200 such pixels, the sub-reach is missing for that scene. The share of used
   pixels that SCL calls water and the share dropped for glint are reported.

5. **Signals.** These are computed per scene:
   - the median NDTI of each sub-reach (upstream, downstream);
   - their difference (downstream − upstream).

   The difference cancels much of the atmosphere, glint and season. It is the headline signal
   for a local pressure between the sub-reaches. For dam sites both sub-reaches are below the
   dam, so the per-sub-reach signals carry an operation's effect.

6. **Baselines.** These are leave-one-out robust statistics: median, and σ = max(1.4826 · MAD,
   0.01). For each value, the baseline is the first group, in this order, that has enough other
   values:
   1. same dam regime and season;
   2. same regime;
   3. same season;
   4. all.

   Season groups need 8 values and the others 12; otherwise the result is "insufficient baseline"
   (never "no anomaly"). Regimes are delimited by the site's day-precision `regime_changes`.
   Seasons are the site's rainy and dry months.

7. **Anomaly.** |z| ≥ 3 on any of the three signals.
8. **Rain.**
   - Hourly rain is taken at each of the site's rain points (the center, plus up to three
     upstream).
   - Sums cover the 24, 72 and 168 hours ending at the acquisition hour. Same-day rain is local
     midnight (America/Bogota) to the acquisition.
   - An anomaly is **rain-coincident** when the wettest point had > 20 mm in the 72 hours before.

## Event validation

- An event is **scored** when it is dated to the day or the week and its window overlaps the
  period. Month-precision events are context only.
- The event window runs from 2 days before the event start to 10 days after its end. The same
  window is used for the score term.
- Each scored event of a stage-2 site gets one outcome:
  - **unobservable**: no usable scene in the window;
  - **hit**: some usable scene in the window has |z| ≥ 3 on any signal;
  - **miss**: there are usable scenes, but none reaches the threshold.
- All three are reported. A site whose documented events show no signal is a finding, and stays
  in the report.
- **Chance rate.** 500 windows of the same length are placed at random (seed 20260101), skipping
  any that overlap a catalog event of the site. The chance rate is the share of observable random
  windows that hit.
- **Control.** The share of the control's scored scenes with any anomalous signal is its
  false-alarm rate.

## Outputs and reproducibility

- **Committed.** `docs/site-screening/results/` holds the stage-1 summary and monthly counts, the
  scores with sensitivity ranks, the stage-2 scenes, event validation, results.md, PNG
  quick-looks under 300 KB, and `run_manifest.json`. The manifest records the method blob, config
  and events hashes, the commit, and a SHA-256 of each site's STAC item ids.
- **Not committed.** `pipeline/out/` (per-acquisition rows and caches). No raster is ever
  committed.
- **Where it runs.** The real run is the `Site screening` GitHub Actions workflow. The development
  sandbox cannot reach the STAC APIs.

## Post-hoc secondary analysis (declared 2026-10-07, after the first real run)

The first real run, on the four dam reaches, showed that SCL almost never labels three of them as
water: Hidroituango had 24 pixels with a water frequency of 0.9 or more, where a 20 km river
about 100 m wide would need about 5,000. Their masks failed even at the 0.25 fallback, so the
pre-registered score gates them out whatever their real observability. A second, **post-hoc**
analysis is declared here, before it is run, and reported next to the pre-registered one. It
never replaces it. Only two rules change:

1. **Water mask.**
   - Where the SCL mask fails at every threshold, the river mask comes from an MNDWI water
     frequency instead (the pre-registered thresholds 0.5, 0.35 and 0.25 are tried in the same
     order).
   - MNDWI = (green − SWIR1) / (green + SWIR1) is computed per acquisition from B03, averaged to
     20 m, and B11, both on reflectance with each item's scale and offset.
   - A clear observation is an SCL value that is neither no data nor invalid, with both bands
     present. It counts as water when MNDWI > 0.
   - Each site reports which mask it used.
2. **Score.** Coverage, the clear-scene gate and contrast feasibility use the **observable** rule
   (valid river-mask pixels whatever their SCL class) instead of SCL water pixels. The weights,
   anchors, other gates and the stage-2 selection and recommendation rules are unchanged.

Stage 2, the event validation and every other threshold are identical. The outputs go to
`results-posthoc/`.

## Deviations

Any change after the first real run is listed here with its date, what changed, why, and whether
results were seen before the change.

Corrections made before any real run (no results existed):

- 2026-10-07, formatting: line wrapping had turned the "+" of the sub-reach placement cost into a
  Markdown bullet, so the formula read "− 2 ×". The formula is now written out in words; the code
  always used "+".
- 2026-10-07, implementation brought in line with this method after a code review:
  - a sub-reach with too few pixels is now missing for that scene, rather than dropping the
    whole scene;
  - pixels without a B11 value are no longer used;
  - the land ring is measured in Euclidean distance;
  - the chance rate uses each event's own window length;
  - a window whose usable scenes all lack a baseline is reported as "insufficient baseline", not
    "unobservable";
  - the recommendation rule and the fragility check are now produced in the outputs;
  - Hidroituango, a canyon reach, uses the 2-pixel bank erosion stated in step 10.
  - the empirical reflectance check of stage 2 now uses every water pixel, before the darkness
    and glint guards; otherwise a too-negative offset would hide itself by making water too dark
    to pass the guards (wording of stage 2, step 3 clarified).
  - mask gaps up to 40 m wide (bridges, rapids) are bridged for connectivity only (stage 1,
    step 5), so one bridge cannot fail a site.
- 2026-10-07, robustness:
  - anchors are snapped together onto the river region that connects them, so a nearer pond or
    reservoir cannot take an anchor;
  - Open-Meteo hourly values are treated as the sum over the hour ending at their timestamp,
    as the API documents (an earlier one-hour shift was removed);
  - rainy months use only the days inside the study period.
- 2026-10-07, after a first real run that could not start (no data read, no results):
  the Earth Search address `earth-search.aws.amazon.com` does not resolve in DNS; the
  screening now uses Element 84's documented host, `earth-search.aws.element84.com/v1`.

Changes made after real results had been seen:

- 2026-10-07, reflectance offset applied twice (results seen: runs 2 and 6, stage 2 at
  `sinu-urra` and the post-hoc masks).
  - **Evidence.** The median B11 of water pixels at Urrá was below −0.05 in 22 of the 27 scenes
    where it could be computed (most between −0.06 and −0.086). Water absorbs SWIR, so its B11
    reflectance is near 0. The same shift explains two other observations:
    - 13 dry-season Urrá scenes were excluded for negative red reflectance;
    - the post-hoc MNDWI mask found 16 always-water pixels where SCL found 34,354 (the Betania
      reservoir). An offset applied twice turns MNDWI's sign over water.
  - **Cause, as inferred from the pixels.** Earth Search items flagged
    `earthsearch:boa_offset_applied: true` already carry the −0.1 offset in their pixel values,
    while their `raster:bands` still list it. This reading comes from the pixels, not from
    documentation; the new B11 check guards against the opposite reading.
  - **Change.**
    - Flagged items now use offset 0. Their scaling status is reported as `offset-in-pixels`.
    - Stage 2 excludes and lists any scene whose median water B11 lies outside [−0.03, 0.08]
      (`stage2.water_swir16_range`). An offset applied twice gives about −0.1 and a missing one
      about +0.1.
    - The post-hoc MNDWI mask skips any acquisition whose 0.5th-percentile B11 (water and shade)
      is below −0.03, and reports how many it skipped.
  - **Effect.**
    - Stage 1 and the pre-registered score use SCL only and do not change.
    - The stage-2 and post-hoc results of runs 2 and 6 are superseded. They remain in the git
      history (commits `aeb8472` and `17fa25b`).
- 2026-10-07, sites added after the first real run: the two mining benchmarks (B), the dredging
  reach (C) and the control (D) were planned from the start. Their research was blocked when the
  build session's web-search budget ran out, and they joined after the dam sites had been run.
  No rule, threshold or weight changed with them.
- 2026-10-07, event catalog after an adversarial re-check (results seen: the Urrá event
  outcomes of runs 2 and 6). Each catalog event was searched for independent confirmation, and
  the outcome is in its `verification` column. Changes:
  - `sinu-urra-02`: description corrected. The inflow rise it quoted belongs to 21 Jul 2025, so
    it is now its own event, `sinu-urra-06`.
  - `sinu-urra-04`: extended to 30 Nov 2025 (four-unit operation, same source).
  - `sinu-urra-05` (14 Aug 2022) and `magdalena-betania-07` (2-3 Jun 2025) were added.
  - `magdalena-betania-01` was narrowed from October 2022 to 31 Oct 2022, from its own source.
  - `cauca-hidroituango-04` and the Salvajina descriptions lost figures no second summary
    supported.
  - The new reaches got their events. Mining operations that sources place downstream of the
    Nechí reach (La Esperanza, Puerto Nuevo) were left out, because they cannot show in it.
  - No event was dropped for its outcome.
- 2026-10-07, after run 11 (results seen; the per-site water-mask quick-looks were added for this
  check):
  - **Corridor.** The code now keeps only band pixels connected to the centerline inside the band,
    as stage 1, step 5 says ("main-channel pixels"). Before, any river-mask pixel within the
    half-width counted, so at the Nechí the downstream sub-reach took in floodplain pits about
    500 m from the channel that join the river only outside the band.
  - **Anchors corrected against the water mask**, as the brief asks. Two estimated downstream
    anchors lay off the river and could not be snapped, so they were moved onto the channel the mask
    shows:
    - `meta-orocue`, about 4 km;
    - `magdalena-betania`, about 4 km.

    No threshold, gate or weight changed.
