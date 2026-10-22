// Whether one record is covered by an anchor on Sepolia, for the case file's trust strip. The
// ledger and its anchors are read once per reach and kept for the session, so stepping through the
// passes (the time-lapse) does not query the RPC again.
import { useEffect, useState } from "react";

import { loadText } from "../reaches/data.ts";
import type { ReachData } from "../reaches/types.ts";
import { readAnchors } from "./client.ts";
import { LEDGER_ANCHOR_ADDRESS } from "./config.ts";
import { useEthersProvider } from "./ethers.ts";
import {
  anchorStatus,
  ledgerHead,
  ledgerPath,
  subjectLabel,
  type ChainAnchor,
  type LedgerKind,
} from "./ledger.ts";
import type { ChainCheck } from "./useLedgerAnchor.ts";

/** A record's anchor, or that it is still being read. */
export type RecordAnchor = ChainCheck | { readonly state: "checking" };

interface LedgerView {
  readonly hashes: string[];
  readonly records: string[]; // each line's record SHA-256, in order
}

const ledgers = new Map<string, Promise<LedgerView>>();
const anchors = new Map<string, Promise<ChainAnchor[]>>();

function ledgerOf(reach: ReachData, kind: LedgerKind): Promise<LedgerView> {
  const path = ledgerPath(kind);
  const key = `${reach.base}${path}`;
  let found = ledgers.get(key);
  if (found === undefined) {
    found = loadText(reach.base, path).then(async (text) => {
      const { hashes } = await ledgerHead(text);
      const records = text
        .split("\n")
        .filter((line) => line.trim() !== "")
        .map((line) => String((JSON.parse(line) as { recordSha256?: unknown }).recordSha256));
      return { hashes, records };
    });
    found.catch(() => ledgers.delete(key));
    ledgers.set(key, found);
  }
  return found;
}

/**
 * The anchor status of one record of a reach's ledger.
 *
 * @param reach - The reach.
 * @param kind - Which of its ledgers holds the record.
 * @param recordSha256 - The record's seal (null: no record selected).
 * @returns `checking` while the ledger and the anchors load, then the status (`unavailable`
 *   without a contract, a provider or a readable RPC).
 */
export function useRecordAnchor(
  reach: ReachData,
  kind: LedgerKind,
  recordSha256: string | null,
): RecordAnchor {
  const provider = useEthersProvider();
  const address = LEDGER_ANCHOR_ADDRESS;
  const [state, setState] = useState<{ key: string; value: RecordAnchor } | null>(null);
  const key = `${reach.base}|${kind}|${recordSha256 ?? ""}`;

  useEffect(() => {
    if (recordSha256 === null || address === null || provider === undefined) {
      return undefined;
    }
    let live = true;
    const label = subjectLabel(reach.info.site, kind);
    let read = anchors.get(label);
    if (read === undefined) {
      read = readAnchors(provider, address, label);
      read.catch(() => anchors.delete(label));
      anchors.set(label, read);
    }
    Promise.all([ledgerOf(reach, kind), read])
      .then(([ledger, found]) => {
        if (live) {
          const position = ledger.records.indexOf(recordSha256);
          setState({
            key,
            value: { ...anchorStatus(found, position, ledger.hashes), via: "public" },
          });
        }
      })
      .catch(() => {
        if (live) {
          setState({ key, value: { state: "unavailable" } });
        }
      });
    return () => {
      live = false;
    };
  }, [reach, kind, recordSha256, address, provider, key]);

  if (recordSha256 === null || address === null || provider === undefined) {
    return { state: "unavailable" };
  }
  return state?.key === key ? state.value : { state: "checking" };
}
