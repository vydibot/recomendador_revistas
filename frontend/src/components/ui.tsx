import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, useId } from "react";

const QUARTILE_STYLES: Record<string, string> = {
  Q1: "bg-emerald-100 text-emerald-800 border-emerald-300",
  Q2: "bg-cyan-100 text-cyan-800 border-cyan-300",
  Q3: "bg-orange-100 text-orange-800 border-orange-300",
  Q4: "bg-red-100 text-red-800 border-red-300",
};

export function QuartileBadge({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <span
      title="Cuartil SJR"
      className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-[11px] font-semibold ${QUARTILE_STYLES[value] ?? "border-stone-300 bg-stone-100 text-stone-600"}`}
    >
      {value}
    </span>
  );
}

export function PublindexBadge({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <span
      title="Categoría Publindex"
      className="inline-flex items-center rounded border border-amber-300 bg-amber-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-800"
    >
      {value}
    </span>
  );
}

export function Meta({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="mb-1 mr-4 inline-flex items-baseline gap-1">
      <span className="text-[11px] uppercase tracking-wider text-stone-400">{label}:</span>
      <span className="font-mono text-[12px] font-medium text-stone-700">{value}</span>
    </span>
  );
}

export function Chip({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  const base = "rounded-full border px-2.5 py-1 text-[11px] transition-all";
  if (!onClick) {
    return <span className={`${base} border-stone-200 bg-stone-100 text-stone-500`}>{children}</span>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`${base} active:scale-95 ${active ? "border-amber-700 bg-amber-700 text-white" : "border-stone-200 bg-stone-50 text-stone-500 hover:border-amber-400 hover:text-amber-700"}`}
    >
      {children}
    </button>
  );
}

const inputClass =
  "w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2.5 text-[13px] text-stone-700 transition focus:border-amber-500 focus:bg-white focus:outline-none";

export function Field({
  label,
  hint,
  span2,
  ...props
}: { label: string; hint?: string; span2?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className={span2 ? "col-span-2" : ""}>
      <label htmlFor={id} className="mb-1.5 block font-mono text-[11px] uppercase tracking-wider text-stone-400">
        {label}
        {props.required && <span className="text-amber-600"> *</span>}
      </label>
      <input id={id} className={inputClass} {...props} />
      {hint && <p className="mt-1 text-[11px] text-stone-400">{hint}</p>}
    </div>
  );
}

export function SelectField({
  label,
  children,
  ...props
}: { label: string; children: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[12px] font-medium text-stone-600">
        {label}
      </label>
      <select id={id} className={inputClass} {...props}>
        {children}
      </select>
    </div>
  );
}

export function PrimaryButton({ className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded-xl bg-amber-700 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-amber-800 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    />
  );
}

export function SecondaryButton({ className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded-xl border border-stone-300 bg-white px-4 py-2.5 text-[13px] font-medium text-stone-600 transition hover:bg-stone-50 disabled:opacity-50 ${className}`}
    />
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "info"; children: ReactNode }) {
  const style =
    kind === "error"
      ? "border-red-200 bg-red-50 text-red-800"
      : "border-amber-200 bg-amber-50 text-amber-900";
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`rounded-xl border p-3 text-[13px] ${style}`}>
      {children}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-[13px] text-stone-500" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-stone-300 border-t-amber-700" />
      {label}
    </div>
  );
}

export { inputClass };
