'use strict';

// ── Config ────────────────────────────────────────────────────────────────────
const API = {
  stream:   '/api/v1/research/stream',
  research: '/api/v1/research',
  logs:     '/api/v1/logs',
  graph:    '/api/v1/graph/mermaid',
};

const FACILITATOR_STORAGE_KEY = 'x402FacilitatorMode';

function getFacilitatorMode() {
  const stored = localStorage.getItem(FACILITATOR_STORAGE_KEY);
  return stored === 'coinbase' ? 'coinbase' : 'public';
}

function facilitatorRequestHeaders(extra = {}) {
  return {
    'X402-Facilitator-Mode': getFacilitatorMode(),
    ...extra,
  };
}

function showFacilitatorWarning(res) {
  const msg = res.headers.get('X402-Facilitator-Warning')
    || res.headers.get('x402-facilitator-warning');
  if (msg) appendPaymentLog('facilitator', msg, 'warn');
}

const NODES_PREMIUM = [
  'payment',
  'classify',
  'search',
  'technical_token_analysis',
  'aggregate',
  'analyze',
];
const NODES_FREE = ['classify', 'search', 'analyze'];
const NODE_LABELS = {
  payment:                  'x402 payment',
  classify:                 'Classifying request',
  search:                   'Searching the web',
  technical_token_analysis: 'Fetching on-chain data',
  aggregate:                'Aggregating content',
  analyze:                  'Generating analysis',
};

// ── DOM ───────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const queryInput      = $('query-input');
const submitBtn       = $('submit-btn');
const modelSelect     = $('model-select');
const loadingInline   = $('loading-inline');
const resultsEl       = $('results-section');
const stepsCard       = $('steps-card');
const stepsList       = $('steps-list');
const stepsStatus     = $('steps-status');
const execLogDetails     = $('exec-log-details');
const execLog            = $('exec-log');
const paymentLogDetails  = $('payment-log-details');
const paymentLog         = $('payment-log');
const logsContainer   = $('logs-container');
const graphContainer  = $('graph-container');
const mermaidDiagram  = $('mermaid-diagram');
const mermaidSource   = $('mermaid-source');
const toggleGraphBtn  = $('toggle-graph-btn');
const refreshLogsBtn  = $('refresh-logs-btn');
const x402TestBtn       = $('x402-test-btn');
const x402Result        = $('x402-result');
const walletConnectBtn  = $('wallet-connect-btn');
const walletConnectedEl = $('wallet-connected');
const walletAddressEl   = $('wallet-address');
const walletNetworkEl   = $('wallet-network');
const walletEthEl       = $('wallet-eth');
const walletUsdcEl      = $('wallet-usdc');
const walletStatusText  = $('wallet-status-text');
const walletStatusDot   = $('wallet-status-dot');
const facilitatorSelect = $('facilitator-select');
const facilitatorRow    = $('facilitator-row');

let _runStart = null;
let _walletRefreshTimer = null;

function updateFacilitatorRowVisibility() {
  if (!facilitatorRow) return;
  facilitatorRow.classList.toggle('hidden', getResearchMode() !== 'premium');
}

// ── Facilitator selector (localStorage → header en cada pago premium) ─────────
if (facilitatorSelect) {
  facilitatorSelect.value = getFacilitatorMode();
  facilitatorSelect.addEventListener('change', () => {
    const mode = facilitatorSelect.value === 'coinbase' ? 'coinbase' : 'public';
    localStorage.setItem(FACILITATOR_STORAGE_KEY, mode);
    appendPaymentLog(
      'facilitator',
      `Facilitator: ${mode === 'coinbase' ? 'Coinbase CDP' : 'Public x402'}`,
      'info',
    );
  });
}
document.querySelectorAll('input[name="research-mode"]').forEach(radio => {
  radio.addEventListener('change', updateFacilitatorRowVisibility);
});
updateFacilitatorRowVisibility();

// ── Submit ────────────────────────────────────────────────────────────────────
submitBtn.addEventListener('click', runResearch);
queryInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runResearch();
});

// ── x402 premium demo (402 + PAYMENT-REQUIRED; no browser signing) ───────────
if (x402TestBtn && x402Result) {
  x402TestBtn.addEventListener('click', runX402Demo);
}

