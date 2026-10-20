# Prospective scoring: rule v2 (written 2026-10-20 UTC, before any pass it applies to)

Rule v2 keeps rule v1 (`prospective.md`) and adds one way to commit a claim before the gauge is
read: a Bitcoin timestamp (OpenTimestamps) of the claim's ledger head. It needs no key, so the
daily run can commit claims without the owner's machine. Its SHA-256 is a line of
`docs/ledgers/frozen-artifacts.jsonl`, whose head is anchored on Ethereum Sepolia
(`terrachain:riveretch:frozen-artifacts`). It is never edited: a change is a new file, rule v3,
with its own line and anchor.

## 1. Which passes it applies to

- **T0v2** is the block time of the first anchor of `terrachain:riveretch:frozen-artifacts` whose
  ledger lists this file.
- Rule v2 applies to passes **acquired after T0v2**. A pass acquired after T0 (rule v1) and before
  T0v2 keeps rule v1. A pass acquired before T0 stays retrospective.
- Everything rule v1 says about the claim, the gauge's value at the overpass, approval, the
  12-hour lag, "no gauge value", abstained claims, the score, the outcomes ledger and the
  reporting (counts until 20 scored passes, prospective and retrospective never added) applies
  unchanged. Rule v1's extreme days (its section 5) are unchanged.

## 2. Committed before the gauge was read

A claim (a sealed record and its line in the reach's ledger) counts as committed when **either**:

- **(A) Sepolia, as rule v1:** an anchor of the ledger covering the claim's line is mined; or
- **(B) Bitcoin:** an OpenTimestamps proof of a head of that ledger, whose line count covers the
  claim's line, is confirmed in a Bitcoin block. The head is the SHA-256 of the ledger's last
  line (each line names the one before, so the head commits to every line above it). The proof is
  committed beside the ledger, and its block is the first Bitcoin block that attests it.

The gauge is read no earlier than the later of:

- 12 hours after the overpass (rule v1), and
- for (B), **2 hours after the attesting Bitcoin block's header time**, and only once RiverEtch has
  seen that block confirmed. Seeing the block first makes the order hold by construction. The
  margin is for anyone who checks it from the timestamps alone: a header time is not the moment the
  block was mined. It only has to exceed the median of the previous 11 blocks (so it can lag by
  about an hour), and it may run up to 2 hours ahead of the network's clock.

The claim is scored only once it is committed by (A) or (B).

## 3. What each outcome records

Each outcome line adds to rule v1's fields:

- `rule`: `v1` or `v2`, and the SHA-256 of the rule's file;
- `commitment`: for (A) the Sepolia block and transaction; for (B) the Bitcoin block height, its
  header time and the path of the `.ots` proof.

## 4. What it proves, and what it does not

- **Proves:** the ledger, up to the claim's line, existed before the attesting Bitcoin block was
  mined. Bitcoin's proof of work and SHA-256 hash paths prove it, with no signature and no key.
  It needs neither Sepolia nor RiverEtch's own servers.
- **Does not prove:** that the gauge value was unknown when the claim was sealed (the USGS
  publishes provisional values within minutes), or that the estimate is right. That is the same
  limit as rule v1.
- **Trust in the calendars:** the public OpenTimestamps calendars aggregate the stamps. A calendar
  can delay or drop a stamp; it cannot forge one. A dropped stamp means the claim waits for
  route (A), or is not committed.
