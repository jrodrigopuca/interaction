import { randomUUID } from 'node:crypto';
import { log as root } from '../lib/logger.mjs';

const log = root.child({ module: 'auth' });
const sessions = new Map();

export function openSession(userId) {
  const id = randomUUID();
  sessions.set(id, { userId, openedAt: Date.now() });
  log.info('session opened', { userId });
  return id;
}

export function closeSession(id) {
  if (!sessions.delete(id)) log.warn('close on unknown session', { sessionId: id });
}
