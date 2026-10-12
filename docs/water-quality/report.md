# Water quality from Sentinel-2: what the satellite can and cannot say (v2–v5)

This report gathers every round of the water-quality validation (decisions D16, D17 and D18), with
the error that counts for each, how many attempts each round made, and what the product publishes
because of it. The rules are in the [preregistration](preregistration.md); every number below is
recomputed from committed snapshots by `climate-pipeline quality run`
([results](results/results.md), [summary](results/summary.json)) and checked byte for byte in CI
by `quality verify`.

> Every published error is out of sample: leave-one-station-out (LOSO), leave-one-river-out (LORO),
> leave-one-year-out or a locked test. An in-sample fit is never shown as an error. A choice made
> after seeing results is labelled exploratory. No output states that any actor caused anything.

## The headline (v5): turbidity where a gauge measures it

Ten gauged rivers met fixed data criteria (continuous, approved turbidity since 2017 or earlier; a
main channel ≥ 300 m; not at a dam), written before any of their values was read. Each was
validated with the same protocol: models trained on the hydrological years 2019–2023 (and, for the
pretrained ones, on other rivers only), selected inside those years, then scored **once** on a lock
box, 2023-12..2026-09, that nothing had seen.

| River (USGS gauge)                         | Lock-box MdSA | Pairs | Median (null) | 90 % coverage | Interval ×/÷ | Level             |
| ------------------------------------------ | ------------- | ----- | ------------- | ------------- | ------------ | ----------------- |
| **Mississippi at Belle Chasse (07374525)** | **17.8 %**    | 57    | 113.7 %       | 94.7 %        | 1.48         | validated         |
| **Platte at Louisville (06805500)**        | **20.3 %**    | 54    | 66.9 %        | 92.5 %        | 1.66         | validated         |
| Atchafalaya at Morgan City (07381600)      | 23.4 %        | 43    | 75.2 %        | 88.3 %        | 1.72         | validated         |
| Ohio at Ironton (03216070)                 | 28.2 %        | 122   | 149.4 %       | 88.5 %        | 2.58         | estimated         |
| Mississippi at Cape Girardeau (07020850)   | 33.1 %        | 74    | 71.4 %        | 89.1 %        | 2.69         | estimated         |
| San Joaquin at Jersey Point (11337190)     | 40.6 %        | 53    | 46.2 %        | 94.3 %        | 2.21         | estimated         |
| Connecticut at Middle Haddam (01193050)    | 38.0 %        | 56    | 31.8 %        | 92.8 %        | 2.23         | none              |
| Willamette at Portland (14211720)          | 52.2 %        | 136   | 64.9 %        | 77.2 %        | 2.50         | indicative        |
| Columbia at Vancouver (14144700)           | 53.6 %        | 48    | 47.4 %        | 89.5 %        | 2.17         | none              |
| Columbia at Port Westward (14246900)       | —             | 1     | —             | —             | —            | insufficient data |

- **The two demo reaches follow the preregistered rule** (the highest level, then the lowest
  error): the Mississippi at Belle Chasse and the Platte at Louisville. Their records show
  turbidity in FNU with a 90 % interval.
- **They are the best two of ten,** so as a pair they flatter the method. The honest summary is the
  median over the nine rivers evaluated: **33.1 %**. Rivers carrying sediment (the lower
  Mississippi, the Platte, the Atchafalaya) do best; clear, tidal rivers (the Columbia, the
  Connecticut) do worst, where the median of past values is already close.
- **Suspended solids:** no river had 20 locked-test pairs. Discrete SSC samples give 4–6 a site in
  2023-12..2026-09, and the USGS surrogate SSC (estimated from turbidity) has no approved value in
  that period. No SSC value is published.
- v5 replaced v4's 97 % coverage ceiling with a cap on the interval's width, decided after Hermann
  and applied only to new evaluations. Under it Hermann would still be _indicative_ (its interval
  is ×/÷ 3.65).

## Earlier rounds (v2–v4)