async function runX402Demo() {
  x402TestBtn.disabled = true;
  x402Result.classList.remove('hidden');
  x402Result.innerHTML = '<p class="empty-hint">Requesting…</p>';

  try {
    const res = await fetch('/api/v1/premium-demo', {
      headers: facilitatorRequestHeaders(),
    });
    showFacilitatorWarning(res);
    const text = await res.text();
    let jsonPretty = '';
    try {
      jsonPretty = JSON.stringify(JSON.parse(text), null, 2);
    } catch (_) {
      jsonPretty = text;
    }

    let decodedBlock = '';
    if (res.status === 402) {
      const raw = res.headers.get('PAYMENT-REQUIRED') || res.headers.get('payment-required');
      if (raw) {
        try {
          const bin = atob(raw.trim());
          decodedBlock = JSON.stringify(JSON.parse(bin), null, 2);
        } catch (e) {
          decodedBlock = 'Could not decode PAYMENT-REQUIRED: ' + e.message;
        }
      } else {
        decodedBlock = 'No PAYMENT-REQUIRED header (check server CORS expose-headers).';
      }
    }

    const parts = [
      '<p><strong>HTTP ' + res.status + '</strong></p>',
      '<h4 style="margin:12px 0 6px;font-size:0.72rem;text-transform:uppercase;color:var(--muted)">Body</h4>',
      '<pre>' + esc(jsonPretty) + '</pre>',
    ];
    if (res.status === 402) {
      parts.push(
        '<h4 style="margin:12px 0 6px;font-size:0.72rem;text-transform:uppercase;color:var(--orange)">PAYMENT-REQUIRED (decoded)</h4>',
        '<pre>' + esc(decodedBlock) + '</pre>',
      );
    }
    x402Result.innerHTML = parts.join('');
  } catch (err) {
    x402Result.innerHTML = '<p style="color:var(--red)">' + esc(err.message) + '</p>';
  } finally {
    x402TestBtn.disabled = false;
  }
}

function getResearchMode() {
  const el = document.querySelector('input[name="research-mode"]:checked');
  return el?.value === 'premium' ? 'premium' : 'free';
}

function decodePaymentRequiredHeader(res) {
  const raw = res.headers.get('PAYMENT-REQUIRED') || res.headers.get('payment-required');
  if (!raw) return null;
  try {
    return JSON.parse(atob(raw.trim()));
  } catch (_) {
    return null;
  }
}

