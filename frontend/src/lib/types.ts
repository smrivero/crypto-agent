export interface LogEntry {
  timestamp: string;
  query: string;
  status: string;
  duration_ms: number;
  error?: string | null;
}

export interface TechnicalDetails {
  network: string;
  chain_id: number;
  contract_address: string;
  token_name: string;
  token_symbol: string;
  decimals: number;
  total_supply_formatted: string;
  holder_count?: number | null;
  warnings?: string[];
}

export interface CryptoReport {
  mode: 'free' | 'premium';
  token: string;
  summary: string;
  bullish_points: string[];
  bearish_points: string[];
  risks?: string[];
  confidence_score: number;
  sources?: string[];
  timestamp: string;
  classification?: string;
  technical_details?: TechnicalDetails | null;
}

export interface ResearchResponse {
  success: boolean;
  report?: CryptoReport | null;
  error?: string | null;
  processing_time_ms: number;
}

export type StepState = 'pending' | 'active' | 'done' | 'error' | 'skipped';

export interface StepRow {
  node: string;
  state: StepState;
  detail?: string;
}

export interface PaymentLogEntry {
  step: string;
  message: string;
  status: string;
  detail?: string;
  elapsed?: string;
}

export interface ExecLogEntry {
  level: string;
  message: string;
  elapsed?: string;
}

export interface X402DebugState {
  status: string;
  required: unknown;
  response: unknown;
  txHash: string | null;
  lastError: string | null;
}

export interface StreamEvent {
  type: string;
  node?: string;
  label?: string;
  detail?: string;
  message?: string;
  level?: string;
  step?: string;
  status?: string;
  data?: ResearchResponse;
}
