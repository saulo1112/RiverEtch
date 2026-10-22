# Preregistration: turbidity along the whole river, the station's earlier years, and how a class is shown (written 2026-10-22 UTC; decided after seeing the reaches' single-window records)

This file fixes, before any of it is read, how RiverEtch reads turbidity along the whole of each
reach the app shows, what it shows for a station's earlier years, and how a class is labelled. Its
SHA-256, and those of the four plans of windows it freezes, are lines of
`docs/ledgers/frozen-artifacts.jsonl`; nothing below runs before that line is anchored on Sepolia.

## 1. Why, and what is already known

- **A record reads one window.** Each reach's records estimate turbidity on one 300 m window: the
  station's, or a chosen reading spot where there is no station. The map shows NDTI per pixel
  along the river, but that is a relative index, with no unit.
- **A model already exists for places it never saw.** The four-class transfer model (A4, trained
  on the training-year pairs of all nine river groups: 1,881 pairs) was tested on each river group
  it did not see ([preregistration-transfer.md](preregistration-transfer.md),
  [preregistration-four-classes.md](preregistration-four-classes.md)): its class matched the
  station in 160 of 298 passes, against 61 for always guessing the most common class. A window
  along a reach, away from any station, is such a place.
- **Decided after seeing results (disclosure).** The reaches' single-window records of 2026, the
  transfer test and the class tests are known. No window along any reach has been read: the plans
  below were measured with geometry only (the reach's water mask), and no reflectance, index,
  estimate or class of any of their windows exists.

## 2. The windows, fixed here

- **Where:** on each reach's frozen centreline, one window every 600 m, the first 300 m downstream
  of its upstream end. So the 300 m windows touch and never overlap.
- **How each is made:** exactly as a station's window (`pipeline/src/climate_pipeline/reach/along.py`,
  reusing the station code): snapped to the main channel of the reach's own SCL water frequency of
  2022 to 2025 (a pixel is water in at least half of at least 20 observations; the largest
  connected water component), within 1,500 m; its width is twice the largest distance to land
  within 300 m of the snapped point, and a window is placed only where it is at least 150 m
  (`pipeline/calibration.yaml`, `stations`). Its 300 m window and its core (the window's pixels at
  least 60 m from land) are a station's (`pipeline/water-quality.yaml`, `window`).
- **The plans, frozen with this file** (`docs/water-quality/reach/<site>/along/windows.json`):

  | Reach                       | Windows | Along   | Placed | Width inside the model's range (304.6 to 772.5 m) |
  | --------------------------- | ------- | ------- | ------ | ------------------------------------------------- |
  | Mississippi at Belle Chasse | 38      | 22.8 km | 38     | 36                                                |
  | Platte at Louisville        | 35      | 21.0 km | 35     | 28                                                |
  | Mississippi above Natchez   | 29      | 17.4 km | 29     | 15                                                |
  | Euphrates at Birecik        | 16      | 9.6 km  | 16     | 14                                                |

  A window whose width lies outside the model's range will abstain on every pass, as the model's
  rule requires; it is shown as a stretch with no reading.

## 3. The model, fixed here

- **US reaches** (Belle Chasse, the Platte, above Natchez): the frozen four-class card
  `docs/water-quality/ungauged/mississippi-st-joseph/turbidity-4.json` (frozen-artifacts line 19),
  the A4 model. Its training included the stations of the Mississippi and the Platte groups, at
  their own windows; the windows along the reaches are places it never saw. Its expected error is
  the transfer test's, applied as it is.
- **Outside the tested region** (Birecik): its own frozen four-class card
  `docs/water-quality/ungauged/firat-birecik/turbidity-4.json` (frozen-artifacts line 20), the same
  model (the same parameters' hash). No error is measured there.
- **Each window's class** is the card's estimate made exactly as a record's
  (`records.estimate`): the window guards (too cloudy to measure, the water-B11 check, too few
  valid pixels, contamination, glint share), the abstention when a feature lies outside its
  training range, and the card's class edges (30, 50 and 100 FNU). A
  class is never a value with a unit, and no window along a reach is ever scored (no station
  measures it).

## 4. What is read, and how it is sealed

- **Every pass of each reach's current records** (2026, a replaced record giving way to its
  replacement), and every later pass the daily run records. Each pass is read once: one read of
  the scene over a grid that holds all the reach's windows.
- **An along-river record per pass** (`riveretch.along-river.v1`): the reach, the pass, the seal of
  its observation record, the plan's SHA-256, the card and its hash, the STAC items, each window's
  class or the reason it has none, in the plan's order, and the code commit. It is sealed with the
  SHA-256 of its canonical JSON (keys sorted, no spaces, the seal left out) and chained in the
  reach's own ledger, `terrachain:<reach>:along`, which is anchored on Sepolia, timestamped on
  Bitcoin and signed like the others.

## 5. A station's earlier years, fixed here

- **What:** the committed `station-windows.csv` of each reach (its baseline's passes, from 2019),
  each pass the baseline did not exclude read by the reach's own frozen turbidity card, exactly as
  a record's estimate; written as `history.json` beside the examples. It is recomputed from
  committed files, so it is not sealed.
- **What it shows:** a value and its 90 % range where a record would show one (a station's
  _validated_ or _estimated_ card), a class on a reach with no station, or the reason for none.
- **Labels:** each pass says whether the card was trained on it (its station's own training years,
  December 2018 to November 2023: in sample), tested on it (its locked test, December 2023 to
  September 2026), came after both, or lies on a river the card never saw.

## 6. How a class is shown, fixed here

This section replaces, for the web app's display only, the labels fixed by
[preregistration-transfer.md](preregistration-transfer.md), section 5 ("unvalidated: expected
error from the transfer test"), and by
[preregistration-outside-us.md](preregistration-outside-us.md), section 4 ("Outside the tested
region. No error estimate.", wherever the class appears). The sealed records and the cards keep
their own labels, unchanged.

- **The class is shown alone**, for example "Under 30 FNU", wherever it appears: the reach's case,
  its charts, its map and along the river.
- **The same facts stay one press away,** in the (?) beside the class, and in the record: on a US
  reach, "In 160 of 298 test passes on rivers the model never saw, the class matched the station";
  at Birecik, "The model was tested on rivers in the United States; its error here has not been
  measured."
- **Along the river,** each stretch shows its class, or why it has none (cloud, glare, or a width
  or a reflectance outside the model's range).

## 7. Runs, after the anchor

- After this file's line is anchored: `climate-pipeline reach along --site <reach>` for the four
  reaches, once over their 2026 passes, then `climate-pipeline reach history --site <reach>`. The
  daily run then reads each new pass along the river. Every outcome is shown as it comes.
- No spacing, window rule, card, class edge or label changes after the anchor. A change is a new
  file with its own line and anchor.
