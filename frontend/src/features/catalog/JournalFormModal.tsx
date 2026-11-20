import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createJournal, deleteJournal, updateJournal } from "@/api/journals";
import { ApiError } from "@/api/client";
import type { Facets, Journal, JournalInput } from "@/api/types";
import Modal from "@/components/Modal";
import { Alert, Chip, Field, PrimaryButton, SecondaryButton, inputClass } from "@/components/ui";

type Text = Exclude<
  keyof JournalInput,
  "apc_usd" | "weeks_to_publication" | "h_index" | "sjr" | "citescore" | "impact_factor" | "topics"
>;
type Num = "apc_usd" | "weeks_to_publication" | "h_index" | "sjr" | "citescore" | "impact_factor";

interface FormState {
  text: Record<Text, string>;
  num: Record<Num, string>;
  topics: string[];
}

const TEXT_KEYS: Text[] = [
  "title", "issn_electronic", "issn_print", "url", "publisher", "country", "language", "keywords",
  "contact_email", "access_type", "quartile", "publindex_category", "apc_text", "time_text",
  "submission_format", "article_types", "issues_per_year",
];
const NUM_KEYS: Num[] = ["apc_usd", "weeks_to_publication", "h_index", "sjr", "citescore", "impact_factor"];

function initialState(journal?: Journal): FormState {
  const text = Object.fromEntries(
    TEXT_KEYS.map((key) => [key, (journal?.[key as keyof Journal] as string | null | undefined) ?? ""]),
  ) as Record<Text, string>;
  const num = Object.fromEntries(
    NUM_KEYS.map((key) => [key, journal?.[key] != null ? String(journal[key]) : ""]),
  ) as Record<Num, string>;
  return { text, num, topics: journal?.topics ?? [] };
}

/** Solo se envía lo que cambió respecto al original (PATCH parcial). */
function buildPayload(state: FormState, original?: Journal): JournalInput {
  const initial = initialState(original);
  const payload: Record<string, unknown> = {};
  for (const key of TEXT_KEYS) {
    if (!original || state.text[key] !== initial.text[key]) payload[key] = state.text[key] || null;
  }
  for (const key of NUM_KEYS) {
    if (!original || state.num[key] !== initial.num[key]) payload[key] = state.num[key] === "" ? null : Number(state.num[key]);
  }
  if (!original || state.topics.join("|") !== initial.topics.join("|")) payload.topics = state.topics;
  return payload as JournalInput;
}

interface Props {
  journal?: Journal;
  facets?: Facets;
  onClose: () => void;
}

