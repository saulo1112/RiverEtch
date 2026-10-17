# TerraChain

**Satellite water-quality estimates, validated against river gauges, with a record nobody can
quietly rewrite.**

TerraChain reads rivers from free satellite imagery (Sentinel-2 and Landsat). It turns each clear
pass into water-quality values with a stated error. Every value was tested once, on years its model
never saw, against a USGS gauge. Each pass is sealed as a record (the SHA-256 of its content) and
chained in an append-only ledger, so anyone can recompute it from public data and see that it has not
changed.

Built for the IEEE ClimateChain Global Hackathon (October 5–25, 2026), Track 4: climate data and
monitoring.

## Who it is for

A water-quality analyst at an environmental agency. They need an independent estimate they can cite,
and they need to show it was not adjusted after the fact. The gauge is the referee: TerraChain
publishes a value only where a gauge validated its model. Every record says which model card
produced it.

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
5. **Check.** After each run, the estimates are compared with the gauge's own readings
   (report-only). That shows whether the error holds on new data.

The daily run is a scheduled task (`pipeline/scripts/reach-run.ps1`). It reads public data only.

**Anchored on Ethereum (Sepolia).** `contracts/src/LedgerAnchor.sol` stores each ledger's head
(the SHA-256 of its last line, which commits to every line above it) with the block's time. The
reach's owner anchors from the web app with a wallet. **Verify this record** then reads the anchor
without a wallet: anchored at block N, recorded after the last anchor, or changed since. An anchor
proves the ledger's state from its own date on, never before. See
[docs/anchoring.md](docs/anchoring.md).

## Limits (read these before the numbers)

- **Clouds:** about three passes in four are lost to them (72–76 % in 2026).
- **Validated only at the gauge:** a value with a unit is published only at a validated gauge's
  window. The per-pixel map along the reach is relative (NDTI) and not validated.
- **The live check raises two warnings:**
  - At Belle Chasse the error holds on new data (18.9 %), but the 90 % intervals covered 13 of 18
    values.
  - The Platte overestimated six provisional summer values by 1.5–2×.
  - Both are reported, not hidden: see [The reaches in operation](docs/water-quality/report.md).
- **Timing:** the 2026 records up to 2026-10-12 were produced in a batch after their gauge values
  were public. What they prove is that the model card was frozen and committed first, and that the
  pipeline reads no gauge value to make an estimate. The strictly prospective check starts with the
  passes after the cards' commit.
- **A seal shows a record has not changed, not that it is right.** Correctness comes from the locked
  tests and the live check.
- **Our own process rejected our first pitch.** TerraChain started on Colombian rivers. IDEAM's
  point samples met too few clear scenes to validate any model, so no Colombian value is published.
  Those rounds stay in the [preregistration](docs/water-quality/preregistration.md) with every
  attempt counted.

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

## Repository structure

```text
.
├── pipeline/   Python 3.12 (uv): screening, water-quality validation (`quality`), reach records (`reach`)
├── web/        Vite + React: the globe, the cases and the case view (map, charts, record verification)
├── contracts/  Hardhat 3: the ledger anchor (LedgerAnchor, Sepolia) and a ZK toolchain scaffold
├── docs/       the water-quality report and preregistration, the record schema, the decision log
└── .github/    CI: every result is recomputed and checked against its MANIFEST
```

**Key documents:**

- **Results:** [report](docs/water-quality/report.md), [preregistration](docs/water-quality/preregistration.md)
  and [results](docs/water-quality/results/results.md).
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
| [circom](https://docs.circom.io/getting-started/installation/) | 2.2.3                                  | the circuit scaffold only                        |

### Run the web app

```bash
git clone https://github.com/saulo1112/Climate_Change_IEEE.git
cd Climate_Change_IEEE
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
```

`reach run`, `reach thermal` and `reach check` make new records from public data and compare them
with the gauges. See [docs/water-quality/reach/README.md](docs/water-quality/reach/README.md).

### Run every check

```bash
npm run check            # format, lint, circuits, compile, types, all tests, frontend build
npm run pipeline:check   # ruff format + lint, mypy --strict, pytest
```

### The contracts

```bash
npm run zk:build         # demo circuit → Groth16 setup → Solidity verifier (see docs/zk-circuits.md)
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

Not chosen yet. Note that the Solidity verifiers generated by snarkjs carry a GPL-3.0 header.
