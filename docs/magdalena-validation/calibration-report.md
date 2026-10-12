# Calibration and climate-context validation: report

**Run:** local, from commit `382bafe`, 2026-10-10. Inputs fetched 2026-10-09/10. Outputs verified
byte for byte by `climate-pipeline calibration verify`.

- **Preregistration:** [calibration-preregistration.md](calibration-preregistration.md), with
  five recorded deviations.
- **Generated results:** [calibration/results/results.md](calibration/results/results.md) and the
  CSV tables, figures and `MANIFEST` next to it.
- **Inputs:** [calibration/inputs/](calibration/inputs/README.md), with SHA-256 fetch manifests,
  under their own licences (IDEAM: CC BY-SA 4.0).
- **Observation records:** 112 records of the reach in
  [calibration/results/observations.sample.json](calibration/results/observations.sample.json),
  schema [observation-record.v1](../schema/README.md).

> Indices and band ratios are relative until a calibration passes, and none passed here. Nothing
> in this report states that any actor caused anything. `CM_D` is IDEAM's rating-model daily
> concentration, never a direct measurement.

## The answer in brief

| Question                                                   | Answer                                                                                                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Can a Sentinel-2 band or ratio be calibrated to turbidity? | **Not yet.** The NIR/red ratio passes the band diagnostic on L2A, but the hold-out has 7 pairs where 8 are needed            |
| … to total suspended solids?                               | **No.** Same direction, interval too wide                                                                                    |
| … to IDEAM's `CM_D`?                                       | **No.** One station; the association disappears once discharge is accounted for                                              |
| Does the satellite see the river's hydrology?              | **Yes, at 7 stations.** Water extent follows daily discharge or level (ρ 0.74–0.88), San Pablo on the study reach among them |
| Do season and rain explain the reach's NDTI?               | **No.** The models are weak, so no climate label is given                                                                    |
| Does ENSO show in water extent or NDTI?                    | **No.** 2 of 62 tests under 0.05, about what chance gives                                                                    |
| Maturity reached                                           | **Baselined** (5b passes). Not _validated in situ_                                                                           |

## What is incomplete

Read this first:

- **Stage 2c (ACOLITE) covers 29 of its 99 listed scenes.** They are all 27 turbidity and solids
  scenes, which came first in the priority order, plus 2 `CM_D` scenes. The other 70 `CM_D` scenes
  were not downloaded in this run, because the download needs the project owner's account. ACOLITE
  used 44 of its 120 minutes.
- **Permanent read errors (deviation 3).** 11 imagery reads and 12 station-selection reads hit
  items of 2024-01-23 that point to a non-public bucket. Those acquisitions count as no data.
- **CHIRPS (rain sensitivity) lacks April–September 2026, except June.** The server had not
  published those days.
- **The `CM_D` target has one station.** Of the two main-stem stations selected, Paso del Colegio
  has `CM_D` only for 1997–2011.

## Data

- **Stations:** 57 of 78 main-stem candidates passed the frozen selection (snap ≤ 1.5 km, channel
  ≥ 150 m). 51 of them passed under SCL alone; deviation 2 added the MNDWI fallback.
- **Station series:** of the series downloaded, 11 of 30 discharge series and 20 of 52 level series
  have no day in 2018-12 – 2026-09. Those stations were discontinued.
- **Clouds:** 75–85 % of scenes leave too few clear pixels. Bands were read only for scenes that
  could pass the guards (deviation 4).

**Pairs** (the same local day for `CM_D`, ±1 day for samples; the most recent 30 % is the hold-out):

| Target    | Pairs | Training | Hold-out | Stations | Cut date   |
| --------- | ----- | -------- | -------- | -------- | ---------- |
| Turbidity | 27    | 20       | 7        | 10       | 2023-09-30 |
| TSS       | 27    | 19       | 7        | 10       | 2023-09-30 |
| `CM_D`    | 73    | 52       | 21       | 1        | 2023-09-25 |

## Results by stage

### Stage 1: band diagnostic (L2A, 300 m window, training pairs)

The criterion is N ≥ 15, ρ ≥ max(0.6, ρ needed for N), and a cluster-bootstrap lower bound > 0.3.
Of 27 candidate-target rows, one passes:

| Target    | Best candidate | N   | ρ [95 % CI]       | ρ needed | NDTI ρ | Status |
| --------- | -------------- | --- | ----------------- | -------- | ------ | ------ |
| Turbidity | B8A/B04        | 20  | 0.76 [0.34, 0.90] | 0.685    | −0.06  | passed |
| TSS       | B8A/B04        | 19  | 0.71 [0.20, 0.89] | 0.694    | 0.06   | failed |
| `CM_D`    | D15switch      | 52  | 0.55 [0.27, 0.76] | 0.544    | 0.49   | failed |

