import type { ExecLogEntry, PaymentLogEntry, StepRow, X402DebugState } from '../lib/types';
import { NODE_LABELS } from '../lib/api';

interface StepsCardProps {
  visible: boolean;
  mode: 'free' | 'premium';
  statusText: string;
  steps: StepRow[];
  paymentLogs: PaymentLogEntry[];
  execLogs: ExecLogEntry[];
  x402Debug: X402DebugState;
}

function stepIcon(state: StepRow['state']): string {
  if (state === 'done') return '✓';
  if (state === 'error') return '✕';
  if (state === 'skipped') return '—';
  return '';
}

export function StepsCard({
  visible,
  mode,
  statusText,
  steps,
  paymentLogs,
  execLogs,
  x402Debug,
}: StepsCardProps) {
  if (!visible) return null;

  const debugJson = {
    status: x402Debug.status,
    paymentRequired: x402Debug.required,
    paymentResponse: x402Debug.response,
    transactionHash: x402Debug.txHash
      ?? (x402Debug.response as { transaction?: string; transactionHash?: string })?.transaction
      ?? (x402Debug.response as { transactionHash?: string })?.transactionHash
      ?? null,
    error: x402Debug.lastError,
  };

  return (
    <section className="card steps-card">
      <div className="section-header">
        <h2 className="tag-label">Agent pipeline</h2>
        <span className="tag-status">{statusText}</span>
      </div>
      <div>
        {steps.map((step) => (
          <div key={step.node} className={`step-row is-${step.state}`}>
            <div className="step-icon">{stepIcon(step.state)}</div>
            <div className="step-body">
              <div className="step-name">{NODE_LABELS[step.node] ?? step.node}</div>
              {step.detail ? <div className="step-detail">{step.detail}</div> : null}
            </div>
          </div>
        ))}
      </div>
      {mode === 'premium' && (
        <details className="payment-log-details" open={paymentLogs.length > 0}>
          <summary>Payment detail</summary>
          <div className="payment-log" aria-live="polite">
            {paymentLogs.map((entry, i) => (
              <div key={`${entry.step}-${i}`} className="payment-entry">
                <span className="log-time">{entry.elapsed ?? ''}</span>
                <span className={`payment-badge ${entry.status}`}>{entry.step}</span>
                <div className="payment-msg-wrap">
                  <span className="payment-msg">{entry.message}</span>
                  {entry.detail ? <div className="payment-detail-line">{entry.detail}</div> : null}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
      <details className="exec-log-details" open={execLogs.length > 0}>
        <summary>Execution trace</summary>
        <div className="exec-log">
          {execLogs.map((entry, i) => (
            <div key={`${entry.level}-${i}`} className="log-entry">
              <span className="log-time">{entry.elapsed ?? ''}</span>
              <span className={`log-badge ${entry.level}`}>{entry.level}</span>
              <span className="log-msg">{entry.message}</span>
            </div>
          ))}
        </div>
      </details>
      <details className="exec-log-details x402-debug-details" open={!!x402Debug.required || !!x402Debug.response || !!x402Debug.lastError}>
        <summary>x402 debug</summary>
        <pre className="x402-debug-pre">{JSON.stringify(debugJson, null, 2)}</pre>
      </details>
    </section>
  );
}