| Reach                                           | Target, unit   | Validation that counts                                                            | Error (MdSA) | n   | Level      | What a record shows                |
| ----------------------------------------------- | -------------- | --------------------------------------------------------------------------------- | ------------ | --- | ---------- | ---------------------------------- |
| Missouri at Hermann (USGS 06934500)             | turbidity, FNU | locked test 2023-12..2026-09, evaluated once (preregistered)                      | **34.9 %**   | 70  | indicative | a relative class (low/medium/high) |
| Magdalena, Puerto Wilches–San Pablo (San Pablo) | turbidity, NTU | v3 round 1 of record: nested LOSO over 11 stations (post hoc)                     | 63.1 %       | 31  | none       | the relative indices only          |
| Magdalena (same)                                | turbidity, NTU | v4 round 3: nested leave-one-hydrological-year-out, station offsets (exploratory) | 102.8 %      | 31  | none       | (not the product)                  |
| Magdalena (same)                                | TSS, mg/L      | v2.1 nested LOSO (post hoc); RAdCor Stage A + B 148.9 % (37 pairs)                | 164.8 %      | 31  | none       | the relative indices only          |

- **Hermann reached a good error and missed a level by one interval rule.** The selected model (H3:
  a ridge on the feature set F trained on eight other US rivers, then a site adjustment) erred by
  34.9 % on 70 held-out overpasses in three years, against 87.7 % for the median. Its 90 % interval
  covered 68 of 70 values (97.1 %); the preregistered rule wants [80 %, 97 %], so intervals too wide
  by one value cap it at _indicative_. The rule is not changed after the fact.
- **The same physics transfers.** A4 (gradient-boosted trees) trained only on the other rivers,
  with no Hermann data at all, erred by 30.4 % on the same locked test. Where turbidity is measured
  continuously at the overpass, Sentinel-2 L2A carries the signal.
- **The Magdalena's limit is the data, not the model.** 184 turbidity samples since 2015 give 31
  usable units at 11 stations; San Pablo, the reach's estimate station, has 7 samples and 3 units.
  Every model class, correction and validation scheme tried lands between 63 % and 140 %.

## Two validations, two questions

- **Leave-one-station-out** asks: _how wrong is the model at a station it has never seen?_ Every
  pair of the held-out station leaves training. It is the right test for a model meant to be moved
  to new places.
- **Temporal validation at a known station** asks: _how wrong is the model at a station with a
  history, on dates it has not seen?_ That is how the product runs: a reach's estimate station is
  fixed, and records are made for new scenes. Its honest form holds out whole time blocks. IDEAM
  samples several Magdalena stations in the same campaign, so holding out one date at one station
  would leave the same campaign's samples at the neighbouring stations in training; v4 round 3 holds
  out whole hydrological years (December to November) at every station.
- **What the Magdalena showed:** the temporal question is harder there. v2.1's model erred by
  77.4 % across stations but 127 % across years; round 3, built for the temporal question with
  per-station offsets, erred by 102.8 % (forward chaining from earlier years only: 140 %). Between
  years the river, the sampling campaigns and the scene gaps change more than between stations.
- **Hermann's locked test is temporal by construction** (train 2018-12..2023-11, test
  2023-12..2026-09), which is why its 34.9 % speaks directly to how its records will behave.

## Every round, its attempts and its result

