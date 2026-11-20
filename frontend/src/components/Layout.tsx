import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useAuth } from "@/auth/AuthContext";
import LoginDialog from "./LoginDialog";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-[13px] font-medium transition ${
    isActive ? "bg-amber-700 text-white" : "text-stone-600 hover:bg-amber-50 hover:text-amber-800"
  }`;

export default function Layout() {
  const { isAdmin, logout } = useAuth();
  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-[rgba(250,246,240,0.92)] px-4 py-3 backdrop-blur md:px-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
          <div className="flex items-center gap-6">
            <NavLink to="/catalogo" className="flex items-center gap-2.5" aria-label="Inicio">
              <span className="flex h-7 w-7 items-center justify-center rounded bg-amber-700">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
                  <rect x="1" y="1" width="5" height="7" rx="0.5" fill="white" />
                  <rect x="8" y="1" width="5" height="4" rx="0.5" fill="white" opacity="0.7" />
                  <rect x="8" y="7" width="5" height="6" rx="0.5" fill="white" opacity="0.5" />
                  <rect x="1" y="10" width="5" height="3" rx="0.5" fill="white" opacity="0.6" />
                </svg>
              </span>
              <span className="hidden font-mono text-[12px] font-semibold uppercase tracking-wider text-stone-600 sm:block">
                Revistas científicas
              </span>
            </NavLink>
            <nav className="flex gap-1" aria-label="Secciones">
              <NavLink to="/catalogo" className={navClass}>
                Catálogo
              </NavLink>
              <NavLink to="/recomendador" className={navClass}>
                Recomendador
              </NavLink>
            </nav>
          </div>

          {isAdmin ? (
            <div className="flex items-center gap-2">
              <span className="hidden rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-800 sm:inline">
                Modo editor
              </span>
              <button
                onClick={logout}
                className="rounded-lg px-3 py-2 text-[13px] text-stone-500 transition hover:bg-stone-100"
              >
                Salir
              </button>
            </div>
          ) : (
            <button
              onClick={() => setLoginOpen(true)}
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-[13px] font-medium text-stone-600 transition hover:bg-stone-50"
            >
              Editar
            </button>
          )}
        </div>
      </header>

      <Outlet />
      {loginOpen && <LoginDialog onClose={() => setLoginOpen(false)} />}
    </div>
  );
}
