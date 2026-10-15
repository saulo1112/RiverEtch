# Water-quality estimates v2: preregistration

**Status: written on 2026-10-10, before any new value was fetched or computed.** Every value lives in
`pipeline/water-quality.yaml`. The pixel guards, SCL classes and water-B11 range are read unchanged
from `pipeline/screening.yaml`. The code is written after this file, in
`pipeline/src/climate_pipeline/quality/`. Each run records this file's git blob hash and the commit.
Any later change is listed under [Deviations](#deviations), with its date and reason. Decision: D16.

> NDTI, NIR/red and every band ratio are relative indices until a level below says otherwise. No
> output states that any actor caused anything. A physical unit is shown only for a target, range and
> station set that reached the level _estimated_ or _validated_, and always with its interval.

## Why a second validation

The calibration validation (D15, [report](../magdalena-validation/calibration-report.md)) ended at
_baselined_. On L2A, the NIR/red ratio B8A/B04 tracked measured turbidity (ρ 0.76 [0.34, 0.90]), but
on 20 training pairs at 10 Magdalena stations, with 7 hold-out pairs where 8 were needed. Under
ACOLITE the ratio fell to ρ 0.33. Published models gave a median symmetric accuracy (MdSA) of
100–336 %. Its diagnosis: too few pairs, one river, narrow channels (adjacency), clouds and
disagreeing atmospheric corrections. This validation attacks each cause and publishes a declared
error instead of a pass or fail.

## Questions

1. **Transfer.** Trained only on other rivers (other Colombian rivers and large USGS rivers), what
   error does a model reach for turbidity (NTU) and total suspended solids (TSS, mg/L) on the
   Magdalena main stem from Sentinel-2 L2A? (Route A)
2. **Adjacency.** Does an adjacency correction (ACOLITE RAdCor) remove the L2A–ACOLITE disagreement
   of D15? (Route B)
3. **Published and pretrained models.** Do Dogliotti 2015, Nechad and the MDN transfer to the
   Magdalena on ACOLITE reflectance? (Route B)
4. **What the product publishes.** For each target and range: a level (_validated_, _estimated_ or
   _indicative_), and for the first two a value with an interval of known coverage.

An honest "indicative only" is a valid outcome and is reported first.

## What was already seen

Disclosed in full, because the Magdalena pairs were analysed in D15 and some criteria were set after
metadata probes.

1. **Everything D15 produced:**
   - the 27 turbidity and 27 TSS pairs at 10 Magdalena stations (values, L2A features, splits);
   - the 73 `CM_D` pairs at Nariño;
   - the ACOLITE (DSF) medians of 29 scenes, with their B11;
   - every Stage 1–5 table and figure.
2. **Metadata probes on 2026-10-10** (no sample value at any new station):
   - **datos.gov.co `62gv-3857`:** turbidity and TSS sample counts per stream, per point and per year
     since 2013 (for example, 1,683 turbidity samples since 2018-12 at 215 points, 278 of them on the
     Magdalena), and the dataset's owner and licence.
   - **IDEAM bucket:**
     - the variable catalogue (`CS_PROMEDIO_D` is not published);
     - the 127 `CM_D` files, which were downloaded to count, per station, the days in
       2018-12..2026-09 and the approval states. No `CM_D` value was summarised.
   - **USGS Water Data API:**
     - the list of continuous turbidity series (parameter 63680, 1,554 sites) and the
       monitoring-location metadata (drainage areas);
     - while testing the API, five 15-minute turbidity values at Colorado River near Cameo
       (09095500) on 2023-06-01, 80.0–86.6 FNU. Cameo is not a pilot site: its drainage area is under
       the threshold.
   - **Imagery catalogues:** item counts and processing baselines per year over the Puerto Wilches
     reach, on Earth Search (`sentinel-2-l2a`, `sentinel-2-c1-l2a`) and Planetary Computer
     (`sentinel-2-l2a`). Collection 1 lacks 66 of 72 L2A dates in 2022, 16 in 2019 and every date
     before 2018.
   - **Software and datasets:**
     - the MDN repository (licence, requirements, weight files, and the text config of its two MSI
       weight archives);
     - ACOLITE's settings at the pinned commit (RAdCor);
     - the GLORIA, Dethier, RivSed and AquaSat records.

**Not seen:**

- any sample value at a station off the Magdalena;
- any USGS turbidity or SSC value at a pilot site;
- any band value at a station off the Magdalena or at a USGS site;
- any RAdCor, MDN or Planetary Computer reflectance;
- any value dated 2015-07..2018-11 at any station.

## Design

- **Route A, the product route.**
  - Sen2Cor L2A surface reflectance from cloud-optimized GeoTIFFs: Earth Search for acquisitions from
    2018-12-01, Planetary Computer for 2015-07-01..2018-11-30.
  - Models trained on other rivers, adjusted to Colombian units.
  - It needs no credentials, so it can run unattended.
- **Route B, the physics check.**
  - ACOLITE water-leaving reflectance (its dark-spectrum fitting, DSF, as in D15, and RAdCor), with
    published or pretrained models.
  - It never publishes a value: Level-1C downloads need the project owner's account.
- **A frozen test set:** every Magdalena main-stem pair. Training, tuning and selection never see it.
  Each candidate is evaluated on it once.

## Data (all fetched on this machine)

| Source                              | What                                                                      | Access                                    | Licence                 |
| ----------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------- | ----------------------- |
| Earth Search `sentinel-2-l2a`       | Route A imagery from 2018-12-01: B02–B8A, B11, B12, SCL                   | STAC + HTTP range reads                   | Copernicus open licence |
| Planetary Computer `sentinel-2-l2a` | Route A imagery 2015-07-01..2018-11-30                                    | STAC + SAS-signed range reads (anonymous) | Copernicus open licence |
| Earth Search `sentinel-2-c1-l2a`    | Sensitivity, where it has the date                                        | STAC + HTTP range reads                   | Copernicus open licence |
| datos.gov.co `62gv-3857`            | Turbidity and TSS samples on the listed streams                           | SODA, cached, SHA-256                     | CC BY-SA 4.0 (IDEAM)    |
| IDEAM bucket `s3-estacionesideam`   | `Q_MEDIA_D`, `NV_MEDIA_D` (flow stability); `CM_D` (report-only)          | S3 list + CSV, SHA-256                    | CC BY-SA 4.0 (IDEAM)    |
| USGS Water Data API                 | Continuous turbidity (63680, FNU) and discrete SSC (80154) at pilot sites | OGC API, cached, SHA-256                  | US public domain        |
| ACOLITE, commit `ca477dd`           | Route B: DSF (the D15 runs) and RAdCor                                    | Local, from the saved Level-1R files      | GPL-3.0 (run as a tool) |
| MDN, commit `ae1626c`               | Route B: pretrained TSS from Rrs                                          | Separate environment                      | GPL-3.0 (run as a tool) |

ACOLITE and the MDN run in their own environments, so the project's `uv.lock` does not change and no
GPL code enters the repository. IDEAM snapshots keep their licence and attribution.

**Fetch and run are separate, as in D15.** `climate-pipeline quality fetch` snapshots every raw input
under `docs/water-quality/inputs/` with a fetch manifest (URL, status, bytes, SHA-256, UTC). Long
series are committed as the subset the analysis uses, with the full response's SHA-256 and size in
the manifest. `climate-pipeline quality run` recomputes every result offline, and
`quality verify` compares the outputs with a committed `MANIFEST`.

## Stations and sites (metadata only, frozen before values are fetched)

### Colombian stations

1. **Streams:** MAGDALENA, CAUCA, SINU, ATRATO, META, SOGAMOSO, NECHI, SAN JORGE, CARARE, LEBRIJA,
   PATIA, MIRA, AMAZONAS, PUTUMAYO, CAQUETA, GUAVIARE, ORINOCO and CANAL DEL DIQUE.
   - A stream matches exactly after accents, case and surrounding spaces are removed, so named arms
     are excluded, as in D15.
   - The list holds every stream with turbidity samples that is wide somewhere along its course. It
     was set from sample counts, before any value.
2. **Candidates:** `62gv-3857` points on those streams with at least one turbidity or TSS sample dated
   2015-07-01 or later.
3. **Main channel, snap and width:** D15's rule, unchanged.
   - The water frequency comes from SCL over the 2022–2025 acquisitions: water where it is ≥ 0.5,
     with at least 20 clear observations.
   - The MNDWI mask applies when SCL fails selection.
   - The station must snap within 1.5 km, to a main channel at least 150 m wide.
   - The Magdalena stations are selected again under this rule. Any difference from D15's list is
     reported.
4. **Flow series for the stability rule:**
   - the station's own `Q_MEDIA_D` (else `NV_MEDIA_D`), matched by the IDEAM code in the point name;
   - else the nearest catalogue station on the same stream within 10 km that has one;
   - else none.
5. **Group:** the stream. Leave-one-river-out (LORO) holds out one stream at a time. The Magdalena
   is the test group.

### USGS pilot sites

1. **Candidates:** monitoring locations of site type stream with a continuous 63680 series
   (computation `Points`) overlapping 2018-12-01..2026-09-30, and a drainage area of at least 20,000
   square miles (35 sites at the probe).
2. **Main channel, snap and width:** the same rule as for Colombian stations, on Earth Search L2A
   over 2022–2025.
3. **Group:** the river named in the site name (Mississippi, Missouri, Ohio, Kansas…). Sites on the
   same river share a group.

The selected lists (ids, names, coordinates, snap distance, width, files, sample counts, no values)
are committed before any value is fetched.

## Windows and extraction

- **Primary window:** D15's, unchanged.
  - Main-channel pixels within 300 m of the snapped point, after a 2-pixel erosion.
  - Valid pixels are those whose SCL class is neither no-data nor invalid. Pixels with B11 > 0.05
    are glint and leave the medians.
  - The scene is excluded when its median water B11 is outside [−0.03, 0.08].
  - A scene needs at least 20 water pixels and contamination ≤ 0.2.
- **Core window (sensitivity):** pixels of the primary window whose distance to land is ≥ 60 m.
- **Bands:** B02–B07, B08, B8A, B11 and B12 on the 20 m grid, with 10 m bands averaged.
  - Scaling follows each item's metadata, as in the screening.
  - Planetary Computer items carry no `earthsearch:boa_offset_applied`. The offset follows their
    processing baseline, and the water-B11 check catches a wrong offset.
- **Read grid:** ±400 m around the snapped point. D15's windows are not touched.
- **SCL is read first.** The other bands are not read when no window can pass the scene guards
  (D15's deviation 4).
- **Which scenes:**
  - **Colombian stations:** the scenes within ±3 days of a sample.
  - **USGS sites:**
    - every acquisition in 2018-12-01..2026-09-30 whose item cloud cover is ≤ 70 %;
    - then, of the scenes that pass the guards, at most 200 per site, drawn with the seed and
      stratified by year.
- **Source split:** a date before 2018-12-01 comes from Planetary Computer, any later date from
  Earth Search. One source per date, never mixed.
- **Source check (report-only, with a rule):** on 2019–2021 dates that both sources hold, at the
  Colombian stations.
  - If the median Planetary Computer minus Earth Search difference of B8A/B04 exceeds 0.5 robust σ,
    Planetary Computer pairs leave the primary analyses and stay as a sensitivity.
  - These reads are bounded at 300 scenes.

## Matchups

- **Colombian samples:**
  - Local dates (America/Bogota) are compared. The nearest usable scene within ±1 day wins (primary);
    a tie goes to the earlier scene.
  - **±3 days (sensitivity)** applies only when the flow was stable between the sample day and the
    scene day:
    - |ln(Q_scene/Q_sample)| ≤ 0.10 on `Q_MEDIA_D`;
    - else a level change ≤ 0.10 m on `NV_MEDIA_D`;
    - else not allowed.
  - Same-station, same-day samples are reduced to their median. Values reported as "<x" are kept,
    flagged and never fitted.
- **USGS turbidity:**
  - The value is the median of `Approved` 15-minute values within ±30 min of the acquisition time
    (UTC). Failing that, it is the nearest approved value within ±60 min; failing that, there is no
    pair.
  - A value that carries any qualifier is excluded.
- **USGS SSC (80154):** discrete samples on the acquisition's local day at the site. They are the TSS
  proxy in pretraining. If the samples endpoint cannot be read, TSS trains on Colombian pairs only,
  and the report says so.
- **Clusters:** one acquisition (platform, date, orbit) is one cluster. Every bootstrap resamples
  acquisitions, as in D15.

## Targets

| Target      | Colombian value              | USGS value              | Unit                |
| ----------- | ---------------------------- | ----------------------- | ------------------- |
| `turbidity` | `62gv-3857` TURBIDEZ         | 63680, continuous       | NTU (USGS: FNU)     |
| `tss`       | `62gv-3857` SOLIDOS SUSP. T. | 80154, discrete (proxy) | mg/L                |
| `cm_d`      | IDEAM `CM_D`, report-only    | —                       | mg/L (rating model) |

- **FNU and NTU are different units.** They diverge in very turbid water. No model treats them as
  one: USGS pairs train the shape, and a Colombian adjustment maps it to NTU (below).
- **`cm_d` is a consistency check only.** At Colombian stations with same-day `CM_D`, the report
  gives the partial Spearman of the predicted turbidity with `CM_D` given log discharge. It is labelled
  "IDEAM rating-model daily concentration" everywhere.

## Features (Route A)

The set **F** is computed from the band medians of each scene:

- log of B02, B03, B04, B05, B06, B07, B08 and B8A (each floored at 0.0001);
- log of the ratios B8A/B04, B05/B04, B06/B04, B07/B04, B04/B03 and B04/B02;
- B8A − B11 and B11, linear;
- the sun zenith angle, from `view:sun_elevation` (Earth Search) or `s2:mean_solar_zenith` (Planetary
  Computer);
- the log of the channel width at the station, and the core share of the window.

Station ids, coordinates and dates are never features.

## Candidates (predeclared; each is evaluated on the test set once)

| Id  | Route | Model                                                                             | Fitted on                                          |
| --- | ----- | --------------------------------------------------------------------------------- | -------------------------------------------------- |
| M0  | A     | Null: median of the training targets                                              | Colombian pairs off the Magdalena                  |
| A1  | A     | log-log OLS on B8A/B04                                                            | Colombian pairs off the Magdalena                  |
| A2  | A     | log-log OLS on B8A/B04, pretrained, then the Colombian adjustment                 | USGS pairs, then Colombian pairs off the Magdalena |
| A3  | A     | Ridge on F in log space, pretrained, then the Colombian adjustment                | Same                                               |
| A4  | A     | Gradient-boosted trees (LightGBM) on F, pretrained, then the Colombian adjustment | Same                                               |
| B1  | B     | Dogliotti 2015 red–NIR switch (turbidity), ACOLITE coefficients                   | Published                                          |
| B2  | B     | Nechad 2009 (turbidity) and 2010 (TSS), ACOLITE coefficients                      | Published                                          |
| B3  | B     | MDN multi-product model, TSS output (Rrs 443, 490, 560, 665, 705, 740, 783 nm)    | Pretrained weights                                 |

- **The Colombian adjustment:** log y = a + b·log ŷ, fitted by ridge on (a, b − 1).
  - λ comes from {0.1, 1, 10}, chosen by leave-one-station-out (LOSO) on the Colombian pairs off the
    Magdalena.
  - With fewer than 10 such pairs, the adjustment is a = 0, b = 1 and the report says so.
- **Hyperparameters:**
  - **A3:** λ from {0.01, 0.1, 1, 10, 100}, chosen by LORO over USGS rivers.
  - **A4:**
    - the grid has num_leaves {7, 15, 31}, min_data_in_leaf {20, 50} and n_estimators {200, 500},
      with learning rate 0.05, chosen by LORO over USGS rivers;
    - deterministic, one thread, the seed below;
    - it is trained in a separate environment and exported as JSON. The pipeline evaluates the trees
      with numpy and checks them against the lab's predictions.
- **Route B inputs:** the medians over the exact L2A pixels (D15's deviation 5).
  - B1 and B2 use the ACOLITE surface reflectance (`rhos`). It equals `rhow` where ACOLITE's water
    mask keeps the pixel.
  - B3 uses Rrs = `rhos`/π.
  - Each is computed for DSF and for RAdCor.
- **Route B models never become the product's model.**

## Selection, test and refit

- **Selection** is by LORO over the Colombian streams off the Magdalena (outer folds), on MdSA.
  - In each fold, the adjustment of A2–A4 and the fit of A1 exclude the held-out stream.
  - The product model is the candidate among A1–A4 with the lowest outer MdSA.
  - Within 5 MdSA points, the simpler one wins, in the order A1, A2, A3, A4.
- **Test:** every candidate is evaluated once on the Magdalena pairs:
  - primary: ±1 day;
  - sensitivities: ±3 days with stable flow, the core window, Collection 1, and Planetary Computer
    pairs alone.
- **Refit:**
  - After the test, the selected model's adjustment is refit with the Magdalena pairs included. That
    is the product's model.
  - Its error is reported by LOSO over the Magdalena stations, next to the test error.
  - **Levels use the test error of the model before the refit.**
- **Local ceiling (report-only):** A1 fitted on Magdalena pairs only, scored by LOSO over its
  stations. It never enters selection.

## Metrics

- **MdSA** = 100 × (exp(median |ln(ŷ/y)|) − 1).
- **SSPB** = 100 × sign(m) × (exp(|m|) − 1), with m = median ln(ŷ/y) (Morley et al., 2018).
- **Spearman ρ**, with a 95 % interval from 10,000 acquisition-cluster bootstrap draws.
- **Error by range**, in bins of the _predicted_ value (the only range known when a value is
  published). Bins of the observed value are also reported.
  - Turbidity: < 30, 30–100, 100–300, 300–1,000 and > 1,000 NTU.
  - TSS: < 50, 50–200, 200–500, 500–1,500 and > 1,500 mg/L.
  - A bin with fewer than 8 test pairs is not rated.
- **Interval coverage and median width,** at 80 % and 90 %.
- **MAPE,** as a secondary metric.

## Intervals

- Split conformal in log space: the residual is |ln(y/ŷ)|. The calibration residuals are the outer
  LORO residuals of the selected model.
- **Mondrian:** the calibration residuals are split into terciles of ŷ.
- Per tercile, q is the ⌈(n + 1)(1 − α)⌉-th smallest residual, and the interval is [ŷ·e^(−q),
  ŷ·e^(q)], with α = 0.20 and 0.10.
- Coverage is checked on the Magdalena test. After the refit, the quantiles are recomputed with the
  Magdalena LOSO residuals added, and both coverages are reported.

## Levels (per target and predicted range)

| Level          | Criteria (Magdalena test, model before the refit)                                                                           | What a record shows                                                                                 |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **validated**  | MdSA ≤ 50 %, \|SSPB\| ≤ 25 %, MdSA ≤ 0.8 × the null model's; N ≥ 20 at ≥ 4 stations; 90 % interval coverage in [80 %, 97 %] | Value, interval and range, worded "validated on the Magdalena main stem at stations X–Y, range A–B" |
| **estimated**  | MdSA ≤ 60 %, \|SSPB\| ≤ 30 %, MdSA below the null model's; 90 % coverage in [80 %, 97 %]                                    | Value, interval and range                                                                           |
| **indicative** | Neither, but Spearman ρ with a 95 % lower bound > 0.3                                                                       | A relative class (low, medium or high, from the station's own history); no unit                     |
| **none**       | None of the above                                                                                                           | The relative index only                                                                             |

- A bin with fewer than 8 test pairs gets the level of its target as a whole, capped at _estimated_.
- **Abstention, at prediction time, as in D15:**
  - a feature outside its training range;
  - glint share > 0.5;
  - contamination > 0.2;
  - fewer than 20 valid pixels;
  - a failed B11 check;
  - a window too cloudy to measure.

## Route B: adjacency and published models

- **DSF:** the 29 scenes of D15, as processed. Their saved Level-2R files are measured again to add
  `rhos` at 443 nm and the medians of ACOLITE's `rhow`. D15's snapshot is not changed.
- **RAdCor:** the same 29 scenes, from their saved Level-1R files.
  - The settings are D15's `settings.txt` plus `atmospheric_correction_method=radcor` and
    `radcor_edge_extend=True` (`pipeline/acolite/settings-radcor.txt`).
    - The saved boxes are ±0.05° (about 5.5 km) and the kernel is 5 km. Without extending the
      edges, RAdCor masks every pixel whose kernel leaves the box, and two of the ten stations snap
      0.85–1.16 km from the box centre.
    - The other RAdCor settings are ACOLITE's defaults (5 km kernel, `radcor_max_vza=15`, TSDSF
      aerosol, edges extended by the box average). The extra outputs (top-of-atmosphere,
      environment and uncorrected surface reflectance) are not written (changed by deviation 1:
      top-of-atmosphere reflectance is written).
    - ACOLITE carries a one-line patch of its RAdCor deconvolution (deviation 1).
  - **Time box:** 4 h of processing.
  - If ACOLITE cannot process a saved Level-1R file, the project owner downloads the Level-1C
    products again for a box of ±0.08°. That is recorded as a deviation.
- **Adjacency is confirmed when both hold:**
  - RAdCor's Spearman ρ of B8A/B04 with turbidity, on D15's 20 training pairs, is ≥ 0.6;
  - the median B11 at stations narrower than 250 m is lower under RAdCor than under DSF.
- **If adjacency is confirmed, Route A's primary window becomes the core window** for training and
  test. The 300 m window is still reported. This is the only result-dependent choice, and it is fixed
  here.
- **MDN:** the MSI multi-product model at commit `ae1626c`, no retuning.
  - The weight archive is `Weights/MSI/1b79098d…`, whose config reads product `chl,tss,cdom`,
    `n_mix` 5, `sat_bands` False, version 2.0.0.
  - Only its TSS output is used.
  - If its environment cannot be built within 3 h, B3 is dropped and the report says so.

## Optional stages (run only if chosen at the checkpoint of 2026-10-18)

- **Landsat 8/9:**
  - Planetary Computer `landsat-c2-l2` (Collection 2 Level-2), 2013-04-01..2026-09-30, at stations
    whose main channel is ≥ 240 m wide;
  - the same matchup rules, with a sensor term in A1–A4;
  - reported as a sensitivity and as a separate candidate set.
- **GLORIA (report-only):** spectra convolved to the MSI bands, to compare the B8A/B04–TSS shape with
  the satellite pairs.
- **Dethier et al. (report-only):** their Landsat SSC calibration, on Landsat pairs at the Colombian
  stations.

## Budgets and stop rules

- **Disk:** every fetch stops when free disk space falls under 20 GB. The new data on disk are planned
  at ≤ 6.5 GB at the peak.
- **Network:**
  - ≤ 15 GB for the Colombian stations;
  - ≤ 60 GB for the USGS sites;
  - ≤ 2 GB for the reach's NIR/red baseline;
  - ≤ 15 GB for Landsat, if it runs.

  A stage that reaches its cap is `incomplete`, with what it has.

- **An unreachable source** makes its stage `incomplete`, reported at the top of the report.
- **Read errors:** transient errors are rerun. Assets in a non-public bucket count as no data, as in
  D15's deviation 3. Any other read error requires a rerun before results count.
- **Without enough data:**
  - with fewer than 15 USGS pairs, A2–A4 are `insufficient_data`;
  - with fewer than 8 Magdalena test pairs, every level is `none` for that target.

## What will not be done

- No threshold, window, candidate, split, bin or seed is changed after a pair table or any result is
  seen.
- No Magdalena pair enters training, tuning or selection before the single test evaluation.
- No candidate other than those above is evaluated on the test set.
- No ACOLITE or MDN value is published by the product.
- No physical unit is shown for an _indicative_ or _none_ record.
- No comparison with a licence or discharge limit ([regulatory.md](../magdalena-validation/regulatory.md)).
- No actor is said to have caused anything.

## Runs and reproducibility

1. `climate-pipeline quality fetch --stations-only` commits the Colombian station list and the USGS
   site list before any value.
2. `climate-pipeline quality fetch` snapshots every value. The ACOLITE and MDN runs follow their
   READMEs.
3. `climate-pipeline quality run` writes the results under `docs/water-quality/results/` with a
   `MANIFEST` in `sha256sum` format.
4. `climate-pipeline quality verify` recomputes the results offline and compares CSV and JSON byte
   for byte (figures are hashed, marked "same-machine"). CI runs it.
5. `climate-pipeline calibration verify` must still reproduce D15 byte for byte.

The seed is 20261010. Every network step is resumable from its cache.

## Checkpoint 2 decisions (2026-10-11, before any Landsat value or post-hoc number)

The checkpoint came a week early: on the Magdalena test every candidate failed every level
(turbidity: A3, the selected model, 135 %; TSS: 249 %). The project owner chose two further
stages. Both are written here before anything they compute exists.

### Phase 3: Landsat 8/9 (the optional stage above, specified)

- **Data:**
  - Planetary Computer `landsat-c2-l2`, platforms Landsat 8 and 9, 2015-07-01..2026-09-30 (the
    Colombian samples start in 2015-07).
  - Tier 1 scenes only (`landsat:collection_category` T1), the ones fit for time series.
  - The selected Colombian stations whose main channel is ≥ 240 m wide (their D15 width). The list
    is committed before any Landsat value.
- **Reflectance:** SR = DN × 2.75 × 10⁻⁵ − 0.2 (Collection 2 Level-2). Bands: blue SR_B2, green
  SR_B3, red SR_B4, NIR SR_B5, SWIR-1 SR_B6, SWIR-2 SR_B7.
- **Window:** the bands are resampled (nearest) onto the station's 20 m grid. The Sentinel-2
  station windows are used unchanged: the 300 m window and the core window (≥ 60 m from land; the
  primary window, since adjacency was confirmed). A 30 m pixel then never mixes more land than at
  20 m inside the core.
- **Pixel and window guards** (as D15's, with QA_PIXEL in place of SCL):
  - a pixel is unusable when QA_PIXEL flags fill, dilated cloud, cirrus, cloud, cloud shadow or
    snow;
  - contamination is the share of window pixels so flagged;
  - SWIR-1 plays B11's part (pixel guard 0.05, water median in −0.03..0.08);
  - the thresholds are those of the Sentinel-2 windows (≥ 20 valid pixels, contamination ≤ 0.2,
    glint share ≤ 0.5).
- **Matchups:** the same rules: ±1 day primary, ±3 days with stable flow as the sensitivity.
- **Candidates (Landsat set, each evaluated once on the Magdalena Landsat pairs):**
  - **L1:** log-log OLS on NIR/red, fitted on Colombian Landsat pairs off the Magdalena.
  - **L2:** A2's USGS model (log-log on B8A/B04) applied to Landsat NIR/red, then the Colombian
    adjustment fitted on the Landsat pairs off the Magdalena.
  - **Pooled sensitivity:** A1 and A2 on Sentinel-2 and Landsat pairs together, with a sensor
    term: log y = α + β·log r + γ·[Landsat].
  - **Not run:** A3 and A4 on Landsat. Their feature set F uses the red-edge bands B05–B07,
    which Landsat lacks, and there are no USGS Landsat pairs to pretrain a reduced set.
- **Selection, levels and intervals:** as for Sentinel-2. Selection is by LORO over the Colombian
  rivers off the Magdalena, within the Landsat set. The levels and the conformal rule are
  unchanged.
- **Budget:** ≤ 15 GB of network; the fetch stops under 20 GB of free disk.

### v2.1: a post-hoc calibration on the Magdalena

The frozen test has been used. A model now fitted on Magdalena pairs cannot be tested on them
again. Its error comes from nested leave-one-station-out (LOSO) over the Magdalena stations. Its
label is **post hoc**, never _validated_.

- **Pairs:** the Magdalena pairs of the sensitivity set: ±1 day, plus ±3 days with stable flow.
  They use the core window. Sensitivities:
  - the ±1-day pairs alone;
  - the 300 m window;
  - the Landsat Magdalena pairs added with a sensor term, once Phase 3 has them.
- **Candidates (predeclared, in order of simplicity):**
  - **P1:** log-log OLS on B8A/B04 (A1 fitted on the Magdalena).
  - **P2, P3, P4:** the USGS-pretrained A2, A3 and A4, then the adjustment log y = a + b·log ŷ
    fitted on the Magdalena (ridge on (a, b − 1), λ from {0.1, 1, 10} by inner LOSO).
  - **P5:** ridge in log space on four features: log B8A/B04, log B04/B03, log B04/B02 and
    B8A − B11. λ comes from {0.1, 1, 10, 100} by inner LOSO.
  - **M0:** the median of the training pairs.
- **Nested LOSO, the error that counts:**
  - for each Magdalena station, the candidates are scored by LOSO over the other stations;
  - the one with the lowest MdSA is chosen (within 5 points, the simpler one wins);
  - it is fitted on the other stations and predicts the held-out station.

  The held-out predictions measure the whole procedure, selection included.

- **Intervals:** for each held-out station, the conformal quantiles come from the chosen
  candidate's inner LOSO residuals. The rule is the Mondrian one, with deviation 4's pooled
  fallback. Coverage is the share of held-out pairs inside their intervals.
- **Level (post hoc, per target and predicted range):** _estimated (post hoc)_ when the nested
  LOSO gives:
  - MdSA ≤ 60 %;
  - |SSPB| ≤ 30 %;
  - MdSA below the nested null's;
  - 90 % coverage in [80 %, 97 %].

  _Indicative (post hoc)_ when Spearman ρ has a 95 % lower bound > 0.3, from acquisition-cluster
  bootstrap draws. A range with fewer than 8 pairs gets the target's level, capped at _estimated
  (post hoc)_.

- **The published model:**
  - the same selection on every Magdalena pair, then a fit on all of them;
  - its model card and every record state the basis "post hoc, nested LOSO on the Magdalena";
  - values appear only at _estimated (post hoc)_, with the interval from the nested residuals.
- **Report-only sensitivity:** leave-one-year-out (by hydrological year, December to November).
- **Reported side by side:** the preregistered result (v2, level none) and the post-hoc one.

### v2.2: a post-hoc calibration on the physical correction (2026-10-11, before computing it)

The project owner accepted running ACOLITE operationally if it helps: Level-1C products downloaded
with the owner's Copernicus account, and RAdCor for adjacency. Route B's published models used no
Magdalena fit and already reached 80 % (Dogliotti 2015 on RAdCor). This stage asks whether a
Magdalena fit on that reflectance does better than v2.1 on L2A. It follows v2.1's rules: nested
LOSO, labelled post hoc, never _validated_.

- **Stage A (no download):** the Magdalena pairs Route B already has under RAdCor (D15's pairs and
  300 m windows: 27 turbidity, 26 TSS).
- **Candidates (in order of simplicity):**
  - **R1:** the published model as it is. Turbidity: Dogliotti 2015. TSS: the MDN (Route B's best
    on RAdCor).
  - **R2:** R1, then the adjustment log y = a + b·log ŷ fitted on the Magdalena (ridge on
    (a, b − 1), λ from {0.1, 1, 10} by inner LOSO).
  - **R3:** log-log OLS on RAdCor's B8A/B04 (`rhos`), fitted on the Magdalena.
  - **M0:** the median of the training pairs.
- **Evaluation, intervals and levels:** exactly v2.1's.
- **Stage B (downloads), only if Stage A does better than v2.1:**
  - Stage A's nested-LOSO MdSA must be below v2.1's for turbidity or for TSS.
  - Then the Magdalena pairs of v2's sensitivity set that Route B lacks are processed the same way
    (Level-1C, ACOLITE RAdCor, the core window's L2A pixels). Stage A's candidates are scored
    again, by nested LOSO on every pair.
  - The downloads stop under 20 GB of free disk, one product at a time.
- **If a level is reached,** the reach's operational runs need ACOLITE: the scene's Level-1C (the
  owner's account, credentials in environment variables only) and RAdCor on a box around the
  estimate station. The record's atmospheric correction then names ACOLITE RAdCor.

### v3: an open search to halve the turbidity error (2026-10-11, before computing it)

The project owner asked for every reasonable attempt to bring the Magdalena turbidity error to at
most half of v2.1's (77 % → ≤ 38 %), without a limit on attempts. The obstacle is data, not the
model class. 184 Magdalena turbidity samples since 2015 give 31 pairs, because a clear scene
within ±3 days is rare. A date-based lock box would hold only 7 pairs, so the search stays honest
another way.

- **Rounds:** each round fixes its candidate space before it is computed, and the report lists
  every round.
- **Error that counts:** a round's error is its nested leave-one-station-out (LOSO) over the
  Magdalena stations. The inner loops choose among the whole candidate space (feature set, pair
  set, penalty), so the error includes the cost of choosing.
- **Test pairs:** the outer test pairs are always the Magdalena pairs within ±3 days with stable
  flow (v2.1's main set), the ones closest to how the product is used. Longer matchups only ever
  train.
- **Later rounds:** a round designed after seeing an earlier one is labelled exploratory. Only
  round 1 is reported as confirmatory.
- **Levels:** as v2.1 (post hoc, never _validated_). A model that uses discharge needs the
  estimate station's daily flow in operation, and its records name that input.

**Round 1 candidate space**

- **Pair sets** (training only):
  - the ±3-day stable set;
  - ±7 days;
  - ±15 days.

  Beyond ±3 days a pair carries the flow ratio g = ln(Q_sample / Q_scene) (Q_MEDIA_D, or the level
  in metres where only NV_MEDIA_D exists). Each sample's pairs are weighted 1/n, so a sample with
  many scenes counts once.

- **Per-sample aggregation:**
  - the nearest scene;
  - the median of the estimates over every valid scene in the window.
- **Feature sets** (ridge in log space, λ from {0.1, 1, 10, 100} by inner LOSO):
  - **S:** log B8A/B04;
  - **S5:** v2.1's four features;
  - **T:** log of A4's USGS estimate;
  - **Q:** log Q_sample (or the level);
  - **G:** g, when the pair set has gaps.

  The combinations S, S5, T, Q, S+Q, S5+Q, T+Q, S+G, S5+G, T+G, S+Q+G, S5+Q+G and T+Q+G are all in
  the space.

- **Physical ensemble:** on the pairs that also have ACOLITE RAdCor, the geometric mean of the
  chosen L2A estimate and Dogliotti 2015 on RAdCor.
- **New imagery:** Sentinel-2 L2A windows, measured as before, for the acquisitions within ±15
  days of a Magdalena sample and of the other Colombian samples. A fetch of its own, capped at
  25 GB of network, keeps the existing snapshots untouched.

**Round 2 (exploratory, 2026-10-11, written before computing it)**

Round 1 reached 71.5 % by nested LOSO (indicative, post hoc). Its inner selection chose T+G on the
±7-day pairs with the nearest scene in 7 of 11 folds. That form's plain Magdalena LOSO, seen with
hindsight, was 38 %: half of v2.1's error, but chosen on the same pairs. Round 2 tests the form on
data round 1 never used.

- **The form, fixed:**
  - a ridge in log space on the log of A4's USGS estimate (T) and the flow change g (G);
  - trained on ±7-day pairs, nearest scene;
  - λ by inner LOSO.
- **Checks:**
  1. **Magdalena LOSO** (biased by hindsight, reported as such).
  2. **External LORO:** the same form on the Colombian rivers off the Magdalena. Each river is
     predicted by a fit on the others, with their ±3-day stable pairs as test units. Round 1 never
     used these data.
  3. **Transfer:** the form fitted on every Magdalena pair, scored on the other rivers' test units.
  4. **Magdalena leave-one-year-out.**
- **The rule for publishing values:** the reach's records may show a value from this form only if
  both of these hold:
  - check 1 meets v2.1's _estimated_ criteria;
  - check 2 gives MdSA ≤ 60 % with |SSPB| ≤ 30 % (the form generalises to other rivers).

  The label is then "estimated (post hoc; form chosen on the Magdalena, confirmed on other rivers)".
  The interval comes from check 1's residuals. Otherwise the product stays at round 1's
  _indicative (post hoc)_.

## v4: a second reach, a temporal validation and Stage B (2026-10-12, before computing any of it)

v3 ended at round 1's _indicative (post hoc)_ (71.5 % by nested LOSO). Round 2 did not confirm its
form. The project owner asked for three things:

1. a river with reliable continuous measurements, as a second demo reach;
2. the lowest out-of-sample error for the Magdalena reach, validated the way the product is used;
3. a closed product.

The owner's choices of 2026-10-12:

- the Missouri River at Hermann (USGS 06934500) as the second reach;
- leave-one-hydrological-year-out as the Magdalena's primary temporal validation;
- RAdCor Stage B for TSS, as v2.2 requires, and also for turbidity (exploratory);
- the observation record v2 schema gains two `basis` values, and each estimate's unit is read from
  its model card.

Each part below is fixed before it is computed. The report counts every round and candidate.

### What was seen before this section

- **USGS pilot (`inputs/usgs/`), per site:**
  - the number of turbidity pairs per year;
  - the 10 %, 50 % and 90 % quantiles of the turbidity values at the drawn scenes, over all years
    (the lock box below included).

  No error of any model at any site was computed or examined.

- **Hermann's earlier use:** its 165 pilot pairs trained A2–A4 in v2 and entered the
  leave-one-river-out tuning of A3's λ and A4's grid (the Missouri fold). Those per-river scores
  were never reported or examined.
- **Magdalena counts:** per-station counts of samples and pairs in each set. San Pablo (23207040),
  the reach's estimate station, has 7 turbidity samples (2021-07..2023-06) and 3 test units. Its
  values are in tables committed with v2.
- **A code review** found that v3's flow features are standardised per station (deviation 9).
- **The water-quality CI** has failed since the v2 merge: the v2.1 turbidity card recorded the
  SHA-256 of its LightGBM file with CRLF line endings (deviation 10).
- **Searches for open continuous turbidity outside the US:**
  - Rijkswaterstaat AQUALARM at Lobith (FTU; the history on request);
  - the Rhône sediment observatory (BDOH: suspended solids derived from turbidity, with an
    account);
  - Elbe stations (no open download found);
  - New South Wales and Queensland portals (continuous turbidity at narrow sites, unconfirmed);
  - ANA (no continuous turbidity found).

  None offers an open, approved, continuous series on a river ≥ 300 m wide that can be fetched now.

### A. The second reach: the Missouri River at Hermann

**Selection.** The hard criteria are:

1. a main channel ≥ 300 m wide;
2. continuous turbidity (63680) since 2017 or earlier, with approved values at clear scenes in
   2024–2026 (a held-out period needs them);
3. no dam on the main stem within the reach;
4. no tributary entering the station window.

Of the 13 pilot sites ≥ 300 m wide:

| Site                         | Outcome                                          |
| ---------------------------- | ------------------------------------------------ |
| Susquehanna near Darlington  | fails: below Conowingo Dam                       |
| Ohio at Olmsted              | fails: at a lock and dam                         |
| Mississippi at Dam 13        | fails: at a dam, and its series starts in 2021   |
| Mississippi at Keokuk        | fails: at a dam, and its series starts in 2021   |
| Mississippi at Clinton       | fails: its series ended in 2021                  |
| Missouri near Council Bluffs | fails: its series ended in 2022                  |
| Missouri at Napoleon         | fails: its series starts in 2023                 |
| Mississippi at Memphis       | fails: its series starts in 2023                 |
| Mississippi at Baton Rouge   | fails: approved values at its scenes end in 2023 |
| Ohio at Ironton              | passes (172 pairs)                               |
| Platte at Louisville         | passes (121 pairs)                               |
| Mississippi at Belle Chasse  | passes (121 pairs)                               |
| Missouri at Hermann          | passes (165 pairs)                               |

The owner chose Hermann among the four that pass:

- its range (p50 51 FNU, p90 263 FNU) is the closest to the Magdalena's;
- Ironton lies in a navigation pool, with a median of 9.5 FNU;
- the Platte is braided and shallow;
- Belle Chasse is tidally influenced, with no 2026 values.

**Data.**

- **Scenes:** every Earth Search L2A acquisition 2018-12-01..2026-09-30 at Hermann with item cloud
  ≤ 70 %, measured and guarded as in the pilot. The pilot drew at most 200; this fetch adds the
  rest. The cap is 4 GB of estimated network.
- **Values:** the pilot's rules (approved 15-minute values, the median within ±30 min of the
  acquisition, else the nearest within ±60 min, qualifiers excluded).
- **Window:** the core window (adjacency was confirmed in v2).
- **Target:** turbidity in FNU only. No TSS is estimated at Hermann.

**Splits.**

- **Training:** pairs dated 2018-12-01..2023-11-30, the hydrological years 2019–2023 (December
  opens the next year).
- **Lock box:** 2023-12-01..2026-09-30. It is evaluated once.

**Candidates.** Selection runs in the order H1, H2, H3, H4.

- **H0:** the median of the training values.
- **H1:** log-log OLS on B8A/B04, fitted on Hermann's training pairs.
- **H2, H3, H4:** A2, A3 and A4 trained on the pilot pairs **without the Missouri's five sites**,
  then the site adjustment log y = a + b·log ŷ fitted on Hermann's training pairs.
  - A3's λ comes from leave-one-river-out over the remaining rivers.
  - A4's grid, seed and determinism are v2's. It is retrained in the lab environment and exported
    as JSON.
  - The adjustment is a ridge on (a, b − 1). λ comes from {0.1, 1, 10} by leave-one-year-out
    within the training years; with fewer than 10 pairs it is the identity.
- **Report-only:** H2–H4 without the site adjustment (trained on other rivers only), scored on the
  lock box.

**Selection and the card.**

- Inside the training years, each candidate is scored by leave-one-hydrological-year-out. The
  lowest MdSA wins; within 5 points, the simpler wins.
- The selected candidate, fitted on the training years only, is the card. **There is no refit,**
  so the lock-box error is the card's own error, and the reach's records from 2023-12 onward are
  out of sample.
- Every candidate's lock-box score is reported. The level comes from the selected one.

**Intervals.** Split conformal in log space, on the selected candidate's inner leave-one-year-out
residuals (Mondrian terciles with deviation 4's pooled fallback). Coverage is checked on the lock
box.

**Levels, per predicted range in FNU** (bins < 30, 30–100, 100–300, 300–1,000, ≥ 1,000; a bin under
8 pairs takes the overall level, capped at _estimated_):

- **validated (site):** lock-box MdSA ≤ 50 %, |SSPB| ≤ 25 %, MdSA ≤ 0.8 × H0's, N ≥ 20 in at
  least 2 hydrological years, and 90 % coverage in [80 %, 97 %].
  - Basis `preregistered_lockbox_site`.
  - Wording: "validated at USGS 06934500 (Missouri River at Hermann) on the held-out period
    2023-12..2026-09, range A–B FNU".
- **estimated (site):** MdSA ≤ 60 %, |SSPB| ≤ 30 %, MdSA below H0's, and the same coverage.
- **indicative:** Spearman ρ with a 95 % lower bound > 0.3 (10,000 acquisition-cluster bootstrap
  draws).

**Prospective check (report-only).** The card's SHA-256 is fixed by its commit. `reach check` pairs
every record of a scene acquired after that commit with the USGS value at the overpass, labelled
with its approval state (usually provisional). It reports MdSA with n and never sets a level.

**The reach.**

- **Baseline:** NDTI and NIR/red computed by the reach itself on its usable scenes from 2019-01-01
  to 2025-12-31 (the D0 rule unchanged). The cap is 6 GB of estimated network.
- **Records:** from 2026-01-01 onward. The estimate station is the gauge's snapped point, in the
  core window.

### B. Magdalena round 3 (exploratory): a known station, validated forward in time

The product always runs at a station with history, so the question here is the error at a known
station on dates it has not seen. Leave-one-station-out measures a new station instead. Round 3
was designed after rounds 1 and 2, so it is exploratory.

**Test units:** v3's 31 units (±3 days with stable flow, nearest scene).

**Outer folds:** the hydrological years (December to November) that hold a unit. In a fold, every
pair of any set whose sample falls in that year leaves training, at every station. IDEAM samples
several stations in one campaign, so holding out a single date would leave that campaign's samples
at neighbouring stations in training.

**Inner selection:** inside the outer training years, the candidates are scored by
leave-one-hydrological-year-out on those years' units. The lowest MdSA wins; within 5 points, the
simplest wins. Simplicity runs: fewer features, then shorter matchups, the nearest scene, a weaker
station effect, all pairs, and the larger λ. The winner is fitted on the outer training years and
predicts the held-out year.

**Candidate space** (a weighted ridge in log space, each sample weighted 1/n as in v3):

- **feature sets:** S5, T, T+G and S5+G, with G only where the pairs have gaps.
  - G is the preregistered flow change: g = ln(Q_sample / Q_scene) on `Q_MEDIA_D`, or the level
    change in metres where only `NV_MEDIA_D` exists (deviation 9).
  - Where the flow is unknown, g is 0 at prediction time (deviation 8); training rows need real
    flow;
- **training pairs:** ±3 days stable, ±7 days, ±15 days;
- **aggregation:** the nearest scene or the median;
- **station effect:**
  - none;
  - one offset per station, ridge-penalised with λₛ ∈ {1, 10}. A station without training pairs
    gets 0 (the pool). The penalty is in the units of the 1/n weights;
- **pair quality (training rows only):** all, or strict (gap ≤ 7 days, ≥ 50 valid pixels, glint
  share ≤ 0.1);
- **feature penalty:** λ ∈ {0.1, 1, 10, 100};
- **+CVC:** each candidate also with the CVC rows of section D added to training, only if its probe
  passes.

**Intervals:** split conformal on the winner's inner residuals, with v2.1's rule.

**Levels:** v2.1's post-hoc criteria, on the outer predictions. The label is "(post hoc, temporal
validation, exploratory)" and the basis is `post_hoc_temporal_magdalena`.

**Reported, never levels:**

- **sensitivities:**
  - one sample out within its station (each unit held out alone, with the same inner selection);
  - forward chaining (each year predicted from earlier years only, for years with at least 3
    earlier years that hold units);
- the form T+G, ±7 days, nearest scene, with station offsets (λₛ = 10, λ by the inner selection),
  labelled as chosen with hindsight;
- Dogliotti 2015 on RAdCor with a common offset and station offsets (λₛ from {none, 1, 10} by the
  inner selection), on the units that have RAdCor at the time of the run;
- San Pablo's own units (3), not rated.

**The product's Magdalena card:**

- Round 1's card is written now, at the level of round 1's result of record (deviation 9). Round
  2's rule already said the product stays at round 1's level, but no card was ever written.
- The reach uses round 3's card (the same selection on every year, then a fit on all of them) only
  when round 3's overall level is at least _indicative_; otherwise round 1's.
- Values appear only at _estimated (post hoc, temporal validation, exploratory)_.

### C. RAdCor Stage B

- **TSS:** due under v2.2's rule (Stage A's 137 % is below v2.1's 165 %), so it is run as v2.2
  states.
- **Turbidity:** the owner's addition. It is exploratory, since Stage A's 80 % did not beat v2.1's
  77 %.
- **Scenes:** the acquisitions of v2's sensitivity-set pairs (±1 day, or ±3 days with stable flow,
  core window) at Magdalena stations that Route B lacks under RAdCor. They are listed after this
  section is committed, without values.
- **Processing:** v2.2's.
  - Level-1C products come through the owner's account, one at a time, each deleted once its
    windows are extracted.
  - ACOLITE `ca477dd` with deviation 1's patch and `settings-radcor.txt`, on a ±0.05° box (±0.08°
    when a station falls near the box edge).
  - The medians are taken over the core window's L2A pixels.
  - The ACOLITE time box is 6 h, and the downloads stop under 20 GB of free disk.
- **Evaluation:** Stage A's candidates (R1 as published, R2 adjusted, R3 log-log on RAdCor's
  B8A/B04, and M0), by nested LOSO on every RAdCor pair of each target, with v2.1's levels. One
  more row (report-only) gives the selected candidate under round 3's outer folds.
- **If a level is reached:** the operational path with ACOLITE is documented. It needs the owner's
  credentials, so it is never unattended.

### D. CVC data (datos.gov.co `d3ft-wu2b`): a probe with a stop rule

- **Metadata only first:** points, coordinates and the number of turbidity samples since
  2018-12-01.
- **Station rule:** each point with ≥ 30 samples goes through the station rule (snap within
  1.5 km to a main channel ≥ 150 m wide, from SCL over 2022–2025).
- **If at least 3 points pass:**
  - their values (NTU) and Sentinel-2 windows within ±15 days are fetched, capped at 5 GB of
    estimated network;
  - they enter round 3 only as training rows, with their own station offsets.
- **Otherwise:** the report says "not suitable", and round 3 runs without them.

### E. Prospective IDEAM samples

The snapshot's last sample is 2025-11-10. Samples in `62gv-3857` at the Magdalena stations dated
later are counted. Those with a usable scene within ±3 days and stable flow are predicted by the
committed product card. This is report-only, with no level under 8 pairs.

### F. What will not be done

- No table of v2, v2.1, v2.2, Landsat or v3 changes, except added rows labelled as such.
- No Magdalena pair trains anything at Hermann.
- No Hermann lock-box pair enters training, selection or the conformal residuals.
- No round 3 outer fold's pairs enter its own selection.
- No unit is shown at a level that was not reached.
- No actor is said to have caused anything.

## v5: gauged rivers where the pipeline can show values (2026-10-12, before computing any of it)

After v4, no reach publishes a value. The Magdalena reached no level in any round, and Hermann reached
34.9 % on its locked test but stayed _indicative_ because its 90 % interval covered 68 of 70 values
(97.1 %, above the 97 % ceiling).

The project owner asked for two demo reaches, anywhere in the world, where turbidity and suspended
solids (or a related variable) can be estimated well enough to publish values. The Magdalena may
leave the demo; its results stay in the report and the repository. v5 evaluates every gauged
river that meets fixed data criteria with Hermann's protocol, reports all of them, and picks the
demo reaches by a rule written here.

### What was seen before this section

- Every v4 result (the report, D17).
- **USGS metadata probes on 2026-10-12** (no value):
  - the time-series metadata of continuous turbidity (63680), continuous and daily suspended
    sediment (80154) and the USGS surrogate SSC (99409);
  - the names, coordinates and drainage areas of the 399 sites active since 2018 or earlier;
  - the main-channel rule at 9 new sites;
  - the number of discrete SSC samples since 2018-12 at 9 sites.
- **Rijkswaterstaat:** at Lobith the turbidity is hourly but "unchecked" from 2018 on, its unit
  changed from NTU to FTU in 2018, and the API serves nothing in 2026.

No value, pair or error of any new site has been read.

### Selection

**Hard criteria:**

1. a continuous turbidity series (63680) that began in 2017 or earlier and is still active in 2025;
2. a main channel ≥ 300 m wide under the station rule (SCL water frequency, 2022–2025);
3. not at a dam or a lock.

**The candidates:**

| Site                                          | River group | Width (m) | In the pilot | SSC target                   |
| --------------------------------------------- | ----------- | --------- | ------------ | ---------------------------- |
| 07020850 Mississippi at Cape Girardeau, MO    | MISSISSIPPI | 560       | no           | —                            |
| 07374525 Mississippi at Belle Chasse, LA      | MISSISSIPPI | 772       | yes          | discrete 80154 (176 samples) |
| 07381600 Lower Atchafalaya at Morgan City, LA | ATCHAFALAYA | 506       | no           | discrete 80154 (167)         |
| 06805500 Platte at Louisville, NE             | PLATTE      | 305       | yes          | discrete 80154 (148)         |
| 03216070 Ohio at Ironton, OH                  | OHIO        | 433       | yes          | —                            |
| 14246900 Columbia at Port Westward, OR        | COLUMBIA    | 632       | no           | 99409 (continuous)           |
| 14144700 Columbia at Vancouver, WA            | COLUMBIA    | 680       | no           | 99409 (continuous)           |
| 11337190 San Joaquin at Jersey Point, CA      | SAN JOAQUIN | 534       | no           | 99409 (continuous)           |
| 14211720 Willamette at Portland, OR           | WILLAMETTE  | 342       | no           | 99409 (continuous)           |
| 01193050 Connecticut at Middle Haddam, CT     | CONNECTICUT | 358       | no           | —                            |

- **Hermann** (v4) also gets its SSC evaluated (discrete 80154, 118 samples). Its turbidity keeps
  its v4 level of record.
- **Left out:**
  - Missouri at Randolph (291 m);
  - Sacramento at Freeport (200 m);
  - Baton Rouge (approved values end in 2023);
  - the pilot's sites at a dam or lock, or with series starting after 2017 or ending before 2025.
- **Every candidate is evaluated and reported.** A site whose lock box holds fewer than 20 approved
  pairs is reported as `insufficient_data`.

### Data

**Scenes:** every Earth Search L2A acquisition 2018-12-01..2026-09-30 with item cloud ≤ 70 %,
measured as in the pilot (300 m and core windows).

**Turbidity:** the pilot's rule (approved 15-minute values, median within ±30 min, else the nearest
within ±60 min, qualifiers excluded).

**Suspended solids, two kinds, never pooled:**

- **Discrete SSC (80154):** samples on the scene's local day (the pilot's TSS rule), at the sites
  with at least 100 samples since 2018-12.
- **Surrogate SSC (99409):** the USGS's continuous SSC record, estimated from turbidity by its own
  surrogate regression, taken at the overpass with the turbidity rule.
  - Wherever it appears it is labelled "SSC estimated by the USGS from turbidity (surrogate
    record)".
  - It is not an independent measurement of solids.

