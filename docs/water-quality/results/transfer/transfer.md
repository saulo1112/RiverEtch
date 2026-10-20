# Turbidity on rivers the model never saw (generated)

Fixed by `docs/water-quality/preregistration-transfer.md`, anchored before it ran; run once. `null_mdsa` is baseline (a), the held-out group's own median; `no_local_data_mdsa` is baseline (b), the other groups' median.

## A4, each river group held out

| site | group | n | mdsa | sspb | rho_low | null_mdsa | no_local_data_mdsa | coverage90 | interval_factor90 | class_agreement | level |
|---|---|---|---|---|---|---|---|---|---|---|---|
| USGS-07381600 | ATCHAFALAYA | 43 | 40.5 | -40.5 | 0.768 | 75.2 | 1e+03 | 0.93 | 2.52 | 32 | indicative |
| USGS-14144700 | COLUMBIA | 48 | 32.2 | 26.5 | -0.041 | 47.4 | 191 | 0.833 | 2.75 | 48 | estimated |
| USGS-01193050 | CONNECTICUT | 56 | 88.4 | 88.4 | 0.282 | 31.8 | 179 | 0.696 | 2.66 | 55 | none |
| USGS-07020850 | MISSISSIPPI | 74 | 33.8 | -0.958 | 0.524 | 72.3 | 600 | 0.959 | 2.42 | 49 | validated |
| USGS-07374525 | MISSISSIPPI | 57 | 15.4 | -6.81 | 0.881 | 113 | 618 | 0.982 | 2.42 | 53 | validated |
| USGS-06934500 | MISSOURI | 70 | 41.2 | -34.3 | 0.41 | 87.7 | 732 | 0.786 | 2.58 | 36 | indicative |
| USGS-03216070 | OHIO | 122 | 48.6 | 45.9 | 0.854 | 149 | 110 | 0.951 | 2.62 | 114 | indicative |
| USGS-06805500 | PLATTE | 54 | 162 | -162 | 0.244 | 66.9 | 729 | 0.481 | 2.57 | 15 | none |
| USGS-11337190 | SAN JOAQUIN | 53 | 33.1 | 26.1 | 0.467 | 46.2 | 85.8 | 0.981 | 2.71 | 53 | estimated |
| USGS-14211720 | WILLAMETTE | 136 | 24.4 | 9.76 | 0.666 | 64.9 | 337 | 0.963 | 3.07 | 135 | indicative |

## Similar rivers, pooled (the ungauged reach's expected error)

