# Preregistration: the turbidity value beside its class, along the river and where there is no station (written 2026-10-23 UTC; decided after seeing the classes)

This file fixes, before any of it runs, how RiverEtch shows a turbidity value in FNU where it now
shows only a class: at the reading spot of the two reaches with no station, and on every window
along the four reaches. Its SHA-256 is a line of `docs/ledgers/frozen-artifacts.jsonl`; nothing
below runs before that line is anchored on Sepolia.

## 1. Why, and what is already known

- **The model already makes a value.** The four-class transfer model (A4, the cards
  `docs/water-quality/ungauged/mississippi-st-joseph/turbidity-4.json` and
  `docs/water-quality/ungauged/firat-birecik/turbidity-4.json`) estimates turbidity in FNU for each
  window and then shows only its class (under 30, 30 to 50, 50 to 100, 100 FNU and over), as
  [preregistration-transfer.md](preregistration-transfer.md), section 5,
  [preregistration-outside-us.md](preregistration-outside-us.md), section 4, and
  [preregistration-along-river.md](preregistration-along-river.md), sections 3 and 6, fix. A
  report needs the value.
- **That value's error is already measured.** The transfer test scored the same model's values on
  the stations of the rivers it never saw (`docs/water-quality/results/transfer/`). Pooled over
  the five similar stations (298 passes): a median symmetric accuracy (MdSA) of 36.9 %, a bias
  (SSPB) of −22.9 % (it reads low), Spearman ρ 0.72 (95 % lower bound 0.65), and its 90 % interval
  held the station's value in 248 of the 298 passes. By station it ranges from 15.4 % (Belle
  Chasse) to 162.0 % (the Platte, where it reads far low).
- **Outside the tested region** (Birecik) no station measures the river, so no error can be
  measured there.
- **Decided after seeing results (disclosure).** The classes of 2026 along the four reaches, the
  transfer test and the class tests are known.

## 2. What is read, fixed here

- **The same model, windows, guards and class edges**, unchanged: each estimate that has a class
  now also carries its value in FNU (two decimals), the number the model already makes. An
  estimate that abstains still has neither.
- **Sealed again, never rewritten.** At the reading spot of St. Joseph and Birecik, each 2026 pass
  is read again and sealed as a new observation record that names the one it replaces, in the
  same ledger (as [preregistration-four-classes.md](preregistration-four-classes.md), section 4,
  does). Along the river, each pass gets a new record (`riveretch.along-river.v2`: each window's
  class and value) that names the one it replaces, in the reach's own along ledger. The earlier
  records stay, unchanged.
- **The earlier years** (2019 to 2025, [preregistration-archive.md](preregistration-archive.md))
  are read again the same way, with the value beside each class; they stay recomputed and not
  sealed.

## 3. What is shown, fixed here

- **On the US reaches** (St. Joseph's reading spot, and every window along Belle Chasse, the
  Platte and St. Joseph): the value, for example "62 FNU", with the transfer test's pooled error
  beside it, "typical error 37 %", and its class. The bias and the stations' spread are one press
  away, in the (?) beside it.
- **At Birecik:** the value and its class's range, for example "4.2 FNU · under 30 FNU". The
  record keeps its basis (`outside_tested_region`) and no error figure.
- **The stations' own windows** at Belle Chasse and the Platte: unchanged (the station's card, its
  value and its 90 % range).
- **Anywhere along a reach where a pass has a reading:** the value, in the case file when the
  reading spot moves there, under the map's pointer, and along the river's charts; the map and the
  charts keep painting each stretch by its class.
- **Exports** carry the value beside the class, and Check a file checks both.
- This section replaces, for what the app shows, "never a value with a unit" in
  preregistration-transfer.md, section 5, preregistration-outside-us.md, section 4, and
  preregistration-along-river.md, sections 3 and 6. The cards and the records already sealed keep
  their own text, unchanged.

## 4. Runs, after the anchor

- After this file's line is anchored: the daily run reads each 2026 pass again once
  (`reach reread` at St. Joseph and Birecik, `reach along` on the four reaches), then every new
  pass with its value. The earlier years are read again once by the "Earlier years" workflow.
- No model, window, guard, class edge, error figure or label changes after the anchor. A change
  is a new file with its own line and anchor.
