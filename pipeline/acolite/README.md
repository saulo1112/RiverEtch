# ACOLITE sensitivity (Stage 2c)

Stage 2c repeats Stage 1 on ACOLITE's water-leaving reflectances, as a sensitivity. It is never
the primary. ACOLITE runs in its own environment, so the project's `uv.lock` does not change. No
Level-1C file is committed. The box is 2 h of ACOLITE processing; scenes not processed by then are
recorded as `time_box`, and the stage reports what it has.

| What                | Value                                                                              |
| ------------------- | ---------------------------------------------------------------------------------- |
| ACOLITE             | `https://github.com/acolite/acolite` at `ca477dd91dfb5f8eb77333824b38cb0bcce5e083` |
| Environment         | micromamba 2.9.0, conda-forge, Python 3.12, GDAL with the JPEG2000 driver          |
| Settings            | [settings.txt](settings.txt); every other setting is ACOLITE's default             |
| Level-1C source     | Copernicus Data Space (the project owner's account)                                |
| Scene list          | `docs/magdalena-validation/calibration/inputs/acolite/scenes.csv`                  |
| Output (a snapshot) | `.../inputs/imagery/acolite-windows.csv`, `acolite/run-log.csv`, `manifest.csv`    |

## How the reflectances are measured

- **Scenes:** the scenes of the primary pairs (L2A, 300 m window). The order is sampled targets'
  training scenes, their hold-out scenes, then the daily target's training and hold-out scenes.
- **Tile:** the Level-1C tile whose footprint covers the station window.
- **Processing:** ACOLITE runs on a box of ±0.05° around the station, at 20 m, with one aerosol
  estimate for that box (`dsf_aot_estimate=fixed`). Pressure comes from the Copernicus DEM, since
  no NASA Earthdata account is used.
- **Pixels:** the medians are taken over **the exact pixels the L2A medians used** (valid, not
  glint, every band finite). Pixels that ACOLITE's water mask rejects drop out, and their count is
  `valid_px`. The scene guards (contamination, the water-B11 check) are the L2A scene's, so both
  corrections are compared on the same scenes and the same water.
- **Baseline:** Copernicus Data Space serves the current processing of each tile, often a
  reprocessed baseline (for example N05.10 for 2023). That is newer than the baseline behind the
  L2A item. The run log names the folder used, and `family` in the output is its baseline family.

## Steps (from `pipeline/`)

1. `uv run climate-pipeline calibration acolite-list --root ..` writes the scene list and the
   pixel file (`out/acolite-work/pixels.json`, from the cached L2A reads).
2. The project owner downloads the listed products with their own account:
   `uv run python acolite/download_l1c.py --max-products 10`. It prompts for the e-mail and
   password with a hidden prompt, keeps them in memory only, and can be stopped and rerun.
3. Set up the environment once (Git Bash):

   ```bash
   export MAMBA_ROOT_PREFIX="$PWD/out/micromamba-root"
   out/tools/micromamba.exe create -y -p "$PWD/out/acolite-env" -c conda-forge --override-channels \
     python=3.12 numpy matplotlib scipy gdal libgdal-jp2openjpeg libgdal-netcdf pyproj scikit-image \
     pyhdf pyresample netcdf4 h5py requests pygrib cartopy zarr fsspec aiohttp
   git clone https://github.com/acolite/acolite out/acolite
   git -C out/acolite checkout ca477dd91dfb5f8eb77333824b38cb0bcce5e083
   ```

4. Run ACOLITE with the environment's own Python. Without activation, GDAL needs its plugin
   folder:

   ```bash
   E="$PWD/out/acolite-env"
   GDAL_DRIVER_PATH="$E/Library/lib/gdalplugins" GDAL_DATA="$E/Library/share/gdal" \
     PROJ_DATA="$E/Library/share/proj" "$E/python.exe" -I acolite/run_windows.py
   ```

5. `climate-pipeline calibration run` reads `acolite-windows.csv` when it exists. Without it, the
   report lists Stage 2c as incomplete.