function loadStoredPaymentHeaders() {
  try {
    const raw = sessionStorage.getItem('x402_payment_headers');
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function savePaymentHeaders(headers) {
  sessionStorage.setItem('x402_payment_headers', JSON.stringify(headers));
}

function getPaymentRequiredRaw(res) {
  return res.headers.get('PAYMENT-REQUIRED') || res.headers.get('payment-required') || '';
}

async function devSignPayment(paymentRequiredB64) {
  const res = await fetch('/api/v1/x402/dev-sign', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ payment_required_header: paymentRequiredB64 }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.message || res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

function decodePaymentRequiredFromB64(b64) {
  if (!b64) return null;
  try {
    return JSON.parse(atob(b64.trim()));
  } catch (_) {
    return null;
  }
}

let _paymentModalOnClose = null;

function closePaymentModal() {
  const modal = $('payment-modal');
  if (modal) modal.classList.add('hidden');
  document.body.classList.remove('modal-open');
  _paymentModalOnClose = null;
}

function openPaymentModal(html, onClose) {
  const modal = $('payment-modal');
  const body  = $('payment-modal-body');
  if (!modal || !body) return;
  body.innerHTML = html;
  _paymentModalOnClose = onClose || null;
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
  const confirmBtn = $('mm-confirm-pay-btn');
  if (confirmBtn) confirmBtn.focus();
}

function initPaymentModal() {
  const modal = $('payment-modal');
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = '1';
  modal.addEventListener('click', e => {
    if (e.target.closest('[data-payment-modal-close]')) {
      if (_paymentModalOnClose) _paymentModalOnClose();
      closePaymentModal();
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      if (_paymentModalOnClose) _paymentModalOnClose();
      closePaymentModal();
    }
  });
}

function buildPaymentSummaryHtml(summary) {
  return `
    <dl class="payment-summary-grid">
      <dt>Amount</dt><dd>${esc(summary.amount)} ${esc(summary.token)}</dd>
      <dt>Network</dt><dd>${esc(summary.network)}</dd>
      <dt>Token contract</dt><dd>${esc(summary.tokenAddress)}</dd>
      <dt>Recipient</dt><dd>${esc(summary.recipient)}</dd>
    </dl>`;
}

async function confirmPaymentWithMetaMask(paymentRequired) {
  const summary = window.X402Pay.formatPaymentSummary(paymentRequired);

  return new Promise((resolve, reject) => {
    const dismiss = () => resolve(null);

    openPaymentModal(`
      <h3 id="payment-modal-title" class="payment-title">Premium payment (x402)</h3>
      <p class="payment-hint">Review the payment, then confirm in MetaMask to start the analysis.</p>
      ${buildPaymentSummaryHtml(summary)}
      <div class="payment-modal-actions">
        <button type="button" id="mm-confirm-pay-btn" class="btn-x402">Sign with MetaMask</button>
        <button type="button" id="mm-cancel-pay-btn" class="btn-ghost" data-payment-modal-close>Cancel</button>
      </div>
    `, dismiss);

    $('mm-confirm-pay-btn')?.addEventListener('click', async () => {
      const btn = $('mm-confirm-pay-btn');
      const statusEl = $('payment-modal-status');
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Waiting for MetaMask…';
      }
      if (statusEl) statusEl.textContent = '';
      try {
        if (!window.CryptoWallet.isConnected()) {
          await window.CryptoWallet.connect();
          await updateWalletUI();
        }
        await window.CryptoWallet.ensureBaseSepolia();
        const signed = await window.X402Pay.signPaymentPayload(
          paymentRequired,
          window.CryptoWallet.getSigner(),
        );
        savePaymentHeaders(signed.headers);
        closePaymentModal();
        resolve(signed.headers);
      } catch (e) {
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Sign with MetaMask';
        }
        reject(e);
      }
    });
  });
}

async function retryWithPayment(paymentRequiredB64, manualSig) {
  setLoading(true);
  initSteps('premium');
  try {
    let headers = {};
    if (manualSig) {
      headers = { 'PAYMENT-SIGNATURE': manualSig };
    } else if (window.CryptoWallet?.hasMetaMask()) {
      const decoded = decodePaymentRequiredFromB64(paymentRequiredB64);
      if (!decoded) throw new Error('Invalid PAYMENT-REQUIRED');
      headers = await confirmPaymentWithMetaMask(decoded);
      if (!headers) {
        setLoading(false);
        return;
      }
    } else {
      const signed = await devSignPayment(paymentRequiredB64);
      headers = signed.headers || {};
    }
    if (!headers?.['PAYMENT-SIGNATURE']) throw new Error('No PAYMENT-SIGNATURE generated');
    appendPaymentLog('retry', 'Retrying with PAYMENT-SIGNATURE', 'info');
    await runResearch();
  } catch (err) {
    window.X402Debug?.setError(err.message);
    renderError(`x402 payment: ${err.message}`);
    setLoading(false);
  }
}

function showPaymentRequired(res, bodyText, paymentRequiredB64) {
  const decoded = decodePaymentRequiredHeader(res) || decodePaymentRequiredFromB64(paymentRequiredB64);
  if (decoded) window.X402Debug?.setRequired(decoded);

  if (decoded && window.CryptoWallet?.hasMetaMask()) {
    setStepState('payment', 'active', 'Confirm payment in modal');
    stepsStatus.textContent = 'Payment required — confirm in dialog';
    confirmPaymentWithMetaMask(decoded)
      .then(headers => {
        if (!headers) {
          setLoading(false);
          stepsStatus.textContent = 'Payment cancelled';
          return;
        }
        setLoading(true);
        return runPremiumStreamAfterPayment(
          queryInput.value.trim(),
          modelSelect.value,
          headers,
        );
      })
      .catch(err => {
        renderError(`x402: ${err.message}`);
        setLoading(false);
      });
    return;
  }

  let bodyJson = bodyText;
  try { bodyJson = JSON.stringify(JSON.parse(bodyText), null, 2); } catch (_) {}
  const summary = decoded && window.X402Pay
    ? window.X402Pay.formatPaymentSummary(decoded)
    : null;
  const summaryHtml = summary ? buildPaymentSummaryHtml(summary) : '';

  openPaymentModal(`
    <h3 id="payment-modal-title" class="payment-title">Payment required (x402)</h3>
    <p class="payment-hint">Connect MetaMask on Base Sepolia, or paste a signature manually.</p>
    ${summaryHtml}
    <div class="payment-modal-actions">
      <button type="button" id="payment-retry-btn" class="btn-x402">Sign with MetaMask</button>
      <button type="button" id="mm-cancel-pay-btn" class="btn-ghost" data-payment-modal-close>Cancel</button>
    </div>
    <details class="payment-manual" style="margin-top:16px">
      <summary>Paste PAYMENT-SIGNATURE manually</summary>
      <label class="payment-label" for="payment-sig-input">Base64 header</label>
      <textarea id="payment-sig-input" rows="3"></textarea>
      <button type="button" id="payment-manual-btn" class="btn-ghost" style="margin-top:8px">Use pasted signature</button>
    </details>
    <h4 class="payment-sub">PAYMENT-REQUIRED</h4>
    <pre class="payment-pre">${esc(decoded ? JSON.stringify(decoded, null, 2) : '(missing)')}</pre>
  `, () => setLoading(false));

  $('payment-retry-btn')?.addEventListener('click', () => {
    closePaymentModal();
    if (decoded) {
      setLoading(true);
      confirmPaymentWithMetaMask(decoded)
        .then(headers => {
          if (!headers) { setLoading(false); return; }
          return runPremiumStreamAfterPayment(
            queryInput.value.trim(),
            modelSelect.value,
            headers,
          );
        })
        .catch(err => {
          renderError(`x402: ${err.message}`);
          setLoading(false);
        });
    }
  });

  $('payment-manual-btn')?.addEventListener('click', () => {
    const manual = $('payment-sig-input')?.value.trim() || '';
    if (manual) {
      closePaymentModal();
      retryWithPayment(paymentRequiredB64, manual);
    }
  });
}

async function consumeSSEStream(res) {
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = '';

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
      try { handleEvent(JSON.parse(raw)); } catch (_) {}
    }
  }
}

