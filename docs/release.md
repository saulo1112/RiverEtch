# Release and operation

How the submitted version is frozen, and how RiverEtch keeps running afterwards without changing
it.

## Two branches

- **`main`** holds the code, the rules, the model cards and a snapshot of every reach's records.
  The submission is a tag on it, and after the deadline `main` does not change.
- **`data`** holds what the daily run produces: the reaches' records and ledgers
  (`docs/water-quality/reach/<site>/examples/`), the Bitcoin proofs (`docs/ledgers/ots/`), the
  signatures and the anchoring log, the run's working state (`state/reach/`) and `status.json`.
  Only the daily workflow and the owner's anchoring script write to it. It holds generated files
  only, so its commits run no Git hooks: Prettier must never rewrite a sealed record.

The web app reads `data` when it is reachable (the repository must be public) and falls back to the
snapshot bundled with its build; it says which one it shows.

## Tagging the submission

From the repository root, on the commit that is submitted:

```bash
git tag -a submission-2026-10-25 -m "IEEE ClimateChain submission"
git push origin submission-2026-10-25
```

The tag is the version judges evaluate. Records sealed later are on `data`, each naming the code
commit that produced it (the tag's commit, as long as `main` does not change).

## The daily run

`.github/workflows/daily.yml` runs at 13:00 and 00:00 UTC (08:00 and 19:00 in Bogotá), and by hand
from the Actions tab. It needs no secret:

1. restores the working state and the published files from `data`;
2. runs `pipeline/scripts/daily.sh`: Bitcoin attestations of the last heads (`ledger upgrade`),
   the score of committed claims (`reach score`), the new passes (`reach run`, `thermal`,
   `context`, `render`, `check`, `examples`), and Bitcoin timestamps of the new heads
   (`ledger stamp`);
3. writes `status.json` and commits everything to `data`.

It never signs, anchors on Sepolia or touches `main`.

## Once: start the data branch

After `main` is pushed, from the repository root (the dry run builds the branch locally and pushes
nothing):

```powershell
powershell -ExecutionPolicy Bypass -File pipeline\scripts\bootstrap-data.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File pipeline\scripts\bootstrap-data.ps1
```

Then run **Daily run** once by hand from the Actions tab. Its first run fills the imagery cache, so
it is the slowest.

## The owner's step: sign and anchor

Whenever `data` has new records (the status panel shows the newest record and the newest anchor):

```powershell
powershell -ExecutionPolicy Bypass -File pipeline\scripts\anchor-pending.ps1
```

It signs every new head with the ML-DSA-65 key (`~/.riveretch/`, never in the repository), anchors
the ledgers that grew on Sepolia (the owner key from the Hardhat keystore), and pushes the
signatures and the rebuilt anchoring log to `data`. Under rule v2 a claim also counts as committed
by its Bitcoin timestamp alone, so the scoreboard keeps growing when this step waits.