**Caps:** 30 GB of estimated network for the whole v5 fetch, and the fetch stops under 20 GB of
free disk.

### Protocol (Hermann's, v4 A, unchanged unless stated)

Per site and target:

- **Training:** hydrological years 2019–2023 (2018-12-01..2023-11-30).
- **Lock box:** 2023-12-01..2026-09-30, evaluated once.
- **Window:** the core window.
- **Candidates:** H0–H4.
  - H2–H4 are pretrained on the pilot **without the site's river group**. Cape Girardeau and Belle
    Chasse leave out MISSISSIPPI, Louisville PLATTE and Ironton OHIO; the other rivers are not in
    the pilot.
  - For SSC, the pretrained models are the pilot's TSS models (A2–A4, discrete SSC pairs), without
    the site's river group.
  - A4 is retrained in the lab environment with v2's grid and seed for each group it leaves out.
- **Selection:** leave-one-year-out in the training years, with the 5-point margin.
- **The card:** the winner fitted on the training years, with no refit.
- **Intervals:** conformal on the inner residuals, as v4.
- **Units:** turbidity in FNU, SSC in mg/L.

### Levels (every v5 evaluation)

The thresholds stay, except the coverage rule:

- **validated:** lock-box MdSA ≤ 50 %, |SSPB| ≤ 25 %, MdSA ≤ 0.8 × H0's, N ≥ 20 in ≥ 2
  hydrological years, 90 % coverage ≥ 80 %, and a median 90 % interval factor ≤ 2.5 (the interval
  spans the value ×/÷ 2.5 or less).
