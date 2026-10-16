// Anchors the demo reaches' ledgers on Sepolia from the terminal, with the account in Hardhat's
// keystore (SEPOLIA_PRIVATE_KEY). The transaction leaves the account directly, with no wallet in
// between. It reuses the web app's own client, so it anchors exactly what the web app would.
//
//   npx hardhat run scripts/anchor.ts --network sepolia
//
// Only ledgers with more lines than their last anchor are sent; run it again after new records.
import { readFileSync } from "node:fs";

import { network } from "hardhat";

import { anchorLedgers, readAnchors } from "../../web/src/features/chain/client.ts";
import { ledgerHead, subjectLabel, type LedgerKind } from "../../web/src/features/chain/ledger.ts";

const REACHES = ["mississippi-belle-chasse", "platte-louisville"];
const LEDGERS: { kind: LedgerKind; path: string }[] = [
  { kind: "observations", path: "ledger.jsonl" },
  { kind: "water-temperature", path: "thermal/ledger.jsonl" },
];
const DEPLOYMENT = new URL(
  "../ignition/deployments/chain-11155111/deployed_addresses.json",
  import.meta.url,
);
const EXAMPLES = new URL("../../docs/water-quality/reach/", import.meta.url);

const { ethers } = await network.create("sepolia");
const addresses = JSON.parse(readFileSync(DEPLOYMENT, "utf8")) as Record<string, string>;
const address = addresses["LedgerAnchorModule#LedgerAnchor"];
const [signer] = await ethers.getSigners();
if (address === undefined || signer === undefined) {
  throw new Error("no deployment of LedgerAnchor on Sepolia, or no account in the keystore");
}
console.log(`contract ${address}\naccount  ${await signer.getAddress()}`);

const pending = [];
for (const reach of REACHES) {
  for (const { kind, path } of LEDGERS) {
    let text: string;
    try {
      text = readFileSync(new URL(`${reach}/examples/${path}`, EXAMPLES), "utf8");
    } catch {
      continue; // the reach keeps no such ledger
    }
    const { head, lines } = await ledgerHead(text);
    if (head === null) {
      continue;
    }
    const label = subjectLabel(reach, kind);
    const anchors = await readAnchors(ethers.provider, address, label);
    const done = anchors.at(-1)?.lines ?? 0;
    console.log(`${label}: ${String(lines)} lines, anchored up to ${String(done)}`);
    if (lines > done) {
      pending.push({ label, head, lines });
    }
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
