'use strict';

(function (global) {
  let _state = {
    status:     'idle',
    required:   null,
    response:   null,
    txHash:     null,
    lastError:  null,
  };

  function render() {
    const pre = document.getElementById('x402-debug-pre');
    const details = document.getElementById('x402-debug-details');
    if (!pre) return;

    const out = {
      status:            _state.status,
      paymentRequired:   _state.required,
      paymentResponse:   _state.response,
      transactionHash:   _state.txHash || _state.response?.transactionHash
        || _state.response?.transaction || null,
      error:             _state.lastError,
    };
    pre.textContent = JSON.stringify(out, null, 2);
    if (details && (_state.required || _state.response || _state.lastError)) {
      details.open = true;
    }
  }

  function setStatus(status) {
    _state.status = status;
    render();
  }

  function setRequired(obj) {
    _state.required = obj;
    render();
  }

  function setResponse(headerOrObj) {
    if (typeof headerOrObj === 'string') {
      _state.response = global.X402Pay
        ? global.X402Pay.decodePaymentResponseHeader(headerOrObj)
        : headerOrObj;
      const tx = _state.response?.transaction
        || _state.response?.transactionHash
        || _state.response?.txHash;
      if (tx) _state.txHash = tx;
    } else {
      _state.response = headerOrObj;
    }
    render();
  }

  function setTxHash(hash) {
    _state.txHash = hash;
    render();
  }

  function setError(msg) {
    _state.lastError = msg;
    render();
  }

  function reset() {
    _state = { status: 'idle', required: null, response: null, txHash: null, lastError: null };
    render();
  }

  global.X402Debug = {
    setStatus,
    setRequired,
    setResponse,
    setTxHash,
    setError,
    reset,
    render,
  };
})(window);
