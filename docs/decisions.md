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

## D14. Demo reach: the Río Magdalena at Puerto Wilches, with a synthetic test event (2026-10-08)

- **Context:**
  - The Urrá validation ended in "no robust signal" (placebo p = 0.944) with regulatory
    verdict (b): no licence condition limits turbidity, and the operator publishes no data
    ([report](urra-validation/report.md)). In February 2026 the environmental authority
    announced a sanctioning procedure against the licensee
    ([regulatory.md](urra-validation/regulatory.md)).
  - D13 left the fallback to a person: a labelled synthetic event on Urrá's real series, or
    another reach.
  - `magdalena-puerto-wilches` is the screening rule's first rank and the most observable reach
    screened: 112 scored scenes in 2018-12..2025-12, a channel 31 px wide, and 1 anomalous scene
    (0.9 %) in the Urrá validation, where it was the quiet reference. It has no dated event, no
    sourced permit parameter and no confirmed environmental authority.
- **Decision:**
  - The project owner chose `magdalena-puerto-wilches` as the demo reach, with a clearly labelled
    synthetic test event. This supersedes D13's choice of `sinu-urra` for the demo. The Urrá
    validation, its settings and its outputs stay as they are.
  - Before the demo relies on it, a validation with different questions answers four things
    ([method.md](magdalena-validation/method.md)):
    1. Is the real series quiet and stable enough to be an honest baseline (false-alarm share
       with intervals, next to the `meta-orocue` control)?
    2. Does NDTI track any in-situ measurement on the reach?
    3. What is the regulatory and public-data situation?
    4. What can the detector find (injection-recovery power)?
  - The validation command reads a per-site settings file
    (`pipeline/magdalena-validation.yaml`, kind `baseline`). It reuses the Urrá code; nothing is
    copied.
- **Consequences:**
  - This reach's real-series numbers were already seen in the Urrá validation, so the method is
    not a blind pre-registration. `method.md` says so and lists what was seen.
  - The demo event is injected into a copy of the series. It lives in a separate
    `synthetic_overlay` layer whose every record carries `synthetic: true`. The real series is
    reproducible without it.
  - The interface uses "simulated permit holder" and "illustrative limit, not the real licence".
    Real names of contracts, entities and authorities appear only in `context.sources`, marked
    "public-source context, not an accusation".

## D15. Calibration and climate-context validation, run locally (2026-10-09)

- **Context:**
  - The Magdalena validation (D14, [report](magdalena-validation/report.md)) found the reach quiet,
    but showed no link between NDTI and turbidity, suspended solids or flow. In-situ pairs were too
    few, and the river level ran the wrong way.
  - The machine that runs the pipeline reaches every source needed, including a public IDEAM bucket
    with daily discharge, daily level and a daily suspended-sediment concentration (`CM_D`, partly
    from a rating model), and Earth Search's homogeneous Sentinel-2 Collection 1.
- **Decision:**
  - A preregistered validation ([preregistration](magdalena-validation/calibration-preregistration.md),
    `pipeline/calibration.yaml`) tests three things:
    1. whether any Sentinel-2 band or ratio can be calibrated to turbidity, total suspended solids
       or `CM_D` on the Magdalena main stem;
    2. whether rain or hydrology explains the reach's signal;
    3. whether the satellite sees the river's hydrology and climate phases.
  - Runs are local. A network `fetch` snapshots every input with SHA-256, and an offline `run`
    recomputes every result from the snapshots, also in CI.
  - `sentinel-2-l2a` stays the primary imagery. Collection 1 and ACOLITE (time-boxed, with Level-1C
    files the project owner downloads) are sensitivities.
  - `CM_D` is a third target, always labelled "IDEAM rating-model daily concentration".
  - The product gains an observation record contract (`docs/schema/observation-record.v1`), a
    sibling of the case file v1, which stays unchanged.
- **Consequences:**
  - A physical unit appears only for a target, range and set of stations where calibration passed.
    Otherwise the record shows an index departure.
  - A climate label is given only when the flagged signal's own season-and-rain model passed;
    otherwise it is `not_evaluated`. `unexplained` is never shown as human pressure.
  - IDEAM snapshots are committed under their CC BY-SA 4.0 licence with attribution. The
    repository-level licence is still open.
- **Outcome (2026-10-10):** [calibration report](magdalena-validation/calibration-report.md).
  - Maturity reached: baselined. Water extent follows discharge or level at 7 stations.
  - No calibration passed. Turbidity's band diagnostic passed on L2A, but its hold-out was one pair
    short and ACOLITE did not confirm it.

## D16. Water-quality estimates v2: other rivers train, the Magdalena tests (2026-10-10)

- **Context:**
  - D15 ended at _baselined_. On L2A, B8A/B04 tracked turbidity at 10 stations, but on 27 pairs from
    one river. ACOLITE disagreed, and published models erred by 100–336 % (MdSA).
  - Metadata probes set the ceilings:
    - off the Magdalena, about 570 turbidity samples on wide rivers since 2018-12, so about 20–30
      more pairs;
    - 1,554 USGS sites with continuous turbidity, 35 of them on large rivers;
    - Earth Search's Collection 1 lacks most of 2022 and every date before 2018 at the reach.
