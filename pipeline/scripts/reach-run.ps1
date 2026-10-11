<#
.SYNOPSIS
    Periodic reach run (water-quality plan P3, D16): observation records v2 of a reach.

.DESCRIPTION
    Runs `climate-pipeline reach run` with uv from the pipeline folder. Each run appends to
    pipeline/out/reach/<site>/runs.log and exits with the run's code:
      0  done
      1  cannot run (no geometry, no NIR/red baseline, bad settings)
      2  partial: an acquisition failed; the next run retries it
      3  a cap stopped the run (network or free disk)
    It reads public data only (Earth Search, Open-Meteo), needs no credentials, and never
    commits or pushes. Register it with the Windows Task Scheduler (docs/water-quality/reach/).

.PARAMETER Site
    The reach's site id (pipeline/sites/<id>.yaml, listed in pipeline/reach.yaml).

.PARAMETER Uv
    The uv executable (default: the one on PATH).
#>
param(
    [string]$Site = "magdalena-puerto-wilches",
    [string]$Uv = ""
)

$ErrorActionPreference = "Stop"
$pipeline = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $pipeline
if (-not $Uv) { $Uv = (Get-Command uv).Source }

$folder = Join-Path $pipeline "out\reach\$Site"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$log = Join-Path $folder "runs.log"
$out = Join-Path $folder "last-run.out.log"
$err = Join-Path $folder "last-run.err.log"

# Start-Process joins arguments with spaces, so the root (which may hold spaces) is quoted here.
$arguments = "run climate-pipeline reach run --site $Site --root `"$root`""
Add-Content -Path $log -Encoding UTF8 -Value "=== $(Get-Date -Format o) reach run $Site"
$process = Start-Process -FilePath $Uv -ArgumentList $arguments -WorkingDirectory $pipeline `
    -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
$code = $process.ExitCode
Get-Content -Path $out, $err | Add-Content -Path $log -Encoding UTF8
Add-Content -Path $log -Encoding UTF8 -Value "=== exit $code"
exit $code
