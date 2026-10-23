"""The daily record (v1): one calendar year of a reach's daily river flow, as published.

The flow the Climate tab shows (preregistration-daily-record.md) comes from a station (USGS daily
means) or, on the Firat, a flood model (GloFAS v4): RiverEtch does not measure it. A record keeps
one year of it exactly as fetched, each value with the status its source gave it, so anyone can see
what the source published on the day it was fetched, and that it has not changed since. The seal
is the readings' seal: ``recordSha256`` is the SHA-256 of the record's canonical JSON (camelCase
keys, sorted, no whitespace, the seal left out), and each reach's daily-record list chains them. A
year that changes at its source gets a new record naming the one it replaces; none is rewritten.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Source(_Model):
    """Who published the values."""

    kind: Literal["usgs", "glofas"]
    station_id: str = Field(alias="stationId", description="e.g. USGS-06805500")
    name: str
    measured: bool = Field(description="false for a flood model's values")
    url: str = Field(description="the station's or the model's page")


class Series(_Model):
    """One parameter's daily values in the year: ``[day, value, status]``, in day order."""

    parameter: str = Field(description="USGS's code (00060, 00010) or GloFAS's river_discharge")
    name: str
    unit: str = Field(description="as the source publishes it")
    days: list[tuple[str, float, str]]


class Provenance(_Model):
    """How the values were fetched."""

    api: str
    query: dict[str, str]
    code_commit: str = Field(alias="codeCommit")


class DailyRecordV1(_Model):
    """One calendar year of a reach's daily flow, as fetched."""

    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    kind: Literal["daily_record"] = "daily_record"
    reach_id: str = Field(alias="reachId")
    record_id: str = Field(alias="recordId", description="<reach>:daily-record:<year>")
    year: int
    date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$", description="the year's last day with a value"
    )
    source: Source
    series: list[Series]
    fetched_utc: str = Field(alias="fetchedUtc")
    replaces: str | None = Field(description="the recordSha256 of the year's previous record")
    provenance: Provenance
    record_sha256: str | None = Field(default=None, alias="recordSha256")


def as_json(record: DailyRecordV1) -> dict[str, Any]:
    """The record as JSON values (camelCase keys), the seal included when set.

    Args:
        record: The record.

    Returns:
        The values.
    """
    return record.model_dump(mode="json", by_alias=True, exclude_none=False)


def canonical_json(record: DailyRecordV1) -> str:
    """The record's canonical JSON (the seal left out).

    Args:
        record: The record.

    Returns:
        The text that :func:`seal` hashes.
    """
    data = record.model_dump(mode="json", by_alias=True, exclude={"record_sha256"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def seal(record: DailyRecordV1) -> DailyRecordV1:
    """The record with its ``record_sha256`` set.

    Args:
        record: The record.

    Returns:
        The sealed copy.
    """
    digest = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return record.model_copy(update={"record_sha256": digest})


def is_sealed(record: DailyRecordV1) -> bool:
    """Whether the record's hash matches its content.

    Args:
        record: The record.

    Returns:
        True for an intact seal.
    """
    return seal(record).record_sha256 == record.record_sha256
