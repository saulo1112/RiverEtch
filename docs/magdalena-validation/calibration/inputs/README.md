# Calibration inputs (snapshots)

Raw inputs of the calibration and climate-context validation, committed so that every result
can be recomputed offline: `climate-pipeline calibration run`, or `npm run pipeline:calibration`.
Preregistration: [calibration-preregistration.md](../../calibration-preregistration.md).

- **Fetched, never edited by hand.** Each file was written by `climate-pipeline calibration
  fetch`. [fetch-manifest-stations.csv](fetch-manifest-stations.csv) and
  [fetch-manifest.csv](fetch-manifest.csv) record each file's source URL, HTTP status, bytes,
  SHA-256 and UTC time.
- **Subsets.** Where a file is a subset (long IDEAM series: the header plus the lines inside the
  period), the manifest's note gives the full file's size and SHA-256.
- **Byte for byte.** IDEAM's series keep their CRLF line ends.
  [.gitattributes](.gitattributes) turns off Git's line-end normalisation here, so the committed
  files match the manifest's SHA-256 on every platform.
- **CHIRPS was kept from an earlier fetch.** The final fetch ran with `--keep-chirps`, because the
  CHIRPS server returned HTTP 500 that evening after a complete read the same day. The manifest
  gives that file's own time and the days the server did not have yet (April–September 2026,
  except June).
- **Cloudy scenes have no band medians.** Bands are read only for scenes that can pass the
  preregistered guards (deviation 4). The other rows keep their SCL statistics and have
  `bands_read` 0.
- **`acolite/scenes.csv`** is derived, not fetched: `climate-pipeline calibration acolite-list`
  writes it from these snapshots and Earth Search's Level-1C items (Stage 2c).
- **Read errors.** `imagery/read-errors.csv` must list only the permanent ones (deviation 3):
  items of 2024-01-23 that point to a non-public bucket.

## Licence and attribution

The files under `ideam/` and `stations/` come from the Instituto de Hidrología, Meteorología y
Estudios Ambientales (IDEAM), through datos.gov.co and IDEAM's public data bucket
(`https://datos.ideam.gov.co/s3-estacionesideam`).

- They are published under the
  [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
  licence, and **these files keep that licence**. Attribution: IDEAM, Bogotá D.C.
- The repository's own licence does not apply to them; it is still open.

The other sources keep their own terms:

| Folder | Source |
| --- | --- |
| `rain/open-meteo/` | Open-Meteo historical weather API (CC BY 4.0) |
| `rain/chirps-daily.csv` | CHIRPS 2.0 (Climate Hazards Center, UC Santa Barbara) |
| `climate/oni.ascii.txt` | NOAA Climate Prediction Center ONI table |
| `coefficients/` | ACOLITE's open coefficient tables, at the pinned commit (GPL-3.0 code repository) |
| `imagery/` | Statistics computed from Copernicus Sentinel-2 data (Earth Search COGs); no image is committed |

## Order of the runs

1. `climate-pipeline calibration fetch --stations-only` writes `stations/` (metadata only).
   It is committed before any value is fetched.
2. `climate-pipeline calibration fetch` writes everything else.
   - It exits with an error when any input failed or any imagery read failed; then rerun it,
     because the caches make a rerun cheap.
3. ACOLITE (optional, Stage 2c) writes `imagery/acolite-windows.csv` from Level-1C files that the
   project owner downloads.
4. `climate-pipeline calibration run` writes `../results/` and its `MANIFEST`.
   `climate-pipeline calibration verify` recomputes and compares.
