"""``climate-pipeline reach score``: the prospective outcomes of anchored claims (rule v1).

The rule is ``docs/water-quality/prospective.md``. A claim is a sealed record of a demo reach (its
turbidity estimate, or its water-temperature estimate) and its line in the reach's published
ledger. A claim is scored only when:

- it was acquired after T0, the block time of the first anchor of the frozen-artifacts ledger
  (``terrachain:riveretch:frozen-artifacts``) that lists the rule;
- its ledger line is covered by a mined anchor (read from the anchoring log, which mirrors the
  chain: ``docs/ledgers/anchors.jsonl``);
- its overpass was at least 12 hours ago.

Each outcome is a line of the reach's outcomes ledger (``examples/outcomes/ledger.jsonl``), chained
by hash like the other ledgers and anchored as ``terrachain:<reach>:outcomes``: the claim's record
SHA-256, its ledger and line, the gauge's reading at the overpass with its approval, whether it
fell inside the sealed interval, and the rule's SHA-256. A first read is never replaced: an
approved re-read, or the final "no gauge value" after 7 days, is a new line.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.sources import usgs

RULE = Path("docs/water-quality/prospective.md")
RULE_V2 = Path("docs/water-quality/prospective-v2.md")
BITCOIN_MARGIN = timedelta(hours=2)  # rule v2: after the attesting block's header time
FROZEN = Path("docs/ledgers/frozen-artifacts.jsonl")
ANCHORS = Path("docs/ledgers/anchors.jsonl")
FROZEN_LABEL = "terrachain:riveretch:frozen-artifacts"
SCORED = ("mississippi-belle-chasse", "platte-louisville")  # rule v1, section 2
FOLDER = "outcomes"
LAG = timedelta(hours=12)
FINAL_AFTER = timedelta(days=7)
APPROVALS = ("Approved", "Provisional")
STAC_ITEM = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/"


@dataclass(frozen=True)
class Claim:
    """One sealed estimate and its place in the reach's ledger."""

    ledger: str  # "observations" or "water-temperature"
    line: int  # 1-based line in the ledger
    record_sha256: str
    scene_id: str
    target: str
    unit: str
    overpass: datetime
    value: float | None  # None: the record abstained
    low: float | None
    high: float | None
    station: str
    parameter: str


@dataclass(frozen=True)
class Reading:
    """The gauge's value at an overpass (NaN when there is none)."""

    value: float
    approval: str
    rule: str
    n: int


@dataclass
class ScoreSummary:
    """What one ``score`` did."""

    t0: str | None
    claims: int = 0
    added: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)


GaugeReader = Callable[[str, str, datetime], Reading]


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


def t0(root: Path) -> datetime | None:
    """The block time of the first frozen-artifacts anchor that covers rule v1's line.

    Args:
        root: Repository root.

    Returns:
        T0 (UTC), or None before the rule is frozen and anchored.
    """
    return frozen_at(root, RULE)


def t0_v2(root: Path) -> datetime | None:
    """T0v2: the block time of the first frozen-artifacts anchor that covers rule v2's line.

    Args:
        root: Repository root.

    Returns:
        T0v2 (UTC), or None before rule v2 is frozen and anchored.
    """
    return frozen_at(root, RULE_V2)


def frozen_at(root: Path, file: Path) -> datetime | None:
    """The block time of the first frozen-artifacts anchor that covers a file's line.

    Args:
        root: Repository root.
        file: A frozen file, relative to the root.

    Returns:
        The time (UTC), or None before the file is frozen and anchored.
    """
    rule = file.as_posix()
    index = next((k for k, line in enumerate(_lines(root / FROZEN)) if line["path"] == rule), None)
    if index is None:
        return None
    times = [datetime.fromisoformat(a["timestampUtc"].replace("Z", "+00:00"))
             for a in _lines(root / ANCHORS)
             if a["label"] == FROZEN_LABEL and int(a["lines"]) > index]  # fmt: skip
    return min(times) if times else None


def anchored_lines(root: Path, label: str) -> int:
    """How many lines of a ledger its anchors cover (0 when it was never anchored).

    Args:
        root: Repository root.
        label: The ledger's label, e.g. ``terrachain:platte-louisville:observations``.

    Returns:
        The line count of its latest anchor.
    """
    return max((int(a["lines"]) for a in _lines(root / ANCHORS) if a["label"] == label), default=0)


