"""The observation record: one published scene of a reach, saying what was and was not calibrated.

A record carries the scene, its relative index (NDTI, never NTU), the D0 z-scores and the
rule-based verdict computed from them only, the rain flags, a calibration block and a climate
context block, and the provenance of every input. Conditional rules keep the record honest:

* a calibration whose status is not ``passed`` carries no value and no uncertainty;
* a climate context whose status is not ``passed`` is labelled ``not_evaluated``;
* the verdict must follow from the z-scores (the trust boundary: no model field can set it).

``record_sha256`` is the SHA-256 of the record's canonical JSON (sorted keys, no whitespace, the
hash field left out), so a registry can anchor the record later. The JSON Schema in
``docs/schema/observation-record.v1.schema.json`` is generated from these models by
:func:`json_schema`; a test fails when the two drift. This contract is a sibling of the case file
v1 (``climate_pipeline.validation.case``), which it does not change.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION: Final = 1
SCHEMA_ID: Final = "observation-record.v1"
SIGNALS: Final = ("upstream", "downstream", "delta")
NOT_RUN_RULE: Final = "climate context not run"

Signal = Literal["upstream", "downstream", "delta"]
CalibrationStatus = Literal["none", "failed", "insufficient_data", "passed"]
ClimateStatus = Literal["not_run", "weak", "passed"]
ClimateLabel = Literal["normal", "explained_by_climate", "unexplained", "not_evaluated"]
Target = Literal["turbidity", "tss", "cm_d"]
EnsoPhase = Literal["el_nino", "la_nina", "neutral"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class IndexValues(_Model):
    """The relative index per sub-reach, their mean and their difference (never NTU)."""

    name: Literal["NDTI"] = "NDTI"
    upstream: float | None
    downstream: float | None
    reach: float | None = Field(description="mean of the sub-reaches that were measured")
    delta: float | None = Field(description="downstream minus upstream")


class ZScores(_Model):
    """Leave-one-out robust z-scores of the three signals under the screening rule (D0)."""

    rule: Literal["D0"] = "D0"
    upstream: float | None
    downstream: float | None
    delta: float | None


class Verdict(_Model):
    """The rule-based flag: a signal is anomalous when its D0 |z| reaches the threshold."""

    rule: Literal["D0"] = "D0"
    threshold: float
    anomalous: bool
    signals: list[Signal]

    @model_validator(mode="after")
    def _check(self) -> Verdict:
        if self.anomalous != bool(self.signals):
            raise ValueError("a verdict is anomalous exactly when it lists a signal")
        return self


class RainFlags(_Model):
    """Rain coincidence of the scene (None: unknown)."""

    point: bool | None
    catchment: bool | None
    union: Literal["yes", "no", "unknown"]


class Uncertainty(_Model):
    """An interval around a calibrated value."""

    low: float
    high: float
    kind: Literal["loo_mdsa_band"] = Field(
        description="value / (1 + MdSA) to value x (1 + MdSA), with the model's LOO MdSA"
    )

    @model_validator(mode="after")
    def _check(self) -> Uncertainty:
        if not self.low <= self.high:
            raise ValueError("uncertainty low must not exceed high")
        return self


class Calibration(_Model):
    """What a calibrated model says about the scene, if one passed; otherwise why there is none."""

    status: CalibrationStatus
    model_id: str | None = Field(default=None, alias="modelId")
    version: str | None = None
    parameters_hash: str | None = Field(default=None, alias="parametersHash")
    target: Target | None = None
    unit: str | None = None
    value: float | None = None
    uncertainty: Uncertainty | None = None
    valid_range: tuple[float, float] | None = Field(default=None, alias="validRange")
    abstain_reason: str | None = Field(default=None, alias="abstainReason")

    @model_validator(mode="after")
    def _check(self) -> Calibration:
        if self.status != "passed":
            if self.value is not None or self.uncertainty is not None:
                raise ValueError("only a passed calibration carries a value or an uncertainty")
            return self
        needed = (self.model_id, self.version, self.parameters_hash, self.target, self.unit)
        if any(v is None for v in needed) or self.valid_range is None:
            raise ValueError("a passed calibration names its model, version, hash, target, unit")
        if self.abstain_reason is None and (self.value is None or self.uncertainty is None):
            raise ValueError("a passed calibration that does not abstain carries a value")
        if self.abstain_reason is not None and (
            self.value is not None or self.uncertainty is not None
        ):
            raise ValueError("an abstaining calibration carries no value")
        return self


class ClimateContext(_Model):
    """Whether rain and season explain the flagged signal, when that signal's model passed."""

    status: ClimateStatus
    signal: Signal | None = None
    model_id: str | None = Field(default=None, alias="modelId")
    expected: float | None = None
    residual: float | None = None
    residual_z: float | None = Field(default=None, alias="residualZ")
    label: ClimateLabel
    rule: str
    discharge_percentile: float | None = Field(
        default=None, alias="dischargePercentile", ge=0, le=1, description="context only"
    )
    enso_phase: EnsoPhase | None = Field(
        default=None, alias="ensoPhase", description="context only"
    )

    @model_validator(mode="after")
    def _check(self) -> ClimateContext:
        model_fields = (self.expected, self.residual, self.residual_z)
        if self.status != "passed":
            if self.label != "not_evaluated" or any(v is not None for v in model_fields):
                raise ValueError("without a passed climate model the label is not_evaluated")
            return self
        if self.label == "not_evaluated":
            raise ValueError("a passed climate model gives a label")
        if self.label != "normal" and (
            self.signal is None or self.model_id is None or any(v is None for v in model_fields)
        ):
            raise ValueError("a climate label names its signal, model, expectation and residual")
        return self


