'use strict';

/**
 * MetaMask wallet — Base Sepolia only.
 */
(function (global) {
  const BASE_SEPOLIA = {
    chainId:         '0x14a34',
    chainIdDec:      84532,
    chainName:       'Base Sepolia',
    rpcUrls:         ['https://sepolia.base.org'],
    blockExplorerUrls: ['https://sepolia.basescan.org'],
    nativeCurrency:  { name: 'Ether', symbol: 'ETH', decimals: 18 },
  };

  const USDC_ADDRESS = '0x036CbD53842c5426634e7929541eC2318f3dCF7e';
  const USDC_DECIMALS = 6;
  const ERC20_ABI = [
    'function balanceOf(address owner) view returns (uint256)',
    'function decimals() view returns (uint8)',
  ];

  let _provider = null;
  let _signer = null;
  let _address = null;
  let _status = 'disconnected'; // disconnected | connected | wrong_network

  function hasMetaMask() {
    return typeof global.ethereum !== 'undefined';
  }

  function shortAddr(addr) {
    if (!addr || addr.length < 10) return addr || '';
    return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
  }

  function formatEth(wei) {
    try {
      return `${Number.parseFloat(global.ethers.formatEther(wei)).toFixed(4)} ETH`;
    } catch (_) {
      return '—';
    }
  }

  function formatUsdc(raw) {
    try {
      return `${Number.parseFloat(global.ethers.formatUnits(raw, USDC_DECIMALS)).toFixed(4)} USDC`;
    } catch (_) {
      return '—';
    }
  }

  async function getChainIdHex() {
    return global.ethereum.request({ method: 'eth_chainId' });
  }

  async function ensureBaseSepolia() {
    if (!hasMetaMask()) throw new Error('MetaMask not installed');
    const current = await getChainIdHex();
    if (current === BASE_SEPOLIA.chainId) {
      _status = 'connected';
      return;
    }
    try {
      await global.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params:  [{ chainId: BASE_SEPOLIA.chainId }],
      });
    } catch (err) {
      if (err?.code === 4902) {
        await global.ethereum.request({
          method: 'wallet_addEthereumChain',
          params:  [BASE_SEPOLIA],
        });
      } else {
        throw err;
      }
    }
    _status = 'connected';
  }

  async function connect() {
    if (!hasMetaMask()) throw new Error('Install MetaMask to use Premium payments');
    const accounts = await global.ethereum.request({ method: 'eth_requestAccounts' });
    if (!accounts?.length) throw new Error('No account selected');
    _address = accounts[0];
    await ensureBaseSepolia();
    _provider = new global.ethers.BrowserProvider(global.ethereum);
    _signer = await _provider.getSigner();
    _status = 'connected';
    return _address;
  }

  async function refreshBalances() {
    if (!_provider || !_address) return { eth: '—', usdc: '—' };
    const ethWei = await _provider.getBalance(_address);
    const usdc = new global.ethers.Contract(USDC_ADDRESS, ERC20_ABI, _provider);
    const usdcRaw = await usdc.balanceOf(_address);
    return {
      eth:  formatEth(ethWei),
      usdc: formatUsdc(usdcRaw),
    };
  }

  async function syncNetworkStatus() {
    if (!_address) {
      _status = 'disconnected';
      return _status;
    }
    try {
      const cid = await getChainIdHex();
      _status = cid === BASE_SEPOLIA.chainId ? 'connected' : 'wrong_network';
    } catch (_) {
      _status = 'disconnected';
    }
    return _status;
  }

  function isConnected() {
    return _status === 'connected' && !!_address && !!_signer;
  }

  function getSigner() {
    if (!_signer) throw new Error('Wallet not connected');
    return _signer;
  }

  function getAddress() {
    return _address;
  }

  function getStatus() {
    return _status;
  }

  function getNetworkLabel() {
    return BASE_SEPOLIA.chainName;
  }

  function onAccountsChanged(handler) {
    if (!global.ethereum) return;
    global.ethereum.on('accountsChanged', handler);
  }

  function onChainChanged(handler) {
    if (!global.ethereum) return;
    global.ethereum.on('chainChanged', handler);
  }

  global.CryptoWallet = {
    BASE_SEPOLIA,
    USDC_ADDRESS,
    hasMetaMask,
    shortAddr,
    connect,
    ensureBaseSepolia,
    refreshBalances,
    syncNetworkStatus,
    isConnected,
    getSigner,
    getAddress,
    getStatus,
    getNetworkLabel,
    onAccountsChanged,
    onChainChanged,
  };
})(window);
