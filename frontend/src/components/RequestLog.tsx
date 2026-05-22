import type { LogEntry } from '../lib/types';
import { esc, fmtTime } from '../lib/utils';

interface RequestLogProps {
  logs: LogEntry[];
  onRefresh: () => void;
}

export function RequestLog({ logs, onRefresh }: RequestLogProps) {
  return (
    <section className="card">
      <div className="section-header">
        <h2 className="tag-label">Request log</h2>
        <button type="button" className="btn-ghost" onClick={onRefresh}>↻ Refresh</button>
      </div>
      {!logs.length ? (
        <p className="empty-hint">No requests yet.</p>
      ) : (
        <table className="logs-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Query</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l, i) => (
              <tr key={`${l.timestamp}-${i}`}>
                <td className="cell-time">{fmtTime(l.timestamp)}</td>
                <td className="cell-query" title={l.query}>{l.query}</td>
                <td>
                  <span className={`status-badge ${l.status === 'success' ? 'ok' : 'err'}`}>
                    {l.status === 'success' ? 'ok' : 'err'}
                  </span>
                </td>
                <td className="cell-dur">{l.duration_ms} ms</td>
                <td className="cell-err">{l.error ? esc(l.error) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
