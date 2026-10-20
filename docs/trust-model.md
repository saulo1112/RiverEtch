# Trust model

What RiverEtch asks you to trust, what you can check yourself, and what nothing here proves.

## The pieces

- **A record** is one satellite pass: its estimate, its interval, the model card and the code commit
  that produced it. Its **seal** is the SHA-256 of its canonical JSON: change one digit and the seal
  no longer matches.
- **A ledger** lists a reach's records in order. Each line names the SHA-256 of the line before, so
  the last line's hash (the **head**) commits to every line above it.
- **A model card** is the frozen model of a reach and a target. Each record names the card's hash.
- **The frozen-artifacts ledger** (`docs/ledgers/frozen-artifacts.jsonl`) lists, with their hashes,
  the preregistration, the results' MANIFEST, the five model cards and the scoring rule
  ([prospective.md](water-quality/prospective.md)).
- **An anchor** stores a ledger's head and line count on Ethereum Sepolia, with the block's time.
  The anchoring log (`docs/ledgers/anchors.jsonl`) lists every anchor and its transaction; it is
  rebuilt from the chain, not typed.

## Who can do what

- **The contract** ([LedgerAnchor.sol](../contracts/src/LedgerAnchor.sol), at
  [`0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762`](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  on Sepolia) has one owner, fixed when it was deployed (`immutable`):
  `0x0c9B476C9C12479657C33780CD0aBB7E00f67F1d`.
- **The owner can only add anchors.** The contract has no function to edit or delete one, and a
  ledger's anchors must grow: a new anchor needs more lines than the last.
- **If the owner's key is lost,** no new anchor can be made. The existing ones stay readable.
- **If the key is stolen,** the thief could anchor a false head with more lines. That is visible:
  the false head matches no published ledger, and every earlier anchor stays as it was.
- **The repository's owner can rewrite the repository,** including its history. The anchors bound
  that: a ledger changed above an anchored line no longer matches its anchor, and the web app says
  so.

## Where: Sepolia

Sepolia is a public Ethereum test network. Anyone can read it for free, with no wallet. It is not
mainnet: its ether has no value and its validators are a smaller, permissioned set, so an anchor
there is a public, checkable timestamp, not a mainnet-grade guarantee.

## What an anchor proves

That the ledger, up to the anchored line, existed unchanged from the anchor's block time on:

- the first four ledgers (Sentinel-2 and Landsat records of the two demo reaches) from
  2026-10-16 01:05:12 UTC, block 11924112;
- the scoring rule, the model cards, the preregistration and the MANIFEST from **T0**, the block
  time of the first anchor of the frozen-artifacts ledger (listed in `docs/ledgers/anchors.jsonl`).

## What it does not prove

- **Anything before its own date.** The 2026 records sealed so far were made in batch runs
  (2026-10-12 to 2026-10-15), after their gauge values were public: those passes are
  **retrospective** (a backtest).
- **That an estimate is right.** That comes from the locked tests (scored once, on years the model
  never saw) and from the scoreboard.
- **That the gauge is right.** The USGS reports it. Provisional values can still be revised; the
  scoreboard labels them.
- **That no pass was skipped.** Each record names its scene. Anyone can list the passes over a
  reach on [Earth Search](https://earth-search.aws.element84.com/v1) and compare.

## The prospective scoreboard

The rule ([prospective.md](water-quality/prospective.md), rule v1) was written and frozen before
any prospective pass. A pass is **prospective** only when:

1. it was acquired after T0, so its model and the rule were already anchored;
2. its record (the claim) was sealed and its ledger line anchored before RiverEtch read the gauge;
3. the gauge is read at least 12 hours after the pass.

`reach score` appends each outcome to the reach's outcomes ledger (itself anchored as
`terrachain:<reach>:outcomes`). A first read is never replaced; an approved re-read is a new line.
The scoreboard gives counts ("k of n inside the expected range"), never percentages, until there
are 20 passes. A count of 0 is shown as 0.

## Why the labels read `terrachain:`

The project was first called TerraChain. The subjects of the first anchors are the keccak256 of
`terrachain:<reach>:<ledger>`; a new prefix would leave those records unanchored, so every label
keeps it ([D22](decisions.md)).

## Check it without trusting us

| What                                 | How                                                                                     |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| A record's seal, its chain, its card | **Verify this record** in the web app, or `uv run climate-pipeline reach verify`        |
| A record's anchor                    | **Verify this record** (no wallet), or `anchorAt(subject, index)` on Etherscan          |
| The anchoring log                    | `npx tsx scripts/anchor-log.ts` (from `contracts/`) rebuilds it from the contract state |
| The frozen artifacts                 | `uv run climate-pipeline ledger verify`                                                 |
| Every result, to the last digit      | `uv run climate-pipeline quality verify` (CI runs it on every change)                   |
| That the passes are all there        | List the scenes on Earth Search and compare with the ledger's `sceneId`s                |

## Open items (2026-10-19)

- The contract's source is not yet verified on Etherscan or Sourcify: the page shows its bytecode
  only. The committed source does reproduce that bytecode: `contracts/scripts/bytecode-check.ts`
  checks it with no key ([anchoring](anchoring.md#verifying)).
- The repository is private, so the code commits the records cite cannot be opened from outside.

T0 is set: the frozen-artifacts ledger (8 lines) was anchored at block 11951391,
2026-10-19 23:21:00 UTC (transaction
`0xfc954ab0d9abe6a417c7a5b388faac4e8c4489700921125e34cbb1f506539517`).
