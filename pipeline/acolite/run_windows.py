"""Stage 2c runner: ACOLITE over the station windows, in ACOLITE's own environment.

Run it with the separate environment's Python, never the project's (README.md), from
``pipeline/``::

    out/acolite-env/python.exe -I acolite/run_windows.py

It reads the scene list (``acolite/scenes.csv`` under the calibration inputs), the L2A window
rows and the pixel file written by ``climate-pipeline calibration acolite-list``. In priority
order, it runs ACOLITE on each listed scene whose Level-1C folder is in ``pipeline/out/l1c``,
over a box around the station. It stops starting scenes when the time box is spent (time is
summed over reruns).

The medians are ACOLITE's surface reflectance (``rhos`` in its L2R file) over the exact pixels
the L2A medians used. Where ACOLITE's water mask keeps a pixel, ``rhos`` equals its
water-leaving reflectance ``rhow``. Its default mask (top-of-atmosphere 1.6 um above 0.0215)
rejects most pixels of the turbid Magdalena, so the pixels are the L2A selection (SCL and the
glint guard) for both corrections (deviation 5).

At the end of every run, every processed scene is measured again from its saved L2R file. It
writes ``imagery/acolite-windows.csv`` (the L2A window columns; the scene guards are the L2A
scene's, the medians ACOLITE's), ``acolite/run-log.csv`` and ``acolite/manifest.csv`` under the
inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import io
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

INPUTS = "docs/magdalena-validation/calibration/inputs"
BAND_ORDER = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
# Nominal centres (nm); each band takes ACOLITE's dataset with the nearest wavelength.
NOMINAL = {"B02": 490, "B03": 560, "B04": 665, "B05": 705, "B06": 740, "B07": 783, "B08": 833,
           "B8A": 865, "B11": 1612, "B12": 2194}  # fmt: skip
WINDOW_COLUMNS = (
    "station", "collection", "key", "datetime_utc", "local_date", "family", "window",
    "window_px", "data_px", "valid_px", "contamination", "glint_share", "b11_median", "b11_ok",
    "ndti_px_median", *BAND_ORDER,
)  # fmt: skip
LOG_COLUMNS = ("priority", "station", "key", "l1c_folder", "status", "seconds", "note")
COPIED = ("datetime_utc", "local_date", "window_px", "data_px", "contamination", "glint_share",
          "b11_ok")  # fmt: skip


def l1c_folder(l1c: Path, datatake: str, tile: str) -> Path | None:
    """The unzipped Level-1C folder of a datatake's tile, if downloaded.

    Args:
        l1c: Download folder.
        datatake: E.g. ``S2B_MSIL1C_20230128T152639``.
        tile: E.g. ``18NXP``.

    Returns:
        The ``.SAFE`` folder (the newest baseline if several), or None.
    """
    found = sorted(l1c.glob(f"{datatake}_*_T{tile}_*.SAFE"))
    return found[-1] if found else None


def family(folder: Path) -> str:
    """The processing-baseline family of a Level-1C name (``N0510`` -> ``05.xx``).

    Args:
        folder: The ``.SAFE`` folder.

    Returns:
        The family, or ``unknown``.
    """
    parts = folder.name.split("_")
    return f"{parts[3][1:3]}.xx" if len(parts) > 3 and parts[3].startswith("N") else "unknown"


def _median(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else math.nan


def band_datasets(names: list[str], prefix: str = "rhos") -> dict[str, str]:
    """Which ``<prefix>_<nm>`` dataset holds each band.

    Args:
        names: The file's dataset names.
        prefix: ``rhos`` (L2R) or ``rhow`` (L2W).

    Returns:
        Band -> dataset name.
    """
    waves = {n: int(n.split("_")[1]) for n in names if n.startswith(f"{prefix}_") and
             n.split("_")[1].isdigit()}  # fmt: skip
    out = {}
    for band, nominal in NOMINAL.items():
        name = min(waves, key=lambda n: abs(waves[n] - nominal))
        if abs(waves[name] - nominal) <= 25:
            out[band] = name
    return out


def measure(path: Path, station: dict[str, Any], pixels: list[list[int]], rg_floor: float,
            ) -> dict[str, float]:  # fmt: skip
    """ACOLITE medians over the L2A water pixels of one window.

    Args:
        path: ACOLITE's L2R NetCDF (``rhos``).
        station: The station grid (``epsg``, ``x0``, ``y0``, ``resolution``).
        pixels: Row and column of each L2A water pixel on that grid.
        rg_floor: The screening's red+green floor for the per-pixel NDTI.

    Returns:
        ``valid_px``, ``b11_median``, ``ndti_px_median`` and the band medians.
    """
    netcdf4 = importlib.import_module("netCDF4")
    pyproj = importlib.import_module("pyproj")
    with netcdf4.Dataset(path) as nc:
        attrs = {k: nc.getncattr(k) for k in nc.ncattrs()}
        names = list(nc.variables)
        x = np.ma.filled(np.ma.asarray(nc.variables["x"][:], dtype=float), np.nan)
        y = np.ma.filled(np.ma.asarray(nc.variables["y"][:], dtype=float), np.nan)
        bands = {
            b: np.ma.filled(np.ma.asarray(nc.variables[d][:], dtype=float), np.nan)
            for b, d in band_datasets(names).items()
        }
    xs = x[0, :] if x.ndim == 2 else x
    ys = y[:, 0] if y.ndim == 2 else y
    res = float(station["resolution"])
    rows = np.array([p[0] for p in pixels], dtype=float)
    cols = np.array([p[1] for p in pixels], dtype=float)
    px = station["x0"] + (cols + 0.5) * res
    py = station["y0"] - (rows + 0.5) * res
    crs = attrs.get("proj4_string")
    if crs:
        to = pyproj.Transformer.from_crs(int(station["epsg"]), pyproj.CRS.from_proj4(crs),
                                         always_xy=True)  # fmt: skip
        px, py = to.transform(px, py)
    ci = np.abs(xs[None, :] - np.asarray(px)[:, None]).argmin(axis=1)
    ri = np.abs(ys[None, :] - np.asarray(py)[:, None]).argmin(axis=1)
    near = (np.abs(xs[ci] - px) <= res / 2 + 1) & (np.abs(ys[ri] - py) <= res / 2 + 1)
    values = {b: np.where(near, a[ri, ci], np.nan) for b, a in bands.items()}
    water = np.ones(len(pixels), dtype=bool)
    for band in BAND_ORDER:
        water &= np.isfinite(values.get(band, np.full(len(pixels), np.nan)))
    red, green = values["B04"][water], values["B03"][water]
    rg = red + green
    keep = rg >= rg_floor
    out = {
        "valid_px": float(water.sum()),
        "b11_median": _median(values["B11"][water]),
        "ndti_px_median": _median((red[keep] - green[keep]) / rg[keep]),
    }
    for band in BAND_ORDER:
        out[band] = _median(values[band][water])
    return out


def _cell(value: object) -> str:
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(round(value, 6))
    return "" if value is None else str(value)


def _csv(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return out.getvalue().encode("utf-8")


def remeasure(
    scenes: list[dict[str, str]],
    state: dict[str, Any],
    work: Path,
    pixel_file: dict[str, Any],
    l2a: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, Any]]:
    """The rows of every processed scene, measured from its saved L2R file, in priority order.

    Args:
        scenes: The scene list.
        state: The runner's state (status and Level-1C folder per scene).
        work: The work folder (``runs/<station>_<key>``).
        pixel_file: Station grids and L2A water pixels.
        l2a: The L2A 300 m window rows.

    Returns:
        One row per scene with ``ok`` status and a saved L2R file.
    """
    pixels = {(s["station"], s["key"]): s["pixels"] for s in pixel_file["scenes"]}
    rows = []
    for scene in scenes:
        sid = f"{scene['station']}|{scene['key']}"
        entry = state.get(sid, {})
        if entry.get("status") != "ok":
            continue
        l2r = sorted((work / "runs" / sid.replace("|", "_")).glob("*_L2R.nc"))
        if not l2r:
            print(f"{sid}: no saved L2R file, left out", flush=True)
            continue
        where = (scene["station"], scene["key"])
        stats = measure(l2r[0], pixel_file["stations"][scene["station"]], pixels[where],
                        pixel_file["rg_floor"])  # fmt: skip
        rows.append({"station": scene["station"], "collection": "acolite", "key": scene["key"],
                     "family": family(Path(entry.get("note", ""))), "window": "300m",
                     **{k: l2a[where][k] for k in COPIED}, **stats})  # fmt: skip
    return rows


def main() -> int:
    """Run ACOLITE on the downloaded scenes, within the time box.

    Returns:
        The exit code.
    """
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=here.parent.parent, help="repository root")
    parser.add_argument("--acolite", type=Path, default=here.parent / "out" / "acolite")
    parser.add_argument("--l1c", type=Path, default=here.parent / "out" / "l1c")
    parser.add_argument("--work", type=Path, default=here.parent / "out" / "acolite-work")
    parser.add_argument("--time-box-h", type=float, default=2.0)
    parser.add_argument("--limit-deg", type=float, default=0.05, help="half box around station")
    parser.add_argument("--max-scenes", type=int, default=0, help="0: no limit (smoke tests)")
    parser.add_argument(
        "--delete-after", action="store_true",
        help="delete each Level-1C folder once no listed scene still needs it (frees disk "
        "between download batches)",
    )  # fmt: skip
    args = parser.parse_args()
    inputs = args.root / INPUTS
    sys.path.insert(0, str(args.acolite))
    ac = importlib.import_module("acolite")
    commit = subprocess.run(["git", "-C", str(args.acolite), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()  # fmt: skip
    settings_path = here / "settings.txt"
    settings = ac.acolite.settings.read(str(settings_path))
    pixel_file = json.loads((args.work / "pixels.json").read_text(encoding="utf-8"))
    with (inputs / "imagery" / "windows-sentinel-2-l2a.csv").open(encoding="utf-8") as handle:
        l2a = {(r["station"], r["key"]): r for r in csv.DictReader(handle) if r["window"] == "300m"}
    with (inputs / "acolite" / "scenes.csv").open(encoding="utf-8") as handle:
        scenes = list(csv.DictReader(handle))
    state_path = args.work / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    spent = sum(float(s.get("seconds", 0)) for s in state.values())
    started = 0
    for scene in scenes:
        sid = f"{scene['station']}|{scene['key']}"
        if state.get(sid, {}).get("status") == "ok":
            continue
        folder = (
            l1c_folder(args.l1c, scene["datatake"], scene["tile"]) if scene["datatake"] else None
        )
        if folder is None:
            state[sid] = {"status": "not_downloaded", "seconds": 0, "note": scene["l1c_product"]}
            continue
        if spent >= args.time_box_h * 3600:
            state[sid] = {"status": "time_box", "seconds": 0, "note": folder.name}
            continue
        if args.max_scenes and started >= args.max_scenes:
            break
        started += 1
        lon = pixel_file["stations"][scene["station"]]["lon"]
        lat = pixel_file["stations"][scene["station"]]["lat"]
        d = args.limit_deg
        out = args.work / "runs" / sid.replace("|", "_")
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        run = {**settings, "inputfile": str(folder), "output": str(out),
               "limit": [round(lat - d, 5), round(lon - d, 5), round(lat + d, 5),
                         round(lon + d, 5)]}  # fmt: skip
        t0 = time.monotonic()
        status, note = "ok", ""
        try:
            ac.acolite.acolite_run(settings=run)
            if not sorted(out.glob("*_L2R.nc")):
                status, note = "no_l2r", "ACOLITE wrote no L2R file"
        except Exception as error:  # one scene's failure is recorded, not fatal
            status, note = "failed", f"{type(error).__name__}: {error}"[:300]
        seconds = round(time.monotonic() - t0, 1)
        spent += seconds
        state[sid] = {"status": status, "seconds": seconds, "note": note or folder.name}
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        took = f"{status} in {seconds:.0f} s (spent {spent / 60:.0f} min)"
        print(f"{scene['priority']} {sid}: {took}", flush=True)
        product = (scene["datatake"], scene["tile"])
        pending = any(
            (s["datatake"], s["tile"]) == product
            and state.get(f"{s['station']}|{s['key']}", {}).get("status") not in ("ok", "failed")
            for s in scenes
        )
        if args.delete_after and status == "ok" and not pending:
            shutil.rmtree(folder, ignore_errors=True)
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    order = {f"{s['station']}|{s['key']}": s for s in scenes}
    rows = remeasure(scenes, state, args.work, pixel_file, l2a)
    log = [{"priority": s["priority"], "station": s["station"], "key": s["key"],
            "l1c_folder": state.get(k, {}).get("note", ""),
            "status": state.get(k, {}).get("status", "not_started"),
            "seconds": state.get(k, {}).get("seconds", 0)} for k, s in order.items()]  # fmt: skip
    files = {
        "imagery/acolite-windows.csv": _csv(rows, WINDOW_COLUMNS),
        "acolite/run-log.csv": _csv(log, LOG_COLUMNS),
    }
    for name, body in files.items():
        (inputs / name).write_bytes(body)
    settings_sha = hashlib.sha256(settings_path.read_bytes()).hexdigest()
    manifest = [{"path": name, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                 "note": f"ACOLITE {commit}; settings sha256 {settings_sha}; "
                         f"{spent / 60:.1f} min of {args.time_box_h * 60:.0f}"}
                for name, body in files.items()]  # fmt: skip
    (inputs / "acolite" / "manifest.csv").write_bytes(
        _csv(manifest, ("path", "sha256", "bytes", "note"))
    )
    done = sum(1 for v in state.values() if v.get("status") == "ok")
    print(f"{done} scenes measured; {spent / 60:.1f} min of the {args.time_box_h:.0f} h box")
    return 3 if spent >= args.time_box_h * 3600 else 0  # 3: the time box is spent


if __name__ == "__main__":
    sys.exit(main())
