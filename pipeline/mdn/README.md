# MDN (Route B3 of the water-quality validation v2)

Route B3 runs the Mixture Density Network of Pahlevan, Smith et al. as published: its Sentinel-2
(MSI) multi-product model, whose TSS output is compared with the Magdalena samples
([preregistration](../../docs/water-quality/preregistration.md)). It is a physics check, never a
value the product publishes.

| What        | Value                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------- |
| MDN         | `https://github.com/BrandonSmithJ/MDN` at `ae1626c7990436d512044fa878f6bf276b5ce20d` (GPL-3.0) |
| Weights     | `Weights/MSI/1b79098d…` (config: product `chl,tss,cdom`, `n_mix` 5, version 2.0.0)             |
| Input       | Rrs = ACOLITE `rhos` / π at 443, 490, 560, 665, 705, 740 and 783 nm (DSF and RAdCor)           |
| Environment | micromamba, Python 3.8, the pins of [requirements.txt](requirements.txt) (CPU TensorFlow 2.5)  |
| Output      | `docs/water-quality/inputs/mdn/predictions.csv` and `manifest.csv`                             |

- The MDN runs in its own environment, so the project's `uv.lock` does not change. No MDN code
  enters the repository: it is cloned under `pipeline/out/` (gitignored) and run as a tool.
- The MDN loads pickled configs from its own repository at the pinned commit. That is why it runs
  isolated, from a clone checked against the pinned commit.
- **Budget:** the environment takes 1.5 GB and the clone 0.16 GB (measured on 2026-10-10). If it
  cannot be built within 3 h, B3 is dropped and the report says so.

## Steps (Git Bash, from `pipeline/`)

1. The ACOLITE window medians exist (`acolite/run_windows.py --outputs`, see
   [../acolite/README.md](../acolite/README.md)).
2. Set up the environment and the clone once:

   ```bash
   export MAMBA_ROOT_PREFIX="$PWD/out/micromamba-root"
   out/tools/micromamba.exe create -y -p "$PWD/out/mdn-env" -c conda-forge --override-channels \
     python=3.8 pip
   out/mdn-env/python.exe -m pip install --no-cache-dir -r mdn/requirements.txt
   git clone https://github.com/BrandonSmithJ/MDN out/mdn-src/MDN
   git -C out/mdn-src/MDN checkout ae1626c7990436d512044fa878f6bf276b5ce20d
   ```

3. Run it:

   ```bash
   out/mdn-env/python.exe -I mdn/run_mdn.py
   ```

`climate-pipeline quality run` reads `predictions.csv` when it exists. Without it, the report lists
B3 as incomplete.
