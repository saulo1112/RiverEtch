"""Sentinel-2 L2A scenes from a STAC API, parsed into typed records.

Reflectance scaling is never hard-coded: each asset's ``raster:bands`` scale and offset are read
from its own item and cross-checked against the processing baseline (baseline 04.00, from
2022-01-25, introduced a -1000 DN offset, i.e. -0.1 in reflectance). A disagreement is flagged,
not silently fixed; stage 2 then decides on the empirical water-reflectance check.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

import httpx
from pystac_client import Client

from climate_pipeline.screening.config import AssetKeys, StacSourceConfig

log = logging.getLogger(__name__)

HTTP_TIMEOUT_S = 60
SEARCH_RETRY_PAUSES_S = (5, 30, 120, 0)

LOGICAL_ASSETS = ("scl", "red", "green", "swir16")
"""Bands the screening reads, by logical name (mapped to each source's asset keys)."""

REFLECTANCE_ASSETS = ("red", "green", "swir16")

BASELINE_WITH_OFFSET = 4.0
"""Processing baselines from 04.00 on carry BOA_ADD_OFFSET = -1000 DN (-0.1 reflectance)."""

EXPECTED_OFFSET_FROM_BASELINE = -0.1


class ScalingError(ValueError):
    """Raised when a reflectance asset has no usable scale and offset."""


@dataclass(frozen=True)
class AssetRef:
    """One asset of a scene: where it is and how to turn digital numbers into values."""

    href: str
    scale: float | None
    offset: float | None
    nodata: float | None
    epsg: int | None


@dataclass(frozen=True)
class Scene:
    """One STAC item (one MGRS tile at one sensing time)."""

    item_id: str
    datetime: datetime
    platform: str
    mgrs_tile: str
    relative_orbit: int | None
    processing_baseline: float | None
    boa_offset_applied: bool | None
    cloud_cover: float | None
    epsg: int | None
    bbox: tuple[float, float, float, float]
    assets: Mapping[str, AssetRef]

    def scaling_status(self) -> str:
        """Compare the reflectance assets' offsets with what the processing baseline implies.

        Returns:
            ``"ok"``, ``"missing"`` (no scale/offset on a reflectance asset), ``"conflict"``
            (offset disagrees with the baseline) or ``"unknown-baseline"``.
        """
        refs = [self.assets[name] for name in REFLECTANCE_ASSETS if name in self.assets]
        if any(ref.scale is None or ref.offset is None for ref in refs):
            return "missing"
        if self.processing_baseline is None:
            return "unknown-baseline"
        expected = (
            EXPECTED_OFFSET_FROM_BASELINE
            if self.processing_baseline >= BASELINE_WITH_OFFSET
            else 0.0
        )
        if any(abs((ref.offset or 0.0) - expected) > 1e-9 for ref in refs):
            return "conflict"
        return "ok"


@dataclass(frozen=True)
class Acquisition:
    """All tiles of one satellite pass over a site: one platform, one day, one relative orbit."""

    key: str
    datetime: datetime
    platform: str
    relative_orbit: int | None
    scenes: tuple[Scene, ...] = field(default_factory=tuple)

    @property
    def tiles(self) -> tuple[str, ...]:
        """The MGRS tiles of this acquisition."""
        return tuple(scene.mgrs_tile for scene in self.scenes)


class SceneSource(Protocol):
    """Something that finds Sentinel-2 L2A scenes and can make their asset URLs readable."""

    name: str

    def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> list[Scene]:
        """Find the scenes intersecting a bounding box in a period (inclusive)."""
        ...

    def sign(self, href: str) -> str:
        """Return a URL that can be read for this asset (e.g. with a SAS token appended)."""
        ...


# ----------------------------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------------------------


def parse_baseline(value: object) -> float | None:
    """Parse a processing baseline such as ``"05.10"`` or ``"N0510"``.

    Args:
        value: The ``s2:processing_baseline`` property, if any.

    Returns:
        The baseline as a number (5.1), or None if absent or unparsable.
    """
    if value is None:
        return None
    text = str(value).strip().upper().removeprefix("N")
    if re.fullmatch(r"\d{2}\.\d{2}", text):
        return float(text)
    if re.fullmatch(r"\d{4}", text):
        return float(f"{text[:2]}.{text[2:]}")
    return None


def _epsg(mapping: Mapping[str, Any]) -> int | None:
    if isinstance(mapping.get("proj:epsg"), int):
        return int(mapping["proj:epsg"])
    code = mapping.get("proj:code")
    if isinstance(code, str) and code.upper().startswith("EPSG:"):
        return int(code.split(":", 1)[1])
    return None


def _mgrs_tile(item_id: str, props: Mapping[str, Any]) -> str:
    for key in ("s2:mgrs_tile", "grid:code"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value.removeprefix("MGRS-")
    zone, band, square = (
        props.get(f"mgrs:{k}") for k in ("utm_zone", "latitude_band", "grid_square")
    )
    if zone is not None and band is not None and square is not None:
        return f"{int(zone):02d}{band}{square}"
    match = re.search(r"_(\d{2}[C-X][A-Z]{2})_", item_id)
    return match.group(1) if match else "unknown"


def _relative_orbit(props: Mapping[str, Any]) -> int | None:
    orbit = props.get("sat:relative_orbit")
    if isinstance(orbit, int | float):
        return int(orbit)
    # Earth Search items may lack the sat extension; the product name carries the orbit (_R025_).
    for key in ("s2:product_uri", "s2:granule_id", "s2:datatake_id"):
        match = re.search(r"_R(\d{3})_", str(props.get(key, "")))
        if match:
            return int(match.group(1))
    return None


def _asset_ref(asset: Mapping[str, Any], item_epsg: int | None) -> AssetRef:
    bands = asset.get("raster:bands")
    band: Mapping[str, Any] = bands[0] if isinstance(bands, list) and bands else {}
    scale, offset, nodata = band.get("scale"), band.get("offset"), band.get("nodata")
    return AssetRef(
        href=str(asset["href"]),
        scale=float(scale) if isinstance(scale, int | float) else None,
        offset=float(offset) if isinstance(offset, int | float) else None,
        nodata=float(nodata) if isinstance(nodata, int | float) else None,
        epsg=_epsg(asset) or item_epsg,
    )


def parse_item(item: Mapping[str, Any], keys: AssetKeys) -> Scene:
    """Parse a STAC item dictionary into a :class:`Scene`.

    Args:
        item: The item as JSON-like data.
        keys: Which asset keys hold the logical bands.

    Returns:
        The scene.

    Raises:
        KeyError: If the item lacks the SCL asset or its datetime.
    """
    props: Mapping[str, Any] = item["properties"]
    item_epsg = _epsg(props)
    mapping = {"scl": keys.scl, "red": keys.red, "green": keys.green, "swir16": keys.swir16}
    assets = {
        name: _asset_ref(item["assets"][key], item_epsg)
        for name, key in mapping.items()
        if key in item["assets"]
    }
    if "scl" not in assets:
        raise KeyError(f"{item['id']}: no {keys.scl!r} asset")
    stamp = datetime.fromisoformat(str(props["datetime"]))
    cloud = props.get("eo:cloud_cover")
    boa = props.get("earthsearch:boa_offset_applied")
    bbox = item.get("bbox") or (0.0, 0.0, 0.0, 0.0)
    return Scene(
        item_id=str(item["id"]),
        datetime=stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC),
        platform=str(props.get("platform", "unknown")).lower(),
        mgrs_tile=_mgrs_tile(str(item["id"]), props),
        relative_orbit=_relative_orbit(props),
        processing_baseline=parse_baseline(props.get("s2:processing_baseline")),
        boa_offset_applied=boa if isinstance(boa, bool) else None,
        cloud_cover=float(cloud) if isinstance(cloud, int | float) else None,
        epsg=item_epsg,
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        assets=assets,
    )


def reflectance_scaling(scene: Scene, name: str) -> tuple[float, float]:
    """The scale and offset of a reflectance asset, from the item's own metadata.

    Args:
        scene: The scene.
        name: Logical asset name (``red``, ``green`` or ``swir16``).

    Returns:
        ``(scale, offset)`` such that reflectance = DN * scale + offset.

    Raises:
        ScalingError: If the asset is missing or carries no scale/offset (never guessed).
    """
    ref = scene.assets.get(name)
    if ref is None or ref.scale is None or ref.offset is None:
        raise ScalingError(f"{scene.item_id}: {name} has no raster:bands scale/offset")
    return ref.scale, ref.offset


# ----------------------------------------------------------------------------------------------
# Grouping
# ----------------------------------------------------------------------------------------------


def _newest(scenes: list[Scene]) -> list[Scene]:
    # All items with the highest baseline: same-baseline copies of one tile can be complementary
    # partial granules (a datatake split), and merging duplicates is harmless.
    top = max(s.processing_baseline or 0.0 for s in scenes)
    return [s for s in scenes if (s.processing_baseline or 0.0) == top]


def group_acquisitions(scenes: Iterable[Scene]) -> list[Acquisition]:
    """Group items into acquisitions and keep only the newest processing of each tile.

    Neighbouring MGRS tiles overlap and the archive holds reprocessed copies, so one satellite
    pass can appear as several items. A pass is identified by platform, UTC date and relative
    orbit; within it each tile keeps the items with its highest processing baseline.

    Args:
        scenes: Parsed items.

    Returns:
        Acquisitions sorted by time.
    """
    passes: dict[tuple[str, date, int | None], dict[str, list[Scene]]] = {}
    for scene in scenes:
        key = (scene.platform, scene.datetime.astimezone(UTC).date(), scene.relative_orbit)
        passes.setdefault(key, {}).setdefault(scene.mgrs_tile, []).append(scene)
    acquisitions = []
    for (platform, day, orbit), tiles in passes.items():
        kept = tuple(
            sorted(
                (s for copies in tiles.values() for s in _newest(copies)),
                key=lambda s: (s.mgrs_tile, s.item_id),
            )
        )
        orbit_label = f"R{orbit:03d}" if orbit is not None else "Rxxx"
        acquisitions.append(
            Acquisition(
                key=f"{platform}_{day.isoformat()}_{orbit_label}",
                datetime=min(s.datetime for s in kept),
                platform=platform,
                relative_orbit=orbit,
                scenes=kept,
            )
        )
    return sorted(acquisitions, key=lambda a: (a.datetime, a.key))


def evidence_hash(acquisitions: Iterable[Acquisition]) -> str:
    """Hash the item ids a result was computed from, as a reproducibility record.

    Args:
        acquisitions: The acquisitions used.

    Returns:
        Hex SHA-256 of the sorted item ids, one per line.
    """
    ids = sorted(scene.item_id for acq in acquisitions for scene in acq.scenes)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


# ----------------------------------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------------------------------


def _search_dicts(
    url: str,
    collection: str,
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
    page_size: int,
) -> list[dict[str, Any]]:
    # The whole search is retried: a failed page part-way through would otherwise lose a site.
    for attempt, pause in enumerate(SEARCH_RETRY_PAUSES_S):
        try:
            client = Client.open(url, timeout=HTTP_TIMEOUT_S)
            search = client.search(
                collections=[collection],
                bbox=list(bbox),
                datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
                limit=page_size,
            )
            return list(search.items_as_dicts())
        except Exception as error:  # network or API errors; retried, then re-raised
            if attempt == len(SEARCH_RETRY_PAUSES_S) - 1:
                raise
            log.warning("STAC search failed (%s); retrying in %s s", error, pause)
            time.sleep(pause)
    raise AssertionError("unreachable")


def parse_items(items: Iterable[Mapping[str, Any]], keys: AssetKeys) -> list[Scene]:
    """Parse search results, skipping (and logging) malformed items.

    Args:
        items: Item dictionaries.
        keys: Asset keys of the source.

    Returns:
        The scenes that parsed.
    """
    scenes = []
    for item in items:
        try:
            scenes.append(parse_item(item, keys))
        except (KeyError, TypeError, ValueError) as error:
            log.warning("skipping item %s: %s", item.get("id", "?"), error)
    return scenes


class EarthSearchSource:
    """Element 84 Earth Search: public COGs on AWS, no signing needed."""

    name = "earth-search"

    def __init__(self, config: StacSourceConfig, page_size: int) -> None:
        """Create the source.

        Args:
            config: The STAC source settings.
            page_size: Items per search page.
        """
        self._config = config
        self._page_size = page_size

    def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> list[Scene]:
        """Find the scenes intersecting a bounding box in a period (inclusive).

        Args:
            bbox: West, south, east, north in degrees.
            start: First day.
            end: Last day.

        Returns:
            Parsed scenes.
        """
        items = _search_dicts(
            self._config.url, self._config.collection, bbox, start, end, self._page_size
        )
        return parse_items(items, self._config.assets)

    def sign(self, href: str) -> str:
        """Earth Search assets are public: the URL is returned as is.

        Args:
            href: Asset URL.

        Returns:
            The same URL.
        """
        return href


class PlanetaryComputerSource:
    """Microsoft Planetary Computer: assets need a short-lived SAS token appended."""

    name = "planetary-computer"

    def __init__(
        self, config: StacSourceConfig, page_size: int, http: httpx.Client | None = None
    ) -> None:
        """Create the source.

        Args:
            config: The STAC source settings (with ``sas_token_url``).
            page_size: Items per search page.
            http: HTTP client for the token endpoint (injectable for tests).

        Raises:
            ValueError: If the configuration has no token URL.
        """
        if config.sas_token_url is None:
            raise ValueError("planetary-computer needs sas_token_url")
        self._config = config
        self._token_url = config.sas_token_url
        self._page_size = page_size
        self._http = http or httpx.Client(timeout=30)
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def search(
        self, bbox: tuple[float, float, float, float], start: date, end: date
    ) -> list[Scene]:
        """Find the scenes intersecting a bounding box in a period (inclusive).

        Args:
            bbox: West, south, east, north in degrees.
            start: First day.
            end: Last day.

        Returns:
            Parsed scenes.
        """
        items = _search_dicts(
            self._config.url, self._config.collection, bbox, start, end, self._page_size
        )
        return parse_items(items, self._config.assets)

    def sign(self, href: str) -> str:
        """Append a SAS token (cached until shortly before it expires).

        Args:
            href: Asset URL.

        Returns:
            The URL with the token as its query string.
        """
        with self._lock:
            if self._token is None or self._token[1] - time.time() < 300:
                response = self._http.get(self._token_url)
                response.raise_for_status()
                payload = response.json()
                expiry = datetime.fromisoformat(str(payload["msft:expiry"])).timestamp()
                self._token = (str(payload["token"]), expiry)
            token = self._token[0]
        return f"{href}{'&' if '?' in href else '?'}{token}"


def make_source(name: str, sources: Mapping[str, StacSourceConfig], page_size: int) -> SceneSource:
    """Build the configured scene source.

    Args:
        name: ``earth-search`` or ``planetary-computer``.
        sources: The configured sources.
        page_size: Items per search page.

    Returns:
        The source.

    Raises:
        ValueError: For an unknown source name.
    """
    if name not in sources:
        raise ValueError(f"unknown STAC source {name!r}")
    if name == "planetary-computer":
        return PlanetaryComputerSource(sources[name], page_size)
    return EarthSearchSource(sources[name], page_size)
