import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  activeFilterCount,
  clearFilters,
  filtersFromParams,
  filtersToParams,
} from "./filters";

describe("filters <-> URL", () => {
  it("round-trips lists, scalars, sort and page", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      q: "agronomía",
      topic: ["Derecho", "Psicología"],
      quartile: ["Q1"],
      apc_max: "1500",
      sort: "apc",
      order: "desc" as const,
      page: 3,
    };
    const params = filtersToParams(filters);
    expect(params.getAll("topic")).toEqual(["Derecho", "Psicología"]);
    expect(filtersFromParams(params)).toEqual(filters);
  });

  it("omits defaults so URLs stay clean", () => {
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("sanitizes invalid page numbers", () => {
    expect(filtersFromParams(new URLSearchParams("page=-4")).page).toBe(1);
    expect(filtersFromParams(new URLSearchParams("page=abc")).page).toBe(1);
  });

  it("counts active filters and clears them keeping the sort", () => {
    const filters = { ...DEFAULT_FILTERS, q: "x", access: ["Híbrido", "Open Access"], sort: "sjr" };
    expect(activeFilterCount(filters)).toBe(3);
    const cleared = clearFilters(filters);
    expect(activeFilterCount(cleared)).toBe(0);
    expect(cleared.sort).toBe("sjr");
  });
});
