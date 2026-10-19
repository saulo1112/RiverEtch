// Anchors RiverEtch's ledgers on Sepolia from the terminal, with the account in Hardhat's keystore
// (SEPOLIA_PRIVATE_KEY). The transaction leaves the account directly, with no wallet in between.
// It reuses the web app's own client, so it anchors exactly what the web app would.
//
//   npx hardhat run scripts/anchor.ts --network sepolia
//
// The ledgers are listed in `ledgers.ts`: the frozen artifacts and each demo reach's observations,
// water temperatures and outcomes. Only ledgers with more lines than their last anchor are sent, in
// one batch; run it again after new records. Afterwards it rebuilds docs/ledgers/anchors.jsonl from
// the contract's state (also possible without a key: `npx tsx scripts/anchor-log.ts`).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { network } from "hardhat";

import { anchorLedgers, readAnchors } from "../../web/src/features/chain/client.ts";
import { headOf, ledgers, LOG, writeLog } from "./ledgers.ts";

const DEPLOYMENT = new URL(
  "../ignition/deployments/chain-11155111/deployed_addresses.json",
  import.meta.url,
);

const { ethers } = await network.create("sepolia");
const addresses = JSON.parse(readFileSync(DEPLOYMENT, "utf8")) as Record<string, string>;
const address = addresses["LedgerAnchorModule#LedgerAnchor"];
const [signer] = await ethers.getSigners();
if (address === undefined || signer === undefined) {
  throw new Error("no deployment of LedgerAnchor on Sepolia, or no account in the keystore");
}
console.log(`contract ${address}\naccount  ${await signer.getAddress()}`);

const pending = [];
for (const { label, path } of ledgers()) {
  const { head, lines } = await headOf(path);
  if (head === null) {
    continue; // the ledger does not exist yet
  }
  const anchors = await readAnchors(ethers.provider, address, label);
  const done = anchors.at(-1)?.lines ?? 0;
  console.log(`${label}: ${String(lines)} lines, anchored up to ${String(done)}`);
  if (lines > done) {
    pending.push({ label, head, lines });
  }
}

if (pending.length === 0) {
  console.log("Every ledger is already anchored up to its last line.");
} else {
  const hash = await anchorLedgers(signer, address, pending);
  console.log(
    `Anchored ${String(pending.length)} ledgers.\nhttps://sepolia.etherscan.io/tx/${hash}`,
  );
}
const logged = await writeLog(ethers.provider, address);
console.log(`${String(logged.length)} anchors in ${fileURLToPath(LOG)} (commit it)`);