- **estimated:** MdSA ≤ 60 %, |SSPB| ≤ 30 %, MdSA below H0's, 90 % coverage ≥ 80 %, and a median
  90 % interval factor ≤ 3.0.
- **indicative:** Spearman ρ with a 95 % lower bound > 0.3.
- Per predicted range, as v4: a range under 8 pairs takes the overall level, capped at _estimated_.

**Why the coverage rule changes, and its limits:**

- v4 failed intervals that covered too much (above 97 %). A conservative interval does not
  mislead about the uncertainty; its cost is width. So v5 keeps the lower bound (80 %, validity)
  and replaces the upper bound with a cap on the width (sharpness).
- The change was decided after seeing Hermann's 97.1 %, so it is labelled that way.
- It applies only to evaluations not yet computed. Hermann's turbidity keeps its v4 level of record.
  A report-only row gives Hermann under the v5 rule, labelled "rule written after seeing it".

### The demo reaches (rule fixed here)

- The two demo reaches are the two gauged reaches with the highest turbidity level of record,
  among Hermann (v4) and the v5 sites. Ties go to the lower lock-box MdSA, then to the larger lock
  box.
- Each demo reach gets a site file and a self-measured NDTI baseline (2019-01-01..2025-12-31, 6 GB
  cap each), records from 2026-01-01, and the prospective check against its gauge after its card's
  commit.
