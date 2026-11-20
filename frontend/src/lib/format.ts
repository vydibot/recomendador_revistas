export const NA = "N/D";

export function formatApc(apcUsd: number | null, status: string, text?: string | null): string {
  if (status === "sin_costo") return "Sin costo";
  if (apcUsd == null) return text && !/^~?\s*usd\s*$/i.test(text) ? text : NA;
  return `USD ${Math.round(apcUsd).toLocaleString("es-CO")}`;
}

export function formatWeeks(weeks: number | null, text?: string | null): string {
  if (text) return text;
  if (weeks == null) return NA;
  if (weeks >= 8.7) return `~${(weeks / 4.345).toFixed(1).replace(/\.0$/, "")} meses`;
  return `${weeks.toFixed(0)} semanas`;
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null) return NA;
  return Number.isInteger(value) ? String(value) : value.toFixed(digits);
}

export function formatScore(value: number | null | undefined): string {
  return value == null ? NA : value.toFixed(3);
}

export const percent = (value: number | null | undefined): number =>
  value == null ? 0 : Math.max(0, Math.min(100, value * 100));

export function issnLabel(print: string | null, electronic: string | null): string {
  return `ISSN-E ${electronic ?? NA} · ISSN-P ${print ?? NA}`;
}

export const ORIGIN_LABEL: Record<string, string> = {
  etl: "Publindex / ETL",
  lider: "Directorio LIDER",
  manual: "Agregada manualmente",
};