def sepolia_commitment(root: Path, label: str, line: int) -> dict[str, Any] | None:
    """The first mined Sepolia anchor of a ledger that covers a line (route A).

    Args:
        root: Repository root.
        label: The ledger's label.
        line: The claim's line (1-based).

    Returns:
        ``{"kind": "sepolia", "block", "tx", "timestampUtc"}``, or None.
    """
    found = [a for a in _lines(root / ANCHORS) if a["label"] == label and int(a["lines"]) >= line]
    if not found:
        return None
    first = min(found, key=lambda a: (int(a["block"]), int(a["index"])))
    return {"kind": "sepolia", "block": int(first["block"]), "tx": first["tx"],
            "timestampUtc": first["timestampUtc"]}  # fmt: skip


def bitcoin_commitment(root: Path, label: str, line: int, ledger: Path,
                       header: Callable[[int], Any] | None = None
                       ) -> tuple[dict[str, Any], datetime] | None:  # fmt: skip
    """The earliest confirmed Bitcoin timestamp of a ledger head that covers a line (route B).

    Args:
        root: Repository root.
        label: The ledger's label.
        line: The claim's line (1-based).
        ledger: The ledger's file (each proof is checked against the line it timestamps).
        header: Bitcoin block-header reader (default: two public explorers).

    Returns:
        ``({"kind": "bitcoin", "height", "blockTime", "ots"}, block time)``, or None.
    """
    from climate_pipeline import timestamps

    texts = [t for t in ledger.read_text(encoding="utf-8").splitlines() if t.strip()]
    best: tuple[dict[str, Any], datetime] | None = None
    for k in range(line, len(texts) + 1):
        path = timestamps.proof_path(root, label, k)
        if not path.exists():
            continue
        digest = hashlib.sha256(texts[k - 1].encode()).digest()
        try:
            proof = timestamps.verify(path, digest, header or timestamps.explorer_header)
        except ValueError:
            continue  # a proof of another head is no commitment
        if proof.block is None or (best is not None and proof.block.time >= best[1]):
            continue
        best = ({"kind": "bitcoin", "height": proof.block.height,
                 "blockTime": proof.block.time.isoformat(timespec="seconds"),
                 "ots": path.relative_to(root).as_posix()}, proof.block.time)  # fmt: skip
    return best


def examples(root: Path, site: str) -> Path:
    """A reach's published folder (what is anchored).

    Args:
        root: Repository root.
        site: The reach.

    Returns:
        ``docs/water-quality/reach/<site>/examples``.
    """
    return root / "docs" / "water-quality" / "reach" / site / "examples"


def overpass_times(root: Path, cfg: ReachConfig, site: str) -> dict[str, datetime]:
    """The acquisition time of every Sentinel-2 scene ``reach run`` noted (public STAC metadata).

    Args:
        root: Repository root.
        cfg: Reach settings.
        site: The reach.

    Returns:
        Scene id -> acquisition time (UTC).
    """
    notes = _lines(root / cfg.out / site / "checks" / "estimates.jsonl")
    return {n["sceneId"]: datetime.fromisoformat(n["datetimeUtc"]) for n in notes}


def stac_time(item_id: str, http: httpx.Client) -> datetime | None:
    """A Sentinel-2 item's acquisition time from Earth Search (when no note has it).

    Args:
        item_id: The STAC item.
        http: HTTP client.

    Returns:
        The time (UTC), or None when the item cannot be read.
    """
    try:
        response = http.get(STAC_ITEM + item_id)
        response.raise_for_status()
        return datetime.fromisoformat(str(response.json()["properties"]["datetime"]))
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def claims(root: Path, cfg: ReachConfig, site: str, http: httpx.Client) -> list[Claim]:
    """Every claim of a demo reach: its Sentinel-2 turbidity and Landsat temperature records.

    Args:
        root: Repository root.
        cfg: Reach settings.
        site: The reach.
        http: HTTP client (for an acquisition time no note has).

    Returns:
        The claims, in ledger order.
    """
    folder = examples(root, site)
    reach = cfg.reach(site)
    times = overpass_times(root, cfg, site)
    out: list[Claim] = []
    for k, line in enumerate(_lines(folder / "ledger.jsonl")):
        rec = json.loads((folder / line["file"]).read_text(encoding="utf-8"))
        e = next((x for x in rec["estimates"] if x["target"] == "turbidity"), None)
        if e is None:
            continue
        when = times.get(rec["sceneId"]) or stac_time(rec["stacItemIds"][0], http)
        if when is None:
            continue  # no acquisition time: cannot be placed against T0
        interval = e.get("interval") or {}
        out.append(Claim("observations", k + 1, rec["recordSha256"], rec["sceneId"], "turbidity",
                         "FNU", when.astimezone(UTC), e.get("value"), interval.get("low"),
                         interval.get("high"), reach.estimate_station,
                         "63680"))  # fmt: skip
    card = root / "docs/water-quality/results/models" / site / "water_temperature.json"
    if card.exists():
        station = json.loads(card.read_text(encoding="utf-8")).get("validationSite")
        thermal = folder / "thermal"
        for k, line in enumerate(_lines(thermal / "ledger.jsonl")):
            rec = json.loads((thermal / line["file"]).read_text(encoding="utf-8"))
            e = rec["estimate"]
            interval = e.get("interval") or {}
            out.append(Claim("water-temperature", k + 1, rec["recordSha256"], rec["sceneId"],
                             "water_temperature", "°C",
                             datetime.fromisoformat(rec["datetimeUtc"]).astimezone(UTC),
                             e.get("value"), interval.get("low"), interval.get("high"),
                             str(station or reach.estimate_station), "00010"))  # fmt: skip
    return out


