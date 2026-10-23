# Preregistration: the daily flow record, sealed and checked against its source, and the year's flow in the Climate tab (written 2026-10-23 UTC; decided after seeing the Climate tab and the stations' records)

This file fixes, before any of it runs, how RiverEtch seals the daily river flow that its Climate
tab shows, how anyone can check it against its source, and what the tab adds about flow. Its
SHA-256 is a line of `docs/ledgers/frozen-artifacts.jsonl`; nothing below runs before that line is
anchored on Sepolia.

## 1. Why, and what is already known

- **The flow is shown, not sealed.** The Climate tab of each of the four reaches the app shows reads
  a daily record of the river's flow: the USGS daily mean discharge at Belle Chasse
  (`USGS-07374525`), at Louisville on the Platte (`USGS-06805500`, with its daily mean water
  temperature) and at Vicksburg for St. Joseph (`USGS-07289000`, 59.0 km upstream in a straight
  line), and the GloFAS v4 flood model's daily river discharge for the Fırat at Birecik (modelled,
  not measured). The record is a snapshot fetched by hand
  (`docs/water-quality/reach/<site>/climate/daily.csv`, whose last values are of 2026-10-17 at Belle
  Chasse and the Platte and of 2026-10-20 at Vicksburg and for the Fırat); nothing in it is
  fingerprinted, timestamped or posted.
- **Sources revise their values.** USGS publishes recent days as provisional and approves or
  changes them later; a flood model's values can change when it is run again.
- **Decided after seeing results (disclosure).** The four records above, their yearly peaks and
  lows, and the tab's charts are known.

## 2. What is sealed, fixed here

- **One record per reach and calendar year:** the year's daily values exactly as the source
  published them when fetched, each with its status as published (USGS: "Approved", "Provisional"
  or another code; GloFAS: "Modelled"): the daily mean discharge (ft³/s, as USGS publishes it, or
  m³/s, as GloFAS does) and, where the station publishes it, the daily mean water temperature (°C).
  The record names the source, the query that fetched it, the fetch time and the code commit.
- **Fetched again every day,** by the daily run, over the whole period of record. A year whose
  values or statuses changed since its last record gets a new record, which names the record it
  replaces; a year that did not change gets none. Nothing written is changed or removed.
- **The same seal as the readings:** each record's SHA-256 over its canonical JSON, chained in the
  reach's record list `terrachain:<reach>:daily-record`
  (`docs/water-quality/reach/<site>/examples/daily-record/ledger.jsonl`), timestamped on Bitcoin,
  signed with the project's ML-DSA-65 key and posted on Ethereum (test network) with the other
  record lists.
- **What a seal proves here:** that the record is what its source published on the day it was
  fetched, and that any later change to it would show. It does not prove that the source's values
  are right, and the Fırat's values stay modelled, not measured.

## 3. How anyone checks it, fixed here

- **Check this record** (the Climate tab): the record's seal, its place in the chained list, the
  post on Ethereum, the Bitcoin timestamp and the signature, as "Check this reading" does.
- **Compare with the source now:** the browser fetches the same year from the source (the USGS
  Water Data OGC API, or the Open-Meteo flood API for GloFAS) and compares it with the sealed record
  day by day. It says how many days are the same, how many the source has revised since (value or
  status) and how many it no longer publishes or has added. A revision is not an error: provisional
  values are expected to change.
- **Export with proof and Check a file** take the daily record too, one CSV row per day: each row
  is checked against that day of the record its fingerprint names, and a day the file no longer
  holds is reported missing.

## 4. What the Climate tab adds about flow, fixed here

- **This year's flow, day by day** (the year shown in the case), in m³/s (USGS's ft³/s × 0.0283168466),
  against the river's **usual flow for each day of the year**:
  - the **reference years**: the record's complete years (at least 90 % of their days with a
    value, as the tab already ranks them) up to 2025;
  - for each calendar day (29 February as 28 February), the reference years' values from 3 days
    before to 3 days after it;
  - the **median** of those values, and the **usual range** between their 10th and 90th
    percentiles (linear interpolation).
- **Each satellite pass of that year** marked on its day, the low-flow and high-flow thresholds of
  rule v1 where they exist (Belle Chasse and the Platte, `docs/water-quality/prospective.md`), and,
  for any day, whether its flow is below, within or above the usual range.
- **The latest day in one sentence:** its flow, and the share of the reference values of its 7 days
  that were higher (for example, "On the same days of 2008 to 2025, it ran higher 81 % of the
  time").
- **No cause is stated.** The tab says that it shows how unusual a day or a year was, not why
  (rain, upstream use, dams or a changing climate). It states no trend and no attribution.
- Provisional values are shown as published and labelled; the Fırat's flow is labelled modelled.

## 5. Runs, after the anchor

- After this file's line is anchored: `climate-pipeline reach daily-record` for the four reaches,
  in every daily run, before their `climate.json` is written. The first run seals every year of
  each record.
- No year, rule, percentile, window or label changes after the anchor. A change is a new file with
  its own line and anchor.
