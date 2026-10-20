// Read-only check that the committed source reproduces the deployed LedgerAnchor, before (or
// instead of) trusting an explorer's "verified" badge. Sends no transaction and needs no key.
//
//   npx hardhat build --build-profile production --force --no-tests
//   npx tsx scripts/bytecode-check.ts
//
// It compares (1) the source the deployment was compiled from (Ignition's build info) with
// src/LedgerAnchor.sol, (2) the deployed runtime bytecode with Ignition's artifact outside the
// immutable `owner`, (3) that immutable with the deployer, and (4) a fresh production-profile
// compile with the deployed artifact. SEPOLIA_PUBLIC_RPC overrides the public RPC.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const DEPLOYMENT = `${ROOT}ignition/deployments/chain-11155111/`;
const RPC = process.env.SEPOLIA_PUBLIC_RPC ?? "https://ethereum-sepolia-rpc.publicnode.com";

interface Artifact {
  readonly bytecode: string;
  readonly deployedBytecode: string;
  readonly immutableReferences?: Record<string, readonly { start: number; length: number }[]>;
  readonly buildInfoId: string;
}

const json = (path: string): unknown => JSON.parse(readFileSync(path, "utf8"));
const hex = (s: string) => s.toLowerCase().replace(/^0x/, "");

const address = (json(`${DEPLOYMENT}deployed_addresses.json`) as Record<string, string>)[
  "LedgerAnchorModule#LedgerAnchor"
];
const deployed = json(`${DEPLOYMENT}artifacts/LedgerAnchorModule#LedgerAnchor.json`) as Artifact;
const build = json(`${DEPLOYMENT}build-info/${deployed.buildInfoId}.json`) as {
  input: { sources: Record<string, { content: string } | undefined> };
};
// The deployer, from Ignition's journal: the contract makes it the immutable owner.
const deployer = readFileSync(`${DEPLOYMENT}journal.jsonl`, "utf8")
  .split("\n")
  .filter((line) => line.trim() !== "")
  .map((line) => JSON.parse(line) as { from?: string })
  .find((entry) => entry.from !== undefined)?.from;

let failures = 0;
const check = (ok: boolean, what: string) => {
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
  failures += ok ? 0 : 1;
};

const source = build.input.sources["project/src/LedgerAnchor.sol"]?.content;
check(
  source === readFileSync(`${ROOT}src/LedgerAnchor.sol`, "utf8"),
  "build info source == src/LedgerAnchor.sol",
);

const response = await fetch(RPC, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "eth_getCode",
    params: [address, "latest"],
  }),
});
const chain = hex(((await response.json()) as { result: string }).result);
let onChain = chain;
let local = hex(deployed.deployedBytecode);
const values: string[] = [];
for (const list of Object.values(deployed.immutableReferences ?? {})) {
  for (const { start, length } of list) {
    values.push(chain.slice(start * 2, (start + length) * 2));
    const blank = "00".repeat(length);
    onChain = onChain.slice(0, start * 2) + blank + onChain.slice((start + length) * 2);
    local = local.slice(0, start * 2) + blank + local.slice((start + length) * 2);
  }
}
check(
  onChain === local,
  `runtime bytecode at ${String(address)} == artifact (${String(chain.length / 2)} bytes, outside the immutables)`,
);
check(
  values.length > 0 &&
    deployer !== undefined &&
    values.every((v) => v === hex(deployer).padStart(64, "0")),
  `immutable owner == deployer ${String(deployer)}`,
);

const fresh = `${ROOT}artifacts/src/LedgerAnchor.sol/LedgerAnchor.json`;
const compiled = existsSync(fresh) ? (json(fresh) as Artifact) : null;
// A build info id hashes the compiler input, so a fresh build with another profile has another id.
if (compiled?.buildInfoId === deployed.buildInfoId) {
  check(
    compiled.bytecode === deployed.bytecode &&
      compiled.deployedBytecode === deployed.deployedBytecode,
    "fresh production-profile compile == deployed artifact (same compiler input)",
  );
} else {
  console.log(
    "skip fresh compile: run `npx hardhat build --build-profile production --force` first",
  );
}
// exitCode, not exit(): exiting while fetch's connection closes trips a libuv assertion on Windows.
process.exitCode = failures === 0 ? 0 : 1;