async function runPremiumStreamAfterPayment(query, model, payHeaders) {
  const body = { query, model, mode: 'premium' };
  initSteps('premium');
  window.X402Debug?.setStatus('streaming');

  const res = await fetch(API.stream, {
    method:  'POST',
    headers: facilitatorRequestHeaders({
      'Content-Type': 'application/json',
      ...payHeaders,
    }),
    body:    JSON.stringify(body),
  });
  showFacilitatorWarning(res);

  const settleHdr = res.headers.get('PAYMENT-RESPONSE') || res.headers.get('payment-response');
  if (settleHdr) window.X402Debug?.setResponse(settleHdr);

  if (res.status === 402) {
    const txt = await res.text();
    showPaymentRequired(res, txt, getPaymentRequiredRaw(res));
    stepsStatus.textContent = 'Payment required';
    setStepState('payment', 'active', 'Awaiting signature');
    markRemainingStepsSkipped('payment');
    return;
  }

  if (!res.ok) {
    const txt = await res.text();
    renderError(`Server error ${res.status}: ${txt}`);
    markRemainingStepsSkipped();
    return;
  }

  await consumeSSEStream(res);
  window.X402Debug?.setStatus('done');
}

async function runPremiumResearch(query, model) {
  if (!window.CryptoWallet?.hasMetaMask()) {
    throw new Error('Install MetaMask for Premium x402 payments');
  }
  if (!window.CryptoWallet.isConnected()) {
    await window.CryptoWallet.connect();
    await updateWalletUI();
  }
  await window.CryptoWallet.ensureBaseSepolia();
  await window.CryptoWallet.syncNetworkStatus();
  if (window.CryptoWallet.getStatus() !== 'connected') {
    throw new Error('Switch MetaMask to Base Sepolia');
  }

  window.X402Debug?.reset();
  window.X402Debug?.setStatus('probing');
  resultsEl.innerHTML = '';
  initSteps('premium');

  const body = { query, model, mode: 'premium' };

  appendPaymentLog('probe', 'POST /api/v1/research', 'info');
  const probe = await fetch(API.research, {
    method:  'POST',
    headers: facilitatorRequestHeaders({ 'Content-Type': 'application/json' }),
    body:    JSON.stringify(body),
  });
  showFacilitatorWarning(probe);

  let payHeaders = {};

  if (probe.status === 402) {
    const decoded = decodePaymentRequiredHeader(probe)
      || decodePaymentRequiredFromB64(getPaymentRequiredRaw(probe));
    if (!decoded) throw new Error('Could not decode PAYMENT-REQUIRED');
    window.X402Debug?.setRequired(decoded);
    window.X402Debug?.setStatus('payment_required');
    appendPaymentLog('402', 'HTTP 402 — payment required', 'warn');

    setStepState('payment', 'active', 'Confirm payment in modal');
    stepsStatus.textContent = 'Payment required — confirm in dialog';
    payHeaders = await confirmPaymentWithMetaMask(decoded);
    if (!payHeaders) {
      stepsStatus.textContent = 'Payment cancelled';
      markRemainingStepsSkipped('payment');
      return;
    }
    appendPaymentLog('sign', 'MetaMask signature OK', 'ok');
    window.X402Debug?.setStatus('signed');
  } else if (probe.ok) {
    const data = await probe.json();
    if (data.success && data.report) {
      const settleHdr = probe.headers.get('PAYMENT-RESPONSE') || probe.headers.get('payment-response');
      if (settleHdr) window.X402Debug?.setResponse(settleHdr);
      stepsStatus.textContent = `Done · ${data.processing_time_ms} ms`;
      renderResults(data);
      return;
    }
  } else {
    throw new Error(`Payment probe failed (${probe.status}): ${await probe.text()}`);
  }

  appendPaymentLog('stream', 'POST /api/v1/research/stream', 'info');
  await runPremiumStreamAfterPayment(query, model, payHeaders);
}