class StacItemRef(_Model):
    """One STAC item behind the scene, with the SHA-256 of its JSON when it was read."""

    id: str
    url: str
    sha256: str | None = None
    retrieved_utc: str | None = Field(default=None, alias="retrievedUtc")


class Provenance(_Model):
    """Where the record came from."""

    collection: str
    stac_items: list[StacItemRef] = Field(alias="stacItems")
    code_commit: str = Field(alias="codeCommit")
    processing_params_sha256: str = Field(alias="processingParamsSha256")
    boa_offset_applied: list[bool | None] = Field(alias="boaOffsetApplied")
    processing_baseline: list[str] = Field(alias="processingBaseline")


class ObservationRecord(_Model):
    """One published observation of a reach."""

    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    reach_id: str = Field(alias="reachId")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scene_id: str = Field(alias="sceneId")
    stac_item_ids: list[str] = Field(alias="stacItemIds")
    index: IndexValues
    z_score: ZScores = Field(alias="zScore")
    verdict: Verdict
    rain: RainFlags
    calibration: Calibration
    climate_context: ClimateContext = Field(alias="climateContext")
    provenance: Provenance
    record_sha256: str | None = Field(default=None, alias="recordSha256")

    @model_validator(mode="after")
    def _check(self) -> ObservationRecord:
        if self.stac_item_ids != [item.id for item in self.provenance.stac_items]:
            raise ValueError("stacItemIds must list the provenance items, in order")
        if self.verdict != verdict_from_z(self.z_score, self.verdict.threshold):
            raise ValueError("the verdict must follow from the D0 z-scores alone")
        return self


def verdict_from_z(z: ZScores, threshold: float) -> Verdict:
    """The rule-based verdict of a scene, from its D0 z-scores only.

    Args:
        z: The scene's D0 z-scores.
        threshold: The anomaly threshold (|z| at or above it).

    Returns:
        The verdict.
    """
    values: list[tuple[Signal, float | None]] = [
        ("upstream", z.upstream),
        ("downstream", z.downstream),
        ("delta", z.delta),
    ]
    signals: list[Signal] = [
        s for s, v in values if v is not None and math.isfinite(v) and abs(v) >= threshold
    ]
    return Verdict(threshold=threshold, anomalous=bool(signals), signals=signals)