| Round                       | Question                                  | Candidates (attempts)                                              | Evaluation                             | Result that counts                               |
| --------------------------- | ----------------------------------------- | ------------------------------------------------------------------ | -------------------------------------- | ------------------------------------------------ |
| D15                         | Any band calibrates on the Magdalena?     | 8 models × 3 targets                                               | 7 hold-out pairs                       | none (baselined)                                 |
| v2, Route A (preregistered) | Transfer from other rivers                | M0, A1–A4 × 3 pair variants × 2 targets (30 test evaluations)      | LORO selection, Magdalena test once    | A3 135 % turbidity, 249 % TSS: none              |
| v2, Route B                 | Published models on ACOLITE               | Dogliotti, Nechad, MDN × L2A, DSF, RAdCor (11 rows)                | same pairs, no fit                     | best 80 % (Dogliotti on RAdCor)                  |
| v2.1 (post hoc)             | A Magdalena calibration                   | P1–P5 + M0; 3 variants, + leave-one-year-out                       | nested LOSO                            | 77.4 % turbidity, 164.8 % TSS: none              |
| Landsat 8/9 (phase 3)       | More pairs from another sensor            | L1, L2, pooled with a sensor term (26 rows)                        | LORO, test once, nested LOSO           | 85.2 % turbidity: none                           |
| v2.2 Stage A (post hoc)     | A calibration on RAdCor                   | R1–R3 + M0 × 2 targets                                             | nested LOSO                            | 80.0 % turbidity, 136.8 % TSS: none              |
| v3 round 1 (post hoc)       | An open search                            | 66 candidates, run twice (deviation 8) and once more (deviation 9) | nested LOSO, the whole space           | of record: 63.1 %, none (was 71.5 %, indicative) |
| v3 round 2 (exploratory)    | Round 1's most chosen form on unused data | 1 form, 4 checks (twice: deviation 9)                              | other rivers, years                    | not confirmed (other rivers 117.6 %)             |
| v4 round 3 (exploratory)    | A known station, forward in time          | 480 candidates; 2 sensitivities; 2 report-only rows                | nested leave-one-hydrological-year-out | 102.8 %, none                                    |
| v4 Stage B (RAdCor)         | RAdCor on every sensitivity pair          | R1–R3 + M0 × 2 targets                                             | nested LOSO                            | 115.8 % turbidity, 148.9 % TSS: none             |
| v4 Hermann (preregistered)  | A gauged river, a locked temporal test    | H0–H4 + 3 transfer-only rows                                       | year-out selection, locked test once   | H3 34.9 %, indicative                            |
| v5 (preregistered)          | Ten gauged rivers, the same locked test   | H0–H4 + 3 transfer-only rows per river and target                  | year-out selection, locked test once   | median 33.1 %; 3 validated, 3 estimated          |

Counted together since v2, the Magdalena turbidity target has met about 570 candidate models
(5 in Route A, 6 in Route B, 6 in v2.1, 4 with Landsat, 3 in v2.2, 66 in v3 round 1, 1 in round 2,
480 in round 3 and 3 in Stage B), most of them inside nested selections that pay for the choosing.
Every round's numbers are reported, including the ones that looked better before a correction
(deviation 9) and the ones chosen with hindsight (labelled so).

### v4 Stage B (RAdCor on the remaining pairs)

Eleven acquisitions of v2's sensitivity set lacked RAdCor; ten Level-1C products were downloaded
with the owner's account, one at a time, processed with ACOLITE RAdCor over the core window's L2A
pixels (all 11 scenes ok, about 10 minutes of the 6 h box) and deleted. The MDN ran on the new windows.
Stage A's pairs (D15's, 300 m window) and Stage B's (core window) were scored together; a sample
that both had kept Stage A's scene.

