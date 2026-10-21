#!/usr/bin/env bash
# Daily run of the reaches (the port of daily.ps1 for GitHub Actions, .github/workflows/daily.yml):
# score the committed claims, seal the new passes, publish the web's copies, and timestamp every
# ledger head on Bitcoin (OpenTimestamps, no key). It never signs, anchors or pushes: the workflow
# commits the result to the data branch, and the owner anchors and signs from there.
#
# Each step's arguments, exit code and last output line go to pipeline/out/reach/daily-steps.jsonl,
# which `climate-pipeline status` turns into status.json. Exit code: 0 when reach run finished or
# ran partly (2: some scenes not published yet), else reach run's code (3: a cap stopped it).
set -u

root="$(cd "$(dirname "$0")/../.." && pwd)"
folder="$root/pipeline/out/reach"
mkdir -p "$folder"
steps="$folder/daily-steps.jsonl"
: > "$steps"
demo=(mississippi-belle-chasse platte-louisville)
ungauged=(mississippi-st-joseph firat-birecik) # no gauge: no thermal, context or check

# One step: `climate-pipeline <arguments>`; its output goes to the job log, its result to $steps.
step() {
  local log code
  log="$(mktemp)"
  (cd "$root/pipeline" && uv run climate-pipeline "$@" --root "$root") > "$log" 2>&1
  code=$?
  cat "$log"
  jq -cn --arg args "$*" --argjson exit "$code" --arg last "$(tail -n 1 "$log")" \
    '{args: $args, exit: $exit, last: $last}' >> "$steps"
  rm -f "$log"
  return "$code"
}

step ledger upgrade # Bitcoin attestations of last run's heads, before the score needs them
step reach score --site all
step reach run --site all
run_code=$?
for site in "${demo[@]}"; do
  step reach thermal --site "$site"
  step reach context --site "$site"
  step reach render --site "$site"
done
for site in "${ungauged[@]}"; do
  # Passes sealed with an earlier card, read again with the current one (each once; a no-op when
  # none is left): preregistration-four-classes.md, section 4.
  step reach reread --site "$site"
  step reach render --site "$site"
done
# The year's check, from 2026-01-01, as the committed one was made (the report's "13 of 18" and the
# web's station values at every 2026 pass): without --since it would keep only the passes after
# the cards' commit.
step reach check --site all --since 2026-01-01
for site in "${demo[@]}" "${ungauged[@]}"; do
  step reach examples --site "$site" --all-records
done
step reach examples --site missouri-hermann
# Each climate.json from its committed daily snapshot (fetching nothing), so its count of the year's
# passes follows the published series: the demo reaches, and St. Joseph's station upstream.
for site in "${demo[@]}" mississippi-st-joseph; do
  step reach climate --site "$site" --snapshot
done
step ledger stamp # the new heads
if [ "$run_code" -eq 2 ]; then run_code=0; fi
exit "$run_code"
