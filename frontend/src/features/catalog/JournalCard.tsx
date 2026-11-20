import type { Journal } from "@/api/types";
import { Chip, Meta, PublindexBadge, QuartileBadge } from "@/components/ui";
import { ORIGIN_LABEL, formatApc, formatNumber, formatWeeks, issnLabel, NA, percent } from "@/lib/format";

interface Props {
  journal: Journal;
  onEdit?: (journal: Journal) => void;
}

export default function JournalCard({ journal, onEdit }: Props) {
  const hasLink = journal.url && /^https?:\/\//i.test(journal.url);
  return (
    <article className="group flex flex-col gap-3 rounded-xl border border-stone-200 bg-white p-5 transition-all duration-200 hover:border-amber-700/40 hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-serif text-[15px] font-semibold leading-snug text-stone-900 transition-colors group-hover:text-amber-800">
          {journal.title}
        </h3>
        <div className="flex shrink-0 gap-1.5">
          <PublindexBadge value={journal.publindex_category} />
          <QuartileBadge value={journal.quartile} />
        </div>
      </div>

      <div className="flex flex-col gap-0.5">
        <p className="font-mono text-[11px] tracking-wide text-stone-400">
          {issnLabel(journal.issn_print, journal.issn_electronic)}
        </p>
        <p className="text-[12px] leading-tight text-stone-500">
          {[journal.publisher, journal.country, journal.submission_format && `Formato: ${journal.submission_format}`]
            .filter(Boolean)
            .join(" · ") || "Sin datos de editorial"}
        </p>
      </div>

      <div className="flex flex-wrap border-t border-stone-100 pt-3">
        <Meta label="Costo" value={formatApc(journal.apc_usd, journal.apc_status, journal.apc_text)} />
        <Meta label="Tiempo" value={formatWeeks(journal.weeks_to_publication, journal.time_text)} />
        <Meta label="Acceso" value={journal.access_type ?? NA} />
        <Meta label="Idioma" value={journal.language ?? NA} />
        <Meta label="Índice H" value={formatNumber(journal.h_index)} />
        <Meta label="SJR" value={formatNumber(journal.sjr, 2)} />
        <Meta label="CiteScore" value={formatNumber(journal.citescore)} />
        <Meta label="Impact Factor" value={formatNumber(journal.impact_factor)} />
      </div>

      {journal.quality_cost_index != null && (
        <div title="Índice TOPSIS de calidad-costo (0 a 1)">
          <div className="mb-1 flex justify-between text-[11px] text-stone-400">
            <span>Calidad-costo</span>
            <span className="font-mono">{journal.quality_cost_index.toFixed(2)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
            <div className="h-full rounded-full bg-amber-600" style={{ width: `${percent(journal.quality_cost_index)}%` }} />
          </div>
        </div>
      )}

      {journal.topics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {journal.topics.map((topic) => (
            <Chip key={topic}>{topic}</Chip>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-center gap-2 border-t border-stone-50 pt-1">
        {hasLink && (
          <a
            href={journal.url!}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[12px] font-medium text-amber-700 underline underline-offset-2 transition-colors hover:text-amber-900"
          >
            Ver fuente
          </a>
        )}
        <span className="text-[11px] text-stone-300" title={ORIGIN_LABEL[journal.origin]}>
          {ORIGIN_LABEL[journal.origin]}
          {journal.locally_modified && journal.origin !== "manual" ? " · editada" : ""}
        </span>
        {onEdit && (
          <button
            onClick={() => onEdit(journal)}
            className="ml-auto rounded-lg border border-stone-300 px-3 py-1.5 text-[12px] font-medium text-stone-600 transition-all hover:border-stone-400 hover:bg-stone-50 active:scale-95"
          >
            Editar
          </button>
        )}
      </div>
    </article>
  );
}
