# RiverEtch: final-week plan (2026-10-19 → 2026-10-24)

## Context

The IEEE ClimateChain submission is due **Saturday 2026-10-24**. Four things should be done before then:

- make the chain do something a database cannot ("commit before the answer, then a public scoreboard");
- show the climate component with real numbers and records;
- make every percentage readable by a non-specialist;
- clean up what judges will open first.

This document is planning only. It was written on Monday 2026-10-19 (Bogotá, UTC−5) after reading the repository, the chain and the public data sources. **Nothing has been changed** besides this file.

How to read the tags:

- **VERIFIED** is followed by the evidence (a file and line, or a command and its output, with the date).
- **ASSUMED** is followed by how to verify it.

Times are Bogotá unless marked UTC.

> **On approval:** create `docs/plans/final-week-plan.md` with exactly this content (the folder does
> not exist yet), print a 15-line summary in the terminal, and stop. No other file changes.

---

## 1. Findings

### F1. Provisional vs approved gauge values in the current scoring

- **Lock box (the levels): approved only.** VERIFIED.
  - Evidence: `pipeline/water-quality.yaml:116-117` (`approval: Approved`, `exclude_qualified: true`) and `docs/water-quality/report.md:151-152`.
- **The overpass value.** VERIFIED (`water-quality.yaml:118-119`).
  - It is the median of approved values within ±30 min of the pass.
  - Otherwise, the nearest approved value within ±60 min.
- **`reach check` (the 2026 comparison): approved first, else provisional, labelled.** VERIFIED (`pipeline/src/climate_pipeline/reach/check.py:34`, `:129-136`).
  - Result in 2026: Belle Chasse 0 approved / 18 provisional; Platte 2 / 6 (`report.md:195-198`).
- **USGS provisional values are public within minutes.** VERIFIED (2026-10-19 19:43 UTC).
  - `latest-continuous` returned 63680 values from 19:30 UTC (07374525, 35.7 FNU) and 19:15 UTC (06805500, 41.3 FNU), both `Provisional`.
- **Approval takes months.** ASSUMED.
  - The evidence points that way: Belle Chasse has no approved 2026 pair.
  - To verify: the approval field of the 2026 rows in `docs/water-quality/reach/*/examples/checks/checks.csv`.
- **Consequence:** any prospective score before Oct 24 can only use provisional values.

### F2. How often the pipeline can realistically produce a new estimate

- **Sentinel-2 L2A over the reaches (Earth Search, 1–19 Oct).** VERIFIED (STAC query, 2026-10-19).
  - Belle Chasse: acquisitions on Oct 1, 3, 6, 8, 11, 13 (two satellites), 16 and 18.
  - Platte: Oct 5, 10, 12 and 15.
  - Published 4.2–17.1 h after acquisition, typically about 5 h.
- **Landsat C2 L2.** VERIFIED (same query).
  - Belle Chasse: Oct 3 and 11. Platte: Oct 5.
  - Published about 19.5 h after acquisition; one item took 154.7 h.
- **Usable after clouds in 2026.** VERIFIED (committed ledgers; `report.md:183-190`).

  | Reach        | Sentinel-2 records (date range) | With a value | Usable passes           | Landsat temperature records |
  | ------------ | ------------------------------- | ------------ | ----------------------- | --------------------------- |
  | Belle Chasse | 33 (01-01..10-11)               | 29           | about 1 every 8.6 days  | 19                          |
  | Platte       | 16 (02-12..10-10)               | 13           | about 1 every 17.7 days | 16                          |

- **Usable passes in earlier years (gauge-matched Sentinel-2 scenes, 2019–2025).** VERIFIED.
  - Belle Chasse: 39–53 a year, median 48. Platte: 28–35 a year, median 31.
  - Source: `docs/water-quality/inputs/usgs-v5/turbidity.csv`, counted 2026-10-19.
- **The daily run is not running.** VERIFIED.
  - `Get-ScheduledTask` shows no RiverEtch task.
  - There is no `runs.log` under `pipeline/out/reach/`.
  - The local ledgers end with the 2026-10-12 run.
  - Yet `README.md:100` and `report.md:212-213` say it runs daily. Either register it (WP2) or correct the text (WP7).
- **Scenes not yet processed** (all retrospective: their gauge values are already public). VERIFIED (STAC).
  - Belle Chasse: Oct 13, 16 and 18, with tile cloud cover of 0–13 %.
  - Platte: Oct 12 (20 %) and Oct 15 (100 %).
- **Expected prospective passes between Oct 20 and the Oct 23 freeze.** ASSUMED, from the 5-day orbit pattern above.
  - Platte Sentinel-2: about Oct 20 17:22 UTC.
  - Belle Chasse Sentinel-2: about Oct 21 16:55 UTC and Oct 23 16:45 UTC.
  - Platte Landsat: about Oct 21 17:06 UTC.
  - Expected number of usable ones, at about 25 % usable: **about 1 (range 0–4).** The plan must work with 0.
  - To verify each morning: run the STAC query, or `reach run`'s summary.

### F3. How the 2026 records were generated and timestamped

- **Every 2026 record was made in one batch run, after its gauge value was public.** VERIFIED (`createdUtc` in the committed ledgers).

  | Ledger                         | Run time (`createdUtc`) | Lines | Passes covered    |
  | ------------------------------ | ----------------------- | ----- | ----------------- |
  | Belle Chasse observations      | 2026-10-12T23:37:19Z    | 33    | 2026-01-01..10-11 |
  | Platte observations            | 2026-10-12T23:36:44Z    | 16    | 2026-02-12..10-10 |
  | Platte water temperature       | 2026-10-13T05:10:37Z    | 16    | —                 |
  | Belle Chasse water temperature | 2026-10-15T02:36:31Z    | 19    | —                 |
  - `createdUtc` is one value per run (`reach/run.py:593`, written at `:481-484`). A record carries no creation time of its own.
  - So **all 2026 records are retrospective (backtest)**. `README.md:119-122` already says so.

- **The cards were committed before the batch.** VERIFIED (`git log --diff-filter=A`).
  - Belle Chasse and Platte turbidity: 2026-10-12 15:55 (bc1a017).
  - Platte temperature: 10-13 (5e2a9ad). Belle Chasse temperature: 10-14 (132bdc5).
  - These are git times in a **private** repository whose owner can rewrite history. The first public timestamp is the anchor of 2026-10-16 01:05:12 UTC (block 11924112).
- **"The prospective check" is a misnomer under this week's definition.** VERIFIED (`report.md:172-174`, `:192-213`; `check.py:107`).
  - The report uses that name for the passes after the card's commit.
  - They were sealed after their gauge values were public, so they are retrospective. Relabel them "post-commit check (retrospective)".
- **`reach check` scores an unsealed note, not the sealed record.** VERIFIED (`run.py:639-647`, `check.py:51-57`).
  - It reads `checks/estimates.jsonl`, rounded to 4 decimals.
  - The sealed value (2 decimals) and its interval are not what gets scored. The scoreboard must score what was sealed.

### F4. Where model-card and preregistration hashes live

- **Records name each card by `modelCardSha256`.** VERIFIED (`quality/cards.py:167-177`; `reach/records.py:193`).
  - It is the SHA-256 of the card's compact, key-sorted JSON.
