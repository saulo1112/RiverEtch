# For the judges

RiverEtch is a verifiable record of the state of rivers that have no gauge. It estimates river
water quality from free satellite images, tests every model once on data it never saw against a
USGS gauge, and seals each estimate so nobody can quietly change it. On a river with no gauge, the
seal is the only protection: nobody can check the number later. This page is the short way through
it.

## Limits first

- **Sealing proves a number was not changed; it does not prove it was right.** The tests show how
  often it was right.
- **On a river with no gauge, a class only** (under 30, 30 to 50, 50 to 100, 100 FNU and over),
  with the error measured on rivers the model never saw: the class matched the gauge in 160 of 298
  test passes, against 61 for always guessing the most common class (a comparison decided after
  seeing the result).
- **Values with a unit only at a validated gauge.** Along the river the map is relative (NDTI).
- **Clouds** hide about three passes in four (72–76 % in 2026).
- **The 2026 records sealed before T0 are retrospective:** they were sealed after their gauge values
  were public. Only passes after T0 (the anchor of the scoring rule) can count as prospective.
- **Station values are often provisional.** The USGS may still revise them; the app says so.
- **Sepolia is a test network,** not mainnet.
- **The two gauged demo reaches are the best two of ten stations** (on eight rivers). The median
  error over the nine rated is 33.1 % (the **Accuracy** tab).

## The 3-minute path

Open [river-etch.vercel.app](https://river-etch.vercel.app). No account, no wallet.

1. **Hero:** choose a case. The Mississippi at Belle Chasse and the Platte at Louisville have a
   station; the Mississippi above Natchez (St. Joseph) and the Fırat at Birecik (Türkiye) have
   none.
2. **Tour** (top left, beside Back): eight steps, each pointing at the control it explains; Esc
   ends it.
3. **The case file** (top left): on a gauged reach, the value, its expected range (?), its level
   (?), "Sealed" and the anchor date, and how far off the model tends to be beside guessing the
   river's usual value. On a reach with no station, the class with the tag "Satellite only", the
   label "unvalidated: expected error from the transfer test" (at the Fırat, "Outside the tested
   region. No error estimate.") and that error, and how the pass compares with the river's own
   past. At the Fırat, published measurements of the river at Birecik, labelled as looked up after
   seeing the result.
4. **Verify this record** (right), below.
5. **Change one number first**, type another number (or pick another class), then verify again:
   the seal breaks; put the sealed value back and it matches again.
6. **Check a file you were sent** (under the record): the record's JSON from its details, or the
   series from Export, edited or not; the browser names any value that differs from the sealed
   record.
7. **Accuracy** (bottom tabs): every station tested, where it works and where it is not
   recommended. On a reach with no station, the same stations scored by a model trained only on
   the other river groups: the error to expect where there is no station.
8. **Track record** (reaches with a station): the counts checked after the station's value was
   public, then the passes sealed before it was read (0 until a pass after T0 is scored).
9. **Climate → Extreme days:** the station's own record of low-flow, high-flow and warm-water
   days, and how often the satellite saw them.
10. **The status chip** (bottom right of the first screen): the daily run's last run, last anchor
    and Bitcoin timestamps.

## Verify a record in one minute

**Verify this record** recomputes, in your browser:

1. the record's canonical content and its **SHA-256**, against the seal it carries;
2. its place in the **ledger**: each line names the hash of the line before;
3. its **model card**'s hash;
4. its **anchor on Ethereum Sepolia**, read through a public node, or through your own wallet's
   connection if you connect one;
5. a **Bitcoin timestamp** of a ledger head covering it (OpenTimestamps, checked against two block
   explorers);
6. the **ML-DSA-65 signature** of that head, with the published key.

Steps 5 and 6 read the daily run's published files; until they are public, the dialog says they
could not be read.

Without the app:

- On chain: the contract
  [`0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762`](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  on Sepolia; every anchor and its transaction are in
  [`docs/ledgers/anchors.jsonl`](ledgers/anchors.jsonl).
- From a clone (see the [README](../README.md#getting-started)):

  ```bash
  cd pipeline
  uv run climate-pipeline quality verify --root ..            # every result against its MANIFEST
  uv run climate-pipeline quality transfer-verify --root ..   # the transfer test and the ungauged cards
  uv run climate-pipeline quality class-verify --root ..      # the class baseline and the four classes
  uv run climate-pipeline ledger verify --root ..             # the frozen rules, cards and tests
  uv run climate-pipeline ledger proofs --root ..             # each Bitcoin timestamp, block by block
  uv run climate-pipeline sign verify --root ..               # each head's ML-DSA-65 signature
  ```

What each check proves and what it does not, and which attacks it stops:
[trust model](trust-model.md).

## Open data

- **In the app:** the **Export** menu downloads the turbidity series (CSV), the reach's geometry
  (GeoJSON), the ledger (JSONL) and the model card (JSON).
- **In the repository:** the records, ledgers and cards under
  [`docs/water-quality/reach/`](water-quality/reach/), the results under
  [`docs/water-quality/results/`](water-quality/results/). Code under MIT, docs and data under
  CC BY 4.0 ([LICENSE](../LICENSE), [LICENSE-docs](../LICENSE-docs)).

## Where the numbers come from

- [Report](water-quality/report.md): every river, every variable, what passed and what did not,
  and the rivers the model never saw.
- [Preregistration](water-quality/preregistration.md) and
  [the transfer test's](water-quality/preregistration-transfer.md): the rules, written and anchored
  before the results.
- Scoring rules [v1](water-quality/prospective.md) and [v2](water-quality/prospective-v2.md): how a
  prospective pass is scored.
- [Decision log](decisions.md): why things are as they are.
