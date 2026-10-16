// ethers v6 on top of wagmi's viem clients (D11), as wagmi's Ethers.js adapters guide documents
// (https://wagmi.sh/react/guides/ethers): a read-only provider from the configured transport and a
// signer from the connected wallet.
import { BrowserProvider, FallbackProvider, JsonRpcProvider, JsonRpcSigner } from "ethers";
import { useMemo } from "react";
import type { Account, Chain, Client, Transport } from "viem";
import { type Config, useClient, useConnectorClient } from "wagmi";

/**
 * A viem client as an ethers provider.
 *
 * @param client - The client (its chain and transport).
 * @returns A JSON-RPC provider, or a fallback over several.
 */
export function clientToProvider(
  client: Client<Transport, Chain>,
): JsonRpcProvider | FallbackProvider {
  const { chain, transport } = client;
  const network = {
    chainId: chain.id,
    name: chain.name,
    ensAddress: chain.contracts?.ensRegistry?.address,
  };
  if (transport.type === "fallback") {
    const providers = (transport.transports as ReturnType<Transport>[]).map(
      ({ value }) => new JsonRpcProvider(value?.url as string | undefined, network),
    );
    const [only] = providers;
    if (providers.length === 1 && only !== undefined) {
      return only;
    }
    return new FallbackProvider(providers);
  }
  return new JsonRpcProvider(transport.url as string | undefined, network);
}

/**
 * The configured chain's read-only ethers provider (no wallet needed).
 *
 * @param options - The options.
 * @param options.chainId - The chain (default: the config's).
 * @returns The provider, or undefined before wagmi has a client.
 */
export function useEthersProvider({ chainId }: { chainId?: number } = {}):
  JsonRpcProvider | FallbackProvider | undefined {
  const client = useClient<Config>({ chainId });
  return useMemo(() => (client === undefined ? undefined : clientToProvider(client)), [client]);
}

/**
 * A connected wallet's viem client as an ethers signer.
 *
 * @param client - The connector client (its account, chain and transport).
 * @returns The signer.
 */
export function clientToSigner(client: Client<Transport, Chain, Account>): JsonRpcSigner {
  const { account, chain, transport } = client;
  const network = {
    chainId: chain.id,
    name: chain.name,
    ensAddress: chain.contracts?.ensRegistry?.address,
  };
  const provider = new BrowserProvider(transport, network);
  return new JsonRpcSigner(provider, account.address);
}

/**
 * The connected wallet's ethers signer.
 *
 * @param options - The options.
 * @param options.chainId - The chain (default: the config's).
 * @returns The signer, or undefined without a connected wallet.
 */
export function useEthersSigner({ chainId }: { chainId?: number } = {}): JsonRpcSigner | undefined {
  const { data: client } = useConnectorClient<Config>({ chainId });
  return useMemo(() => (client === undefined ? undefined : clientToSigner(client)), [client]);
}
