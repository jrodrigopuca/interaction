// Sincroniza el catálogo con el ERP. Corre por cron a las 03:00.
export async function nightlySync(erp, db) {
  console.time('nightly-sync');
  let page = 1, updated = 0;
  try {
    for (;;) {
      const batch = await erp.products({ page });
      if (batch.length === 0) break;
      for (const p of batch) { db.stock.set(p.sku, p.qty); updated++; }
      console.log(`nightly-sync page ${page}: ${batch.length} products`);
      page++;
    }
  } catch (err) {
    console.error('nightly-sync aborted', err.message);
    throw err;
  } finally {
    console.timeEnd('nightly-sync');
  }
  console.log('nightly-sync done, updated', updated);
  return updated;
}
