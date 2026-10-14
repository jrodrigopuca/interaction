// Fake mínimo del cliente `redis` v4 para los tests.
export function fakeRedis() {
  const kv = new Map(), lists = new Map();
  return {
    async get(k) { return kv.get(k) ?? null; },
    async set(k, v) { kv.set(k, v); return 'OK'; },
    async del(k) { return kv.delete(k) ? 1 : 0; },
    async incr(k) { const n = Number(kv.get(k) ?? 0) + 1; kv.set(k, String(n)); return n; },
    async expire() { return 1; },
    async lPush(k, v) { const l = lists.get(k) ?? []; l.unshift(v); lists.set(k, l); return l.length; },
    async brPop(k) { const l = lists.get(k) ?? []; const v = l.pop(); return v ? { key: k, element: v } : null; },
  };
}
