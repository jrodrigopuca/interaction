import { createClient } from 'redis';

let client;
export async function getRedis() {
  if (!client) {
    client = createClient({ url: process.env.REDIS_URL ?? 'redis://localhost:6379' });
    await client.connect();
  }
  return client;
}
