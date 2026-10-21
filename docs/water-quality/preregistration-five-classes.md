# Preregistration: five turbidity classes for the ungauged reaches (written 2026-10-21 UTC, before it ran)

This file fixes, before any of it is run, a test of whether splitting the lowest turbidity class
still beats guessing on rivers the model never saw, and what the ungauged reaches show if it does.
Its SHA-256 is a line of `docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum
Sepolia (`terrachain:riveretch:frozen-artifacts`). The test runs **once**, after that anchor is
mined. It is never edited: a change is a new file with its own line and anchor.

Nothing here edits `preregistration-transfer.md`, `preregistration-outside-us.md`,
`preregistration-class-baseline.md`, `preregistration-four-classes.md`, their results, any card or
any ledger line. Section 5 says how the display rules change if, and only if, the test passes.

## 1. Why, and what is already known

- The ungauged reaches show one of four classes: under 30, 30 to 50, 50 to 100, and 100 FNU and
  over (`preregistration-four-classes.md`, which passed). The lowest class has no lower end. At
  the Fırat at Birecik, all 55 of the 70 sealed 2026 passes that have a class are under 30; the
  other 15 abstained. The owner asked for a reading that says more.
- **Already known (disclosure):**
  - the four-class result: 160 of 298, the baseline 61, b = 121 and c = 22, so p = 4.6 × 10⁻¹⁸
    (`results/four-classes/four_classes.json`, which rounds p to 0; `report.md`); the
    three-class 185 of 298;
  - the sealed records of both ungauged reaches and their classes (St. Joseph's 22 passes, the
    Fırat's 70);
  - a published measurement, read before this file was written: the Euphrates River sampled at
    the outlets of the Atatürk and Birecik dams over eight months of 2002 and 2003, turbidity
    median, minimum and maximum 5.0 NTU (Alp, Koçer, Sen and Ozbay 2010, _Journal of Animal and
    Veterinary Advances_ 9(18): 2412–2421, Table 2, row EPH). It plays no part in the test.
  - The lowest training value on the ungauged card, 0.55 FNU (`targetRange`), was read to try the
    edge rule of `preregistration-four-classes.md` (section 2 below).
- **Decided after seeing the result.** The split was proposed after all of the above were known.
  It is labelled so wherever it is shown.
- While writing this file, no five-class count, no baseline count and no estimate were computed.
- **This is the third class test on the same 298 pairs** (three classes, four classes, now five).
  Each extra test on the same pairs makes a pass by chance more likely, so the level is divided by
  three (section 3), and the counts of each class are reported (section 4).

## 2. The five classes

- **Under 15, 15 to 30, 30 to 50, 50 to 100, and 100 FNU and over** (edges 15, 30, 50 and 100
  FNU). The lowest class of four is split at 15 FNU: 30 divided by 2, so that every class below
  100 FNU is at most a factor of two wide, as 50 to 100 is.
- The rule of `preregistration-four-classes.md` (a round number near the middle of the class on
  the log scale) does not fit a class with no lower end. Taken from the card's lowest training
  value (0.55 FNU) it gives about 4 FNU, which would make a class from 4 to 30, more than seven
  times wide; it is not used.
- A value on an edge belongs to the upper class, as now (`observation_v2.fnu_class`).

## 3. The test

- **Pairs:** exactly the 298 pooled pairs of the transfer test, as in
  `preregistration-four-classes.md`, section 3: the lock-box pairs (2023-12-01..2026-09-30) of its
  five similar sites, each with the estimate of the model that never saw its river group, rebuilt
  from the committed models; the rebuild must reproduce the three-class 185 of 298 first.
- **The baseline:** always guessing the most common class among the training-year pairs
  (2018-12-01..2023-11-30) of the **other similar sites**, those not in the pair's river group;
  ties go to the lower class (the form of B1 in `preregistration-class-baseline.md`).
- **McNemar:** on the pairs where exactly one of the two is right, with b pairs the model matched
  and the baseline missed and c the other way, p is the probability of b or more successes in
  b + c fair coin tosses (exact, one-sided).
- **Pass rule (fixed here), both of:**
  1. **Five classes:** the model's five-class count k5 against the five-class baseline, p below
     **0.05 / 3 = 0.0167**.
  2. **The split itself:** on the pairs whose estimate **and** gauge value are both under 30 FNU,
     the model's call (under 15, or 15 to 30) against the baseline's: the more common of the two
     among the training-year values under 30 FNU of the other similar sites (a tie goes to under
     15). p below **0.0167**. Without this, a split the model cannot make would still pass rule 1
     on the strength of the classes above 30.
- Otherwise the five classes are not shown anywhere.
- **Run once.**

## 4. Reported, whatever the outcome

- k5 of 298, the baseline's count, b, c and p, pooled and per site; the same for the split (its
  number of pairs, the model's and the baseline's counts, b, c and p);
- for each of the five classes: the pairs whose gauge value is in it, the pairs whose estimate is
  in it, and the pairs where both are;
- the pairs two or more classes away (report-only); and the four-class 160 of 298, unchanged, for
  reference.

## 5. If it passes

- **What the ungauged reaches show:** one of the five classes, never a value with a unit. At St.
  Joseph, beside it, "in k5 of 298 test passes on rivers it never saw, the class matched the
  gauge" replaces the four-class count, with the label "unvalidated: expected error from the
  transfer test" unchanged. At the Fırat, the five classes with "Outside the tested region. No
  error estimate." unchanged. This changes the class of `preregistration-four-classes.md`, section
  4, for the ungauged reaches only, and nothing else.
- **New cards:** each ungauged reach gets a new card: the same model, ranges and abstention, the
  class edges 15, 30, 50 and 100 FNU, and, at St. Joseph, k5 of 298 as its class agreement. Each
  is frozen with its own line before any record names it. The earlier cards stay frozen and stay
  named by the records sealed with them.
- **Records:** every pass sealed after the new cards names them. The 2026 passes already sealed
  are read again with the new card and sealed as new records, each naming the record it replaces
  (`supersedes`); the earlier records stay in their ledger, unchanged and verifiable.
- The four-class and three-class results stay in the report.

## 6. If it does not pass

- The four classes stay everywhere, and the five-class result is reported as it came.

## 7. Outputs

- `docs/water-quality/results/five-classes/`: `five_classes.csv` (per site and pooled),
  `five_classes_bins.csv` (each class's counts) and `five_classes.json`, with their own MANIFEST,
  recomputable from the committed inputs and models by `quality class-verify`. No other results'
  MANIFEST is touched.
