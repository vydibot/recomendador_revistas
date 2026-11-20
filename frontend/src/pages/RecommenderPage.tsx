import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";
import { getModelInfo, recommend } from "@/api/recommend";
import type { Dimension, RecommendRequest, RecommendResponse } from "@/api/types";
import { Alert, PrimaryButton, SelectField, Spinner, inputClass } from "@/components/ui";
import PriorityOrder from "@/features/recommender/PriorityOrder";
import ResultCard from "@/features/recommender/ResultCard";

const MIN_CHARS = 20;

export default function RecommenderPage() {
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [keywords, setKeywords] = useState("");
  const [language, setLanguage] = useState<RecommendRequest["language"]>("auto");
  const [order, setOrder] = useState<Dimension[]>(["impacto", "eficiencia", "flujo"]);
  const [topK, setTopK] = useState(10);
  const resultsRef = useRef<HTMLDivElement>(null);

  const model = useQuery({
    queryKey: ["model-info"],
    queryFn: getModelInfo,
    // Mientras el modelo carga en el servidor (primer arranque), se reintenta.
    refetchInterval: (query) => (query.state.data?.available ? false : 5_000),
  });

  const run = useMutation<RecommendResponse, Error, RecommendRequest>({
    mutationFn: recommend,
    onSuccess: () => setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth" }), 50),
  });

  const textLength = `${title}${abstract}${keywords}`.trim().length;
  const ready = model.data?.available === true;
  const canSubmit = ready && textLength >= MIN_CHARS && !run.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    run.mutate({ title, abstract, keywords, language, priority_order: order, top_k: topK });
  };

  const info = model.data;
  return (
    <div className="mx-auto grid max-w-7xl gap-8 px-4 py-6 md:px-6 md:py-8 lg:grid-cols-[minmax(0,26rem)_1fr]">
      <section aria-labelledby="form-title" className="lg:sticky lg:top-[76px] lg:self-start">
        <h1 id="form-title" className="font-serif text-[20px] font-semibold text-stone-900">
          Recomendador de revistas
        </h1>
        <p className="mb-5 mt-1 text-[13px] leading-snug text-stone-500">
          Ingresa el título, el resumen y las palabras clave de tu manuscrito. El sistema compara su contenido con el de
          cada revista (TF-IDF + SciBERT) y lo combina con un índice de calidad-costo según tus prioridades.
        </p>

        <form onSubmit={submit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="title" className="mb-1.5 block text-[12px] font-medium text-stone-600">
              Título
            </label>
            <input id="title" className={inputClass} value={title} maxLength={500} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label htmlFor="abstract" className="mb-1.5 block text-[12px] font-medium text-stone-600">
              Resumen
            </label>
            <textarea
              id="abstract"
              rows={8}
              maxLength={10000}
              className={inputClass}
              value={abstract}
              onChange={(e) => setAbstract(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="keywords" className="mb-1.5 block text-[12px] font-medium text-stone-600">
              Palabras clave <span className="text-stone-400">(separadas por comas)</span>
            </label>
            <input id="keywords" className={inputClass} value={keywords} maxLength={2000} onChange={(e) => setKeywords(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Idioma del texto" value={language} onChange={(e) => setLanguage(e.target.value as typeof language)}>
              <option value="auto">Detectar</option>
              <option value="es">Español</option>
              <option value="en">Inglés</option>
            </SelectField>
            <SelectField label="Resultados" value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
              {[5, 10, 20, 30].map((n) => (
                <option key={n} value={n}>
                  {n} revistas
                </option>
              ))}
            </SelectField>
          </div>

          <div>
            <span className="mb-2 block text-[12px] font-medium text-stone-600">Prioridades (de mayor a menor)</span>
            <PriorityOrder value={order} onChange={setOrder} />
          </div>

          <PrimaryButton type="submit" disabled={!canSubmit} className="py-3">
            {run.isPending ? "Analizando…" : "Recomendar revistas"}
          </PrimaryButton>
          {textLength > 0 && textLength < MIN_CHARS && (
            <p className="text-[12px] text-stone-400">Escribe al menos {MIN_CHARS} caracteres entre los tres campos.</p>
          )}
        </form>

        <div className="mt-6">
          {model.isPending && <p className="text-[12px] text-stone-400">Consultando el modelo…</p>}
          {model.isError && <Alert>No se pudo consultar el modelo: {model.error.message}</Alert>}
          {info && !info.available && (
            <Alert kind="info">El modelo se está cargando en el servidor. Estará disponible en unos segundos.</Alert>
          )}
          {info?.available && (
            <p className="rounded-xl border border-stone-200 bg-white p-3 text-[12px] leading-relaxed text-stone-500">
              El modelo fue entrenado con artículos reales de{" "}
              <strong className="text-stone-700">{info.journals_covered}</strong> de las{" "}
              <strong className="text-stone-700">{info.catalog_total?.toLocaleString("es-CO")}</strong> revistas del
              catálogo; solo esas pueden recomendarse. Fusión α = {info.alpha} (TF-IDF {info.alpha} · SciBERT{" "}
              {info.alpha != null ? (1 - info.alpha).toFixed(1) : ""}). Explora el resto en el catálogo.
            </p>
          )}
        </div>
      </section>

      <section ref={resultsRef} aria-live="polite" aria-label="Resultados" className="min-w-0">
        {run.isPending && <Spinner label="Calculando similitud con SciBERT…" />}
        {run.isError && <Alert>{run.error.message}</Alert>}
        {!run.data && !run.isPending && !run.isError && (
          <div className="flex h-full min-h-64 items-center justify-center rounded-2xl border border-dashed border-stone-300 p-8 text-center text-[13px] text-stone-400">
            Los resultados aparecerán aquí.
          </div>
        )}
        {run.data && !run.isPending && (
          <div className="flex flex-col gap-3">
            <h2 className="font-serif text-[16px] font-semibold text-stone-900">
              {run.data.results.length} revistas sugeridas
            </h2>
            {run.data.results.map((result) => (
              <ResultCard key={result.issn} result={result} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
