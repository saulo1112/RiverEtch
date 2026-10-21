# Site screening report: choosing the study reach

**Status:** final screening run of 2026-10-07 (Actions run 12, commit `2a8508a`), reproduced byte
for byte by run 13 on commit `b597450`. Outputs are in [results/](results/results.md) and
[results-posthoc/](results-posthoc/results.md). The method was pre-registered in
[method.md](method.md) before any real run; every later change is listed under its
[Deviations](method.md#deviations). The real run executed in GitHub Actions, not in the development
sandbox, which cannot reach the data services (see [Network probe](#network-probe)).

> NDTI is a **relative index**. Its level is comparable only within one sub-reach, never between
> sites, and it is never turbidity in NTU. An anomaly is a departure from the reach's own
> baseline: a flag to investigate, never evidence that any actor caused anything.

## Decision summary

| Rank (pre-registered rule) | Reach                                                                   | Category      | Score | Why it ranks here                                                                                                                                                                                      |
| -------------------------- | ----------------------------------------------------------------------- | ------------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1, recommended**         | Río Magdalena, Puerto Wilches to San Pablo (`magdalena-puerto-wilches`) | C (dredging)  | 0.673 | Best observability by far: 65 clear scenes (16 a year, 81 % of months), 31 px wide. But 0 anomalies in 61 usable scenes, and no source dates dredging inside the reach, so nothing could be validated. |
| **2, runner-up**           | Río Sinú below the Urrá I dam (`sinu-urra`)                             | A (reservoir) | 0.627 | Fewer clear scenes (31, 7.8 a year), adequate width (9.5 px). A regulated operator and dated operations. 1 of 2 observable events is a hit, but the chance rate is 0.26.                               |

- **The ranking is fragile.** Dropping either the coverage term or the width term puts Urrá first.
  The post-hoc variant gives the same top two.
- **Fallback:** if neither reach supports a natural event the demo can stand on, run the demo on
  the Urrá reach with a **clearly labeled synthetic test event** injected into its real NDTI
  series. It must never be presented as an observation (see [Recommendation](#recommendation)).
- **Main finding on the hypothesis:** reservoir operations did **not** show up as consistent,
  datable NDTI events in this screening.
  - Three of the four dam reaches could not be observed with the pre-registered SCL mask.
  - Two of them are too narrow for 10 m NDTI even with the post-hoc MNDWI mask.
  - At Urrá, one documented operation coincides with an anomaly, at a rate a random window
    reaches about a quarter of the time.

## Network probe

Probe of the development sandbox before any code was written (Step 0 of the brief). STAC was
unreachable, so, as the brief requires, nothing was worked around: everything was built and tested
offline, and the real run happens in the `Site screening` workflow.

| Host                                                      | Reachable from the sandbox | Status                                                         |
| --------------------------------------------------------- | -------------------------- | -------------------------------------------------------------- |
| earth-search.aws.amazon.com (STAC, as given in the brief) | no                         | proxy 403 on CONNECT; later found not to resolve in DNS at all |
| sentinel-cogs.s3.us-west-2.amazonaws.com (COG assets)     | yes                        | 200                                                            |
| archive-api.open-meteo.com                                | no                         | proxy 403                                                      |
| planetarycomputer.microsoft.com (STAC + SAS)              | no                         | proxy 403                                                      |
| sentinel2l2a01.blob.core.windows.net (PC assets)          | no                         | proxy 403                                                      |
| data.chc.ucsb.edu (CHIRPS)                                | no                         | proxy 403                                                      |
| stac.dataspace.copernicus.eu                              | no                         | proxy 403                                                      |
| pypi.org                                                  | yes                        | 200                                                            |
| WebSearch (server-side)                                   | yes                        | works; WebFetch is egress-blocked                              |

In GitHub Actions, Earth Search v1 (at Element 84's host `earth-search.aws.element84.com/v1`), the
COGs on S3 and the Open-Meteo archive were all reachable.

## Method in brief

The full method is in [method.md](method.md).

- **Data.** Sentinel-2 L2A from Earth Search, 2022-01-01 to 2025-12-31, read as COGs onto a per-site
  UTM grid (20 m SCL and B11, 10 m red and green). Items are grouped into acquisitions (platform,
  day, relative orbit). Rain is hourly Open-Meteo reanalysis at each site's rain points.
- **Stage 1 (observability, SCL only).**
  - The water mask is the share of clear observations that SCL calls water (class 6).
  - Anchors are snapped to the river within 1.5 km, the centerline is the shortest path between
    them, and the corridor is the main channel within 600 m of it.
  - Two 2 km sub-reaches are placed 5-15 km apart.
  - A scene is **clear** when both sub-reaches have at least 200 water pixels, under 20 %
    contamination and at least 90 % data.
- **Score.** Five terms, with absolute anchors:
  - coverage, 0.30;
  - width, 0.20;
  - tile integrity, 0.10;
  - sub-reach contrast feasibility, 0.15;
  - documented events with a clear scene in their window, 0.25.

  Hard gates: mask failed, width under 5 px, fewer than 24 clear scenes. Stage 2 takes the top
  three non-control sites (at most one mining benchmark) plus the control. The recommendation is
  the best eligible A or C site.

- **Stage 2 (NDTI).**
  - NDTI = (red − green) / (red + green), on reflectance scaled per item.
  - Scenes whose water is implausible are excluded and listed. Water must be dark in red and green
    and near 0 in B11.
  - Robust leave-one-out z per sub-reach and for the downstream − upstream difference. An anomaly
    is \|z\| ≥ 3.
  - An anomaly is **rain-coincident** when a rain point had over 20 mm in the 72 h before.
- **Events.** A scored event (day or week precision) is a **hit** when a usable scene within −2/+10
  days of it reaches \|z\| ≥ 3. It is a **miss** when usable scenes exist but none does, and
  **unobservable** when there is no usable scene. Each event is compared with the share of random
  windows of the same length that hit (the chance rate).
- **Post-hoc variant** (declared after the first run, reported next to the pre-registered one):
  where the SCL mask fails, the mask comes from MNDWI, and the score counts observable scenes
  (valid pixels whatever SCL's class) instead of clear ones.

### Changes after real results were seen

All are in [Deviations](method.md#deviations).

1. **Earth Search reflectance offset.** Items flagged `earthsearch:boa_offset_applied` already
   carry the −0.1 BOA offset in their pixels, and the code applied it a second time. The
   empirical check caught it: water B11 was about −0.08 where it should be near 0.
   - Flagged items now use offset 0.
   - A B11 guard excludes any scene whose water B11 lies outside [−0.03, 0.08]. It also catches
     unflagged Sentinel-2C items whose pixels carry the offset anyway.
   - This invalidated the stage-2 and post-hoc results of the first runs, which are superseded.
2. **The added reaches.** The B, C and D reaches were researched and added after the dam reaches
   had run. The research had been blocked by a web-search budget. No rule changed.
3. **Event catalog.** The catalog was re-checked adversarially, and corrected and extended (see
   [Event validation](#event-validation)).
4. **Corridor.** The corridor was restricted to water connected to the main channel, as the method
   states. Before, mining pits about 500 m off the Nechí entered a sub-reach.
5. **Anchors.** Two estimated downstream anchors lay about 4 km off the river (`meta-orocue`,
   `magdalena-betania`). They were corrected against the water-mask quick-looks, as the brief asks.

## Stage 1: observability

Run 12; both variants. Width is in 10 m pixels after bank erosion. "Clear" is the pre-registered
rule; the post-hoc variant counts "observable" scenes.

| Reach                      | Cat. | Acq. | Pre-registered (SCL mask)                           | Clear | Clear/yr | Months with clear | Longest gap (d) | Width (px) | Score | Eligible    | Post-hoc mask         | Observable | Width (px) | Score | Eligible    |
| -------------------------- | ---- | ---: | --------------------------------------------------- | ----: | -------: | ----------------: | --------------: | ---------: | ----: | ----------- | --------------------- | ---------: | ---------: | ----: | ----------- |
| `cauca-hidroituango`       | A    |  627 | failed: anchors are not connected by the river mask |     0 |        0 |               0 % |            1461 |          – |     0 | no          | MNDWI, threshold 0.5  |         80 |        1.2 |  0.75 | no (width)  |
| `cauca-salvajina`          | A    |  308 | failed: anchors are not connected by the river mask |     0 |        0 |               0 % |            1461 |          – |     0 | no          | MNDWI, threshold 0.35 |         42 |        3.0 | 0.409 | no (width)  |
| `sinu-urra`                | A    |  308 | reach derived (threshold 0.25)                      |    31 |     7.75 |            47.9 % |             139 |        9.5 | 0.627 | yes         | SCL, threshold 0.25   |         31 |        9.5 | 0.627 | yes         |
| `magdalena-betania`        | A    |  318 | failed: anchors are not connected by the river mask |     0 |        0 |               0 % |            1461 |          – |     0 | no          | MNDWI, threshold 0.5  |         47 |        5.6 | 0.602 | yes         |
| `nechi-zaragoza`           | B    |  318 | failed: anchors are not connected by the river mask |     0 |        0 |               0 % |            1461 |          – |     0 | no          | MNDWI, threshold 0.5  |         38 |       13.1 | 0.652 | yes         |
| `atrato-quibdo`            | B    |  308 | reach derived (threshold 0.5)                       |     6 |      1.5 |            12.5 % |             669 |       21.9 | 0.478 | no (6 < 24) | SCL, threshold 0.5    |          6 |       21.9 | 0.478 | no (6 < 24) |
| `magdalena-puerto-wilches` | C    |  319 | reach derived (threshold 0.5)                       |    65 |    16.25 |            81.2 % |              99 |       30.6 | 0.673 | yes         | SCL, threshold 0.5    |         65 |       30.6 | 0.673 | yes         |
| `meta-orocue`              | D    |  319 | failed: anchors are not connected by the river mask |     0 |        0 |               0 % |            1461 |          – |     0 | no          | MNDWI, threshold 0.5  |         61 |       16.9 | 0.652 | yes         |

What the table shows:

- **SCL rarely calls these rivers water.** Five of the eight reaches could not be derived from SCL
  even at the 0.25 fallback threshold.
  - At Hidroituango only 24 pixels had a water frequency of 0.9 or more, where a 20 km river about
    100 m wide would need several thousand.
  - The MNDWI mask recovers all five. The [mask quick-looks](results-posthoc/figures/) show each
    derived reach.
- **The Cauca canyon reaches are too narrow for 10 m NDTI.** Below Hidroituango and Salvajina, the
  water the MNDWI mask sees is 4.8 and 5.2 px wide before erosion, and 1.2 and 3.0 px after.
- **The Atrato at Quibdó is barely observable:** 6 clear scenes in four years, the longest gap
  669 days. This means "not observable", not "clean".
- **Clear days are drier days.** Mean daily rain on clear days against all days:
  - Urrá: 5.4 against 9.1 mm.
  - Puerto Wilches: 5.0 against 11.9 mm.
  - Meta: 2.0 against 6.3 mm.

  Clear-sky imagery under-samples wet conditions, so rain-driven turbidity is seen less often
  than it happens.

- **Anchor shifts.** Snapping moved every anchor less than 1.2 km. The mask quick-looks (one per
  site, in `results/figures/` and `results-posthoc/figures/`) show configured against snapped
  anchors.

### Sensitivity of the ranking

| Variant        | Without coverage | Without width | Without tile integrity | Without contrast | Without events | Coverage from observable rule |
| -------------- | ---------------- | ------------- | ---------------------- | ---------------- | -------------- | ----------------------------- |
| Pre-registered | Urrá first       | Urrá first    | unchanged              | unchanged        | unchanged      | unchanged                     |
| Post-hoc       | Urrá first       | Betania first | unchanged              | unchanged        | unchanged      | unchanged                     |

The recommendation rests on coverage and width: the two terms where the Magdalena is strongest.
The events term (0.25) gives the Magdalena 0, because no scored event exists for it.

## Stage 2: NDTI results

| Reach                      | Variant       | Observable | Usable | Excluded                                                   | Anomalous | Not rain-coincident |
| -------------------------- | ------------- | ---------: | -----: | ---------------------------------------------------------- | --------: | ------------------: |
| `magdalena-puerto-wilches` | both          |         65 |     61 | B11 check 3 (offset applied twice), too few water pixels 1 |         0 |                   0 |
| `sinu-urra`                | both          |         31 |     26 | B11 check 5 (2 offset applied twice, 3 sun glint)          |         7 |                   6 |
| `nechi-zaragoza`           | post-hoc only |         38 |     37 | B11 check 1                                                |         2 |                   0 |
| `meta-orocue` (control)    | post-hoc only |         61 |     41 | B11 check 20 (17 sun glint, 3 offset applied twice)        |         1 |                   1 |

Every excluded scene is listed in `stage2_scenes.csv` with its reason. Across the usable scenes,
the median water B11 is 0.016 to 0.033 depending on the reach, as expected for river water. Before
the offset fix it was about −0.08.

### Río Sinú below Urrá I (A)

The two sub-reaches track each other closely ([series](results/figures/sinu-urra_series.png),
[maps](results/figures/sinu-urra_maps.png)). The seven anomalies:

| Scene      | Signal                | Max z | Rain 72 h (mm) | Rain-coincident | Catalog context                                                                                                              |
| ---------- | --------------------- | ----: | -------------: | --------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 2022-12-07 | downstream            |   3.3 |            9.2 | no              | 7 days after the reported spillway overflow of 30 Nov 2022 (`sinu-urra-01`, a hit)                                           |
| 2023-12-02 | downstream            |   3.0 |           10.2 | no              | none                                                                                                                         |
| 2024-01-16 | downstream − upstream |   3.9 |            5.3 | no              | none; strong glint (66-76 % of water pixels above the B11 glint limit)                                                       |
| 2024-02-10 | downstream − upstream |   5.6 |           12.0 | no              | none                                                                                                                         |
| 2024-02-25 | downstream − upstream |   3.0 |            8.7 | no              | none                                                                                                                         |
| 2025-11-06 | downstream            |   3.8 |           34.2 | yes             | none                                                                                                                         |
| 2025-12-16 | downstream            |   3.9 |           11.2 | no              | 6 days after the window of `sinu-urra-04` closes (reservoir above 130 m a.s.l. and four units from 30 Nov 2025); not counted |

Reading the anomalies:

- **Jan–Feb 2024 difference anomalies.** The three anomalies of the downstream − upstream
  difference fall in a dry period, when water reflectance is lowest and NDTI least stable. They
  show the downstream sub-reach relatively less negative than the upstream one, a pattern that is
  a candidate to investigate between the two sub-reaches. No catalog event covers it, and nothing
  here says what produced it.
- **2025-12-16 anomaly.** It falls just outside the pre-registered event window. The window was not
  widened after the fact.
- **The control comparison.** 27 % of usable Urrá scenes are anomalous, against 2.4 % at the
  control, in the post-hoc variant. The Urrá baselines are also short (26 usable scenes split by
  season), which inflates z.

### Río Magdalena, Puerto Wilches to San Pablo (C)

- **No anomaly in 61 usable scenes.** The downstream − upstream z stays within ±2.3 for the whole
  period ([series](results/figures/magdalena-puerto-wilches_series.png)).
- **The chance rate of a random window is 0** (99 observable windows).
- **No dated dredging inside the reach.** The catalog has only context rows:
  - the 2024-2026 maintenance-dredging contract for the whole 640 km sector;
  - a 2023 dredge at the Sitio Nuevo sector, whose position relative to the reach is unknown.

  So the absence of anomalies cannot be read as "dredging leaves no signal": no source says when
  or where dredging happened in this reach.

### Post-hoc only: Nechí (B) and the Meta control (D)

- **Nechí.** 2 anomalies (14 Nov 2023 and 10 Nov 2025), both rain-coincident (51 and 44 mm in 72 h).
  This is the mining benchmark selected by the rule.
- **Meta control.** False-alarm rate 0.024: 1 anomalous scene of 41, on 15 Jan 2023, downstream,
  not rain-coincident. Its random-window chance rate is 0.027. Sun glint over the wide dry-season
  river removed 17 of 61 observable scenes.

## Event validation

28 catalog events in total; 22 are scored (day or week precision). Every event was searched
adversarially for independent confirmation, and the result is in the `verification` column of
[events.csv](events.csv):

- Hidroituango: 3 confirmed by outlets other than the original, 1 description corrected.
- Urrá: 1 confirmed, 1 corrected (it mixed two dates), 2 found by the re-check.
- Salvajina: all 3 supported only by summaries of their own source.
- Betania: dates sharpened from the operator's own releases, plus 1 new event.

Stage 2 could test only the events of the stage-2 sites:

| Event               | Date (source)         | Outcome      | Max \|z\| | Signal     | Rain-coincident scene | Chance rate |
| ------------------- | --------------------- | ------------ | --------: | ---------- | --------------------- | ----------: |
| `sinu-urra-01`      | 2022-11-28 to 11-30   | **hit**      |       3.3 | downstream | no                    |        0.26 |
| `sinu-urra-02`      | 2025-07-12 to 07-13   | miss         |      1.02 | downstream | yes                   |        0.23 |
| `sinu-urra-03`      | 2025-08-01 to 08-02   | unobservable |           |            |                       |        0.23 |
| `sinu-urra-04`      | 2025-11-29 to 11-30   | unobservable |           |            |                       |        0.23 |
| `sinu-urra-05`      | 2022-08-14            | unobservable |           |            |                       |        0.23 |
| `sinu-urra-06`      | 2025-07-21            | unobservable |           |            |                       |        0.23 |
| `nechi-zaragoza-01` | 2024-10-16 (post-hoc) | unobservable |           |            |                       |        0.07 |
| `nechi-zaragoza-03` | 2025-08-11 (post-hoc) | miss         |      0.78 | difference | yes                   |        0.07 |

**Hits: 1. Misses: 2. Unobservable: 5.**

- **The one hit is not distinguishable from chance.** About a quarter of random windows at Urrá
  also contain an anomaly.
- **Untested events:**
  - Hidroituango (4 scored) and Salvajina (2 scored) were gated out in both variants.
  - Betania's 6 scored events were not tested: in the post-hoc variant it is eligible but ranks
    fifth, outside the stage-2 set.
  - The Atrato's 2 floods were not tested: the reach is gated out (6 clear scenes).
  - The Magdalena and the control have no scored event by construction.

## Caveats

- **Relative index only.** NDTI levels are comparable only within one sub-reach, never across
  sites, and are never NTU. There is no in-situ turbidity data, so no anomaly is ground-truthed.
- **SCL misses turbid water.** This decided the pre-registered stage 1 at five of eight reaches.
  The post-hoc MNDWI analysis was declared after seeing that failure and is reported next to it,
  never instead of it.
- **Reflectance scaling.** It depends on Earth Search metadata that proved inconsistent; the
  empirical B11 guard is what makes the stage-2 numbers usable. Three items (two from 23 Jan 2024,
  one from 7 Feb 2023) pointed to legacy JP2 files that do not exist. They were skipped and
  recorded in the run manifest.
- **Clouds, glint and dryness.** Clear scenes are rarer in the wet season and on wet days, so
  rain-driven turbidity is under-sampled. Glint removes many dry-season scenes over wide rivers.
  The Chocó reach is effectively unobservable.
- **Width.** Below about 5 px after erosion, edges and mixed pixels dominate. Both Cauca canyon
  reaches are below that.
- **Rain** is Open-Meteo reanalysis at a few points, not gauge data. The 20 mm / 72 h
  rain-coincidence rule is a convention, not a calibrated threshold.
- **Events** come from search-result summaries; no page was opened (WebFetch was blocked). Many are
  single-source. The scored windows (−2/+10 days) were fixed in advance and were not adjusted after
  results were seen.
- **Short baselines.** The leave-one-out baselines are short at Urrá (26 usable scenes) and fall
  back to season-only groups. That makes \|z\| ≥ 3 easier to reach than at the well-observed
  Magdalena.
- **Corridor geometry.** Chainage follows a pixel staircase (lengths up to about 8 % long). On
  braided reaches (Magdalena, Meta) the corridor includes side arms within 600 m of the centerline.

## What I could not verify

- **Positions.**
  - Every coordinate in `pipeline/sites/`: dams, towns, confluences, anchors. Each comes from
    search summaries or from estimates off a named place, then corrected by snapping or against
    the mask quick-looks.
  - Each site file lists its own unverified items, notably:
    - where the Río Porce joins the Nechí, and whether its dams affect the reach;
    - whether the corrected Betania anchor lies above or below the Río Neiva confluence;
    - the Río Quito and Río Cravo Sur confluence positions;
    - all river widths stated by sources.
- **The meaning of `earthsearch:boa_offset_applied`.** It is inferred from the pixels (water B11),
  not from documentation. Some unflagged Sentinel-2C items behave like flagged ones. The guard
  excludes them instead of guessing.
- **Event dates and descriptions.** All come from search-result summaries:
  - Salvajina: no independent confirmation; summaries of the cited report disagree on its
    discharge figure.
  - Betania 01, 02, 05, 06: the operator's own releases only.
  - Urrá 03 and 04: one outlet only.
  - Nechí: single-source floods, one possibly dated by its report rather than its occurrence.
- **Dredging at the Magdalena reach.** No source found names the crossings dredged in 2024-2025 or
  their dates. That the "Canta Gallo" critical point lies inside the reach is inferred from the
  town's position. The environmental authority for that dredging (ANLA, CAS or CSB) is unconfirmed.
- **The control's "no identified major pressure"** means none was found in the searches. Dams
  upstream were checked with one search only (Chivor and Guavio are in the Andean departments,
  far upstream).
- **Operators and regulators.** Named as public sources name them, from summaries.
- **Thresholds.** Every threshold (water frequency 0.5, the 5 px width gate, \|z\| ≥ 3, the B11
  range, the rain rule) is a pre-set convention, not calibrated against ground truth.
- **Data paths not exercised on real data.** The Planetary Computer source path never ran on real
  data. Its items lack `raster:bands` scaling, so they would be excluded.

## Recommendation

1. **Recommended by the pre-registered rule: Río Magdalena, Puerto Wilches to San Pablo
   (`magdalena-puerto-wilches`).**
   - It is the most observable reach screened by a wide margin: 65 clear scenes, 81 % of months,
     31 px wide, one tile and one orbit.
   - Its NDTI series is stable: no anomaly in 61 usable scenes, chance rate 0.
   - It is inside a contracted maintenance-dredging sector, but no public source places dated
     dredging inside the reach. Before it can carry a narrative, it needs dated activity at named
     crossings, for example from Cormagdalena's contract reports.
2. **Runner-up: Río Sinú below Urrá I (`sinu-urra`).**
   - Half the clear scenes of the Magdalena, adequate width, an operator and regulators named in
     public sources, and dated operations.
   - It has one hit that a random window would match about a quarter of the time, and a cluster of
     dry-season difference anomalies with no catalog event.
   - It wins the ranking if either coverage or width is dropped.
3. **Fallback:** if the chosen reach yields no defensible natural event, demonstrate the pipeline
   on the Urrá reach with a **synthetic test event**: a known NDTI step injected into a copy of its
   real series, labeled as synthetic everywhere it appears. The proof then shows the mechanics
   (baseline, anomaly, rain flag) without claiming an observation.

**Not recommended:**

- the Cauca canyon reaches below Hidroituango and Salvajina: too narrow for 10 m NDTI;
- Betania: post-hoc only, and barely wide enough at 5.6 px;
- the Atrato at Quibdó: not observable;
- the Nechí: a mining benchmark, which the brief excludes as the study reach, and observable only
  with the post-hoc mask.

## Fit for the demo narrative

The demo needs three things: a natural anomaly that is not explained by rain, an identifiable
regulated operator, and a permit parameter a proof could be about.

| Need                                       | Magdalena, Puerto Wilches                                                                                          | Sinú below Urrá I                                                                                                                                                                                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anomaly not rain-coincident                | none in 61 scenes                                                                                                  | 6 of 7 anomalies, including 2022-12-07, 7 days after a reported spillway overflow; weak against a 0.26 chance rate                                                                                                                                      |
| Regulated operator named in public sources | Cormagdalena (contracting entity) and Consorcio PanMar-Vías 2023 (contractor); environmental authority unconfirmed | URRÁ S.A. E.S.P. (operator), ANLA (licence follow-up), CVS (regional authority)                                                                                                                                                                         |
| Permit parameter a proof could be about    | not found; a dredging licence would plausibly set conditions on sediment plumes or disposal, but none was sourced  | not found; the licence would plausibly set discharge or flow-ramping conditions, but no public value was sourced. A proof could attest "NDTI downstream exceeded its own baseline within N days of a documented operation", which needs no permit value |
| Dated events to validate against           | none inside the reach                                                                                              | 6 scored, 2 observable                                                                                                                                                                                                                                  |

For the demo story, the Urrá reach fits better than the Magdalena: it has dated operations, a
named regulated operator and at least one observation inside an event window. The Magdalena has the
better imagery and nothing yet to anchor a story to. The screening's pre-registered rule ranks the
Magdalena first, and that ranking is fragile. The choice between "best imagery" and "best story" is
a human decision; this report does not make it.

## Reproducibility

- **Runs.** `run_manifest.json` in each results folder records:
  - the git blob of method.md;
  - the config and events hashes;
  - the commit;
  - a SHA-256 of each site's STAC item ids.
- **Same archive every time.** The item-id hashes of the four dam reaches were identical in runs 7,
  11 and 12, and those of all eight reaches in runs 11 and 12. So Earth Search returned the same
  archive each time.
- **Same numbers on a deterministic re-run.**
  - Run 13 re-ran all eight reaches, both variants, with unchanged code, config and catalog. Every
    CSV, figure and table matches run 12 byte for byte; only the commit and the timestamps in the
    manifest differ.
  - Earlier, with the same code, the pre-registered stage-1 rows of the dam reaches were identical
    in runs 2, 6 and 7.
- **Re-running.** From `pipeline/`, run `uv run climate-pipeline screening --root ..`
  (`--sites`, `--start` and `--end` pick a subset); it needs network access to the services above.
  The `Site screening` workflow that made the committed runs was removed afterwards
  ([D24](../decisions.md)); it stays in the git history.
