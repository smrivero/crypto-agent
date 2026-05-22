import type { ResearchResponse } from '../lib/types';
import { escLines, hostname } from '../lib/utils';

interface ResultsSectionProps {
  data: ResearchResponse | null;
  error: string | null;
}

export function ResultsSection({ data, error }: ResultsSectionProps) {
  if (error) {
    return (
      <div className="error-card">{error}</div>
    );
  }

  if (!data?.success || !data.report) {
    if (data && !data.success) {
      return <div className="error-card">{data.error ?? 'Agent returned an empty response.'}</div>;
    }
    return null;
  }

  const r = data.report;
  const isFree = r.mode === 'free';
  const pct = Math.round(r.confidence_score * 100);
  const cClass = pct >= 70 ? 'conf-high' : pct >= 40 ? 'conf-mid' : 'conf-low';
  const abbr = r.token.replace(/[^A-Z0-9]/gi, '').slice(0, 3).toUpperCase() || '?';
  const cls = (r.classification ?? (isFree ? 'free snapshot' : 'analysis')).replace(/_/g, ' ');
  const ms = data.processing_time_ms;
  const td = r.technical_details;

  return (
    <div className="card result-card">
      <div className="result-header">
        <div className="token-badge">
          <div className="token-avatar">{abbr}</div>
          <div>
            <div className="token-name">{r.token}</div>
            <div className="token-class">{cls}</div>
          </div>
        </div>
        <div className={`confidence-wrap ${cClass}`}>
          <div className="confidence-label">Confidence</div>
          <div className="confidence-row">
            <div className="confidence-bar">
              <div className="confidence-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="confidence-pct">{pct}%</span>
          </div>
        </div>
      </div>

      <div className="result-meta-row">
        <span className="meta-pill">{isFree ? 'Free report' : 'Premium report'}</span>
        {r.sources?.length ? <span className="meta-pill">{r.sources.length} sources</span> : null}
        <span className="meta-pill">{ms ? `${ms} ms` : '—'}</span>
        <span className="meta-pill">{new Date(r.timestamp).toLocaleString()}</span>
      </div>

      <p className="summary-text" dangerouslySetInnerHTML={{ __html: escLines(r.summary) }} />

      <div className="analysis-grid">
        <div className="analysis-block bullish">
          <h3>Bullish</h3>
          <ul>{r.bullish_points.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
        <div className="analysis-block bearish">
          <h3>Bearish</h3>
          <ul>{r.bearish_points.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
        {!isFree && r.risks?.length ? (
          <div className="analysis-block risks full-row">
            <h3>Risks</h3>
            <ul>{r.risks.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
        ) : null}
      </div>

      {td ? (
        <div className="tech-section">
          <h3 className="tech-heading">On-Chain Data</h3>
          <div className="tech-grid">
            <div className="tech-row"><span className="tech-label">Network</span><span className="tech-value tech-badge-net">{td.network}</span></div>
            <div className="tech-row"><span className="tech-label">Chain ID</span><span className="tech-value">{String(td.chain_id)}</span></div>
            <div className="tech-row tech-full"><span className="tech-label">Contract</span><span className="tech-value tech-mono">{td.contract_address}</span></div>
            <div className="tech-row"><span className="tech-label">Token Name</span><span className="tech-value">{td.token_name}</span></div>
            <div className="tech-row"><span className="tech-label">Symbol</span><span className="tech-value">{td.token_symbol}</span></div>
            <div className="tech-row"><span className="tech-label">Decimals</span><span className="tech-value">{String(td.decimals)}</span></div>
            <div className="tech-row tech-full"><span className="tech-label">Total Supply</span><span className="tech-value">{td.total_supply_formatted}</span></div>
            <div className="tech-row">
              <span className="tech-label">Holders</span>
              <span className="tech-value">
                {td.holder_count != null ? td.holder_count.toLocaleString() : <span className="tech-na">n/a</span>}
              </span>
            </div>
          </div>
          {td.warnings?.length ? (
            <div className="tech-warnings">
              {td.warnings.map((w) => <div key={w} className="tech-warn">⚠ {w}</div>)}
            </div>
          ) : null}
        </div>
      ) : null}

      {r.sources?.length ? (
        <div className="sources-section">
          <h3>Sources</h3>
          <div className="sources-chips">
            {r.sources.map((s) => {
              const host = hostname(s);
              const first = host.replace('www.', '')[0]?.toUpperCase() ?? '?';
              return (
                <a
                  key={s}
                  className="source-chip"
                  href={s}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={s}
                >
                  <span className="source-favicon">{first}</span>
                  {host}
                </a>
              );
            })}
          </div>
        </div>
      ) : null}

      <details>
        <summary>Raw JSON response</summary>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </details>
    </div>
  );
}
