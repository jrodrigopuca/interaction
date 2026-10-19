// Removes repeated ids, keeping the first occurrence of each so the caller's
// order survives (the batch endpoint relies on it to map results back).
export function dedupeIds(ids) {
  const seen = new Set();
  const out = [];
  for (const id of ids) {
    if (!seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}
