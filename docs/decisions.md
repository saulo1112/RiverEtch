# Decision log

Short records of the architectural and tooling decisions, with the reasoning behind them. Newest
last. Format: context → decision → consequences.

## D1. Monorepo with npm workspaces plus a uv-managed Python project (2026-10-05)

- **Context:** Three codebases (contracts and circuits, frontend, data pipeline) that change
  together during a 3-week hackathon.
- **Decision:**
  - One repository; `contracts/` and `web/` are npm workspaces.
  - `pipeline/` is a Python project managed by uv in the same repository, **not** an npm
    workspace; root npm scripts wrap its commands.
  - Lint, format and TypeScript base config live at the root.
- **Consequences:**
  - A single `npm install` covers the JavaScript side.
  - Python needs `uv sync`.
  - CI runs one job per ecosystem.

## D2. Hardhat 3 instead of Foundry (2026-10-05)

- **Context:** The ZK proofs are produced by snarkjs (JavaScript), and the stack prescribes ethers.js.
- **Decision:** Hardhat 3 with the mocha + ethers toolbox.
- **Why:**
  - TypeScript tests can generate a snarkjs proof and check it against the generated verifier in
    the same test; Foundry would need `vm.ffi` or pre-generated fixtures.
  - Hardhat 3 also runs Foundry-compatible Solidity tests (forge-std, fuzzing), so fast Solidity
    unit tests are not lost.
  - Everything installs from npm: no separate toolchain, simpler CI.
  - Ignition handles deployments and the keystore holds secrets.
- **Consequences:** Solidity sources in `contracts/src/` (avoids `contracts/contracts/`); forge-std
  is a GitHub dependency, as in Hardhat's own template.

## D3. Vite + React SPA instead of Next.js (2026-10-05)

- **Context:**
  - Everything in the dApp runs client-side: wallet connection, in-browser proving (snarkjs
    WASM), maps.
  - Server-side logic and secrets (Sentinel Hub credentials) belong to the pipeline.
- **Decision:** Vite + React + TypeScript single-page app, based on the create-vite react-ts template.
- **Consequences:**
  - No SSR/hydration workarounds for wagmi, RainbowKit, snarkjs or Leaflet.
  - Static hosting anywhere, including IPFS.
  - No API routes: if a backend is ever needed, it is a separate service.

## D4. Python for the satellite and climate pipeline (2026-10-05)

- **Decision:** Python 3.12, managed with uv; ruff, mypy (strict) and pytest.
- **Why:**
  - `sentinelhub-py` is the official Sentinel Hub SDK and supports the Copernicus Data Space
    Ecosystem.
  - numpy, rasterio and xarray cover raster and rainfall analysis.
  - Python 3.12 because current numpy and rasterio releases require it.

## D5. Groth16 with circom + snarkjs; two-level circuit testing (2026-10-05)

