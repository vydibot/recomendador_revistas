import type { Dimension } from "@/api/types";

export const DIMENSION_INFO: Record<Dimension, { label: string; hint: string }> = {
  impacto: { label: "Impacto", hint: "SJR, índice H y cuartil" },
  eficiencia: { label: "Eficiencia", hint: "Velocidad editorial y costo (APC ajustado por PPP)" },
  flujo: { label: "Flujo", hint: "Citas y volumen de documentos" },
};

export default function PriorityOrder({
  value,
  onChange,
}: {
  value: Dimension[];
  onChange: (order: Dimension[]) => void;
}) {
  const move = (index: number, delta: -1 | 1) => {
    const target = index + delta;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target]!, next[index]!];
    onChange(next);
  };

  return (
    <ol className="flex flex-col gap-2" aria-label="Orden de prioridad">
      {value.map((dimension, index) => (
        <li key={dimension} className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-3 py-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-700 font-mono text-[11px] font-semibold text-white">
            {index + 1}
          </span>
          <div className="flex-1">
            <p className="text-[13px] font-medium text-stone-700">{DIMENSION_INFO[dimension].label}</p>
            <p className="text-[11px] text-stone-400">{DIMENSION_INFO[dimension].hint}</p>
          </div>
          <button
            type="button"
            onClick={() => move(index, -1)}
            disabled={index === 0}
            aria-label={`Subir prioridad de ${DIMENSION_INFO[dimension].label}`}
            className="rounded-lg px-2 py-1 text-stone-500 hover:bg-white disabled:opacity-30"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={() => move(index, 1)}
            disabled={index === value.length - 1}
            aria-label={`Bajar prioridad de ${DIMENSION_INFO[dimension].label}`}
            className="rounded-lg px-2 py-1 text-stone-500 hover:bg-white disabled:opacity-30"
          >
            ↓
          </button>
        </li>
      ))}
    </ol>
  );
}