- **The report gives every site's result,** the number of sites evaluated and their median
  lock-box MdSA. The two demo reaches are the best of N, so their pair of errors is an optimistic
  summary of the method. The table of all N is the honest one.
- The Magdalena leaves the demo (the owner's choice). Its reach stays in the repository and keeps
  its results.

## v6: more variables at the demo reaches (2026-10-12, before computing any of it)

The project owner asked to include as many variables as the satellite can predict with a
relatively low error. v6 adds the variables that are both observable from orbit and measured by
the demo gauges, so each can be validated under the same rules as turbidity.

### What was seen before this section

- Every v5 result. Discrete SSC was `insufficient_data` at both demo sites: the lock box held 6
  (Belle Chasse) and 4 (the Platte) samples on a clear pass's local day.
- **USGS time-series metadata on 2026-10-12** (no value):
  - Belle Chasse (07374525): discharge (00060), gage height (00065), turbidity (63680) and mean
    velocity;
  - the Platte at Louisville (06805500): water temperature (00010), discharge, gage height,
    specific conductance (00095), dissolved oxygen (00300), nitrate plus nitrite (00630) and
    turbidity.
- The number of discrete SSC samples (80154): 176 at Belle Chasse, 148 at the Platte.

No pair of SSC with the gauge's turbidity, no gauge temperature and no Landsat thermal value has
been read at either site.

### The variables, and why only these

| Variable                        | Reaches               | How                                         | Validated against            |
| ------------------------------- | --------------------- | ------------------------------------------- | ---------------------------- |
| Suspended-sediment conc. (mg/L) | both                  | the turbidity card, then the gauge's rating | discrete SSC samples (80154) |
| Suspended-sediment flux (t/day) | both                  | SSC × the gauge's discharge                 | follows SSC                  |
| Water temperature (°C)          | the Platte            | Landsat 8/9 surface temperature (thermal)   | the gauge's 00010            |
| Gauge context (no estimate)     | both (more at Platte) | the gauge's own readings at the overpass    | — (measurements)             |

- **Not estimated from the satellite:** dissolved oxygen, nitrate, specific conductance and pH are
  not optically active; chlorophyll is measured by neither gauge, and suspended sediment confounds
  its red-edge retrievals. Their gauge readings may appear as context, always labelled "measured
  by the USGS gauge", never as an estimate.
- **No temperature at Belle Chasse:** its gauge does not measure it.

### A. Suspended-sediment concentration: a chain of two links

- **Link 1:** the turbidity card of record (v5), unchanged.
- **Link 2: the gauge's rating, turbidity → SSC.**
  - **Pairs:** every discrete SSC sample (80154, accepted or approved) with the gauge's continuous
    turbidity (63680, approved) at the sample's time, by the overpass rule (median within ±30 min,
    else the nearest within ±60 min, qualifiers excluded).
  - **Candidates:** R1, OLS of ln SSC on ln turbidity with Duan's smearing factor (the USGS
    surrogate method); R2, R1 plus ln discharge at the sample's time (same rule).
  - **Selection:** leave-one-hydrological-year-out MdSA within the training samples (before
    2023-12-01), with the 5-point margin; R1 is the simpler.
  - **Locked test:** the samples of 2023-12-01..2026-09-30, scored once with the rating fitted on
    the training samples.
