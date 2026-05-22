export function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function escAttr(s: unknown): string {
  return String(s ?? '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function escLines(s: unknown): string {
  return esc(s).replace(/\n/g, '<br>');
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 40);
  }
}

export function shortAddr(addr: string | undefined): string {
  if (!addr || addr.length < 10) return addr ?? '';
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

export function formatEth(wei: bigint): string {
  const eth = Number(wei) / 1e18;
  return `${eth.toFixed(4)} ETH`;
}

export function formatUsdc(raw: bigint): string {
  const amount = Number(raw) / 1e6;
  return `${amount.toFixed(4)} USDC`;
}