async function runResearch() {
  const query = queryInput.value.trim();
  if (!query) { queryInput.focus(); return; }

  const mode = getResearchMode();
  setLoading(true);

  try {
    if (mode === 'premium') {
      await runPremiumResearch(query, modelSelect.value);
      return;
    }

    resultsEl.innerHTML = '';
    initSteps(mode);
    const body = { query, model: modelSelect.value, mode };

    const res = await fetch(API.stream, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });

    if (!res.ok) {
      const txt = await res.text();
      renderError(`Server error ${res.status}: ${txt}`);
      markRemainingStepsSkipped();
      return;
    }

    await consumeSSEStream(res);
  } catch (err) {
    window.X402Debug?.setError(err.message);
    renderError(err.message);
  } finally {
    setLoading(false);
    loadLogs();
  }
}

function setLoading(on) {
  submitBtn.disabled = on;
  loadingInline.classList.toggle('hidden', !on);
}

// ── Step pipeline UI ──────────────────────────────────────────────────────────
function initSteps(mode = 'free') {
  stepsCard.classList.remove('hidden');
  stepsStatus.textContent = (mode === 'premium' ? 'Premium · ' : 'Free · ') + 'Running…';
  stepsList.innerHTML = '';
  execLog.innerHTML = '';
  execLogDetails.open = false;
  if (paymentLog) paymentLog.innerHTML = '';
  if (paymentLogDetails) {
    paymentLogDetails.classList.toggle('hidden', mode !== 'premium');
    paymentLogDetails.open = mode === 'premium';
  }
  _runStart = Date.now();

  const nodes = mode === 'premium' ? NODES_PREMIUM : NODES_FREE;
  for (const node of nodes) {
    const row = document.createElement('div');
    row.className = 'step-row is-pending';
    row.id = `step-${node}`;
    row.innerHTML = `
      <div class="step-icon"></div>
      <div class="step-body">
        <div class="step-name">${NODE_LABELS[node]}</div>
        <div class="step-detail"></div>
      </div>`;
    stepsList.appendChild(row);
  }
}

function markRemainingStepsSkipped(exceptNode = null) {
  for (const node of NODES_PREMIUM) {
    if (node === exceptNode) continue;
    const row = $(`step-${node}`);
    if (row && (row.classList.contains('is-pending') || row.classList.contains('is-active'))) {
      row.className = 'step-row is-skipped';
      row.querySelector('.step-icon').textContent = '';
    }
  }
}

function appendPaymentLog(step, message, status = 'info', detail = '') {
  if (!paymentLog) return;
  const elapsed = _runStart ? ((Date.now() - _runStart) / 1000).toFixed(2) + 's' : '';
  const entry   = document.createElement('div');
  entry.className = 'payment-entry';
  const detailHtml = detail
    ? `<div class="payment-detail-line">${esc(detail)}</div>`
    : '';
  entry.innerHTML = `
    <span class="log-time">${esc(elapsed)}</span>
    <span class="payment-badge ${esc(status)}">${esc(step)}</span>
    <div class="payment-msg-wrap">
      <span class="payment-msg">${esc(message)}</span>
      ${detailHtml}
    </div>
  `;
  paymentLog.appendChild(entry);
  paymentLog.scrollTop = paymentLog.scrollHeight;
  if (paymentLogDetails && !paymentLogDetails.open) paymentLogDetails.open = true;
}

function appendLog(ev) {
  const elapsed = _runStart ? ((Date.now() - _runStart) / 1000).toFixed(2) + 's' : '';
  const entry   = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `
    <span class="log-time">${esc(elapsed)}</span>
    <span class="log-badge ${esc(ev.level)}">${esc(ev.level)}</span>
    <span class="log-msg">${esc(ev.message)}</span>
  `;
  execLog.appendChild(entry);
  execLog.scrollTop = execLog.scrollHeight;
  if (!execLogDetails.open) execLogDetails.open = true;
}

