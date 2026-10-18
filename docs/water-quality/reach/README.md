# Reach runs: observation records v2

`climate-pipeline reach` publishes one [observation record v2](../../schema/README.md) per usable
Sentinel-2 scene of a reach. The settings live in `pipeline/reach.yaml`; the code in
`pipeline/src/climate_pipeline/reach/`. Only public data are read (Earth Search L2A, Open-Meteo),
so no credentials are needed and a run can be unattended.

| Reach                      | Site file                  | Estimate station                        | Targets         | Level of the card   | Baseline                                    |
| -------------------------- | -------------------------- | --------------------------------------- | --------------- | ------------------- | ------------------------------------------- |
| `mississippi-belle-chasse` | `pipeline/reaches/` (demo) | USGS 07374525 (the gauge), downstream   | turbidity (FNU) | validated (17.8 %)  | its own scenes, 2019-01..2024-10 (6 GB cap) |
| `platte-louisville`        | `pipeline/reaches/` (demo) | USGS 06805500 (the gauge), upstream end | turbidity (FNU) | validated (20.3 %)  | its own scenes, 2019-01..2025-12            |
| `missouri-hermann`         | `pipeline/reaches/`        | USGS 06934500 (the gauge), upstream end | turbidity (FNU) | indicative (34.9 %) | its own scenes, 2019-01..2024-12 (6 GB cap) |

## What a record says

- **NDTI and NIR/red (B8A/B04) per sub-reach**, with their D0 z-scores. Both are relative indices,
  never a unit.
  - The z-scores compare the scene with the **frozen baseline** only: the reach's usable scenes up
    to `baseline_end`. So a sealed record never changes when later scenes arrive.
  - The rule is the screening's D0 (season group of ≥ 8 values, else all of ≥ 12; σ = max(1.4826 ×
    MAD, 0.01)).
- **The verdict** follows from the NDTI z-scores alone (|z| ≥ 3). NIR/red is context.
- **One estimate per target**, from the model card the reach declares (`cards:` in
  `pipeline/reach.yaml`), read on the estimate station's window. The unit is the card's (FNU at
  the USGS gauges).
  - _validated_ or _estimated_: a value, its 90 % interval and the predicted range's MdSA;
  - _indicative_: a relative class (low, medium or high, the tercile among the station's own
    historical estimates), no unit;
  - _none_: nothing.
  - An `abstainReason` replaces the value when the scene was excluded, the window failed D15's
    guards (glint, contamination, valid pixels, water B11, clouds), a feature lies outside its
    training range, or the interval is not finite.
  - `basis` says where the level comes from: `preregistered_lockbox_site` for every reach run
    today (one site's held-out years, evaluated once); the schema keeps the earlier rounds' values.
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

- **Without `ndti_scenes`** (every reach today), the reach decides every acquisition from `baseline_start` to
  `baseline_end` itself: SCL first (the screening's observable rule), then the bands of the
  observable ones; the scene's exclusion rule decides which enter the history.
- **With `ndti_scenes`** (a reach with a validation's frozen scenes), the baseline measures NIR/red
  and the station's windows on those scenes, and NDTI again as a reproduction check.
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

## More variables (v6)

```powershell
uv run climate-pipeline reach thermal --site platte-louisville --since 2026-01-01 --root ..
uv run climate-pipeline reach context --site all --root ..
```

- **`thermal`:** a reach with a water-temperature card (`models/<site>/water_temperature.json`,
  today the Platte) gets a record per Landsat 8/9 pass with at least the card's clear-water pixels
  in the gauge's core window: the card's value in °C, its level and its 90 % interval, sealed
  (`docs/schema/README.md`, water-temperature record v1) and chained in `thermal/ledger.jsonl`.
  Beside them, `thermal/checks.csv` notes the gauge's own water temperature at each pass (approved,
  else provisional, labelled).
- **`context`:** `checks/context.csv` notes, at each recorded Sentinel-2 pass, what the gauge itself
  measured (discharge and gage height; at the Platte also water temperature, dissolved oxygen,
  specific conductance and nitrate plus nitrite). Measurements, never estimates.

## Climate context

```powershell
uv run climate-pipeline reach climate --site all --until 2026-10-17 --root ..
```

`climate` fetches the estimate station's daily mean discharge, and its daily mean water temperature
where the gauge measures it, over the whole period of record (USGS OGC API, `daily`). The values
stay as a snapshot in `docs/water-quality/reach/<site>/climate/daily.csv`, not served to the web.
From them it writes `examples/climate.json`, beside the examples, without touching any record or
ledger. These rules were fixed before the first value was fetched:

- **Per calendar year:** the peak (the highest daily mean discharge and its day); the 7-day low (the
  lowest mean of 7 consecutive days inside the year, all seven measured, and the last of them); the
  warmest day (the highest daily mean water temperature from June to September).
- **Ranked years:** a year is ranked when at least 90 % of its days have a discharge (for the
  temperature, 90 % of the days from June to September). The year of the last value is shown to
  date and never ranked. Ties share the better rank.
- **Labels:** a year with a provisional value says so. Discharge is converted to m³/s
  (1 ft³/s = 0.028316846592 m³/s).
- **What it is not:** the gauge's measurements, never a satellite estimate. It states no trend and
  no cause.

## Files for the web (`docs/water-quality/reach/<site>/examples/`, committed)

```powershell
uv run climate-pipeline reach examples --site mississippi-belle-chasse --all-records --root ..
uv run climate-pipeline reach render --site mississippi-belle-chasse --root ..
```

| File                 | Content                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------- |
| `records/*.json`     | The sealed records, unchanged (every one with `--all-records`, else the newest three)         |
| `latest.json`        | The newest record                                                                             |
| `series.json`        | Every record by date, trimmed for a chart                                                     |
| `ledger.jsonl`       | The whole ledger (`--all-records`; else `ledger.tail.jsonl`, its last lines)                  |
| `checks/*`           | The prospective check: each scene's estimate beside the gauge (report-only)                   |
| `cards/*.json`       | The reach's model cards: their hash is each record's `modelCardSha256`                        |
| `reach.json`         | The site, the estimate station (with its USGS page), the targets, the baseline and the cards  |
| `geometry.geojson`   | `render`: the centreline (with chainage), the two sub-reaches, the station and its window     |
| `maps/*.png`         | `render`: each recorded scene's NDTI over the pixels its medians read (encoding: `maps.json`) |
| `maps.json`          | `render`: the PNG encoding, the image's corners in WGS84 and one entry per scene              |
| `maps/*.rgb.webp`    | `render`: each pass in true color (bands 4, 3, 2) over the same box, for comparison           |
| `thermal/*`          | v6: the water-temperature records, their ledger, series and the gauge check                   |
| `checks/context.csv` | v6: the gauge's own readings at each pass (measurements, labelled)                            |
| `climate.json`       | `climate`: the gauge's whole record, each year's peak, 7-day low and warmest day, ranked      |

A map is a picture of the record's own pixels: NDTI is relative, so the maps carry no unit. A test
(`pipeline/tests/test_reach_examples.py`) fails if a committed record stops matching the schema, its
seal, its ledger chain or its card's hash.

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