export default function JournalFormModal({ journal, facets, onClose }: Props) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<FormState>(() => initialState(journal));
  const [newTopic, setNewTopic] = useState("");
  const [error, setError] = useState<string | null>(null);

  const setText = (key: Text) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setState((s) => ({ ...s, text: { ...s.text, [key]: event.target.value } }));
  const setNum = (key: Num) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setState((s) => ({ ...s, num: { ...s.num, [key]: event.target.value } }));
  const toggleTopic = (topic: string) =>
    setState((s) => ({
      ...s,
      topics: s.topics.includes(topic) ? s.topics.filter((t) => t !== topic) : [...s.topics, topic],
    }));
  const addTopic = () => {
    const name = newTopic.trim();
    if (name && !state.topics.some((t) => t.toLowerCase() === name.toLowerCase())) toggleTopic(name);
    setNewTopic("");
  };

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["journals"] });
    queryClient.invalidateQueries({ queryKey: ["facets"] });
  };

  const save = useMutation({
    mutationFn: async () => {
      const payload = buildPayload(state, journal);
      const run = (force: boolean) =>
        journal ? updateJournal(journal.id, payload, force) : createJournal(payload, force);
      try {
        return await run(false);
      } catch (err) {
        // ISSN repetido: se avisa y el usuario decide (igual que en el prototipo original).
        if (err instanceof ApiError && err.status === 409) {
          const found = (err.detail as { journals?: { title: string }[] })?.journals ?? [];
          const names = found.map((j) => `“${j.title}”`).join(", ");
          if (window.confirm(`Ya existe una revista con el mismo ISSN: ${names}.\n\n¿Guardar de todos modos?`)) {
            return run(true);
          }
          throw new Error("Guardado cancelado");
        }
        throw err;
      }
    },
    onSuccess: () => {
      refresh();
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: () => deleteJournal(journal!.id),
    onSuccess: () => {
      refresh();
      onClose();
    },
    onError: (err) => setError(err.message),
  });

  const confirmRemove = () => {
    if (window.confirm(`¿Eliminar “${journal?.title}”? Esta acción no se puede deshacer.`)) remove.mutate();
  };

  const knownTopics = (facets?.topics ?? []).map((t) => t.value);
  const topicOptions = [...new Set([...state.topics, ...knownTopics.slice(0, 30)])];
  const busy = save.isPending || remove.isPending;

  return (
    <Modal
      wide
      eyebrow={journal ? "Editar revista" : "Nueva revista"}
      title={journal ? journal.title : "Añadir manualmente"}
      onClose={onClose}
      footer={
        <>
          {journal?.origin === "manual" && (
            <button
              type="button"
              onClick={confirmRemove}
              disabled={busy}
              className="rounded-xl px-3 py-2.5 text-[13px] text-red-700 transition hover:bg-red-50 disabled:opacity-50"
            >
              Eliminar
            </button>
          )}
          <SecondaryButton type="button" onClick={onClose} className="ml-auto">
            Cancelar
          </SecondaryButton>
          <PrimaryButton
            type="button"
            disabled={busy || !state.text.title.trim()}
            onClick={() => {
              setError(null);
              save.mutate();
            }}
          >
            {save.isPending ? "Guardando…" : "Guardar"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-4">
        <Field label="Nombre de la revista" required span2 value={state.text.title} onChange={setText("title")} />
        <Field label="Enlace (URL)" span2 type="url" value={state.text.url} onChange={setText("url")} placeholder="https://…" />
        <Field label="ISSN electrónico" value={state.text.issn_electronic} onChange={setText("issn_electronic")} placeholder="1234-5678" />
        <Field label="ISSN impreso" value={state.text.issn_print} onChange={setText("issn_print")} placeholder="1234-5678" />
        <Field label="Editorial" value={state.text.publisher} onChange={setText("publisher")} />
        <Field label="País" value={state.text.country} onChange={setText("country")} />
        <Field label="Idioma" value={state.text.language} onChange={setText("language")} />
        <Field label="Tipo de acceso" value={state.text.access_type} onChange={setText("access_type")} placeholder="Open Access, Híbrido, Suscripción" list="access-options" />
        <datalist id="access-options">
          <option value="Open Access" />
          <option value="Híbrido" />
          <option value="Suscripción" />
        </datalist>
        <Field label="Cuartil (Q1–Q4)" value={state.text.quartile} onChange={setText("quartile")} placeholder="Q1" />
        <Field label="Categoría Publindex" value={state.text.publindex_category} onChange={setText("publindex_category")} placeholder="A1, A2, B, C" />
        <Field
          label="Costo APC (USD)"
          type="number"
          min={0}
          step="any"
          value={state.num.apc_usd}
          onChange={setNum("apc_usd")}
          hint="0 = sin costo. Vacío = desconocido."
        />
        <Field label="Costo (texto original)" value={state.text.apc_text} onChange={setText("apc_text")} placeholder="~USD 2300 | CHF 1800" hint="Si dejas el número vacío, se interpreta desde este texto." />
        <Field label="Semanas a publicación" type="number" min={0} step="any" value={state.num.weeks_to_publication} onChange={setNum("weeks_to_publication")} />
        <Field label="Tiempo (texto original)" value={state.text.time_text} onChange={setText("time_text")} placeholder="3–6 meses" />
        <Field label="Índice H" type="number" min={0} value={state.num.h_index} onChange={setNum("h_index")} />
        <Field label="SJR" type="number" min={0} step="any" value={state.num.sjr} onChange={setNum("sjr")} />
        <Field label="CiteScore" type="number" min={0} step="any" value={state.num.citescore} onChange={setNum("citescore")} />
        <Field label="Impact Factor" type="number" min={0} step="any" value={state.num.impact_factor} onChange={setNum("impact_factor")} />
        <Field label="Formato para publicar" value={state.text.submission_format} onChange={setText("submission_format")} placeholder="Elsevier, IEEE, MDPI…" />
        <Field label="Tipos de artículo que recibe" value={state.text.article_types} onChange={setText("article_types")} />
        <Field label="Números por año" value={state.text.issues_per_year} onChange={setText("issues_per_year")} />
        <Field label="Correo de contacto" type="email" value={state.text.contact_email} onChange={setText("contact_email")} />
        <Field label="Palabras clave" span2 value={state.text.keywords} onChange={setText("keywords")} />

        <div className="col-span-2">
          <span className="mb-2 block font-mono text-[11px] uppercase tracking-wider text-stone-400">Temas</span>
          <div className="flex flex-wrap gap-1.5">
            {topicOptions.map((topic) => (
              <Chip key={topic} active={state.topics.includes(topic)} onClick={() => toggleTopic(topic)}>
                {topic}
              </Chip>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <input
              className={inputClass}
              value={newTopic}
              onChange={(event) => setNewTopic(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addTopic();
                }
              }}
              placeholder="Añadir un tema nuevo…"
              aria-label="Nuevo tema"
            />
            <SecondaryButton type="button" onClick={addTopic}>
              Añadir
            </SecondaryButton>
          </div>
        </div>
      </div>
      {error && (
        <div className="mt-4">
          <Alert>{error}</Alert>
        </div>
      )}
    </Modal>
  );
}
