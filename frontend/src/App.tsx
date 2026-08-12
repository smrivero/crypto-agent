import { useCallback, useEffect, useRef, useState } from 'react';
import { useConnectModal } from '@rainbow-me/rainbowkit';
import { useAccount } from 'wagmi';

import { GraphSection } from './components/GraphSection';
import { PaymentModal } from './components/PaymentModal';
import { RequestLog } from './components/RequestLog';
import { ResultsSection } from './components/ResultsSection';
import { StepsCard } from './components/StepsCard';
import { ThemeSwitch } from './components/ThemeSwitch';
import { WalletPanel } from './components/WalletPanel';
import { BASE_SEPOLIA_CHAIN_ID } from './config/chains';
import { useX402Wallet } from './hooks/useX402Wallet';
import {
  API,
  FACILITATOR_STORAGE_KEY,
  MODEL_OPTIONS,
  NODES_FREE,
  NODES_PREMIUM,
  facilitatorRequestHeaders,
  getFacilitatorMode,
} from './lib/api';
import type {
  ExecLogEntry,
  LogEntry,
  PaymentLogEntry,
  ResearchResponse,
  StepRow,
  StreamEvent,
  X402DebugState,
} from './lib/types';
import {
  decodePaymentRequiredFromB64,
  decodePaymentRequiredHeader,
  decodePaymentResponseHeader,
  getPaymentRequiredRaw,
  showFacilitatorWarning,
  signPaymentPayload,
  type PaymentRequired,
} from './lib/x402';
import { Web3Provider } from './providers/Web3Provider';
import { LoginScreen } from './components/LoginScreen';

type ResearchMode = 'free' | 'premium';

function initSteps(mode: ResearchMode): StepRow[] {
  const nodes = mode === 'premium' ? NODES_PREMIUM : NODES_FREE;
  return nodes.map((node) => ({ node, state: 'pending' as const }));
}

function applyStreamEvent(steps: StepRow[], ev: StreamEvent): StepRow[] {
  const next = steps.map((s) => ({ ...s }));
  const idx = (node: string) => next.findIndex((s) => s.node === node);

  switch (ev.type) {
    case 'step_start': {
      const i = idx(ev.node ?? '');
      if (i >= 0) next[i] = { ...next[i], state: 'active' };
      break;
    }
    case 'step_end': {
      const i = idx(ev.node ?? '');
      if (i >= 0) next[i] = { ...next[i], state: 'done', detail: ev.detail ?? '' };
      break;
    }
    case 'step_error': {
      const i = idx(ev.node ?? '');
      if (i >= 0) next[i] = { ...next[i], state: 'error', detail: ev.detail ?? '' };
      break;
    }
    case 'step_skip': {
      const i = idx(ev.node ?? '');
      if (i >= 0) next[i] = { ...next[i], state: 'skipped', detail: ev.detail ?? '' };
      break;
    }
    default:
      break;
  }
  return next;
}

function markRemainingSkipped(steps: StepRow[], exceptNode?: string): StepRow[] {
  return steps.map((s) => {
    if (s.node === exceptNode) return s;
    if (s.state === 'pending' || s.state === 'active') {
      return { ...s, state: 'skipped' as const };
    }
    return s;
  });
}

function markPaymentCancelled(steps: StepRow[]): StepRow[] {
  return steps.map((s) => {
    if (s.node === 'payment') {
      return { ...s, state: 'error' as const, detail: 'Payment cancelled' };
    }
    if (s.state === 'pending' || s.state === 'active') {
      return { ...s, state: 'skipped' as const };
    }
    return s;
  });
}

function walletErrorMessage(e: unknown): string {
  const err = e as { code?: number; message?: string; shortMessage?: string };
  const text = `${err?.message ?? ''} ${err?.shortMessage ?? ''}`.toLowerCase();
  if (err?.code === 4001 || /reject|denied|cancel|declined/.test(text)) {
    return 'Payment cancelled in wallet';
  }
  return e instanceof Error ? e.message : String(e);
}

