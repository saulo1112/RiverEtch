# Preregistration: the earlier years, 2019 to 2025, along the river and at the station (written 2026-10-22 UTC; decided after seeing the 2026 records along the river)

This file fixes, before any of it is read, how RiverEtch reads the years before its sealed records
(2019 to 2025) on every reach the app shows, and how the app shows them. Its SHA-256 is a line of
`docs/ledgers/frozen-artifacts.jsonl`; nothing below runs before that line is anchored on Sepolia.

## 1. Why, and what is already known

- **The sealed records start in 2026.** A record is sealed and anchored when its pass is read, so
  earlier years cannot become records. A reader still wants to see them: how the river looked in
  earlier years, at the station and along the river.
- **What is stored now:** each reach's station window on the baseline's passes
  (`docs/water-quality/reach/<site>/station-windows.csv`; preregistration-along-river.md, section
  5), which stops before 2025 at Belle Chasse and in mid-2021 at Birecik; Landsat's surface
  temperature at the two temperature stations (`docs/water-quality/inputs/v6`, `v7`). No window
  along any reach has been read before 2026, and no map of an earlier pass is kept.
- **Decided after seeing results (disclosure).** The 2026 records, along the river and at the
  station, the models' tests and the station windows above are known.

## 2. What is read, fixed here

- **Sentinel-2, every reach** (Belle Chasse, the Platte, above Natchez, Birecik): every pass from
  2019-01-01 to 2025-12-31 that the daily run's search finds over the reach and that the daily
  run's scene rule calls observable (the screening's rule on the scene classification, unchanged).
  Each pass is read once, with no other filter:
  - **along the river:** every placed window of the reach's frozen plan, read and classed exactly
    as preregistration-along-river.md, sections 2 and 3, fix (the same card, guards and edges);
  - **at the start:** the station's window, or the reading spot's on a reach with no station, read
    by the reach's own frozen turbidity card exactly as a record's estimate is made: a value and
    its 90 % range where the card gives one, a class where it gives a class, or no reading.
- **Landsat 8/9, the two reaches with a water-temperature card** (Belle Chasse and the Platte):
  every Tier 1 pass from 2019-01-01 to 2025-12-31 over the reach, read once: the station's core
  window by the reach's card exactly as a water-temperature record's estimate, and every placed
  window's core in the six classes of preregistration-along-temperature.md, section 2.
- **What each pass was to the model:** its training years (a turbidity card's own training dates;
  for water temperature, before the locked test), its locked test (2023-12-01 to 2026-09-30,
  preregistration.md, "Splits"), or after both; on a reach with no station, a river the model
  never saw.

## 3. What is written, fixed here

- **Recomputed, not sealed.** A pass read after the fact is not a record: nothing is sealed or
  anchored. The results are written per reach and per year
  (`docs/water-quality/reach/<site>/examples/archive/<year>.json`, and `archive-temperature/` for
  water temperature), each naming the code commit, the plan's SHA-256 and each card's hash, so
  anyone can read the same passes again and compare.
- **Run once,** by `climate-pipeline reach archive` and `climate-pipeline reach
archive-temperature`, in a manual workflow after the anchor. A pass that fails to read is
  retried; nothing read is changed or dropped afterwards.

## 4. How the app shows an earlier year, fixed here

- **A year to choose** in the case's calendar, 2019 to 2026. 2026 shows the sealed records, as
  before.
- **An earlier year is labelled "Recomputed, not sealed"** wherever it appears, with each pass's
  phase from section 2 (for example, "training years: the model learned from this period").
- **The same rules as the records:** a value with a unit only at the station's window of a reach
  whose card gives one; a class everywhere else; "No reading" where there is none
  (preregistration-along-temperature.md, sections 3 and 4).
- **The map** paints the river by each stretch's class on the reach's water outline from a 2026
  pass, as no image of an earlier pass is kept; the per-pixel index and the true-colour image are
  not shown for an earlier year.
- **The station's earlier years** on the turbidity chart come from this read, which covers every
  observable pass. This replaces, for the app only, the source fixed by preregistration-along-river.md,
  section 5 (`station-windows.csv`).

## 5. Runs, after the anchor

- After this file's line is anchored: `reach archive` for the four reaches and `reach
archive-temperature` for Belle Chasse and the Platte, once each. Every outcome is shown as it
  comes.
- No year, rule, card, class edge or label changes after the anchor. A change is a new file with
  its own line and anchor.
