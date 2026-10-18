# Anchoring the ledgers on Ethereum (Sepolia)

Every TerraChain record is sealed (the SHA-256 of its canonical JSON) and listed in an append-only
ledger whose lines each name the SHA-256 of the line before. The ledger can be checked by anyone,
but it lives in this repository: whoever controls the repository could rewrite it. Anchoring the
ledger's **head** (the SHA-256 of its last line) on a public chain adds a timestamp nobody controls.

## What is anchored

- **One subject per ledger:** `keccak256("terrachain:<reach>:<ledger>")`, where the ledger is
  `observations` (Sentinel-2 records) or `water-temperature` (Landsat records).
- **Its head and its line count,** with the block's time and number. Because each line names the
  one before, the head commits to every record above it.
- **The contract** (`contracts/src/LedgerAnchor.sol`):
  - only its owner, the deploying account, can anchor;
  - a ledger only grows: an anchor must have more lines than the last one;
  - `anchorBatch` anchors several ledgers in one transaction;
  - `count` and `anchorAt` read every anchor, oldest first.

## What it proves, and what it does not

- **It proves** that, at the anchor's block time, the ledger already held every record up to that
  line, unchanged. If the ledger is edited later, its hash of that line no longer matches the anchor
  and the web app shows the mismatch.
- **It does not prove anything before the first anchor.** The 2026 records sealed before the
  contract existed are covered only from that day on.
- **It does not prove a value is right:** that is the locked tests' and the live check's job.
- **Sepolia is a test network.** The proof is public and checkable, but it is not mainnet.

## Deploying (once)

You need an Ethereum account with a little Sepolia ETH (from a faucet). Use a test-only account.

1. **Store the RPC URL and the account's key in Hardhat's encrypted keystore.** Hardhat asks for the
   keystore password. Nothing is written in the repository.

   ```bash
   cd contracts
   npx hardhat keystore set SEPOLIA_RPC_URL
   npx hardhat keystore set SEPOLIA_PRIVATE_KEY
   npx hardhat keystore set ETHERSCAN_API_KEY   # optional: verifies the source on Etherscan
   ```

2. **Deploy the contract with Hardhat Ignition.** Hardhat asks for the keystore password and a
   confirmation.

   ```bash
   npx hardhat ignition deploy ignition/modules/LedgerAnchor.ts --network sepolia --verify
   ```

3. **Commit the deployment.** Ignition writes the address under
   `contracts/ignition/deployments/chain-11155111/`. The web app reads
   `deployed_addresses.json` from there when it builds.

## Anchoring (each time new records arrive)

From `contracts/`, with the owner's account in the keystore:

```bash
npx hardhat run scripts/anchor.ts --network sepolia
```

- The script computes each ledger's head from the published records, with the web app's own code.
- It skips any ledger already anchored up to its last line.
- It sends one `anchorBatch` transaction for the rest and prints its hash.

The demo reaches' four ledgers were anchored this way at block 11924112.

The web app also offers **Anchor this reach's ledgers on Sepolia** in the record panel, shown only
when the connected wallet is the contract's owner. It sends the same transaction. A MetaMask smart
account (EIP-7702) routes the call through a delegation that ran out of gas in our test, so the
terminal is the supported path.

## Verifying

- **In the web app:** **Verify this record** reads the anchors without a wallet. It shows whether
  the record's ledger line is covered by an anchor (with its block and date), is recorded after the
  last anchor, or no longer matches the anchor.
- **On Etherscan:** the contract's `anchorAt(subject, index)` returns each anchor. The subject is
  the keccak256 of the label above.
