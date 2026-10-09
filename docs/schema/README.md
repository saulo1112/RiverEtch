# Observation record contract (v1)

[`observation-record.v1.schema.json`](observation-record.v1.schema.json) is the JSON Schema
(draft 2020-12) of one published observation: one scene of a river reach.

- **Generated, never edited by hand.** It comes from the pydantic models in
  `pipeline/src/climate_pipeline/contract/observation.py`:

  ```sh
  climate-pipeline contract schema --out docs/schema/observation-record.v1.schema.json
  ```

  A test fails if the file and the models drift.

- **Sample records** are built from a case file v1, reading each STAC item's JSON to hash it:

  ```sh
  climate-pipeline contract sample --case docs/magdalena-validation/magdalena.sample.json \
    --reach-id magdalena-puerto-wilches --out records.json
  ```

  `pipeline/tests/fixtures/observation-records.sample.json` holds five real records made this way.

- **A sibling of the case file v1, not a replacement.** The case file
  (`climate_pipeline.validation.case`, `schemaVersion: 1`) is unchanged and pinned by the
  validations' reproduction checks.

## What a record holds

| Field                            | Meaning                                                                                                                                                                                |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `date`, `sceneId`, `stacItemIds` | The scene (local date of the acquisition) and its STAC items                                                                                                                           |
| `index`                          | NDTI per sub-reach, their mean (`reach`) and difference (`delta`): **relative, never NTU**                                                                                             |
| `zScore`                         | Leave-one-out robust z of the three signals under the screening rule (D0)                                                                                                              |
| `verdict`                        | The rule-based flag: anomalous when a D0 \|z\| reaches `threshold`. Computed from `zScore` only                                                                                        |
| `rain`                           | Rain coincidence: point rule, catchment rule, union                                                                                                                                    |
| `calibration`                    | `status` (`none`, `failed`, `insufficient_data`, `passed`); for `passed`: model id, version, parameter hash, target, unit, `value`, `uncertainty`, `validRange`, or an `abstainReason` |
| `climateContext`                 | `status` (`not_run`, `weak`, `passed`), the flagged signal's season-and-rain model, its expected value and residual, a `label`, and context (discharge percentile, ENSO phase)         |
| `provenance`                     | Collection, each STAC item's URL and SHA-256 of its JSON, code commit, processing-settings hash, BOA-offset flags and processing baselines                                             |
| `recordSha256`                   | SHA-256 of the canonical JSON (sorted keys, no whitespace, this field left out). A registry can anchor it                                                                              |

## Rules the schema enforces

- `calibration.status` ≠ `passed` ⇒ `value` and `uncertainty` are null.
- `calibration.status` = `passed` and no `abstainReason` ⇒ the model, `value`, `uncertainty` and
  `validRange` are all present.
- `climateContext.status` ≠ `passed` ⇒ `label` is `not_evaluated`, and `expected`, `residual` and
  `residualZ` are null.
- `verdict.anomalous` is true exactly when `verdict.signals` is not empty. The model also checks
  that the verdict follows from `zScore` and `threshold`: no model field can set it.

## Display rules

1. **Show a physical unit only when `calibration.status == "passed"` and `abstainReason` is
   null.** Show it with its `uncertainty` and `validRange`, and name the `target`.
   - `cm_d` is "IDEAM rating-model daily concentration", never a direct measurement.
   - Otherwise show "index departure" (the NDTI value and its z), with no unit.
2. **Show a climate label only when `climateContext.status == "passed"`.** `not_evaluated` means
   "not assessed", not "normal".
3. **Never show `unexplained` as human pressure, a violation or a cause.** It means only that the
   season-and-rain model did not account for the departure.
4. **Discharge percentile and ENSO phase are context.** Never present them as an explanation.

## How the calibration validation fills a record

`climate-pipeline calibration run` writes the reach's records with both blocks filled in.

- **Which target:** a record has one calibration block. It carries the first target, in the
  settings' order (turbidity, tss, cm_d), whose calibration passed.
  - Its value comes from the reach station's window on that scene.
  - It is replaced by an `abstainReason` when that is missing, or when the calibration was not
    trained at the reach's stations.
- **When no target passed:** the status is `failed` (when any target failed) or
  `insufficient_data`, and the record carries no value.

## Mapping from older shapes

| Case file v1 (`ui.scenes[]`)               | Observation record                                                     |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `date`                                     | `date`                                                                 |
| `stacItemIds`                              | `stacItemIds`, `provenance.stacItems[].id`                             |
| `processingBaseline`                       | `provenance.processingBaseline`                                        |
| `ndti.upstream` / `downstream` / `delta`   | `index.upstream` / `downstream` / `delta`; `index.reach` is their mean |
| `z.D0.*`                                   | `zScore.*` (other variants stay in the case file)                      |
| `variantFlags.D0`                          | `verdict.anomalous` (recomputed from `zScore`)                         |
| `rain`                                     | `rain`                                                                 |
| `excluded`, `exclusionReason`              | not published as records (only usable scenes become records)           |
| `manifest.commit`, `manifest.configSha256` | `provenance.codeCommit`, `provenance.processingParamsSha256`           |

| Web `CaseData` (`web/src/features/case/types.ts`, illustrative) | Observation record                                                                                  |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `samples[]` (NDTI per scene)                                    | `index` of each record                                                                              |
| `anomaly.zScore`, `sceneDate`                                   | `zScore`, `date` of the flagged record                                                              |
| `classification: "normal"`                                      | `climateContext.label: "normal"` (only if `status == "passed"`)                                     |
| `classification: "explained_by_climate"`                        | `climateContext.label: "explained_by_climate"` (only if `status == "passed"`)                       |
| `classification: "candidate_human_pressure"`                    | **No equivalent.** The nearest is `unexplained`, which must not be shown as human pressure (rule 3) |
| `rainfall[]`                                                    | `rain` flags (daily sums are not part of the record)                                                |
| `illustrative: true`                                            | Not needed: records are real. Synthetic events stay in the case file's `synthetic_overlay`          |

The web app is not changed by this contract. Moving it to these records is a separate change.
