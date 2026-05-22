# Crypto Research Agent

AI-powered cryptocurrency research using LangGraph + LangChain.

## Setup

### Backend

```bash
cp .env.example .env
# Edit .env — OPENAI_API_KEY, TAVILY_API_KEY, x402 wallet vars
uv sync
```

### Frontend

```bash
cd frontend
cp .env.example .env
# Optional: VITE_WALLETCONNECT_PROJECT_ID for WalletConnect (https://cloud.walletconnect.com)
npm install
npm run build
```

## Run

### Production (backend serves built UI)

```bash
cd frontend && npm run build && cd ..
uv run python main.py serve
```

Open **http://localhost:8000**

### Development (hot reload UI + API proxy)

Terminal 1 — API:

```bash
uv run python main.py serve
```

Terminal 2 — frontend:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** (Vite proxies `/api` to port 8000).

### Railway

Set **Start Command** to:

```bash
uv run python main.py serve
```

Railway injects `PORT`; the server binds to `0.0.0.0` by default. Override with `HOST` if needed.

For local parity:

```bash
PORT=8000 uv run python main.py serve
```

## CLI mode

```bash
uv run python main.py "Analyze DEXTF token"
```

## Wallets (Premium x402)

The UI uses **wagmi + RainbowKit** on **Base Sepolia**:

- MetaMask
- Coinbase Wallet
- Rabby
- WalletConnect (requires `VITE_WALLETCONNECT_PROJECT_ID` in `frontend/.env`)

Connect via **Connect Wallet** (top right). Premium payments sign EIP-3009 in your connected wallet.

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/research` | Research query (`mode`: `free` \| `premium`; premium requires x402) |
| `POST` | `/api/v1/research/stream` | Same as research, SSE pipeline steps |
| `GET`  | `/api/v1/premium-demo` | **x402 demo** — 402 + payment, then JSON when paid (see below) |
| `GET`  | `/api/v1/logs` | Recent request log (dev) |
| `GET`  | `/api/v1/graph/mermaid` | Agent graph as Mermaid diagram |
| `GET`  | `/api/v1/health` | Health check |

Interactive docs: **http://localhost:8000/docs**

## x402 payments (Base Sepolia)

Premium research uses [x402](https://www.x402.org/) on **Base Sepolia** with **USDC**.

**Facilitator choice is in the UI**: with **Premium** selected, use the **Facilitator** dropdown — **Public x402** or **Coinbase CDP**. Saved in `localStorage`, sent as `X402-Facilitator-Mode` on each payment request.

| UI option | URL |
|-----------|-----|
| Public x402 (default) | `X402_PUBLIC_FACILITATOR_URL` → `https://x402.org/facilitator` |
| Coinbase CDP | `https://api.cdp.coinbase.com/platform/v2/x402` |

### Backend `.env` (credentials)

```bash
X402_PUBLIC_FACILITATOR_URL=https://x402.org/facilitator
X402_NETWORK=base-sepolia
X402_RECEIVING_WALLET_ADDRESS=0xYourSellerAddress

# When using Coinbase CDP in the UI:
CDP_API_KEY_ID=...
CDP_API_KEY_SECRET=...
CDP_PROJECT_ID=...
```

`scripts/x402_buyer_test.py` always uses the **public** facilitator (CLI, no browser).

## x402 buyer script (unchanged)

```bash
uv run python scripts/x402_buyer_test.py
```

Uses `EVM_PRIVATE_KEY` in `.env` — not the browser wallet.

## Tests

```bash
uv run pytest
```