def usgs_reader(api: str, median: int, nearest: int, exclude: bool,
                http: httpx.Client) -> GaugeReader:  # fmt: skip
    """A gauge reader with the lock box's overpass settings, any approval (approved first).

    Args:
        api: The USGS OGC API root.
        median: Half-width of the median window, minutes.
        nearest: Half-width of the nearest-value window, minutes.
        exclude: Drop qualified values.
        http: HTTP client.

    Returns:
        A function of (station, parameter, overpass) -> the reading.
    """

    def read(station: str, parameter: str, when: datetime) -> Reading:
        span = timedelta(minutes=nearest)
        readings, _ = usgs.continuous_many(http, api, station, parameter,
                                           [(when - span, when + span)])  # fmt: skip
        for status in APPROVALS:
            value, rule, n = usgs.overpass_value(readings, when, median, nearest, status, exclude)
            if math.isfinite(value):
                return Reading(value, status, rule, n)
        return Reading(math.nan, "", "none", 0)

    return read


def _append(path: Path, fields: Mapping[str, Any]) -> None:
    texts = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = hashlib.sha256(texts[-1].encode()).hexdigest() if texts else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({**fields, "previousLineSha256": previous}, sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False) + "\n")  # fmt: skip


def _outcome(claim: Claim, reading: Reading | None, status: str, read_utc: str, rule_sha: str,
             final: bool, rule: str = "v1", commitment: dict[str, Any] | None = None
             ) -> dict[str, Any]:  # fmt: skip
    gauge = None
    inside = None
    if reading is not None and math.isfinite(reading.value):
        gauge = {"station": claim.station, "parameter": claim.parameter,
                 "value": round(reading.value, 2), "unit": claim.unit,
                 "approval": reading.approval, "rule": reading.rule, "n": reading.n}  # fmt: skip
        if claim.low is not None and claim.high is not None:
            inside = claim.low <= reading.value <= claim.high
    return {
        "claimLedger": claim.ledger, "claimLine": claim.line,
        "claimRecordSha256": claim.record_sha256, "sceneId": claim.scene_id,
        "target": claim.target, "unit": claim.unit, "estimate": claim.value,
        "interval": None if claim.low is None else {"low": claim.low, "high": claim.high},
        "overpassUtc": claim.overpass.isoformat(timespec="seconds"),
        "gauge": gauge, "inside": inside, "status": status, "final": final,
        "readUtc": read_utc, "rule": rule, "ruleSha256": rule_sha, "commitment": commitment,
    }  # fmt: skip