- **`docs/water-quality/results/MANIFEST` holds the file SHA-256 of every result and card.** VERIFIED.
  - 76 lines; for example, line 11 is the Belle Chasse turbidity card.
  - Its own SHA-256 was `d2e0538c…5d5a` on 2026-10-19.
- **The preregistration is pinned only by its git blob.** VERIFIED.
  - `results/provenance.json` records `preregistration_blob: 4af0c112…`, written by `quality/report.py:225`. The current file's blob is the same.
- **Neither card nor preregistration hash is on chain.** VERIFIED (F5: only 4 subjects anchored).
- **Constraint: do not edit `preregistration.md` this week.** VERIFIED.
  - `provenance.json` is in the MANIFEST (line 34) and `.json` files are verified (`calibration/report.py:35`).
  - A new blob would make `quality verify` fail in CI, which runs on any `docs/water-quality/**` change (`.github/workflows/quality.yml:7-18`).
  - New rules therefore go in a new file.

### F5. How anchoring works end to end, and what new subjects need

- **The contract.** VERIFIED (`contracts/src/LedgerAnchor.sol:64-67`, `:73-85`, `:105-116`).
  - It accepts any `bytes32` subject.
  - Only the immutable owner can anchor.
  - Line counts must strictly grow.
  - `anchorBatch` handles several ledgers in one transaction.
- **The head and the label.** VERIFIED (`web/src/features/chain/ledger.ts:36-38`, `:46-52`).
  - The head is the SHA-256 of the ledger's last raw line.
  - The label is `terrachain:<reach>:<ledger>`; the subject is its keccak256.
- **The script hard-codes 2 reaches × 2 ledgers.** VERIFIED (`contracts/scripts/anchor.ts:15-19`).
  - It sends one `anchorBatch` for the ledgers that grew (`:35-64`).
  - It prints the transaction but records it nowhere.
- **On chain today.** VERIFIED (`eth_call` via publicnode, 2026-10-19).
  - Four anchors, all in block 11924112 at 2026-10-16T01:05:12Z:

    | Ledger                         | Lines | Head        |
    | ------------------------------ | ----- | ----------- |
    | Belle Chasse observations      | 33    | 0xec67…e860 |
    | Belle Chasse water temperature | 19    | 0x91f9…8521 |
    | Platte observations            | 16    | 0xbf5a…f526 |
    | Platte water temperature       | 16    | 0x6052…a899 |

  - Each head equals the committed ledger's head.
  - Hermann has no anchor.
  - The owner is `0x0c9B476C9C12479657C33780CD0aBB7E00f67F1d`, the deployer named in `ignition/deployments/chain-11155111/journal.jsonl`, with 0.0463 SepoliaETH.
- **The transaction.** VERIFIED (Etherscan page, read 2026-10-19).
  - Etherscan lists one transaction, `0x19b4ac2e7ee64cdd8ee3622a053c46820fcbe6fc1b94330901c67860b2029eb0`.
  - Its selector `0x6f00486b` is `anchorBatch(bytes32[],bytes32[],uint64[])`, which I recomputed.
- **Cost per batch.** ASSUMED: a fraction of a milli-ETH. To verify: gasUsed × gasPrice of `0x19b4…` on Etherscan.
- **What a new subject needs: no contract change.**
  1. Write a JSONL ledger whose lines name `previousLineSha256`, the same format as `append_ledger` (`run.py:470-484`).
  2. Add `{label, path}` to `anchor.ts`.
  3. Run the script.

### F6. Does the lock box have enough extreme days?

The definitions below were fixed before counting. Only counts were computed, never an error.

- **Low flow:** a daily mean discharge at or below the 10th percentile of the gauge's approved days up to 2025-12-31.
- **High flow:** at or above the 90th percentile of the same days.
- **Warm:** a Jun–Sep daily mean water temperature at or above the 90th percentile of approved summer days 2002–2025.
  - Platte only: the Belle Chasse gauge has no temperature (`examples/climate.json` → `temperature: null`).

|                                              | Belle Chasse (07374525)                                                    | Platte (06805500)                                                                      |
| -------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Thresholds                                   | low ≤ 6,654 m³/s (235,000 ft³/s), high ≥ 27,807 m³/s                       | low ≤ 62.6 m³/s, high ≥ 379 m³/s, warm ≥ 28.9 °C                                       |
| Lock-box pairs on extreme days               | **13 low, 0 high** of 57                                                   | **1 low, 4 high, 4 warm** (9 in all) of 54                                             |
| Extreme days 2019–2025 seen by a usable pass | low 49 / 306 (16.0 %), high 37 / 369 (10.0 %), normal 198 / 1,655 (12.0 %) | low 11 / 100 (11.0 %), high 34 / 351 (9.7 %), normal 160 / 2,030 (7.9 %), warm 18 / 95 |

- **These figures are VERIFIED.**
  - Computed 2026-10-19 from `inputs/usgs-v5/turbidity.csv` and `reach/<site>/climate/daily.csv`.
  - The lock-box rows reproduce the published 57 and 54 pairs exactly.
  - "Usable pass" here is preliminary; WP6 recounts it with a committed script and test.
- **With the preregistered minimum N ≥ 20** (`preregistration.md:967`), no category qualifies.
  - So B4 shows "not enough extreme days to say", with the counts.
- **Heat and drought are seen at least as often as normal days.**
- **Floods are seen less often at Belle Chasse (10 % against 12 %) but not at the Platte (9.7 % against 7.9 %).**
  - "Storms bring clouds" holds for Belle Chasse only. Say that, not the general claim.

### F7. Etherscan, repo visibility, CI, licence

- **The contract source is not verified on Etherscan.** VERIFIED (page shows "Contract: Unverified", 2026-10-19).
  - Yet `docs/decisions.md` D22 says it is: a false statement to fix.
  - Ignition's build info is committed (`ignition/deployments/chain-11155111/build-info/solc-0_8_34-…json`), so verification needs no transaction. `docs/anchoring.md:43` already plans for the API key.
  - Command: `npx hardhat ignition verify chain-11155111` with `ETHERSCAN_API_KEY` in the keystore. ASSUMED to work on Hardhat 3; the fallback is `npx hardhat verify --network sepolia 0xe5d1…`.
- **The repository is private.** VERIFIED (`gh repo view`: `isPrivate: true`, `licenseInfo: null`).
  - The record panel links each code commit to `github.com/saulo1112/RiverEtch` (`web/src/features/case/panels/RecordPanel.tsx:34`), so those links 404 for judges.
  - The commits the records cite (ceeb838, 5e2a9ad, d61e5e1) are on `origin/main`. VERIFIED (`git branch -r --contains`).
- **CI is green.** VERIFIED (`gh run list`).
  - CI succeeded on main `2676cec` (2026-10-19 17:07 UTC).
  - Water quality and Calibration succeeded on `b4144d1` (2026-10-18).
  - CI still installs circom and builds and tests the circuits (`ci.yml:19`, `:38-45`, `:56-57`, `:69-70`).
- **No licence anywhere.** VERIFIED.
  - There is no LICENSE file; `README.md:241-243` says "Not chosen yet".
  - The contract is `SPDX-License-Identifier: UNLICENSED` (`LedgerAnchor.sol:1`).
  - The root `package.json` description still speaks of Colombia and zero-knowledge proofs.

