/** Filtros del catálogo <-> parámetros de URL (la URL es la fuente de verdad: enlaces compartibles). */

export interface Filters {
  q: string;
  topic: string[];
  quartile: string[];
  publindex: string[];
  access: string[];
  country: string[];
  language: string[];
  format: string[];
  origin: string[];
  apc_status: string;
  apc_max: string;
  weeks_max: string;
  h_index_min: string;
  sjr_min: string;
  citescore_min: string;
  impact_factor_min: string;
  quality_min: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
}

const LIST_KEYS = ["topic", "quartile", "publindex", "access", "country", "language", "format", "origin"] as const;
const SCALAR_KEYS = [
  "q", "apc_status", "apc_max", "weeks_max", "h_index_min", "sjr_min", "citescore_min",
  "impact_factor_min", "quality_min",
] as const;

export const DEFAULT_FILTERS: Filters = {
  q: "", topic: [], quartile: [], publindex: [], access: [], country: [], language: [],
  format: [], origin: [], apc_status: "", apc_max: "", weeks_max: "", h_index_min: "",
  sjr_min: "", citescore_min: "", impact_factor_min: "", quality_min: "",
  sort: "title", order: "asc", page: 1,
};

export function filtersFromParams(params: URLSearchParams): Filters {
  const filters: Filters = { ...DEFAULT_FILTERS };
  for (const key of LIST_KEYS) filters[key] = params.getAll(key).filter(Boolean);
  for (const key of SCALAR_KEYS) filters[key] = params.get(key) ?? "";
  filters.sort = params.get("sort") || DEFAULT_FILTERS.sort;
  filters.order = params.get("order") === "desc" ? "desc" : "asc";
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  filters.page = Number.isFinite(page) && page > 0 ? page : 1;
  return filters;
}

export function filtersToParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of SCALAR_KEYS) if (filters[key]) params.set(key, filters[key]);
  for (const key of LIST_KEYS) for (const value of filters[key]) params.append(key, value);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.order !== DEFAULT_FILTERS.order) params.set("order", filters.order);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

/** Cantidad de filtros activos (sin contar orden ni página). */
export function activeFilterCount(filters: Filters): number {
  return (
    SCALAR_KEYS.filter((key) => filters[key]).length +
    LIST_KEYS.reduce((total, key) => total + filters[key].length, 0)
  );
}

export const clearFilters = (filters: Filters): Filters => ({
  ...DEFAULT_FILTERS,
  sort: filters.sort,
  order: filters.order,
});
