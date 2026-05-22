# Agent log — crypto-agent

## Completado

- Integración de **Tavily** para búsqueda web real (`tavily-python`).
- Variable de entorno **`TAVILY_API_KEY`** documentada en `.env.example` y línea añadida en `.env`.
- `config/settings.py`: campo `tavily_api_key` (vacío = fallback a `mock_search`).
- `tools/web_search.py`: llama a Tavily con `max_search_results`; sin API key usa mock (útil para CI).
- `tools/__init__.py`: exporta `search_crypto` desde `web_search`.
- **Execution trace (SSE)**: niveles `web` y `rpc` — Tavily/Explorer HTTPS y JSON-RPC visibles en la UI; `config/stream_trace.py` + drenado en `astream_research`.
- **Demo x402 aislado**: `GET /api/v1/premium-demo` (Base Sepolia), `api/x402_payment.py` compartido, script `scripts/x402_buyer_test.py`.
- **Facilitators x402 dual**: `services/facilitator.py` — elección **solo en UI** (dropdown Premium → header `X402-Facilitator-Mode`); `.env` solo credenciales CDP; fallback a público si CDP inválido.
- **Research free/premium**: `POST /api/v1/research` con `mode: free|premium`; grafo único con `analysis_depth`; premium exige x402 (`api/x402_payment.py`); UI toggle Free/Premium + retry con `PAYMENT-SIGNATURE`.
- **Fix x402 local**: `load_dotenv()` + `Settings.evm_private_key` (UI `/x402/dev-sign` ya no depende solo de `os.getenv`); `premium-demo` no devuelve 500 si `settle` falla (try/except + headers coercion).
- **Pipeline pago**: nodo LangGraph `payment` (premium); trazas `config/payment_trace.py` + SSE `payment_log`; panel UI **Payment detail**.
- **Etherscan**: `ETHERSCAN_API_KEY` en `.env`; holders vía **Blockscout** si Etherscan tokeninfo exige API Pro (`tools/token_rpc.py`).
- **MetaMask (UI)**: migrado a **React + Vite** en `frontend/` con **wagmi + RainbowKit** (MetaMask, Coinbase, Rabby, WalletConnect); x402 EIP-3009 sin cambios de protocolo.
- **UI tema/ancho**: layout ~1320px, modo claro por defecto, switch ☀/☾ (`localStorage.theme`).
- **Modal pago x402**: confirmación Premium centrada (backdrop, Esc, Cancel); ya no se pierde abajo en la página.

## Mejoras / tareas posibles

- Probar flujo premium con dropdown **Coinbase CDP** en la UI y claves CDP en `.env`.
- Permitir `TAVILY_SEARCH_DEPTH=advanced` vía settings si hace falta más profundidad.
- Tests de integración con Tavily mockados (HTTP) para evitar llamadas reales.
- Rotar o revisar claves si `.env` llegó a versionarse por error (mantener solo `.env.example` en git).

## Próximos pasos sugeridos

1. `cd frontend && npm run build` antes de servir en producción (`uv run python main.py serve`).
2. Dev UI: `npm run dev` en `frontend/` + API en `:8000`.
3. Probar Premium con varias wallets (MetaMask, Rabby, WalletConnect) en Base Sepolia.
