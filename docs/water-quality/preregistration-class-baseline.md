# Preregistration: a baseline for the class on rivers the model never saw (written 2026-10-20 UTC, before it ran)

This file fixes, before it is run, what the transfer test's class agreement is compared with. Its
SHA-256 is a line of `docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum
Sepolia (`terrachain:riveretch:frozen-artifacts`). It runs **once**, after that anchor is mined.
It is never edited: a change is a new file with its own line and anchor.

Nothing here edits `preregistration-transfer.md`, its results (`results/transfer/` and their
MANIFEST), the model cards or any ledger line.

## 1. Why, and what is already known

- An ungauged reach shows a turbidity class (under 30, 30 to 100, 100 FNU and over), beside the
  transfer test's class agreement: on the similar rivers, the class matched the gauge in
  **185 of 298** lock-box pairs (`results/transfer/transfer_pooled.json`, `class_agreement`, `n`).
- A count alone does not say whether that is good: if most of those pairs sit in one class, always
  guessing that class could match as often.
- **Decided after seeing the result.** This baseline was proposed after 185 of 298 was known. It is
  labelled so wherever it is shown.
- While writing this file, no class count of any baseline was made. The pairs' gauge values are the
  same ones the transfer test already used.

## 2. Data

- **Pairs:** exactly the 298 pooled pairs of the transfer test: the lock-box pairs
  (2023-12-01..2026-09-30) of the five similar sites (`transfer_pooled.json`, `similar_sites`:
  USGS-06805500, USGS-06934500, USGS-07020850, USGS-07374525, USGS-07381600), as
  `quality transfer-verify` rebuilds them (`quality/transfer_test.py`, `evaluate`).
- **Training years:** 2018-12-01..2023-11-30, the same split (`quality/site.py`, `split`).
- **Classes:** the transfer test's edges, 30 and 100 FNU (`transfer_pooled.json`,
  `class_edges_fnu`): under 30, 30 to under 100, 100 and over.
- No new river, gauge, scene or model.

## 3. The baselines

For a pair at a site of river group G (the group held out when the model estimated that pair):

- **B1 (the comparison):** always guess the most common class among the **training-year pairs of the
  other similar sites**, those not in G. It knows what an ungauged reach is chosen to be (a
  sediment-carrying river) and uses no data from G.
- **B2 (report-only):** always guess the most common class among the training-year pairs of **every
  site not in G** (all nine groups but G), as the transfer test's baseline (b) does for values.
- **B3 (report-only, a reference):** always guess the most common class of **G's own** training-year
  pairs. It uses local data, which an ungauged river does not have.
- **Ties** between two classes go to the lower class.
- The Mississippi's two sites share one held-out group, as in the transfer test.

## 4. What is reported

- For each baseline: the count of the 298 pairs whose guessed class matches the gauge's, as
  **k of 298**, beside the model's 185 of 298. Also per site.
- For B1, the paired split: pairs the model matched and B1 missed, and pairs B1 matched and the
  model missed.
- No percentage without its count, no test of significance, no threshold: this is a reference for
  reading 185 of 298, not a new level. Nothing about the ungauged reach's display changes with it.
- **Run once.** Every number is reported, whatever it shows.

## 5. Outputs

- `docs/water-quality/results/transfer-baseline/`: `class_baseline.csv` (one row per baseline and
  site, and the pooled rows) and `class_baseline.json`, with their own MANIFEST. The transfer
  test's MANIFEST is not touched.
- Recomputable from the committed inputs by a verify command, as the transfer test is.
- In the web's "Does it work?" chapter and the report, next to 185 of 298: "Always guessing the most
  common class of similar rivers: k of 298 (a comparison decided after seeing the result)".
