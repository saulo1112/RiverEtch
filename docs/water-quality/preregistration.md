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
