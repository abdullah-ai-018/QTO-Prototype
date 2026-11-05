/**
 * Runs `fn` over `items` with at most `limit` in flight at once — used to
 * replace unbounded `Promise.all`/`Promise.allSettled` fan-outs (e.g. one
 * request per page of an 18-page blueprint) that can storm a dev-grade
 * backend into multi-second response times per request. Each call settles
 * independently: a rejection in one item doesn't stop the others.
 */
export async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<void>,
): Promise<void> {
  if (items.length === 0) return;
  let cursor = 0;
  const workerCount = Math.max(1, Math.min(limit, items.length));

  async function worker() {
    while (cursor < items.length) {
      const index = cursor++;
      try {
        await fn(items[index], index);
      } catch {
        // Individual item failures are the caller's concern (they should
        // catch inside fn if they need per-item error state) — a worker
        // must keep pulling the next item regardless.
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, worker));
}