- **Decision** (the project owner's choices):
  - A preregistered validation ([preregistration](water-quality/preregistration.md),
    `pipeline/water-quality.yaml`) estimates turbidity and TSS with a declared error.
    - **Route A, the product:**
      - L2A from Earth Search from 2018-12, and from Planetary Computer before;
      - models trained on other Colombian rivers and 35 large USGS rivers, adjusted to Colombian
        units.
    - **Route B, a physics check never published:** ACOLITE DSF and RAdCor, with Dogliotti, Nechad
      and the MDN.
    - **Test:** every Magdalena pair is a frozen test set, and each candidate is evaluated on it
      once. The product model is chosen by leave-one-river-out, then refit with the Magdalena pairs
      after the test.
    - **Levels:**
      - _validated_: D15's Stage 3 criteria on the test;
      - _estimated_: MdSA ≤ 60 % and |SSPB| ≤ 30 %;
      - _indicative_: rank only.

      Conformal intervals give each value its range.
  - **Software:** numpy models in the pipeline. Gradient boosting runs only in a separate
    environment and is exported as JSON. ACOLITE and the MDN run in their own environments, and
    `uv.lock` does not change.
  - **Product:** it stays on L2A, without credentials in unattended runs. The D0 verdict stays on
    NDTI, with NIR/red added as context. Periodic runs use the Windows Task Scheduler.
  - **Disk:** every fetch stops under 20 GB free.
- **Consequences:**
  - A physical value appears only for a target and range that reached _estimated_ or _validated_,
    always with its interval.
  - FNU (USGS) and NTU (IDEAM) are never treated as one unit.
  - GPL tools (ACOLITE, the MDN) are run, never vendored.

## D17. Water-quality v4: a gauged second reach, a temporal round, Stage B (2026-10-12)

- **Context:**
  - After v3 (D16's line of work), the Magdalena turbidity estimate was at most _indicative (post
    hoc)_, at 71.5 % by nested LOSO, and the product had never run with final cards.
  - The estimate station of the demo reach, San Pablo, has 7 samples and 3 test units: its own
    error cannot be rated. The diagnosis was that the data, not the model, set the limit.
- **Decision** (the project owner's choices, preregistered as v4 before computing):
  - **A second reach on a gauged river:** the Missouri at Hermann (USGS 06934500), chosen among four
    pilot sites that met the hard criteria (≥ 300 m, continuous approved turbidity since 2017 or
    earlier, values in 2024–2026, no dam or tributary in the window), for its Magdalena-like range.
    Its validation is a locked temporal test (2023-12..2026-09) evaluated once, with models
    trained without the Missouri's sites; the card is not refit.
  - **The Magdalena's temporal question:** round 3 holds out whole hydrological years at every
    station (one sample out and forward chaining as sensitivities) and adds per-station offsets.
  - **RAdCor Stage B** for TSS (due under v2.2's rule) and turbidity (exploratory), with Level-1C
    products the owner downloads one at a time.
  - **Schema:** observation record v2 gains the bases `post_hoc_temporal_magdalena` and
    `preregistered_lockbox_site`; each estimate's unit comes from its card (FNU at Hermann).
  - **Integrity:** deviation 9 makes v3's preregistered flow features the result of record;
    deviation 10 fixes a card hashed from a CRLF working copy (CI had failed since the v2 merge).
- **Outcome** ([report](water-quality/report.md)):
  - Hermann: 34.9 % on 70 locked-test overpasses (the median: 87.7 %); 90 % coverage 97.1 %, one
    value above the preregistered ceiling, so _indicative_. Trees trained on other rivers alone
    reach 30.4 % there.
  - Magdalena: round 1 of record 63.1 % (none: its rank interval fell below the rule), round 3
    102.8 % (none). The reach publishes relative indices only.
  - RAdCor Stage B (11 more scenes): TSS 148.9 %, turbidity 115.8 % by nested LOSO on 37 pairs;
    none. Stage A's 80 % (Dogliotti, 27 pairs) did not hold.
  - The CVC probe stopped (at most 20 samples per station, no coordinates, 80–120 m channels); no
    new IDEAM sample exists after 2025-11-10.
- **Consequences:**
  - `reach` runs several reaches (`--site all`), measures its own NDTI baseline where no validation
    exists, reads cards per reach and stamps the card's unit.
  - A gauged reach notes its raw estimates beside the sealed records, and `reach check` compares new
    scenes with the gauge after the card's commit (report-only, never a level).
  - The most valuable next step for the Magdalena is in-situ: a continuous turbidity probe at the
    estimate station.

## D18. Demo reaches on gauged rivers: the Mississippi at Belle Chasse and the Platte at Louisville (2026-10-12)

- **Context:**
  - After v4 (D17) no reach published a value: the Magdalena reached no level in any round, and
    Hermann missed _estimated_ by one interval rule.
  - The project owner asked for two demo reaches, anywhere, where turbidity and suspended solids
    can be estimated well enough to publish values; the Magdalena could leave the demo.
  - The hackathon's judges ask for measured accuracy against a baseline, good data sources, a
    working demo and a named user.
- **Decision** (preregistered as v5 before computing):
  - Ten USGS rivers that met fixed data criteria were each validated once on the same locked test.
  - The demo reaches are the two with the highest turbidity level of record, then the lowest error:
    the **Mississippi at Belle Chasse** (17.8 %, _validated_) and the **Platte at Louisville** (20.3 %,
    _validated_). Their records show turbidity in FNU with a 90 % interval.
  - The **Magdalena leaves the demo** (the owner's choice). Its reach keeps running with relative
    indices only, and every Magdalena result stays in the report.
  - v5's level rule keeps the 80 % coverage floor and caps the interval's width instead of failing a
    conservative interval; it was decided after Hermann and applies only to new evaluations.
- **Consequences:**
  - The report gives every river: the median lock-box error over the nine evaluated is 33.1 %, and
    the two demo reaches are the best of ten.
  - No SSC value is published: no river had 20 locked-test SSC pairs.
  - Each demo reach has a self-measured NDTI baseline (2019–2025), records from 2026-01-01 and the
    prospective check against its gauge after its card's commit.