- **NDTI does not track turbidity or solids across stations** (ρ ≈ 0). It stays a within-site
  change index.
- **The NIR/red ratio is the physically expected candidate for very turbid water.** Red saturates
  while NIR keeps rising. The curvature check agrees: the slope of B8A on B04 rises from 0.67 in
  the lower half of B04 to 0.98 in the upper half.

**Sensitivities of the turbidity pass** (report-only):

| Variant                         | N   | ρ [95 % CI]        | Reading                      |
| ------------------------------- | --- | ------------------ | ---------------------------- |
| 1 km window                     | 19  | 0.78 [0.32, 0.92]  | passes                       |
| ±3 days                         | 34  | 0.74 [0.47, 0.85]  | passes                       |
| Collection 1 (2b)               | 14  | 0.81 [0.38, 0.95]  | `insufficient_data` (N < 15) |
| **ACOLITE (2c), same 20 pairs** | 20  | 0.33 [−0.10, 0.80] | **fails**                    |

- **The pass holds across window size, matching window and collection, but not under ACOLITE.**
  ACOLITE's ratio is highest at the narrow upper-river stations at low turbidity, where its NIR
  exceeds its red. That is consistent with NIR adjacency from the banks over a 150–200 m river,
  which this ACOLITE configuration does not correct. That is an interpretation, not a finding.
- **Post hoc, not preregistered.** At 2 of the 20 pairs, L2A's B8A sits at its floor (0.0001).
  Without them L2A's ρ is 0.70 and ACOLITE's 0.21. So the floor does not explain the L2A result.
- **`CM_D`: the partial Spearman given log discharge is −0.01 to 0.10** for every candidate. The
  satellite adds nothing over discharge, as expected of a rating model. Restricted to validated
  values (N = 16), every candidate fails.

### Stage 2: processing homogeneity

- **2a (L2A baseline families 02.xx, 04.xx, 05.xx):** NDTI shows a reported shift: 02.xx is
  −0.67 robust σ, p = 0.0003. B8A/B04 differs between families (p < 0.0001), but by at most 0.34
  σ. That is under the 0.5 σ preregistered for a reported shift, and it is noted here.
- **2b (Collection 1):** on the 66 scenes both collections share (all baseline 05.xx), L2A and C1
  are identical (median difference 0). C1's gain would be the older years it reprocesses; its
  turbidity pairs (14) are one short of the minimum.
- **2c (ACOLITE):** see above. The rule is the same pixels, ACOLITE's surface reflectance, and no
  ACOLITE water mask (deviation 5).

### Stage 3: calibration

| Target    | Status              | Reason                          |
| --------- | ------------------- | ------------------------------- |
| Turbidity | `insufficient_data` | 7 hold-out pairs, 8 needed      |
| TSS       | `failed`            | Stage 1 failed; Stage 3 not run |
| `CM_D`    | `failed`            | Stage 1 failed; Stage 3 not run |

No model was fitted, no model card exists, and no record carries a physical value.

### Stage 4: published models (report-only, no retuning)

| Target    | Model           | N   | MdSA  | SSPB   |
| --------- | --------------- | --- | ----- | ------ |
| Turbidity | Nechad 2009     | 25  | 163 % | −119 % |
| Turbidity | Dogliotti 2015  | 27  | 100 % | +31 %  |
| TSS       | Nechad 2010     | 24  | 336 % | −321 % |
| `CM_D`    | Nechad 2010 TSS | 72  | 152 % | +130 % |

The published coastal coefficients do not transfer to this river on L2A reflectance.

### Stage 5: climate and hydrology

- **5a, season and rain (reach NDTI, leave-one-hydrological-year-out):**
  - Skill is 0.05 upstream, 0.04 downstream and −0.08 for the delta. The bar is 0.15.
  - All three signals are `weak`, so every record's climate label is `not_evaluated`.
  - Discharge as an extra regressor does not help.
- **5b, water extent against discharge or level (lag 0):** 7 stations pass, 23 fail, and 22 have no
  series in the period (`no_data`).

  | Station                    | Series | N   | ρ [95 % CI]       |
  | -------------------------- | ------ | --- | ----------------- |
  | San Pablo 23207040 (reach) | Q      | 77  | 0.78 [0.62, 0.86] |
  | El Contento 23217030       | Q      | 137 | 0.88 [0.80, 0.92] |
  | La Gloria 23217060         | Level  | 134 | 0.87 [0.77, 0.92] |
  | Gamarra (aut.) 23217080    | Level  | 133 | 0.81 [0.71, 0.87] |
  | Regidor 25027410           | Q      | 140 | 0.74 [0.61, 0.83] |
  | Tacamocho I 25028450       | Q      | 26  | 0.85 [0.53, 0.94] |
  | Calamar 29037020           | Q      | 184 | 0.77 [0.64, 0.86] |

  The passing stations are on the middle and lower river. A likely reason is that there a 2 km
  disk holds enough floodplain to change with the flow; it was not tested.