function setStepState(node, state, detail = '') {
  const row = $(`step-${node}`);
  if (!row) return;
  row.className = `step-row is-${state}`;
  const icon = row.querySelector('.step-icon');
  icon.textContent = state === 'done' ? '✓' : state === 'error' ? '✕' : state === 'skipped' ? '—' : '';
  if (detail) row.querySelector('.step-detail').textContent = detail;
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'step_start':
      setStepState(ev.node, 'active');
      stepsStatus.textContent = ev.label + '…';
      break;

    case 'step_end':
      setStepState(ev.node, 'done', ev.detail || '');
      break;

    case 'step_error':
      setStepState(ev.node, 'error', ev.detail || '');
      stepsStatus.textContent = 'Error in ' + ev.label;
      markRemainingStepsSkipped();
      break;

    case 'step_skip':
      setStepState(ev.node, 'skipped', ev.detail || '');
      break;

    case 'result':
      stepsStatus.textContent = `Done · ${ev.data.processing_time_ms} ms`;
      renderResults(ev.data);
      break;

    case 'error':
      stepsStatus.textContent = 'Failed';
      renderError(ev.message);
      markRemainingStepsSkipped();
      break;

    case 'log':
      appendLog(ev);
      break;

    case 'payment_log':
      appendPaymentLog(ev.step || 'payment', ev.message || '', ev.status || 'info', ev.detail || '');
      break;
  }
}

// ── Results ───────────────────────────────────────────────────────────────────
function renderResults(data) {
  if (!data.success || !data.report) {
    renderError(data.error || 'Agent returned an empty response.');
    return;
  }

  const r      = data.report;
  const isFree = r.mode === 'free';
  const pct    = Math.round(r.confidence_score * 100);
  const cClass = pct >= 70 ? 'conf-high' : pct >= 40 ? 'conf-mid' : 'conf-low';
  const abbr   = r.token.replace(/[^A-Z0-9]/gi, '').slice(0, 3).toUpperCase() || '?';
  const cls    = (r.classification || (isFree ? 'free snapshot' : 'analysis')).replace(/_/g, ' ');
  const ms     = data.processing_time_ms;

  const sourcesHtml = r.sources && r.sources.length
    ? `<div class="sources-section">
        <h3>Sources</h3>
        <div class="sources-chips">
          ${r.sources.map(s => {
            const host  = hostname(s);
            const first = host.replace('www.', '')[0]?.toUpperCase() ?? '?';
            return `<a class="source-chip" href="${escAttr(s)}" target="_blank" rel="noopener noreferrer" title="${escAttr(s)}">
              <span class="source-favicon">${esc(first)}</span>${esc(host)}
            </a>`;
          }).join('')}
        </div>
      </div>`
    : '';

  const td = r.technical_details;
  const technicalHtml = td ? `
    <div class="tech-section">
      <h3 class="tech-heading">On-Chain Data</h3>
      <div class="tech-grid">
        <div class="tech-row"><span class="tech-label">Network</span><span class="tech-value tech-badge-net">${esc(td.network)}</span></div>
        <div class="tech-row"><span class="tech-label">Chain ID</span><span class="tech-value">${esc(String(td.chain_id))}</span></div>
        <div class="tech-row tech-full"><span class="tech-label">Contract</span><span class="tech-value tech-mono">${esc(td.contract_address)}</span></div>
        <div class="tech-row"><span class="tech-label">Token Name</span><span class="tech-value">${esc(td.token_name)}</span></div>
        <div class="tech-row"><span class="tech-label">Symbol</span><span class="tech-value">${esc(td.token_symbol)}</span></div>
        <div class="tech-row"><span class="tech-label">Decimals</span><span class="tech-value">${esc(String(td.decimals))}</span></div>
        <div class="tech-row tech-full"><span class="tech-label">Total Supply</span><span class="tech-value">${esc(td.total_supply_formatted)}</span></div>
        <div class="tech-row"><span class="tech-label">Holders</span><span class="tech-value">${td.holder_count != null ? esc(td.holder_count.toLocaleString()) : '<span class="tech-na">n/a</span>'}</span></div>
      </div>
      ${td.warnings && td.warnings.length ? `<div class="tech-warnings">${td.warnings.map(w => `<div class="tech-warn">⚠ ${esc(w)}</div>`).join('')}</div>` : ''}
    </div>` : '';

  resultsEl.innerHTML = `
    <div class="card result-card">

      <div class="result-header">
        <div class="token-badge">
          <div class="token-avatar">${esc(abbr)}</div>
          <div>
            <div class="token-name">${esc(r.token)}</div>
            <div class="token-class">${esc(cls)}</div>
          </div>
        </div>

        <div class="confidence-wrap ${cClass}">
          <div class="confidence-label">Confidence</div>
          <div class="confidence-row">
            <div class="confidence-bar">
              <div class="confidence-fill" id="conf-fill" style="width:0%"></div>
            </div>
            <span class="confidence-pct">${pct}%</span>
          </div>
        </div>
      </div>

      <div class="result-meta-row">
        <span class="meta-pill">${isFree ? 'Free report' : 'Premium report'}</span>
        ${r.sources?.length ? `<span class="meta-pill">${r.sources.length} sources</span>` : ''}
        <span class="meta-pill">${ms ? ms + ' ms' : '—'}</span>
        <span class="meta-pill">${new Date(r.timestamp).toLocaleString()}</span>
      </div>

      <p class="summary-text">${escLines(r.summary)}</p>

      <div class="analysis-grid">
        <div class="analysis-block bullish">
          <h3>Bullish</h3>
          <ul>${r.bullish_points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>
        </div>
        <div class="analysis-block bearish">
          <h3>Bearish</h3>
          <ul>${r.bearish_points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>
        </div>
        ${!isFree && r.risks?.length ? `
        <div class="analysis-block risks full-row">
          <h3>Risks</h3>
          <ul>${r.risks.map(p => `<li>${esc(p)}</li>`).join('')}</ul>
        </div>` : ''}
      </div>

      ${technicalHtml}

      ${sourcesHtml}

      <details>
        <summary>Raw JSON response</summary>
        <pre>${esc(JSON.stringify(data, null, 2))}</pre>
      </details>
    </div>
  `;

  // Animate confidence bar after paint
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const fill = $('conf-fill');
      if (fill) fill.style.width = pct + '%';
    });
  });
}

