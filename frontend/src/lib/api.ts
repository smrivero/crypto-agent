export const API = {
  stream: '/api/v1/research/stream',
  research: '/api/v1/research',
  logs: '/api/v1/logs',
  graph: '/api/v1/graph/mermaid',
  premiumDemo: '/api/v1/premium-demo',
  devSign: '/api/v1/x402/dev-sign',
} as const;

export const FACILITATOR_STORAGE_KEY = 'x402FacilitatorMode';

export type FacilitatorMode = 'public' | 'coinbase';

export function getFacilitatorMode(): FacilitatorMode {
  const stored = localStorage.getItem(FACILITATOR_STORAGE_KEY);
  return stored === 'coinbase' ? 'coinbase' : 'public';
}

export function facilitatorRequestHeaders(
  extra: Record<string, string> = {},
): Record<string, string> {
  return {
    'X402-Facilitator-Mode': getFacilitatorMode(),
    ...extra,
  };
}

export const NODES_PREMIUM = [
  'payment',
  'classify',
  'search',
  'technical_token_analysis',
  'aggregate',
  'analyze',
] as const;

export const NODES_FREE = ['classify', 'search', 'analyze'] as const;

export const NODE_LABELS: Record<string, string> = {
  payment: 'x402 payment',
  classify: 'Classifying request',
  search: 'Searching the web',
  technical_token_analysis: 'Fetching on-chain data',
  aggregate: 'Aggregating content',
  analyze: 'Generating analysis',
};

export const MODEL_OPTIONS = [
  'gpt-5.5',
  'gpt-5.4',
  'gpt-5.4-mini',
  'gpt-4o',
  'gpt-4o-mini',
] as const;