def score(
    root: Path,
    cfg: ReachConfig,
    site: str,
    read: GaugeReader | None = None,
    http: httpx.Client | None = None,
    now: datetime | None = None,
    header: Callable[[int], Any] | None = None,
) -> ScoreSummary:
    """Score a demo reach's committed claims under rule v1 or v2 (see the module docstring).

    Args:
        root: Repository root.
        cfg: Reach settings.
        site: A demo reach.
        read: Gauge reader (default: the USGS API with the lock box's overpass settings).
        http: HTTP client (injectable).
        now: The time of the read (default: now, UTC).
        header: Bitcoin block-header reader for rule v2 (default: two public explorers).

    Returns:
        The counts of what was added and skipped.

    Raises:
        ValueError: For a reach rule v1 does not score.
    """
    if site not in SCORED:
        raise ValueError(f"{site}: rule v1 scores only {', '.join(SCORED)}")
    start = t0(root)
    summary = ScoreSummary(None if start is None else start.isoformat(timespec="seconds"))
    if start is None:
        return summary
    client = http or httpx.Client(timeout=120, follow_redirects=True)
    if read is None:
        u = load_quality_config(root / cfg.quality_config).usgs
        read = usgs_reader(u.api, u.overpass_median_minutes, u.overpass_nearest_minutes,
                           u.exclude_qualified, client)  # fmt: skip
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    read_utc = moment.isoformat(timespec="seconds")
    start2 = t0_v2(root)
    shas = {"v1": hashlib.sha256((root / RULE).read_bytes()).hexdigest()}
    if (root / RULE_V2).exists():
        shas["v2"] = hashlib.sha256((root / RULE_V2).read_bytes()).hexdigest()
    folder = examples(root, site)
    files = {"observations": folder / "ledger.jsonl",
             "water-temperature": folder / "thermal" / "ledger.jsonl"}  # fmt: skip
    path = folder / FOLDER / "ledger.jsonl"
    done: dict[str, list[dict[str, Any]]] = {}
    for line in _lines(path):
        done.setdefault(line["claimRecordSha256"], []).append(line)
    covered = {ledger: anchored_lines(root, f"terrachain:{site}:{ledger}")
               for ledger in ("observations", "water-temperature")}  # fmt: skip

    def skip(reason: str) -> None:
        summary.skipped[reason] = summary.skipped.get(reason, 0) + 1

    def add(fields: Mapping[str, Any]) -> None:
        _append(path, fields)
        key = str(fields["status"]) + (" (final)" if fields["final"] else "")
        summary.added[key] = summary.added.get(key, 0) + 1

    for claim in claims(root, cfg, site, client):
        summary.claims += 1
        if claim.overpass <= start:
            skip("retrospective: acquired before T0")
            continue
        rule = "v2" if start2 is not None and claim.overpass > start2 else "v1"
        label = f"terrachain:{site}:{claim.ledger}"
        ready = claim.overpass + LAG
        commitment = None
        if claim.line <= covered[claim.ledger]:  # route A: a mined Sepolia anchor
            commitment = sepolia_commitment(root, label, claim.line)
        elif rule == "v2":  # route B: a confirmed Bitcoin timestamp of a covering head
            found = bitcoin_commitment(root, label, claim.line, files[claim.ledger], header)
            if found is not None:
                commitment, block_time = found
                ready = max(ready, block_time + BITCOIN_MARGIN)
        if commitment is None:
            skip("not anchored yet" if rule == "v1"
                 else "not committed yet (no anchor, no confirmed Bitcoin timestamp)")  # fmt: skip
            continue
        if moment < ready:
            skip("less than 12 h since the overpass" if moment - claim.overpass < LAG
                 else "less than 2 h since the Bitcoin block")  # fmt: skip
            continue
        rule_sha = shas[rule]

        def outcome(reading: Reading | None, status: str, final: bool,
                    c: Claim = claim, r: str = rule, sha: str = rule_sha,
                    commit: dict[str, Any] | None = commitment) -> dict[str, Any]:  # fmt: skip
            return _outcome(c, reading, status, read_utc, sha, final, r, commit)

        before = done.get(claim.record_sha256, [])
        if any(x["status"] == "abstained" for x in before):
            skip("abstained")
            continue
        if claim.value is None:
            add(outcome(None, "abstained", final=True))
            continue
        scored = [x for x in before if x["status"] == "scored"]
        if any(x["gauge"]["approval"] == "Approved" for x in scored):
            skip("scored on an approved value")
            continue
        if scored or any(x["final"] for x in before):
            if scored:  # a provisional first read: only an approved value adds a line
                reading = read(claim.station, claim.parameter, claim.overpass)
                if reading.approval == "Approved":
                    add(outcome(reading, "scored", final=False))
                else:
                    skip("scored on a provisional value; not approved yet")
            else:
                skip("no gauge value (final)")
            continue
        reading = read(claim.station, claim.parameter, claim.overpass)
        if math.isfinite(reading.value):
            add(outcome(reading, "scored", final=False))
        elif moment - claim.overpass >= FINAL_AFTER:
            add(outcome(None, "no gauge value", final=True))
        elif before:
            skip("no gauge value yet (listed)")
        else:
            add(outcome(None, "no gauge value", final=False))
    return summary