- **Decision:**
  - Groth16 on BN254: cheapest on-chain verification, mature tooling.
  - An explicit build script (`npm run zk:build`) rather than a framework.
  - Tests at two levels: circom_tester constraint tests (circomlib's pattern, no setup needed),
    and proof-level tests that verify real proofs with the generated Solidity verifier on Hardhat.
- **Rejected:** circomkit, which has good DX but would duplicate the build pipeline with its own
  conventions.

## D6. Trusted setup: Hermez phase 1, development phase 2 (2026-10-05)

- **Decision:**
  - Phase 1 downloads the public Hermez Powers of Tau, verified against pinned BLAKE2b-512
    hashes; `--local-ptau` works offline.
  - Phase 2 is a single development contribution.
- **Consequences:** Fine for a testnet demo. A production deployment needs a multi-party phase 2
  (see [zk-circuits.md](zk-circuits.md#trusted-setup)).

## D7. Generated ZK artifacts are not committed (2026-10-05)

- **Decision:** ptau, r1cs, wasm, witness, zkey and the generated verifier `.sol` are built by
  `npm run zk:build` and ignored by git.
- **Consequences:**
  - CI and a fresh clone must run `zk:build` before compiling contracts.
  - A release set must be frozen before the Sepolia demo (see
    [zk-circuits.md](zk-circuits.md#releasing-artifacts)).

## D8. Documentation standard enforced by linters (2026-10-05)

- **Decision:**
  - NatSpec through Solhint `use-natspec` as an error. Named return values are required, because
    Solhint only checks `@return` tags for named returns.
  - TSDoc on exported functions, components and classes through eslint-plugin-jsdoc.
  - Google-style docstrings through ruff.

## D9. Pre-commit: auto-fix formatting, block what cannot be fixed (2026-10-05)

- **Decision:** Husky + lint-staged on staged files only.
  - Prettier, `eslint --fix` and `ruff --fix` repair what they can and re-stage it.
  - Remaining lint errors (missing docs, unsafe types, Solhint findings) block the commit.
  - No tests in the hook: CI runs them.
- **Consequences:** Low friction; a merely badly-formatted file is fixed, not rejected.

## D10. Version pins forced by compatibility (2026-10-05)

- **TypeScript `~6.0.3`, not 7.x:** typescript-eslint supports TypeScript < 6.1.
- **wagmi 2 (+ viem 2), not wagmi 3:** RainbowKit 2.2 requires wagmi 2.
- **Node.js 24 LTS:** required by lint-staged 17 (≥ 22.22.1) and eslint-plugin-jsdoc 65
  (≥ 22.22.2 / 24.15).
- **solc 0.8.34** (Hardhat 3.18 template, EVM target osaka) and **circom 2.2.3**, pinned in CI.
- **Dependency install scripts** are disabled through npm's `allowScripts`. The packages denied
  so far (esbuild, bufferutil, utf-8-validate, keccak) all work without theirs.

## D11. ethers.js usage on the frontend (2026-10-05)

- **Context:** wagmi (required by RainbowKit) is built on viem; the stack prescribes ethers.js for
  contract interaction.
- **Decision:** Contract tests already use ethers v6. In `web/`, ethers v6 is added with the first
  contract call, through wagmi's documented viem-to-ethers adapter, not as an unused dependency
  of the skeleton.

## D12. Site screening on STAC + COGs and Open-Meteo, run in GitHub Actions (2026-10-07)

- **Context:** Before modelling a permit, the project needs one real study reach. The choice should
  be data-driven and reproducible, and diversified by pressure type, because gold-mining turbidity
  in Colombia is well-trodden prior art. The development sandbox cannot reach the STAC APIs,
  Open-Meteo or CHIRPS.
- **Decision:**
  - The screening reads Sentinel-2 L2A from a STAC API: Earth Search v1 by default, Planetary
    Computer behind the same interface. It reads the cloud-optimized GeoTIFFs with rasterio and
    takes hourly rain from the Open-Meteo archive. It needs no credentials, unlike the Sentinel
    Hub route of D4, which stays the plan for operational ingestion.
  - Every threshold and site is configuration (`pipeline/screening.yaml`, `pipeline/sites/`). The
    method was pre-registered in `docs/site-screening/method.md` before any real run.
  - The real run is the `Site screening` workflow. Its small outputs are committed under
    `docs/site-screening/results/`; rasters and caches never are.
- **Consequences:**
  - The screening is reproducible by anyone with the repository and GitHub Actions.
  - Results carry the method blob, config hash and STAC item-id hashes.
  - The sandbox runs only the offline tests.
  - Reflectance scaling cannot be taken from `raster:bands` alone. Earth Search items flagged
    `earthsearch:boa_offset_applied` already carry the BOA offset in their pixels, and some
    unflagged Sentinel-2C items do too. Any reader of these COGs (the screening, a future
    operational pipeline) needs an empirical check, such as water B11 near 0, before using the
    values.

## D13. Study reach: the Río Sinú below Urrá I, chosen over the rule's first rank (2026-10-07)

- **Context:**
  - The site screening's pre-registered rule recommends the Río Magdalena at Puerto Wilches;
    the Río Sinú below Urrá I (`sinu-urra`) is the runner-up
    ([report](site-screening/report.md#recommendation)).
  - The ranking is fragile. In the pre-registered variant, dropping either the coverage or the
    width term puts Urrá first. In the post-hoc variant, dropping coverage puts Urrá first and
    dropping width puts Betania first.
  - The report leaves the choice between "best imagery" and "best story" to a person.
- **Decision:**
  - The project owner chose `sinu-urra` for the demo. It has dated operations, a licensed
    operator and one observation inside an event window. This deviates from the pre-registered
    recommendation rule, and is recorded here as such.
  - Before the demo relies on it, two checks were set:
    - a regulatory verification, with verdict (b): the licensee is verified, but no licence
      condition is a limit the observation can be compared with
      ([regulatory.md](urra-validation/regulatory.md));
    - a pre-registered robustness check of the signal ([method.md](urra-validation/method.md)).
- **Consequences:**
  - Any permit in the demo is labelled as simulated: holder "simulated permit holder", limit
    "illustrative limit, not the real licence".
  - The interface names the river and the municipality, never the dam or the company.
  - If the validation finds "no robust signal", or cannot compute a verdict, a person decides the
    fallback: a clearly labelled synthetic test event on Urrá's real series, or another reach.
    The validation report does not decide it.
