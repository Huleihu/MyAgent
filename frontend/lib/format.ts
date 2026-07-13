/** 将毫秒以最多四位小数呈现，避免调试面板出现冗长浮点数。 */
export function formatDurationMs(durationMs: number): string {
  if (!Number.isFinite(durationMs)) return "—";

  return durationMs.toFixed(4).replace(/\.?0+$/, "");
}
