// The ledgers RiverEtch anchors on Sepolia, and the anchoring log rebuilt from the contract.
// Shared by `anchor.ts` (sends the anchors) and `anchor-log.ts` (read-only).
//
// The log, `docs/ledgers/anchors.jsonl`, is a mirror of the chain, not a source of truth: one line
// per anchor (subject, index, head, lines, block, time and transaction). It is regenerated from
// the contract's own state (`count`, `anchorAt`) every time, and each anchor's transaction is the
// one in its block that called the contract with its subject, so anyone can rebuild the log from a
// public RPC and compare. (Public RPCs prune their event index, so events are not used.)
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

import { id, Interface, type Provider } from "ethers";

import { LEDGER_ANCHOR_ABI } from "../../web/src/features/chain/abi.ts";
import { readAnchors } from "../../web/src/features/chain/client.ts";
import { ledgerHead } from "../../web/src/features/chain/ledger.ts";

/** One anchorable ledger: its label (keccak256 is the subject) and its file. */
export interface LedgerFile {
  /** E.g. `terrachain:platte-louisville:observations`. */
  readonly label: string;
  /** The ledger's file. */
  readonly path: URL;
}

/** One anchor, as the log records it. */
export interface LoggedAnchor {
  readonly label: string;
  readonly subject: string;
  readonly index: number;
  readonly head: string;
  readonly lines: number;
  readonly block: number;
  readonly timestampUtc: string;
  readonly tx: string;
}

const ROOT = new URL("../../", import.meta.url);
const REACHES = new URL("docs/water-quality/reach/", ROOT);

/** The demo reaches whose ledgers are anchored. */
export const REACHES_ANCHORED = ["mississippi-belle-chasse", "platte-louisville"] as const;

/** The anchoring log (a mirror of the chain's events). */
export const LOG = new URL("docs/ledgers/anchors.jsonl", ROOT);

const ANCHOR = new Interface(LEDGER_ANCHOR_ABI);

/**
 * Every ledger that can be anchored: each demo reach's observations, water temperatures and
 * outcomes, and the project's frozen artifacts. A ledger whose file does not exist yet is skipped
 * by the callers.
 *
 * @returns The ledgers, in a stable order.
 */
export function ledgers(): LedgerFile[] {
  const out: LedgerFile[] = [
    {
      label: "terrachain:riveretch:frozen-artifacts",
      path: new URL("docs/ledgers/frozen-artifacts.jsonl", ROOT),
    },
  ];
  for (const reach of REACHES_ANCHORED) {
    const folder = new URL(`${reach}/examples/`, REACHES);
    out.push(
      { label: `terrachain:${reach}:observations`, path: new URL("ledger.jsonl", folder) },
      {
        label: `terrachain:${reach}:water-temperature`,
        path: new URL("thermal/ledger.jsonl", folder),
      },
      {
        label: `terrachain:${reach}:outcomes`,
        path: new URL("outcomes/ledger.jsonl", folder),
      },
    );
  }
  return out;
}

/**
 * A ledger file's head and line count, with the web app's own code.
 *
 * @param path - The ledger.
 * @returns The head (null for a missing or empty ledger) and the line count.
 */
export async function headOf(path: URL): Promise<{ head: string | null; lines: number }> {
  if (!existsSync(path)) {
    return { head: null, lines: 0 };
  }
  const { head, lines } = await ledgerHead(readFileSync(path, "utf8"));
  return { head, lines };
}

// The transaction in a block that called the contract with a subject (null if none is found).
async function transactionOf(
  provider: Provider,
  address: string,
  blockNumber: number,
  subject: string,
): Promise<string | null> {
  const block = await provider.getBlock(blockNumber, true);
  for (const tx of block?.prefetchedTransactions ?? []) {
    if (tx.to?.toLowerCase() !== address.toLowerCase()) {
      continue;
    }
    const call = ANCHOR.parseTransaction({ data: tx.data });
    const subjects: unknown =
      call?.name === "anchorBatch" ? call.args[0] : call?.name === "anchor" ? [call.args[0]] : [];
    if (Array.isArray(subjects) && subjects.some((s) => String(s) === subject)) {
      return tx.hash;
    }
  }
  return null;
}

/**
 * Every anchor of the given ledgers, read from the contract's state, oldest first, each with the
 * transaction that made it.
 *
 * @param provider - A Sepolia provider.
 * @param address - The contract.
 * @param labels - The ledgers' labels.
 * @returns One entry per anchor.
 */
export async function anchorsFromChain(
  provider: Provider,
  address: string,
  labels: readonly string[],
): Promise<LoggedAnchor[]> {
  const out: LoggedAnchor[] = [];
  for (const label of labels) {
    const subject = id(label);
    const anchors = await readAnchors(provider, address, label);
    for (const [index, a] of anchors.entries()) {
      const tx = await transactionOf(provider, address, a.blockNumber, subject);
      out.push({
        label,
        subject,
        index,
        head: a.head,
        lines: a.lines,
        block: a.blockNumber,
        timestampUtc: new Date(a.timestamp * 1000).toISOString().replace(".000Z", "Z"),
        tx: tx ?? "unknown",
      });
    }
  }
  return out.sort((a, b) => a.block - b.block || a.label.localeCompare(b.label));
}

/**
 * Rewrites the anchoring log from the chain's events.
 *
 * @param provider - A Sepolia provider.
 * @param address - The contract.
 * @returns The anchors written.
 */
export async function writeLog(provider: Provider, address: string): Promise<LoggedAnchor[]> {
  const anchors = await anchorsFromChain(
    provider,
    address,
    ledgers().map((l) => l.label),
  );
  const keys = ["block", "head", "index", "label", "lines", "subject", "timestampUtc", "tx"];
  const text = anchors
    .map((a) => JSON.stringify(a, keys))
    .map((line) => `${line}\n`)
    .join("");
  mkdirSync(new URL(".", LOG), { recursive: true });
  writeFileSync(LOG, text, "utf8");
  return anchors;
}
