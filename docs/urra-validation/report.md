# Urrá validation report

**Status:** full run of 2026-10-08, Actions run
[37797380051](https://github.com/saulo1112/Climate_Change_IEEE/actions/runs/37797380051) at
commit `f8cc1ce`, outputs in [results/](results/results.md) (committed by the workflow in
`0a45235`). The method was pre-registered in [method.md](method.md) (git blob `583ee4fe`, last
changed in `63254a3`) before any NDTI of this validation was computed, and it has not changed
since.

> NDTI is a relative index: comparable only within one sub-reach, never between sites, never NTU.
> An anomaly is a departure from the sub-reach's own baseline. It is a flag to investigate, never
> evidence that any actor caused anything.

## Result

**No robust signal.** The anomalies the screening found below Urrá I do not persist across
reasonable changes of the assumptions, away from rain, more often than at the control.

- **Criterion (a) is not met.** There are 2 episodes, where 4 were needed.
- **Criterion (b) is not met.** The share ratio is 2.43, where 3 was needed.
- **The placebo does not separate the real series from shuffles** (p = 0.944 and 0.888).
- **The regulatory verdict is (b)** ([regulatory.md](regulatory.md)). The licensee is verified, but
  no licence condition is a limit the observation can be compared with.
- **Consequence for the demo.** Decision D13 left the fallback to a person. On 2026-10-08 the
  project owner decided that the demo reach becomes the Río Magdalena at Puerto Wilches
  (`magdalena-puerto-wilches`), with a clearly labeled synthetic test event. Urrá is not used as the
  demo reach. That choice is recorded and validated separately (decision record and
  `docs/magdalena-validation/`); this report does not make it.

| Check                                          | Result                                                                                                                              |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Mechanical verdict (from `results/results.md`) | **no robust signal**: (a) 2 episodes (needed: at least 4); (b) 7/49 = 0.1429 against 3/51 = 0.0588, ratio 2.43 (needed: at least 3) |
| Regulatory verdict                             | **(b)**: licensee verified, no comparable limit; any permit in the demo is simulated                                                |
| Hand recomputation from `results/scenes.csv`   | D0 shares 7/49 and 3/51; ratio 2.43; candidate scenes 2019-02-11, 2024-01-16, 2024-02-10; 2 episodes. Same verdict                  |

## Criteria (pre-registered)

- **(a)** At least 4 episodes of target scenes that are anomalous in at least 8 of the 10
  variants and not rain-coincident under the union rule. Scenes 30 days apart or less merge.
- **(b)** The target's D0 anomalous-scene share is at least 3 times the control's
  (`meta-orocue`), over 2018-12-01 to 2025-12-31.
- Both hold: "candidate signal". Otherwise "no robust signal".

## The target's anomalous scenes

Every scene anomalous under D0, or in at least 8 variants. Persistence counts the 10 variants;
"distinct" counts B2, B3, Z3.5, G1 and G2. Rain is the union rule (point or catchment).

| Date       | Period    | Signal     | Persistence | Distinct | Rain (point / catchment / union) | Largest glint share | Criterion (a) |
| ---------- | --------- | ---------- | ----------: | -------: | -------------------------------- | ------------------: | ------------- |
| 2019-02-11 | hold-out  | difference |           9 |        4 | no / no / no                     |               0.669 | candidate     |
| 2019-10-29 | hold-out  | difference |           9 |        4 | yes / yes / yes                  |               0.169 | rain          |
| 2020-10-28 | hold-out  | downstream |           5 |        0 | no / yes / yes                   |               0.156 | -             |
| 2020-12-02 | hold-out  | downstream |           5 |        0 | yes / no / yes                   |               0.302 | -             |
| 2024-01-16 | 2022-2025 | difference |           8 |        3 | no / no / no                     |               0.758 | candidate     |
| 2024-02-10 | 2022-2025 | difference |          10 |        5 | no / no / no                     |               0.222 | candidate     |
| 2025-12-16 | 2022-2025 | downstream |           5 |        0 | no / no / no                     |               0.208 | -             |

**Episodes:** 2019-02-11 (1 scene), and 2024-01-16 to 2024-02-10 (2 scenes).

**The screening's anomalies, against this run.** Of its seven anomalous scenes, four are no
longer anomalous under D0:

- 2022-12-07 (the screening's single event hit), now at most |z| = 2.6;
- 2023-12-02, now at most 2.38;
- 2024-02-25, now 2.91 on the difference;
- 2025-11-06, now 2.98 downstream.

2025-12-16 is still anomalous under D0, but in 5 variants only. The baselines grew from a median of
15 to 34 values per signal (table below).

## Variants

| Reach     | Variant | Distinct | Scored | Insufficient | Removed (G2) | Anomalous | Share | Anomalous in D0 and the variant | D0 only | Variant only |
| --------- | ------- | -------- | -----: | -----------: | -----------: | --------: | ----: | ------------------------------: | ------: | -----------: |
| Urrá      | D0      | no       |     49 |            0 |            0 |         7 | 0.143 |                               7 |       0 |            0 |
| Urrá      | B1      | no       |     49 |            0 |            0 |         7 | 0.143 |                               7 |       0 |            0 |
| Urrá      | B2      | yes      |     36 |           13 |            0 |         3 | 0.083 |                               3 |       4 |            0 |
| Urrá      | B3      | yes      |     31 |           18 |            0 |         6 | 0.194 |                               4 |       3 |            2 |
| Urrá      | B4      | no       |     49 |            0 |            0 |         7 | 0.143 |                               7 |       0 |            0 |
| Urrá      | B5      | no       |     49 |            0 |            0 |         7 | 0.143 |                               7 |       0 |            0 |
| Urrá      | Z2.5    | no       |     49 |            0 |            0 |        12 | 0.245 |                               7 |       0 |            5 |
| Urrá      | Z3.5    | yes      |     49 |            0 |            0 |         4 | 0.082 |                               4 |       3 |            0 |
| Urrá      | G1      | yes      |     36 |            0 |            0 |         3 | 0.083 |                               3 |       4 |            0 |
| Urrá      | G2      | yes      |     37 |            0 |           12 |         2 | 0.054 |                               2 |       5 |            0 |
| Control   | D0      | no       |     51 |            0 |            0 |         3 | 0.059 |                               3 |       0 |            0 |
| Control   | B2      | yes      |     40 |           11 |            0 |         3 | 0.075 |                               1 |       2 |            2 |
| Control   | B3      | yes      |     37 |           14 |            0 |         2 | 0.054 |                               1 |       2 |            1 |
| Control   | Z3.5    | yes      |     51 |            0 |            0 |         1 | 0.020 |                               1 |       2 |            0 |
| Control   | G1      | yes      |     41 |            0 |            0 |         2 | 0.049 |                               2 |       1 |            0 |
| Control   | G2      | yes      |     37 |            0 |           14 |         2 | 0.054 |                               1 |       2 |            1 |
| Reference | D0      | no       |    112 |            0 |            0 |         1 | 0.009 |                               1 |       0 |            0 |
| Reference | B3      | yes      |    112 |            0 |            0 |         6 | 0.054 |                               1 |       0 |            5 |
| Reference | G2      | yes      |    106 |            0 |            6 |         0 |     0 |                               0 |       1 |            0 |

The control's and the reference's other variants are in [variants.csv](results/variants.csv). The
control is `meta-orocue` and the reference `magdalena-puerto-wilches`.

**Anomalous scenes per signal (Urrá):** under D0, 0 upstream, 3 downstream and 4 on the difference.
Under B2, G1 and G2, no downstream anomaly is left; only difference anomalies remain
([signal_split.csv](results/signal_split.csv)).

## Placebo, chance level and hold-out

- **Placebo (1000 within-season shuffles, seed 20261007):**
  - S1, D0 anomalies that are not rain-coincident: observed 4, p = 0.944.
  - S2, criterion-(a) episodes: observed 2, p = 0.888.
  - S1 only measures how anomalies pair with dry dates (method.md); S2 recomputes every variant.
- **Chance level (binomial, report-only).** At the control's D0 share p = 0.0588 and n = 49 scored
  target scenes:
  - P(X ≥ 4) = 0.326;
  - P(X ≥ 3), for the observed 3 candidate scenes, = 0.556.

**Hold-out view (never seen before this run):**

| Reach     | Part                      | Scenes | Scored (D0) | Anomalous (D0) | Persistent | Candidates | Episodes |
| --------- | ------------------------- | -----: | ----------: | -------------: | ---------: | ---------: | -------: |
| Urrá      | hold-out 2018-12..2021-12 |     24 |          23 |              4 |          2 |          1 |        1 |
| Urrá      | 2022-2025                 |     31 |          26 |              3 |          2 |          2 |        1 |
| Control   | hold-out 2018-12..2021-12 |     42 |          10 |              0 |          0 |          0 |        0 |
| Control   | 2022-2025                 |     61 |          41 |              3 |          1 |          1 |        1 |
| Reference | hold-out 2018-12..2021-12 |     54 |          51 |              1 |          1 |          0 |        0 |
| Reference | 2022-2025                 |     65 |          61 |              0 |          0 |          0 |        0 |

The control's hold-out has few scored scenes: 42 observable, 10 scored. Its B11 water check
excluded many dry-season scenes for glint (table below).

## Seasonality and the January-February scenes

**Same time of year in other years (±15 days, D0 values):**

| Date       | Signal     |   NDTI | z (D0) | Other years: n |  Median |     Min |     Max |
| ---------- | ---------- | -----: | -----: | -------------: | ------: | ------: | ------: |
| 2019-02-11 | difference | 0.0454 |   5.23 |              9 | -0.0091 | -0.0187 |  0.0474 |
| 2019-10-29 | difference | 0.0305 |   3.74 |              3 | -0.0020 | -0.0086 | -0.0016 |
| 2020-10-28 | downstream | 0.0288 |   3.25 |              3 |  0.0122 | -0.0500 |  0.0131 |
| 2020-12-02 | downstream | 0.0223 |   3.14 |              9 | -0.0363 | -0.1892 |  0.0186 |
| 2024-01-16 | difference | 0.0314 |   3.83 |              3 | -0.0113 | -0.0172 | -0.0059 |
| 2024-02-10 | difference | 0.0474 |   5.44 |              9 | -0.0091 | -0.0187 |  0.0454 |
| 2025-12-16 | downstream | 0.0186 |   3.08 |              9 | -0.0546 | -0.1892 |  0.0223 |

The two largest difference values of early February, 0.0454 (2019-02-11) and 0.0474 (2024-02-10),
are each the largest value the other finds at the same time of year in other years: the same
high difference appears in early February of two years, five years apart.

**Every January and February scene** ([january_february.csv](results/january_february.csv)):

- 18 scenes, of which 3 are anomalous under D0, B2 and B3 alike: 2019-02-11, 2024-01-16 and
  2024-02-10.
- 9 of the 18 have a largest glint share above 0.5, including 2 of the 3 anomalies (0.669 and
  0.758).
- 2024-02-25, anomalous in the screening, is now at z = 2.91.

## Event test (report-only)

| Event          | Date       | Outcome under D0 | Largest \|z\| | Persistent scene in window | Chance rate |
| -------------- | ---------- | ---------------- | ------------: | -------------------------- | ----------: |
| `sinu-urra-01` | 2022-11-28 | miss             |           2.6 | no                         |       0.098 |
| `sinu-urra-02` | 2025-07-12 | miss             |          1.16 | no                         |       0.099 |
| `sinu-urra-03` | 2025-08-01 | unobservable     |               | no                         |       0.099 |
| `sinu-urra-04` | 2025-11-29 | unobservable     |               | no                         |       0.099 |
| `sinu-urra-05` | 2022-08-14 | unobservable     |               | no                         |       0.103 |
| `sinu-urra-06` | 2025-07-21 | unobservable     |               | no                         |       0.103 |

With the longer baselines, the screening's single hit (`sinu-urra-01`) becomes a miss.

## Rain

- **Catchment grid:** 6 points at 0.25° in 36 HydroBASINS level-12 basins (4,909 km²). The points
  fall in 6 distinct Open-Meteo cells.
- **Thresholds** (90th percentile of 2,588 daily values):

  | Statistic | 24 h    | 72 h     | 168 h    |
  | --------- | ------- | -------- | -------- |
  | max       | 44.2 mm | 115.6 mm | 237.2 mm |
  | mean      | 21.7 mm | 58.4 mm  | 127.1 mm |

- **How much the rule flags:** 24.5 % of days, and 23 of the 55 target scenes under the union rule
  (32 not flagged, no scene unknown).
- **CHIRPS** (report-only): its 3-day catchment mean against Open-Meteo's 72-hour mean, at each
  D0 anomaly.

  | Date       | CHIRPS 3 days | Open-Meteo 72 h |
  | ---------- | ------------: | --------------: |
  | 2019-02-11 |        0.0 mm |          6.4 mm |
  | 2019-10-29 |       52.4 mm |         56.3 mm |
  | 2020-10-28 |       21.2 mm |         16.5 mm |
  | 2020-12-02 |       99.3 mm |         45.2 mm |
  | 2024-01-16 |        0.0 mm |          9.6 mm |
  | 2024-02-10 |        9.5 mm |         22.5 mm |
  | 2025-12-16 |        4.8 mm |         42.0 mm |

  The two sources agree that 2019-02-11 and 2024-01-16 were dry. They disagree in size elsewhere.

## Reproduction checks (2022-2025)

**36 of 36 pass.**

- The STAC item ids of 2022-2025 hash to the screening's values at all three reaches:
  - Urrá `678e6ef8…`;
  - control `16548143…`;
  - reference `8bff3e8c…`.
- Every geometry field equals the screening's post-hoc `stage1_summary.csv`: mask source,
  threshold, reach length, separation, anchor shifts, width and centerline midpoint.
- NDTI (upstream, downstream, difference) matches the screening's post-hoc `stage2_scenes.csv` to 4
  decimals for all 157 scenes (31 + 61 + 65), with the same scenes excluded.

## Other tables

- **Baseline sizes (Urrá, D0, median values in the baseline group):**
  - upstream and downstream: 15 in the screening, 34 here;
  - difference: 15 in the screening, 33 here.
- **Rainy months:** the rule applied to the whole period gives the frozen months at all three
  reaches (Urrá April-September).
- **B11 water check, scenes excluded:**
  - Urrá: 4 (glint or a missing offset) and 2 (offset applied twice?) across 2021-2025;
  - control: 49 (glint or a missing offset) and 3 (offset applied twice?);
  - reference: 3 and 3 ([b11_exclusions.csv](results/b11_exclusions.csv)).
- **Read errors:** none.
- **Median NDTI by processing-baseline family at Urrá:**

  | Family            | Usable scenes | Upstream | Downstream | Difference |
  | ----------------- | ------------: | -------: | ---------: | ---------: |
  | 00.xx (2018)      |             2 |  -0.0418 |    -0.0455 |    -0.0037 |
  | 02.xx (2018-2019) |             5 |  -0.1789 |    -0.1855 |    -0.0069 |
  | 04.xx (2022)      |             4 |   0.0161 |     0.0103 |    -0.0059 |
  | 05.xx             |            38 |  -0.0836 |    -0.0797 |    -0.0040 |

  The families cover different seasons and years, so their level medians are not comparable. The
  difference signal varies little between them (-0.004 to -0.007).

- **Whole-period geometry check** (sub-reach overlap with the frozen geometry, intersection over
  union):

  | Reach     | Upstream | Downstream |
  | --------- | -------: | ---------: |
  | Urrá      |     0.98 |       0.52 |
  | Control   |    0.005 |       0.26 |
  | Reference |     0.70 |       0.79 |

  A water mask built from 2018-2025 would place several sub-reaches elsewhere, especially at the
  braided control. The frozen 2022-2025 geometry was used, as pre-registered.

## Caveats

- **Processing chain.** The archive mixes baseline families: 00.xx and 02.xx in 2018-2019, the
  reprocessed 05.00 in 2019-2021, and 04.xx and 05.xx from 2022. Offsets were handled per item and
  checked on water B11, but a residual step between families cannot be excluded on level signals.
- **Glint.** Both remaining episodes are difference anomalies in January or February. Two of their
  three scenes had more than half of the water pixels above the glint limit. G2, which drops such
  scenes, keeps 2 of 7 D0 anomalies.
- **Reservoir regulation.** The licence sets a monthly discharge band (regulatory.md, C4). No public
  archive of discharges was found, so the flow at each scene is unknown.
- **Rain-driven catalog events.** Every catalog event is an inflow or alert episode driven by rain,
  and the event dates come from search-result summaries (screening caveat). None was hit here.
- **Clear-sky bias.** Clear scenes are rarer on wet days, so wet conditions are under-sampled.
- **Geometry.** The frozen geometry reproduces the screening exactly. The whole-period check shows
  that the mask, and with it the sub-reach positions, depends on the period used.
- **Figure.** In [sinu-urra_series.png](results/figures/sinu-urra_series.png) the legend overlaps the
  data near late 2020. The red dot there belongs to the legend, not to a scene. The figure is kept
  as the run produced it.
- **NDTI is relative**, never NTU, and no in-situ data exist for the reach (regulatory.md).

## Deviations from the plan (logistics only; the method did not change)

- **Regulatory fetch.** The documents were fetched on the developer's machine, which reaches the
  sources, so the planned `regulatory-docs` workflow was not created.
- **Catchment grid.** The grid run in Actions
  ([37732708699](https://github.com/saulo1112/Climate_Change_IEEE/actions/runs/37732708699)) got
  HTTP 403 from `data.hydrosheds.org`.
  - The grid was built locally with the same command at commit `a9a3ccf`. It was committed by the
    project owner in `2421310`, not by the workflow.
  - The HydroBASINS archive's SHA-256 (`50afa9de…`) is recorded in every row.
  - An earlier local build gave the same file.
- **Smoke run.** The smoke run
  ([37733457260](https://github.com/saulo1112/Climate_Change_IEEE/actions/runs/37733457260)) was
  read from its log; its outputs are not committed. All 33 of its checks passed.
- **Full run.** It was started by an empty commit (`f8cc1ce`) carrying the run tag.

## What I could not verify

- Everything listed under UNVERIFIED in [regulatory.md](regulatory.md#unverified), notably:
  - the 2010 resolutions behind the discharge band;
  - the operator's turbidity monitoring at Angostura and Pasacaballos;
  - an archive of hourly discharges.
- **The flow at each anomalous scene**, and so whether the January-February difference pattern
  coincides with any operation. No source dates an operation then, and nothing here says what
  produced the pattern.
- **Whether the operator's Pasacaballos station lies inside the downstream sub-reach.**
- **The meaning of the processing-baseline families' level differences.** They are confounded with
  season and year.

## Files

- Generated: [results/results.md](results/results.md), every CSV in [results/](results/), the
  figures in [results/figures/](results/figures/), and [urra.sample.json](urra.sample.json). The
  sample (119,184 bytes) is byte-identical to the run's `pipeline/out/case/urra.json`, SHA-256
  `fd414485…`.
- Method: [method.md](method.md). Regulatory verification: [regulatory.md](regulatory.md). Grid:
  [rain-grid.csv](rain-grid.csv).
