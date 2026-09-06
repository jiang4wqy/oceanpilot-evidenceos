// Shared transport primitives. A timeout is an unknown write outcome, never a retry.
const OceanRequest = (() => {
  const inflight = new Map();
  const scopes = new Map();
  const defaultTimeoutMs = 90000;

  async function read(url, options = {}, timeoutMs = defaultTimeoutMs, format = 'json') {
    const controller = new AbortController();
    let timer;
    const timeout = new Promise(resolve => {
      timer = setTimeout(() => {
        resolve({ok: false, status: 0, data: {detail: 'network unavailable'}, timedOut: true});
        controller.abort();
      }, timeoutMs);
    });
    const operation = (async () => {
      try {
        const response = await fetch(url, {...options, signal: controller.signal});
        const data = await response[format]().catch(() => format === 'json' ? {} : '');
        return {ok: response.ok, status: response.status, data};
      } catch (error) {
        return {ok: false, status: 0, data: {detail: 'network unavailable'}};
      }
    })();
    try {
      return await Promise.race([operation, timeout]);
    } finally {
      clearTimeout(timer);
    }
  }

  function singleFlight(key, operation) {
    if (inflight.has(key)) return inflight.get(key);
    const pending = Promise.resolve().then(operation).finally(() => {
      if (inflight.get(key) === pending) inflight.delete(key);
    });
    inflight.set(key, pending);
    return pending;
  }

  function begin(scope) {
    const sequence = (scopes.get(scope) || 0) + 1;
    scopes.set(scope, sequence);
    return {scope, sequence};
  }

  function isLatest(ticket) {
    return scopes.get(ticket.scope) === ticket.sequence;
  }

  const json = (url, options, timeoutMs) => read(url, options, timeoutMs, 'json');
  const text = (url, options, timeoutMs) => read(url, options, timeoutMs, 'text');
  return {json, text, singleFlight, begin, isLatest};
})();
