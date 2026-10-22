// What "Export with proof" and "Check a file" read in the browser: a reach's published files, its
// record lists' posts on Ethereum (through the visitor's own wallet on the test network, else a
// public node; null when neither answers, so nothing is shown as checked), the Bitcoin timestamps
// and signatures the daily run publishes, two public block explorers, and the published key.
import { useMemo } from "react";

import {
  loadProof,
  loadReach,
  loadSignatures,
  loadStatus,
  loadTextOrNull,
} from "../reaches/data.ts";
import type { CheckIo } from "../reaches/proofcheck.ts";
import { readAnchors } from "./client.ts";
import { LEDGER_ANCHOR_ADDRESS, SEPOLIA_CHAIN_ID } from "./config.ts";
import { useEthersProvider, useEthersSigner } from "./ethers.ts";
import { explorerHeader } from "./witness.ts";

/**
 * The browser's reader of the chain and the published files, for an export or a check.
 *
 * @returns The reader.
 */
export function useProofIo(): CheckIo {
  const provider = useEthersProvider();
  const wallet = useEthersSigner({ chainId: SEPOLIA_CHAIN_ID })?.provider;
  return useMemo(
    (): CheckIo => ({
      text: (reach, path) => loadTextOrNull(reach.base, path),
      anchors: async (label) => {
        const address = LEDGER_ANCHOR_ADDRESS;
        if (address === null) {
          return null;
        }
        if (wallet !== undefined) {
          try {
            const network = await wallet.getNetwork();
            if (network.chainId === BigInt(SEPOLIA_CHAIN_ID)) {
              return await readAnchors(wallet, address, label);
            }
          } catch {
            // The wallet could not answer: the public node is tried next.
          }
        }
        if (provider === undefined) {
          return null;
        }
        try {
          return await readAnchors(provider, address, label);
        } catch {
          return null;
        }
      },
      proofs: async () => (await loadStatus())?.proofs ?? [],
      proof: loadProof,
      signatures: loadSignatures,
      reach: (site) => loadReach(site).catch(() => null),
      header: (height) => explorerHeader(height),
      publicKey: __ML_DSA_PUBLIC_KEY__,
    }),
    [provider, wallet],
  );
}
