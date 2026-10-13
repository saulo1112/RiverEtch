"""The water-temperature record (v1): one Landsat 8/9 pass of a reach (preregistration v6, C).

Landsat passes are not Sentinel-2 passes, so water temperature gets its own records beside the
observation records v2, with the same seal: ``recordSha256`` is the SHA-256 of the record's
canonical JSON (camelCase keys, sorted, no whitespace, the seal left out), and each reach's
temperature ledger chains them. The value comes from the reach's temperature card, with the
card's level and its 90 % interval (split conformal on absolute errors, in °C).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["validated", "estimated", "indicative", "none"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Interval(_Model):
    """The value's interval of known coverage, in °C."""

    low: float
    high: float
    coverage: float
    method: Literal["split_conformal_absolute"]


class Estimate(_Model):
    """Water temperature at the gauge's window."""

    target: Literal["water_temperature"] = "water_temperature"
    unit: Literal["°C"] = "°C"
    level: Level
    value: float | None = None
    interval: Interval | None = None
    model_id: str = Field(alias="modelId")
    model_version: str = Field(alias="modelVersion")
    model_card_sha256: str = Field(alias="modelCardSha256")
    basis: Literal["preregistered_lockbox_site"]


class Window(_Model):
    """The gauge's core window on Landsat's 30 m pixels."""

    pixels: int
    water_pixels: int = Field(alias="waterPixels", description="clear water in QA_PIXEL")
    surface_temperature_k: float = Field(alias="surfaceTemperatureK", description="median ST_B10")


class StacItemRef(_Model):
    """One Landsat item behind the pass."""

    id: str
    url: str


class Provenance(_Model):
    """Where the record came from."""

    collection: Literal["landsat-c2-l2"] = "landsat-c2-l2"
    stac_items: list[StacItemRef] = Field(alias="stacItems")
    code_commit: str = Field(alias="codeCommit")
    processing_params_sha256: str = Field(alias="processingParamsSha256")


class ThermalRecordV1(_Model):
    """One water-temperature observation of a reach."""

    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    kind: Literal["water_temperature"] = "water_temperature"
    reach_id: str = Field(alias="reachId")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    datetime_utc: str = Field(alias="datetimeUtc", description="the pass's acquisition time")
    scene_id: str = Field(alias="sceneId")
    platform: str
    window: Window
    estimate: Estimate
    provenance: Provenance
    record_sha256: str | None = Field(default=None, alias="recordSha256")


def canonical_json(record: ThermalRecordV1) -> str:
    """The record's canonical JSON (the seal left out).

    Args:
        record: The record.

    Returns:
        The text that :func:`seal` hashes.
    """
    data = record.model_dump(mode="json", by_alias=True, exclude={"record_sha256"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def seal(record: ThermalRecordV1) -> ThermalRecordV1:
    """The record with its ``record_sha256`` set.

    Args:
        record: The record.

    Returns:
        The sealed copy.
    """
    digest = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return record.model_copy(update={"record_sha256": digest})


def is_sealed(record: ThermalRecordV1) -> bool:
    """Whether the record's hash matches its content.

    Args:
        record: The record.

    Returns:
        True for an intact seal.
    """
    return seal(record).record_sha256 == record.record_sha256
