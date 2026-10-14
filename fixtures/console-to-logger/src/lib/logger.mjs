// Logger estructurado: una línea JSON por evento, a stderr.
// Uso: log.info('order created', { orderId })
const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const threshold = LEVELS[process.env.LOG_LEVEL ?? 'info'] ?? LEVELS.info;

function emit(level, msg, fields = {}, sink = process.stderr) {
  if (LEVELS[level] < threshold) return;
  sink.write(JSON.stringify({ ts: new Date().toISOString(), level, msg, ...fields }) + '\n');
}

export function createLogger(base = {}, sink) {
  const at = (level) => (msg, fields) => emit(level, msg, { ...base, ...fields }, sink);
  return {
    debug: at('debug'), info: at('info'), warn: at('warn'), error: at('error'),
    child: (more) => createLogger({ ...base, ...more }, sink),
  };
}

export const log = createLogger({ service: 'pedidos-api' });
