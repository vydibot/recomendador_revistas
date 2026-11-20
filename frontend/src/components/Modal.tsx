import { type ReactNode, useEffect, useId } from "react";

interface ModalProps {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}

export default function Modal({ title, eyebrow, onClose, children, footer, wide }: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-stone-900/55 p-0 backdrop-blur-sm md:items-center md:p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`flex max-h-[92dvh] w-full flex-col rounded-t-3xl border border-stone-200 bg-white shadow-2xl md:rounded-2xl ${wide ? "md:max-w-3xl" : "md:max-w-lg"}`}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-stone-100 px-6 py-4">
          <div>
            {eyebrow && <p className="font-mono text-[11px] uppercase tracking-wider text-stone-400">{eyebrow}</p>}
            <h2 id={titleId} className="mt-0.5 font-serif text-lg font-semibold text-stone-900">
              {title}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-100 text-stone-500 transition hover:bg-stone-200"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex shrink-0 gap-3 border-t border-stone-100 px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}
