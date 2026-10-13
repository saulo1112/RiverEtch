"""Route B3 of the water-quality validation v2: the MDN's MSI multi-product model, TSS output.

Run it with the MDN environment's own Python, never the project's (README.md), from
``pipeline/``::

    out/mdn-env/python.exe -I mdn/run_mdn.py

It reads the ACOLITE window medians that ``acolite/run_windows.py --outputs`` wrote for DSF and
RAdCor, converts ``rhos`` to remote-sensing reflectance (Rrs = rhos / pi, sr^-1) at the seven MSI
bands the model takes (443, 490, 560, 665, 705, 740 and 783 nm), and runs the MDN at its pinned
commit with the weights of product ``chl,tss,cdom``. Only TSS is kept, never retuned. It writes
``predictions.csv`` and ``manifest.csv`` under ``docs/water-quality/inputs/mdn/``. This file runs
under Python 3.8, the MDN's interpreter.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import io
import math
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

INPUTS = "docs/water-quality/inputs"
SOURCES = {"dsf": "acolite/dsf/windows.csv", "radcor": "acolite/radcor/windows.csv"}
STAGE_B = "acolite/stage-b"  # v4: RAdCor Stage B (its windows and the MDN's TSS)
BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07")  # the MDN's MSI bands, in order
COMMIT = "ae1626c7990436d512044fa878f6bf276b5ce20d"
WEIGHTS = "Weights/MSI/1b79098defa9693eb03ac734467c3854cf4fb81ce3d1a96b9bf0f511f1c997b1.zip"
PRODUCT = "chl,tss,cdom"
COLUMNS = ("correction", "station", "key", "local_date", "valid_px", "tss_mg_l")


def rrs_rows(text: str) -> list[tuple[dict[str, str], list[float]]]:
    """The window rows whose seven bands are all finite, with their Rrs.

    Args:
        text: A ``windows.csv`` written by ``run_windows.py --outputs``.

    Returns:
        Each usable row and its Rrs at the MDN's bands, in sr^-1.
    """
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        values = []
        for band in BANDS:
            try:
                values.append(float(row.get(band) or "nan") / math.pi)
            except ValueError:
                values.append(math.nan)
        if all(math.isfinite(v) for v in values):
            out.append((row, values))
    return out


def ensure_weights(archive: Path) -> Path:
    """Extract the pinned weight archive into its own folder, where the MDN looks for it.

    The MDN's ``compress`` writes archives without their folder, while its ``uncompress``
    extracts into the parent folder: this archive would land loose in ``Weights/MSI``.

    Args:
        archive: The weight archive (``.zip``).

    Returns:
        The folder the MDN reads.

    Raises:
        SystemExit: If a name in the archive would escape the folder.
    """
    folder = archive.with_suffix("")
    if folder.is_dir():
        return folder
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
            raise SystemExit(f"{archive.name}: unsafe member names")
        prefixed = all(n.startswith(f"{folder.name}/") for n in names)
        zf.extractall(folder.parent if prefixed else folder)
    return folder


def tss_slice(slices: Any) -> slice:
    """Where the TSS estimates sit in the model's output.

    Args:
        slices: The output slices the MDN returns with its estimates.

    Returns:
        The TSS slice.

    Raises:
        SystemExit: If the model gives no TSS output.
    """
    if isinstance(slices, dict) and "tss" in slices:
        return slices["tss"]
    raise SystemExit(f"the MDN returned no TSS output: {slices!r}")


def _cell(value: object) -> str:
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(round(value, 6))
    return "" if value is None else str(value)


def _csv(rows: list[dict[str, object]], columns: tuple[str, ...]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return out.getvalue().encode("utf-8")


def main() -> int:
    """Run the MDN on the ACOLITE window medians.

    Returns:
        The exit code.
    """
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=here.parent.parent, help="repository root")
    parser.add_argument("--mdn", type=Path, default=here.parent / "out" / "mdn-src",
                        help="folder that holds the MDN clone as MDN/")  # fmt: skip
    parser.add_argument(
        "--stage-b", action="store_true",
        help="v4's RAdCor Stage B: its windows in, its own predictions out (acolite/stage-b/)",
    )  # fmt: skip
    args = parser.parse_args()
    sources = {"radcor": STAGE_B + "/windows.csv"} if args.stage_b else SOURCES
    folder, prefix = (STAGE_B, "mdn-") if args.stage_b else ("mdn", "")
    clone = args.mdn / "MDN"
    commit = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True,
                            text=True, check=True).stdout.strip()  # fmt: skip
    if commit != COMMIT:
        raise SystemExit(f"the MDN clone is at {commit}, not the pinned {COMMIT}")
    weights_sha = hashlib.sha256((clone / WEIGHTS).read_bytes()).hexdigest()
    ensure_weights(clone / WEIGHTS)
    np = importlib.import_module("numpy")
    sys.path.insert(0, str(args.mdn))
    mdn = importlib.import_module("MDN")
    rows: list[dict[str, object]] = []
    used: dict[str, str] = {}
    for correction, relative in sources.items():
        path = args.root / INPUTS / relative
        if not path.exists():
            print(f"{correction}: {relative} not found, skipped", flush=True)
            continue
        body = path.read_bytes()
        used[relative] = hashlib.sha256(body).hexdigest()
        usable = rrs_rows(body.decode("utf-8"))
        if not usable:
            continue
        data = np.array([values for _, values in usable], dtype=float)[None, :, :]
        estimates, slices = mdn.image_estimates(data, sensor="MSI", product=PRODUCT,
                                                use_cmdline=False)  # fmt: skip
        tss = np.asarray(np.ma.filled(estimates[0, :, tss_slice(slices)], np.nan)).reshape(-1)
        for k, (row, _) in enumerate(usable):
            rows.append({
                "correction": correction, "station": row["station"], "key": row["key"],
                "local_date": row["local_date"], "valid_px": row["valid_px"],
                "tss_mg_l": float(tss[k]),
            })  # fmt: skip
    out = args.root / INPUTS / folder
    out.mkdir(parents=True, exist_ok=True)
    body = _csv(rows, COLUMNS)
    (out / f"{prefix}predictions.csv").write_bytes(body)
    note = f"MDN {commit}; weights {WEIGHTS} sha256 {weights_sha}; product {PRODUCT}"
    manifest = [{"path": f"{prefix}predictions.csv", "sha256": hashlib.sha256(body).hexdigest(),
                 "bytes": len(body), "note": note}]  # fmt: skip
    manifest += [{"path": f"../{relative}" if not args.stage_b else Path(relative).name,
                  "sha256": sha, "bytes": "", "note": "input"}
                 for relative, sha in sorted(used.items())]  # fmt: skip
    (out / f"{prefix}manifest.csv").write_bytes(_csv(manifest, ("path", "sha256", "bytes", "note")))
    print(f"{len(rows)} TSS estimates written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
