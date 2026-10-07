# Architecture (design draft)

> **Status (2026-10-05): draft.** This describes the intended design, to guide the hackathon
> implementation. Nothing below is implemented yet beyond the scaffolding. Items marked
> _candidate_ are options to evaluate, not decisions.

## Goals

1. **Detect** abnormal turbidity on selected Colombian river reaches from satellite imagery.
2. **Explain** each anomaly against climate context, starting with extreme rainfall.
3. **Let regulated operators (mining) prove permit compliance** for a period without disclosing
   their operational data.
4. Make (1) and (2) **reproducible by anyone**, and (3) **verifiable by anyone** on Ethereum.

Non-goals for the hackathon: legal enforcement, real sensor hardware integration, mainnet
deployment, production-grade trusted setup.

## Components

| Component                    | Location                             | Role                                                                         |
| ---------------------------- | ------------------------------------ | ---------------------------------------------------------------------------- |
| Satellite + climate pipeline | `pipeline/` (Python)                 | Ingest imagery and rainfall, compute turbidity, detect and explain anomalies |
| Circuits                     | `contracts/circuits/` (circom)       | Encode the compliance statement as constraints                               |
| Contracts                    | `contracts/src/` (Solidity, Sepolia) | Verify proofs, record compliance attestations and anomaly references         |
| dApp                         | `web/` (React)                       | Map and timeline of anomalies; in-browser proof generation and submission    |

## Public layer: satellite detection

Everything here uses open data and open code, so any third party can re-run it and get the same
results.

1. **Area of interest.** River reaches (polygons) on rivers affected by mining, for example
   reaches of the Cauca, Magdalena or Atrato basins (_candidate_ list).
2. **Imagery.** Sentinel-2 L2A (surface reflectance, 10–20 m) through the Sentinel Hub APIs of the
   Copernicus Data Space Ecosystem (`sentinelhub-py`; credentials in `pipeline/.env`). The site
   screening that chose the study reach reads the same product from public STAC catalogs and
   cloud-optimized GeoTIFFs instead (no credentials; see [D12](decisions.md) and
   [site-screening/method.md](site-screening/method.md)).
3. **Water and cloud masking.** Keep clear water pixels only (scene classification layer and/or a
   water index such as NDWI).
4. **Turbidity proxy.** _Candidates:_ red-band reflectance calibrated to turbidity
   (Nechad/Dogliotti style), or the Normalized Difference Turbidity Index
   (B4 − B3) / (B4 + B3). Output: a per-reach time series.
5. **Anomaly detection.** Deviation from the reach's own seasonal baseline (_candidate:_ robust
   z-score on a rolling window).
6. **Climate correlation.** Join each anomaly with precipitation over the upstream catchment in a
   preceding window (_candidates:_ CHIRPS, GPM IMERG, IDEAM station data). Classify as
   rain-explained or not rain-explained.
7. **Publication.** Anomaly records (reach, date, magnitude, rainfall context) plus an evidence
   hash (for example the hash or IPFS CID of the input scene list and outputs), optionally
   anchored on-chain so they cannot be silently rewritten.

## Private layer: ZK compliance

**Actors.** The _operator_ holds a discharge permit and private measurements. The _regulator_
defines the permit (limit, period, site) and recognises the verifier. _The public_ can check
attestations.

**Statement (first version, _candidate_).** For permit `P`, period `T` and commitment `C`:

> "I know readings r₁…rₙ such that `C = Poseidon(r₁…rₙ, salt)` and every rᵢ ≤ limit(P)."

- Private inputs: the readings and the salt.
- Public inputs: permit id, period, limit and the commitment `C`.
- Bind the proof to the operator's address (as a public input, or by checking `msg.sender`), so
  a valid proof cannot be replayed by someone else.

**Flow.**

1. The operator loads their data in the dApp.
2. snarkjs computes the witness and a Groth16 proof in the browser, from the circuit's WASM and
   proving key (`.zkey`). The data never leaves the machine.
3. The operator submits the proof with MetaMask.
4. A registry contract calls the generated verifier and records `(permit, period, commitment,
operator, timestamp)`.

**Contracts (planned).** One generated `<Circuit>Verifier` per circuit (snarkjs output, not
hand-written), plus a `ComplianceRegistry` that depends on a verifier interface and stores
attestations. The scaffold already tests this path end to end with the demo circuit.

## How the layers connect

Both layers are indexed by **place** (river reach / site) and **time** (period). The dApp shows, for
a reach and a time window:

- satellite anomalies and their rainfall context;
- the compliance attestations of the sites upstream.

A turbidity spike with heavy rain upstream, at a site with a valid attestation, reads differently
from a spike in dry weather downstream of a site with no attestation. The system provides
evidence, not verdicts.

## Trust model and known limitations

- **Data authenticity (oracle problem).** A proof shows that _the operator's data_ satisfies the
  permit, not that the data is true. Mitigations to explore: readings signed by a certified sensor
  key and verified inside the circuit (EdDSA/Poseidon over BabyJubJub from circomlib), with the
  satellite layer as an independent cross-check.
- **Trusted setup.** Groth16 needs a trusted setup. Phase 1 uses the public Hermez ceremony.
  Phase 2 is currently a single development contribution, so whoever ran it could forge proofs.
  Production would need a multi-party phase-2 ceremony (see [zk-circuits.md](zk-circuits.md)).
- **Leakage through public inputs.** Public inputs (period, limit, commitment) are visible
  on-chain; avoid putting anything there that narrows down the private readings.
- **Remote sensing limits.** Clouds, narrow rivers (below Sentinel-2 resolution), sun glint and
  revisit time (about 5 days) limit coverage; anomalies are indicators, not measurements.

## Open questions

- Which river reaches and which permit format do we model for the demo?
- Rainfall source and resolution suitable for small Andean catchments?
- Daily maximum vs. period average in the compliance statement?
- Do anomaly records go on-chain (cost) or to IPFS with an on-chain hash?
- How are generated ZK artifacts frozen for the deployed demo (see
  [zk-circuits.md](zk-circuits.md#releasing-artifacts))?
