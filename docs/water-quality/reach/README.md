# Reach runs: observation records v2

`climate-pipeline reach` publishes one [observation record v2](../../schema/README.md) per usable
Sentinel-2 scene of a reach. The settings live in `pipeline/reach.yaml`; the code in
`pipeline/src/climate_pipeline/reach/`. Only public data are read (Earth Search L2A, Open-Meteo), so
no credentials are needed and a run can be unattended.

## What a record says

- **NDTI and NIR/red (B8A/B04) per sub-reach**, with their D0 z-scores. Both are relative indices,
  never a unit.
  - The z-scores compare the scene with the **frozen baseline** only: the reach's usable scenes up
    to `baseline_end`. So a sealed record never changes when later scenes arrive.
  - The rule is the screening's D0 (season group of ≥ 8 values, else all of ≥ 12; σ = max(1.4826 ×
    MAD, 0.01)).
- **The verdict** follows from the NDTI z-scores alone (|z| ≥ 3). NIR/red is context.
- **One estimate per target** (turbidity, TSS), from the product's model card in
  `docs/water-quality/results/models/`, read on the estimate station's window (San Pablo, 23207040,
  at the downstream end):
  - _validated_ or _estimated_: a value, its 90 % interval and the predicted range's test MdSA;
  - _indicative_: a relative class (low, medium or high, the tercile among the station's own
    historical estimates), no unit;
  - _none_: nothing.
  - An `abstainReason` replaces the value when the scene was excluded, the window failed D15's
    guards (glint, contamination, valid pixels, water B11, clouds), a feature lies outside its
    training range, or the interval is not finite.
- **Rain:** the screening's point rule (> 20 mm in the 72 h before, at a rain point). Catchment
  rain is not computed by a reach run (`null`).
- **Provenance:** the STAC items, the code commit, the SHA-256 of the settings, and
  `recordSha256` over the canonical JSON.

## Running

The model cards come from `climate-pipeline quality run`. Then, once per reach:

```powershell
cd pipeline
uv run climate-pipeline reach baseline --root ..
```

It measures NIR/red per sub-reach and the station's windows on the frozen baseline's scenes, and
measures NDTI again as a reproduction check (`baseline.json` gives the largest difference). It
writes `docs/water-quality/reach/<site>/`. The network cap is 2 GB.

Then, as often as wanted:

```powershell
uv run climate-pipeline reach run --root ..                       # the last 30 days
uv run climate-pipeline reach run --root .. --since 2026-01-01    # a longer span
```

| Exit code | Meaning                                                           |
| --------- | ----------------------------------------------------------------- |
| 0         | done                                                              |
| 1         | cannot run (no geometry, no NIR/red baseline)                     |
| 2         | partial: an acquisition failed, and the next run retries it       |
| 3         | a cap stopped the run (2 GB of network, or under 20 GB free disk) |

## Outputs (`pipeline/out/reach/<site>/`, not committed)

| File             | Content                                                                                      |
| ---------------- | -------------------------------------------------------------------------------------------- |
| `records/*.json` | One sealed record per usable scene                                                           |
| `latest.json`    | The newest record                                                                            |
| `series.json`    | Every record by date, trimmed for a chart: indices, verdict, rain, estimates                 |
| `ledger.jsonl`   | Append-only: scene, record hash, file, time, and the SHA-256 of the line before (anchorable) |
| `state.json`     | Every acquisition already decided (recorded, not observable, excluded)                       |
| `runs.log`       | Output of the scheduled runs                                                                 |

## Daily run with the Task Scheduler

`pipeline/scripts/reach-run.ps1` runs `reach run`, appends to `runs.log` and returns the run's exit
code. To register it (once, in PowerShell):

```powershell
$script = "C:\Users\ASUS\Desktop\S\IEEE Hackathon\pipeline\scripts\reach-run.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:30am
Register-ScheduledTask -TaskName "TerraChain reach run" -Action $action -Trigger $trigger `
    -Description "Observation records v2 of the Magdalena reach (no commits)"
```

`Unregister-ScheduledTask -TaskName "TerraChain reach run"` removes it.