- **The chain:** SSC = rating(turbidity estimate). Its 90 % interval comes from the sum of the two
  links' log errors, taken as independent: every pair of link 1's inner residuals (its card's) and
  link 2's leave-one-year-out residuals.
- **End-to-end check (report-only):** the lock-box samples on a clear pass's local day (6 and 4)
  against the chained estimate.
- **Level (`chained_rating`), never validated** (no end-to-end lock box of 20 pairs exists):
  - **estimated** when link 1 is _validated_ or _estimated_ and link 2's locked test has N ≥ 20 in
    ≥ 2 hydrological years, MdSA ≤ 30 %, |SSPB| ≤ 15 %, MdSA ≤ 0.8 × its null (the training
    median SSC), and the chain's median 90 % interval factor is ≤ 3.0;
  - **indicative** when link 2's Spearman ρ has a 95 % lower bound > 0.3;
  - otherwise **none**.

### B. Suspended-sediment flux

- **Discharge:** the gauge's 00060 at the overpass by the same rule, approved else provisional
  (labelled), ft³/s converted to m³/s.
- **Flux (t/day)** = SSC (mg/L) × discharge (m³/s) × 0.0864. Its interval is SSC's times the
  discharge. The discharge record's own uncertainty is stated, not propagated.
- **Level:** SSC's. The flux is written beside the records (the record holds SSC; the discharge is
  the gauge's measurement).

### C. Water temperature at the Platte (Landsat 8/9 thermal)

- **Scenes:** Landsat 8/9 Collection 2 Level-2, Tier 1 (Planetary Computer),
  2018-12-01..2026-09-30, scene cloud ≤ 70 %.
- **Value:** the median surface temperature (ST_B10 × 0.00341802 + 149.0 K) of the core window's
  pixels that QA_PIXEL marks clear and water (no fill, dilated cloud, cirrus, cloud, cloud shadow or
  snow), with at least 10 such 30 m pixels.
- **Pairs:** the gauge's water temperature (00010, approved) at the overpass, by the overpass rule.
- **Candidates:** W0, the gauge's day-of-year climatology in the training years (the null); W1, the
  product as it is (ST − 273.15); W2, a + b · ST fitted on the training pairs.
- **Selection:** leave-one-hydrological-year-out MAE in the training years (2018-12-01..2023-11-30);
  within 0.3 °C the simpler wins (W1, then W2).
- **Locked test:** 2023-12-01..2026-09-30, scored once, with no refit.
- **Metrics:** MAE, mean bias and RMSE in °C, Spearman ρ. MdSA is not used (temperatures near 0 °C).
- **Intervals:** split conformal on the absolute inner residuals (°C), 90 %.
- **Levels (`preregistered_lockbox_site`):**
  - **validated:** MAE ≤ 1.5 °C, |bias| ≤ 0.75 °C, MAE ≤ 0.8 × W0's, N ≥ 20 in ≥ 2 hydrological
    years, 90 % coverage ≥ 80 %, and a median 90 % half-width ≤ 3 °C;
  - **estimated:** MAE ≤ 2.5 °C, |bias| ≤ 1.5 °C, MAE below W0's, 90 % coverage ≥ 80 %, and a
    median 90 % half-width ≤ 4.5 °C;
  - **indicative:** Spearman ρ with a 95 % lower bound > 0.3.
- **Records:** Landsat passes are not Sentinel-2 passes, so temperature gets its own sealed records
  and ledger per reach, with the same seal and chain rules.

### D. Gauge context (no estimate)

At each recorded pass: the gauge's discharge and gage height (both reaches), and at the Platte its
water temperature, dissolved oxygen, specific conductance and nitrate plus nitrite, by the overpass
rule with the approval labelled. Written beside the records (`context.csv`), never in them.

### E. Attempts, budgets and what will not be done

- **Attempts:** 2 rating candidates per site (R1, R2); 3 temperature candidates (W0–W2), one site.
  Each locked test is scored once.
- **Budgets:** ≤ 6 GB of estimated network for v6; the fetch stops under 20 GB of free disk.
- **Not done:** no change to the turbidity cards; no satellite estimate of dissolved oxygen,
  nitrate, conductance, pH or chlorophyll; no temperature at Belle Chasse; no variable that misses
  every level is shown with a unit.

## v7: discharge at the Platte from its water surface (2026-10-13, before computing any of it)

After v6 the product shows two variables: turbidity at both demo reaches and water temperature at
the Platte. The project owner asked whether a third can be added. Of the candidates checked (below),
only one is both visible from orbit and measured by a demo gauge: the discharge of a braided river,
whose wetted area grows as the flow covers its sand bars.

**Basis:**

- at-a-station hydraulic geometry: width grows as a power of discharge (Leopold & Maddock 1953,
  USGS Professional Paper 252);
- discharge from satellite water extent on braided rivers (Smith et al. 1996, _Water Resources
  Research_ 32(7); Smith & Pavelsky 2008, _Water Resources Research_ 44);
- MNDWI for open water, including turbid water (Xu 2006, _International Journal of Remote
  Sensing_ 27(14)).

### What was seen before this section

- Every v6 result.
- **v6's rating R2 at the Platte** used ln discharge at each SSC sample's time
  (`inputs/v6/gauge-readings.csv`, 2018-12..2026-09). Only its aggregate scores were read.
- **The gauge's discharge at the 16 recorded 2026 passes** (`checks/context.csv`), shown in the web
  on 2026-10-12 and 2026-10-13.
- **USGS time-series metadata on 2026-10-13** (no value):
  - the Platte at Louisville (06805500) has continuous discharge (00060) since 1988 and daily
    values since 1953;
  - no demo gauge, nor Hermann, measures chlorophyll; Hermann alone has fDOM (32295).
- **The frozen geometry** (river mask, corridor) and, per 2026 pass, the corridor's area and its
  usable share in the web. Both are fixed areas, not water extent.
- **The screening's per-scene SCL water counts** inside the sub-reaches (the scene classification).
  They were not written for the Platte and were never compared with discharge.

No water extent of any scene has been compared with any discharge value.

### The candidates checked, and why only this one

| Candidate                              | Outcome                                                         |
| -------------------------------------- | --------------------------------------------------------------- |
| Discharge at the Platte (water area)   | **Evaluated here**                                              |
| Discharge at Belle Chasse              | Not done: the river runs between levees; its width barely moves |
| Chlorophyll                            | Not done: no gauge measures it, so it cannot be validated       |
| Dissolved oxygen, nitrate, conductance | Not done: not optically active                                  |
| fDOM                                   | Not done: Hermann only; sediment masks its signal               |

### Area of interest (fixed here)

- **The active channel:** the pixels of the frozen corridor (between the anchors, the 20 m site
  grid) whose SCL water frequency in the geometry period (2022–2025) is at least 0.05, kept only
  where they connect (8-connectivity) to the frozen river mask.
- This keeps the sand bars the river covers at high flow, and drops the sand-pit lakes that line the
  valley but do not connect to the channel.
- The water frequency used is SCL classes only. It holds no discharge, so the area of interest
  carries no information on the target.

### Data

- **Scenes:** every Earth Search L2A acquisition 2018-12-01..2026-10-10 with item cloud ≤ 70 %.
- **Clear rule:** at least 95 % of the area of interest's pixels have data and are not in the
  invalid SCL classes (1, 3, 8, 9, 10, 11: saturated, cloud shadow, cloud, cirrus, snow). A scene
  that fails is skipped, never filled in.
- **SCL first:** SCL is read first; B03 and B11 are read only for the scenes that pass.
- **Water, two ways (each on the 20 m grid, over the clear pixels):**
  - SCL class 6;
  - MNDWI = (B03 − B11) / (B03 + B11) > 0, with B03 averaged to 20 m. The threshold is fixed at 0
    and is not tuned.
- **Feature:** the water fraction f = water pixels / clear pixels of the area of interest.
- **Pairs:** the gauge's discharge (00060) at the overpass, by the overpass rule (median of the
  15-minute values within ±30 min, else the nearest within ±60 min). Any value carrying a qualifier
  (ice-affected, estimated, equipment) is excluded. Training and the locked test use approved
  values only; ft³/s are converted to m³/s.

