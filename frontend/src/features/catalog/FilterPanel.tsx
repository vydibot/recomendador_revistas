import { useEffect, useState } from "react";
import type { Facets, FacetValue } from "@/api/types";
import { Chip, SelectField, inputClass } from "@/components/ui";
import { type Filters, activeFilterCount } from "@/lib/filters";
import { ORIGIN_LABEL } from "@/lib/format";

type ListKey = "topic" | "quartile" | "publindex" | "access" | "country" | "language" | "format" | "origin";
type ScalarKey = Exclude<keyof Filters, ListKey | "sort" | "order" | "page">;

interface Props {
  filters: Filters;
  facets: Facets | undefined;
  onChange: (patch: Partial<Filters>) => void;
  onClear: () => void;
  total: number;
}

const WEEKS_PRESETS = [
  { value: "", label: "Cualquier tiempo" },
  { value: "8.7", label: "Hasta 2 meses" },
  { value: "13", label: "Hasta 3 meses" },
  { value: "26", label: "Hasta 6 meses" },
  { value: "52", label: "Hasta 1 año" },
];

const SCORE_FIELDS: { key: ScalarKey; label: string; step: string }[] = [
  { key: "h_index_min", label: "Índice H mínimo", step: "1" },
  { key: "sjr_min", label: "SJR mínimo", step: "0.1" },
  { key: "citescore_min", label: "CiteScore mínimo", step: "0.5" },
  { key: "impact_factor_min", label: "Impact Factor mínimo", step: "0.5" },
  { key: "quality_min", label: "Índice calidad-costo mín. (0–1)", step: "0.05" },
];

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[12px] font-medium text-stone-600">{title}</legend>
      {children}
    </fieldset>
  );
}

/** Lista de casillas con conteo; añade buscador cuando hay muchas opciones. */
function CheckList({
  title,
  options,
  selected,
  onToggle,
  labelOf = (value: string) => value,
  collapsedCount = 6,
}: {
  title: string;
  options: FacetValue[];
  selected: string[];
  onToggle: (value: string) => void;
  labelOf?: (value: string) => string;
  collapsedCount?: number;
}) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  if (options.length === 0) return null;

  const needle = query.trim().toLowerCase();
  const matching = needle ? options.filter((o) => labelOf(o.value).toLowerCase().includes(needle)) : options;
  // Lo seleccionado siempre visible aunque quede fuera del recorte.
  const visible =
    expanded || needle
      ? matching
      : [...matching.slice(0, collapsedCount), ...matching.slice(collapsedCount).filter((o) => selected.includes(o.value))];

  return (
    <Section title={title}>
      {options.length > collapsedCount && (
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={`Buscar en ${title.toLowerCase()}…`}
          aria-label={`Buscar en ${title}`}
          className={inputClass}
        />
      )}
      <div className="flex max-h-56 flex-col gap-1 overflow-y-auto pr-1">
        {visible.map((option) => (
          <label key={option.value} className="flex cursor-pointer items-center gap-2 text-[13px] text-stone-600">
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => onToggle(option.value)}
              className="h-3.5 w-3.5 accent-amber-700"
            />
            <span className="flex-1 truncate">{labelOf(option.value)}</span>
            <span className="font-mono text-[11px] text-stone-400">{option.count}</span>
          </label>
        ))}
      </div>
      {!needle && matching.length > collapsedCount && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="self-start text-[12px] font-medium text-amber-700 hover:underline"
        >
          {expanded ? "Ver menos" : `Ver todos (${matching.length})`}
        </button>
      )}
    </Section>
  );
}

/** Input numérico que confirma al escribir con una pequeña espera (evita una consulta por tecla). */
function DebouncedInput({
  value,
  onCommit,
  ...props
}: { value: string; onCommit: (value: string) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onCommit(draft), 350);
    return () => clearTimeout(timer);
  }, [draft, value, onCommit]);
  return <input {...props} value={draft} onChange={(event) => setDraft(event.target.value)} className={inputClass} />;
}

