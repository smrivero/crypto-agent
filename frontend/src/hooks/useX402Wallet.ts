import { useCallback } from 'react';
import { useSwitchChain, useWalletClient } from 'wagmi';
import type { WalletClient } from 'viem';

import { BASE_SEPOLIA_CHAIN_ID } from '../config/chains';

const EIP712_TYPES = {
  TransferWithAuthorization: [
    { name: 'from', type: 'address' },
    { name: 'to', type: 'address' },
    { name: 'value', type: 'uint256' },
    { name: 'validAfter', type: 'uint256' },
    { name: 'validBefore', type: 'uint256' },
    { name: 'nonce', type: 'bytes32' },
  ],
} as const;

function walletClientToSigner(client: WalletClient) {
  if (!client.account) {
    throw new Error('Wallet account unavailable');
  }

  return {
    getAddress: async () => client.account!.address,
    signTypedData: async (params: {
      domain: Record<string, unknown>;
      message: Record<string, bigint | string>;
    }) => {
      if (!client.account) throw new Error('Wallet account unavailable');
      return client.signTypedData({
        account: client.account,
        domain: params.domain as never,
        types: EIP712_TYPES,
        primaryType: 'TransferWithAuthorization',
        message: params.message as never,
      });
    },
  };
}

export function useX402Wallet() {
  const { data: walletClient } = useWalletClient();
  const { switchChainAsync } = useSwitchChain();

  const ensureBaseSepolia = useCallback(async () => {
    await switchChainAsync({ chainId: BASE_SEPOLIA_CHAIN_ID });
  }, [switchChainAsync]);

  const getSigner = useCallback(() => {
    if (!walletClient) throw new Error('Wallet not connected');
    return walletClientToSigner(walletClient);
  }, [walletClient]);

  return { ensureBaseSepolia, getSigner, walletClient };
}
