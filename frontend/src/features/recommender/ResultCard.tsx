import { Link } from "react-router";
import type { RecommendedJournal } from "@/api/types";
import { Chip, Meta, PublindexBadge, QuartileBadge } from "@/components/ui";
import { NA, formatApc, formatNumber, formatScore, formatWeeks, percent } from "@/lib/format";

function ScoreBar({ label, value, hint, strong }: { label: string; value: number | null; hint: string; strong?: boolean }) {
  return (
    <div title={hint}>
      <div className="mb-1 flex justify-between text-[11px] text-stone-500">
        <span className={strong ? "font-semibold text-stone-700" : ""}>{label}</span>
        <span className="font-mono">{value == null ? NA : value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
        <div
          className={`h-full rounded-full ${strong ? "bg-amber-700" : "bg-amber-400"}`}
          style={{ width: `${percent(value)}%` }}
        />
      </div>
    </div>
  );
}

export default function ResultCard({ result }: { result: RecommendedJournal }) {
  const journal = result.journal;
  return (
    <article className="flex gap-4 rounded-xl border border-stone-200 bg-white p-5 transition-shadow hover:shadow-md">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-700 font-mono text-[13px] font-semibold text-white">
        {result.rank}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-serif text-[16px] font-semibold leading-snug text-stone-900">
              {journal?.title ?? `Revista ISSN ${result.issn}`}
            </h3>
            <p className="font-mono text-[11px] text-stone-400">
              ISSN {result.issn}
              {journal?.country ? ` · ${journal.country}` : ""}
            </p>
          </div>
          <div className="flex gap-1.5">
            <PublindexBadge value={journal?.publindex_category ?? null} />
            <QuartileBadge value={journal?.quartile ?? null} />
          </div>
        </div>

        {journal && (
          <div className="mt-3 flex flex-wrap">
            <Meta label="Costo" value={formatApc(journal.apc_usd, journal.apc_status)} />
            <Meta label="Tiempo" value={formatWeeks(journal.weeks_to_publication)} />
            <Meta label="Acceso" value={journal.access_type ?? NA} />
            <Meta label="Índice H" value={formatNumber(journal.h_index)} />
          </div>
        )}

        {journal && journal.topics.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {journal.topics.slice(0, 4).map((topic) => (
              <Chip key={topic}>{topic}</Chip>
            ))}
          </div>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <ScoreBar label="Afinidad temática" value={result.score_tematico} hint="0,8·TF-IDF + 0,2·SciBERT (similitud coseno)" />
          <ScoreBar label="Calidad-costo" value={result.score_calidad_costo} hint="Índice TOPSIS según tus prioridades" />
          <ScoreBar label="Puntaje final" value={result.score_final} hint="50 % afinidad (normalizada) + 50 % calidad-costo" strong />
        </div>

        <details className="mt-3 text-[12px] text-stone-500">
          <summary className="cursor-pointer select-none hover:text-stone-700">Detalle de similitud</summary>
          <p className="mt-1 font-mono">
            TF-IDF {formatScore(result.score_tfidf)} · SciBERT {formatScore(result.score_scibert)} · temática{" "}
            {formatScore(result.score_tematico)}
          </p>
        </details>

        <div className="mt-3 flex items-center gap-4 text-[12px]">
          {journal?.url && /^https?:\/\//i.test(journal.url) && (
            <a href={journal.url} target="_blank" rel="noreferrer noopener" className="font-medium text-amber-700 underline underline-offset-2">
              Ver fuente
            </a>
          )}
          <Link to={`/catalogo?q=${encodeURIComponent(result.issn)}`} className="font-medium text-amber-700 underline underline-offset-2">
            Ver en el catálogo
          </Link>
        </div>
      </div>
    </article>
  );
}