| Target    | Status                         | Pairs (A + B) | Nested LOSO (MdSA) | R1 as published    | Year-out folds (report-only) | Level |
| --------- | ------------------------------ | ------------- | ------------------ | ------------------ | ---------------------------- | ----- |
| TSS       | confirmatory (due under v2.2)  | 26 + 11       | 148.9 %            | 115.1 % (MDN)      | 135.8 %                      | none  |
| turbidity | exploratory (owner's addition) | 27 + 10       | 115.8 %            | 90.3 % (Dogliotti) | 140.8 %                      | none  |

With more pairs, Stage A's encouraging numbers (80 % for Dogliotti on RAdCor, 136.8 % for TSS) did
not hold: the adjacency correction does not lift the Magdalena to a level either.

## What the product publishes, and why

- **The demo reaches** (`mississippi-belle-chasse`, `platte-louisville`): NDTI and NIR/red per
  sub-reach with their D0 z-scores and the verdict, plus **turbidity in FNU with its 90 % interval**
  at the gauge's window, from the locked-test card (`preregistered_lockbox_site`, _validated_). A
  scene whose features leave the card's training range, or whose window fails the guards, abstains
  and says why.
- **Magdalena reach** (left out of the demo by the owner's choice, D18; it keeps running) (`magdalena-puerto-wilches`): NDTI and NIR/red per sub-reach with their D0
  z-scores and the verdict; no turbidity or TSS value or class. Round 3 did not reach _indicative_,
  so the preregistered rule keeps round 1's card of record, whose level is _none_. TSS stays at
  v2.1's _none_.
- **Missouri reach** (`missouri-hermann`): the same indices, plus turbidity as a relative class (the
  tercile among the gauge window's own history), never a unit, from the locked-test card
  (`preregistered_lockbox_site`, _indicative_).
- **The prospective check:** beside the sealed records, `reach run` notes each gauged reach's raw
  estimate of every new scene, and `reach check` compares the scenes acquired after the card's
  commit with the gauge's value at the overpass (provisional data, labelled). It is report-only.
- Every record is sealed (SHA-256 of its canonical JSON) and chained in an append-only ledger ready
  for anchoring.

## Data, probes and checks of v4

- **Hermann:** 243 clear Earth Search scenes 2018-12..2026-09 and 197 approved overpass values; 127
  training and 70 locked-test pairs in the core window.
- **CVC (Cauca, `d3ft-wu2b`), not suitable:** at most 20 turbidity samples per station since
  2018-12 (30 needed), no coordinates in the dataset, and every IDEAM station on that stretch is
  80–120 m wide (150 m needed) ([probe](inputs/cvc/probe.json)).
- **IDEAM prospective samples:** none yet; the dataset's latest sample at the Magdalena points is
  2025-11-10 ([count](inputs/ideam/prospective-count.json)).
- **CI:** the water-quality check had failed since the v2 merge because a card hashed a CRLF
  working copy of its model file (deviation 10); it is fixed and green.

## What would improve the estimates (research and proposals)

- **More and better matched in-situ data beats a new model.** The Magdalena's point samples meet a
  clear scene within ±3 days 31 times in ten years; a continuous turbidity probe at San Pablo (the
  USGS setup at Hermann) would give hundreds of exact matchups in a year. This is the single most
  valuable addition.
- **Clouds and shadows:** Sen2Cor's SCL is built for its atmospheric correction, not as a cloud
  product, and false clouds on bright targets were a known issue of its screening
  ([DLR, Sen2Cor status](https://elib.dlr.de/142245)). A cloud-probability mask such as
  OmniCloudMask (Sentinel-2, Landsat; trained on CloudSEN12 classes, including cloud shadow)
  ([docs](https://omnicloudmask.readthedocs.io/)) could replace or check SCL over the windows. It
  needs a deep-learning environment, kept apart like ACOLITE.
- **Glint and adjacency:** the pipeline already drops pixels with B11 > 0.05, checks the water B11
  median and uses a core window ≥ 60 m from land (adjacency was confirmed in v2). ACOLITE's SWIR
  glint correction can leave hot spots in turbid water
  ([ACOLITE forum](https://odnature.naturalsciences.be/remsem/acolite-forum/viewtopic.php?p=2111)).
  The core window is the cheap, transparent defence and stays.
- **Physical models:** Dogliotti et al. (2015) switch from red to NIR as turbidity rises and were
  validated within 12–22 % in five coastal and estuarine sites
  ([RSE 156](https://biblio.naturalsciences.be/library-1/rbins-staff-publications/dogliotti_single_2015));
  on RAdCor they gave the Magdalena's best unfitted result (80 %). Generic algorithms were mostly
  built for 0–100 FNU, and the red band saturates above about 250 FNU in a turbid estuary
  ([Frontiers in Marine Science, 2023](https://www.frontiersin.org/articles/10.3389/fmars.2023.1186441/full)),
  which is the Magdalena's usual range; the NIR branch and the SWIR bands matter there.
- **Continuous-sensor validation elsewhere:** Sentinel-2 turbidity validated against continuous
  stations reached R² 0.63–0.75 over 965 matchups in the San Francisco Estuary
  ([UC Merced](https://escholarship.org/uc/item/4hz1q8jm)), and under 35 % mean error at the USGS
  Colorado River site ([USGS](https://pubs.usgs.gov/publication/70273951)), in line with Hermann's
  34.9 %.
- **Rivers with open continuous turbidity outside the US** were searched (Rijkswaterstaat AQUALARM
  at Lobith, the Rhône sediment observatory, the Elbe, New South Wales and Queensland, ANA); none
  offers an approved, continuous, open series on a river ≥ 300 m wide that can be fetched now.

## Integrity

- Ten deviations are listed in the preregistration, each with what was seen when it was found.
  Deviation 9 (v3's flow features were standardised in code but not in the preregistration) lowered
  round 1's error and removed its level; the preregistered version is the result of record.
- The pipeline runs `quality run` in about 3.5 minutes (it was 4 before v4 added round 3, Stage B
  and Hermann) and CI recomputes everything byte for byte.
