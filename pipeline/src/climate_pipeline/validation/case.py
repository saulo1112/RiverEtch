"""The case file the demo reads: the reach, its real scenes and a clearly simulated permit.

The ``ui`` block names the river and the municipality, never the dam or the company; any permit
in it is simulated. Real names live only in ``context.sources``, marked as public-source context.
The reach geometry matches the web's ``ReachFeature`` (a GeoJSON LineString in ``[lng, lat]``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from climate_pipeline.screening.events import CatalogEvent
from climate_pipeline.screening.mask import RiverGeometry, path_chainage
from climate_pipeline.screening.rio import Grid, rowcols_lonlat
from climate_pipeline.screening.stage2 import SIGNALS, Stage2Scene

SIMULATED_HOLDER: Final = "simulated permit holder"
SIMULATED_LIMIT: Final = "illustrative limit, not the real licence"
CONTEXT_LABEL: Final = "public-source context, not an accusation"

EVENT_SUMMARIES = {
    "flow_increase": "reported rise in river flow",
    "contingency": "reported operational alert",
    "powerhouse_operation": "reported change in plant operation",
    "flood": "reported flood",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class LineString(_Model):
    """A GeoJSON LineString in ``[lng, lat]`` order."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]


class ReachProperties(_Model):
    """Properties of the reach feature (the web's ``ReachFeature.properties``)."""

    name: str
    length_m: float = Field(alias="lengthM")


class ReachFeature(_Model):
    """The reach as a GeoJSON Feature, upstream to downstream."""

    type: Literal["Feature"] = "Feature"
    properties: ReachProperties
    geometry: LineString


class Subreach(_Model):
    """One measured window of the reach."""

    name: str
    chainage_m: tuple[float, float] = Field(alias="chainageM")
    line: LineString


class SubreachValues(_Model):
    """A value per sub-reach (None when the sub-reach is missing)."""

    upstream: float | None
    downstream: float | None


class Rain(_Model):
    """Rain coincidence flags of a scene (None: unknown)."""

    point: bool | None
    catchment: bool | None
    union: Literal["yes", "no", "unknown"]


class CaseScene(_Model):
    """One observable scene of the reach."""

    date: str
    stac_item_ids: list[str] = Field(alias="stacItemIds")
    processing_baseline: list[str] = Field(alias="processingBaseline")
    ndti: dict[str, float | None]
    z: dict[str, dict[str, float | None]]  # variant -> signal -> z
    variant_flags: dict[str, bool] = Field(alias="variantFlags")
    persistence: int
    rain: Rain
    valid_water_px: SubreachValues = Field(alias="validWaterPx")
    glint_share: SubreachValues = Field(alias="glintShare")
    water_b11: SubreachValues = Field(alias="waterB11")
    excluded: bool
    exclusion_reason: str = Field(alias="exclusionReason")


class CaseEvent(_Model):
    """A documented event, as a neutral summary."""

    date: str
    date_end: str = Field(alias="dateEnd")
    type: str
    confidence: str
    summary: str


class Permit(_Model):
    """The demo's permit: always simulated."""

    simulated: Literal[True] = True
    holder: Literal["simulated permit holder"] = SIMULATED_HOLDER
    label: Literal["illustrative limit, not the real licence"] = SIMULATED_LIMIT
    note: str


class ValidationSummary(_Model):
    """The mechanical verdict of the validation."""

    verdict: str
    episodes: int
    episodes_needed: int = Field(alias="episodesNeeded")
    share_ratio: float | None = Field(alias="shareRatio")
    share_ratio_needed: float = Field(alias="shareRatioNeeded")


class Ui(_Model):
    """Everything the interface may show."""

    reach_label: str = Field(alias="reachLabel")
    reach: ReachFeature
    subreaches: list[Subreach]
    scenes: list[CaseScene]
    events: list[CaseEvent]
    permit: Permit
    validation: ValidationSummary
    note: str


class ContextSource(_Model):
    """A public source behind the context (real names allowed here only)."""

    title: str
    url: str
    text: str


class Context(_Model):
    """Public-source context, kept apart from the interface."""

    label: Literal["public-source context, not an accusation"] = CONTEXT_LABEL
    sources: list[ContextSource]


class Manifest(_Model):
    """Provenance of the case file."""

    commit: str
    config_sha256: str = Field(alias="configSha256")
    method_blob: str = Field(alias="methodBlob")
    item_ids_sha256: dict[str, str] = Field(alias="itemIdsSha256")


class CaseFile(_Model):
    """The whole case file."""

    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    ui: Ui
    context: Context
    manifest: Manifest

    def to_json(self) -> str:
        """Serialize with the web's camelCase names.

        Returns:
            JSON text.
        """
        return self.model_dump_json(by_alias=True, indent=1) + "\n"


# ----------------------------------------------------------------------------------------------
# Building
# ----------------------------------------------------------------------------------------------


def reach_label(river: str, site_name: str) -> str:
    """A neutral label: the river and the place in the site name's parentheses.

    Args:
        river: E.g. ``Río Sinú``.
        site_name: E.g. ``Río Sinú below ... (Tierralta, Córdoba)``.

    Returns:
        E.g. ``Río Sinú near Tierralta, Córdoba``.
    """
    match = re.search(r"\(([^)]*)\)", site_name)
    return f"{river} near {match.group(1)}" if match else river