### Candidates

| Id                | Model                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Q0** (the null) | The gauge's day-of-year climatology: the median daily discharge (00060, statistic 00003) of the training years within ±15 days |
| **Q1**            | ln Q = a + b · ln f, with f from SCL water; OLS with Duan's smearing factor                                                    |
| **Q2**            | The same power law, with f from MNDWI                                                                                          |

- **Simplest first:** Q1, then Q2 (SCL needs no extra band).
- **Abstention:** when f lies outside the range of the training pairs' f, the estimate abstains
  ("outside the fitted range"). There is no extrapolation.

### Selection, locked test and the card

- **Training:** hydrological years 2019–2023 (2018-12-01..2023-11-30).
- **Selection:** leave-one-hydrological-year-out MdSA in the training years. Within 5 points the
  simpler wins.
- **Locked test:** hydrological years 2024–2025 (2023-12-01..2025-11-30), scored once.
- **The card:** the winner fitted on the training years, with no refit.
- **Prospective check (report-only):** 2025-12-01 onwards, against approved or provisional values,
  labelled. It holds the 2026 passes whose discharge was already seen, so it never enters a level.
- **Metrics:** MdSA, SSPB and Spearman ρ (95 % lower bound by a block bootstrap over hydrological
  years), as for turbidity.
- **Intervals:** split conformal on the inner leave-one-year-out log residuals, 90 %: the estimate
  ×/÷ exp(q₉₀ of |log residual|).
