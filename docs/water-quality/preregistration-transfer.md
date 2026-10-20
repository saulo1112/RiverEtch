# Preregistration: turbidity on rivers the model never saw (written 2026-10-20 UTC, before it ran)

This file fixes, before any of it is run, a test of how far off a turbidity model is on a river it
was never trained on, and the rule an ungauged reach follows. Its SHA-256 is a line of
`docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum Sepolia
(`terrachain:riveretch:frozen-artifacts`). The test runs **once**, after that anchor is mined. It
is never edited: a change is a new file with its own line and anchor.

Nothing here edits `preregistration.md`, the model cards or the results' MANIFEST.

## 1. Why, and what is already known

- RiverEtch is meant for rivers without a gauge. There, nobody can score a value later, so the
  error that matters is the error on a river the model never saw.
- **Already known (disclosure):**
  - v5 scored each river's lock box once with its site model (`results/v5_levels.csv`).
  - v5 also scored, report-only, models pretrained on the USGS pilot "without the site's river
    group", with no site adjustment (`results/results.md`, rows "H2–H4 without the site
    adjustment (other rivers only)"). H4 there beat the river's own median on 7 of 10 rivers and
    failed badly on the clear, tidal ones (Connecticut, Willamette); at Hermann, A4 erred by 30.4 %
    against 87.7 % for the median.
  - **This design was chosen after seeing those results.** The pilot holds only four of the study's
    river groups (Mississippi, Missouri, Ohio, Platte). This test trains on all nine groups of the
    v5 study, clear and tidal rivers included, which no model has done before.
  - While writing this file, the usable pairs per site and period, and each site's median turbidity
    over the training years, were counted (section 4). No model of this design had been trained or
    scored.

## 2. Data

- **Pairs:** the v5 turbidity pairs (`docs/water-quality/inputs/usgs-v5/`), core window, feature
  set F (`pipeline/water-quality.yaml`, `features`), exactly as v5 builds them
  (`quality/gauged.py`, `pairs_by_source`). No new river, gauge or scene.
- **Periods:** training years 2018-12-01..2023-11-30; lock box 2023-12-01..2026-09-30
  (`quality/site.py`, `split`).
- **Groups** (the `river` column of `inputs/usgs-v5/sites.csv`):

  | Group       | Sites                                                        |
  | ----------- | ------------------------------------------------------------ |
  | ATCHAFALAYA | USGS-07381600                                                |
  | COLUMBIA    | USGS-14144700 (Vancouver), USGS-14246900 (Port Westward)     |
  | CONNECTICUT | USGS-01193050                                                |
  | MISSISSIPPI | USGS-07020850 (Cape Girardeau), USGS-07374525 (Belle Chasse) |
  | MISSOURI    | USGS-06934500 (Hermann)                                      |
  | OHIO        | USGS-03216070                                                |
  | PLATTE      | USGS-06805500                                                |
  | SAN JOAQUIN | USGS-11337190                                                |
  | WILLAMETTE  | USGS-14211720                                                |

## 3. The test

- **Leave one river group out.** For each group G, a model is trained on the training-year pairs of
  every other group, and scored on G's lock-box pairs. **No pair from any lock-box year is used in
  training**, for any group, and no pair of G at all.
- **Model (fixed, no tuning beyond its own inner rule):** A4, LightGBM on F (`pipeline/lab/train_gbm.py`):
  the configuration with the lowest inner leave-one-group-out MdSA over the grid
  `num_leaves` [7, 15, 31] × `min_data_in_leaf` [20, 50] × `n_estimators` [200, 500], learning
  rate 0.05, one thread, seed 20261010; ties to the smaller model; then fitted on every training
  pair of the fold. **No site adjustment.**
- **Report-only:** A3, ridge in log space on F, λ from [0.01, 0.1, 1, 10, 100] by inner
  leave-one-group-out, no site adjustment.
- **Interval (90 %):** the estimate ×/÷ q, where q is the 90th percentile of the absolute log
  residuals of the chosen configuration's inner leave-one-group-out estimates on the fold's
  training pairs.
- **Metrics** (`quality/route_a.py`, `evaluate`, as the levels compute them): n, MdSA, SSPB, 90 %
  coverage, Spearman ρ with its 95 % interval (block bootstrap over scenes, 10,000 resamples,
  seed 20261010).
- **Baselines:**
  - **(a) the river's own usual value:** the median of G's training values. It uses local data, so
    it is a reference, not something an ungauged river has.
  - **(b) no local data:** the median of the other groups' training values.
- **Scored sites:** every site with at least 20 lock-box pairs (Port Westward, with 1, trains but is
  not scored). Each site is scored on its own; Mississippi's two sites share one model.
- **Levels** (basis `transfer`): the v5 thresholds (`preregistration.md`, _Levels (every v5
  evaluation)_), with baseline (a) as H0.
- **Report-only sensitivity:** the same test with the two hydrologically joined pairs held out
  together: {MISSISSIPPI, ATCHAFALAYA} (the Atchafalaya takes part of the Mississippi's flow) and
  {COLUMBIA, WILLAMETTE} (the Willamette joins the Columbia at Portland).
- **Run once.** Every scored site is reported, the failures included, with both baselines.

## 4. Rivers like an ungauged reach would be

- **"Similar rivers"** are the scored sites whose median turbidity over the training years is at
  least 20 FNU: sediment-carrying main stems. From the counts made while writing (no model involved):

  | Site                 | Training pairs | Lock-box pairs | Training median (FNU) | Similar |
  | -------------------- | -------------- | -------------- | --------------------- | ------- |
  | Atchafalaya 07381600 | 78             | 43             | 45.0                  | yes     |
  | Mississippi 07020850 | 123            | 74             | 51.2                  | yes     |
  | Mississippi 07374525 | 179            | 57             | 38.4                  | yes     |
  | Missouri 06934500    | 127            | 70             | 48.8                  | yes     |
  | Platte 06805500      | 94             | 54             | 55.8                  | yes     |
  | Ohio 03216070        | 218            | 122            | 10.5                  | no      |
  | Columbia 14144700    | 235            | 48             | 3.4                   | no      |
  | San Joaquin 11337190 | 241            | 53             | 5.8                   | no      |
  | Connecticut 01193050 | 139            | 56             | 2.8                   | no      |
  | Willamette 14211720  | 238            | 136            | 2.4                   | no      |

- **Pooled result:** the similar sites' lock-box pairs, each estimated by the model that never saw
  its group: MdSA, SSPB, Spearman ρ with its 95 % lower bound, and the **class agreement**: how
  many pairs fall in the same class as the gauge (classes in FNU: under 30, 30 to 100, 100 and
  over), as a count.

## 5. The ungauged reach (what it may show)

- **Its model:** A4 trained the same way on the training-year pairs of all nine groups. Its card's
  SHA-256 is named by every record, as for the other reaches.
- **Its reach:** a wide, sediment-carrying US river reach with no USGS turbidity gauge (63680) on it,
  chosen by the owner from candidates after the test.
- **What it shows, fixed here:**
  - **a class** (under 30, 30 to 100, 100 and over FNU), never a value with a unit, and only if the
    pooled similar-river result reaches at least _indicative_ (ρ's 95 % lower bound above 0.3);
  - beside it, the expected error from section 4: the pooled MdSA, the bias and the class agreement
    ("in k of n test passes on rivers it never saw, the class matched the gauge");
  - the label **"unvalidated: expected error from the transfer test"**;
  - if the pooled result does not reach _indicative_, the reach shows the relative NDTI map only.
- An ungauged reach has no gauge, so it is never scored and never earns a level of its own.

## 6. Outputs

- Results: `docs/water-quality/results/transfer/` with their own MANIFEST (the v5 MANIFEST is not
  touched), recomputable from the committed inputs and the trained models
  (`docs/water-quality/inputs/lab/transfer/`).
- A report section and a web view, "Rivers it never saw", listing every scored site.