- Rule: training-year median at least 20 FNU; sites: USGS-06805500 (55.8 FNU), USGS-06934500 (48.8 FNU), USGS-07020850 (51.2 FNU), USGS-07374525 (38.4 FNU), USGS-07381600 (45.0 FNU)
- n = 298; MdSA 36.9 %; SSPB -22.9 %; Spearman rho 0.719 (95 % interval 0.647 to 0.781)
- Inside the 90 % interval: 248 of 298; class agreement: 185 of 298
- The ungauged reach shows: **class (under 30, 30 to 100, 100 and over FNU)** (rho's lower bound above 0.3).

## Report-only: A3 and the joined folds

| fold | site | candidate | n | mdsa | sspb | rho_low | null_mdsa | no_local_data_mdsa |
|---|---|---|---|---|---|---|---|---|
| atchafalaya | USGS-07381600 | A3 (report-only) | 43 | 124 | -124 | 0.453 | 75.2 | 1e+03 |
| columbia | USGS-14144700 | A3 (report-only) | 48 | 69.4 | 57.7 | 0.126 | 47.4 | 191 |
| connecticut | USGS-01193050 | A3 (report-only) | 56 | 85 | 64 | 0.351 | 31.8 | 179 |
| mississippi | USGS-07020850 | A3 (report-only) | 74 | 107 | -107 | 0.386 | 72.3 | 600 |
| mississippi | USGS-07374525 | A3 (report-only) | 57 | 103 | -103 | 0.821 | 113 | 618 |
| missouri | USGS-06934500 | A3 (report-only) | 70 | 147 | -140 | 0.421 | 87.7 | 732 |
| ohio | USGS-03216070 | A3 (report-only) | 122 | 64.6 | 61.6 | 0.758 | 149 | 110 |
| platte | USGS-06805500 | A3 (report-only) | 54 | 167 | -167 | 0.762 | 66.9 | 729 |
| san-joaquin | USGS-11337190 | A3 (report-only) | 53 | 38.2 | 35.3 | 0.423 | 46.2 | 85.8 |
| willamette | USGS-14211720 | A3 (report-only) | 136 | 61.7 | 33.6 | 0.482 | 64.9 | 337 |
| mississippi-atchafalaya | USGS-07020850 | A4 | 74 | 27.8 | -5.85 | 0.533 | 72.3 | 637 |
| mississippi-atchafalaya | USGS-07020850 | A3 (report-only) | 74 | 126 | -124 | 0.343 | 72.3 | 637 |
| mississippi-atchafalaya | USGS-07374525 | A4 | 57 | 24.7 | -8.08 | 0.849 | 112 | 656 |
| mississippi-atchafalaya | USGS-07374525 | A3 (report-only) | 57 | 123 | -123 | 0.784 | 112 | 656 |
| mississippi-atchafalaya | USGS-07381600 | A4 | 43 | 78.7 | -78.7 | 0.717 | 79.5 | 1.39e+03 |
| mississippi-atchafalaya | USGS-07381600 | A3 (report-only) | 43 | 195 | -195 | 0.417 | 79.5 | 1.39e+03 |
| columbia-willamette | USGS-14144700 | A4 | 48 | 43 | 20.8 | -0.211 | 53.6 | 375 |
| columbia-willamette | USGS-14144700 | A3 (report-only) | 48 | 58.9 | 38.8 | 0.021 | 53.6 | 375 |
| columbia-willamette | USGS-14211720 | A4 | 136 | 32.2 | 2.14 | 0.523 | 92 | 822 |
| columbia-willamette | USGS-14211720 | A3 (report-only) | 136 | 79.6 | 14.8 | 0.35 | 92 | 822 |

## The folds

| fold | held_out | report_only | training_pairs | training_groups | num_leaves | min_data_in_leaf | n_estimators | q90 | interval_factor90 |
|---|---|---|---|---|---|---|---|---|---|
| atchafalaya | ATCHAFALAYA | no | 1803 | 8 | 31 | 20 | 200 | 0.924 | 2.52 |
| columbia | COLUMBIA | no | 1437 | 8 | 15 | 50 | 200 | 1.01 | 2.75 |
| connecticut | CONNECTICUT | no | 1742 | 8 | 31 | 50 | 500 | 0.978 | 2.66 |
| mississippi | MISSISSIPPI | no | 1579 | 8 | 7 | 20 | 500 | 0.883 | 2.42 |
| missouri | MISSOURI | no | 1754 | 8 | 15 | 20 | 500 | 0.949 | 2.58 |
| ohio | OHIO | no | 1663 | 8 | 7 | 50 | 500 | 0.962 | 2.62 |
| platte | PLATTE | no | 1787 | 8 | 15 | 20 | 500 | 0.944 | 2.57 |
| san-joaquin | SAN JOAQUIN | no | 1640 | 8 | 31 | 50 | 500 | 0.995 | 2.7 |
| willamette | WILLAMETTE | no | 1643 | 8 | 15 | 20 | 200 | 1.12 | 3.07 |
| mississippi-atchafalaya | MISSISSIPPI + ATCHAFALAYA | yes | 1501 | 7 | 7 | 20 | 500 | 0.865 | 2.38 |
| columbia-willamette | COLUMBIA + WILLAMETTE | yes | 1199 | 7 | 15 | 20 | 500 | 1.25 | 3.49 |
| all | none | no | 1881 | 9 | 7 | 20 | 500 | 0.884 | 2.42 |
