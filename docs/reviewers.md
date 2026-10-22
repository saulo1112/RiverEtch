# For reviewers

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
- **Values with a unit only at a validated gauge.** Along the river, each 600 m stretch gets a
  class, never a value; no station measures those stretches.
- **Clouds** hide about three passes in four (72–76 % in 2026).
- **The 2026 records sealed before T0 are retrospective:** they were sealed after their gauge values
  were public. Only passes after T0 (the anchor of the scoring rule) can count as prospective.
- **Station values are often provisional.** The USGS may still revise them; the app says so.
- **Sepolia is a test network,** not mainnet.
- **The two gauged demo reaches are the best two of ten stations** (on eight rivers). The median
  error over the nine rated is 33.1 % (**How it works → Does it work?**).

## The 3-minute path

Open [river-etch.vercel.app](https://river-etch.vercel.app). No account, no wallet.

1. **Hero:** choose a case. The Mississippi at Belle Chasse and the Platte at Louisville have a
   station; the Mississippi above Natchez (St. Joseph) and the Fırat at Birecik (Türkiye) have
   none.
2. **Tour** (top left, beside Back): eight steps, each pointing at the control it explains; Esc
   ends it.
3. **The case file** (top left): on a gauged reach, the value, its expected range (?), its level
   (?), "Sealed" and the anchor date, and how far off the model tends to be beside guessing the
   river's usual value. On a reach with no station, the class with the tag "Satellite only"; its
   (?) gives the error measured on rivers the model never saw (at the Fırat: not measured), and
   the case file shows how the pass compares with the river's own past. At the Fırat, published
   measurements of the river at Birecik, labelled as looked up after seeing the result. Under
   the value, the reading spot's stretch and its arrows: move it upstream or downstream (or drag
   the amber spot on the map, or click the river) and the panels follow that stretch, as a class.
4. **Verify this record** (right), below.
5. **Change one number first**, type another number (or pick another class), then verify again:
   the seal breaks; put the sealed value back and it matches again.
6. **Check a file you were sent** (under the record): the record's JSON from its details, or the
   series from Export, edited or not; the browser names any value that differs from the sealed
   record.
7. **Along the river** (bottom tabs): the year's passes along the whole reach, one column per
   pass and one row per 600 m stretch, coloured by class (turbidity, or water temperature where the
   reach has it); hover a stretch to mark it on the map, click it to move the reading spot there.
   The **Turbidity** tab beside it has a year menu: an earlier year is the station window, read
   by the same frozen model and labelled in sample or locked test.
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

Steps 5 and 6 read the daily run's published files on the `data` branch. A record the daily run
made after the owner's last anchor and signature shows "not anchored yet" and "not signed yet"
until then, and its Bitcoin proof waits a few hours for its block.

Without the app:

- On chain: the contract
  [`0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762`](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762)
  on Sepolia; every anchor and its transaction are in
  [`docs/ledgers/anchors.jsonl`](ledgers/anchors.jsonl).
- From a clone (see the [README](../README.md#quick-start)):

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

## Questions a blockchain reviewer will ask

Each answer is short; the [trust model](trust-model.md) has the detail.

- **Why a blockchain, not a signed git tag?** A tag's date is the signer's own claim, and the
  repository's owner can move it. A public chain's date is set by no single party, and nobody,
  RiverEtch included, can edit it ([why a blockchain](trust-model.md#why-a-blockchain-and-why-two)).
- **What is on chain?** For each ledger: its head (the hash of its last line), its line count, and
  the block's time and number, every anchor kept. Only the owner adds, and a ledger's line count
  must grow. No reading itself goes on chain. The contract's source is
  [verified on Etherscan](https://sepolia.etherscan.io/address/0xe5d12E7C63041537ffcb3dd258aD69BF345Fe762#code).
- **If a seal does not make a reading right, what does it add?** It shows the reading was not
  changed after its date. How it was computed is named in the record (its scene, its card, its code
  commit); how often it is right comes from the locked tests and the scoreboard.
- **What stops the owner sealing false readings from the start?** Nothing on chain. Each record's
  inputs are public, so its numbers can be computed again, and prospective passes are scored
  against USGS stations after the seal
  ([attacks](trust-model.md#attacks-what-stops-them-and-how-to-check)).
- **Why Sepolia?** A prototype: anchoring costs nothing of value. The date on a main network comes
  from Bitcoin (OpenTimestamps), which needs no key ([Sepolia](trust-model.md#where-sepolia)).
- **When is an anchor final?** About 15 minutes after its block. The first two scored passes were
  read 3 minutes after their anchor; its block has been final since
  ([Sepolia](trust-model.md#where-sepolia)).
- **Can the owner's key be changed if it leaks?** No: the owner is fixed in the contract. A thief
  could only add anchors with more lines, whose heads match no published ledger and carry no ML-DSA
  signature ([who can do what](trust-model.md#who-can-do-what)).
- **Why is the ML-DSA signature not checked in the contract?** The contract was deployed before the
  signatures existed and cannot be changed. A contract that checked them would refuse a false head;
  here a false head is detected
  ([post-quantum](trust-model.md#post-quantum-what-a-quantum-computer-would-and-would-not-break)).
- **How do I know the ML-DSA key is yours?** Its file is line 11 of the frozen-artifacts ledger,
  anchored at block 11952275 (2026-10-20 02:19:48 UTC), before the earliest signature's stated
  time (05:50:57 UTC that day).
- **Do I have to trust your block explorers or RPC node?** No. Connect a wallet to read Sepolia
  through your own connection; check a Bitcoin proof with `ots verify` or your own node.
- **Why does the contract say TerraChain and `UNLICENSED`?** They are as deployed: changing any
  character of the source would break its verified match. The repository's
  [LICENSE](../LICENSE) releases the file under MIT.
- **Why no Merkle tree?** The ledgers are short (93 lines at most) and are replayed in full.
- **Is zero-knowledge used?** No. An unused scaffold from the first draft was removed
  ([D24](decisions.md)); it stays in the git history.
- **What if this repository goes away?** The records are kept only here for now. The anchors and
  timestamps would stay, with nothing to check them against.

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
