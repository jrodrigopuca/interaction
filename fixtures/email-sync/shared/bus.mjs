// Bus de eventos. En producción es un tópico por evento en el broker; acá, la
// misma interfaz en memoria para desarrollo y tests.
// Entrega: at-least-once. Un consumidor que tira error recibe el evento de
// nuevo (hasta 5 veces) y después va a la dead-letter `<evento>.dlq`.
export function createBus() {
  const handlers = new Map();
  const dlq = [];
  return {
    subscribe(event, fn) {
      handlers.set(event, [...(handlers.get(event) ?? []), fn]);
    },
    async publish(event, payload) {
      for (const fn of handlers.get(event) ?? []) {
        let ok = false;
        for (let attempt = 1; attempt <= 5 && !ok; attempt++) {
          try { await fn(payload); ok = true; } catch { /* reintenta */ }
        }
        if (!ok) dlq.push({ event: `${event}.dlq`, payload });
      }
    },
    dlq,
  };
}