- **Report-only:** the locked test's error by tercile of the gauge's discharge, and the share of
  scenes the clear rule skipped by the same terciles (cloud-flagged turbid water can bias which
  flows are seen).

### Levels (`preregistered_lockbox_site`, one overall level)

The thresholds are stricter than turbidity's: the gauge itself measures discharge within about 10 %,
so an estimate has to be well inside the river's natural spread to be worth showing.

- **validated:** MdSA ≤ 30 %, |SSPB| ≤ 15 %, MdSA ≤ 0.8 × Q0's, N ≥ 20 in ≥ 2 hydrological years,
  90 % coverage ≥ 80 %, and a median 90 % interval factor ≤ 2.0;
- **estimated:** MdSA ≤ 45 %, |SSPB| ≤ 25 %, MdSA below Q0's, 90 % coverage ≥ 80 %, and a median
  90 % interval factor ≤ 2.5;
- **indicative:** Spearman ρ with a 95 % lower bound > 0.3;
- otherwise **none**.

### Records and the web (only at _estimated_ or better)

- **Records:** each 2026 Sentinel-2 pass that passes the clear rule gets a sealed discharge record.
  It has its own ledger and the same seal and chain rules as the water-temperature records. It holds
  the water fraction, the estimate in m³/s with its interval, and the card's hash.
- **The web:** a discharge tab beside the gauge's own discharge at each pass.
- **Below _estimated_:** the result is reported and nothing is shown. The water area is not shown on
  its own either.

### Attempts, budgets and what will not be done

- **Attempts:** 2 candidates (Q1, Q2) and the null, one site. The locked test is scored once.
- **Budgets:**
  - ≤ 6 GB of estimated network (SCL for every scene; B03 and B11 only for those that pass);
  - the fetch stops under 20 GB of free disk;
  - one day of computing.
- **Not done:**
  - no discharge from the gauge's own stage (that is the gauge's rating, not the satellite);
  - no other threshold, area of interest or water index after results are seen;
  - no discharge at Belle Chasse;
  - no change to the turbidity or water-temperature cards.

## v7.1: conductance and dissolved oxygen at the Platte, temperature at Belle Chasse (2026-10-14, before computing any of it)

After v7 was committed, the project owner asked for more water-quality variables. v7.1 adds three.
Each is validated against a USGS gauge, and each is shown only if it reaches _estimated_. v7's
discharge section stays as committed. Nothing of v7 or v7.1 has been computed.

**What changed since v7's table.** v7 left conductance and dissolved oxygen out because they are not
optically active. v7.1 does not claim the satellite sees them. Each comes through a physical link
from something it does see:

- **specific conductance** from the water surface (high flows dilute dissolved salts);
- **dissolved oxygen** from the water temperature (oxygen solubility).

The locked tests decide whether those links are strong enough at this river.

### What was seen before this section

Everything listed in v7, plus:

- **The Platte gauge's other readings at the 16 recorded 2026 Sentinel-2 passes**
  (`checks/context.csv`): water temperature, dissolved oxygen, specific conductance and nitrate.
  They were shown in the web on 2026-10-12..14. Two of those passes (07-17 and 10-05) fall on a
  Landsat day.
- **The Platte's water temperature at its 2026 Landsat passes** (v6's prospective check).
- **USGS metadata on 2026-10-14** (no value read):
  - the gauges in the lower Mississippi box (−91.3..−89.2 E, 29.2..30.6 N) that publish
    temperature, dissolved oxygen or conductance, and their names. The only main-stem gauge with
    temperature is Baton Rouge (07374000); the others are bays, canals and marsh stations.
  - the approval status alone, on four days, of Baton Rouge's temperature (provisional from 2024)
    and of the Platte's dissolved oxygen and conductance (approved through 2025-10).
- **Baton Rouge's pilot data** (sites, windows, turbidity pairs; v2). No temperature value was read
  there.

No Landsat temperature at Baton Rouge or Belle Chasse, and no saturation value, has been compared
with any gauge value.

### Common rules (v7's)

These are v7's rules, unchanged:

- training: hydrological years 2019–2023;
- selection: leave-one-hydrological-year-out within training;
- the locked test: hydrological years 2024–2025, scored once, with no refit;
- the prospective check: report-only, from 2025-12-01, with provisional values labelled;
- the overpass rule, with qualified values excluded;
- the null: the gauge's day-of-year climatology from daily values;
- abstention outside the training range;
- split-conformal 90 % intervals;
- Spearman ρ, with a block-bootstrap lower bound.

Pairs use approved values only, except at Baton Rouge (see C).

### A. Specific conductance at the Platte (µS/cm)

- **Feature:** v7's water fraction f of the active channel, from the water detection v7 selects for
  discharge. There is no second choice.
- **Candidates:**
  - **C0**, the null;
  - **C1**, ln SC = a + b · ln f, fitted by OLS with Duan's smearing factor;
  - **C2**, C1 plus an annual harmonic (sin and cos of 2π · day-of-year / 365.25).
- **Selection:** C1 is the simpler, with a margin of 3 points of MdSA.
- **Metrics:** MdSA, SSPB and Spearman ρ against the gauge's 00095.
- **Levels** (strict, because conductance moves within a narrow range):
  - **validated:** MdSA ≤ 15 %, |SSPB| ≤ 10 %, MdSA ≤ 0.8 × C0's, N ≥ 20 in ≥ 2 hydrological
    years, 90 % coverage ≥ 80 %, and a median 90 % interval factor ≤ 1.5;
  - **estimated:** MdSA ≤ 25 %, |SSPB| ≤ 15 %, MdSA below C0's, 90 % coverage ≥ 80 %, and a median
    factor ≤ 2.0.

### B. Dissolved oxygen at the Platte (mg/L)

- **Input:** the water temperature T from v6's committed card (W1, the Landsat surface temperature
  as it is) at each Landsat pass that meets v6's window rule.
- **Saturation:** C\*(T, P), from the Benson & Krause (1984) equations for fresh water, as
  tabulated by the USGS in DOTABLES. P is fixed: the standard-atmosphere pressure at the gauge's
  datum elevation, taken from the USGS monitoring-location metadata.
- **Candidates:**
  - **O0**, the null;
  - **O1**, DO = C\*(T, P): 100 % saturation, with no fitted parameter;
  - **O2**, DO = a + b · C\*(T, P), fitted on the training pairs.
- **Selection:** O1 is the simpler, with a margin of 0.3 mg/L of MAE.
- **Metrics:** MAE, mean bias and RMSE in mg/L, and Spearman ρ, against the gauge's 00300.
- **Intervals:** ± a half-width from the absolute residuals.
- **Levels:**
  - **validated:** MAE ≤ 0.75 mg/L, |bias| ≤ 0.4 mg/L, MAE ≤ 0.8 × O0's, N ≥ 20 in ≥ 2
    hydrological years, 90 % coverage ≥ 80 %, and a median 90 % half-width ≤ 1.5 mg/L;
  - **estimated:** MAE ≤ 1.2 mg/L, |bias| ≤ 0.75 mg/L, MAE below O0's, 90 % coverage ≥ 80 %, and a
    median 90 % half-width ≤ 2.5 mg/L.
- **What it cannot see:** C\* is the oxygen that water at that temperature holds at equilibrium.
  Blooms raise oxygen above it, and decomposition lowers it below. Neither shows from orbit.

### C. Water temperature at Belle Chasse, validated at Baton Rouge (°C)

- **Why Baton Rouge:** the Belle Chasse gauge does not measure temperature. The only main-stem gauge
  on the lower Mississippi that does is Baton Rouge (07374000), about 245 km upstream. Its channel
  is 640 m wide (in the pilot).
- **Validation at Baton Rouge, by v6's method:**
  - Landsat 8/9 Collection 2 Level-2: the median surface temperature of the clear water pixels
    (QA_PIXEL) in Baton Rouge's pilot core window, with at least 10 pixels;
  - candidates W0 (the null), W1 (ST − 273.15) and W2 (a + b · ST);
  - within 0.3 °C of MAE, the simpler wins (W1, then W2);
  - v6's metrics and thresholds.
- **Provisional values:** Baton Rouge's temperature has been provisional since 2024. Its pairs use
  approved values where they exist, else provisional values, each labelled. Because the locked test
  rests on provisional values, the level is capped at _estimated_.
- **At Belle Chasse:**
  - the card is applied to the median surface temperature of Belle Chasse's core window (the
    turbidity station's window, with the same pixel rules);
  - it takes Baton Rouge's level, capped at _estimated_, and every value is labelled "validated at
    Baton Rouge, about 245 km upstream, against provisional values";
  - **report-only:** Belle Chasse's estimate is compared with Baton Rouge's gauge on the same pass
    day, to show how far the two places differ. That comparison never enters a level.

### Records and the web (only at _estimated_ or better)

- **Conductance:** shares v7's discharge record for each clear 2026 Sentinel-2 pass, as a second
  estimate with its own card hash.
- **Dissolved oxygen:** a sealed record per 2026 Landsat pass at the Platte, with its own ledger. It
  names the SHA-256 of the water-temperature record it was computed from.
- **Water temperature at Belle Chasse:** v6's water-temperature records, with the label above.
- **The web:** each variable appears beside the gauge's own reading at the pass, with its level, its
  locked-test error and its null's error.
- **A variable below _estimated_** is reported and not shown.

### Attempts, budgets and what will not be done

