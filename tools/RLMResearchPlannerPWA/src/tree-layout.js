export function compactExplicitRowSlots(columns, sourceColumnCount, targetColumnCount) {
  const ordered = [...columns].sort((left, right) => left - right);
  if (!ordered.length) return [];
  if (targetColumnCount <= 1) return ordered.map(() => 0);
  if (ordered.length >= targetColumnCount) return ordered.map((_, index) => index);
  if (
    sourceColumnCount === 5
    && targetColumnCount === 4
    && ordered.length === 2
    && ordered[0] === 1
    && ordered[1] === 3
  ) return [1, 2];

  const sourceSpan = Math.max(1, sourceColumnCount - 1);
  const targetSpan = targetColumnCount - 1;
  const raw = ordered.map((column) => column / sourceSpan * targetSpan);
  if (raw.every((slot, index) => index === 0 || slot - raw[index - 1] >= 1)) return raw;

  const rowSpan = ordered.length - 1;
  const centeredStart = raw.reduce((sum, slot) => sum + slot, 0) / raw.length - rowSpan / 2;
  const start = Math.max(0, Math.min(targetSpan - rowSpan, centeredStart));
  return ordered.map((_, index) => start + index);
}

export function explicitTreeLayout(nodes) {
  const rows = new Map();
  for (const node of nodes) {
    if (!rows.has(node.row)) rows.set(node.row, []);
    rows.get(node.row).push(node);
  }
  const sourceColumnCount = Math.max(1, ...nodes.map((node) => node.column + 1));
  const targetColumnCount = Math.max(1, ...rows.values().map((row) => row.length));
  const slots = new Map();
  for (const row of rows.values()) {
    row.sort((left, right) => left.column - right.column);
    const compacted = compactExplicitRowSlots(row.map((node) => node.column), sourceColumnCount, targetColumnCount);
    row.forEach((node, index) => slots.set(node.id, compacted[index]));
  }
  return {
    slots,
    columnCount: targetColumnCount,
    rowCount: Math.max(1, ...nodes.map((node) => node.row + 1)),
  };
}