### F8. Web state relevant to work area C

- **The strings to change.** VERIFIED.
  - Folded case file: "17.8 % typical error" (`CaseFile.tsx:167`, `content.ts:21`).
  - Details: "Locked test …" / "Median of past values" (`CaseFile.tsx:232-238`, `content.ts:20-24`).
  - Tile foot: "17.8 % error · 113.7 % without the satellite" (`WaterQualityView.tsx:107-110`, `content.ts:174-175`).
  - Interval label: "90 % interval" (`content.ts:12`).
  - The gauge approval is lower-case detail text, not a chip.
  - The level chips have no explanation.
  - "The prediction fell in a range…" is shown for the Platte's 3 valueless passes (`content.ts:18`).
- **The cards already carry what the sentences need.** VERIFIED.
  - `metrics.lockbox.{n, coverage90, mdsa, null_mdsa, sspb}` for turbidity, and `{mae, bias, n, coverage90}` for temperature.
  - Belle Chasse turbidity coverage: 0.9474 × 57 = **54 of 57**. Platte: **50 of 54**.
  - Platte temperature: 23 of 24. Belle Chasse temperature: 33 of 37.
- **The "All evaluated rivers" data exists but is not served to the web.** VERIFIED.
  - Source: `docs/water-quality/results/v5_levels.csv`, rows with `predicted_range=all`.
  - The nine values reproduce the 33.1 % median.
- **The UI rules are currently broken in two places.** VERIFIED (`case.css`).
  - The Water quality tile row scrolls sideways below its column minimums.
  - 11 px text exists (`--type-micro`).
- **Skills.**
  - **ui-ux-pro-max was incomplete and is now complete.** VERIFIED.
    - Until 2026-10-19 `.claude/skills/ui-ux-pro-max/` held only `SKILL.md`, so its searches could not run.
    - On 2026-10-19 the missing parts were copied from `github.com/nextlevelbuilder/ui-ux-pro-max-skill` (commit `56ea9cf`, 2026-10-15): `data/` (39 files), `references/` (2) and the 4 runtime scripts (`search.py`, `core.py`, `design_system.py`, `reasoning_contract.py`).
    - The files were normalised to LF.
    - The scripts were audited first: standard library only, no network calls, and they write files only with `--persist`, which is never used here.
    - Run them without `python -I`: isolated mode drops the script's folder from the import path and breaks `import core`.
  - `frontend-design` is installed.
  - The searches' results, each checked for fit before it was adopted, are in §3a.

- **Copy-test trap.** VERIFIED (`web/test/case.test.ts:56`).
  - The test rejects `/caus/i` in case copy, which matches "**because**". Microcopy must use "so", "as" or "since".

---

## 2. Decisions for you

| #   | Decision                       | Options (cost)                                                                                                                                                                                                                             | Recommendation                                                                               | Cost of being wrong                                                                                                   |
| --- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| D1  | **Repository visibility**      | **a)** Public now (15 min; history becomes visible). **b)** Public at the Oct 23 freeze. **c)** Private, with judges invited.                                                                                                              | **a**                                                                                        | Judges cannot open the code a record cites; "recompute it" becomes unverifiable.                                      |
| D2  | **Prospective cut-off T0**     | **a)** Block time of the first frozen-artifacts anchor. **b)** 2026-10-19 00:00. **c)** The cards' commit (2026-10-12).                                                                                                                    | **a**                                                                                        | With b or c, passes scored under a rule that was not yet public would be called "prospective", which is an overclaim. |
| D3  | **Gauge values for scoring**   | **a)** First read provisional, labelled; approved re-reads appended later, never replacing. **b)** Approved only (zero outcomes by Oct 24). **c)** Two columns from the start.                                                             | **a**                                                                                        | Provisional values can be revised; mitigated by the label and the re-score rule.                                      |
| D4  | **What a "claim" is**          | **a)** The sealed observation or temperature record itself, plus its ledger line (zero schema change). **b)** A separate claims ledger repeating estimate, interval, card hash and seal (+1.5 h).                                          | **a**                                                                                        | Low either way; b only duplicates fields already sealed.                                                              |
| D5  | **Extreme-event records (B3)** | **a)** A derived, unsealed index in `climate.json` linking each observed extreme day to its sealed record (1 h). **b)** A new sealed and anchored extreme-event ledger: a new record type, plus a Python↔JS canonical cross-test (+4–6 h). | **a**                                                                                        | With a, the event list itself is not tamper-evident. Its inputs are (USGS data and sealed records).                   |
| D6  | **Tabs**                       | **a)** 8 tabs (add Scoreboard and All rivers); the strip scrolls under about 1,180 px (0.5 h). **b)** 7 tabs: fold "Along the river" into "This pass" with a toggle (+1 h). **c)** 6 tabs: also merge the two series (+2.5 h).             | **b**                                                                                        | Too many tabs overwhelm; c costs time you do not have.                                                                |
| D7  | **Licence**                    | **a)** MIT for code, CC BY 4.0 for docs and data. **b)** Apache-2.0 plus CC BY 4.0. **c)** None.                                                                                                                                           | **a**, noting that `LedgerAnchor.sol` keeps `UNLICENSED` (its deployed source cannot change) | c tells judges and reusers nothing is reusable.                                                                       |
| D8  | **Etherscan source**           | **a)** Verify now (no transaction; needs a free Etherscan API key). **b)** Leave it unverified and correct D22.                                                                                                                            | **a**                                                                                        | With b, judges see "Unverified" one click after "Anchored on Ethereum Sepolia".                                       |

**Defaults that need no decision:**

- Keep the ZK scaffold and its CI steps, and remove ZK only from the prose (README prerequisites, `package.json` description, a banner on `zk-circuits.md`). Removing it from CI is +1.5 h and a red-CI risk.
- Hermann's card goes in the frozen ledger (the reach runs) but stays off the scoreboard (it is indicative).

---

## 3. Work packages

Effort assumes about 6 productive hours a day. "You" marks steps only the owner can do (keys, commits, pushes, transactions).

### WP1: Freeze and anchor the rules, cards and preregistration (clock-critical)

- **Goal:** a public, dated commitment, before any prospective pass, to:
  - the cards that make the estimates;
  - the preregistration;
  - the MANIFEST;
  - the scoring rule;
  - the extreme-day definitions.
- **What the user sees:**
  - `docs/water-quality/prospective.md` with the rules.
  - `docs/ledgers/frozen-artifacts.jsonl`.
  - `docs/ledgers/anchors.jsonl`, the anchoring log with every transaction.
  - On Etherscan, a second transaction.
- **Files:**
  - New: `docs/water-quality/prospective.md`, `docs/ledgers/frozen-artifacts.jsonl`, `docs/ledgers/anchors.jsonl`, `pipeline/src/climate_pipeline/ledgers.py`, `pipeline/tests/test_ledgers.py`.
  - Modified: `pipeline/src/climate_pipeline/cli.py` (a `ledger freeze` action), `contracts/scripts/anchor.ts`.