function renderError(msg) {
  resultsEl.innerHTML = `<div class="error-card">${esc(msg)}</div>`;
}

// ── Request log ───────────────────────────────────────────────────────────────
refreshLogsBtn.addEventListener('click', loadLogs);

async function loadLogs() {
  try {
    const res = await fetch(API.logs);
    if (!res.ok) return;
    renderLogs(await res.json());
  } catch (_) {}
}

function renderLogs(logs) {
  if (!logs.length) {
    logsContainer.innerHTML = '<p class="empty-hint">No requests yet.</p>';
    return;
  }

  logsContainer.innerHTML = `
    <table class="logs-table">
      <thead>
        <tr>
          <th>Time</th><th>Query</th><th>Status</th><th>Duration</th><th>Error</th>
        </tr>
      </thead>
      <tbody>
        ${logs.map(l => `
          <tr>
            <td class="cell-time">${esc(fmtTime(l.timestamp))}</td>
            <td class="cell-query" title="${escAttr(l.query)}">${esc(l.query)}</td>
            <td><span class="status-badge ${l.status === 'success' ? 'ok' : 'err'}">
              ${l.status === 'success' ? 'ok' : 'err'}
            </span></td>
            <td class="cell-dur">${l.duration_ms} ms</td>
            <td class="cell-err">${l.error ? esc(l.error) : ''}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString(); } catch (_) { return iso; }
}

// ── Agent graph ───────────────────────────────────────────────────────────────
let _mermaidText   = null;
let _graphRendered = false;

async function loadGraph() {
  try {
    const res = await fetch(API.graph);
    if (!res.ok) return;
    const data  = await res.json();
    _mermaidText = data.mermaid || null;
    if (_mermaidText) mermaidSource.textContent = _mermaidText;
  } catch (_) {}
}

