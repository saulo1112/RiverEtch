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
- **A Bitcoin timestamp** is an [OpenTimestamps](https://opentimestamps.org) proof that a ledger
  head existed by a Bitcoin block's time (`docs/ledgers/ots/<label>.<lines>.ots`). The daily run
  makes one for every new head, with no key.
- **A head signature** is an ML-DSA-65 signature (FIPS 204, post-quantum) of a ledger head, its
  line count, its label and the signing time (`docs/ledgers/signatures.jsonl`). The public key is
  [`docs/keys/ml-dsa-65.json`](keys/ml-dsa-65.json), frozen in the frozen-artifacts ledger (line
  11), whose anchor covering it is at block 11952275 (2026-10-20 02:19:48 UTC).

## Why a blockchain, and why two

A seal shows that a reading was not changed. It needs a date that RiverEtch itself cannot move.

- **A signed git tag** says who signed, not when: its date is the signer's own claim, and the
  repository's owner can delete or move the tag.
- **A timestamping service** (RFC 3161) gives a date, but from one company that has to be trusted
  and has to keep its records.
- **A public chain** gives a date that no single party sets, that anyone can read without asking,
  and that nobody, RiverEtch included, can edit or delete.

RiverEtch uses two chains, for different things. The Sepolia contract takes an anchor in its next
block (a slot is 12 seconds, [ethereum.org](https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/)),
enforces its rules (only the owner adds; a ledger's anchors only grow) and answers queries
(`anchorAt`). The Bitcoin timestamp needs no key and sits on a main network, but its proof is
complete only once a later Bitcoin block includes it; the daily run upgrades it then.

**What a chain cannot do.** It dates a reading; it does not make it right. Three separate things
answer three questions:

1. **Was it changed after its date?** The seal, the ledger and the anchors.
2. **How was it computed?** The record names its inputs: its scene (public, on Earth Search), its
   model card's hash and its code commit, so its numbers can be computed again by running the
   pipeline at that commit. There is no one-step command for that yet.
3. **How often is such a reading right?** The locked tests, scored once on years the model never
   saw, and the scoreboard against USGS stations.

## Who can do what

- **The contract** ([LedgerAnchor.sol](../contracts/src/LedgerAnchor.sol), at
  [`0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762`](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  on Sepolia) has one owner, fixed when it was deployed (`immutable`):
  `0x0c9B476C9C12479657C33780CD0aBB7E00f67F1d`.
- **The owner can only add anchors.** The contract has no function to edit or delete one, and a
  ledger's anchors must grow: a new anchor needs more lines than the last.
- **The owner cannot be changed.** There is no function for it: a new key would need a new
  contract, whose anchors would start from none. The old contract's anchors stay readable.
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

**Why Sepolia, not mainnet or a layer 2:** RiverEtch is a prototype, and anchoring on Sepolia
costs nothing of value. The date on a main network comes from Bitcoin instead: each head's
OpenTimestamps proof, which needs no key.

**When an anchor counts.** The anchoring script waits for the transaction's block (one
confirmation). Sepolia runs Ethereum's proof of stake, where a block is final after two epochs,
"about 15 minutes" ([ethereum.org](https://ethereum.org/en/roadmap/single-slot-finality/));
before that it could in principle be reverted. The prospective rule counts the anchor's block time
without waiting for finality: the first two scored passes had their gauges read on 2026-10-21 at
17:04:50 UTC, about 3 minutes after their anchor (block 11963767, 17:01:36 UTC), which has been
final since. Had that block been reverted, the outcome lines would name a block that no longer
holds the anchor, and `anchorAt` on the contract would show it.

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

Rule v2 ([prospective-v2.md](water-quality/prospective-v2.md)), frozen and anchored at block
11952275 (2026-10-20 02:19:48 UTC), applies to passes acquired after that anchor. It accepts a
second kind of commitment besides a Sepolia anchor: a Bitcoin timestamp of a head covering the
claim, confirmed in a block. Bitcoin block times can run up to 2 hours ahead of the network's
clock, so the gauge is read no earlier than 2 hours after that block's time, and only once the
block has been seen. Each outcome line names its rule and its commitment.

**The honest limit stays:** sealing a claim before scoring it does not prove that the gauge value
was unknown when the claim was made. The USGS publishes readings within minutes; what the
commitment proves is that the claim did not change after it.

## Attacks, what stops them, and how to check

| Attack                                         | What stops it                                                                                                                                                                                                                                | How to check                                                                                       |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Change a value in a sealed record              | Its seal (SHA-256 of the canonical JSON) no longer matches                                                                                                                                                                                   | **Verify this record** ("Change one number first" shows it failing); `reach verify`                |
| Change a value in a copy sent outside the app  | The copy's values no longer match the sealed record of its pass; a recomputed seal is in no ledger line                                                                                                                                      | **Check a file you were sent** (a record's JSON or the series' CSV), in the browser                |
| Edit, remove or reorder a ledger line          | Each line names the SHA-256 of the line before: every later link breaks                                                                                                                                                                      | Step 3 of **Verify this record**; `reach verify`                                                   |
| Rewrite a whole ledger, consistently           | Its head no longer matches the anchored head on Sepolia, the Bitcoin timestamp or the signed head                                                                                                                                            | Steps 5 to 7 of **Verify this record**                                                             |
| Swap a model card after seeing results         | Each record names its card's hash; the cards are in the frozen-artifacts ledger, anchored before the passes they score                                                                                                                       | `ledger verify`; step 4 of **Verify this record**                                                  |
| Retune a test after seeing its result          | Each test is preregistered, frozen and anchored before it runs, and run once; results are recomputed from committed inputs                                                                                                                   | The anchor's block time against the results' run time; `quality verify`, `quality transfer-verify` |
| Backdate a prospective claim                   | It counts only if committed (Sepolia anchor, or a Bitcoin block plus 2 hours) before the gauge read                                                                                                                                          | Each outcome line names its commitment; compare the block time with `gaugeReadUtc`                 |
| Delete or edit an anchor                       | The contract has no such function; a ledger's anchors must grow                                                                                                                                                                              | `anchorAt(subject, index)` on Etherscan                                                            |
| Steal the owner's Ethereum key                 | The thief can only append anchors with more lines. A false head matches no published ledger and has no signature by the frozen ML-DSA key                                                                                                    | Compare each anchor with the ledger and with `signatures.jsonl`                                    |
| Take over the daily run (GitHub)               | It holds no key: it can publish a record but not anchor or sign it. Anything published after the last anchor shows as "not anchored yet"                                                                                                     | The anchor and signature steps of **Verify this record**                                           |
| Seal false readings from the start (the owner) | Nothing on chain: an anchor dates whatever it is given. Each record names its public scene, its frozen card and its code commit, so its numbers can be computed again; prospective passes are scored against the USGS station after the seal | Run the pipeline at the record's commit on its scene; the scoreboard                               |
| Leave out an awkward pass                      | Each record names its scene, and skipped passes have their reason in the run's state                                                                                                                                                         | List the scenes over the reach on Earth Search and compare with the ledger's `sceneId`s            |
| Lie about Bitcoin through a block explorer     | The web app asks two independent explorers (mempool.space, blockstream.info), which must agree                                                                                                                                               | Any Bitcoin node, or `ots verify` on the proof file                                                |
| Lie about Sepolia through an RPC node          | With a wallet connected on Sepolia, the app reads the anchors through the wallet's own connection and says so                                                                                                                                | Connect a wallet; or read the contract on Etherscan                                                |

## Post-quantum: what a quantum computer would and would not break

- **The seals, the ledgers and the Bitcoin timestamps are hash-based.** SHA-256 (records, ledger
  lines, heads, the OpenTimestamps path) and keccak256 (anchor subjects) have no known quantum
  break. Grover's algorithm at best halves the exponent of a preimage search, leaving about 2^128
  work for SHA-256. A Bitcoin timestamp depends on SHA-256 and the block's place in the
  proof-of-work chain, which is SHA-256 too; it involves no signature. These carry the "not edited
  since" guarantee.
- **The Sepolia anchors depend on ECDSA (secp256k1).** Every anchoring transaction exposes the
  owner's public key on chain. Shor's algorithm on a large enough quantum computer would recover
  the private key, and the attacker could then append false anchors (with more lines). It could not
  edit or delete the existing ones, and its heads would match no published ledger.
- **What ML-DSA-65 adds:** post-quantum authorship of a head. A signature by the frozen key says the
  key's holder published that head, and a quantum attacker who recovers the Ethereum key still
  cannot make one. It is a signature, not a timestamp: `signedAt` is the signer's own claim. The
  time comes from Bitcoin and Sepolia.
- **Why the signature is checked off chain:** the contract was deployed (2026-10-16) before the
  signatures were added (the key was frozen on 2026-10-20), and it cannot be changed, so it does
  not check them. Checking them in a contract would mean a new contract and every ledger anchored
  again. A contract that did check them would _refuse_ a false head anchored with a stolen or
  quantum-broken Ethereum key; here such a head is only _detected_, by its missing signature.
- **What stays classical:** Ethereum's transactions and consensus, and Bitcoin's coin signatures
  (not its block headers). A break there is outside RiverEtch's control.
- **Implementations:** the pipeline signs with [pqcrypto](https://pypi.org/project/pqcrypto/) 1.0.0
  (bindings to Backbone's Rust crates, which by its own description have had no formal security audit); the browser
  verifies with [@noble/post-quantum](https://github.com/paulmillr/noble-post-quantum) 0.7.1
  (self-audited; it makes no constant-time claim). Both pass NIST's ACVP sigVer vectors for
  ML-DSA-65 (external interface, pure: `pipeline/tests/fixtures/ml-dsa/`), and each verifies the
  other's signatures. Only the owner's machine signs, so a side channel in signing matters there
  only.
- **Limits:** one key, held by one person, with no revocation beyond freezing a new key file with
  its own anchor. The ledgers are short (1 to 93 lines on the `data` branch on 2026-10-21) and are
  replayed in full, so there is no Merkle tree (one would matter for proofs of single lines in long
  ledgers: future work).

**If Sepolia goes away.** A proposal of 27 May 2026 (Ethereum Magicians,
[Sepolia testnet replacement and sunsetting](https://ethereum-magicians.org/t/sepolia-testnet-replacement-sunsetting/28647))
would deprecate Sepolia and sunset it fully in Q2 or Q3 2027. It is a proposal, not a decision. If
it happens, the anchors can no longer be read from a live node; the Bitcoin timestamps and the
signatures stay checkable.

**If this repository goes away.** The records, the ledgers and the proofs are kept in this
repository (its `main` and `data` branches) and nowhere else yet. The anchors and the timestamps
would stay, but there would be nothing left to check them against. A copy in a public archive
(with a DOI) has not been made yet.

## Why the labels read `terrachain:`

The project was first called TerraChain. The subjects of the first anchors are the keccak256 of
`terrachain:<reach>:<ledger>`; a new prefix would leave those records unanchored, so every label
keeps it ([D22](decisions.md)). The contract's comments say TerraChain too, and its licence line
reads `UNLICENSED`: both are as deployed, since changing any character of its source would break
its verified match (see the open items). The repository's [LICENSE](../LICENSE) releases the file
under MIT.

## Check it without trusting us

| What                                 | How                                                                                     |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| A record's seal, its chain, its card | **Verify this record** in the web app, or `uv run climate-pipeline reach verify`        |
| A record's anchor                    | **Verify this record** (no wallet), or `anchorAt(subject, index)` on Etherscan          |
| A head's Bitcoin timestamp           | **Verify this record**; `uv run climate-pipeline ledger proofs`; or `ots verify`        |
| A head's signature                   | **Verify this record**; `uv run climate-pipeline sign verify`                           |
| The anchoring log                    | `npx tsx scripts/anchor-log.ts` (from `contracts/`) rebuilds it from the contract state |
| The frozen artifacts                 | `uv run climate-pipeline ledger verify`                                                 |
| Every result, to the last digit      | `uv run climate-pipeline quality verify` (CI runs it on every change)                   |
| That the passes are all there        | List the scenes on Earth Search and compare with the ledger's `sceneId`s                |

## Open items (2026-10-21)

- The contract's source is verified: an exact match on
  [Sourcify](https://sourcify.dev/server/repo-ui/11155111/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  (creation and runtime bytecode, 2026-10-21 22:28:09 UTC) and on
  [Etherscan](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762#code)
  ("Source Code Verified", exact match). It still reads TerraChain and
  `SPDX-License-Identifier: UNLICENSED`, as deployed: changing even a comment would change the
  compiled metadata and break the match. `contracts/scripts/bytecode-check.ts` checks the same
  with no key ([anchoring](anchoring.md#verifying)).
- The repository is private, so the code commits the records cite cannot be opened from outside.

T0 is set: the frozen-artifacts ledger (8 lines) was anchored at block 11951391,
2026-10-19 23:21:00 UTC (transaction
`0xfc954ab0d9abe6a417c7a5b388faac4e8c4489700921125e34cbb1f506539517`).
