import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { PAGE_SIZE, getFacets, listJournals } from "@/api/journals";
import type { Journal } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import Modal from "@/components/Modal";
import { Alert, PrimaryButton, SecondaryButton, Spinner } from "@/components/ui";
import FilterPanel from "@/features/catalog/FilterPanel";
import ImportModal from "@/features/catalog/ImportModal";
import JournalCard from "@/features/catalog/JournalCard";
import JournalFormModal from "@/features/catalog/JournalFormModal";
import { type Filters, activeFilterCount, clearFilters, filtersFromParams, filtersToParams } from "@/lib/filters";

export default function CatalogPage() {
  const { isAdmin } = useAuth();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const [editing, setEditing] = useState<Journal | null>(null);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [drawer, setDrawer] = useState(false);

  const facets = useQuery({ queryKey: ["facets"], queryFn: getFacets, staleTime: 60_000 });
  const journals = useQuery({
    queryKey: ["journals", filters],
    queryFn: () => listJournals(filters),
    placeholderData: keepPreviousData,
  });

  // Cualquier cambio de filtro vuelve a la página 1; el cambio de página la conserva.
  const update = useCallback(
    (patch: Partial<Filters>) => {
      setParams(
        (previous) => {
          const current = filtersFromParams(previous);
          const next = { ...current, ...patch };
          if (!("page" in patch)) next.page = 1;
          return filtersToParams(next);
        },
        { replace: true },
      );
    },
    [setParams],
  );
  const clear = useCallback(() => setParams(filtersToParams(clearFilters(filters)), { replace: true }), [filters, setParams]);

  const total = journals.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const active = activeFilterCount(filters);
  const goTo = (page: number) => {
    update({ page });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const panel = (
    <FilterPanel filters={filters} facets={facets.data} onChange={update} onClear={clear} total={total} />
  );

  return (
    <div className="mx-auto flex max-w-7xl gap-8 px-4 py-4 md:px-6 md:py-8">
      <aside className="sticky top-[76px] hidden h-[calc(100vh-100px)] w-72 shrink-0 flex-col gap-4 md:flex">
        <div>
          <h1 className="font-serif text-[18px] font-semibold text-stone-900">Catálogo de revistas</h1>
          <p className="text-[13px] leading-snug text-stone-500">
            {facets.data ? `${facets.data.total.toLocaleString("es-CO")} revistas` : "Cargando…"} de Publindex, DOAJ,
            Scimago y el directorio LIDER.
          </p>
        </div>
        <div className="overflow-y-auto pb-8 pr-2">{panel}</div>
      </aside>

      <main className="min-w-0 flex-1 pb-20">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="md:hidden">
            <h1 className="font-serif text-[18px] font-semibold text-stone-900">Catálogo</h1>
          </div>
          <p className="hidden font-mono text-[12px] text-stone-400 md:block" aria-live="polite">
            {total.toLocaleString("es-CO")} resultados · página {filters.page} de {pages}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawer(true)}
              className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-[13px] font-medium text-stone-600 md:hidden"
            >
              Filtros
              {active > 0 && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-700 text-[10px] font-bold text-white">
                  {active}
                </span>
              )}
            </button>
            {isAdmin && (
              <>
                <SecondaryButton onClick={() => setImporting(true)}>Subir CSV</SecondaryButton>
                <PrimaryButton onClick={() => setAdding(true)}>+ Añadir</PrimaryButton>
              </>
            )}
          </div>
        </div>

        {journals.isError && <Alert>No se pudo cargar el catálogo: {journals.error.message}</Alert>}
        {journals.isPending && <Spinner label="Cargando revistas…" />}

        {journals.data && journals.data.items.length === 0 && (
          <div className="flex flex-col items-center py-20 text-center">
            <p className="text-[14px] text-stone-400">Ninguna revista coincide con los filtros.</p>
            <button onClick={clear} className="mt-3 text-[12px] text-amber-700 hover:underline">
              Limpiar filtros
            </button>
          </div>
        )}

        {journals.data && journals.data.items.length > 0 && (
          <div
            className={`grid grid-cols-1 gap-3 transition-opacity md:gap-4 xl:grid-cols-2 ${journals.isPlaceholderData ? "opacity-60" : ""}`}
          >
            {journals.data.items.map((journal) => (
              <JournalCard key={journal.id} journal={journal} onEdit={isAdmin ? setEditing : undefined} />
            ))}
          </div>
        )}

        {pages > 1 && (
          <nav className="mt-8 flex items-center justify-center gap-3" aria-label="Paginación">
            <SecondaryButton disabled={filters.page <= 1} onClick={() => goTo(filters.page - 1)}>
              ← Anterior
            </SecondaryButton>
            <span className="font-mono text-[12px] text-stone-500">
              {filters.page} / {pages}
            </span>
            <SecondaryButton disabled={filters.page >= pages} onClick={() => goTo(filters.page + 1)}>
              Siguiente →
            </SecondaryButton>
          </nav>
        )}
      </main>

      {drawer && (
        <Modal
          title="Filtros"
          onClose={() => setDrawer(false)}
          footer={
            <PrimaryButton className="flex-1" onClick={() => setDrawer(false)}>
              Ver {total} resultados
            </PrimaryButton>
          }
        >
          {panel}
        </Modal>
      )}
      {adding && <JournalFormModal facets={facets.data} onClose={() => setAdding(false)} />}
      {editing && <JournalFormModal journal={editing} facets={facets.data} onClose={() => setEditing(null)} />}
      {importing && <ImportModal onClose={() => setImporting(false)} />}
    </div>
  );
}