- **Attempts:**
  - 2 candidates and a null for A, and the same for B;
  - 3 candidates (W0–W2) for C.
  - Each locked test is scored once.
- **Budgets:**
  - A and B read no new image beyond v7's;
  - C reads ≤ 2 GB of estimated network (the Landsat windows at Baton Rouge and Belle Chasse);
  - the fetches stop under 20 GB of free disk;
  - computing is time-boxed to two days, together with v7.
- **Not done:**
  - nitrate (no physical link to anything the satellite sees);
  - pH and chlorophyll;
  - discharge at Belle Chasse;
  - no other validation gauge, threshold or link after results are seen;
  - no change to any v5, v6 or v7 rule.

## Deviation protocol

- A technical failure (network, timeout) is rerun, unchanged.
- A bug found after results were seen is fixed. Both results are reported, and the change is listed
  under Deviations.
- A stage that overruns its time box or budget is `incomplete`.

## Deviations

1. **2026-10-10, before any RAdCor value was seen: two technical fixes to run RAdCor.**
   - **What was preregistered:** ACOLITE at commit `ca477dd`, unchanged, with RAdCor's
     top-of-atmosphere output off.
   - **What the first scene showed:** two failures, no reflectance.
     - RAdCor stopped with "operands could not be broadcast together with shapes (555,554)
       (555,555)". With edges extended, `acolite/adjacency/radcor/tools/deconv.py` takes the
       column range from the row count, so it fails on any box that is not square. ACOLITE's
       current version has the same line (checked on 2026-10-10).
     - Then the Level-2W step stopped. ACOLITE's water mask reads the top-of-atmosphere reflectance
       from the Level-2R file, and it had not been written.
   - **The changes:**
     - The column range uses the column count. That is a one-line patch,
       `pipeline/acolite/patches/radcor-deconv-columns.patch`, applied to the pinned commit; the
       v2 manifests record its SHA-256.
     - `radcor_write_rhot` returns to ACOLITE's default (written).
   - **What does not change:** every other setting, the DSF runs (the patched function is only
     used by RAdCor), any rule.
   - **What was seen:** the two error messages, and a Level-2R file whose values were not read.
2. **2026-10-10, before any value was fetched: how the core window is computed.**
   - **What was preregistered:** pixels of the primary window whose distance to land is ≥ 60 m.
   - **The implementation:** the main channel eroded by 3 pixels (60 m) with D15's 4-neighbour
     erosion, the same operation that makes D15's 2-pixel window. It keeps the pixels whose
     city-block distance to land exceeds 3 pixels. Diagonally, that is somewhat less than 60 m in
     a straight line.
   - **Why:** it reuses D15's tested operation and needs no new dependency.
   - **What was seen:** no value.
3. **2026-10-10, during the station selection, before any value: accented stream names.**
   - **What was preregistered:** a stream matches exactly after accents, case and surrounding
     spaces are removed.
   - **What the first selection showed:** SINU and NECHI had no candidate, although the data hold
     points on them. D15's query (`upper(corriente) like '%SINU%'`) never matches the stored
     spellings `SINÚ`, `NECHÍ` and `PATÍA`. D15 was not affected: MAGDALENA has no accent.
   - **The fix:** the stream spellings in the data are listed first (`stream-spellings.json`), and
     each stream is queried on every spelling that matches it after the normalization. That is the
     preregistered rule. CAQUETA has no sample since 2015-07.
   - **What was seen:** metadata only (stream names and sample counts). The selection was stopped
     and run again; the snap and width reads are cached, so no outcome could change.
4. **2026-10-11, before any USGS value was fetched: a pooled interval where a tercile is too
   small.**
   - **What was preregistered:** Mondrian split conformal. Per tercile of ŷ, q is the
     ⌈(n + 1)(1 − α)⌉-th smallest residual.
   - **What Phase 1 showed:** there are 14 Colombian training pairs per target, so a tercile holds
     4–5 LORO residuals. At 90 %, the rank exceeds n in any tercile with fewer than 9 residuals.
     Then q is infinite, the interval covers everything and the coverage is 100 %. No target could
     meet the 90 % coverage rule of the validated and estimated levels ([80 %, 97 %]), whatever its
     error.
   - **The change:** at each coverage, the Mondrian quantiles are used only when every tercile has
     enough residuals for a finite one (≥ 9 at 90 %, ≥ 4 at 80 %).
     - Otherwise that coverage uses one quantile over all the calibration residuals, the same in
       every tercile. With fewer than 9 residuals in all, it stays infinite.
     - The intervals table and the model cards name the pooled coverages.
   - **What does not change:** the calibration residuals (the Colombian LORO residuals of the
     selected model), the coverage check on the Magdalena and every level rule.
   - **What was seen:**
     - Route A's Phase 1 results for A1 (`15e5d8d`). With the change, A1's 90 % coverage on the
       Magdalena test moves from 100 % to 95–97 % in five of its six rows. It stays at 100 % for
       turbidity on the primary pairs, where the pooled factor is ×16.
     - No level changes: A1's test MdSA (92–208 %) fails every level.
     - No USGS value and no A2–A4 result had been computed.
5. **2026-10-11, during the USGS value fetch, before any value was examined: the network meter
   undercounts.**
   - **What was preregistered:** ≤ 60 GB of network for the USGS sites. The meter is an estimate:
     0.2 MB per SCL read and 8.5 MB per acquisition whose bands are read, one COG block per band.
   - **What a measurement showed:** GDAL's range requests on 18 acquisitions at three sites summed
     to 79 MB against an estimate of 55 MB (1.4×). An acquisition on one tile reads about 10 MB; a
     site in the overlap of two MGRS tiles reads each tile, about 19 MB. SCL-only reads are smaller
     than estimated.
   - **The decision (the project owner's):** the fetch goes on to the preregistered 200 clear
     scenes per site, with the meter unchanged. Its estimate of about 46 GB means about 65 GB of
     real traffic. The disk budget is unaffected.
   - **What was seen:** the clear-scene counts and estimated volumes of the first sites in the run
     log. No turbidity, SSC or pair had been read or examined.
6. **2026-10-11, before any reach record: the reach's NIR/red baseline cap.**
   - **What was preregistered:** ≤ 2 GB for the reach's NIR/red baseline.
   - **What the first run showed:** the estimate (34 MB per scene) reached 2 GB after 60 of the 112
     frozen scenes. It measures in date order, so the 60 cover 2018-12 to about 2021 only. A
     measurement gave about 28 MB per scene in reality.
   - **The decision (the project owner's):** the cap rises to 4 GB estimated (about 3.1 GB real) so
     the baseline holds all 112 scenes. A rerun keeps the 60 scenes already measured.
   - **What was seen:** NIR/red per sub-reach of the 60 scenes (not examined), and the NDTI
     reproduction check: the largest difference from the frozen NDTI is 0.00005, which is rounding.
7. **2026-10-11, during the Landsat fetch, before any Landsat value was examined: one corrupt
   item.**
   - **What was preregistered:** a read error other than a non-public bucket requires a rerun
     before results count.
   - **What the rerun showed:** the red and NIR assets of `LC08_L2SP_009054_20220506_02_T1` fail
     on every read, in both runs and when read directly. Its other bands read fine, so the source
     file is damaged; the network is not at fault.
   - **The change:** that acquisition counts as no data, like an asset in a non-public bucket. Its
     window has no water pixel with red and NIR, so it makes no pair either way.
   - **What was seen:** the read errors and the item's band list. No Landsat value was examined.
8. **2026-10-11, after v3 round 1's first run: candidates compared on different units.**
   - **What the first run showed:** a candidate with the flow index (Q) or the flow change (G)
     could not predict a unit whose station or day lacks flow data, and the unit was dropped.
     - Inside each fold, candidates were then scored on different subsets of units. The selection
       favoured those that skipped the hard cases.
     - The run scored 23 of the 31 test units at 9 of 11 stations: nested MdSA 81.7 %.
   - **The fix:** where the flow is unknown, its standardised index is taken as 0 (the station's
     typical flow, no change) at prediction time. Every candidate then predicts every unit. The
     training rows still need real flow.
   - **What does not change:** the candidate space, the pair sets, the test units and the
     selection rule.
   - **Reported:** both runs. The fixed run is round 1's result. It was designed after the first
     run's number was seen, so it carries that caveat.
9. **2026-10-12, found in a code review after v3's results were seen: the flow features of v3.**
   - **What was preregistered** (v3, round 1): Q is log Q_sample (or the level), and G is
     g = ln(Q_sample / Q_scene) (Q_MEDIA_D, or the level in metres where only NV_MEDIA_D exists).
   - **What the code did** (`quality/search.py`, `flow_index`):
     - it standardised each station's log discharge (or level in metres) by the station's own
       median and 1.4826 × MAD;
     - it used that index as Q, and the index's change z_sample − z_scene as G.

     G was therefore the preregistered g divided by a scale that differs between stations. This
     choice was made in the code before any v3 result existed, but it was not written in the
     preregistration.

   - **The fix** (the deviation protocol for a bug found after results were seen):
     - rounds 1 and 2 are computed again with Q and G as preregistered;
     - those runs become the rounds' results of record;
     - the standardised runs stay in the tables, labelled "standardised flow (first computed)".
   - **Round 3 (v4)** uses the preregistered g.
   - **What was seen:** every v3 result (round 1: 71.5 %, indicative; round 2's four checks). No
     result with the preregistered features had been computed.
10. **2026-10-12, found when CI failed after the v2 merge: a card hashed a CRLF working copy.**
    - **What happened:**
      - The v2.1 turbidity card (`models/turbidity.posthoc.json`, candidate P4) records the SHA-256
        of `inputs/lab/gbm-turbidity-core.json`.
      - It was written from a Windows working copy that held the file with CRLF line endings. The
        repository holds it with LF, so every checkout recomputes another hash, and `quality verify`
        fails on that card. CI has failed since the merge of v2.
    - **The fix:** the card hashes a model file with LF line endings, whatever the checkout wrote.
      The card is written again.
    - **What does not change:**
      - every estimate, coefficient, interval and level;
      - the trees, which are the same JSON with either line ending.

      Only the card's `sha256` and `parametersHash` change.

    - **What was seen:** the CI log, the two hashes and that the committed blob hashes to the
      recomputed value.
11. **2026-10-12, during v5's fetch, before any v5 value was examined: the network cap.**
    - **What was preregistered:** 30 GB of estimated network for the whole v5 fetch.
    - **What the run showed:** after 8 of its 11 sites the meter read 24.5 GB. Willamette,
      Connecticut and Hermann remain. The meter also counts Hermann's cached reads, which cost no
      real traffic but come last in the list. The cap would stop the fetch during Connecticut, leaving
      it incomplete and Hermann's SSC without windows.
    - **The decision (the project owner's):** if the 30 GB cap stops the fetch, it rises to 40 GB
      estimated, and the fetch is rerun. It resumes from its cache, so no measured scene is read
      twice.
    - **What does not change:** the disk rule (stop under 20 GB free), every selection rule and the
      protocol.
    - **What was seen:** the per-site clear-scene counts and the meter in the run log. No turbidity,
      SSC or pair value of a v5 site had been read or examined.
    - **What happened:** the cap stopped the first run during Connecticut (197 clear scenes). The
      rerun at 40 GB completed every site (3,481 clear scenes, 32.5 GB estimated, nothing
      incomplete).
