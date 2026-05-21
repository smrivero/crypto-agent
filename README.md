# Crypto Research Agent

AI-powered cryptocurrency research using LangGraph + LangChain.

## Setup

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY and TAVILY_API_KEY
uv sync
```

## Run

```bash
uv run python main.py serve
```

Open **http://localhost:8000** in your browser.

## CLI mode

```bash
uv run python main.py "Analyze DEXTF token"
```

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

**Facilitator choice is in the UI** (not in `.env`): with **Premium** selected, use the **Facilitator** dropdown next to the mode toggle — **Public x402** or **Coinbase CDP**. The choice is saved in `localStorage` and sent as `X402-Facilitator-Mode` on each payment request.

| UI option | URL |
|-----------|-----|
| Public x402 (default) | `X402_PUBLIC_FACILITATOR_URL` → `https://x402.org/facilitator` |
| Coinbase CDP | `https://api.cdp.coinbase.com/platform/v2/x402` |

### `.env` (credentials only)

```bash
X402_PUBLIC_FACILITATOR_URL=https://x402.org/facilitator
X402_NETWORK=base-sepolia
X402_RECEIVING_WALLET_ADDRESS=0xYourSellerAddress

# Required only when you pick Coinbase CDP in the UI:
CDP_API_KEY_ID=...
CDP_API_KEY_SECRET=...
CDP_PROJECT_ID=...
```

If you select Coinbase in the UI but CDP keys are missing or invalid, the server **falls back to public** and returns `X402-Facilitator-Warning`.

`scripts/x402_buyer_test.py` always uses the **public** facilitator (no UI).

## x402 payment demo (Base Sepolia, isolated)

Minimal **HTTP 402** flow for `GET /api/v1/premium-demo`. This is **not** connected to the LangGraph agent.

### A. Add Base Sepolia to MetaMask

In MetaMask: **Networks → Add network → Base Sepolia** (chain id **84532**), or add manually using [Base docs](https://docs.base.org/learn/onchain-development/networks).

### B. Get Base Sepolia ETH for gas

Use the official Base Sepolia faucet (or another trusted testnet faucet) so the **buyer** address can pay gas.

### C. Get testnet USDC (buyer)

On Base Sepolia, x402 uses **USDC** (see SDK network defaults). Fund the **buyer** wallet with test USDC from a faucet or bridge, as required for your testing setup.

### D. Seller wallet in `.env`

Set **`X402_RECEIVING_WALLET_ADDRESS`** to the **seller** `0x` address that should receive payment (no private key on the server).

### E. Buyer private key (local script only)

For **`scripts/x402_buyer_test.py`** only, set **`EVM_PRIVATE_KEY`** in `.env` to a **test** wallet that holds Base Sepolia ETH + USDC.

- **Never** commit `.env` or paste keys into git.
- **Never** use a mainnet key or real funds.

### F. Run the server

```bash
uv run python main.py serve
```

(`uv run python main.py` with no arguments also starts the server.)

### G. Run the buyer test

```bash
uv run python scripts/x402_buyer_test.py
```

The script calls **`GET /api/v1/premium-demo`**, handles **402** + `PAYMENT-REQUIRED`, signs the payment with **`EVM_PRIVATE_KEY`**, retries with payment headers, and prints the **200** JSON body.

### Frontend smoke test

Use **“Test x402 Premium Endpoint”** on the home page: it shows **402** and decodes **`PAYMENT-REQUIRED`** (no browser wallet signing).

### Dependency note

This project uses:

```bash
uv add "x402[fastapi]"
```

If `uv` rejects extras on your platform, install the base package and FastAPI separately, e.g.:

```bash
uv add x402 fastapi
```

## Tests

```bash
uv run pytest
```
