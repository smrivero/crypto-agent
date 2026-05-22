import { useEffect, useState } from 'react';
import mermaid from 'mermaid';

interface GraphSectionProps {
  theme: 'light' | 'dark';
  mermaidText: string | null;
}

function mermaidThemeVars(theme: 'light' | 'dark') {
  return theme === 'light'
    ? {
        background: '#eef1f6',
        primaryColor: '#f1f5f9',
        primaryTextColor: '#0f172a',
        primaryBorderColor: '#2563eb',
        lineColor: '#94a3b8',
        secondaryColor: '#ffffff',
        tertiaryColor: '#f8fafc',
        edgeLabelBackground: '#ffffff',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontSize: '13px',
      }
    : {
        background: '#07090f',
        primaryColor: '#1a2332',
        primaryTextColor: '#e2e8f0',
        primaryBorderColor: '#3b82f6',
        lineColor: '#64748b',
        secondaryColor: '#121920',
        tertiaryColor: '#0d1117',
        edgeLabelBackground: '#0d1117',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontSize: '13px',
      };
}

export function GraphSection({ theme, mermaidText }: GraphSectionProps) {
  const [visible, setVisible] = useState(false);
  const [svg, setSvg] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    setSvg(null);
    setRenderError(null);
  }, [theme, mermaidText]);

  useEffect(() => {
    if (!visible || !mermaidText || svg) return;

    mermaid.initialize({
      startOnLoad: false,
      theme: 'base',
      themeVariables: mermaidThemeVars(theme),
    });

    mermaid.render('research-graph', mermaidText)
      .then(({ svg: rendered }) => setSvg(rendered))
      .catch((err: Error) => setRenderError(err.message));
  }, [visible, mermaidText, theme, svg]);

  return (
    <section className="card">
      <div className="section-header">
        <h2 className="tag-label">Agent graph</h2>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? 'Hide diagram' : 'Show diagram'}
        </button>
      </div>
      {!visible ? null : (
        <div>
          {renderError ? (
            <p style={{ color: 'var(--muted)', fontSize: '0.83rem' }}>Render error: {renderError}</p>
          ) : svg ? (
            <div dangerouslySetInnerHTML={{ __html: svg }} />
          ) : (
            <p className="empty-hint">Loading diagram…</p>
          )}
          {mermaidText ? (
            <details style={{ marginTop: 18 }}>
              <summary>Raw Mermaid source</summary>
              <pre>{mermaidText}</pre>
            </details>
          ) : null}
        </div>
      )}
    </section>
  );
}
