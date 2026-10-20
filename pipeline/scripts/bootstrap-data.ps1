<#
.SYNOPSIS
    Start the data branch once: the daily workflow's working state and published files.

.DESCRIPTION
    Creates the orphan branch `data` (no code, generated files only) with:
      docs/water-quality/reach/<site>/examples/  main's committed copies (records, ledgers, maps)
      docs/ledgers/                              the anchoring log, the frozen artifacts and, if
                                                 any, the signatures and Bitcoin proofs
      state/reach/<site>/                        this machine's pipeline/out/reach/<site>/: the
                                                 working state `reach run` resumes from
    and pushes it to origin. It refuses when origin already has a data branch, or when a local
    ledger differs from the one committed on main (the state must be the sealed history).

    The commit runs without the repository's Git hooks: the data branch has no .prettierignore,
    and Prettier must never rewrite a sealed record (its seal would no longer match). Normal
    commits on main keep their hooks.

    Run once, from the repository root, after main is pushed:
      powershell -ExecutionPolicy Bypass -File pipeline\scripts\bootstrap-data.ps1
    With -DryRun it builds the branch and its commit locally, lists them and pushes nothing.

.PARAMETER DryRun
    Build and list the commit, then remove the worktree and the local branch; push nothing.
#>
param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root

git fetch origin
if (git ls-remote --heads origin data) { throw "origin already has a data branch" }

# The working state must be the sealed history: each local ledger equals main's copy.
$demo = @("mississippi-belle-chasse", "platte-louisville")
foreach ($site in $demo) {
    foreach ($ledger in @("ledger.jsonl", "thermal\ledger.jsonl")) {
        $local = Join-Path $root "pipeline\out\reach\$site\$ledger"
        $committed = Join-Path $root "docs\water-quality\reach\$site\examples\$ledger"
        if ((Get-FileHash $local).Hash -ne (Get-FileHash $committed).Hash) {
            throw "$site\$ledger differs from main's copy: the working state is not the sealed history"
        }
    }
}

$worktree = Join-Path ([IO.Path]::GetTempPath()) "riveretch-data"
if (Test-Path $worktree) { throw "$worktree exists: remove it first" }
git worktree add --orphan -b data $worktree

foreach ($examples in Get-ChildItem "docs\water-quality\reach\*\examples" -Directory) {
    $site = $examples.Parent.Name
    $target = Join-Path $worktree "docs\water-quality\reach\$site"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Recurse -Path $examples.FullName -Destination $target
}
$ledgers = Join-Path $worktree "docs\ledgers"
New-Item -ItemType Directory -Force -Path $ledgers | Out-Null
foreach ($file in @("anchors.jsonl", "frozen-artifacts.jsonl", "signatures.jsonl")) {
    if (Test-Path "docs\ledgers\$file") { Copy-Item "docs\ledgers\$file" $ledgers }
}
if (Test-Path "docs\ledgers\ots") { Copy-Item -Recurse "docs\ledgers\ots" $ledgers }
foreach ($state in Get-ChildItem "pipeline\out\reach" -Directory | Where-Object { $_.Name -ne "_superseded" }) {
    $target = Join-Path $worktree "state\reach"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Recurse -Path $state.FullName -Destination $target
    Get-ChildItem (Join-Path $target $state.Name) -Filter "daily*.log" | Remove-Item
}

# Byte for byte on every platform: LF line ends (a ledger's heads are hashes of its lines), and
# images and Bitcoin proofs as binary. Without it, a checkout on Windows could write CRLF.
$attributes = "# Generated data: LF line ends on every platform; images and proofs are binary.`n" +
    "* text=auto eol=lf`n*.png binary`n*.webp binary`n*.ots binary`n"
[IO.File]::WriteAllText((Join-Path $worktree ".gitattributes"), $attributes)

$noHooks = Join-Path $worktree ".git-no-hooks"
New-Item -ItemType Directory -Force -Path $noHooks | Out-Null
git -C $worktree add -A -- .gitattributes docs state
git -C $worktree -c core.hooksPath=$noHooks commit -q -m "data: start from main's snapshot and the working state"
if ($DryRun) {
    git -C $worktree log --stat --oneline -1 | Select-Object -Last 12
    Write-Output "files: $((git -C $worktree ls-files | Measure-Object).Count)"
    git worktree remove --force $worktree
    git branch -D data | Out-Null
    Write-Output "Dry run: nothing pushed; the local branch and worktree are removed."
    exit 0
}
git -C $worktree push -u origin data
git worktree remove --force $worktree
Write-Output "data branch pushed. Run the 'Daily run' workflow once by hand (Actions tab) to check it."
