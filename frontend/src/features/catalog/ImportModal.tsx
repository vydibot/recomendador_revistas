import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { importCsv } from "@/api/journals";
import type { ImportReport } from "@/api/types";
import Modal from "@/components/Modal";
import { Alert, PrimaryButton, SecondaryButton } from "@/components/ui";

const COLUMNS = [
  "Nombre", "Indexación", "Link", "Formato que recibe", "ISSN Electrónico", "ISSN Impreso",
  "Formato necesario para publicar", "Acceso", "Costo", "Idioma", "Cuantas revistas/articulos al año",
  "Ubicación", "Correo", "Cuanto demora en publicar?", "Índice H", "CiteScore", "Impact Factor",
];

type Mode = "skip" | "update" | "add";

export default function ImportModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Mode>("skip");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) => importCsv(file!, mode, dryRun),
    onSuccess: (result) => {
      setReport(result);
      setError(null);
      if (!result.dry_run) {
        queryClient.invalidateQueries({ queryKey: ["journals"] });
        queryClient.invalidateQueries({ queryKey: ["facets"] });
      }
    },
    onError: (err) => setError(err.message),
  });

  const applied = report && !report.dry_run;

  return (
    <Modal
      wide
      eyebrow="Importar"
      title="Subir revistas desde CSV"
      onClose={onClose}
      footer={
        applied ? (
          <PrimaryButton onClick={onClose} className="flex-1">
            Listo
          </PrimaryButton>
        ) : (
          <>
            <SecondaryButton onClick={onClose} className="flex-1">
              Cancelar
            </SecondaryButton>
            <SecondaryButton disabled={!file || run.isPending} onClick={() => run.mutate(true)} className="flex-1">
              Revisar archivo
            </SecondaryButton>
            <PrimaryButton disabled={!file || !report || run.isPending} onClick={() => run.mutate(false)} className="flex-1">
              Importar
            </PrimaryButton>
          </>
        )
      }
    >
      <div className="flex flex-col gap-4 text-[13px] text-stone-600">
        <p>
          Archivo <strong>.csv</strong> (UTF-8) con encabezados exactos. Solo <code>Nombre</code> es obligatorio; los
          valores vacíos están permitidos y textos como <code>~USD 2300</code> o <code>3–6 meses</code> se interpretan
          automáticamente.
        </p>
        <details className="rounded-xl border border-stone-200 bg-stone-50 p-3">
          <summary className="cursor-pointer font-medium text-stone-700">Columnas reconocidas</summary>
          <ul className="mt-2 columns-2 font-mono text-[11px] text-stone-500">
            {COLUMNS.map((column) => (
              <li key={column}>{column}</li>
            ))}
          </ul>
        </details>

        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="Archivo CSV"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setReport(null);
          }}
          className="text-[13px]"
        />

        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 font-medium text-stone-700">Si el ISSN ya existe en el catálogo</legend>
          {(
            [
              ["skip", "Omitir la fila (recomendado)"],
              ["update", "Actualizar la revista existente"],
              ["add", "Crear una revista duplicada"],
            ] as [Mode, string][]
          ).map(([value, label]) => (
            <label key={value} className="flex items-center gap-2">
              <input
                type="radio"
                name="mode"
                checked={mode === value}
                onChange={() => {
                  setMode(value);
                  setReport(null);
                }}
                className="accent-amber-700"
              />
              {label}
            </label>
          ))}
        </fieldset>

        {error && <Alert>{error}</Alert>}
        {report && (
          <Alert kind="info">
            <p className="font-semibold">
              {applied ? "Importación completada" : "Vista previa (aún no se guardó nada)"}
            </p>
            <ul className="mt-1 list-disc pl-5">
              <li>{report.rows} filas leídas</li>
              <li>{report.created} revistas nuevas</li>
              <li>{report.updated} actualizadas</li>
              <li>{report.skipped} omitidas por ISSN repetido</li>
              <li>{report.invalid} filas inválidas</li>
            </ul>
            {report.duplicates.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer">ISSN ya existentes ({report.duplicates.length})</summary>
                <ul className="mt-1 max-h-32 list-disc overflow-y-auto pl-5">
                  {report.duplicates.slice(0, 50).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </details>
            )}
          </Alert>
        )}
      </div>
    </Modal>
  );
}
