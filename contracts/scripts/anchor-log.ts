// Rebuilds docs/ledgers/anchors.jsonl from the LedgerAnchor's state, read-only, through a public
// Sepolia RPC (no key, no keystore, no transaction). `anchor.ts` does the same after anchoring.
//
//   npx tsx scripts/anchor-log.ts            (from contracts/; SEPOLIA_PUBLIC_RPC overrides the RPC)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { JsonRpcProvider } from "ethers";

import { LOG, writeLog } from "./ledgers.ts";

const DEPLOYMENT = new URL(
  "../ignition/deployments/chain-11155111/deployed_addresses.json",
  import.meta.url,
);
const rpc = process.env.SEPOLIA_PUBLIC_RPC ?? "https://ethereum-sepolia-rpc.publicnode.com";
const addresses = JSON.parse(readFileSync(DEPLOYMENT, "utf8")) as Record<string, string>;
const address = addresses["LedgerAnchorModule#LedgerAnchor"];
if (address === undefined) {
  throw new Error("no deployment of LedgerAnchor on Sepolia");
}
const anchors = await writeLog(new JsonRpcProvider(rpc, 11_155_111), address);
console.log(`${String(anchors.length)} anchors written to ${fileURLToPath(LOG)}`);
for (const a of anchors) {
  console.log(`  ${a.timestampUtc} block ${String(a.block)}  ${a.label}  ${String(a.lines)} lines`);
}
