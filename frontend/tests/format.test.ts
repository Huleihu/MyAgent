import { describe, expect, it } from "vitest";

import { formatDurationMs } from "@/lib/format";

describe("耗时格式化", () => {
  it("最多保留四位小数，并移除无意义的尾随零", () => {
    expect(formatDurationMs(0.1329999840911478)).toBe("0.133");
    expect(formatDurationMs(0.01170000177808106)).toBe("0.0117");
    expect(formatDurationMs(1.23456)).toBe("1.2346");
    expect(formatDurationMs(2)).toBe("2");
    expect(formatDurationMs(0)).toBe("0");
  });
});
