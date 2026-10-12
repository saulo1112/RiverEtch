# Calibration and climate-context validation: preregistration

**Status: written on 2026-10-09, before any new value was fetched.** Every value lives in
`pipeline/calibration.yaml`. The pixel guards, SCL classes and water-B11 range are read unchanged
from `pipeline/screening.yaml`. The code is written after this file, in
`pipeline/src/climate_pipeline/calibration/`. Each run records this file's git blob hash and the
commit. Any later change is listed under [Deviations](#deviations), with its date and reason.
Decision: D15.

> NDTI and every band ratio here are relative indices until a stage below says otherwise. No
> output states that any actor caused anything. A physical unit is shown only for a target and
> range where Stage 3 passed.

## Questions

The Magdalena validation ([report](report.md)) left NDTI on the Puerto Wilches reach as a quiet,
relative signal with no demonstrated link to turbidity, suspended solids or flow. This validation
asks:

1. **Can any Sentinel-2 band or ratio be calibrated** to turbidity, total suspended solids (TSS) or
   IDEAM's daily suspended-sediment concentration on the Magdalena main stem? (Stages 1-4)
2. **Does rain or hydrology explain the reach's signal?** Can the satellite see the river's
   hydrology (water extent against discharge) and its climate phases (ENSO)? (Stage 5)
3. **What record does the product publish?** It publishes an observation record whose fields say
   what was calibrated and what was not (the observation contract).

An honest negative result is a valid outcome, and is reported first.

## What was already seen

Disclosed in full because some criteria were set after it was seen.

1. **The Magdalena validation's outputs** (PR #11): its in-situ pairs (`insitu_pairs.csv`, 23
   rows with turbidity and TSS values at Puerto Wilches, San Pablo, Barrancabermeja and Sitio
   Nuevo), the NDTI-against-in-situ figure, the saturation result (NDTI against red reflectance),
   the river-level correlations, and the reach's per-scene NDTI and D0 flags.
2. **Metadata probes on 2026-10-09**, no values:
   - water-quality points on a "Magdalena" stream since 2018-12: 30 points, 284 turbidity and
     287 TSS samples (counts and date ranges per point);
   - IDEAM's public bucket: its variable list and catalogue definitions (`CM_D`: "Concentración
     media diaria / depende de CS_PROMEDIO_D y EQ_CS-CM (raiting model)", mg/L), which stations
     have `CM_D` (127; on the Magdalena main stem: Pericongo 21027010, Paso del Colegio 21077020,
     Puente Santander 21097070, Nariño 21237010), file sizes, and that `Q_MEDIA_D` and
     `NV_MEDIA_D` exist for the Puerto Wilches, San Pablo, Barrancabermeja, Sitio Nuevo, Puerto
     Salgar and El Banco stations;
   - Earth Search's Collection 1 (`sentinel-2-c1-l2a`) item counts and processing baselines at the
     reach for four three-month windows (none for 2018-12 to 2019-02);
   - that the NOAA ONI table is reachable.

**Not seen:** any value of `CM_D`, `Q_MEDIA_D`, `NV_MEDIA_D` or `TR_QS_M`; any sample value at a
station other than the four above; any band other than red, green and B11 at any place; any rain
sum beyond 168 h; any water width or extent; any Collection-1 reflectance; any ONI value used here.

## Data (all fetched on this machine)

| Source                            | What                                                                          | Access                  |
| --------------------------------- | ----------------------------------------------------------------------------- | ----------------------- |
| Earth Search `sentinel-2-l2a`     | Primary imagery: B02-B8A, B11, B12, SCL (COGs)                                | STAC + HTTP range reads |
| Earth Search `sentinel-2-c1-l2a`  | Stage 2b sensitivity (homogeneous baselines)                                  | same                    |
| datos.gov.co `62gv-3857`          | Turbidity and TSS samples (IDEAM)                                             | SODA, cached, SHA-256   |
| IDEAM bucket `s3-estacionesideam` | `CM_D`, `Q_MEDIA_D`, `NV_MEDIA_D`, `TR_QS_M`, station and variable catalogues | S3 list + CSV, SHA-256  |
| Open-Meteo archive                | Daily catchment rain at the 10 grid points of `rain-grid.csv`                 | cached, SHA-256         |
| CHIRPS 2.0 daily COGs             | Rain sensitivity at the same points                                           | point reads             |
| NOAA CPC ONI                      | ENSO index                                                                    | text table, SHA-256     |
| ACOLITE repository                | Stage 2c code and Stage 4 coefficient tables                                  | git, pinned commit      |