def canonical_json(record: ObservationRecord) -> str:
    """The record's canonical JSON: camelCase keys, sorted, no whitespace, no hash field.

    Args:
        record: The record.

    Returns:
        The text that :func:`record_hash` hashes.
    """
    data = record.model_dump(mode="json", by_alias=True, exclude={"record_sha256"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(record: ObservationRecord) -> str:
    """SHA-256 of the record's canonical JSON.

    Args:
        record: The record.

    Returns:
        The hex digest.
    """
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def seal(record: ObservationRecord) -> ObservationRecord:
    """The record with its ``record_sha256`` set.

    Args:
        record: The record (any hash it carries is replaced).

    Returns:
        The sealed copy.
    """
    return record.model_copy(update={"record_sha256": record_hash(record)})


def is_sealed(record: ObservationRecord) -> bool:
    """Whether the record's hash matches its content.

    Args:
        record: The record.

    Returns:
        True when ``record_sha256`` equals the hash of the canonical JSON.
    """
    return record.record_sha256 == record_hash(record)


# ----------------------------------------------------------------------------------------------
# JSON Schema
# ----------------------------------------------------------------------------------------------

_NOT_PASSED: Final = {
    "properties": {"status": {"not": {"const": "passed"}}},
    "required": ["status"],
}


def json_schema() -> dict[str, Any]:
    """The JSON Schema of the record, generated from the models, with the conditional rules.

    Returns:
        The schema (draft 2020-12).
    """
    schema = ObservationRecord.model_json_schema(by_alias=True, mode="validation")
    defs = schema["$defs"]
    defs["Calibration"]["allOf"] = [
        {
            "if": _NOT_PASSED,
            "then": {"properties": {"value": {"const": None}, "uncertainty": {"const": None}}},
        },
        {
            "if": {
                "properties": {"status": {"const": "passed"}, "abstainReason": {"const": None}},
                "required": ["status"],
            },
            "then": {
                "required": ["modelId", "version", "parametersHash", "target", "unit", "value",
                             "uncertainty", "validRange"],
                "properties": {"value": {"type": "number"},
                               "uncertainty": {"$ref": "#/$defs/Uncertainty"}},
            },
        },
    ]  # fmt: skip
    defs["ClimateContext"]["allOf"] = [
        {
            "if": _NOT_PASSED,
            "then": {
                "properties": {
                    "label": {"const": "not_evaluated"},
                    "expected": {"const": None},
                    "residual": {"const": None},
                    "residualZ": {"const": None},
                }
            },
        },
        {
            "if": {"properties": {"status": {"const": "passed"}}, "required": ["status"]},
            "then": {"properties": {"label": {"not": {"const": "not_evaluated"}}}},
        },
    ]
    defs["Verdict"]["allOf"] = [
        {
            "if": {"properties": {"anomalous": {"const": True}}, "required": ["anomalous"]},
            "then": {"properties": {"signals": {"minItems": 1}}},
            "else": {"properties": {"signals": {"maxItems": 0}}},
        }
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        **schema,
        "description": (
            "One published observation of a river reach. The index is relative (never NTU); a "
            "physical value appears only when calibration.status is 'passed' and no "
            "abstainReason is set. The verdict follows from the D0 z-scores alone."
        ),
    }


def schema_text() -> str:
    """The schema as committed: indented JSON with sorted keys and a final newline.

    Returns:
        The text of ``docs/schema/observation-record.v1.schema.json``.
    """
    return json.dumps(json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------------------------------------
# Records from the case file v1 (no calibration, no climate model yet)
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemMeta:
    """What was read from one STAC item's JSON."""

    url: str
    sha256: str | None
    retrieved_utc: str | None
    boa_offset_applied: bool | None
    processing_baseline: str


def _num(value: Any, digits: int) -> float | None:
    if value is None:
        return None
    x = float(value)
    return round(x, digits) if math.isfinite(x) else None


def _reach(up: float | None, down: float | None) -> float | None:
    values = [v for v in (up, down) if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def records_from_case(
    case: Mapping[str, Any],
    reach_id: str,
    collection: str,
    items: Mapping[str, ItemMeta],
    threshold: float,
    dates: Sequence[str] | None = None,
) -> list[ObservationRecord]:
    """Observation records for the usable scenes of a case file v1.

    Calibration is ``none`` and the climate context ``not_run``, because neither has run when a
    case file is written.

    Args:
        case: The case file v1 (as loaded JSON).
        reach_id: The reach's site id.
        collection: The STAC collection the scenes came from.
        items: Item id -> what its JSON said.
        threshold: The D0 anomaly threshold.
        dates: Only these scene dates (default: every usable scene).

    Returns:
        Sealed records, in the case file's order.
    """
    manifest = case["manifest"]
    out = []
    for scene in case["ui"]["scenes"]:
        if scene["excluded"] or (dates is not None and scene["date"] not in dates):
            continue
        ndti, d0 = scene["ndti"], scene["z"]["D0"]
        z = ZScores(
            upstream=_num(d0.get("upstream"), 2),
            downstream=_num(d0.get("downstream"), 2),
            delta=_num(d0.get("delta"), 2),
        )
        ids = list(scene["stacItemIds"])
        metas = [items[i] for i in ids]
        up, down = _num(ndti.get("upstream"), 4), _num(ndti.get("downstream"), 4)
        record = ObservationRecord(
            reach_id=reach_id,
            date=scene["date"],
            scene_id=f"{reach_id}:{scene['date']}",
            stac_item_ids=ids,
            index=IndexValues(
                upstream=up, downstream=down, reach=_reach(up, down),
                delta=_num(ndti.get("delta"), 4),
            ),
            z_score=z,
            verdict=verdict_from_z(z, threshold),
            rain=RainFlags(
                point=scene["rain"]["point"], catchment=scene["rain"]["catchment"],
                union=scene["rain"]["union"],
            ),
            calibration=Calibration(status="none"),
            climate_context=ClimateContext(
                status="not_run", label="not_evaluated", rule=NOT_RUN_RULE
            ),
            provenance=Provenance(
                collection=collection,
                stac_items=[
                    StacItemRef(id=i, url=m.url, sha256=m.sha256, retrieved_utc=m.retrieved_utc)
                    for i, m in zip(ids, metas, strict=True)
                ],
                code_commit=str(manifest["commit"]),
                processing_params_sha256=str(manifest["configSha256"]),
                boa_offset_applied=[m.boa_offset_applied for m in metas],
                processing_baseline=[m.processing_baseline for m in metas],
            ),
        )  # fmt: skip
        out.append(seal(record))
    return out


def item_json_url(item_id: str) -> str:
    """The public S3 URL of a Sentinel-2 L2A COG item's JSON (Earth Search ``sentinel-2-l2a``).

    Args:
        item_id: E.g. ``S2A_18NXP_20181205_0_L2A``.

    Returns:
        The URL.
    """
    _, tile, day, _, _ = item_id.split("_")
    zone, band, square = tile[:2], tile[2], tile[3:]
    path = f"{zone}/{band}/{square}/{day[:4]}/{int(day[4:6])}/{item_id}/{item_id}.json"
    return f"https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/{path}"


def item_meta_from_json(url: str, body: bytes, retrieved_utc: str) -> ItemMeta:
    """What the record needs from one item's JSON.

    Args:
        url: Where it was read.
        body: The raw bytes (hashed as they are).
        retrieved_utc: When.

    Returns:
        The item's provenance.
    """
    props = json.loads(body)["properties"]
    offset = props.get("earthsearch:boa_offset_applied")
    return ItemMeta(
        url=url,
        sha256=hashlib.sha256(body).hexdigest(),
        retrieved_utc=retrieved_utc,
        boa_offset_applied=offset if isinstance(offset, bool) else None,
        processing_baseline=str(props.get("s2:processing_baseline", "unknown")),
    )
