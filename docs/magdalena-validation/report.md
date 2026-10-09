# Magdalena validation: report

**Run:** full, local, from commit `bc588ea`, 2026-10-09 01:58-02:24 UTC.

- [method.md](method.md) git blob `975903a1`, unchanged since its pre-registration commit `c25f1e6`.
- Generated results: [results/results.md](results/results.md) and the CSV tables and figures next
  to it.
- Regulatory verification: [regulatory.md](regulatory.md).
- Case file: [magdalena.sample.json](magdalena.sample.json), a byte copy of
  `pipeline/out/case/magdalena.json`.

> NDTI is a relative index: comparable only within one sub-reach, never between sites, never NTU.
> An anomaly is a departure from the sub-reach's own baseline. It is a flag to investigate, never
> evidence that any actor caused anything. This reach's real series was seen before this method
> was written (see [method.md](method.md#what-was-already-seen)), so question 1 is not a blind test.

## The four results

**First, what limits the demo's claims.** Nothing here shows that NDTI tracks turbidity, suspended
solids or flow on this reach:

- the in-situ data are too few, or point the other way;
- NDTI barely rises with red reflectance;
- the detector finds a step mainly when it lands on one sub-reach and not the other.

The demo can therefore show a quiet real series and the detector's mechanics on a labelled
synthetic event. It cannot claim that NDTI measures water quality here, or that a real plume of a
given concentration would be detected.

### 1. Quietness: quiet on the frozen geometry; one corridor alternative would not be

| Reach (frozen geometry)           | D0 anomalous / scored | Share | Wilson 95 %     | Largest variant share |
| --------------------------------- | --------------------- | ----- | --------------- | --------------------- |
| Target `magdalena-puerto-wilches` | 1 / 112               | 0.9 % | [0.2 %, 4.9 %]  | B3: 6 / 112 = 5.4 %   |
| Control `meta-orocue`             | 3 / 51                | 5.9 % | [2.0 %, 15.9 %] | Z2.5: 5 / 51 = 9.8 %  |

- **Mechanical reading: quiet.** The D0 upper bound (4.9 %) is under 10 %, and every variant's
  share is under 10 %. These are the numbers already seen in the Urrá validation; the reproduction
  is exact (below).
- **Against the control: not distinguishable.** The intervals overlap, mainly because the control
  has only 51 scored scenes. The target's point share is lower; the data cannot say it is lower.
- **Corridor sensitivity (report-only, but it changes the reading):**
  - at 300 m the target would still read quiet: D0 2 / 117 [0.5 %, 6.0 %], largest variant B3
    5.1 %;
  - at **150 m** (the "main channel" approximation), D0 stays at 1 / 98 [0.2 %, 5.6 %], but
    **variant B3 (a centred 365-day baseline) flags 11 / 98 = 11.2 %**, above the 10 % cap. On that
    geometry the reach would read **not quiet**.

  The corridor table does not split B3's flags by signal. On the frozen geometry, B3's six
  anomalous scenes carry 5 upstream, 1 downstream and 1 difference flag. The quiet reading therefore depends on the corridor and on
  the baseline window.

- **The one D0 anomaly, 2020-08-26:**
  - it is on the difference signal: z = −4.51, so downstream was _less_ turbid than upstream;
  - its glint share was 0.625, and G2 removes it for glint;
  - point rain (48 mm in 72 h) and catchment rain flagged it (CHIRPS 3-day catchment mean
    22.6 mm, Open-Meteo 72 h catchment mean 42.3 mm);
  - the same signal within ±15 days of that date in the other 7 years lies between −0.009 and
    0.020 (median 0.007), so the value (−0.046) is unusual for its season;
  - no river level exists for that date.

  It reads as a glinty, rainy scene, not as a pattern.

### 2. In-situ data: no ground truth on this reach

| Comparison (pre-registered)                       | Pairs | Spearman ρ | Bootstrap 95 % | Reading         |
| ------------------------------------------------- | ----- | ---------- | -------------- | --------------- |
| Turbidity (NTU), primary stations, ±1 day         | 2     | -          | -              | not enough data |
| Suspended solids (mg/L), primary stations, ±1 day | 2     | -          | -              | not enough data |
| Turbidity, all four stations, ±3 days             | 9     | −0.32      | [−0.88, 0.51]  | not enough data |
| Suspended solids, all four stations, ±3 days      | 10    | −0.45      | [−0.97, 0.37]  | does not track  |
| River level, Puerto Wilches (2024-10..2025-12)    | 19    | −0.47      | [−0.76, −0.04] | does not track  |
| River level, San Pablo (2019-01..2020-03)         | 11    | 0.22       | [−0.61, 0.88]  | inconclusive    |
| River level percentile, both stations pooled      | 30    | −0.18      | [−0.55, 0.25]  | does not track  |

- **Turbidity and suspended solids.** The primary stations sit 7-8 km from the reach's
  midpoint, at its two ends. With 7 samples each in 2021-2023, only 2 met a usable scene within a
  day. Widening to all four stations (two of them about 40 km away) and ±3 days gives 9-10 pairs.
  - These samples run from 127 to 1,946 mg/L and from 190 to 1,400 NTU: very turbid water.
  - The suspended-solids reading is "does not track" because the whole interval lies below 0.4.
    With 10 pairs from four places, that means no sign of a strong positive relation, not proof
    that there is none.
- **River levels.** At Puerto Wilches NDTI was _lower_ at higher water (ρ −0.47, interval below 0).
  This is an observation over 19 scenes from December 2024 to December 2025; no cause is inferred. San Pablo's level, in
  an earlier period, gives an interval too wide to read. Levels are not discharge: no rating curve
  was used.
- **Saturation check.** Over the 112 usable scenes, NDTI and red reflectance correlate weakly
  (ρ ≈ 0.30 in each sub-reach). Within the lower and the upper half of red reflectance they do not
  correlate at all (|ρ| ≤ 0.13). The reading is "weak relation in both halves": no range was found
  where NDTI clearly rises with red reflectance.
  - NDTI spans −0.02 to 0.13 and red reflectance 0.05 to 0.14 ([figure](results/figures/ndti_vs_red.png)).
  - With in-situ turbidity in the hundreds of NTU, this is consistent with an index that has little
    room left to respond. It is not proof of saturation.

**Meaning for the demo:** NDTI on this reach is a relative signal with no demonstrated link to
measured turbidity or flow. A demo anomaly can be described only as "a departure from this
sub-reach's own baseline".

### 3. Regulatory verdict: the evidence points to (c)

From [regulatory.md](regulatory.md):

- **Contract:** maintenance dredging of the sector containing the reach is under contract
  0-458-2023, from 2024-01-04 to 2026-12-31 (open contract record). Its documents are behind a
  reCAPTCHA and unread.
- **No licence:** the licensing rules read license only deepening dredging. The sector's 2021
  tender says maintenance dredging "no requiere de Licencia Ambiental" (tr. "does not require an
  environmental licence"). It manages the work through a contractor's PAGA approved by the
  supervision, not by an environmental authority.
- **No numeric limit:** none was found for turbidity or suspended solids. The 2011 environmental
  guide only recommends monitoring them.
- **Authority unverified:** no environmental authority or instrument for the current contract
  could be verified.

**Recommendation:** keep the simulated labels and no entity names in the interface. A person
decides.

### 4. Detection power and the demo event

On copies of the real series (the file is never edited), each of the 112 eligible scenes received
every step on its downstream sub-reach, and the unchanged D0 rule scored it
([figure](results/figures/detection_curve.png)):

| NDTI step added downstream | 0     | 0.01  | 0.02  | 0.03  | 0.04  | 0.05 | 0.08  | 0.12  | 0.15  |
| -------------------------- | ----- | ----- | ----- | ----- | ----- | ---- | ----- | ----- | ----- |
| Detected (D0 rule)         | 0.9 % | 5.4 % | 17 %  | 50 %  | 88 %  | 98 % | 100 % | 100 % | 100 % |
| … on the downstream signal | 0 %   | 0.9 % | 1.8 % | 2.7 % | 8.0 % | 13 % | 39 %  | 71 %  | 98 %  |
| … on the difference signal | 0.9 % | 4.5 % | 17 %  | 50 %  | 88 %  | 98 % | 100 % | 100 % | 100 % |

- **80 % detection at a step of 0.038 NDTI** (interpolated; 0.04 is the first grid step to
  reach it). That is about 1.1 times the downstream signal's robust σ (0.036).
- **The false-positive rate on the uninjected copy is 0.9 %** (1 / 112, the 2020-08-26 scene).
- Detection hardly differs between seasons or glint classes.
- **Almost all of this power comes from the difference signal.** A step added downstream only, with
  upstream unchanged, moves the downstream − upstream difference, whose baseline spread is small.
  - On the downstream signal alone, 80 % needs about 0.13 NDTI (interpolated between 71 % at 0.12
    and 98 % at 0.15).
  - A change that reaches both sub-reaches, such as a reach-wide rise or a plume spanning the
    sub-reach boundary, would need steps of that size to be found.
  - The downstream series itself swings by about 0.14 over the period
    ([figure](results/figures/magdalena-puerto-wilches_series.png)).

**The demo event (SYNTHETIC), fixed by the pre-registered rule:**

| Date       | Step       | Downstream NDTI, real → overlay | Largest abs. z, real → overlay | Detected | Eligible scenes | Events avoided |
| ---------- | ---------- | ------------------------------- | ------------------------------ | -------- | --------------- | -------------- |
| 2022-03-09 | +0.08 NDTI | 0.015 → 0.095                   | −0.81 → 7.61                   | yes      | 12              | 11             |

- **Magnitude:** 2 × 0.0378, rounded up to 0.01.
- **Date:** one seeded draw among the 12 scenes that met every condition: clear, usable,
  not anomalous, glint share ≤ 0.2 (this scene: 0.107), and at least 30 days from the 2 catalogued
  and 9 post-hoc events.
- **What the demo shows:** it is detected through the difference signal. Its overlay value (0.095)
  is inside the range of real downstream values. The demo should therefore show the difference
  signal, not just the downstream series
  ([figure](results/figures/demo_event_synthetic.png)).
- **Separation from the real series:** the event lives only in the case file's
  `synthetic_overlay`, with `synthetic: true`, its magnitude and its label. The case file's real
  scenes do not include it.
- **2022 dredging dates were not found** ([regulatory.md](regulatory.md#unverified)). The rule
  cannot keep away from a campaign nobody dated, so the label "SYNTHETIC [...] not observed"
  carries this weight.

## Checks

- **Reproduction against the screening (2022-2025):** 24 of 24 checks pass (item-id hashes,
  geometry, per-scene NDTI to 4 decimals).
- **Reproduction against the Urrá validation:** this run's per-scene table equals the Urrá
  validation's for both reaches: 119 target and 103 control rows, NDTI, D0 status, D0 flags and
  exclusions, 0 differing cells. Checked by script, as pre-registered.
- **Read errors:** 0.
- **Anonymity:** no forbidden name appears outside the case file's context
  (`case_names_outside_context: []` in the manifest).
- **Placebo (report-only):** no D0 anomaly escapes the rain flags, and no criterion-(a) episode
  exists (observed 0 and 0, p = 1.0). It has nothing to test here.
- **Event test:** neither catalogued event has day or week precision, so none is scored.
- **Hold-out view:** 1 of 51 scored scenes in 2018-12..2021-12; 0 of 61 in 2022-2025.
- **Whole-period geometry (report-only):** the sub-reach overlap with the frozen geometry is 0.70
  (upstream) and 0.79 (downstream). The braided channel moves between periods. For the control,
  which uses MNDWI masks, the overlap is 0.005 and 0.26.

## Caveats

- **NDTI is relative and never NTU.** No number here converts it, and none should be read as a
  concentration.
- **Braided reach.** Islands and side arms fall inside the 600 m corridor. The 150 m alternative
  changes the reading (B3), and the masks from the whole period overlap the frozen ones by only
  70-79 %. Dredged material is placed "on bars and secondary channels" (2021 tender), that is,
  inside such arms.
- **Large-catchment rain proxy.** The catchment is 118,573 km² (922 HydroBASINS basins), sampled at
  10 points 1° apart, and its flow is regulated upstream: the Sogamoso dam, and Betania and El
  Quimbo on the upper river. The catchment rule flags 25.8 % of days, so "not rain-coincident" means
  little here.
- **Possible saturation.** Turbidity at the stations was 190-1,400 NTU, and NDTI hardly follows red
  reflectance within either half of its range.
- **Clear-sky bias.** Clear scenes are rarer in the rainy months (17.6 % of acquisitions) than in
  the dry months (26.4 %), so the series under-samples high-water periods.
- **In-situ distances and dependence.** The primary stations are 7-8 km from the midpoint and the
  secondary ones about 40 km. Several samples pair with the same scene. Levels cover only
  2019-01..2020-03 (San Pablo) and 2024-10..2025-12 (Puerto Wilches).
- **Not blind.** The target's and control's frozen-geometry numbers were seen before the criterion
  was set. The 10 % cap was chosen after a seen 0.9 % (upper 4.9 %) and 5.4 % (B3).

## What I could not verify

- The 2024-2026 contract's technical annex, environmental obligations and PAGA, and whether they
  name crossings inside the reach (SECOP II reCAPTCHA).
- Any regional-authority (CAS, CSB) permit or follow-up act for dredging at this reach.
- Cormagdalena's 2013 environmental management plan for maintenance dredging.
- Where the 2020 "Cantagallo" dredging sector lies. Whether any dredging happened inside the reach
  on any specific date from 2018 to 2025, including near 2020-08-26 or 2022-03-09.
- The dates of the 2022 dredging campaign, if any; the 2018 and 2021 campaigns' exact dates.
- Where the Sogamoso's mouth lies relative to the reach.
- Whether NDTI responds to turbidity here at all: the in-situ pairs are too few.

## Logistics notes (no value was changed)

- **Smoke run.** The first smoke run (2026-10-08) lost DNS resolution of the imagery host from
  13:12 to 15:35 local time (3,276 failed reads) and was stopped. As the deviation protocol says,
  it was rerun unchanged: 22 of 22 checks passed, 0 read errors. The band cache keeps only
  successful reads.
- **Local runs.** The runs ran on the developer's machine (stated in [method.md](method.md#runs)).
  The rain grid was built from the same HydroBASINS archive as the Urrá grid (SHA-256 `50afa9de…`).
- **Two tooling changes before the full run, neither touching a method value:**
  - `fetch-docs --timeout`, for a slow open-data query;
  - the post-hoc events' SHA-256 in the run manifest (`4979d9b9…`).
- **Figure.** On the in-situ figure, the log-scale tick labels of the left panel overlap; the
  values are in `insitu_pairs.csv`.