def thin_line(
    grid: Grid, path: Sequence[tuple[int, int]], step_m: float, first: float = 0.0
) -> tuple[list[tuple[float, float]], list[float]]:
    """A centerline in ``[lng, lat]`` with about one vertex per ``step_m``, ends kept.

    Args:
        grid: The 20 m site grid.
        path: The centerline pixels ``(row, col)``.
        step_m: Spacing of the kept vertices.
        first: Chainage of the first pixel (for a sub-reach, its start).

    Returns:
        The coordinates (5 decimals) and their chainage in metres.
    """
    if not path:
        return [], []
    chainage = path_chainage(path, grid.resolution) + first
    keep = [0]
    for k in range(1, len(path) - 1):
        if chainage[k] - chainage[keep[-1]] >= step_m:
            keep.append(k)
    if len(path) > 1:
        keep.append(len(path) - 1)
    lonlat = rowcols_lonlat(grid, [path[k][0] for k in keep], [path[k][1] for k in keep])
    coords = [(round(lon, 5), round(lat, 5)) for lon, lat in lonlat]
    return coords, [round(float(chainage[k]), 1) for k in keep]


def _num(value: float, digits: int) -> float | None:
    return round(value, digits) if math.isfinite(value) else None


def case_scene(
    scene: Stage2Scene,
    item_ids: list[str],
    baselines: list[str],
    z: dict[str, dict[str, float]],
    flags: dict[str, bool],
    persistence: int,
    rain: Rain,
) -> CaseScene:
    """One scene of the case file.

    Args:
        scene: The scene at the screening's glint limit.
        item_ids: Its STAC item ids.
        baselines: Processing baselines of those items.
        z: Variant -> signal -> z.
        flags: Variant -> anomalous.
        persistence: Variants in which it is anomalous.
        rain: Its rain flags.

    Returns:
        The entry.
    """
    up, down = scene.sub.get("upstream"), scene.sub.get("downstream")

    def pair(attr: str, digits: int) -> SubreachValues:
        return SubreachValues(
            upstream=_num(float(getattr(up, attr)), digits) if up else None,
            downstream=_num(float(getattr(down, attr)), digits) if down else None,
        )

    return CaseScene(
        date=scene.datetime.date().isoformat(),
        stac_item_ids=item_ids,
        processing_baseline=baselines,
        ndti={s: _num(v, 4) for s, v in scene.values.items()},
        z={
            vid: {s: _num(by_signal.get(s, math.nan), 2) for s in SIGNALS}
            for vid, by_signal in z.items()
        },
        variant_flags=flags,
        persistence=persistence,
        rain=rain,
        valid_water_px=pair("pixels", 0),
        glint_share=pair("glint_share", 3),
        water_b11=pair("swir16", 4),
        excluded=not scene.usable,
        exclusion_reason=scene.exclusion,
    )


def case_events(events: Sequence[CatalogEvent]) -> list[CaseEvent]:
    """Catalog events as neutral summaries (no names, no source wording).

    Args:
        events: The reach's catalog events.

    Returns:
        The summaries, in time order.
    """
    return [
        CaseEvent(
            date=e.date_start.isoformat(),
            date_end=e.date_end.isoformat(),
            type=e.event_type,
            confidence=e.confidence,
            summary=EVENT_SUMMARIES.get(e.event_type, "reported event"),
        )
        for e in sorted(events, key=lambda e: e.date_start)
    ]


def build_reach(
    name: str, grid: Grid, geometry: RiverGeometry, step_m: float = 100.0
) -> tuple[ReachFeature, list[Subreach]]:
    """The reach and its sub-reaches as GeoJSON lines.

    Args:
        name: Neutral display name.
        grid: The 20 m site grid.
        geometry: The site's river geometry.
        step_m: Vertex spacing.

    Returns:
        The reach feature and the sub-reach lines.
    """
    path = geometry.centerline
    coords, _ = thin_line(grid, path, step_m)
    reach = ReachFeature(
        properties=ReachProperties(name=name, length_m=round(geometry.reach_length_m)),
        geometry=LineString(coordinates=coords),
    )
    chainage = path_chainage(path, grid.resolution) if path else np.array([])
    subreaches = []
    for sub in geometry.subreaches:
        lo, hi = sub.chainage_m
        inside = [p for p, c in zip(path, chainage, strict=True) if lo <= c <= hi]
        line, _ = thin_line(grid, inside, step_m, lo)
        subreaches.append(
            Subreach(
                name=sub.name,
                chainage_m=(round(lo, 1), round(hi, 1)),
                line=LineString(coordinates=line),
            )
        )
    return reach, subreaches


FORBIDDEN_IN_UI = ("urra", "urrá", "emec", "corelca", "multiproposito", "multipropósito")
"""Names that must never appear outside ``context`` (case-insensitive)."""


def names_outside_context(case: CaseFile) -> list[str]:
    """Forbidden names found in the ``ui`` and ``manifest`` blocks.

    Args:
        case: The case file.

    Returns:
        The names found (empty when the file is anonymous).
    """
    text = (case.ui.model_dump_json() + case.manifest.model_dump_json()).lower()
    return [name for name in FORBIDDEN_IN_UI if name in text]