export default function FilterPanel({ filters, facets, onChange, onClear, total }: Props) {
  const setList = (key: ListKey, value: string) => onChange({ [key]: toggle(filters[key], value) });
  const active = activeFilterCount(filters);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="search" className="text-[12px] font-medium text-stone-600">
          Buscar
        </label>
        <DebouncedInput
          id="search"
          type="search"
          value={filters.q}
          onCommit={(q) => onChange({ q })}
          placeholder="Nombre, ISSN, editorial, tema…"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <SelectField label="Ordenar por" value={filters.sort} onChange={(e) => onChange({ sort: e.target.value })}>
          <option value="title">Nombre</option>
          <option value="apc">Costo (APC)</option>
          <option value="weeks">Tiempo de publicación</option>
          <option value="h_index">Índice H</option>
          <option value="sjr">SJR</option>
          <option value="citescore">CiteScore</option>
          <option value="impact_factor">Impact Factor</option>
          <option value="quality">Calidad-costo</option>
        </SelectField>
        <SelectField label="Sentido" value={filters.order} onChange={(e) => onChange({ order: e.target.value as "asc" | "desc" })}>
          <option value="asc">Ascendente</option>
          <option value="desc">Descendente</option>
        </SelectField>
      </div>

      <Section title="Indexación (cuartil SJR)">
        <div className="flex flex-wrap gap-1.5">
          {["Q1", "Q2", "Q3", "Q4"].map((q) => (
            <Chip key={q} active={filters.quartile.includes(q)} onClick={() => setList("quartile", q)}>
              {q}
            </Chip>
          ))}
        </div>
      </Section>

      {facets && facets.publindex_categories.length > 0 && (
        <Section title="Categoría Publindex">
          <div className="flex flex-wrap gap-1.5">
            {facets.publindex_categories.map((c) => (
              <Chip key={c.value} active={filters.publindex.includes(c.value)} onClick={() => setList("publindex", c.value)}>
                {c.value}
              </Chip>
            ))}
          </div>
        </Section>
      )}

      <Section title="Costo de publicación (APC)">
        <select
          aria-label="Estado del costo"
          value={filters.apc_status}
          onChange={(event) => onChange({ apc_status: event.target.value })}
          className={inputClass}
        >
          <option value="">Cualquier costo</option>
          <option value="sin_costo">Sin costo</option>
          <option value="con_costo">Con costo</option>
          <option value="desconocido">Costo desconocido</option>
        </select>
        <label className="text-[11px] text-stone-400" htmlFor="apc-max">
          Máximo (USD)
        </label>
        <DebouncedInput
          id="apc-max"
          type="number"
          min={0}
          step={100}
          value={filters.apc_max}
          onCommit={(apc_max) => onChange({ apc_max })}
          placeholder={facets?.max_apc_usd ? `hasta ${Math.round(facets.max_apc_usd)}` : "Sin límite"}
        />
      </Section>

      <SelectField
        label="Tiempo de publicación"
        value={filters.weeks_max}
        onChange={(event) => onChange({ weeks_max: event.target.value })}
      >
        {WEEKS_PRESETS.map((preset) => (
          <option key={preset.value} value={preset.value}>
            {preset.label}
          </option>
        ))}
      </SelectField>

      {facets && (
        <>
          <CheckList
            title="Tipo de acceso"
            options={facets.access_types}
            selected={filters.access}
            onToggle={(v) => setList("access", v)}
          />
          <CheckList title="País" options={facets.countries} selected={filters.country} onToggle={(v) => setList("country", v)} />
          <CheckList title="Idioma" options={facets.languages} selected={filters.language} onToggle={(v) => setList("language", v)} />
          <CheckList
            title="Formato para publicar"
            options={facets.submission_formats}
            selected={filters.format}
            onToggle={(v) => setList("format", v)}
          />
          <CheckList
            title="Temas"
            options={facets.topics}
            selected={filters.topic}
            onToggle={(v) => setList("topic", v)}
            collapsedCount={10}
          />
          <CheckList
            title="Origen de los datos"
            options={facets.origins}
            selected={filters.origin}
            onToggle={(v) => setList("origin", v)}
            labelOf={(v) => ORIGIN_LABEL[v] ?? v}
          />
        </>
      )}

      <Section title="Indicadores mínimos">
        <div className="grid grid-cols-1 gap-2">
          {SCORE_FIELDS.map((field) => (
            <div key={field.key} className="flex items-center gap-2">
              <label htmlFor={field.key} className="flex-1 text-[12px] text-stone-500">
                {field.label}
              </label>
              <div className="w-24">
                <DebouncedInput
                  id={field.key}
                  type="number"
                  min={0}
                  step={field.step}
                  value={filters[field.key]}
                  onCommit={(value) => onChange({ [field.key]: value })}
                />
              </div>
            </div>
          ))}
        </div>
      </Section>

      <div className="flex items-center justify-between rounded-xl border border-stone-100 bg-stone-50 px-4 py-3">
        <span className="text-[12px] text-stone-400">
          <span className="font-mono font-semibold text-stone-700">{total}</span> resultados
        </span>
        {active > 0 && (
          <button onClick={onClear} className="text-[12px] font-medium text-amber-700 hover:underline">
            Limpiar ({active})
          </button>
        )}
      </div>
    </div>
  );
}
