import { log as root } from '../lib/logger.mjs';

const log = root.child({ module: 'billing' });

export async function charge(gateway, order) {
  const res = await gateway.charge({ amount: order.totalCents, ref: order.id });
  if (res.status === 'declined') {
    // El texto 'charge declined' lo matchea ops/alerts.yaml: no cambiarlo.
    log.warn('charge declined', { orderId: order.id, reason: res.reason });
    return false;
  }
  log.info('charge ok', { orderId: order.id });
  return true;
}
