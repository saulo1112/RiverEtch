# Preregistration: four turbidity classes for the ungauged reaches (written 2026-10-20 UTC, before it ran)

This file fixes, before any of it is run, a test of whether a finer turbidity class still beats
guessing on rivers the model never saw, and what the ungauged reaches show if it does. Its SHA-256
is a line of `docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum Sepolia
(`terrachain:riveretch:frozen-artifacts`). The test runs **once**, after that anchor is mined. It
is never edited: a change is a new file with its own line and anchor.

Nothing here edits `preregistration-transfer.md`, `preregistration-outside-us.md`,
`preregistration-class-baseline.md`, their results, any card or any ledger line. Section 4 says
how the display rules of the first two change if, and only if, the test passes.

## 1. Why, and what is already known

- The ungauged reaches show a class: under 30, 30 to 100, 100 FNU and over
  (`preregistration-transfer.md`, sections 4 and 5; `preregistration-outside-us.md`, section 4).
  The middle class spans more than a factor of three. St. Joseph's 22 sealed records hold 11 in
  it, 7 under 30, 2 at 100 and over, and 2 abstentions. The owner asked for a finer class.
- **Already known (disclosure):** the three-class agreement on the similar rivers, 185 of 298
  (`results/transfer/transfer_pooled.json`), and St. Joseph's records and their classes. The
  three-class baseline (`preregistration-class-baseline.md`) is frozen and anchored; it has not
  run.
- **Decided after seeing the result.** The finer class was proposed after 185 of 298 and St.
  Joseph's records were known. It is labelled so wherever it is shown.
- While writing this file, no four-class count, no baseline count and no estimate were computed.

## 2. The four classes

- **Under 30, 30 to 50, 50 to 100, and 100 FNU and over** (edges 30, 50 and 100 FNU). The middle
  class of three is split at 50 FNU: a round number near the middle of 30 and 100 on the log scale
  the errors are measured on (the geometric mean is 54.8).
- A value on an edge belongs to the upper class, as now (`observation_v2.fnu_class`).

## 3. The test

- **Pairs:** exactly the 298 pooled pairs of the transfer test: the lock-box pairs
  (2023-12-01..2026-09-30) of its five similar sites (`transfer_pooled.json`, `similar_sites`),
  each with the estimate of the model that never saw its river group, rebuilt from the committed
  models as `quality transfer-verify` rebuilds them (`quality/transfer_test.py`, `evaluate`).
- **The model's count, k4:** the pairs whose estimate falls in the same four-class class as the
  gauge's value.
- **The baseline's count:** always guessing the most common four-class class among the
  training-year pairs (2018-12-01..2023-11-30) of the **other similar sites**, those not in the
  pair's river group; ties go to the lower class. It is the four-class form of B1 in
  `preregistration-class-baseline.md`, and uses no data from the pair's own river.
- **Pass rule (fixed here):** on the pairs where exactly one of the two is right, the model must be
  right more often than the baseline by an exact one-sided McNemar test: with b pairs the model
  matched and the baseline missed, and c the other way, the probability of b or more successes in
  b + c fair coin tosses is below 0.05. Otherwise the four classes are not shown anywhere.
- **Reported, whatever the outcome:** k4 of 298, the baseline's count, b, c and the p-value; the
  same per site; how many pairs land two or more classes away from the gauge's (report-only); and
  the three-class 185 of 298, unchanged, for reference.
- **Run once.**

## 4. If it passes

- **What the ungauged reaches show:** one of the four classes, never a value with a unit. At St.
  Joseph, beside it, "in k4 of 298 test passes on rivers it never saw, the class matched the gauge"
  replaces the three-class count, with the label "unvalidated: expected error from the transfer
  test" unchanged. At the Fırat, the four classes with "Outside the tested region. No error
  estimate." This changes the class of `preregistration-transfer.md`, section 5, and of
  `preregistration-outside-us.md`, section 4, for the ungauged reaches only, and nothing else in
  them.
- **New cards:** each ungauged reach gets a new card: the same model, ranges and abstention, the
  class edges 30, 50 and 100 FNU, and, at St. Joseph, k4 of 298 as its class agreement. Each is
  frozen with its own line before any record names it. The earlier cards stay frozen and stay
  named by the records sealed with them.
- **Records:** every pass sealed after the new cards names them. The 2026 passes already sealed
  with three classes are read again with the new card and sealed as new records; each names the
  record it replaces (`supersedes`, that record's SHA-256). The earlier records stay in their
  ledger, unchanged and verifiable. The case view shows the newest record of each pass and says
  that it replaced an earlier one.
- The three-class result (185 of 298) stays in the report.

## 5. If it does not pass

- The three classes stay everywhere, and the four-class result is reported as it came.

## 6. Outputs

- `docs/water-quality/results/four-classes/`: `four_classes.csv` (per site and pooled) and
  `four_classes.json`, with their own MANIFEST, recomputable from the committed inputs and models
  by a verify command. No other results' MANIFEST is touched.
