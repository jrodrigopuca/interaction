// Thin wrapper over the driver. `text` uses $1..$n placeholders.
export const pool = {
  async query(text, params = []) {
    const { default: pg } = await import("pg");
    const client = new pg.Pool({ connectionString: process.env.DATABASE_URL });
    try { return (await client.query(text, params)).rows; } finally { await client.end(); }
  },
};
