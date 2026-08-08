export function formatResourceAmount(amount, mode = "exact", locale = "ja-JP") {
  const value = Math.trunc(Number(amount) || 0);
  if (mode !== "short" || Math.abs(value) < 1_000) return value.toLocaleString(locale);
  for (const [divisor, suffix] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (Math.abs(value) >= divisor) {
      return `${Number((value / divisor).toFixed(2))}${suffix}`;
    }
  }
  return value.toLocaleString(locale);
}
