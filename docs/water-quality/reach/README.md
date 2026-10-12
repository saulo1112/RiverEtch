# Reach runs: observation records v2

`climate-pipeline reach` publishes one [observation record v2](../../schema/README.md) per usable
Sentinel-2 scene of a reach. The settings live in `pipeline/reach.yaml`; the code in
`pipeline/src/climate_pipeline/reach/`. Only public data are read (Earth Search L2A, Open-Meteo),
so no credentials are needed and a run can be unattended.

| Reach                      | Site file                                   | Estimate station                        | Targets         | Baseline                                |
| -------------------------- | ------------------------------------------- | --------------------------------------- | --------------- | --------------------------------------- |
| `magdalena-puerto-wilches` | `pipeline/sites/`                           | San Pablo (IDEAM 23207040), downstream  | turbidity, TSS  | the Magdalena validation's 112 scenes   |
| `missouri-hermann`         | `pipeline/reaches/` (outside the screening) | USGS 06934500 (the gauge), upstream end | turbidity (FNU) | measured by the reach itself, 2019–2025 |

## What a record says

- **NDTI and NIR/red (B8A/B04) per sub-reach**, with their D0 z-scores. Both are relative indices,
  never a unit.
  - The z-scores compare the scene with the **frozen baseline** only: the reach's usable scenes up
    to `baseline_end`. So a sealed record never changes when later scenes arrive.
  - The rule is the screening's D0 (season group of ≥ 8 values, else all of ≥ 12; σ = max(1.4826 ×
    MAD, 0.01)).
- **The verdict** follows from the NDTI z-scores alone (|z| ≥ 3). NIR/red is context.
- **One estimate per target**, from the model card the reach declares (`cards:` in
  `pipeline/reach.yaml`), read on the estimate station's window. The unit is the card's (NTU for
  IDEAM, FNU for USGS).
  - _validated_ or _estimated_: a value, its 90 % interval and the predicted range's MdSA;
  - _indicative_: a relative class (low, medium or high, the tercile among the station's own
    historical estimates), no unit;
  - _none_: nothing.
  - An `abstainReason` replaces the value when the scene was excluded, the window failed D15's
    guards (glint, contamination, valid pixels, water B11, clouds), a feature lies outside its
    training range, or the interval is not finite.
  - `basis` says where the level comes from: `preregistered_test` (v2), `post_hoc_nested_loso_magdalena`
    (v2.1, v3), `post_hoc_temporal_magdalena` (v4 round 3, exploratory) or
    `preregistered_lockbox_site` (v4: one site's held-out years, evaluated once).
- **Rain:** the screening's point rule (> 20 mm in the 72 h before, at a rain point), in the reach's
  time zone. Catchment rain is not computed by a reach run (`null`).
- **Provenance:** the STAC items, the code commit, the SHA-256 of the settings, and
  `recordSha256` over the canonical JSON.

## Running

The model cards come from `climate-pipeline quality run`. Then, once per reach:

```powershell
cd pipeline
uv run climate-pipeline reach baseline --site missouri-hermann --root ..
```

- **With `ndti_scenes`** (the Magdalena), the baseline measures NIR/red and the station's windows on
  the validation's frozen scenes, and NDTI again as a reproduction check (`baseline.json` gives the
  largest difference).
- **Without it** (Hermann), the reach decides every acquisition from `baseline_start` to
  `baseline_end` itself: SCL first (the screening's observable rule), then the bands of the
  observable ones; the scene's exclusion rule decides which enter the history.
- It writes `docs/water-quality/reach/<site>/` and resumes where a capped run stopped. The network
  cap is `baseline_max_gb` (4 GB by default; 6 GB at Hermann).

Then, as often as wanted:

```powershell
uv run climate-pipeline reach run --site all --root ..               # every reach, last 30 days
uv run climate-pipeline reach run --site missouri-hermann --root .. --since 2026-01-01
uv run climate-pipeline reach check --site missouri-hermann --root ..   # the gauge, report-only
```

| Exit code | Meaning                                                                |
| --------- | ---------------------------------------------------------------------- |
| 0         | done                                                                   |
| 1         | cannot run (no geometry, no NIR/red baseline, a declared card missing) |
| 2         | partial: an acquisition failed, and the next run retries it            |
| 3         | a cap stopped the run (2 GB of network, or under 20 GB free disk)      |

With `--site all` the exit code is the largest of the reaches'.

## The prospective check (gauged reaches only)

At a reach whose estimate station is a USGS gauge, `reach run` also notes the card's raw estimate of
every recorded scene in `checks/estimates.jsonl`, **beside the sealed records and never in them**.
`reach check` pairs the scenes acquired after the card's first commit with the gauge's turbidity at
the overpass (the pilot's rule; approved, else provisional, and labelled) and writes
`checks/checks.csv` and `checks/summary.json`. It never sets a level (preregistration v4, A).

## Outputs (`pipeline/out/reach/<site>/`, not committed)

| File             | Content                                                                                      |
| ---------------- | -------------------------------------------------------------------------------------------- |
| `records/*.json` | One sealed record per usable scene                                                           |
| `latest.json`    | The newest record                                                                            |
| `series.json`    | Every record by date, trimmed for a chart: indices, verdict, rain, estimates                 |
| `ledger.jsonl`   | Append-only: scene, record hash, file, time, and the SHA-256 of the line before (anchorable) |
| `state.json`     | Every acquisition already decided (recorded, not observable, excluded)                       |
| `checks/*`       | Gauged reaches: unpublished raw estimates and the prospective check                          |
| `runs.log`       | Output of the scheduled runs                                                                 |

Committed examples for the frontend live in `docs/water-quality/reach/<site>/examples/`.

## Daily run with the Task Scheduler

`pipeline/scripts/reach-run.ps1` runs `reach run` for every reach, appends to `runs.log` and returns
the run's exit code. To register it (once, in PowerShell):

```powershell
$script = "C:\Users\ASUS\Desktop\S\IEEE Hackathon\pipeline\scripts\reach-run.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:30am
Register-ScheduledTask -TaskName "TerraChain reach run" -Action $action -Trigger $trigger `
    -Description "Observation records v2 of every reach (no commits)"
```

`Unregister-ScheduledTask -TaskName "TerraChain reach run"` removes it.
