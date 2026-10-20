"""``climate-pipeline status``: what the daily run did, for the web app's status panel.

The daily workflow (``.github/workflows/daily.yml``) writes ``status.json`` on the ``data``
branch after every run: the run's steps and exit codes, the last successful run, the newest
sealed record, the newest Sepolia anchor, the newest Bitcoin timestamp and how many are pending,
and the recent failures with their reasons. Everything comes from the committed files and the
run's own step log; nothing is typed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation

from climate_pipeline import timestamps
from climate_pipeline.reach.score import ANCHORS, SCORED

KEEP_FAILURES = 20
OK_EXITS = {"reach run": (0, 2)}  # reach run: 2 is a partial run (some scenes not ready yet)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


def _ok(step: dict[str, Any]) -> bool:
    args = str(step["args"])
    allowed = next((v for k, v in OK_EXITS.items() if args.startswith(k)), (0,))
    return int(step["exit"]) in allowed


def last_sealed(root: Path) -> dict[str, Any] | None:
    """The newest sealed record of the scored and ungauged reaches (Sentinel-2 or Landsat).

    Args:
        root: Repository root.

    Returns:
        ``{reach, sceneId, date}``, or None.
    """
    best: dict[str, Any] | None = None
    for reach in (*SCORED, *timestamps.UNGAUGED):
        folder = root / "docs" / "water-quality" / "reach" / reach / "examples"
        for series in (folder / "series.json", folder / "thermal" / "series.json"):
            if not series.exists():
                continue
            rows = json.loads(series.read_text(encoding="utf-8"))
            for row in rows[-1:]:
                if best is None or str(row["date"]) > str(best["date"]):
                    best = {"reach": reach, "sceneId": row["sceneId"], "date": row["date"]}
    return best


def last_anchor(root: Path) -> dict[str, Any] | None:
    """The newest Sepolia anchor in the anchoring log.

    Args:
        root: Repository root.

    Returns:
        ``{label, lines, block, timestampUtc, tx}``, or None.
    """
    anchors = _jsonl(root / ANCHORS)
    if not anchors:
        return None
    a = max(anchors, key=lambda x: (int(x["block"]), int(x["index"])))
    return {k: a[k] for k in ("label", "lines", "block", "timestampUtc", "tx")}


def bitcoin(root: Path, header: Callable[[int], timestamps.Block | None] | None = None
            ) -> tuple[dict[str, Any] | None, int]:  # fmt: skip
    """The newest Bitcoin-attested proof, and how many proofs are still pending.

    Args:
        root: Repository root.
        header: Block-header reader for the newest proof's time (default: public explorers).

    Returns:
        ``({file, height, blockTime}, pending)``; the first is None without an attested proof.
    """
    newest: tuple[int, Path] | None = None
    pending = 0
    for path in sorted((root / timestamps.OTS_DIR).glob("*.ots")):
        attestations = [a for _, a in timestamps.read(path).timestamp.all_attestations()]
        heights = [int(a.height) for a in attestations
                   if isinstance(a, BitcoinBlockHeaderAttestation)]  # fmt: skip
        if heights:
            if newest is None or min(heights) > newest[0]:
                newest = (min(heights), path)
        elif any(isinstance(a, PendingAttestation) for a in attestations):
            pending += 1
    if newest is None:
        return None, pending
    block = (header or timestamps.explorer_header)(newest[0])
    return {"file": newest[1].relative_to(root).as_posix(), "height": newest[0],
            "blockTime": None if block is None else block.time.isoformat(timespec="seconds")
            }, pending  # fmt: skip


def proofs(root: Path) -> list[dict[str, Any]]:
    """Every Bitcoin proof, so the web app fetches only proofs that exist.

    Args:
        root: Repository root.

    Returns:
        ``{label, lines, file, height}`` per proof (``height``: the earliest attesting block,
        None while pending), sorted by label and line count.
    """
    out = []
    for ledger in timestamps.ledgers(root):
        prefix = ledger.label.replace(":", "_") + "."
        for path in (root / timestamps.OTS_DIR).glob(f"{prefix}*.ots"):
            lines = path.name[len(prefix) : -len(".ots")]
            if not lines.isdigit():
                continue
            heights = [int(a.height) for _, a in timestamps.read(path).timestamp.all_attestations()
                       if isinstance(a, BitcoinBlockHeaderAttestation)]  # fmt: skip
            out.append({"label": ledger.label, "lines": int(lines),
                        "file": path.relative_to(root).as_posix(),
                        "height": min(heights) if heights else None})  # fmt: skip
    return sorted(out, key=lambda r: (r["label"], r["lines"]))


def build(root: Path, steps: Sequence[dict[str, Any]], previous: dict[str, Any] | None,
          run_url: str, now: datetime | None = None,
          header: Callable[[int], timestamps.Block | None] | None = None
          ) -> dict[str, Any]:  # fmt: skip
    """``status.json`` after one run.

    Args:
        root: Repository root (the run's checkout).
        steps: The run's steps: ``{args, exit, last}`` (``last``: the step's last output line).
        previous: The previous ``status.json`` (its last success and failures carry over).
        run_url: The workflow run's URL.
        now: The time (default: now, UTC).
        header: Block-header reader (tests).

    Returns:
        The document.
    """
    at = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    ok = bool(steps) and all(_ok(s) for s in steps)
    failures = list((previous or {}).get("failures", []))
    failed = [s for s in steps if not _ok(s)]
    if not steps:
        failed = [{"args": "the run", "exit": 1, "last": "no step ran"}]
    for s in failed:
        failures.append({"utc": at, "run": run_url, "step": s["args"], "exit": int(s["exit"]),
                         "reason": str(s.get("last", ""))[:300]})  # fmt: skip
    newest, pending = bitcoin(root, header)
    return {
        "updatedUtc": at,
        "run": {"url": run_url, "ok": ok,
                "steps": [{"args": s["args"], "exit": int(s["exit"])} for s in steps]},
        "lastSuccessUtc": at if ok else (previous or {}).get("lastSuccessUtc"),
        "lastSealed": last_sealed(root),
        "lastAnchor": last_anchor(root),
        "lastBitcoin": newest,
        "pendingBitcoin": pending,
        "proofs": proofs(root),
        "outcomes": [r for r in SCORED if (root / "docs" / "water-quality" / "reach" / r
                                           / "examples" / "outcomes" / "ledger.jsonl").exists()],
        "failures": failures[-KEEP_FAILURES:],
    }  # fmt: skip


def write(root: Path, steps_file: Path, previous_file: Path, out: Path, run_url: str) -> bool:
    """Write ``status.json`` from the run's step log.

    Args:
        root: Repository root.
        steps_file: The step log (JSON lines).
        previous_file: The previous ``status.json`` (may not exist).
        out: Where to write it.
        run_url: The workflow run's URL.

    Returns:
        Whether the run succeeded.
    """
    previous = (json.loads(previous_file.read_text(encoding="utf-8"))
                if previous_file.exists() else None)  # fmt: skip
    doc = build(root, _jsonl(steps_file), previous, run_url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    return bool(doc["run"]["ok"])
