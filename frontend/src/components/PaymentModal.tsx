import type { PaymentRequired, PaymentSummary } from '../lib/x402';
import { formatPaymentSummary } from '../lib/x402';

interface PaymentModalProps {
  open: boolean;
  title: string;
  hint: string;
  paymentRequired: PaymentRequired | null;
  signing: boolean;
  signLabel?: string;
  onClose: () => void;
  onSign: () => void;
  children?: React.ReactNode;
}

function PaymentSummaryGrid({ summary }: { summary: PaymentSummary }) {
  return (
    <dl className="payment-summary-grid">
      <dt>Amount</dt>
      <dd>{summary.amount} {summary.token}</dd>
      <dt>Network</dt>
      <dd>{summary.network}</dd>
      <dt>Token contract</dt>
      <dd>{summary.tokenAddress}</dd>
      <dt>Recipient</dt>
      <dd>{summary.recipient}</dd>
    </dl>
  );
}

export function PaymentModal({
  open,
  title,
  hint,
  paymentRequired,
  signing,
  signLabel = 'Sign with wallet',
  onClose,
  onSign,
  children,
}: PaymentModalProps) {
  if (!open) return null;

  const summary = paymentRequired ? formatPaymentSummary(paymentRequired) : null;

  return (
    <div className="payment-modal" role="dialog" aria-modal="true" aria-labelledby="payment-modal-title">
      <div
        className="payment-modal-backdrop"
        onClick={signing ? undefined : onClose}
        tabIndex={-1}
      />
      <div className="payment-modal-panel card payment-card">
        <button type="button" className="payment-modal-close" onClick={onClose} aria-label="Close">
          &times;
        </button>
        <h3 id="payment-modal-title" className="payment-title">{title}</h3>
        <p className="payment-hint">{hint}</p>
        {summary && <PaymentSummaryGrid summary={summary} />}
        <div className="payment-modal-actions">
          <button type="button" className="btn-x402" onClick={onSign} disabled={signing}>
            {signing ? 'Waiting for wallet…' : signLabel}
          </button>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={signing}>
            Cancel
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
