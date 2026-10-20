<#
.SYNOPSIS
    Sign and anchor the heads the daily run grew on the data branch (the owner's step).

.DESCRIPTION
    1. Checks out origin/data in a temporary worktree.
    2. Signs every new ledger head with the ML-DSA-65 key (`climate-pipeline sign heads`; the
       private key is read from ~/.riveretch, never from the repository).
    3. Anchors every ledger that grew on Ethereum Sepolia (`contracts/scripts/anchor.ts`, with
       RIVERETCH_ROOT at the worktree; the owner key comes from the Hardhat keystore). The script
       rebuilds docs/ledgers/anchors.jsonl there from the chain.
    4. Commits the signatures and the anchoring log to the data branch and pushes it.

    The commit runs without the repository's Git hooks, as the daily workflow's do: the data branch
    holds generated files only, and Prettier must never rewrite a sealed record.

    Run from the repository root, whenever the data branch has new records:
      powershell -ExecutionPolicy Bypass -File pipeline\scripts\anchor-pending.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

git fetch origin data
$worktree = Join-Path ([IO.Path]::GetTempPath()) "riveretch-data-anchor"
if (Test-Path $worktree) { git worktree remove --force $worktree }
git worktree add -B data-anchor $worktree origin/data

try {
    # Main's frozen artifacts are the source; the data branch carries a copy.
    Copy-Item "docs\ledgers\frozen-artifacts.jsonl" (Join-Path $worktree "docs\ledgers\frozen-artifacts.jsonl")

    Push-Location "pipeline"
    uv run climate-pipeline sign heads --root $worktree
    if ($LASTEXITCODE -ne 0) { throw "sign heads failed ($LASTEXITCODE)" }
    Pop-Location

    Push-Location "contracts"
    $env:RIVERETCH_ROOT = $worktree
    npx hardhat run scripts/anchor.ts --network sepolia
    $code = $LASTEXITCODE
    Remove-Item Env:\RIVERETCH_ROOT
    Pop-Location
    if ($code -ne 0) { throw "anchor.ts failed ($code)" }

    Push-Location "pipeline"
    uv run climate-pipeline sign verify --root $worktree
    if ($LASTEXITCODE -ne 0) { throw "a signature does not verify" }
    Pop-Location

    $noHooks = Join-Path $worktree ".git-no-hooks"
    New-Item -ItemType Directory -Force -Path $noHooks | Out-Null
    git -C $worktree add -- docs/ledgers
    git -C $worktree diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git -C $worktree -c core.hooksPath=$noHooks commit -q -m "data: sign and anchor the new heads"
        git -C $worktree push origin data-anchor:data
    } else {
        Write-Output "Nothing new to sign or anchor."
    }
}
finally {
    Set-Location $root
    git worktree remove --force $worktree
    git branch -D data-anchor 2>$null
}