- **Steps:**
  1. **Write `prospective.md`, rule v1.** Do not edit `preregistration.md` (F4). Its contents:
     - **Prospective:** a pass acquired after T0 (D2), whose claim (its sealed record's ledger line) is anchored before RiverEtch reads its gauge value. Everything else is **retrospective (backtest)**; that includes every pass acquired before T0.
     - **Gauge series:**
       - turbidity: parameter 63680 at the reach's estimate station (07374525, 06805500);
       - water temperature: 00010 at the station the card was validated against (Louisville for the Platte, Baton Rouge for Belle Chasse, as the card's `validationSite` names it).
     - **Overpass value:** the median within ±30 min; otherwise the nearest within ±60 min; qualified values excluded. These are the lock box's own settings (`water-quality.yaml:118-119`), with any approval status allowed.
     - **Approval:** the first read uses whatever exists, normally Provisional, and is labelled. An approved re-read is appended as a new line and never replaces the first. Headline counts use first reads.
     - **Lag:** the gauge is read no earlier than 12 h after the overpass, and only for claims whose anchor is already mined.
     - **Inside:** `low ≤ gauge ≤ high`, using the sealed record's own interval.
     - **No gauge value:** recorded as "no gauge value"; re-read at the next daily run; final after 7 days. Never counted as inside or outside.
     - **Abstained claims:** listed as abstained, never scored.
     - **Reporting:** counts ("k of n inside") until n ≥ 20. No percentages, no error statistics, no level change (as preregistration v4, A).
     - **Extreme days:** F6's three definitions, verbatim. Ranks are among ranked years under `reach/README.md`'s 90 %-coverage rule. Thresholds are never applied to satellite values. The minimum n for an error comparison is 20, taken from `preregistration.md:967`.
     - **Disclosure:** the extreme-day counts in F6 were computed while writing these definitions; no error on extreme days had been computed.
  2. **`ledger freeze`.** It appends one line per artifact to `docs/ledgers/frozen-artifacts.jsonl`. Each line holds:
     - `path`;
     - `sha256` (the file's bytes);
     - `canonicalSha256` (cards only, `cards.card_hash`, the value records name);
     - `gitBlob`;
     - `purpose`;
     - `createdUtc`;
     - `previousLineSha256`.

     It refuses to re-add a path that has not changed. The artifacts are `preregistration.md`, `results/MANIFEST`, every card named in `pipeline/reach.yaml` (the 2 turbidity cards, Hermann's card and the 2 temperature cards) and `prospective.md`.

  3. **`anchor.ts`.** Generalise its list of `{label, path}` and add `terrachain:riveretch:frozen-artifacts`. After each transaction, append `{label, lines, head, tx, block, timestampUtc}` to `docs/ledgers/anchors.jsonl`. Backfill the 2026-10-16 batch (block 11924112, `0x19b4…eb0`) from chain reads.
  4. **You:**
     - commit and push;
     - pause the antivirus for the hooks;
     - run `npx hardhat run scripts/anchor.ts --network sepolia`;
     - commit `anchors.jsonl`.
  5. **You:** verify the source on Etherscan (D8), and make the repository public (D1).
- **Acceptance:**
  - `uv run pytest tests/test_ledgers.py`, `ruff` and `mypy` pass.
  - For every line, `sha256sum <path>` equals its `sha256`.
  - Each card line's `canonicalSha256` equals the `modelCardSha256` in its reach's records.
  - Re-running `anchor.ts` prints "Every ledger is already anchored".
  - `quality verify` is green in CI.
  - Etherscan shows the transaction.
- **Done:** the anchor is mined **before Tue Oct 20 12:00 Bogotá (17:00 UTC)**, ahead of the expected Platte pass.
- **Effort:** 4.5 h. **Dependencies:** D1, D2, D3, D8.
- **Risks:**
  - Keystore or RPC trouble. Fall back to the web button; it is known to fail with smart accounts (`anchoring.md:71-74`), so use a plain account.
  - Missing the deadline only moves the first prospective chance to the Belle Chasse Oct 21 pass.

### WP2: Daily claims and the outcomes ledger

- **Goal:** each new pass is sealed and its claim anchored, then scored against the gauge into an append-only outcomes ledger.
- **What the user sees:**
  - new records each day;
  - `docs/water-quality/reach/<site>/examples/outcomes/ledger.jsonl`;
  - the scoreboard's prospective rows (WP3).
- **Files:**
  - New: `pipeline/src/climate_pipeline/reach/score.py`, `pipeline/tests/test_score.py`, `pipeline/scripts/daily.ps1`.
  - Modified: `cli.py` (a `reach score` action), `reach/run.py` (`write_examples` copies `outcomes/`), `contracts/scripts/anchor.ts` (adds `terrachain:<reach>:outcomes`), `web/src/features/reaches/data.ts` (loads outcomes).
- **Steps:**
  1. **`daily.ps1`** runs `reach run`, then `thermal`, `context`, `render` and `examples --all-records` for the demo reaches. It never commits.
     - **You:** register it at **19:00** daily (the instructions are at `docs/water-quality/reach/README.md:162-178`), or run it by hand.
  2. **`reach score`** takes, for each demo reach and target, every sealed record acquired after T0.
     - A record is scored only if `anchors.jsonl` shows its ledger line covered by an anchor, and the overpass was at least 12 h ago.
     - It reads the gauge with the rule-v1 settings and scores the **sealed** value and interval (F3).
     - It appends `{claimRecordSha256, claimLedger, claimLine, sceneId, target, estimate, interval, gauge{station, parameter, value, unit, approval, rule, n}, readUtc, status, inside, ruleSha256, previousLineSha256}`.
     - It is idempotent: a claim already scored is skipped unless an approved value has appeared.
  3. **Daily rhythm:**
     - **08:00** `reach score`, then commit.
     - **19:00** `daily.ps1`, then commit, then **one anchor batch** (the new claims plus the morning's outcomes).
- **Acceptance:**
  - pytest covers each status: scored inside, scored outside, no gauge value, abstained, not yet anchored (skipped), before T0 (retrospective, skipped).
  - Running `reach score` twice adds nothing.
  - `reach verify` still passes.
  - The outcomes chain checks with the same `ledger_ok`.
  - The records' schema is untouched (`git diff` shows no change under `contract/`).
- **Done:** the cycle has run at least once end to end, even if it scored 0 passes.
- **Effort:** 4 h, plus 0.5 h a day of operations. **Dependencies:** WP1.
- **Risks:**
  - Clouds give n = 0. The UI must say so (microcopy).
  - Earth Search sometimes publishes 17 h or more late.
  - The 19:00 run needs the PC on and online.

### WP3: Scoreboard tab (C8)

- **Goal:** a public record of hits and misses, honestly labelled.
- **What the user sees:**
  - **Prospective, sealed and anchored before scoring:** "k of n inside the expected range". Each pass lists its date, estimate and range, the gauge value with a Provisional/Approved chip, and Inside/Outside shown by shape, word and colour.
  - **Retrospective (backtest):**
    - post-commit checks from `checks.csv` and `thermal/checks.csv` (Belle Chasse 13 of 18; Platte 7 of 8);
    - lock-box coverage from the cards (54 of 57; 50 of 54).
  - Counts only while n < 20. A visually hidden table carries the same data.
  - A pass is marked Inside or Outside by a distinct shape (a filled circle, or a ring with a cross) **and** its word, with colour on top. Rule `color-not-only` (§3a).
  - When n = 0, the empty state reads as guidance, not a blank chart (`empty-data-state`).
  - A changed count is announced as a whole phrase in one `role="status"` region, without moving focus (`contextual-live-badge-updates`).
- **Files:** a new `web/src/features/case/panels/ScoreboardView.tsx`; `Timeline.tsx`; `content.ts`; `case.css`; `web/src/features/reaches/types.ts`.
- **Steps:**
  1. Add the outcomes type and loader.
  2. Build the view with three groups.
  3. Write the empty state for n = 0.
  4. Add the tab (D6).
  5. **Stretch:** mark hits and misses in the Turbidity series chart (see the cut list).
- **Acceptance:**
  - With an empty outcomes ledger, the tab shows the n = 0 sentence and no percentage.
  - `npm test` passes, including the copy test.
  - The tab-strip check (`tabs.mjs`) is still identical on every tab.
  - Keyboard: every row is reachable.
- **Effort:** 3 h. **Dependencies:** WP2's outcome format (fixtures are enough to start).

### WP4: Level-1 case card and readable numbers (C1–C6, C9)

- **Goal:** one value, one range, a trust strip and a reliability comparison anyone can read.
- **What the user sees:** the folded case file becomes:
  - the value;
  - "Expected range 21.0–44.4 FNU (?)";
  - a trust strip: `[Validated (?)] · Sealed · Anchored 16 Oct 2026`;
  - "How far off it tends to be (less is better)", with two bars on one scale: "Satellite estimate 17.8 %" and "Guess the river's usual value 113.7 %";
  - "About 6 times smaller error · 57 test passes the model never saw".
  - Help buttons (?) open on tap or focus (never hover only), with a 44×44 px hit area and an accessible label.
- **Level 2 (Water quality tiles) gets:**
  - the bias in words ("tends to read 1.1 °C warm");
  - Provisional/Approved chips on gauge values;
  - three visually distinct number kinds, each with icon, label and colour: Gauge · measured (amber ring), Satellite · estimated (cyan dot), History · computed (neutral square).
- **Files:**
  - New: `web/src/features/case/panels/HelpTip.tsx`, `ReliabilityBars.tsx`.
  - Modified: `CaseFile.tsx`, `WaterQualityView.tsx`, `content.ts`, `case.css`.
- **Steps:**
  1. Strings from §6 into `content.ts`.
  2. **`HelpTip`:** a button with `aria-expanded` and a popover that closes on Esc and on a click outside.
     - It opens on click, tap, Enter or Space; never on hover alone (`hover-vs-tap`, `tooltip-keyboard`).
     - The popover never covers its own button (`focus-not-obscured`).
     - Its 44×44 px hit area exceeds WCAG 2.2 AA's 24×24 CSS px (`web-target-size`). Your rule is the stricter one, and it stands.
     - The (?) sits in the same relative place on every panel (`consistent-help`).
  3. **`ReliabilityBars`:** an SVG with text values; it does not rely on colour.
     - Each bar is labelled directly with its value (`direct-labeling`).
     - Bars reach at least 3:1 against the panel and their labels 4.5:1 (`contrast-data`).
     - A sentence summarises the comparison for screen readers (`screen-reader-summary`).
  4. The anchor date in the trust strip, read once with the existing `readAnchors`; "Checking…" while it loads; "Not anchored yet" if pending.
  5. Change "prediction" to "estimate" in `content.ts:18`.
  6. Raise all body text to at least 12 px (`--type-micro: 12px`).
  7. **Stacked Water quality layout under 1,100 px:** groups stack and tiles wrap on a grid, so nothing scrolls sideways (`horizontal-scroll`, high severity).
     - **Tablets (761–1,099 px):** `--timeline-body` grows at this breakpoint to fit two tile rows, with no inner scroll. The height is the same on every tab, so the tab strip still never moves.
     - **Phones (≤ 760 px):** the panel scrolls vertically inside. The skill's `scroll-behavior` rule warns against nested scroll regions that fight the page's scroll. The case view has no page scroll (it is a fixed, full-screen map), so here the panel's own scroll is the only one.
  8. **Truncated tile titles** (e.g. "Specific conduct…") wrap to two lines instead. A `title` attribute is not reachable by keyboard (`compact-label-overflow`, `truncation-strategy`).
- **Acceptance:**
  - The ratio is computed from the card: Belle Chasse "about 6 times", Platte "about 3 times".
  - Vitest-free unit tests in `web/test/` for the ratio and ordinal helpers.
  - Keyboard: Tab reaches each (?), and Enter or Space opens it.
  - In a 390–1,024 px screenshot, no element scrolls horizontally.
  - Contrast ≥ 4.5:1 for text tokens over `--glass-solid` (computed in the test).
  - `tsc`, `eslint`, `prettier` and `npm test` pass.
- **Effort:** 5 h. **Dependencies:** none (it can start Oct 20).

### WP5: "All evaluated rivers" tab (C7)

- **Goal:** every river's level and error next to its baseline, including those that do not beat it.
- **What the user sees:**
  - A table sorted by error.
  - Each row shows the river and gauge, the level chip, the satellite error and the guess-the-usual-value error as two bars, the pairs, and "k of n inside".
  - The demo reaches are marked, and Columbia, Connecticut and San Joaquin read "No clear gain over guessing the usual value".
  - The header carries "The two demo reaches are the best two of ten. The honest summary is the median over the nine rivers evaluated: 33.1 %." The median appears only here.
- **Files:** `web/vite.config.ts` (a define read from `v5_levels.csv`, as in `__REACH_FACTS__`), `web/src/env.d.ts`, a new `AllRiversView.tsx`, `content.ts`.
- **Acceptance:**
  - A test recomputes the 33.1 % median from the CSV.
  - The rows match `report.md:22-33`.
  - The table is a real `<table>`.
  - Its sortable headers report the current order with `aria-sort` (`sortable-table`). Sorting is optional and on the cut list; the default order (by error) needs no control.
  - The bars meet `contrast-data` (§3a).
- **Effort:** 2 h (+0.5 h with sorting). **Dependencies:** D6.

### WP6: Climate component with extreme days (B1, B2, B4, B5)

- **Goal:** climate shown with counts and ranks from the gauge, plus how often the satellite saw those days.
- **Placement in the Climate tab** (designed with the frontend-design and ui-ux-pro-max rules):
  - **The measure switch (radio group)** keeps the three existing record facts (annual peak, 7-day low, warmest day) and adds "Low-flow days", "High-flow days" and "Warm-water days" (Platte only).
  - **The left column** shows the selected year's count, then "Nth most in Y years", then "Seen by the satellite: k of n days".
  - **The existing per-year chart** draws the counts. The top three years are amber; the selected year is outlined.
  - **Under it, a one-row day strip** for the selected year: extreme days as cells, with a dot where a usable pass existed. This is the skill's calendar heatmap (§3a):
    - at most 365 cells in one SVG;
    - the satellite's passes are marked by a symbol (the dot), never by colour alone;
    - a legend sits right beside the strip (`legend-visible`).
  - **Per-year bars (§3a, bar chart for ranking):**
    - only the selected year and the top three carry direct value labels (`direct-labeling`);
    - gridlines stay faint (`gridline-subtle`);
    - the time unit is spelled out: "days per calendar year" (`time-scale-clarity`).
  - **The caption** keeps the IPCC sentence and "measurements, not a trend or an attribution".
  - **Below the chart, the error comparison line:** "Not enough extreme days to say: 13 of 57 test passes fell on low-flow days; at least 20 are needed."
  - **Text alternatives:** a visually hidden table carries every year, and one summary sentence states the selected year's count, rank and "seen by the satellite" figure (`data-table`, `screen-reader-summary`).
  - **No new animation:** the existing chart's motion already respects reduced motion (`excessive-motion`, `animation-optional`).
- **Files:** `pipeline/src/climate_pipeline/reach/climate.py` (extremes in `climate.json`); `pipeline/tests/`; `ClimateView.tsx`; `content.ts`; `case.css`; `docs/water-quality/reach/README.md`.
- **Steps:**
  1. Compute the thresholds from `daily.csv` exactly as rule v1 says.
  2. Count extreme days per year and rank the ranked years.
  3. Mark observed days: 2026 from the sealed records with a value; 2019–2025 from `inputs/usgs-v5/turbidity.csv`, labelled as such.
  4. Add the lock-box counts.
  5. B5: "Readings per year" = usable passes per year (median 48 at Belle Chasse, 31 at the Platte). There is no field-visit comparison unless a sourced number exists for these two gauges.
  6. Build the web view.
- **Acceptance:**
  - A pytest reproduces F6's thresholds and counts.
  - `climate.json` keeps every existing field.
  - The web shows "not enough" with counts, never an error number.
  - "From the gauge's record, never from the satellite" is visible.
- **Effort:** 5 h. **Dependencies:** WP1 (the rules anchored first).

### WP7: Trust model, judges' page, README, hygiene (A6, B6, D)

- **Files:**
  - New: `docs/trust-model.md`, `docs/judges.md`, `LICENSE`, `LICENSE-docs`.
  - Modified: `README.md`, `docs/water-quality/report.md` (not in the MANIFEST), `docs/decisions.md` (D23 entry; D22 correction), `docs/anchoring.md`, `docs/zk-circuits.md` (banner), `package.json` (description).
- **`trust-model.md` content:**
  - **Who:**
    - the single, immutable owner key (`0x0c9B…7F1d`), which can only add anchors;
    - no one can edit or delete an anchor;
    - a lost key means no future anchors;
    - a stolen key could add a false _new_ head, which is detectable because it would not match the public ledger.
  - **Where:** Sepolia is a public test network. It costs nothing to verify, and it is not mainnet.
  - **What an anchor proves:** that the ledger up to that line existed, unchanged, from the block's time. That is 2026-10-16 01:05:12 UTC for the first four ledgers, and T0 for the cards and rules.
  - **What it does not prove:**
    - anything before its own date;
    - that an estimate is right (that comes from the locked tests);
    - that the gauge is right (the USGS reports it, and provisional values can change);
    - that no scene was skipped (anyone can list the passes on Earth Search and compare).
  - **The prefix:** why it reads `terrachain:`.
  - **Unverifiable today:**
    - Etherscan source: until D8 is done.
    - Code links: until D1 is done.
- **`judges.md`, one page:**
  - what to look at;
  - the 3-minute path: hero, then a case, then Verify, then "Alter one value first", then Scoreboard, then All rivers;
  - verifying without a wallet;
  - open data (the Export menu plus the raw files);
  - limits first.
- **README:**
  - Open with the problem: the 2023 lowest 7-day flow at Belle Chasse (rank 1 of 16, with saltwater moving up the river), the 2019 Platte peak (1 of 72) and the 2023 warmest summer day (1 of 20). These are VERIFIED in `climate.json` and already cited at `README.md:28-39`.
  - Then what RiverEtch does, then who decides: the agency's analyst; RiverEtch informs.
  - Keep "this does not claim attribution".
  - Fix the daily-run claim, the "prospective" wording and the prerequisites (circom marked as legacy scaffold only).
- **Acceptance:**
  - `npm run format:check` passes.
  - A link check on `judges.md` passes.
  - The §7 checklist is ticked on the final README and video script.
- **Effort:** 4 h.

### WP8: Freeze, final anchor, video, QA

- **Freeze, Fri Oct 23, 21:00:**
  1. last scoring and run;
  2. final commit;
  3. final anchor batch (all ledgers, including outcomes and frozen artifacts);
  4. record the transaction in `anchors.jsonl` and the README.
- **Video, Thu Oct 22:** it shows the scoreboard as it stands and promises nothing.
- **QA:**
  - all CI jobs;
  - `quality verify`;
  - `reach verify`;
  - the web checks;
  - the screenshot suite and `tabs.mjs`.
- **Effort:** 3 h of QA and freeze, plus 3 h of video.

---

## 3a. Design guidance from ui-ux-pro-max (searched 2026-10-19)

**How the guidance was gathered:**

- Queries ran with `python .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --domain <chart|ux>` or `--stack react`, one design question per query.
- Each top result was checked for fit before it was adopted. An off-topic result got one narrower retry, as the skill's own query contract asks.
- Rule ids in backticks come from `references/quick-reference.md`.
- **Your content decisions win over any suggestion.** Where the skill disagreed with them, the table says so.

| Component (WP)                    | Query                                                                                                    | Result adopted                                                                                                                                        | Fit                                                                  | How it is applied                                                                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Climate day strip (WP6)           | "event days calendar strip timeline" (chart)                                                             | Heat map / calendar heatmap: at most 365 cells per SVG; symbols or labels in cells, not colour alone; grid table fallback                             | Good (result 2). Result 1, a process map, is off-topic and rejected. | A one-row strip per year with dots for passes, a legend beside it, and the hidden table                                                                 |
| Per-year extreme-day counts (WP6) | "count per year ranking comparison" (chart)                                                              | Bar chart: ranking is the insight; direct value labels; never colour alone; sortable table fallback; focus reveals the values                         | Good                                                                 | The existing per-year chart with direct labels on the selected and top-three years                                                                      |
| Reliability comparison (WP4, WP5) | "two values comparison" was off-topic (radar, scatter). Retry: "benchmark target bullet" (chart)         | Bullet or gauge: number and benchmark text beside the bars; a one-row table fallback; red/yellow/green alone is insufficient                          | Partial                                                              | Your decision stands: two bars on one scale with text values. Its threshold zones are not used, since there are no defined quality ranges.              |
| Scoreboard (WP3)                  | "hit miss outcome small sample" (no result). Retry: "status pass fail table" (chart)                     | Streaming area and pie: both off-topic                                                                                                                | **No verified match**                                                | Fallback from the general rules: a table with shape, word and colour per status (`color-not-only`), `empty-data-state`, `contextual-live-badge-updates` |
| Help (?) (WP4)                    | "tooltip touch keyboard focus" was generic. Retry: "tooltip hover only" (ux)                             | Hover vs tap (high): tap or click for primary actions; never hover alone                                                                              | Good                                                                 | Opens on click, tap, Enter or Space, plus `tooltip-keyboard`, `focus-not-obscured` and `consistent-help`                                                |
| Touch targets (WP4)               | "touch target size" (ux)                                                                                 | WCAG 2.2 AA asks for 24×24 CSS px on the web; 44 pt and 48 dp are native rules                                                                        | Good                                                                 | Your 44×44 px rule is stricter and stays                                                                                                                |
| No horizontal scroll (WP4)        | "horizontal scroll mobile" (ux)                                                                          | High severity: content fits the viewport width                                                                                                        | Good                                                                 | Tiles wrap. Tablets get a taller panel; phones get a vertical scroll inside the panel.                                                                  |
| Colour and contrast (all)         | "color alone meaning" (ux)                                                                               | Colour-only is high severity; 4.5:1 for text                                                                                                          | Good                                                                 | All number kinds and statuses get an icon or shape plus text. Bars reach 3:1 (`contrast-data`).                                                         |
| Folding panels                    | "progressive disclosure" was off-topic (heading balance). Retry: "accordion expand collapse" (no result) | Quick reference: `progressive-disclosure` (reveal complex options progressively)                                                                      | Rule only; no search match                                           | The existing `DisclosureButton` pattern stays                                                                                                           |
| Chart text alternatives           | "chart data table screen reader" and "chart accessibility alternative" (ux): generic or off-topic        | Every chart-domain result lists "a visible data table plus a summary; focus reveals hover values", and so do `data-table` and `screen-reader-summary` | Good (chart domain)                                                  | Hidden tables for the series, thermal, profile, histogram, climate and scoreboard views, plus one summary sentence each                                 |
| React (WP3–WP6)                   | "popover tooltip accessible", "tabs keyboard aria", "list rendering memo" (stack react)                  | Announce dynamic content with `aria-live`; stable list keys; `React.memo` only where measured                                                         | Partial; the rest is generic                                         | Live regions for the scoreboard and verification; no blanket memoisation                                                                                |

**Resolved conflicts:**

- **Phone body text.** `readable-font-size` asks for 16 px body text on phones; your floor is 12 px. On phones, the Level-1 sentences and the help popovers use 16 px; data labels and chips keep 12 px.
- **Nested scrolling.** `scroll-behavior` warns against nested scroll regions. The case view has no page scroll, so a scrolling tab panel on phones is the only scroll on screen (WP4, step 7).

**Not used:**

- `--design-system`: RiverEtch already has its system in `web/src/styles/tokens.css`, and the brief says to reuse it.
- `--persist`: it would write files into the repo.

---

## 4. Schedule (Bogotá)

| Day                     | Clock-bound                                                                                                                                                                                 | Build                                      | Hours |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----- |
| **Mon 19** (from 15:00) | D1/D2/D3/D8 decided; WP1 steps 1–3; **you:** Etherscan verify, repo public                                                                                                                  | WP1                                        | 4     |
| **Tue 20**              | **Anchor #1 (frozen artifacts) before 12:00**, ahead of the Platte pass at about 12:22. 19:00 `daily.ps1` (Oct 12–20 passes; Oct 12–19 are retrospective) → commit → **anchor #2** (claims) | WP2 (4 h), WP4 start (2 h)                 | 6     |
| **Wed 21**              | 08:00 `reach score` (the Platte Oct 20 pass, if usable). 19:00 run → **anchor #3** (claims plus outcomes)                                                                                   | WP4 finish (3 h), WP3 (3 h)                | 6     |
| **Thu 22**              | 08:00 score. 19:00 run → **anchor #4**                                                                                                                                                      | WP5 (2 h), WP6 part (1 h), **video (3 h)** | 6     |
| **Fri 23**              | 08:00 score; 19:00 last run; **21:00 freeze → final anchor**                                                                                                                                | WP6 rest (2 h), WP7 (3.5 h), QA (0.5 h)    | 6     |
| **Sat 24**              | Submit. Nothing scored after the freeze is part of the submission.                                                                                                                          | Buffer only: fixes, no features            | 2–3   |

**Every transaction hash** goes to `docs/ledgers/anchors.jsonl` (written by `anchor.ts`). The table in `docs/anchoring.md` and the final one in the README repeat it.

**Budget.** About 28 h are available, and the work packages total about 34 h. The cut list below closes the gap.

## 5. Cut list (drop from the top) and the minimum honest version

1. B3 as a sealed ledger (D5b): already recommended against.
2. Hit and miss marks in the series chart (the scoreboard table already shows them).
3. The Climate day strip (keep counts, ranks and "seen by the satellite k of n").
4. Bars and sorting in All rivers (keep the numbers table, ordered by error).
5. Help buttons beyond the four key ones (interval, error, baseline, level).
6. The live anchor date in the trust strip. Show "Anchored, see the record" and link to Verify.
7. Polish of the stacked tablet layout beyond "no horizontal scroll".
8. Verifying the frozen-artifacts and outcomes ledgers inside the web dialog. Keep the CLI, `anchors.jsonl` and Etherscan.

**The minimum honest version (about 15 h):**

- WP1 complete;
- WP2 with the outcomes ledger, even if it holds 0 rows;
- the Scoreboard with labels and counts;
- the C1–C3 sentences, the C6 chips and the two-bar comparison;
- `trust-model.md`, `judges.md` and the README limits;
- the repo public, Etherscan verified (or D22 corrected);
- the "prospective check" relabel and the daily-run claim fixed.

---

## 6. Microcopy kit (for `content.ts`; no "because", "caus", "human", "operator", "pressure" or "pollut")

```ts
export const TIMING = {
  retrospective: "Retrospective (backtest)",
  retrospectiveHelp:
    "Sealed after the gauge's value was public. It shows the model's behaviour, not a commitment made in advance.",
  prospective: "Prospective",
  prospectiveHelp:
    "Its model and the scoring rule were anchored on Sepolia before the satellite took the image, and the estimate was sealed and anchored before RiverEtch read the gauge.",
} as const;

export const RELIABILITY = {
  title: "How far off it tends to be",
  lessIsBetter: "less is better",
  satellite: "Satellite estimate",
  baseline: "Guess the river's usual value",
  baselineHelp:
    "The error you would get by always guessing the median of the river's past values, with no satellite.",
  median: (n: number, mdsa: string) =>
    `In ${String(n)} test passes the model never saw, half of the errors were smaller than ${mdsa} %.`,
  times: (r: string) => `About ${r} times smaller error than guessing the usual value.`,
  noGain: "No clear gain over guessing the usual value.",
  worse: "Worse than guessing the usual value.",
  unitsHelp:
    "Turbidity runs from a few FNU to hundreds, so an error of 5 FNU is large at 10 FNU and small at 300: it is given as a share of the value. A degree means the same in any season, so temperature errors are in °C.",
  biasWarm: (d: string) => `Tends to read ${d} °C warm.`,
  biasCold: (d: string) => `Tends to read ${d} °C cold.`,
  biasNone: "No clear tendency to read warm or cold.",
  biasHigh: (p: string) => `Tends to read about ${p} % high.`,
  biasLow: (p: string) => `Tends to read about ${p} % low.`,
} as const;

export const INTERVAL = {
  label: "Expected range",
  sentence: (k: number, n: number) =>
    `We expect the measured value to fall inside this range about 9 times out of 10; in testing it did ${String(k)} of ${String(n)} times.`,
} as const;

export const LEVEL_HELP = {
  validated:
    "Passed the locked test with a clear margin over guessing the usual value, on at least 20 passes in two years, with an honest range. You can cite the value with its range.",
  estimated:
    "Beat guessing the usual value under looser limits. Use the value with its range, and confirm it against the gauge when it matters.",
  estimatedCapped:
    "Met every validated threshold, but against a gauge whose values are still provisional, so it is capped at estimated.",
  indicative:
    "Follows the river's rises and falls, but not its level. Read it as low, medium or high, never as a number.",
  none: "Did not pass the locked test. Only the relative index is shown.",
} as const;

export const NUMBER_KINDS = {
  gauge: "Gauge · measured",
  satellite: "Satellite · estimated",
  history: "History · computed",
  provisional: "Provisional",
  provisionalHelp: "Published by the USGS within minutes of the reading. It may still be revised.",
  approved: "Approved",
  approvedHelp: "Reviewed and approved by the USGS.",
} as const;

export const TRUST = {
  sealed: "Sealed",
  anchored: (date: string) => `Anchored ${date}`,
  checking: "Checking the anchor…",
  notAnchored: "Not anchored yet",
} as const;

export const SCOREBOARD = {
  title: "Scoreboard",
  inside: (k: number, n: number) => `${String(k)} of ${String(n)} inside the expected range`,
  hit: "Inside the range",
  miss: "Outside the range",
  noGauge: "No gauge value",
  abstained: "No estimate (abstained)",
  countsNote: "Counts, not percentages, until there are 20 passes.",
  provisionalNote:
    "Scored against provisional gauge values; scored again, on a new line, when the USGS approves them.",
  empty:
    "No prospective pass scored yet. Clouds hide about three passes in four; the next clear pass is scored the morning after its anchor.",
  lockbox: "Locked test (Dec 2023 – Sep 2026)",
  postCommit: "After the model card's commit, 2026",
} as const;

export const CLIMATE_EXTREMES = {
  low: "Low-flow days",
  high: "High-flow days",
  warm: "Warm-water days",
  count: (n: number, year: string) => `${String(n)} in ${year}`,
  rank: (ordinal: string, years: number) => `${ordinal} most in ${String(years)} years`,
  seen: (k: number, n: number) => `Seen by the satellite: ${String(k)} of ${String(n)} days`,
  notEnough: (k: number, n: number, kind: string) =>
    `Not enough extreme days to say: ${String(k)} of ${String(n)} test passes fell on ${kind} days; at least 20 are needed.`,
  source: "From the gauge's own record, never from the satellite.",
  definitionLow: (first: string) =>
    `A day whose mean flow is among the lowest tenth of this gauge's approved days since ${first}. Fixed on 19 Oct 2026, before any error on such days was computed.`,
  readings: (n: number) => `About ${String(n)} usable satellite readings a year`,
} as const;

export const ALL_RIVERS = {
  title: "All evaluated rivers",
  honest:
    "The two demo reaches are the best two of ten. The honest summary is the median over the nine rivers evaluated: 33.1 %.",
  demo: "Demo reach",
  insufficient: "Too few test passes",
} as const;

export const GLOSSARY = {
  estimate:
    "A value read from a satellite image at the time it was taken. RiverEtch never says what the river will do.",
  lockedTest:
    "Passes from Dec 2023 to Sep 2026 that the model never saw in training or selection, scored once.",
  seal: "The SHA-256 of a record's content. Change one digit and the seal no longer matches.",
  anchor:
    "A ledger's latest seal stored on Ethereum Sepolia with the block's time: proof of what the ledger held from then on.",
} as const;
```

Two notes on the kit:

- The median sentence, the 33.1 % and the "about N times" figure are computed from the cards and the CSV, never typed.
- Ordinals ("2nd", "the highest") come from a helper.

---

## 7. Honesty checklist (final README and video script)

- [ ] **Limits come first:** clouds (about 3 passes in 4 lost), values with a unit only at validated gauges, retrospective 2026, provisional gauge values, Sepolia.
- [ ] **Vocabulary:**
  - say "estimate" and "estimated", never "prediction", "predict" or "forecast" (fix `content.ts:18`);
  - never "worth buying";
  - never call turbidity or river temperature "Essential Climate Variables". Re-word `README.md:46` ("a climate variable in itself") to "Water temperature matters for climate impacts".
- [ ] **No attribution or trend:**
  - the sentence "this does not claim attribution" stays;
  - nothing says or implies a trend (the satellite record starts in 2018);
  - a climate rank is always "Nth in Y years at this gauge".
- [ ] **"Fills the gaps between gauges"** is followed by "as a relative map; values with a unit only where a gauge validated the model".
- [ ] **Scope of the numbers:**
  - the nine-river median (33.1 %) appears only with all rivers, never beside one river;
  - the demo pair is called "the best two of ten".
- [ ] **Counts:** every count below 20 is a count ("7 of 8"), never a percentage.
- [ ] **Labels:** every scored pass is labelled retrospective or prospective. The prospective n is stated as it is, including 0.
- [ ] **What the anchor proves:** "from its block date on". The 2026 records are not presented as committed before their gauge values.
- [ ] **What the seal proves:** that a record has not changed, not that it is right.
- [ ] **Gauge values:** provisional values are labelled, and the gauge is the referee: the USGS reports it.
- [ ] **No promised results:** no result is promised for after Oct 24, and the video shows the scoreboard as it stands.
- [ ] **Checkable claims:** the repo is public and Etherscan is verified, or the README says plainly that they are not.

---

## 8. Open questions for you

1. **Level 1 "case card":** I assumed it means the case view's left panel (folded). Should the hero's cases-screen card also get the trust strip? (+0.5 h)
2. **Machine availability:** can this PC be on and online at 08:00 and 19:00 daily, Oct 20–23, for the runs and anchors?
3. **Etherscan API key:** do you have one (free), or should D8 fall back to correcting D22?
4. **Hackathon rules:** do they require a public repository or a maximum video length? Unverified: check the submission page.
5. **Prospective reporting:** should the README's results table show the prospective count, even if it is 0 at the freeze, or only the scoreboard?
6. **ZK scaffold:** keep it out of the prose only (the default), or also out of CI and the repo after the submission?
7. **`.claude/skills/` and Prettier.** Should it go in `.prettierignore`?
   - From the repo root, a local `npm run format:check` flags 5 of the skill's files, your original `SKILL.md` included.
   - CI is unaffected, since the folder is untracked.
   - The cost is one line in `.prettierignore`, or committing the skills formatted.

---

## Verification of this plan's own claims

Re-run any VERIFIED item with the command named beside it:

- `gh repo view` and `gh run list`;
- `Get-ScheduledTask`;
- the Earth Search STAC POST for the two points;
- `latest-continuous` on the USGS OGC API;
- `eth_call` `count`/`anchorAt` on `0xe5d1…e762`;
- `git log --diff-filter=A`;
- `sha256sum` and `git hash-object` on the cited files.

The F6 counting script will be committed with WP6 as a test, so the counts can be reproduced in CI.