- **5c, ENSO:**
  - Of 62 tests, 2 have p < 0.05: extent at Puerto Salgar and `TR_QS_M` at El Banco. Chance gives
    about 3.
  - Water extent is larger in La Niña than in El Niño at 29 of 52 stations.
  - The reach's NDTI shows no phase difference (p 0.51 and 0.58).
  - Records carry the ONI phase as context only.

### Observation records

- The reach has 112 records, all sealed and valid against the v1 schema.
- **Calibration status is `failed` in every record**, the strictest status across the three
  targets. No record carries a value.
- **Climate context:** the label is `not_evaluated` (5a weak). The ENSO phase is present in all
  112 records, the discharge percentile at Puerto Wilches (23187010) in 71.
- **Verdict:** 1 record is anomalous (D0), as in PR #11.

## Reproduction gate

- **The Magdalena validation was rerun on 2026-10-10** into a scratch folder.
- **24 of 24** reproduction checks pass, with 0 read errors.
- All 34 result tables are identical, cell by cell, to those committed in PR #11, including
  `scenes.csv`.

## Deviations

| #   | When                                     | Change                                                                    |
| --- | ---------------------------------------- | ------------------------------------------------------------------------- |
| 1   | before any value                         | YAML quoting fix of one candidate's formula                               |
| 2   | after the first selection, before values | MNDWI fallback when SCL fails selection, as the screening does            |
| 3   | during selection                         | items of 2024-01-23 in a non-public bucket count as no data               |
| 4   | during the value fetch                   | bands read only for scenes that can pass the guards (data volume)         |
| 5   | after the first ACOLITE scene            | ACOLITE on the L2A pixels, without its water mask (it rejected the river) |

Deviation 5 was decided after a preliminary run had shown the L2A and C1 Stage 1 results. The
preregistration says so.

## What can and cannot be said

| Can be said                                                                                            | Cannot be said                                                                       |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Sentinel-2 water extent follows IDEAM discharge or level at 7 main-stem stations, San Pablo included   | That water extent measures discharge anywhere else, or at the 23 failing stations    |
| On L2A, the NIR/red ratio tracks measured turbidity at 10 stations (training pairs, cluster bootstrap) | Any value in NTU or mg/L; that the ratio survives a different atmospheric correction |
| NDTI is a within-site change index; it does not track turbidity across stations                        | That NDTI measures water quality                                                     |
| The reach is quiet and its NDTI is not explained by season, rain or ENSO                               | That an anomaly is "explained by rain", or that anyone caused it                     |
| IDEAM's `CM_D` at Nariño behaves as a function of discharge                                            | That the satellite measures sediment concentration                                   |

## What could not be verified

- **Station metadata, not checked in the field:**
  - Reservoir influence at Paso del Colegio (snapped 1.16 km from its coordinate) and at Gigante's
    El Quimbo outflow.
  - The catalogue's labelling of Uré as main stem.
  - Coordinates at Tacamocho I and Puerto Suiza.
  - Tacamocho I passes 5b with 26 scenes, so its result rests on its listed coordinate.
- **Sample methods:** the IDEAM water-quality samples are taken as published. Their methods and
  replicates were not audited.
- **Why ACOLITE's ratio disagrees** (adjacency, the fixed-aerosol choice over a small box, or the
  reprocessed Level-1C baseline) was not tested.
- **Cross-platform reproduction:** CSV and JSON outputs are verified byte for byte on this machine.
  Linux reproduction runs in CI (`.github/workflows/calibration.yml`).

## What would move the maturity

- **One more turbidity hold-out pair**, or a new sampling campaign timed to clear Sentinel-2
  passes, would let Stage 3 run on turbidity.
- **Field turbidity at the 5b stations** would test the ratio where the satellite already tracks
  the flow.
- **An adjacency-corrected run** (ACOLITE's RAdCor) would test whether the ACOLITE disagreement is
  the banks' signal.

## Reproduce

From `pipeline/`:

```bash
uv run climate-pipeline calibration run --root ..     # about 1 minute, offline
uv run climate-pipeline calibration verify --root ..  # recompute and compare with MANIFEST
```

The fetch (`calibration fetch`) and the ACOLITE runs (`pipeline/acolite/README.md`) need the
network. Their outputs are the committed snapshots.
