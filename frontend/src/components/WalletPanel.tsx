import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount, useBalance, useReadContract } from 'wagmi';
import { formatUnits } from 'viem';

import { BASE_SEPOLIA, ERC20_BALANCE_ABI, USDC_ADDRESS } from '../config/chains';
import { formatEth, shortAddr } from '../lib/utils';

export function WalletPanel() {
  const { address, isConnected, connector, chain } = useAccount();

  const { data: ethBalance } = useBalance({
    address,
    chainId: BASE_SEPOLIA.id,
    query: { enabled: !!address },
  });

  const { data: usdcRaw } = useReadContract({
    address: USDC_ADDRESS,
    abi: ERC20_BALANCE_ABI,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
    chainId: BASE_SEPOLIA.id,
    query: { enabled: !!address },
  });

  const wrongNetwork = isConnected && chain?.id !== BASE_SEPOLIA.id;
  const status = !isConnected ? 'disconnected' : wrongNetwork ? 'wrong_network' : 'connected';

  const ethLabel = ethBalance ? formatEth(ethBalance.value) : '—';
  const usdcLabel = usdcRaw != null
    ? `${Number(formatUnits(usdcRaw, 6)).toFixed(4)} USDC`
    : '—';

  const walletName = connector?.name ?? 'Wallet';

  return (
    <div className="wallet-panel">
      <ConnectButton.Custom>
        {({ openConnectModal, mounted }) => {
          if (!mounted) return null;
          if (!isConnected) {
            return (
              <button type="button" className="btn-wallet" onClick={openConnectModal}>
                Connect Wallet
              </button>
            );
          }
          return null;
        }}
      </ConnectButton.Custom>

      {isConnected && (
        <div className="wallet-connected">
          <div className="wallet-row">
            <span
              className={`wallet-status-dot ${
                status === 'connected' ? 'is-ok' : status === 'wrong_network' ? 'is-warn' : 'is-err'
              }`}
              title="Connection status"
            />
            <span className="wallet-address">{shortAddr(address)}</span>
            <span className="wallet-meta-item wallet-name-tag">{walletName}</span>
          </div>
          <div className="wallet-meta">
            <span className="wallet-meta-item">
              {wrongNetwork ? `Wrong chain (${chain?.name ?? '?'})` : BASE_SEPOLIA.name}
            </span>
            <span className="wallet-meta-item">{ethLabel}</span>
            <span className="wallet-meta-item">{usdcLabel}</span>
          </div>
          <span className="wallet-status-text">
            {status === 'connected'
              ? 'Connected'
              : status === 'wrong_network'
                ? 'Switch to Base Sepolia'
                : 'Disconnected'}
          </span>
          {wrongNetwork && (
            <ConnectButton.Custom>
              {({ openChainModal }) => (
                <button type="button" className="btn-wallet btn-wallet--switch" onClick={openChainModal}>
                  Switch network
                </button>
              )}
            </ConnectButton.Custom>
          )}
        </div>
      )}
    </div>
  );
}
