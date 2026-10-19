# RiverEtch

**Satellite water-quality estimates, validated against river gauges, with a record nobody can
quietly rewrite.**

Built for the IEEE ClimateChain Global Hackathon (October 5–25, 2026), Track 4: climate data and
monitoring. Judges: start with [docs/judges.md](docs/judges.md) and the live app,
[river-etch.vercel.app](https://river-etch.vercel.app).

## Why it matters for climate

Rivers carry the climate's extremes, and the two reaches RiverEtch follows have lived through
them. These numbers are the USGS gauges' own daily records (`reach climate`), not satellite
estimates:

**Platte at Louisville, Nebraska** (daily record since 1953):

- **2019:** the highest annual peak in 72 complete years, 6,201 m³/s on 16 March
  ([the March 2019 floods](https://www.usgs.gov/media/images/spring-2019-flooding-louisville-ne)).
- **2022:** its annual peak ranked 70th of 72.
- **2023:** the warmest summer day in 20 summers, 32.1 °C.

**Mississippi at Belle Chasse, Louisiana** (daily record since 2008):

- **2023, 2022 and 2024:** the three lowest 7-day flows in 16 complete years. In 2022 and 2023,
  [saltwater moved up the river](https://www.wwno.org/coastal-desk/2023-09-19/saltwater-threatens-south-louisiana-drinking-water-second-year-in-a-row-amid-severe-drought)
  towards the parish's drinking-water intakes.

What these years mean:

- **More of these years are expected.** Continued warming is projected to make wet and dry
  extremes more severe ([IPCC AR6 WGI, SPM B.3.1](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/)).
  Those are the years an agency most needs to read a river, between and beyond its gauges: between
  them as a relative map, with a unit only where a gauge validated the model.
- **Water temperature matters for climate impacts.** The Belle Chasse gauge does not measure it.
  Landsat does, with a 0.86 °C error validated at Baton Rouge.
- **Adaptation runs on records.** Drinking-water intakes, permits and insurance claims all depend
  on readings that nobody revised after the fact. Each pass is sealed, and its ledger is anchored on
  Ethereum, so the record of a flood or a drought stays as it was measured.
- **What this does not claim.** One gauge's record attributes no event to climate change, and the
  satellite record (since 2018) is far too short for a trend.

In the web app, each case's **Climate** tab shows its gauge's whole record, year by year, and its
extreme days: how many low-flow, high-flow and warm-water days each year held, and how often the
satellite saw them. The locked test holds fewer than 20 passes on any kind of extreme day, so the
app says so instead of giving an error for them.

## What RiverEtch does

RiverEtch reads rivers from free satellite imagery (Sentinel-2 and Landsat). It turns each clear
pass into water-quality values with a stated error. Every value was tested once, on years its model
never saw, against a USGS gauge. Each pass is sealed as a record (the SHA-256 of its content) and
chained in an append-only ledger, so anyone can recompute it from public data and see that it has not
changed.

## Who decides

A water-quality analyst at an environmental agency decides; RiverEtch informs. The analyst needs an
independent estimate they can cite, and needs to show it was not adjusted after the fact. The gauge
is the referee: RiverEtch publishes a value only where a gauge validated its model. Every record
says which model card produced it.

## Limits (read these before the numbers)

- **Clouds:** about three passes in four are lost to them (72–76 % in 2026).
- **Validated only at the gauge:** a value with a unit is published only at a validated gauge's
  window. The per-pixel map along the reach is relative (NDTI) and not validated.
- **The 2026 check (retrospective) raises two warnings:**
  - At Belle Chasse the error holds on new data (18.9 %), but the 90 % intervals covered 13 of 18
    values.
  - The Platte overestimated six provisional summer values by 1.5–2×.
  - Both are reported, not hidden: see [The reaches in operation](docs/water-quality/report.md).
- **Timing:** every 2026 record so far was sealed in batch runs (2026-10-12 to 2026-10-15), after
  its gauge value was public. Those passes are a backtest: they show that the model cards were
  frozen and committed first, and that the pipeline reads no gauge value to make an estimate. Only
  passes after T0, the anchor of the scoring rule, are scored as prospective (see the scoreboard
  below).
- **Gauge values are often provisional.** The USGS can still revise them; every one is labelled.
- **Sepolia is a test network,** not mainnet: an anchor there is a public, checkable timestamp.
- **A seal shows a record has not changed, not that it is right.** Correctness comes from the locked
  tests and the scoreboard.
- **Our own process rejected our first pitch.** RiverEtch started on Colombian rivers. IDEAM's
  point samples met too few clear scenes to validate any model, so no Colombian value is published.
  Those rounds stay in the [preregistration](docs/water-quality/preregistration.md) with every
  attempt counted.

## What it measures today

Every error is out of sample: a locked test (December 2023 to September 2026) that training and
model selection never saw, scored once. Each error sits next to its baseline, the error a user would
get without the satellite.

| Variable, reach                              | Locked-test error            | Baseline (no satellite)         | Level     |
| -------------------------------------------- | ---------------------------- | ------------------------------- | --------- |
| Turbidity, Mississippi at Belle Chasse (LA)  | **17.8 %** median, 57 passes | 113.7 % (median of past values) | validated |
| Turbidity, Platte at Louisville (NE)         | **20.3 %** median, 54 passes | 66.9 % (median of past values)  | validated |
| Water temperature, Platte at Louisville (NE) | **1.28 °C** mean, 24 passes  | 2.51 °C (day-of-year average)   | estimated |
| Water temperature, Mississippi (LA)          | **0.86 °C** mean, 37 passes  | 1.41 °C (day-of-year average)   | estimated |
| Suspended sediment, both reaches             | too few samples, or biased   | —                               | not shown |
| Discharge, dissolved oxygen (Platte)         | 110.6 % and 1.02 mg/L        | 65.5 % and 1.34 mg/L            | not shown |

- **The two reaches are the best two of ten rivers** validated with the same protocol. The honest
  summary of the method is the median over the nine evaluated: **33.1 %**. Turbid rivers do best;
  clear, tidal rivers do worst. Every river's result is in the
  [report](docs/water-quality/report.md).
- **Water temperature at Belle Chasse** was validated at Baton Rouge, the only main-stem gauge on
  the lower Mississippi that measures it (about 245 km upstream), against provisional values, so it
  is capped at _estimated_.
- **What did not pass (v7, v7.1):**
  - discharge from the water surface erred more than the seasonal average;
  - dissolved oxygen missed on its interval's coverage;
  - specific conductance earned _estimated_ by the rule but does not follow the river's changes
    (correlation 0.03), so it is not shown.
  - The gauges' own readings of all three stay visible as context, labelled as measurements.

## The scoreboard: committed before the gauge is read

What the chain adds is a commitment made before the answer exists. The scoring rule
([rule v1](docs/water-quality/prospective.md)), the model cards, the preregistration and the
results' MANIFEST are listed with their hashes in a frozen ledger and anchored on Sepolia; that
anchor's block time is **T0**. A pass after T0 is **prospective** only when its record was sealed
and anchored before RiverEtch read the gauge, at least 12 hours after the pass. `reach score` then
appends the outcome (inside or outside the sealed range, with the gauge value's approval) to an
outcomes ledger, which is anchored too.

The **Scoreboard** tab shows counts, never percentages, until there are 20 passes. The
retrospective counts, labelled as such:

| Inside the expected range  | Turbidity, Belle Chasse | Turbidity, Platte | Water temperature, Belle Chasse | Water temperature, Platte |
| -------------------------- | ----------------------- | ----------------- | ------------------------------- | ------------------------- |
| 2026 passes, retrospective | 13 of 18                | 7 of 8            | 11 of 13                        | 11 of 13                  |
| Locked test, retrospective | 54 of 57                | 50 of 54          | 33 of 37                        | 23 of 24                  |

The prospective count is in the app, and is stated here at the submission freeze, 0 included.
Clouds hide about three passes in four, so it grows slowly. Every count is computed from the
committed files (`web/test/scoreboard.test.ts`).

## How it works

1. **Observe.** At every clear Sentinel-2 pass, each water pixel of the reach gets its NDTI, a
   relative turbidity index. Clouds, glint and the banks are masked out.
2. **Estimate.** At the gauge's window, a model card turns the pass into a value with a 90 %
   interval: turbidity in FNU from Sentinel-2, water temperature in °C from Landsat's thermal band.
   A value outside the card's training range abstains and says why.
3. **Seal.** Each pass becomes a record: the SHA-256 of its canonical JSON. The record names its
   model card's hash and the code commit that produced it. Records are chained in a ledger, where
   each line names the hash of the line before.
4. **Verify.** The web app recomputes a record's seal in the browser, walks the ledger chain and
   checks the model card. Changing a single digit breaks the seal.
5. **Check (retrospective).** After each run, the estimates are compared with the gauge's own
   readings (report-only). That shows whether the error holds on new data.
6. **Score (prospective).** Each anchored claim after T0 is scored against the gauge into the
   outcomes ledger, under the frozen rule (see the scoreboard above).

`pipeline/scripts/daily.ps1` runs the cycle (score, new records, check, the web's files) and is
meant to run as a scheduled task at 19:00 Bogotá time; it reads public data only and never commits.
The ledgers and the anchoring log show when it actually ran.

**Anchored on Ethereum (Sepolia).** `contracts/src/LedgerAnchor.sol` stores each ledger's head
(the SHA-256 of its last line, which commits to every line above it) with the block's time. The
contract's owner anchors the ledgers from the terminal (`contracts/scripts/anchor.ts`), which also
rebuilds the anchoring log, [docs/ledgers/anchors.jsonl](docs/ledgers/anchors.jsonl), from the
chain. **Verify this record** then reads the anchor without a wallet: anchored at block N, recorded
after the last anchor, or changed since. An anchor proves the ledger's state from its own date on,
never before. See [docs/anchoring.md](docs/anchoring.md) and the
[trust model](docs/trust-model.md).

## Glossary

| Term            | Meaning                                                                                         |
| --------------- | ----------------------------------------------------------------------------------------------- |
| NDTI            | Normalized Difference Turbidity Index, (red − green) / (red + green): relative, with no unit    |
| FNU             | Formazin Nephelometric Units, the unit the USGS turbidity sensors report                        |
| Median error    | MdSA, median symmetric accuracy: 100 × (exp(median of abs(ln(estimate / gauge))) − 1), in %     |
| Locked test     | Years held out from training and selection, scored once                                         |
| Preregistration | The rules (candidates, metrics, thresholds) written and committed before any result is computed |
| Level           | _validated_ / _estimated_ / _indicative_: what a locked test earned; below _estimated_, no unit |
| Model card      | The frozen model of a reach and target, with its locked-test scores; records name its SHA-256   |
| Seal, ledger    | A record's SHA-256, and the append-only list of seals where each line names the one before      |
| 7-day low flow  | A year's lowest mean discharge over 7 consecutive days: the standard measure of a dry spell     |
| T0              | The block time of the scoring rule's first anchor: passes after it can be prospective           |
| Prospective     | Sealed and anchored before the gauge was read, after T0; anything else is retrospective         |

## Repository structure

```text
.
├── pipeline/   Python 3.12 (uv): screening, water-quality validation (`quality`), reach records (`reach`)
├── web/        Vite + React: the globe, the cases and the case view (map, charts, record verification)
├── contracts/  Hardhat 3: the ledger anchor (LedgerAnchor, Sepolia); a legacy ZK scaffold, unused
├── docs/       the water-quality report and preregistration, the record schema, the decision log
└── .github/    CI: every result is recomputed and checked against its MANIFEST
```

**Key documents:**

- **For judges:** [the short path](docs/judges.md) and [the trust model](docs/trust-model.md).
- **Results:** [report](docs/water-quality/report.md), [preregistration](docs/water-quality/preregistration.md),
  [results](docs/water-quality/results/results.md) and the
  [scoring rule](docs/water-quality/prospective.md).
- **Records:** [the record schema](docs/schema/README.md) and
  [the reach pipeline](docs/water-quality/reach/README.md).
- **Design:** [architecture](docs/architecture.md) and [decision log](docs/decisions.md).

## Getting started

### Prerequisites

| Tool                                                           | Version                                | Needed for                                       |
| -------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------ |
| [Git](https://git-scm.com/)                                    | any recent                             | everything                                       |
| [Node.js](https://nodejs.org/)                                 | 24 LTS (see `.nvmrc`; npm 11 included) | web, contracts, hooks                            |
| [uv](https://docs.astral.sh/uv/getting-started/installation/)  | 0.12 or newer                          | Python pipeline (uv installs Python 3.12 itself) |
| [circom](https://docs.circom.io/getting-started/installation/) | 2.2.3                                  | the legacy ZK scaffold only (unused)             |

### Run the web app

```bash
git clone https://github.com/saulo1112/RiverEtch.git
cd RiverEtch
nvm use            # or any other way to run Node 24
npm install        # installs every workspace and the Git pre-commit hook
npm run dev        # http://localhost:5173
```

The app reads the reaches' committed records from `docs/water-quality/reach/*/examples/`. It needs
no account and no wallet. `web/.env.example` lists the optional WalletConnect and Sepolia settings.

### Reproduce the results

```bash
cd pipeline
uv sync                                                  # Python 3.12 and the locked dependencies
uv run climate-pipeline quality run --root ..            # recompute every validation from the snapshots
uv run climate-pipeline quality verify --root ..         # compare them with the MANIFEST, to the last digit
uv run pytest tests/test_reach_examples.py               # check every committed record's seal, ledger and card
uv run climate-pipeline ledger verify --root ..          # the frozen rule, cards and MANIFEST are unchanged
```

`reach run`, `reach thermal` and `reach check` make new records from public data and compare them
with the gauges; `reach score` scores the anchored claims under the frozen rule. `reach climate`
fetches each gauge's whole daily record for the Climate tab. See
[docs/water-quality/reach/README.md](docs/water-quality/reach/README.md).

### Run every check

```bash
npm run check            # format, lint, circuits, compile, types, all tests, frontend build
npm run pipeline:check   # ruff format + lint, mypy --strict, pytest
```

### The contracts

```bash
npm run zk:build         # legacy demo circuit, unused by RiverEtch (see docs/zk-circuits.md)
npm run compile          # contracts and TypeChain bindings
npm test                 # circuit tests, then contract tests (LedgerAnchor included)
```

Deploying the ledger anchor to Sepolia and anchoring the ledgers is described in
[docs/anchoring.md](docs/anchoring.md). Secrets are read from Hardhat's encrypted keystore, never
from committed files.

## Useful scripts

Run from the repository root.

| Script                          | What it does                                                                           |
| ------------------------------- | -------------------------------------------------------------------------------------- |
| `npm run dev` / `npm run build` | Frontend dev server / production build                                                 |
| `npm run pipeline:check`        | Everything CI runs for the Python side                                                 |
| `npm run check`                 | Everything CI runs for the JavaScript side                                             |
| `npm run lint`                  | ESLint (TypeScript + TSDoc) and Solhint (Solidity + NatSpec)                           |
| `npm run format`                | Format everything with Prettier                                                        |
| `npm run typecheck`             | `tsc` in every workspace                                                               |
| `npm run zk:build`              | Circuit pipeline: compile → witness → Groth16 setup → Solidity verifier → sanity proof |
| `npm run compile`               | Compile Solidity with Hardhat (also generates TypeChain bindings)                      |
| `npm test`                      | Circuit tests, then contract tests                                                     |

## Contributing

Conventions (commit messages, branches, documentation standards, the English-only rule) are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

The code is under the [MIT License](LICENSE); the documentation and the data RiverEtch produces
(`docs/`) are under [CC BY 4.0](LICENSE-docs). Third-party data keep their own terms. The Solidity
verifiers that snarkjs generates (never committed) carry a GPL-3.0 header.
