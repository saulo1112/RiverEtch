"""Download the Stage 2c Level-1C products from Copernicus Data Space with your own account.

Run it yourself, in your own terminal, from ``pipeline/``::

    uv run python acolite/download_l1c.py --max-products 10

With ``--process`` it runs ACOLITE on each product right after downloading it
(``acolite/run_windows.py --delete-after``, in ACOLITE's environment) and deletes the product,
so only one product (about 1.7 GB with its zip) is on disk at a time. Products whose scenes are
all processed are skipped, and it stops when ACOLITE's time box is spent.

It asks for your Copernicus Data Space username and password with a hidden prompt (or reads
``CDSE_USER`` and ``CDSE_PASSWORD`` if you set them), keeps them in memory only, and never
prints or writes them. It reads ``acolite/scenes.csv`` under the calibration inputs, finds each
product in the public catalogue by its datatake and tile (the catalogue serves the current
processing, often a newer baseline than the one Earth Search lists), streams it to
``pipeline/out/l1c/<name>.zip``, checks its MD5, and unzips ``<name>.SAFE`` there. Products
already unzipped are skipped, so it can be stopped and rerun. It stops before the disk's free
space would fall under ``--keep-free-gb``.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

CATALOGUE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value"
TOKEN = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
INPUTS = "docs/magdalena-validation/calibration/inputs"


def products(scenes_csv: Path) -> list[tuple[str, str]]:
    """The distinct (datatake, tile) pairs of the scene list, in priority order.

    Args:
        scenes_csv: ``acolite/scenes.csv``.

    Returns:
        Datatake prefix and tile, first use first.
    """
    out: list[tuple[str, str]] = []
    with scenes_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pair = (row["datatake"], row["tile"])
            if all(pair) and pair not in out:
                out.append(pair)
    return out


def _baseline(name: str) -> int:
    m = re.search(r"_N(\d{4})_", name)
    return int(m.group(1)) if m else -1


def find(client: httpx.Client, datatake: str, tile: str) -> dict[str, object] | None:
    """The catalogue entry of a datatake's tile (the newest processing baseline).

    Args:
        client: HTTP client.
        datatake: E.g. ``S2B_MSIL1C_20230128T152639``.
        tile: E.g. ``18NXP``.

    Returns:
        The entry (``Id``, ``Name``, ``ContentLength``, ``Checksum``), or None.
    """
    query = (
        f"startswith(Name,'{datatake}') and contains(Name,'_T{tile}_') "
        "and Collection/Name eq 'SENTINEL-2'"
    )
    params = {"$filter": query, "$select": "Id,Name,ContentLength,Checksum,Online"}
    response = client.get(CATALOGUE, params=params)
    response.raise_for_status()
    found = [p for p in response.json().get("value", []) if p.get("Online", True)]
    return max(found, key=lambda p: _baseline(str(p["Name"]))) if found else None


def token(client: httpx.Client, user: str, password: str) -> str:
    """A fresh access token (valid for a few minutes).

    Args:
        client: HTTP client.
        user: Account e-mail.
        password: Account password.

    Returns:
        The bearer token.

    Raises:
        SystemExit: If the account is refused (the reason is printed, never the password).
    """
    data = {"client_id": "cdse-public", "grant_type": "password", "username": user,
            "password": password}  # fmt: skip
    response = client.post(TOKEN, data=data)
    if response.status_code != 200 or "access_token" not in response.json():
        detail = response.json().get("error_description", "") if response.content else ""
        raise SystemExit(
            f"Copernicus Data Space refused the login ({response.status_code}) {detail}"
        )
    return str(response.json()["access_token"])


def download(client: httpx.Client, product: dict[str, object], bearer: str, out: Path) -> Path:
    """Stream one product to ``<name>.zip`` and check its size and MD5.

    Args:
        client: HTTP client.
        product: Catalogue entry.
        bearer: Access token.
        out: Folder.

    Returns:
        The zip file.

    Raises:
        RuntimeError: If the size or checksum differs.
    """
    name = str(product["Name"]).removesuffix(".SAFE")
    target = out / f"{name}.zip"
    partial = target.with_suffix(".zip.part")
    url = DOWNLOAD.format(id=product["Id"])
    headers = {"Authorization": f"Bearer {bearer}"}
    md5 = hashlib.md5()
    # Follow redirects by hand: the download host redirects to another host, and the header
    # must go with it.
    for _ in range(5):
        with client.stream("GET", url, headers=headers, follow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = response.headers["Location"]
                continue
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=8 * 1024 * 1024):
                    handle.write(chunk)
                    md5.update(chunk)
            break
    else:
        raise RuntimeError(f"{name}: too many redirects")
    size = partial.stat().st_size
    checksums = product.get("Checksum")
    expected = {
        str(c.get("Algorithm", "")).upper(): str(c.get("Value", "")).lower()
        for c in (checksums if isinstance(checksums, list) else [])
    }
    if product.get("ContentLength") and size != int(str(product["ContentLength"])):
        raise RuntimeError(f"{name}: {size} bytes, expected {product['ContentLength']}")
    if "MD5" in expected and md5.hexdigest() != expected["MD5"]:
        raise RuntimeError(f"{name}: MD5 differs")
    partial.replace(target)
    return target


def done_products(scenes_csv: Path, state_json: Path) -> set[tuple[str, str]]:
    """Products whose every listed scene ACOLITE has already processed (ok or failed).

    Args:
        scenes_csv: ``acolite/scenes.csv``.
        state_json: The runner's ``state.json`` (may not exist yet).

    Returns:
        Datatake and tile of each finished product.
    """
    state = json.loads(state_json.read_text(encoding="utf-8")) if state_json.exists() else {}
    status: dict[tuple[str, str], set[str]] = {}
    with scenes_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sid = f"{row['station']}|{row['key']}"
            status.setdefault((row["datatake"], row["tile"]), set()).add(
                state.get(sid, {}).get("status", "")
            )
    return {p for p, s in status.items() if s <= {"ok", "failed"}}


def run_acolite(here: Path) -> int:
    """Run ``run_windows.py --delete-after`` with ACOLITE's own Python.

    The Copernicus credentials are not passed on.

    Args:
        here: This folder (``pipeline/acolite``).

    Returns:
        The runner's exit code (3 when the time box is spent).
    """
    env_dir = here.parent / "out" / "acolite-env"
    python = env_dir / "python.exe"
    if not python.exists():
        python = env_dir / "bin" / "python"
    env = {k: v for k, v in os.environ.items() if k not in ("CDSE_USER", "CDSE_PASSWORD")}
    env.update({
        "GDAL_DRIVER_PATH": str(env_dir / "Library" / "lib" / "gdalplugins"),
        "GDAL_DATA": str(env_dir / "Library" / "share" / "gdal"),
        "PROJ_DATA": str(env_dir / "Library" / "share" / "proj"),
    })  # fmt: skip
    command = [str(python), "-I", str(here / "run_windows.py"), "--delete-after"]
    return subprocess.run(command, env=env, check=False).returncode


def main() -> int:
    """Download the listed products.

    Returns:
        The exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(".."), help="repository root")
    parser.add_argument("--out", type=Path, default=Path("out/l1c"), help="Level-1C folder")
    parser.add_argument("--max-products", type=int, default=10, help="stop after this many new")
    parser.add_argument("--keep-free-gb", type=float, default=8.0, help="free disk to keep")
    parser.add_argument(
        "--process", action="store_true",
        help="run ACOLITE on each product right after downloading it, then delete it",
    )  # fmt: skip
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    scenes = args.root / INPUTS / "acolite" / "scenes.csv"
    args.out.mkdir(parents=True, exist_ok=True)
    finished = done_products(scenes, here.parent / "out" / "acolite-work" / "state.json")
    wanted = [p for p in products(scenes) if not args.process or p not in finished]
    if args.process and finished:
        print(f"{len(finished)} products already processed: skipped")
    print(f"{len(wanted)} Level-1C products listed in {scenes}")
    user = os.environ.get("CDSE_USER") or input("Copernicus Data Space e-mail: ").strip()
    password = os.environ.get("CDSE_PASSWORD") or getpass.getpass("Password (hidden): ")
    new = 0
    with httpx.Client(timeout=httpx.Timeout(60.0, read=600.0)) as client:
        for i, (datatake, tile) in enumerate(wanted, 1):
            if new >= args.max_products:
                print(f"stopped after {new} new products (--max-products)")
                break
            if any(args.out.glob(f"{datatake}_*_T{tile}_*.SAFE")):
                print(f"[{i}/{len(wanted)}] {datatake} T{tile}: already here")
                continue
            product = find(client, datatake, tile)
            if product is None:
                print(f"[{i}/{len(wanted)}] {datatake} T{tile}: not in the catalogue")
                continue
            need = 2 * int(str(product.get("ContentLength") or 0))
            free = shutil.disk_usage(args.out).free
            if free - need < args.keep_free_gb * 1e9:
                print(f"stopped: {free / 1e9:.1f} GB free, {args.keep_free_gb} GB to keep")
                break
            print(f"[{i}/{len(wanted)}] {product['Name']} ({need / 2e6:.0f} MB) ...", flush=True)
            archive = download(client, product, token(client, user, password), args.out)
            with zipfile.ZipFile(archive) as z:
                z.extractall(args.out)
            archive.unlink()
            new += 1
            if args.process and run_acolite(here) == 3:
                print("stopped: ACOLITE's time box is spent")
                break
    print(f"{new} new products in {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
