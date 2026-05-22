const DEFAULT_BUFFER_SEC = 600;
const DEFAULT_VALIDITY_SEC = 3600;

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

export interface PaymentAccept {
  scheme?: string;
  network?: string;
  payTo: string;
  amount: string;
  asset: string;
  maxTimeoutSeconds?: number;
  extra?: { name?: string; version?: string };
}

export interface PaymentRequired {
  accepts: PaymentAccept[];
  resource?: unknown;
}

export interface PaymentSummary {
  amount: string;
  amountAtomic: string;
  token: string;
  tokenAddress: string;
  network: string;
  networkCaip: string;
  recipient: string;
  scheme: string;
  raw: PaymentAccept;
}

function randomNonce(): `0x${string}` {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `0x${hex}`;
}

function validityWindow(maxTimeoutSeconds?: number) {
  const now = Math.floor(Date.now() / 1000);
  const duration = maxTimeoutSeconds && maxTimeoutSeconds > 0
    ? maxTimeoutSeconds
    : DEFAULT_VALIDITY_SEC;
  return {
    validAfter: String(now - DEFAULT_BUFFER_SEC),
    validBefore: String(now + duration),
  };
}

export function pickAccept(paymentRequired: PaymentRequired): PaymentAccept {
  const accepts = paymentRequired?.accepts;
  if (!accepts?.length) throw new Error('No payment requirements in PAYMENT-REQUIRED');
  return accepts[0];
}

export function formatPaymentSummary(paymentRequired: PaymentRequired): PaymentSummary {
  const req = pickAccept(paymentRequired);
  const extra = req.extra ?? {};
  const decimals = 6;
  let amountHuman = req.amount;
  try {
    const atomic = BigInt(req.amount);
    amountHuman = (Number(atomic) / 10 ** decimals).toFixed(6).replace(/\.?0+$/, '');
  } catch {
    /* keep atomic */
  }

  const network = req.network ?? 'eip155:84532';
  const networkLabel = network.includes('84532') ? 'Base Sepolia' : network;

  return {
    amount: amountHuman,
    amountAtomic: req.amount,
    token: extra.name ?? 'USDC',
    tokenAddress: req.asset,
    network: networkLabel,
    networkCaip: network,
    recipient: req.payTo,
    scheme: req.scheme ?? 'exact',
    raw: req,
  };
}

export interface SignPaymentResult {
  headers: { 'PAYMENT-SIGNATURE': string };
  payload: unknown;
  summary: PaymentSummary;
}

export interface X402Signer {
  getAddress(): Promise<string>;
  signTypedData(params: {
    domain: Record<string, unknown>;
    types: typeof EIP712_TYPES;
    primaryType: 'TransferWithAuthorization';
    message: Record<string, bigint | string>;
  }): Promise<string>;
}

export async function signPaymentPayload(
  paymentRequired: PaymentRequired,
  signer: X402Signer,
  chainId = 84532,
): Promise<SignPaymentResult> {
  const selected = pickAccept(paymentRequired);
  const extra = selected.extra ?? {};
  const tokenName = extra.name ?? 'USDC';
  const tokenVersion = extra.version ?? '2';

  const from = await signer.getAddress();
  const { validAfter, validBefore } = validityWindow(selected.maxTimeoutSeconds);
  const nonce = randomNonce();

  const domain = {
    name: tokenName,
    version: tokenVersion,
    chainId,
    verifyingContract: selected.asset as `0x${string}`,
  };

  const message = {
    from: from as `0x${string}`,
    to: selected.payTo as `0x${string}`,
    value: BigInt(selected.amount),
    validAfter: BigInt(validAfter),
    validBefore: BigInt(validBefore),
    nonce,
  };

  const signature = await signer.signTypedData({
    domain,
    types: EIP712_TYPES,
    primaryType: 'TransferWithAuthorization',
    message,
  });

  const innerPayload = {
    authorization: {
      from,
      to: selected.payTo,
      value: String(selected.amount),
      validAfter,
      validBefore,
      nonce,
    },
    signature,
  };

  const fullPayload = {
    x402Version: 2,
    payload: innerPayload,
    accepted: selected,
    resource: paymentRequired.resource ?? null,
  };

  const json = JSON.stringify(fullPayload);
  const b64 = btoa(unescape(encodeURIComponent(json)));

  return {
    headers: { 'PAYMENT-SIGNATURE': b64 },
    payload: fullPayload,
    summary: formatPaymentSummary(paymentRequired),
  };
}

export function decodePaymentRequiredHeader(res: Response): PaymentRequired | null {
  const raw = res.headers.get('PAYMENT-REQUIRED') ?? res.headers.get('payment-required');
  if (!raw) return null;
  try {
    return JSON.parse(atob(raw.trim())) as PaymentRequired;
  } catch {
    return null;
  }
}

export function decodePaymentRequiredFromB64(b64: string): PaymentRequired | null {
  if (!b64) return null;
  try {
    return JSON.parse(atob(b64.trim())) as PaymentRequired;
  } catch {
    return null;
  }
}

export function getPaymentRequiredRaw(res: Response): string {
  return res.headers.get('PAYMENT-REQUIRED') ?? res.headers.get('payment-required') ?? '';
}

export function decodePaymentResponseHeader(headerValue: string): unknown {
  if (!headerValue) return null;
  try {
    const json = decodeURIComponent(escape(atob(headerValue.trim())));
    return JSON.parse(json);
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e), raw: headerValue.slice(0, 120) };
  }
}

export function showFacilitatorWarning(res: Response): string | null {
  return res.headers.get('X402-Facilitator-Warning')
    ?? res.headers.get('x402-facilitator-warning');
}
