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
ungauged=(mississippi-st-joseph) # no gauge: no thermal, context or check

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
  step reach render --site "$site"
done
step reach check --site all
for site in "${demo[@]}" "${ungauged[@]}"; do
  step reach examples --site "$site" --all-records
done
step reach examples --site missouri-hermann
step ledger stamp # the new heads
if [ "$run_code" -eq 2 ]; then run_code=0; fi
exit "$run_code"
