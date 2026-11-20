import { describe, expect, it } from "vitest";
import { formatApc, formatNumber, formatWeeks, percent } from "./format";

describe("format", () => {
  it("formats APC by status", () => {
    expect(formatApc(0, "sin_costo")).toBe("Sin costo");
    expect(formatApc(null, "desconocido")).toBe("N/D");
    expect(formatApc(null, "desconocido", "~USD")).toBe("N/D");
    expect(formatApc(1234.4, "con_costo")).toMatch(/^USD 1\D?234$/);
  });

  it("prefers the original duration text and falls back to weeks/months", () => {
    expect(formatWeeks(19.6, "3–6 meses")).toBe("3–6 meses");
    expect(formatWeeks(12, null)).toBe("~2.8 meses");
    expect(formatWeeks(4, null)).toBe("4 semanas");
    expect(formatWeeks(null)).toBe("N/D");
  });

  it("formats numbers and percentages", () => {
    expect(formatNumber(4)).toBe("4");
    expect(formatNumber(4.567)).toBe("4.6");
    expect(formatNumber(null)).toBe("N/D");
    expect(percent(0.5)).toBe(50);
    expect(percent(2)).toBe(100);
    expect(percent(null)).toBe(0);
  });
});
