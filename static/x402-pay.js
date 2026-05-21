'use strict';

/**
 * Browser x402 EIP-3009 signing (MetaMask) — no server private key.
 */
(function (global) {
  const DEFAULT_BUFFER_SEC = 600;
  const DEFAULT_VALIDITY_SEC = 3600;

  const EIP712_TYPES = {
    TransferWithAuthorization: [
      { name: 'from',         type: 'address' },
      { name: 'to',           type: 'address' },
      { name: 'value',        type: 'uint256' },
      { name: 'validAfter',   type: 'uint256' },
      { name: 'validBefore',  type: 'uint256' },
      { name: 'nonce',        type: 'bytes32' },
    ],
  };

  function randomNonce() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return '0x' + Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  }

  function validityWindow(maxTimeoutSeconds) {
    const now = Math.floor(Date.now() / 1000);
    const duration = maxTimeoutSeconds > 0 ? maxTimeoutSeconds : DEFAULT_VALIDITY_SEC;
    return {
      validAfter:  String(now - DEFAULT_BUFFER_SEC),
      validBefore: String(now + duration),
    };
  }

  function pickAccept(paymentRequired) {
    const accepts = paymentRequired?.accepts;
    if (!accepts?.length) throw new Error('No payment requirements in PAYMENT-REQUIRED');
    return accepts[0];
  }

  function formatPaymentSummary(paymentRequired) {
    const req = pickAccept(paymentRequired);
    const extra = req.extra || {};
    const decimals = extra.name === 'USDC' ? 6 : 6;
    let amountHuman = req.amount;
    try {
      amountHuman = global.ethers.formatUnits(req.amount, decimals);
    } catch (_) { /* keep atomic */ }

    const network = req.network || 'eip155:84532';
    const networkLabel = network.includes('84532') ? 'Base Sepolia' : network;

    return {
      amount:       amountHuman,
      amountAtomic: req.amount,
      token:        extra.name || 'USDC',
      tokenAddress: req.asset,
      network:      networkLabel,
      networkCaip:  network,
      recipient:    req.payTo,
      scheme:       req.scheme || 'exact',
      raw:          req,
    };
  }

  async function signPaymentPayload(paymentRequired, signer) {
    const selected = pickAccept(paymentRequired);
    const extra = selected.extra || {};
    const tokenName = extra.name || 'USDC';
    const tokenVersion = extra.version || '2';
    const chainId = global.CryptoWallet?.BASE_SEPOLIA?.chainIdDec ?? 84532;

    const from = await signer.getAddress();
    const { validAfter, validBefore } = validityWindow(selected.maxTimeoutSeconds);
    const nonce = randomNonce();

    const domain = {
      name:              tokenName,
      version:           tokenVersion,
      chainId,
      verifyingContract: selected.asset,
    };

    const message = {
      from,
      to:          selected.payTo,
      value:       BigInt(selected.amount),
      validAfter:  BigInt(validAfter),
      validBefore: BigInt(validBefore),
      nonce,
    };

    const signature = await signer.signTypedData(domain, EIP712_TYPES, message);

    const innerPayload = {
      authorization: {
        from,
        to:          selected.payTo,
        value:       String(selected.amount),
        validAfter,
        validBefore,
        nonce,
      },
      signature,
    };

    const fullPayload = {
      x402Version: 2,
      payload:     innerPayload,
      accepted:    selected,
      resource:    paymentRequired.resource ?? null,
    };

    const json = JSON.stringify(fullPayload);
    const b64 = btoa(unescape(encodeURIComponent(json)));

    return {
      headers: { 'PAYMENT-SIGNATURE': b64 },
      payload: fullPayload,
      summary: formatPaymentSummary(paymentRequired),
    };
  }

  function decodePaymentResponseHeader(headerValue) {
    if (!headerValue) return null;
    try {
      const json = decodeURIComponent(escape(atob(headerValue.trim())));
      return JSON.parse(json);
    } catch (e) {
      return { error: e.message, raw: headerValue.slice(0, 120) };
    }
  }

  global.X402Pay = {
    formatPaymentSummary,
    signPaymentPayload,
    decodePaymentResponseHeader,
  };
})(window);
