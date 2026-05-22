import { getDefaultConfig } from '@rainbow-me/rainbowkit';
import {
  coinbaseWallet,
  metaMaskWallet,
  rabbyWallet,
  walletConnectWallet,
} from '@rainbow-me/rainbowkit/wallets';

import { BASE_SEPOLIA } from './chains';

const projectId =
  import.meta.env.VITE_WALLETCONNECT_PROJECT_ID?.trim() ||
  '00000000000000000000000000000000';

export const wagmiConfig = getDefaultConfig({
  appName: 'Crypto Research Agent',
  projectId,
  chains: [BASE_SEPOLIA],
  wallets: [
    {
      groupName: 'Connect',
      wallets: [metaMaskWallet, coinbaseWallet, rabbyWallet, walletConnectWallet],
    },
  ],
  ssr: false,
});
