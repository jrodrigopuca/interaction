// Numerador global de pedidos: cada llamada avanza el contador del proceso.
let next = 1000;
export function nextOrderNumber() { return `P-${next++}`; }
