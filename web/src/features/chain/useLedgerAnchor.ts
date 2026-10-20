// The ledger anchor from a reach's case view: whether one of its records is anchored on Sepolia,
// and, for the contract's owner, anchoring the reach's ledgers in one transaction.
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "wagmi";

import { loadText } from "../reaches/data.ts";
import type { ReachData } from "../reaches/types.ts";
import { anchorLedgers, readAnchors, readOwner, type LedgerState } from "./client.ts";
import { LEDGER_ANCHOR_ADDRESS, SEPOLIA_CHAIN_ID } from "./config.ts";
import { useEthersProvider, useEthersSigner } from "./ethers.ts";
import {
  anchorStatus,
  ledgerHead,
  subjectLabel,
  type AnchorStatus,
  type LedgerKind,
} from "./ledger.ts";

/**
 * What a record's anchor check found (`unavailable`: no contract yet, or the RPC failed), and
 * through what it was read: the visitor's own wallet (its EIP-1193 provider, on Sepolia), or the
 * app's public Sepolia node.
 */
export type ChainCheck =
  (AnchorStatus & { readonly via: "wallet" | "public" }) | { readonly state: "unavailable" };

/** What anchoring the reach's ledgers did. */
export type AnchorOutcome =
  | { readonly state: "done"; readonly hash: string; readonly ledgers: number }
  | { readonly state: "upToDate" };

// The reach's ledgers, by kind, as files of its folder.
function ledgerFiles(reach: ReachData): { kind: LedgerKind; path: string }[] {
  return [
    { kind: "observations", path: "ledger.jsonl" },
    ...(reach.thermal === null
      ? []
      : [{ kind: "water-temperature" as const, path: "thermal/ledger.jsonl" }]),
  ];
}

/**
 * The ledger anchor for one reach.
 *
 * @param reach - The reach.
 * @returns Whether a contract is configured, whether the connected account owns it, a record
 *   check and the owner's anchoring action.
 */
export function useLedgerAnchor(reach: ReachData) {
  const provider = useEthersProvider();
  const signer = useEthersSigner();
  // A connected wallet's own provider on Sepolia: the anchors read through the visitor's node.
  const wallet = useEthersSigner({ chainId: SEPOLIA_CHAIN_ID })?.provider;
  const { address: account } = useAccount();
  const [owner, setOwner] = useState<string | null>(null);
  const address = LEDGER_ANCHOR_ADDRESS;
  const site = reach.info.site;

  useEffect(() => {
    if (address === null || provider === undefined) {
      return undefined;
    }
    let live = true;
    readOwner(provider, address)
      .then((found) => {
        if (live) {
          setOwner(found);
        }
      })
      .catch(() => {
        // No owner read: the anchoring action stays hidden.
      });
    return () => {
      live = false;
    };
  }, [address, provider]);

  const check = useCallback(
    async (kind: LedgerKind, position: number, lineHashes: readonly string[]) => {
      if (address === null || (provider === undefined && wallet === undefined)) {
        return { state: "unavailable" } as const;
      }
      const hashes = lineHashes.map((h) => (h.startsWith("0x") ? h : `0x${h}`));
      const label = subjectLabel(site, kind);
      if (wallet !== undefined) {
        try {
          const network = await wallet.getNetwork();
          if (network.chainId === BigInt(SEPOLIA_CHAIN_ID)) {
            const anchors = await readAnchors(wallet, address, label);
            return { ...anchorStatus(anchors, position, hashes), via: "wallet" } as const;
          }
        } catch {
          // The wallet could not answer: fall back to the public node.
        }
      }
      if (provider === undefined) {
        return { state: "unavailable" } as const;
      }
      try {
        const anchors = await readAnchors(provider, address, label);
        return { ...anchorStatus(anchors, position, hashes), via: "public" } as const;
      } catch {
        return { state: "unavailable" } as const;
      }
    },
    [address, provider, wallet, site],
  );

  const anchorReach = useCallback(async (): Promise<AnchorOutcome> => {
    if (address === null || provider === undefined || signer === undefined) {
      throw new Error("no contract or no wallet");
    }
    const states: LedgerState[] = [];
    for (const { kind, path } of ledgerFiles(reach)) {
      const { head, lines } = await ledgerHead(await loadText(reach.base, path));
      if (head === null) {
        continue;
      }
      const label = subjectLabel(site, kind);
      const anchors = await readAnchors(provider, address, label);
      if (lines > (anchors.at(-1)?.lines ?? 0)) {
        states.push({ label, head, lines });
      }
    }
    if (states.length === 0) {
      return { state: "upToDate" };
    }
    const hash = await anchorLedgers(signer, address, states);
    return { state: "done", hash, ledgers: states.length };
  }, [address, provider, signer, reach, site]);

  const isOwner = owner !== null && owner.toLowerCase() === account?.toLowerCase();
  return { configured: address !== null, address, isOwner, check, anchorReach };
}
