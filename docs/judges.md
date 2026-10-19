# For the judges

RiverEtch estimates river water quality from free satellite images, tests every model once on
years it never saw against a USGS gauge, and seals each estimate so nobody can quietly change it.
This page is the short way through it.

## Limits first

- **Clouds** hide about three passes in four (72–76 % in 2026).
- **Values with a unit only at a validated gauge.** Along the river the map is relative (NDTI).
- **The 2026 records are retrospective:** they were sealed after their gauge values were public.
  Only passes after T0 (the anchor of the scoring rule) count as prospective.
- **Gauge values are often provisional.** The USGS may still revise them; they are labelled.
- **Sepolia is a test network,** not mainnet.
- **The two demo reaches are the best two of ten rivers.** The median error over the nine rated is
  33.1 % (the **All rivers** tab).

## The 3-minute path

Open [river-etch.vercel.app](https://river-etch.vercel.app). No account, no wallet.

1. **Hero:** choose a case (the Mississippi at Belle Chasse, or the Platte at Louisville).
2. **The case file** (top left): the value, its expected range (?), its level (?), "Sealed" and the
   anchor date, and how far off the model tends to be beside guessing the river's usual value.
3. **Verify this record** (right): the browser recomputes the seal, walks the ledger, checks the
   model card and reads the anchor on Sepolia.
4. **Alter one value first**, then verify again: the seal breaks.
5. **Scoreboard** (bottom tabs): the prospective count (0 until a pass after T0 is scored), then
   the retrospective counts, each labelled.
6. **All rivers:** every river evaluated, the ones that do not beat the guess included.
7. **Climate → Extreme days:** the gauge's own record of low-flow, high-flow and warm-water days,
   and how often the satellite saw them.

## Verify without a wallet or our word

- In the app: **Verify this record** (step 3).
- On chain: the contract
  [`0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762`](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  on Sepolia; every anchor and its transaction are in
  [`docs/ledgers/anchors.jsonl`](ledgers/anchors.jsonl).
- From a clone (see the [README](../README.md#getting-started)):

  ```bash
  cd pipeline
  uv run climate-pipeline quality verify --root ..   # every result against its MANIFEST
  uv run climate-pipeline reach verify --root ..     # every record's seal, chain and card
  uv run climate-pipeline ledger verify --root ..    # the frozen rule and cards
  ```

What an anchor proves and what it does not: [trust model](trust-model.md).

## Open data

- **In the app:** the **Export** menu downloads the turbidity series (CSV), the reach's geometry
  (GeoJSON), the ledger (JSONL) and the model card (JSON).
- **In the repository:** the records, ledgers and cards under
  [`docs/water-quality/reach/`](water-quality/reach/), the results under
  [`docs/water-quality/results/`](water-quality/results/). Code under MIT, docs and data under
  CC BY 4.0 ([LICENSE](../LICENSE), [LICENSE-docs](../LICENSE-docs)).

## Where the numbers come from

- [Report](water-quality/report.md): every river, every variable, what passed and what did not.
- [Preregistration](water-quality/preregistration.md): the rules, written before the results.
- [Scoring rule v1](water-quality/prospective.md): how a prospective pass is scored.
- [Decision log](decisions.md): why things are as they are.