toggleGraphBtn.addEventListener('click', async () => {
  const nowHidden = graphContainer.classList.toggle('hidden');
  toggleGraphBtn.textContent = nowHidden ? 'Show diagram' : 'Hide diagram';

  if (!nowHidden && !_graphRendered && _mermaidText) {
    try {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: mermaidThemeVars(),
      });
      const { svg } = await mermaid.render('research-graph', _mermaidText);
      mermaidDiagram.innerHTML = svg;
      _graphRendered = true;
    } catch (err) {
      mermaidDiagram.innerHTML =
        `<p style="color:var(--muted);font-size:0.83rem">Render error: ${esc(err.message)}</p>`;
    }
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return String(s ?? '').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function escLines(s) { return esc(s).replace(/\n/g, '<br>'); }
function hostname(url) { try { return new URL(url).hostname; } catch (_) { return url.slice(0, 40); } }

// ── Wallet UI ─────────────────────────────────────────────────────────────────
async function updateWalletUI() {
  if (!window.CryptoWallet) return;

  await window.CryptoWallet.syncNetworkStatus();
  const status = window.CryptoWallet.getStatus();
  const connected = status === 'connected' && window.CryptoWallet.getAddress();

  if (walletConnectBtn) {
    walletConnectBtn.classList.toggle('hidden', !!connected);
  }
  if (walletConnectedEl) {
    walletConnectedEl.classList.toggle('hidden', !connected);
  }

  if (walletStatusDot) {
    walletStatusDot.className = 'wallet-status-dot'
      + (status === 'connected' ? ' is-ok' : status === 'wrong_network' ? ' is-warn' : ' is-err');
  }
  if (walletStatusText) {
    walletStatusText.textContent = status === 'connected'
      ? 'Connected'
      : status === 'wrong_network'
        ? 'Wrong network'
        : 'Disconnected';
  }

  if (!connected) return;

  if (walletAddressEl) {
    walletAddressEl.textContent = window.CryptoWallet.shortAddr(window.CryptoWallet.getAddress());
  }
  if (walletNetworkEl) {
    walletNetworkEl.textContent = window.CryptoWallet.getNetworkLabel();
  }

  try {
    const bal = await window.CryptoWallet.refreshBalances();
    if (walletEthEl) walletEthEl.textContent = bal.eth;
    if (walletUsdcEl) walletUsdcEl.textContent = bal.usdc;
  } catch (_) {
    if (walletEthEl) walletEthEl.textContent = '—';
    if (walletUsdcEl) walletUsdcEl.textContent = '—';
  }
}

function initWallet() {
  if (!walletConnectBtn || !window.CryptoWallet) return;

  walletConnectBtn.addEventListener('click', async () => {
    walletConnectBtn.disabled = true;
    try {
      await window.CryptoWallet.connect();
      await updateWalletUI();
      if (_walletRefreshTimer) clearInterval(_walletRefreshTimer);
      _walletRefreshTimer = setInterval(updateWalletUI, 30_000);
    } catch (err) {
      renderError(err.message);
    } finally {
      walletConnectBtn.disabled = false;
    }
  });

  window.CryptoWallet.onAccountsChanged(() => updateWalletUI());
  window.CryptoWallet.onChainChanged(() => updateWalletUI());

  if (window.CryptoWallet.hasMetaMask()) {
    window.CryptoWallet.syncNetworkStatus().then(updateWalletUI);
  } else {
    walletConnectBtn.textContent = 'No MetaMask';
    walletConnectBtn.disabled = true;
  }
}

// ── Theme ─────────────────────────────────────────────────────────────────────
const themeSwitch = $('theme-switch');

function getTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function applyTheme(theme) {
  const t = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  if (themeSwitch) themeSwitch.checked = t === 'light';
  _graphRendered = false;
}

function mermaidThemeVars() {
  const light = getTheme() === 'light';
  return light
    ? {
        background:          '#eef1f6',
        primaryColor:          '#f1f5f9',
        primaryTextColor:      '#0f172a',
        primaryBorderColor:    '#2563eb',
        lineColor:             '#94a3b8',
        secondaryColor:        '#ffffff',
        tertiaryColor:         '#f8fafc',
        edgeLabelBackground:   '#ffffff',
        fontFamily:            '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontSize:              '13px',
      }
    : {
        background:          '#07090f',
        primaryColor:        '#1a2332',
        primaryTextColor:    '#e2e8f0',
        primaryBorderColor:  '#3b82f6',
        lineColor:           '#64748b',
        secondaryColor:      '#121920',
        tertiaryColor:       '#0d1117',
        edgeLabelBackground: '#0d1117',
        fontFamily:          '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontSize:            '13px',
      };
}

function initTheme() {
  if (!themeSwitch) return;
  const saved = localStorage.getItem('theme');
  applyTheme(saved === 'dark' ? 'dark' : 'light');
  themeSwitch.addEventListener('change', () => {
    applyTheme(themeSwitch.checked ? 'light' : 'dark');
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
initTheme();
initPaymentModal();
initWallet();
loadLogs();
loadGraph();
setInterval(loadLogs, 30_000);
