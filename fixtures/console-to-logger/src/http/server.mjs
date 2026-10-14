import { createServer } from 'node:http';
import { log } from '../lib/logger.mjs';

const PORT = Number(process.env.PORT ?? 3000);

export const server = createServer((req, res) => {
  console.log(req.method, req.url);
  res.setHeader('content-type', 'application/json');
  res.end(JSON.stringify({ ok: true }));
});

if (import.meta.url === `file://${process.argv[1]}`) {
  server.listen(PORT, () => log.info('listening', { port: PORT }));
}
