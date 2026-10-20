<#
.SYNOPSIS
    Daily run of the demo reaches (prospective scoring, rule v1): score, record, publish.

.DESCRIPTION
    Runs, with uv from the pipeline folder:
      1. reach score    the claims anchored last evening, against their gauge (rule v1,
                        docs/water-quality/prospective.md; it waits 12 h after each overpass)
      2. reach run      new Sentinel-2 passes of every reach (sealed records, ledgers)
      3. reach thermal  new Landsat passes of the demo reaches (water temperature)
      4. reach context  the gauges' own readings at each pass
      5. reach render   the maps of the new passes (web)
      6. reach check    the post-commit check (report-only)
      7. reach examples the published copies under docs/water-quality/reach/<site>/examples/

    It reads public data only, needs no credentials, and never commits, pushes or anchors.
    Afterwards the owner commits the changes and anchors them:
      cd contracts; npx hardhat run scripts/anchor.ts --network sepolia
    Each step appends to pipeline/out/reach/daily.log; the script exits with reach run's code
    (0 done, 2 partial, 3 a cap stopped it).

    Register it once (PowerShell), to run every day at 19:00:
      $script = "<repository>\pipeline\scripts\daily.ps1"
      $action = New-ScheduledTaskAction -Execute "powershell.exe" `
          -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
      $trigger = New-ScheduledTaskTrigger -Daily -At 7:00pm
      Register-ScheduledTask -TaskName "RiverEtch daily" -Action $action -Trigger $trigger `
          -Description "Score, record and publish the demo reaches (no commits)"

.PARAMETER Uv
    The uv executable (default: the one on PATH).
#>
param(
    [string]$Uv = ""
)

$ErrorActionPreference = "Stop"
$pipeline = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $pipeline
if (-not $Uv) { $Uv = (Get-Command uv).Source }

$folder = Join-Path $pipeline "out\reach"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$log = Join-Path $folder "daily.log"
$out = Join-Path $folder "daily.out.log"
$err = Join-Path $folder "daily.err.log"
$demo = @("mississippi-belle-chasse", "platte-louisville")
$ungauged = @("mississippi-st-joseph") # no gauge: no thermal, context or check

# One step: `climate-pipeline <arguments>`, its output appended to the log; returns its exit code.
function Step([string]$arguments) {
    # Start-Process joins arguments with spaces, so the root (which may hold spaces) is quoted.
    $full = "run climate-pipeline $arguments --root `"$root`""
    Add-Content -Path $log -Encoding UTF8 -Value "=== $(Get-Date -Format o) $arguments"
    $process = Start-Process -FilePath $Uv -ArgumentList $full -WorkingDirectory $pipeline `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    Get-Content -Path $out, $err | Add-Content -Path $log -Encoding UTF8
    Add-Content -Path $log -Encoding UTF8 -Value "=== exit $($process.ExitCode)"
    return $process.ExitCode
}

Step "reach score --site all" | Out-Null
$code = Step "reach run --site all"
foreach ($site in $demo) {
    Step "reach thermal --site $site" | Out-Null
    Step "reach context --site $site" | Out-Null
    Step "reach render --site $site" | Out-Null
}
foreach ($site in $ungauged) {
    Step "reach render --site $site" | Out-Null
}
Step "reach check --site all" | Out-Null
foreach ($site in $demo + $ungauged) {
    Step "reach examples --site $site --all-records" | Out-Null
}
Step "reach examples --site missouri-hermann" | Out-Null
exit $code
