# Prospective scoring: rule v1 (written 2026-10-19, before any prospective pass was scored)

This file fixes how RiverEtch scores its estimates against the gauge from now on, and how it
counts extreme days. It is written before any pass it applies to was acquired. Its SHA-256 is a
line of `docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum Sepolia
(`terrachain:riveretch:frozen-artifacts`). It is never edited: a change is a new file, rule v2,
with its own line and anchor, and applies only to passes acquired after that anchor.

The preregistration (`preregistration.md`) is not edited: its git blob is part of the recomputed
results that CI checks against the MANIFEST.

## 1. Two kinds of pass

- **T0** is the block time of the first anchor of `terrachain:riveretch:frozen-artifacts` whose
  ledger lists this file.
- **Prospective:** a pass acquired after T0 whose claim is anchored before RiverEtch reads its
  gauge value. The claim is the pass's sealed record (an observation record for turbidity, a
  water-temperature record for temperature) and its line in the reach's ledger. Its model card and
  this rule were anchored before the satellite took the image.
- **Retrospective (backtest):** every other pass, including every pass acquired before T0. All
  records of 2026 up to T0 are retrospective: they were sealed after their gauge values were
  public.
- What a prospective pass proves: the estimate is a fixed function of an anchored card, public
  imagery and a public code commit, so it could not be tuned to a gauge value that did not exist
  when the card was anchored; and the claim could not be changed after RiverEtch scored it. It does
  not prove that the gauge value was unknown when the claim was sealed: the USGS publishes
  provisional values within minutes, hours before the imagery.

## 2. What is scored

| Target            | Claim (sealed)                                                 | Gauge series                                                                                                                         |
| ----------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Turbidity (FNU)   | The record's `turbidity` estimate: its value and 90 % interval | USGS parameter 63680 at the reach's estimate station: 07374525 (Belle Chasse), 06805500 (Louisville)                                 |
| Water temperature | The temperature record's estimate: its value and 90 % interval | USGS parameter 00010 at the station the card was validated against: 07374000 (Baton Rouge) for Belle Chasse, 06805500 for the Platte |

- Only the demo reaches are scored (Belle Chasse and the Platte). Hermann's card is _indicative_:
  it publishes a class, not a value with an interval.
- The value and interval scored are the sealed ones, as written in the record, never a value
  recomputed or noted elsewhere.
- A claim that abstained (no value) is listed as **abstained** and never scored.

## 3. The gauge's value at the overpass

- The overpass time is the imagery's acquisition time (public STAC metadata).
- The value is the median of the gauge's values within ±30 minutes of the overpass; otherwise the
  nearest value within ±60 minutes. Qualified values are excluded. These are the lock box's own
  settings (`pipeline/water-quality.yaml`, `usgs`), except that any approval status is accepted.
- **Approval:** the first read takes what exists, normally _Provisional_, and says so. When an
  _Approved_ value appears later, it is appended as a new line; it never replaces the first read.
  Headline counts use first reads.
- **Lag:** the gauge is read no earlier than 12 hours after the overpass, and only for a claim
  whose ledger line is already covered by a mined anchor.
- **No gauge value:** recorded as **no gauge value**, read again at the next daily run, final after
  7 days. It is never counted as inside or outside.

## 4. The score

- **Inside:** `low ≤ gauge ≤ high`, with the sealed interval's bounds, inclusive. Otherwise
  **outside**.
- Each scored pass is one line of the reach's outcomes ledger
  (`docs/water-quality/reach/<site>/examples/outcomes/ledger.jsonl`). Each line names the claim's
  record SHA-256, its ledger and line, the gauge reading (station, parameter, value, unit, approval,
  rule, number of values), the time it was read, the status, and the SHA-256 of this file. Lines
  chain by hash, like every other ledger, and the ledger is anchored as
  `terrachain:<reach>:outcomes`.
- **Reporting:** counts ("7 of 8 inside the expected range") until there are 20 scored passes of a
  kind. No percentage, no error statistic, and no level changes on these counts (as preregistration
  v4, A). Prospective and retrospective counts are never added together.

## 5. Extreme days (the climate component)

Defined here before any error on extreme days was computed. They are counted from the gauge's
own daily record (`docs/water-quality/reach/<site>/climate/daily.csv`), never from satellite
values.

- **Low-flow day:** a daily mean discharge (00060) at or below the 10th percentile of the gauge's
  approved daily means from its first day to 2025-12-31.
- **High-flow day:** at or above the 90th percentile of the same days.
- **Warm-water day:** a daily mean water temperature (00010), June to September, at or above the
  90th percentile of the gauge's approved June–September daily means from 2002 to 2025. Only where
  the gauge measures temperature (the Platte); the Belle Chasse gauge does not.
- **Ranks:** a year's count of extreme days is ranked among the years ranked by the climate
  context's rule (`docs/water-quality/reach/README.md`, _Climate context_: at least 90 % of the
  year's days measured; for temperature, of June–September). The current year is shown to date and
  never ranked.
- **Seen by the satellite:** an extreme day on which the reach has a usable pass. For 2026, a
  sealed record with a value; for 2019–2025, a gauge-matched usable scene of the v5 inputs
  (`docs/water-quality/inputs/usgs-v5/turbidity.csv`), labelled as such.
- **Error on extreme days:** compared with normal days only where the lock box holds at least 20
  pairs on that kind of day (the levels' minimum, preregistration v5). Otherwise the product says
  "not enough extreme days to say" and gives the counts.
- **Disclosure:** while these definitions were written, the number of lock-box pairs on each kind
  of day and the share of extreme days seen by a usable pass were counted (13 low-flow pairs of 57
  at Belle Chasse; 1 low-flow, 4 high-flow and 4 warm of 54 at the Platte). No error on extreme
  days had been computed.