function AppContent({ theme, onToggleTheme }: { theme: 'light' | 'dark'; onToggleTheme: () => void }) {
  const { isConnected, chain } = useAccount();
  const { openConnectModal } = useConnectModal();
  const { ensureBaseSepolia, getSigner } = useX402Wallet();

  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<ResearchMode>('free');
  const [model, setModel] = useState('gpt-5.4-mini');
  const [facilitatorMode, setFacilitatorMode] = useState(getFacilitatorMode());
  const [loading, setLoading] = useState(false);

  const [stepsVisible, setStepsVisible] = useState(false);
  const [stepsStatus, setStepsStatus] = useState('');
  const [steps, setSteps] = useState<StepRow[]>([]);
  const [paymentLogs, setPaymentLogs] = useState<PaymentLogEntry[]>([]);
  const [execLogs, setExecLogs] = useState<ExecLogEntry[]>([]);
  const [x402Debug, setX402Debug] = useState<X402DebugState>({
    status: 'idle',
    required: null,
    response: null,
    txHash: null,
    lastError: null,
  });

  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [paymentModal, setPaymentModal] = useState<{
    open: boolean;
    paymentRequired: PaymentRequired | null;
    signing: boolean;
  }>({ open: false, paymentRequired: null, signing: false });

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [mermaidText, setMermaidText] = useState<string | null>(null);

  const runStartRef = useRef<number | null>(null);
  const paymentModalResolver = useRef<((headers: Record<string, string> | null) => void) | null>(null);

  const elapsed = useCallback(() => {
    if (!runStartRef.current) return '';
    return `${((Date.now() - runStartRef.current) / 1000).toFixed(2)}s`;
  }, []);

  const appendPaymentLog = useCallback((
    step: string,
    message: string,
    status = 'info',
    detail = '',
  ) => {
    setPaymentLogs((prev) => [...prev, { step, message, status, detail, elapsed: elapsed() }]);
  }, [elapsed]);

  const appendExecLog = useCallback((level: string, message: string) => {
    setExecLogs((prev) => [...prev, { level, message, elapsed: elapsed() }]);
  }, [elapsed]);

  const loadLogs = useCallback(async () => {
    try {
      const res = await fetch(API.logs);
      if (res.ok) setLogs(await res.json());
    } catch {
      /* ignore */
    }
  }, []);

  const loadGraph = useCallback(async () => {
    try {
      const res = await fetch(API.graph);
      if (res.ok) {
        const data = await res.json();
        setMermaidText(data.mermaid ?? null);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadLogs();
    loadGraph();
    const id = setInterval(loadLogs, 30_000);
    return () => clearInterval(id);
  }, [loadLogs, loadGraph]);

  useEffect(() => {
    document.body.classList.toggle('modal-open', paymentModal.open);
  }, [paymentModal.open]);

  const ensureWalletReady = useCallback(async (): Promise<boolean> => {
    if (!isConnected) {
      openConnectModal?.();
      return false;
    }
    if (chain?.id !== BASE_SEPOLIA_CHAIN_ID) {
      await ensureBaseSepolia();
    }
    return true;
  }, [isConnected, chain?.id, openConnectModal, ensureBaseSepolia]);

  const handleModeChange = useCallback((next: ResearchMode) => {
    setMode(next);
    if (next === 'premium' && !isConnected) {
      openConnectModal?.();
    }
  }, [isConnected, openConnectModal]);

  const promptPaymentSignature = useCallback((paymentRequired: PaymentRequired) => {
    return new Promise<Record<string, string> | null>((resolve) => {
      paymentModalResolver.current = resolve;
      setPaymentModal({ open: true, paymentRequired, signing: false });
    });
  }, []);

  const handlePaymentSign = useCallback(async () => {
    if (!paymentModal.paymentRequired) return;
    setPaymentModal((m) => ({ ...m, signing: true }));
    try {
      if (!(await ensureWalletReady())) {
        setPaymentModal((m) => ({ ...m, signing: false }));
        return;
      }
      const signed = await signPaymentPayload(
        paymentModal.paymentRequired,
        getSigner(),
        BASE_SEPOLIA_CHAIN_ID,
      );
      setPaymentModal({ open: false, paymentRequired: null, signing: false });
      paymentModalResolver.current?.(signed.headers);
      paymentModalResolver.current = null;
    } catch (e) {
      const msg = walletErrorMessage(e);
      setX402Debug((d) => ({ ...d, lastError: msg, status: 'cancelled' }));
      setPaymentModal({ open: false, paymentRequired: null, signing: false });
      paymentModalResolver.current?.(null);
      paymentModalResolver.current = null;
    }
  }, [paymentModal.paymentRequired, ensureWalletReady, getSigner]);

  const handlePaymentClose = useCallback(() => {
    setPaymentModal({ open: false, paymentRequired: null, signing: false });
    paymentModalResolver.current?.(null);
    paymentModalResolver.current = null;
  }, []);

  const consumeSSEStream = useCallback(async (res: Response) => {
    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') return;

        try {
          const ev = JSON.parse(raw) as StreamEvent;
          if (ev.type === 'log') {
            appendExecLog(ev.level ?? 'info', ev.message ?? '');
          } else if (ev.type === 'payment_log') {
            appendPaymentLog(ev.step ?? 'payment', ev.message ?? '', ev.status ?? 'info', ev.detail ?? '');
          } else if (ev.type === 'result' && ev.data) {
            setResult(ev.data);
            setStepsStatus(`Done · ${ev.data.processing_time_ms} ms`);
          } else if (ev.type === 'error') {
            setError(ev.message ?? 'Stream error');
            setStepsStatus('Failed');
            setSteps((s) => markRemainingSkipped(s));
          } else if (ev.type === 'step_start') {
            setStepsStatus(`${ev.label ?? ev.node}…`);
            setSteps((s) => applyStreamEvent(s, ev));
          } else if (['step_end', 'step_error', 'step_skip'].includes(ev.type)) {
            setSteps((s) => applyStreamEvent(s, ev));
            if (ev.type === 'step_error') {
              setStepsStatus(`Error in ${ev.label ?? ev.node}`);
              setSteps((s) => markRemainingSkipped(s));
            }
          }
        } catch {
          /* skip */
        }
      }
    }
  }, [appendExecLog, appendPaymentLog]);

  const runPremiumStreamAfterPayment = useCallback(async (
    q: string,
    m: string,
    payHeaders: Record<string, string>,
  ) => {
    setSteps(initSteps('premium'));
    setX402Debug((d) => ({ ...d, status: 'streaming' }));

    const res = await fetch(API.stream, {
      method: 'POST',
      headers: facilitatorRequestHeaders({
        'Content-Type': 'application/json',
        ...payHeaders,
      }),
      body: JSON.stringify({ query: q, model: m, mode: 'premium' }),
    });

    const warn = showFacilitatorWarning(res);
    if (warn) appendPaymentLog('facilitator', warn, 'warn');

    const settleHdr = res.headers.get('PAYMENT-RESPONSE') ?? res.headers.get('payment-response');
    if (settleHdr) {
      setX402Debug((d) => ({ ...d, response: decodePaymentResponseHeader(settleHdr) }));
    }

    if (res.status === 402) {
      setStepsStatus('Payment required');
      setSteps((s) => markRemainingSkipped(s, 'payment'));
      setError('Payment verification failed (402)');
      return;
    }

    if (!res.ok) {
      setError(`Server error ${res.status}: ${await res.text()}`);
      setSteps((s) => markRemainingSkipped(s));
      return;
    }

    await consumeSSEStream(res);
    setX402Debug((d) => ({ ...d, status: 'done' }));
  }, [appendPaymentLog, consumeSSEStream]);

  const runPremiumResearch = useCallback(async (q: string, m: string) => {
    if (!(await ensureWalletReady())) {
      return;
    }

    setX402Debug({ status: 'probing', required: null, response: null, txHash: null, lastError: null });
    setResult(null);
    setError(null);
    setStepsVisible(true);
    setSteps(initSteps('premium'));
    setPaymentLogs([]);
    setExecLogs([]);
    runStartRef.current = Date.now();
    setStepsStatus('Premium · Running…');
    appendPaymentLog('probe', 'POST /api/v1/research', 'info');

    const probe = await fetch(API.research, {
      method: 'POST',
      headers: facilitatorRequestHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ query: q, model: m, mode: 'premium' }),
    });

    const warn = showFacilitatorWarning(probe);
    if (warn) appendPaymentLog('facilitator', warn, 'warn');

    let payHeaders: Record<string, string> = {};

    if (probe.status === 402) {
      const decoded = decodePaymentRequiredHeader(probe)
        ?? decodePaymentRequiredFromB64(getPaymentRequiredRaw(probe));
      if (!decoded) throw new Error('Could not decode PAYMENT-REQUIRED');

      setX402Debug((d) => ({ ...d, required: decoded, status: 'payment_required' }));
      appendPaymentLog('402', 'HTTP 402 — payment required', 'warn');
      setStepsStatus('Payment required — confirm in dialog');
      setSteps((s) => {
        const next = [...s];
        const i = next.findIndex((x) => x.node === 'payment');
        if (i >= 0) next[i] = { ...next[i], state: 'active', detail: 'Confirm payment in modal' };
        return next;
      });

      const headers = await promptPaymentSignature(decoded);
      if (!headers) {
        setStepsStatus('Payment cancelled');
        setSteps((s) => markPaymentCancelled(s));
        appendPaymentLog('sign', 'Payment cancelled', 'warn');
        setX402Debug((d) => ({ ...d, status: 'cancelled' }));
        return;
      }
      payHeaders = headers;
      appendPaymentLog('sign', 'Wallet signature OK', 'ok');
      setX402Debug((d) => ({ ...d, status: 'signed' }));
    } else if (probe.ok) {
      const data = await probe.json() as ResearchResponse;
      if (data.success && data.report) {
        setResult(data);
        setStepsStatus(`Done · ${data.processing_time_ms} ms`);
        return;
      }
    } else {
      throw new Error(`Payment probe failed (${probe.status}): ${await probe.text()}`);
    }

    appendPaymentLog('stream', 'POST /api/v1/research/stream', 'info');
    await runPremiumStreamAfterPayment(q, m, payHeaders);
  }, [appendPaymentLog, ensureWalletReady, promptPaymentSignature, runPremiumStreamAfterPayment]);

  const runResearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      if (mode === 'premium') {
        await runPremiumResearch(q, model);
        return;
      }

      setStepsVisible(true);
      setSteps(initSteps('free'));
      setPaymentLogs([]);
      setExecLogs([]);
      runStartRef.current = Date.now();
      setStepsStatus('Free · Running…');

      const res = await fetch(API.stream, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, model, mode: 'free' }),
      });

      if (!res.ok) {
        setError(`Server error ${res.status}: ${await res.text()}`);
        setSteps((s) => markRemainingSkipped(s));
        return;
      }

      await consumeSSEStream(res);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setX402Debug((d) => ({ ...d, lastError: msg }));
      setError(msg);
    } finally {
      setLoading(false);
      loadLogs();
    }
  }, [query, mode, model, runPremiumResearch, consumeSSEStream, loadLogs]);

  const onFacilitatorChange = (value: string) => {
    const fm = value === 'coinbase' ? 'coinbase' : 'public';
    setFacilitatorMode(fm);
    localStorage.setItem(FACILITATOR_STORAGE_KEY, fm);
  };

  return (
    <>
      <div className="page-grid-bg" aria-hidden="true" />

      <header>
        <div className="header-inner header-inner--split">
          <div className="header-brand">
            <div className="logo-mark" aria-hidden="true">◈</div>
            <h1>Crypto Research Agent</h1>
            <p>AI-powered market analysis · LangGraph + LangChain</p>
          </div>
          <div className="header-tools">
            <ThemeSwitch theme={theme} onToggle={onToggleTheme} />
            <WalletPanel />
          </div>
        </div>
      </header>

      <main>
        <section className="card search-card">
          <label className="search-label" htmlFor="query-input">Research query</label>
          <textarea
            id="query-input"
            rows={2}
            placeholder="e.g.  Analyze DEXTF token  ·  Bitcoin fundamentals  ·  Sentiment on Solana"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void runResearch();
            }}
          />
          <div className="search-toolbar">
            <div className="search-toolbar-primary">
              <div className="mode-toggle" role="group" aria-label="Report tier">
                <label className="mode-option">
                  <input type="radio" name="research-mode" value="free" checked={mode === 'free'} onChange={() => handleModeChange('free')} />
                  <span>Free</span>
                </label>
                <label className="mode-option">
                  <input type="radio" name="research-mode" value="premium" checked={mode === 'premium'} onChange={() => handleModeChange('premium')} />
                  <span>Premium</span>
                </label>
              </div>

              {mode === 'premium' && (
                <div className="toolbar-field" title="x402 facilitator">
                  <span className="toolbar-field-label">Facilitator</span>
                  <select
                    id="facilitator-select"
                    className="toolbar-select"
                    value={facilitatorMode}
                    onChange={(e) => onFacilitatorChange(e.target.value)}
                  >
                    <option value="public">Public x402</option>
                    <option value="coinbase">Coinbase CDP</option>
                  </select>
                </div>
              )}

              <div className="toolbar-field">
                <label className="toolbar-field-label" htmlFor="model-select">Model</label>
                <select
                  id="model-select"
                  className="toolbar-select toolbar-select--model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                >
                  {MODEL_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="search-toolbar-actions">
              <span className="hint">Ctrl + Enter</span>
              {loading && (
                <span className="loading-inline">
                  <span className="dot-pulse" /> Running…
                </span>
              )}
              <button
                id="submit-btn"
                type="button"
                className="btn-analyze"
                onClick={() => void runResearch()}
                disabled={loading}
              >
                Analyze
              </button>
            </div>
          </div>
        </section>

        <StepsCard
          visible={stepsVisible}
          mode={mode}
          statusText={stepsStatus}
          steps={steps}
          paymentLogs={paymentLogs}
          execLogs={execLogs}
          x402Debug={x402Debug}
        />

        <div id="results-section">
          <ResultsSection data={result} error={error} />
        </div>

        <RequestLog logs={logs} onRefresh={() => void loadLogs()} />
        <GraphSection theme={theme} mermaidText={mermaidText} />
      </main>

      <PaymentModal
        open={paymentModal.open}
        title="Premium payment (x402)"
        hint="Review the payment, then confirm in your wallet to start the analysis."
        paymentRequired={paymentModal.paymentRequired}
        signing={paymentModal.signing}
        onClose={handlePaymentClose}
        onSign={() => void handlePaymentSign()}
      />
    </>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(() => sessionStorage.getItem('auth') === '1');

  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    return saved === 'dark' ? 'dark' : 'light';
  });

  const toggleTheme = () => {
    setTheme((t) => {
      const next = t === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      return next;
    });
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  if (!loggedIn) {
    return (
      <LoginScreen onLogin={() => { sessionStorage.setItem('auth', '1'); setLoggedIn(true); }} />
    );
  }

  return (
    <Web3Provider theme={theme}>
      <AppContent theme={theme} onToggleTheme={toggleTheme} />
    </Web3Provider>
  );
}