IDEAM data are CC BY-SA 4.0 (attribution: IDEAM); their snapshots keep that licence.

**Fetch and run are separate.** `climate-pipeline calibration fetch` snapshots every raw input under
`docs/magdalena-validation/calibration/inputs/` with a fetch manifest (URL, status, bytes, SHA-256,
UTC). `climate-pipeline calibration run` recomputes every result from those snapshots without the
network, on any machine and in CI.

## Station selection (metadata only, frozen before values are fetched)

1. **Candidates** are the union of:
   - `62gv-3857` points whose stream is the Magdalena with at least one turbidity or TSS sample
     dated 2018-12-01 or later;
   - stations in IDEAM's catalogue with `corriente` = MAGDALENA that have a `CM_D`, `Q_MEDIA_D` or
     `NV_MEDIA_D` file.

   "Magdalena" means an exact match after removing accents, case and surrounding spaces, so named
   arms (Brazo de Loba, Brazo de Mompox) are excluded. Coordinates come from the catalogue when the
   station code matches. In the datos.gov.co copy of the catalogue the latitude and longitude
   fields are swapped; this is handled and tested.

2. **Main channel.** On a ±3 km grid around each station (20 m), the SCL water frequency over the
   2022-2025 acquisitions marks water where the frequency is ≥ 0.5, with at least 20 clear
   observations (the screening's values). The screening's MNDWI fallback applies when SCL gives no
   water component. The main channel is the largest connected water component.
3. **Snap and width.** The station snaps to the nearest main-channel pixel within 1.5 km. Its width
   is 2 × the largest distance to land among main-channel pixels within 300 m of the snapped point.
   **A station is selected if it snaps and its width is ≥ 150 m.**
4. The selected list (codes, names, coordinates, snap distance, width, which files exist, sample
   counts, no values) is committed before any value is fetched.

## Station windows and extraction

- **Window:** main-channel pixels within 300 m of the snapped point, after eroding the water mask by
  2 pixels (20 m), against land adjacency in the near infrared. A 1 km window is report-only.
- **Bands:** B02-B07, B08, B8A, B11 and B12 on the 20 m grid, with 10 m bands averaged. Scaling
  follows each item's processing baseline and `boa_offset_applied`, as the screening.
- **Per scene:**
  - valid pixels are window pixels whose SCL class is neither no-data nor invalid;
  - contamination is the invalid share;
  - pixels with B11 > 0.05 are glint and leave the medians;
  - the scene is excluded when the median water B11 is outside [−0.03, 0.08] (a scaling problem);
  - a scene needs at least 20 valid pixels and contamination ≤ 0.2.
- **Features:** band medians first, then the ratios and indices from those medians. NDTI is also
  reported as the median of per-pixel NDTI, for comparison with the product.
- **Which scenes:**
  - for sample stations, the scenes within ±3 days of a sample;
  - for `CM_D` stations, every scene;
  - for 5b stations, every scene in a 2 km window;
  - for the reach curvature check, every usable Puerto Wilches scene.

  Small windows are cached, so a rerun reads nothing new.

## Matchups and splits

- A sample's local date is compared with the acquisition's local date (America/Bogota). The
  nearest scene wins; a tie goes to the earlier scene. **Only ±1 day can pass a stage**; ±3 days
  is report-only. `CM_D` is matched on the same local day.
- Same-station, same-day samples are reduced to their median. Values reported as "<x" are kept
  and flagged, and never fitted.
- **Clusters:** one acquisition (date and orbit) can match several stations and samples, so every
  bootstrap resamples acquisitions, not pairs.
- **Hold-out:** per target, the most recent 30 % of pairs. The cut is the 70th percentile of pair
  dates, computed when the pair table is frozen; ties go to training. Hold-out pairs never enter
  selection or tuning. Leave-one-station-out is reported as the transfer test.

## Candidates and targets

**9 candidates:** B03, B04, B05, B8A, NDTI, B04/B02, B05/B04, B8A/B04, and the Dogliotti 2015
red-NIR switch (available only if its published coefficients are fetched). NDTI and B04/B03 have
identical ranks, so only NDTI is kept. The expected sign is positive for all.

**3 targets:**

| Target    | Values                    | Unit | Matching |
| --------- | ------------------------- | ---- | -------- |
| turbidity | `62gv-3857` samples       | NTU  | ±1 day   |
| tss       | `62gv-3857` samples       | mg/L | ±1 day   |
| cm_d      | IDEAM `CM_D` daily series | mg/L | same day |

`CM_D` is labelled "IDEAM rating-model daily concentration" everywhere, and never presented as a
direct measurement. Any pass is worded "tracks IDEAM's rating-model concentration at stations X-Y,
range A-B". Because a rating model may tie `CM_D` to discharge, the report adds a partial Spearman
given log discharge (report-only), so a band that only tracks discharge is flagged.

In all, 27 candidate-target pairs, all reported. The top 2 per target are chosen on training only.

## Criteria

| Stage             | Pass (else)                                                                                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 band diagnostic | N_train ≥ 15 (±1 d), Spearman ρ ≥ 0.6 (expected positive), cluster-bootstrap 95 % lower bound > 0.3 (10,000 resamples, seed fixed) (else `failed`; N_train < 15 → `insufficient_data`) |
| 3 calibration     | N_holdout ≥ 8; LOO and hold-out MdSA ≤ 50 %, \|SSPB\| ≤ 25 %, MdSA ≤ 0.8 × the null model's MdSA (null = training median); ridge only if N_train ≥ 10 per feature                      |
| 4 transfer        | report-only: MdSA and SSPB of published models, no retuning                                                                                                                            |
| 5a climate        | per signal: leave-one-hydrological-year-out skill = 1 − SSE(season + rain) / SSE(season) ≥ 0.15 (else `weak`)                                                                          |
| 5b extent-flow    | per station, lag 0: ρ ≥ 0.7 and lower bound > 0.5 (month-block bootstrap); lags ±1 and ±3 days report-only, no best-lag picking                                                        |
| 5c known periods  | report-only: hit / miss / false alarm per ENSO episode, hydrological-year-block permutation (10,000, α = 0.05)                                                                         |

**The bar at small N is set by the interval, not by ρ ≥ 0.6.** For a 95 % lower bound above 0.3,
the ρ needed is roughly as follows (Fisher z with the Bonett-Wright Spearman error; the criterion
itself uses the bootstrap):

| N        | 10   | 15   | 20   | 25   | 30   | 33   | 40                   | 50   | 100  |
| -------- | ---- | ---- | ---- | ---- | ---- | ---- | -------------------- | ---- | ---- |
| ρ needed | 0.82 | 0.74 | 0.69 | 0.65 | 0.62 | 0.60 | 0.60 (ρ ≥ 0.6 binds) | 0.60 | 0.60 |

**Metrics.** Water-quality variables are roughly log-normal, so percentage errors are asymmetric.
The primary metrics are the median symmetric accuracy, MdSA = 100 × (exp(median |ln(ŷ/y)|) − 1),
and the symmetric signed percentage bias, SSPB = 100 × sign(m) × (exp(|m|) − 1) with
m = median ln(ŷ/y) (Morley et al., 2018). MAPE is reported as a secondary metric.

## Stages

1. **Stage 1, band diagnostic** (training pairs only).
   - Compute Spearman ρ and the cluster-bootstrap interval for each candidate and target.
   - Binned plots of each candidate against each target show saturation.
   - An in-situ-free curvature check on every usable Puerto Wilches scene asks whether B8A keeps
     rising where B04 flattens.
2. **Stage 2, processing homogeneity** (report-only, informs 5a).
   - **2a:** for each candidate, a Kruskal-Wallis test across processing-baseline families (00.xx,
     02.xx, 04.xx, 05.xx; families with ≥ 10 scenes) on seasonal anomalies (feature minus its
     station-month median). Each family's median shift is given in robust σ; a shift above 0.5 σ
     with p < 0.01 is reported as a shift.
   - **2b:** the same windows extracted from `sentinel-2-c1-l2a`, with Stage 1 and 2a repeated as a
     sensitivity. If C1 passes where L2A fails, the report recommends migrating the product to C1,
     as a separate decision.
   - **2c, ACOLITE:** for the matchup scenes only. The user downloads the Level-1C SAFE files; the
     pipeline lists them. ACOLITE runs at a pinned commit, in its own environment, with a
     committed settings file. Its water-leaving reflectances repeat Stage 1 as a sensitivity. The
     box is 2 h, after which the outcome is `incomplete`. No SAFE file is committed.
3. **Stage 3, calibration** (only for a target whose Stage 1 passed).
   - Candidate models:
     - M1: log-log OLS on the top candidate;
     - M2: log-log OLS on the second;
     - M3: ridge on both, if N_train ≥ 20, with λ from {0.01, 0.1, 1, 10} chosen by LOO on
       training.
   - A feature enters as its logarithm when it is positive on every training pair, else linearly
     (NDTI).
   - The model with the lowest training LOO MdSA is selected, then evaluated once on the hold-out.
   - **Abstention**, at prediction time, when:
     - a feature is outside its training range;
     - the glint share is > 0.5;
     - contamination is > 0.2;
     - there are fewer than 20 valid pixels;
     - the B11 check failed.
   - A model card (JSON) carries the coefficients, range and parameter hash.
4. **Stage 4, transfer** (report-only).
   - Models: Nechad 2009 (turbidity), Nechad 2010 (TSS) and the Dogliotti 2015 switch, with
     Sentinel-2 coefficients taken from ACOLITE's open coefficient tables. The source is fetched
     with SHA-256; if it cannot be fetched, the stage is skipped.
   - No retuning. L2A surface reflectance stands in for water-leaving reflectance, which is a
     stated limitation.
5. **Stage 5, climate and hydrology.**
   - **5a, per signal** (upstream, downstream, difference), on the reach's frozen
     `results/scenes.csv`:
     - Season model: 2 harmonics of the day of year. Full model: season + log1p of catchment-mean
       rain summed over 1, 3, 7, 14 and 30 days ending on the acquisition day (Open-Meteo). CHIRPS
       is a sensitivity.
     - Validation is leave-one-hydrological-year-out (December to November). Skill is computed on
       the out-of-fold predictions.
     - Discharge as an extra regressor is report-only. A lag-1 autoregressive model is reported only
       as a persistence diagnostic, never as the expected value: it would turn a weeks-long
       anomaly into "expected".
   - **5b, per station with discharge or level:** water extent in a 2 km window (MNDWI > 0 among
     valid pixels; scenes with ≥ 90 % valid) against same-day `Q_MEDIA_D` (else `NV_MEDIA_D`).
     - Imagery runs to the end of each series, within the period.
     - The bootstrap resamples calendar months.
   - **5c, known periods:**
     - ENSO episodes come from the ONI snapshot, by the operational rule: at least 5 consecutive
       overlapping seasons at ≥ +0.5 (El Niño) or ≤ −0.5 (La Niña).
     - The test compares per-station water-extent seasonal anomalies between phases, one-sided,
       because physics fixes the direction: more water in La Niña than in El Niño. NDTI and
       `TR_QS_M` are tested two-sided.
     - Per episode the result is a hit or a miss: its mean anomaly has the expected sign and
       exceeds 0.5 robust σ. A false alarm is a neutral hydrological year whose mean anomaly
       exceeds 0.5 σ.
     - The permutation shuffles phase labels across hydrological years.
     - The news-reported high-water periods (`post-hoc-events.csv`) are described only.

## Labels in the observation record

A label is given only when the flagged signal's own 5a model passed:

- The **expected** value is the season + rain out-of-fold prediction, and the **residual z** is
  (observed − expected) / the robust σ of the out-of-fold residuals.
- **The labels:**
  - a D0-anomalous scene with |residual z| < 3 is `explained_by_climate`;
  - one at or above 3 is `unexplained`;
  - other scenes are `normal`.
- **If 5a is weak for that signal, every label is `not_evaluated`, never `explained_by_climate`.**
- `unexplained` is never displayed as human pressure.

The record's schema is `docs/schema/observation-record.v1.schema.json`. It is generated from the
pydantic model and checked against it by a test.

## Stop rules and maturity ladder

**Stop rules:**

- An unreachable source makes its stage `incomplete`, reported at the top of the report.
- If Stage 1 does not pass for a target, Stage 3 does not run for it. That target's calibration
  status is `failed` or `insufficient_data`.
- If 5a is weak for a signal, that signal's labels are `not_evaluated`.
- A failed reproduction check (the Magdalena validation's 24 checks and its per-scene table) stops
  the publication of outputs.

**Maturity ladder:**

| Level             | Reached when                                                                     |
| ----------------- | -------------------------------------------------------------------------------- |
| Observable        | index departures, with false-alarm share and detection power (reached in PR #11) |
| Baselined         | 5a passes for a reach signal, or 5b passes                                       |
| Validated in situ | Stage 3 passes for a target, within its range, at its stations                   |

## Runs and reproducibility

The runs happen on the developer's machine, which reaches every source above:

1. `climate-pipeline calibration fetch --stations-only`. The station list is committed before any
   value.
2. `climate-pipeline calibration fetch`. The snapshots are committed.
3. ACOLITE (optional), as in Stage 2c.
4. The Magdalena validation reruns into a scratch folder, and must give 24 of 24 checks and an
   identical per-scene table.
5. `climate-pipeline calibration run`. Results go to `calibration/results/` with a `MANIFEST` in
   `sha256sum` format.

`climate-pipeline calibration verify` recomputes the results offline and compares CSV and JSON byte
for byte. Figures are hashed but marked "same-machine", because PNG bytes vary across machines. CI
runs the same verification on every pull request.

Every network step is resumable from its cache. A run with any read error is rerun before its
results are accepted.

## What will not be done

- No threshold, window, candidate, target, split or seed is changed after the pair table or any
  result is seen.
- No best lag, window or station subset is picked after seeing results.
- No hold-out pair enters selection or tuning.
- No comparison with a licence or discharge limit: Resolution 631 of 2015 covers point discharges,
  not the river's ambient sediment ([regulatory.md](regulatory.md)).
- No physical unit is shown for an uncalibrated record.
- No actor is said to have caused anything.

## Deviation protocol

- A technical failure (network, timeout) is rerun, unchanged.
- A bug found after results were seen is fixed. Both results are reported, and the change is
  listed under Deviations.
- A stage that overruns its time box is `incomplete`.

## Deviations

1. **2026-10-09, before any value was fetched: a YAML syntax fix.** In `pipeline/calibration.yaml`,
   the Dogliotti candidate's formula `dogliotti_2015_switch(B04, B8A)` sat unquoted in a flow
   mapping, where YAML splits at the comma. It is now quoted. No value, threshold or rule changed.
   The loader caught it the first time the file was read.
2. **2026-10-09, after the first station selection and before any value was fetched: the MNDWI
   fallback follows the screening.** Decided by the project owner.
   - **What was preregistered:** the MNDWI mask was used only when SCL gave _no_ water component.
   - **What the first selection showed:** SCL classified the very turbid river as non-water and
     fragmented it. Girardot (21237030) and Arrancaplumas (21237020) sit on the river, yet their
     water-frequency maps showed only fragments, and they were excluded for "no main channel within
     1500 m". This is the failure the screening's post-hoc MNDWI rule exists for; the screening
     applies MNDWI whenever the SCL mask fails, not only when it is empty.
   - **The change:** when the SCL mask does not select a station (no water, no snap within 1.5 km,
     or a channel under 150 m), the same rule is applied to the MNDWI mask.
   - **What was seen and what was not:** the first selection's station list, the outcomes and the
     masks. No sample, series or other value had been fetched.
   - **The original rule stays visible:** `stations.csv` keeps each station's outcome under the
     SCL mask alone (`scl_selected`, `scl_reason`, `scl_width_m`), and the report gives that list
     as a sensitivity.
   - **Outcome:** 57 of 78 candidates selected, 51 of them under SCL alone. The fallback added
     Nariño (21237010) and Paso del Colegio (21077020), the only `CM_D` stations selected, plus
     Uré (2501700189), Aipe, Gigante Las Vueltas and Gigante "salida represa El Quimbo". Girardot
     and Arrancaplumas remain excluded under both masks (channel 126 m and 120 m wide).
3. **2026-10-09: permanent read errors.** Earth Search's items of 2024-01-23 (sentinel-2b, tiles
   18NUH, 18NVH, 18NVK, 18NWL, 18PWQ, 18PXQ) point to a non-public JPEG2000 bucket
   (`/vsis3/sentinel-s2-l2a/...`) instead of public COGs.
   - They fail identically on every rerun, so they are a catalogue fault, not a network failure,
     and that acquisition counts as no data.
   - A run is accepted when its only read errors are these (listed in `read-errors.csv`). Any
     other read error still requires a rerun.
4. **2026-10-09, during the value fetch: bands are read only for scenes that can pass.** Proposed
   after the project owner flagged the data volume.
   - **What the fetch showed:** each band read downloads whole COG blocks, about 2 MB, to keep
     about 43 KB. The ~130,000 reads came to about 250 GB over a 72 Mbit/s link. On the SCL
     already read (first three stations), only 15–18 % of scenes leave ≥ 90 % of the 2 km disk
     clear, and 17–27 % leave the 300 m window usable.
   - **The change:** SCL is read first. The other bands are not read when:
     - no window can pass the scene guards: fewer valid SCL pixels than `min_valid_px` (the water
       pixels are a subset of them), or contamination above `max_contamination`; or
     - the disk's clear SCL share is under `valid_fraction_min`.
   - **Those rows** keep their SCL statistics. Their medians and B11 check are empty, and
     `bands_read` is 0.
   - **What does not change:** any rule, and any row an analysis uses. The scene guards and the
     5b/5c filter admit only rows whose bands were read in full. One wording changes: a
     calibrated record on such a scene abstains with "window too cloudy to measure" instead of
     naming the guard it failed.
   - **What was seen:** no value had been analysed. The cloud shares come from the SCL the fetch
     had already read.
5. **2026-10-10, after the first ACOLITE scene: ACOLITE is measured on the L2A pixels, without
   its own water mask.** The project owner left the choice to the analyst, with the aim of
   detecting turbidity where the data allow.
   - **What was preregistered:** Stage 2c measures ACOLITE's water-leaving reflectance (`rhow`,
     L2W) over the L2A window pixels. Pixels that ACOLITE's default water mask rejects drop out.
   - **What the first scene showed:** at Regidor on 2019-02-08, that mask flagged 285 of the
     window's 293 pixels as non-water. Its rule is top-of-atmosphere reflectance at 1.6 µm above
     0.0215, and the turbid river gave 0.0239. The correction itself ran on all 293 pixels.
   - **Why it matters:** most turbid-river scenes would have kept fewer than 20 pixels, so Stage
     2c would have measured only the clearer water.
   - **The change:** the medians come from ACOLITE's surface reflectance (`rhos`, L2R) over
     exactly the L2A pixels: SCL-valid, not glint, every band finite.
     - Where ACOLITE's mask keeps a pixel, `rhow` equals `rhos` (difference 0 on 2,571 pixels of
       that scene).
     - ACOLITE's settings do not change.
     - Both corrections are compared on the same pixels, as the design intended.
   - **What was seen:**
     - That scene's ACOLITE mask flags and reflectance medians. No ACOLITE value had been paired
       with a sample.
     - A preliminary run of the analysis on the L2A and C1 snapshots, made to check the code and
       its runtime, had already shown the Stage 1 results of those collections.
